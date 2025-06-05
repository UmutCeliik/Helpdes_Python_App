# user_service/keycloak_api_helpers.py
import httpx
import uuid
from typing import Optional, Dict, Any, List
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

async def create_keycloak_user(user_representation: Dict[str, Any], settings: Settings) -> Optional[str]:
    """
    Keycloak'ta verilen UserRepresentation ile yeni bir kullanıcı oluşturur.
    Başarılı olursa oluşturulan kullanıcının ID'sini (UUID string) döndürür.
    user_representation en az 'username', 'email', 'enabled' içermelidir.
    'firstName' ve 'lastName' de eklenebilir.
    """
    admin_token = await get_admin_api_token(settings)
    if not admin_token:
        print("HATA (USER_SVC_KC_HELPER): Kullanıcı oluşturmak için admin token alınamadı.")
        return None
    if not settings.keycloak.admin_api_realm_url:
        print("HATA (USER_SVC_KC_HELPER): admin_api_realm_url yapılandırılmamış (kullanıcı oluşturma).")
        return None

    create_user_url = f"{settings.keycloak.admin_api_realm_url}/users"
    headers = {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}

    # Keycloak'un beklediği temel alanlar: username, enabled. Email de genellikle istenir.
    # Gelen user_representation'da bu alanların olduğundan emin olun.
    # Örnek: user_representation = {
    # "username": "newuser@example.com", "email": "newuser@example.com",
    # "enabled": True, "firstName": "Yeni", "lastName": "Kullanıcı"
    # }
    print(f"USER_SVC_KC_HELPER: Creating Keycloak user with username '{user_representation.get('username')}' at {create_user_url}")
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(create_user_url, json=user_representation, headers=headers)
            
            if response.status_code == 201: # Başarılı kullanıcı oluşturma
                location_header = response.headers.get("Location")
                if location_header:
                    created_user_id = location_header.split("/")[-1]
                    print(f"USER_SVC_KC_HELPER: User '{user_representation.get('username')}' created successfully. ID: {created_user_id}")
                    return created_user_id
                else:
                    print(f"HATA (USER_SVC_KC_HELPER): User created (201) but Location header (for user ID) not found.")
                    # Bu durumda kullanıcı oluşturulmuş olabilir ama ID'sini alamadık.
                    # Alternatif olarak, kullanıcıyı email/username ile arayıp ID'yi bulabiliriz. Şimdilik None dönelim.
                    return None 
            elif response.status_code == 409: # Conflict - Kullanıcı zaten var (username veya email ile çakışma)
                print(f"HATA (USER_SVC_KC_HELPER): User '{user_representation.get('username')}' already exists (409 Conflict). Response: {response.text[:200]}")
                return "EXISTS" # Kullanıcının zaten var olduğunu belirtmek için özel bir değer
            else:
                response.raise_for_status() # Diğer 4xx/5xx hataları için exception fırlat
                print(f"HATA (USER_SVC_KC_HELPER): User creation failed with unexpected status {response.status_code}. Response: {response.text[:200]}")
                return None

    except httpx.HTTPStatusError as e:
        print(f"HATA (USER_SVC_KC_HELPER): HTTP error creating user '{user_representation.get('username')}': {e.response.status_code} - {e.response.text[:200]}")
    except Exception as e:
        print(f"HATA (USER_SVC_KC_HELPER): Unexpected error creating user '{user_representation.get('username')}': {e}")
    return None

async def set_keycloak_user_password(user_id: str, password: str, temporary: bool, settings: Settings) -> bool:
    """
    Verilen Keycloak kullanıcı ID'si için şifre atar.
    temporary: True ise, kullanıcı ilk login'de şifresini değiştirmek zorunda kalır.
    Başarılı olursa True, olmazsa False döner.
    """
    admin_token = await get_admin_api_token(settings)
    if not admin_token:
        print(f"HATA (USER_SVC_KC_HELPER): Şifre atamak için admin token alınamadı (user: {user_id}).")
        return False
    if not settings.keycloak.admin_api_realm_url:
        print(f"HATA (USER_SVC_KC_HELPER): admin_api_realm_url yapılandırılmamış (şifre atama).")
        return False

    password_payload = {
        "type": "password",
        "value": password,
        "temporary": temporary
    }
    set_password_url = f"{settings.keycloak.admin_api_realm_url}/users/{user_id}/reset-password"
    headers = {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}

    print(f"USER_SVC_KC_HELPER: Setting password for user ID '{user_id}' (temporary: {temporary}) at {set_password_url}")
    try:
        async with httpx.AsyncClient() as client:
            response = await client.put(set_password_url, json=password_payload, headers=headers)
            response.raise_for_status() # Genellikle 204 No Content döner
            print(f"USER_SVC_KC_HELPER: Password set successfully for user ID '{user_id}'. Status: {response.status_code}")
            return True
    except httpx.HTTPStatusError as e:
        print(f"HATA (USER_SVC_KC_HELPER): HTTP error setting password for user '{user_id}': {e.response.status_code} - {e.response.text[:200]}")
    except Exception as e:
        print(f"HATA (USER_SVC_KC_HELPER): Unexpected error setting password for user '{user_id}': {e}")
    return False

async def get_keycloak_realm_role_representation(role_name: str, settings: Settings) -> Optional[Dict[str, Any]]:
    """Helper: Verilen rol adına göre Keycloak'tan tam rol temsilini alır."""
    admin_token = await get_admin_api_token(settings)
    if not admin_token: return None
    if not settings.keycloak.admin_api_realm_url: return None

    role_url = f"{settings.keycloak.admin_api_realm_url}/roles/{role_name}"
    headers = {"Authorization": f"Bearer {admin_token}"}
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(role_url, headers=headers)
            response.raise_for_status()
            return response.json()
    except Exception:
        print(f"HATA (USER_SVC_KC_HELPER): Could not fetch role representation for '{role_name}'.")
        return None

async def assign_realm_roles_to_user(user_id: str, role_names: List[str], settings: Settings) -> bool:
    """
    Verilen Keycloak kullanıcı ID'sine, belirtilen realm rollerini atar.
    Rol adları (List[str]) alır, bunları Keycloak RoleRepresentation'larına çevirir.
    """
    admin_token = await get_admin_api_token(settings)
    if not admin_token:
        print(f"HATA (USER_SVC_KC_HELPER): Rol atamak için admin token alınamadı (user: {user_id}).")
        return False
    if not settings.keycloak.admin_api_realm_url:
        print(f"HATA (USER_SVC_KC_HELPER): admin_api_realm_url yapılandırılmamış (rol atama).")
        return False

    roles_to_assign = []
    for role_name in role_names:
        role_rep = await get_keycloak_realm_role_representation(role_name, settings)
        if role_rep:
            roles_to_assign.append(role_rep)
        else:
            print(f"UYARI (USER_SVC_KC_HELPER): Realm rolü '{role_name}' bulunamadı, kullanıcıya atanamayacak (user: {user_id}).")
    
    if not roles_to_assign:
        print(f"UYARI (USER_SVC_KC_HELPER): Kullanıcıya ({user_id}) atanacak geçerli rol bulunamadı veya sağlanmadı. (İstenen roller: {role_names})")
        return True # Hata değil, atanacak rol yoksa işlem başarılı sayılabilir.

    assign_roles_url = f"{settings.keycloak.admin_api_realm_url}/users/{user_id}/role-mappings/realm"
    headers = {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}

    print(f"USER_SVC_KC_HELPER: Assigning realm roles {role_names} to user ID '{user_id}' at {assign_roles_url}")
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(assign_roles_url, json=roles_to_assign, headers=headers)
            response.raise_for_status() # Genellikle 204 No Content döner
            print(f"USER_SVC_KC_HELPER: Realm roles assigned successfully to user ID '{user_id}'. Status: {response.status_code}")
            return True
    except httpx.HTTPStatusError as e:
        print(f"HATA (USER_SVC_KC_HELPER): HTTP error assigning roles to user '{user_id}': {e.response.status_code} - {e.response.text[:200]}")
    except Exception as e:
        print(f"HATA (USER_SVC_KC_HELPER): Unexpected error assigning roles to user '{user_id}': {e}")
    return False

async def add_user_to_group(user_id: str, group_id: str, settings: Settings) -> bool:
    """
    Verilen Keycloak kullanıcı ID'sini, belirtilen Keycloak grup ID'sine ekler.
    """
    admin_token = await get_admin_api_token(settings)
    if not admin_token:
        print(f"HATA (USER_SVC_KC_HELPER): Kullanıcıyı gruba eklemek için admin token alınamadı (user: {user_id}, group: {group_id}).")
        return False
    if not settings.keycloak.admin_api_realm_url:
        print(f"HATA (USER_SVC_KC_HELPER): admin_api_realm_url yapılandırılmamış (kullanıcıyı gruba ekleme).")
        return False

    add_to_group_url = f"{settings.keycloak.admin_api_realm_url}/users/{user_id}/groups/{group_id}"
    headers = {"Authorization": f"Bearer {admin_token}"} # Content-Type genellikle gerekmeyebilir PUT için (payload yoksa)

    print(f"USER_SVC_KC_HELPER: Adding user ID '{user_id}' to group ID '{group_id}' at {add_to_group_url}")
    try:
        async with httpx.AsyncClient() as client:
            response = await client.put(add_to_group_url, headers=headers) # Body göndermiyoruz, sadece ID'ler URL'de
            response.raise_for_status() # Genellikle 204 No Content döner
            print(f"USER_SVC_KC_HELPER: User '{user_id}' added to group '{group_id}' successfully. Status: {response.status_code}")
            return True
    except httpx.HTTPStatusError as e:
        print(f"HATA (USER_SVC_KC_HELPER): HTTP error adding user '{user_id}' to group '{group_id}': {e.response.status_code} - {e.response.text[:200]}")
    except Exception as e:
        print(f"HATA (USER_SVC_KC_HELPER): Unexpected error adding user '{user_id}' to group '{group_id}': {e}")
    return False

# ... ( _user_service_admin_token_cache, get_admin_api_token, create_keycloak_group, 
#       create_keycloak_user, set_keycloak_user_password, 
#       get_keycloak_realm_role_representation, add_user_to_group fonksiyonlarınız burada olmalı)

# --- YENİ VE GÜNCELLENMİŞ KEYCLOAK HELPER FONKSİYONLARI ---

async def get_keycloak_user(user_id: str, settings: Settings) -> Optional[Dict[str, Any]]:
    """Verilen Keycloak kullanıcı ID'sine sahip kullanıcının tam temsilini getirir."""
    admin_token = await get_admin_api_token(settings)
    if not admin_token:
        print(f"HATA (USER_SVC_KC_HELPER): Kullanıcı detayı getirmek için admin token alınamadı (user: {user_id}).")
        return None
    if not settings.keycloak.admin_api_realm_url:
        print(f"HATA (USER_SVC_KC_HELPER): admin_api_realm_url yapılandırılmamış (kullanıcı detayı).")
        return None

    user_url = f"{settings.keycloak.admin_api_realm_url}/users/{user_id}"
    headers = {"Authorization": f"Bearer {admin_token}"}

    print(f"USER_SVC_KC_HELPER: Fetching user details for ID '{user_id}' from {user_url}")
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(user_url, headers=headers)
            response.raise_for_status() # 404 dahil hataları fırlatır
            return response.json() # UserRepresentation
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            print(f"BİLGİ (USER_SVC_KC_HELPER): User with ID '{user_id}' not found in Keycloak.")
        else:
            print(f"HATA (USER_SVC_KC_HELPER): HTTP error fetching user '{user_id}': {e.response.status_code} - {e.response.text[:200]}")
    except Exception as e:
        print(f"HATA (USER_SVC_KC_HELPER): Unexpected error fetching user '{user_id}': {e}")
    return None

async def update_keycloak_user_attributes(user_id: str, user_representation_update: Dict[str, Any], settings: Settings) -> bool:
    """
    Verilen Keycloak kullanıcı ID'si için temel kullanıcı özelliklerini günceller.
    user_representation_update sadece güncellenecek alanları içermelidir (örn: {'firstName': 'Can', 'enabled': False}).
    """
    admin_token = await get_admin_api_token(settings)
    if not admin_token:
        print(f"HATA (USER_SVC_KC_HELPER): Kullanıcı güncellemek için admin token alınamadı (user: {user_id}).")
        return False
    if not settings.keycloak.admin_api_realm_url:
        print(f"HATA (USER_SVC_KC_HELPER): admin_api_realm_url yapılandırılmamış (kullanıcı güncelleme).")
        return False

    update_user_url = f"{settings.keycloak.admin_api_realm_url}/users/{user_id}"
    headers = {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}

    print(f"USER_SVC_KC_HELPER: Updating Keycloak user ID '{user_id}' with data: {user_representation_update} at {update_user_url}")
    try:
        async with httpx.AsyncClient() as client:
            response = await client.put(update_user_url, json=user_representation_update, headers=headers)
            response.raise_for_status() # Genellikle 204 No Content döner
            print(f"USER_SVC_KC_HELPER: User attributes updated successfully for ID '{user_id}'. Status: {response.status_code}")
            return True
    except httpx.HTTPStatusError as e:
        print(f"HATA (USER_SVC_KC_HELPER): HTTP error updating user attributes '{user_id}': {e.response.status_code} - {e.response.text[:200]}")
    except Exception as e:
        print(f"HATA (USER_SVC_KC_HELPER): Unexpected error updating user attributes '{user_id}': {e}")
    return False

async def get_user_keycloak_groups(user_id: str, settings: Settings) -> Optional[List[Dict[str, Any]]]:
    """Bir kullanıcının üye olduğu grupların listesini Keycloak'tan getirir."""
    admin_token = await get_admin_api_token(settings)
    if not admin_token:
        print(f"HATA (USER_SVC_KC_HELPER): Kullanıcı gruplarını getirmek için admin token alınamadı (user: {user_id}).")
        return None
    if not settings.keycloak.admin_api_realm_url:
        print(f"HATA (USER_SVC_KC_HELPER): admin_api_realm_url yapılandırılmamış (kullanıcı grupları).")
        return None
        
    groups_url = f"{settings.keycloak.admin_api_realm_url}/users/{user_id}/groups"
    headers = {"Authorization": f"Bearer {admin_token}"}

    print(f"USER_SVC_KC_HELPER: Fetching groups for user ID '{user_id}' from {groups_url}")
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(groups_url, headers=headers)
            response.raise_for_status()
            return response.json() # List of GroupRepresentation
    except httpx.HTTPStatusError as e:
        print(f"HATA (USER_SVC_KC_HELPER): HTTP error fetching groups for user '{user_id}': {e.response.status_code} - {e.response.text[:200]}")
    except Exception as e:
        print(f"HATA (USER_SVC_KC_HELPER): Unexpected error fetching groups for user '{user_id}': {e}")
    return None

async def remove_user_from_keycloak_group(user_id: str, group_id: str, settings: Settings) -> bool:
    """Bir kullanıcıyı belirtilen Keycloak grubundan çıkarır."""
    admin_token = await get_admin_api_token(settings)
    if not admin_token:
        print(f"HATA (USER_SVC_KC_HELPER): Kullanıcıyı gruptan çıkarmak için admin token alınamadı (user: {user_id}, group: {group_id}).")
        return False
    if not settings.keycloak.admin_api_realm_url:
        print(f"HATA (USER_SVC_KC_HELPER): admin_api_realm_url yapılandırılmamış (kullanıcıyı gruptan çıkarma).")
        return False

    remove_from_group_url = f"{settings.keycloak.admin_api_realm_url}/users/{user_id}/groups/{group_id}"
    headers = {"Authorization": f"Bearer {admin_token}"}

    print(f"USER_SVC_KC_HELPER: Removing user ID '{user_id}' from group ID '{group_id}' at {remove_from_group_url}")
    try:
        async with httpx.AsyncClient() as client:
            response = await client.delete(remove_from_group_url, headers=headers)
            response.raise_for_status() # Genellikle 204 No Content döner
            print(f"USER_SVC_KC_HELPER: User '{user_id}' removed from group '{group_id}' successfully. Status: {response.status_code}")
            return True
    except httpx.HTTPStatusError as e:
        print(f"HATA (USER_SVC_KC_HELPER): HTTP error removing user '{user_id}' from group '{group_id}': {e.response.status_code} - {e.response.text[:200]}")
    except Exception as e:
        print(f"HATA (USER_SVC_KC_HELPER): Unexpected error removing user '{user_id}' from group '{group_id}': {e}")
    return False

async def set_user_realm_roles(user_id: str, new_desired_role_names: List[str], settings: Settings) -> bool:
    """
    Kullanıcının realm rollerini, verilen 'new_desired_role_names' listesiyle tam olarak eşleşecek şekilde ayarlar.
    Mevcut fazla rolleri siler, eksik yeni rolleri ekler.
    """
    admin_token = await get_admin_api_token(settings)
    if not admin_token:
        print(f"HATA (USER_SVC_KC_HELPER): Rolleri ayarlamak için admin token alınamadı (user: {user_id}).")
        return False
    if not settings.keycloak.admin_api_realm_url:
        print(f"HATA (USER_SVC_KC_HELPER): admin_api_realm_url yapılandırılmamış (rolleri ayarlama).")
        return False

    base_role_mappings_url = f"{settings.keycloak.admin_api_realm_url}/users/{user_id}/role-mappings/realm"
    headers = {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}

    # 1. Mevcut rolleri al
    current_roles_rep: List[Dict[str, Any]] = []
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(base_role_mappings_url, headers={"Authorization": f"Bearer {admin_token}"})
            response.raise_for_status()
            current_roles_rep = response.json() or []
            current_role_names = {role['name'] for role in current_roles_rep}
            print(f"USER_SVC_KC_HELPER: User '{user_id}' current roles: {current_role_names}")
    except Exception as e:
        print(f"HATA (USER_SVC_KC_HELPER): Kullanıcının ({user_id}) mevcut rolleri alınırken hata: {e}")
        return False

    # 2. İstenen yeni rollerin tam temsillerini (ID'leriyle birlikte) al
    desired_roles_rep_map: Dict[str, Dict[str, Any]] = {} # name -> representation
    for role_name in new_desired_role_names:
        role_rep = await get_keycloak_realm_role_representation(role_name, settings)
        if role_rep:
            desired_roles_rep_map[role_name] = role_rep
        else:
            print(f"UYARI (USER_SVC_KC_HELPER): İstenen rol '{role_name}' Keycloak'ta bulunamadı, atlanacak (user: {user_id}).")
    
    desired_role_names_set = set(desired_roles_rep_map.keys())
    print(f"USER_SVC_KC_HELPER: User '{user_id}' desired new roles (found in KC): {desired_role_names_set}")

    # 3. Silinecek rolleri belirle (mevcutta var, yenide yok)
    roles_to_delete_names = current_role_names - desired_role_names_set
    roles_to_delete_reps = [role for role in current_roles_rep if role['name'] in roles_to_delete_names]

    # 4. Eklenecek rolleri belirle (yenide var, mevcutte yok)
    roles_to_add_names = desired_role_names_set - current_role_names
    roles_to_add_reps = [desired_roles_rep_map[name] for name in roles_to_add_names]

    all_successful = True

    # 5. Rolleri Sil
    if roles_to_delete_reps:
        print(f"USER_SVC_KC_HELPER: Deleting roles {roles_to_delete_names} from user '{user_id}'")
        try:
            async with httpx.AsyncClient() as client:
                # DELETE metodu için payload json=roles_to_delete_reps olmalı
                request = httpx.Request("DELETE", base_role_mappings_url, json=roles_to_delete_reps, headers=headers)
                response = await client.send(request)
                response.raise_for_status()
                print(f"USER_SVC_KC_HELPER: Roles deleted successfully for user '{user_id}'.")
        except Exception as e:
            print(f"HATA (USER_SVC_KC_HELPER): Kullanıcıdan ({user_id}) roller silinirken hata: {e}")
            all_successful = False # Sadece logla, diğer işlemlere devam etmeyi deneyebiliriz veya burada kesebiliriz.
                                   # Şimdilik devam etmeyi seçiyoruz.

    # 6. Rolleri Ekle
    if roles_to_add_reps:
        print(f"USER_SVC_KC_HELPER: Adding roles {roles_to_add_names} to user '{user_id}'")
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(base_role_mappings_url, json=roles_to_add_reps, headers=headers)
                response.raise_for_status()
                print(f"USER_SVC_KC_HELPER: Roles added successfully for user '{user_id}'.")
        except Exception as e:
            print(f"HATA (USER_SVC_KC_HELPER): Kullanıcıya ({user_id}) roller eklenirken hata: {e}")
            all_successful = False
            
    return all_successful

async def update_keycloak_group(group_id: str, new_name: str, settings: Settings) -> bool:
    """
    Verilen ID'ye sahip Keycloak grubunun adını günceller.
    Keycloak'un path'i otomatik olarak güncelleyip güncellemediği kontrol edilmeli
    veya path'in de ayrıca güncellenmesi gerekebilir. Şimdilik sadece adı güncelliyoruz.
    """
    admin_token = await get_admin_api_token(settings)
    if not admin_token:
        print(f"HATA (USER_SVC_KC_HELPER): Grup güncellemek için admin token alınamadı (grup: {group_id}).")
        return False
    if not settings.keycloak.admin_api_realm_url:
        print(f"HATA (USER_SVC_KC_HELPER): admin_api_realm_url yapılandırılmamış (grup güncelleme).")
        return False

    group_url = f"{settings.keycloak.admin_api_realm_url}/groups/{group_id}"
    headers = {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}

    # 1. Mevcut grup temsilini al
    current_group_representation: Optional[Dict[str, Any]] = None
    try:
        async with httpx.AsyncClient() as client:
            print(f"USER_SVC_KC_HELPER: Fetching current representation for group ID '{group_id}' from {group_url}")
            response_get = await client.get(group_url, headers={"Authorization": f"Bearer {admin_token}"})
            response_get.raise_for_status()
            current_group_representation = response_get.json()
    except httpx.HTTPStatusError as e:
        print(f"HATA (USER_SVC_KC_HELPER): Mevcut grup bilgisi alınırken HTTP hatası (grup: {group_id}): {e.response.status_code} - {e.response.text[:200]}")
        return False
    except Exception as e:
        print(f"HATA (USER_SVC_KC_HELPER): Mevcut grup bilgisi alınırken beklenmedik hata (grup: {group_id}): {e}")
        return False

    if not current_group_representation:
        print(f"HATA (USER_SVC_KC_HELPER): Grup '{group_id}' için mevcut temsil alınamadı veya grup bulunamadı.")
        return False

    # 2. Grup adını güncelle (ve path'i de adla tutarlı hale getirebiliriz - Keycloak bunu kendi yapabilir)
    updated_group_representation = current_group_representation.copy()
    updated_group_representation["name"] = new_name
    
    # Keycloak'ta path genellikle '/group_name' şeklindedir.
    # Ad değiştiğinde path'in de değişmesi gerekebilir.
    # Keycloak'un bunu otomatik yapıp yapmadığını test etmek iyi olur.
    # Güvenli olması için path'i de yeni ada göre güncelleyelim:
    if 'path' in updated_group_representation: # Path alanı varsa güncelleyelim
         # Path'in her zaman / ile başladığından emin olalım
        current_path_parts = updated_group_representation['path'].strip('/').split('/')
        if len(current_path_parts) > 0 : # Eğer path /A/B/C ise sadece son kısmı (C) değiştiririz
            current_path_parts[-1] = new_name
            updated_group_representation['path'] = "/" + "/".join(current_path_parts)
        else: # Eğer path sadece /A gibiyse veya boşsa
            updated_group_representation['path'] = f"/{new_name}"
    else: # Path alanı yoksa (pek olası değil ama) yeni ada göre oluşturalım
        updated_group_representation['path'] = f"/{new_name}"


    print(f"USER_SVC_KC_HELPER: Updating Keycloak group ID '{group_id}' with new name: '{new_name}' (new path: '{updated_group_representation.get('path')}') at {group_url}")

    # 3. Güncellenmiş grup temsilini gönder
    try:
        async with httpx.AsyncClient() as client:
            response_put = await client.put(group_url, json=updated_group_representation, headers=headers)
            response_put.raise_for_status() # Genellikle 204 No Content döner
            print(f"USER_SVC_KC_HELPER: Group '{group_id}' updated successfully. Status: {response_put.status_code}")
            return True
    except httpx.HTTPStatusError as e:
        print(f"HATA (USER_SVC_KC_HELPER): HTTP error updating group '{group_id}': {e.response.status_code} - {e.response.text[:200]}")
        if e.response.status_code == 409: # İsim çakışması
            print(f"DETAY: Grup adı '{new_name}' muhtemelen başka bir grup tarafından kullanılıyor.")
    except Exception as e:
        print(f"HATA (USER_SVC_KC_HELPER): Unexpected error updating group '{group_id}': {e}")
    return False

async def delete_keycloak_group(group_id: str, settings: Settings) -> bool:
    """
    Verilen ID'ye sahip Keycloak grubunu siler.
    Başarılı olursa True, olmazsa False döner.
    """
    admin_token = await get_admin_api_token(settings)
    if not admin_token:
        print(f"HATA (USER_SVC_KC_HELPER): Grup silmek için admin token alınamadı (grup: {group_id}).")
        return False
    if not settings.keycloak.admin_api_realm_url:
        print(f"HATA (USER_SVC_KC_HELPER): admin_api_realm_url yapılandırılmamış (grup silme).")
        return False

    delete_group_url = f"{settings.keycloak.admin_api_realm_url}/groups/{group_id}"
    headers = {"Authorization": f"Bearer {admin_token}"}

    print(f"USER_SVC_KC_HELPER: Deleting Keycloak group ID '{group_id}' from {delete_group_url}")
    try:
        async with httpx.AsyncClient() as client:
            response = await client.delete(delete_group_url, headers=headers)
            # Başarılı silme genellikle 204 No Content döner.
            # Eğer grup bulunamazsa (zaten silinmiş veya yanlış ID), Keycloak 404 dönebilir.
            if response.status_code == 204:
                print(f"USER_SVC_KC_HELPER: Group '{group_id}' deleted successfully from Keycloak.")
                return True
            elif response.status_code == 404:
                print(f"BİLGİ (USER_SVC_KC_HELPER): Group '{group_id}' not found in Keycloak (already deleted or invalid ID). Treating as success for deletion.")
                return True # Zaten yoksa, silinmiş kabul edebiliriz.
            else:
                response.raise_for_status() # Diğer 4xx/5xx hataları için exception fırlat
                # Buraya normalde gelinmemeli raise_for_status'tan dolayı
                print(f"HATA (USER_SVC_KC_HELPER): Group deletion failed with unexpected status {response.status_code}. Response: {response.text[:200]}")
                return False
    except httpx.HTTPStatusError as e:
        # 404 durumu yukarıda ele alındı, burası diğer HTTP hataları için.
        print(f"HATA (USER_SVC_KC_HELPER): HTTP error deleting group '{group_id}': {e.response.status_code} - {e.response.text[:200]}")
    except Exception as e:
        print(f"HATA (USER_SVC_KC_HELPER): Unexpected error deleting group '{group_id}': {e}")
    return False

async def delete_keycloak_user(user_id: str, settings: Settings) -> bool:
    """
    Verilen ID'ye sahip Keycloak kullanıcısını siler.
    Başarılı olursa veya kullanıcı zaten yoksa True, aksi halde False döner.
    """
    admin_token = await get_admin_api_token(settings)
    if not admin_token:
        print(f"HATA (USER_SVC_KC_HELPER): Kullanıcı silmek için admin token alınamadı (user: {user_id}).")
        return False
    if not settings.keycloak.admin_api_realm_url:
        print(f"HATA (USER_SVC_KC_HELPER): admin_api_realm_url yapılandırılmamış (kullanıcı silme).")
        return False

    delete_user_url = f"{settings.keycloak.admin_api_realm_url}/users/{user_id}"
    headers = {"Authorization": f"Bearer {admin_token}"}

    print(f"USER_SVC_KC_HELPER: Deleting Keycloak user ID '{user_id}' from {delete_user_url}")
    try:
        async with httpx.AsyncClient() as client:
            response = await client.delete(delete_user_url, headers=headers)
            # Başarılı silme genellikle 204 No Content döner.
            # Eğer kullanıcı bulunamazsa (zaten silinmiş veya yanlış ID), Keycloak 404 dönebilir.
            if response.status_code == 204:
                print(f"USER_SVC_KC_HELPER: User '{user_id}' deleted successfully from Keycloak.")
                return True
            elif response.status_code == 404:
                print(f"BİLGİ (USER_SVC_KC_HELPER): User '{user_id}' not found in Keycloak (already deleted or invalid ID). Treating as success for deletion.")
                return True # Zaten yoksa, silinmiş kabul edebiliriz.
            else:
                # Diğer 4xx/5xx hataları için exception fırlatmak yerine False dönelim ki çağıran yer karar versin.
                print(f"HATA (USER_SVC_KC_HELPER): User deletion failed with status {response.status_code}. Response: {response.text[:200]}")
                # response.raise_for_status() # Bunu kullanmıyoruz, False döneceğiz.
                return False
    except httpx.HTTPStatusError as e:
        # Bu blok normalde raise_for_status kullanılsaydı çalışırdı. Üstteki mantıkla buraya pek gelinmemeli.
        print(f"HATA (USER_SVC_KC_HELPER): HTTP error deleting user '{user_id}': {e.response.status_code} - {e.response.text[:200]}")
    except Exception as e:
        print(f"HATA (USER_SVC_KC_HELPER): Unexpected error deleting user '{user_id}': {e}")
    return False