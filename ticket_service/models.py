# ticket_service/models.py
from pydantic import BaseModel, Field
from typing import Optional
import uuid
from datetime import datetime
# Ortak Role enum'ını import et
from database_pkg.schemas import Role

class TicketBase(BaseModel):
    title: str = Field(..., min_length=3, max_length=100)
    description: str = Field(..., min_length=10)

class TicketCreate(TicketBase):
    pass

class Ticket(TicketBase):
    id: uuid.UUID
    status: str = Field("Açık")
    created_at: datetime
    creator_id: uuid.UUID

    class Config:
        from_attributes = True

class TicketUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=3, max_length=100)
    description: Optional[str] = Field(None, min_length=10)
    status: Optional[str] = Field(None)

    class Config:
        from_attributes = True