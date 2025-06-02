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
from .auth import get_current_user_payload, verify_internal_secret # Token korumalı endpointler için
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

@app.post("/users/sync-from-keycloak", response_model=models.User, summary="Keycloak kullanıcısını lokal DB ile senkronize et/oluştur (JIT - İç Servis Çağrısı)")
async def sync_user_from_keycloak(
    # Artık token payload'u değil, doğrudan request body'sinden UserCreateInternal bekliyoruz.
    # FastAPI, gelen JSON'u bu Pydantic modeline göre otomatik olarak doğrular.
    user_data_to_sync: models.UserCreateInternal,
    # Yeni eklediğimiz dahili sır doğrulama dependency'si.
    # Bu fonksiyon çalışmadan önce verify_internal_secret çalışacak. Başarısız olursa endpoint hiç çalışmaz.
    is_internal_request_valid: bool = Depends(verify_internal_secret),
    db: Session = Depends(get_db)
):
    """
    Başka bir backend servisinden (örn: ticket_service) gelen JIT provisioning
    isteğini işler. İstek, 'X-Internal-Secret' başlığı ile doğrulanmalıdır.
    Gelen kullanıcı verilerini (request body'sinden alınır) kullanarak lokal
    veritabanında kullanıcıyı oluşturur veya günceller.
    """
    # Eğer kod buraya ulaştıysa, verify_internal_secret dependency'si başarılı olmuştur.
    # (is_internal_request_valid değişkenini kullanmak zorunda değiliz, dependency'nin varlığı yeterli)

    # Gelen verinin Pydantic modeli (user_data_to_sync) zaten doğrulandı.
    # crud.get_or_create_user fonksiyonuna doğrudan bu modeli verebiliriz.
    print(f"USER_SERVICE_MAIN (sync): Dahili istekten kullanıcı senkronize ediliyor: ID={user_data_to_sync.id}, Email={user_data_to_sync.email}")

    try:
        # crud fonksiyonumuz zaten UserCreateInternal modelini bekliyordu 
        db_user = crud.get_or_create_user(db, user_data=user_data_to_sync)
        if not db_user:
            # crud.get_or_create_user None dönerse (beklenmedik bir durum)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Kullanıcı senkronizasyonu sırasında bir hata oluştu.")

        # crud.get_or_create_user, db_models.User döndürür.
        # response_model=models.User olduğu için FastAPI bunu otomatik olarak Pydantic modeline dönüştürür.
        # Not: Bu otomatik dönüşüm, models.User içindeki 'roles' alanını nasıl dolduracak?
        #      Eğer from_attributes=True kullanılıyorsa ve db_models.User'da 'roles' ilişkisi yoksa,
        #      Pydantic modeli 'roles' alanını boş liste yapabilir veya DB'deki tek 'role' (enum) ile doldurmaya çalışabilir.
        #      API yanıtında token'daki rolleri görmek istiyorsak, /users/me endpoint'indeki gibi manuel dönüşüm gerekebilir.
        #      Şimdilik otomatik dönüşüme bırakıyoruz, testlerde yanıtı kontrol ederiz.
        print(f"USER_SERVICE_MAIN (sync): Kullanıcı {db_user.id} başarıyla senkronize edildi/getirildi.")
        return db_user

    except IntegrityError as e:
        db.rollback() # Hata durumunda işlemi geri al
        print(f"HATA (UserService-Sync): Senkronizasyon sırasında IntegrityError: {e}")
        # Bu genellikle e-posta zaten başka bir kullanıcı tarafından kullanılıyorsa olur.
        # crud.get_or_create_user normalde bunu yakalayıp güncelleme yapmalı.
        # Eğer yine de bu hata alınıyorsa, farklı bir sorun olabilir. 409 Conflict döndürelim.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Kullanıcı senkronizasyonu sırasında veritabanı çakışması.")
    except Exception as e:
        db.rollback()
        print(f"HATA (UserService-Sync): Senkronizasyon sırasında beklenmedik hata: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Kullanıcı senkronizasyonu sırasında beklenmedik sunucu hatası.")


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

@app.get("/users/me", response_model=models.User, summary="Mevcut login olmuş kullanıcının bilgilerini getir")
async def read_users_me(
    current_user_payload: Annotated[Dict[str, Any], Depends(get_current_user_payload)],
    db: Session = Depends(get_db)
):
    """
    Gelen geçerli JWT token'ına ait kullanıcının bilgilerini döndürür.
    Kullanıcı lokal veritabanında yoksa, token'dan alınan bilgilerle
    Just-In-Time (JIT) olarak oluşturulur.
    """
    keycloak_id_str = current_user_payload.get("sub")
    if not keycloak_id_str:
        # Bu durum normalde get_current_user_payload tarafından yakalanmalı, ama yine de kontrol edelim.
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token'da 'sub' (Kullanıcı ID) bulunamadı.")

    try:
        keycloak_id_uuid = uuid.UUID(keycloak_id_str)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token'daki 'sub' geçerli bir UUID değil.")

    # 1. Kullanıcıyı lokal DB'de ara
    db_user = crud.get_user_by_keycloak_id(db, keycloak_id=keycloak_id_uuid)

    if db_user is None:
        # 2. JIT Provisioning: Kullanıcı lokalde yok, token bilgileriyle oluştur
        print(f"USER_SERVICE_MAIN (/users/me): User (sub: {keycloak_id_uuid}) not found locally. Attempting JIT provisioning.")

        # Keycloak rollerini al (string listesi olarak)
        keycloak_roles = current_user_payload.get("roles", [])
        if not keycloak_roles and current_user_payload.get("realm_access"):
            keycloak_roles = current_user_payload.get("realm_access", {}).get("roles", [])

        # Token'dan gelen bilgilerle UserCreateInternal modelini doldur
        user_data_to_sync = models.UserCreateInternal(
            id=keycloak_id_uuid,
            # Email ve full_name Pydantic/DB modelinde zorunluysa ve token'da yoksa placeholder kullan
            email=current_user_payload.get("email", f"placeholder-{keycloak_id_uuid}@example.com"),
            full_name=current_user_payload.get("name") or \
                      f"{current_user_payload.get('given_name', '')} {current_user_payload.get('family_name', '')}".strip() or \
                      current_user_payload.get("preferred_username", f"user-{keycloak_id_uuid}"),
            roles=keycloak_roles, # Keycloak'tan gelen roller
            is_active=current_user_payload.get("email_verified", True) # Keycloak'tan 'enabled' durumu alınabilir veya email_verified kullanılabilir
        )

        try:
            # crud.get_or_create_user fonksiyonu kullanıcıyı oluşturur veya günceller (varsa)
            db_user = crud.get_or_create_user(db, user_data=user_data_to_sync)
            if not db_user: # Eğer bir şekilde kullanıcı oluşturulamazsa
                 raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Kullanıcı senkronizasyonu sırasında bir hata oluştu.")
            print(f"USER_SERVICE_MAIN (/users/me): User (sub: {keycloak_id_uuid}) JIT provisioned successfully.")
        except IntegrityError as e:
             # Genellikle email unique constraint hatası olabilir. Rollback yap ve tekrar sorgula.
             db.rollback()
             print(f"ERROR (UserService-/users/me-JIT): IntegrityError during JIT provisioning: {e}. Rolling back and re-fetching.")
             db_user = crud.get_user_by_keycloak_id(db, keycloak_id=keycloak_id_uuid)
             if not db_user: # Tekrar sorgulamada da bulunamazsa, beklenmedik bir durum.
                 raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="JIT provisioning sırasında veritabanı hatası ve kullanıcı bulunamadı.")
        except Exception as e:
             db.rollback()
             print(f"ERROR (UserService-/users/me-JIT): Unexpected error during JIT provisioning: {e}")
             raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="JIT provisioning sırasında beklenmedik sunucu hatası.")

    # 3. Kullanıcı bilgilerini response_model'e (models.User) uygun olarak döndür
    # DB'den gelen kullanıcı bilgisini ve token'daki rolleri birleştirerek Pydantic modelini oluşturuyoruz.
    user_response = models.User(
        id=db_user.id,
        email=db_user.email,
        full_name=db_user.full_name,
        is_active=db_user.is_active,
        created_at=db_user.created_at,
        # response_model'deki 'roles' alanı string listesi bekliyor , bu yüzden token'daki rolleri kullanıyoruz.
        roles=current_user_payload.get("roles", []) or current_user_payload.get("realm_access", {}).get("roles", [])
        # Not: İsterseniz db_user.role (RoleEnum) bilgisini de farklı bir alanda döndürebilirsiniz.
    )
    return user_response