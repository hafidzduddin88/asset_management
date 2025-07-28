from fastapi import APIRouter, Request, Form, Depends, HTTPException, status, Response
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.security import OAuth2PasswordRequestForm
import os
from supabase import create_client, Client

# Load Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

router = APIRouter(tags=["authentication"])
templates = Jinja2Templates(directory="app/templates")

# ✅ GET Login Page
@router.get("/login", response_class=HTMLResponse)
@router.head("/login", response_class=HTMLResponse)
async def login_page(request: Request, next: str = "/"):
    return templates.TemplateResponse("login_logout.html", {"request": request, "next": next})

# ✅ POST Login (HTML Form)
@router.post("/login", response_class=HTMLResponse)
async def login_form(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    next: str = Form("/")
):
    try:
        auth_res = supabase.auth.sign_in_with_password({"email": username, "password": password})
        if not auth_res or not auth_res.session:
            return templates.TemplateResponse(
                "login_logout.html",
                {"request": request, "error": "Invalid username or password", "next": next},
                status_code=status.HTTP_401_UNAUTHORIZED
            )

        access_token = auth_res.session.access_token
        refresh_token = auth_res.session.refresh_token

        response = RedirectResponse(url=next, status_code=status.HTTP_303_SEE_OTHER)
        response.set_cookie("access_token", access_token, httponly=True, samesite="lax", max_age=86400)  # 1 day
        response.set_cookie("refresh_token", refresh_token, httponly=True, samesite="lax", max_age=604800)  # 7 days
        return response

    except Exception as e:
        return templates.TemplateResponse(
            "login_logout.html",
            {"request": request, "error": f"Login failed: {str(e)}", "next": next},
            status_code=status.HTTP_400_BAD_REQUEST
        )

# ✅ API Login (Token Only)
@router.post("/login/token")
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    try:
        auth_res = supabase.auth.sign_in_with_password({
            "email": form_data.username,
            "password": form_data.password
        })
        if not auth_res or not auth_res.session:
            raise HTTPException(status_code=401, detail="Invalid credentials")

        return {
            "access_token": auth_res.session.access_token,
            "refresh_token": auth_res.session.refresh_token,
            "token_type": "bearer",
            "user_id": auth_res.user.id,
            "email": auth_res.user.email
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Login failed: {str(e)}")

# ✅ Refresh Token (using Supabase)
@router.post("/refresh")
async def refresh_token(request: Request, response: Response):
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        raise HTTPException(status_code=401, detail="Missing refresh token")

    try:
        session = supabase.auth.refresh_session(refresh_token)
        if not session or not session.session:
            raise HTTPException(status_code=401, detail="Invalid refresh token")

        new_access = session.session.access_token
        new_refresh = session.session.refresh_token

        response.set_cookie("access_token", new_access, httponly=True, samesite="lax", max_age=86400)
        response.set_cookie("refresh_token", new_refresh, httponly=True, samesite="lax", max_age=604800)
        return {"access_token": new_access}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Refresh failed: {str(e)}")

# ✅ Logout
@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token")
    return response