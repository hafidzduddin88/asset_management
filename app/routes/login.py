# app/routes/login.py
from fastapi import APIRouter, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from supabase import create_client, Client
from app.config import load_config
from app.utils.auth import decode_supabase_jwt, refresh_supabase_token
import logging
import os
from urllib.parse import urlparse
from datetime import datetime, timezone

config = load_config()
supabase: Client = create_client(config.SUPABASE_URL, config.SUPABASE_ANON_KEY)

router = APIRouter(tags=["authentication"])
templates = Jinja2Templates(directory="app/templates")

def sign_in_with_email(email: str, password: str):
    """Login with email and password - Supabase style"""
    try:
        response = supabase.auth.sign_in_with_password({"email": email, "password": password})
        
        if hasattr(response, 'error') and response.error:
            return {"success": False, "error": response.error.message}
        
        # Supabase automatically handles JWT rotation
        return {
            "success": True,
            "session": response.session,
            "user": response.user
        }
    except Exception as err:
        return {"success": False, "error": str(err)}

def refresh_session():
    """Manual token refresh if needed"""
    try:
        response = supabase.auth.refresh_session()
        if hasattr(response, 'error') and response.error:
            return None
        return response.session
    except Exception:
        return None

def sign_out():
    """Logout function"""
    try:
        supabase.auth.sign_out()
    except Exception as err:
        logging.error(f"Error signing out: {err}")

def get_cookie_settings() -> dict:
    """Get secure cookie settings based on environment"""
    parsed_url = urlparse(config.APP_URL)
    is_secure = not config.APP_URL.startswith("http://localhost")
    domain = parsed_url.hostname if parsed_url.hostname not in [None, "localhost"] else None
    
    return {
        "httponly": True,
        "secure": is_secure,
        "samesite": "lax",
        "domain": domain
    }

def set_auth_cookies(response, session, remember_me: bool = False):
    """Set authentication cookies with proper security"""
    cookie_settings = get_cookie_settings()
    
    # Access token (short-lived)
    access_max_age = 60 * 60 * 24 * 7 if remember_me else 3600  # 7 days or 1 hour
    response.set_cookie(
        key="sb_access_token",
        value=session.access_token,
        max_age=access_max_age,
        **cookie_settings
    )
    
    # Refresh token (long-lived)
    refresh_max_age = 60 * 60 * 24 * 30  # 30 days
    response.set_cookie(
        key="sb_refresh_token",
        value=session.refresh_token,
        max_age=refresh_max_age,
        **cookie_settings
    )

def clear_auth_cookies(response):
    """Clear authentication cookies"""
    cookie_settings = get_cookie_settings()
    response.delete_cookie("sb_access_token", **{k: v for k, v in cookie_settings.items() if k != 'httponly'})
    response.delete_cookie("sb_refresh_token", **{k: v for k, v in cookie_settings.items() if k != 'httponly'})

def is_user_authenticated(request: Request) -> bool:
    """Check if user is already authenticated"""
    access_token = request.cookies.get("sb_access_token")
    refresh_token = request.cookies.get("sb_refresh_token")
    
    if access_token:
        payload = decode_supabase_jwt(access_token)
        if payload and payload.get("sub"):
            return True
    
    if refresh_token:
        new_tokens = refresh_supabase_token(refresh_token)
        if new_tokens:
            return True
    
    return False

@router.get("/login", response_class=HTMLResponse)
@router.head("/login", response_class=HTMLResponse)
async def login_page(request: Request, next: str = None):
    """Login page with authentication check"""
    # Redirect if already authenticated
    if is_user_authenticated(request):
        return RedirectResponse(url=next or "/", status_code=303)
    
    return templates.TemplateResponse("login_logout.html", {
        "request": request, 
        "next": next
    })

@router.post("/login")
async def login_form(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    remember_me: bool = Form(False),
    next: str = Form(None)
):
    """Enhanced login with Supabase auth and JWT rotation support"""
    try:
        # Use Supabase-style login
        result = sign_in_with_email(email, password)
        
        if not result["success"]:
            raise Exception(result["error"])
        
        response = result
        session = result["session"]
        
        # Validate JWT token
        payload = decode_supabase_jwt(session.access_token)
        if not payload or not payload.get("sub"):
            raise Exception("Invalid JWT token received")
        
        # Create redirect response
        redirect_url = next or "/"
        redirect_response = RedirectResponse(url=redirect_url, status_code=303)
        
        # Set authentication cookies
        set_auth_cookies(redirect_response, session, remember_me)
        
        logging.info(f"User {email} logged in successfully")
        return redirect_response
        
    except Exception as e:
        error_msg = str(e)
        logging.error(f"Login failed for {email}: {error_msg}")
        
        # Return error response
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
    """Signup page with authentication check"""
    # Redirect if already authenticated
    if is_user_authenticated(request):
        return RedirectResponse(url="/", status_code=303)
    
    return templates.TemplateResponse("signup.html", {"request": request})

@router.post("/signup")
async def signup_form(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    full_name: str = Form(...)
):
    """Enhanced signup with Supabase auth"""
    try:
        # Attempt signup
        response = supabase.auth.sign_up({
            "email": email,
            "password": password,
            "options": {
                "data": {
                    "full_name": full_name
                }
            }
        })
        
        if not response.user:
            raise Exception("Signup failed - user may already exist")
        
        logging.info(f"User {email} signed up successfully")
        
        return templates.TemplateResponse(
            "signup.html",
            {
                "request": request,
                "success": "Account created! Please check your email to verify your account."
            }
        )
        
    except Exception as e:
        error_msg = str(e)
        logging.error(f"Signup failed for {email}: {error_msg}")
        
        return templates.TemplateResponse(
            "signup.html",
            {
                "request": request,
                "error": "Signup failed. Please try again or contact support."
            },
            status_code=400
        )

@router.get("/auth/callback")
async def auth_callback(request: Request):
    """OAuth callback handler"""
    return templates.TemplateResponse("auth_callback.html", {"request": request})

@router.post("/auth/confirm")
async def confirm_email(request: Request):
    """Email confirmation endpoint"""
    try:
        data = await request.json()
        token_hash = data.get("token_hash")
        type_param = data.get("type")
        
        if not token_hash or type_param != "signup":
            return JSONResponse(
                content={"success": False, "error": "Invalid parameters"},
                status_code=400
            )
        
        # Verify OTP
        response = supabase.auth.verify_otp({
            "token_hash": token_hash,
            "type": "signup"
        })
        
        if response.user:
            logging.info(f"Email confirmed for user {response.user.email}")
            return JSONResponse(content={"success": True})
        else:
            return JSONResponse(
                content={"success": False, "error": "Verification failed"},
                status_code=400
            )
            
    except Exception as e:
        logging.error(f"Email confirmation failed: {str(e)}")
        return JSONResponse(
            content={"success": False, "error": "Confirmation failed"},
            status_code=500
        )

@router.post("/auth/refresh")
async def refresh_token_endpoint(request: Request):
    """Manual token refresh endpoint for client-side use"""
    try:
        refresh_token = request.cookies.get("sb_refresh_token")
        if not refresh_token:
            return JSONResponse(
                content={"success": False, "error": "No refresh token found"},
                status_code=401
            )
        
        # Attempt token refresh
        new_tokens = refresh_supabase_token(refresh_token)
        if not new_tokens:
            return JSONResponse(
                content={"success": False, "error": "Token refresh failed"},
                status_code=401
            )
        
        # Validate new token
        payload = decode_supabase_jwt(new_tokens["access_token"])
        if not payload or not payload.get("sub"):
            return JSONResponse(
                content={"success": False, "error": "Invalid refreshed token"},
                status_code=401
            )
        
        # Create response with new tokens
        response = JSONResponse(content={
            "success": True,
            "message": "Token refreshed successfully"
        })
        
        # Update cookies
        cookie_settings = get_cookie_settings()
        response.set_cookie(
            key="sb_access_token",
            value=new_tokens["access_token"],
            max_age=3600,
            **cookie_settings
        )
        response.set_cookie(
            key="sb_refresh_token",
            value=new_tokens["refresh_token"],
            max_age=86400 * 30,
            **cookie_settings
        )
        
        logging.info(f"Token refreshed for user {payload.get('sub')}")
        return response
        
    except Exception as e:
        logging.error(f"Token refresh endpoint error: {str(e)}")
        return JSONResponse(
            content={"success": False, "error": "Internal server error"},
            status_code=500
        )

@router.post("/auth/forgot-password")
async def forgot_password(request: Request):
    """Password reset endpoint"""
    try:
        data = await request.json()
        email = data.get("email")
        
        if not email:
            return JSONResponse(
                content={"success": False, "error": "Email is required"},
                status_code=400
            )
        
        # Send password reset email
        response = supabase.auth.reset_password_email(email)
        
        logging.info(f"Password reset requested for {email}")
        
        return JSONResponse(content={
            "success": True,
            "message": "Password reset link sent to your email"
        })
        
    except Exception as e:
        logging.error(f"Password reset failed: {str(e)}")
        return JSONResponse(
            content={"success": False, "error": "Failed to send reset link"},
            status_code=500
        )

@router.get("/logout")
async def logout(request: Request):
    """Enhanced logout with proper cleanup"""
    try:
        # Get current user info for logging
        access_token = request.cookies.get("sb_access_token")
        user_email = "unknown"
        
        if access_token:
            payload = decode_supabase_jwt(access_token)
            if payload:
                user_email = payload.get("email", "unknown")
        
        # Sign out using Supabase-style function
        sign_out()
        
        logging.info(f"User {user_email} logged out successfully")
        
    except Exception as e:
        logging.warning(f"Logout warning: {str(e)}")
    
    # Create redirect response and clear cookies
    response = RedirectResponse(url="/login", status_code=303)
    clear_auth_cookies(response)
    
    return response