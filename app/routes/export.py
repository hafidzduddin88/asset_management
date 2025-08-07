# app/routes/export.py
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import StreamingResponse
from fastapi.templating import Jinja2Templates
from app.utils.auth import get_current_profile
from app.utils.database_manager import get_supabase
import io
import json
from datetime import datetime
from typing import List

router = APIRouter(prefix="/export", tags=["export"])
templates = Jinja2Templates(directory="app/templates")

# Available tables for export
EXPORT_TABLES = {
    'assets': {
        'name': 'Assets',
        'table': 'assets',
        'columns': {
            'asset_id': 'Asset ID',
            'asset_name': 'Asset Name',
            'asset_tag': 'Asset Tag',
            'manufacture': 'Manufacture',
            'model': 'Model',
            'serial_number': 'Serial Number',
            'purchase_date': 'Purchase Date',
            'purchase_cost': 'Purchase Cost',
            'status': 'Status',
            'item_condition': 'Condition',
            'room_name': 'Room',
            'notes': 'Notes',
            'warranty': 'Warranty',
            'supplier': 'Supplier'
        }
    },
    'approvals': {
        'name': 'Approvals',
        'table': 'approvals',
        'columns': {
            'approval_id': 'Approval ID',
            'type': 'Type',
            'asset_name': 'Asset Name',
            'status': 'Status',
            'submitted_by': 'Submitted By',
            'submitted_date': 'Submitted Date',
            'approved_by': 'Approved By',
            'approved_date': 'Approved Date',
            'description': 'Description'
        }
    },
    'damage_log': {
        'name': 'Damage Log',
        'table': 'damage_log',
        'columns': {
            'damage_id': 'Damage ID',
            'asset_name': 'Asset Name',
            'damage_type': 'Damage Type',
            'severity': 'Severity',
            'description': 'Description',
            'reported_by': 'Reported By',
            'report_date': 'Report Date',
            'status': 'Status'
        }
    },
    'repair_log': {
        'name': 'Repair Log',
        'table': 'repair_log',
        'columns': {
            'repair_id': 'Repair ID',
            'asset_name': 'Asset Name',
            'repair_action': 'Repair Action',
            'description': 'Description',
            'performed_by': 'Performed By',
            'repair_date': 'Repair Date',
            'status': 'Status'
        }
    }
}

@router.get("/")
async def export_page(request: Request, current_profile=Depends(get_current_profile)):
    """Export data page"""
    return templates.TemplateResponse("export/index.html", {
        "request": request,
        "user": current_profile,
        "tables": EXPORT_TABLES
    })

@router.post("/excel")
async def export_to_excel(
    request: Request,
    table: str = Form(...),
    columns: List[str] = Form(...),
    exclude_disposed: bool = Form(False),
    current_profile=Depends(get_current_profile)
):
    """Export selected table and columns to Excel"""
    try:
        # Import openpyxl here to avoid dependency if not used
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill
        
        if table not in EXPORT_TABLES:
            raise ValueError("Invalid table selected")
        
        table_config = EXPORT_TABLES[table]
        supabase = get_supabase()
        
        # Build query
        query = supabase.table(table_config['table']).select(','.join(columns))
        
        # Apply filters
        if table == 'assets' and exclude_disposed:
            query = query.neq('status', 'Disposed')
        
        # Execute query
        response = query.execute()
        data = response.data
        
        # Create Excel workbook
        wb = Workbook()
        ws = wb.active
        ws.title = table_config['name']
        
        # Add headers
        headers = [table_config['columns'][col] for col in columns if col in table_config['columns']]
        ws.append(headers)
        
        # Style headers
        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
        
        for cell in ws[1]:
            cell.font = header_font
            cell.fill = header_fill
        
        # Add data rows
        for row in data:
            row_data = []
            for col in columns:
                value = row.get(col, '')
                # Format dates
                if col.endswith('_date') and value:
                    try:
                        if 'T' in str(value):
                            dt = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
                            value = dt.strftime('%Y-%m-%d %H:%M:%S')
                    except:
                        pass
                row_data.append(value)
            ws.append(row_data)
        
        # Auto-adjust column widths
        for column in ws.columns:
            max_length = 0
            column_letter = column[0].column_letter
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = min(max_length + 2, 50)
            ws.column_dimensions[column_letter].width = adjusted_width
        
        # Save to BytesIO
        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        
        # Generate filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{table_config['name']}_{timestamp}.xlsx"
        
        # Return as streaming response
        return StreamingResponse(
            io.BytesIO(output.read()),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
        
    except ImportError:
        return {"error": "Excel export not available - openpyxl not installed"}
    except Exception as e:
        return {"error": f"Export failed: {str(e)}"}