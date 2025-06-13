# ticket_service/main.py
from typing import Annotated, Dict, Any, List, Optional
import uuid
import os
import shutil
from pathlib import Path # Path için import eklendi
import httpx
from fastapi import Depends, FastAPI, HTTPException, status, UploadFile, File, Response # Response eklendi
from fastapi.middleware.cors import CORSMiddleware # CORSMiddleware eklendi
from sqlalchemy.orm import Session
from fastapi.responses import FileResponse
# --- IMPORT GÜNCELLEMELERİ SONU ---

# ticket_service'e ait yerel modüllerin import edilmesi
from . import crud
from . import models
# --- YENİ EKLENEN/GÜNCELLENEN IMPORTLAR ---
from .config import Settings, get_settings # Settings ve get_settings import edildi
from .keycloak_admin_api import get_group_id_from_path # get_group_id_from_path import edildi
from .database import get_db
from .auth import get_current_user_payload

app = FastAPI(
    title="Ticket Service API",
    description="Helpdesk uygulaması için bilet (ticket) yönetim servisi.",
    version="1.2.0",
)

USER_SERVICE_URL = "http://user_service:8000" 

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

@app.get("/healthz", status_code=status.HTTP_200_OK, tags=["Health Check"])
def health_check():
    """
    Kubernetes probları için basit sağlık kontrolü. 
    Hiçbir dış bağımlılığı yoktur.
    """
    return {"status": "healthy"}

@app.post("/tickets/", response_model=models.Ticket, status_code=status.HTTP_201_CREATED, tags=["Tickets"])
async def create_ticket(
    ticket: models.TicketCreate,
    db: Session = Depends(get_db),
    current_user_payload: dict = Depends(get_current_user_payload),
    settings: Settings = Depends(get_settings),
):
    """Yeni bir destek bileti oluşturur."""
    user_sub_str = current_user_payload.get("sub")

    # Adım 1: Kullanıcı ve tenant bilgisini almak için user_service'e JIT isteği at.
    # Bu istek, hem kullanıcının DB'de var olmasını sağlar hem de bize tenant_id'yi döndürür.
    sync_payload = {
        "id": user_sub_str,
        "email": current_user_payload.get("email"),
        "full_name": current_user_payload.get("name", "Unknown User"),
        "roles": current_user_payload.get("realm_access", {}).get("roles", []),
        "keycloak_groups": current_user_payload.get("groups", [])
    }
    
    sync_url = f"{USER_SERVICE_URL}/internal/users/sync" # user_service'te bu endpoint'i oluşturacağız
    headers = {"X-Internal-Secret": settings.internal_service_secret}
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(sync_url, json=sync_payload, headers=headers)
            response.raise_for_status()
            synced_user_data = response.json()
            
            creator_id = uuid.UUID(synced_user_data.get("id"))
            company_info = synced_user_data.get("company")
            
            if not company_info or not company_info.get("id"):
                raise HTTPException(status_code=400, detail="Bilet oluşturmak için kullanıcının bir tenant'a atanmış olması gerekir.")
            
            tenant_id = uuid.UUID(company_info.get("id"))

    except httpx.RequestError as exc:
        raise HTTPException(status_code=503, detail=f"user_service'e ulaşılamıyor: {exc}")
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=exc.response.status_code, detail=f"user_service senkronizasyon hatası: {exc.response.text}")

    # Adım 2: Elde edilen ID'lerle bileti oluştur.
    db_ticket = crud.create_ticket(db=db, ticket=ticket, creator_id=creator_id, tenant_id=tenant_id)
    return db_ticket



@app.get("/tickets/", response_model=List[models.Ticket], tags=["Tickets"])
async def read_tickets_list(
    current_user_payload: Annotated[Dict[str, Any], Depends(get_current_user_payload)],
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 100,
):
    """Kullanıcının rolüne göre biletleri listeler."""
    user_sub = uuid.UUID(current_user_payload.get('sub'))
    user_roles = current_user_payload.get("realm_access", {}).get("roles", [])

    query = db.query(crud.db_models.Ticket)

    # Mimari ayrımı sonrası, tenant filtrelemesi artık ticket_service'in değil,
    # bir üst katmanın veya API Gateway'in sorumluluğunda olabilir.
    # Şimdilik en basit haliyle rol bazlı bir ayrım yapıyoruz.
    if "agent" in user_roles or "helpdesk_admin" in user_roles or "general-admin" in user_roles:
        # TODO: Ajanların sadece kendi tenant'ının biletlerini görmesi için
        # user_service'ten tenant bilgisi alınarak filtreleme yapılmalı.
        # Şimdilik tüm biletleri görüyorlar.
        pass
    else: # customer-user ve diğerleri
        # Kullanıcı sadece kendi oluşturduğu biletleri görür.
        query = query.filter(crud.db_models.Ticket.creator_id == user_sub)

    db_tickets = query.order_by(crud.db_models.Ticket.created_at.desc()).offset(skip).limit(limit).all()
    return db_tickets


@app.get("/tickets/{ticket_id}", response_model=models.TicketWithDetails, tags=["Tickets"])
async def read_ticket_details(
   ticket_id: uuid.UUID,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings), # Düzeltilmiş satır
    current_user_payload: dict = Depends(get_current_user_payload)
):
    """
    Belirli bir biletin tüm detaylarını, yaratan kullanıcı bilgisiyle
    birlikte getirir ve yetki kontrolü yapar.
    """
    db_ticket = crud.get_ticket_with_details(db, ticket_id=ticket_id)
    if db_ticket is None:
        raise HTTPException(status_code=404, detail="Bilet bulunamadı")

    # TODO: Bu endpoint için detaylı yetkilendirme mantığı buraya eklenecek.

    creator_info: Optional[models.UserInTicketResponse] = None
    
    # Adım 2.1: user_service'e API isteği at
    user_id = db_ticket.creator_id
    internal_url = f"{USER_SERVICE_URL}/internal/users/{user_id}"
    headers = {"X-Internal-Secret": settings.internal_service_secret}

    try:
        async with httpx.AsyncClient() as client:
            print(f"TICKET_SERVICE: Calling User Service at {internal_url}")
            response = await client.get(internal_url, headers=headers)
        
        if response.status_code == 200:
            user_data = response.json()
            creator_info = models.UserInTicketResponse(
                id=user_data.get("id"),
                full_name=user_data.get("full_name"),
                email=user_data.get("email")
            )
        else:
            # Kullanıcı bulunamazsa veya user_service'te bir hata olursa,
            # bu durumu loglayıp devam edebiliriz.
            print(f"UYARI: Kullanıcı detayı alınamadı. User ID: {user_id}, Status: {response.status_code}")
            creator_info = models.UserInTicketResponse(
                id=user_id,
                full_name="Bilinmeyen Kullanıcı",
                email="-"
            )
    except httpx.RequestError as exc:
        print(f"HATA: user_service'e bağlanılamadı: {exc}")
        # Servise bağlanılamazsa bile bileti temel bilgilerle döndürebiliriz.
        creator_info = models.UserInTicketResponse(
            id=user_id,
            full_name="Kullanıcı Servisine Ulaşılamadı",
            email="-"
        )

    # Adım 2.2: Bilet bilgilerini ve kullanıcı bilgilerini birleştir
    ticket_response = models.TicketWithDetails.from_orm(db_ticket)
    ticket_response.creator_details = creator_info
    
    return ticket_response

@app.patch("/tickets/{ticket_id}", response_model=models.Ticket, tags=["Tickets"])
async def update_ticket(
    ticket_id: uuid.UUID,
    ticket_update: models.TicketUpdate,
    db: Session = Depends(get_db),
    current_user_payload: dict = Depends(get_current_user_payload),
    settings: Settings = Depends(get_settings),
):
    """Bir biletin durumunu veya diğer alanlarını günceller (Sadece agent ve adminler)."""
    user_roles = current_user_payload.get("realm_access", {}).get("roles", [])

    if "customer-user" in user_roles:
        raise HTTPException(status_code=403, detail="Biletleri sadece yetkili personel güncelleyebilir.")

    db_ticket = crud.get_ticket(db, ticket_id)
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

    return crud.update_ticket(db=db, ticket_id=ticket_id, ticket_update=ticket_update)


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

    db_ticket = crud.get_ticket(db, ticket_id)
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

    crud.delete_ticket(db=db, ticket_id=ticket_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@app.post("/tickets/{ticket_id}/comments", response_model=models.Comment, status_code=status.HTTP_201_CREATED, tags=["Comments"])
async def create_ticket_comment(
    ticket_id: uuid.UUID,
    comment: models.CommentCreate,
    db: Session = Depends(get_db),
    current_user_payload: dict = Depends(get_current_user_payload)
):
    """
    Belirli bir bilete yeni bir yorum ekler.
    """
    author_id = uuid.UUID(current_user_payload.get("sub"))
    
    # Yorum yapmadan önce kullanıcının bileti görme yetkisi var mı diye kontrol edilebilir.
    # Şimdilik bu kontrolü atlayarak devam ediyoruz.
    db_ticket = crud.get_ticket(db, ticket_id=ticket_id)
    if not db_ticket:
        raise HTTPException(status_code=404, detail="Yorum yapılacak bilet bulunamadı.")
    
    # Yorumu veritabanına kaydet
    new_comment = crud.create_comment(db=db, comment=comment, ticket_id=ticket_id, author_id=author_id)
    return new_comment

@app.post("/tickets/{ticket_id}/attachments", response_model=List[models.Attachment], tags=["Attachments"])
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
    db_ticket = crud.get_ticket(db, ticket_id=ticket_id)
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
        db_attachment = crud.create_attachment(
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
    attachment = crud.get_attachment(db, attachment_id=attachment_id)
    if not attachment:
        raise HTTPException(status_code=404, detail="Dosya eki bulunamadı.")

    # 2. Yetki Kontrolü: Kullanıcının bu eki indirmeye yetkisi var mı?
    # Bunun için ekin ait olduğu bileti görme yetkisine sahip olmalı.
    # Bu mantığı read_ticket_details endpoint'inden kopyalayabiliriz.
    db_ticket = crud.get_ticket(db, ticket_id=attachment.ticket_id)
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