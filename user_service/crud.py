# user_service/crud.py
from sqlalchemy.orm import Session
import uuid
# Ortak DB modelini ve User Pydantic modelini import et
from database_pkg import db_models
from . import models # Kendi Pydantic modelleri

def get_user_by_email(db: Session, email: str) -> db_models.User | None:
    return db.query(db_models.User).filter(db_models.User.email == email).first()

def get_user(db: Session, user_id: uuid.UUID) -> db_models.User | None:
    return db.query(db_models.User).filter(db_models.User.id == user_id).first()

def create_user(db: Session, user: models.UserCreate, hashed_password: str) -> db_models.User:
    db_user = db_models.User(
        email=user.email,
        full_name=user.full_name,
        hashed_password=hashed_password,
        role=user.role
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user