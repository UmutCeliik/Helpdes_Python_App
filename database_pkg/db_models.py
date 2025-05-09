# database_pkg/db_models.py
from sqlalchemy import Column, String, Boolean, DateTime, Enum as SQLAlchemyEnum, ForeignKey
from sqlalchemy.dialects.postgresql import UUID as SQLAlchemyUUID
from sqlalchemy.sql import func
import uuid
# Ortak Base'i ve Role Enum'ını import et
from .database import Base
from .schemas import Role

class User(Base):
    """Veritabanındaki 'users' tablosu."""
    __tablename__ = "users"
    __table_args__ = {'schema': 'users_schema'}

    id = Column(SQLAlchemyUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, index=True, nullable=False)
    full_name = Column(String, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(SQLAlchemyEnum(Role), nullable=False, default=Role.EMPLOYEE)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Ticket(Base):
    """Veritabanındaki 'tickets' tablosu."""
    __tablename__ = "tickets"
    __table_args__ = {'schema': 'tickets_schema'}

    id = Column(SQLAlchemyUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String, index=True, nullable=False)
    description = Column(String, nullable=False)
    status = Column(String, index=True, nullable=False, default='Açık')
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    # Foreign Key tanımı artık User modelini aynı Base üzerinden tanıyor
    creator_id = Column(SQLAlchemyUUID(as_uuid=True), ForeignKey(f"{User.__table_args__['schema']}.{User.__tablename__}.id"), nullable=False)