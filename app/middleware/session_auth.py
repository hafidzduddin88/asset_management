from fastapi import Request
from fastapi.responses import RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware
from supabase import create_client, Client
from app.config import load_config
from jose import jwt, jwk
from jose.exceptions import JWTError
from jose.utils import base64url_decode
import requests
import logging
from urllib.parse import quote
from datetime import datetime, timezone
from typing import Optional

config = load_config()
supabase: Client = create_client(config.SUPABASE_URL, config.SUPABASE_ANON_KEY)

# Optional: cache JWKS for 5 minutes (can be improved with TTL or async caching lib)
_cached_jwks: Optional[dict] = None

def get_jwks():
    global _cached_jwks
    if _cached_jwks is None:
        jwks_url = f"{config.SUPABASE_URL}/auth/v1/.well-known/jwks.json"
        resp = requests.get(jwks_url)
        resp.raise_for_status()
        _cached_jwks = resp.json()
    return _cached_jwks

def decode_supabase_jwt(token: str) -> dict:
    try:
        headers = jwt.get_unverified_header(token)
        kid = headers.get("kid")
        alg = headers.get("alg", "ES256")

        jwks = get_jwks()
        
        # Find key by kid - must match exactly
        key_data = None
        if kid:
            for key in jwks.get("keys", []):
                if key.get("kid") == kid:
                    key_data = key
                    break
        
        # If no kid match, try all keys until one works
        if not key_data:
            logging.warning(f"Kid {kid} not found, trying all available keys")
            for key in jwks.get("keys", []):
                try:
                    test_key = jwk.construct(key)
                    jwt.decode(token, test_key, algorithms=[alg])
                    key_data = key
                    logging.info(f"Found working key: {key.get('kid')}")
                    break
                except:
                    continue
        
        if not key_data:
            raise Exception("No suitable key found in JWKS")

        public_key = jwk.construct(key_data)
        return jwt.decode(token, public_key, algorithms=[alg])
        
    except Exception as e:
        logging.error(f"JWT decode error: {str(e)}")
        raise

class SessionAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Skip authentication for selected paths
        if (
            request.url.path.startswith("/static")
            or request.url.path in [
                "/login", "/health", "/offline",
                "/service-worker.js", "/manifest.json", "/favicon.ico"
            ]
            or request.method == "HEAD"
            or (request.url.path == "/login" and request.method == "POST")
        ):
            return await call_next(request)

        token = request.cookies.get("sb_access_token")
        if not token:
            return RedirectResponse(
                url=f"/login?next={quote(str(request.url.path + '?' + str(request.query_params) if request.query_params else request.url.path))}",
                status_code=303
            )

        try:
            payload = decode_supabase_jwt(token)

            # Optional expiry check
            exp = payload.get("exp")
            if exp and datetime.fromtimestamp(exp, tz=timezone.utc) < datetime.now(tz=timezone.utc):
                raise Exception("Token expired")

            user_id = payload.get("sub")
            if not user_id:
                raise Exception("Invalid token")

            request.state.user = {
                "id": user_id,
                "email": payload.get("email", "")
            }

        except Exception as e:
            logging.error(f"Auth middleware error: {str(e)}")
            return RedirectResponse(
                url=f"/login?next={quote(str(request.url.path))}",
                status_code=303
            )

        return await call_next(request)
