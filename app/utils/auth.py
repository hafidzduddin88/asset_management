from datetime import datetime, timezone
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session
from typing import Optional, List

from app.database.database import get_db
from app.database.models import Profile, UserRole
from app.config import load_config

config = load_config()
ALGORITHM = "HS256"  # Supabase JWT uses HS256
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token")


# ✅ Decode Supabase JWT
def decode_supabase_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, config.SUPABASE_JWT_SECRET, algorithms=[ALGORITHM])
    except JWTError:
        return None


# ✅ Extract token (from header or cookie)
def get_token_from_request(request: Request) -> Optional[str]:
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header.split(" ", 1)[1]
    return request.cookies.get("access_token")


# ✅ Ambil profile user yang sedang login
def get_current_profile(request: Request, db: Session = Depends(get_db)) -> Profile:
    token = get_token_from_request(request)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    payload = decode_supabase_token(token)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    user_id: str = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

    profile = db.query(Profile).filter(Profile.auth_user_id == user_id).first()
    if not profile or not profile.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not active or not found")

    return profile


# ✅ Role-based access
def require_roles(allowed_roles: List[UserRole]):
    def role_checker(current_profile: Profile = Depends(get_current_profile)) -> Profile:
        if current_profile.role not in allowed_roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")
        return current_profile
    return role_checker


# ✅ Shortcuts
def get_admin_user(current_profile: Profile = Depends(get_current_profile)) -> Profile:
    if current_profile.role != UserRole.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")
    return current_profile