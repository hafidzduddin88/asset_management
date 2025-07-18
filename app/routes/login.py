from fastapi import (
    APIRouter, Depends, HTTPException, status,
    Request, Response, Form
)
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import timedelta, datetime, timezone

from app.database.database import get_db
from app.database.models import User
from app.utils.auth import verify_password, create_access_token
from app.config import load_config

# Load configuration
config = load_config()

router = APIRouter(tags=["authentication"])
templates = Jinja2Templates(directory="app/templates")

# --- GET LOGIN PAGE ---
@router.get("/login", response_class=HTMLResponse)
@router.head("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login_logout.html", {"request": request})

# --- HANDLE LOGIN FORM (HTML) ---
@router.post("/login", response_class=HTMLResponse)
async def login_form(
    request: Request,
    response: Response,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.username == username).first()

    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            "login_logout.html",
            {"request": request, "error": "Invalid username or password"},
            status_code=status.HTTP_401_UNAUTHORIZED
        )

    # Update last login
    user.last_login = datetime.now(timezone.utc)
    db.commit()

    # Generate JWT token
    access_token_expires = timedelta(minutes=60 * 24)  # 24 jam
    access_token = create_access_token(
        data={"sub": user.username, "role": user.role},
        expires_delta=access_token_expires
    )

    # Set token in HTTP-only cookie
    response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        max_age=60 * 60 * 24,
        samesite="lax",
        secure=False  # Ganti ke True saat sudah HTTPS
    )
    return response

# --- HANDLE TOKEN REQUEST (API CLIENT) ---
@router.post("/login/token")
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.username == form_data.username).first()

    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Update last login
    user.last_login = datetime.now(timezone.utc)
    db.commit()

    # Generate token
    access_token_expires = timedelta(minutes=60 * 24)
    access_token = create_access_token(
        data={"sub": user.username, "role": user.role},
        expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

# --- HANDLE LOGOUT ---
@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(key="access_token")
    return response