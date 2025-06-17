# user_service/keycloak_api_helpers.py
import httpx
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta

from .config import Settings # user_service'in kendi config'ini kullanacak

_user_service_admin_token_cache: Dict[str, Any] = {
    "token": None,
    "expires_at": datetime.utcnow()
}

async def get_admin_api_token(settings: Settings) -> Optional[str]:
    """Keycloak Admin API için (user_service adına) token alır."""
    global _user_service_admin_token_cache

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
        # DEĞİŞİKLİK: SSL doğrulamasını atlamak için verify=False eklendi.
        async with httpx.AsyncClient(verify=False) as client:
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
    """Keycloak'ta verilen isimle yeni bir ana grup (tenant) oluşturur."""
    admin_token = await get_admin_api_token(settings)
    if not admin_token:
        print("HATA (USER_SVC_KC_HELPER): Grup oluşturmak için admin token alınamadı.")
        return None

    group_payload = {"name": group_name}
    create_group_url = f"{settings.keycloak.admin_api_realm_url}/groups"
    headers = {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}

    print(f"USER_SVC_KC_HELPER: Creating Keycloak group '{group_name}' at {create_group_url}")
    try:
        # DEĞİŞİKLİK: SSL doğrulamasını atlamak için verify=False eklendi.
        async with httpx.AsyncClient(verify=False) as client:
            response = await client.post(create_group_url, json=group_payload, headers=headers)
            if response.status_code == 201:
                location_header = response.headers.get("Location")
                if location_header:
                    created_group_id = location_header.split("/")[-1]
                    print(f"USER_SVC_KC_HELPER: Keycloak group '{group_name}' created successfully. ID: {created_group_id}")
                    return created_group_id
                else:
                    print(f"HATA (USER_SVC_KC_HELPER): Grup '{group_name}' oluşturuldu (201) ancak Location header bulunamadı.")
                    return None
            else:
                response.raise_for_status()
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 409:
            print(f"UYARI (USER_SVC_KC_HELPER): Keycloak group '{group_name}' zaten mevcut (409 Conflict).")
            return "EXISTS"
        else:
            print(f"HATA (USER_SVC_KC_HELPER): Keycloak group oluşturulurken HTTP hatası: {e.response.status_code} - {e.response.text[:200]}")
    except Exception as e:
        print(f"HATA (USER_SVC_KC_HELPER): Keycloak group oluşturulurken beklenmedik hata: {e}")
    return None

async def create_keycloak_user(user_representation: Dict[str, Any], settings: Settings) -> Optional[str]:
    """Keycloak'ta yeni bir kullanıcı oluşturur."""
    admin_token = await get_admin_api_token(settings)
    if not admin_token:
        return None

    create_user_url = f"{settings.keycloak.admin_api_realm_url}/users"
    headers = {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}

    print(f"USER_SVC_KC_HELPER: Creating Keycloak user '{user_representation.get('username')}'")
    try:
        # DEĞİŞİKLİK: SSL doğrulamasını atlamak için verify=False eklendi.
        async with httpx.AsyncClient(verify=False) as client:
            response = await client.post(create_user_url, json=user_representation, headers=headers)
            if response.status_code == 201:
                location_header = response.headers.get("Location")
                if location_header:
                    return location_header.split("/")[-1]
                return None 
            elif response.status_code == 409:
                print(f"HATA (USER_SVC_KC_HELPER): User '{user_representation.get('username')}' zaten mevcut (409 Conflict).")
                return "EXISTS"
            else:
                response.raise_for_status()
    except httpx.HTTPStatusError as e:
        print(f"HATA (USER_SVC_KC_HELPER): HTTP hatası (kullanıcı oluşturma): {e.response.status_code} - {e.response.text[:200]}")
    except Exception as e:
        print(f"HATA (USER_SVC_KC_HELPER): Beklenmedik hata (kullanıcı oluşturma): {e}")
    return None

async def set_keycloak_user_password(user_id: str, password: str, temporary: bool, settings: Settings) -> bool:
    """Verilen kullanıcı için şifre atar."""
    admin_token = await get_admin_api_token(settings)
    if not admin_token:
        return False

    password_payload = {"type": "password", "value": password, "temporary": temporary}
    set_password_url = f"{settings.keycloak.admin_api_realm_url}/users/{user_id}/reset-password"
    headers = {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}

    print(f"USER_SVC_KC_HELPER: Setting password for user ID '{user_id}'")
    try:
        # DEĞİŞİKLİK: SSL doğrulamasını atlamak için verify=False eklendi.
        async with httpx.AsyncClient(verify=False) as client:
            response = await client.put(set_password_url, json=password_payload, headers=headers)
            response.raise_for_status()
            return True
    except httpx.HTTPStatusError as e:
        print(f"HATA (USER_SVC_KC_HELPER): HTTP hatası (şifre atama): {e.response.status_code} - {e.response.text[:200]}")
    except Exception as e:
        print(f"HATA (USER_SVC_KC_HELPER): Beklenmedik hata (şifre atama): {e}")
    return False

async def get_keycloak_realm_role_representation(role_name: str, settings: Settings) -> Optional[Dict[str, Any]]:
    """Verilen rol adına göre Keycloak'tan tam rol temsilini alır."""
    admin_token = await get_admin_api_token(settings)
    if not admin_token: return None

    role_url = f"{settings.keycloak.admin_api_realm_url}/roles/{role_name}"
    headers = {"Authorization": f"Bearer {admin_token}"}
    try:
        # DEĞİŞİKLİK: SSL doğrulamasını atlamak için verify=False eklendi.
        async with httpx.AsyncClient(verify=False) as client:
            response = await client.get(role_url, headers=headers)
            response.raise_for_status()
            return response.json()
    except Exception:
        print(f"HATA (USER_SVC_KC_HELPER): Rol temsili alınamadı: '{role_name}'.")
        return None

async def assign_realm_roles_to_user(user_id: str, role_names: List[str], settings: Settings) -> bool:
    """Belirtilen kullanıcıya realm rollerini atar."""
    admin_token = await get_admin_api_token(settings)
    if not admin_token:
        return False

    roles_to_assign = []
    for role_name in role_names:
        role_rep = await get_keycloak_realm_role_representation(role_name, settings)
        if role_rep:
            roles_to_assign.append(role_rep)
        else:
            print(f"UYARI: Realm rolü '{role_name}' bulunamadı, kullanıcıya atanamayacak.")
    
    if not roles_to_assign:
        return True 

    assign_roles_url = f"{settings.keycloak.admin_api_realm_url}/users/{user_id}/role-mappings/realm"
    headers = {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}

    print(f"USER_SVC_KC_HELPER: Assigning roles {role_names} to user '{user_id}'")
    try:
        # DEĞİŞİKLİK: SSL doğrulamasını atlamak için verify=False eklendi.
        async with httpx.AsyncClient(verify=False) as client:
            response = await client.post(assign_roles_url, json=roles_to_assign, headers=headers)
            response.raise_for_status()
            return True
    except httpx.HTTPStatusError as e:
        print(f"HATA (USER_SVC_KC_HELPER): HTTP hatası (rol atama): {e.response.status_code} - {e.response.text[:200]}")
    except Exception as e:
        print(f"HATA (USER_SVC_KC_HELPER): Beklenmedik hata (rol atama): {e}")
    return False

async def add_user_to_group(user_id: str, group_id: str, settings: Settings) -> bool:
    """Bir kullanıcıyı bir gruba ekler."""
    admin_token = await get_admin_api_token(settings)
    if not admin_token:
        return False

    add_to_group_url = f"{settings.keycloak.admin_api_realm_url}/users/{user_id}/groups/{group_id}"
    headers = {"Authorization": f"Bearer {admin_token}"}

    print(f"USER_SVC_KC_HELPER: Adding user '{user_id}' to group '{group_id}'")
    try:
        # DEĞİŞİKLİK: SSL doğrulamasını atlamak için verify=False eklendi.
        async with httpx.AsyncClient(verify=False) as client:
            response = await client.put(add_to_group_url, headers=headers)
            response.raise_for_status()
            return True
    except httpx.HTTPStatusError as e:
        print(f"HATA (USER_SVC_KC_HELPER): HTTP hatası (gruba ekleme): {e.response.status_code} - {e.response.text[:200]}")
    except Exception as e:
        print(f"HATA (USER_SVC_KC_HELPER): Beklenmedik hata (gruba ekleme): {e}")
    return False

async def get_keycloak_user(user_id: str, settings: Settings) -> Optional[Dict[str, Any]]:
    """Kullanıcı detaylarını Keycloak'tan alır."""
    admin_token = await get_admin_api_token(settings)
    if not admin_token:
        return None
    
    user_url = f"{settings.keycloak.admin_api_realm_url}/users/{user_id}"
    headers = {"Authorization": f"Bearer {admin_token}"}

    print(f"USER_SVC_KC_HELPER: Fetching user details for ID '{user_id}'")
    try:
        # DEĞİŞİKLİK: SSL doğrulamasını atlamak için verify=False eklendi.
        async with httpx.AsyncClient(verify=False) as client:
            response = await client.get(user_url, headers=headers)
            if response.status_code == 404:
                return None
            response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"HATA: Keycloak'tan kullanıcı detayı alınırken hata: {e}")
        return None

async def update_keycloak_user_attributes(user_id: str, user_representation_update: Dict[str, Any], settings: Settings) -> bool:
    """Kullanıcı özelliklerini günceller."""
    admin_token = await get_admin_api_token(settings)
    if not admin_token:
        return False

    update_user_url = f"{settings.keycloak.admin_api_realm_url}/users/{user_id}"
    headers = {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}

    print(f"USER_SVC_KC_HELPER: Updating Keycloak user ID '{user_id}'")
    try:
        # DEĞİŞİKLİK: SSL doğrulamasını atlamak için verify=False eklendi.
        async with httpx.AsyncClient(verify=False) as client:
            response = await client.put(update_user_url, json=user_representation_update, headers=headers)
            response.raise_for_status()
            return True
    except httpx.HTTPStatusError as e:
        print(f"HATA (USER_SVC_KC_HELPER): HTTP hatası (kullanıcı güncelleme): {e.response.status_code} - {e.response.text[:200]}")
    except Exception as e:
        print(f"HATA (USER_SVC_KC_HELPER): Beklenmedik hata (kullanıcı güncelleme): {e}")
    return False

async def get_user_keycloak_groups(user_id: str, settings: Settings) -> Optional[List[Dict[str, Any]]]:
    """Kullanıcının üye olduğu grupları getirir."""
    admin_token = await get_admin_api_token(settings)
    if not admin_token:
        return None
        
    groups_url = f"{settings.keycloak.admin_api_realm_url}/users/{user_id}/groups"
    headers = {"Authorization": f"Bearer {admin_token}"}

    print(f"USER_SVC_KC_HELPER: Fetching groups for user ID '{user_id}'")
    try:
        # DEĞİŞİKLİK: SSL doğrulamasını atlamak için verify=False eklendi.
        async with httpx.AsyncClient(verify=False) as client:
            response = await client.get(groups_url, headers=headers)
            response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as e:
        print(f"HATA (USER_SVC_KC_HELPER): HTTP hatası (grup getirme): {e.response.status_code} - {e.response.text[:200]}")
    except Exception as e:
        print(f"HATA (USER_SVC_KC_HELPER): Beklenmedik hata (grup getirme): {e}")
    return None

async def remove_user_from_keycloak_group(user_id: str, group_id: str, settings: Settings) -> bool:
    """Bir kullanıcıyı bir gruptan çıkarır."""
    admin_token = await get_admin_api_token(settings)
    if not admin_token:
        return False

    remove_from_group_url = f"{settings.keycloak.admin_api_realm_url}/users/{user_id}/groups/{group_id}"
    headers = {"Authorization": f"Bearer {admin_token}"}

    print(f"USER_SVC_KC_HELPER: Removing user '{user_id}' from group '{group_id}'")
    try:
        # DEĞİŞİKLİK: SSL doğrulamasını atlamak için verify=False eklendi.
        async with httpx.AsyncClient(verify=False) as client:
            response = await client.delete(remove_from_group_url, headers=headers)
            response.raise_for_status()
            return True
    except httpx.HTTPStatusError as e:
        print(f"HATA (USER_SVC_KC_HELPER): HTTP hatası (gruptan çıkarma): {e.response.status_code} - {e.response.text[:200]}")
    except Exception as e:
        print(f"HATA (USER_SVC_KC_HELPER): Beklenmedik hata (gruptan çıkarma): {e}")
    return False

async def set_user_realm_roles(user_id: str, new_role_names: List[str], settings: Settings) -> bool:
    """Kullanıcının realm rollerini günceller."""
    admin_token = await get_admin_api_token(settings)
    if not admin_token:
        return False

    headers = {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}
    
    try:
        # DEĞİŞİKLİK: Tüm httpx istemcileri için verify=False eklendi.
        async with httpx.AsyncClient(verify=False) as client:
            # Mevcut tüm rolleri al
            all_roles_url = f"{settings.keycloak.admin_api_realm_url}/roles"
            roles_response = await client.get(all_roles_url, headers=headers)
            roles_response.raise_for_status()
            available_roles_map = {role['name']: role for role in roles_response.json()}

            # Mevcut kullanıcı rollerini al
            user_roles_url = f"{settings.keycloak.admin_api_realm_url}/users/{user_id}/role-mappings/realm"
            user_roles_response = await client.get(user_roles_url, headers=headers)
            user_roles_response.raise_for_status()
            current_user_roles_set = {role['name'] for role in user_roles_response.json()}

            new_roles_set = set(new_role_names)
            roles_to_add = new_roles_set - current_user_roles_set
            roles_to_remove = current_user_roles_set - new_roles_set

            # Rolleri sil
            if roles_to_remove:
                roles_to_remove_reps = [available_roles_map[name] for name in roles_to_remove if name in available_roles_map]
                if roles_to_remove_reps:
                    delete_response = await client.request("DELETE", user_roles_url, headers=headers, json=roles_to_remove_reps)
                    delete_response.raise_for_status()

            # Rolleri ekle
            if roles_to_add:
                roles_to_add_reps = [available_roles_map[name] for name in roles_to_add if name in available_roles_map]
                if roles_to_add_reps:
                    add_response = await client.post(user_roles_url, headers=headers, json=roles_to_add_reps)
                    add_response.raise_for_status()
        return True
    except Exception as e:
        print(f"HATA (set_user_realm_roles): {e}")
        return False

async def update_keycloak_group(group_id: str, new_name: str, settings: Settings) -> bool:
    """Bir Keycloak grubunu günceller."""
    admin_token = await get_admin_api_token(settings)
    if not admin_token:
        return False

    group_url = f"{settings.keycloak.admin_api_realm_url}/groups/{group_id}"
    headers = {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}

    try:
        # DEĞİŞİKLİK: SSL doğrulamasını atlamak için verify=False eklendi.
        async with httpx.AsyncClient(verify=False) as client:
            response_get = await client.get(group_url, headers={"Authorization": f"Bearer {admin_token}"})
            response_get.raise_for_status()
            current_group_representation = response_get.json()
            
            updated_group_representation = current_group_representation.copy()
            updated_group_representation["name"] = new_name
            
            response_put = await client.put(group_url, json=updated_group_representation, headers=headers)
            response_put.raise_for_status()
        return True
    except httpx.HTTPStatusError as e:
        print(f"HATA (update_keycloak_group): {e.response.status_code} - {e.response.text[:200]}")
    except Exception as e:
        print(f"HATA (update_keycloak_group): {e}")
    return False

async def delete_keycloak_group(group_id: str, settings: Settings) -> bool:
    """Bir Keycloak grubunu siler."""
    admin_token = await get_admin_api_token(settings)
    if not admin_token:
        return False

    delete_group_url = f"{settings.keycloak.admin_api_realm_url}/groups/{group_id}"
    headers = {"Authorization": f"Bearer {admin_token}"}

    print(f"USER_SVC_KC_HELPER: Deleting Keycloak group ID '{group_id}'")
    try:
        # DEĞİŞİKLİK: SSL doğrulamasını atlamak için verify=False eklendi.
        async with httpx.AsyncClient(verify=False) as client:
            response = await client.delete(delete_group_url, headers=headers)
            if response.status_code in [204, 404]: # Başarılı veya zaten yok
                return True
            response.raise_for_status()
    except httpx.HTTPStatusError as e:
        print(f"HATA (delete_keycloak_group): {e.response.status_code} - {e.response.text[:200]}")
    except Exception as e:
        print(f"HATA (delete_keycloak_group): {e}")
    return False

async def delete_keycloak_user(user_id: str, settings: Settings) -> bool:
    """Bir Keycloak kullanıcısını siler."""
    admin_token = await get_admin_api_token(settings)
    if not admin_token:
        return False

    delete_user_url = f"{settings.keycloak.admin_api_realm_url}/users/{user_id}"
    headers = {"Authorization": f"Bearer {admin_token}"}

    print(f"USER_SVC_KC_HELPER: Deleting Keycloak user ID '{user_id}'")
    try:
        # DEĞİŞİKLİK: SSL doğrulamasını atlamak için verify=False eklendi.
        async with httpx.AsyncClient(verify=False) as client:
            response = await client.delete(delete_user_url, headers=headers)
            if response.status_code in [204, 404]:
                return True
            response.raise_for_status()
    except httpx.HTTPStatusError as e:
        print(f"HATA (delete_keycloak_user): {e.response.status_code} - {e.response.text[:200]}")
    except Exception as e:
        print(f"HATA (delete_keycloak_user): {e}")
    return False

async def get_all_keycloak_users_paginated(settings: Settings) -> Optional[List[Dict[str, Any]]]:
    """Tüm Keycloak kullanıcılarını sayfalama yaparak çeker."""
    admin_token = await get_admin_api_token(settings)
    if not admin_token: return None

    all_users, first, max_results = [], 0, 100
    users_url = f"{settings.keycloak.admin_api_realm_url}/users"
    headers = {"Authorization": f"Bearer {admin_token}"}

    # DEĞİŞİKLİK: SSL doğrulamasını atlamak için verify=False eklendi.
    async with httpx.AsyncClient(verify=False) as client:
        while True:
            response = await client.get(users_url, headers=headers, params={"first": first, "max": max_results})
            if response.status_code != 200:
                return None
            users_page = response.json()
            if not users_page:
                break
            all_users.extend(users_page)
            first += max_results
    return all_users

async def get_all_keycloak_groups_paginated(settings: Settings) -> Optional[List[Dict[str, Any]]]:
    """Tüm Keycloak gruplarını sayfalama yaparak çeker."""
    admin_token = await get_admin_api_token(settings)
    if not admin_token: return None

    all_groups, first, max_results = [], 0, 100
    groups_url = f"{settings.keycloak.admin_api_realm_url}/groups"
    headers = {"Authorization": f"Bearer {admin_token}"}

    # DEĞİŞİKLİK: SSL doğrulamasını atlamak için verify=False eklendi.
    async with httpx.AsyncClient(verify=False) as client:
        while True:
            params = {"first": first, "max": max_results, "briefRepresentation": "false"}
            response = await client.get(groups_url, headers=headers, params=params)
            if response.status_code != 200:
                return None
            groups_page = response.json()
            if not groups_page:
                break
            all_groups.extend(groups_page)
            first += max_results
    return all_groups
