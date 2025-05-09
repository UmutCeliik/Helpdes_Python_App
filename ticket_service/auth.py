# ticket_service/auth.py
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from typing import Optional, Dict, Any
import httpx
from datetime import datetime, timedelta

from .config import get_settings, Settings # config.py'den import

_jwks_cache: Optional[Dict[str, Any]] = None
_jwks_cache_expiry: Optional[datetime] = None
JWKS_CACHE_TTL_SECONDS = 3600

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token_provided_by_auth_service") # Bu sadece OpenAPI için

async def fetch_jwks_for_ticket_service(settings: Settings) -> Dict[str, Any]:
    global _jwks_cache, _jwks_cache_expiry
    now = datetime.utcnow()
    if _jwks_cache and _jwks_cache_expiry and _jwks_cache_expiry > now:
        return _jwks_cache
    if not settings.keycloak.jwks_uri:
        print("ERROR (TicketService): JWKS URI is not configured.")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="JWKS URI not configured in TicketService")
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(settings.keycloak.jwks_uri)
            response.raise_for_status()
            new_jwks = response.json()
            _jwks_cache = new_jwks
            _jwks_cache_expiry = now + timedelta(seconds=JWKS_CACHE_TTL_SECONDS)
            return new_jwks
    except Exception as e:
        print(f"ERROR (TicketService): Could not fetch JWKS: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Could not fetch JWKS from {settings.keycloak.jwks_uri}")

class AuthHandlerTicketService:
    @staticmethod
    async def decode_token(token: str, settings: Settings) -> Optional[dict]:
        if not settings.keycloak.issuer_uri or not settings.keycloak.audience:
            print("ERROR (TicketService): Keycloak issuer_uri or audience not configured.")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Auth config error in TicketService")
        jwks = await fetch_jwks_for_ticket_service(settings)
        if not jwks:
             raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not retrieve JWKS for token validation in TicketService.")
        try:
            unverified_header = jwt.get_unverified_header(token)
            rsa_key = {}
            for key_val in jwks["keys"]:
                if key_val["kid"] == unverified_header["kid"]:
                    rsa_key = {"kty": key_val["kty"], "kid": key_val["kid"], "use": key_val["use"], "n": key_val["n"], "e": key_val["e"]}
                    if "alg" in key_val: rsa_key["alg"] = key_val["alg"]
                    break
            if rsa_key:
                payload = jwt.decode(token, rsa_key, algorithms=["RS256"], issuer=settings.keycloak.issuer_uri, audience=settings.keycloak.audience)
                return payload
            raise JWTError("TicketService: Unable to find appropriate key in JWKS")
        except JWTError as e:
            print(f"ERROR (TicketService): Token validation error: {e}")
            return None
        except Exception as e:
            print(f"ERROR (TicketService): Unexpected error during token decoding: {e}")
            return None

async def get_current_user_payload(token: str = Depends(oauth2_scheme), settings: Settings = Depends(get_settings)) -> Dict[str, Any]:
    payload = await AuthHandlerTicketService.decode_token(token, settings)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Geçersiz kimlik bilgileri veya token", headers={"WWW-Authenticate": "Bearer"})
    return payload