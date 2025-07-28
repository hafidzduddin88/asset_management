from fastapi import Request, status
from fastapi.responses import RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware
from jose import jwt, JWTError, ExpiredSignatureError
import logging
from urllib.parse import quote
import secrets

from app.config import load_config

config = load_config()

class SessionAuthMiddleware(BaseHTTPMiddleware):
    """Middleware for session authentication and token refresh."""
    
    async def dispatch(self, request: Request, call_next):
        # Skip authentication for public paths
        if (
            request.url.path.startswith("/static") or
            request.url.path.startswith("/api") or
            request.url.path in [
                "/login", "/login/token", "/health", "/offline",
                "/service-worker.js", "/manifest.json", "/favicon.ico"
            ] or
            request.method == "HEAD"
        ):
            return await call_next(request)
        
        token = request.cookies.get("access_token")
        
        if not token:
            # Try authenticate with remember_token
            remember_token = request.cookies.get("remember_token")
            if remember_token:
                from sqlalchemy.orm import Session
                from app.database.database import SessionLocal
                from app.database.models import User
                from app.utils.auth import create_access_token

                db = SessionLocal()
                try:
                    user = db.query(User).filter(User.remember_token == remember_token).first()
                    if user and user.is_active:
                        access_token = create_access_token(
                            data={"sub": user.username, "role": user.role}
                        )
                        response = await call_next(request)
                        
                        # Set new access token
                        response.set_cookie(
                            key="access_token",
                            value=access_token,
                            httponly=True,
                            max_age=60 * 60 * 24,  # 1 day
                            samesite="lax",
                            secure=False  # Change to True in production
                        )
                        
                        # Rotate remember token
                        new_remember_token = secrets.token_hex(32)
                        user.remember_token = new_remember_token
                        db.commit()
                        
                        response.set_cookie(
                            key="remember_token",
                            value=new_remember_token,
                            httponly=True,
                            max_age=60 * 60 * 24 * 30,  # 30 days
                            samesite="lax",
                            secure=False
                        )
                        
                        return response
                finally:
                    db.close()
            
            return self._redirect_to_login(request)
        
        try:
            payload = jwt.decode(token, config.SECRET_KEY, algorithms=["HS256"])
            request.state.user = payload  # Add user info to request
        except ExpiredSignatureError:
            logging.warning("Access token expired")
            return self._redirect_to_login(request)
        except JWTError as e:
            logging.error(f"Invalid token: {str(e)}")
            return self._redirect_to_login(request)
        
        return await call_next(request)
    
    def _redirect_to_login(self, request: Request) -> RedirectResponse:
        original_url = request.url.path
        if request.query_params:
            original_url += "?" + str(request.query_params)
        
        return RedirectResponse(
            url=f"/login?next={quote(original_url)}", 
            status_code=status.HTTP_303_SEE_OTHER
        )