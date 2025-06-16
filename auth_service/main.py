# auth_service/main.py
from fastapi import FastAPI, Depends, HTTPException, status, Form, Body
from fastapi.middleware.cors import CORSMiddleware
from typing import Annotated, Dict, Any, Optional
import httpx
from pydantic import BaseModel, Field

# auth.py ve config.py'den gerekli importlar
from .auth import AuthHandler, oauth2_scheme # oauth2_scheme'i şimdilik tutuyoruz, korumalı endpointler için
from .config import get_settings, Settings

app = FastAPI(title="Authentication Service API - Keycloak Integrated")

# CORS Ayarları (Mevcut ayarlarınızla aynı kalabilir)
origins = [
    "http://localhost:5173", # Vue frontend
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

# --- Pydantic Modelleri ---
class TokenRequest(BaseModel):
    authorization_code: str = Field(..., description="Keycloak'tan alınan yetkilendirme kodu")
    redirect_uri: str = Field(..., description="Token talebi için kullanılan redirect_uri, Keycloak'a gönderilenle aynı olmalı")
    # PKCE kullanılıyorsa 'code_verifier' da eklenebilir. Şimdilik basit tutuyoruz.

class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(..., description="Yenileme token'ı")

class TokenResponse(BaseModel):
    access_token: str
    expires_in: int
    refresh_expires_in: int
    refresh_token: str
    token_type: str
    id_token: Optional[str] = None # ID Token da döndürülebilir
    session_state: Optional[str] = None
    scope: Optional[str] = None

# --- Helper Fonksiyon ---
async def get_current_user_from_token(
    token: Annotated[str, Depends(oauth2_scheme)], # Bu, Authorization: Bearer header'ını bekler
    settings: Settings = Depends(get_settings)
) -> Dict[str, Any]:
    """
    Verilen token'ı doğrular ve payload'u döndürür.
    Bu fonksiyon, auth_service içinde token gerektiren diğer endpointler olursa kullanılabilir.
    """
    payload = await AuthHandler.decode_token(token, settings)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Geçersiz veya süresi dolmuş token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    # Burada kullanıcıya ait ek bilgiler (örneğin DB'den) çekilebilir, şimdilik sadece payload.
    return payload

# --- Endpointler ---

@app.get("/")
async def read_root():
    return {"message": "Authentication Service API (Keycloak Entegreli) - Hoş Geldiniz!"}

@app.get("/healthz", status_code=status.HTTP_200_OK, tags=["Health Check"])
def health_check():
    """
    Kubernetes probları için basit sağlık kontrolü. 
    Hiçbir dış bağımlılığı yoktur.
    """
    return {"status": "healthy"}

@app.post("/auth/token", response_model=TokenResponse, summary="Authorization Code ile Access Token Al")
async def exchange_authorization_code_for_token(
    token_request: TokenRequest, # Request body olarak JSON bekleniyor
    settings: Settings = Depends(get_settings)
):
    """
    Frontend'den gelen `authorization_code` ve `redirect_uri`'yi kullanarak
    Keycloak'tan access token, refresh token vb. alır.
    """
    if not settings.keycloak.token_endpoint or not settings.keycloak.client_id or not settings.keycloak.client_secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Keycloak token endpoint, client_id veya client_secret yapılandırılmamış."
        )

    token_payload = {
        "grant_type": "authorization_code",
        "code": token_request.authorization_code,
        "redirect_uri": token_request.redirect_uri, # Bu, kod alınırken kullanılan URI ile aynı olmalı
        "client_id": settings.keycloak.client_id,
        "client_secret": settings.keycloak.client_secret,
    }

    async with httpx.AsyncClient() as client:
        try:
            print(f"Requesting token from Keycloak: {settings.keycloak.token_endpoint} with client_id: {settings.keycloak.client_id}")
            response = await client.post(
                settings.keycloak.token_endpoint,
                data=token_payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            response.raise_for_status()  # HTTP 4xx veya 5xx hatası varsa exception fırlat
            keycloak_tokens = response.json()
            
            # Keycloak'tan dönen tüm token bilgilerini TokenResponse modeline uygun döndür
            return TokenResponse(**keycloak_tokens)

        except httpx.HTTPStatusError as exc:
            error_detail = f"Keycloak token exchange hatası: {exc.response.status_code}"
            try:
                keycloak_error = exc.response.json()
                error_detail += f" - {keycloak_error.get('error_description', keycloak_error.get('error', 'Detay yok'))}"
                print(f"Keycloak error response: {keycloak_error}")
            except Exception:
                error_detail += f" - Yanıt: {exc.response.text}"
            
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, # Genellikle 400 Bad Request döner Keycloak
                detail=error_detail,
            )
        except httpx.RequestError as exc:
            print(f"Keycloak'a bağlanılamadı: {exc}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Kimlik doğrulama servisine (Keycloak) şu anda bağlanılamıyor.",
            )
        except Exception as e:
            print(f"Token exchange sırasında beklenmedik hata: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Token alımı sırasında beklenmedik bir sunucu hatası oluştu.",
            )

@app.post("/auth/refresh", response_model=TokenResponse, summary="Refresh Token ile Access Token Yenile")
async def refresh_access_token(
    refresh_request: RefreshTokenRequest,
    settings: Settings = Depends(get_settings)
):
    """
    Verilen `refresh_token`'ı kullanarak Keycloak'tan yeni bir access token alır.
    """
    if not settings.keycloak.token_endpoint or not settings.keycloak.client_id or not settings.keycloak.client_secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Keycloak token endpoint, client_id veya client_secret yapılandırılmamış."
        )

    refresh_payload = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_request.refresh_token,
        "client_id": settings.keycloak.client_id,
        "client_secret": settings.keycloak.client_secret, # Confidential client için secret gerekli
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                settings.keycloak.token_endpoint,
                data=refresh_payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            response.raise_for_status()
            keycloak_tokens = response.json()
            return TokenResponse(**keycloak_tokens)

        except httpx.HTTPStatusError as exc:
            error_detail = f"Keycloak token refresh hatası: {exc.response.status_code}"
            try:
                keycloak_error = exc.response.json()
                error_detail += f" - {keycloak_error.get('error_description', keycloak_error.get('error', 'Detay yok'))}"
            except Exception:
                error_detail += f" - Yanıt: {exc.response.text}"
            
            # Refresh token geçersizse genellikle 400 Bad Request döner
            status_code = exc.response.status_code if exc.response.status_code in [400, 401] else status.HTTP_500_INTERNAL_SERVER_ERROR
            raise HTTPException(
                status_code=status_code,
                detail=error_detail,
            )
        except httpx.RequestError as exc:
            print(f"Keycloak'a bağlanılamadı (refresh): {exc}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Kimlik doğrulama servisine (Keycloak) şu anda bağlanılamıyor.",
            )
        except Exception as e:
            print(f"Token refresh sırasında beklenmedik hata: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Token yenileme sırasında beklenmedik bir sunucu hatası oluştu.",
            )


# Örnek korumalı endpoint (gerekirse)
# Bu endpoint, sadece geçerli bir Keycloak access token'ı ile çağrılabilir.
@app.get("/auth/me", summary="Mevcut Kullanıcı Bilgisini Getir (Token Gerekli)")
async def read_users_me(
    current_user: Annotated[Dict[str, Any], Depends(get_current_user_from_token)]
):
    """
    Geçerli bir Bearer token ile çağrıldığında token payload'unu döndürür.
    `roles` ve `sub` (user_id) gibi bilgileri içerir.
    """
    return current_user

# Eski login_for_access_token (OAuth2PasswordRequestForm kullanan) ve
# USER_SERVICE_URL ile ilgili kısımlar silindi.