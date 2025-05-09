# database_pkg/database.py
from sqlalchemy import create_engine
# declarative_base artık sqlalchemy.orm altında
from sqlalchemy.orm import sessionmaker, declarative_base
import os

# --- Veritabanı Bağlantı URL'si ---
# !!! Ortam değişkenlerinden alınması önerilir !!!
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:Passw0rd12.@127.0.0.1:5432/Helpdesk_Tickets_Dev")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# ORM modellerimizin miras alacağı TEKİL temel sınıf
Base = declarative_base()

# --- Dependency: Veritabanı Oturumu Sağlayıcı ---
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()