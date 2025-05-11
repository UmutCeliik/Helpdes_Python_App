# user_service/main.py
from fastapi import FastAPI, HTTPException, status, Depends
from pydantic import EmailStr # Kullanılmıyor gibi ama kalabilir
from typing import Annotated, Dict, Any, List # List eklendi
import uuid
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateSchema
from sqlalchemy.exc import ProgrammingError, IntegrityError

# Ortak ve yerel modülleri import et
from database_pkg.database import engine, Base, get_db
from database_pkg import db_models
from database_pkg.schemas import Role as RoleEnum # database_pkg.schemas'dan Role enum'ı
from . import models # Güncellenmiş Pydantic modelleriniz
from . import crud
from .auth import get_current_user_payload # Token korumalı endpointler için
from .config import get_settings, Settings # config.py'den settings

# --- SADECE BİR KERE app TANIMI ---
app = FastAPI(title="User Service API - Keycloak Integrated")

# --- Veritabanı Şema ve Tablo Oluşturma ---
def create_db_and_tables():
    print("User Service: Veritabanı şemaları ve tabloları oluşturuluyor/kontrol ediliyor...")
    _ = db_models.User.__table__
    # Ticket tablosunun user_service tarafından oluşturulması ideal değil,
    # ancak mevcut yapınızda var olduğu için bırakıyorum.
    # Uzun vadede her servis kendi tablolarını veya ortak bir migration sistemi yönetmeli.
    _ = db_models.Ticket.__table__

    schemas_to_create = []
    if db_models.User.__table_args__ and 'schema' in db_models.User.__table_args__:
        schemas_to_create.append(db_models.User.__table_args__['schema'])
    if db_models.Ticket.__table_args__ and 'schema' in db_models.Ticket.__table_args__:
        schemas_to_create.append(db_models.Ticket.__table_args__['schema'])
    
    unique_schemas = set(s for s in schemas_to_create if s) # None olmayan ve benzersiz şemalar

    for schema_name in unique_schemas:
        try:
            with engine.connect() as connection:
                connection.execute(CreateSchema(schema_name, if_not_exists=True))
                connection.commit()
            print(f"User Service: '{schema_name}' şeması kontrol edildi/oluşturuldu.")
        except ProgrammingError:
            print(f"User Service: Şema '{schema_name}' zaten mevcut veya oluşturulamadı (izin sorunu olabilir).")
        except Exception as e:
            print(f"User Service: Şema '{schema_name}' oluşturulurken beklenmedik hata: {e}")
    try:
        Base.metadata.create_all(bind=engine)
        print("User Service: Veritabanı tabloları başarıyla kontrol edildi/oluşturuldu.")
    except Exception as e:
        print(f"User Service: Tablolar oluşturulurken HATA: {e}")
        import traceback
        traceback.print_exc()

create_db_and_tables()
# --- Veritabanı Kurulum Sonu ---

@app.get("/")
async def read_root_main(settings: Settings = Depends(get_settings)): # Fonksiyon adını değiştirdim
    print(f"UserService Root - Configured Audience: {settings.keycloak.audience}") # Test için
    return {"message": "User Service API'ye hoş geldiniz! (Keycloak Odaklı)"}

@app.post("/users/sync-from-keycloak", response_model=models.User, summary="Keycloak kullanıcısını lokal DB ile senkronize et/oluştur (JIT)")
async def sync_user_from_keycloak(
    user_data_from_service: models.UserCreateInternal, # ticket_service'ten gelen payload
    db: Session = Depends(get_db)
):
    print(f"USER_SERVICE_MAIN: Received POST to /users/sync-from-keycloak for User ID: {user_data_from_service.id}, Email: {user_data_from_service.email}")
    
    db_user = crud.get_or_create_user(db, user_data=user_data_from_service)
    
    if not db_user:
        print(f"ERROR (UserService-Sync): crud.get_or_create_user failed for user ID {user_data_from_service.id}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Kullanıcı senkronizasyonu sırasında veritabanı hatası.")
    
    print(f"USER_SERVICE_MAIN: User {db_user.id} ({db_user.email}) synced/retrieved successfully from local DB.")
    return db_user # FastAPI otomatik olarak db_models.User'ı models.User'a dönüştürecek (from_attributes=True sayesinde)

@app.get("/users/me", response_model=models.User, summary="Mevcut login olmuş kullanıcının bilgilerini getir")
async def read_users_me(
    current_user_payload: Annotated[Dict[str, Any], Depends(get_current_user_payload)],
    db: Session = Depends(get_db)
):
    keycloak_id_str = current_user_payload.get("sub")
    if not keycloak_id_str:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Token'da 'sub' (Kullanıcı ID) bulunamadı.")
    
    try:
        keycloak_id_uuid = uuid.UUID(keycloak_id_str)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Token'daki 'sub' geçerli bir UUID değil.")

    db_user = crud.get_user_by_keycloak_id(db, keycloak_id=keycloak_id_uuid)
    
    if db_user is None:
        print(f"USER_SERVICE_MAIN: User for /users/me (sub: {keycloak_id_uuid}) not found locally. Attempting JIT provisioning.")
        
        keycloak_roles = current_user_payload.get("roles", [])
        if not keycloak_roles and current_user_payload.get("realm_access"):
            keycloak_roles = current_user_payload.get("realm_access", {}).get("roles", [])

        user_data_to_sync = models.UserCreateInternal(
            id=keycloak_id_uuid,
            email=current_user_payload.get("email", "no-email-provided@example.com"),
            full_name=current_user_payload.get("name") or \
                      f"{current_user_payload.get('given_name', '')} {current_user_payload.get('family_name', '')}".strip() or \
                      current_user_payload.get("preferred_username"),
            roles=keycloak_roles,
            is_active=current_user_payload.get("email_verified", True) # Keycloak'taki 'enabled' statusu daha iyi olabilir
        )
        db_user = crud.get_or_create_user(db, user_data=user_data_to_sync)
        if not db_user:
             raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı ve JIT provisioning ile senkronize edilemedi.")
    
    print(f"USER_SERVICE_MAIN: /users/me request for user_sub: {keycloak_id_uuid}, returning: {db_user.email}")
    return db_user

# Eski user creation ve internal endpoint'ler kaldırıldı.