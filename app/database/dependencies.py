from fastapi import Depends, HTTPException, status, Request
from jose import jwt, JWTError
from supabase import create_client
import logging

from app.config import load_config

# Load configuration
config = load_config()

# Supabase client
supabase = create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_KEY)

def get_token_from_request(request: Request) -> str:
    """Ambil token dari cookies atau header Authorization."""
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header.split(" ", 1)[1]

    token = request.cookies.get("access_token")
    return token

async def get_current_user(request: Request) -> dict:
    """Ambil user dari Supabase JWT & tabel profiles."""
    token = get_token_from_request(request)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )

    try:
        # Decode JWT dengan Supabase JWT secret
        payload = jwt.decode(token, config.SECRET_KEY, algorithms=["HS256"])
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError as e:
        logging.error(f"JWT Error: {str(e)}")
        raise HTTPException(status_code=401, detail="Invalid token")

    # Ambil data user dari tabel profiles
    response = supabase.table("profiles").select("*").eq("auth_user_id", user_id).execute()
    if not response.data:
        raise HTTPException(status_code=404, detail="User not found")

    return response.data[0]

async def get_current_active_user(current_user: dict = Depends(get_current_user)) -> dict:
    """Pastikan user aktif (bisa ditambahkan flag is_active di profiles)."""
    # Jika ada kolom is_active di profiles:
    if "is_active" in current_user and not current_user["is_active"]:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user

async def get_admin_user(current_user: dict = Depends(get_current_user)) -> dict:
    """Hanya admin yang boleh akses."""
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    return current_user