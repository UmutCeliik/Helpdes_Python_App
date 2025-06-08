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
from .schemas import Role  # schemas.py içindeki Role enum'ını kullanıyoruz

class Company(Base):
    __tablename__ = "companies"
    __table_args__ = (
        Index('ix_companies_name', 'name'),
        Index('ix_companies_keycloak_group_id', 'keycloak_group_id'),
        {'schema': 'public'}
    )
    id = Column(SQLAlchemyUUID(as_uuid=True), primary_key=True, default=uuid.uuid4, comment="Yerel veritabanındaki şirket (tenant) ID'si")
    name = Column(String(255), nullable=False, unique=True, index=True, comment="Şirketin (tenant) adı")
    keycloak_group_id = Column(SQLAlchemyUUID(as_uuid=True), nullable=False, unique=True, index=True, comment="Bu şirketi temsil eden Keycloak grubunun ID'si")
    status = Column(String(50), nullable=False, default="active", index=True, comment="Tenant durumu (örn: active, inactive, suspended)")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    users = relationship("User", back_populates="company")

class User(Base):
    __tablename__ = "users"
    __table_args__ = {'schema': 'users_schema'}
    id = Column(SQLAlchemyUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, index=True, nullable=False)
    full_name = Column(String, nullable=False)
    role = Column(SQLAlchemyEnum(Role), nullable=False, default=Role.EMPLOYEE)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # DÜZELTME: ForeignKey'i doğrudan 'schema.table.column' formatında belirtiyoruz.
    company_id = Column(SQLAlchemyUUID(as_uuid=True), ForeignKey('public.companies.id'), nullable=True)
    company = relationship("Company", back_populates="users")
    
    tickets = relationship("Ticket", back_populates="creator")
    comments = relationship("Comment", back_populates="author")
    attachments = relationship("Attachment", back_populates="uploader")

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
    
    # DÜZELTME: ForeignKey'leri doğrudan 'schema.table.column' formatında belirtiyoruz.
    creator_id = Column(SQLAlchemyUUID(as_uuid=True), ForeignKey('users_schema.users.id'), nullable=False)
    tenant_id = Column(SQLAlchemyUUID(as_uuid=True), ForeignKey('public.companies.id'), nullable=False, index=True)

    creator = relationship("User", back_populates="tickets")
    comments = relationship("Comment", back_populates="ticket", cascade="all, delete-orphan")
    attachments = relationship("Attachment", back_populates="ticket", cascade="all, delete-orphan")

# --- YENİ EKLENDİ: Comment modeli ---
class Comment(Base):
    __tablename__ = "comments"
    __table_args__ = {'schema': 'tickets_schema'}
    id = Column(SQLAlchemyUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # DÜZELTME: ForeignKey'leri doğrudan 'schema.table.column' formatında belirtiyoruz.
    ticket_id = Column(SQLAlchemyUUID(as_uuid=True), ForeignKey('tickets_schema.tickets.id'), nullable=False)
    author_id = Column(SQLAlchemyUUID(as_uuid=True), ForeignKey('users_schema.users.id'), nullable=False)
    
    ticket = relationship("Ticket", back_populates="comments")
    author = relationship("User", back_populates="comments")

# --- YENİ EKLENDİ: Attachment modeli ---
class Attachment(Base):
    __tablename__ = "attachments"
    __table_args__ = {'schema': 'tickets_schema'}
    id = Column(SQLAlchemyUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    file_name = Column(String(255), nullable=False)
    file_path = Column(String(1024), nullable=False, unique=True)
    file_type = Column(String(100), nullable=True)
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # DÜZELTME: ForeignKey'leri doğrudan 'schema.table.column' formatında belirtiyoruz.
    ticket_id = Column(SQLAlchemyUUID(as_uuid=True), ForeignKey('tickets_schema.tickets.id'), nullable=False)
    uploader_id = Column(SQLAlchemyUUID(as_uuid=True), ForeignKey('users_schema.users.id'), nullable=False)
    
    ticket = relationship("Ticket", back_populates="attachments")
    uploader = relationship("User", back_populates="attachments")