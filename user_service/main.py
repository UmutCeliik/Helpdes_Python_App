# user_service/main.py
from fastapi import FastAPI, HTTPException, status, Depends
from pydantic import EmailStr
from typing import Annotated, Dict, Any, List
import uuid
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateSchema
from sqlalchemy.exc import ProgrammingError, IntegrityError
from .auth import get_current_user_payload

# Ortak ve yerel modülleri import et
from database_pkg.database import engine, Base, get_db
from database_pkg import db_models # Tüm DB modelleri burada
from database_pkg.schemas import Role
from . import models # Kendi Pydantic modelleri (UserInternal dahil)
from . import crud

app = FastAPI(title="User Service API - Keycloak Integrated")

# --- Veritabanı Şema ve Tablo Oluşturma ---
# Sadece bir serviste (örn. burada) yapılmalı
def create_db_and_tables():
    print("User Service: Veritabanı şemaları ve tabloları oluşturuluyor/kontrol ediliyor...")
    # User modelinin güncel olduğundan emin ol (hashed_password kaldırıldı)
    _ = db_models.User.__table__ 
    # Ticket tablosunu user_service oluşturmamalı, ama mevcut kodda olduğu için bırakıyorum
    _ = db_models.Ticket.__table__ 

    schemas_to_create = [db_models.User.__table_args__.get('schema'),
                       db_models.Ticket.__table_args__.get('schema')] # Ticket şeması hala burada
    schemas_to_create = [s for s in schemas_to_create if s]

    for schema_name in set(schemas_to_create):
         try:
            with engine.connect() as connection:
                connection.execute(CreateSchema(schema_name, if_not_exists=True))
                connection.commit()
            print(f"User Service: '{schema_name}' şeması kontrol edildi/oluşturuldu.")
         except ProgrammingError: # Zaten varsa hata vermemesi için if_not_exists=True kullandık
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
async def read_root():
    return {"message": "User Service API'ye hoş geldiniz! (Keycloak Odaklı)"}

# Bu endpoint, diğer servisler (örn: ticket_service) tarafından bir kullanıcının
# lokal DB'de var olduğundan emin olmak ve gerekirse oluşturmak için çağrılabilir.
# Veya frontend'den bir token geldikten sonra ilk istekte çağrılabilir.
@app.post("/users/sync-from-keycloak", response_model=models.User, summary="Keycloak kullanıcısını lokal DB ile senkronize et/oluştur (JIT)")
async def sync_user_from_keycloak(
    current_user_payload: Annotated[Dict[str, Any], Depends(get_current_user_payload)], # Token'dan gelen payload
    db: Session = Depends(get_db)
):
    keycloak_id_str = current_user_payload.get("sub")
    if not keycloak_id_str:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Token'da 'sub' (Kullanıcı ID) bulunamadı.")

    try:
        keycloak_id_uuid = uuid.UUID(keycloak_id_str)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Token'daki 'sub' geçerli bir UUID değil.")

    # Keycloak rollerini al (string listesi olarak)
    keycloak_roles = current_user_payload.get("roles", [])
    if not keycloak_roles and current_user_payload.get("realm_access"):
        keycloak_roles = current_user_payload.get("realm_access", {}).get("roles", [])

    user_data_to_sync = models.UserCreateInternal(
        id=keycloak_id_uuid,
        email=current_user_payload.get("email", "no-email@provided.com"), # Email yoksa varsayılan
        full_name=current_user_payload.get("name") or \
                  f"{current_user_payload.get('given_name', '')} {current_user_payload.get('family_name', '')}".strip() or \
                  current_user_payload.get("preferred_username"),
        roles=keycloak_roles,
        is_active=current_user_payload.get("email_verified", True) # Veya Keycloak'taki 'enabled' status
    )

    print(f"USER_SERVICE_MAIN: Syncing user from Keycloak token: ID={user_data_to_sync.id}, Email={user_data_to_sync.email}")
    db_user = crud.get_or_create_user(db, user_data=user_data_to_sync)
    if not db_user:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Kullanıcı senkronizasyonu sırasında bir hata oluştu.")

    # Pydantic modeline dönüştürerek döndür (User modeline roles eklenmeli)
    return models.User.from_orm(db_user) # Eğer User modelinizde roles alanı varsa ve SQLAlchemy ilişkisiyle geliyorsa
                                         # Veya db_user'ı doğrudan döndürün eğer User modeli zaten uyumluysa
                                         # from_orm yerine model_validate kullanilabilir pydantic v2'de

# @app.get("/users/me", response_model=models.User, summary="Mevcut login olmuş kullanıcının bilgilerini getir")
# async def read_users_me(
#     current_user_payload: Annotated[Dict[str, Any], Depends(get_current_user_payload)], # Aktif edildiğinde
#     db: Session = Depends(get_db)
# ):
#     keycloak_id = uuid.UUID(current_user_payload.get("sub"))
#     db_user = crud.get_user_by_keycloak_id(db, keycloak_id=keycloak_id)
#     if db_user is None:
#         # JIT: Kullanıcı lokalde yoksa, token'dan gelen bilgilerle oluşturup döndür
#         print(f"USER_SERVICE_MAIN: User for /users/me (sub: {keycloak_id}) not found locally. Attempting JIT provisioning.")
#         user_data_to_sync = models.UserCreateInternal(
#             id=keycloak_id,
#             email=current_user_payload.get("email"),
#             full_name=current_user_payload.get("name") or f"{current_user_payload.get('given_name', '')} {current_user_payload.get('family_name', '')}".strip(),
#             roles=current_user_payload.get("roles", []) or current_user_payload.get("realm_access", {}).get("roles", []),
#             is_active=current_user_payload.get("email_verified", True) # Keycloak'taki 'enabled' ile senkronize et
#         )
#         db_user = crud.get_or_create_user(db, user_data=user_data_to_sync)
#         if not db_user: # Eğer JIT sonrası hala yoksa bir sorun vardır
#              raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı ve senkronize edilemedi.")
#     return db_user

# Eski /users/ POST ve /users/internal/by_email/{email} endpoint'lerini kaldırın.

app = FastAPI(title="User Service API")


@app.get("/")
async def read_root():
    return {"message": "User Service API'ye hoş geldiniz!"}

