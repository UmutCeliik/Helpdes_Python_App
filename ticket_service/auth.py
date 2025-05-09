# ticket_service/auth.py
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError, exceptions
# PyJWT'nin (python-jose'un kullandığı) spesifik hatalarını import etmek için:
# Eğer jose.jwt altında direkt yoksa, jose.exceptions'tan import edilebilirler.
# Genellikle jwt.ExpiredSignatureError gibi erişilebilir olurlar.
# from jose.exceptions import ExpiredSignatureError, InvalidAudienceError, InvalidClaimError # InvalidIssuerError için InvalidClaimError kullanılabilir

from typing import Optional, Dict, Any
import httpx
from datetime import datetime, timedelta

# config.py'den ayarları import et
from .config import get_settings, Settings

# JWKS'leri cache'lemek için
_jwks_cache: Optional[Dict[str, Any]] = None
_jwks_cache_expiry: Optional[datetime] = None
JWKS_CACHE_TTL_SECONDS = 3600 # 1 saat cache'le

# Bu scheme, token'ın "Authorization: Bearer YOUR_TOKEN" başlığından alınmasını sağlar.
# tokenUrl burada sadece FastAPI'nin OpenAPI dökümanı için bir ipucu.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token_not_issued_here")

async def fetch_jwks_for_ticket_service(settings: Settings) -> Dict[str, Any]:
    global _jwks_cache, _jwks_cache_expiry
    now = datetime.utcnow()

    if _jwks_cache and _jwks_cache_expiry and _jwks_cache_expiry > now:
        print("TICKET_SERVICE_AUTH: Using cached JWKS.")
        return _jwks_cache

    if not settings.keycloak.jwks_uri:
        print("ERROR (TicketService): JWKS URI is not configured.")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="JWKS URI not configured in TicketService")

    try:
        async with httpx.AsyncClient() as client:
            print(f"TICKET_SERVICE_AUTH: Fetching JWKS from {settings.keycloak.jwks_uri}")
            response = await client.get(settings.keycloak.jwks_uri)
            response.raise_for_status()
            new_jwks = response.json()
            _jwks_cache = new_jwks
            _jwks_cache_expiry = now + timedelta(seconds=JWKS_CACHE_TTL_SECONDS)
            print("TICKET_SERVICE_AUTH: Fetched and cached new JWKS.")
            return new_jwks
    except httpx.HTTPStatusError as exc:
        print(f"ERROR (TicketService): Could not fetch JWKS (HTTPStatusError): {exc.response.status_code} - {exc.response.text}")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"Could not fetch JWKS: {exc.response.status_code}")
    except Exception as e:
        print(f"ERROR (TicketService): Could not fetch JWKS (Exception): {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Could not fetch JWKS from {settings.keycloak.jwks_uri}")


class AuthHandlerTicketService:
    @staticmethod
    async def decode_token(token: str, settings: Settings) -> Optional[dict]:
        print(f"TICKET_SERVICE_AUTH: Attempting to decode token. Expected audience: '{settings.keycloak.audience}', Expected issuer: '{settings.keycloak.issuer_uri}'")
        
        if not settings.keycloak.issuer_uri or not settings.keycloak.audience:
            print("ERROR (TicketService): Keycloak issuer_uri or audience not configured in settings.")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Auth config error in TicketService: issuer or audience missing.")
        
        jwks = await fetch_jwks_for_ticket_service(settings)
        if not jwks or not jwks.get("keys"):
             print(f"ERROR (TicketService): JWKS not found or no keys in JWKS. JWKS: {jwks}")
             raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not retrieve valid JWKS for token validation in TicketService.")

        try:
            unverified_header = jwt.get_unverified_header(token)
            token_kid = unverified_header.get("kid")
            print(f"TICKET_SERVICE_AUTH: Token unverified header: {unverified_header}, Token KID: {token_kid}")

            if not token_kid:
                print("ERROR (TicketService): Token header does not contain 'kid' (Key ID).")
                raise JWTError("Token header missing 'kid'")

            rsa_key = {}
            for key_val in jwks["keys"]:
                if key_val.get("kid") == token_kid:
                    rsa_key = {
                        "kty": key_val.get("kty"),
                        "kid": key_val.get("kid"),
                        "use": key_val.get("use"),
                        "n": key_val.get("n"),
                        "e": key_val.get("e")
                    }
                    if "alg" in key_val: 
                        rsa_key["alg"] = key_val.get("alg")
                    print(f"TICKET_SERVICE_AUTH: Found matching RSA key in JWKS for kid: {token_kid}")
                    break
            
            if not rsa_key:
                available_kids = [k.get('kid') for k in jwks.get('keys', [])]
                print(f"ERROR (TicketService): Could not find RSA key in JWKS for kid: {token_kid}. Available kids in JWKS: {available_kids}")
                raise JWTError("TicketService: Unable to find appropriate key in JWKS matching token's kid")

            # Token'ı doğrulamadan önce bazı claim'leri loglayalım
            unverified_claims = jwt.get_unverified_claims(token)
            print(f"TICKET_SERVICE_AUTH: Unverified token claims - iss: '{unverified_claims.get('iss')}', aud: '{unverified_claims.get('aud')}'")

            payload = jwt.decode(
                token, 
                rsa_key, 
                algorithms=["RS256"], # Keycloak genellikle RS256 kullanır
                issuer=settings.keycloak.issuer_uri, 
                audience=settings.keycloak.audience  # Bu, token'daki 'aud' claim'i ile eşleşmeli
            )
            print(f"TICKET_SERVICE_AUTH: Token successfully decoded. Payload 'sub': {payload.get('sub')}, 'aud': {payload.get('aud')}, 'iss': {payload.get('iss')}")
            return payload

        except jwt.ExpiredSignatureError as e:
            print(f"ERROR (TicketService): Token ExpiredSignatureError: {e}")
            return None
        except jwt.InvalidAudienceError as e:
            # PyJWT'de InvalidAudienceError'un mesajı genellikle beklenen ve alınan audience'ı içerir.
            print(f"ERROR (TicketService): Token InvalidAudienceError: {e}")
            return None
        except jwt.InvalidIssuerError as e:
            print(f"ERROR (TicketService): Token InvalidIssuerError: {e}")
            return None
        except JWTError as e: # Diğer JWT (jose) hataları
            print(f"ERROR (TicketService): General JWTError during token validation: {e}")
            return None
        except Exception as e:
            print(f"ERROR (TicketService): Unexpected error during token decoding: {type(e).__name__} - {e}")
            return None

async def get_current_user_payload(
    token: str = Depends(oauth2_scheme), 
    settings: Settings = Depends(get_settings)
) -> Dict[str, Any]:
    payload = await AuthHandlerTicketService.decode_token(token, settings)
    if payload is None:
        # decode_token içinde detaylı loglama yapıldığı için burada daha genel bir mesaj verilebilir
        # veya spesifik hata loglardan takip edilir.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="Geçersiz kimlik bilgileri veya token doğrulanamadı", # Mesajı biraz güncelledim
            headers={"WWW-Authenticate": "Bearer"}
        )
    return payload