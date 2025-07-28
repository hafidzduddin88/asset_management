# app/routes/login.py
from fastapi import APIRouter, Request, Response, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from supabase import create_client, Client
from datetime import timedelta
import secrets

from app.config import load_config

config = load_config()
router = APIRouter(tags=["authentication"])
templates = Jinja2Templates(directory="app/templates")

# Initialize Supabase client
supabase: Client = create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_KEY)


# ✅ GET login page
@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, next: str = None):
    return templates.TemplateResponse("login_logout.html", {"request": request, "next": next})


# ✅ POST login
@router.post("/login", response_class=HTMLResponse)
async def login_form(
    request: Request,
    response: Response,
    email: str = Form(...),
    password: str = Form(...),
    next: str = Form(None),
    remember: bool = Form(False),
):
    try:
        # Supabase Auth sign in
        auth_response = supabase.auth.sign_in_with_password({"email": email, "password": password})
        if not auth_response or not auth_response.session:
            return templates.TemplateResponse(
                "login_logout.html",
                {"request": request, "error": "Invalid email or password", "next": next},
                status_code=status.HTTP_401_UNAUTHORIZED
            )

        session = auth_response.session
        user = auth_response.user

        # Ambil profile user dari tabel profiles (Supabase public.profiles)
        profile_data = supabase.table("profiles").select("*").eq("auth_user_id", user.id).execute()
        profile = profile_data.data[0] if profile_data.data else {}

        full_name = profile.get("full_name", user.email)
        photo_url = profile.get("photo_url")

        # Set cookies (access_token)
        response = RedirectResponse(url=next if next else "/", status_code=status.HTTP_303_SEE_OTHER)
        response.set_cookie(
            key="sb_access_token",
            value=session.access_token,
            httponly=True,
            max_age=60 * 60 * 24 * 7 if remember else 60 * 60 * 24,  # 7 hari jika remember
            samesite="lax",
            secure=False  # Set True jika HTTPS
        )

        # Simpan info user di cookie (non-HTTPOnly)
        response.set_cookie("user_name", full_name, max_age=60 * 60 * 24)
        if photo_url:
            response.set_cookie("user_photo", photo_url, max_age=60 * 60 * 24)

        return response

    except Exception as e:
        return templates.TemplateResponse(
            "login_logout.html",
            {"request": request, "error": f"Login failed: {str(e)}", "next": next},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# ✅ Logout
@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(key="sb_access_token")
    response.delete_cookie(key="user_name")
    response.delete_cookie(key="user_photo")
    return response