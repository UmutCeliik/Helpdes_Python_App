# user_service/crud.py
from sqlalchemy.orm import Session
import uuid
from typing import Optional, List

# Kendi servisimize ait modelleri import ediyoruz
from . import db_models
from . import models
from .models import Role as RoleEnum

def get_user_by_keycloak_id(db: Session, keycloak_id: uuid.UUID) -> Optional[db_models.User]:
    return db.query(db_models.User).filter(db_models.User.id == keycloak_id).first()

def get_user_by_email(db: Session, email: str) -> Optional[db_models.User]: # Bu hala faydalı olabilir
    return db.query(db_models.User).filter(db_models.User.email == email).first()

def delete_user_by_keycloak_id(db: Session, keycloak_id: uuid.UUID) -> Optional[db_models.User]:
    """
    Verilen Keycloak ID'sine sahip kullanıcıyı lokal veritabanından siler.
    Kullanıcı bulunup silinirse, silinen kullanıcı nesnesini döndürür.
    Kullanıcı bulunamazsa None döndürür.
    """
    db_user = db.query(db_models.User).filter(db_models.User.id == keycloak_id).first()
    if db_user:
        print(f"USER_SERVICE_CRUD: Deleting user {db_user.email} (ID: {keycloak_id}) from local DB.")
        db.delete(db_user)
        db.commit()
        # db.commit() sonrası db_user session'dan expire olmuş olabilir,
        # ancak silme işlemi öncesi bilgileri hala tutar.
        # Silme onayı için bu objeyi döndürebiliriz.
        return db_user
    else:
        print(f"USER_SERVICE_CRUD: User with ID {keycloak_id} not found in local DB for deletion.")
        return None

def get_or_create_user(db: Session, user_data: models.UserCreateInternal) -> db_models.User:
    db_user = get_user_by_keycloak_id(db, keycloak_id=user_data.id)
    if db_user:
        # Kullanıcı zaten var, bilgilerini güncelle (opsiyonel)
        print(f"USER_SERVICE_CRUD: User {user_data.id} found, updating info.")
        db_user.email = user_data.email
        db_user.full_name = user_data.full_name
        db_user.is_active = user_data.is_active
        # Rolleri güncelleme mantığı eklenebilir.
        # Örneğin, ilk gelen Keycloak rolünü DB'ye yazabiliriz (eğer DB'de tek bir rol tutuyorsak)
        # Veya rolleri ayrı bir tabloda yönetebiliriz. Şimdilik basit tutalım.
        # Eğer DB'deki 'role' enum ise ve Keycloak'tan gelen string listesi varsa eşleştirme gerekir.
        # Şimdilik Keycloak'tan gelen ilk rolü (varsa ve enum'da varsa) atayalım:
        if user_data.roles:
            if "general-admin" in user_data.roles and hasattr(RoleEnum, "GENERAL_ADMIN"): # RoleEnum'da GENERAL_ADMIN varsa
                 db_user.role = RoleEnum.GENERAL_ADMIN
            elif "helpdesk-admin" in user_data.roles and hasattr(RoleEnum, "HELPDESK_ADMIN"): # RoleEnum'da HELPDESK_ADMIN varsa
                 db_user.role = RoleEnum.HELPDESK_ADMIN
            elif RoleEnum.AGENT.value in user_data.roles:
                db_user.role = RoleEnum.AGENT
            elif RoleEnum.EMPLOYEE.value in user_data.roles: # employee bizim customer-user için genel tabirimizdi
                db_user.role = RoleEnum.EMPLOYEE

    else:
        print(f"USER_SERVICE_CRUD: User {user_data.id} not found, creating new user.")
        determined_role = RoleEnum.EMPLOYEE 
        if user_data.roles:
            if "general-admin" in user_data.roles and hasattr(RoleEnum, "GENERAL_ADMIN"):
                 determined_role = RoleEnum.GENERAL_ADMIN
            elif "helpdesk-admin" in user_data.roles and hasattr(RoleEnum, "HELPDESK_ADMIN"):
                 determined_role = RoleEnum.HELPDESK_ADMIN
            elif RoleEnum.AGENT.value in user_data.roles:
                determined_role = RoleEnum.AGENT
            # EMPLOYEE zaten varsayılan olduğu için ayrıca kontrol etmeye gerek yok.
            
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
    """
    Veritabanındaki tüm kullanıcıları sayfalama yaparak listeler.
    """
    return db.query(db_models.User).order_by(db_models.User.created_at.desc()).offset(skip).limit(limit).all()

def count_users(db: Session) -> int:
    """
    Veritabanındaki toplam kullanıcı sayısını döndürür.
    """
    return db.query(db_models.User).count()

    