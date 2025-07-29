import os
from datetime import datetime, timezone
from fastapi import Depends, HTTPException, status, Request
from jose import jwt, jwk
from jose.exceptions import JWTError
from supabase import create_client, Client
from typing import Optional, List
import requests
import logging

from app.database.models import Profile, UserRole
from app.config import load_config

config = load_config()  # Tetap untuk ANON_KEY
supabase: Client = create_client(os.getenv("SUPABASE_URL"), config.SUPABASE_ANON_KEY)

JWKS_URL = f"{os.getenv('SUPABASE_URL')}/auth/v1/.well-known/jwks.json"
_jwks_cache: Optional[dict] = None  # Cache sederhana JWKS

def get_jwks() -> dict:
    global _jwks_cache
    if _jwks_cache is None:
        try:
            resp = requests.get(JWKS_URL)
            resp.raise_for_status()
            _jwks_cache = resp.json()
        except Exception as e:
            logging.error(f"Failed to fetch JWKS: {e}")
            _jwks_cache = {}
    return _jwks_cache

def decode_supabase_token(token: str) -> Optional[dict]:
    try:
        headers = jwt.get_unverified_header(token)
        kid = headers.get("kid")
        alg = headers.get("alg", "ES256")
        jwks = get_jwks()

        # Cari key yang cocok dengan KID
        key_data = next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)

        if not key_data:
            logging.warning(f"Kid {kid} not found, trying all available keys")
            for key in jwks.get("keys", []):
                try:
                    test_key = jwk.construct(key)
                    jwt.decode(token, test_key, algorithms=[key.get("alg", alg)])
                    key_data = key
                    break
                except Exception:
                    continue

        if not key_data:
            raise Exception("No suitable key found in JWKS")

        public_key = jwk.construct(key_data)
        payload = jwt.decode(token, public_key, algorithms=[alg])

        # Optional: cek expired
        exp = payload.get("exp")
        if exp and datetime.fromtimestamp(exp, tz=timezone.utc) < datetime.now(tz=timezone.utc):
            return None

        return payload
    except Exception as e:
        logging.error(f"JWT decode error: {e}")
        return None

def get_token_from_request(request: Request) -> Optional[str]:
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header.split(" ", 1)[1]
    return request.cookies.get("sb_access_token")

def get_current_profile(request: Request) -> Profile:
    token = get_token_from_request(request)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    payload = decode_supabase_token(token)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    user_id: str = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

    supabase.auth.set_session(token, None)
    response = supabase.table("profiles").select("*").eq("auth_user_id", user_id).execute()

    if not response.data or not response.data[0].get("is_active"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not active or not found")

    profile_data = response.data[0]
    profile = Profile(
        id=profile_data.get("id"),
        auth_user_id=profile_data.get("auth_user_id"),
        email=profile_data.get("email"),
        full_name=profile_data.get("full_name"),
        role=UserRole(profile_data.get("role")),
        is_active=profile_data.get("is_active"),
        photo_url=profile_data.get("photo_url")
    )

    return profile

def require_roles(allowed_roles: List[UserRole]):
    def role_checker(current_profile: Profile = Depends(get_current_profile)) -> Profile:
        if current_profile.role not in allowed_roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")
        return current_profile
    return role_checker

def get_admin_user(current_profile: Profile = Depends(get_current_profile)) -> Profile:
    if current_profile.role != UserRole.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")
    return current_profile
