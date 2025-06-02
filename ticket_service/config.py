# ticket_service/config.py
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
main_dotenv_path = Path(__file__).parent.parent / '.env'
if main_dotenv_path.exists():
    print(f"TicketService: Loading main .env file from {main_dotenv_path}")
    load_dotenv(dotenv_path=main_dotenv_path, override=False)
else:
     print(f"TicketService: Main .env file not found at {main_dotenv_path}")

class KeycloakSettings(BaseModel):
    issuer_uri: str = Field(default=os.getenv("KEYCLOAK_ISSUER_URI", ""))
    jwks_uri: str = Field(default=os.getenv("KEYCLOAK_JWKS_URI", ""))
    # Bu ticket_service'in API'ları için (örn: /tickets/) beklenecek audience
    audience: str = Field(default=os.getenv("KEYCLOAK_TOKEN_AUDIENCE", "account")) # Daha önceki loglarda 'account' olarak görünüyordu 

class VaultSettings(BaseModel): # Vault ayarları için sınıf
    addr: str = Field(default=os.getenv("VAULT_ADDR", "https://vault.cloudpro.com.tr"))
    token: Optional[str] = Field(default=os.getenv("VAULT_TOKEN"))
    # Vault'taki path
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
        client = hvac.Client(url=settings.vault.addr, token=settings.vault.token, verify=False)
        if client.is_authenticated():
            print("TicketService: Vault ile başarıyla kimlik doğrulandı (SSL doğrulaması kapalı).") # Log prefix'i değişti

            api_path = settings.vault.internal_secret_path.replace("secret/data/", "")
            mount_point = "secret"
            print(f"TicketService: Vault'tan dahili sır okunuyor: Path='{api_path}', Mount Point='{mount_point}'") # Log prefix'i değişti

            internal_secret_data = client.secrets.kv.v2.read_secret_version(
                path=api_path,
                mount_point=mount_point
            )

            secret_content = internal_secret_data.get('data', {}).get('data', {})
            fetched_secret = secret_content.get('ticket-user-service-secret')

            if fetched_secret:
                settings.internal_service_secret = fetched_secret
                print("TicketService: Dahili servis sırrı Vault'tan başarıyla yüklendi.") # Log prefix'i değişti
            else:
                available_keys = list(secret_content.keys())
                print(f"UYARI (TicketService): Vault path '{settings.vault.internal_secret_path}' içinde 'ticket-user-service-secret' anahtarı bulunamadı. Bulunan anahtarlar: {available_keys}") # Log prefix'i değişti

        else:
            print("HATA (TicketService): Vault ile kimlik doğrulanamadı. VAULT_ADDR ve VAULT_TOKEN ayarlarını kontrol edin.") # Log prefix'i değişti
    except Exception as e:
        print(f"HATA (TicketService): Vault'a bağlanırken veya sır okunurken hata oluştu: {e}") # Log prefix'i değişti
        print("TicketService: Vault sunucusunun çalıştığından, mührünün açık olduğundan ve adres/token bilgilerinin doğru olduğundan emin olun.") # Log prefix'i değişti
else:
    print("UYARI (TicketService): Vault adresi veya token'ı yapılandırılmamış. Dahili servis sırrı Vault'tan okunamadı.") # Log prefix'i değişti


# --- Mevcut Keycloak Ayar Logları ---
print(f"TicketService - Keycloak Issuer: {settings.keycloak.issuer_uri}")
print(f"TicketService - Keycloak JWKS URI: {settings.keycloak.jwks_uri}")
print(f"TicketService - Expected Token Audience: {settings.keycloak.audience}")

# --- Yeni Eklenen Sır Durumu Logu ---
print(f"TicketService - Internal Service Secret Loaded: {'Yes' if settings.internal_service_secret else 'No'}") # Log prefix'i değişti

# --- Uyarılar ---
if not settings.keycloak.issuer_uri or not settings.keycloak.jwks_uri or not settings.keycloak.audience:
    print("UYARI: TicketService - Keycloak ayarları (.env içinde) tam olarak yapılandırılmamış. Token doğrulaması başarısız olabilir.") # Log prefix'i değişti
if not settings.internal_service_secret:
     print("UYARI: TicketService - Dahili servis sırrı Vault'tan yüklenemedi. User service'e yapılan çağrı doğrulaması başarısız olabilir.") # Log prefix'i değişti

def get_settings():
    # Bu fonksiyon, güncellenmiş 'settings' nesnesini döndürür
    return settings