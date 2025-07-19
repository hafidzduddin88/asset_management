from fastapi import Request, HTTPException, status
from fastapi.responses import RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware
from jose import jwt
import logging
from urllib.parse import quote
from app.config import load_config

# Load configuration
config = load_config()

class SessionAuthMiddleware(BaseHTTPMiddleware):
    """Middleware for session authentication."""
    
    async def dispatch(self, request: Request, call_next):
        # Skip authentication for static files, API routes, and login page
        if (
            request.url.path.startswith("/static") or
            request.url.path.startswith("/api") or
            request.url.path == "/login" or
            request.url.path == "/login/token" or
            request.url.path == "/health" or
            request.url.path == "/offline" or
            request.url.path == "/service-worker.js" or
            request.url.path == "/manifest.json" or
            request.url.path == "/favicon.ico" or
            request.method == "HEAD"
        ):
            return await call_next(request)
        
        # Check for JWT token in cookies
        token = request.cookies.get("access_token")
        
        if not token:
            # Save the original URL for redirect after login
            original_url = request.url.path
            if request.query_params:
                original_url += "?" + str(request.query_params)
            
            # Redirect to login page if no token
            logging.warning(f"No access_token in cookies for path: {original_url}")
            return RedirectResponse(
                url=f"/login?next={quote(original_url)}", 
                status_code=status.HTTP_303_SEE_OTHER
            )
        
        try:
            # Validate token
            payload = jwt.decode(
                token, 
                config.SECRET_KEY, 
                algorithms=["HS256"]
            )
            
            # Add user info to request state
            request.state.user = payload
            
        except Exception as e:
            # Save the original URL for redirect after login
            original_url = request.url.path
            if request.query_params:
                original_url += "?" + str(request.query_params)
            
            # Redirect to login page if token is invalid
            logging.error(f"Invalid token: {str(e)}")
            return RedirectResponse(
                url=f"/login?next={quote(original_url)}", 
                status_code=status.HTTP_303_SEE_OTHER
            )
        
        # Continue with the request
        return await call_next(request)