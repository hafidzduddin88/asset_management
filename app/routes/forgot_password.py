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
        "samesite": "lax"
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
    """Send password reset email via Supabase Auth API"""
    try:
        # Get the base URL for redirect
        base_url = str(request.base_url).rstrip('/')
        redirect_url = f"{base_url}/auth/change-password"
        
        # Send recovery email using Supabase Auth REST API with service role key
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{config.SUPABASE_URL}/auth/v1/recover",
                headers={
                    "apikey": config.SUPABASE_SERVICE_KEY,
                    "Authorization": f"Bearer {config.SUPABASE_SERVICE_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "email": email,
                    "redirect_to": redirect_url,
                },
                timeout=30,
            )
            
            # Handle rate limiting
            if response.status_code == 429:
                template_path = get_template(request, "forgot_password/request.html")
                return templates.TemplateResponse(template_path, {
                    "request": request,
                    "email": email,
                    "error": "Terlalu banyak permintaan. Silakan tunggu beberapa saat."
                })
        
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
    # Get token_hash and type from query params (Supabase email link format)
    token_hash = request.query_params.get("token_hash")
    type_param = request.query_params.get("type")
    
    # Handle old token format
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
        const hash = window.location.hash.substring(1);
        if (hash) {
            const params = new URLSearchParams(hash);
            const error = params.get('error');
            if (error) {
                window.location.href = '/forgot-password?error=' + encodeURIComponent(params.get('error_description') || error);
            } else {
                window.location.href = '/auth/change-password?' + hash;
            }
        } else {
            window.location.href = '/forgot-password?error=' + encodeURIComponent('Link tidak valid');
        }
    </script>
</body>
</html>
        """
        return HTMLResponse(content=html_content)
    
    try:
        # Verify token with Supabase Auth API using service role key
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{config.SUPABASE_URL}/auth/v1/verify",
                headers={
                    "apikey": config.SUPABASE_SERVICE_KEY,
                    "Authorization": f"Bearer {config.SUPABASE_SERVICE_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "type": type_param,
                    "token_hash": token_hash,
                },
                timeout=30,
            )
            
            if response.status_code >= 400:
                logging.warning(f"Token verification failed: {response.status_code}")
                template_path = get_template(request, "login_logout.html")
                return templates.TemplateResponse(template_path, {
                    "request": request,
                    "error": "Link reset password tidak valid atau sudah kadaluarsa."
                })
            
            data = response.json()
            access_token = data.get("access_token")
            refresh_token = data.get("refresh_token")
            
            if not access_token or not refresh_token:
                raise Exception("No tokens received from verify")
            
            # Redirect to form with cookies set (matching session_auth.py pattern)
            response_obj = RedirectResponse("/auth/change-password/form", status_code=303)
            
            settings = get_cookie_settings(request)
            
            # Set sb_access_token (matching session_auth.py)
            response_obj.set_cookie(
                key="sb_access_token",
                value=access_token,
                max_age=3600,  # 1 hour
                **settings
            )
            
            # Set sb_refresh_token (matching session_auth.py)
            response_obj.set_cookie(
                key="sb_refresh_token",
                value=refresh_token,
                max_age=86400 * 30,  # 30 days (matching session_auth.py)
                **settings
            )
            
            logging.info("Password reset session created successfully")
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
        
        if not access_token:
            template_path = get_template(request, "login_logout.html")
            return templates.TemplateResponse(template_path, {
                "request": request,
                "error": "Session tidak valid. Silakan request link reset password baru."
            })
        
        # Update password using Supabase Auth API with access token (use ANON_KEY for user operations)
        async with httpx.AsyncClient() as client:
            response = await client.put(
                f"{config.SUPABASE_URL}/auth/v1/user",
                headers={
                    "apikey": config.SUPABASE_ANON_KEY,
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                json={"password": new_password},
                timeout=30,
            )
            
            if response.status_code >= 400:
                logging.error(f"Failed to update password: {response.status_code}")
                return RedirectResponse("/auth/change-password/form?error=Gagal+mengubah+password", status_code=303)
        
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
        response_obj.delete_cookie("sb_access_token", **{k: v for k, v in settings.items() if k != "httponly"})
        response_obj.delete_cookie("sb_refresh_token", **{k: v for k, v in settings.items() if k != "httponly"})
        
        return response_obj
        
    except Exception as e:
        logging.error(f"Change password error: {str(e)}")
        return RedirectResponse("/auth/change-password/form?error=Terjadi+kesalahan", status_code=303)
