# app/routes/export.py
from fastapi import APIRouter, Depends, Request, Query, HTTPException
from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from typing import List, Optional
import io
import openpyxl
from openpyxl.styles import Font, Alignment
from fpdf import FPDF
from datetime import datetime

from app.database.database import get_db
from app.database.models import User, UserRole
from app.utils.sheets import get_all_assets, get_asset_by_id
from app.database.dependencies import get_current_active_user

router = APIRouter(tags=["export"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/export", response_class=HTMLResponse)
async def export_form(
    request: Request,
    current_user: User = Depends(get_current_active_user)
):
    """Export form."""
    return templates.TemplateResponse(
        "export/form.html",
        {
            "request": request,
            "user": current_user
        }
    )

@router.get("/export/excel")
async def export_excel(
    report_type: str = Query(...),
    status: Optional[str] = None,
    category: Optional[str] = None,
    location: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Export data to Excel."""
    # Create a new workbook and select the active worksheet
    workbook = openpyxl.Workbook()
    worksheet = workbook.active
    worksheet.title = f"{report_type.capitalize()} Report"
    
    # Add headers
    headers = []
    if report_type == "assets":
        headers = ["Asset Tag", "Item Name", "Category", "Location", "Status", "Purchase Date", "Purchase Cost", "Photo URL"]
        
        # Get assets from Google Sheets
        all_assets = get_all_assets()
        
        # Apply filters
        filtered_assets = all_assets
        if status:
            filtered_assets = [a for a in filtered_assets if a.get('Status') == status]
        if category:
            filtered_assets = [a for a in filtered_assets if a.get('Category') == category]
        if location:
            filtered_assets = [a for a in filtered_assets if a.get('Location') == location]
        
        # Add headers
        for col, header in enumerate(headers, start=1):
            worksheet.cell(row=1, column=col, value=header).font = Font(bold=True)
        
        # Add data rows
        for i, asset in enumerate(filtered_assets, start=2):
            worksheet.cell(row=i, column=1, value=asset.get('Asset Tag', ''))
            worksheet.cell(row=i, column=2, value=asset.get('Item Name', ''))
            worksheet.cell(row=i, column=3, value=asset.get('Category', ''))
            worksheet.cell(row=i, column=4, value=asset.get('Location', ''))
            worksheet.cell(row=i, column=5, value=asset.get('Status', ''))
            worksheet.cell(row=i, column=6, value=asset.get('Purchase Date', ''))
            worksheet.cell(row=i, column=7, value=asset.get('Purchase Cost', ''))
            worksheet.cell(row=i, column=8, value=asset.get('Photo URL', ''))
    
    # Only assets report is supported with Google Sheets integration
    
    # Auto-adjust column width
    for col in worksheet.columns:
        max_length = 0
        column = col[0].column_letter
        for cell in col:
            if cell.value:
                max_length = max(max_length, len(str(cell.value)))
        adjusted_width = (max_length + 2)
        worksheet.column_dimensions[column].width = adjusted_width
    
    # Save to BytesIO
    output = io.BytesIO()
    workbook.save(output)
    output.seek(0)
    
    # Return Excel file
    filename = f"{report_type}_{datetime.now().strftime('%Y%m%d%H%M%S')}.xlsx"
    headers = {
        "Content-Disposition": f"attachment; filename={filename}"
    }
    
    return StreamingResponse(
        output, 
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers
    )

@router.get("/export/pdf")
async def export_pdf(
    report_type: str = Query(...),
    status: Optional[str] = None,
    category: Optional[str] = None,
    location: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Export data to PDF."""
    # Create PDF
    pdf = FPDF()
    pdf.add_page()
    
    # Set font
    pdf.set_font("Arial", "B", 16)
    
    # Title
    pdf.cell(0, 10, f"{report_type.capitalize()} Report", 0, 1, "C")
    pdf.ln(10)
    
    # Report date
    pdf.set_font("Arial", "", 10)
    pdf.cell(0, 10, f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", 0, 1, "R")
    pdf.ln(5)
    
    # Add filters info
    if status or category or location or start_date or end_date:
        pdf.set_font("Arial", "B", 12)
        pdf.cell(0, 10, "Filters:", 0, 1)
        pdf.set_font("Arial", "", 10)
        
        if status:
            pdf.cell(0, 8, f"Status: {status}", 0, 1)
        if category:
            pdf.cell(0, 8, f"Category: {category}", 0, 1)
        if location:
            pdf.cell(0, 8, f"Location: {location}", 0, 1)
        if start_date:
            pdf.cell(0, 8, f"Start Date: {start_date}", 0, 1)
        if end_date:
            pdf.cell(0, 8, f"End Date: {end_date}", 0, 1)
        
        pdf.ln(5)
    
    # Table header
    pdf.set_font("Arial", "B", 12)
    
    if report_type == "assets":
        # Get assets from Google Sheets
        all_assets = get_all_assets()
        
        # Apply filters
        filtered_assets = all_assets
        if status:
            filtered_assets = [a for a in filtered_assets if a.get('Status') == status]
        if category:
            filtered_assets = [a for a in filtered_assets if a.get('Category') == category]
        if location:
            filtered_assets = [a for a in filtered_assets if a.get('Location') == location]
        
        # Table header
        pdf.cell(30, 10, "Asset Tag", 1)
        pdf.cell(50, 10, "Item Name", 1)
        pdf.cell(30, 10, "Category", 1)
        pdf.cell(30, 10, "Location", 1)
        pdf.cell(30, 10, "Status", 1)
        pdf.ln()
        
        # Table data
        pdf.set_font("Arial", "", 10)
        for asset in filtered_assets:
            pdf.cell(30, 10, asset.get('Asset Tag', ''), 1)
            pdf.cell(50, 10, asset.get('Item Name', ''), 1)
            pdf.cell(30, 10, asset.get('Category', ''), 1)
            pdf.cell(30, 10, asset.get('Location', ''), 1)
            pdf.cell(30, 10, asset.get('Status', ''), 1)
            pdf.ln()
    
    # Only assets report is supported with Google Sheets integration
    
    # Save to BytesIO
    output = io.BytesIO()
    pdf_bytes = pdf.output(dest="S").encode("latin1")
    output.write(pdf_bytes)
    output.seek(0)
    
    # Return PDF file
    filename = f"{report_type}_{datetime.now().strftime('%Y%m%d%H%M%S')}.pdf"
    headers = {
        "Content-Disposition": f"attachment; filename={filename}"
    }
    
    return StreamingResponse(
        output, 
        media_type="application/pdf",
        headers=headers
    )