# user_service/main.py
from __future__ import annotations
import uuid
from contextlib import asynccontextmanager
from typing import Annotated, Dict, Any, List, Optional

import httpx
from fastapi import FastAPI, Depends, HTTPException, status, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

# user_service'e ait yerel modüllerin import edilmesi
# DÜZELTME: Tüm importları tek bir yerden ve doğru takma adlarla yapıyoruz.
from . import crud as user_crud
from . import company_crud
from . import keycloak_api_helpers
from . import db_models # SQLAlchemy modelleri
from . import models as user_pydantic_models # Pydantic modelleri
from .database import get_db, SessionLocal # SessionLocal'ı lifespan için import ediyoruz
from .auth import get_current_user_payload, verify_internal_secret
from .config import Settings, get_settings

async def sync_all_tenants_from_keycloak_on_startup(db: Session, settings: Settings):
    """Keycloak'taki grupları lokal 'companies' tablosuyla senkronize eder."""
    print("STARTUP SYNC: Tenant'lar (gruplar) senkronize ediliyor...")
    try:
        all_kc_groups = await keycloak_api_helpers.get_all_keycloak_groups_paginated(settings)
        if all_kc_groups is None:
            print("HATA (Startup Sync): Admin token alınamadığı için tenant senkronizasyonu atlandı.")
            return

        for group_rep in all_kc_groups:
            kc_group_id_str = group_rep.get("id")
            kc_group_name = group_rep.get("name")
            if not kc_group_id_str or not kc_group_name:
                continue
            
            kc_group_uuid = uuid.UUID(kc_group_id_str)
            company_in_db = company_crud.get_company_by_keycloak_group_id(db, keycloak_group_id=kc_group_uuid)

            if not company_in_db:
                # DÜZELTME: `common_schemas` yerine `user_pydantic_models` kullanılıyor.
                new_company_data = user_pydantic_models.CompanyCreate(
                    name=kc_group_name,
                    keycloak_group_id=kc_group_uuid,
                    status="active"
                )
                company_crud.create_company(db, company=new_company_data)
                print(f"BİLGİ (Startup Sync): Yeni tenant eklendi: {kc_group_name}")
            elif company_in_db.name != kc_group_name:
                # DÜZELTME: `common_schemas` yerine `user_pydantic_models` kullanılıyor.
                company_crud.update_company(db, company_in_db, user_pydantic_models.CompanyUpdate(name=kc_group_name))
                print(f"BİLGİ (Startup Sync): Tenant adı güncellendi: {kc_group_name}")

        print("STARTUP SYNC: Tenant senkronizasyonu tamamlandı.")
    except Exception as e:
        print(f"KRİTİK HATA (Startup Sync - Tenants): {e}")

async def sync_all_users_from_keycloak_on_startup(db: Session, settings: Settings):
    """Keycloak'taki kullanıcıları lokal 'users' tablosuyla senkronize eder."""
    print("STARTUP SYNC: Kullanıcılar senkronize ediliyor...")
    try:
        all_kc_users = await keycloak_api_helpers.get_all_keycloak_users_paginated(settings)
        if all_kc_users is None:
            print("HATA (Startup Sync): Admin token alınamadığı için kullanıcı senkronizasyonu atlandı.")
            return

        for user_rep in all_kc_users:
            user_id_str = user_rep.get("id")
            if not user_id_str or not user_rep.get("email"):
                continue

            # DÜZELTME: `user_models` yerine `user_pydantic_models` kullanılıyor.
            user_create_data = user_pydantic_models.UserCreateInternal(
                id=uuid.UUID(user_id_str),
                email=user_rep.get("email"),
                full_name=f"{user_rep.get('firstName', '')} {user_rep.get('lastName', '')}".strip() or user_rep.get("username"),
                roles=user_rep.get("realmRoles", []),
                is_active=user_rep.get("enabled", False)
            )
            user_crud.get_or_create_user(db, user_data=user_create_data)
        
        print("STARTUP SYNC: Kullanıcı senkronizasyonu tamamlandı.")
    except Exception as e:
        print(f"KRİTİK HATA (Startup Sync - Users): {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Uygulama yaşam döngüsü yöneticisi."""
    print("Uygulama başlıyor...")
    # DÜZELTME: `SessionLocal` doğru import edildi.
    db_session = SessionLocal()
    app_settings = get_settings()
    try:
        await sync_all_tenants_from_keycloak_on_startup(db=db_session, settings=app_settings)
        await sync_all_users_from_keycloak_on_startup(db=db_session, settings=app_settings)
    finally:
        db_session.close()
    yield
    print("Uygulama kapanıyor...")

# --- FastAPI Uygulama Tanımı ---


API_PREFIX = "/api/users"

app = FastAPI(
    title="User Service API",
    description="Helpdesk uygulaması için Kullanıcı ve Şirket (Tenant) Yönetimi Servisi.",
    version="1.4.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:8080"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class UserListResponse(BaseModel):
    items: List[user_pydantic_models.User]
    total: int

def _split_full_name(full_name: str) -> tuple[str, str]:
    parts = full_name.strip().split(maxsplit=1)
    return (parts[0], parts[1]) if len(parts) > 1 else (parts[0], "")

@app.delete(f"{API_PREFIX}/admin/tenants/{{company_id}}",
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

@app.get(f"{API_PREFIX}/admin/users/{{user_id}}", response_model=user_pydantic_models.User, tags=["Admin - User Management"])
async def read_user_details_for_admin(
    user_id: uuid.UUID,
    current_admin_payload: Annotated[dict, Depends(get_current_user_payload)],
    settings: Annotated[Settings, Depends(get_settings)],
    db: Annotated[Session, Depends(get_db)] # <-- DEĞİŞİKLİK BURADA
):
    """
    (General Admin Only) Belirli bir kullanıcının detaylarını getirir.
    Tenant (şirket) ve Keycloak rollerini içerir.
    """
    # Yetki kontrolü
    if "general-admin" not in current_admin_payload.get("realm_access", {}).get("roles", []):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bu işlem için yetkiniz yok.")

    # Lokal veritabanından kullanıcıyı al
    db_user = user_crud.get_user_by_keycloak_id(db, keycloak_id=user_id)
    if not db_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Kullanıcı ID '{user_id}' bulunamadı.")

    # Keycloak'tan güncel kullanıcı detaylarını (roller dahil) al
    kc_user_details = await keycloak_api_helpers.get_keycloak_user(str(user_id), settings)
    kc_roles = []
    if kc_user_details:
        kc_roles = kc_user_details.get("realmRoles", [])
        # Lokal DB'deki is_active durumunu Keycloak'taki 'enabled' ile senkronize edebiliriz (isteğe bağlı)
        # if db_user.is_active != kc_user_details.get("enabled", db_user.is_active):
        #     db_user.is_active = kc_user_details.get("enabled", db_user.is_active)
        #     db.commit()
        #     db.refresh(db_user)
    else:
        # Keycloak'ta kullanıcı bulunamadıysa bu bir tutarsızlık olabilir.
        # Bu durumu loglayıp, belki lokal kullanıcıyı pasif hale getirebilirsiniz.
        print(f"UYARI: Kullanıcı {user_id} lokal DB'de var ama Keycloak'ta bulunamadı.")


    # Kullanıcının şirket (tenant) bilgisini al
    user_company_info: Optional[user_pydantic_models.CompanyBasicInfo] = None # Pydantic model tipini belirttik
    kc_user_groups = await keycloak_api_helpers.get_user_keycloak_groups(str(user_id), settings)
    
    if kc_user_groups:
        for group_representation in kc_user_groups:
            keycloak_group_id_str = group_representation.get("id")
            if keycloak_group_id_str:
                try:
                    kc_group_uuid = uuid.UUID(keycloak_group_id_str)
                    company_in_db = company_crud.get_company_by_keycloak_group_id(db, keycloak_group_id=kc_group_uuid)
                    if company_in_db:
                        # Pydantic modelini kullanarak şirket bilgisini oluştur
                        user_company_info = user_pydantic_models.CompanyBasicInfo(
                            id=company_in_db.id, 
                            name=company_in_db.name
                        )
                        break # İlk eşleşen tenant'ı kullan (bir kullanıcı idealde tek tenant'a bağlı olmalı)
                except ValueError:
                    print(f"UYARI: Keycloak grup ID '{keycloak_group_id_str}' geçerli bir UUID değil.")
                    continue
    
    # Yanıt modelini oluştur
    user_response = user_pydantic_models.User(
        id=db_user.id,
        email=db_user.email,
        full_name=db_user.full_name, # Keycloak'tan gelen güncel full_name de kullanılabilirdi.
        is_active=kc_user_details.get("enabled") if kc_user_details else db_user.is_active, # Keycloak'tan gelen güncel durum
        created_at=db_user.created_at, # Lokal DB'deki oluşturulma tarihi
        roles=kc_roles, # Keycloak'tan gelen güncel roller
        company=user_company_info # Lokal DB'den bulunan şirket bilgisi
    )
    return user_response


@app.patch(f"{API_PREFIX}/admin/users/{{user_id}}", response_model=user_pydantic_models.User, tags=["Admin - User Management"])
async def update_user_for_admin(
    user_id: uuid.UUID,
    user_update_data: user_pydantic_models.AdminUserUpdateRequest,
    current_admin_payload: Annotated[dict, Depends(get_current_user_payload)],
    settings: Annotated[Settings, Depends(get_settings)],
    db: Annotated[Session, Depends(get_db)] # <-- DEĞİŞİKLİK BURADA
):
    """
    (General Admin Only) Belirli bir kullanıcının bilgilerini günceller.
    (Tam ad, aktiflik durumu, Keycloak rolleri, tenant ataması)
    """
    if "general-admin" not in current_admin_payload.get("realm_access", {}).get("roles", []):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bu işlem için yetkiniz yok.")

    db_user = user_crud.get_user_by_keycloak_id(db, keycloak_id=user_id)
    if not db_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Güncellenecek kullanıcı ID '{user_id}' bulunamadı.")

    kc_user_id_str = str(user_id)
    kc_attributes_to_update = {} # Keycloak UserRepresentation için güncellenecek alanlar

    # Tam Ad Güncellemesi
    if user_update_data.full_name is not None and db_user.full_name != user_update_data.full_name:
        name_parts = user_update_data.full_name.strip().split(" ", 1)
        kc_attributes_to_update["firstName"] = name_parts[0]
        kc_attributes_to_update["lastName"] = name_parts[1] if len(name_parts) > 1 else ""
        db_user.full_name = user_update_data.full_name
        print(f"Kullanıcı {kc_user_id_str}: Tam ad güncelleniyor -> {user_update_data.full_name}")

    # Aktiflik Durumu Güncellemesi
    if user_update_data.is_active is not None and db_user.is_active != user_update_data.is_active:
        kc_attributes_to_update["enabled"] = user_update_data.is_active
        db_user.is_active = user_update_data.is_active
        print(f"Kullanıcı {kc_user_id_str}: Aktiflik durumu güncelleniyor -> {user_update_data.is_active}")

    # Keycloak'ta temel kullanıcı attribute'larını güncelle (eğer değişiklik varsa)
    if kc_attributes_to_update:
        success_kc_attr_update = await keycloak_api_helpers.update_keycloak_user_attributes(
            kc_user_id_str, kc_attributes_to_update, settings
        )
        if not success_kc_attr_update:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Keycloak'ta kullanıcı attribute'ları güncellenirken hata oluştu.")

    # Roller Güncellemesi
    if user_update_data.roles is not None: # Boş liste de geçerli bir güncellemedir (tüm rolleri sil)
        print(f"Kullanıcı {kc_user_id_str}: Roller güncelleniyor -> {user_update_data.roles}")
        success_kc_roles_update = await keycloak_api_helpers.set_user_realm_roles(
            kc_user_id_str, user_update_data.roles, settings
        )
        if not success_kc_roles_update:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Keycloak'ta kullanıcı rolleri güncellenirken hata oluştu.")
        
        # Lokal DB'deki rolü güncelle (crud.get_or_create_user içindeki mantığa benzer)
        # Bu rol eşleme mantığı projenizin ihtiyaçlarına göre özelleştirilmelidir.
        determined_local_role = user_pydantic_models.Role.EMPLOYEE # Varsayılan
        if user_update_data.roles:
            if "general-admin" in user_update_data.roles and hasattr(user_pydantic_models.Role, "GENERAL_ADMIN"):
                 determined_local_role = user_pydantic_models.Role.GENERAL_ADMIN
            elif "helpdesk-admin" in user_update_data.roles and hasattr(user_pydantic_models.Role, "HELPDESK_ADMIN"):
                 determined_local_role = user_pydantic_models.Role.HELPDESK_ADMIN
            elif user_pydantic_models.Role.AGENT.value in user_update_data.roles:
                determined_local_role = user_pydantic_models.Role.AGENT
            # EMPLOYEE zaten varsayılan olduğu için son else'e kalabilir
        
        if db_user.role != determined_local_role:
            db_user.role = determined_local_role


    # Tenant Ataması Güncellemesi
    if "tenant_id" in user_update_data.model_fields_set: # Alanın istekte gelip gelmediğini kontrol et
        new_tenant_id = user_update_data.tenant_id # Bu null veya UUID olabilir
        print(f"Kullanıcı {kc_user_id_str}: Tenant ataması güncelleniyor. Yeni tenant_id (lokal DB): {new_tenant_id}")
        
        current_kc_groups = await keycloak_api_helpers.get_user_keycloak_groups(kc_user_id_str, settings)
        
        # Kullanıcıyı mevcut (tenant ile ilişkili olduğu varsayılan) tüm Keycloak gruplarından çıkar
        if current_kc_groups:
            for group in current_kc_groups:
                # İPUCU: Sadece tenant'ları temsil eden gruplardan çıkarmak için burada bir kontrol eklenebilir.
                # Örneğin, grubun adında 'tenant_' ön eki var mı, veya özel bir attribute'u var mı gibi.
                # Şimdilik, kullanıcının sadece bir tenant grubunda olabileceğini varsayıyoruz.
                group_id_to_remove = group.get("id")
                if group_id_to_remove:
                    print(f"Kullanıcı {kc_user_id_str}: '{group_id_to_remove}' grubundan çıkarılıyor.")
                    await keycloak_api_helpers.remove_user_from_keycloak_group(
                        kc_user_id_str, group_id_to_remove, settings
                    )
        
        # Eğer yeni bir tenant_id (lokal DB şirket ID'si) verilmişse (null değilse),
        # kullanıcıyı o tenant'ın Keycloak grubuna ekle
        if new_tenant_id is not None:
            target_company_db = company_crud.get_company(db, company_id=new_tenant_id)
            if not target_company_db:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Belirtilen tenant_id '{new_tenant_id}' ile şirket bulunamadı.")
            if not target_company_db.keycloak_group_id:
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Hedef şirket '{target_company_db.name}' için Keycloak grup ID'si tanımlanmamış.")
            
            print(f"Kullanıcı {kc_user_id_str}: '{str(target_company_db.keycloak_group_id)}' grubuna ekleniyor.")
            success_kc_group_add = await keycloak_api_helpers.add_user_to_group(
                kc_user_id_str, str(target_company_db.keycloak_group_id), settings
            )
            if not success_kc_group_add:
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Kullanıcı yeni Keycloak grubuna eklenirken hata oluştu.")

    db.add(db_user) # Değişiklikleri session'a ekle
    db.commit()
    db.refresh(db_user)

    # Güncellenmiş kullanıcı bilgilerini tam olarak döndürmek için GET endpoint'ini çağır
    # Bu, tüm bağlı verilerin (yeni roller, yeni şirket) doğru şekilde yüklenmesini sağlar.
    return await read_user_details_for_admin(user_id, current_admin_payload, settings, db)

@app.get(f"{API_PREFIX}/internal/users/{{user_id}}", response_model=user_pydantic_models.User, tags=["Internal"])
async def get_user_for_internal_service(
    user_id: uuid.UUID,
    # Bu endpoint'in sadece diğer servisler tarafından çağrıldığından emin olmak için
    # basit bir "shared secret" doğrulaması kullanıyoruz.
    is_internal: Annotated[bool, Depends(verify_internal_secret)],
    db: Session = Depends(get_db)
):
    """
    İç servis iletişimi için belirli bir kullanıcının detaylarını döndürür.
    """
    if not is_internal:
        # Bu hata normalde `verify_internal_secret` içinde fırlatılır,
        # ama ekstra bir güvenlik katmanı olarak kalabilir.
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Yetkisiz erişim.")
    
    print(f"INTERNAL CALL: Fetching details for user_id: {user_id}")
    db_user = user_crud.get_user_by_keycloak_id(db, keycloak_id=user_id)
    
    if not db_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kullanıcı bulunamadı.")
        
    # Yanıtı Pydantic modeline uygun şekilde döndür
    return db_user

@app.post(f"{API_PREFIX}/admin/users",
    response_model=user_pydantic_models.User,
    status_code=status.HTTP_201_CREATED,
    summary="Yeni bir kullanıcı oluşturur (Keycloak + Lokal DB) (Sadece General Admin)"
)
async def admin_create_user(
    request_data: user_pydantic_models.AdminUserCreateRequest,
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

    user_data_for_local_db = user_pydantic_models.UserCreateInternal(
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
    return user_pydantic_models.User(
        id=db_user.id,
        email=db_user.email,
        full_name=db_user.full_name,
        roles=request_data.roles, # Adminin atadığı roller
        is_active=db_user.is_active,
        created_at=db_user.created_at 
    )

@app.post(f"{API_PREFIX}/internal/users/sync", response_model=user_pydantic_models.User, tags=["Internal"])
async def sync_user_internally(
    sync_data: user_pydantic_models.UserCreateInternal, # JIT için gelen veri
    db: Session = Depends(get_db),
    # is_internal: Annotated[bool, Depends(verify_internal_secret)], # Güvenlik için eklenebilir
):
    """
    İç servis çağrısıyla kullanıcıyı lokal DB'ye senkronize eder/oluşturur
    ve kullanıcının tenant bilgisini de günceller.
    """
    # if not is_internal: raise HTTPException(status_code=403, detail="Yetkisiz erişim.")

    # 1. Kullanıcıyı lokal DB'de oluştur veya bilgilerini güncelle
    db_user = user_crud.get_or_create_user(db=db, user_data=sync_data)
    
    # 2. Keycloak'tan gelen grup bilgisine göre kullanıcının şirketini (tenant) ayarla
    user_company_info = None
    if sync_data.keycloak_groups:
        # Şimdilik ilk grubu kullanıcının ana grubu olarak kabul ediyoruz
        group_path = sync_data.keycloak_groups[0]
        # Bu path'ten grup ID'sini ve adını almamız gerekebilir,
        # şimdilik sadece path'in adını şirket adı olarak varsayalım.
        # İdealde burada keycloak_api_helpers kullanılır.
        group_name = group_path.strip("/").split("/")[-1]
        
        company = company_crud.get_company_by_name(db, name=group_name)
        if company:
            db_user.company_id = company.id
            db.commit()
            db.refresh(db_user)
            user_company_info = user_pydantic_models.CompanyBasicInfo.from_orm(company)

    # 3. Frontend ve diğer servislerin kullanması için tam kullanıcı modelini döndür
    response_user = user_pydantic_models.User(
        id=db_user.id,
        email=db_user.email,
        full_name=db_user.full_name,
        is_active=db_user.is_active,
        created_at=db_user.created_at,
        roles=sync_data.roles,
        company=user_company_info
    )
    return response_user

@app.get(f"{API_PREFIX}/admin/users", 
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
    pydantic_users: List[user_pydantic_models.User] = []
    for db_user in db_users:
        # DB'deki enum rolünü string listesine çevir (user_models.User 'roles: List[str]' bekliyor)
        # Eğer db_user.role None olma ihtimali varsa ona göre kontrol ekleyin.
        db_role_str_list = [str(db_user.role.value)] if db_user.role else []
        
        pydantic_users.append(
            user_pydantic_models.User(
                id=db_user.id,
                email=db_user.email,
                full_name=db_user.full_name,
                roles=db_role_str_list, # DB'deki atanmış rolü liste olarak ver
                is_active=db_user.is_active,
                created_at=db_user.created_at
            )
        )
        
    return UserListResponse(items=pydantic_users, total=total_users)

@app.get(f"{API_PREFIX}/", tags=["Root"])
async def read_root_user_service():
    return {"message": "User Service API çalışıyor"}


@app.post(f"{API_PREFIX}/admin/tenants", response_model=user_pydantic_models.Company, status_code=status.HTTP_201_CREATED, summary="Yeni bir tenant (müşteri şirketi) oluşturur (Sadece General Admin)")
async def create_new_tenant(
    tenant_request: user_pydantic_models.TenantCreateRequest, 
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

    company_to_create = user_pydantic_models.CompanyCreate(
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

@app.get(f"{API_PREFIX}/admin/tenants", response_model=user_pydantic_models.CompanyList, summary="Tüm tenantları (müşteri şirketlerini) listeler (Sadece General Admin)")
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
    
    return user_pydantic_models.CompanyList(items=companies, total=total_companies)

@app.get(f"{API_PREFIX}/admin/tenants/{{company_id}}", response_model=user_pydantic_models.Company, summary="Belirli bir tenantın detaylarını getirir (Sadece General Admin)")
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

@app.patch(f"{API_PREFIX}/admin/tenants/{{company_id}}", response_model=user_pydantic_models.Company, summary="Belirli bir tenantın statüsünü veya adını günceller (Sadece General Admin)")
async def update_tenant_details( # Fonksiyon adını daha genel yaptım
    company_id: uuid.UUID, 
    company_update_request: user_pydantic_models.CompanyUpdate, # database_pkg.schemas.CompanyUpdate Pydantic modeli
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

@app.delete(f"{API_PREFIX}/admin/users/{{user_id}}",
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

@app.patch(f"{API_PREFIX}/admin/users/{{user_id}}", response_model=user_pydantic_models.User, tags=["Admin - Users"])
async def admin_update_user(
    user_id: uuid.UUID,
    update_data: user_pydantic_models.AdminUserUpdateRequest,
    current_admin_payload: Annotated[Dict, Depends(get_current_user_payload)],
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """Bir kullanıcının adını, aktiflik durumunu, rollerini ve tenant'ını günceller."""
    if "general-admin" not in current_admin_payload.get("realm_access", {}).get("roles", []):
        raise HTTPException(status_code=403, detail="Bu işlem için yetkiniz yok.")

    db_user = user_crud.get_user_by_keycloak_id(db, user_id)
    if not db_user:
        raise HTTPException(status_code=404, detail="Güncellenecek kullanıcı bulunamadı.")

    kc_user_id_str = str(user_id)
    kc_attribs_to_update = {}
    
    # 1. İsim ve Aktiflik Durumunu Güncelle
    if "full_name" in update_data.model_fields_set:
        first_name, last_name = _split_full_name(update_data.full_name)
        kc_attribs_to_update.update({"firstName": first_name, "lastName": last_name})
    if "is_active" in update_data.model_fields_set:
        kc_attribs_to_update["enabled"] = update_data.is_active
    
    if kc_attribs_to_update:
        if not await keycloak_api_helpers.update_keycloak_user_attributes(kc_user_id_str, kc_attribs_to_update, settings):
            raise HTTPException(status_code=500, detail="Keycloak'ta kullanıcı özellikleri güncellenemedi.")

    # 2. Rolleri Güncelle
    if "roles" in update_data.model_fields_set:
        if not await keycloak_api_helpers.set_user_realm_roles(kc_user_id_str, update_data.roles, settings):
            raise HTTPException(status_code=500, detail="Keycloak'ta kullanıcı rolleri güncellenemedi.")
    
    # 3. Tenant/Grup Atamasını Güncelle
    if "tenant_id" in update_data.model_fields_set:
        new_tenant_id = update_data.tenant_id
        current_kc_groups = await keycloak_api_helpers.get_user_keycloak_groups(kc_user_id_str, settings)
        for group in current_kc_groups or []:
            await keycloak_api_helpers.remove_user_from_keycloak_group(kc_user_id_str, group['id'], settings)
        
        if new_tenant_id is not None:
            target_company = company_crud.get_company(db, new_tenant_id)
            if not target_company or not target_company.keycloak_group_id:
                raise HTTPException(status_code=404, detail="Hedef tenant veya Keycloak grup ID'si bulunamadı.")
            await keycloak_api_helpers.add_user_to_group(kc_user_id_str, str(target_company.keycloak_group_id), settings)

    # 4. Lokal DB'yi Güncelle ve Güncel Kullanıcıyı Dön
    # Bu JIT call, lokal DB'yi en son bilgilerle güncelleyecektir.
    updated_user_response = await get_user_details_for_admin(user_id, current_admin_payload, db, settings)
    
    # get_or_create_user'ı çağırarak lokal DB'deki temel bilgilerin de (isim, rol vs.) güncel olduğundan emin olalım
    user_crud.get_or_create_user(db, user_pydantic_models.UserCreateInternal(
        id=updated_user_response.id,
        email=updated_user_response.email,
        full_name=updated_user_response.full_name,
        roles=updated_user_response.roles,
        is_active=updated_user_response.is_active
    ))
    
    return updated_user_response

@app.get(f"{API_PREFIX}/admin/users/{{user_id}}", response_model=user_pydantic_models.User, tags=["Admin - Users"])
async def get_user_details_for_admin(
    user_id: uuid.UUID,
    current_admin_payload: Annotated[Dict, Depends(get_current_user_payload)],
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """(TEK VE DOĞRU VERSİYON) Belirli bir kullanıcının detaylarını getirir."""
    if "general-admin" not in current_admin_payload.get("realm_access", {}).get("roles", []):
        raise HTTPException(status_code=403, detail="Bu işlem için yetkiniz yok.")

    db_user = user_crud.get_user_by_keycloak_id(db, user_id)
    if not db_user:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı.")

    kc_user_details = await keycloak_api_helpers.get_keycloak_user(str(user_id), settings)
    kc_user_groups = await keycloak_api_helpers.get_user_keycloak_groups(str(user_id), settings)
    
    kc_roles = kc_user_details.get("realmRoles", []) if kc_user_details else []
    kc_is_active = kc_user_details.get("enabled", db_user.is_active) if kc_user_details else db_user.is_active

    user_company_info = None
    if kc_user_groups:
        kc_group_id_str = kc_user_groups[0].get('id')
        if kc_group_id_str:
            try:
                company = company_crud.get_company_by_keycloak_group_id(db, uuid.UUID(kc_group_id_str))
                if company:
                    user_company_info = user_pydantic_models.CompanyBasicInfo.from_orm(company)
            except (ValueError, IndexError):
                print(f"UYARI: Kullanıcı grupları işlenirken hata oluştu. ID: {user_id}")

    return user_pydantic_models.User(
        id=db_user.id,
        email=db_user.email,
        full_name=db_user.full_name,
        roles=kc_roles,
        is_active=kc_is_active,
        created_at=db_user.created_at,
        company=user_company_info
    )

@app.post(f"{API_PREFIX}/users/sync-from-keycloak", response_model=user_pydantic_models.User, tags=["Internal"])
async def sync_user_from_keycloak(
    user_in: user_pydantic_models.UserCreateInternal,
    is_internal: Annotated[bool, Depends(verify_internal_secret)],
    db: Session = Depends(get_db)
):
    """İç servis çağrısıyla kullanıcıyı lokal DB'ye senkronize eder/oluşturur."""
    if not is_internal: raise HTTPException(status_code=403, detail="Yetkisiz erişim.")
    db_user = user_crud.get_or_create_user(db=db, user_data=user_in)
    return user_pydantic_models.User(
        id=db_user.id, email=db_user.email, full_name=db_user.full_name,
        roles=user_in.roles, is_active=db_user.is_active, created_at=db_user.created_at
    )

@app.get(f"{API_PREFIX}/users/me", response_model=user_pydantic_models.User, tags=["Users"])
async def read_users_me(
    current_user_payload: Annotated[Dict, Depends(get_current_user_payload)],
    db: Session = Depends(get_db)
):
    """Mevcut (login olmuş) kullanıcının bilgilerini JIT Provisioning ile getirir."""
    keycloak_id_str = current_user_payload.get("sub")
    email = current_user_payload.get("email")
    if not keycloak_id_str or not email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Token içinde ID veya e-posta eksik.")

    user_data = user_pydantic_models.UserCreateInternal(
        id=uuid.UUID(keycloak_id_str),
        email=email,
        full_name=current_user_payload.get("name", email),
        roles=current_user_payload.get("realm_access", {}).get("roles", []),
        is_active=current_user_payload.get("email_verified", True)
    )
    db_user = user_crud.get_or_create_user(db=db, user_data=user_data)
    
    return user_pydantic_models.User(
        id=db_user.id, email=db_user.email, full_name=db_user.full_name,
        roles=user_data.roles, is_active=db_user.is_active, created_at=db_user.created_at
    )