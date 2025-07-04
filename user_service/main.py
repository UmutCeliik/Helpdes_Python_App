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

# Yerel modüller
from . import crud as user_crud
from . import company_crud
from . import keycloak_api_helpers
from . import db_models
from . import models as user_pydantic_models
from .database import get_db, SessionLocal
from .auth import get_current_user_payload, verify_internal_secret
from .config import Settings, get_settings
from .logging_config import setup_logging, LoggingMiddleware

# Loglamayı başlat
SERVICE_NAME = "user_service"
logger = setup_logging(SERVICE_NAME)

async def sync_all_tenants_from_keycloak_on_startup(db: Session, settings: Settings):
    """Keycloak'taki grupları lokal 'companies' tablosuyla senkronize eder."""
    logger.info("STARTUP_SYNC: Tenant (group) synchronization starting...")
    try:
        all_kc_groups = await keycloak_api_helpers.get_all_keycloak_groups_paginated(settings)
        if all_kc_groups is None:
            logger.error("STARTUP_SYNC: Admin token could not be obtained. Tenant sync skipped.")
            return

        for group_rep in all_kc_groups:
            kc_group_id_str = group_rep.get("id")
            kc_group_name = group_rep.get("name")
            if not kc_group_id_str or not kc_group_name:
                continue
            
            kc_group_uuid = uuid.UUID(kc_group_id_str)
            company_in_db = company_crud.get_company_by_keycloak_group_id(db, keycloak_group_id=kc_group_uuid)

            if not company_in_db:
                new_company_data = user_pydantic_models.CompanyCreate(
                    name=kc_group_name,
                    keycloak_group_id=kc_group_uuid,
                    status="active"
                )
                company_crud.create_company(db, company=new_company_data)
                logger.info(f"STARTUP_SYNC: New tenant added from Keycloak: {kc_group_name}")
            elif company_in_db.name != kc_group_name:
                company_crud.update_company(db, company_in_db, user_pydantic_models.CompanyUpdate(name=kc_group_name))
                logger.info(f"STARTUP_SYNC: Tenant name updated from Keycloak: {kc_group_name}")

        logger.info("STARTUP_SYNC: Tenant synchronization finished.")
    except Exception:
        logger.exception("CRITICAL_ERROR (Startup Sync - Tenants)")

async def sync_all_users_from_keycloak_on_startup(db: Session, settings: Settings):
    """Keycloak'taki kullanıcıları lokal 'users' tablosuyla senkronize eder."""
    logger.info("STARTUP_SYNC: User synchronization starting...")
    try:
        all_kc_users = await keycloak_api_helpers.get_all_keycloak_users_paginated(settings)
        if all_kc_users is None:
            logger.error("STARTUP_SYNC: Admin token could not be obtained. User sync skipped.")
            return

        for user_rep in all_kc_users:
            user_id_str = user_rep.get("id")
            if not user_id_str or not user_rep.get("email"):
                continue

            user_create_data = user_pydantic_models.UserCreateInternal(
                id=uuid.UUID(user_id_str),
                email=user_rep.get("email"),
                full_name=f"{user_rep.get('firstName', '')} {user_rep.get('lastName', '')}".strip() or user_rep.get("username"),
                roles=user_rep.get("realmRoles", []),
                is_active=user_rep.get("enabled", False)
            )
            user_crud.get_or_create_user(db, user_data=user_create_data)
        
        logger.info("STARTUP_SYNC: User synchronization finished.")
    except Exception:
        logger.exception("CRITICAL_ERROR (Startup Sync - Users)")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Uygulama yaşam döngüsü yöneticisi."""
    logger.info("Application startup...")
    app_settings = get_settings()
    
    logger.info("Configuration loaded", extra={
        "config": {
            "database_url_loaded": bool(app_settings.database.url),
            "keycloak_issuer": app_settings.keycloak.issuer_uri,
            "keycloak_admin_client_id_loaded": bool(app_settings.keycloak.admin_client_id),
            "vault_addr": app_settings.vault.addr,
            "vault_token_loaded": bool(app_settings.vault.token),
            "internal_secret_loaded": bool(app_settings.internal_service_secret)
        }
    })
    
    db_session = SessionLocal()
    try:
        await sync_all_tenants_from_keycloak_on_startup(db=db_session, settings=app_settings)
        await sync_all_users_from_keycloak_on_startup(db=db_session, settings=app_settings)
    finally:
        db_session.close()
    yield
    logger.info("Application shutdown.")

API_PREFIX = "/api/users"

app = FastAPI(
    title="User Service API",
    description="Helpdesk uygulaması için Kullanıcı ve Şirket (Tenant) Yönetimi Servisi.",
    version="1.4.0",
    lifespan=lifespan,
)

app.add_middleware(LoggingMiddleware, logger=logger)
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

@app.get(f"{API_PREFIX}/", tags=["Root"])
async def read_root_user_service():
    logger.info("Root endpoint of user_service was called.")
    return {"message": "User Service API is running"}

@app.get(f"{API_PREFIX}/healthz", status_code=status.HTTP_200_OK, tags=["Health Check"])
def health_check():
    return {"status": "healthy"}

@app.post(f"{API_PREFIX}/admin/tenants", response_model=user_pydantic_models.Company, status_code=status.HTTP_201_CREATED, summary="Yeni bir tenant (müşteri şirketi) oluşturur (Sadece General Admin)")
async def create_new_tenant(
    tenant_request: user_pydantic_models.TenantCreateRequest, 
    current_user_payload: Annotated[Dict[str, Any], Depends(get_current_user_payload)],
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings)
):
    user_roles = current_user_payload.get("realm_access", {}).get("roles", [])
    if "general-admin" not in user_roles:
        logger.warning(f"Unauthorized tenant creation attempt by user {current_user_payload.get('sub')}.", extra={"user_roles": user_roles})
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bu işlemi yapma yetkiniz yok.")

    logger.info(f"Admin {current_user_payload.get('sub')} attempting to create tenant with name: '{tenant_request.name}'")
    
    existing_company_by_name = company_crud.get_company_by_name(db, name=tenant_request.name)
    if existing_company_by_name:
        logger.warning(f"Tenant name '{tenant_request.name}' already exists locally with ID {existing_company_by_name.id}.")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"'{tenant_request.name}' adlı şirket zaten mevcut.")

    created_keycloak_group_id_str = await keycloak_api_helpers.create_keycloak_group(
        group_name=tenant_request.name, 
        settings=settings
    )

    if created_keycloak_group_id_str is None:
        logger.error(f"Failed to create Keycloak group for tenant '{tenant_request.name}'. Helper returned None.")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Keycloak'ta müşteri grubu oluşturulurken bir hata oluştu.")
    
    if created_keycloak_group_id_str == "EXISTS":
        logger.warning(f"A Keycloak group named '{tenant_request.name}' already exists.")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"'{tenant_request.name}' adında bir Keycloak grubu zaten mevcut.")

    try:
        keycloak_group_uuid = uuid.UUID(created_keycloak_group_id_str)
    except ValueError:
        logger.error(f"Keycloak returned an invalid UUID for group ID: '{created_keycloak_group_id_str}'")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Keycloak'tan geçersiz grup ID formatı alındı.")

    existing_company_by_kc_id = company_crud.get_company_by_keycloak_group_id(db, keycloak_group_id=keycloak_group_uuid)
    if existing_company_by_kc_id:
        logger.error(f"Keycloak group ID '{keycloak_group_uuid}' already linked to local company '{existing_company_by_kc_id.name}'. This is an inconsistency.")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Kritik sistem hatası: Keycloak grup ID çakışması.")

    company_to_create = user_pydantic_models.CompanyCreate(
        name=tenant_request.name,
        keycloak_group_id=keycloak_group_uuid,
        status="active" 
    )
    
    try:
        db_company = company_crud.create_company(db=db, company=company_to_create)
        logger.info(f"Tenant '{db_company.name}' (ID: {db_company.id}) created successfully with Keycloak Group ID: {db_company.keycloak_group_id}")
        return db_company
    except IntegrityError as e: 
        db.rollback()
        logger.error(f"IntegrityError while saving company to DB: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Şirket adı veya Keycloak ID'si veritabanında zaten mevcut.")
    except Exception as e:
        db.rollback()
        logger.exception("Unexpected error while saving company to DB.")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Şirket veritabanına kaydedilirken bir hata oluştu.")

@app.delete(f"{API_PREFIX}/admin/tenants/{{company_id}}", status_code=status.HTTP_204_NO_CONTENT, summary="Belirli bir tenant'ı siler (Sadece General Admin)")
async def delete_tenant_by_admin(
    company_id: uuid.UUID,
    current_user_payload: Annotated[Dict[str, Any], Depends(get_current_user_payload)],
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings)
):
    user_roles = current_user_payload.get("realm_access", {}).get("roles", [])
    if "general-admin" not in user_roles:
        logger.warning(f"Unauthorized tenant deletion attempt by user {current_user_payload.get('sub')}.", extra={"user_roles": user_roles})
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bu işlemi yapma yetkiniz yok.")

    logger.info(f"Admin {current_user_payload.get('sub')} attempting to delete company (tenant) with ID: {company_id}")

    db_company = company_crud.get_company(db, company_id=company_id)
    if not db_company:
        logger.warning(f"Company with ID {company_id} not found in local DB. Nothing to delete.")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Silinecek şirket (tenant) bulunamadı.")

    if db_company.keycloak_group_id:
        logger.info(f"Attempting to delete Keycloak group with ID: {db_company.keycloak_group_id} (associated with company '{db_company.name}')")
        keycloak_group_deleted = await keycloak_api_helpers.delete_keycloak_group(str(db_company.keycloak_group_id), settings)
        if not keycloak_group_deleted:
            logger.error(f"Keycloak group (ID: {db_company.keycloak_group_id}) could not be deleted. Local company record will NOT be deleted.")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Keycloak'ta şirket grubu silinirken bir sorun oluştu.")
        logger.info(f"Keycloak group (ID: {db_company.keycloak_group_id}) deleted successfully (or was already not present).")
    else:
        logger.warning(f"Company '{db_company.name}' (ID: {company_id}) has no associated Keycloak group ID. Skipping Keycloak group deletion.")

    deleted_company_from_db = company_crud.delete_company(db, company_id=company_id)
    if deleted_company_from_db is None:
        logger.error(f"Company (ID: {company_id}) was found but could not be deleted from local DB. This is unexpected.")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Şirket lokal veritabanından silinirken bir sorun oluştu.")
    
    logger.info(f"Company '{deleted_company_from_db.name}' (ID: {company_id}) and its Keycloak group have been deleted.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@app.get(f"{API_PREFIX}/admin/users/{{user_id}}", response_model=user_pydantic_models.User, tags=["Admin - User Management"])
async def read_user_details_for_admin(
    user_id: uuid.UUID,
    current_admin_payload: Annotated[dict, Depends(get_current_user_payload)],
    settings: Annotated[Settings, Depends(get_settings)],
    db: Annotated[Session, Depends(get_db)]
):
    """(General Admin Only) Belirli bir kullanıcının detaylarını getirir."""
    if "general-admin" not in current_admin_payload.get("realm_access", {}).get("roles", []):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bu işlem için yetkiniz yok.")

    logger.info(f"Admin {current_admin_payload.get('sub')} fetching details for user {user_id}")
    db_user = user_crud.get_user_by_keycloak_id(db, keycloak_id=user_id)
    if not db_user:
        logger.warning(f"User with ID '{user_id}' not found in local DB.")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Kullanıcı ID '{user_id}' bulunamadı.")

    kc_user_details = await keycloak_api_helpers.get_keycloak_user(str(user_id), settings)
    kc_roles = kc_user_details.get("realmRoles", []) if kc_user_details else []
    if not kc_user_details:
        logger.warning(f"User {user_id} exists in local DB but not found in Keycloak. Data may be inconsistent.")

    user_company_info: Optional[user_pydantic_models.CompanyBasicInfo] = None
    kc_user_groups = await keycloak_api_helpers.get_user_keycloak_groups(str(user_id), settings)
    
    if kc_user_groups:
        for group_representation in kc_user_groups:
            keycloak_group_id_str = group_representation.get("id")
            if keycloak_group_id_str:
                try:
                    kc_group_uuid = uuid.UUID(keycloak_group_id_str)
                    company_in_db = company_crud.get_company_by_keycloak_group_id(db, keycloak_group_id=kc_group_uuid)
                    if company_in_db:
                        user_company_info = user_pydantic_models.CompanyBasicInfo.from_orm(company_in_db)
                        break
                except ValueError:
                    logger.warning(f"Keycloak group ID '{keycloak_group_id_str}' for user {user_id} is not a valid UUID.")
                    continue
    
    user_response = user_pydantic_models.User(
        id=db_user.id,
        email=db_user.email,
        full_name=db_user.full_name,
        is_active=kc_user_details.get("enabled", db_user.is_active) if kc_user_details else db_user.is_active,
        created_at=db_user.created_at,
        roles=kc_roles,
        company=user_company_info
    )
    return user_response


@app.patch(f"{API_PREFIX}/admin/users/{{user_id}}", response_model=user_pydantic_models.User, tags=["Admin - User Management"])
async def update_user_for_admin(
    user_id: uuid.UUID,
    user_update_data: user_pydantic_models.AdminUserUpdateRequest,
    current_admin_payload: Annotated[dict, Depends(get_current_user_payload)],
    settings: Annotated[Settings, Depends(get_settings)],
    db: Annotated[Session, Depends(get_db)]
):
    """(General Admin Only) Belirli bir kullanıcının bilgilerini günceller."""
    if "general-admin" not in current_admin_payload.get("realm_access", {}).get("roles", []):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bu işlem için yetkiniz yok.")

    logger.info(f"Admin {current_admin_payload.get('sub')} attempting to update user {user_id} with data: {user_update_data.model_dump(exclude_unset=True)}")
    db_user = user_crud.get_user_by_keycloak_id(db, keycloak_id=user_id)
    if not db_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Güncellenecek kullanıcı ID '{user_id}' bulunamadı.")

    kc_user_id_str = str(user_id)
    kc_attributes_to_update = {}

    if user_update_data.full_name is not None and db_user.full_name != user_update_data.full_name:
        name_parts = user_update_data.full_name.strip().split(" ", 1)
        kc_attributes_to_update["firstName"] = name_parts[0]
        kc_attributes_to_update["lastName"] = name_parts[1] if len(name_parts) > 1 else ""
        db_user.full_name = user_update_data.full_name
        logger.info(f"User {kc_user_id_str}: Full name will be updated to -> {user_update_data.full_name}")

    if user_update_data.is_active is not None and db_user.is_active != user_update_data.is_active:
        kc_attributes_to_update["enabled"] = user_update_data.is_active
        db_user.is_active = user_update_data.is_active
        logger.info(f"User {kc_user_id_str}: Active status will be updated to -> {user_update_data.is_active}")

    if kc_attributes_to_update:
        if not await keycloak_api_helpers.update_keycloak_user_attributes(kc_user_id_str, kc_attributes_to_update, settings):
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Keycloak'ta kullanıcı attribute'ları güncellenirken hata oluştu.")

    if user_update_data.roles is not None:
        logger.info(f"User {kc_user_id_str}: Roles will be updated to -> {user_update_data.roles}")
        if not await keycloak_api_helpers.set_user_realm_roles(kc_user_id_str, user_update_data.roles, settings):
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Keycloak'ta kullanıcı rolleri güncellenirken hata oluştu.")
        
        determined_local_role = user_pydantic_models.Role.EMPLOYEE
        if user_update_data.roles:
            if "general-admin" in user_update_data.roles: determined_local_role = user_pydantic_models.Role.GENERAL_ADMIN
            elif "helpdesk-admin" in user_update_data.roles: determined_local_role = user_pydantic_models.Role.HELPDESK_ADMIN
            elif "agent" in user_update_data.roles: determined_local_role = user_pydantic_models.Role.AGENT
        if db_user.role != determined_local_role: db_user.role = determined_local_role

    if "tenant_id" in user_update_data.model_fields_set:
        new_tenant_id = user_update_data.tenant_id
        logger.info(f"User {kc_user_id_str}: Tenant assignment will be updated. New local DB tenant_id: {new_tenant_id}")
        
        current_kc_groups = await keycloak_api_helpers.get_user_keycloak_groups(kc_user_id_str, settings)
        if current_kc_groups:
            for group in current_kc_groups:
                await keycloak_api_helpers.remove_user_from_keycloak_group(kc_user_id_str, group.get("id"), settings)
        
        if new_tenant_id is not None:
            target_company_db = company_crud.get_company(db, company_id=new_tenant_id)
            if not target_company_db:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Belirtilen tenant_id '{new_tenant_id}' ile şirket bulunamadı.")
            if not target_company_db.keycloak_group_id:
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Hedef şirket '{target_company_db.name}' için Keycloak grup ID'si tanımlanmamış.")
            
            if not await keycloak_api_helpers.add_user_to_group(kc_user_id_str, str(target_company_db.keycloak_group_id), settings):
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Kullanıcı yeni Keycloak grubuna eklenirken hata oluştu.")
        
        db_user.company_id = new_tenant_id

    db.add(db_user)
    db.commit()
    db.refresh(db_user)

    return await read_user_details_for_admin(user_id, current_admin_payload, settings, db)

@app.get(f"{API_PREFIX}/internal/users/{{user_id}}", response_model=user_pydantic_models.User, tags=["Internal"])
async def get_user_for_internal_service(
    user_id: uuid.UUID,
    is_internal: Annotated[bool, Depends(verify_internal_secret)],
    db: Session = Depends(get_db)
):
    """İç servis iletişimi için belirli bir kullanıcının detaylarını döndürür."""
    if not is_internal:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Yetkisiz erişim.")
    
    logger.info(f"Internal call received: Fetching details for user_id: {user_id}")
    db_user = user_crud.get_user_by_keycloak_id(db, keycloak_id=user_id)
    
    if not db_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kullanıcı bulunamadı.")
        
    return db_user

@app.post(f"{API_PREFIX}/admin/users", response_model=user_pydantic_models.User, status_code=status.HTTP_201_CREATED, summary="Yeni bir kullanıcı oluşturur (Keycloak + Lokal DB) (Sadece General Admin)")
async def admin_create_user(
    request_data: user_pydantic_models.AdminUserCreateRequest,
    current_user_payload: Annotated[Dict[str, Any], Depends(get_current_user_payload)],
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings)
):
    user_roles_from_token = current_user_payload.get("realm_access", {}).get("roles", [])
    if "general-admin" not in user_roles_from_token:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bu işlemi yapma yetkiniz yok.")

    logger.info(f"Admin {current_user_payload.get('sub')} attempting to create user with email: {request_data.email}")

    keycloak_group_id_to_assign: Optional[str] = None
    if request_data.tenant_id:
        company = company_crud.get_company(db, company_id=request_data.tenant_id)
        if not company:
            logger.error(f"Specified tenant_id ({request_data.tenant_id}) not found.")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Belirtilen tenant ID ({request_data.tenant_id}) ile şirket bulunamadı.")
        if not company.keycloak_group_id:
            logger.error(f"Company '{company.name}' is missing Keycloak group ID configuration.")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Şirketin Keycloak grup ID yapılandırması eksik.")
        keycloak_group_id_to_assign = str(company.keycloak_group_id)
        logger.info(f"User will be assigned to Keycloak group ID: {keycloak_group_id_to_assign} (Tenant: {company.name})")

    first_name, last_name = _split_full_name(request_data.full_name)
    user_representation_for_kc = {
        "username": request_data.email,
        "email": request_data.email,
        "firstName": first_name,
        "lastName": last_name,
        "enabled": request_data.is_active,
        "emailVerified": True
    }
    
    new_kc_user_id_str = await keycloak_api_helpers.create_keycloak_user(user_representation_for_kc, settings)

    if new_kc_user_id_str is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Keycloak'ta kullanıcı oluşturulurken bir hata oluştu. Logları kontrol edin.")
    if new_kc_user_id_str == "EXISTS":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"'{request_data.email}' e-posta adresine veya kullanıcı adına sahip bir kullanıcı Keycloak'ta zaten mevcut.")
    
    logger.info(f"User created in Keycloak with ID: {new_kc_user_id_str}")

    if not await keycloak_api_helpers.set_keycloak_user_password(new_kc_user_id_str, request_data.password, True, settings):
        logger.critical(f"User created in Keycloak (ID: {new_kc_user_id_str}) BUT password could not be set!")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Kullanıcı şifresi Keycloak'ta ayarlanamadı. Kullanıcı eksik yapılandırılmış olabilir.")

    if request_data.roles:
        if not await keycloak_api_helpers.assign_realm_roles_to_user(new_kc_user_id_str, request_data.roles, settings):
            logger.warning(f"User created in Keycloak (ID: {new_kc_user_id_str}) BUT roles ({request_data.roles}) could not be fully assigned.")

    if keycloak_group_id_to_assign:
        if not await keycloak_api_helpers.add_user_to_group(new_kc_user_id_str, keycloak_group_id_to_assign, settings):
            logger.warning(f"User created in Keycloak (ID: {new_kc_user_id_str}) BUT could not be added to group ({keycloak_group_id_to_assign}).")

    try:
        new_user_keycloak_id_uuid = uuid.UUID(new_kc_user_id_str)
    except ValueError:
        logger.critical(f"Keycloak returned an invalid user ID format: '{new_kc_user_id_str}'")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Keycloak'tan geçersiz kullanıcı ID formatı alındı.")

    user_data_for_local_db = user_pydantic_models.UserCreateInternal(
        id=new_user_keycloak_id_uuid,
        email=request_data.email,
        full_name=request_data.full_name,
        roles=request_data.roles,
        is_active=request_data.is_active
    )
    
    try:
        db_user = user_crud.get_or_create_user(db=db, user_data=user_data_for_local_db)
        if request_data.tenant_id:
            db_user.company_id = request_data.tenant_id
            db.commit()
            db.refresh(db_user)
    except IntegrityError as e:
        db.rollback()
        logger.error(f"IntegrityError while saving user to local DB: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Kullanıcı bilgileri lokal veritabanıyla çakışıyor.")
    except Exception:
        db.rollback()
        logger.exception("Unexpected error while saving user to local DB.")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Kullanıcı lokal veritabanına kaydedilirken bir hata oluştu.")

    logger.info(f"User '{db_user.email}' (ID: {db_user.id}) successfully created in Keycloak and synced to local DB.")
    
    # En güncel bilgiyi döndürmek için GET endpoint'ini çağır
    return await read_user_details_for_admin(db_user.id, current_user_payload, settings, db)

app.post(f"{API_PREFIX}/internal/users/sync", response_model=user_pydantic_models.User, tags=["Internal"])
async def sync_user_internally(
    sync_data: user_pydantic_models.UserCreateInternal,
    db: Session = Depends(get_db),
    is_internal: Annotated[bool, Depends(verify_internal_secret)] = False,
):
    """İç servis çağrısıyla kullanıcıyı lokal DB'ye senkronize eder/oluşturur ve tenant bilgisini günceller."""
    if not is_internal: 
        logger.warning("Unauthorized attempt to access internal sync endpoint.")
        raise HTTPException(status_code=403, detail="Yetkisiz erişim.")

    logger.info(f"Internal sync call received for user: {sync_data.id}")
    db_user = user_crud.get_or_create_user(db=db, user_data=sync_data)
    
    user_company_info = None
    if sync_data.keycloak_groups:
        group_path = sync_data.keycloak_groups[0]
        group_name = group_path.strip("/").split("/")[-1]
        
        company = company_crud.get_company_by_name(db, name=group_name)
        if company:
            db_user.company_id = company.id
            db.commit()
            db.refresh(db_user)
            user_company_info = user_pydantic_models.CompanyBasicInfo.from_orm(company)

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

@app.get(f"{API_PREFIX}/admin/users", response_model=UserListResponse, summary="Tüm kullanıcıları listeler (Sadece General Admin)")
async def list_users_for_admin(
    current_user_payload: Annotated[Dict[str, Any], Depends(get_current_user_payload)],
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 100
):
    user_roles_from_token = current_user_payload.get("realm_access", {}).get("roles", [])
    if "general-admin" not in user_roles_from_token:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bu işlemi yapma yetkiniz yok.")

    logger.info(f"Admin '{current_user_payload.get('sub')}' listing users. Skip: {skip}, Limit: {limit}")
    
    db_users = user_crud.get_users(db, skip=skip, limit=limit)
    total_users = user_crud.count_users(db)
    
    pydantic_users: List[user_pydantic_models.User] = []
    for db_user in db_users:
        db_role_str_list = [str(db_user.role.value)] if db_user.role else []
        pydantic_users.append(user_pydantic_models.User.from_orm(db_user))
        
    return UserListResponse(items=pydantic_users, total=total_users)


@app.get(f"{API_PREFIX}/admin/tenants", response_model=user_pydantic_models.CompanyList, summary="Tüm tenantları (müşteri şirketlerini) listeler (Sadece General Admin)")
async def list_tenants(
    current_user_payload: Annotated[Dict[str, Any], Depends(get_current_user_payload)],
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 100
):
    user_roles = current_user_payload.get("realm_access", {}).get("roles", [])
    if "general-admin" not in user_roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bu işlemi yapma yetkiniz yok.")

    logger.info(f"Admin '{current_user_payload.get('sub')}' listing tenants. Skip: {skip}, Limit: {limit}")
    
    companies = company_crud.get_companies(db, skip=skip, limit=limit)
    total_companies = company_crud.count_companies(db)
    
    return user_pydantic_models.CompanyList(items=companies, total=total_companies)

@app.get(f"{API_PREFIX}/admin/tenants/{{company_id}}", response_model=user_pydantic_models.Company, summary="Belirli bir tenantın detaylarını getirir (Sadece General Admin)")
async def get_tenant_details(
    company_id: uuid.UUID, 
    current_user_payload: Annotated[Dict[str, Any], Depends(get_current_user_payload)],
    db: Session = Depends(get_db)
):
    user_roles = current_user_payload.get("realm_access", {}).get("roles", [])
    if "general-admin" not in user_roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bu işlemi yapma yetkiniz yok.")

    logger.info(f"Admin '{current_user_payload.get('sub')}' requesting details for company ID: {company_id}")
    
    db_company = company_crud.get_company(db, company_id=company_id)
    if db_company is None:
        logger.warning(f"Company with ID {company_id} not found.")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Şirket (tenant) bulunamadı.")
    
    return db_company

@app.patch(f"{API_PREFIX}/admin/tenants/{{company_id}}", response_model=user_pydantic_models.Company, summary="Belirli bir tenantın statüsünü veya adını günceller (Sadece General Admin)")
async def update_tenant_details(
    company_id: uuid.UUID, 
    company_update_request: user_pydantic_models.CompanyUpdate,
    current_user_payload: Annotated[Dict[str, Any], Depends(get_current_user_payload)],
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings)
):
    user_roles = current_user_payload.get("realm_access", {}).get("roles", [])
    if "general-admin" not in user_roles:
        logger.warning(f"Unauthorized tenant update attempt by user {current_user_payload.get('sub')}.")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bu işlemi yapma yetkiniz yok.")

    logger.info(f"Admin {current_user_payload.get('sub')} attempting to update company {company_id} with data: {company_update_request.model_dump(exclude_unset=True)}")

    db_company = company_crud.get_company(db, company_id=company_id)
    if db_company is None:
        logger.warning(f"Company with ID {company_id} not found for update.")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Güncellenecek şirket (tenant) bulunamadı.")

    if company_update_request.name is not None and company_update_request.name != db_company.name:
        logger.info(f"Name update requested from '{db_company.name}' to '{company_update_request.name}'.")
        
        existing_company_with_new_name = company_crud.get_company_by_name(db, name=company_update_request.name)
        if existing_company_with_new_name and existing_company_with_new_name.id != company_id:
            logger.warning(f"Attempt to update company name to '{company_update_request.name}', but this name is already used by company ID {existing_company_with_new_name.id}.")
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"'{company_update_request.name}' adlı şirket zaten mevcut.")

        if not db_company.keycloak_group_id:
            logger.error(f"Company '{db_company.name}' has no Keycloak group ID. Cannot update Keycloak group name.")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Şirketin Keycloak yapılandırması eksik, ad güncellenemiyor.")

        if not await keycloak_api_helpers.update_keycloak_group(str(db_company.keycloak_group_id), company_update_request.name, settings):
            logger.error(f"Failed to update Keycloak group name for group ID {db_company.keycloak_group_id}. Local DB will not be updated.")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Keycloak'ta şirket adı güncellenirken bir sorun oluştu.")
        
        logger.info(f"Keycloak group name updated successfully for group ID: {db_company.keycloak_group_id}.")

    updated_company = company_crud.update_company(db=db, company_db=db_company, company_in=company_update_request)
    logger.info(f"Company '{updated_company.name}' (ID: {updated_company.id}) updated successfully in local DB.")
    return updated_company

@app.delete(f"{API_PREFIX}/admin/users/{{user_id}}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Belirli bir kullanıcıyı sistemden (Keycloak ve lokal DB) siler (Sadece General Admin)"
)
async def admin_delete_user(
    user_id: uuid.UUID,
    current_admin_payload: Annotated[Dict[str, Any], Depends(get_current_user_payload)],
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings)
):
    admin_id = current_admin_payload.get('sub')
    admin_roles = current_admin_payload.get("realm_access", {}).get("roles", [])

    if "general-admin" not in admin_roles:
        logger.warning(f"Unauthorized user deletion attempt by user: {admin_id}", extra={"target_user_id": str(user_id)})
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bu işlemi yapma yetkiniz yok.")

    logger.info(f"Admin {admin_id} attempting to delete user with ID: {user_id}")

    # 1. Keycloak'tan kullanıcıyı silmeyi dene
    kc_user_deleted_successfully = await keycloak_api_helpers.delete_keycloak_user(str(user_id), settings)

    if not kc_user_deleted_successfully:
        logger.error(f"Failed to delete user from Keycloak (ID: {user_id}). Halting operation. Admin: {admin_id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Kullanıcı Keycloak'ta silinirken bir sorun oluştu. Lokal veritabanı etkilenmedi."
        )
    
    logger.info(f"User (ID: {user_id}) successfully deleted from Keycloak (or was not found).")

    # 2. Lokal veritabanından kullanıcıyı sil
    deleted_db_user = user_crud.delete_user_by_keycloak_id(db, keycloak_id=user_id)

    if deleted_db_user:
        logger.info(f"User (ID: {user_id}, Email: {deleted_db_user.email}) also deleted from local DB.")
    else:
        logger.info(f"User (ID: {user_id}) was not found in local DB (possibly already deleted or never synced).")

    return Response(status_code=status.HTTP_204_NO_CONTENT)

@app.patch(f"{API_PREFIX}/admin/users/{{user_id}}", response_model=user_pydantic_models.User, tags=["Admin - User Management"])
async def admin_update_user(
    user_id: uuid.UUID,
    update_data: user_pydantic_models.AdminUserUpdateRequest,
    current_admin_payload: Annotated[Dict, Depends(get_current_user_payload)],
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """Bir kullanıcının adını, aktiflik durumunu, rollerini ve tenant'ını günceller."""
    admin_id = current_admin_payload.get('sub')
    if "general-admin" not in current_admin_payload.get("realm_access", {}).get("roles", []):
        logger.warning(f"Unauthorized user update attempt by user: {admin_id}", extra={"target_user_id": str(user_id)})
        raise HTTPException(status_code=403, detail="Bu işlemi yapma yetkiniz yok.")

    logger.info(f"Admin {admin_id} attempting to update user {user_id} with data: {update_data.model_dump(exclude_unset=True)}")

    db_user = user_crud.get_user_by_keycloak_id(db, user_id)
    if not db_user:
        logger.warning(f"User {user_id} not found in DB for update.", extra={"admin_id": admin_id})
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
        logger.info(f"Updating user attributes in Keycloak for user {user_id}", extra={"attributes": kc_attribs_to_update})
        if not await keycloak_api_helpers.update_keycloak_user_attributes(kc_user_id_str, kc_attribs_to_update, settings):
            raise HTTPException(status_code=500, detail="Keycloak'ta kullanıcı özellikleri güncellenemedi.")

    # 2. Rolleri Güncelle
    if "roles" in update_data.model_fields_set:
        logger.info(f"Updating roles in Keycloak for user {user_id}", extra={"new_roles": update_data.roles})
        if not await keycloak_api_helpers.set_user_realm_roles(kc_user_id_str, update_data.roles, settings):
            raise HTTPException(status_code=500, detail="Keycloak'ta kullanıcı rolleri güncellenemedi.")
    
    # 3. Tenant/Grup Atamasını Güncelle
    if "tenant_id" in update_data.model_fields_set:
        new_tenant_id = update_data.tenant_id
        logger.info(f"Updating tenant assignment for user {user_id}", extra={"new_tenant_id": str(new_tenant_id)})
        current_kc_groups = await keycloak_api_helpers.get_user_keycloak_groups(kc_user_id_str, settings)
        for group in current_kc_groups or []:
            await keycloak_api_helpers.remove_user_from_keycloak_group(kc_user_id_str, group['id'], settings)
        
        if new_tenant_id is not None:
            target_company = company_crud.get_company(db, new_tenant_id)
            if not target_company or not target_company.keycloak_group_id:
                raise HTTPException(status_code=404, detail="Hedef tenant veya Keycloak grup ID'si bulunamadı.")
            await keycloak_api_helpers.add_user_to_group(kc_user_id_str, str(target_company.keycloak_group_id), settings)

    # 4. Lokal DB'yi Güncelle ve Güncel Kullanıcıyı Dön
    updated_user_response = await read_user_details_for_admin(user_id, current_admin_payload, settings, db)
    
    user_crud.get_or_create_user(db, user_pydantic_models.UserCreateInternal(
        id=updated_user_response.id,
        email=updated_user_response.email,
        full_name=updated_user_response.full_name,
        roles=updated_user_response.roles,
        is_active=updated_user_response.is_active
    ))
    
    logger.info(f"User {user_id} updated successfully by admin {admin_id}.")
    return updated_user_response

@app.get(f"{API_PREFIX}/admin/users/{{user_id}}", response_model=user_pydantic_models.User, tags=["Admin - Users"])
async def get_user_details_for_admin(
    user_id: uuid.UUID,
    current_admin_payload: Annotated[Dict, Depends(get_current_user_payload)],
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """(General Admin Only) Belirli bir kullanıcının detaylarını getirir."""
    if "general-admin" not in current_admin_payload.get("realm_access", {}).get("roles", []):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bu işlem için yetkiniz yok.")

    db_user = user_crud.get_user_by_keycloak_id(db, user_id)
    if not db_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kullanıcı bulunamadı.")

    kc_user_details = await keycloak_api_helpers.get_keycloak_user(str(user_id), settings)
    kc_user_groups = await keycloak_api_helpers.get_user_keycloak_groups(str(user_id), settings)
    
    kc_roles = kc_user_details.get("realmRoles", []) if kc_user_details else []
    kc_is_active = kc_user_details.get("enabled", db_user.is_active) if kc_user_details else db_user.is_active

    if not kc_user_details:
        logger.warning(f"User {user_id} exists in local DB but not found in Keycloak. Data may be inconsistent.")

    user_company_info = None
    if kc_user_groups:
        if len(kc_user_groups) > 0:
            kc_group_id_str = kc_user_groups[0].get('id')
            if kc_group_id_str:
                try:
                    company = company_crud.get_company_by_keycloak_group_id(db, uuid.UUID(kc_group_id_str))
                    if company:
                        user_company_info = user_pydantic_models.CompanyBasicInfo.from_orm(company)
                except (ValueError, IndexError):
                    logger.warning(f"Could not process group info for user {user_id}", extra={"group_id": kc_group_id_str})

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
        logger.error("Token is missing 'sub' or 'email' claim.")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Token içinde ID veya e-posta eksik.")

    logger.debug(f"Handling /users/me for user {keycloak_id_str}")
    user_data = user_pydantic_models.UserCreateInternal(
        id=uuid.UUID(keycloak_id_str),
        email=email,
        full_name=current_user_payload.get("name", email),
        roles=current_user_payload.get("realm_access", {}).get("roles", []),
        is_active=current_user_payload.get("email_verified", True)
    )
    db_user = user_crud.get_or_create_user(db=db, user_data=user_data)
    
    return user_pydantic_models.User.from_orm(db_user)