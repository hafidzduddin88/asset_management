from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from supabase import create_client
from app.config import load_config
from app.utils.auth import get_current_profile
import logging

router = APIRouter(tags=["password"])
templates = Jinja2Templates(directory="app/templates")

config = load_config()
supabase = create_client(config.SUPABASE_URL, config.SUPABASE_ANON_KEY)

@router.get("/profile/reset-password", response_class=HTMLResponse)
async def reset_password_page(
    request: Request,
    current_profile = Depends(get_current_profile)
):
    """Reset password page."""
    return templates.TemplateResponse(
        "profile/reset_password.html",
        {
            "request": request,
            "user": current_profile
        }
    )

@router.post("/profile/reset-password")
async def send_reset_password_email(
    request: Request,
    current_profile = Depends(get_current_profile)
):
    """Send password reset email via Supabase."""
    try:
        # Send password reset email
        response = supabase.auth.reset_password_email(
            current_profile.username,
            {
                "redirect_to": f"{config.APP_URL}/auth/reset-password"
            }
        )
        
        logging.info(f"Password reset email sent to {current_profile.username}")
        
        return templates.TemplateResponse(
            "profile/reset_password.html",
            {
                "request": request,
                "user": current_profile,
                "success": f"Password reset link has been sent to {current_profile.username}. Please check your email."
            }
        )
        
    except Exception as e:
        logging.error(f"Password reset email failed: {str(e)}")
        return templates.TemplateResponse(
            "profile/reset_password.html",
            {
                "request": request,
                "user": current_profile,
                "error": "Failed to send reset email. Please try again."
            }
        )