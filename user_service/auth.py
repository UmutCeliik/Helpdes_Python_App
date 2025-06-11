# user_service/auth.py
from fastapi import Depends, HTTPException, status, Header
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from typing import Optional, Dict, Any
import httpx
from datetime import datetime, timedelta
from .config import get_settings, Settings
import secrets

_jwks_cache_user: Optional[Dict[str, Any]] = None # Cache değişken adını özelleştir
_jwks_cache_expiry_user: Optional[datetime] = None
JWKS_CACHE_TTL_SECONDS = 3600

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token_not_issued_here_either")
async def fetch_jwks_for_user_service(settings: Settings) -> Dict[str, Any]:
    global _jwks_cache_user, _jwks_cache_expiry_user # global değişkenleri kullan
    # ... (ticket_service/auth.py'deki fetch_jwks_for_ticket_service ile aynı mantık, sadece print loglarında "UserService" yazabilir) ...
    # Örnek olarak sadece print'i değiştiriyorum, geri kalanı aynı varsayıyorum:
    now = datetime.utcnow()
    if _jwks_cache_user and _jwks_cache_expiry_user and _jwks_cache_expiry_user > now:
        print("USER_SERVICE_AUTH: Using cached JWKS.")
        return _jwks_cache_user
    if not settings.keycloak.jwks_uri:
        # ... (hata yönetimi) ...
        print("ERROR (UserService): JWKS URI is not configured.")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="JWKS URI not configured in UserService")
    try:
        async with httpx.AsyncClient() as client:
            print(f"USER_SERVICE_AUTH: Fetching JWKS from {settings.keycloak.jwks_uri}")
            # ... (geri kalan fetch mantığı ticket_service/auth.py ile aynı) ...
            response = await client.get(settings.keycloak.jwks_uri)
            response.raise_for_status()
            new_jwks = response.json()
            _jwks_cache_user = new_jwks
            _jwks_cache_expiry_user = now + timedelta(seconds=JWKS_CACHE_TTL_SECONDS)
            print("USER_SERVICE_AUTH: Fetched and cached new JWKS.")
            return new_jwks
    except Exception as e:
        print(f"ERROR (UserService): Could not fetch JWKS: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Could not fetch JWKS from {settings.keycloak.jwks_uri}")


class AuthHandlerUserService: # Sınıf adını değiştir
    @staticmethod
    async def decode_token(token: str, settings: Settings) -> Optional[dict]:
        print(f"USER_SERVICE_AUTH: Attempting to decode token. Expected audience: '{settings.keycloak.audience}', Expected issuer: '{settings.keycloak.issuer_uri}'")
        
        if not settings.keycloak.issuer_uri or not settings.keycloak.audience:
            # ... (hata yönetimi aynı) ...
            print("ERROR (UserService): Keycloak issuer_uri or audience not configured.")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Auth config error in UserService")

        jwks = await fetch_jwks_for_user_service(settings)
        if not jwks or not jwks.get("keys"):
            # ... (hata yönetimi aynı) ...
            print(f"ERROR (UserService): JWKS not found or no keys in JWKS. JWKS: {jwks}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not retrieve valid JWKS for token validation in UserService.")
        
        try:
            unverified_header = jwt.get_unverified_header(token)
            token_kid = unverified_header.get("kid")
            # ... (RSA key bulma mantığı aynı) ...
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

            # --- YENİ EKLENEN KISIM ---
            # Token'dan 'groups' claim'ini de alıp payload'a ekleyelim.
            # Keycloak bazen grup yollarını başında çift slash ile verebilir (örn: "//Musteri_Alpha_AS")
            # Bunları temizleyip tek slash ile standart hale getirebiliriz.
            raw_groups = payload.get("groups", [])
            cleaned_groups = []
            if isinstance(raw_groups, list):
                for group_path in raw_groups:
                    if isinstance(group_path, str):
                        # Baştaki fazla slash'ları temizle (en fazla bir tane kalsın)
                        while group_path.startswith("//"):
                            group_path = group_path[1:]
                        if not group_path.startswith("/"): # Eğer hiç slash yoksa başına ekle (pek olası değil ama önlem)
                            group_path = "/" + group_path
                        cleaned_groups.append(group_path)
            
            payload["tenant_groups"] = cleaned_groups # Payload'a 'tenant_groups' olarak ekleyelim
            print(f"USER_SERVICE_AUTH: Tenant groups added to payload: {payload['tenant_groups']}")
            # --- YENİ EKLENEN KISIM SONU ---

            return payload

        except JWTError as e:
            print(f"ERROR (UserService): JWT validation error: {type(e).__name__} - {e}")
            return None
        except Exception as e:
            print(f"ERROR (UserService): Unexpected error during token decoding: {type(e).__name__} - {e}")
            return None



async def get_current_user_payload(token: str = Depends(oauth2_scheme), settings: Settings = Depends(get_settings)) -> Dict[str, Any]:
    payload = await AuthHandlerUserService.decode_token(token, settings) # Doğru handler'ı çağır
    if payload is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="UserService: Geçersiz kimlik bilgileri veya token", headers={"WWW-Authenticate": "Bearer"})
    return payload

async def verify_internal_secret(
    settings: Settings = Depends(get_settings),
    # Gelen istekteki 'X-Internal-Secret' başlığını oku
    # alias kullanarak header adını Python değişken adından farklı yapabiliriz
    x_internal_secret: Optional[str] = Header(None, alias="X-Internal-Secret")
) -> bool:
    """
    Servisler arası iletişim için 'X-Internal-Secret' başlığında gönderilen
    paylaşılan sırrı doğrulayan dependency fonksiyonu.
    """
    # Ayarlardan beklenen sırrı al
    expected_secret = settings.internal_service_secret
    print("UserService AUTH: Dahili sır doğrulanıyor...")

    # 1. Sunucu tarafında sırrın yapılandırılıp yapılandırılmadığını kontrol et
    if not expected_secret:
        print("HATA (UserService AUTH - Internal): Dahili servis sırrı ayarlarda yapılandırılmamış.")
        # Bu bir sunucu yapılandırma hatası olduğu için 500 döndürelim
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="İç sunucu hatası: Sır yapılandırması eksik."
        )

    # 2. İstek başlığında sırrın gönderilip gönderilmediğini kontrol et
    if x_internal_secret is None:
        print("UYARI (UserService AUTH - Internal): İstekte 'X-Internal-Secret' başlığı eksik.")
        # Eksik kimlik bilgisi için 401 veya yetkisiz erişim için 403 kullanılabilir. 401 daha uygun görünüyor.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Eksik dahili kimlik doğrulama başlığı."
            # headers={"WWW-Authenticate": "Internal"} # İsteğe bağlı
        )

    # 3. Zamanlama saldırılarına karşı güvenli karşılaştırma yap
    # secrets.compare_digest, sırların uzunlukları farklı olsa bile veya
    # içerikleri farklı olsa bile yaklaşık aynı sürede yanıt dönerek
    # saldırganın sırrı tahmin etmesini zorlaştırır.
    is_valid = secrets.compare_digest(expected_secret, x_internal_secret)

    if not is_valid:
        print("HATA (UserService AUTH - Internal): Geçersiz 'X-Internal-Secret' sağlandı.")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, # Geçersiz sır için 403 Forbidden
            detail="Geçersiz dahili kimlik doğrulama sırrı."
        )

    # Tüm kontrollerden geçerse
    print("UserService AUTH: Dahili sır başarıyla doğrulandı.")
    return True # Dependency başarılı olduysa True döndürmek yeterli