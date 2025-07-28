from jose import jwt, JWTError
from fastapi import Request
from fastapi.responses import RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware
from urllib.parse import quote
import logging
from app.config import load_config

config = load_config()

class SessionAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Path yang tidak butuh autentikasi
        public_paths = [
            "/login", "/login/token", "/health",
            "/static", "/favicon.ico", "/manifest.json", "/service-worker.js"
        ]
        if any(request.url.path.startswith(p) for p in public_paths):
            return await call_next(request)

        # Ambil token dari cookie atau header
        token = request.cookies.get("access_token") or request.headers.get("Authorization", "").replace("Bearer ", "")

        if not token:
            return RedirectResponse(url=f"/login?next={quote(str(request.url))}")

        try:
            # Decode Supabase JWT
            payload = jwt.decode(token, config.SECRET_KEY, algorithms=["HS256"])
            # Pastikan ada sub (user_id)
            if "sub" not in payload:
                raise JWTError("Missing sub claim")
            # Simpan user info di request.state
            request.state.user = {
                "id": payload.get("sub"),
                "email": payload.get("email"),
                "role": payload.get("role", "staff")  # default staff
            }
        except JWTError as e:
            logging.error(f"JWT decode error: {str(e)}")
            return RedirectResponse(url=f"/login?next={quote(str(request.url))}")

        return await call_next(request)