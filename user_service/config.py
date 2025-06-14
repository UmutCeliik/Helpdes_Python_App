# user_service/config.py
"""
User Servisi için konfigürasyon ayarları.

Bu modül, Pydantic kullanarak ortam değişkenlerinden veya yerel geliştirme için
servis kök dizinindeki `.env` dosyasından uygulama ayarlarını yükler.
Bu yapı, hem yerel geliştirme (docker-compose) hem de production (Kubernetes)
ortamlarında değişiklik yapmadan çalışmayı sağlar.
"""
import os
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from pathlib import Path
from typing import Optional
import hvac

# --- .env Dosyasını Yükleme ---
# Yalnızca bu servisin kendi dizinindeki .env dosyasını yüklemeye çalışır.
# Eğer dosya yoksa (örneğin Kubernetes ortamında), sorun olmaz çünkü ayarlar
# doğrudan ortam değişkenlerinden okunur.
dotenv_path = Path(__file__).parent / '.env'
if dotenv_path.exists():
    load_dotenv(dotenv_path=dotenv_path)
    print(f"[Config - UserService] Local .env file loaded from: {dotenv_path}")

# --- Pydantic Ayar Modelleri ---

class DatabaseSettings(BaseModel):
    """Veritabanı bağlantı ayarları."""
    url: str = Field(default=os.getenv("DATABASE_URL", ""), description="PostgreSQL bağlantı adresi")

class KeycloakSettings(BaseModel):
    """Keycloak ile ilgili tüm ayarlar."""
    # Gelen kullanıcı token'larını doğrulamak için standart OIDC ayarları
    issuer_uri: str = Field(default=os.getenv("KEYCLOAK_ISSUER_URI", ""), description="Keycloak realm issuer URI")
    jwks_uri: str = Field(default=os.getenv("KEYCLOAK_JWKS_URI", ""), description="Keycloak JWKS URI")
    audience: str = Field(default=os.getenv("KEYCLOAK_TOKEN_AUDIENCE", "helpdesk-frontend"), description="Token'ın hedeflendiği kitle")
    
    # Keycloak Admin API istemcisi için ayarlar (servis hesabı)
    admin_client_id: Optional[str] = Field(default=os.getenv("KEYCLOAK_ADMIN_CLIENT_ID"), description="Admin API için client ID")
    admin_client_secret: Optional[str] = Field(default=os.getenv("KEYCLOAK_ADMIN_CLIENT_SECRET"), description="Admin API için client secret")
    
    # Admin API etkileşimi için URL'ler (issuer_uri'den otomatik türetilir)
    admin_api_realm_url: Optional[str] = None 
    admin_api_token_endpoint: Optional[str] = None

class VaultSettings(BaseModel):
    """HashiCorp Vault ile ilgili ayarlar."""
    addr: str = Field(default=os.getenv("VAULT_ADDR", "https://vault.cloudpro.com.tr"), description="Vault sunucu adresi")
    token: Optional[str] = Field(default=os.getenv("VAULT_TOKEN"), description="Vault token'ı")
    internal_secret_path: str = Field(default=os.getenv("VAULT_INTERNAL_SECRET_PATH", "secret/data/helpdesk/internal-communication"), description="Servisler arası iletişim sırrının Vault'taki yolu")

class Settings(BaseModel):
    """Tüm uygulama ayarlarını birleştiren ana model."""
    database: DatabaseSettings = DatabaseSettings()
    keycloak: KeycloakSettings = KeycloakSettings()
    vault: VaultSettings = VaultSettings()
    internal_service_secret: Optional[str] = None

# --- Ayarları Başlat ve Zenginleştir ---

settings = Settings()

# Keycloak Admin API URL'lerini issuer_uri'den otomatik olarak türet
if settings.keycloak.issuer_uri:
    try:
        base_keycloak_url = settings.keycloak.issuer_uri.split('/realms/')[0]
        settings.keycloak.admin_api_realm_url = f"{base_keycloak_url}/admin/realms/{settings.keycloak.issuer_uri.split('/realms/')[-1]}"
        settings.keycloak.admin_api_token_endpoint = f"{settings.keycloak.issuer_uri}/protocol/openid-connect/token"
    except IndexError:
        print(f"HATA [Config - UserService]: KEYCLOAK_ISSUER_URI formatı beklenmedik: {settings.keycloak.issuer_uri}")

# Vault'tan Dahili İletişim Sırrını Oku
if settings.vault.token and settings.vault.addr:
    try:
        # verify=False production için önerilmez, ancak internal CA'nız yoksa gereklidir.
        client = hvac.Client(url=settings.vault.addr, token=settings.vault.token, verify=False)
        if client.is_authenticated():
            api_path = settings.vault.internal_secret_path.replace("secret/data/", "")
            internal_secret_data = client.secrets.kv.v2.read_secret_version(path=api_path, mount_point="secret")
            
            secret_content = internal_secret_data.get('data', {}).get('data', {})
            # Not: Bu sır, ticket ve user servisleri arasında paylaşıldığı için anahtar adı aynı kalır.
            fetched_secret = secret_content.get('ticket-user-service-secret')
            
            if fetched_secret:
                settings.internal_service_secret = fetched_secret
            else:
                print(f"UYARI [Config - UserService]: Vault path '{settings.vault.internal_secret_path}' içinde 'ticket-user-service-secret' anahtarı bulunamadı.")
        else:
            print("HATA [Config - UserService]: Vault token'ı geçerli değil veya kimlik doğrulanamadı.")
    except Exception as e:
        print(f"HATA [Config - UserService]: Vault'a bağlanırken veya sır okunurken hata oluştu: {e}")
else:
    print("UYARI [Config - UserService]: Vault adresi veya token'ı yapılandırılmamış. Dahili servis sırrı okunamayacak.")

# --- Başlangıç Logları ve Kontroller ---

print("-" * 50)
print("User Service - Konfigürasyon Yüklendi")
print(f"  Veritabanı URL'si Yüklendi: {'Evet' if settings.database.url else 'Hayır'}")
print(f"  Keycloak Issuer: {settings.keycloak.issuer_uri}")
print(f"  Keycloak Admin Client ID Yüklendi: {'Evet' if settings.keycloak.admin_client_id else 'Hayır'}")
print(f"  Keycloak Admin Client Secret Yüklendi: {'Evet' if settings.keycloak.admin_client_secret else 'Hayır'}")
print(f"  Vault'tan Dahili Sır Yüklendi: {'Evet' if settings.internal_service_secret else 'Hayır'}")
print("-" * 50)

# Eksik ayarlar için uyarılar
if not all([settings.keycloak.issuer_uri, settings.keycloak.jwks_uri]):
    print("UYARI [Config - UserService]: Temel Keycloak ayarları (issuer_uri, jwks_uri) tam olarak yapılandırılmamış.")
if not all([settings.keycloak.admin_client_id, settings.keycloak.admin_client_secret]):
    print("UYARI [Config - UserService]: Keycloak Admin API istemci ID veya Sırrı yüklenemedi. Tenant oluşturma gibi işlemler başarısız olabilir.")

# Uygulamanın diğer kısımlarında kullanılacak fonksiyon
def get_settings():
    """Tüm uygulama için konfigürasyon ayarlarını döndürür."""
    return settings