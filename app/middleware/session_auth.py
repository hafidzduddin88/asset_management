from fastapi import Request
from fastapi.responses import RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware
from supabase import create_client, Client
from app.config import load_config
from app.utils.auth import decode_supabase_jwt, refresh_supabase_token
import logging
from urllib.parse import quote
from datetime import datetime, timezone
from typing import Optional

config = load_config()
supabase: Client = create_client(config.SUPABASE_URL, config.SUPABASE_ANON_KEY)

class SessionAuthMiddleware(BaseHTTPMiddleware):
    """
    Enhanced session authentication middleware with full Supabase auth 
    and JWT key rotation support
    """
    
    # Paths that don't require authentication
    SKIP_AUTH_PATHS = {
        "/login", "/signup", "/health", "/offline", "/favicon.ico",
        "/service-worker.js", "/manifest.json", "/auth/callback", 
        "/auth/confirm", "/auth/refresh"
    }
    
    # Path prefixes that don't require authentication
    SKIP_AUTH_PREFIXES = {"/static"}
    
    def should_skip_auth(self, request: Request) -> bool:
        """Check if request should skip authentication"""
        path = request.url.path
        
        # Skip for specific paths
        if path in self.SKIP_AUTH_PATHS:
            return True
            
        # Skip for path prefixes
        if any(path.startswith(prefix) for prefix in self.SKIP_AUTH_PREFIXES):
            return True
            
        # Skip for HEAD requests
        if request.method == "HEAD":
            return True
            
        # Skip for POST to auth endpoints
        if request.method == "POST" and path in {"/login", "/signup", "/auth/confirm"}:
            return True
            
        return False
    
    def get_tokens_from_request(self, request: Request) -> tuple[Optional[str], Optional[str]]:
        """Extract access and refresh tokens from request"""
        # Try Authorization header first
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            access_token = auth_header.split(" ", 1)[1]
            refresh_token = request.cookies.get("sb_refresh_token")
            return access_token, refresh_token
        
        # Try cookies
        access_token = request.cookies.get("sb_access_token")
        refresh_token = request.cookies.get("sb_refresh_token")
        return access_token, refresh_token
    
    def create_redirect_response(self, request: Request) -> RedirectResponse:
        """Create redirect response to login page"""
        original_url = request.url.path
        if request.query_params:
            original_url += "?" + str(request.query_params)
        
        return RedirectResponse(
            url=f"/login?next={quote(original_url)}", 
            status_code=303
        )
    
    def validate_token_payload(self, payload: dict) -> Optional[dict]:
        """Validate JWT payload and extract user info"""
        if not payload:
            return None
            
        user_id = payload.get("sub")
        email = payload.get("email", "")
        
        if not user_id:
            return None
            
        # Check token expiry
        exp = payload.get("exp")
        if exp:
            exp_time = datetime.fromtimestamp(exp, tz=timezone.utc)
            now = datetime.now(tz=timezone.utc)
            if exp_time <= now:
                logging.warning(f"Token expired for user {user_id}")
                return None
        
        return {
            "id": user_id,
            "email": email,
            "exp": exp
        }
    
    def should_refresh_token(self, user_info: dict) -> bool:
        """Check if token should be refreshed (expires within 5 minutes)"""
        exp = user_info.get("exp")
        if not exp:
            return False
            
        exp_time = datetime.fromtimestamp(exp, tz=timezone.utc)
        now = datetime.now(tz=timezone.utc)
        time_until_expiry = (exp_time - now).total_seconds()
        
        # Refresh if expires within 5 minutes
        return time_until_expiry < 300
    
    def set_token_cookies(self, response, tokens: dict):
        """Set token cookies on response"""
        # Determine security settings
        is_secure = not config.APP_URL.startswith("http://localhost")
        
        # Set access token cookie
        response.set_cookie(
            key="sb_access_token",
            value=tokens["access_token"],
            httponly=True,
            secure=is_secure,
            samesite="lax",
            max_age=3600  # 1 hour
        )
        
        # Set refresh token cookie
        response.set_cookie(
            key="sb_refresh_token",
            value=tokens["refresh_token"],
            httponly=True,
            secure=is_secure,
            samesite="lax",
            max_age=86400 * 30  # 30 days
        )
    
    async def dispatch(self, request: Request, call_next):
        """Main middleware dispatch method"""
        
        # Skip authentication for certain paths
        if self.should_skip_auth(request):
            return await call_next(request)
        
        # Get tokens from request
        access_token, refresh_token = self.get_tokens_from_request(request)
        
        # If no tokens, redirect to login
        if not access_token and not refresh_token:
            logging.info("No tokens found, redirecting to login")
            return self.create_redirect_response(request)
        
        user_info = None
        new_tokens = None
        
        # Try to validate access token
        if access_token:
            try:
                payload = decode_supabase_jwt(access_token)
                user_info = self.validate_token_payload(payload)
                
                # Check if token should be refreshed proactively
                if user_info and self.should_refresh_token(user_info) and refresh_token:
                    logging.info(f"Proactively refreshing token for user {user_info['id']}")
                    new_tokens = refresh_supabase_token(refresh_token)
                    if new_tokens:
                        # Validate new access token
                        new_payload = decode_supabase_jwt(new_tokens["access_token"])
                        new_user_info = self.validate_token_payload(new_payload)
                        if new_user_info:
                            user_info = new_user_info
                        else:
                            logging.error("New access token validation failed")
                            new_tokens = None
                    else:
                        logging.error("Proactive token refresh failed")
                        
            except Exception as e:
                logging.error(f"Access token validation failed: {e}")
                user_info = None
        
        # If access token invalid/expired, try refresh token
        if not user_info and refresh_token:
            logging.info("Access token invalid, attempting refresh")
            try:
                new_tokens = refresh_supabase_token(refresh_token)
                if new_tokens:
                    payload = decode_supabase_jwt(new_tokens["access_token"])
                    user_info = self.validate_token_payload(payload)
                    if user_info:
                        logging.info(f"Token refreshed successfully for user {user_info['id']}")
                    else:
                        logging.error("Refreshed token validation failed")
                        new_tokens = None
                else:
                    logging.error("Token refresh failed")
            except Exception as e:
                logging.error(f"Token refresh error: {e}")
        
        # If still no valid user, redirect to login
        if not user_info:
            logging.warning("No valid authentication found, redirecting to login")
            return self.create_redirect_response(request)
        
        # Set user info in request state
        request.state.user = user_info
        
        # Store new tokens for response if refreshed
        if new_tokens:
            request.state.new_tokens = new_tokens
        
        # Process the request
        try:
            response = await call_next(request)
        except Exception as e:
            logging.error(f"Request processing error: {e}")
            raise
        
        # Update cookies if tokens were refreshed
        if hasattr(request.state, 'new_tokens'):
            try:
                self.set_token_cookies(response, request.state.new_tokens)
                logging.info(f"Updated token cookies for user {user_info['id']}")
            except Exception as e:
                logging.error(f"Failed to set token cookies: {e}")
        
        return response