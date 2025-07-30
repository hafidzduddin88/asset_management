from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from supabase import create_client
from app.config import load_config
import logging

router = APIRouter(tags=["auth"])
templates = Jinja2Templates(directory="app/templates")

config = load_config()
supabase = create_client(config.SUPABASE_URL, config.SUPABASE_ANON_KEY)

@router.get("/auth/reset-password", response_class=HTMLResponse)
async def reset_password_form(request: Request, access_token: str = None, refresh_token: str = None):
    """Password reset form from email link."""
    if not access_token:
        return RedirectResponse(url="/login?error=Invalid reset link", status_code=303)
    
    return templates.TemplateResponse(
        "auth/reset_password_form.html",
        {
            "request": request,
            "access_token": access_token,
            "refresh_token": refresh_token
        }
    )

@router.post("/auth/reset-password")
async def update_password(
    request: Request,
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    access_token: str = Form(...)
):
    """Update password from reset form."""
    try:
        # Validate passwords match
        if new_password != confirm_password:
            return templates.TemplateResponse(
                "auth/reset_password_form.html",
                {
                    "request": request,
                    "access_token": access_token,
                    "error": "Passwords do not match"
                }
            )
        
        # Validate password length
        if len(new_password) < 6:
            return templates.TemplateResponse(
                "auth/reset_password_form.html",
                {
                    "request": request,
                    "access_token": access_token,
                    "error": "Password must be at least 6 characters"
                }
            )
        
        # Set session with access token
        supabase.auth.set_session(access_token, None)
        
        # Update password
        response = supabase.auth.update_user({"password": new_password})
        
        if response.user:
            logging.info(f"Password updated for user {response.user.email}")
            return RedirectResponse(url="/login?success=Password updated successfully", status_code=303)
        else:
            raise Exception("Failed to update password")
            
    except Exception as e:
        logging.error(f"Password update failed: {str(e)}")
        return templates.TemplateResponse(
            "auth/reset_password_form.html",
            {
                "request": request,
                "access_token": access_token,
                "error": "Failed to update password. Please try again."
            }
        )