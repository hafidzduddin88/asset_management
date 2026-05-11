from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse, HTMLResponse
from app.utils.device_detector import get_template
from app.config import load_config
from starlette.templating import Jinja2Templates
import httpx
import logging
from urllib.parse import urlparse

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
    # Check for error from recovery redirect
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
        # Import supabase client
        from supabase import create_client
        supabase = create_client(config.SUPABASE_URL, config.SUPABASE_ANON_KEY)
        
        # Get the base URL for redirect
        base_url = str(request.base_url).rstrip('/')
        redirect_url = f"{base_url}/auth/change-password"
        
        # Use SDK method instead of manual HTTP
        try:
            result = supabase.auth.reset_password_for_email(
                email, 
                {"redirect_to": redirect_url}
            )
            
        except Exception as reset_error:
            # Handle rate limiting and other errors
            if "429" in str(reset_error) or "rate" in str(reset_error).lower():
                template_path = get_template(request, "forgot_password/request.html")
                return templates.TemplateResponse(template_path, {
                    "request": request,
                    "email": email,
                    "error": "Terlalu banyak permintaan. Silakan tunggu beberapa saat."
                })
            # For other errors, continue to success message (don't expose errors)
        
        # Don't expose whether email exists (security best practice)
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
        # Handle Supabase auth errors directly
        error_msg = error_description or error
        if "expired" in error.lower() or "invalid" in error.lower():
            error_msg = "Link reset password sudah kadaluarsa. Silakan request link baru."
        
        # Use proper URL encoding for redirect
        from urllib.parse import quote_plus
        return RedirectResponse(f"/forgot-password?error={quote_plus(error_msg)}", status_code=303)
    
    # Get token_hash and type from query params (Supabase email link format)
    # Support both modern (token_hash) and legacy (token) formats
    token_hash = request.query_params.get("token_hash")
    type_param = request.query_params.get("type")
    
    # Handle legacy token format
    if not token_hash:
        token_hash = request.query_params.get("token")
    
    if not token_hash or not type_param:
        # Return HTML with JavaScript to handle fragment format
        html_content = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Processing...</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-50 min-h-screen flex items-center justify-center">
    <div class="text-center">
        <div class="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto"></div>
        <p class="mt-4 text-gray-600">Memproses reset password...</p>
    </div>
    <script>
        // Handle both query params and hash fragments
        const urlParams = new URLSearchParams(window.location.search);
        const hash = window.location.hash.substring(1);
        const hashParams = new URLSearchParams(hash);
        
        // Check for errors in query params first
        let error = urlParams.get('error') || urlParams.get('error_code');
        let errorDescription = urlParams.get('error_description');
        
        // If no error in query params, check hash
        if (!error && hash) {
            error = hashParams.get('error') || hashParams.get('error_code');
            errorDescription = hashParams.get('error_description');
        }
        
        if (error) {
            // Redirect to forgot password page with error
            const errorMsg = errorDescription || error;
            window.location.href = '/forgot-password?error=' + encodeURIComponent(errorMsg);
        } else if (hash && (hashParams.get('token_hash') || hashParams.get('token'))) {
            // Valid token in hash, redirect with query params
            window.location.href = '/auth/change-password?' + hash;
        } else {
            // No valid params, redirect with generic error
            window.location.href = '/forgot-password?error=' + encodeURIComponent('Link tidak valid atau sudah kadaluarsa');
        }
    </script>
</body>
</html>
        """
        return HTMLResponse(content=html_content)
    
    try:
        # Import supabase client
        from supabase import create_client
        supabase = create_client(config.SUPABASE_URL, config.SUPABASE_ANON_KEY)
        
        # Use SDK method for token verification instead of manual HTTP
        try:
            # Use verifyOtp for recovery token verification
            result = supabase.auth.verify_otp({
                "type": "recovery",
                "token_hash": token_hash
            })
            
            if not result.session or not result.session.access_token or not result.session.refresh_token:
                logging.warning(f"Recovery verification returned incomplete session")
                template_path = get_template(request, "login_logout.html")
                return templates.TemplateResponse(template_path, {
                    "request": request,
                    "error": "Link reset password tidak valid atau sudah kadaluarsa."
                })
            
            # SDK already knows about this session - don't call set_session()
            session = result.session
            
        except Exception as verify_error:
            logging.warning(f"Recovery token verification failed: {verify_error}")
            template_path = get_template(request, "login_logout.html")
            return templates.TemplateResponse(template_path, {
                "request": request,
                "error": "Link reset password tidak valid atau sudah kadaluarsa."
            })
        
        # Redirect to form with cookies set (matching session_auth.py pattern)
        response_obj = RedirectResponse("/auth/change-password/form", status_code=303)
        
        settings = get_cookie_settings(request)
        
        # Set sb_access_token (matching session_auth.py)
        response_obj.set_cookie(
            key="sb_access_token",
            value=session.access_token,
            max_age=3600,  # 1 hour
            **settings
        )
        
        # Set sb_refresh_token (matching session_auth.py)
        response_obj.set_cookie(
            key="sb_refresh_token",
            value=session.refresh_token,
            max_age=86400 * 30,  # 30 days (matching session_auth.py)
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
    # Middleware will validate sb_access_token cookie and populate request.state.user
    # If no valid session, middleware will redirect to login
    
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
        
        # Get access token from cookie (set by GET /auth/change-password)
        access_token = request.cookies.get("sb_access_token")
        refresh_token = request.cookies.get("sb_refresh_token")
        
        logging.info(f"POST change-password - access_token present: {bool(access_token)}, refresh_token present: {bool(refresh_token)}")
        
        if not access_token or not refresh_token:
            template_path = get_template(request, "login_logout.html")
            return templates.TemplateResponse(template_path, {
                "request": request,
                "error": "Session tidak valid. Silakan request link reset password baru."
            })
        
        # Import supabase client and use SDK method
        from supabase import create_client
        supabase = create_client(config.SUPABASE_URL, config.SUPABASE_ANON_KEY)
        
        # Set session with current tokens to use SDK method
        refresh_token = request.cookies.get("sb_refresh_token")
        if access_token and refresh_token:
            try:
                supabase.auth.set_session(access_token, refresh_token)
                
                # Use SDK method to update password
                result = supabase.auth.update_user({"password": new_password})
                
                if not result.user:
                    logging.error("Failed to update password via SDK")
                    return RedirectResponse("/auth/change-password/form?error=Gagal+mengubah+password", status_code=303)
                    
            except Exception as update_error:
                logging.error(f"Failed to update password: {update_error}")
                return RedirectResponse("/auth/change-password/form?error=Gagal+mengubah+password", status_code=303)
        else:
            return RedirectResponse("/auth/change-password/form?error=Session+tidak+valid", status_code=303)
        
        logging.info(f"Attempting password update with tokens - access_token: {bool(access_token)}, refresh_token: {bool(refresh_token)}")
        
        logging.info("Password updated successfully")
        
        # Clear SDK session after password change
        supabase.auth.sign_out()
        
        # Clear cookies and redirect to login (matching login.py pattern)
        template_path = get_template(request, "login_logout.html")
        response_obj = templates.TemplateResponse(template_path, {
            "request": request,
            "success": "Password berhasil diubah. Silakan login dengan password baru."
        })
        
        # Clear reset session cookies (matching login.py clear_auth_cookies pattern)
        settings = get_cookie_settings(request)
        response_obj.delete_cookie("sb_access_token", path="/", httponly=True, secure=settings["secure"], samesite="lax")
        response_obj.delete_cookie("sb_refresh_token", path="/", httponly=True, secure=settings["secure"], samesite="lax")
        
        return response_obj
        
    except Exception as e:
        logging.error(f"Change password error: {str(e)}")
        return RedirectResponse("/auth/change-password/form?error=Terjadi+kesalahan", status_code=303)
