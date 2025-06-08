# ticket_service/models.py
from pydantic import BaseModel, Field
from typing import Optional, List # List'i import ettiğinizden emin olun
import uuid
from datetime import datetime
from database_pkg.schemas import Role

# --- YENİ: Yorumlar için Pydantic modeli ---
class Comment(BaseModel):
    id: uuid.UUID
    content: str
    created_at: datetime
    author_id: uuid.UUID
    # İsteğe bağlı olarak yazarın adını da ekleyebiliriz, şimdilik ID yeterli.

    class Config:
        from_attributes = True

# --- YENİ: Dosya ekleri için Pydantic modeli ---
class Attachment(BaseModel):
    id: uuid.UUID
    file_name: str
    file_type: Optional[str] = None
    uploaded_at: datetime
    uploader_id: uuid.UUID

    class Config:
        from_attributes = True

class TicketBase(BaseModel):
    title: str = Field(..., min_length=3, max_length=100)
    description: str = Field(..., min_length=10)

class TicketCreate(TicketBase):
    tenant_id_override: Optional[uuid.UUID] = Field(None, description="Eğer agent/admin belirli bir tenant için bilet oluşturuyorsa, o tenantın ID'si")

class Ticket(TicketBase):
    id: uuid.UUID
    status: str = Field("Açık")
    created_at: datetime
    creator_id: uuid.UUID
    tenant_id: uuid.UUID

    class Config:
        from_attributes = True

# --- YENİ: Tüm detayları içeren Pydantic modeli ---
class TicketWithDetails(Ticket):
    comments: List[Comment] = []
    attachments: List[Attachment] = []
    # İsteğe bağlı olarak oluşturan kullanıcının detaylarını da ekleyebiliriz.

class TicketUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=3, max_length=100)
    description: Optional[str] = Field(None, min_length=10)
    status: Optional[str] = Field(None)

    class Config:
        from_attributes = True

# --- YENİ EKLENDİ: Yorum oluşturma için Pydantic modeli ---
class CommentCreate(BaseModel):
    content: str = Field(..., min_length=1, description="Yorumun içeriği")