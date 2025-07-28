# app/middleware/session_auth.py
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import RedirectResponse
from jose import jwt, JWTError
from fastapi import Request
import logging
import os

logger = logging.getLogger(__name__)

SECRET_KEY = os.getenv("SECRET_KEY")  # Supabase JWT Secret
ALGORITHM = "HS256"  # Supabase default JWT algorithm

class SessionAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Daftar path yang dilewati (tanpa auth)
        public_paths = ["/login", "/static", "/api/docs", "/api/redoc", "/health"]
        
        if any(request.url.path.startswith(path) for path in public_paths):
            return await call_next(request)

        token = request.cookies.get("access_token")

        if not token:
            logger.warning("No access token found, redirecting to login")
            return RedirectResponse(url="/login", status_code=303)

        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            username: str = payload.get("sub")
            role: str = payload.get("role")

            if username is None:
                raise JWTError("Invalid token: no username")

            # Simpan user info di request.state
            request.state.user = {
                "username": username,
                "role": role
            }

        except JWTError as e:
            logger.error(f"JWT validation error: {e}")
            return RedirectResponse(url="/login", status_code=303)

        return await call_next(request)