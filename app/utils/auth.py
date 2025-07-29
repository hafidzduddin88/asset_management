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

config = load_config()
supabase: Client = create_client(config.SUPABASE_URL, config.SUPABASE_ANON_KEY)

# JWKS cache for key rotation support
_jwks_cache: Optional[dict] = None
_jwks_cache_time: Optional[datetime] = None
JWKS_CACHE_TTL = 300  # 5 minutes

def get_jwks() -> dict:
    """Get JWKS with caching for key rotation support"""
    global _jwks_cache, _jwks_cache_time
    
    now = datetime.now()
    if _jwks_cache is None or (
        _jwks_cache_time and (now - _jwks_cache_time).total_seconds() > JWKS_CACHE_TTL
    ):
        try:
            jwks_url = f"{config.SUPABASE_URL}/auth/v1/.well-known/jwks.json"
            resp = requests.get(jwks_url, timeout=10)
            resp.raise_for_status()
            _jwks_cache = resp.json()
            _jwks_cache_time = now
        except Exception as e:
            logging.error(f"Failed to fetch JWKS: {e}")
            if _jwks_cache is None:
                raise
    
    return _jwks_cache

def decode_supabase_jwt(token: str) -> Optional[dict]:
    """Decode Supabase JWT with key rotation support"""
    try:
        # Get token header
        headers = jwt.get_unverified_header(token)
        kid = headers.get("kid")
        alg = headers.get("alg", "ES256")
        
        # Get JWKS
        jwks = get_jwks()
        keys = jwks.get("keys", [])
        
        if not keys:
            logging.error("No keys found in JWKS")
            return None
        
        # Try to find key by kid first
        key_data = None
        if kid:
            key_data = next((k for k in keys if k.get("kid") == kid), None)
        
        # If kid not found or not provided, try all keys
        if not key_data:
            for key in keys:
                try:
                    public_key = jwk.construct(key)
                    payload = jwt.decode(token, public_key, algorithms=[alg])
                    
                    # Validate expiry
                    exp = payload.get("exp")
                    if exp and datetime.fromtimestamp(exp, tz=timezone.utc) < datetime.now(tz=timezone.utc):
                        continue
                    
                    return payload
                except Exception:
                    continue
            
            logging.error("No valid key found for token")
            return None
        
        # Use found key
        try:
            public_key = jwk.construct(key_data)
            payload = jwt.decode(token, public_key, algorithms=[alg])
            
            # Validate expiry
            exp = payload.get("exp")
            if exp and datetime.fromtimestamp(exp, tz=timezone.utc) < datetime.now(tz=timezone.utc):
                return None
            
            return payload
        except Exception as e:
            logging.error(f"JWT decode failed with matched key: {e}")
            return None
            
    except Exception as e:
        logging.error(f"JWT decode error: {e}")
        return None

def refresh_supabase_token(refresh_token: str) -> Optional[dict]:
    """Refresh Supabase tokens"""
    try:
        # Set API key header
        supabase.auth._client.headers.update({
            "apikey": config.SUPABASE_ANON_KEY
        })
        
        response = supabase.auth.refresh_session(refresh_token)
        if response.session:
            return {
                "access_token": response.session.access_token,
                "refresh_token": response.session.refresh_token,
                "expires_at": response.session.expires_at
            }
    except Exception as e:
        logging.error(f"Token refresh failed: {e}")
    return None

def get_token_from_request(request: Request) -> tuple[Optional[str], Optional[str]]:
    """Get access and refresh tokens from request"""
    # Try Authorization header first
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        access_token = auth_header.split(" ", 1)[1]
        refresh_token = request.cookies.get("sb_refresh_token")
        return access_token, refresh_token
    
    # Try cookies
    access_token = request.cookies.get("sb_access_token")
    refresh_token = request.cookies.get("sb_refresh_token")
    return access_token, refresh_token

def validate_and_refresh_token(request: Request) -> Optional[dict]:
    """Validate token and refresh if needed"""
    access_token, refresh_token = get_token_from_request(request)
    
    if not access_token and not refresh_token:
        return None
    
    # Try to validate access token
    if access_token:
        payload = decode_supabase_jwt(access_token)
        if payload:
            # Check if token expires soon (within 5 minutes)
            exp = payload.get("exp")
            if exp:
                exp_time = datetime.fromtimestamp(exp, tz=timezone.utc)
                now = datetime.now(tz=timezone.utc)
                if (exp_time - now).total_seconds() < 300 and refresh_token:
                    # Token expiring soon, try to refresh
                    new_tokens = refresh_supabase_token(refresh_token)
                    if new_tokens:
                        # Store new tokens for middleware to set cookies
                        request.state.new_tokens = new_tokens
                        return decode_supabase_jwt(new_tokens["access_token"])
            
            return payload
    
    # Access token invalid/expired, try refresh
    if refresh_token:
        new_tokens = refresh_supabase_token(refresh_token)
        if new_tokens:
            request.state.new_tokens = new_tokens
            return decode_supabase_jwt(new_tokens["access_token"])
    
    return None

def get_current_profile(request: Request) -> Profile:
    """Get current user profile with token validation and refresh"""
    # First check if middleware already validated
    if hasattr(request.state, 'user') and request.state.user:
        user_id = request.state.user.get("id")
    else:
        # Validate token ourselves
        payload = validate_and_refresh_token(request)
        if not payload:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, 
                detail="Not authenticated"
            )
        
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, 
                detail="Invalid token payload"
            )
    
    # Get profile from Supabase
    try:
        # Set API key for Supabase requests
        supabase.postgrest.auth(config.SUPABASE_ANON_KEY)
        
        response = supabase.table("profiles").select("*").eq("auth_user_id", user_id).execute()
        
        if not response.data or not response.data[0].get("is_active"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, 
                detail="User not active or not found"
            )
        
        profile_data = response.data[0]
        
        # Create Profile object
        profile = Profile()
        profile.id = profile_data.get("id")
        profile.auth_user_id = profile_data.get("auth_user_id")
        profile.email = profile_data.get("email")
        profile.full_name = profile_data.get("full_name")
        profile.role = UserRole(profile_data.get("role"))
        profile.is_active = profile_data.get("is_active")
        profile.photo_url = profile_data.get("photo_url")
        
        return profile
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Failed to get user profile: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="Failed to get user profile"
        )

def require_roles(allowed_roles: List[UserRole]):
    """Decorator for role-based access control"""
    def role_checker(current_profile: Profile = Depends(get_current_profile)) -> Profile:
        if current_profile.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, 
                detail="Not enough permissions"
            )
        return current_profile
    return role_checker

def get_admin_user(current_profile: Profile = Depends(get_current_profile)) -> Profile:
    """Get current user if admin"""
    if current_profile.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="Admin access required"
        )
    return current_profile

def get_manager_user(current_profile: Profile = Depends(get_current_profile)) -> Profile:
    """Get current user if manager or admin"""
    if current_profile.role not in [UserRole.ADMIN, UserRole.MANAGER]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="Manager access required"
        )
    return current_profile