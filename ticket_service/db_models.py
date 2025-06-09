# database_pkg/db_models.py
import uuid
from sqlalchemy import (
    Column,
    String,
    Boolean,
    DateTime,
    Enum as SQLAlchemyEnum,
    ForeignKey,
    Index,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID as SQLAlchemyUUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .database import Base

class Ticket(Base):
    __tablename__ = "tickets"
    __table_args__ = (
        Index('ix_tickets_tenant_id', 'tenant_id'),
        {'schema': 'tickets_schema'}
    )
    
    id = Column(SQLAlchemyUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String, index=True, nullable=False)
    description = Column(String, nullable=False)
    status = Column(String, index=True, nullable=False, default='Açık')
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # DÜZELTME: ForeignKey('users_schema.users.id') kaldırıldı.
    creator_id = Column(SQLAlchemyUUID(as_uuid=True), nullable=False)
    
    tenant_id = Column(SQLAlchemyUUID(as_uuid=True), nullable=False, index=True)

    comments = relationship("Comment", back_populates="ticket", cascade="all, delete-orphan")
    attachments = relationship("Attachment", back_populates="ticket", cascade="all, delete-orphan")


class Comment(Base):
    __tablename__ = "comments"
    __table_args__ = {'schema': 'tickets_schema'}

    id = Column(SQLAlchemyUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    ticket_id = Column(SQLAlchemyUUID(as_uuid=True), ForeignKey('tickets_schema.tickets.id'), nullable=False)
    
    # DÜZELTME: ForeignKey('users_schema.users.id') kaldırıldı.
    author_id = Column(SQLAlchemyUUID(as_uuid=True), nullable=False)
    
    ticket = relationship("Ticket", back_populates="comments")

class Attachment(Base):
    __tablename__ = "attachments"
    __table_args__ = {'schema': 'tickets_schema'}
    
    id = Column(SQLAlchemyUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    file_name = Column(String(255), nullable=False)
    file_path = Column(String(1024), nullable=False, unique=True)
    file_type = Column(String(100), nullable=True)
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())
    
    ticket_id = Column(SQLAlchemyUUID(as_uuid=True), ForeignKey('tickets_schema.tickets.id'), nullable=False)
    
    # DÜZELTME: ForeignKey('users_schema.users.id') kaldırıldı.
    uploader_id = Column(SQLAlchemyUUID(as_uuid=True), nullable=False)

    ticket = relationship("Ticket", back_populates="attachments")
