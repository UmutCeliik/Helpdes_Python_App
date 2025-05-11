# user_service/crud.py
from sqlalchemy.orm import Session
import uuid
# Ortak DB modelini ve User Pydantic modelini import et
from database_pkg import db_models
from . import models # Kendi Pydantic modelleri
from database_pkg.schemas import Role as RoleEnum
from typing import Optional

def get_user_by_keycloak_id(db: Session, keycloak_id: uuid.UUID) -> Optional[db_models.User]:
    return db.query(db_models.User).filter(db_models.User.id == keycloak_id).first()

def get_user_by_email(db: Session, email: str) -> Optional[db_models.User]: # Bu hala faydalı olabilir
    return db.query(db_models.User).filter(db_models.User.email == email).first()

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
            # Basit bir mantık: Keycloak rollerinden bilinen birini ata
            # Bu kısım projenizin rol yönetimine göre detaylandırılmalı
            if RoleEnum.AGENT.value in user_data.roles:
                db_user.role = RoleEnum.AGENT
            elif "helpdesk-admin" in user_data.roles: # Keycloak rol adı
                # DB'de 'admin' diye bir enum yoksa bu hata verir, ya enum'a ekleyin ya da başka bir mantık kurun
                # Şimdilik 'agent' yapalım veya nullable bırakalım
                db_user.role = RoleEnum.AGENT # Veya None, ya da admin rolünü enum'a ekleyin
            elif RoleEnum.EMPLOYEE.value in user_data.roles:
                db_user.role = RoleEnum.EMPLOYEE
            else:
                db_user.role = RoleEnum.EMPLOYEE # Varsayılan
        else:
            db_user.role = RoleEnum.EMPLOYEE # Rol gelmezse varsayılan

    else:
        # Kullanıcı yok, yeni oluştur
        print(f"USER_SERVICE_CRUD: User {user_data.id} not found, creating new user.")
        # DB'deki role alanı için gelen Keycloak rollerinden birini seçmemiz gerekebilir
        # veya varsayılan bir rol atayabiliriz.
        determined_role = RoleEnum.EMPLOYEE # Varsayılan
        if user_data.roles:
            if RoleEnum.AGENT.value in user_data.roles:
                determined_role = RoleEnum.AGENT
            elif "helpdesk-admin" in user_data.roles:
                 # DB'de 'admin' diye bir enum yoksa bu hata verir.
                determined_role = RoleEnum.AGENT # Veya admin rolünü enum'a ekleyin
            # Diğer roller için de benzer mantık eklenebilir

        db_user = db_models.User(
            id=user_data.id, # Keycloak ID'si
            email=user_data.email,
            full_name=user_data.full_name,
            role=determined_role, # Keycloak'tan gelen role göre ayarlanmalı
            is_active=user_data.is_active
            # hashed_password artık yok
        )
        db.add(db_user)

    db.commit()
    db.refresh(db_user)
    return db_user