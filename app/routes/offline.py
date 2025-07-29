# app/routes/offline.py
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter(tags=["offline"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/offline", response_class=HTMLResponse)
async def offline_page(request: Request):
    """Offline page for PWA."""
    return templates.TemplateResponse(
        "offline.html",
        {
            "request": request
        }
    )