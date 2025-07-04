# ticket_service/auth.py
import logging
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from typing import Optional, Dict, Any
import httpx
from datetime import datetime, timedelta

from .config import get_settings, Settings

# Servis adıyla logger'ı al
logger = logging.getLogger("ticket_service")

_jwks_cache: Optional[Dict[str, Any]] = None
_jwks_cache_expiry: Optional[datetime] = None
JWKS_CACHE_TTL_SECONDS = 3600

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token_not_issued_here")

async def fetch_jwks_for_ticket_service(settings: Settings) -> Dict[str, Any]:
    """JWKS'leri Keycloak'tan çeker. SSL doğrulamasını atlar."""
    global _jwks_cache, _jwks_cache_expiry
    now = datetime.utcnow()

    if _jwks_cache and _jwks_cache_expiry and _jwks_cache_expiry > now:
        logger.debug("Using cached JWKS.")
        return _jwks_cache

    if not settings.keycloak.jwks_uri:
        logger.error("JWKS URI is not configured.")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="JWKS URI not configured in TicketService")

    logger.info(f"Fetching JWKS from {settings.keycloak.jwks_uri}")
    try:
        async with httpx.AsyncClient(verify=False) as client:
            response = await client.get(settings.keycloak.jwks_uri)
            response.raise_for_status()
            new_jwks = response.json()
            _jwks_cache = new_jwks
            _jwks_cache_expiry = now + timedelta(seconds=JWKS_CACHE_TTL_SECONDS)
            logger.info("Fetched and cached new JWKS.")
            return new_jwks
    except Exception as e:
        logger.exception("Could not fetch JWKS for ticket_service.")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Could not fetch validation keys from authentication server: {e}")


class AuthHandlerTicketService:
    @staticmethod
    async def decode_token(token: str, settings: Settings) -> Optional[dict]:
        logger.debug(f"Attempting to decode token. Expected audience: '{settings.keycloak.audience}', Expected issuer: '{settings.keycloak.issuer_uri}'")
        
        if not settings.keycloak.issuer_uri or not settings.keycloak.audience:
            logger.error("Keycloak issuer_uri or audience not configured in settings.")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Auth config error in TicketService: issuer or audience missing.")
            
        jwks = await fetch_jwks_for_ticket_service(settings)
        
        if not jwks or not jwks.get("keys"):
            logger.error("JWKS not found or no keys in JWKS.", extra={"jwks_response": jwks})
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not retrieve valid JWKS for token validation in TicketService.")

        try:
            unverified_header = jwt.get_unverified_header(token)
            token_kid = unverified_header.get("kid")
            if not token_kid:
                raise JWTError("Token header missing 'kid'")
            
            rsa_key = next((key for key in jwks["keys"] if key.get("kid") == token_kid), None)
            
            if not rsa_key:
                raise JWTError("TicketService: Unable to find appropriate key in JWKS matching token's kid")

            payload = jwt.decode(
                token, 
                rsa_key, 
                algorithms=["RS256"], 
                issuer=settings.keycloak.issuer_uri, 
                audience=settings.keycloak.audience
            )
            logger.debug(f"Token successfully decoded. Payload 'sub': {payload.get('sub')}")

            raw_groups = payload.get("groups", [])
            cleaned_groups = [g.lstrip('/') for g in raw_groups if isinstance(g, str)]
            payload["tenant_groups"] = ["/" + g for g in cleaned_groups]
            
            return payload

        except JWTError as e:
            logger.warning(f"JWT validation error: {e}", exc_info=True)
            return None
        except Exception:
            logger.exception("Unexpected error during token decoding.")
            return None


async def get_current_user_payload(
    token: str = Depends(oauth2_scheme), 
    settings: Settings = Depends(get_settings)
) -> Dict[str, Any]:
    payload = await AuthHandlerTicketService.decode_token(token, settings)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="Geçersiz kimlik bilgileri veya token doğrulanamadı",
            headers={"WWW-Authenticate": "Bearer"}
        )
    return payload
