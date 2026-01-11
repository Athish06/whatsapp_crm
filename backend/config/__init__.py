"""
Configuration module for the application.
"""
from config.database import Database, get_db
from config.settings import settings

__all__ = ["Database", "get_db", "settings"]
