# user_service/models.py
from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List
import uuid
from datetime import datetime
# Ortak Role enum'ını import et
from database_pkg.schemas import Role

class UserBase(BaseModel):
    email: EmailStr = Field(..., description="Kullanıcının e-posta adresi (benzersiz olmalı)")
    full_name: str = Field(..., min_length=2, max_length=100, description="Kullanıcının tam adı")

class UserCreateInternal(UserBase): # Adını değiştirdim, bu artık dışarıdan çağrılmayacak
    id: uuid.UUID # Keycloak User ID (sub claim)
    # Keycloak'tan gelen rolleri bir string listesi olarak alabiliriz
    roles: Optional[List[str]] = Field(default_factory=list, description="Kullanıcının Keycloak'tan gelen rolleri")
    is_active: bool = Field(default=True, description="Kullanıcının Keycloak'taki durumu (enabled)")
    # Şifre artık burada yok

class User(UserBase):
    id: uuid.UUID
    # Lokal DB'deki 'role' enum'ını mı kullanacağız, yoksa Keycloak'tan gelen string listesini mi?
    # Şimdilik Keycloak'tan gelen string listesini yansıtalım.
    # Veya lokal DB'deki role'ü de ayrıca gösterebiliriz (eğer senkronize ediyorsak).
    # Bu kısım multi-tenancy'de daha da netleşecek.
    # Şimdilik basit tutalım:
    roles: Optional[List[str]] = Field(default_factory=list) # JIT ile Keycloak'tan gelen roller eklenebilir
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True # SQLAlchemy modelinden Pydantic modeline dönüşüm için
