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
from app.database.models import Asset, User, Damage, Relocation, Disposal
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
        headers = ["Asset Tag", "Name", "Category", "Location", "Status", "Purchase Date", "Purchase Cost", "Photo URL"]
        
        # Query assets with filters
        query = db.query(Asset)
        if status:
            query = query.filter(Asset.status == status)
        if category:
            query = query.filter(Asset.category == category)
        if location:
            query = query.filter(Asset.location == location)
        
        assets = query.all()
        
        # Add data rows
        for i, asset in enumerate(assets, start=2):
            worksheet.cell(row=1, column=1, value="Asset Tag").font = Font(bold=True)
            worksheet.cell(row=1, column=2, value="Name").font = Font(bold=True)
            worksheet.cell(row=1, column=3, value="Category").font = Font(bold=True)
            worksheet.cell(row=1, column=4, value="Location").font = Font(bold=True)
            worksheet.cell(row=1, column=5, value="Status").font = Font(bold=True)
            worksheet.cell(row=1, column=6, value="Purchase Date").font = Font(bold=True)
            worksheet.cell(row=1, column=7, value="Purchase Cost").font = Font(bold=True)
            worksheet.cell(row=1, column=8, value="Photo URL").font = Font(bold=True)
            
            worksheet.cell(row=i, column=1, value=asset.asset_tag)
            worksheet.cell(row=i, column=2, value=asset.name)
            worksheet.cell(row=i, column=3, value=asset.category)
            worksheet.cell(row=i, column=4, value=asset.location)
            worksheet.cell(row=i, column=5, value=asset.status)
            worksheet.cell(row=i, column=6, value=asset.purchase_date.strftime("%Y-%m-%d") if asset.purchase_date else "")
            worksheet.cell(row=i, column=7, value=asset.purchase_cost)
            worksheet.cell(row=i, column=8, value=asset.photo_url)
    
    elif report_type == "damages":
        headers = ["Asset Tag", "Asset Name", "Damage Date", "Description", "Reported By", "Is Repaired", "Repair Date", "Photo URL"]
        
        # Query damages with filters
        query = db.query(Damage).join(Asset)
        if status:
            if status == "repaired":
                query = query.filter(Damage.is_repaired == True)
            elif status == "unrepaired":
                query = query.filter(Damage.is_repaired == False)
        if category:
            query = query.filter(Asset.category == category)
        if location:
            query = query.filter(Asset.location == location)
        if start_date:
            query = query.filter(Damage.damage_date >= datetime.strptime(start_date, "%Y-%m-%d"))
        if end_date:
            query = query.filter(Damage.damage_date <= datetime.strptime(end_date, "%Y-%m-%d"))
        
        damages = query.all()
        
        # Add data rows
        for i, damage in enumerate(damages, start=2):
            worksheet.cell(row=1, column=1, value="Asset Tag").font = Font(bold=True)
            worksheet.cell(row=1, column=2, value="Asset Name").font = Font(bold=True)
            worksheet.cell(row=1, column=3, value="Damage Date").font = Font(bold=True)
            worksheet.cell(row=1, column=4, value="Description").font = Font(bold=True)
            worksheet.cell(row=1, column=5, value="Reported By").font = Font(bold=True)
            worksheet.cell(row=1, column=6, value="Is Repaired").font = Font(bold=True)
            worksheet.cell(row=1, column=7, value="Repair Date").font = Font(bold=True)
            worksheet.cell(row=1, column=8, value="Photo URL").font = Font(bold=True)
            
            worksheet.cell(row=i, column=1, value=damage.asset.asset_tag)
            worksheet.cell(row=i, column=2, value=damage.asset.name)
            worksheet.cell(row=i, column=3, value=damage.damage_date.strftime("%Y-%m-%d"))
            worksheet.cell(row=i, column=4, value=damage.description)
            worksheet.cell(row=i, column=5, value=damage.reporter.username)
            worksheet.cell(row=i, column=6, value="Yes" if damage.is_repaired else "No")
            worksheet.cell(row=i, column=7, value=damage.repair_date.strftime("%Y-%m-%d") if damage.repair_date else "")
            worksheet.cell(row=i, column=8, value=damage.photo_url)
    
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
        # Query assets with filters
        query = db.query(Asset)
        if status:
            query = query.filter(Asset.status == status)
        if category:
            query = query.filter(Asset.category == category)
        if location:
            query = query.filter(Asset.location == location)
        
        assets = query.all()
        
        # Table header
        pdf.cell(30, 10, "Asset Tag", 1)
        pdf.cell(50, 10, "Name", 1)
        pdf.cell(30, 10, "Category", 1)
        pdf.cell(30, 10, "Location", 1)
        pdf.cell(30, 10, "Status", 1)
        pdf.ln()
        
        # Table data
        pdf.set_font("Arial", "", 10)
        for asset in assets:
            pdf.cell(30, 10, asset.asset_tag, 1)
            pdf.cell(50, 10, asset.name, 1)
            pdf.cell(30, 10, asset.category, 1)
            pdf.cell(30, 10, asset.location, 1)
            pdf.cell(30, 10, asset.status, 1)
            pdf.ln()
    
    elif report_type == "damages":
        # Query damages with filters
        query = db.query(Damage).join(Asset)
        if status:
            if status == "repaired":
                query = query.filter(Damage.is_repaired == True)
            elif status == "unrepaired":
                query = query.filter(Damage.is_repaired == False)
        if category:
            query = query.filter(Asset.category == category)
        if location:
            query = query.filter(Asset.location == location)
        if start_date:
            query = query.filter(Damage.damage_date >= datetime.strptime(start_date, "%Y-%m-%d"))
        if end_date:
            query = query.filter(Damage.damage_date <= datetime.strptime(end_date, "%Y-%m-%d"))
        
        damages = query.all()
        
        # Table header
        pdf.cell(30, 10, "Asset Tag", 1)
        pdf.cell(50, 10, "Asset Name", 1)
        pdf.cell(30, 10, "Damage Date", 1)
        pdf.cell(30, 10, "Repaired", 1)
        pdf.cell(30, 10, "Repair Date", 1)
        pdf.ln()
        
        # Table data
        pdf.set_font("Arial", "", 10)
        for damage in damages:
            pdf.cell(30, 10, damage.asset.asset_tag, 1)
            pdf.cell(50, 10, damage.asset.name, 1)
            pdf.cell(30, 10, damage.damage_date.strftime("%Y-%m-%d"), 1)
            pdf.cell(30, 10, "Yes" if damage.is_repaired else "No", 1)
            pdf.cell(30, 10, damage.repair_date.strftime("%Y-%m-%d") if damage.repair_date else "", 1)
            pdf.ln()
    
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