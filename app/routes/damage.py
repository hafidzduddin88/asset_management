# /app/app/routes/damage_report.py
from fastapi import APIRouter, Request, Depends
from starlette.templating import Jinja2Templates
from app.utils.auth import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/")
async def damaged_assets_page(request: Request, current_user = Depends(get_current_user)):
    """Damaged assets page with search and log functionality"""
    from app.utils.sheets import get_all_assets
    import logging
    
    # Get real asset data from Google Sheets
    all_assets = get_all_assets()
    logging.info(f"Asset Issue: Retrieved {len(all_assets)} total assets")
    
    # Debug: Check for Under Repair assets
    under_repair_assets = [asset for asset in all_assets if asset.get("Status", "") == "Under Repair"]
    logging.info(f"Asset Issue: Found {len(under_repair_assets)} Under Repair assets")
    
    # Debug: Log all unique statuses
    statuses = set(asset.get("Status", "No Status") for asset in all_assets)
    logging.info(f"Asset Issue: All statuses found: {statuses}")
    
    # Debug: Log sample asset if available
    if all_assets:
        sample_asset = all_assets[0]
        logging.info(f"Asset Issue: Sample asset keys: {list(sample_asset.keys())}")
        logging.info(f"Asset Issue: Sample asset status: '{sample_asset.get('Status', 'NO STATUS FIELD')}'")
    
    return templates.TemplateResponse("damaged_assets.html", {
        "request": request,
        "user": current_user,
        "assets_data": all_assets
    })

@router.post("/report")
async def submit_damage_report(request: Request, current_user = Depends(get_current_user)):
    """Submit damage report - requires admin approval"""
    # This would handle the form submission
    # For now, just return success
    return {"status": "success", "message": "Damage report submitted for approval"}