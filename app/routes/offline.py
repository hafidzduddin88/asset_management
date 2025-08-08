# app/routes/offline.py
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from app.utils.device_detector import get_template

router = APIRouter(tags=["offline"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/offline", response_class=HTMLResponse)
async def offline_page(request: Request):
    """Offline page for PWA."""
    template_path = get_template(request, "offline.html")
    return templates.TemplateResponse(
        template_path,
        {
            "request": request
        }
    )