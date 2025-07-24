# /app/app/routes/assets.py
from fastapi import APIRouter, Request, Depends
from starlette.templating import Jinja2Templates
from app.utils.auth import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/assets")
async def assets_page(request: Request, current_user = Depends(get_current_user)):
    """Assets listing page with filtering and pagination"""
    return templates.TemplateResponse("assets.html", {
        "request": request,
        "user": current_user
    })