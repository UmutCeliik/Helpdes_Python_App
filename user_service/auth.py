# user_service/auth.py
import logging
import secrets
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import httpx
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt

from .config import Settings, get_settings

# Logger'ı al
logger = logging.getLogger("user_service")

_jwks_cache_user: Optional[Dict[str, Any]] = None
_jwks_cache_expiry_user: Optional[datetime] = None
JWKS_CACHE_TTL_SECONDS = 3600

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token_not_issued_here_either")

async def fetch_jwks_for_user_service(settings: Settings) -> Dict[str, Any]:
    """JWKS'leri Keycloak'tan çeker. SSL doğrulamasını atlar."""
    global _jwks_cache_user, _jwks_cache_expiry_user
    
    now = datetime.utcnow()
    if _jwks_cache_user and _jwks_cache_expiry_user and _jwks_cache_expiry_user > now:
        logger.debug("Using cached JWKS for user_service.")
        return _jwks_cache_user

    if not settings.keycloak.jwks_uri:
        logger.error("JWKS URI is not configured in user_service.")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="JWKS URI not configured in UserService")
    
    logger.info(f"Fetching JWKS from {settings.keycloak.jwks_uri}")
    try:
        async with httpx.AsyncClient(verify=False) as client:
            response = await client.get(settings.keycloak.jwks_uri)
            response.raise_for_status()
            new_jwks = response.json()
            _jwks_cache_user = new_jwks
            _jwks_cache_expiry_user = now + timedelta(seconds=JWKS_CACHE_TTL_SECONDS)
            logger.info("Fetched and cached new JWKS for user_service.")
            return new_jwks
    except Exception as e:
        logger.exception("Could not fetch JWKS for user_service.")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Could not fetch validation keys from authentication server: {e}")

class AuthHandlerUserService:
    @staticmethod
    async def decode_token(token: str, settings: Settings) -> Optional[dict]:
        logger.debug(f"Attempting to decode token. Expected audience: '{settings.keycloak.audience}', Expected issuer: '{settings.keycloak.issuer_uri}'")
        
        if not settings.keycloak.issuer_uri or not settings.keycloak.audience:
            logger.error("Keycloak issuer_uri or audience not configured in user_service settings.")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Auth config error in UserService")

        jwks = await fetch_jwks_for_user_service(settings)
        
        if not jwks or not jwks.get("keys"):
            logger.error(f"JWKS not found or no keys in JWKS.", extra={"jwks_response": jwks})
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not retrieve valid JWKS for token validation in UserService.")
        
        try:
            unverified_header = jwt.get_unverified_header(token)
            token_kid = unverified_header.get("kid")
            if not token_kid:
                raise JWTError("Token header missing 'kid'")
            
            rsa_key = next((key for key in jwks["keys"] if key.get("kid") == token_kid), None)
            
            if not rsa_key:
                raise JWTError("UserService: Unable to find appropriate key in JWKS")

            payload = jwt.decode(
                token, 
                rsa_key, 
                algorithms=["RS256"], 
                issuer=settings.keycloak.issuer_uri, 
                audience=settings.keycloak.audience
            )
            logger.debug(f"Token successfully decoded for user_id: {payload.get('sub')}")

            raw_groups = payload.get("groups", [])
            cleaned_groups = [g.lstrip('/') for g in raw_groups if isinstance(g, str)]
            payload["tenant_groups"] = ["/" + g for g in cleaned_groups]
            
            return payload

        except JWTError as e:
            logger.warning(f"JWT validation error: {e}", exc_info=True)
            return None
        except Exception as e:
            logger.exception("Unexpected error during token decoding in user_service.")
            return None

async def get_current_user_payload(token: str = Depends(oauth2_scheme), settings: Settings = Depends(get_settings)) -> Dict[str, Any]:
    payload = await AuthHandlerUserService.decode_token(token, settings)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="UserService: Invalid or expired token", headers={"WWW-Authenticate": "Bearer"})
    return payload

async def verify_internal_secret(
    settings: Settings = Depends(get_settings),
    x_internal_secret: Optional[str] = Header(None, alias="X-Internal-Secret")
) -> bool:
    expected_secret = settings.internal_service_secret
    logger.debug("Verifying internal secret for inter-service communication.")

    if not expected_secret:
        logger.error("Internal service secret is not configured in settings.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error: Secret configuration is missing."
        )

    if x_internal_secret is None:
        logger.warning("Request is missing 'X-Internal-Secret' header.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing internal authentication header."
        )

    if not secrets.compare_digest(expected_secret, x_internal_secret):
        logger.error("Invalid 'X-Internal-Secret' provided.")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid internal authentication secret."
        )

    logger.debug("Internal secret verified successfully.")
    return True
