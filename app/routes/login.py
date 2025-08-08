from fastapi import APIRouter, Request, Form, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from app.config import load_config
from app.utils.auth import decode_supabase_jwt
from supabase import create_client, Client
import logging
from urllib.parse import urlparse

config = load_config()
supabase: Client = create_client(config.SUPABASE_URL, config.SUPABASE_ANON_KEY)

router = APIRouter(tags=["authentication"])
templates = Jinja2Templates(directory="app/templates")


def get_cookie_settings() -> dict:
    parsed_url = urlparse(config.APP_URL)
    is_secure = parsed_url.scheme == "https"
    domain = parsed_url.hostname if parsed_url.hostname not in ("localhost", "127.0.0.1") else None
    return {
        "httponly": True,
        "secure": is_secure,
        "samesite": "lax",
        "domain": domain
    }


def set_auth_cookies(response, session, remember_me: bool = False):
    settings = get_cookie_settings()
    access_max_age = 60 * 60 * 24 * 7 if remember_me else 3600
    refresh_max_age = 60 * 60 * 24 * 30

    response.set_cookie("sb_access_token", session.access_token, max_age=access_max_age, **settings)
    response.set_cookie("sb_refresh_token", session.refresh_token, max_age=refresh_max_age, **settings)


def clear_auth_cookies(response):
    settings = get_cookie_settings()
    response.delete_cookie("sb_access_token", **{k: v for k, v in settings.items() if k != "httponly"})
    response.delete_cookie("sb_refresh_token", **{k: v for k, v in settings.items() if k != "httponly"})


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, next: str = "/"):
    if hasattr(request.state, 'user') and request.state.user:
        return RedirectResponse(url=next, status_code=303)
    
    from app.utils.database_manager import get_dropdown_options
    dropdown_options = get_dropdown_options()

    return templates.TemplateResponse("login_logout.html", {
        "request": request, 
        "next": next,
        "business_units": dropdown_options.get('business_units', [])
    })


@router.post("/login")
async def login_form(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    remember_me: bool = Form(False),
    next: str = Form("/")
):
    try:
        # Clear any existing session first
        try:
            supabase.auth.sign_out()
        except:
            pass
        
        # Sign in with fresh credentials
        result = supabase.auth.sign_in_with_password({"email": email, "password": password})
        session = result.session

        # Decode token to verify
        payload = decode_supabase_jwt(session.access_token)
        if not payload or not payload.get("sub"):
            raise Exception("Invalid JWT token received")

        # Create profile if doesn't exist (first time login)
        from app.utils.profile_utils import create_profile_if_not_exists
        create_profile_if_not_exists(payload.get("sub"), email)
        
        # Set fresh cookies
        redirect_response = RedirectResponse(url=next or "/", status_code=303)
        set_auth_cookies(redirect_response, session, remember_me)

        logging.info(f"User {email} logged in successfully with fresh token")
        return redirect_response

    except Exception as e:
        logging.error(f"Login failed for {email}: Authentication error")
        return templates.TemplateResponse(
            "login_logout.html",
            {
                "request": request,
                "error": "Login failed. Please check your credentials.",
                "next": next
            },
            status_code=401
        )


@router.get("/signup", response_class=HTMLResponse)
async def signup_page(request: Request):
    if hasattr(request.state, 'user') and request.state.user:
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse("signup.html", {"request": request})


@router.post("/signup")
async def signup_form(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    full_name: str = Form(...),
    business_unit_name: str = Form(None)
):
    try:
        result = supabase.auth.sign_up({
            "email": email,
            "password": password,
            "options": {"data": {"full_name": full_name, "business_unit_name": business_unit_name}}
        })

        if not result.user:
            raise Exception("Signup failed")
        
        # Create profile with business unit data
        from app.utils.profile_utils import create_profile_if_not_exists
        user_metadata = result.user.user_metadata or {}
        create_profile_if_not_exists(result.user.id, email, user_metadata)

        logging.info("User registered successfully")
        return templates.TemplateResponse(
            "signup.html",
            {
                "request": request,
                "success": "Account created. Please check your email for verification."
            }
        )
    except Exception as e:
        logging.error("Signup failed: Registration error")
        return templates.TemplateResponse(
            "signup.html",
            {
                "request": request,
                "error": "Signup failed. Please try again."
            },
            status_code=400
        )


@router.post("/auth/forgot-password")
async def forgot_password(request: Request):
    try:
        body = await request.json()
        email = body.get('email')
        
        if not email:
            return {"success": False, "error": "Email is required"}
        
        # Send password reset email via Supabase
        result = supabase.auth.reset_password_email(email)
        
        logging.info(f"Password reset email sent to {email}")
        return {"success": True, "message": "Password reset link sent to your email"}
        
    except Exception as e:
        logging.error(f"Forgot password error: {str(e)}")
        return {"success": False, "error": "Failed to send reset link"}


@router.get("/logout")
async def logout(request: Request):
    user_email = "unknown"
    if hasattr(request.state, 'user') and request.state.user:
        user_email = request.state.user.get("email", "unknown")

    try:
        # Get access token from cookies to sign out properly
        access_token = request.cookies.get("sb_access_token")
        if access_token:
            # Set the session before signing out
            supabase.auth.set_session(access_token, request.cookies.get("sb_refresh_token", ""))
        supabase.auth.sign_out()
        logging.info(f"User {user_email} logged out successfully")
    except Exception as e:
        logging.warning(f"Logout error: {e}")

    response = RedirectResponse(url="/login", status_code=303)
    clear_auth_cookies(response)
    return response
