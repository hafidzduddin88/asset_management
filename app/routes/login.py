# app/routes/login.py
from fastapi import APIRouter, Request, Response, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from supabase import create_client, Client
from app.config import load_config
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
    return templates.TemplateResponse("login_logout.html", {"request": request, "next": next})

@router.post("/login", response_class=HTMLResponse)
async def login_form(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    next: str = Form(None)
):
    try:
        response = supabase.auth.sign_in_with_password({
            "email": email,
            "password": password
        })
        # Render.com specific cookie configuration
        render_domain = urlparse(os.getenv('APP_URL', '')).netloc
        
        redirect_response = RedirectResponse(url=next or "/", status_code=303)
        
        # Adjust cookie settings for Render
        redirect_response.set_cookie(
            key="sb_access_token",
            value=response.session.access_token,
            httponly=True,
            secure=True,
            samesite="lax",
            max_age=3600,
            domain=render_domain or None  # Use None if domain parsing fails
        )
        
        return redirect_response
    except Exception as e:
        # Detailed logging
        logging.error(f"Login Error on Render: {str(e)}", extra={
            'email': email,
            'render_url': os.getenv('APP_URL')
        })
        
        return templates.TemplateResponse(
            "login_logout.html",
            {
                "request": request, 
                "error": "Login failed. Please check your credentials.",
                "next": next
            },
            status_code=401
        )

@router.get("/auth/callback")
async def auth_callback(request: Request):
    return templates.TemplateResponse("auth_callback.html", {"request": request})

@router.get("/logout")
async def logout():
    try:
        supabase.auth.sign_out()
    except:
        pass
    
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(key="sb_access_token")
    return response