# ticket_service/main.py
from fastapi import FastAPI, HTTPException, status, Depends, Response
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict, Any, Annotated, Optional
import uuid
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
import httpx

# Ortak ve yerel modülleri import et
from database_pkg.database import get_db
# SQLAlchemy DB Modelleri (User, Ticket) için doğru import
from database_pkg import db_models as common_db_models # <-- DÜZELTİLMİŞ IMPORT
from database_pkg.schemas import Role as RoleEnum
from . import models as ticket_models # ticket_service Pydantic modelleri
from . import crud as ticket_crud
from .auth import get_current_user_payload
from .config import get_settings, Settings
from .keycloak_admin_api import get_group_id_from_path

app = FastAPI(
    title="Ticket Service API - Keycloak Integrated (Multi-Tenant WIP)",
    description="Helpdesk Ticket Service with multi-tenancy support in progress."
)

USER_SERVICE_URL = "http://localhost:8001"

# CORS Ayarları
origins = [
    "http://localhost:5173",
    "http://localhost:8080",
    "http://localhost:3000",
    "http://localhost",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def read_root(settings: Settings = Depends(get_settings)):
    return {"message": "Ticket Service API'ye hoş geldiniz! Multi-Tenancy geliştiriliyor."}


@app.post("/tickets/", response_model=ticket_models.Ticket, status_code=status.HTTP_201_CREATED)
async def create_ticket(
    ticket_in: ticket_models.TicketCreate,
    current_user_payload: Annotated[Dict[str, Any], Depends(get_current_user_payload)],
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings)
):
    keycloak_id_str = current_user_payload.get("sub")
    if not keycloak_id_str:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token ID (sub) yok")
    
    creator_id_uuid = uuid.UUID(keycloak_id_str)

    user_roles = current_user_payload.get("roles", [])
    if not user_roles and current_user_payload.get("realm_access"):
        user_roles = current_user_payload.get("realm_access", {}).get("roles", [])
    
    # --- ROL TANIMA İÇİN DEBUG LOGLARI ---
    print(f"DEBUG (POST /tickets/): Raw user_roles from payload: {user_roles}, Type: {type(user_roles)}")
    # --- ROL TANIMA İÇİN DEBUG LOGLARI SONU ---
        
    user_tenant_groups_paths = current_user_payload.get("tenant_groups", []) 

    determined_tenant_id: Optional[uuid.UUID] = None
    
    log_prefix = f"INFO (POST /tickets/ User: {creator_id_uuid}, Roles: {user_roles}, Groups: {user_tenant_groups_paths}):"
    print(f"{log_prefix} Starting tenant ID determination.")

    is_customer_user = "customer-user" in user_roles
    is_agent_type = any(role in user_roles for role in ["agent", "helpdesk_admin", "general-admin"])
    
    # --- ROL TANIMA İÇİN DEBUG LOGLARI ---
    print(f"DEBUG (POST /tickets/): Checking for 'customer-user' in {user_roles}. Result: {is_customer_user}")
    print(f"DEBUG (POST /tickets/): Is agent_type? {is_agent_type}")
    # --- ROL TANIMA İÇİN DEBUG LOGLARI SONU ---

    if is_customer_user:
        if len(user_tenant_groups_paths) == 1:
            customer_group_path = user_tenant_groups_paths[0]
            print(f"{log_prefix} customer-user belongs to group path: {customer_group_path}. Resolving to ID...")
            resolved_id = await get_group_id_from_path(customer_group_path, settings)
            if resolved_id:
                determined_tenant_id = resolved_id
                print(f"{log_prefix} Resolved tenant ID for customer-user: {determined_tenant_id}")
            else:
                print(f"ERROR ({log_prefix}): Could not resolve group ID for path {customer_group_path}.")
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Kullanıcının müşteri şirketi ID'si ({customer_group_path}) çözümlenemedi.")
        elif len(user_tenant_groups_paths) == 0:
            print(f"ERROR ({log_prefix}): customer-user not assigned to any tenant group.")
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Müşteri kullanıcısı herhangi bir şirkete atanmamış.")
        else: 
            print(f"ERROR ({log_prefix}): customer-user assigned to multiple tenant groups ({len(user_tenant_groups_paths)}).")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Müşteri kullanıcısı birden fazla şirkete atanmış olamaz.")

    elif is_agent_type:
        if ticket_in.tenant_id_override:
            determined_tenant_id = ticket_in.tenant_id_override
            print(f"{log_prefix} agent_type user using tenant_id_override: {determined_tenant_id}")
        elif len(user_tenant_groups_paths) == 1:
            agent_group_path = user_tenant_groups_paths[0]
            print(f"{log_prefix} agent_type user (single tenant assignment: {agent_group_path}). Resolving to ID...")
            resolved_id = await get_group_id_from_path(agent_group_path, settings)
            if resolved_id:
                determined_tenant_id = resolved_id
                print(f"{log_prefix} Resolved tenant ID for single-tenant agent_type: {determined_tenant_id}")
            else:
                print(f"ERROR ({log_prefix}): Could not resolve group ID for agent_type path {agent_group_path}.")
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Agent/Admin kullanıcısının müşteri şirketi ID'si ({agent_group_path}) çözümlenemedi.")
        elif len(user_tenant_groups_paths) > 1 and "general-admin" not in user_roles:
            print(f"ERROR ({log_prefix}): agent/helpdesk_admin serves multiple tenants but no tenant_id_override provided.")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Birden fazla müşteri şirketine hizmet veriyorsunuz. Lütfen bilet için bir 'tenant_id_override' belirtin.")
        elif "general-admin" in user_roles and not ticket_in.tenant_id_override:
             print(f"ERROR ({log_prefix}): general-admin creating ticket without tenant_id_override.")
             raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="General admin olarak bilet oluştururken bir 'tenant_id_override' belirtmelisiniz.")
        elif len(user_tenant_groups_paths) == 0 and "general-admin" not in user_roles:
             print(f"ERROR ({log_prefix}): agent/helpdesk_admin not assigned to any tenant group.")
             raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bu kullanıcı herhangi bir müşteri şirketine atanmamış.")
        else: 
            print(f"WARN ({log_prefix}): Unhandled tenant ID determination case for agent_type.")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Bilet için müşteri şirketi (tenant) belirlenemedi (agent_type).")
    else:
        print(f"ERROR ({log_prefix}): User role not recognized for ticket creation logic. Roles present: {user_roles}") # Rolleri loga ekle
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bu rolle bilet oluşturma yetkiniz yok.")

    if determined_tenant_id is None:
        print(f"CRITICAL ERROR ({log_prefix}): determined_tenant_id is still None after logic processing.")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Bilet için müşteri şirketi (tenant) atanamadı. Sistem yöneticinize başvurun.")
    
    print(f"{log_prefix} Final determined_tenant_id: {determined_tenant_id}")

    # Kullanıcıyı user_service üzerinden senkronize et
    try:
        keycloak_roles_for_sync = current_user_payload.get("roles", []) 
        if not keycloak_roles_for_sync and current_user_payload.get("realm_access"):
            keycloak_roles_for_sync = current_user_payload.get("realm_access", {}).get("roles", [])
        user_sync_payload = {
            "id": keycloak_id_str, "email": current_user_payload.get("email"),
            "full_name": current_user_payload.get("name") or f"{current_user_payload.get('given_name', '')} {current_user_payload.get('family_name', '')}".strip() or current_user_payload.get("preferred_username"),
            "roles": keycloak_roles_for_sync, "is_active": current_user_payload.get("email_verified", True)
        }
        internal_secret = settings.internal_service_secret
        if not internal_secret:
             print(f"ERROR ({log_prefix}): internal_service_secret not loaded. Cannot call user_service.")
             raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Dahili sunucu yapılandırma hatası: Servis iletişim sırrı yüklenemedi.")
        print(f"{log_prefix} Syncing user {keycloak_id_str} with user_service...")
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{USER_SERVICE_URL}/users/sync-from-keycloak", json=user_sync_payload, headers={"X-Internal-Secret": internal_secret})
            response.raise_for_status()
            synced_user = response.json()
            print(f"{log_prefix} User {synced_user.get('id')} synced/retrieved from user_service.")
    except httpx.HTTPStatusError as e:
        error_detail = f"Kullanıcı servisi ile senkronizasyon hatası: {e.response.status_code}"
        try: user_service_error = e.response.json(); error_detail += f" - {user_service_error.get('detail', e.response.text)}"
        except Exception: error_detail += f" - Yanıt: {e.response.text}"
        print(f"ERROR ({log_prefix}): Failed to sync user with user_service. Details: {error_detail}")
        status_code_to_raise = e.response.status_code if e.response.status_code in [401, 403] else status.HTTP_503_SERVICE_UNAVAILABLE
        raise HTTPException(status_code=status_code_to_raise, detail=error_detail)
    except Exception as e:
        print(f"ERROR ({log_prefix}): Unexpected error during user sync: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Kullanıcı senkronizasyonu sırasında beklenmedik hata.")

    print(f"{log_prefix} Creating ticket in DB: user_sub={keycloak_id_str}, DB creator_id={creator_id_uuid}, tenant_id={determined_tenant_id}")
    try:
        created_db_ticket = ticket_crud.create_ticket(db=db, ticket=ticket_in, creator_id=creator_id_uuid, tenant_id=determined_tenant_id)
        return created_db_ticket 
    except IntegrityError as e:
        db.rollback(); print(f"ERROR ({log_prefix}): IntegrityError while creating ticket: {e}"); raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Bilet oluşturulurken veritabanı bütünlük hatası.")
    except Exception as e:
        db.rollback(); print(f"ERROR ({log_prefix}): Unexpected error while creating ticket: {e}"); raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Bilet oluşturulurken beklenmedik bir sunucu hatası oluştu.")


@app.get("/tickets/", response_model=List[ticket_models.Ticket])
async def read_tickets_list(
    current_user_payload: Annotated[Dict[str, Any], Depends(get_current_user_payload)],
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings)
):
    user_sub_str = current_user_payload.get('sub') # <--- KULLANICI SUB'INI AL
    if not user_sub_str: # <--- SUB KONTROLÜ
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token ID (sub) yok")
    user_sub_uuid = uuid.UUID(user_sub_str) # <--- SUB'I UUID'YE ÇEVİR

    user_roles = current_user_payload.get("roles", [])
    if not user_roles and current_user_payload.get("realm_access"):
        user_roles = current_user_payload.get("realm_access", {}).get("roles", [])
    
    user_tenant_groups_paths = current_user_payload.get("tenant_groups", [])
    
    log_prefix = f"INFO (GET /tickets/ User: {user_sub_str}, Roles: {user_roles}, Groups: {user_tenant_groups_paths}):" # user_sub_str kullanıldı
    print(f"{log_prefix} Listing tickets.")
    
    query = db.query(common_db_models.Ticket)

    if "customer-user" in user_roles:
        if len(user_tenant_groups_paths) == 1:
            customer_tenant_path = user_tenant_groups_paths[0]
            customer_tenant_id = await get_group_id_from_path(customer_tenant_path, settings)
            if customer_tenant_id:
                print(f"{log_prefix} customer-user filtering by tenant_id: {customer_tenant_id} AND creator_id: {user_sub_uuid}") # <--- LOG GÜNCELLENDİ
                query = query.filter(common_db_models.Ticket.tenant_id == customer_tenant_id)
                query = query.filter(common_db_models.Ticket.creator_id == user_sub_uuid) # <--- YENİ FİLTRE: Sadece kendi oluşturduğu biletler
            else:
                print(f"WARN ({log_prefix}): Could not resolve tenant ID for customer-user path {customer_tenant_path}. Returning no tickets for this user.")
                return [] 
        else: 
            print(f"WARN ({log_prefix}): customer-user has {len(user_tenant_groups_paths)} tenant groups or no groups. Returning no tickets.")
            return []
            
    elif "agent" in user_roles or "helpdesk_admin" in user_roles:
        if user_tenant_groups_paths:
            agent_tenant_ids: List[uuid.UUID] = []
            for group_path in user_tenant_groups_paths:
                resolved_id = await get_group_id_from_path(group_path, settings)
                if resolved_id:
                    agent_tenant_ids.append(resolved_id)
            
            if agent_tenant_ids:
                print(f"{log_prefix} agent/helpdesk_admin filtering by tenant_ids: {agent_tenant_ids}")
                query = query.filter(common_db_models.Ticket.tenant_id.in_(agent_tenant_ids))
            else: 
                print(f"WARN ({log_prefix}): Could not resolve any tenant IDs for agent/helpdesk_admin or no groups assigned. Returning no tickets.")
                return []
        else: 
            print(f"WARN ({log_prefix}): agent/helpdesk_admin not assigned to any tenant groups. Returning no tickets.")
            return []
    
    elif "general-admin" in user_roles:
        print(f"{log_prefix} general-admin accessing all tickets (no tenant filter applied).")
        # general-admin için ek filtre yok, tüm biletleri görebilir.
        pass 
        
    else: 
        print(f"WARN ({log_prefix}): Unknown role or not authorized to list tickets. Returning no tickets.")
        return []

    db_tickets = query.order_by(common_db_models.Ticket.created_at.desc()).offset(skip).limit(limit).all()
    return db_tickets


@app.get("/tickets/{ticket_id}", response_model=ticket_models.Ticket)
async def read_ticket(
    ticket_id: uuid.UUID,
    current_user_payload: Annotated[Dict[str, Any], Depends(get_current_user_payload)],
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings)
):
    user_sub_str = current_user_payload.get("sub")
    user_roles = current_user_payload.get("roles", [])
    if not user_roles and current_user_payload.get("realm_access"):
        user_roles = current_user_payload.get("realm_access", {}).get("roles", [])
    user_tenant_groups_paths = current_user_payload.get("tenant_groups", [])

    log_prefix = f"INFO (GET /tickets/{{ticket_id}} User: {user_sub_str}, Roles: {user_roles}, Groups: {user_tenant_groups_paths}):"
    print(f"{log_prefix} Reading ticket {ticket_id}")

    db_ticket = ticket_crud.get_ticket(db=db, ticket_id=ticket_id)
    if db_ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bilet bulunamadı")

    ticket_tenant_id = db_ticket.tenant_id
    can_access = False

    if "general-admin" in user_roles:
        print(f"{log_prefix} general-admin accessing ticket {ticket_id} from tenant {ticket_tenant_id}.")
        return db_ticket 
    
    allowed_tenant_ids_for_user: List[uuid.UUID] = []
    for group_path in user_tenant_groups_paths:
        resolved_id = await get_group_id_from_path(group_path, settings)
        if resolved_id:
            allowed_tenant_ids_for_user.append(resolved_id)
    
    print(f"{log_prefix} User allowed tenant_ids: {allowed_tenant_ids_for_user}")
    print(f"{log_prefix} Ticket's tenant_id: {ticket_tenant_id}")

    if ticket_tenant_id in allowed_tenant_ids_for_user:
        if "customer-user" in user_roles:
            # <--- YENİ/DEĞİŞEN SATIR BAŞLANGICI ---
            if str(db_ticket.creator_id) == user_sub_str: # Kullanıcı ID'si UUID olduğu için string'e çevirerek karşılaştır
                can_access = True 
                print(f"{log_prefix} customer_user accessing own ticket within their tenant.")
            else:
                print(f"ERROR ({log_prefix}): customer_user ({user_sub_str}) trying to access ticket ({ticket_id}) not created by them (creator: {db_ticket.creator_id}) within their tenant.")
            # <--- YENİ/DEĞİŞEN SATIR SONU ---
        elif "agent" in user_roles or "helpdesk_admin" in user_roles:
            can_access = True
            print(f"{log_prefix} agent/helpdesk_admin accessing ticket within their assigned tenant.")
            
    if not can_access:
        print(f"ERROR ({log_prefix}): User not authorized to view ticket {ticket_id}. Ticket tenant: {ticket_tenant_id}, User allowed tenants: {allowed_tenant_ids_for_user}")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bu bileti görüntüleme yetkiniz yok")
    
    return db_ticket


@app.patch("/tickets/{ticket_id}", response_model=ticket_models.Ticket)
async def update_ticket_status(
    ticket_id: uuid.UUID,
    ticket_update: ticket_models.TicketUpdate,
    current_user_payload: Annotated[Dict[str, Any], Depends(get_current_user_payload)],
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings)
):
    user_sub_str = current_user_payload.get("sub")
    user_roles = current_user_payload.get("roles", [])
    if not user_roles and current_user_payload.get("realm_access"):
        user_roles = current_user_payload.get("realm_access", {}).get("roles", [])
    user_tenant_groups_paths = current_user_payload.get("tenant_groups", [])

    log_prefix = f"INFO (PATCH /tickets/{{ticket_id}} User: {user_sub_str}, Roles: {user_roles}, Groups: {user_tenant_groups_paths}):"
    print(f"{log_prefix} Updating ticket {ticket_id} with data: {ticket_update.model_dump_json(exclude_unset=True)}")

    db_ticket = ticket_crud.get_ticket(db=db, ticket_id=ticket_id)
    if db_ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Güncellenecek bilet bulunamadı")

    ticket_tenant_id = db_ticket.tenant_id
    can_update = False

    # <--- YENİ KONTROL BAŞLANGICI ---
    if "customer-user" in user_roles:
        print(f"ERROR ({log_prefix}): customer-user ({user_sub_str}) not allowed to update ticket {ticket_id} via this endpoint.")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bilet güncelleme yetkiniz yok (customer-user).")
    # <--- YENİ KONTROL SONU ---

    if "general-admin" in user_roles:
        can_update = True 
        print(f"{log_prefix} general-admin updating ticket {ticket_id} in tenant {ticket_tenant_id}.")
    elif "agent" in user_roles or "helpdesk_admin" in user_roles:
        allowed_tenant_ids_for_user: List[uuid.UUID] = []
        for group_path in user_tenant_groups_paths:
            resolved_id = await get_group_id_from_path(group_path, settings)
            if resolved_id:
                allowed_tenant_ids_for_user.append(resolved_id)
        
        if ticket_tenant_id in allowed_tenant_ids_for_user:
            can_update = True
            print(f"{log_prefix} agent/helpdesk_admin updating ticket {ticket_id} within their assigned tenant {ticket_tenant_id}.")

    if not can_update:
        print(f"ERROR ({log_prefix}): User not authorized to update ticket {ticket_id}. Ticket tenant: {ticket_tenant_id}")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bilet güncelleme yetkiniz yok")

    updated_db_ticket = ticket_crud.update_ticket(db=db, ticket_id=ticket_id, ticket_update=ticket_update)
    if updated_db_ticket is None: 
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Güncellenecek bilet bulunamadı (iç hata).")
    return updated_db_ticket


@app.delete("/tickets/{ticket_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_ticket_endpoint(
    ticket_id: uuid.UUID,
    current_user_payload: Annotated[Dict[str, Any], Depends(get_current_user_payload)],
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings)
):
    user_sub_str = current_user_payload.get("sub")
    user_roles = current_user_payload.get("roles", [])
    if not user_roles and current_user_payload.get("realm_access"):
        user_roles = current_user_payload.get("realm_access", {}).get("roles", [])
    user_tenant_groups_paths = current_user_payload.get("tenant_groups", [])
    
    log_prefix = f"INFO (DELETE /tickets/{{ticket_id}} User: {user_sub_str}, Roles: {user_roles}, Groups: {user_tenant_groups_paths}):"
    print(f"{log_prefix} Deleting ticket {ticket_id}")
    
    db_ticket = ticket_crud.get_ticket(db=db, ticket_id=ticket_id)
    if db_ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Silinecek bilet bulunamadı")

    ticket_tenant_id = db_ticket.tenant_id
    can_delete = False

    if "general-admin" in user_roles:
        can_delete = True
        print(f"{log_prefix} general-admin deleting ticket {ticket_id} in tenant {ticket_tenant_id}.")
    elif "helpdesk-admin" in user_roles:
        allowed_tenant_ids_for_user: List[uuid.UUID] = []
        for group_path in user_tenant_groups_paths:
            resolved_id = await get_group_id_from_path(group_path, settings)
            if resolved_id:
                allowed_tenant_ids_for_user.append(resolved_id)
        
        if ticket_tenant_id in allowed_tenant_ids_for_user:
            can_delete = True
            print(f"{log_prefix} helpdesk_admin deleting ticket {ticket_id} within their assigned tenant {ticket_tenant_id}.")

    if not can_delete:
        print(f"ERROR ({log_prefix}): User not authorized to delete ticket {ticket_id}. Ticket tenant: {ticket_tenant_id}")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bilet silme yetkiniz yok")

    deleted_db_ticket_result = ticket_crud.delete_ticket(db=db, ticket_id=ticket_id)
    if deleted_db_ticket_result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Silinecek bilet bulunamadı (iç hata).")
    return Response(status_code=status.HTTP_204_NO_CONTENT)