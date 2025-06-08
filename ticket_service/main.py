# ticket_service/main.py

import uuid
from typing import List, Dict, Any, Annotated

import httpx
from fastapi import FastAPI, Depends, HTTPException, status, Response, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from fastapi.responses import FileResponse

# Yerel ve ortak modüllerin import edilmesi
from database_pkg import db_models
from database_pkg.database import get_db
from . import crud as ticket_crud
from . import models as ticket_models
from .auth import get_current_user_payload
from .config import Settings, get_settings
# DÜZELTME: Sınıf yerine doğrudan fonksiyonu import ediyoruz.
from .keycloak_admin_api import get_group_id_from_path

import shutil
from pathlib import Path
import os

app = FastAPI(
    title="Ticket Service API",
    description="Helpdesk uygulaması için bilet (ticket) yönetim servisi.",
    version="1.2.0",
)

USER_SERVICE_URL = "http://localhost:8001" 

# CORS Ayarları
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:8080"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/", tags=["Root"])
async def read_root():
    return {"message": "Ticket Service çalışıyor."}

@app.post("/tickets/", response_model=ticket_models.Ticket, status_code=status.HTTP_201_CREATED, tags=["Tickets"])
async def create_ticket(
    ticket: ticket_models.TicketCreate,
    db: Session = Depends(get_db),
    current_user_payload: dict = Depends(get_current_user_payload),
    settings: Settings = Depends(get_settings),
):
    """Yeni bir destek bileti oluşturur."""
    user_sub = current_user_payload.get("sub")
    user_roles = current_user_payload.get("realm_access", {}).get("roles", [])
    user_groups = current_user_payload.get("tenant_groups", [])
    creator_id = uuid.UUID(user_sub)

    # 1. Biletin ait olacağı Tenant'ın Keycloak Grup ID'sini belirle
    determined_keycloak_group_id = None
    
    # DÜZELTME: "customer-user" rolünü de tenant belirleme mantığına dahil ediyoruz.
    if ("agent" in user_roles or "helpdesk_admin" in user_roles or "customer-user" in user_roles) and user_groups:
        # Bir kullanıcı kendi tenant'ı için bilet oluşturur.
        # Şimdilik kullanıcının sadece ilk grubuna ait olduğunu varsayıyoruz.
        group_path = user_groups[0]
        group_id_obj = await get_group_id_from_path(group_path, settings)
        if group_id_obj:
            determined_keycloak_group_id = group_id_obj

    if not determined_keycloak_group_id:
        # general-admin gibi bir rol biletsiz tenant oluşturamaz (bu mantıklı).
        raise HTTPException(status_code=400, detail="Biletin ait olacağı tenant belirlenemedi. Kullanıcının bir gruba atanmış olması gerekir.")

    # 2. Keycloak Grup ID'sini kullanarak LOKAL COMPANY ID'sini bul
    local_company = ticket_crud.get_company_by_keycloak_group_id(db, keycloak_group_id=determined_keycloak_group_id)
    if not local_company:
        raise HTTPException(status_code=404, detail=f"Tenant (Grup ID: {determined_keycloak_group_id}) lokal veritabanında bulunamadı.")
    
    # 3. Kullanıcıyı API üzerinden JIT ile senkronize et
    user_sync_payload = {
        "id": user_sub,
        "email": current_user_payload.get("email"),
        "full_name": current_user_payload.get("name", "Unknown User"),
        "is_active": current_user_payload.get("active", True),
        "roles": user_roles,
        "company_id": str(local_company.id)
    }

    sync_url = f"{USER_SERVICE_URL}/users/sync-from-keycloak"
    headers = {"X-Internal-Secret": settings.internal_service_secret}
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(sync_url, json=user_sync_payload, headers=headers)
            response.raise_for_status()
            print(f"User {user_sub} synced with user_service successfully.")
    except httpx.RequestError as exc:
        raise HTTPException(status_code=503, detail=f"user_service'e ulaşılamıyor: {exc}")
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=exc.response.status_code, detail=f"user_service senkronizasyon hatası: {exc.response.text}")

    # 4. Bileti, doğru olan LOKAL COMPANY ID'si ile oluştur
    db_ticket = ticket_crud.create_ticket(db=db, ticket=ticket, creator_id=creator_id, tenant_id=local_company.id)
    return db_ticket



@app.get("/tickets/", response_model=List[ticket_models.Ticket], tags=["Tickets"])
async def read_tickets_list(
    current_user_payload: Annotated[Dict[str, Any], Depends(get_current_user_payload)],
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    skip: int = 0,
    limit: int = 100,
):
    """Kullanıcının rolüne ve tenant'ına göre biletleri listeler."""
    user_sub = uuid.UUID(current_user_payload.get('sub'))
    user_roles = current_user_payload.get("realm_access", {}).get("roles", [])
    user_tenant_paths = current_user_payload.get("tenant_groups", [])

    query = db.query(db_models.Ticket)

    # 1. Rol bazlı filtreleme mantığı
    if "general-admin" in user_roles:
        # general-admin tüm biletleri görür, ek filtre yok.
        pass
    elif "agent" in user_roles or "helpdesk_admin" in user_roles:
        # DÜZELTME BAŞLANGICI: Keycloak Grup ID'lerini Lokal Şirket ID'lerine çeviriyoruz.
        if not user_tenant_paths:
            return [] # Kullanıcı hiçbir gruba atanmamışsa boş liste döner.

        # 2. Önce kullanıcının Keycloak'taki grup ID'lerini bulalım.
        user_keycloak_group_ids = [await get_group_id_from_path(path, settings) for path in user_tenant_paths]
        user_keycloak_group_ids = [uid for uid in user_keycloak_group_ids if uid is not None]

        if not user_keycloak_group_ids:
            return [] # Grup ID'leri çözümlenemezse boş liste döner.

        # 3. Şimdi bu Keycloak Grup ID'lerine karşılık gelen LOKAL ŞİRKET ID'lerini bulalım.
        local_companies = db.query(db_models.Company).filter(db_models.Company.keycloak_group_id.in_(user_keycloak_group_ids)).all()
        user_local_company_ids = [company.id for company in local_companies]
        
        if not user_local_company_ids:
            return [] # Lokal DB'de karşılıkları yoksa boş liste döner.
            
        # 4. Veritabanını doğru olan LOKAL ID'lere göre filtreleyelim.
        query = query.filter(db_models.Ticket.tenant_id.in_(user_local_company_ids))
        # DÜZELTME SONU
    elif "customer-user" in user_roles:
        # Müşteri sadece kendi oluşturduğu biletleri görür.
        query = query.filter(db_models.Ticket.creator_id == user_sub)
    else:
        # Bilinmeyen veya yetkisiz roller boş liste görür.
        return []

    # 5. Sonuçları sırala ve döndür
    db_tickets = query.order_by(db_models.Ticket.created_at.desc()).offset(skip).limit(limit).all()
    return db_tickets


@app.get("/tickets/{ticket_id}", response_model=ticket_models.TicketWithDetails, tags=["Tickets"])
async def read_ticket_details(
    ticket_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user_payload: dict = Depends(get_current_user_payload),
    settings: Settings = Depends(get_settings),
):
    """Belirli bir biletin tüm detaylarını getirir ve yetki kontrolü yapar."""
    user_sub = uuid.UUID(current_user_payload.get("sub"))
    user_roles = current_user_payload.get("realm_access", {}).get("roles", [])
    
    db_ticket = ticket_crud.get_ticket_with_details(db, ticket_id=ticket_id)
    if db_ticket is None:
        raise HTTPException(status_code=404, detail="Bilet bulunamadı")

    # Yetkilendirme mantığı
    can_access = False
    if "general-admin" in user_roles:
        can_access = True
    elif "customer-user" in user_roles:
        if db_ticket.creator_id == user_sub:
            can_access = True
    elif "agent" in user_roles or "helpdesk_admin" in user_roles:
        # DÜZELTME BAŞLANGICI: Keycloak ID'lerini lokal ID'lere çeviriyoruz
        user_tenant_paths = current_user_payload.get("tenant_groups", [])
        
        user_keycloak_group_ids = [await get_group_id_from_path(path, settings) for path in user_tenant_paths]
        user_keycloak_group_ids = [uid for uid in user_keycloak_group_ids if uid is not None]

        if user_keycloak_group_ids:
            # Keycloak ID'leri ile lokal şirketleri sorgula
            local_companies = db.query(db_models.Company).filter(db_models.Company.keycloak_group_id.in_(user_keycloak_group_ids)).all()
            user_local_company_ids = [company.id for company in local_companies]
            
            # Karşılaştırmayı DOĞRU olan lokal ID'ler ile yap
            if db_ticket.tenant_id in user_local_company_ids:
                can_access = True
        # DÜZELTME SONU
    
    if not can_access:
        raise HTTPException(status_code=403, detail="Bu bileti görüntüleme yetkiniz yok.")
        
    return db_ticket


@app.patch("/tickets/{ticket_id}", response_model=ticket_models.Ticket, tags=["Tickets"])
async def update_ticket(
    ticket_id: uuid.UUID,
    ticket_update: ticket_models.TicketUpdate,
    db: Session = Depends(get_db),
    current_user_payload: dict = Depends(get_current_user_payload),
    settings: Settings = Depends(get_settings),
):
    """Bir biletin durumunu veya diğer alanlarını günceller (Sadece agent ve adminler)."""
    user_roles = current_user_payload.get("realm_access", {}).get("roles", [])

    if "customer-user" in user_roles:
        raise HTTPException(status_code=403, detail="Biletleri sadece yetkili personel güncelleyebilir.")

    db_ticket = ticket_crud.get_ticket(db, ticket_id)
    if not db_ticket:
        raise HTTPException(status_code=404, detail="Güncellenecek bilet bulunamadı.")

    can_update = False
    if "general-admin" in user_roles:
        can_update = True
    elif "agent" in user_roles or "helpdesk_admin" in user_roles:
        user_tenant_paths = current_user_payload.get("tenant_groups", [])
        user_tenant_ids = [await get_group_id_from_path(path, settings) for path in user_tenant_paths]
        if db_ticket.tenant_id in user_tenant_ids:
            can_update = True

    if not can_update:
        raise HTTPException(status_code=403, detail="Bu bileti güncelleme yetkiniz yok.")

    return ticket_crud.update_ticket(db=db, ticket_id=ticket_id, ticket_update=ticket_update)


@app.delete("/tickets/{ticket_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Tickets"])
async def delete_ticket(
    ticket_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user_payload: dict = Depends(get_current_user_payload),
    settings: Settings = Depends(get_settings),
):
    """Bir bileti siler (Sadece adminler)."""
    user_roles = current_user_payload.get("realm_access", {}).get("roles", [])

    if "agent" in user_roles or "customer-user" in user_roles:
        raise HTTPException(status_code=403, detail="Bilet silme yetkisi sadece adminlere aittir.")

    db_ticket = ticket_crud.get_ticket(db, ticket_id)
    if not db_ticket:
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    can_delete = False
    if "general-admin" in user_roles:
        can_delete = True
    elif "helpdesk-admin" in user_roles:
        user_tenant_paths = current_user_payload.get("tenant_groups", [])
        user_tenant_ids = [await get_group_id_from_path(path, settings) for path in user_tenant_paths]
        if db_ticket.tenant_id in user_tenant_ids:
            can_delete = True

    if not can_delete:
        raise HTTPException(status_code=403, detail="Bu bileti silme yetkiniz yok.")

    ticket_crud.delete_ticket(db=db, ticket_id=ticket_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@app.post("/tickets/{ticket_id}/comments", response_model=ticket_models.Comment, status_code=status.HTTP_201_CREATED, tags=["Comments"])
async def create_ticket_comment(
    ticket_id: uuid.UUID,
    comment: ticket_models.CommentCreate,
    db: Session = Depends(get_db),
    current_user_payload: dict = Depends(get_current_user_payload)
):
    """
    Belirli bir bilete yeni bir yorum ekler.
    """
    author_id = uuid.UUID(current_user_payload.get("sub"))
    
    # Yorum yapmadan önce kullanıcının bileti görme yetkisi var mı diye kontrol edilebilir.
    # Şimdilik bu kontrolü atlayarak devam ediyoruz.
    db_ticket = ticket_crud.get_ticket(db, ticket_id=ticket_id)
    if not db_ticket:
        raise HTTPException(status_code=404, detail="Yorum yapılacak bilet bulunamadı.")
    
    # Yorumu veritabanına kaydet
    new_comment = ticket_crud.create_comment(db=db, comment=comment, ticket_id=ticket_id, author_id=author_id)
    return new_comment

@app.post("/tickets/{ticket_id}/attachments", response_model=List[ticket_models.Attachment], tags=["Attachments"])
async def upload_ticket_attachments(
    ticket_id: uuid.UUID,
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
    current_user_payload: dict = Depends(get_current_user_payload),
):
    """
    Belirli bir bilete bir veya daha fazla dosya ekler.
    """
    uploader_id = uuid.UUID(current_user_payload.get("sub"))
    
    # Yetki kontrolü (kullanıcı bu bilete dosya ekleyebilir mi?)
    # Şimdilik basit bir kontrol yapıyoruz, bu detaylandırılabilir.
    db_ticket = ticket_crud.get_ticket(db, ticket_id=ticket_id)
    if not db_ticket:
        raise HTTPException(status_code=404, detail="Dosya eklenecek bilet bulunamadı.")
    
    # Yüklenecek dosyaların kaydedileceği klasör
    UPLOAD_DIRECTORY = Path("uploads") / str(ticket_id)
    UPLOAD_DIRECTORY.mkdir(parents=True, exist_ok=True)
    
    saved_attachments = []
    for file in files:
        # Güvenli ve benzersiz bir dosya adı oluştur
        unique_suffix = uuid.uuid4().hex
        file_extension = Path(file.filename).suffix
        unique_filename = f"{unique_suffix}{file_extension}"
        file_location = UPLOAD_DIRECTORY / unique_filename

        # Dosyayı sunucuya kaydet
        try:
            with open(file_location, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
        finally:
            file.file.close()

        # Veritabanına kaydet
        db_attachment = ticket_crud.create_attachment(
            db=db,
            file_name=file.filename,
            file_path=str(file_location),
            file_type=file.content_type,
            ticket_id=ticket_id,
            uploader_id=uploader_id
        )
        saved_attachments.append(db_attachment)

    return saved_attachments

@app.get("/attachments/{attachment_id}", tags=["Attachments"])
async def download_attachment(
    attachment_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user_payload: dict = Depends(get_current_user_payload)
):
    """
    ID'si verilen bir dosyayı, kullanıcının yetkisi varsa indirilebilir olarak sunar.
    """
    # 1. Veritabanından attachment kaydını bul
    attachment = ticket_crud.get_attachment(db, attachment_id=attachment_id)
    if not attachment:
        raise HTTPException(status_code=404, detail="Dosya eki bulunamadı.")

    # 2. Yetki Kontrolü: Kullanıcının bu eki indirmeye yetkisi var mı?
    # Bunun için ekin ait olduğu bileti görme yetkisine sahip olmalı.
    # Bu mantığı read_ticket_details endpoint'inden kopyalayabiliriz.
    db_ticket = ticket_crud.get_ticket(db, ticket_id=attachment.ticket_id)
    if not db_ticket:
         raise HTTPException(status_code=404, detail="Dosyanın ait olduğu bilet bulunamadı.")

    user_sub = uuid.UUID(current_user_payload.get("sub"))
    user_roles = current_user_payload.get("realm_access", {}).get("roles", [])
    
    can_access = False
    if "general-admin" in user_roles:
        can_access = True
    elif "customer-user" in user_roles and db_ticket.creator_id == user_sub:
        can_access = True
    # Not: Agent/Helpdesk admin yetkilendirmesi daha karmaşık olduğu için şimdilik atlıyoruz.
    # Onu da eklemek için tenant kontrolü yapılmalıdır.
    
    if not can_access:
        raise HTTPException(status_code=403, detail="Bu dosyayı indirme yetkiniz yok.")

    # 3. Dosyanın fiziksel olarak varlığını kontrol et
    file_path = attachment.file_path
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Dosya sunucuda bulunamadı. Lütfen yöneticiyle iletişime geçin.")

    # 4. Dosyayı FileResponse ile döndür
    return FileResponse(
        path=file_path, 
        media_type='application/octet-stream', # Tarayıcının dosyayı açmak yerine indirmeye zorlaması için
        filename=attachment.file_name # Kullanıcının bilgisayarına indirilecek dosya adı
    )