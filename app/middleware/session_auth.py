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
            # Try to authenticate with remember_token
            remember_token = request.cookies.get("remember_token")
            if remember_token:
                # Import here to avoid circular imports
                from sqlalchemy.orm import Session
                from app.database.database import SessionLocal
                from app.database.models import User
                from app.utils.auth import create_access_token
                import secrets
                
                # Create a new database session
                db = SessionLocal()
                try:
                    # Find user by remember_token
                    user = db.query(User).filter(User.remember_token == remember_token).first()
                    if user and user.is_active:
                        # Create new access token
                        access_token = create_access_token(
                            data={"sub": user.username, "role": user.role}
                        )
                        
                        # Create response with the original request
                        response = await call_next(request)
                        
                        # Set new access token cookie
                        response.set_cookie(
                            key="access_token",
                            value=access_token,
                            httponly=True,
                            max_age=60 * 60 * 24,  # 1 day
                            samesite="lax",
                            secure=config.IS_PRODUCTION
                        )
                        
                        # Generate new remember token for security
                        new_remember_token = secrets.token_hex(32)
                        user.remember_token = new_remember_token
                        db.commit()
                        
                        # Set new remember token cookie
                        response.set_cookie(
                            key="remember_token",
                            value=new_remember_token,
                            httponly=True,
                            max_age=60 * 60 * 24 * 30,  # 30 days
                            samesite="lax",
                            secure=config.IS_PRODUCTION
                        )
                        
                        return response
                finally:
                    db.close()
            
            # Save the original URL for redirect after login
            original_url = request.url.path
            if request.query_params:
                original_url += "?" + str(request.query_params)
            
            # Redirect to login page if no valid tokens
            logging.warning(f"No valid tokens for path: {original_url}")
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