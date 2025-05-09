# ticket_service/main.py
from fastapi import FastAPI, HTTPException, status, Path, Body, Depends, Response
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Annotated
import uuid
from datetime import datetime
from sqlalchemy.orm import Session
# Schema oluşturma ve DB hataları importları kaldırıldı (artık burada değil)
from sqlalchemy.exc import IntegrityError # Sadece bu gerekli olabilir

# Ortak ve yerel modülleri import et
from database_pkg.database import get_db # Sadece get_db gerekli
from database_pkg.schemas import Role
from . import models # Kendi Pydantic modelleri
from . import crud
from .auth import get_current_user_payload # Kendi Auth dependency

app = FastAPI(title="Ticket Service API")

# CORS Ayarları
origins = [
    "http://localhost:5173",
    "http://localhost:8080",
    "http://localhost:3000",
    "http://localhost",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Veritabanı Şema ve Tablo Oluşturma Kodu BURADAN KALDIRILDI ---
# Bu işlem artık User Service tarafından yapılacak.

@app.get("/")
async def read_root():
    return {"message": "Ticket Service API'ye hoş geldiniz!"}

# --- Endpointler (Importlar ve DB kullanımı güncellendi, mantık aynı) ---

@app.post("/tickets/", response_model=models.Ticket, status_code=status.HTTP_201_CREATED)
async def create_ticket(
    ticket_in: models.TicketCreate,
    current_user_payload: Annotated[dict, Depends(get_current_user_payload)],
    db: Session = Depends(get_db),
):
    creator_user_id = current_user_payload.get("user_id")
    if not creator_user_id:
         raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token ID yok")

    print(f"Bileti oluşturan kullanıcı ID: {creator_user_id}")
    try:
        created_db_ticket = crud.create_ticket(
            db=db, ticket=ticket_in, creator_id=uuid.UUID(creator_user_id)
        )
        return created_db_ticket
    except IntegrityError: # Kullanıcı ID geçersizse FK hatası verir
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Geçersiz kullanıcı ID")
    except Exception as e:
        db.rollback()
        print(f"Bilet oluştururken DB hatası: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Sunucu hatası")


@app.get("/tickets/", response_model=List[models.Ticket])
async def read_tickets(
    current_user_payload: Annotated[dict, Depends(get_current_user_payload)],
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 100,
):
    # Rol kontrolünü kaldırmıştık
    db_tickets = crud.get_tickets(db=db, skip=skip, limit=limit)
    return db_tickets


@app.get("/tickets/{ticket_id}", response_model=models.Ticket)
async def read_ticket(
    ticket_id: uuid.UUID,
    current_user_payload: Annotated[dict, Depends(get_current_user_payload)],
    db: Session = Depends(get_db),
):
    db_ticket = crud.get_ticket(db=db, ticket_id=ticket_id)
    if db_ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bilet bulunamadı")

    user_id = current_user_payload.get("user_id")
    user_role = current_user_payload.get("role")

    if str(db_ticket.creator_id) != user_id and user_role != Role.AGENT:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Yetki yok")
    return db_ticket


@app.patch("/tickets/{ticket_id}", response_model=models.Ticket)
async def update_ticket(
    ticket_id: uuid.UUID,
    ticket_update: models.TicketUpdate,
    current_user_payload: Annotated[dict, Depends(get_current_user_payload)],
    db: Session = Depends(get_db)
):
    user_role = current_user_payload.get("role")
    if user_role != Role.AGENT:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Yetki yok")

    updated_db_ticket = crud.update_ticket(db=db, ticket_id=ticket_id, ticket_update=ticket_update)
    if updated_db_ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bilet bulunamadı")
    return updated_db_ticket


@app.delete("/tickets/{ticket_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_ticket(
    ticket_id: uuid.UUID,
    current_user_payload: Annotated[dict, Depends(get_current_user_payload)],
    db: Session = Depends(get_db)
 ):
    user_role = current_user_payload.get("role")
    if user_role != Role.AGENT:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Yetki yok")

    deleted_db_ticket = crud.delete_ticket(db=db, ticket_id=ticket_id)
    if deleted_db_ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bilet bulunamadı")
    return Response(status_code=status.HTTP_204_NO_CONTENT)