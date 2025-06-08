# user_service/database.py veya ticket_service/database.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import os
from .config import get_settings # Kendi config dosyasından okumak için

settings = get_settings()

# Artık her servis kendi DATABASE_URL'ini kendi config'inden alacak
DATABASE_URL = settings.database.url 

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()