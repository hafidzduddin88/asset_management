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
    error_description: str = None,
    access_token: str = None,
    refresh_token: str = None
):
    """Handle Supabase recovery/reset password flow."""
    
    # Check for errors from Supabase
    if error:
        logging.error(f"Supabase recovery error: {error} - {error_description}")
        response = RedirectResponse(
            url="/forgot-password/",
            status_code=status.HTTP_303_SEE_OTHER
        )
        set_flash(response, f"Password reset link expired or invalid. Please request a new one.", "error")
        return response
    
    # If we have access_token, user is authenticated via recovery link
    if access_token:
        # Show reset password form with access token
        template_path = get_template(request, "forgot_password/reset.html")
        return templates.TemplateResponse(template_path, {
            "request": request,
            "access_token": access_token,
            "refresh_token": refresh_token
        })
    
    # If we have token and type=recovery, show reset form
    if token and type == "recovery":
        template_path = get_template(request, "forgot_password/reset.html")
        return templates.TemplateResponse(template_path, {
            "request": request,
            "token": token,
            "type": type
        })
    
    # Invalid recovery request
    raise HTTPException(status_code=400, detail="Invalid recovery request")

@router.post("/reset-password")
async def reset_password_submit(
    request: Request,
    password: str = Form(...),
    password_confirm: str = Form(...),
    access_token: str = Form(None),
    token: str = Form(None),
    type: str = Form(None)
):
    """Reset password using Supabase recovery token or access token."""
    try:
        # Validate passwords match
        if password != password_confirm:
            template_path = get_template(request, "forgot_password/reset.html")
            return templates.TemplateResponse(template_path, {
                "request": request,
                "token": token or access_token,
                "type": type,
                "access_token": access_token,
                "error": "Passwords do not match"
            })
        
        # Validate password strength
        if len(password) < 6:
            template_path = get_template(request, "forgot_password/reset.html")
            return templates.TemplateResponse(template_path, {
                "request": request,
                "token": token or access_token,
                "type": type,
                "access_token": access_token,
                "error": "Password must be at least 6 characters"
            })
        
        supabase = get_supabase()
        
        try:
            # If we have access_token, use it to update password
            if access_token:
                # Create a new supabase client with the access token
                from supabase import create_client
                from app.config import load_config
                
                config = load_config()
                user_supabase = create_client(config.SUPABASE_URL, config.SUPABASE_ANON_KEY)
                
                # Set the session with access token
                user_supabase.auth.set_session(access_token, access_token)
                
                # Update password
                response = user_supabase.auth.update_user({"password": password})
                
                if response.user:
                    user_id = response.user.id
                    
                    # Log password reset
                    supabase.table("user_management_logs").insert({
                        "admin_id": None,
                        "target_user_id": user_id,
                        "action": "PASSWORD_RESET_COMPLETED",
                        "details": f"Password reset completed via recovery link"
                    }).execute()
                    
                    logging.info(f"Password reset completed for user {user_id}")
                    
                    response = RedirectResponse(
                        url="/forgot-password/success",
                        status_code=status.HTTP_303_SEE_OTHER
                    )
                    set_flash(response, "Password reset successfully. You can now login with your new password.", "success")
                    return response
                else:
                    raise Exception("Failed to update password")
            
            # If we have token and type=recovery, verify OTP
            elif token and type == "recovery":
                # Verify OTP token
                response = supabase.auth.verify_otp({
                    "token": token,
                    "type": type
                })
                
                if response.user:
                    # Update password using admin API
                    supabase.auth.admin.update_user_by_id(
                        response.user.id,
                        {"password": password}
                    )
                    
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
            else:
                raise Exception("No valid token provided")
                
        except Exception as e:
            logging.error(f"Error resetting password: {e}")
            template_path = get_template(request, "forgot_password/reset.html")
            return templates.TemplateResponse(template_path, {
                "request": request,
                "token": token or access_token,
                "type": type,
                "access_token": access_token,
                "error": "Invalid or expired recovery token. Please request a new password reset."
            })
        
    except Exception as e:
        logging.error(f"Error in password reset: {e}")
        response = RedirectResponse(
            url="/forgot-password/",
            status_code=status.HTTP_303_SEE_OTHER
        )
        set_flash(response, "An error occurred. Please try again.", "error")
        return response
