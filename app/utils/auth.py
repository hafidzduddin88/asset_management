from datetime import datetime, timezone
from fastapi import Request, HTTPException, status, Depends
from jose import jwt, jwk
from jose.exceptions import JWTError
from supabase import create_client, Client
from typing import Optional, List
import requests
import logging

from app.database.models import Profile, UserRole
from app.schemas.profile import ProfileResponse
from app.config import load_config

config = load_config()
supabase: Client = create_client(config.SUPABASE_URL, config.SUPABASE_ANON_KEY)

# JWKS cache
_jwks_cache: Optional[dict] = None
_jwks_cache_time: Optional[datetime] = None
JWKS_CACHE_TTL = 300  # seconds (5 minutes)

def get_jwks() -> dict:
    """Fetch JWKS keys with caching."""
    global _jwks_cache, _jwks_cache_time

    now = datetime.now()
    if _jwks_cache is None or (_jwks_cache_time and (now - _jwks_cache_time).total_seconds() > JWKS_CACHE_TTL):
        try:
            jwks_url = f"{config.SUPABASE_URL}/auth/v1/.well-known/jwks.json"
            resp = requests.get(jwks_url, timeout=10)
            resp.raise_for_status()
            new_jwks = resp.json()

            if _jwks_cache and _jwks_cache != new_jwks:
                old_kids = [k.get('kid') for k in _jwks_cache.get('keys', [])]
                new_kids = [k.get('kid') for k in new_jwks.get('keys', [])]
                logging.info(f"JWKS keys updated: {old_kids} -> {new_kids}")
            else:
                logging.info("JWKS cache updated")

            _jwks_cache = new_jwks
            _jwks_cache_time = now
        except Exception as e:
            logging.error(f"Failed to fetch JWKS: {e}")
            if _jwks_cache is None:
                raise

    return _jwks_cache

def decode_supabase_jwt(token: str) -> Optional[dict]:
    """Decode Supabase JWT using ES256 with public key (JWKS)."""
    try:
        headers = jwt.get_unverified_header(token)
        kid = headers.get("kid")
        alg = headers.get("alg", "ES256")

        if alg != "ES256":
            logging.error(f"Unsupported JWT alg: {alg}. Only ES256 is allowed.")
            return None

        jwks = get_jwks()
        keys = jwks.get("keys", [])
        if not keys:
            logging.error("No JWKS keys available")
            return None

        key_data = next((k for k in keys if k.get("kid") == kid), None)
        if not key_data:
            logging.error(f"No key found for kid: {kid}")
            return None

        public_key = jwk.construct(key_data)
        payload = jwt.decode(
            token,
            public_key,
            algorithms=["ES256"],
            options={"verify_aud": False}  # Disable audience check
        )

        # Validate expiration
        exp = payload.get("exp")
        if exp and datetime.fromtimestamp(exp, tz=timezone.utc) < datetime.now(tz=timezone.utc):
            logging.warning(f"Token expired for user {payload.get('sub')}")
            return None

        logging.info(f"Successfully decoded token for user {payload.get('sub')}")
        return payload

    except JWTError as e:
        logging.error(f"JWT decode error: {e}")
        return None
    except Exception as e:
        logging.error(f"Unexpected JWT error: {e}")
        return None

def refresh_supabase_token(refresh_token: str) -> Optional[dict]:
    """Refresh access/refresh tokens using Supabase API."""
    try:
        url = f"{config.SUPABASE_URL}/auth/v1/token?grant_type=refresh_token"
        headers = {
            "apikey": config.SUPABASE_ANON_KEY,
            "Content-Type": "application/json"
        }
        payload = {"refresh_token": refresh_token}

        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()

        return {
            "access_token": data["access_token"],
            "refresh_token": data.get("refresh_token", refresh_token),
            "expires_at": data.get("expires_at")
        }
    except Exception as e:
        logging.error(f"Token refresh failed: {e}")
        return None

def get_current_profile(request: Request) -> ProfileResponse:
    """Get current authenticated user's profile."""
    if not hasattr(request.state, 'user') or not request.state.user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )

    user_id = request.state.user.get("id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user session"
        )

    try:
        response = supabase.table("profiles").select("*").eq("id", user_id).execute()
        
        # If profile doesn't exist, create it
        if not response.data:
            # Get user email from request state
            user_email = request.state.user.get("email", "unknown@example.com")
            
            # Create profile with basic data
            profile_data = {
                "id": user_id,
                "username": user_email,
                "full_name": "",
                "role": "staff",
                "is_active": True
            }
            supabase.table("profiles").insert(profile_data).execute()
            response = supabase.table("profiles").select("*").eq("id", user_id).execute()
        
        if not response.data or not response.data[0].get("is_active"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not active or not found"
            )

        profile_data = response.data[0]
        return ProfileResponse(
            id=str(profile_data.get("id")),
            auth_user_id=str(profile_data.get("id")),  # Use id as auth_user_id
            email=profile_data.get("username"),  # username is email
            full_name=profile_data.get("full_name"),
            role=UserRole(profile_data.get("role", "staff")),
            is_active=profile_data.get("is_active", True),
            photo_url=None  # No photo_url in schema
        )

    except Exception as e:
        logging.error(f"Failed to get user profile: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Failed to get user profile"
        )

def require_roles(allowed_roles: List[UserRole]):
    """Check if current profile has one of the allowed roles."""
    def role_checker(current_profile: ProfileResponse = Depends(get_current_profile)) -> ProfileResponse:
        if current_profile.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not enough permissions"
            )
        return current_profile
    return role_checker

def get_admin_user(current_profile: ProfileResponse = Depends(get_current_profile)) -> ProfileResponse:
    if current_profile.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_profile

def get_manager_user(current_profile: ProfileResponse = Depends(get_current_profile)) -> ProfileResponse:
    if current_profile.role not in [UserRole.ADMIN, UserRole.MANAGER]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Manager access required"
        )
    return current_profile
