from fastapi import Request
from fastapi.responses import RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware
from app.utils.auth import decode_supabase_jwt, refresh_supabase_token
from app.config import load_config
import logging
from urllib.parse import quote
from datetime import datetime, timezone

config = load_config()

class SessionAuthMiddleware(BaseHTTPMiddleware):
    """Minimal session auth middleware for JWT token management"""
    
    SKIP_PATHS = {
        "/login", "/signup", "/health", "/favicon.ico",
        "/auth/callback", "/auth/confirm", "/auth/refresh", "/auth/forgot-password"
    }
    
    SKIP_PREFIXES = {"/static"}
    
    async def dispatch(self, request: Request, call_next):
        # Skip auth for public paths
        if request.url.path in self.SKIP_PATHS:
            return await call_next(request)
            
        # Skip auth for static files
        if any(request.url.path.startswith(prefix) for prefix in self.SKIP_PREFIXES):
            return await call_next(request)
        
        if request.method in ["HEAD", "OPTIONS"]:
            return await call_next(request)
        
        # Get tokens
        access_token = request.cookies.get("sb_access_token")
        refresh_token = request.cookies.get("sb_refresh_token")
        
        if not access_token and not refresh_token:
            return RedirectResponse(f"/login?next={quote(request.url.path)}", status_code=303)
        
        user_info = None
        new_tokens = None
        
        # Validate access token
        if access_token:
            payload = decode_supabase_jwt(access_token)
            if payload:
                user_info = {
                    "id": payload.get("sub"),
                    "email": payload.get("email", ""),
                    "exp": payload.get("exp")
                }
                
                # Check if token expires soon (5 minutes)
                exp = payload.get("exp")
                if exp and refresh_token:
                    exp_time = datetime.fromtimestamp(exp, tz=timezone.utc)
                    now = datetime.now(tz=timezone.utc)
                    if (exp_time - now).total_seconds() < 300:
                        new_tokens = refresh_supabase_token(refresh_token)
                        if new_tokens:
                            new_payload = decode_supabase_jwt(new_tokens["access_token"])
                            if new_payload:
                                user_info = {
                                    "id": new_payload.get("sub"),
                                    "email": new_payload.get("email", ""),
                                    "exp": new_payload.get("exp")
                                }
        
        # Try refresh if no valid access token
        if not user_info and refresh_token:
            new_tokens = refresh_supabase_token(refresh_token)
            if new_tokens:
                payload = decode_supabase_jwt(new_tokens["access_token"])
                if payload:
                    user_info = {
                        "id": payload.get("sub"),
                        "email": payload.get("email", ""),
                        "exp": payload.get("exp")
                    }
        
        # Redirect if no valid user
        if not user_info or not user_info.get("id"):
            return RedirectResponse(f"/login?next={quote(request.url.path)}", status_code=303)
        
        # Set user in request state
        request.state.user = user_info
        
        # Process request
        response = await call_next(request)
        
        # Update cookies if tokens refreshed
        if new_tokens:
            is_secure = not config.APP_URL.startswith("http://localhost")
            
            response.set_cookie(
                key="sb_access_token",
                value=new_tokens["access_token"],
                httponly=True,
                secure=is_secure,
                samesite="lax",
                max_age=3600
            )
            
            response.set_cookie(
                key="sb_refresh_token", 
                value=new_tokens["refresh_token"],
                httponly=True,
                secure=is_secure,
                samesite="lax",
                max_age=86400 * 30
            )
        
        return response