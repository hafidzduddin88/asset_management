# /app/app/routes/damage_report.py
from fastapi import APIRouter, Request, Depends
from starlette.templating import Jinja2Templates
from app.utils.auth import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/damage/report")
async def damage_report_page(request: Request, current_user = Depends(get_current_user)):
    """Damage report page"""
    return templates.TemplateResponse("damage_report.html", {
        "request": request,
        "user": current_user
    })

@router.post("/damage/report")
async def submit_damage_report(request: Request, current_user = Depends(get_current_user)):
    """Submit damage report - requires admin approval"""
    # This would handle the form submission
    # For now, just return success
    return {"status": "success", "message": "Damage report submitted for approval"}