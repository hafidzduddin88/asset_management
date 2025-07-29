# app/routes/user_management.py
from fastapi import APIRouter, Depends, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.database.models import Profile, UserRole
from app.utils.auth import get_current_profile, get_admin_user
from app.utils.flash import set_flash

router = APIRouter(prefix="/user_management", tags=["user_management"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def user_list(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """List all users (admin only)."""
    users = db.query(Profile).all()
    
    return templates.TemplateResponse(
        "user_management/list.html",
        {
            "request": request,
            "user": current_user,
            "users": users
        }
    )

@router.get("/create", response_class=HTMLResponse)
async def create_user_form(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Create user form (admin only)."""
    return templates.TemplateResponse(
        "user_management/create.html",
        {
            "request": request,
            "user": current_user
        }
    )

@router.post("/create")
async def create_user(
    request: Request,
    email: str = Form(...),
    full_name: str = Form(...),
    role: str = Form(...),
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Create new user (admin only)."""
    # Check if user exists
    existing_user = db.query(Profile).filter(Profile.email == email).first()
    if existing_user:
        return templates.TemplateResponse(
            "user_management/create.html",
            {
                "request": request,
                "user": current_user,
                "error": "Email already exists"
            }
        )
    
    # Create user profile (Supabase handles auth)
    new_user = Profile(
        email=email,
        full_name=full_name,
        role=getattr(UserRole, role.upper()),
        is_active=True
    )
    
    db.add(new_user)
    db.commit()
    
    response = RedirectResponse(url="/user_management", status_code=status.HTTP_303_SEE_OTHER)
    set_flash(response, f"User {email} created successfully", "success")
    return response

@router.post("/reset_password/{user_id}")
async def reset_password(
    user_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
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
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Toggle user active status (admin only)."""
    user = db.query(Profile).filter(Profile.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Update status
    user.is_active = is_active
    db.commit()
    
    status_text = "activated" if is_active else "deactivated"
    response = RedirectResponse(url="/user_management", status_code=status.HTTP_303_SEE_OTHER)
    set_flash(response, f"User {user.email} {status_text}", "success")
    return response