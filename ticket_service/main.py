# ticket_service/main.py
import uuid
import os
import shutil
from pathlib import Path
from typing import Annotated, Dict, Any, List, Optional

import httpx
from fastapi import Depends, FastAPI, HTTPException, status, UploadFile, File, Response, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

# Yerel modüller
from . import crud, models
from .config import Settings, get_settings
from .database import get_db
from .auth import get_current_user_payload
from .logging_config import setup_logging, LoggingMiddleware

# Loglamayı başlat
SERVICE_NAME = "ticket_service"
SERVICE_NAME22= "ticket_servicee"
logger = setup_logging(SERVICE_NAME)

API_PREFIX = "/api/tickets"

app = FastAPI(
    title="Ticket Service API",
    description="Helpdesk uygulaması için bilet (ticket) yönetim servisi.",
    version="1.5.0",
)

# Middleware'leri ekle
app.add_middleware(LoggingMiddleware, logger=logger)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:8080", "https://helpdesk.cloudpro.com.tr"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get(f"{API_PREFIX}/healthz", status_code=status.HTTP_200_OK, tags=["Health Check"])
def health_check():
    """Servisin sağlık durumunu kontrol eder."""
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
    logger.info(f"Creating ticket for user_id: {user_sub_str}")
    
    sync_payload = {
        "id": user_sub_str,
        "email": current_user_payload.get("email"),
        "full_name": current_user_payload.get("name", "Unknown User"),
        "roles": current_user_payload.get("realm_access", {}).get("roles", []),
        "keycloak_groups": current_user_payload.get("groups", [])
    }
    
    sync_url = f"{settings.user_service_url}/api/users/internal/users/sync"
    headers = {"X-Internal-Secret": settings.internal_service_secret}
    
    try:
        async with httpx.AsyncClient(verify=False) as client:
            logger.info(f"Syncing user {user_sub_str} with user_service at {sync_url}")
            response = await client.post(sync_url, json=sync_payload, headers=headers)
            response.raise_for_status()
            synced_user_data = response.json()
            
            creator_id = uuid.UUID(synced_user_data.get("id"))
            company_info = synced_user_data.get("company")
            
            if not company_info or not company_info.get("id"):
                logger.error(f"User {user_sub_str} is not assigned to a tenant. Cannot create ticket.")
                raise HTTPException(status_code=400, detail="Bilet oluşturmak için kullanıcının bir tenant'a atanmış olması gerekir.")
            
            tenant_id = uuid.UUID(company_info.get("id"))
            logger.info(f"User {user_sub_str} belongs to tenant {tenant_id}. Proceeding to create ticket.")

    except httpx.RequestError as exc:
        logger.error(f"Could not reach user_service for user sync: {exc}", extra={"target_url": sync_url})
        raise HTTPException(status_code=503, detail=f"user_service'e ulaşılamıyor: {exc}")
    except httpx.HTTPStatusError as exc:
        logger.error(f"Error during user_service sync: {exc.response.status_code} - {exc.response.text}", extra={"target_url": sync_url})
        raise HTTPException(status_code=exc.response.status_code, detail=f"user_service senkronizasyon hatası: {exc.response.text}")

    db_ticket = crud.create_ticket(db=db, ticket=ticket, creator_id=creator_id, tenant_id=tenant_id)
    logger.info(f"Ticket {db_ticket.id} created successfully for user {user_sub_str}.")
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
    logger.info(f"Fetching tickets for user {user_sub} with roles {user_roles}")

    query = db.query(crud.db_models.Ticket)

    if "agent" in user_roles or "helpdesk_admin" in user_roles or "general-admin" in user_roles:
        logger.info(f"User {user_sub} is staff, fetching all tickets.")
    else:
        logger.info(f"User {user_sub} is a customer, fetching only their tickets.")
        query = query.filter(crud.db_models.Ticket.creator_id == user_sub)

    db_tickets = query.order_by(crud.db_models.Ticket.created_at.desc()).offset(skip).limit(limit).all()
    logger.info(f"Found {len(db_tickets)} tickets for user {user_sub}.")
    return db_tickets

@app.get(f"{API_PREFIX}/{{ticket_id}}", response_model=models.TicketWithDetails, tags=["Tickets"])
async def read_ticket_details(
    ticket_id: uuid.UUID,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    current_user_payload: dict = Depends(get_current_user_payload)
):
    """Belirli bir biletin yorumlar ve ekler dahil tüm detaylarını getirir."""
    logger.info(f"Fetching details for ticket_id: {ticket_id}")
    db_ticket = crud.get_ticket_with_details(db, ticket_id=ticket_id)
    if db_ticket is None:
        logger.warning(f"Ticket with id {ticket_id} not found.")
        raise HTTPException(status_code=404, detail="Bilet bulunamadı")

    creator_info: Optional[models.UserInTicketResponse] = None
    user_id = db_ticket.creator_id
    internal_url = f"{settings.user_service_url}/api/users/internal/users/{user_id}"
    headers = {"X-Internal-Secret": settings.internal_service_secret}

    try:
        async with httpx.AsyncClient(verify=False) as client:
            logger.info(f"Fetching creator details for ticket {ticket_id} from user_service.")
            response = await client.get(internal_url, headers=headers)
            if response.status_code == 200:
                user_data = response.json()
                creator_info = models.UserInTicketResponse(**user_data)
                logger.info(f"Successfully fetched creator details for user {user_id}.")
            else:
                logger.warning(f"Could not fetch creator details for user {user_id}. Status: {response.status_code}")
                creator_info = models.UserInTicketResponse(id=user_id, full_name="Bilinmeyen Kullanıcı", email="-")
    except httpx.RequestError as e:
        logger.error(f"Request to user_service failed while fetching creator details for user {user_id}: {e}")
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
):
    """Bir biletin durumunu veya diğer alanlarını günceller."""
    user_id = current_user_payload.get('sub')
    user_roles = current_user_payload.get("realm_access", {}).get("roles", [])
    logger.info(f"User {user_id} attempting to update ticket {ticket_id} with data: {ticket_update.model_dump(exclude_unset=True)}")

    if "customer-user" in user_roles and not ("agent" in user_roles or "helpdesk-admin" in user_roles or "general-admin" in user_roles):
        logger.warning(f"User {user_id} with role 'customer-user' attempted to update ticket {ticket_id}. Forbidden.")
        raise HTTPException(status_code=403, detail="Biletleri sadece yetkili personel güncelleyebilir.")
        
    db_ticket = crud.get_ticket(db, ticket_id)
    if not db_ticket:
        logger.warning(f"Update failed: Ticket with id {ticket_id} not found.")
        raise HTTPException(status_code=404, detail="Güncellenecek bilet bulunamadı.")
        
    updated_ticket = crud.update_ticket(db=db, ticket_id=ticket_id, ticket_update=ticket_update)
    logger.info(f"Ticket {ticket_id} updated successfully by user {user_id}.")
    return updated_ticket

@app.delete(f"{API_PREFIX}/{{ticket_id}}", status_code=status.HTTP_204_NO_CONTENT, tags=["Tickets"])
async def delete_ticket(
    ticket_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user_payload: dict = Depends(get_current_user_payload),
):
    """Bir bileti siler (Sadece adminler)."""
    user_id = current_user_payload.get('sub')
    user_roles = current_user_payload.get("realm_access", {}).get("roles", [])
    logger.info(f"User {user_id} attempting to delete ticket {ticket_id}")

    if "helpdesk-admin" not in user_roles and "general-admin" not in user_roles:
        logger.warning(f"User {user_id} with roles {user_roles} attempted to delete ticket {ticket_id}. Forbidden.")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bilet silme yetkisi sadece adminlere aittir.")
        
    db_ticket = crud.get_ticket(db, ticket_id)
    if not db_ticket:
        logger.info(f"Ticket {ticket_id} not found for deletion. Returning 204 as it is already gone.")
        return Response(status_code=status.HTTP_204_NO_CONTENT)
        
    crud.delete_ticket(db=db, ticket_id=ticket_id)
    logger.info(f"Ticket {ticket_id} deleted successfully by user {user_id}.")
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
    logger.info(f"User {author_id} adding comment to ticket {ticket_id}")
    
    db_ticket = crud.get_ticket(db, ticket_id=ticket_id)
    if not db_ticket:
        logger.warning(f"Comment creation failed: Ticket {ticket_id} not found.")
        raise HTTPException(status_code=404, detail="Yorum yapılacak bilet bulunamadı.")
        
    new_comment = crud.create_comment(db=db, comment=comment, ticket_id=ticket_id, author_id=author_id)
    logger.info(f"Comment {new_comment.id} added to ticket {ticket_id} by user {author_id}.")
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
    logger.info(f"User {uploader_id} attempting to upload {len(files)} file(s) to ticket {ticket_id}")
    
    db_ticket = crud.get_ticket(db, ticket_id=ticket_id)
    if not db_ticket:
        logger.warning(f"Attachment upload failed: Ticket {ticket_id} not found.")
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
            logger.info(f"File '{file.filename}' saved to '{file_location}' for ticket {ticket_id}")
        except Exception:
            logger.exception(f"Failed to save uploaded file '{file.filename}' to disk.")
            raise HTTPException(status_code=500, detail="Dosya sunucuya kaydedilirken bir hata oluştu.")
        finally:
            file.file.close()

        db_attachment = crud.create_attachment(
            db=db, file_name=file.filename, file_path=str(file_location),
            file_type=file.content_type, ticket_id=ticket_id, uploader_id=uploader_id
        )
        saved_attachments.append(db_attachment)

    logger.info(f"Successfully saved {len(saved_attachments)} attachments for ticket {ticket_id}.")
    return saved_attachments

@app.get(f"{API_PREFIX}/attachments/{{attachment_id}}", tags=["Attachments"])
async def download_attachment(
    attachment_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user_payload: dict = Depends(get_current_user_payload)
):
    """ID'si verilen bir dosyayı indirilebilir olarak sunar."""
    user_id = current_user_payload.get('sub')
    logger.info(f"User {user_id} requesting download for attachment {attachment_id}")
    
    attachment = crud.get_attachment(db, attachment_id=attachment_id)
    if not attachment:
        logger.warning(f"Download request for non-existent attachment {attachment_id} by user {user_id}.")
        raise HTTPException(status_code=404, detail="Dosya eki bulunamadı.")

    # TODO: Yetki kontrolü eklenebilir. Örneğin, sadece bileti oluşturan veya yetkili agent'lar indirebilir.
    # Bu, projenin ilerleyen aşamaları için bir nottur.

    file_path = attachment.file_path
    if not os.path.exists(file_path):
        logger.error(f"Attachment record exists for {attachment_id}, but file not found on disk at path: {file_path}")
        raise HTTPException(status_code=404, detail="Dosya sunucuda bulunamadı.")

    logger.info(f"Serving file {file_path} for attachment {attachment_id} to user {user_id}.")
    return FileResponse(
        path=file_path, 
        media_type='application/octet-stream',
        filename=attachment.file_name
    )
