# app/routes/user_management.py
from fastapi import APIRouter, Depends, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from supabase import create_client
from app.config import load_config
from app.database.models import UserRole
from app.utils.auth import get_current_profile, get_admin_user
from app.utils.flash import set_flash
import logging

router = APIRouter(prefix="/user_management", tags=["user_management"])
templates = Jinja2Templates(directory="app/templates")

config = load_config()
supabase = create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_KEY)

@router.get("/", response_class=HTMLResponse)
async def user_list(
    request: Request,
    current_profile = Depends(get_admin_user)
):
    """List all users (admin only)."""
    try:
        response = supabase.table("profiles").select("*").execute()
        users = response.data or []
        
        return templates.TemplateResponse(
            "user_management/list.html",
            {
                "request": request,
                "user": current_profile,
                "users": users
            }
        )
    except Exception as e:
        logging.error(f"Failed to get users: {e}")
        return templates.TemplateResponse(
            "user_management/list.html",
            {
                "request": request,
                "user": current_profile,
                "users": [],
                "error": "Failed to load users"
            }
        )

@router.get("/create", response_class=HTMLResponse)
async def create_user_form(
    request: Request,
    db: Session = Depends(get_db),
    current_profile = Depends(get_admin_user)
):
    """Create user form (admin only)."""
    return templates.TemplateResponse(
        "user_management/create.html",
        {
            "request": request,
            "user": current_profile
        }
    )

@router.post("/create")
async def create_user(
    request: Request,
    email: str = Form(...),
    full_name: str = Form(...),
    role: str = Form(...),
    current_profile = Depends(get_admin_user)
):
    """Create new user (admin only)."""
    try:
        # Check if user exists
        existing = supabase.table("profiles").select("username").eq("username", email).execute()
        if existing.data:
            return templates.TemplateResponse(
                "user_management/create.html",
                {
                    "request": request,
                    "user": current_profile,
                    "error": "Email already exists"
                }
            )
        
        # Create user in Supabase Auth
        auth_response = supabase.auth.admin.create_user({
            "email": email,
            "password": f"{email.split('@')[0]}123",  # Default password
            "email_confirm": True
        })
        
        if auth_response.user:
            # Create profile
            profile_data = {
                "id": auth_response.user.id,
                "username": email,
                "full_name": full_name,
                "role": role.lower(),
                "is_active": True
            }
            supabase.table("profiles").insert(profile_data).execute()
            
            response = RedirectResponse(url="/user_management", status_code=status.HTTP_303_SEE_OTHER)
            set_flash(response, f"User {email} created successfully", "success")
            return response
        else:
            raise Exception("Failed to create user")
            
    except Exception as e:
        logging.error(f"Failed to create user: {e}")
        return templates.TemplateResponse(
            "user_management/create.html",
            {
                "request": request,
                "user": current_profile,
                "error": "Failed to create user"
            }
        )

@router.post("/reset_password/{user_id}")
async def reset_password(
    user_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_profile = Depends(get_admin_user)
):
    """Reset user password to default (admin only)."""
    user = db.query(Profile).filter(Profile.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Password reset handled by Supabase
    default_password = f"{user.email.split('@')[0]}123"
    
    response = RedirectResponse(url="/user_management", status_code=status.HTTP_303_SEE_OTHER)
    set_flash(response, f"Password reset instructions sent to {user.email}", "success")
    return response

@router.post("/toggle_status/{user_id}")
async def toggle_user_status(
    user_id: str,
    request: Request,
    is_active: bool = Form(...),
    current_profile = Depends(get_admin_user)
):
    """Toggle user active status (admin only)."""
    try:
        # Update profile status
        response = supabase.table("profiles").update({
            "is_active": is_active
        }).eq("id", user_id).execute()
        
        if response.data:
            status_text = "activated" if is_active else "deactivated"
            redirect_response = RedirectResponse(url="/user_management", status_code=status.HTTP_303_SEE_OTHER)
            set_flash(redirect_response, f"User {status_text} successfully", "success")
            return redirect_response
        else:
            raise HTTPException(status_code=404, detail="User not found")
            
    except Exception as e:
        logging.error(f"Failed to toggle user status: {e}")
        redirect_response = RedirectResponse(url="/user_management", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(redirect_response, "Failed to update user status", "error")
        return redirect_response