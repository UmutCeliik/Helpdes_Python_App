# ticket_service/config.py
import os
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from pathlib import Path

# .env dosyasının config.py ile aynı dizinde olduğunu varsayarak yükle
dotenv_path = Path(__file__).parent / '.env'
load_dotenv(dotenv_path=dotenv_path)

class KeycloakSettings(BaseModel):
    issuer_uri: str = Field(default=os.getenv("KEYCLOAK_ISSUER_URI", ""))
    jwks_uri: str = Field(default=os.getenv("KEYCLOAK_JWKS_URI", ""))
    audience: str = Field(default=os.getenv("KEYCLOAK_TOKEN_AUDIENCE", "helpdesk-frontend")) # Varsayılanı da güncelledim

class Settings(BaseModel):
    keycloak: KeycloakSettings = KeycloakSettings()

settings = Settings()

print(f"TicketService - Keycloak Issuer: {settings.keycloak.issuer_uri}")
print(f"TicketService - Keycloak JWKS URI: {settings.keycloak.jwks_uri}")
print(f"TicketService - Expected Token Audience: {settings.keycloak.audience}")

if not settings.keycloak.issuer_uri or not settings.keycloak.jwks_uri or not settings.keycloak.audience:
    print("WARNING: TicketService - Keycloak Issuer URI, JWKS URI, or Audience is not configured in .env. Token validation may fail.")

def get_settings():
    return settings