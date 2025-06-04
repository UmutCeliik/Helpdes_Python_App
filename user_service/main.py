# user_service/main.py
from fastapi import FastAPI, HTTPException, status, Depends
from pydantic import EmailStr # Kullanılmıyor gibi ama kalabilir
from typing import Annotated, Dict, Any, List # List eklendi
import uuid
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateSchema
from sqlalchemy.exc import ProgrammingError, IntegrityError
from fastapi.middleware.cors import CORSMiddleware
# Ortak ve yerel modülleri import et
from database_pkg.database import engine, Base, get_db
from database_pkg import db_models
from database_pkg.schemas import Role as RoleEnum # database_pkg.schemas'dan Role enum'ı
from . import models # Güncellenmiş Pydantic modelleriniz
from . import crud
from .auth import get_current_user_payload, verify_internal_secret # Token korumalı endpointler için
from .config import get_settings, Settings # config.py'den settings
from . import company_crud # Company CRUD fonksiyonları
from . import keycloak_api_helpers # Keycloak'ta grup oluşturma helper'ı
from database_pkg import schemas as common_schemas # CompanyCreate Pydantic modeli için
from .models import TenantCreateRequest # API isteği için Pydantic modeli

# --- SADECE BİR KERE app TANIMI ---
app = FastAPI(title="User Service API - Keycloak Integrated")

origins = [
    "http://localhost:5173",  # Vue frontend'inizin çalıştığı adres
    "http://localhost:8080",  # Gerekirse diğer origin'ler
    # Production için gerçek domain adreslerinizi eklemeyi unutmayın
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"], # OPTIONS dahil tüm metodlara izin ver
    allow_headers=["*"], # Tüm başlıklara izin ver (Authorization dahil)
)

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

@app.post("/admin/tenants", response_model=common_schemas.Company, status_code=status.HTTP_201_CREATED, summary="Yeni bir tenant (müşteri şirketi) oluşturur (Sadece General Admin)")
async def create_new_tenant(
    tenant_request: TenantCreateRequest, # Request body'den tenant adı alınacak
    current_user_payload: Annotated[Dict[str, Any], Depends(get_current_user_payload)],
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings)
):
    user_roles = current_user_payload.get("roles", [])
    if not user_roles and current_user_payload.get("realm_access"):
        user_roles = current_user_payload.get("realm_access", {}).get("roles", [])

    # 1. Yetki Kontrolü: Sadece 'general-admin' bu işlemi yapabilir
    if "general-admin" not in user_roles:
        print(f"HATA (POST /admin/tenants): Yetkisiz erişim denemesi. Kullanıcı rolleri: {user_roles}")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bu işlemi yapma yetkiniz yok.")

    print(f"INFO (POST /admin/tenants): General admin '{current_user_payload.get('sub')}' trying to create tenant with name: '{tenant_request.name}'")

    # 2. Mevcut Tenant Adı Kontrolü (Lokal DB'de)
    existing_company_by_name = company_crud.get_company_by_name(db, name=tenant_request.name)
    if existing_company_by_name:
        print(f"HATA (POST /admin/tenants): Tenant name '{tenant_request.name}' already exists locally with ID {existing_company_by_name.id}.")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"'{tenant_request.name}' adlı şirket zaten mevcut.")

    # 3. Keycloak'ta Yeni Grup Oluşturma
    # Not: Keycloak'ta grup adları benzersiz olmak zorunda değildir, ama biz kendi sistemimizde benzersiz isim istiyoruz.
    # Keycloak'ta grup oluştururken path genellikle "/{group_name}" şeklinde olur.
    created_keycloak_group_id_str = await keycloak_api_helpers.create_keycloak_group(
        group_name=tenant_request.name, # Keycloak grup adı olarak tenant adını kullanıyoruz
        settings=settings
    )

    if created_keycloak_group_id_str is None:
        print(f"HATA (POST /admin/tenants): Keycloak'ta '{tenant_request.name}' grubu oluşturulamadı (helper None döndü).")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Keycloak'ta müşteri grubu oluşturulurken bir hata oluştu.")
    
    if created_keycloak_group_id_str == "EXISTS":
        # Bu durum, create_keycloak_group helper'ında grup zaten var diye 409 Conflict alındığında dönüyor.
        # Bu durumda, bu isimle lokalde de bir kayıt var mı diye tekrar kontrol edebiliriz
        # veya doğrudan hata verebiliriz çünkü yeni bir tenant oluşturmaya çalışıyoruz.
        print(f"HATA (POST /admin/tenants): Keycloak'ta '{tenant_request.name}' adında bir grup zaten mevcut.")
        # Belki bu Keycloak grubuna ait lokal bir Company kaydı var mı diye kontrol edip, yoksa oluşturulabilir.
        # Şimdilik, eğer Keycloak'ta varsa ve biz yeni oluşturmaya çalışıyorsak, bu bir çakışmadır.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"'{tenant_request.name}' adında bir Keycloak grubu zaten mevcut.")

    try:
        keycloak_group_uuid = uuid.UUID(created_keycloak_group_id_str)
    except ValueError:
        print(f"HATA (POST /admin/tenants): Keycloak'tan dönen grup ID'si ('{created_keycloak_group_id_str}') geçerli bir UUID değil.")
        # Bu durumda Keycloak'ta oluşturulan grubu silmek veya durumu loglamak gerekebilir.
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Keycloak'tan geçersiz grup ID formatı alındı.")

    # 4. Keycloak Grup ID'sinin Lokal DB'de Zaten Kullanılmadığından Emin Olma
    existing_company_by_kc_id = company_crud.get_company_by_keycloak_group_id(db, keycloak_group_id=keycloak_group_uuid)
    if existing_company_by_kc_id:
        print(f"HATA (POST /admin/tenants): Keycloak group ID '{keycloak_group_uuid}' already linked to local company '{existing_company_by_kc_id.name}'. This is an inconsistency.")
        # Bu çok beklenmedik bir durum, Keycloak'ta yeni oluşturulan bir grubun ID'sinin bizde daha önce kayıtlı olması.
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Kritik sistem hatası: Keycloak grup ID çakışması.")

    # 5. Yeni Şirketi (Tenant) Lokal Veritabanına Kaydetme
    company_to_create = common_schemas.CompanyCreate(
        name=tenant_request.name,
        keycloak_group_id=keycloak_group_uuid,
        status="active" # Yeni tenant varsayılan olarak aktif
    )
    
    try:
        db_company = company_crud.create_company(db=db, company=company_to_create)
        print(f"INFO (POST /admin/tenants): Tenant '{db_company.name}' (ID: {db_company.id}) created successfully with Keycloak Group ID: {db_company.keycloak_group_id}")
        return db_company
    except IntegrityError as e: # Veritabanında name veya keycloak_group_id unique constraint hatası
        db.rollback()
        print(f"HATA (POST /admin/tenants): Veritabanına şirket kaydedilirken IntegrityError: {e}")
        # Bu noktada Keycloak'ta oluşturulan grubu silmek iyi bir pratik olabilir (rollback mekanizması).
        # Şimdilik basit hata mesajı dönüyoruz.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Şirket adı veya Keycloak ID'si veritabanında zaten mevcut.")
    except Exception as e:
        db.rollback()
        print(f"HATA (POST /admin/tenants): Veritabanına şirket kaydedilirken beklenmedik hata: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Şirket veritabanına kaydedilirken bir hata oluştu.")

@app.get("/admin/tenants", response_model=common_schemas.CompanyList, summary="Tüm tenantları (müşteri şirketlerini) listeler (Sadece General Admin)")
async def list_tenants(
    current_user_payload: Annotated[Dict[str, Any], Depends(get_current_user_payload)],
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 100
):
    user_roles = current_user_payload.get("roles", [])
    if not user_roles and current_user_payload.get("realm_access"):
        user_roles = current_user_payload.get("realm_access", {}).get("roles", [])

    if "general-admin" not in user_roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bu işlemi yapma yetkiniz yok.")

    print(f"INFO (GET /admin/tenants): General admin '{current_user_payload.get('sub')}' listing tenants. Skip: {skip}, Limit: {limit}")
    
    companies = company_crud.get_companies(db, skip=skip, limit=limit)
    total_companies = company_crud.count_companies(db) # Toplam sayıyı almak için yeni bir CRUD fonksiyonu ekledik
    
    return common_schemas.CompanyList(items=companies, total=total_companies)

@app.get("/admin/tenants/{company_id}", response_model=common_schemas.Company, summary="Belirli bir tenantın detaylarını getirir (Sadece General Admin)")
async def get_tenant_details(
    company_id: uuid.UUID, # Path parametresi olarak tenant'ın yerel DB ID'si
    current_user_payload: Annotated[Dict[str, Any], Depends(get_current_user_payload)],
    db: Session = Depends(get_db)
):
    user_roles = current_user_payload.get("roles", [])
    if not user_roles and current_user_payload.get("realm_access"):
        user_roles = current_user_payload.get("realm_access", {}).get("roles", [])

    if "general-admin" not in user_roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bu işlemi yapma yetkiniz yok.")

    print(f"INFO (GET /admin/tenants/{{company_id}}): General admin '{current_user_payload.get('sub')}' requesting details for company ID: {company_id}")
    
    db_company = company_crud.get_company(db, company_id=company_id)
    if db_company is None:
        print(f"WARN (GET /admin/tenants/{{company_id}}): Company with ID {company_id} not found.")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Şirket (tenant) bulunamadı.")
    
    return db_company

@app.patch("/admin/tenants/{company_id}", response_model=common_schemas.Company, summary="Belirli bir tenantın statüsünü veya adını günceller (Sadece General Admin)")
async def update_tenant_status(
    company_id: uuid.UUID, # Path parametresi olarak güncellenecek şirketin ID'si
    company_update_request: common_schemas.CompanyUpdate, # Request body'den gelecek güncelleme verisi (örn: {"status": "inactive"})
    current_user_payload: Annotated[Dict[str, Any], Depends(get_current_user_payload)],
    db: Session = Depends(get_db)
):
    user_roles = current_user_payload.get("roles", [])
    if not user_roles and current_user_payload.get("realm_access"):
        user_roles = current_user_payload.get("realm_access", {}).get("roles", [])

    # 1. Yetki Kontrolü: Sadece 'general-admin' bu işlemi yapabilir
    if "general-admin" not in user_roles:
        print(f"HATA (PATCH /admin/tenants/{company_id}): Yetkisiz erişim denemesi. Kullanıcı rolleri: {user_roles}")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bu işlemi yapma yetkiniz yok.")

    log_prefix = f"INFO (PATCH /admin/tenants/{company_id} User: {current_user_payload.get('sub')}):"
    print(f"{log_prefix} Attempting to update company.")

    # 2. Güncellenecek Şirketi Veritabanından Al
    db_company = company_crud.get_company(db, company_id=company_id)
    if db_company is None:
        print(f"{log_prefix} Company with ID {company_id} not found.")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Güncellenecek şirket (tenant) bulunamadı.")

    # 3. İsim Güncellemesi Varsa ve Yeni İsim Başka Bir Şirkete Aitse Kontrol Et
    if company_update_request.name is not None and company_update_request.name != db_company.name:
        existing_company_with_new_name = company_crud.get_company_by_name(db, name=company_update_request.name)
        if existing_company_with_new_name and existing_company_with_new_name.id != company_id:
            print(f"{log_prefix} Attempt to update company name to '{company_update_request.name}', but this name is already used by company ID {existing_company_with_new_name.id}.")
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"'{company_update_request.name}' adlı şirket zaten mevcut.")
        # TODO: Eğer isim güncelleniyorsa, Keycloak'taki grup adını da güncellemek gerekir mi? (Bu daha karmaşık bir işlem)
        # Şimdilik sadece lokal DB'deki adı güncelliyoruz. Keycloak grup adı sabit kalıyor.

    # 4. Şirketi Güncelle (company_crud.update_company zaten bunu yapıyor)
    # company_update_request Pydantic modeli sadece gönderilen alanları içerecektir (exclude_unset=True sayesinde)
    updated_company = company_crud.update_company(db=db, company_db=db_company, company_in=company_update_request)
    
    print(f"{log_prefix} Company '{updated_company.name}' (ID: {updated_company.id}) updated successfully. Status: {updated_company.status}")
    return updated_company

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