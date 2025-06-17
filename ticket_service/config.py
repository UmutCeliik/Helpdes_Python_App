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
    # Ortam değişkenlerinden gelen ayarlar
    issuer_uri: str
    jwks_uri: str
    audience: str
    admin_client_id: Optional[str] = None
    admin_client_secret: Optional[str] = None
    
    # Otomatik türetilecek URL'ler
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
    # --- YENİ EKLENEN ALAN ---
    # Bu alan, ticket_service'in user_service ile konuşması için gereklidir.
    user_service_url: str


# --- Ayarları Başlatma ve Zenginleştirme ---

# Uygulama genelinde kullanılacak tek bir 'settings' nesnesi oluşturuluyor.
# Tüm değerler, Kubernetes tarafından pod'a enjekte edilen ortam değişkenlerinden okunur.
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
        # --- DEĞİŞİKLİK BURADA ---
        # USER_SERVICE_URL ortam değişkenini okuyup settings nesnesine ekliyoruz.
        # Eğer bu değişken bulunamazsa, varsayılan olarak cluster içi servis adını kullanır.
        user_service_url=os.getenv("USER_SERVICE_URL", "http://user-service:80")
    )
except KeyError as e:
    # Eğer zorunlu bir ortam değişkeni ayarlanmamışsa, uygulama başlamadan hata verir.
    print(f"KRİTİK HATA: Zorunlu ortam değişkeni eksik: {e}")
    # Production ortamında bu, sistemin yanlış konfigürasyonla çalışmasını engeller.
    raise SystemExit(f"Configuration Error: Missing environment variable {e}") from e


# Keycloak Admin API URL'lerini issuer_uri'den otomatik olarak türet
if settings.keycloak.issuer_uri:
    try:
        base_keycloak_url = settings.keycloak.issuer_uri.split('/realms/')[0]
        realm_name = settings.keycloak.issuer_uri.split('/realms/')[-1]
        settings.keycloak.admin_api_realm_url = f"{base_keycloak_url}/admin/realms/{realm_name}"
        settings.keycloak.admin_api_token_endpoint = f"{settings.keycloak.issuer_uri}/protocol/openid-connect/token"
    except IndexError:
        print(f"HATA [Config - TicketService]: KEYCLOAK_ISSUER_URI formatı beklenmedik: {settings.keycloak.issuer_uri}")

# Vault'tan Dahili İletişim Sırrını Oku
if settings.vault.token and settings.vault.addr:
    try:
        # verify=False production için önerilmez, ancak internal CA'nız yoksa gereklidir.
        client = hvac.Client(url=settings.vault.addr, token=settings.vault.token, verify=False) 
        if client.is_authenticated():
            print("Vault ile başarıyla kimlik doğrulandı.")
            api_path = settings.vault.internal_secret_path.replace("secret/data/", "")
            internal_secret_data = client.secrets.kv.v2.read_secret_version(path=api_path, mount_point="secret")
            
            secret_content = internal_secret_data.get('data', {}).get('data', {})
            fetched_secret = secret_content.get('ticket-user-service-secret')
            
            if fetched_secret:
                settings.internal_service_secret = fetched_secret
                print("Dahili servis sırrı Vault'tan başarıyla yüklendi.")
            else:
                 print(f"UYARI: Vault path '{settings.vault.internal_secret_path}' içinde 'ticket-user-service-secret' anahtarı bulunamadı.")
        else:
            print("HATA: Vault token'ı geçerli değil veya kimlik doğrulanamadı.")
    except Exception as e:
        print(f"HATA: Vault'a bağlanırken veya sır okunurken hata oluştu: {e}")
else:
    print("UYARI: Vault adresi veya token'ı yapılandırılmamış. Dahili servis sırrı okunamayacak.")

# Başlangıçta ayarları yazdır (Hata ayıklama için)
print("-" * 50)
print("Ticket Service - Konfigürasyon Yüklendi")
print(f"  Veritabanı URL'si Yüklendi: {'Evet' if settings.database.url else 'Hayır'}")
print(f"  Keycloak Issuer: {settings.keycloak.issuer_uri}")
# --- DEĞİŞİKLİK BURADA ---
# Yeni eklenen ayarı loglara yazdırıyoruz.
print(f"  User Service URL: {settings.user_service_url}")
print(f"  Vault Adresi: {settings.vault.addr}")
print(f"  Vault Token'ı Yüklendi: {'Evet' if settings.vault.token else 'Hayır'}")
print(f"  Dahili Sır Yüklendi: {'Evet' if settings.internal_service_secret else 'Hayır'}")
print("-" * 50)


# Uygulamanın diğer kısımlarında bu fonksiyon aracılığıyla ayarlara erişilecek.
def get_settings():
    """Tüm uygulama için konfigürasyon ayarlarını döndürür."""
    return settings
