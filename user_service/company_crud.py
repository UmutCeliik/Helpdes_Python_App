# user_service/company_crud.py
from sqlalchemy.orm import Session
from typing import List, Optional
import uuid

# Kendi servisimize ait modelleri import ediyoruz
from . import db_models  # SQLAlchemy modelleri (Company, User)
from . import models as schemas # Pydantic modelleri (CompanyCreate, vb.) artık kendi models.py dosyamızda

def create_company(db: Session, company: schemas.CompanyCreate) -> db_models.Company:
    """
    Veritabanında yeni bir şirket (tenant) kaydı oluşturur.
    """
    db_company = db_models.Company(
        name=company.name,
        keycloak_group_id=company.keycloak_group_id,
        status=company.status if company.status else "active" # Pydantic modelinde default var ama burada da kontrol
    )
    db.add(db_company)
    db.commit()
    db.refresh(db_company)
    print(f"CRUD: Company created: {db_company.name} (ID: {db_company.id}, Keycloak Group ID: {db_company.keycloak_group_id})")
    return db_company

def get_company(db: Session, company_id: uuid.UUID) -> Optional[db_models.Company]:
    """
    Verilen ID'ye sahip şirketi veritabanından getirir.
    """
    return db.query(db_models.Company).filter(db_models.Company.id == company_id).first()

def get_company_by_name(db: Session, name: str) -> Optional[db_models.Company]:
    """
    Verilen isme sahip şirketi veritabanından getirir.
    """
    return db.query(db_models.Company).filter(db_models.Company.name == name).first()

def get_company_by_keycloak_group_id(db: Session, keycloak_group_id: uuid.UUID) -> Optional[db_models.Company]:
    """
    Verilen Keycloak grup ID'sine sahip şirketi veritabanından getirir.
    """
    return db.query(db_models.Company).filter(db_models.Company.keycloak_group_id == keycloak_group_id).first()

def get_companies(db: Session, skip: int = 0, limit: int = 100) -> List[db_models.Company]:
    """
    Veritabanındaki şirketleri sayfalama yaparak listeler.
    """
    return db.query(db_models.Company).offset(skip).limit(limit).all()

def count_companies(db: Session) -> int:
    """
    Veritabanındaki toplam şirket (tenant) sayısını döndürür.
    """
    return db.query(db_models.Company).count()

def update_company(db: Session, company_db: db_models.Company, company_in: schemas.CompanyUpdate) -> db_models.Company:
    """
    Mevcut bir şirketin bilgilerini günceller.
    company_db: Güncellenecek SQLAlchemy Company nesnesi.
    company_in: Pydantic CompanyUpdate modeli (güncellenecek alanları içerir).
    """
    update_data = company_in.model_dump(exclude_unset=True) # Pydantic V2 için .model_dump()
    for key, value in update_data.items():
        setattr(company_db, key, value)

    db.add(company_db) # Zaten session'da olduğu için db.add() gerekmeyebilir ama zararı olmaz.
    db.commit()
    db.refresh(company_db)
    print(f"CRUD: Company updated: {company_db.name} (ID: {company_db.id})")
    return company_db

def delete_company(db: Session, company_id: uuid.UUID) -> Optional[db_models.Company]:
    """
    Verilen ID'ye sahip şirketi veritabanından siler (hard delete).
    Alternatif olarak status='deleted' olarak işaretlenebilir (soft delete).
    """
    company_db = db.query(db_models.Company).filter(db_models.Company.id == company_id).first()
    if company_db:
        print(f"CRUD: Deleting company: {company_db.name} (ID: {company_db.id})")
        db.delete(company_db)
        db.commit()
        return company_db # Silinen nesne, commit sonrası session'dan çıkarılmış olabilir.
    return None