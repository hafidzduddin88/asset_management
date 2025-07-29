from datetime import datetime, timezone
from fastapi import Depends, HTTPException, status, Request
from jose import JWTError, jwt, jwk
import requests
from supabase import create_client, Client
from typing import Optional, List

from app.database.models import Profile, UserRole
from app.config import load_config

config = load_config()
ALGORITHM = "ES256"
JWKS_URL = f"{config.SUPABASE_URL}/auth/v1/.well-known/jwks.json"
supabase: Client = create_client(config.SUPABASE_URL, config.SUPABASE_ANON_KEY)

def get_jwks():
    response = requests.get(JWKS_URL)
    return response.json()

def decode_supabase_token(token: str) -> Optional[dict]:
    try:
        # Get JWKS and find the right key
        jwks = get_jwks()
        header = jwt.get_unverified_header(token)
        kid = header.get('kid')
        
        # Find the key with matching kid
        key_data = None
        for key in jwks['keys']:
            if key['kid'] == kid:
                key_data = key
                break
        
        if not key_data:
            return None
            
        # Convert JWK to PEM format
        public_key = jwk.construct(key_data).to_pem()
        
        # Decode with ES256
        return jwt.decode(token, public_key, algorithms=[ALGORITHM])
    except Exception:
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
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    user_id: str = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

    # Set JWT token for authenticated request
    supabase.auth.set_session(token, None)
    
    # Query profiles table using Supabase
    response = supabase.table("profiles").select("*").eq("auth_user_id", user_id).execute()
    
    if not response.data or not response.data[0].get("is_active"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not active or not found")

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