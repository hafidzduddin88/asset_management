from fastapi import Request, Response
from fastapi.responses import RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware
from supabase import create_client, Client
from app.config import load_config
from jose import jwt, jwk
from jose.exceptions import JWTError
import requests
import logging
from urllib.parse import quote
from datetime import datetime, timezone
from typing import Optional

config = load_config()
supabase: Client = create_client(config.SUPABASE_URL, config.SUPABASE_ANON_KEY)

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
        key_data = None

        # Cari key berdasarkan kid
        if kid:
            for key in jwks.get("keys", []):
                if key.get("kid") == kid:
                    key_data = key
                    break

        # Coba semua key jika kid tidak ditemukan
        if not key_data:
            for key in jwks.get("keys", []):
                try:
                    test_key = jwk.construct(key)
                    jwt.decode(token, test_key, algorithms=[alg])
                    key_data = key
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

def refresh_access_token(refresh_token: str) -> Optional[dict]:
    """Manual refresh Supabase session"""
    try:
        url = f"{config.SUPABASE_URL}/auth/v1/token?grant_type=refresh_token"
        headers = {
            "apikey": config.SUPABASE_ANON_KEY,
            "Content-Type": "application/json"
        }
        payload = {
            "refresh_token": refresh_token
        }

        res = requests.post(url, headers=headers, json=payload)
        res.raise_for_status()
        data = res.json()

        return {
            "access_token": data.get("access_token"),
            "refresh_token": data.get("refresh_token", refresh_token)
        }

    except Exception as e:
        logging.error(f"Token refresh failed: {str(e)}")
        return None

class SessionAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Bypass auth untuk path tertentu
        if (
            request.url.path.startswith("/static")
            or request.url.path in [
                "/login", "/signup", "/health", "/offline",
                "/service-worker.js", "/manifest.json", "/favicon.ico",
                "/auth/callback", "/auth/confirm"
            ]
            or request.method == "HEAD"
            or (request.url.path in ["/login", "/signup"] and request.method == "POST")
        ):
            return await call_next(request)

        access_token = request.cookies.get("sb_access_token")
        refresh_token = request.cookies.get("sb_refresh_token")

        if not access_token and not refresh_token:
            return RedirectResponse(
                url=f"/login?next={quote(str(request.url.path))}",
                status_code=303
            )

        payload = None

        # Validasi access token
        if access_token:
            try:
                payload = decode_supabase_jwt(access_token)

                # Cek apakah token hampir kedaluwarsa (< 5 menit)
                exp = payload.get("exp")
                if exp:
                    now = datetime.now(tz=timezone.utc)
                    exp_time = datetime.fromtimestamp(exp, tz=timezone.utc)
                    if (exp_time - now).total_seconds() < 300 and refresh_token:
                        new_tokens = refresh_access_token(refresh_token)
                        if new_tokens:
                            request.state.new_tokens = new_tokens
                            payload = decode_supabase_jwt(new_tokens["access_token"])
                        else:
                            payload = None
            except Exception:
                payload = None

        # Jika token tidak valid, coba refresh manual
        if not payload and refresh_token:
            new_tokens = refresh_access_token(refresh_token)
            if new_tokens:
                request.state.new_tokens = new_tokens
                try:
                    payload = decode_supabase_jwt(new_tokens["access_token"])
                except Exception:
                    payload = None

        if not payload:
            return RedirectResponse(
                url=f"/login?next={quote(str(request.url.path))}",
                status_code=303
            )

        user_id = payload.get("sub")
        if not user_id:
            return RedirectResponse(
                url=f"/login?next={quote(str(request.url.path))}",
                status_code=303
            )

        request.state.user = {
            "id": user_id,
            "email": payload.get("email") or payload.get("user_metadata", {}).get("email", "")
        }

        response = await call_next(request)

        # Perbarui cookie jika token berhasil di-refresh
        if hasattr(request.state, 'new_tokens'):
            new_tokens = request.state.new_tokens

            response.set_cookie(
                key="sb_access_token",
                value=new_tokens["access_token"],
                httponly=True,
                secure=not config.APP_URL.startswith("http://localhost"),
                samesite="lax",
                max_age=3600
            )
            response.set_cookie(
                key="sb_refresh_token",
                value=new_tokens["refresh_token"],
                httponly=True,
                secure=not config.APP_URL.startswith("http://localhost"),
                samesite="lax",
                max_age=86400 * 30
            )

        return response