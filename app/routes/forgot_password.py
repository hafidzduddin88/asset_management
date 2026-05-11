from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse
from app.utils.device_detector import get_template
from app.config import load_config
from starlette.templating import Jinja2Templates
import logging
from urllib.parse import quote_plus

config = load_config()
router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

def get_cookie_settings(request: Request) -> dict:
    """Get cookie settings matching session_auth.py"""
    is_secure = request.url.scheme == "https"
    return {
        "httponly": True,
        "secure": is_secure,
        "samesite": "lax",
        "path": "/"
    }

@router.get("/forgot-password")
async def forgot_password_page(request: Request):
    """Display forgot password form"""
    error = request.query_params.get("error")
    
    template_path = get_template(request, "forgot_password/request.html")
    return templates.TemplateResponse(template_path, {
        "request": request,
        "error": error if error else None
    })

@router.post("/forgot-password")
async def forgot_password_submit(request: Request, email: str = Form(...)):
    """Send password reset email via Supabase SDK"""
    try:
        from supabase import create_client
        supabase = create_client(config.SUPABASE_URL, config.SUPABASE_ANON_KEY)
        
        base_url = str(request.base_url).rstrip('/')
        redirect_url = f"{base_url}/auth/change-password"
        
        try:
            supabase.auth.reset_password_for_email(
                email, 
                {"redirect_to": redirect_url}
            )
        except Exception as reset_error:
            if "429" in str(reset_error) or "rate" in str(reset_error).lower():
                template_path = get_template(request, "forgot_password/request.html")
                return templates.TemplateResponse(template_path, {
                    "request": request,
                    "email": email,
                    "error": "Terlalu banyak permintaan. Silakan tunggu beberapa saat."
                })
        
        logging.info(f"Password reset email requested for: {email}")
        template_path = get_template(request, "login_logout.html")
        return templates.TemplateResponse(template_path, {
            "request": request,
            "success": f"Jika email {email} terdaftar, link reset password telah dikirim. Silakan cek inbox Anda."
        })
        
    except Exception as e:
        logging.error(f"Forgot password error: {str(e)}")
        template_path = get_template(request, "forgot_password/request.html")
        return templates.TemplateResponse(template_path, {
            "request": request,
            "email": email,
            "error": "Terjadi kesalahan. Silakan coba lagi."
        })

@router.get("/auth/change-password")
async def change_password_page(request: Request):
    """Handle Supabase recovery callback and verify token"""
    # Check for errors in query params first (from Supabase)
    error = request.query_params.get("error") or request.query_params.get("error_code")
    error_description = request.query_params.get("error_description")
    
    if error:
        error_msg = error_description or error
        if "expired" in error.lower() or "invalid" in error.lower():
            error_msg = "Link reset password sudah kadaluarsa. Silakan request link baru."
        return RedirectResponse(f"/forgot-password?error={quote_plus(error_msg)}", status_code=303)
    
    # Get token_hash and type from query params (Supabase email link format)
    token_hash = request.query_params.get("token_hash")
    type_param = request.query_params.get("type")
    access_token = request.query_params.get("access_token")
    refresh_token = request.query_params.get("refresh_token")
    
    # Handle legacy token format
    if not token_hash:
        token_hash = request.query_params.get("token")
    
    # If we have access_token and refresh_token from Supabase redirect, use them directly
    if access_token and refresh_token:
        try:
            response_obj = RedirectResponse("/auth/change-password/form", status_code=303)
            settings = get_cookie_settings(request)
            
            response_obj.set_cookie(
                key="sb_access_token",
                value=access_token,
                max_age=3600,
                **settings
            )
            
            response_obj.set_cookie(
                key="sb_refresh_token",
                value=refresh_token,
                max_age=86400 * 30,
                **settings
            )
            
            logging.info("Password reset session created from Supabase redirect")
            return response_obj
        except Exception as e:
            logging.error(f"Error setting cookies from Supabase tokens: {str(e)}")
            template_path = get_template(request, "login_logout.html")
            return templates.TemplateResponse(template_path, {
                "request": request,
                "error": "Terjadi kesalahan saat memproses link reset password."
            })
    
    if not token_hash or not type_param:
        template_path = get_template(request, "forgot_password/processing.html")
        return templates.TemplateResponse(template_path, {"request": request})
    
    try:
        from supabase import create_client
        supabase = create_client(config.SUPABASE_URL, config.SUPABASE_ANON_KEY)
        
        # Verify recovery token
        try:
            result = supabase.auth.verify_otp({
                "type": "recovery",
                "token_hash": token_hash
            })
            
            if not result.session or not result.session.access_token or not result.session.refresh_token:
                logging.warning(f"Recovery verification returned incomplete session - access_token: {bool(result.session.access_token) if result.session else False}, refresh_token: {bool(result.session.refresh_token) if result.session else False}")
                template_path = get_template(request, "login_logout.html")
                return templates.TemplateResponse(template_path, {
                    "request": request,
                    "error": "Link reset password tidak valid atau sudah kadaluarsa."
                })
            
            session = result.session
            
        except Exception as verify_error:
            logging.warning(f"Recovery token verification failed: {verify_error}")
            template_path = get_template(request, "login_logout.html")
            return templates.TemplateResponse(template_path, {
                "request": request,
                "error": "Link reset password tidak valid atau sudah kadaluarsa."
            })
        
        # Set cookies and redirect to form
        response_obj = RedirectResponse("/auth/change-password/form", status_code=303)
        settings = get_cookie_settings(request)
        
        response_obj.set_cookie(
            key="sb_access_token",
            value=session.access_token,
            max_age=3600,
            **settings
        )
        
        response_obj.set_cookie(
            key="sb_refresh_token",
            value=session.refresh_token,
            max_age=86400 * 30,
            **settings
        )
        
        logging.info(f"Password reset session created - access_token: {bool(session.access_token)}, refresh_token: {bool(session.refresh_token)}")
        return response_obj
            
    except Exception as e:
        logging.error(f"Change password page error: {str(e)}")
        template_path = get_template(request, "login_logout.html")
        return templates.TemplateResponse(template_path, {
            "request": request,
            "error": "Terjadi kesalahan saat memproses link reset password."
        })

@router.get("/auth/change-password/form")
async def change_password_form(request: Request):
    """Display password change form (requires valid session from cookies)"""
    # Check if user has valid reset session cookies
    access_token = request.cookies.get("sb_access_token")
    refresh_token = request.cookies.get("sb_refresh_token")
    
    if not access_token or not refresh_token:
        # Redirect to forgot password if no valid session
        return RedirectResponse("/forgot-password?error=Session+tidak+valid", status_code=303)
    
    template_path = get_template(request, "forgot_password/reset.html")
    return templates.TemplateResponse(template_path, {
        "request": request,
        "error": request.query_params.get("error")
    })

@router.post("/auth/change-password")
async def change_password_submit(
    request: Request,
    new_password: str = Form(...),
    confirm_password: str = Form(...)
):
    """Update password using authenticated session from cookies"""
    try:
        # Validate passwords
        if new_password != confirm_password:
            return RedirectResponse("/auth/change-password/form?error=Password+tidak+cocok", status_code=303)
        
        if len(new_password) < 6:
            return RedirectResponse("/auth/change-password/form?error=Password+minimal+6+karakter", status_code=303)
        
        # Get tokens from cookies
        access_token = request.cookies.get("sb_access_token")
        refresh_token = request.cookies.get("sb_refresh_token")
        
        logging.info(f"POST /auth/change-password - access_token present: {bool(access_token)}, refresh_token present: {bool(refresh_token)}, refresh_token length: {len(refresh_token) if refresh_token else 0}")
        
        if not access_token or not refresh_token:
            template_path = get_template(request, "login_logout.html")
            return templates.TemplateResponse(template_path, {
                "request": request,
                "error": "Session tidak valid. Silakan request link reset password baru."
            })
        
        # Update password
        from supabase import create_client
        supabase = create_client(config.SUPABASE_URL, config.SUPABASE_ANON_KEY)
        
        try:
            supabase.auth.set_session(access_token, refresh_token)
            result = supabase.auth.update_user({"password": new_password})
            
            if not result.user:
                logging.error("Failed to update password via SDK")
                return RedirectResponse("/auth/change-password/form?error=Gagal+mengubah+password", status_code=303)
            
            logging.info("Password updated successfully")
            
        except Exception as update_error:
            logging.error(f"Failed to update password: {update_error}")
            return RedirectResponse("/auth/change-password/form?error=Gagal+mengubah+password", status_code=303)
        
        # Clear session and cookies
        supabase.auth.sign_out()
        
        template_path = get_template(request, "login_logout.html")
        response_obj = templates.TemplateResponse(template_path, {
            "request": request,
            "success": "Password berhasil diubah. Silakan login dengan password baru."
        })
        
        settings = get_cookie_settings(request)
        response_obj.delete_cookie("sb_access_token", path="/", httponly=True, secure=settings["secure"], samesite="lax")
        response_obj.delete_cookie("sb_refresh_token", path="/", httponly=True, secure=settings["secure"], samesite="lax")
        
        return response_obj
        
    except Exception as e:
        logging.error(f"Change password error: {str(e)}")
        return RedirectResponse("/auth/change-password/form?error=Terjadi+kesalahan", status_code=303)
