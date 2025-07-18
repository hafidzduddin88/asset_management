# app/utils/flash.py
from fastapi import Request, Response
from starlette.responses import Response as StarletteResponse
import json
from typing import Optional, Dict, Any, Union

def set_flash(response: Union[Response, StarletteResponse], message: str, category: str = "info") -> None:
    """Set flash message in cookie."""
    flash_data = {
        "message": message,
        "category": category
    }
    response.set_cookie(
        key="flash",
        value=json.dumps(flash_data),
        httponly=True,
        max_age=30,  # 30 seconds
        samesite="lax",
        secure=False  # Set to True in production with HTTPS
    )

def get_flash(request: Request) -> Optional[Dict[str, Any]]:
    """Get flash message from cookie and clear it."""
    flash_cookie = request.cookies.get("flash")
    if not flash_cookie:
        return None
    
    try:
        flash_data = json.loads(flash_cookie)
        # Clear flash cookie in response
        request.scope["flash_to_clear"] = True
        return flash_data
    except:
        return None

class FlashMiddleware:
    """Middleware to clear flash messages after they are read."""
    
    def __init__(self, app):
        self.app = app
    
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        
        scope["flash_to_clear"] = False
        
        async def send_wrapper(message):
            if message["type"] == "http.response.start" and scope.get("flash_to_clear"):
                # Add Set-Cookie header to clear flash cookie
                headers = list(message.get("headers", []))
                headers.append(
                    (b"set-cookie", b"flash=; Path=/; Max-Age=0; HttpOnly; SameSite=lax")
                )
                message["headers"] = headers
            
            await send(message)
        
        await self.app(scope, receive, send_wrapper)