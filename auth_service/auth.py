# auth_service/auth.py
from jose import jwt, JWTError
from fastapi import HTTPException, status, Depends
from fastapi.security import OAuth2PasswordBearer 
# OAuth2PasswordBearer'ı artık doğrudan kullanmayacağız ama token doğrulama için bir scheme gerekebilir.
# Şimdilik get_current_user_payload için bırakalım, sonra ticket_service'teki gibi düzenleyebiliriz.
from typing import Optional, Dict, Any
import httpx # JWKS çekmek için
from datetime import datetime, timedelta # Token expiry kontrolü için

# config.py'den ayarları import et
from .config import get_settings, Settings

# JWKS'leri cache'lemek için basit bir global değişken (production için daha iyi bir cache mekanizması gerekebilir)
_jwks_cache: Optional[Dict[str, Any]] = None
_jwks_cache_expiry: Optional[datetime] = None
JWKS_CACHE_TTL_SECONDS = 3600 # 1 saat cache'le

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token") # Bu satır hala diğer servislerin bu URL'e token için geleceğini belirtir.

async def fetch_jwks(settings: Settings) -> Dict[str, Any]:
    global _jwks_cache, _jwks_cache_expiry
    now = datetime.utcnow()

    if _jwks_cache and _jwks_cache_expiry and _jwks_cache_expiry > now:
        print("Using cached JWKS.")
        return _jwks_cache

    if not settings.keycloak.jwks_uri:
        print("ERROR: JWKS URI is not configured.")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="JWKS URI not configured")

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(settings.keycloak.jwks_uri)
            response.raise_for_status()
            new_jwks = response.json()
            _jwks_cache = new_jwks
            _jwks_cache_expiry = now + timedelta(seconds=JWKS_CACHE_TTL_SECONDS)
            print("Fetched and cached new JWKS.")
            return new_jwks
    except httpx.HTTPStatusError as e:
        print(f"Error fetching JWKS: {e.response.status_code} - {e.response.text}")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"Could not fetch JWKS: {e.response.status_code}")
    except Exception as e:
        print(f"Unexpected error fetching JWKS: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error fetching JWKS")


class AuthHandler:
    @staticmethod
    async def decode_token(token: str, settings: Settings = Depends(get_settings)) -> Optional[dict]:
        if not settings.keycloak.issuer_uri or not settings.keycloak.client_id:
            print("ERROR: Keycloak issuer_uri or client_id not configured for token decoding.")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Authentication service not properly configured (issuer/client_id)."
            )
        
        jwks = await fetch_jwks(settings)
        if not jwks:
             raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Could not retrieve JWKS for token validation."
            )

        try:
            # Token başlığından kid (Key ID) al
            unverified_header = jwt.get_unverified_header(token)
            rsa_key = {}
            for key in jwks["keys"]:
                if key["kid"] == unverified_header["kid"]:
                    rsa_key = {
                        "kty": key["kty"],
                        "kid": key["kid"],
                        "use": key["use"],
                        "n": key["n"],
                        "e": key["e"]
                    }
                    # Bazı Keycloak versiyonları 'alg' de içerebilir, onu da ekleyebiliriz.
                    if "alg" in key:
                         rsa_key["alg"] = key["alg"]
                    break
            
            if rsa_key:
                payload = jwt.decode(
                    token,
                    rsa_key,
                    algorithms=["RS256"], # Keycloak genellikle RS256 kullanır, kontrol edin
                    issuer=settings.keycloak.issuer_uri,
                    audience=settings.keycloak.client_id, # Token'ın bu client için olduğunu doğrula
                    # options={"verify_aud": True} # Pydantic v2'de bu otomatik olabilir
                )
                # Token'ın süresinin dolup dolmadığını manuel olarak da kontrol edebiliriz (jwt.decode bunu yapar)
                # if datetime.utcfromtimestamp(payload.get("exp", 0)) < datetime.utcnow():
                #    raise JWTError("Token has expired")
                return payload
            raise JWTError("Unable to find appropriate key")

        except JWTError as e:
            print(f"Token validation error: {e}")
            # raise HTTPException(
            #     status_code=status.HTTP_401_UNAUTHORIZED,
            #     detail=f"Invalid token: {e}",
            #     headers={"WWW-Authenticate": "Bearer"},
            # )
            return None # Hata durumunda None döndür, çağıran yer yönetsin.
        except Exception as e:
            print(f"An unexpected error occurred during token decoding: {e}")
            # raise HTTPException(
            #     status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            #     detail=f"Could not process token: {e}"
            # )
            return None

    # verify_password, get_password_hash, create_access_token metodları artık burada GEREKLİ DEĞİL.
    # Onları silebilirsiniz.