from fastapi import APIRouter, Depends, HTTPException, status, Request, Response, Form
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import timedelta, datetime, timezone
import secrets

from app.database.database import get_db
from app.database.models import User, UserRole
from app.utils.auth import verify_password, create_access_token, create_refresh_token, decode_token
from app.config import load_config

# Load configuration
config = load_config()

router = APIRouter(tags=["authentication"])
templates = Jinja2Templates(directory="app/templates")

# GET login page (HTML form)
@router.get("/login", response_class=HTMLResponse)
@router.head("/login", response_class=HTMLResponse)
async def login_page(request: Request, next: str = None):
    return templates.TemplateResponse("login_logout.html", {"request": request, "next": next})

# POST login from HTML form
@router.post("/login", response_class=HTMLResponse)
async def login_form(
    request: Request,
    response: Response,
    username: str = Form(...),
    password: str = Form(...),
    next: str = Form(None),
    remember: bool = Form(False),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            "login_logout.html",
            {"request": request, "error": "Invalid username or password", "next": next},
            status_code=status.HTTP_401_UNAUTHORIZED
        )

    user.last_login = datetime.now(timezone.utc)
    
    # Set remember_token if remember option is checked
    if remember:
        user.remember_token = secrets.token_hex(32)
    
    db.commit()

    access_token_expires = timedelta(minutes=60 * 24)  # 1 day
    refresh_token_expires = timedelta(days=7)
    access_token = create_access_token(
        data={"sub": user.username, "role": user.role},
        expires_delta=access_token_expires
    )
    refresh_token = create_refresh_token(
        data={"sub": user.username},
        expires_delta=refresh_token_expires
    )

    # Redirect to original URL if available, otherwise to home
    redirect_url = next if next else "/"
    
    response = RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        max_age=60 * 60 * 24,
        samesite="lax",
        secure=False  # Set to False for development
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        max_age=60 * 60 * 24 * 7,
        samesite="lax",
        secure=False  # Set to False for development
    )
    
    # Set remember_token cookie if remember option is checked
    if remember and user.remember_token:
        response.set_cookie(
            key="remember_token",
            value=user.remember_token,
            httponly=True,
            max_age=60 * 60 * 24 * 30,  # 30 days
            samesite="lax",
            secure=False  # Set to False for development
        )
    
    return response

# Token-only login (API access)
@router.post("/login/token")
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.username == form_data.username).first()
    if not user or not verify_password(password=form_data.password, hashed_password=user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user.last_login = datetime.now(timezone.utc)
    db.commit()

    access_token_expires = timedelta(minutes=60 * 24)
    access_token = create_access_token(
        data={
            "sub": user.username,
            "role": user.role
        },
        expires_delta=access_token_expires
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "username": user.username,
        "role": user.role
    }

# Refresh access token
@router.post("/refresh")
async def refresh_token(request: Request, response: Response, db: Session = Depends(get_db)):
    refresh_token = request.cookies.get("refresh_token")
    payload = decode_token(refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    username = payload.get("sub")
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    access_token_expires = timedelta(minutes=60 * 24)
    access_token = create_access_token(
        data={"sub": user.username, "role": user.role},
        expires_delta=access_token_expires
    )
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        max_age=60 * 60 * 24,
        samesite="lax",
        secure=False  # Set to False for development
    )
    return {"access_token": access_token}

# Logout
@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(key="access_token")
    response.delete_cookie(key="refresh_token")
    response.delete_cookie(key="remember_token")
    return response