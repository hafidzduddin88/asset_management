from fastapi import Depends, HTTPException, status, Request
from jose import JWTError, jwt
import logging
from typing import Dict, Optional

from app.config import load_config

# Load configuration
config = load_config()

def get_token_from_request(request: Request) -> Optional[str]:
    """
    Ambil token JWT dari header Authorization atau cookie.
    """
    # Ambil dari Authorization header
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header.split(" ", 1)[1]
    
    # Ambil dari cookie
    return request.cookies.get("access_token")

def get_current_user(request: Request) -> Dict:
    """
    Decode token Supabase JWT & return user info.
    """
    token = get_token_from_request(request)

    if not token:
        logging.warning("Token tidak ditemukan dalam request")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token tidak ditemukan",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        # Decode Supabase JWT
        payload = jwt.decode(
            token,
            config.SECRET_KEY,  # Supabase JWT Secret
            algorithms=["HS256"]
        )

        user_id: str = payload.get("sub")
        role: str = payload.get("role", "user")
        email: str = payload.get("email")

        if user_id is None:
            logging.warning("sub (user_id) tidak ada di token")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
                headers={"WWW-Authenticate": "Bearer"},
            )

        return {
            "id": user_id,
            "email": email,
            "role": role
        }

    except JWTError as e:
        logging.error(f"JWT Error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )

def get_current_active_user(current_user: Dict = Depends(get_current_user)) -> Dict:
    """
    Pastikan user aktif (Supabase tidak punya flag is_active, jadi hanya cek token).
    """
    return current_user

def get_admin_user(current_user: Dict = Depends(get_current_user)) -> Dict:
    """
    Pastikan user punya role admin.
    """
    if current_user["role"] != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Anda tidak memiliki akses"
        )
    return current_user