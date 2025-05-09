# database_pkg/schemas.py
from enum import Enum

class Role(str, Enum):
    """Kullanıcı rolleri için Enum."""
    AGENT = "agent"
    EMPLOYEE = "employee"