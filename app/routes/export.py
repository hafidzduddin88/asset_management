from fastapi import APIRouter, Depends, Request, HTTPException, status
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import io
import csv
import json
from datetime import datetime

from app.database.database import get_db
from app.database.models import User
from app.database.dependencies import get_current_user
from app.utils.sheets import get_all_assets

router = APIRouter(tags=["export"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/export", response_class=HTMLResponse)
async def export_page(
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """Export page."""
    return templates.TemplateResponse(
        "export/index.html",
        {
            "request": request,
            "user": current_user
        }
    )

@router.get("/export/excel")
async def export_excel(
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """Export assets to Excel (CSV format)."""
    assets = get_all_assets()
    
    # Create CSV in memory
    output = io.StringIO()
    
    # Get all possible field names from assets
    fieldnames = set()
    for asset in assets:
        fieldnames.update(asset.keys())
    fieldnames = sorted(list(fieldnames))
    
    # Write CSV
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(assets)
    
    # Set up response
    output_bytes = io.BytesIO(output.getvalue().encode())
    filename = f"assets_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    
    return StreamingResponse(
        output_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@router.get("/export/pdf")
async def export_pdf(
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """Export assets to PDF."""
    # This would typically use a PDF generation library like ReportLab or WeasyPrint
    # For now, we'll return a simple text file as a placeholder
    content = "PDF export functionality will be implemented soon."
    
    output = io.BytesIO(content.encode())
    filename = f"assets_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    
    return StreamingResponse(
        output,
        media_type="text/plain",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@router.get("/report", response_class=HTMLResponse)
async def report_page(
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """Report page."""
    assets = get_all_assets()
    
    # Get summary statistics
    total_assets = len(assets)
    active_assets = len([a for a in assets if a.get('Status') == 'Active'])
    damaged_assets = len([a for a in assets if a.get('Status') == 'Damaged'])
    disposed_assets = len([a for a in assets if a.get('Status') == 'Disposed'])
    
    # Group assets by location
    locations = {}
    for asset in assets:
        location = asset.get('Location', 'Unknown')
        if location not in locations:
            locations[location] = 0
        locations[location] += 1
    
    # Group assets by category
    categories = {}
    for asset in assets:
        category = asset.get('Category', 'Unknown')
        if category not in categories:
            categories[category] = 0
        categories[category] += 1
    
    return templates.TemplateResponse(
        "export/report.html",
        {
            "request": request,
            "user": current_user,
            "assets": assets,
            "total_assets": total_assets,
            "active_assets": active_assets,
            "damaged_assets": damaged_assets,
            "disposed_assets": disposed_assets,
            "locations": locations,
            "categories": categories
        }
    )