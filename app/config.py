# app/config.py
import os
import json
from typing import Dict

class Config:
    def __init__(self):
        self._creds = self._load_google_creds()
        self._is_production = self._check_production_env()

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
        # Fix PostgreSQL URL format if needed (Render.com/Supabase compatibility)
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
    def SUPABASE_ANON_KEY(self) -> str:
        """Supabase Anonymous Key (optional)"""
        return os.getenv("SUPABASE_ANON_KEY", "")
    
    @property
    def SUPABASE_SERVICE_KEY(self) -> str:
        """Supabase Service Role Key (optional)"""
        return os.getenv("SUPABASE_SERVICE_KEY", "")
    
    @property
    def APP_URL(self) -> str:
        """Application URL for external services"""
        return os.getenv("APP_URL", "http://localhost:8000")
    
    @property
    def IS_PRODUCTION(self) -> bool:
        """Check if running in production environment"""
        return self._is_production
        
    def _load_google_creds(self) -> Dict:
        creds_json_str = os.getenv("GOOGLE_CREDS_JSON")
        if not creds_json_str:
            raise RuntimeError("GOOGLE_CREDS_JSON not set in environment")

        creds_json = json.loads(creds_json_str)
        if "private_key" in creds_json:
            creds_json["private_key"] = creds_json["private_key"].replace("\\\\n", "\\n")
        return creds_json
    
    def _check_production_env(self) -> bool:
        """Check if running in production environment"""
        # Check for common production environment variables
        return bool(os.getenv("RENDER") or 
                   os.getenv("PRODUCTION") or 
                   os.getenv("ENVIRONMENT") == "production" or
                   "onrender.com" in os.getenv("APP_URL", ""))

def load_config() -> Config:
    return Config()