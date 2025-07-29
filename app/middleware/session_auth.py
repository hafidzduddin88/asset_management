from fastapi import Request
from fastapi.responses import RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware
from supabase import create_client, Client
from app.config import load_config
import logging
from urllib.parse import quote

config = load_config()
supabase: Client = create_client(config.SUPABASE_URL, config.SUPABASE_ANON_KEY)

class SessionAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Skip authentication for static files and login
        if (
            request.url.path.startswith("/static") or
            request.url.path == "/login" or
            request.url.path == "/health" or
            request.url.path == "/offline" or
            request.url.path == "/service-worker.js" or
            request.url.path == "/manifest.json" or
            request.url.path == "/favicon.ico" or
            request.method == "HEAD"
        ):
            return await call_next(request)
        
        token = request.cookies.get("sb_access_token")
        
        if not token:
            original_url = request.url.path
            if request.query_params:
                original_url += "?" + str(request.query_params)
            
            return RedirectResponse(
                url=f"/login?next={quote(original_url)}", 
                status_code=303
            )
        
        try:
            from jose import jwt
            payload = jwt.decode(token, config.SECRET_KEY, algorithms=["HS256"])
            user_id = payload.get("sub")
            
            if not user_id:
                raise Exception("Invalid token")
            
            request.state.user = {
                "id": user_id,
                "email": payload.get("email", "")
            }
            
        except Exception as e:
            original_url = request.url.path
            if request.query_params:
                original_url += "?" + str(request.query_params)
            
            logging.error(f"Auth middleware error: {str(e)}")
            return RedirectResponse(
                url=f"/login?next={quote(original_url)}", 
                status_code=303
            )
        
        return await call_next(request)