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
from .models import Role  # schemas.py içindeki Role enum'ını kullanıyoruz
from . import models as user_pydantic_models
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
    # DÜZELTME: Role enum'ı artık user_service/models.py içinden geliyor
    role = Column(SQLAlchemyEnum(user_pydantic_models.Role), nullable=False, default=user_pydantic_models.Role.EMPLOYEE)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    company_id = Column(SQLAlchemyUUID(as_uuid=True), ForeignKey('public.companies.id'), nullable=True)

    # Bu ilişki aynı veritabanı içinde olduğu için DOĞRU ve KALMALIDIR.
    company = relationship("Company", back_populates="users")
    
    # BU İLİŞKİLER ARTIK FARKLI VERİTABANLARINDA OLDUĞU İÇİN SİLİNMELİDİR:
    # tickets = relationship("Ticket", back_populates="creator")
    # comments = relationship("Comment", back_populates="author")
    # attachments = relationship("Attachment", back_populates="uploader")