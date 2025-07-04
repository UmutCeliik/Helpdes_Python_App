# user_service/keycloak_api_helpers.py
import logging
import httpx
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta

from .config import Settings

# Servis adıyla logger'ı al
logger = logging.getLogger("user_service")

_user_service_admin_token_cache: Dict[str, Any] = {
    "token": None,
    "expires_at": datetime.utcnow()
}

async def get_admin_api_token(settings: Settings) -> Optional[str]:
    """Keycloak Admin API için (user_service adına) token alır."""
    global _user_service_admin_token_cache

    if _user_service_admin_token_cache["token"] and \
       _user_service_admin_token_cache["expires_at"] > datetime.utcnow() + timedelta(seconds=30):
        logger.debug("Using cached Keycloak admin token.")
        return _user_service_admin_token_cache["token"]

    if not all([settings.keycloak.admin_api_token_endpoint, 
                settings.keycloak.admin_client_id, 
                settings.keycloak.admin_client_secret]):
        logger.error("Admin API token endpoint, client ID, or secret is not configured.")
        return None

    payload = {
        "grant_type": "client_credentials",
        "client_id": settings.keycloak.admin_client_id,
        "client_secret": settings.keycloak.admin_client_secret,
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    logger.info(f"Requesting new Keycloak admin token from {settings.keycloak.admin_api_token_endpoint}")
    try:
        async with httpx.AsyncClient(verify=False) as client:
            response = await client.post(settings.keycloak.admin_api_token_endpoint, data=payload, headers=headers)
            response.raise_for_status()
            token_data = response.json()

            access_token = token_data.get("access_token")
            expires_in = token_data.get("expires_in", 300)

            _user_service_admin_token_cache["token"] = access_token
            _user_service_admin_token_cache["expires_at"] = datetime.utcnow() + timedelta(seconds=expires_in)

            logger.info("New Keycloak admin token obtained and cached.")
            return access_token
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error while getting admin token: {e.response.status_code} - {e.response.text}", exc_info=True)
    except Exception:
        logger.exception("Unexpected error while getting admin token.")
    
    _user_service_admin_token_cache["token"] = None
    return None

async def create_keycloak_group(group_name: str, settings: Settings) -> Optional[str]:
    """Keycloak'ta verilen isimle yeni bir ana grup (tenant) oluşturur."""
    admin_token = await get_admin_api_token(settings)
    if not admin_token:
        logger.error("Could not get admin token to create group.")
        return None

    group_payload = {"name": group_name}
    create_group_url = f"{settings.keycloak.admin_api_realm_url}/groups"
    headers = {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}

    logger.info(f"Creating Keycloak group '{group_name}' at {create_group_url}")
    try:
        async with httpx.AsyncClient(verify=False) as client:
            response = await client.post(create_group_url, json=group_payload, headers=headers)
            if response.status_code == 201:
                location_header = response.headers.get("Location")
                if location_header:
                    created_group_id = location_header.split("/")[-1]
                    logger.info(f"Keycloak group '{group_name}' created successfully. ID: {created_group_id}")
                    return created_group_id
                else:
                    logger.error(f"Group '{group_name}' created (201) but Location header was not found.")
                    return None
            else:
                response.raise_for_status()
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 409:
            logger.warning(f"Keycloak group '{group_name}' already exists (409 Conflict).")
            return "EXISTS"
        else:
            logger.error(f"HTTP error while creating Keycloak group: {e.response.status_code} - {e.response.text[:200]}", exc_info=True)
    except Exception:
        logger.exception("Unexpected error while creating Keycloak group.")
    return None

async def create_keycloak_user(user_representation: Dict[str, Any], settings: Settings) -> Optional[str]:
    """Keycloak'ta yeni bir kullanıcı oluşturur."""
    admin_token = await get_admin_api_token(settings)
    if not admin_token:
        logger.error("Could not get admin token to create user.")
        return None

    create_user_url = f"{settings.keycloak.admin_api_realm_url}/users"
    headers = {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}

    logger.info(f"Creating Keycloak user '{user_representation.get('username')}'")
    try:
        async with httpx.AsyncClient(verify=False) as client:
            response = await client.post(create_user_url, json=user_representation, headers=headers)
            if response.status_code == 201:
                location_header = response.headers.get("Location")
                if location_header:
                    return location_header.split("/")[-1]
                return None 
            elif response.status_code == 409:
                logger.warning(f"User '{user_representation.get('username')}' already exists in Keycloak (409 Conflict).")
                return "EXISTS"
            else:
                response.raise_for_status()
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error while creating user: {e.response.status_code} - {e.response.text[:200]}", exc_info=True)
    except Exception:
        logger.exception("Unexpected error while creating user.")
    return None

async def delete_keycloak_user(user_id: str, settings: Settings) -> bool:
    """Bir Keycloak kullanıcısını siler."""
    admin_token = await get_admin_api_token(settings)
    if not admin_token:
        logger.error(f"Could not get admin token to delete user {user_id}.")
        return False

    delete_user_url = f"{settings.keycloak.admin_api_realm_url}/users/{user_id}"
    headers = {"Authorization": f"Bearer {admin_token}"}

    logger.info(f"Deleting Keycloak user with ID '{user_id}'")
    try:
        async with httpx.AsyncClient(verify=False) as client:
            response = await client.delete(delete_user_url, headers=headers)
            if response.status_code in [204, 404]:
                logger.info(f"Keycloak user {user_id} deleted successfully or was already not found.")
                return True
            response.raise_for_status()
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error while deleting user {user_id}: {e.response.status_code} - {e.response.text[:200]}", exc_info=True)
    except Exception:
        logger.exception(f"Unexpected error while deleting user {user_id}.")
    return False

async def set_keycloak_user_password(user_id: str, password: str, temporary: bool, settings: Settings) -> bool:
    """Verilen kullanıcı için şifre atar."""
    admin_token = await get_admin_api_token(settings)
    if not admin_token:
        logger.error(f"Could not get admin token to set password for user {user_id}.")
        return False

    password_payload = {"type": "password", "value": password, "temporary": temporary}
    set_password_url = f"{settings.keycloak.admin_api_realm_url}/users/{user_id}/reset-password"
    headers = {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}

    logger.info(f"Setting password for user ID '{user_id}'")
    try:
        async with httpx.AsyncClient(verify=False) as client:
            response = await client.put(set_password_url, json=password_payload, headers=headers)
            response.raise_for_status()
            logger.info(f"Password set successfully for user {user_id}.")
            return True
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error while setting password for user {user_id}: {e.response.status_code} - {e.response.text[:200]}", exc_info=True)
    except Exception:
        logger.exception(f"Unexpected error while setting password for user {user_id}.")
    return False

async def get_keycloak_realm_role_representation(role_name: str, settings: Settings) -> Optional[Dict[str, Any]]:
    """Verilen rol adına göre Keycloak'tan tam rol temsilini alır."""
    admin_token = await get_admin_api_token(settings)
    if not admin_token: return None

    role_url = f"{settings.keycloak.admin_api_realm_url}/roles/{role_name}"
    headers = {"Authorization": f"Bearer {admin_token}"}
    try:
        async with httpx.AsyncClient(verify=False) as client:
            response = await client.get(role_url, headers=headers)
            response.raise_for_status()
            return response.json()
    except Exception:
        logger.error(f"Could not get role representation for role: '{role_name}'.", exc_info=True)
        return None

async def assign_realm_roles_to_user(user_id: str, role_names: List[str], settings: Settings) -> bool:
    """Belirtilen kullanıcıya realm rollerini atar."""
    admin_token = await get_admin_api_token(settings)
    if not admin_token:
        logger.error(f"Could not get admin token to assign roles to user {user_id}.")
        return False

    roles_to_assign = []
    for role_name in role_names:
        role_rep = await get_keycloak_realm_role_representation(role_name, settings)
        if role_rep:
            roles_to_assign.append(role_rep)
        else:
            logger.warning(f"Realm role '{role_name}' not found, it will not be assigned to user {user_id}.")
    
    if not roles_to_assign:
        logger.info(f"No valid roles found to assign for user {user_id}.")
        return True 

    assign_roles_url = f"{settings.keycloak.admin_api_realm_url}/users/{user_id}/role-mappings/realm"
    headers = {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}

    logger.info(f"Assigning roles {role_names} to user '{user_id}'")
    try:
        async with httpx.AsyncClient(verify=False) as client:
            response = await client.post(assign_roles_url, json=roles_to_assign, headers=headers)
            response.raise_for_status()
            logger.info(f"Roles successfully assigned to user {user_id}.")
            return True
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error while assigning roles to user {user_id}: {e.response.status_code} - {e.response.text[:200]}", exc_info=True)
    except Exception:
        logger.exception(f"Unexpected error while assigning roles to user {user_id}.")
    return False

async def add_user_to_group(user_id: str, group_id: str, settings: Settings) -> bool:
    """Bir kullanıcıyı bir gruba ekler."""
    admin_token = await get_admin_api_token(settings)
    if not admin_token:
        logger.error(f"Could not get admin token to add user {user_id} to group {group_id}.")
        return False

    add_to_group_url = f"{settings.keycloak.admin_api_realm_url}/users/{user_id}/groups/{group_id}"
    headers = {"Authorization": f"Bearer {admin_token}"}

    logger.info(f"Adding user '{user_id}' to group '{group_id}'")
    try:
        async with httpx.AsyncClient(verify=False) as client:
            response = await client.put(add_to_group_url, headers=headers)
            response.raise_for_status()
            logger.info(f"Successfully added user '{user_id}' to group '{group_id}'.")
            return True
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error while adding user {user_id} to group {group_id}: {e.response.status_code} - {e.response.text[:200]}", exc_info=True)
    except Exception:
        logger.exception(f"Unexpected error while adding user {user_id} to group {group_id}.")
    return False

async def get_keycloak_user(user_id: str, settings: Settings) -> Optional[Dict[str, Any]]:
    """Kullanıcı detaylarını Keycloak'tan alır."""
    admin_token = await get_admin_api_token(settings)
    if not admin_token: return None
    
    user_url = f"{settings.keycloak.admin_api_realm_url}/users/{user_id}"
    headers = {"Authorization": f"Bearer {admin_token}"}

    logger.debug(f"Fetching Keycloak user details for ID '{user_id}'")
    try:
        async with httpx.AsyncClient(verify=False) as client:
            response = await client.get(user_url, headers=headers)
            if response.status_code == 404:
                logger.warning(f"User with ID '{user_id}' not found in Keycloak.")
                return None
            response.raise_for_status()
        return response.json()
    except Exception:
        logger.exception(f"Error fetching user details from Keycloak for user ID: {user_id}")
        return None

async def update_keycloak_user_attributes(user_id: str, user_representation_update: Dict[str, Any], settings: Settings) -> bool:
    """Kullanıcı özelliklerini günceller."""
    admin_token = await get_admin_api_token(settings)
    if not admin_token: return False

    update_user_url = f"{settings.keycloak.admin_api_realm_url}/users/{user_id}"
    headers = {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}

    logger.info(f"Updating Keycloak user ID '{user_id}' with data: {user_representation_update}")
    try:
        async with httpx.AsyncClient(verify=False) as client:
            response = await client.put(update_user_url, json=user_representation_update, headers=headers)
            response.raise_for_status()
            logger.info(f"Successfully updated attributes for user {user_id}.")
            return True
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error while updating user attributes for {user_id}: {e.response.status_code} - {e.response.text[:200]}", exc_info=True)
    except Exception:
        logger.exception(f"Unexpected error while updating user attributes for {user_id}.")
    return False

async def get_user_keycloak_groups(user_id: str, settings: Settings) -> Optional[List[Dict[str, Any]]]:
    """Kullanıcının üye olduğu grupları getirir."""
    admin_token = await get_admin_api_token(settings)
    if not admin_token: return None
        
    groups_url = f"{settings.keycloak.admin_api_realm_url}/users/{user_id}/groups"
    headers = {"Authorization": f"Bearer {admin_token}"}

    logger.debug(f"Fetching groups for user ID '{user_id}'")
    try:
        async with httpx.AsyncClient(verify=False) as client:
            response = await client.get(groups_url, headers=headers)
            response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error while fetching groups for user {user_id}: {e.response.status_code} - {e.response.text[:200]}", exc_info=True)
    except Exception:
        logger.exception(f"Unexpected error while fetching groups for user {user_id}.")
    return None

async def remove_user_from_keycloak_group(user_id: str, group_id: str, settings: Settings) -> bool:
    """Bir kullanıcıyı bir gruptan çıkarır."""
    admin_token = await get_admin_api_token(settings)
    if not admin_token: return False

    remove_from_group_url = f"{settings.keycloak.admin_api_realm_url}/users/{user_id}/groups/{group_id}"
    headers = {"Authorization": f"Bearer {admin_token}"}

    logger.info(f"Removing user '{user_id}' from group '{group_id}'")
    try:
        async with httpx.AsyncClient(verify=False) as client:
            response = await client.delete(remove_from_group_url, headers=headers)
            response.raise_for_status()
            logger.info(f"Successfully removed user '{user_id}' from group '{group_id}'.")
            return True
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error while removing user {user_id} from group {group_id}: {e.response.status_code} - {e.response.text[:200]}", exc_info=True)
    except Exception:
        logger.exception(f"Unexpected error while removing user {user_id} from group {group_id}.")
    return False

async def set_user_realm_roles(user_id: str, new_role_names: List[str], settings: Settings) -> bool:
    """Kullanıcının realm rollerini günceller."""
    admin_token = await get_admin_api_token(settings)
    if not admin_token: return False

    headers = {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}
    
    try:
        async with httpx.AsyncClient(verify=False) as client:
            all_roles_url = f"{settings.keycloak.admin_api_realm_url}/roles"
            roles_response = await client.get(all_roles_url, headers=headers)
            roles_response.raise_for_status()
            available_roles_map = {role['name']: role for role in roles_response.json()}

            user_roles_url = f"{settings.keycloak.admin_api_realm_url}/users/{user_id}/role-mappings/realm"
            user_roles_response = await client.get(user_roles_url, headers=headers)
            user_roles_response.raise_for_status()
            current_user_roles_set = {role['name'] for role in user_roles_response.json()}

            new_roles_set = set(new_role_names)
            roles_to_add = new_roles_set - current_user_roles_set
            roles_to_remove = current_user_roles_set - new_roles_set

            if roles_to_remove:
                roles_to_remove_reps = [available_roles_map[name] for name in roles_to_remove if name in available_roles_map]
                if roles_to_remove_reps:
                    logger.info(f"Removing roles {list(roles_to_remove)} from user {user_id}.")
                    delete_response = await client.request("DELETE", user_roles_url, headers=headers, json=roles_to_remove_reps)
                    delete_response.raise_for_status()

            if roles_to_add:
                roles_to_add_reps = [available_roles_map[name] for name in roles_to_add if name in available_roles_map]
                if roles_to_add_reps:
                    logger.info(f"Adding roles {list(roles_to_add)} to user {user_id}.")
                    add_response = await client.post(user_roles_url, headers=headers, json=roles_to_add_reps)
                    add_response.raise_for_status()
        return True
    except Exception:
        logger.exception(f"Failed to set realm roles for user {user_id}.")
        return False

async def update_keycloak_group(group_id: str, new_name: str, settings: Settings) -> bool:
    """Bir Keycloak grubunu günceller."""
    admin_token = await get_admin_api_token(settings)
    if not admin_token: return False

    group_url = f"{settings.keycloak.admin_api_realm_url}/groups/{group_id}"
    headers = {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}

    try:
        async with httpx.AsyncClient(verify=False) as client:
            response_get = await client.get(group_url, headers={"Authorization": f"Bearer {admin_token}"})
            response_get.raise_for_status()
            current_group_representation = response_get.json()
            
            updated_group_representation = current_group_representation.copy()
            updated_group_representation["name"] = new_name
            
            logger.info(f"Updating Keycloak group {group_id} name to '{new_name}'.")
            response_put = await client.put(group_url, json=updated_group_representation, headers=headers)
            response_put.raise_for_status()
        return True
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error while updating Keycloak group {group_id}: {e.response.status_code} - {e.response.text[:200]}", exc_info=True)
    except Exception:
        logger.exception(f"Unexpected error while updating Keycloak group {group_id}.")
    return False

async def delete_keycloak_group(group_id: str, settings: Settings) -> bool:
    """Bir Keycloak grubunu siler."""
    admin_token = await get_admin_api_token(settings)
    if not admin_token: return False

    delete_group_url = f"{settings.keycloak.admin_api_realm_url}/groups/{group_id}"
    headers = {"Authorization": f"Bearer {admin_token}"}

    logger.info(f"Deleting Keycloak group ID '{group_id}'")
    try:
        async with httpx.AsyncClient(verify=False) as client:
            response = await client.delete(delete_group_url, headers=headers)
            if response.status_code in [204, 404]:
                logger.info(f"Keycloak group {group_id} deleted or was not found.")
                return True
            response.raise_for_status()
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error while deleting Keycloak group {group_id}: {e.response.status_code} - {e.response.text[:200]}", exc_info=True)
    except Exception:
        logger.exception(f"Unexpected error while deleting Keycloak group {group_id}.")
    return False

async def get_all_keycloak_groups_paginated(settings: Settings) -> Optional[List[Dict[str, Any]]]:
    """Tüm Keycloak gruplarını sayfalama yaparak çeker."""
    admin_token = await get_admin_api_token(settings)
    if not admin_token: return None

    all_groups, first, max_results = [], 0, 100
    groups_url = f"{settings.keycloak.admin_api_realm_url}/groups"
    headers = {"Authorization": f"Bearer {admin_token}"}

    logger.info("Fetching all groups from Keycloak with pagination.")
    async with httpx.AsyncClient(verify=False) as client:
        while True:
            try:
                params = {"first": first, "max": max_results, "briefRepresentation": "false"}
                response = await client.get(groups_url, headers=headers, params=params)
                response.raise_for_status()
                groups_page = response.json()
                if not groups_page:
                    break
                all_groups.extend(groups_page)
                first += max_results
            except Exception:
                logger.exception(f"Failed to fetch group page starting from index {first}.")
                return None
    logger.info(f"Successfully fetched a total of {len(all_groups)} groups from Keycloak.")
    return all_groups