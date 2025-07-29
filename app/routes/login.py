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

    response.set_cookie("sb-access-token", session.access_token, max_age=access_max_age, **settings)
    response.set_cookie("sb-refresh-token", session.refresh_token, max_age=refresh_max_age, **settings)


def clear_auth_cookies(response):
    settings = get_cookie_settings()
    response.delete_cookie("sb-access-token", **{k: v for k, v in settings.items() if k != "httponly"})
    response.delete_cookie("sb-refresh-token", **{k: v for k, v in settings.items() if k != "httponly"})


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, next: str = "/"):
    if request.state.user:
        return RedirectResponse(url=next, status_code=303)

    return templates.TemplateResponse("login_logout.html", {"request": request, "next": next})


@router.post("/login")
async def login_form(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    remember_me: bool = Form(False),
    next: str = Form("/")
):
    try:
        result = supabase.auth.sign_in_with_password({"email": email, "password": password})
        session = result.session

        # Decode token to verify
        payload = decode_supabase_jwt(session.access_token)
        if not payload or not payload.get("sub"):
            raise Exception("Invalid JWT token received")

        # Set cookie
        redirect_response = RedirectResponse(url=next or "/", status_code=303)
        set_auth_cookies(redirect_response, session, remember_me)

        logging.info(f"User {email} logged in")
        return redirect_response

    except Exception as e:
        logging.error(f"Login failed for {email}: {str(e)}")
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
    if request.state.user:
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
        result = supabase.auth.sign_up({
            "email": email,
            "password": password,
            "options": {"data": {"full_name": full_name}}
        })

        if not result.user:
            raise Exception("Signup failed")

        logging.info(f"User {email} registered")
        return templates.TemplateResponse(
            "signup.html",
            {
                "request": request,
                "success": "Account created. Please check your email for verification."
            }
        )
    except Exception as e:
        logging.error(f"Signup failed for {email}: {str(e)}")
        return templates.TemplateResponse(
            "signup.html",
            {
                "request": request,
                "error": "Signup failed. Please try again."
            },
            status_code=400
        )


@router.get("/logout")
async def logout(request: Request):
    user_email = request.state.user.get("email") if request.state.user else "unknown"

    try:
        supabase.auth.sign_out()
        logging.info(f"User {user_email} logged out")
    except Exception as e:
        logging.warning(f"Logout error: {e}")

    response = RedirectResponse(url="/login", status_code=303)
    clear_auth_cookies(response)
    return response
