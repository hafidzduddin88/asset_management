# app/config.py
import os
import json
from typing import Dict, Optional
from functools import lru_cache

class Config:
    def __init__(self):
        # Centralized configuration retrieval
        self._validate_critical_configs()

    def _validate_critical_configs(self):
        """Validate critical configuration parameters"""
        critical_configs = [
            'SUPABASE_URL', 
            'SUPABASE_ANON_KEY', 
            'SUPABASE_SERVICE_KEY',
            'DATABASE_URL'
        ]
        
        for config in critical_configs:
            if not os.getenv(config):
                raise ValueError(f"Critical configuration {config} is not set in environment")

    @property
    def GOOGLE_SHEET_ID(self) -> str:
        return os.getenv("GOOGLE_SHEET_ID", "")
    
    @property
    def DATABASE_URL(self) -> str:
        """
        Convert postgres:// to postgresql:// for compatibility
        Render.com typically provides DATABASE_URL
        """
        db_url = os.getenv("DATABASE_URL", "")
        if not db_url:
            raise ValueError("DATABASE_URL is not set in environment")
        return db_url.replace("postgres://", "postgresql://", 1)

    @property
    def SUPABASE_URL(self) -> str:
        """Supabase Project URL from Render.com environment"""
        url = os.getenv("SUPABASE_URL")
        if not url:
            raise ValueError("SUPABASE_URL is not set in environment")
        return url

    @property
    def SUPABASE_ANON_KEY(self) -> str:
        """Supabase Anonymous Key from Render.com environment"""
        key = os.getenv("SUPABASE_ANON_KEY")
        if not key:
            raise ValueError("SUPABASE_ANON_KEY is not set in environment")
        return key

    @property
    def SUPABASE_SERVICE_KEY(self) -> str:
        """Supabase Service Role Key from Render.com environment"""
        key = os.getenv("SUPABASE_SERVICE_KEY")
        if not key:
            raise ValueError("SUPABASE_SERVICE_KEY is not set in environment")
        return key

    @property
    def SUPABASE_JWT_SECRET(self) -> str:
        """JWT Secret Key from Render.com environment"""
        secret = os.getenv("SUPABASE_JWT_SECRET")
        if not secret:
            raise ValueError("SUPABASE_JWT_SECRET is not set in environment")
        return secret

    @property
    def APP_URL(self) -> str:
        """Application URL for external services"""
        return os.getenv("APP_URL", "http://localhost:8000")

    @property
    def GOOGLE_CREDS_JSON(self) -> Dict:
        """
        Load Google credentials from environment variable
        Handles newline and escape character processing
        """
        creds_json_str = os.getenv("GOOGLE_CREDS_JSON")
        if not creds_json_str:
            raise ValueError("GOOGLE_CREDS_JSON not set in environment")

        try:
            creds_json = json.loads(creds_json_str)
            
            # Special handling for private key newlines
            if "private_key" in creds_json:
                private_key = creds_json["private_key"]
                # Replace escaped newlines with actual newlines
                private_key = private_key.replace('\\n', '\n').replace('\\\\n', '\n')
                creds_json["private_key"] = private_key
            
            return creds_json
        except json.JSONDecodeError:
            raise ValueError("Invalid JSON format for GOOGLE_CREDS_JSON")

    def validate(self) -> bool:
        """
        Comprehensive configuration validation
        Useful for pre-deployment checks
        """
        try:
            # Attempt to access all critical properties
            _ = [
                self.SUPABASE_URL, 
                self.SUPABASE_ANON_KEY, 
                self.SUPABASE_SERVICE_KEY,
                self.DATABASE_URL,
                self.GOOGLE_CREDS_JSON
            ]
            return True
        except ValueError:
            return False

@lru_cache(maxsize=1)
def load_config() -> Config:
    """
    Cached configuration loader
    Ensures only one instance of Config is created
    """
    config = Config()
    if not config.validate():
        raise RuntimeError("Configuration validation failed")
    return config
