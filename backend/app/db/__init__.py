"""Database access layer.

Re-exports the ORM Base, models, session factory, and the FastAPI dependency
so callers only need ``from app.db import ...``.
"""

from app.db.models import (
    AuditLog,
    Base,
    BenchmarkNote,
    CityNote,
    ColumnMapping,
    Comment,
    ConfigKV,
    HubPair,
    RoleEnum,
    SheetSnapshot,
    User,
    UserHubScope,
)
from app.db.session import get_db, get_engine, get_session_factory

__all__ = [
    "AuditLog",
    "Base",
    "BenchmarkNote",
    "CityNote",
    "ColumnMapping",
    "Comment",
    "ConfigKV",
    "HubPair",
    "RoleEnum",
    "SheetSnapshot",
    "User",
    "UserHubScope",
    "get_db",
    "get_engine",
    "get_session_factory",
]
