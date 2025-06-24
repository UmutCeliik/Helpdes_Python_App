# user_service/auth.py
from fastapi import Depends, HTTPException, status, Header
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from typing import Optional, Dict, Any
import httpx
from datetime import datetime, timedelta
from .config import get_settings, Settings
import secrets

_jwks_cache_user: Optional[Dict[str, Any]] = None
_jwks_cache_expiry_user: Optional[datetime] = None
JWKS_CACHE_TTL_SECONDS = 3600

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token_not_issued_here_either")
oauth23_scheme = OAuth2PasswordBearer(tokenUrl="auth/token_not_issued_here_either")
async def fetch_jwks_for_user_service(settings: Settings) -> Dict[str, Any]:
    """
    JWKS'leri Keycloak'tan çeker. SSL sertifika doğrulamasını atlar.
    """
    global _jwks_cache_user, _jwks_cache_expiry_user
    
    now = datetime.utcnow()
    if _jwks_cache_user and _jwks_cache_expiry_user and _jwks_cache_expiry_user > now:
        print("USER_SERVICE_AUTH: Using cached JWKS.")
        return _jwks_cache_user

    if not settings.keycloak.jwks_uri:
        print("ERROR (UserService): JWKS URI is not configured.")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="JWKS URI not configured in UserService")
    
    print(f"USER_SERVICE_AUTH: Fetching JWKS from {settings.keycloak.jwks_uri}")
    try:
        # ---- DEĞİŞİKLİK BURADA ----
        # SSL sertifika doğrulamasını atlamak için verify=False eklendi.
        async with httpx.AsyncClient(verify=False) as client:
            response = await client.get(settings.keycloak.jwks_uri)
            response.raise_for_status()
            new_jwks = response.json()
            _jwks_cache_user = new_jwks
            _jwks_cache_expiry_user = now + timedelta(seconds=JWKS_CACHE_TTL_SECONDS)
            print("USER_SERVICE_AUTH: Fetched and cached new JWKS.")
            return new_jwks
    except Exception as e:
        print(f"ERROR (UserService): Could not fetch JWKS: {e}")
        # Hata artık burada loglanıyor, 500 hatası fırlatılıyor.
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Could not fetch validation keys from authentication server: {e}")


class AuthHandlerUserService:
    @staticmethod
    async def decode_token(token: str, settings: Settings) -> Optional[dict]:
        print(f"USER_SERVICE_AUTH: Attempting to decode token. Expected audience: '{settings.keycloak.audience}', Expected issuer: '{settings.keycloak.issuer_uri}'")
        
        if not settings.keycloak.issuer_uri or not settings.keycloak.audience:
            print("ERROR (UserService): Keycloak issuer_uri or audience not configured.")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Auth config error in UserService")

        jwks = await fetch_jwks_for_user_service(settings) # Düzeltilmiş fetch_jwks fonksiyonunu çağırır.
        
        if not jwks or not jwks.get("keys"):
            print(f"ERROR (UserService): JWKS not found or no keys in JWKS. JWKS: {jwks}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not retrieve valid JWKS for token validation in UserService.")
        
        try:
            unverified_header = jwt.get_unverified_header(token)
            token_kid = unverified_header.get("kid")
            if not token_kid:
                raise JWTError("Token header missing 'kid'")
            
            rsa_key = {}
            for key_val in jwks["keys"]:
                if key_val.get("kid") == token_kid:
                    rsa_key = { "kty": key_val.get("kty"), "kid": key_val.get("kid"), "use": key_val.get("use"), "n": key_val.get("n"), "e": key_val.get("e")}
                    if "alg" in key_val: rsa_key["alg"] = key_val.get("alg")
                    break
            
            if not rsa_key:
                raise JWTError("UserService: Unable to find appropriate key in JWKS")

            payload = jwt.decode(
                token, 
                rsa_key, 
                algorithms=["RS256"], 
                issuer=settings.keycloak.issuer_uri, 
                audience=settings.keycloak.audience
            )
            print(f"USER_SERVICE_AUTH: Token successfully decoded. Payload 'sub': {payload.get('sub')}")

            raw_groups = payload.get("groups", [])
            cleaned_groups = []
            if isinstance(raw_groups, list):
                for group_path in raw_groups:
                    if isinstance(group_path, str):
                        while group_path.startswith("//"):
                            group_path = group_path[1:]
                        if not group_path.startswith("/"):
                            group_path = "/" + group_path
                        cleaned_groups.append(group_path)
            
            payload["tenant_groups"] = cleaned_groups
            print(f"USER_SERVICE_AUTH: Tenant groups added to payload: {payload['tenant_groups']}")
            return payload

        except JWTError as e:
            print(f"ERROR (UserService): JWT validation error: {type(e).__name__} - {e}")
            return None
        except Exception as e:
            print(f"HATA (UserService): Token doğrulama sırasında beklenmedik hata: {type(e).__name__} - {e}")
            return None


async def get_current_user_payload(token: str = Depends(oauth2_scheme), settings: Settings = Depends(get_settings)) -> Dict[str, Any]:
    payload = await AuthHandlerUserService.decode_token(token, settings)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="UserService: Geçersiz kimlik bilgileri veya token", headers={"WWW-Authenticate": "Bearer"})
    return payload

async def verify_internal_secret(
    settings: Settings = Depends(get_settings),
    x_internal_secret: Optional[str] = Header(None, alias="X-Internal-Secret")
) -> bool:
    """
    Servisler arası iletişim için paylaşılan sırrı doğrular.
    """
    expected_secret = settings.internal_service_secret
    print("UserService AUTH: Dahili sır doğrulanıyor...")

    if not expected_secret:
        print("HATA (UserService AUTH - Internal): Dahili servis sırrı ayarlarda yapılandırılmamış.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="İç sunucu hatası: Sır yapılandırması eksik."
        )

    if x_internal_secret is None:
        print("UYARI (UserService AUTH - Internal): İstekte 'X-Internal-Secret' başlığı eksik.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Eksik dahili kimlik doğrulama başlığı."
        )

    is_valid = secrets.compare_digest(expected_secret, x_internal_secret)

    if not is_valid:
        print("HATA (UserService AUTH - Internal): Geçersiz 'X-Internal-Secret' sağlandı.")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Geçersiz dahili kimlik doğrulama sırrı."
        )

    print("UserService AUTH: Dahili sır başarıyla doğrulandı.")
    return True