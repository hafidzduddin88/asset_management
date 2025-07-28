# app/routes/user_management.py
from fastapi import APIRouter, Depends, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from passlib.context import CryptContext

from app.database.database import get_db
from app.database.models import User, UserRole
from app.database.dependencies import get_admin_user
from app.utils.flash import set_flash

router = APIRouter(prefix="/user_management", tags=["user_management"])
templates = Jinja2Templates(directory="app/templates")
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

@router.get("/", response_class=HTMLResponse)
async def user_list(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
):
    """List all users (admin only)."""
    users = db.query(User).all()
    
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
    current_user: User = Depends(get_admin_user)
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
    username: str = Form(...),
    email: str = Form(...),
    full_name: str = Form(...),
    role: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
):
    """Create new user (admin only)."""
    # Check if user exists
    existing_user = db.query(User).filter(User.username == username).first()
    if existing_user:
        return templates.TemplateResponse(
            "user_management/create.html",
            {
                "request": request,
                "user": current_user,
                "error": "Username already exists"
            }
        )
    
    # Create user
    hashed_password = pwd_context.hash(password)
    new_user = User(
        username=username,
        email=email,
        full_name=full_name,
        hashed_password=hashed_password,
        role=UserRole(role),
        is_active=True
    )
    
    db.add(new_user)
    db.commit()
    
    response = RedirectResponse(url="/user_management", status_code=status.HTTP_303_SEE_OTHER)
    set_flash(response, f"User {username} created successfully", "success")
    return response

@router.post("/reset_password/{user_id}")
async def reset_password(
    user_id: int,
    request: Request,
    new_password: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
):
    """Reset user password (admin only)."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Update password
    user.hashed_password = pwd_context.hash(new_password)
    db.commit()
    
    response = RedirectResponse(url="/user_management", status_code=status.HTTP_303_SEE_OTHER)
    set_flash(response, f"Password reset for {user.username}", "success")
    return response

@router.post("/toggle_status/{user_id}")
async def toggle_user_status(
    user_id: int,
    request: Request,
    is_active: bool = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
):
    """Toggle user active status (admin only)."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Update status
    user.is_active = is_active
    db.commit()
    
    status_text = "activated" if is_active else "deactivated"
    response = RedirectResponse(url="/user_management", status_code=status.HTTP_303_SEE_OTHER)
    set_flash(response, f"User {user.username} {status_text}", "success")
    return response