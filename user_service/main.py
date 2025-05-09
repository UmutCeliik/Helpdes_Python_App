# user_service/main.py
from fastapi import FastAPI, HTTPException, status, Depends
from pydantic import EmailStr
from typing import List # List importu burada gerekli değilmiş
import uuid
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateSchema
from sqlalchemy.exc import ProgrammingError, IntegrityError

# Ortak ve yerel modülleri import et
from database_pkg.database import engine, Base, get_db
from database_pkg import db_models # Tüm DB modelleri burada
from database_pkg.schemas import Role
from . import models # Kendi Pydantic modelleri (UserInternal dahil)
from . import crud
from .hashing import Hasher

# --- Veritabanı Şema ve Tablo Oluşturma ---
# Sadece bir serviste (örn. burada) yapılmalı
def create_db_and_tables():
    print("Veritabanı şemaları ve tabloları oluşturuluyor/kontrol ediliyor...")
    # Gerekli tüm modellerin Base.metadata'ya tanıtıldığından emin olmak için
    # db_models modülünü import etmek yeterli olmalı.
    # Explicit import'a gerek yok ama emin olmak için:
    _ = db_models.User.__table__
    _ = db_models.Ticket.__table__

    # Şemaları oluştur
    schemas_to_create = [db_models.User.__table_args__.get('schema'),
                       db_models.Ticket.__table_args__.get('schema')]
    schemas_to_create = [s for s in schemas_to_create if s] # None olanları filtrele

    for schema_name in set(schemas_to_create): # Benzersiz şemalar
         try:
            with engine.connect() as connection:
                connection.execute(CreateSchema(schema_name, if_not_exists=True))
                connection.commit()
            print(f"'{schema_name}' şeması kontrol edildi/oluşturuldu.")
         except ProgrammingError as e:
             print(f"Şema '{schema_name}' oluşturma sırasında uyarı/hata (muhtemelen zaten var): {e}")
         except Exception as e:
             print(f"Şema '{schema_name}' oluşturulurken beklenmedik hata: {e}")

    # Tüm tabloları oluştur (Artık Base tüm modelleri biliyor)
    try:
        Base.metadata.create_all(bind=engine) # tables argümanına gerek yok
        print("Veritabanı tabloları başarıyla kontrol edildi/oluşturuldu.")
    except Exception as e:
        print(f"Tablolar oluşturulurken HATA: {e}")
        import traceback
        traceback.print_exc()

create_db_and_tables()
# --- Veritabanı Kurulum Sonu ---


app = FastAPI(title="User Service API")


@app.get("/")
async def read_root():
    return {"message": "User Service API'ye hoş geldiniz!"}


@app.post("/users/", response_model=models.User, status_code=status.HTTP_201_CREATED, summary="Yeni Kullanıcı Oluştur")
async def create_user_endpoint(
    user_in: models.UserCreate,
    db: Session = Depends(get_db)
):
    db_user = crud.get_user_by_email(db, email=user_in.email)
    if db_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bu e-posta adresi zaten kullanılıyor."
        )
    hashed_password = Hasher.get_password_hash(user_in.password)
    try:
        created_db_user = crud.create_user(db=db, user=user_in, hashed_password=hashed_password)
        return created_db_user # Otomatik dönüşüm
    except IntegrityError:
         db.rollback()
         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="DB Bütünlük Hatası.")
    except Exception as e:
        db.rollback()
        print(f"Kullanıcı oluşturulurken DB hatası: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Sunucu hatası.")


@app.get("/users/internal/by_email/{email}", response_model=models.UserInternal, include_in_schema=False)
async def get_user_internal_by_email_endpoint(
    email: EmailStr,
    db: Session = Depends(get_db)
  ):
    db_user = crud.get_user_by_email(db, email=email)
    if db_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kullanıcı bulunamadı")
    # UserInternal Pydantic modeli (models.py'da) hashlenmiş şifre dahil tüm alanları içeriyor
    # ve from_attributes=True ile SQLAlchemy nesnesinden otomatik dönüşüm yapıyor.
    return db_user

# Diğer User CRUD endpointleri eklenebilir