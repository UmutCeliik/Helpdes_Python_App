# database_pkg/schemas.py
from enum import Enum
from pydantic import BaseModel, Field
from typing import Optional, List # List eklendiğinden emin olun
import uuid
from datetime import datetime

# Mevcut Role enum'ınız:
class Role(str, Enum):
    AGENT = "agent"
    EMPLOYEE = "employee"
    # Belki burada 'customer-user', 'general-admin', 'helpdesk_admin' gibi
    # Keycloak'ta tanımladığınız diğer rolleri de eklemek isteyebilirsiniz.
    # Şimdilik mevcut haliyle bırakıyorum.

class CompanyBasicInfo(BaseModel):
    id: uuid.UUID
    name: str

    class Config:
        from_attributes = True
# --- YENİ EKLENEN COMPANY (TENANT) PYDANTIC MODELLERİ ---

class CompanyBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=255, description="Şirket (tenant) adı")
    # status alanı oluşturmada isteğe bağlı olabilir ve varsayılanı 'active' olabilir.
    # Ya da oluştururken belirtilmesi zorunlu kılınabilir.
    status: Optional[str] = Field("active", max_length=50, description="Tenant durumu (örn: active, inactive)")

class CompanyCreate(CompanyBase):
    # Yeni bir şirket oluşturulurken Keycloak grup ID'sinin de verilmesi gerekecek.
    # Bu ID, Keycloak'ta grup oluşturulduktan sonra alınır.
    keycloak_group_id: uuid.UUID = Field(..., description="Bu şirketi temsil eden Keycloak grubunun ID'si")

class CompanyUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=255)
    status: Optional[str] = Field(None, max_length=50)

class CompanyInDBBase(CompanyBase):
    id: uuid.UUID
    keycloak_group_id: uuid.UUID
    status: str # DB'den okurken status her zaman dolu olacak
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True # SQLAlchemy modelinden Pydantic modeline dönüşüm için

# API yanıtlarında kullanılacak tam Company modeli
class Company(CompanyInDBBase):
    pass

# Birden fazla şirket listelemek için
class CompanyList(BaseModel):
    items: List[Company]
    total: int

# --- YENİ EKLENEN COMPANY (TENANT) PYDANTIC MODELLERİ SONU ---