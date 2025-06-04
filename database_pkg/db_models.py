# database_pkg/db_models.py
from sqlalchemy import Column, String, Boolean, DateTime, Enum as SQLAlchemyEnum, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID as SQLAlchemyUUID
from sqlalchemy.sql import func
import uuid
# Ortak Base'i ve Role Enum'ını import et
from .database import Base
from .schemas import Role

class User(Base):
    __tablename__ = "users"
    __table_args__ = {'schema': 'users_schema'}
    # ... (User kolonları) ...
    id = Column(SQLAlchemyUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, index=True, nullable=False)
    full_name = Column(String, nullable=False)
    # role = Column(SQLAlchemyEnum(Role), nullable=False, default=Role.EMPLOYEE) # Role enum'ı schemas.py'den geliyordu
    # database_pkg.schemas'daki Role enum'ını kullanmaya devam ediyorsanız, bu satırda bir değişiklik yok.
    # Eğer Role enum'ını kaldırdıysanız veya farklı bir yerden alıyorsanız burayı gözden geçirin.
    # Şimdilik Role enum'ının hala geçerli olduğunu varsayıyorum.
    from .schemas import Role # Role enum'ını import ettiğinizden emin olun
    role = Column(SQLAlchemyEnum(Role), nullable=False, default=Role.EMPLOYEE)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Ticket(Base):
    __tablename__ = "tickets"
    __table_args__ = (
        Index('ix_tickets_schema_tickets_tenant_id', 'tenant_id'), 
        {'schema': 'tickets_schema'}
    )
    # ... (Ticket kolonları) ...
    id = Column(SQLAlchemyUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String, index=True, nullable=False)
    description = Column(String, nullable=False)
    status = Column(String, index=True, nullable=False, default='Açık')
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    creator_id = Column(SQLAlchemyUUID(as_uuid=True), ForeignKey(f"{User.__table_args__['schema']}.{User.__tablename__}.id"), nullable=False)
    tenant_id = Column(SQLAlchemyUUID(as_uuid=True), nullable=False, index=True)

class Company(Base):
    __tablename__ = "companies"
    # Diğer tablolarınız gibi şema kullanmak isteyebilirsiniz, örn: 'tenants_schema'
    # Şimdilik public şemada olacağını varsayalım veya istediğiniz bir şemayı belirtin.
    # Eğer yeni bir şema (örn: 'tenants_schema') kullanacaksanız, 
    # bu şemanın da veritabanında oluşturulması gerekir.
    __table_args__ = (
        Index('ix_companies_name', 'name'), # Şema belirtirseniz index tanımına da ekleyin
        Index('ix_companies_keycloak_group_id', 'keycloak_group_id'),
        {'schema': 'public'} # Veya 'tenants_schema' veya kullandığınız başka bir şema
    ) 

    id = Column(SQLAlchemyUUID(as_uuid=True), primary_key=True, default=uuid.uuid4, comment="Yerel veritabanındaki şirket (tenant) ID'si")
    name = Column(String(255), nullable=False, unique=True, index=True, comment="Şirketin (tenant) adı")
    keycloak_group_id = Column(SQLAlchemyUUID(as_uuid=True), nullable=False, unique=True, index=True, comment="Bu şirketi temsil eden Keycloak grubunun ID'si")
    status = Column(String(50), nullable=False, default="active", index=True, comment="Tenant durumu (örn: active, inactive, suspended)") # String(50) örnek bir uzunluktur

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<Company(id={self.id}, name='{self.name}', keycloak_group_id='{self.keycloak_group_id}')>"
# --- YENİ EKLENEN COMPANY (TENANT) MODELİ SONU ---
