# app/routes/login.py
from fastapi import APIRouter, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from supabase import create_client, Client
from app.config import load_config
import logging

config = load_config()
supabase: Client = create_client(config.SUPABASE_URL, config.SUPABASE_ANON_KEY)

router = APIRouter(tags=["authentication"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/login", response_class=HTMLResponse)
@router.head("/login", response_class=HTMLResponse)
async def login_page(request: Request, next: str = None):
    return templates.TemplateResponse("login_logout.html", {"request": request, "next": next})

@router.post("/login")
async def login_form(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    next: str = Form(None)
):
    try:
        # Supabase auth with ECC P-256 JWT
        response = supabase.auth.sign_in_with_password({
            "email": email,
            "password": password
        })
        
        if not response.session or not response.session.access_token:
            raise Exception("Authentication failed")
        
        redirect_response = RedirectResponse(url=next or "/", status_code=303)
        
        # Set JWT token cookie for ECC P-256 verification
        redirect_response.set_cookie(
            key="sb_access_token",
            value=response.session.access_token,
            httponly=True,
            secure=False,  # Set True in production with HTTPS
            samesite="lax",
            max_age=3600
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

@router.get("/logout")
async def logout():
    try:
        supabase.auth.sign_out()
    except:
        pass
    
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(key="sb_access_token")
    return response