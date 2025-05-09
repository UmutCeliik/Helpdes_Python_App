# ticket_service/crud.py
from sqlalchemy.orm import Session
from typing import List, Optional
import uuid
# Ortak DB modelini ve Ticket Pydantic modellerini import et
from database_pkg import db_models
from . import models # Kendi Pydantic modelleri

def create_ticket(db: Session, ticket: models.TicketCreate, creator_id: uuid.UUID) -> db_models.Ticket:
    db_ticket = db_models.Ticket(
        title=ticket.title,
        description=ticket.description,
        creator_id=creator_id
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