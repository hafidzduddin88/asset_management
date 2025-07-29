from fastapi import APIRouter, Request, Response, Form, HTTPException, status
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

@router.post("/login", response_class=HTMLResponse)
async def login_form(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    next: str = Form(None)
):
    try:
        # Use service key client for admin operations
        from supabase import create_client
        admin_supabase = create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_KEY)
        
        response = admin_supabase.auth.sign_in_with_password({
            "email": email,
            "password": password
        })
        
        if not response.user:
            return templates.TemplateResponse(
                "login_logout.html",
                {"request": request, "error": "Invalid email or password", "next": next},
                status_code=401
            )
        
        # Get user profile
        profile_response = admin_supabase.table('profiles').select('*').eq('id', response.user.id).single().execute()
        if not profile_response.data or not profile_response.data.get('is_active'):
            return templates.TemplateResponse(
                "login_logout.html",
                {"request": request, "error": "Account is inactive", "next": next},
                status_code=401
            )
        
        redirect_url = next if next else "/"
        redirect_response = RedirectResponse(url=redirect_url, status_code=303)
        
        redirect_response.set_cookie(
            key="sb_access_token",
            value=response.session.access_token,
            httponly=True,
            max_age=3600,
            samesite="lax",
            secure=True
        )
        
        return redirect_response
        
    except Exception as e:
        logging.error(f"Login error: {str(e)}")
        return templates.TemplateResponse(
            "login_logout.html",
            {"request": request, "error": "Login failed", "next": next},
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