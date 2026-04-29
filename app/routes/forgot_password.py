from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse, HTMLResponse
from app.utils.database_manager import get_supabase
from app.utils.device_detector import get_template
from starlette.templating import Jinja2Templates

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

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
    """Send password reset email via Supabase"""
    try:
        supabase = get_supabase()
        
        # Get the base URL for redirect
        base_url = str(request.base_url).rstrip('/')
        redirect_url = f"{base_url}/auth/recovery"
        
        # Send recovery email using Supabase Auth
        supabase.auth.reset_password_email(
            email=email,
            options={
                "redirect_to": redirect_url
            }
        )
        
        template_path = get_template(request, "login_logout.html")
        return templates.TemplateResponse(template_path, {
            "request": request,
            "success": f"Email reset password telah dikirim ke {email}. Silakan cek inbox Anda."
        })
        
    except Exception as e:
        template_path = get_template(request, "forgot_password/request.html")
        return templates.TemplateResponse(template_path, {
            "request": request,
            "email": email,
            "error": "Terjadi kesalahan. Silakan coba lagi."
        })

@router.get("/auth/recovery")
async def auth_recovery_handler(request: Request):
    """Handle Supabase recovery callback - convert fragment to query params"""
    # Return HTML page that will handle fragment conversion via JavaScript
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
        (function() {
            // Check URL fragment first (new Supabase format)
            const hash = window.location.hash.substring(1);
            
            if (hash) {
                const params = new URLSearchParams(hash);
                const error = params.get('error');
                const errorDescription = params.get('error_description');
                const accessToken = params.get('access_token');
                const refreshToken = params.get('refresh_token');
                
                if (error) {
                    window.location.href = '/forgot-password?error=' + encodeURIComponent(errorDescription || error);
                    return;
                } else if (accessToken) {
                    window.location.href = '/reset-password?access_token=' + accessToken + 
                        (refreshToken ? '&refresh_token=' + refreshToken : '');
                    return;
                }
            }
            
            // Check query params (old Supabase format)
            const urlParams = new URLSearchParams(window.location.search);
            const token = urlParams.get('token');
            const type = urlParams.get('type');
            
            if (token && type === 'recovery') {
                // Old format - redirect with message
                window.location.href = '/forgot-password?error=' + 
                    encodeURIComponent('Link sudah kadaluarsa. Silakan request link baru.');
                return;
            }
            
            // No valid params
            window.location.href = '/forgot-password?error=' + 
                encodeURIComponent('Link tidak valid. Silakan request link baru.');
        })();
    </script>
</body>
</html>
    """
    return HTMLResponse(content=html_content)

@router.get("/reset-password")
async def reset_password_page(request: Request):
    """Display reset password form"""
    access_token = request.query_params.get("access_token")
    refresh_token = request.query_params.get("refresh_token")
    
    if not access_token:
        template_path = get_template(request, "login_logout.html")
        return templates.TemplateResponse(template_path, {
            "request": request,
            "error": "Link reset password tidak valid atau sudah kadaluarsa."
        })
    
    template_path = get_template(request, "forgot_password/reset.html")
    return templates.TemplateResponse(template_path, {
        "request": request,
        "access_token": access_token,
        "refresh_token": refresh_token
    })

@router.post("/reset-password")
async def reset_password_submit(
    request: Request,
    access_token: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...)
):
    """Update password using Supabase Auth"""
    try:
        if new_password != confirm_password:
            template_path = get_template(request, "forgot_password/reset.html")
            return templates.TemplateResponse(template_path, {
                "request": request,
                "access_token": access_token,
                "error": "Password tidak cocok."
            })
        
        if len(new_password) < 6:
            template_path = get_template(request, "forgot_password/reset.html")
            return templates.TemplateResponse(template_path, {
                "request": request,
                "access_token": access_token,
                "error": "Password minimal 6 karakter."
            })
        
        supabase = get_supabase()
        
        # Set session with the access token
        supabase.auth.set_session(access_token, access_token)
        
        # Update password - Supabase handles encryption
        supabase.auth.update_user({
            "password": new_password
        })
        
        template_path = get_template(request, "login_logout.html")
        return templates.TemplateResponse(template_path, {
            "request": request,
            "success": "Password berhasil diubah. Silakan login dengan password baru."
        })
        
    except Exception as e:
        template_path = get_template(request, "forgot_password/reset.html")
        return templates.TemplateResponse(template_path, {
            "request": request,
            "access_token": access_token,
            "error": f"Gagal mengubah password: {str(e)}"
        })
