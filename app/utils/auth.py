from datetime import datetime, timezone
from fastapi import Depends, HTTPException, status, Request
from jose import jwt, jwk
from jose.exceptions import JWTError
from supabase import create_client, Client
from typing import Optional, List
import requests

from app.database.models import Profile, UserRole
from app.config import load_config

config = load_config()
supabase: Client = create_client(config.SUPABASE_URL, config.SUPABASE_ANON_KEY)

JWKS_URL = f"{config.SUPABASE_URL}/auth/v1/.well-known/jwks.json"
_jwks_cache: Optional[dict] = None  # simple global cache


def get_jwks() -> dict:
    global _jwks_cache
    if _jwks_cache is None:
        resp = requests.get(JWKS_URL)
        resp.raise_for_status()
        _jwks_cache = resp.json()
    return _jwks_cache


def decode_supabase_token(token: str) -> Optional[dict]:
    try:
        headers = jwt.get_unverified_header(token)
        kid = headers.get("kid")
        alg = headers.get("alg", "ES256")

        jwks = get_jwks()
        
        # Find key by kid - must match exactly
        key_data = None
        if kid:
            for key in jwks.get("keys", []):
                if key.get("kid") == kid:
                    key_data = key
                    break
        
        # If no kid match, try all keys until one works
        if not key_data:
            for key in jwks.get("keys", []):
                try:
                    test_key = jwk.construct(key)
                    jwt.decode(token, test_key, algorithms=[alg])
                    key_data = key
                    break
                except:
                    continue
        
        if not key_data:
            return None

        public_key = jwk.construct(key_data)
        payload = jwt.decode(token, public_key, algorithms=[alg])

        # Optional: check expiry
        exp = payload.get("exp")
        if exp and datetime.fromtimestamp(exp, tz=timezone.utc) < datetime.now(tz=timezone.utc):
            return None

        return payload

    except (JWTError, Exception):
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

    # Set session for supabase client (optional but may be needed)
    supabase.auth.set_session(token, None)

    # Query user profile from Supabase
    response = supabase.table("profiles").select("*").eq("auth_user_id", user_id).execute()

    if not response.data or not response.data[0].get("is_active"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not active or not found")

    profile_data = response.data[0]

    profile = Profile()
    profile.id = profile_data.get("id")
    profile.auth_user_id = profile_data.get("auth_user_id")
    profile.email = profile_data.get("email")
    profile.full_name = profile_data.get("full_name")
    profile.role = UserRole(profile_data.get("role"))
    profile.is_active = profile_data.get("is_active")
    profile.photo_url = profile_data.get("photo_url")

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
