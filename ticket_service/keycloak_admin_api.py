# ticket_service/keycloak_admin_api.py
import httpx
import uuid
from typing import Optional, Dict, Any, List # List eklendi
from datetime import datetime, timedelta

from .config import Settings # Ayarları import et

# Basit in-memory cache'ler
_admin_token_cache: Dict[str, Any] = {
    "token": None,
    "expires_at": datetime.utcnow()
}
_group_id_cache: Dict[str, uuid.UUID] = {} # path -> UUID eşlemesi

async def get_keycloak_admin_token(settings: Settings) -> Optional[str]:
    """
    Keycloak Admin API'si için client credentials grant type ile bir access token alır.
    Token'ı basit bir şekilde cache'ler.
    """
    global _admin_token_cache

    if _admin_token_cache["token"] and _admin_token_cache["expires_at"] > datetime.utcnow() + timedelta(seconds=30):
        print("KC_ADMIN_API: Using cached admin token.")
        return _admin_token_cache["token"]

    if not all([settings.keycloak.admin_api_token_endpoint, settings.keycloak.admin_client_id, settings.keycloak.admin_client_secret]):
        print("HATA (KC_ADMIN_API): Admin API token endpoint, client ID veya secret yapılandırılmamış.")
        return None

    payload = {
        "grant_type": "client_credentials",
        "client_id": settings.keycloak.admin_client_id,
        "client_secret": settings.keycloak.admin_client_secret,
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    print(f"KC_ADMIN_API: Requesting new admin token from {settings.keycloak.admin_api_token_endpoint}")
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(settings.keycloak.admin_api_token_endpoint, data=payload, headers=headers)
            response.raise_for_status()
            token_data = response.json()
            
            access_token = token_data.get("access_token")
            expires_in = token_data.get("expires_in", 300) 

            _admin_token_cache["token"] = access_token
            _admin_token_cache["expires_at"] = datetime.utcnow() + timedelta(seconds=expires_in)
            
            print("KC_ADMIN_API: New admin token obtained and cached.")
            return access_token
    except httpx.HTTPStatusError as e:
        print(f"HATA (KC_ADMIN_API): Admin token alırken HTTP hatası: {e.response.status_code} - {e.response.text}")
    except Exception as e:
        print(f"HATA (KC_ADMIN_API): Admin token alırken beklenmedik hata: {e}")
    
    _admin_token_cache["token"] = None 
    return None


async def get_group_id_from_path(group_path_from_token: str, settings: Settings) -> Optional[uuid.UUID]:
    """
    Verilen grup yolundan (örn: "/Musteri_Beta_Ltd" veya "//Musteri_Beta_Ltd") grup adını çıkararak
    Keycloak Admin API'sinden grubun UUID'sini alır. Sonuçları cache'ler.
    Bu fonksiyon grup adına göre arama yapar ve bulunan grubun path'ini token'daki path ile doğrular.
    """
    global _group_id_cache

    # Token'dan gelen grup yolunu normalize et (başında tek bir '/' olacak şekilde)
    # örn: "//Musteri_Beta_Ltd" -> "/Musteri_Beta_Ltd"
    # örn: "Musteri_Beta_Ltd" -> "/Musteri_Beta_Ltd" (eğer başta / yoksa ekler)
    normalized_token_path = group_path_from_token
    if normalized_token_path:
        while normalized_token_path.startswith("//"):
            normalized_token_path = normalized_token_path[1:]
        if not normalized_token_path.startswith("/") and normalized_token_path: # Boş değilse ve / ile başlamıyorsa
            normalized_token_path = "/" + normalized_token_path
    
    # Arama için grup adını al (baştaki '/' olmadan)
    group_name_for_search = normalized_token_path.lstrip("/") if normalized_token_path else ""

    if not group_name_for_search:
        print(f"HATA (KC_ADMIN_API): Geçersiz grup yolu/adı sağlandı (işlem sonrası boş): '{group_path_from_token}' -> '{group_name_for_search}'")
        return None

    # Cache anahtarı olarak normalize edilmiş token path'ini kullanalım
    cache_key = normalized_token_path 
    if cache_key in _group_id_cache:
        print(f"KC_ADMIN_API: Using cached group ID for normalized path: {cache_key}")
        return _group_id_cache[cache_key]

    admin_token = await get_keycloak_admin_token(settings)
    if not admin_token:
        return None

    if not settings.keycloak.admin_api_realm_url:
        print("HATA (KC_ADMIN_API): admin_api_realm_url yapılandırılmamış.")
        return None
            
    lookup_url = f"{settings.keycloak.admin_api_realm_url}/groups?search={group_name_for_search}&exact=true&briefRepresentation=false"
    headers = {"Authorization": f"Bearer {admin_token}"}

    print(f"KC_ADMIN_API: Looking up group ID for name '{group_name_for_search}' (from token path '{group_path_from_token}') at {lookup_url}")
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(lookup_url, headers=headers)
            print(f"DEBUG (KC_ADMIN_API): Group search response status: {response.status_code}")
            # Yanıtın tamamını loglamak yerine bir kısmını loglayalım (çok uzun olabilir)
            response_text_preview = response.text[:500] if response.text else "No content"
            print(f"DEBUG (KC_ADMIN_API): Group search response text (preview): {response_text_preview}")
            response.raise_for_status()
            groups_list: List[Dict[str, Any]] = response.json()
            
            target_group_details: Optional[Dict[str, Any]] = None

            if groups_list and isinstance(groups_list, list):
                # exact=true ile arama yaptığımız için idealde 0 veya 1 sonuç bekleriz.
                # Eğer birden fazla sonuç dönerse, bu grup adlarının benzersiz olmadığı anlamına gelir (KÖTÜ).
                # Bu durumda, token'daki path ile eşleşeni bulmaya çalışırız.
                for group_data in groups_list:
                    retrieved_kc_path = group_data.get("path", "")
                    # Keycloak'tan gelen path'i de normalize edelim (başta tek / olsun)
                    normalized_retrieved_kc_path = retrieved_kc_path
                    if normalized_retrieved_kc_path:
                        while normalized_retrieved_kc_path.startswith("//"):
                            normalized_retrieved_kc_path = normalized_retrieved_kc_path[1:]
                        if not normalized_retrieved_kc_path.startswith("/") and normalized_retrieved_kc_path: # Boş değilse ve / ile başlamıyorsa
                            normalized_retrieved_kc_path = "/" + normalized_retrieved_kc_path
                    
                    if normalized_retrieved_kc_path == normalized_token_path:
                        target_group_details = group_data
                        print(f"KC_ADMIN_API: Matched group by path: Token Path='{normalized_token_path}', KC Path='{normalized_retrieved_kc_path}'")
                        break 
                
                if not target_group_details and len(groups_list) == 1:
                    # Eğer path tam eşleşmediyse ama sadece 1 sonuç döndüyse ve isim aynıysa, belki bu kabul edilebilir
                    # (Keycloak path'lerinde beklenmedik bir durum varsa diye bir uyarı logu ile).
                    # Ancak path'in tam eşleşmesi daha güvenli. Şimdilik path eşleşmesini zorunlu tutalım.
                    print(f"WARN (KC_ADMIN_API): Group name '{group_name_for_search}' found, but path mismatch. Token Path: '{normalized_token_path}', Found Paths: {[g.get('path') for g in groups_list]}")

            if target_group_details:
                group_id_str = target_group_details.get("id")
                if group_id_str:
                    try:
                        group_uuid = uuid.UUID(group_id_str)
                        _group_id_cache[cache_key] = group_uuid 
                        print(f"KC_ADMIN_API: Group ID '{group_uuid}' for path '{cache_key}' (name: '{group_name_for_search}') found and cached.")
                        return group_uuid
                    except ValueError:
                        print(f"HATA (KC_ADMIN_API): Alınan grup ID '{group_id_str}' geçerli bir UUID değil.")
                        return None # Hata durumunda None döndür
                else:
                    print(f"HATA (KC_ADMIN_API): Grup '{group_name_for_search}' (path: '{cache_key}') için yanıtta ID bulunamadı. Detay: {target_group_details}")
                    return None # Hata durumunda None döndür
            else: 
                print(f"HATA (KC_ADMIN_API): Grup adı '{group_name_for_search}' (path: '{cache_key}') ile arama sonucunda eşleşen/doğrulanan grup bulunamadı. Dönen gruplar: {groups_list}")
                return None # Hata durumunda None döndür

    except httpx.HTTPStatusError as e:
        print(f"HATA (KC_ADMIN_API): Grup ID'si alınırken HTTP hatası: {e.response.status_code} - {e.response.text[:200]}. URL: {lookup_url}")
    except Exception as e:
        print(f"HATA (KC_ADMIN_API): Grup ID'si alınırken beklenmedik hata: {type(e).__name__} - {e}. URL: {lookup_url}")
            
    return None # Fonksiyonun sonundaki genel fallback