# user_service/models.py
from __future__ import annotations
from enum import Enum  # Role için Enum importu gerekli
from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List
import uuid
from datetime import datetime

class Role(str, Enum):
    """Veritabanı ve Pydantic modellerinde kullanılacak roller."""
    AGENT = "agent"
    EMPLOYEE = "employee"
    # Proje raporlarında geçen diğer rolleri de buraya ekleyebiliriz:
    GENERAL_ADMIN = "general-admin"
    HELPDESK_ADMIN = "helpdesk-admin"
    CUSTOMER_USER = "customer-user"

class CompanyBasicInfo(BaseModel):
    """API yanıtlarında temel şirket bilgisi için kullanılacak model."""
    id: uuid.UUID
    name: str

    class Config:
        from_attributes = True

class UserBase(BaseModel):
    email: EmailStr = Field(..., description="Kullanıcının e-posta adresi (benzersiz olmalı)")
    full_name: str = Field(..., min_length=2, max_length=100, description="Kullanıcının tam adı")

class UserCreateInternal(UserBase): # Adını değiştirdim, bu artık dışarıdan çağrılmayacak
    id: uuid.UUID # Keycloak User ID (sub claim)
    # Keycloak'tan gelen rolleri bir string listesi olarak alabiliriz
    roles: Optional[List[str]] = Field(default_factory=list, description="Kullanıcının Keycloak'tan gelen rolleri")
    is_active: bool = Field(default=True, description="Kullanıcının Keycloak'taki durumu (enabled)")
    keycloak_groups: Optional[List[str]] = Field(default_factory=list, description="Kullanıcının Keycloak'tan gelen grup yolları")

class AdminUserUpdateRequest(BaseModel):
    full_name: Optional[str] = Field(None, min_length=2, max_length=100, description="Kullanıcının yeni tam adı")
    is_active: Optional[bool] = Field(None, description="Kullanıcının Keycloak'taki 'enabled' durumu")
    
    # Gönderilen liste, kullanıcının Keycloak'taki TÜM realm rollerini temsil eder.
    # Eğer boş liste gönderilirse, tüm realm rolleri kaldırılır.
    # Eğer None (gönderilmezse), roller değiştirilmez.
    roles: Optional[List[str]] = Field(None, description="Kullanıcıya atanacak YENİ Keycloak realm rollerinin tam listesi. Boş liste tüm rolleri kaldırır.")
    
    # Eğer null (None değil, JSON'da null) gönderilirse kullanıcı tüm gruplardan çıkarılır (tenant'sız yapılır).
    # Eğer bir UUID gönderilirse, kullanıcı mevcut gruplarından çıkarılıp bu yeni tenant'a (gruba) atanır.
    # Eğer bu alan request'te hiç gönderilmezse (None), tenant/grup ataması değiştirilmez.
    tenant_id: Optional[uuid.UUID | None] = Field(None, description="Kullanıcının atanacağı YENİ şirketin (tenant) lokal DB ID'si. JSON'da 'null' göndermek kullanıcıyı tüm tenant gruplarından çıkarır.")

    class Config:
        json_schema_extra = {
            "example": {
                "full_name": "Güncel Kullanıcı Adı",
                "is_active": True,
                "roles": ["agent"],
                "tenant_id": "yeni-şirket-uuid-buraya-gelecek" 
                # tenant_id için 'null' göndermek, kullanıcıyı mevcut tenantından çıkarmak anlamına gelir.
            }
        }

class User(UserBase):
    id: uuid.UUID
    roles: Optional[List[str]] = Field(default_factory=list)
    is_active: bool
    created_at: datetime
    company: Optional[CompanyBasicInfo] = None # YENİ ALAN: Kullanıcının atandığı şirket

    class Config:
        from_attributes = True # SQLAlchemy modelinden Pydantic modeline dönüşüm için

class TenantCreateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=255, description="Oluşturulacak yeni tenant'ın (şirketin) adı")

class AdminUserCreateRequest(BaseModel):
    email: EmailStr = Field(..., description="Oluşturulacak kullanıcının e-posta adresi (Keycloak'ta kullanıcı adı olarak da kullanılacak)")
    full_name: str = Field(..., min_length=2, max_length=100, description="Kullanıcının tam adı")
    password: str = Field(..., min_length=8, description="Kullanıcının başlangıç şifresi")
    roles: List[str] = Field(default_factory=list, description="Kullanıcıya atanacak Keycloak realm rollerinin listesi (örn: ['agent', 'customer-user'])")
    is_active: bool = Field(default=True, description="Kullanıcının Keycloak'ta 'enabled' durumu")
    
    # Kullanıcının hangi tenant'a (şirkete) atanacağını belirtmek için.
    # Frontend'den tenant'ın lokal DB'deki UUID'si gönderilebilir.
    # Bu ID ile company_crud'dan Company.keycloak_group_id alınır.
    tenant_id: Optional[uuid.UUID] = Field(None, description="Kullanıcının atanacağı şirketin (tenant) lokal veritabanındaki ID'si. Boş bırakılırsa hiçbir gruba atanmaz (örn: general-admin).")

    # Alternatif olarak, Keycloak grup path'i de alınabilirdi:
    # keycloak_group_path: Optional[str] = Field(None, description="Kullanıcının atanacağı Keycloak grubunun tam yolu (örn: /Musteri_Alpha_AS)")

    class Config:
        json_schema_extra = {
            "example": {
                "email": "yeni.kullanici@ornek.com",
                "full_name": "Yeni Kullanıcı Adı",
                "password": "GucluBirSifre123!",
                "roles": ["employee"], # Veya Keycloak'taki gerçek rol adları: ["customer-user"]
                "is_active": True,
                "tenant_id": "şirket-uuid-buraya-gelecek" # Opsiyonel
            }
        }

class CompanyBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=255, description="Şirket (tenant) adı")
    status: Optional[str] = Field("active", max_length=50, description="Tenant durumu (örn: active, inactive)")

class CompanyCreate(CompanyBase):
    keycloak_group_id: uuid.UUID = Field(..., description="Bu şirketi temsil eden Keycloak grubunun ID'si")

class CompanyUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=255)
    status: Optional[str] = Field(None, max_length=50)

class CompanyInDBBase(CompanyBase):
    id: uuid.UUID
    keycloak_group_id: uuid.UUID
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class Company(CompanyInDBBase):
    pass

class CompanyList(BaseModel):
    items: List[Company]
    total: int