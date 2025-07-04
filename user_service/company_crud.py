# user_service/company_crud.py
import logging
from sqlalchemy.orm import Session
import uuid
from typing import Optional, List

from . import db_models
from . import models
from .models import Role as RoleEnum

logger = logging.getLogger("user_service")

def create_company(db: Session, company: models.CompanyCreate) -> db_models.Company:
    db_company = db_models.Company(
        name=company.name,
        keycloak_group_id=company.keycloak_group_id,
        status=company.status if company.status else "active"
    )
    db.add(db_company)
    db.commit()
    db.refresh(db_company)
    logger.info(f"Company created in DB: {db_company.name} (ID: {db_company.id})")
    return db_company

def get_company(db: Session, company_id: uuid.UUID) -> Optional[db_models.Company]:
    return db.query(db_models.Company).filter(db_models.Company.id == company_id).first()

def get_company_by_name(db: Session, name: str) -> Optional[db_models.Company]:
    return db.query(db_models.Company).filter(db_models.Company.name == name).first()

def get_company_by_keycloak_group_id(db: Session, keycloak_group_id: uuid.UUID) -> Optional[db_models.Company]:
    return db.query(db_models.Company).filter(db_models.Company.keycloak_group_id == keycloak_group_id).first()

def get_companies(db: Session, skip: int = 0, limit: int = 100) -> List[db_models.Company]:
    return db.query(db_models.Company).offset(skip).limit(limit).all()

def count_companies(db: Session) -> int:
    return db.query(db_models.Company).count()

def update_company(db: Session, company_db: db_models.Company, company_in: models.CompanyUpdate) -> db_models.Company:
    update_data = company_in.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(company_db, key, value)
    db.add(company_db)
    db.commit()
    db.refresh(company_db)
    logger.info(f"Company updated in DB: {company_db.name} (ID: {company_db.id})")
    return company_db

def delete_company(db: Session, company_id: uuid.UUID) -> Optional[db_models.Company]:
    company_db = db.query(db_models.Company).filter(db_models.Company.id == company_id).first()
    if company_db:
        logger.info(f"Deleting company from DB: {company_db.name} (ID: {company_db.id})")
        db.delete(company_db)
        db.commit()
        return company_db
    return None