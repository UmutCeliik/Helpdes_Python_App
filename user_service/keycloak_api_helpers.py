# user_service/keycloak_api_helpers.py
import httpx
import uuid
from typing import Optional, Dict, Any
from datetime import datetime, timedelta

from .config import Settings # user_service'in kendi config'ini kullanacak

_user_service_admin_token_cache: Dict[str, Any] = { # Cache adını değiştirdim
    "token": None,
    "expires_at": datetime.utcnow()
}

async def get_admin_api_token(settings: Settings) -> Optional[str]: # Fonksiyon adını genel yaptım
    """Keycloak Admin API için (user_service adına) token alır."""
    global _user_service_admin_token_cache

    # Cache kontrolü
    if _user_service_admin_token_cache["token"] and \
       _user_service_admin_token_cache["expires_at"] > datetime.utcnow() + timedelta(seconds=30):
        print("USER_SVC_KC_HELPER: Using cached admin token.")
        return _user_service_admin_token_cache["token"]

    if not all([settings.keycloak.admin_api_token_endpoint, 
                settings.keycloak.admin_client_id, 
                settings.keycloak.admin_client_secret]):
        print("HATA (USER_SVC_KC_HELPER): Admin API token endpoint, client ID veya secret yapılandırılmamış.")
        return None

    payload = {
        "grant_type": "client_credentials",
        "client_id": settings.keycloak.admin_client_id,
        "client_secret": settings.keycloak.admin_client_secret,
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    print(f"USER_SVC_KC_HELPER: Requesting new admin token from {settings.keycloak.admin_api_token_endpoint}")
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(settings.keycloak.admin_api_token_endpoint, data=payload, headers=headers)
            response.raise_for_status()
            token_data = response.json()

            access_token = token_data.get("access_token")
            expires_in = token_data.get("expires_in", 300)

            _user_service_admin_token_cache["token"] = access_token
            _user_service_admin_token_cache["expires_at"] = datetime.utcnow() + timedelta(seconds=expires_in)

            print("USER_SVC_KC_HELPER: New admin token obtained and cached.")
            return access_token
    except httpx.HTTPStatusError as e:
        print(f"HATA (USER_SVC_KC_HELPER): Admin token alırken HTTP hatası: {e.response.status_code} - {e.response.text}")
    except Exception as e:
        print(f"HATA (USER_SVC_KC_HELPER): Admin token alırken beklenmedik hata: {e}")

    _user_service_admin_token_cache["token"] = None
    return None

async def create_keycloak_group(group_name: str, settings: Settings) -> Optional[str]:
    """
    Keycloak'ta verilen isimle yeni bir ana grup (tenant) oluşturur.
    Başarılı olursa oluşturulan grubun ID'sini (UUID string) döndürür.
    """
    admin_token = await get_admin_api_token(settings)
    if not admin_token:
        print("HATA (USER_SVC_KC_HELPER): Grup oluşturmak için admin token alınamadı.")
        return None

    if not settings.keycloak.admin_api_realm_url:
        print("HATA (USER_SVC_KC_HELPER): admin_api_realm_url yapılandırılmamış.")
        return None

    # Keycloak'ta grupların başında / olması standarttır.
    # Eğer gelen group_name başında / yoksa ekleyebiliriz, ya da Keycloak'un kendi path oluşturma mekanizmasına bırakabiliriz.
    # Genellikle sadece 'name' göndermek yeterlidir, Keycloak path'i '/name' olarak oluşturur.
    group_payload = {
        "name": group_name 
        # "path": f"/{group_name}" # İsteğe bağlı, genellikle name'den türetilir
    }

    create_group_url = f"{settings.keycloak.admin_api_realm_url}/groups"
    headers = {
        "Authorization": f"Bearer {admin_token}",
        "Content-Type": "application/json"
    }

    print(f"USER_SVC_KC_HELPER: Creating Keycloak group '{group_name}' at {create_group_url}")
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(create_group_url, json=group_payload, headers=headers)

            # Grup oluşturma başarılı ise Keycloak 201 Created döner ve
            # Location header'ında yeni grubun URL'ini (ID'sini içerir) verir.
            if response.status_code == 201:
                location_header = response.headers.get("Location")
                if location_header:
                    # Location header örneği: .../groups/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
                    created_group_id = location_header.split("/")[-1]
                    print(f"USER_SVC_KC_HELPER: Keycloak group '{group_name}' created successfully. ID: {created_group_id}")
                    return created_group_id
                else:
                    # Location header yoksa, bu beklenmedik bir durum.
                    # Alternatif olarak, oluşturduktan sonra grupları isimle arayıp ID'yi bulabiliriz,
                    # ama bu ek bir API çağrısı olur. Şimdilik Location header'ına güvenelim.
                    print(f"HATA (USER_SVC_KC_HELPER): Grup '{group_name}' oluşturuldu (201) ancak Location header bulunamadı.")
                    return None # Veya hata fırlat
            else:
                # Diğer HTTP hatalarını yakala
                response.raise_for_status() # Bu, 4xx/5xx için HTTPStatusError fırlatır
                # Eğer raise_for_status sonrasında kod buraya gelirse, bu beklenmedik bir durumdur.
                print(f"HATA (USER_SVC_KC_HELPER): Grup '{group_name}' oluşturulamadı, beklenmedik durum. Status: {response.status_code}, Yanıt: {response.text[:200]}")
                return None

    except httpx.HTTPStatusError as e:
        # Grup zaten varsa Keycloak genellikle 409 Conflict döner.
        if e.response.status_code == 409:
             print(f"UYARI (USER_SVC_KC_HELPER): Keycloak group '{group_name}' zaten mevcut (409 Conflict). Yanıt: {e.response.text[:200]}")
             # Bu durumda mevcut grubun ID'sini bulup döndürmek gerekebilir, şimdilik None dönüyoruz.
             # Veya bu bir hata olarak kabul edilebilir.
             return "EXISTS" # Özel bir string ile grubun var olduğunu belirtelim
        else:
            print(f"HATA (USER_SVC_KC_HELPER): Keycloak group '{group_name}' oluşturulurken HTTP hatası: {e.response.status_code} - {e.response.text[:200]}")
    except Exception as e:
        print(f"HATA (USER_SVC_KC_HELPER): Keycloak group '{group_name}' oluşturulurken beklenmedik hata: {e}")

    return None