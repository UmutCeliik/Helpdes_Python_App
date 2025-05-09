# auth_service/config.py
import os
from dotenv import load_dotenv
import hvac
from pydantic import BaseModel, Field
from typing import Optional

load_dotenv() # .env dosyasındaki değişkenleri yükler

class KeycloakSettings(BaseModel):
    realm_name: str = Field(default=os.getenv("KEYCLOAK_REALM_NAME", "helpdesk-realm"))
    client_id: str = Field(default=os.getenv("KEYCLOAK_CLIENT_ID", "helpdesk-backend-api"))
    client_secret: Optional[str] = None
    issuer_uri: Optional[str] = None
    jwks_uri: Optional[str] = None
    token_endpoint: Optional[str] = None
    authorization_endpoint: Optional[str] = None
    userinfo_endpoint: Optional[str] = None

class VaultSettings(BaseModel):
    addr: str = Field(default=os.getenv("VAULT_ADDR", "https://vault.cloudpro.com.tr"))
    token: Optional[str] = Field(default=os.getenv("VAULT_TOKEN"))
    keycloak_client_secret_path: str = Field(default=os.getenv("VAULT_KEYCLOAK_CLIENT_SECRET_PATH", "secret/data/keycloak/helpdesk-realm/clients/helpdesk-backend-api/secret"))
    keycloak_oidc_config_path: str = Field(default=os.getenv("VAULT_KEYCLOAK_OIDC_CONFIG_PATH", "secret/data/keycloak/helpdesk-realm/config/oidc-provider"))

class Settings(BaseModel):
    keycloak: KeycloakSettings = KeycloakSettings()
    vault: VaultSettings = VaultSettings()
    frontend_redirect_uri: str = Field(default=os.getenv("FRONTEND_REDIRECT_URI", "http://localhost:5173/auth/callback"))

settings = Settings()

# Vault'tan gizli bilgileri yükle
if settings.vault.token and settings.vault.addr:
    try:
        client = hvac.Client(url=settings.vault.addr, token=settings.vault.token, verify=False) 
        if client.is_authenticated():
            print("Successfully authenticated with Vault (SSL verification disabled).")

            # Keycloak Client Secret'ı Vault'tan oku
            client_secret_data = client.secrets.kv.v2.read_secret_version(
                path=settings.vault.keycloak_client_secret_path.replace("secret/data/", ""), # API path'i farklı olabilir, kontrol edin
                mount_point="secret" # Eğer mount point'iniz farklıysa değiştirin
            )
            # Vault'taki secret yapınıza göre 'secret' veya 'client_secret' key'ini alın
            # Örnek olarak Vault path'i 'secret/data/keycloak/...' şeklinde ise, gelen data['data']['data']['secret_key_name'] şeklinde olabilir.
            # Verdiğiniz path `secret/keycloak/helpdesk-realm/clients/helpdesk-backend-api/secret` idi.
            # Bu durumda Vault CLI'da `vault kv get secret/keycloak/helpdesk-realm/clients/helpdesk-backend-api/secret` ile nasıl bir çıktı aldığınıza bakın.
            # Genellikle `data` altında bir `data` daha olur ve onun içinde key-value'lar bulunur.
            # `client.secrets.kv.v2.read_secret_version` genellikle şu yapıda döner: {'data': {'data': {'your_key': 'your_value'}}}
            # Vault'taki secret içeriğinde client secret'ın hangi key ile saklandığını bilmemiz gerekiyor. Örneğin 'clientSecret' veya sadece 'secret'.
            # Şimdilik 'secret' olduğunu varsayalım. Lütfen Vault'taki secret'ınızın içeriğini kontrol edin.
            # Örneğin, `secret/keycloak/helpdesk-realm/clients/helpdesk-backend-api/secret` path'inde `value` adında bir key ile saklanıyorsa:
            # settings.keycloak.client_secret = client_secret_data['data']['data'].get('value')
            # Eğer Vault'taki secret doğrudan { "secret": "YOUR_CLIENT_SECRET_VALUE" } ise:
            secret_content = client_secret_data['data']['data']
            settings.keycloak.client_secret = secret_content.get('client_credentials') # Vault'taki key adınız 'secret' ise
            if not settings.keycloak.client_secret:
                print(f"WARN: Could not find 'secret' key in Vault path {settings.vault.keycloak_client_secret_path}. Available keys: {secret_content.keys()}")

            # Keycloak OIDC Provider Config'i Vault'tan oku
            oidc_provider_data = client.secrets.kv.v2.read_secret_version(
                path=settings.vault.keycloak_oidc_config_path.replace("secret/data/", ""),
                mount_point="secret"
            )
            oidc_config = oidc_provider_data['data']['data']
            settings.keycloak.issuer_uri = oidc_config.get('ISSUER_URI')
            settings.keycloak.jwks_uri = oidc_config.get('JWKS_URI')

            # Diğer endpointleri issuer_uri'den türetebiliriz (OpenID Connect Discovery)
            # veya doğrudan Vault'a ekleyebiliriz. Şimdilik issuer_uri üzerinden gideriz.
            if settings.keycloak.issuer_uri:
                settings.keycloak.token_endpoint = f"{settings.keycloak.issuer_uri}/protocol/openid-connect/token"
                settings.keycloak.authorization_endpoint = f"{settings.keycloak.issuer_uri}/protocol/openid-connect/auth"
                settings.keycloak.userinfo_endpoint = f"{settings.keycloak.issuer_uri}/protocol/openid-connect/userinfo"

            print("Keycloak client secret and OIDC config loaded from Vault.")
        else:
            print("ERROR: Could not authenticate with Vault. Check VAULT_ADDR and VAULT_TOKEN.")
    except Exception as e:
        print(f"ERROR: Could not connect to Vault or read secrets: {e}")
        print("Please ensure Vault is running, unsealed, and VAULT_ADDR/VAULT_TOKEN are correct.")
        print("Falling back to default/empty Keycloak settings for client_secret, issuer_uri, jwks_uri.")

# Başlangıçta ayarları yazdır (hassas bilgileri yazdırmamaya dikkat et)
print(f"Keycloak Issuer: {settings.keycloak.issuer_uri}")
print(f"Keycloak Client ID: {settings.keycloak.client_id}")
print(f"Keycloak Client Secret Loaded: {'Yes' if settings.keycloak.client_secret else 'No'}")

# Bu fonksiyonu auth.py ve main.py'de kullanacağız.
def get_settings():
    return settings