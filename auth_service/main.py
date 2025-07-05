# auth_service/main.py
import uuid
import time
from fastapi import FastAPI, Depends, HTTPException, status, Request
from fastapi.middleware.cors import CORSMiddleware
from typing import Annotated, Dict, Any, Optional
import httpx
from pydantic import BaseModel, Field

# auth.py ve config.py'den gerekli importlar
from .auth import AuthHandler, oauth2_scheme
from .config import get_settings, Settings
from .logging_config import setup_logging, LoggingMiddleware


import logging
from pythonjsonlogger import jsonlogger
import sys

SERVICE_NAME = "auth_service"
SERVICE_NAME22 = "auth_service"
logger = setup_logging(SERVICE_NAME)

app = FastAPI(title="Authentication Service API - Keycloak Integrated")

app.add_middleware(LoggingMiddleware, logger=logger)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:8080", "http://localhost:3000", "http://localhost"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class TokenRequest(BaseModel):
    authorization_code: str = Field(..., description="Keycloak'tan alınan yetkilendirme kodu")
    redirect_uri: str = Field(..., description="Token talebi için kullanılan redirect_uri, Keycloak'a gönderilenle aynı olmalı")

class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(..., description="Yenileme token'ı")

class TokenResponse(BaseModel):
    access_token: str
    expires_in: int
    refresh_expires_in: int
    refresh_token: str
    token_type: str
    id_token: Optional[str] = None
    session_state: Optional[str] = None
    scope: Optional[str] = None

# --- Helper Fonksiyon ---
async def get_current_user_from_token(
    token: Annotated[str, Depends(oauth2_scheme)],
    settings: Settings = Depends(get_settings)
) -> Dict[str, Any]:
    payload = await AuthHandler.decode_token(token, settings, logger) # logger'ı auth handler'a da geçireceğiz
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Geçersiz veya süresi dolmuş token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload

# --- Endpointler ---

@app.get("/")
async def read_root():
    logger.info("Root endpoint called.", extra={"request_id": request.state.request_id})
    return {"message": "Authentication Service API (Keycloak Entegreli) - Hoş Geldiniz!"}

@app.get("/healthz", status_code=status.HTTP_200_OK, tags=["Health Check"])
def health_check():
    return {"status": "healthy"}

@app.post("/auth/token", response_model=TokenResponse, summary="Authorization Code ile Access Token Al")
async def exchange_authorization_code_for_token(
    token_request: TokenRequest,
    settings: Settings = Depends(get_settings)
):
    if not settings.keycloak.token_endpoint or not settings.keycloak.client_id or not settings.keycloak.client_secret:
        logger.error("Keycloak token endpoint, client_id, or client_secret is not configured.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Keycloak token endpoint, client_id veya client_secret yapılandırılmamış."
        )

    token_payload = {
        "grant_type": "authorization_code",
        "code": token_request.authorization_code,
        "redirect_uri": token_request.redirect_uri,
        "client_id": settings.keycloak.client_id,
        "client_secret": settings.keycloak.client_secret,
    }

    async with httpx.AsyncClient() as client:
        try:
            logger.info(f"Requesting token from Keycloak for client_id: {settings.keycloak.client_id}")
            response = await client.post(
                settings.keycloak.token_endpoint,
                data=token_payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            response.raise_for_status()
            keycloak_tokens = response.json()
            logger.info(f"Token exchange successful for client_id: {settings.keycloak.client_id}")
            return TokenResponse(**keycloak_tokens)
        except httpx.HTTPStatusError as exc:
            error_detail = f"Keycloak token exchange hatası: {exc.response.status_code}"
            try:
                keycloak_error = exc.response.json()
                error_description = keycloak_error.get('error_description', keycloak_error.get('error', 'Detay yok'))
                error_detail += f" - {error_description}"
                logger.warning(f"Keycloak error response during token exchange: {keycloak_error}", extra={"keycloak_error": keycloak_error})
            except Exception:
                error_detail += f" - Yanıt: {exc.response.text}"
                logger.warning(f"Keycloak non-JSON error response: {exc.response.text}")
            
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_detail,
            )
        except httpx.RequestError as exc:
            logger.error(f"Could not connect to Keycloak for token exchange: {exc}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Kimlik doğrulama servisine (Keycloak) şu anda bağlanılamıyor.",
            )
        except Exception as e:
            logger.exception("Unexpected error during token exchange")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Token alımı sırasında beklenmedik bir sunucu hatası oluştu.",
            )
        
@app.post("/auth/refresh", response_model=TokenResponse, summary="Refresh Token ile Access Token Yenile")
async def refresh_access_token(
    refresh_request: RefreshTokenRequest,
    settings: Settings = Depends(get_settings)
):
    if not settings.keycloak.token_endpoint or not settings.keycloak.client_id or not settings.keycloak.client_secret:
        logger.error("Keycloak token endpoint, client_id, or client_secret is not configured for refresh.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Keycloak token endpoint, client_id veya client_secret yapılandırılmamış."
        )

    refresh_payload = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_request.refresh_token,
        "client_id": settings.keycloak.client_id,
        "client_secret": settings.keycloak.client_secret,
    }

    async with httpx.AsyncClient() as client:
        try:
            logger.info(f"Requesting token refresh for client_id: {settings.keycloak.client_id}")
            response = await client.post(
                settings.keycloak.token_endpoint,
                data=refresh_payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            response.raise_for_status()
            keycloak_tokens = response.json()
            logger.info(f"Token refresh successful for client_id: {settings.keycloak.client_id}")
            return TokenResponse(**keycloak_tokens)
        except httpx.HTTPStatusError as exc:
            error_detail = f"Keycloak token refresh hatası: {exc.response.status_code}"
            try:
                keycloak_error = exc.response.json()
                error_description = keycloak_error.get('error_description', keycloak_error.get('error', 'Detay yok'))
                error_detail += f" - {error_description}"
                logger.warning(f"Keycloak error response during token refresh: {keycloak_error}", extra={"keycloak_error": keycloak_error})
            except Exception:
                error_detail += f" - Yanıt: {exc.response.text}"
                logger.warning(f"Keycloak non-JSON error response on refresh: {exc.response.text}")
            
            status_code = exc.response.status_code if exc.response.status_code in [400, 401] else status.HTTP_500_INTERNAL_SERVER_ERROR
            raise HTTPException(
                status_code=status_code,
                detail=error_detail,
            )
        except httpx.RequestError as exc:
            logger.error(f"Could not connect to Keycloak for token refresh: {exc}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Kimlik doğrulama servisine (Keycloak) şu anda bağlanılamıyor.",
            )
        except Exception as e:
            logger.exception("Unexpected error during token refresh")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Token yenileme sırasında beklenmedik bir sunucu hatası oluştu.",
            )


@app.get("/auth/me", summary="Mevcut Kullanıcı Bilgisini Getir (Token Gerekli)")
async def read_users_me(
    current_user: Annotated[Dict[str, Any], Depends(get_current_user_from_token)]
):
    logger.info(f"User info requested for user_id: {current_user.get('sub')}")
    return current_user