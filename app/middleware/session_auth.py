import os
import logging
import requests
from datetime import datetime, timezone
from urllib.parse import quote_plus
from typing import Optional

from fastapi import Request
from fastapi.responses import RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware

from jose import jwt, jwk
from jose.exceptions import JWTError

from supabase import create_client, Client
from app.config import load_config

# Load config for Supabase ANON_KEY only
config = load_config()
SUPABASE_URL = os.getenv("SUPABASE_URL")
supabase: Client = create_client(SUPABASE_URL, config.SUPABASE_ANON_KEY)

# Simple JWKS cache
_jwks_cache: Optional[dict] = None

def get_jwks() -> dict:
    global _jwks_cache
    if _jwks_cache is None:
        jwks_url = f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json"
        resp = requests.get(jwks_url)
        resp.raise_for_status()
        _jwks_cache = resp.json()
    return _jwks_cache

def decode_supabase_jwt(token: str) -> dict:
    try:
        headers = jwt.get_unverified_header(token)
        kid = headers.get("kid")
        alg = headers.get("alg", "ES256")

        jwks = get_jwks()
        key_data = next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)

        # Try all keys if specific kid not found
        if not key_data:
            logging.warning(f"Kid {kid} not found in JWKS, trying fallback keys")
            for key in jwks.get("keys", []):
                try:
                    jwt.decode(token, jwk.construct(key), algorithms=[alg])
                    key_data = key
                    logging.info(f"Using fallback key kid={key.get('kid')}")
                    break
                except Exception:
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
        # Allow unauthenticated access to these paths
        public_paths = {
            "/login", "/signup", "/health", "/offline",
            "/service-worker.js", "/manifest.json", "/favicon.ico"
        }

        if (
            request.url.path.startswith("/static") or
            request.method == "HEAD" or
            request.url.path in public_paths or
            (request.url.path == "/login" and request.method == "POST")
        ):
            return await call_next(request)

        token = request.cookies.get("sb_access_token")
        if not token:
            next_path = request.url.path
            if request.query_params:
                next_path += f"?{request.query_params}"
            return RedirectResponse(
                url=f"/login?next={quote_plus(next_path)}",
                status_code=303
            )

        try:
            payload = decode_supabase_jwt(token)

            # Expiry validation
            exp = payload.get("exp")
            if exp and datetime.fromtimestamp(exp, tz=timezone.utc) < datetime.now(tz=timezone.utc):
                raise Exception("Token expired")

            user_id = payload.get("sub")
            if not user_id:
                raise Exception("Invalid token payload: no 'sub'")

            # Attach user info to request
            request.state.user = {
                "id": user_id,
                "email": payload.get("email", "")
            }

        except Exception as e:
            logging.error(f"Auth middleware error: {str(e)}")
            return RedirectResponse(
                url=f"/login?next={quote_plus(str(request.url.path))}",
                status_code=303
            )

        return await call_next(request)
