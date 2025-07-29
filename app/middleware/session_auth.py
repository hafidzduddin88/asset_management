from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import RedirectResponse
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp
from app.utils.auth import decode_supabase_jwt
from app.config import load_config
import logging

config = load_config()

class SessionAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        # Ambil token dari cookie
        token = request.cookies.get("sb-access-token")
        refresh_token = request.cookies.get("sb-refresh-token")

        user = None
        if token:
            payload = decode_supabase_jwt(token)
            if payload:
                user = {
                    "id": payload.get("sub"),
                    "email": payload.get("email"),
                    "role": payload.get("role"),
                    "name": payload.get("user_metadata", {}).get("full_name") or payload.get("name"),
                    "picture": payload.get("user_metadata", {}).get("avatar_url")
                }
            else:
                logging.warning("Invalid or expired JWT in cookie")

        # Simpan user di state
        request.state.user = user

        # Lanjutkan request
        response = await call_next(request)

        # Tambahkan header CORS jika perlu
        headers = MutableHeaders(response.headers)
        headers.append("Access-Control-Allow-Credentials", "true")

        return response
