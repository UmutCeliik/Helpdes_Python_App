# user_service/main.py
from __future__ import annotations

from fastapi import FastAPI, HTTPException, status, Depends, Header, Response
from typing import Annotated, Dict, Any, List, Optional # List eklendi
import uuid
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateSchema # Şema oluşturmak için
from sqlalchemy.exc import ProgrammingError, IntegrityError
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Ortak ve yerel modülleri import et
from database_pkg.database import engine, Base, get_db
from database_pkg import db_models # SQLAlchemy DB Modelleri
# from database_pkg.schemas import Role as RoleEnum # common_schemas.Role olarak kullanılacak
from database_pkg import schemas as common_schemas # Ortak Pydantic Şemaları (Role, Company vb.)

from . import models as user_models # user_service'e özel Pydantic modelleri
from . import crud as user_crud # user_service için CRUD fonksiyonları
from .auth import get_current_user_payload, verify_internal_secret # Token korumalı endpointler için
from .config import get_settings, Settings # config.py'den settings
from . import company_crud # Company CRUD fonksiyonları
from .keycloak_api_helpers import create_keycloak_group # Keycloak'ta grup oluşturma helper'ı
from . import keycloak_api_helpers

app = FastAPI(
    title="User Service API - Keycloak Integrated (Multi-Tenant Admin WIP)",
    description="User and Company (Tenant) Management Service for Helpdesk."
)

origins = [
    "http://localhost:5173",  # Vue frontend'inizin çalıştığı adres
    "http://localhost:8080",  # Gerekirse diğer origin'ler
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"], # OPTIONS dahil tüm metodlara izin ver
    allow_headers=["*"], # Tüm başlıklara izin ver (Authorization dahil)
)

class UserListResponse(BaseModel): # Yanıt için Pydantic modeli
    items: List[user_models.User]
    total: int

def _split_full_name(full_name: str) -> tuple[str, str]:
    parts = full_name.strip().split(maxsplit=1)
    first_name = parts[0] if parts else ""
    last_name = parts[1] if len(parts) > 1 else ""
    return first_name, last_name

@app.delete(
    "/admin/tenants/{company_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Belirli bir tenant'ı (Keycloak grubu ve lokal DB kaydı) siler (Sadece General Admin)"
)
async def delete_tenant_by_admin(
    company_id: uuid.UUID,
    current_user_payload: Annotated[Dict[str, Any], Depends(get_current_user_payload)],
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings)
):
    user_roles = current_user_payload.get("roles", [])
    if not user_roles and current_user_payload.get("realm_access"):
        user_roles = current_user_payload.get("realm_access", {}).get("roles", [])

    if "general-admin" not in user_roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bu işlemi yapma yetkiniz yok.")

    log_prefix = f"INFO (DELETE /admin/tenants/{company_id} - Admin: {current_user_payload.get('sub')}):"
    print(f"{log_prefix} Attempting to delete company (tenant) with ID: {company_id}")

    # 1. Lokal DB'den şirketi (tenant'ı) bul
    db_company = company_crud.get_company(db, company_id=company_id)
    if not db_company:
        print(f"WARN ({log_prefix}): Company with ID {company_id} not found in local DB. Nothing to delete.")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Silinecek şirket (tenant) bulunamadı.")

    # 2. Keycloak'taki ilişkili grubu sil (eğer keycloak_group_id varsa)
    if db_company.keycloak_group_id:
        print(f"{log_prefix} Attempting to delete Keycloak group with ID: {db_company.keycloak_group_id} (associated with company '{db_company.name}')")
        keycloak_group_deleted_successfully = await keycloak_api_helpers.delete_keycloak_group(
            group_id=str(db_company.keycloak_group_id), # Helper str bekliyor olabilir
            settings=settings
        )
        if not keycloak_group_deleted_successfully:
            # delete_keycloak_group helper'ı 404 durumunda (zaten silinmiş) True dönecek şekilde ayarlanmıştı.
            # Bu nedenle False dönüşü, beklenmedik bir silme hatası anlamına gelir.
            print(f"HATA ({log_prefix}): Keycloak group (ID: {db_company.keycloak_group_id}) could not be deleted. Local company record will NOT be deleted to maintain consistency for investigation.")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Keycloak'ta şirket grubu silinirken bir sorun oluştu. Lokal kayıt silinmedi. Lütfen sistem yöneticisi ile iletişime geçin."
            )
        print(f"{log_prefix} Keycloak group (ID: {db_company.keycloak_group_id}) deleted successfully (or was already not present).")
    else:
        print(f"UYARI ({log_prefix}): Company '{db_company.name}' (ID: {company_id}) does not have an associated Keycloak group ID in local DB. Skipping Keycloak group deletion.")

    # 3. Lokal DB'den şirketi (tenant'ı) sil
    # ÖNEMLİ NOT: Bu aşamada, bu şirkete bağlı kullanıcılar veya biletler varsa ne olacağı düşünülmelidir.
    # Foreign key kısıtlamaları nedeniyle bu silme işlemi başarısız olabilir veya
    # bu bağımlı kayıtların da silinmesi/güncellenmesi gerekebilir (CASCADE, SET NULL vb.).
    # Şimdilik, doğrudan silmeyi deniyoruz. CRUD fonksiyonu bu durumu ele alabilir.
    
    deleted_company_from_db = company_crud.delete_company(db, company_id=company_id)
    if deleted_company_from_db is None: # delete_company bulamazsa None döner, ama yukarıda zaten bulduk. Bu bir tutarlılık kontrolü.
        print(f"HATA ({log_prefix}): Company (ID: {company_id}) was found but could not be deleted from local DB. This is unexpected.")
        # Keycloak grubu silinmiş olabilir. Manuel müdahale gerekebilir.
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Şirket lokal veritabanından silinirken bir sorun oluştu.")
    
    print(f"{log_prefix} Company '{deleted_company_from_db.name}' (ID: {company_id}) and its Keycloak group (if associated) have been deleted.")
    
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@app.delete(
    "/admin/users/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Belirli bir kullanıcıyı sistemden (Keycloak ve lokal DB) siler (Sadece General Admin)"
)
async def admin_delete_user(
    user_id: uuid.UUID, # Path parametresi olarak kullanıcı ID'si
    current_admin_payload: Annotated[Dict[str, Any], Depends(get_current_user_payload)],
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings)
):
    admin_roles = current_admin_payload.get("roles", [])
    if not admin_roles and current_admin_payload.get("realm_access"):
        admin_roles = current_admin_payload.get("realm_access", {}).get("roles", [])

    if "general-admin" not in admin_roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bu işlemi yapma yetkiniz yok.")

    log_prefix = f"INFO (DELETE /admin/users/{user_id} - Admin: {current_admin_payload.get('sub')}):"
    print(f"{log_prefix} Attempting to delete user with ID: {user_id}")

    # 1. Keycloak'tan kullanıcıyı silmeyi dene
    # delete_keycloak_user helper'ı, kullanıcı bulunamazsa (404) da True döner (silinmiş kabul edilir).
    # Sadece beklenmedik bir hata durumunda False döner.
    kc_user_deleted_successfully = await keycloak_api_helpers.delete_keycloak_user(str(user_id), settings)

    if not kc_user_deleted_successfully:
        # Bu durum, helper içinde loglanmış bir silme hatası (404 dışında) anlamına gelir.
        print(f"HATA ({log_prefix}): Kullanıcı Keycloak'ta silinirken bir sorun oluştu (ID: {user_id}). Lokal veritabanı silme işlemi denenmeyecek.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Kullanıcı Keycloak'ta silinirken bir sorun oluştu. Lokal veritabanı etkilenmedi."
        )
    
    print(f"{log_prefix} User (ID: {user_id}) successfully deleted from Keycloak (or was not found).")

    # 2. Lokal veritabanından kullanıcıyı sil
    # Bu işlem, Keycloak'tan silme başarılı olduktan sonra (veya kullanıcı zaten Keycloak'ta yoksa) yapılır.
    deleted_db_user = user_crud.delete_user_by_keycloak_id(db, keycloak_id=user_id)

    if deleted_db_user:
        print(f"{log_prefix} User (ID: {user_id}, Email: {deleted_db_user.email}) also deleted from local DB.")
    else:
        # Bu durum, kullanıcının Keycloak'ta silindiği (veya zaten olmadığı)
        # ancak lokal DB'de de bulunamadığı anlamına gelir. Bu genellikle beklenen bir durumdur
        # eğer kullanıcı daha önce hiç senkronize edilmemişse veya zaten silinmişse.
        print(f"BİLGİ ({log_prefix}): User (ID: {user_id}) was not found in local DB (possibly already deleted or never synced).")

    # Her iki silme işlemi de "başarılı" (yani kullanıcı artık sistemde tanımlı değil) ise 204 dön.
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@app.post(
    "/admin/users",
    response_model=user_models.User,
    status_code=status.HTTP_201_CREATED,
    summary="Yeni bir kullanıcı oluşturur (Keycloak + Lokal DB) (Sadece General Admin)"
)
async def admin_create_user(
    request_data: user_models.AdminUserCreateRequest,
    current_user_payload: Annotated[Dict[str, Any], Depends(get_current_user_payload)],
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings)
):
    user_roles_from_token = current_user_payload.get("roles", [])
    if not user_roles_from_token and current_user_payload.get("realm_access"):
        user_roles_from_token = current_user_payload.get("realm_access", {}).get("roles", [])

    if "general-admin" not in user_roles_from_token:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bu işlemi yapma yetkiniz yok.")

    log_prefix = f"INFO (POST /admin/users - Admin: {current_user_payload.get('sub')}):"
    print(f"{log_prefix} Attempting to create user with email: {request_data.email}")

    # 1. Tenant/Grup ID'sini Belirle (Eğer request_data.tenant_id sağlanmışsa)
    keycloak_group_id_to_assign: Optional[str] = None
    if request_data.tenant_id:
        company = company_crud.get_company(db, company_id=request_data.tenant_id)
        if not company:
            print(f"HATA ({log_prefix}): Belirtilen tenant_id ({request_data.tenant_id}) ile şirket bulunamadı.")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Belirtilen tenant ID ({request_data.tenant_id}) ile şirket bulunamadı.")
        if not company.keycloak_group_id:
            print(f"HATA ({log_prefix}): Şirketin ({company.name}) Keycloak grup ID'si lokal DB'de kayıtlı değil.")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Şirketin Keycloak grup ID yapılandırması eksik.")
        keycloak_group_id_to_assign = str(company.keycloak_group_id)
        print(f"{log_prefix} User will be assigned to Keycloak group ID: {keycloak_group_id_to_assign} (Tenant: {company.name})")

    # 2. Keycloak'ta Kullanıcı Oluştur
    first_name, last_name = _split_full_name(request_data.full_name)
    user_representation_for_kc = {
        "username": request_data.email, # Keycloak'ta username genellikle email ile aynıdır veya email'den türetilir
        "email": request_data.email,
        "firstName": first_name,
        "lastName": last_name,
        "enabled": request_data.is_active,
        "emailVerified": True # Yeni oluşturulan kullanıcıları genellikle doğrulanmış kabul edebiliriz
    }
    
    new_kc_user_id_str = await keycloak_api_helpers.create_keycloak_user(user_representation_for_kc, settings)

    if new_kc_user_id_str is None:
        # keycloak_api_helpers.create_keycloak_user içinde zaten detaylı loglama yapılıyor olmalı
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Keycloak'ta kullanıcı oluşturulurken bir hata oluştu. Logları kontrol edin.")
    if new_kc_user_id_str == "EXISTS":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"'{request_data.email}' e-posta adresine veya kullanıcı adına sahip bir kullanıcı Keycloak'ta zaten mevcut.")
    
    print(f"{log_prefix} User created in Keycloak with ID: {new_kc_user_id_str}")

    # 3. Keycloak'ta Şifre Ata
    password_set_success = await keycloak_api_helpers.set_keycloak_user_password(
        user_id=new_kc_user_id_str,
        password=request_data.password,
        temporary=True, # Kullanıcı ilk girişte şifresini değiştirsin
        settings=settings
    )
    if not password_set_success:
        # İdealde burada Keycloak'ta oluşturulan kullanıcı silinmeli (telafi işlemi).
        # Şimdilik sadece hata loglayıp 500 dönüyoruz.
        print(f"KRİTİK HATA ({log_prefix}): Kullanıcı Keycloak'ta oluşturuldu (ID: {new_kc_user_id_str}) ANCAK şifresi ayarlanamadı!")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Kullanıcı şifresi Keycloak'ta ayarlanamadı. Kullanıcı eksik yapılandırılmış olabilir.")

    # 4. Keycloak'ta Rol Ata
    if request_data.roles:
        roles_assigned_success = await keycloak_api_helpers.assign_realm_roles_to_user(
            user_id=new_kc_user_id_str,
            role_names=request_data.roles,
            settings=settings
        )
        if not roles_assigned_success:
            print(f"UYARI ({log_prefix}): Kullanıcı Keycloak'ta oluşturuldu (ID: {new_kc_user_id_str}) ANCAK roller ({request_data.roles}) atanamadı veya kısmen atandı.")
            # Bu işlemi kritik bir hata olarak görmeyebiliriz, loglanması yeterli olabilir. Şimdilik devam edelim.
    
    # 5. Keycloak'ta Gruba (Tenant'a) Ata (eğer tenant_id sağlanmışsa)
    if keycloak_group_id_to_assign:
        group_assigned_success = await keycloak_api_helpers.add_user_to_group(
            user_id=new_kc_user_id_str,
            group_id=keycloak_group_id_to_assign,
            settings=settings
        )
        if not group_assigned_success:
            print(f"UYARI ({log_prefix}): Kullanıcı Keycloak'ta oluşturuldu (ID: {new_kc_user_id_str}) ANCAK gruba ({keycloak_group_id_to_assign}) atanamadı.")
            # Bu da kritik bir hata olmayabilir, loglanması yeterli.

    # 6. Lokal Veritabanına Senkronize Et (JIT)
    try:
        new_user_keycloak_id_uuid = uuid.UUID(new_kc_user_id_str)
    except ValueError:
        print(f"KRİTİK HATA ({log_prefix}): Keycloak'tan dönen kullanıcı ID'si ('{new_kc_user_id_str}') geçerli bir UUID değil.")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Keycloak'tan geçersiz kullanıcı ID formatı alındı.")

    user_data_for_local_db = user_models.UserCreateInternal(
        id=new_user_keycloak_id_uuid, # Keycloak'tan gelen ID
        email=request_data.email,
        full_name=request_data.full_name,
        roles=request_data.roles, # Keycloak'a atanması istenen roller, crud bunları DB'deki tek role mapleyebilir
        is_active=request_data.is_active
    )
    
    try:
        db_user = user_crud.get_or_create_user(db=db, user_data=user_data_for_local_db)
    except IntegrityError as e: # Örneğin email unique constraint ihlali (Keycloak'ta yokken DB'de varsa)
        db.rollback()
        print(f"HATA ({log_prefix}): Kullanıcı lokal DB'ye kaydedilirken IntegrityError: {e}")
        # Bu durum, Keycloak'ta kullanıcı oluşturulduktan sonra DB'de bir çakışma olduğunu gösterir.
        # İdealde Keycloak'taki kullanıcı silinmeli.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Kullanıcı bilgileri lokal veritabanıyla çakışıyor.")
    except Exception as e:
        db.rollback()
        print(f"HATA ({log_prefix}): Kullanıcı lokal DB'ye kaydedilirken beklenmedik hata: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Kullanıcı lokal veritabanına kaydedilirken bir hata oluştu.")

    print(f"{log_prefix} User '{db_user.email}' (ID: {db_user.id}) successfully created in Keycloak and synced to local DB.")
    
    # Yanıt modelini oluştururken, Keycloak'a atanan rolleri (request_data.roles) kullanalım
    return user_models.User(
        id=db_user.id,
        email=db_user.email,
        full_name=db_user.full_name,
        roles=request_data.roles, # Adminin atadığı roller
        is_active=db_user.is_active,
        created_at=db_user.created_at 
    )

@app.get(
    "/admin/users", 
    response_model=UserListResponse, # <--- Güncellenmiş yanıt modeli
    summary="Tüm kullanıcıları listeler (Sadece General Admin)"
)
async def list_users_for_admin(
    current_user_payload: Annotated[Dict[str, Any], Depends(get_current_user_payload)],
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 100
):
    user_roles_from_token = current_user_payload.get("roles", [])
    if not user_roles_from_token and current_user_payload.get("realm_access"):
        user_roles_from_token = current_user_payload.get("realm_access", {}).get("roles", [])

    if "general-admin" not in user_roles_from_token:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bu işlemi yapma yetkiniz yok.")

    print(f"INFO (GET /admin/users): General admin '{current_user_payload.get('sub')}' listing users. Skip: {skip}, Limit: {limit}")
    
    db_users = user_crud.get_users(db, skip=skip, limit=limit)
    total_users = user_crud.count_users(db)
    
    # Pydantic user_models.User listesine dönüştür
    # ve roles alanını DB'deki role enum değerinden oluştur
    pydantic_users: List[user_models.User] = []
    for db_user in db_users:
        # DB'deki enum rolünü string listesine çevir (user_models.User 'roles: List[str]' bekliyor)
        # Eğer db_user.role None olma ihtimali varsa ona göre kontrol ekleyin.
        db_role_str_list = [str(db_user.role.value)] if db_user.role else []
        
        pydantic_users.append(
            user_models.User(
                id=db_user.id,
                email=db_user.email,
                full_name=db_user.full_name,
                roles=db_role_str_list, # DB'deki atanmış rolü liste olarak ver
                is_active=db_user.is_active,
                created_at=db_user.created_at
            )
        )
        
    return UserListResponse(items=pydantic_users, total=total_users)

@app.patch(
    "/admin/users/{user_id}",
    response_model=user_models.User,
    summary="Belirli bir kullanıcının bilgilerini, rollerini veya tenant atamasını günceller (Sadece General Admin)"
)
async def admin_update_user(
    user_id: uuid.UUID, # Path parametresi
    update_data: user_models.AdminUserUpdateRequest, # Request body
    current_admin_payload: Annotated[Dict[str, Any], Depends(get_current_user_payload)],
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings)
):
    admin_roles = current_admin_payload.get("roles", [])
    if not admin_roles and current_admin_payload.get("realm_access"):
        admin_roles = current_admin_payload.get("realm_access", {}).get("roles", [])

    if "general-admin" not in admin_roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bu işlemi yapma yetkiniz yok.")

    log_prefix = f"INFO (PATCH /admin/users/{user_id} - Admin: {current_admin_payload.get('sub')}):"
    print(f"{log_prefix} Attempting to update user with data: {update_data.model_dump(exclude_unset=True)}")

    # 1. Lokal DB'den ve Keycloak'tan mevcut kullanıcıyı çek
    db_user = user_crud.get_user_by_keycloak_id(db, keycloak_id=user_id)
    if not db_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Güncellenecek kullanıcı lokal veritabanında bulunamadı.")

    kc_user_representation = await keycloak_api_helpers.get_keycloak_user(str(user_id), settings)
    if not kc_user_representation:
        # Bu durum bir tutarsızlık belirtir: Kullanıcı lokalde var ama Keycloak'ta yok.
        print(f"KRİTİK HATA ({log_prefix}): Kullanıcı (ID: {user_id}) lokal DB'de var ama Keycloak'ta bulunamadı!")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kullanıcı kimlik sağlayıcıda (Keycloak) bulunamadı.")

    # Güncellenecek Keycloak kullanıcı özelliklerini biriktir
    kc_attrib_updates: Dict[str, Any] = {}
    final_name_for_db = db_user.full_name
    final_is_active_for_db = db_user.is_active

    # 2. Temel Kullanıcı Özelliklerini Güncelle (isim, aktiflik)
    if "full_name" in update_data.model_fields_set: # Pydantic v2 için, v1 için update_data.__fields_set__
        if update_data.full_name is not None:
            first_name, last_name = _split_full_name(update_data.full_name)
            kc_attrib_updates["firstName"] = first_name
            kc_attrib_updates["lastName"] = last_name
            final_name_for_db = update_data.full_name
            print(f"{log_prefix} Name update: firstName='{first_name}', lastName='{last_name}'")

    if "is_active" in update_data.model_fields_set:
        if update_data.is_active is not None:
            kc_attrib_updates["enabled"] = update_data.is_active
            final_is_active_for_db = update_data.is_active
            print(f"{log_prefix} Status update: enabled={update_data.is_active}")
    
    if kc_attrib_updates:
        # email ve username gibi alanları mevcut UserRepresentation'dan alıp güncelleme request'ine ekleyebiliriz,
        # çünkü Keycloak PUT /users/{id} endpoint'i tam bir UserRepresentation bekleyebilir.
        # Ya da sadece değişenleri göndeririz. Keycloak API'si genellikle sadece değişenleri kabul eder.
        # Güvenli olması için, mevcut kc_user_representation'dan bazı zorunlu alanları alıp,
        # kc_attrib_updates ile üzerine yazarak gönderelim.
        # Ancak, Keycloak genellikle PUT ile sadece gönderilen alanları günceller.
        # update_keycloak_user_attributes fonksiyonunuz bu detayı ele almalı.
        # Mevcut update_keycloak_user_attributes sadece gönderilenleri PUT ettiği için bu yeterli.
        success_attrib_update = await keycloak_api_helpers.update_keycloak_user_attributes(
            str(user_id), kc_attrib_updates, settings
        )
        if not success_attrib_update:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Keycloak'ta kullanıcı özellikleri güncellenirken hata oluştu.")
        print(f"{log_prefix} Basic attributes updated in Keycloak.")

    # 3. Rolleri Güncelle
    final_roles_for_db = [str(db_user.role.value)] if db_user.role else [] # DB'deki mevcut rolü al
    if "roles" in update_data.model_fields_set: # Eğer roles alanı requestte belirtilmişse (boş liste dahil)
        if update_data.roles is not None:
            success_roles_update = await keycloak_api_helpers.set_user_realm_roles(
                str(user_id), update_data.roles, settings
            )
            if not success_roles_update:
                # Rol güncelleme kritik olmayabilir, loglayıp devam edebiliriz veya hata verebiliriz.
                print(f"UYARI ({log_prefix}): Keycloak'ta kullanıcı rolleri tam olarak güncellenemedi.")
                # raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Keycloak'ta kullanıcı rolleri güncellenirken hata oluştu.")
            else:
                print(f"{log_prefix} Roles updated in Keycloak to: {update_data.roles}")
            final_roles_for_db = update_data.roles # DB'ye senkronize edilecek rolleri güncelle
        else: # update_data.roles explicit olarak null ise (pek olası değil modelde List[str] olduğu için, ama boş liste [] olabilir)
            # Eğer update_data.roles None ise (modelde Optional[List[str]] = None), bu dokunma demek.
            # Eğer update_data.roles == [] ise, tüm rolleri sil demek. set_user_realm_roles bunu yapar.
            pass # set_user_realm_roles zaten None veya boş liste durumunu ele alır.

    # 4. Tenant/Grup Atamasını Güncelle
    if "tenant_id" in update_data.model_fields_set: # Eğer tenant_id alanı requestte belirtilmişse
        print(f"{log_prefix} Tenant assignment change requested. New tenant_id: {update_data.tenant_id}")
        current_kc_groups = await keycloak_api_helpers.get_user_keycloak_groups(str(user_id), settings)
        current_kc_group_ids = {group['id'] for group in current_kc_groups} if current_kc_groups else set()

        new_kc_group_id_to_assign: Optional[str] = None
        if update_data.tenant_id is not None: # Yeni bir tenant ID'si verilmiş
            new_tenant_company = company_crud.get_company(db, company_id=update_data.tenant_id)
            if not new_tenant_company:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Belirtilen yeni tenant ID'si ile şirket bulunamadı.")
            if not new_tenant_company.keycloak_group_id:
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Yeni şirketin Keycloak grup ID'si eksik.")
            new_kc_group_id_to_assign = str(new_tenant_company.keycloak_group_id)

        # Önce mevcut tüm gruplardan çıkar (genellikle kullanıcı en fazla 1 tenant grubunda olur)
        # Eğer yeni grup eskisinden farklıysa veya kullanıcı bir gruptan tamamen çıkarılıyorsa.
        for group_id_to_remove in current_kc_group_ids:
            if group_id_to_remove != new_kc_group_id_to_assign: # Yeni gruba eşit değilse veya yeni grup yoksa sil
                print(f"{log_prefix} Removing user from old Keycloak group: {group_id_to_remove}")
                await keycloak_api_helpers.remove_user_from_keycloak_group(str(user_id), group_id_to_remove, settings)
        
        # Eğer yeni bir grup atanacaksa ve kullanıcı zaten o grupta değilse ekle
        if new_kc_group_id_to_assign and new_kc_group_id_to_assign not in current_kc_group_ids:
            print(f"{log_prefix} Adding user to new Keycloak group: {new_kc_group_id_to_assign}")
            await keycloak_api_helpers.add_user_to_group(str(user_id), new_kc_group_id_to_assign, settings)
        
        print(f"{log_prefix} Tenant/Group assignment updated in Keycloak.")


    # 5. Lokal Veritabanını Güncelle (get_or_create_user ile efektif update)
    # Not: get_or_create_user, UserCreateInternal bekler. final_roles_for_db listesini kullanacağız.
    user_data_for_local_db_update = user_models.UserCreateInternal(
        id=user_id, # Path'ten gelen user_id (UUID)
        email=kc_user_representation.get('email', db_user.email), # Email güncellenmiyor, mevcut olanı kullan
        full_name=final_name_for_db,
        roles=final_roles_for_db, # Güncellenmiş veya mevcut roller (Keycloak'a atananlar)
        is_active=final_is_active_for_db
    )
    
    try:
        updated_db_user = user_crud.get_or_create_user(db=db, user_data=user_data_for_local_db_update)
    except Exception as e:
        # Keycloak'ta değişiklikler yapıldı ama lokal DB senkronizasyonu başarısız oldu.
        # Bu durum manuel müdahale gerektirebilir.
        print(f"KRİTİK HATA ({log_prefix}): Keycloak işlemleri sonrası lokal DB güncellenemedi: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Kullanıcı lokal veritabanında güncellenirken bir hata oluştu. Sistem yöneticisine başvurun.")

    print(f"{log_prefix} User '{updated_db_user.email}' (ID: {updated_db_user.id}) successfully updated in Keycloak and synced to local DB.")

    # Yanıt için Pydantic modelini oluştur. Roller için Keycloak'a atanan güncel rolleri (final_roles_for_db) kullanalım.
    return user_models.User(
        id=updated_db_user.id,
        email=updated_db_user.email,
        full_name=updated_db_user.full_name,
        roles=final_roles_for_db, # Keycloak'a gönderilen/güncellenen roller
        is_active=updated_db_user.is_active,
        created_at=updated_db_user.created_at # updated_at alanı DB modelinde varsa o da eklenebilir.
    )

# --- Veritabanı Şema ve Tablo Oluşturma ---
def create_db_and_tables():
    print("User Service: Veritabanı şemaları ve tabloları oluşturuluyor/kontrol ediliyor...")
    
    # Sadece User Service'in sorumlu olduğu modelleri burada işleyin
    # User ve Company modelleri için şema kontrolü
    schemas_to_create = set()
    if hasattr(db_models.User, '__table_args__') and isinstance(db_models.User.__table_args__, dict) and 'schema' in db_models.User.__table_args__:
        schemas_to_create.add(db_models.User.__table_args__['schema'])
    if hasattr(db_models.Company, '__table_args__') and isinstance(db_models.Company.__table_args__, dict) and 'schema' in db_models.Company.__table_args__:
        schemas_to_create.add(db_models.Company.__table_args__['schema'])

    # Ticket tablosu User Service'in sorumluluğunda olmamalı.
    # Eğer db_models altında Ticket varsa ve şeması User ile aynıysa zaten yukarıda yakalanır,
    # değilse ve özellikle User Service'in Ticket tablosu oluşturması istenmiyorsa, aşağıdaki satırlar kaldırılmalı/yorumlanmalı.
    # if db_models.Ticket.__table_args__ and 'schema' in db_models.Ticket.__table_args__:
    # schemas_to_create.add(db_models.Ticket.__table_args__['schema'])
    
    unique_schemas = set(s for s in schemas_to_create if s) 

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
        Base.metadata.create_all(bind=engine) # Bu, User ve Company tablolarını (ve şemaları içindeyse onları) oluşturur.
        print("User Service: Veritabanı tabloları başarıyla kontrol edildi/oluşturuldu.")
    except Exception as e:
        print(f"User Service: Tablolar oluşturulurken HATA: {e}")
        import traceback
        traceback.print_exc()

create_db_and_tables()
# --- Veritabanı Kurulum Sonu ---

@app.get(
    "/admin/users/{user_id}", 
    response_model=user_models.User,
    summary="Belirli bir kullanıcının detaylarını getirir (Sadece General Admin)"
)
async def get_user_details_for_admin(
    user_id: uuid.UUID, # Path parametresi olarak kullanıcı ID'si
    current_user_payload: Annotated[Dict[str, Any], Depends(get_current_user_payload)],
    db: Session = Depends(get_db)
):
    user_roles_from_token = current_user_payload.get("roles", [])
    if not user_roles_from_token and current_user_payload.get("realm_access"):
        user_roles_from_token = current_user_payload.get("realm_access", {}).get("roles", [])

    if "general-admin" not in user_roles_from_token:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bu işlemi yapma yetkiniz yok.")

    print(f"INFO (GET /admin/users/{{user_id}}): General admin '{current_user_payload.get('sub')}' requesting details for user ID: {user_id}")
    
    db_user = user_crud.get_user_by_keycloak_id(db, keycloak_id=user_id)
    
    if db_user is None:
        print(f"WARN (GET /admin/users/{{user_id}}): User with ID {user_id} not found in local DB.")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kullanıcı bulunamadı.")
    
    # Pydantic user_models.User modeline dönüştür
    # DB'deki enum rolünü string listesine çevir
    db_role_str_list = [str(db_user.role.value)] if db_user.role else []
        
    return user_models.User(
        id=db_user.id,
        email=db_user.email,
        full_name=db_user.full_name,
        roles=db_role_str_list, # DB'deki atanmış rolü liste olarak ver
        is_active=db_user.is_active,
        created_at=db_user.created_at
    )

@app.get("/")
async def read_root_user_service(settings: Settings = Depends(get_settings)): # Tek bir root endpoint
    print(f"UserService Root - Configured Audience: {settings.keycloak.audience}")
    return {"message": "User Service API (Keycloak Entegreli ve Tenant Yönetimi)"}

@app.post(
    "/users/sync-from-keycloak", 
    response_model=user_models.User,
    summary="Keycloak kullanıcısını lokal DB ile senkronize et/oluştur (JIT - İç Servis Çağrısı)"
)
async def sync_user_from_keycloak(
    user_in: user_models.UserCreateInternal, 
    is_internal_request: Annotated[bool, Depends(verify_internal_secret)], 
    db: Session = Depends(get_db)
):
    if not is_internal_request:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Yetkisiz erişim.")

    print(f"USER_SERVICE: /users/sync-from-keycloak called for user ID: {user_in.id}, email: {user_in.email}")
    
    db_user = user_crud.get_or_create_user(db=db, user_data=user_in)
    
    return user_models.User(
        id=db_user.id,
        email=db_user.email,
        full_name=db_user.full_name,
        roles=user_in.roles, 
        is_active=db_user.is_active,
        created_at=db_user.created_at
    )

# Bu, `/users/me` endpoint'inin doğru ve tek versiyonu
@app.get("/users/me", response_model=user_models.User, summary="Mevcut login olmuş kullanıcının bilgilerini getir")
async def read_users_me(
    current_user_payload: Annotated[Dict[str, Any], Depends(get_current_user_payload)],
    db: Session = Depends(get_db)
):
    keycloak_id_str = current_user_payload.get("sub")
    if not keycloak_id_str:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token ID (sub) bulunamadı")

    try:
        user_id_uuid = uuid.UUID(keycloak_id_str)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Geçersiz kullanıcı ID formatı (sub).")

    email = current_user_payload.get("email")
    if not email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Token içinde e-posta bilgisi bulunamadı.")

    full_name = (
        current_user_payload.get("name") or
        f"{current_user_payload.get('given_name', '')} {current_user_payload.get('family_name', '')}".strip() or
        current_user_payload.get("preferred_username")
    )
    if not full_name:
        full_name = email 

    keycloak_roles = current_user_payload.get("roles", [])
    if not keycloak_roles and current_user_payload.get("realm_access"): 
        keycloak_roles = current_user_payload.get("realm_access", {}).get("roles", [])
    
    is_active = current_user_payload.get("email_verified", True) 

    user_data_for_crud = user_models.UserCreateInternal(
        id=user_id_uuid,
        email=email,
        full_name=full_name,
        roles=keycloak_roles, 
        is_active=is_active
    )

    # crud.get_or_create_user çağrısı JIT provisioning'i yapar
    # Eğer IntegrityError (örn: email unique constraint) olursa, bu crud içinde ele alınmalı veya burada try-except ile yakalanmalı.
    # Şimdilik crud.get_or_create_user'ın bu durumu yönettiğini varsayıyoruz.
    db_user = user_crud.get_or_create_user(db=db, user_data=user_data_for_crud)
    if not db_user: # get_or_create_user bir şekilde None dönerse (beklenmedik)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Kullanıcı bilgileri alınırken veya oluşturulurken hata oluştu.")

    return user_models.User(
        id=db_user.id,
        email=db_user.email,
        full_name=db_user.full_name,
        roles=keycloak_roles, 
        is_active=db_user.is_active,
        created_at=db_user.created_at
    )

@app.post("/admin/tenants", response_model=common_schemas.Company, status_code=status.HTTP_201_CREATED, summary="Yeni bir tenant (müşteri şirketi) oluşturur (Sadece General Admin)")
async def create_new_tenant(
    tenant_request: user_models.TenantCreateRequest, 
    current_user_payload: Annotated[Dict[str, Any], Depends(get_current_user_payload)],
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings)
):
    user_roles = current_user_payload.get("roles", [])
    if not user_roles and current_user_payload.get("realm_access"):
        user_roles = current_user_payload.get("realm_access", {}).get("roles", [])

    if "general-admin" not in user_roles:
        print(f"HATA (POST /admin/tenants): Yetkisiz erişim denemesi. Kullanıcı rolleri: {user_roles}")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bu işlemi yapma yetkiniz yok.")

    print(f"INFO (POST /admin/tenants): General admin '{current_user_payload.get('sub')}' trying to create tenant with name: '{tenant_request.name}'")

    existing_company_by_name = company_crud.get_company_by_name(db, name=tenant_request.name)
    if existing_company_by_name:
        print(f"HATA (POST /admin/tenants): Tenant name '{tenant_request.name}' already exists locally with ID {existing_company_by_name.id}.")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"'{tenant_request.name}' adlı şirket zaten mevcut.")

    created_keycloak_group_id_str = await keycloak_api_helpers.create_keycloak_group(
        group_name=tenant_request.name, 
        settings=settings
    )

    if created_keycloak_group_id_str is None:
        print(f"HATA (POST /admin/tenants): Keycloak'ta '{tenant_request.name}' grubu oluşturulamadı (helper None döndü).")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Keycloak'ta müşteri grubu oluşturulurken bir hata oluştu.")
    
    if created_keycloak_group_id_str == "EXISTS":
        print(f"HATA (POST /admin/tenants): Keycloak'ta '{tenant_request.name}' adında bir grup zaten mevcut.")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"'{tenant_request.name}' adında bir Keycloak grubu zaten mevcut.")

    try:
        keycloak_group_uuid = uuid.UUID(created_keycloak_group_id_str)
    except ValueError:
        print(f"HATA (POST /admin/tenants): Keycloak'tan dönen grup ID'si ('{created_keycloak_group_id_str}') geçerli bir UUID değil.")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Keycloak'tan geçersiz grup ID formatı alındı.")

    existing_company_by_kc_id = company_crud.get_company_by_keycloak_group_id(db, keycloak_group_id=keycloak_group_uuid)
    if existing_company_by_kc_id:
        print(f"HATA (POST /admin/tenants): Keycloak group ID '{keycloak_group_uuid}' already linked to local company '{existing_company_by_kc_id.name}'. This is an inconsistency.")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Kritik sistem hatası: Keycloak grup ID çakışması.")

    company_to_create = common_schemas.CompanyCreate(
        name=tenant_request.name,
        keycloak_group_id=keycloak_group_uuid,
        status="active" 
    )
    
    try:
        db_company = company_crud.create_company(db=db, company=company_to_create)
        print(f"INFO (POST /admin/tenants): Tenant '{db_company.name}' (ID: {db_company.id}) created successfully with Keycloak Group ID: {db_company.keycloak_group_id}")
        return db_company
    except IntegrityError as e: 
        db.rollback()
        print(f"HATA (POST /admin/tenants): Veritabanına şirket kaydedilirken IntegrityError: {e}")
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
    total_companies = company_crud.count_companies(db)
    
    return common_schemas.CompanyList(items=companies, total=total_companies)

@app.get("/admin/tenants/{company_id}", response_model=common_schemas.Company, summary="Belirli bir tenantın detaylarını getirir (Sadece General Admin)")
async def get_tenant_details(
    company_id: uuid.UUID, 
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
async def update_tenant_details( # Fonksiyon adını daha genel yaptım
    company_id: uuid.UUID, 
    company_update_request: common_schemas.CompanyUpdate, # database_pkg.schemas.CompanyUpdate Pydantic modeli
    current_user_payload: Annotated[Dict[str, Any], Depends(get_current_user_payload)],
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings)
):
    user_roles = current_user_payload.get("roles", [])
    if not user_roles and current_user_payload.get("realm_access"):
        user_roles = current_user_payload.get("realm_access", {}).get("roles", [])

    if "general-admin" not in user_roles:
        print(f"HATA (PATCH /admin/tenants/{company_id}): Yetkisiz erişim denemesi. Kullanıcı rolleri: {user_roles}")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bu işlemi yapma yetkiniz yok.")

    log_prefix = f"INFO (PATCH /admin/tenants/{company_id} User: {current_user_payload.get('sub')}):"
    print(f"{log_prefix} Attempting to update company with data: {company_update_request.model_dump(exclude_unset=True)}")

    db_company = company_crud.get_company(db, company_id=company_id)
    if db_company is None:
        print(f"{log_prefix} Company with ID {company_id} not found.")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Güncellenecek şirket (tenant) bulunamadı.")

    if company_update_request.name is not None and company_update_request.name != db_company.name:
        print(f"{log_prefix} Name update requested from '{db_company.name}' to '{company_update_request.name}'.")
        
        # 1. Lokal DB'de yeni isimle başka bir tenant var mı kontrol et (aynı ID hariç)
        existing_company_with_new_name = company_crud.get_company_by_name(db, name=company_update_request.name)
        if existing_company_with_new_name and existing_company_with_new_name.id != company_id:
            print(f"{log_prefix} Attempt to update company name to '{company_update_request.name}', but this name is already used by company ID {existing_company_with_new_name.id}.")
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"'{company_update_request.name}' adlı şirket zaten mevcut.")

        # 2. Keycloak'ta grup adını güncelle
        if not db_company.keycloak_group_id:
            # Bu durum normalde olmamalı, tenant oluşturulurken Keycloak grup ID'si atanır.
            print(f"KRİTİK HATA ({log_prefix}): Şirketin ({db_company.name}) Keycloak grup ID'si lokal DB'de kayıtlı değil. Keycloak adı güncellenemiyor.")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Şirketin Keycloak yapılandırması eksik, ad güncellenemiyor.")

        print(f"{log_prefix} Attempting to update Keycloak group name for group ID: {db_company.keycloak_group_id} to '{company_update_request.name}'")
        keycloak_update_success = await keycloak_api_helpers.update_keycloak_group(
            group_id=str(db_company.keycloak_group_id), # Helper str bekliyor olabilir
            new_name=company_update_request.name,
            settings=settings
        )
        
        if not keycloak_update_success:
            # Keycloak'ta güncelleme başarısız olursa, lokal DB'yi güncelleme ve hata dön.
            # Bu, tutarlılığı korumak için daha güvenli bir yaklaşımdır.
            print(f"HATA ({log_prefix}): Keycloak grup adı güncellenemedi. Lokal veritabanı güncellenmeyecek.")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Keycloak'ta şirket adı güncellenirken bir sorun oluştu. Lokal değişiklikler uygulanmadı.")
        
        print(f"{log_prefix} Keycloak group name updated successfully for group ID: {db_company.keycloak_group_id}.")
        # İsim Keycloak'ta başarıyla güncellendi, şimdi lokal DB'yi güncelleyebiliriz.

    updated_company = company_crud.update_company(db=db, company_db=db_company, company_in=company_update_request)
    
    print(f"{log_prefix} Company '{updated_company.name}' (ID: {updated_company.id}) updated successfully. New data: {updated_company}")
    return updated_company