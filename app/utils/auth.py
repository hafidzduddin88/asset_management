from datetime import datetime, timezone
from fastapi import Depends, HTTPException, status, Request
from jose import jwt, jwk
from jose.exceptions import JWTError
from typing import Optional, List
import requests

from app.database.models import Profile, UserRole
from app.config import load_config

config = load_config()

JWKS_URL = f"{config.SUPABASE_URL}/auth/v1/.well-known/jwks.json"
REST_API_URL = f"{config.SUPABASE_URL}/rest/v1"
SUPABASE_API_KEY = config.SUPABASE_ANON_KEY

_jwks_cache: Optional[dict] = None

def get_jwks() -> dict:
    """Fetch JWKS from Supabase (cached)"""
    global _jwks_cache
    if _jwks_cache is None:
        resp = requests.get(JWKS_URL)
        resp.raise_for_status()
        _jwks_cache = resp.json()
    return _jwks_cache

def decode_supabase_token(token: str) -> Optional[dict]:
    """Decode and verify Supabase JWT token using JWKS"""
    try:
        headers = jwt.get_unverified_header(token)
        kid = headers.get("kid")
        alg = headers.get("alg", "ES256")
        jwks = get_jwks()

        key_data = None
        if kid:
            key_data = next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)

        if not key_data:
            # Try all keys if no match
            for key in jwks.get("keys", []):
                try:
                    test_key = jwk.construct(key)
                    jwt.decode(token, test_key, algorithms=[alg])
                    key_data = key
                    break
                except Exception:
                    continue

        if not key_data:
            return None

        public_key = jwk.construct(key_data)
        return jwt.decode(token, public_key, algorithms=[alg])

    except (JWTError, Exception):
        return None

def get_token_from_request(request: Request) -> Optional[str]:
    """Extract JWT from Authorization header or cookie"""
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header.split(" ", 1)[1]
    return request.cookies.get("sb_access_token")

def get_current_profile(request: Request) -> Profile:
    """Decode token and fetch user profile from Supabase"""
    token = get_token_from_request(request)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    payload = decode_supabase_token(token)
    if not payload or "sub" not in payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    user_id = payload.get("sub")

    try:
        url = f"{REST_API_URL}/profiles?auth_user_id=eq.{user_id}&select=*"
        headers = {
            "apikey": SUPABASE_API_KEY,
            "Authorization": f"Bearer {SUPABASE_API_KEY}",
            "Accept": "application/json"
        }

        res = requests.get(url, headers=headers)
        res.raise_for_status()
        data = res.json()

        if not data or not data[0].get("is_active"):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not active or not found")

        profile_data = data[0]

        profile = Profile()
        profile.id = profile_data.get("id")
        profile.auth_user_id = profile_data.get("auth_user_id")
        profile.email = profile_data.get("email")
        profile.full_name = profile_data.get("full_name")
        profile.role = UserRole(profile_data.get("role"))
        profile.is_active = profile_data.get("is_active")
        profile.photo_url = profile_data.get("photo_url")

        return profile

    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Failed to fetch user profile")

def require_roles(allowed_roles: List[UserRole]):
    """Dependency to restrict routes to specific roles"""
    def role_checker(current_profile: Profile = Depends(get_current_profile)) -> Profile:
        if current_profile.role not in allowed_roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")
        return current_profile
    return role_checker

def get_admin_user(current_profile: Profile = Depends(get_current_profile)) -> Profile:
    """Shortcut to restrict to ADMIN only"""
    if current_profile.role != UserRole.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")
    return current_profile