# ticket_service/crud.py
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional
import uuid
# Ortak DB modelini ve Ticket Pydantic modellerini import et
from database_pkg import db_models
from . import models # Kendi Pydantic modelleri

def create_ticket(db: Session, ticket: models.TicketCreate, creator_id: uuid.UUID, tenant_id: uuid.UUID) -> db_models.Ticket: # tenant_id parametresi eklendi
    db_ticket = db_models.Ticket(
        title=ticket.title,
        description=ticket.description,
        creator_id=creator_id,
        tenant_id=tenant_id  # Yeni eklenen tenant_id alanı
    )
    db.add(db_ticket)
    db.commit()
    db.refresh(db_ticket)
    return db_ticket

def get_ticket(db: Session, ticket_id: uuid.UUID) -> db_models.Ticket | None:
    return db.query(db_models.Ticket).filter(db_models.Ticket.id == ticket_id).first()

def get_tickets(db: Session, skip: int = 0, limit: int = 100) -> List[db_models.Ticket]:
    return db.query(db_models.Ticket).offset(skip).limit(limit).all()

def update_ticket(db: Session, ticket_id: uuid.UUID, ticket_update: models.TicketUpdate) -> db_models.Ticket | None:
    db_ticket = get_ticket(db, ticket_id)
    if db_ticket is None:
        return None
    update_data = ticket_update.dict(exclude_unset=True)
    if not update_data:
        return db_ticket
    for key, value in update_data.items():
        setattr(db_ticket, key, value)
    db.add(db_ticket)
    db.commit()
    db.refresh(db_ticket)
    return db_ticket

def delete_ticket(db: Session, ticket_id: uuid.UUID) -> db_models.Ticket | None:
    db_ticket = get_ticket(db, ticket_id)
    if db_ticket is None:
        return None
    db.delete(db_ticket)
    db.commit()
    return db_ticket

def get_ticket_with_details(db: Session, ticket_id: uuid.UUID) -> Optional[db_models.Ticket]:
    """
    Verilen ID'ye sahip bir bileti, ilişkili olduğu yorumlar ve eklerle
    birlikte veritabanından çeker.
    """
    return (
        db.query(db_models.Ticket)
        .options(
            joinedload(db_models.Ticket.comments),
            joinedload(db_models.Ticket.attachments)
        )
        .filter(db_models.Ticket.id == ticket_id)
        .first()
    )

def get_company_by_keycloak_group_id(db: Session, keycloak_group_id: uuid.UUID) -> Optional[db_models.Company]:
    """
    Verilen Keycloak grup ID'sine sahip şirketi lokal veritabanından getirir.
    """
    # Not: db_models.Company'de keycloak_group_id UUID tipinde olmalı
    return db.query(db_models.Company).filter(db_models.Company.keycloak_group_id == keycloak_group_id).first()

def create_comment(db: Session, comment: models.CommentCreate, ticket_id: uuid.UUID, author_id: uuid.UUID) -> db_models.Comment:
    """
    Belirli bir bilete yeni bir yorum ekler.
    """
    db_comment = db_models.Comment(
        content=comment.content,
        ticket_id=ticket_id,
        author_id=author_id
    )
    db.add(db_comment)
    db.commit()
    db.refresh(db_comment)
    return db_comment

def create_attachment(db: Session, file_name: str, file_path: str, file_type: str, ticket_id: uuid.UUID, uploader_id: uuid.UUID) -> db_models.Attachment:
    """
    Bir bilet için yeni bir dosya eki kaydı oluşturur.
    """
    db_attachment = db_models.Attachment(
        file_name=file_name,
        file_path=file_path,
        file_type=file_type,
        ticket_id=ticket_id,
        uploader_id=uploader_id
    )
    db.add(db_attachment)
    db.commit()
    db.refresh(db_attachment)
    return db_attachment

def get_attachment(db: Session, attachment_id: uuid.UUID) -> Optional[db_models.Attachment]:
    """
    Verilen ID'ye sahip tek bir attachment kaydını getirir.
    """
    return db.query(db_models.Attachment).filter(db_models.Attachment.id == attachment_id).first()