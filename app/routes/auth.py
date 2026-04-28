# app/routes/auth.py
from fastapi import APIRouter, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
import logging

from app.utils.database_manager import get_supabase
from app.utils.device_detector import get_template
from app.utils.flash import set_flash

router = APIRouter(prefix="/auth", tags=["auth"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/recovery", response_class=HTMLResponse)
async def recovery_page(
    request: Request,
    token: str = None,
    type: str = None,
    error: str = None,
    error_description: str = None
):
    """Handle Supabase recovery/reset password flow."""
    
    if error:
        # Token expired or invalid
        response = RedirectResponse(
            url="/forgot-password/",
            status_code=status.HTTP_303_SEE_OTHER
        )
        set_flash(response, f"Password reset link expired or invalid. Please request a new one.", "error")
        return response
    
    if not token or type != "recovery":
        raise HTTPException(status_code=400, detail="Invalid recovery request")
    
    # Redirect to custom reset page with token
    return RedirectResponse(
        url=f"/forgot-password/reset/{token}",
        status_code=status.HTTP_303_SEE_OTHER
    )

@router.post("/reset-password")
async def reset_password_with_supabase_token(
    request: Request,
    token: str = Form(...),
    password: str = Form(...),
    password_confirm: str = Form(...)
):
    """Reset password using Supabase recovery token."""
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
        
        # Use Supabase recovery token to reset password
        try:
            # Exchange recovery token for session
            response = supabase.auth.verify_otp({
                "token": token,
                "type": "recovery"
            })
            
            if response.user:
                # Update password
                supabase.auth.admin.update_user_by_id(response.user.id, {"password": password})
                
                # Log password reset
                supabase.table("user_management_logs").insert({
                    "admin_id": None,
                    "target_user_id": response.user.id,
                    "action": "PASSWORD_RESET_COMPLETED",
                    "details": f"Password reset completed via recovery link"
                }).execute()
                
                logging.info(f"Password reset completed for user {response.user.id}")
                
                response = RedirectResponse(
                    url="/forgot-password/success",
                    status_code=status.HTTP_303_SEE_OTHER
                )
                set_flash(response, "Password reset successfully. You can now login with your new password.", "success")
                return response
            else:
                raise Exception("Failed to verify token")
                
        except Exception as e:
            logging.error(f"Error verifying recovery token: {e}")
            template_path = get_template(request, "forgot_password/reset.html")
            return templates.TemplateResponse(template_path, {
                "request": request,
                "token": token,
                "error": "Invalid or expired recovery token"
            })
        
    except Exception as e:
        logging.error(f"Error resetting password: {e}")
        response = RedirectResponse(
            url="/forgot-password/",
            status_code=status.HTTP_303_SEE_OTHER
        )
        set_flash(response, "An error occurred. Please try again.", "error")
        return response
