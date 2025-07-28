from fastapi import APIRouter, Depends, Request, Form, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from supabase import create_client, Client
from app.config import load_config
import secrets

config = load_config()
router = APIRouter(tags=["authentication"])
templates = Jinja2Templates(directory="app/templates")

# Supabase client
supabase: Client = create_client(config.APP_URL, config.SUPABASE_SERVICE_KEY)


# ✅ GET Login Page
@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, next: str = None):
    return templates.TemplateResponse("login.html", {"request": request, "next": next})


# ✅ POST Login (HTML form)
@router.post("/login", response_class=HTMLResponse)
async def login_form(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    remember: bool = Form(False),
    next: str = Form(None)
):
    try:
        # Call Supabase Auth sign-in
        response = supabase.auth.sign_in_with_password({"email": email, "password": password})

        if not response.user:
            return templates.TemplateResponse(
                "login.html",
                {"request": request, "error": "Invalid email or password", "next": next},
                status_code=status.HTTP_401_UNAUTHORIZED
            )

        # Get access token and refresh token
        access_token = response.session.access_token
        refresh_token = response.session.refresh_token

        # Redirect to next page or home
        redirect_url = next if next else "/"
        redirect_response = RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)

        # Set cookies
        max_age_access = 60 * 60 * 24  # 1 day
        max_age_refresh = 60 * 60 * 24 * 7  # 7 days

        redirect_response.set_cookie(
            key="access_token",
            value=access_token,
            httponly=True,
            max_age=max_age_access,
            samesite="lax",
            secure=False  # change to True in production
        )

        redirect_response.set_cookie(
            key="refresh_token",
            value=refresh_token,
            httponly=True,
            max_age=max_age_refresh,
            samesite="lax",
            secure=False
        )

        if remember:
            redirect_response.set_cookie(
                key="remember_me",
                value=secrets.token_hex(16),
                httponly=True,
                max_age=60 * 60 * 24 * 30,  # 30 days
                samesite="lax",
                secure=False
            )

        return redirect_response

    except Exception as e:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": f"Login failed: {str(e)}", "next": next},
            status_code=status.HTTP_400_BAD_REQUEST
        )


# ✅ Logout
@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(key="access_token")
    response.delete_cookie(key="refresh_token")
    response.delete_cookie(key="remember_me")
    return response