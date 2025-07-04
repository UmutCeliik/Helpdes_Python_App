# user_service/config.py
"""
User Servisi için konfigürasyon ayarları.

Bu modül, Pydantic kullanarak ortam değişkenlerinden veya yerel geliştirme için
servis kök dizinindeki `.env` dosyasından uygulama ayarlarını yükler.
"""
import os
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from pathlib import Path
from typing import Optional
import hvac

# .env dosyasını yükle
dotenv_path = Path(__file__).parent / '.env'
if dotenv_path.exists():
    load_dotenv(dotenv_path=dotenv_path)

class DatabaseSettings(BaseModel):
    url: str = Field(default=os.getenv("DATABASE_URL", ""), description="PostgreSQL bağlantı adresi")

class KeycloakSettings(BaseModel):
    issuer_uri: str = Field(default=os.getenv("KEYCLOAK_ISSUER_URI", "https://keycloak.cloudpro.com.tr/realms/helpdesk-realm"))
    jwks_uri: str = Field(default=os.getenv("KEYCLOAK_JWKS_URI", "https://keycloak.cloudpro.com.tr/realms/helpdesk-realm/protocol/openid-connect/certs"))
    audience: str = Field(default=os.getenv("KEYCLOAK_TOKEN_AUDIENCE", "account"))
    admin_client_id: Optional[str] = Field(default=os.getenv("KEYCLOAK_ADMIN_CLIENT_ID"), description="Admin API için client ID")
    admin_client_secret: Optional[str] = Field(default=os.getenv("KEYCLOAK_ADMIN_CLIENT_SECRET"), description="Admin API için client secret")
    admin_api_realm_url: Optional[str] = None 
    admin_api_token_endpoint: Optional[str] = None

class VaultSettings(BaseModel):
    addr: str = Field(default=os.getenv("VAULT_ADDR", "https://vault.cloudpro.com.tr"), description="Vault sunucu adresi")
    token: Optional[str] = Field(default=os.getenv("VAULT_TOKEN"), description="Vault token'ı")
    internal_secret_path: str = Field(default=os.getenv("VAULT_INTERNAL_SECRET_PATH", "secret/data/helpdesk/internal-communication"), description="Servisler arası iletişim sırrının Vault'taki yolu")

class Settings(BaseModel):
    database: DatabaseSettings = DatabaseSettings()
    keycloak: KeycloakSettings = KeycloakSettings()
    vault: VaultSettings = VaultSettings()
    internal_service_secret: Optional[str] = None

settings = Settings()

# Keycloak Admin API URL'lerini issuer_uri'den otomatik olarak türet
if settings.keycloak.issuer_uri:
    try:
        base_keycloak_url = settings.keycloak.issuer_uri.split('/realms/')[0]
        settings.keycloak.admin_api_realm_url = f"{base_keycloak_url}/admin/realms/{settings.keycloak.issuer_uri.split('/realms/')[-1]}"
        settings.keycloak.admin_api_token_endpoint = f"{settings.keycloak.issuer_uri}/protocol/openid-connect/token"
    except IndexError:
        # Bu hata, uygulama başlangıcında main.py'deki logger tarafından yakalanacak.
        # Şimdilik bir print ile belirtmekte sakınca yok.
        print(f"CRITICAL CONFIG ERROR [UserService]: KEYCLOAK_ISSUER_URI format is unexpected: {settings.keycloak.issuer_uri}")

# Vault'tan Dahili İletişim Sırrını Oku
if settings.vault.token and settings.vault.addr:
    try:
        client = hvac.Client(url=settings.vault.addr, token=settings.vault.token, verify=False)
        if client.is_authenticated():
            api_path = settings.vault.internal_secret_path.replace("secret/data/", "")
            internal_secret_data = client.secrets.kv.v2.read_secret_version(path=api_path, mount_point="secret")
            
            secret_content = internal_secret_data.get('data', {}).get('data', {})
            fetched_secret = secret_content.get('ticket-user-service-secret')
            
            if fetched_secret:
                settings.internal_service_secret = fetched_secret
    except Exception as e:
        # Bu hata da main.py'de loglanacak.
        print(f"CRITICAL CONFIG ERROR [UserService]: Could not connect to Vault or read secrets: {e}")

def get_settings():
    """Tüm uygulama için konfigürasyon ayarlarını döndürür."""
    return settings
