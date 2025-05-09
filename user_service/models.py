# user_service/models.py
from pydantic import BaseModel, Field, EmailStr
from typing import Optional
import uuid
from datetime import datetime
# Ortak Role enum'ını import et
from database_pkg.schemas import Role

class UserBase(BaseModel):
    email: EmailStr = Field(..., description="Kullanıcının e-posta adresi (benzersiz olmalı)")
    full_name: str = Field(..., min_length=2, max_length=100, description="Kullanıcının tam adı")

class UserCreate(UserBase):
    password: str = Field(..., min_length=8, description="Kullanıcının şifresi (hashlenecek)")
    role: Role = Field(Role.EMPLOYEE, description="Kullanıcının rolü (varsayılan: employee)")

class User(UserBase):
    id: uuid.UUID
    role: Role
    is_active: bool = Field(True)
    created_at: datetime

    class Config:
        from_attributes = True

# Auth Service'in ihtiyaç duyduğu dahili model (hashlenmiş şifre dahil)
class UserInternal(User):
    hashed_password: str
    class Config:
        from_attributes = True