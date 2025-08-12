# app/routes/depreciation.py
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime
import logging

from app.utils.auth import get_current_profile, UserRole
from app.utils.database_manager import get_supabase
from app.utils.device_detector import get_template

router = APIRouter(prefix="/depreciation", tags=["depreciation"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def depreciation_page(request: Request, current_profile = Depends(get_current_profile)):
    """Depreciation update page (admin only)"""
    if current_profile.role != UserRole.ADMIN:
        return JSONResponse({"error": "Access denied"}, status_code=403)
    
    template_path = get_template(request, "depreciation/index.html")
    return templates.TemplateResponse(template_path, {
        "request": request,
        "user": current_profile,
        "current_year": datetime.now().year
    })

@router.post("/update")
async def update_depreciation(request: Request, current_profile = Depends(get_current_profile)):
    """Update all assets depreciation and book values"""
    if current_profile.role != UserRole.ADMIN:
        return JSONResponse({"error": "Access denied"}, status_code=403)
    
    try:
        supabase = get_supabase()
        current_year = datetime.now().year
        
        # Get all assets with category info
        assets_response = supabase.table('assets').select('''
            asset_id, purchase_date, purchase_cost, year,
            ref_categories(residual_percent, useful_life)
        ''').execute()
        
        updated_count = 0
        
        for asset in assets_response.data:
            try:
                purchase_cost = float(asset.get('purchase_cost', 0) or 0)
                if purchase_cost <= 0:
                    continue
                
                # Get category data
                category = asset.get('ref_categories')
                if not category:
                    continue
                
                residual_percent = float(category.get('residual_percent', 0) or 0)
                useful_life = int(category.get('useful_life', 0) or 0)
                
                if useful_life <= 0:
                    continue
                
                # Calculate years used
                purchase_year = asset.get('year', current_year)
                years_used = current_year - purchase_year
                
                # Calculate values
                residual_value = purchase_cost * (residual_percent / 100)
                annual_depreciation = (purchase_cost - residual_value) / useful_life
                
                if years_used >= useful_life:
                    # Fully depreciated
                    depreciation_value = purchase_cost - residual_value
                    book_value = residual_value
                else:
                    # Partial depreciation
                    depreciation_value = annual_depreciation * years_used
                    book_value = purchase_cost - depreciation_value
                
                # Update asset
                supabase.table('assets').update({
                    'depreciation_value': round(depreciation_value, 2),
                    'book_value': round(book_value, 2),
                    'residual_value': round(residual_value, 2)
                }).eq('asset_id', asset['asset_id']).execute()
                
                updated_count += 1
                
            except Exception as e:
                logging.error(f"Error updating asset {asset.get('asset_id')}: {e}")
                continue
        
        return JSONResponse({
            "status": "success",
            "message": f"Updated {updated_count} assets successfully",
            "updated_count": updated_count
        })
        
    except Exception as e:
        logging.error(f"Error updating depreciation: {e}")
        return JSONResponse({
            "status": "error", 
            "message": str(e)
        }, status_code=500)