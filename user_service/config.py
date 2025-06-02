# user_service/config.py
import os
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from pathlib import Path
from typing import Optional
import hvac # hvac import edildi

# Servise özel .env'yi yükle (Keycloak ayarları için)
dotenv_path = Path(__file__).parent / '.env'
load_dotenv(dotenv_path=dotenv_path)

# Ana .env'yi de yükle (Vault ayarları genellikle burada)
# Not: override=False, eğer aynı değişken her iki yerde de varsa, servise özel olanın kalmasını sağlar.
main_dotenv_path = Path(__file__).parent.parent / '.env'
if main_dotenv_path.exists():
    print(f"UserService: Loading main .env file from {main_dotenv_path}")
    load_dotenv(dotenv_path=main_dotenv_path, override=False)
else:
    print(f"UserService: Main .env file not found at {main_dotenv_path}")


class KeycloakSettings(BaseModel):
    issuer_uri: str = Field(default=os.getenv("KEYCLOAK_ISSUER_URI", ""))
    jwks_uri: str = Field(default=os.getenv("KEYCLOAK_JWKS_URI", ""))
    # Bu user_service'in kendi API'ları için (örn: /users/me) beklenecek audience
    audience: str = Field(default=os.getenv("KEYCLOAK_TOKEN_AUDIENCE", "helpdesk-frontend")) # Veya başka bir audience belirleyebilirsiniz

class VaultSettings(BaseModel): # Vault ayarları için sınıf
    addr: str = Field(default=os.getenv("VAULT_ADDR", "https://vault.cloudpro.com.tr"))
    token: Optional[str] = Field(default=os.getenv("VAULT_TOKEN"))
    # Vault'taki path (UI'da gördüğünüz path, genellikle API için '/data/' eklenir KV v2'de)
    internal_secret_path: str = Field(default=os.getenv("VAULT_INTERNAL_SECRET_PATH", "secret/data/helpdesk/internal-communication"))

class Settings(BaseModel):
    keycloak: KeycloakSettings = KeycloakSettings()
    vault: VaultSettings = VaultSettings() # Vault ayarları eklendi
    internal_service_secret: Optional[str] = None # Okunan sırrı saklamak için alan

settings = Settings()

# --- Vault'tan Dahili İletişim Sırrını Oku ---
if settings.vault.token and settings.vault.addr:
    try:
        # Lokal Vault için SSL doğrulamasını kapatıyoruz (verify=False) 
        # Production için sertifika yönetimi yapıp True yapın.
        client = hvac.Client(url=settings.vault.addr, token=settings.vault.token, verify=False)
        if client.is_authenticated():
            print("UserService: Vault ile başarıyla kimlik doğrulandı (SSL doğrulaması kapalı).")

            # Vault KV v2 API path'i genellikle UI'da gösterilen path'in önüne 'data/' eklenmiş halidir.
            # read_secret_version path parametresi ise 'data/' olmadan kullanılır.
            api_path = settings.vault.internal_secret_path.replace("secret/data/", "")
            mount_point = "secret" # KV v2 engine'inizin mount point'i
            print(f"UserService: Vault'tan dahili sır okunuyor: Path='{api_path}', Mount Point='{mount_point}'")

            internal_secret_data = client.secrets.kv.v2.read_secret_version(
                path=api_path,
                mount_point=mount_point
            )

            # Sır verisi genellikle {'data': {'data': {'key': 'value'}}} yapısındadır
            secret_content = internal_secret_data.get('data', {}).get('data', {})
            fetched_secret = secret_content.get('ticket-user-service-secret') # UI'da belirlediğimiz anahtar

            if fetched_secret:
                settings.internal_service_secret = fetched_secret
                print("UserService: Dahili servis sırrı Vault'tan başarıyla yüklendi.")
            else:
                # Anahtar bulunamazsa uyarı ver
                available_keys = list(secret_content.keys())
                print(f"UYARI (UserService): Vault path '{settings.vault.internal_secret_path}' içinde 'ticket-user-service-secret' anahtarı bulunamadı. Bulunan anahtarlar: {available_keys}")

        else:
            # Vault token geçersizse veya başka bir sorun varsa
            print("HATA (UserService): Vault ile kimlik doğrulanamadı. VAULT_ADDR ve VAULT_TOKEN ayarlarını kontrol edin.")
    except Exception as e:
        # Vault'a bağlanamazsa veya başka bir hata olursa
        print(f"HATA (UserService): Vault'a bağlanırken veya sır okunurken hata oluştu: {e}")
        print("UserService: Vault sunucusunun çalıştığından, mührünün açık olduğundan ve adres/token bilgilerinin doğru olduğundan emin olun.")
else:
    # Vault token veya adresi konfigürasyonda yoksa
    print("UYARI (UserService): Vault adresi veya token'ı yapılandırılmamış. Dahili servis sırrı Vault'tan okunamadı.")

# --- Mevcut Keycloak Ayar Logları ---
print(f"UserService - Keycloak Issuer: {settings.keycloak.issuer_uri}")
print(f"UserService - Keycloak JWKS URI: {settings.keycloak.jwks_uri}")
print(f"UserService - Expected Token Audience: {settings.keycloak.audience}")

# --- Yeni Eklenen Sır Durumu Logu ---
print(f"UserService - Internal Service Secret Loaded: {'Yes' if settings.internal_service_secret else 'No'}")

# --- Uyarılar ---
if not settings.keycloak.issuer_uri or not settings.keycloak.jwks_uri or not settings.keycloak.audience:
    print("UYARI: UserService - Keycloak ayarları (.env içinde) tam olarak yapılandırılmamış. Token doğrulaması başarısız olabilir.")
if not settings.internal_service_secret:
     print("UYARI: UserService - Dahili servis sırrı Vault'tan yüklenemedi. Servisler arası çağrı doğrulaması başarısız olabilir.")

def get_settings():
    # Bu fonksiyon, güncellenmiş 'settings' nesnesini döndürür
    return settings