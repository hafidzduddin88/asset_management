from fastapi import APIRouter, Depends, Request, HTTPException, status
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import pandas as pd
import io
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
    """Export assets to Excel."""
    assets = get_all_assets()
    
    # Convert to DataFrame
    df = pd.DataFrame(assets)
    
    # Create Excel file in memory
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, sheet_name='Assets', index=False)
        
        # Get the xlsxwriter workbook and worksheet objects
        workbook = writer.book
        worksheet = writer.sheets['Assets']
        
        # Add a header format
        header_format = workbook.add_format({
            'bold': True,
            'text_wrap': True,
            'valign': 'top',
            'fg_color': '#D7E4BC',
            'border': 1
        })
        
        # Write the column headers with the defined format
        for col_num, value in enumerate(df.columns.values):
            worksheet.write(0, col_num, value, header_format)
            
        # Auto-adjust columns' width
        for i, col in enumerate(df.columns):
            column_width = max(df[col].astype(str).map(len).max(), len(col)) + 2
            worksheet.set_column(i, i, column_width)
    
    # Set up response
    output.seek(0)
    filename = f"assets_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
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