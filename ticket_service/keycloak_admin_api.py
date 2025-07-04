# ticket_service/keycloak_admin_api.py
import logging
import httpx
import uuid
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta

from .config import Settings

logger = logging.getLogger("ticket_service")

_admin_token_cache: Dict[str, Any] = {
    "token": None,
    "expires_at": datetime.utcnow()
}
_group_id_cache: Dict[str, uuid.UUID] = {}

async def get_keycloak_admin_token(settings: Settings) -> Optional[str]:
    """Keycloak Admin API'si için token alır ve cache'ler."""
    global _admin_token_cache

    if _admin_token_cache["token"] and _admin_token_cache["expires_at"] > datetime.utcnow() + timedelta(seconds=30):
        logger.debug("Using cached Keycloak admin token.")
        return _admin_token_cache["token"]

    if not all([settings.keycloak.admin_api_token_endpoint, settings.keycloak.admin_client_id, settings.keycloak.admin_client_secret]):
        logger.error("Admin API token endpoint, client ID, or secret is not configured.")
        return None

    payload = {
        "grant_type": "client_credentials",
        "client_id": settings.keycloak.admin_client_id,
        "client_secret": settings.keycloak.admin_client_secret,
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    logger.info(f"Requesting new admin token from {settings.keycloak.admin_api_token_endpoint}")
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(settings.keycloak.admin_api_token_endpoint, data=payload, headers=headers)
            response.raise_for_status()
            token_data = response.json()
            
            access_token = token_data.get("access_token")
            expires_in = token_data.get("expires_in", 300) 

            _admin_token_cache["token"] = access_token
            _admin_token_cache["expires_at"] = datetime.utcnow() + timedelta(seconds=expires_in)
            
            logger.info("New admin token obtained and cached.")
            return access_token
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error while getting admin token: {e.response.status_code} - {e.response.text}", exc_info=True)
    except Exception:
        logger.exception("Unexpected error while getting admin token.")
    
    _admin_token_cache["token"] = None 
    return None


async def get_group_id_from_path(group_path_from_token: str, settings: Settings) -> Optional[uuid.UUID]:
    """Verilen grup yolundan grubun UUID'sini alır."""
    global _group_id_cache
    
    normalized_token_path = group_path_from_token
    if normalized_token_path:
        while normalized_token_path.startswith("//"):
            normalized_token_path = normalized_token_path[1:]
        if not normalized_token_path.startswith("/") and normalized_token_path:
            normalized_token_path = "/" + normalized_token_path
    
    group_name_for_search = normalized_token_path.lstrip("/") if normalized_token_path else ""

    if not group_name_for_search:
        logger.error(f"Invalid group path provided: '{group_path_from_token}'")
        return None

    cache_key = normalized_token_path 
    if cache_key in _group_id_cache:
        logger.debug(f"Using cached group ID for normalized path: {cache_key}")
        return _group_id_cache[cache_key]

    admin_token = await get_keycloak_admin_token(settings)
    if not admin_token: return None

    if not settings.keycloak.admin_api_realm_url:
        logger.error("admin_api_realm_url is not configured.")
        return None
            
    lookup_url = f"{settings.keycloak.admin_api_realm_url}/groups?search={group_name_for_search}&exact=true&briefRepresentation=false"
    headers = {"Authorization": f"Bearer {admin_token}"}

    logger.info(f"Looking up group ID for name '{group_name_for_search}' at {lookup_url}")
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(lookup_url, headers=headers)
            response.raise_for_status()
            groups_list: List[Dict[str, Any]] = response.json()
            
            target_group_details: Optional[Dict[str, Any]] = None

            if groups_list and isinstance(groups_list, list):
                for group_data in groups_list:
                    retrieved_kc_path = group_data.get("path", "")
                    if retrieved_kc_path == normalized_token_path:
                        target_group_details = group_data
                        logger.debug(f"Matched group by path: Token Path='{normalized_token_path}', KC Path='{retrieved_kc_path}'")
                        break 
            
            if target_group_details:
                group_id_str = target_group_details.get("id")
                if group_id_str:
                    try:
                        group_uuid = uuid.UUID(group_id_str)
                        _group_id_cache[cache_key] = group_uuid 
                        logger.info(f"Group ID '{group_uuid}' for path '{cache_key}' found and cached.")
                        return group_uuid
                    except ValueError:
                        logger.error(f"Retrieved group ID '{group_id_str}' is not a valid UUID.")
                        return None
                else:
                    logger.error(f"Group '{group_name_for_search}' found, but response is missing the 'id' field.", extra={"group_details": target_group_details})
                    return None
            else: 
                logger.warning(f"Group with name '{group_name_for_search}' and path '{cache_key}' was not found in Keycloak.", extra={"search_results": groups_list})
                return None

    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error while getting group ID: {e.response.status_code} - {e.response.text[:200]}", exc_info=True)
    except Exception:
        logger.exception("Unexpected error while getting group ID.")
            
    return None
