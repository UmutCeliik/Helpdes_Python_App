# ticket_service/main.py
from typing import Annotated, Dict, Any, List, Optional
import uuid
import os
import shutil
from pathlib import Path
import httpx
from fastapi import Depends, FastAPI, HTTPException, status, UploadFile, File, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from fastapi.responses import FileResponse

from . import crud, models
from .config import Settings, get_settings
from .database import get_db
from .auth import get_current_user_payload

# Ana API yolunu (prefix) bir sabit olarak tanımlıyoruz.
API_PREFIX = "/api/tickets"

app = FastAPI(
    title="Ticket Service API",
    description="Helpdesk uygulaması için bilet (ticket) yönetim servisi.",
    version="1.4.0", # Versiyon güncellendi
)

# CORS Ayarları
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:8080", "https://helpdesk.cloudpro.com.tr"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],    
)

# --- TÜM ENDPOINT'LERDEKİ YOL (PATH) TANIMLAMALARI f-string KULLANILARAK DÜZELTİLDİ ---

@app.get(f"{API_PREFIX}/healthz", status_code=status.HTTP_200_OK, tags=["Health Check"])
def health_check():
    """Kubernetes probları için basit sağlık kontrolü."""
    return {"status": "healthy"}

@app.post(f"{API_PREFIX}/", response_model=models.Ticket, status_code=status.HTTP_201_CREATED, tags=["Tickets"])
async def create_ticket(
    ticket: models.TicketCreate,
    db: Session = Depends(get_db),
    current_user_payload: dict = Depends(get_current_user_payload),
    settings: Settings = Depends(get_settings),
):
    """Yeni bir destek bileti oluşturur."""
    user_sub_str = current_user_payload.get("sub")
    
    sync_payload = {
        "id": user_sub_str,
        "email": current_user_payload.get("email"),
        "full_name": current_user_payload.get("name", "Unknown User"),
        "roles": current_user_payload.get("realm_access", {}).get("roles", []),
        "keycloak_groups": current_user_payload.get("groups", [])
    }
    
    # user_service ile iletişim, config dosyasından alınan URL ile yapılacak.
    # Bu ayarın `ticket-service-chart/values.yaml` içinde tanımlı olması gerekir.
    sync_url = f"{settings.user_service_url}/api/users/internal/sync" # user-service'in yolu da güncellendi.
    headers = {"X-Internal-Secret": settings.internal_service_secret}
    
    try:
        async with httpx.AsyncClient(verify=False) as client:
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

    db_ticket = crud.create_ticket(db=db, ticket=ticket, creator_id=creator_id, tenant_id=tenant_id)
    return db_ticket

@app.get(f"{API_PREFIX}/", response_model=List[models.Ticket], tags=["Tickets"])
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

    if "agent" in user_roles or "helpdesk_admin" in user_roles or "general-admin" in user_roles:
        pass
    else:
        query = query.filter(crud.db_models.Ticket.creator_id == user_sub)

    db_tickets = query.order_by(crud.db_models.Ticket.created_at.desc()).offset(skip).limit(limit).all()
    return db_tickets

@app.get(f"{API_PREFIX}/{{ticket_id}}", response_model=models.TicketWithDetails, tags=["Tickets"])
async def read_ticket_details(
    ticket_id: uuid.UUID,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    current_user_payload: dict = Depends(get_current_user_payload)
):
    db_ticket = crud.get_ticket_with_details(db, ticket_id=ticket_id)
    if db_ticket is None:
        raise HTTPException(status_code=404, detail="Bilet bulunamadı")

    creator_info: Optional[models.UserInTicketResponse] = None
    user_id = db_ticket.creator_id
    internal_url = f"{settings.user_service_url}/api/users/internal/users/{user_id}"
    headers = {"X-Internal-Secret": settings.internal_service_secret}

    try:
        async with httpx.AsyncClient(verify=False) as client:
            response = await client.get(internal_url, headers=headers)
            if response.status_code == 200:
                user_data = response.json()
                creator_info = models.UserInTicketResponse(**user_data)
            else:
                creator_info = models.UserInTicketResponse(id=user_id, full_name="Bilinmeyen Kullanıcı", email="-")
    except httpx.RequestError:
        creator_info = models.UserInTicketResponse(id=user_id, full_name="Kullanıcı Servisine Ulaşılamadı", email="-")

    ticket_response = models.TicketWithDetails.from_orm(db_ticket)
    ticket_response.creator_details = creator_info
    return ticket_response

@app.patch(f"{API_PREFIX}/{{ticket_id}}", response_model=models.Ticket, tags=["Tickets"])
async def update_ticket(
    ticket_id: uuid.UUID,
    ticket_update: models.TicketUpdate,
    db: Session = Depends(get_db),
    current_user_payload: dict = Depends(get_current_user_payload),
    # settings: Settings = Depends(get_settings), # Bu parametre şu an kullanılmıyor, kaldırılabilir.
):
    """Bir biletin durumunu veya diğer alanlarını günceller."""
    user_roles = current_user_payload.get("realm_access", {}).get("roles", [])

    if "customer-user" in user_roles:
        raise HTTPException(status_code=403, detail="Biletleri sadece yetkili personel güncelleyebilir.")

    db_ticket = crud.get_ticket(db, ticket_id)
    if not db_ticket:
        raise HTTPException(status_code=404, detail="Güncellenecek bilet bulunamadı.")
    
    # ... (Yetki kontrol mantığı aynı kalabilir) ...

    return crud.update_ticket(db=db, ticket_id=ticket_id, ticket_update=ticket_update)

@app.delete(f"{API_PREFIX}/{{ticket_id}}", status_code=status.HTTP_204_NO_CONTENT, tags=["Tickets"])
async def delete_ticket(
    ticket_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user_payload: dict = Depends(get_current_user_payload),
    # settings: Settings = Depends(get_settings), # Bu parametre şu an kullanılmıyor, kaldırılabilir.
):
    """Bir bileti siler."""
    user_roles = current_user_payload.get("realm_access", {}).get("roles", [])

    if "agent" in user_roles or "customer-user" in user_roles:
        raise HTTPException(status_code=403, detail="Bilet silme yetkisi sadece adminlere aittir.")

    db_ticket = crud.get_ticket(db, ticket_id)
    if not db_ticket:
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    # ... (Yetki kontrol mantığı aynı kalabilir) ...

    crud.delete_ticket(db=db, ticket_id=ticket_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@app.post(f"{API_PREFIX}/{{ticket_id}}/comments", response_model=models.Comment, status_code=status.HTTP_201_CREATED, tags=["Comments"])
async def create_ticket_comment(
    ticket_id: uuid.UUID,
    comment: models.CommentCreate,
    db: Session = Depends(get_db),
    current_user_payload: dict = Depends(get_current_user_payload)
):
    """Belirli bir bilete yeni bir yorum ekler."""
    author_id = uuid.UUID(current_user_payload.get("sub"))
    
    db_ticket = crud.get_ticket(db, ticket_id=ticket_id)
    if not db_ticket:
        raise HTTPException(status_code=404, detail="Yorum yapılacak bilet bulunamadı.")
    
    new_comment = crud.create_comment(db=db, comment=comment, ticket_id=ticket_id, author_id=author_id)
    return new_comment

@app.post(f"{API_PREFIX}/{{ticket_id}}/attachments", response_model=List[models.Attachment], tags=["Attachments"])
async def upload_ticket_attachments(
    ticket_id: uuid.UUID,
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
    current_user_payload: dict = Depends(get_current_user_payload),
):
    """Belirli bir bilete bir veya daha fazla dosya ekler."""
    uploader_id = uuid.UUID(current_user_payload.get("sub"))
    
    db_ticket = crud.get_ticket(db, ticket_id=ticket_id)
    if not db_ticket:
        raise HTTPException(status_code=404, detail="Dosya eklenecek bilet bulunamadı.")
    
    UPLOAD_DIRECTORY = Path("uploads") / str(ticket_id)
    UPLOAD_DIRECTORY.mkdir(parents=True, exist_ok=True)
    
    saved_attachments = []
    for file in files:
        unique_suffix = uuid.uuid4().hex
        file_extension = Path(file.filename).suffix
        unique_filename = f"{unique_suffix}{file_extension}"
        file_location = UPLOAD_DIRECTORY / unique_filename

        try:
            with open(file_location, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
        finally:
            file.file.close()

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

@app.get(f"{API_PREFIX}/attachments/{{attachment_id}}", tags=["Attachments"])
async def download_attachment(
    attachment_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user_payload: dict = Depends(get_current_user_payload)
):
    """ID'si verilen bir dosyayı indirilebilir olarak sunar."""
    attachment = crud.get_attachment(db, attachment_id=attachment_id)
    if not attachment:
        raise HTTPException(status_code=404, detail="Dosya eki bulunamadı.")

    # ... (Yetki kontrol mantığı aynı kalabilir) ...

    file_path = attachment.file_path
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Dosya sunucuda bulunamadı.")

    return FileResponse(
        path=file_path, 
        media_type='application/octet-stream',
        filename=attachment.file_name
    )
