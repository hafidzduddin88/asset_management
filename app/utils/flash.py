# app/utils/flash.py
from fastapi import Request, Response
import json
from typing import Optional, Dict, Any

def set_flash(response: Response, message: str, category: str = "info", data: Optional[Dict[str, Any]] = None):
    """Set flash message in cookie."""
    flash_data = {
        "message": message,
        "category": category
    }
    
    if data:
        flash_data["data"] = data
    
    response.set_cookie(
        key="flash",
        value=json.dumps(flash_data),
        httponly=True,
        max_age=60,  # 1 minute
        samesite="lax"
    )

def get_flash(request: Request) -> Optional[Dict[str, Any]]:
    """Get flash message from cookie and clear it."""
    flash = request.cookies.get("flash")
    if flash:
        try:
            return json.loads(flash)
        except json.JSONDecodeError:
            return None
    return None