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
        
        # Find key by kid
        key_data = None
        if kid:
            for key in jwks.get("keys", []):
                if key.get("kid") == kid:
                    key_data = key
                    break
        
        # If no kid match, try all keys until one works
        if not key_data:
            for key in jwks.get("keys", []):
                try:
                    test_key = jwk.construct(key)
                    jwt.decode(token, test_key, algorithms=[alg])
                    key_data = key
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

def refresh_access_token(refresh_token: str) -> Optional[dict]:
    """Refresh access token using refresh token"""
    try:
        response = supabase.auth.refresh_session(refresh_token)
        if response.session:
            return {
                "access_token": response.session.access_token,
                "refresh_token": response.session.refresh_token
            }
    except Exception as e:
        logging.error(f"Token refresh failed: {str(e)}")
    return None

class SessionAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Skip authentication for selected paths
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

        # Try to validate access token
        payload = None
        if access_token:
            try:
                payload = decode_supabase_jwt(access_token)
                
                # Check if token is about to expire (within 5 minutes)
                exp = payload.get("exp")
                if exp:
                    exp_time = datetime.fromtimestamp(exp, tz=timezone.utc)
                    now = datetime.now(tz=timezone.utc)
                    if (exp_time - now).total_seconds() < 300:  # 5 minutes
                        # Token expiring soon, refresh it
                        if refresh_token:
                            new_tokens = refresh_access_token(refresh_token)
                            if new_tokens:
                                # Update tokens and continue
                                request.state.new_tokens = new_tokens
                                payload = decode_supabase_jwt(new_tokens["access_token"])
                            else:
                                payload = None
                        else:
                            payload = None
                            
            except Exception:
                payload = None

        # If access token invalid/expired, try refresh
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

        # Set user info
        user_id = payload.get("sub")
        if not user_id:
            return RedirectResponse(
                url=f"/login?next={quote(str(request.url.path))}", 
                status_code=303
            )

        request.state.user = {
            "id": user_id,
            "email": payload.get("email", "")
        }

        # Process request
        response = await call_next(request)

        # Update cookies if tokens were refreshed
        if hasattr(request.state, 'new_tokens'):
            new_tokens = request.state.new_tokens
            
            # Set new access token
            response.set_cookie(
                key="sb_access_token",
                value=new_tokens["access_token"],
                httponly=True,
                secure=not config.APP_URL.startswith("http://localhost"),
                samesite="lax",
                max_age=3600
            )
            
            # Set new refresh token
            response.set_cookie(
                key="sb_refresh_token", 
                value=new_tokens["refresh_token"],
                httponly=True,
                secure=not config.APP_URL.startswith("http://localhost"),
                samesite="lax",
                max_age=86400 * 30
            )

        return response