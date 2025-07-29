from datetime import datetime, timezone
from fastapi import Depends, HTTPException, status, Request
from jose import JWTError, jwt
from supabase import create_client, Client
from typing import Optional, List

from app.database.models import Profile, UserRole
from app.config import load_config

config = load_config()
ALGORITHM = "HS256"
supabase: Client = create_client(config.SUPABASE_URL, config.SUPABASE_ANON_KEY)

def decode_supabase_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, config.SUPABASE_JWT_SECRET, algorithms=[ALGORITHM])
    except JWTError:
        return None

def get_token_from_request(request: Request) -> Optional[str]:
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header.split(" ", 1)[1]
    return request.cookies.get("access_token")

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