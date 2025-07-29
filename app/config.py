# app/config.py
import os
import json
from typing import Dict, Protocol
from functools import lru_cache

class ConfigProtocol(Protocol):
    SUPABASE_URL: str
    SUPABASE_ANON_KEY: str

class Config:
    @property
    def SUPABASE_URL(self) -> str:
        url = os.getenv("SUPABASE_URL")
        if not url:
            raise RuntimeError("SUPABASE_URL is not set in environment")
        return url

    @property
    def SUPABASE_ANON_KEY(self) -> str:
        key = os.getenv("SUPABASE_ANON_KEY")
        if not key:
            raise RuntimeError("SUPABASE_ANON_KEY is not set in environment")
        return key

    @property
    def SUPABASE_SERVICE_KEY(self) -> str:
        key = os.getenv("SUPABASE_SERVICE_KEY")
        if not key:
            raise RuntimeError("SUPABASE_SERVICE_KEY is not set in environment")
        return key

    @property
    def SUPABASE_JWT_SECRET(self) -> str:
        # Not needed for ECC P-256, but kept for compatibility
        return os.getenv("SUPABASE_JWT_SECRET", "")

    @property
    def DATABASE_URL(self) -> str:
        db_url = os.getenv("DATABASE_URL")
        if not db_url:
            raise RuntimeError("DATABASE_URL is not set in environment")
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)
        return db_url

    @property
    def GOOGLE_SHEET_ID(self) -> str:
        return os.getenv("GOOGLE_SHEET_ID", "")

    @property
    def APP_URL(self) -> str:
        return os.getenv("APP_URL", "http://localhost:8000")

    @property
    def GOOGLE_CREDS_JSON(self) -> Dict:
        creds_json_str = os.getenv("GOOGLE_CREDS_JSON")
        if not creds_json_str:
            raise RuntimeError("GOOGLE_CREDS_JSON not set in environment")

        creds_json = json.loads(creds_json_str)
        if "private_key" in creds_json:
            private_key = creds_json["private_key"]
            private_key = private_key.replace('\\n', '\n').replace('\\\\n', '\n')
            creds_json["private_key"] = private_key
        return creds_json

@lru_cache(maxsize=1)
def load_config() -> Config:
    return Config()