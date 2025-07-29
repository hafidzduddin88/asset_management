from fastapi import APIRouter, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from supabase import create_client, Client
from app.config import load_config
from app.utils.auth import decode_supabase_jwt, refresh_supabase_token
import logging
from urllib.parse import urlparse
from datetime import datetime, timezone

config = load_config()
supabase: Client = create_client(config.SUPABASE_URL, config.SUPABASE_ANON_KEY)

router = APIRouter(tags=["authentication"])
templates = Jinja2Templates(directory="app/templates")

def sign_in_with_email(email: str, password: str):
    try:
        response = supabase.auth.sign_in_with_password({"email": email, "password": password})
        if hasattr(response, 'error') and response.error:
            return {"success": False, "error": response.error.message}
        return {"success": True, "session": response.session, "user": response.user}
    except Exception as err:
        return {"success": False, "error": str(err)}

def sign_out():
    try:
        supabase.auth.sign_out()
    except Exception as err:
        logging.error(f"Error signing out: {err}")

def get_cookie_settings() -> dict:
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
    cookie_settings = get_cookie_settings()
    access_max_age = 60 * 60 * 24 * 7 if remember_me else 3600
    response.set_cookie(
        key="sb_access_token",
        value=session.access_token,
        max_age=access_max_age,
        **cookie_settings
    )
    response.set_cookie(
        key="sb_refresh_token",
        value=session.refresh_token,
        max_age=60 * 60 * 24 * 30,
        **cookie_settings
    )

def clear_auth_cookies(response):
    cookie_settings = get_cookie_settings()
    response.delete_cookie("sb_access_token", **{k: v for k, v in cookie_settings.items() if k != 'httponly'})
    response.delete_cookie("sb_refresh_token", **{k: v for k, v in cookie_settings.items() if k != 'httponly'})

def is_user_authenticated(request: Request) -> bool:
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
    try:
        result = sign_in_with_email(email, password)
        if not result["success"]:
            raise Exception(result["error"])

        session = result["session"]
        payload = decode_supabase_jwt(session.access_token)
        if not payload or not payload.get("sub"):
            raise Exception("Invalid JWT token received")

        redirect_url = next or "/"
        redirect_response = RedirectResponse(url=redirect_url, status_code=303)
        set_auth_cookies(redirect_response, session, remember_me)

        logging.info(f"User {email} logged in successfully")
        return redirect_response

    except Exception as e:
        logging.error(f"Login failed for {email}: {e}")
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
    try:
        response = supabase.auth.sign_up({
            "email": email,
            "password": password,
            "options": {
                "data": {"full_name": full_name}
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
        logging.error(f"Signup failed for {email}: {e}")
        return templates.TemplateResponse(
            "signup.html",
            {
                "request": request,
                "error": "Signup failed. Please try again or contact support."
            },
            status_code=400
        )

@router.post("/auth/refresh")
async def refresh_token_endpoint(request: Request):
    try:
        refresh_token = request.cookies.get("sb_refresh_token")
        if not refresh_token:
            return JSONResponse(
                content={"success": False, "error": "No refresh token found"},
                status_code=401
            )

        new_tokens = refresh_supabase_token(refresh_token)
        if not new_tokens:
            return JSONResponse(
                content={"success": False, "error": "Token refresh failed"},
                status_code=401
            )

        payload = decode_supabase_jwt(new_tokens["access_token"])
        if not payload or not payload.get("sub"):
            return JSONResponse(
                content={"success": False, "error": "Invalid refreshed token"},
                status_code=401
            )

        response = JSONResponse(content={"success": True, "message": "Token refreshed successfully"})
        cookie_settings = get_cookie_settings()
        response.set_cookie("sb_access_token", new_tokens["access_token"], max_age=3600, **cookie_settings)
        response.set_cookie("sb_refresh_token", new_tokens["refresh_token"], max_age=86400 * 30, **cookie_settings)
        logging.info(f"Token refreshed for user {payload.get('sub')}")
        return response

    except Exception as e:
        logging.error(f"Token refresh endpoint error: {e}")
        return JSONResponse(
            content={"success": False, "error": "Internal server error"},
            status_code=500
        )

@router.get("/logout")
async def logout(request: Request):
    try:
        access_token = request.cookies.get("sb_access_token")
        user_email = "unknown"
        if access_token:
            payload = decode_supabase_jwt(access_token)
            if payload:
                user_email = payload.get("email", "unknown")

        sign_out()
        logging.info(f"User {user_email} logged out successfully")

    except Exception as e:
        logging.warning(f"Logout warning: {str(e)}")

    response = RedirectResponse(url="/login", status_code=303)
    clear_auth_cookies(response)
    return response
