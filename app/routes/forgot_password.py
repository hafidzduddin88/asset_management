# app/routes/forgot_password.py
from fastapi import APIRouter, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime, timedelta
import logging
import secrets
import os

from app.utils.database_manager import get_supabase
from app.utils.device_detector import get_template
from app.utils.flash import set_flash

router = APIRouter(prefix="/forgot-password", tags=["forgot_password"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def forgot_password_page(request: Request):
    """Forgot password page (public - no login required)."""
    template_path = get_template(request, "forgot_password/index.html")
    return templates.TemplateResponse(template_path, {
        "request": request
    })

@router.post("/request")
async def request_password_reset(
    request: Request,
    email: str = Form(...)
):
    """Request password reset link (public - no login required)."""
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
        user_id = user_data["id"]
        user_name = user_data.get("full_name") or email
        
        # Generate reset token
        reset_token = secrets.token_urlsafe(32)
        token_expiry = datetime.now() + timedelta(hours=24)
        
        # Store reset token in database
        supabase.table("password_reset_tokens").insert({
            "user_id": user_id,
            "token": reset_token,
            "expires_at": token_expiry.isoformat(),
            "used": False
        }).execute()
        
        # Log password reset request
        supabase.table("user_management_logs").insert({
            "admin_id": None,
            "target_user_id": user_id,
            "action": "PASSWORD_RESET_REQUESTED",
            "details": f"Password reset requested for {user_name} ({email})"
        }).execute()
        
        logging.info(f"Password reset requested for {email}")
        
        # In production, send email with reset link
        # For now, just redirect to check email page
        response = RedirectResponse(
            url="/forgot-password/check-email",
            status_code=status.HTTP_303_SEE_OTHER
        )
        set_flash(response, "If an account exists with this email, you will receive a password reset link.", "info")
        return response
        
    except Exception as e:
        logging.error(f"Error requesting password reset: {e}")
        response = RedirectResponse(
            url="/forgot-password",
            status_code=status.HTTP_303_SEE_OTHER
        )
        set_flash(response, "An error occurred. Please try again.", "error")
        return response

@router.get("/check-email", response_class=HTMLResponse)
async def check_email_page(request: Request):
    """Check email page after requesting reset."""
    template_path = get_template(request, "forgot_password/check_email.html")
    return templates.TemplateResponse(template_path, {
        "request": request
    })

@router.get("/reset/{token}", response_class=HTMLResponse)
async def reset_password_page(
    request: Request,
    token: str
):
    """Reset password page with token."""
    try:
        supabase = get_supabase()
        
        # Validate token
        token_response = supabase.table("password_reset_tokens").select(
            "user_id, expires_at, used"
        ).eq("token", token).execute()
        
        if not token_response.data:
            raise HTTPException(status_code=404, detail="Invalid reset token")
        
        token_data = token_response.data[0]
        
        # Check if token is used
        if token_data["used"]:
            raise HTTPException(status_code=400, detail="Reset token already used")
        
        # Check if token expired
        expires_at = datetime.fromisoformat(token_data["expires_at"])
        if datetime.now() > expires_at:
            raise HTTPException(status_code=400, detail="Reset token expired")
        
        template_path = get_template(request, "forgot_password/reset.html")
        return templates.TemplateResponse(template_path, {
            "request": request,
            "token": token
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error validating reset token: {e}")
        raise HTTPException(status_code=500, detail="An error occurred")

@router.post("/reset/{token}")
async def reset_password_submit(
    request: Request,
    token: str,
    password: str = Form(...),
    password_confirm: str = Form(...)
):
    """Submit new password."""
    try:
        # Validate passwords match
        if password != password_confirm:
            template_path = get_template(request, "forgot_password/reset.html")
            return templates.TemplateResponse(template_path, {
                "request": request,
                "token": token,
                "error": "Passwords do not match"
            })
        
        # Validate password strength
        if len(password) < 6:
            template_path = get_template(request, "forgot_password/reset.html")
            return templates.TemplateResponse(template_path, {
                "request": request,
                "token": token,
                "error": "Password must be at least 6 characters"
            })
        
        supabase = get_supabase()
        
        # Validate token
        token_response = supabase.table("password_reset_tokens").select(
            "user_id, expires_at, used"
        ).eq("token", token).execute()
        
        if not token_response.data:
            raise HTTPException(status_code=404, detail="Invalid reset token")
        
        token_data = token_response.data[0]
        user_id = token_data["user_id"]
        
        # Check if token is used
        if token_data["used"]:
            raise HTTPException(status_code=400, detail="Reset token already used")
        
        # Check if token expired
        expires_at = datetime.fromisoformat(token_data["expires_at"])
        if datetime.now() > expires_at:
            raise HTTPException(status_code=400, detail="Reset token expired")
        
        # Update password in Supabase Auth
        supabase.auth.admin.update_user_by_id(user_id, {"password": password})
        
        # Mark token as used
        supabase.table("password_reset_tokens").update({
            "used": True
        }).eq("token", token).execute()
        
        # Get user info for logging
        user_response = supabase.table("profiles").select("username, full_name").eq("id", user_id).execute()
        if user_response.data:
            user_data = user_response.data[0]
            user_name = user_data.get("full_name") or user_data["username"]
            
            # Log password reset
            supabase.table("user_management_logs").insert({
                "admin_id": None,
                "target_user_id": user_id,
                "action": "PASSWORD_RESET_COMPLETED",
                "details": f"Password reset completed for {user_name}"
            }).execute()
        
        logging.info(f"Password reset completed for user {user_id}")
        
        response = RedirectResponse(
            url="/forgot-password/success",
            status_code=status.HTTP_303_SEE_OTHER
        )
        set_flash(response, "Password reset successfully. You can now login with your new password.", "success")
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error resetting password: {e}")
        response = RedirectResponse(
            url="/forgot-password",
            status_code=status.HTTP_303_SEE_OTHER
        )
        set_flash(response, "An error occurred. Please try again.", "error")
        return response

@router.get("/success", response_class=HTMLResponse)
async def reset_success_page(request: Request):
    """Password reset success page."""
    template_path = get_template(request, "forgot_password/success.html")
    return templates.TemplateResponse(template_path, {
        "request": request
    })
