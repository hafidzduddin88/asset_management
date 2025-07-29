# app/config.py
import os
import json
from typing import Dict

class Config:
    def __init__(self):
        self._creds = self._load_google_creds()

    @property
    def GOOGLE_CREDS_JSON(self) -> Dict:
        return self._creds

    @property
    def GOOGLE_SHEET_ID(self) -> str:
        return os.getenv("GOOGLE_SHEET_ID", "")
    
    @property
    def DATABASE_URL(self) -> str:
        db_url = os.getenv("DATABASE_URL")
        if not db_url:
            raise RuntimeError("DATABASE_URL is not set in environment")
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)
        return db_url

    @property
    def SECRET_KEY(self) -> str:
        """JWT Secret Key (Supabase Legacy JWT Secret)"""
        secret = os.getenv("SECRET_KEY")
        if not secret:
            raise RuntimeError("SECRET_KEY is not set in environment")
        return secret

    @property
    def SUPABASE_URL(self) -> str:
        """Supabase Project URL"""
        url = os.getenv("SUPABASE_URL")
        if not url:
            raise RuntimeError("SUPABASE_URL is not set in environment")
        return url

    @property
    def SUPABASE_ANON_KEY(self) -> str:
        """Supabase Anonymous Key"""
        key = os.getenv("SUPABASE_ANON_KEY")
        if not key:
            raise RuntimeError("SUPABASE_ANON_KEY is not set in environment")
        return key

    @property
    def SUPABASE_SERVICE_KEY(self) -> str:
        """Supabase Service Role Key"""
        key = os.getenv("SUPABASE_SERVICE_KEY")
        if not key:
            raise RuntimeError("SUPABASE_SERVICE_KEY is not set in environment")
        return key

    @property
    def APP_URL(self) -> str:
        """Application URL for external services"""
        return os.getenv("APP_URL", "http://localhost:8000")
        
    def _load_google_creds(self) -> Dict:
        creds_json_str = os.getenv("GOOGLE_CREDS_JSON")
        if not creds_json_str:
            raise RuntimeError("GOOGLE_CREDS_JSON not set in environment")

        creds_json = json.loads(creds_json_str)
        if "private_key" in creds_json:
            private_key = creds_json["private_key"]
            private_key = private_key.replace('\\n', '\n').replace('\\\\n', '\n')
            creds_json["private_key"] = private_key
        return creds_json

def load_config() -> Config:
    return Config()