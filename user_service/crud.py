# user_service/crud.py
import logging
from sqlalchemy.orm import Session
import uuid
from typing import Optional, List

from . import db_models
from . import models
from .models import Role as RoleEnum

logger = logging.getLogger("user_service")

def get_user_by_keycloak_id(db: Session, keycloak_id: uuid.UUID) -> Optional[db_models.User]:
    return db.query(db_models.User).filter(db_models.User.id == keycloak_id).first()

def get_user_by_email(db: Session, email: str) -> Optional[db_models.User]:
    return db.query(db_models.User).filter(db_models.User.email == email).first()

def delete_user_by_keycloak_id(db: Session, keycloak_id: uuid.UUID) -> Optional[db_models.User]:
    db_user = db.query(db_models.User).filter(db_models.User.id == keycloak_id).first()
    if db_user:
        logger.info(f"Deleting user {db_user.email} (ID: {keycloak_id}) from local DB.")
        db.delete(db_user)
        db.commit()
        return db_user
    else:
        logger.warning(f"User with ID {keycloak_id} not found in local DB for deletion.")
        return None

def get_or_create_user(db: Session, user_data: models.UserCreateInternal) -> db_models.User:
    db_user = get_user_by_keycloak_id(db, keycloak_id=user_data.id)
    if db_user:
        logger.debug(f"User {user_data.id} found, updating info.")
        db_user.email = user_data.email
        db_user.full_name = user_data.full_name
        db_user.is_active = user_data.is_active
    else:
        logger.info(f"User {user_data.id} not found, creating new user.")
        determined_role = RoleEnum.EMPLOYEE 
        if user_data.roles:
            if "general-admin" in user_data.roles and hasattr(RoleEnum, "GENERAL_ADMIN"):
                 determined_role = RoleEnum.GENERAL_ADMIN
            elif "helpdesk-admin" in user_data.roles and hasattr(RoleEnum, "HELPDESK_ADMIN"):
                 determined_role = RoleEnum.HELPDESK_ADMIN
            elif RoleEnum.AGENT.value in user_data.roles:
                determined_role = RoleEnum.AGENT
        
        db_user = db_models.User(
            id=user_data.id,
            email=user_data.email,
            full_name=user_data.full_name,
            role=determined_role,
            is_active=user_data.is_active
        )
        db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

def get_users(db: Session, skip: int = 0, limit: int = 100) -> List[db_models.User]:
    return db.query(db_models.User).order_by(db_models.User.created_at.desc()).offset(skip).limit(limit).all()

def count_users(db: Session) -> int:
    return db.query(db_models.User).count()