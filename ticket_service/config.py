# ticket_service/config.py
import os
from pydantic import BaseModel, Field
from typing import Optional
import hvac

class DatabaseSettings(BaseModel):
    """Veritabanı bağlantı ayarları."""
    url: str

class KeycloakSettings(BaseModel):
    """Keycloak ile ilgili tüm ayarlar."""
    issuer_uri: str
    jwks_uri: str
    audience: str
    admin_client_id: Optional[str] = None
    admin_client_secret: Optional[str] = None
    admin_api_realm_url: Optional[str] = None 
    admin_api_token_endpoint: Optional[str] = None

class VaultSettings(BaseModel):
    """HashiCorp Vault ile ilgili ayarlar."""
    addr: str
    token: Optional[str] = None
    internal_secret_path: str = Field("secret/data/helpdesk/internal-communication")

class Settings(BaseModel):
    """Tüm uygulama ayarlarını birleştiren ana model."""
    database: DatabaseSettings
    keycloak: KeycloakSettings
    vault: VaultSettings
    internal_service_secret: Optional[str] = None
    user_service_url: str

try:
    settings = Settings(
        database=DatabaseSettings(url=os.environ["DATABASE_URL"]),
        keycloak=KeycloakSettings(
            issuer_uri=os.environ["KEYCLOAK_ISSUER_URI"],
            jwks_uri=os.environ["KEYCLOAK_JWKS_URI"],
            audience=os.environ["KEYCLOAK_TOKEN_AUDIENCE"],
            admin_client_id=os.getenv("KEYCLOAK_ADMIN_CLIENT_ID"),
            admin_client_secret=os.getenv("KEYCLOAK_ADMIN_CLIENT_SECRET"),
        ),
        vault=VaultSettings(
            addr=os.environ["VAULT_ADDR"],
            token=os.getenv("VAULT_TOKEN"),
            internal_secret_path=os.getenv("VAULT_INTERNAL_SECRET_PATH", "secret/data/helpdesk/internal-communication")
        ),
        user_service_url=os.getenv("USER_SERVICE_URL", "http://user-service:80")
    )
except KeyError as e:
    print(f"CRITICAL CONFIG ERROR [TicketService]: Missing environment variable {e}")
    raise SystemExit(f"Configuration Error: Missing environment variable {e}") from e

if settings.keycloak.issuer_uri:
    try:
        base_keycloak_url = settings.keycloak.issuer_uri.split('/realms/')[0]
        realm_name = settings.keycloak.issuer_uri.split('/realms/')[-1]
        settings.keycloak.admin_api_realm_url = f"{base_keycloak_url}/admin/realms/{realm_name}"
        settings.keycloak.admin_api_token_endpoint = f"{settings.keycloak.issuer_uri}/protocol/openid-connect/token"
    except IndexError:
        print(f"CRITICAL CONFIG ERROR [TicketService]: KEYCLOAK_ISSUER_URI format is unexpected: {settings.keycloak.issuer_uri}")

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
        print(f"CRITICAL CONFIG ERROR [TicketService]: Could not connect to Vault or read secrets: {e}")

def get_settings():
    """Tüm uygulama için konfigürasyon ayarlarını döndürür."""
    return settings
