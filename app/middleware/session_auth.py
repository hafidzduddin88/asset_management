from fastapi import Request, HTTPException, status
from fastapi.responses import RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware
import jwt
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
            request.url.path == "/service-worker.js" or
            request.url.path == "/manifest.json"
        ):
            return await call_next(request)
        
        # Check for JWT token in cookies
        token = request.cookies.get("access_token")
        
        if not token:
            # Redirect to login page if no token
            return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
        
        try:
            # Validate token
            payload = jwt.decode(
                token, 
                config.SECRET_KEY, 
                algorithms=["HS256"]
            )
            
            # Add user info to request state
            request.state.user = payload
            
        except jwt.PyJWTError:
            # Redirect to login page if token is invalid
            return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
        
        # Continue with the request
        return await call_next(request)