# app/routes/forgot_password.py
from fastapi import APIRouter, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
import logging
import os

from app.utils.database_manager import get_supabase
from app.utils.device_detector import get_template
from app.utils.flash import set_flash
from app.config import load_config

# Create two routers for both paths
router = APIRouter(tags=["forgot_password"])
templates = Jinja2Templates(directory="app/templates")

config = load_config()

@router.get("/forgot-password/", response_class=HTMLResponse)
@router.get("/auth/forgot-password/", response_class=HTMLResponse)
async def forgot_password_page(request: Request):
    """Forgot password page (public - no login required)."""
    template_path = get_template(request, "forgot_password/index.html")
    return templates.TemplateResponse(template_path, {
        "request": request
    })

@router.post("/forgot-password/request")
@router.post("/auth/forgot-password/request")
async def request_password_reset(
    request: Request,
    email: str = Form(...)
):
    """Request password reset using Supabase recovery email."""
    try:
        supabase = get_supabase()
        
        # Check if user exists
        user_response = supabase.table("profiles").select("id, username, full_name").eq("username", email).execute()
        
        if not user_response.data:
            # Don't reveal if email exists (security best practice)
            response = RedirectResponse(
                url="/forgot-password/check-email",
                status_code=status.HTTP_303_SEE_OTHER
            )
            set_flash(response, "If an account exists with this email, you will receive a password reset link.", "info")
            return response
        
        user_data = user_response.data[0]
        user_name = user_data.get("full_name") or email
        
        # Send password recovery email via Supabase
        try:
            # Get app URL from config
            app_url = os.getenv("APP_URL", "http://localhost:8000")
            redirect_to = f"{app_url}/auth/recovery"
            
            # Use correct Supabase method with redirect URL
            supabase.auth.reset_password_for_email(
                email,
                options={
                    "redirect_to": redirect_to
                }
            )
            
            # Log password reset request
            supabase.table("user_management_logs").insert({
                "admin_id": None,
                "target_user_id": user_data["id"],
                "action": "PASSWORD_RESET_REQUESTED",
                "details": f"Password reset requested for {user_name} ({email})"
            }).execute()
            
            logging.info(f"Password reset email sent to {email} with redirect to {redirect_to}")
            
        except Exception as e:
            logging.error(f"Error sending password reset email: {e}")
            # Still show success message for security
        
        response = RedirectResponse(
            url="/forgot-password/check-email",
            status_code=status.HTTP_303_SEE_OTHER
        )
        set_flash(response, "If an account exists with this email, you will receive a password reset link.", "info")
        return response
        
    except Exception as e:
        logging.error(f"Error requesting password reset: {e}")
        response = RedirectResponse(
            url="/forgot-password/",
            status_code=status.HTTP_303_SEE_OTHER
        )
        set_flash(response, "An error occurred. Please try again.", "error")
        return response

@router.get("/forgot-password/check-email", response_class=HTMLResponse)
@router.get("/auth/forgot-password/check-email", response_class=HTMLResponse)
async def check_email_page(request: Request):
    """Check email page after requesting reset."""
    template_path = get_template(request, "forgot_password/check_email.html")
    return templates.TemplateResponse(template_path, {
        "request": request
    })

@router.get("/forgot-password/success", response_class=HTMLResponse)
@router.get("/auth/forgot-password/success", response_class=HTMLResponse)
async def reset_success_page(request: Request):
    """Password reset success page."""
    template_path = get_template(request, "forgot_password/success.html")
    return templates.TemplateResponse(template_path, {
        "request": request
    })
