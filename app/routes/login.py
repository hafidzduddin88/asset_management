# app/routes/login.py
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from supabase import create_client, Client
from app.config import load_config
from app.utils.auth import decode_supabase_token
import logging
import os
from urllib.parse import urlparse

config = load_config()
supabase: Client = create_client(config.SUPABASE_URL, config.SUPABASE_ANON_KEY)

router = APIRouter(tags=["authentication"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/login", response_class=HTMLResponse)
@router.head("/login", response_class=HTMLResponse)
async def login_page(request: Request, next: str = None):
    token = request.cookies.get("sb_access_token")

    if token:
        try:
            payload = decode_supabase_token(token)
            if payload.get("sub"):
                return RedirectResponse(url=next or "/", status_code=303)
        except:
            pass

    return templates.TemplateResponse("login_logout.html", {"request": request, "next": next})


@router.post("/login")
async def login_form(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    remember_me: bool = Form(False),
    next: str = Form(None)
):
    try:
        response = supabase.auth.sign_in_with_password({
            "email": email,
            "password": password
        })

        if not response.session or not response.session.access_token:
            raise Exception("Invalid credentials or no session")

        redirect_response = RedirectResponse(url=next or "/", status_code=303)

        # Cookie config
        parsed_url = urlparse(os.getenv("APP_URL", ""))
        domain = parsed_url.hostname if parsed_url.hostname not in [None, "localhost"] else None

        max_age = 60 * 60 * 24 * 7 if remember_me else 3600  # 7 days or 1 hour

        redirect_response.set_cookie(
            key="sb_access_token",
            value=response.session.access_token,
            httponly=True,
            secure=not os.getenv("DEV", False),
            samesite="lax",
            max_age=max_age,
            domain=domain
        )

        return redirect_response

    except Exception as e:
        logging.error(f"Login failed: {str(e)}")
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
    token = request.cookies.get("sb_access_token")

    if token:
        try:
            payload = decode_supabase_token(token)
            if payload.get("sub"):
                return RedirectResponse(url="/", status_code=303)
        except:
            pass

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
                "data": {
                    "full_name": full_name
                }
            }
        })

        if not response.user:
            raise Exception("Signup failed or user already exists")

        return templates.TemplateResponse(
            "signup.html",
            {
                "request": request,
                "success": "Account created! Please check your email to verify."
            }
        )

    except Exception as e:
        logging.error(f"Signup failed: {str(e)}")
        return templates.TemplateResponse(
            "signup.html",
            {
                "request": request,
                "error": "Signup failed. Please try again."
            },
            status_code=400
        )


@router.get("/auth/callback")
async def auth_callback(request: Request):
    return templates.TemplateResponse("auth_callback.html", {"request": request})


@router.post("/auth/confirm")
async def confirm_email(request: Request):
    try:
        data = await request.json()
        token_hash = data.get("token_hash")
        type_param = data.get("type")

        if not token_hash or type_param != "signup":
            return {"success": False, "error": "Invalid parameters"}

        response = supabase.auth.verify_otp({
            "token_hash": token_hash,
            "type": "signup"
        })

        if response.user:
            return {"success": True}
        else:
            return {"success": False, "error": "Verification failed"}

    except Exception as e:
        logging.error(f"Email confirmation failed: {str(e)}")
        return {"success": False, "error": "Confirmation failed"}


@router.get("/logout")
async def logout():
    try:
        supabase.auth.sign_out()
    except Exception as e:
        logging.warning(f"Logout warning: {str(e)}")

    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie("sb_access_token")
    return response
