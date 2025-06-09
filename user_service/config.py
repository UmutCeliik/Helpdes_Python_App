# user_service/config.py
import os
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from pathlib import Path
from typing import Optional
import hvac

# Servise özel .env'yi yükle
dotenv_path = Path(__file__).parent / '.env'
load_dotenv(dotenv_path=dotenv_path)

# Ana .env'yi de yükle (Vault ve Admin Client ayarları burada olabilir)
main_dotenv_path = Path(__file__).parent.parent / '.env'
if main_dotenv_path.exists():
    print(f"UserService: Loading main .env file from {main_dotenv_path}")
    load_dotenv(dotenv_path=main_dotenv_path, override=False) # override=False önemli
else:
    print(f"UserService: Main .env file not found at {main_dotenv_path}")

class DatabaseSettings(BaseModel):
    url: str = Field(default=os.getenv("DATABASE_URL", ""))

class KeycloakSettings(BaseModel):
    issuer_uri: str = Field(default=os.getenv("KEYCLOAK_ISSUER_URI", ""))
    jwks_uri: str = Field(default=os.getenv("KEYCLOAK_JWKS_URI", ""))
    audience: str = Field(default=os.getenv("KEYCLOAK_TOKEN_AUDIENCE", "helpdesk-frontend"))

    # Settings for Keycloak Admin API client (service account)
    admin_client_id: Optional[str] = Field(default=os.getenv("KEYCLOAK_ADMIN_CLIENT_ID"))
    admin_client_secret: Optional[str] = Field(default=os.getenv("KEYCLOAK_ADMIN_CLIENT_SECRET"))
    admin_api_realm_url: Optional[str] = None 
    admin_api_token_endpoint: Optional[str] = None

class VaultSettings(BaseModel):
    addr: str = Field(default=os.getenv("VAULT_ADDR", "https://vault.cloudpro.com.tr"))
    token: Optional[str] = Field(default=os.getenv("VAULT_TOKEN"))
    internal_secret_path: str = Field(default=os.getenv("VAULT_INTERNAL_SECRET_PATH", "secret/data/helpdesk/internal-communication"))

class Settings(BaseModel):
    database: DatabaseSettings = DatabaseSettings()
    keycloak: KeycloakSettings = KeycloakSettings()
    vault: VaultSettings = VaultSettings()
    internal_service_secret: Optional[str] = None

settings = Settings()

# Derive Admin API URLs from issuer_uri if possible
if settings.keycloak.issuer_uri:
    base_keycloak_url = settings.keycloak.issuer_uri.split('/realms/')[0]
    realm_name = settings.keycloak.issuer_uri.split('/realms/')[-1]
    settings.keycloak.admin_api_realm_url = f"{base_keycloak_url}/admin/realms/{realm_name}"
    settings.keycloak.admin_api_token_endpoint = f"{settings.keycloak.issuer_uri}/protocol/openid-connect/token"
    print(f"UserService - Derived Keycloak Admin Realm URL: {settings.keycloak.admin_api_realm_url}")
    print(f"UserService - Derived Keycloak Admin Token Endpoint: {settings.keycloak.admin_api_token_endpoint}")
else:
    print("WARN (UserService): KEYCLOAK_ISSUER_URI not set, cannot derive Admin API URLs automatically.")

# Vault'tan Dahili İletişim Sırrını Oku (Bu kısım aynı kalıyor)
if settings.vault.token and settings.vault.addr:
    try:
        client = hvac.Client(url=settings.vault.addr, token=settings.vault.token, verify=False)
        if client.is_authenticated():
            print("UserService: Vault ile başarıyla kimlik doğrulandı (SSL doğrulaması kapalı).")
            api_path = settings.vault.internal_secret_path.replace("secret/data/", "")
            mount_point = "secret"
            internal_secret_data = client.secrets.kv.v2.read_secret_version(path=api_path, mount_point=mount_point)
            secret_content = internal_secret_data.get('data', {}).get('data', {})
            fetched_secret = secret_content.get('ticket-user-service-secret')
            if fetched_secret:
                settings.internal_service_secret = fetched_secret
                print("UserService: Dahili servis sırrı Vault'tan başarıyla yüklendi.")
            else:
                print(f"UYARI (UserService): Vault path '{settings.vault.internal_secret_path}' içinde 'ticket-user-service-secret' anahtarı bulunamadı.")
        else:
            print("HATA (UserService): Vault ile kimlik doğrulanamadı.")
    except Exception as e:
        print(f"HATA (UserService): Vault'a bağlanırken veya sır okunurken hata oluştu: {e}")
else:
    print("UYARI (UserService): Vault adresi veya token'ı yapılandırılmamış. Dahili servis sırrı Vault'tan okunamadı.")

# Ayar Logları
print(f"UserService - Keycloak Issuer: {settings.keycloak.issuer_uri}")
print(f"UserService - Keycloak JWKS URI: {settings.keycloak.jwks_uri}")
print(f"UserService - Expected Token Audience: {settings.keycloak.audience}")
print(f"UserService - Internal Service Secret Loaded: {'Yes' if settings.internal_service_secret else 'No'}")
print(f"UserService - Keycloak Admin Client ID Loaded: {'Yes' if settings.keycloak.admin_client_id else 'No'}")
print(f"UserService - Keycloak Admin Client Secret Loaded: {'Yes' if settings.keycloak.admin_client_secret else 'No'}")

# Uyarılar
if not all([settings.keycloak.issuer_uri, settings.keycloak.jwks_uri, settings.keycloak.audience]):
    print("UYARI: UserService - Temel Keycloak ayarları (.env içinde) tam olarak yapılandırılmamış.")
if not settings.internal_service_secret:
     print("UYARI: UserService - Dahili servis sırrı Vault'tan yüklenemedi.")
if not all([settings.keycloak.admin_client_id, settings.keycloak.admin_client_secret]):
    print("UYARI: UserService - Keycloak Admin API istemci ID veya Sırrı yüklenemedi. Tenant oluşturma başarısız olabilir.")

def get_settings():
    return settings