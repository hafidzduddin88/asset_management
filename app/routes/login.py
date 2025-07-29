# app/routes/approvals.py
from fastapi import APIRouter, Depends, Request, HTTPException, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.utils.auth import get_current_user
from app.utils.sheets import get_all_approvals, update_approval_status

router = APIRouter(prefix="/approvals", tags=["approvals"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def approvals_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Approvals page for admin and manager."""
    if current_user.role not in ['admin', 'manager']:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get all approvals from Google Sheets
    all_approvals = get_all_approvals()
    
    # Filter approvals based on user role
    if current_user.role == 'admin':
        # Admin sees all approvals except disposal and edit_asset
        approvals_data = [a for a in all_approvals if a.get('Type') not in ['disposal', 'edit_asset']]
    elif current_user.role == 'manager':
        # Manager sees disposal and edit_asset approvals
        approvals_data = [a for a in all_approvals if a.get('Type') in ['disposal', 'edit_asset']]
    else:
        approvals_data = []
    
    return templates.TemplateResponse(
        "approvals/list.html",
        {
            "request": request,
            "user": current_user,
            "approvals_data": approvals_data
        }
    )

@router.post("/approve/{approval_id}")
async def approve_request(
    approval_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Approve a request."""
    if current_user.role not in ['admin', 'manager']:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get approval details
    all_approvals = get_all_approvals()
    approval = next((a for a in all_approvals if str(a.get('ID')) == str(approval_id)), None)
    
    if not approval:
        return JSONResponse({"status": "error", "message": "Approval not found"})
    
    # Process approval based on type
    try:
        if approval.get('Type') == 'damage_report':
            # Update asset status to "Under Repair"
            from app.utils.sheets import update_asset
            success = update_asset(approval.get('Asset_ID'), {'Status': 'Under Repair'})
            if not success:
                return JSONResponse({"status": "error", "message": "Failed to update asset status"})
        
        elif approval.get('Type') == 'relocation':
            # Process relocation approval
            import json
            try:
                request_data_str = approval.get('Request_Data', '')
                if request_data_str:
                    relocation_data = json.loads(request_data_str)
                    update_data = {
                        'Location': relocation_data.get('new_location'),
                        'Room': relocation_data.get('new_room')
                    }
                    from app.utils.sheets import update_asset
                    success = update_asset(approval.get('Asset_ID'), update_data)
                    if not success:
                        return JSONResponse({"status": "error", "message": "Failed to relocate asset"})
            except Exception as e:
                return JSONResponse({"status": "error", "message": f"Error processing relocation: {str(e)}"})
            
        elif approval.get('Type') == 'edit_asset':
            # Process edit asset approval
            import json
            try:
                request_data_str = approval.get('Request_Data', '')
                if request_data_str:
                    edit_data = json.loads(request_data_str)
                    from app.utils.sheets import update_asset
                    success = update_asset(approval.get('Asset_ID'), edit_data)
                    if not success:
                        return JSONResponse({"status": "error", "message": "Failed to update asset"})
            except Exception as e:
                return JSONResponse({"status": "error", "message": f"Error processing edit: {str(e)}"})
        
        # Update approval status
        approval_update = {
            'Status': 'Approved',
            'Approved_By': current_user.full_name or current_user.email,
            'Approved_Date': __import__('datetime').datetime.now().strftime('%Y-%m-%d')
        }
        
        success = update_approval_status(approval_id, approval_update)
        
        if success:
            return JSONResponse({"status": "success", "message": "Request approved successfully"})
        else:
            return JSONResponse({"status": "error", "message": "Failed to update approval status"})
            
    except Exception as e:
        return JSONResponse({"status": "error", "message": f"Error processing approval: {str(e)}"})

@router.post("/reject/{approval_id}")
async def reject_request(
    approval_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Reject a request."""
    if current_user.role not in ['admin', 'manager']:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Update approval status
    approval_update = {
        'Status': 'Rejected',
        'Approved_By': current_user.full_name or current_user.email,
        'Approved_Date': __import__('datetime').datetime.now().strftime('%Y-%m-%d')
    }
    
    success = update_approval_status(approval_id, approval_update)
    
    if success:
        return JSONResponse({"status": "success", "message": "Request rejected"})
    else:
        return JSONResponse({"status": "error", "message": "Failed to update approval status"})
from fastapi import APIRouter, Request, Depends
from starlette.templating import Jinja2Templates
from app.utils.auth import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/assets")
async def assets_page(request: Request, current_user=Depends(get_current_user)):
    """Assets listing page with filtering and pagination"""
    from app.utils.sheets import get_all_assets
    
    # Ambil data asset dari Google Sheets
    all_assets = get_all_assets()
    
    # Filter hanya aset aktif (bukan Disposed)
    active_assets = [asset for asset in all_assets if asset.get("Status", "").lower() != "disposed"]
    
    return templates.TemplateResponse("assets.html", {
        "request": request,
        "user": current_user,
        "assets_data": active_assets
    })
# app/routes/asset_management.py
from fastapi import APIRouter, Depends, Request, Form, File, UploadFile, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import json
from datetime import datetime
import io

from app.database.database import get_db
from app.database.models import Profile, UserRole
from app.utils.photo import resize_and_convert_image, upload_to_drive
from app.utils.sheets import get_dropdown_options, add_asset as sheets_add_asset
from app.utils.flash import set_flash
from app.utils.auth import get_current_user, get_admin_user
from app.config import load_config

config = load_config()
router = APIRouter(prefix="/asset_management", tags=["asset_management"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/add", response_class=HTMLResponse)
async def add_asset_form(
    request: Request,
    db: Session = Depends(get_db),
    current_profile = Depends(get_current_user)
):
    """Form to add a new asset."""
    dropdown_options = get_dropdown_options()
    return templates.TemplateResponse(
        "asset_management/add.html",
        {
            "request": request,
            "user": current_profile,
            "dropdown_options": dropdown_options
        }
    )


@router.get("/list", response_class=HTMLResponse)
async def asset_list(
    request: Request,
    db: Session = Depends(get_db),
    current_profile = Depends(get_current_user)
):
    """List assets for editing (admin and manager only)."""
    if current_profile.role not in [UserRole.ADMIN, UserRole.MANAGER]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    from app.utils.sheets import get_all_assets
    assets = get_all_assets()
    
    locations = list(set(asset.get('Location', '') for asset in assets if asset.get('Location')))
    location_rooms = {}
    for asset in assets:
        location = asset.get('Location', '')
        room = asset.get('Room', '')
        if location and room:
            if location not in location_rooms:
                location_rooms[location] = set()
            location_rooms[location].add(room)
    
    for location in location_rooms:
        location_rooms[location] = list(location_rooms[location])
    
    return templates.TemplateResponse(
        "asset_management/list.html",
        {
            "request": request,
            "user": current_profile,
            "assets": assets,
            "locations": sorted(locations),
            "location_rooms": location_rooms
        }
    )


@router.get("/edit/{asset_id}", response_class=HTMLResponse)
async def edit_asset_form(
    asset_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_profile = Depends(get_current_user)
):
    """Form to edit an existing asset (admin/manager only)."""
    if current_profile.role not in [UserRole.ADMIN, UserRole.MANAGER]:
        raise HTTPException(status_code=403, detail="Access denied")

    from app.utils.sheets import get_asset_by_id
    asset = get_asset_by_id(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    dropdown_options = get_dropdown_options()
    
    return templates.TemplateResponse(
        "asset_management/edit.html",
        {
            "request": request,
            "user": current_profile,
            "asset": asset,
            "dropdown_options": dropdown_options
        }
    )


@router.post("/edit/{asset_id}")
async def update_asset(
    asset_id: str,
    request: Request,
    status: str = Form(...),
    company: str = Form(...),
    location: str = Form(...),
    room: str = Form(...),
    bisnis_unit: str = Form(None),
    edit_reason: str = Form(...),
    db: Session = Depends(get_db),
    current_profile = Depends(get_current_user)
):
    """Update existing asset (admin and manager only)."""
    if current_profile.role not in [UserRole.ADMIN, UserRole.MANAGER]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    from app.utils.sheets import update_asset as sheets_update_asset, calculate_asset_financials, get_asset_by_id
    asset = get_asset_by_id(asset_id)

    update_data = {
        "Status": status,
        "Company": company,
        "Location": location,
        "Room": room,
        "Bisnis Unit": bisnis_unit or ""
    }
    
    # Jika perlu hitung ulang nilai finansial, misalnya setelah perubahan harga
    # financials = calculate_asset_financials(purchase_cost, purchase_date, category)
    # update_data.update(financials)
    
    from app.utils.sheets import add_approval_request
    
    approval_data = {
        'type': 'edit_asset',
        'asset_id': asset_id,
        'asset_name': asset.get('Item Name', ''),
        'submitted_by': current_profile.full_name or current_profile.email,
        'submitted_date': datetime.now().strftime('%Y-%m-%d'),
        'description': f"Edit asset: {asset.get('Item Name', '')} - Reason: {edit_reason}",
        'edit_reason': edit_reason,
        'request_data': json.dumps(update_data, ensure_ascii=False)
    }
    
    approval_success = add_approval_request(approval_data)
    
    if approval_success:
        response = RedirectResponse(url="/asset_management/list", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, "Asset edit request submitted for manager approval", "success")
        return response
    else:
        dropdown_options = get_dropdown_options()
        return templates.TemplateResponse(
            "asset_management/edit.html",
            {
                "request": request,
                "user": current_profile,
                "asset": asset,
                "dropdown_options": dropdown_options,
                "error": "Error submitting edit request"
            },
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@router.post("/add")
async def add_asset(
    request: Request,
    item_name: str = Form(...),
    category: str = Form(...),
    type: str = Form(...),
    manufacture: str = Form(None),
    model: str = Form(None),
    serial_number: str = Form(None),
    company: str = Form(...),
    bisnis_unit: str = Form(None),
    location: str = Form(...),
    room: str = Form(...),
    notes: str = Form(None),
    item_condition: str = Form(None),
    purchase_date: str = Form(...),
    purchase_cost: str = Form(...),
    warranty: str = Form(None),
    supplier: str = Form(None),
    journal: str = Form(None),
    owner: str = Form(...),
    photo: UploadFile = File(None),
    db: Session = Depends(get_db),
    current_profile = Depends(get_current_user)
):
    """Process add asset form."""
    dropdown_options = get_dropdown_options()
    
    asset_data = {
        "Item Name": item_name,
        "Category": category,
        "Type": type,
        "Manufacture": manufacture or "",
        "Model": model or "",
        "Serial Number": serial_number or "",
        "Company": company,
        "Bisnis Unit": bisnis_unit or "",
        "Location": location,
        "Room": room,
        "Notes": notes or "",
        "Item Condition": item_condition or "",
        "Purchase Date": purchase_date,
        "Purchase Cost": purchase_cost,
        "Warranty": warranty or "",
        "Supplier": supplier or "",
        "Journal": journal or "",
        "Owner": owner,
        "Status": "Active"
    }
    
    photo_url = None
    if photo and photo.filename:
        try:
            contents = await photo.read()
            image_file = io.BytesIO(contents)
            processed_image = resize_and_convert_image(image_file)
            
            if processed_image:
                photo_url = upload_to_drive(processed_image, photo.filename, "new")
                if photo_url:
                    asset_data["Photo URL"] = photo_url
        except Exception as e:
            print(f"Error processing photo: {str(e)}")
    
    if current_profile.role == UserRole.ADMIN:
        success = sheets_add_asset(asset_data)
        
        if success:
            response = RedirectResponse(url="/assets/", status_code=status.HTTP_303_SEE_OTHER)
            set_flash(response, "Asset added successfully", "success")
            return response
        else:
            return templates.TemplateResponse(
                "asset_management/add.html",
                {
                    "request": request,
                    "user": current_profile,
                    "dropdown_options": dropdown_options,
                    "error": "Error adding asset to Google Sheets",
                    "form_data": asset_data
                },
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    from app.utils.sheets import add_approval_request
    
    approval_data = {
        'type': 'add_asset',
        'asset_id': 'NEW',
        'asset_name': item_name,
        'submitted_by': current_profile.full_name or current_profile.email,
        'submitted_date': datetime.now().strftime('%Y-%m-%d'),
        'description': f"Add new asset: {item_name}",
        'request_data': json.dumps(asset_data, ensure_ascii=False)
    }
    
    approval_success = add_approval_request(approval_data)
    
    if approval_success:
        response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, "Asset request submitted for approval", "success")
        return response
    else:
        return templates.TemplateResponse(
            "asset_management/add.html",
            {
                "request": request,
                "user": current_profile,
                "dropdown_options": dropdown_options,
                "error": "Error submitting approval request",
                "form_data": asset_data
            },
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
from fastapi import APIRouter, Request, Depends
from starlette.templating import Jinja2Templates
from app.utils.auth import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/")
async def damaged_assets_page(request: Request, current_user = Depends(get_current_user)):
    """Damaged assets page with search and log functionality"""
    from app.utils.sheets import get_all_assets, get_dropdown_options

    all_assets = get_all_assets()
    dropdown_options = get_dropdown_options()

    return templates.TemplateResponse("damaged_assets.html", {
        "request": request,
        "user": current_user,
        "assets_data": all_assets,
        "dropdown_options": dropdown_options
    })


@router.post("/lost")
async def submit_lost_report(request: Request, current_user = Depends(get_current_user)):
    """Submit lost report - syncs to Google Sheets"""
    from app.utils.sheets import add_lost_log, add_approval_request
    from datetime import datetime

    try:
        data = await request.json()

        lost_data = {
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'last_location': data.get('last_location'),
            'last_room': data.get('last_room', ''),
            'date_lost': data.get('date_lost'),
            'description': data.get('description'),
            'reported_by': current_user.full_name or current_user.email,
            'report_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'notes': data.get('notes', '')
        }

        log_success = add_lost_log(lost_data)

        approval_data = {
            'type': 'lost_report',
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'submitted_by': current_user.full_name or current_user.email,
            'submitted_date': datetime.now().strftime('%Y-%m-%d'),
            'description': f"Lost report: {data.get('description')}",
            'location': data.get('last_location')
        }

        approval_success = add_approval_request(approval_data)

        if log_success and approval_success:
            return {"status": "success", "message": "Lost report submitted and logged to Google Sheets"}
        else:
            return {"status": "error", "message": "Failed to sync with Google Sheets"}

    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/disposal")
async def submit_disposal_request(request: Request, current_user = Depends(get_current_user)):
    """Submit disposal request - syncs to Google Sheets"""
    from app.utils.sheets import add_disposal_log, add_approval_request
    from datetime import datetime

    try:
        data = await request.json()

        disposal_data = {
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'disposal_reason': data.get('disposal_reason'),
            'disposal_method': data.get('disposal_method', 'Standard'),
            'description': data.get('description'),
            'requested_by': current_user.full_name or current_user.email,
            'request_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'notes': data.get('notes', '')
        }

        log_success = add_disposal_log(disposal_data)

        approval_data = {
            'type': 'disposal_request',
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'submitted_by': current_user.full_name or current_user.email,
            'submitted_date': datetime.now().strftime('%Y-%m-%d'),
            'description': f"Disposal request: {data.get('description')}"
        }

        approval_success = add_approval_request(approval_data)

        if log_success and approval_success:
            return {"status": "success", "message": "Disposal request submitted and logged to Google Sheets"}
        else:
            return {"status": "error", "message": "Failed to sync with Google Sheets"}

    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/report")
async def submit_damage_report(request: Request, current_user = Depends(get_current_user)):
    """Submit damage report - syncs to Google Sheets"""
    from app.utils.sheets import add_damage_log, add_approval_request
    from datetime import datetime

    try:
        data = await request.json()

        damage_data = {
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'damage_type': data.get('damage_type'),
            'severity': data.get('severity'),
            'description': data.get('damage_description'),
            'reported_by': current_user.full_name or current_user.email,
            'report_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'location': data.get('location', ''),
            'room': data.get('room', ''),
            'notes': data.get('notes', '')
        }

        approval_data = {
            'type': 'damage_report',
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'submitted_by': current_user.full_name or current_user.email,
            'submitted_date': datetime.now().strftime('%Y-%m-%d'),
            'description': f"Damage report: {data.get('damage_description')}",
            'damage_type': data.get('damage_type'),
            'severity': data.get('severity')
        }

        approval_success = add_approval_request(approval_data)

        if approval_success:
            return {"status": "success", "message": "Damage report submitted for approval"}
        else:
            return {"status": "error", "message": "Failed to submit approval request"}

    except Exception as e:
        return {"status": "error", "message": str(e)}
# app/routes/disposal.py
from fastapi import APIRouter, Depends, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime

from app.database.database import get_db
from app.database.models import Profile
from app.utils.auth import get_admin_user
from app.utils.sheets import get_all_assets, update_asset, add_disposal_log
from app.utils.flash import set_flash

router = APIRouter(prefix="/disposal", tags=["disposal"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def disposal_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Disposal assets page (admin only)."""
    # Get assets that are ready to dispose only
    all_assets = get_all_assets()
    # Debug: check all statuses
    statuses = [str(asset.get('Status', '')).strip() for asset in all_assets]
    print(f"All statuses found: {set(statuses)}")
    
    disposable_assets = []
    for asset in all_assets:
        status = str(asset.get('Status', '')).strip()
        if status in ['To Be Disposed', 'To be Disposed', 'TO BE DISPOSED']:
            disposable_assets.append(asset)
    
    return templates.TemplateResponse(
        "disposal/index.html",
        {
            "request": request,
            "user": current_user,
            "assets": disposable_assets
        }
    )

@router.post("/dispose/{asset_id}")
async def dispose_asset(
    asset_id: str,
    request: Request,
    disposal_reason: str = Form(...),
    disposal_method: str = Form(...),
    description: str = Form(None),
    notes: str = Form(None),
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Dispose an asset (admin only)."""
    from app.utils.sheets import get_asset_by_id
    
    # Get asset data
    asset = get_asset_by_id(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    if str(asset.get('Status', '')).strip() != 'To Be Disposed':
        raise HTTPException(status_code=400, detail="Asset must be marked 'To Be Disposed' first")
    
    # Create disposal approval request
    from app.utils.sheets import add_approval_request
    
    approval_data = {
        'type': 'disposal',
        'asset_id': asset_id,
        'asset_name': asset.get('Item Name', ''),
        'submitted_by': current_user.full_name or current_user.email,
        'submitted_date': datetime.now().strftime('%Y-%m-%d'),
        'description': f"Disposal request: {disposal_reason} - {disposal_method}",
        'disposal_reason': disposal_reason,
        'disposal_method': disposal_method,
        'notes': f"Description: {description or ''} | Notes: {notes or ''}"
    }
    
    approval_success = add_approval_request(approval_data)
    
    if approval_success:
        response = RedirectResponse(url="/disposal", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, f"Disposal request for {asset.get('Item Name', '')} submitted for manager approval", "success")
        return response
    else:
        response = RedirectResponse(url="/disposal", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, "Error submitting disposal request", "error")
        return response
# app/routes/health.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
import time

from app.database.database import get_db
from app.config import load_config

router = APIRouter(tags=["health"])
config = load_config()

@router.get("/health")
async def health_check(db: Session = Depends(get_db)):
    """Health check endpoint."""
    start_time = time.time()
    
    # Check database connection
    try:
        db.execute(text("SELECT 1"))
        db_status = "healthy"
    except Exception as e:
        db_status = f"unhealthy: {str(e)}"
    
    # Check Google Sheets API
    sheets_status = "configured" if config.GOOGLE_SHEET_ID else "not configured"
    
    # Response time
    response_time = time.time() - start_time
    
    return {
        "status": "ok",
        "database": db_status,
        "google_sheets": sheets_status,
        "response_time_ms": round(response_time * 1000, 2)
    }
# /app/app/routes/home.py
import logging
from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse
from starlette.templating import Jinja2Templates
from app.utils.auth import get_current_user
from app.utils.sheets import get_summary_data, get_chart_data, get_all_assets

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=RedirectResponse)
async def redirect_root():
    return RedirectResponse("/dashboard")

@router.get("/dashboard")
async def home(request: Request, current_user = Depends(get_current_user)):
    try:
        # Summary and chart data
        summary_data = get_summary_data()
        chart_data = get_chart_data()
        all_assets = get_all_assets()

        # Filter out disposed assets for dashboard counts
        active_assets = [asset for asset in all_assets if asset.get("Status", "") != "Disposed"]
        disposed_assets = [asset for asset in all_assets if asset.get("Status", "") == "Disposed"]
        
        # Count assets by status and activity
        total_assets = len(active_assets)
        disposed_count = len(disposed_assets)
        damaged_count = len([a for a in all_assets if a.get("Status", "") == "Under Repair"])
        
        # Count assets by activity type
        relocated_count = len([a for a in all_assets if a.get("Last Activity", "") == "Relocated"])
        repaired_count = len([a for a in all_assets if a.get("Last Activity", "") == "Repaired"])
        to_be_disposed_count = len([a for a in all_assets if a.get("Status", "") == "To Be Disposed"])
        
        # Helper function to safely convert values to float
        def safe_float(value):
            if value is None or value == '':
                return 0.0
            try:
                return float(value)
            except (ValueError, TypeError):
                return 0.0
        
        # Calculate financial values directly from assets
        total_purchase_value = sum(safe_float(asset.get("Purchase Cost")) for asset in active_assets)
        total_book_value = sum(safe_float(asset.get("Book Value")) for asset in active_assets)
        # Calculate depreciation as purchase value minus book value
        total_depreciation_value = total_purchase_value - total_book_value
        category_counts = chart_data.get("category_counts", {})
        
        # Format location data
        location_data = chart_data.get("location_chart_data", {})
        location_counts = location_data.get("labels", [])
        location_values = location_data.get("values", [])
        location_counts_dict = dict(zip(location_counts, location_values))

        # Format time-based chart data
        monthly_data = chart_data.get("monthly_chart_data", {})
        monthly_chart_labels = monthly_data.get("labels", [])
        monthly_chart_values = monthly_data.get("values", [])
        
        # Generate quarterly data (last 12 quarters - 3 years)
        quarterly_chart_labels = []
        quarterly_chart_values = []
        
        # Get current year and quarter
        from datetime import datetime
        current_date = datetime.now()
        current_year = current_date.year
        current_quarter = (current_date.month - 1) // 3 + 1
        
        # Generate data for the last 12 quarters
        for i in range(11, -1, -1):
            year = current_year
            quarter = current_quarter - i
            
            # Adjust year if quarter is negative or > 4
            while quarter <= 0:
                year -= 1
                quarter += 4
            while quarter > 4:
                year += 1
                quarter -= 4
                
            quarterly_chart_labels.append(f"Q{quarter} {year}")
            
            # Count assets added in this quarter
            quarter_start_month = (quarter - 1) * 3 + 1
            quarter_end_month = quarter * 3
            
            count = 0
            for asset in all_assets:
                purchase_date = asset.get("Purchase Date", "")
                if purchase_date:
                    try:
                        date = datetime.strptime(purchase_date, "%Y-%m-%d")
                        if date.year == year and quarter_start_month <= date.month <= quarter_end_month:
                            count += 1
                    except:
                        pass
            
            quarterly_chart_values.append(count)
        
        # Generate yearly data (last 5 years)
        yearly_chart_labels = []
        yearly_chart_values = []
        
        # Generate data for the last 5 years
        for i in range(4, -1, -1):
            year = current_year - i
            yearly_chart_labels.append(str(year))
            
            # Count assets added in this year
            count = 0
            for asset in all_assets:
                purchase_date = asset.get("Purchase Date", "")
                if purchase_date:
                    try:
                        date = datetime.strptime(purchase_date, "%Y-%m-%d")
                        if date.year == year:
                            count += 1
                    except:
                        pass
            
            yearly_chart_values.append(count)

        # Format age distribution - convert to list of tuples for proper serialization
        age_distribution = chart_data.get("age_distribution", {})
        age_distribution_list = [
            {"label": str(k), "value": int(v)} 
            for k, v in age_distribution.items()
        ]

        # Format latest assets (excluding disposed assets)
        latest_assets = sorted(
            active_assets, 
            key=lambda a: a.get("Purchase Date", ""), 
            reverse=True
        )[:10]
        
        # Process assets to ensure they have a display_name field
        for asset in latest_assets:
            # Try different possible field names for the asset name
            name_fields = ["Name", "Asset Name", "AssetName", "Item Name", "Description", "Item"]
            display_name = None
            
            for field in name_fields:
                if asset.get(field):
                    display_name = asset.get(field)
                    break
            
            # If no name found, use a default
            if not display_name:
                display_name = f"Asset #{asset.get('ID', 'Unknown')}"
                
            # Add the display_name to the asset
            asset["display_name"] = display_name
            
        # Debug: Print the first asset's keys to see what fields are available
        if latest_assets:
            logging.info(f"Asset keys: {list(latest_assets[0].keys())}")
            logging.info(f"Asset display name: {latest_assets[0].get('display_name', 'Not found')}")
            logging.info(f"Original asset name fields: {[latest_assets[0].get(f, 'None') for f in name_fields]}")

        context = {
            "request": request,
            "user": current_user,
            "total_assets": total_assets,
            "total_purchase_value": total_purchase_value,
            "total_book_value": total_book_value,
            "total_depreciation_value": total_depreciation_value,
            "disposed_count": disposed_count,
            "damaged_count": damaged_count,
            "relocated_count": relocated_count,
            "repaired_count": repaired_count,
            "to_be_disposed_count": to_be_disposed_count,
            "category_counts": category_counts,
            "location_counts": location_counts_dict,
            "monthly_chart_labels": monthly_chart_labels,
            "monthly_chart_values": monthly_chart_values,
            "quarterly_chart_labels": quarterly_chart_labels,
            "quarterly_chart_values": quarterly_chart_values,
            "yearly_chart_labels": yearly_chart_labels,
            "yearly_chart_values": yearly_chart_values,
            "age_distribution": age_distribution_list,
            "latest_assets": latest_assets
        }

        return templates.TemplateResponse("dashboard.html", context)

    except Exception as e:
        logging.error("Dashboard error: %s", e, exc_info=True)
        return templates.TemplateResponse("error.html", {
            "request": request,
            "user": current_user,
            "message": "Terjadi kesalahan saat memuat dashboard.",
        })
from fastapi import APIRouter, Request, Response, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from supabase import create_client, Client
from app.config import load_config
import logging

config = load_config()
supabase: Client = create_client(config.SUPABASE_URL, config.SUPABASE_ANON_KEY)

router = APIRouter(tags=["authentication"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/login", response_class=HTMLResponse)
@router.head("/login", response_class=HTMLResponse)
async def login_page(request: Request, next: str = None):
    return templates.TemplateResponse("login_logout.html", {"request": request, "next": next})

@router.post("/login", response_class=HTMLResponse)
async def login_form(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    next: str = Form(None)
):
    try:
        # Use service key client for admin operations
        from supabase import create_client
        admin_supabase = create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_KEY)
        
        response = admin_supabase.auth.sign_in_with_password({
            "email": email,
            "password": password
        })
        
        if not response.user:
            return templates.TemplateResponse(
                "login_logout.html",
                {"request": request, "error": "Invalid email or password", "next": next},
                status_code=401
            )
        
        # Get user profile
        profile_response = admin_supabase.table('profiles').select('*').eq('id', response.user.id).single().execute()
        if not profile_response.data or not profile_response.data.get('is_active'):
            return templates.TemplateResponse(
                "login_logout.html",
                {"request": request, "error": "Account is inactive", "next": next},
                status_code=401
            )
        
        redirect_url = next if next else "/"
        redirect_response = RedirectResponse(url=redirect_url, status_code=303)
        
        redirect_response.set_cookie(
            key="sb_access_token",
            value=response.session.access_token,
            httponly=True,
            max_age=3600,
            samesite="lax",
            secure=True,
            domain=".onrender.com"
        )
        
        return redirect_response
        
    except Exception as e:
        logging.error(f"Login error: {str(e)}")
        return templates.TemplateResponse(
            "login_logout.html",
            {"request": request, "error": "Login failed", "next": next},
            status_code=401
        )

@router.get("/auth/callback")
async def auth_callback(request: Request):
    return templates.TemplateResponse("auth_callback.html", {"request": request})

@router.get("/logout")
async def logout():
    try:
        supabase.auth.sign_out()
    except:
        pass
    
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(key="sb_access_token")
    return response
# app/routes/logs.py
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.database.models import Profile
from app.utils.auth import get_current_user
from app.utils.sheets import get_all_approvals

router = APIRouter(prefix="/logs", tags=["logs"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def logs_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """View approval logs based on user role."""
    all_approvals = get_all_approvals()
    
    # Filter based on user role
    if current_user.role.value == 'staff':
        # Staff can only see their own requests
        user_identifier = current_user.full_name or current_user.email
        approvals = [a for a in all_approvals if a.get('Submitted_By') == user_identifier]
    else:
        # Manager and admin can see all approvals
        approvals = all_approvals
    
    # Separate pending and completed
    pending_approvals = [a for a in approvals if a.get('Status') == 'Pending']
    completed_approvals = [a for a in approvals if a.get('Status') in ['Approved', 'Rejected']]
    
    return templates.TemplateResponse(
        "logs/index.html",
        {
            "request": request,
            "user": current_user,
            "pending_approvals": pending_approvals,
            "completed_approvals": completed_approvals
        }
    )
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
from fastapi import APIRouter, Depends, Request, Form, UploadFile, File, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from app.database.database import get_db
from app.database.models import Profile
from app.utils.auth import get_current_user
from app.utils.photo import resize_and_convert_image, upload_to_drive
from app.utils.flash import set_flash

router = APIRouter(tags=["profile"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/profile", response_class=HTMLResponse)
async def profile_page(
    request: Request,
    current_user = Depends(get_current_user)
):
    """User profile page."""
    return templates.TemplateResponse(
        "profile/view.html",
        {
            "request": request,
            "user": current_user
        }
    )

@router.get("/profile/edit", response_class=HTMLResponse)
async def edit_profile_page(
    request: Request,
    current_user = Depends(get_current_user)
):
    """Edit user profile page."""
    return templates.TemplateResponse(
        "profile/edit.html",
        {
            "request": request,
            "user": current_user
        }
    )

@router.post("/profile/edit")
async def update_profile(
    request: Request,
    full_name: str = Form(...),
    email: str = Form(...),
    photo: UploadFile = File(None),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Update user profile."""
    # Update basic info
    current_user.full_name = full_name
    current_user.email = email
    current_user.updated_at = datetime.now(timezone.utc)
    
    # Handle photo upload if provided
    if photo and photo.filename:
        try:
            # Process image
            contents = await photo.read()
            import io
            image_file = io.BytesIO(contents)
            processed_image = resize_and_convert_image(image_file)
            
            if processed_image:
                # Upload to Google Drive
                photo_url = upload_to_drive(
                    processed_image, 
                    photo.filename, 
                    f"profile_{current_user.email}"
                )
                if photo_url:
                    current_user.photo_url = photo_url
        except Exception as e:
            return templates.TemplateResponse(
                "profile/edit.html",
                {
                    "request": request,
                    "user": current_user,
                    "error": f"Error uploading photo: {str(e)}"
                },
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    # Save changes
    db.commit()
    
    # Redirect to profile page
    response = RedirectResponse(url="/profile", status_code=status.HTTP_303_SEE_OTHER)
    set_flash(response, "Profile updated successfully", "success")
    return response
# app/routes/relocation.py
from fastapi import APIRouter, Depends, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime
import json

from app.database.database import get_db
from app.database.models import Profile
from app.utils.auth import get_current_user
from app.utils.sheets import get_all_assets, get_dropdown_options, add_approval_request
from app.utils.flash import set_flash

router = APIRouter(prefix="/relocation", tags=["relocation"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def relocation_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Asset relocation page."""
    # Get assets and dropdown options
    all_assets = get_all_assets()
    dropdown_options = get_dropdown_options()
    
    return templates.TemplateResponse(
        "relocation/index.html",
        {
            "request": request,
            "user": current_user,
            "assets": all_assets,
            "dropdown_options": dropdown_options
        }
    )

@router.post("/relocate/{asset_id}")
async def relocate_asset(
    asset_id: str,
    request: Request,
    new_location: str = Form(...),
    new_room: str = Form(...),
    reason: str = Form(...),
    notes: str = Form(None),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Submit asset relocation request."""
    from app.utils.sheets import get_asset_by_id
    
    # Get asset data
    asset = get_asset_by_id(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    # Create relocation approval request
    relocation_data = {
        'new_location': new_location,
        'new_room': new_room,
        'current_location': asset.get('Location', ''),
        'current_room': asset.get('Room', ''),
        'reason': reason,
        'notes': notes or ''
    }
    
    approval_data = {
        'type': 'relocation',
        'asset_id': asset_id,
        'asset_name': asset.get('Item Name', ''),
        'submitted_by': current_user.full_name or current_user.email,
        'submitted_date': datetime.now().strftime('%Y-%m-%d'),
        'description': f"Relocate from {asset.get('Location', '')} - {asset.get('Room', '')} to {new_location} - {new_room}",
        'request_data': json.dumps(relocation_data, ensure_ascii=False)
    }
    
    approval_success = add_approval_request(approval_data)
    
    if approval_success:
        response = RedirectResponse(url="/relocation", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, f"Relocation request for {asset.get('Item Name', '')} submitted for approval", "success")
        return response
    else:
        response = RedirectResponse(url="/relocation", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, "Error submitting relocation request", "error")
        return response
# /app/app/routes/repair.py
from fastapi import APIRouter, Request, Depends
from starlette.templating import Jinja2Templates
from app.utils.auth import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.post("/action")
async def submit_repair_action(request: Request, current_user = Depends(get_current_user)):
    """Submit repair action - creates approval request for store, direct action for allocate"""
    from app.utils.sheets import add_repair_log, update_asset, add_approval_request
    from datetime import datetime
    
    try:
        # Get JSON data
        data = await request.json()
        action_type = data.get('action_type')  # 'store' or 'allocate'
        
        if action_type == 'store':
            # Store action requires approval - only create approval request
            approval_data = {
                'type': 'repair_action',
                'asset_id': data.get('asset_id'),
                'asset_name': data.get('asset_name'),
                'submitted_by': current_user.full_name or current_user.email,
                'submitted_date': datetime.now().strftime('%Y-%m-%d'),
                'description': f"Request to store asset: {data.get('description')}",
                'action': 'Store Asset'
            }
            
            approval_success = add_approval_request(approval_data)
            
            if approval_success:
                return {"status": "success", "message": "Store request submitted for admin approval"}
            else:
                return {"status": "error", "message": "Failed to submit approval request"}
        
        else:  # allocate - direct action
            # Add to Repair_Log sheet
            repair_data = {
                'asset_id': data.get('asset_id'),
                'asset_name': data.get('asset_name'),
                'repair_action': 'Allocate Asset',
                'action_type': action_type,
                'description': data.get('description', ''),
                'performed_by': current_user.full_name or current_user.email,
                'action_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'new_location': data.get('location', ''),
                'new_room': data.get('room', ''),
                'notes': data.get('notes', '')
            }
            
            # Add to repair log
            log_success = add_repair_log(repair_data)
            
            # Update asset from Under Repair to Active
            update_data = {
                'Status': 'Active',
                'Bisnis Unit': data.get('business_unit', ''),
                'Location': data.get('location', ''),
                'Room': data.get('room', '')
            }
            
            asset_success = update_asset(data.get('asset_id'), update_data)
            
            if log_success and asset_success:
                return {"status": "success", "message": "Asset allocated successfully and synced to Google Sheets"}
            else:
                return {"status": "error", "message": "Failed to sync with Google Sheets"}
            
    except Exception as e:
        return {"status": "error", "message": str(e)}
# app/routes/user_management.py
from fastapi import APIRouter, Depends, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.database.models import Profile, UserRole
from app.utils.auth import get_current_user, get_admin_user
from app.utils.flash import set_flash

router = APIRouter(prefix="/user_management", tags=["user_management"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def user_list(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """List all users (admin only)."""
    users = db.query(Profile).all()
    
    return templates.TemplateResponse(
        "user_management/list.html",
        {
            "request": request,
            "user": current_user,
            "users": users
        }
    )

@router.get("/create", response_class=HTMLResponse)
async def create_user_form(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Create user form (admin only)."""
    return templates.TemplateResponse(
        "user_management/create.html",
        {
            "request": request,
            "user": current_user
        }
    )

@router.post("/create")
async def create_user(
    request: Request,
    email: str = Form(...),
    full_name: str = Form(...),
    role: str = Form(...),
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Create new user (admin only)."""
    # Check if user exists
    existing_user = db.query(Profile).filter(Profile.email == email).first()
    if existing_user:
        return templates.TemplateResponse(
            "user_management/create.html",
            {
                "request": request,
                "user": current_user,
                "error": "Email already exists"
            }
        )
    
    # Create user profile (Supabase handles auth)
    new_user = Profile(
        email=email,
        full_name=full_name,
        role=getattr(UserRole, role.upper()),
        is_active=True
    )
    
    db.add(new_user)
    db.commit()
    
    response = RedirectResponse(url="/user_management", status_code=status.HTTP_303_SEE_OTHER)
    set_flash(response, f"User {email} created successfully", "success")
    return response

@router.post("/reset_password/{user_id}")
async def reset_password(
    user_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Reset user password to default (admin only)."""
    user = db.query(Profile).filter(Profile.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Password reset handled by Supabase
    default_password = f"{user.email.split('@')[0]}123"
    
    response = RedirectResponse(url="/user_management", status_code=status.HTTP_303_SEE_OTHER)
    set_flash(response, f"Password reset instructions sent to {user.email}", "success")
    return response

@router.post("/toggle_status/{user_id}")
async def toggle_user_status(
    user_id: str,
    request: Request,
    is_active: bool = Form(...),
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Toggle user active status (admin only)."""
    user = db.query(Profile).filter(Profile.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Update status
    user.is_active = is_active
    db.commit()
    
    status_text = "activated" if is_active else "deactivated"
    response = RedirectResponse(url="/user_management", status_code=status.HTTP_303_SEE_OTHER)
    set_flash(response, f"User {user.email} {status_text}", "success")
    return response
# app/routes/__init__.py

# Import all route modules to make them available from app.routes
from app.routes import (
    home,
    assets,
    asset_management,
    login,
    damage,
    health,
    offline,
    profile,
    repair,
    approvals,
    disposal,
    user_management,
    logs,
    relocation
)
# app/routes/approvals.py
from fastapi import APIRouter, Depends, Request, HTTPException, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.utils.auth import get_current_user
from app.utils.sheets import get_all_approvals, update_approval_status

router = APIRouter(prefix="/approvals", tags=["approvals"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def approvals_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Approvals page for admin and manager."""
    if current_user.role not in ['admin', 'manager']:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get all approvals from Google Sheets
    all_approvals = get_all_approvals()
    
    # Filter approvals based on user role
    if current_user.role == 'admin':
        # Admin sees all approvals except disposal and edit_asset
        approvals_data = [a for a in all_approvals if a.get('Type') not in ['disposal', 'edit_asset']]
    elif current_user.role == 'manager':
        # Manager sees disposal and edit_asset approvals
        approvals_data = [a for a in all_approvals if a.get('Type') in ['disposal', 'edit_asset']]
    else:
        approvals_data = []
    
    return templates.TemplateResponse(
        "approvals/list.html",
        {
            "request": request,
            "user": current_user,
            "approvals_data": approvals_data
        }
    )

@router.post("/approve/{approval_id}")
async def approve_request(
    approval_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Approve a request."""
    if current_user.role not in ['admin', 'manager']:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get approval details
    all_approvals = get_all_approvals()
    approval = next((a for a in all_approvals if str(a.get('ID')) == str(approval_id)), None)
    
    if not approval:
        return JSONResponse({"status": "error", "message": "Approval not found"})
    
    # Process approval based on type
    try:
        if approval.get('Type') == 'damage_report':
            # Update asset status to "Under Repair"
            from app.utils.sheets import update_asset
            success = update_asset(approval.get('Asset_ID'), {'Status': 'Under Repair'})
            if not success:
                return JSONResponse({"status": "error", "message": "Failed to update asset status"})
        
        elif approval.get('Type') == 'relocation':
            # Process relocation approval
            import json
            try:
                request_data_str = approval.get('Request_Data', '')
                if request_data_str:
                    relocation_data = json.loads(request_data_str)
                    update_data = {
                        'Location': relocation_data.get('new_location'),
                        'Room': relocation_data.get('new_room')
                    }
                    from app.utils.sheets import update_asset
                    success = update_asset(approval.get('Asset_ID'), update_data)
                    if not success:
                        return JSONResponse({"status": "error", "message": "Failed to relocate asset"})
            except Exception as e:
                return JSONResponse({"status": "error", "message": f"Error processing relocation: {str(e)}"})
            
        elif approval.get('Type') == 'edit_asset':
            # Process edit asset approval
            import json
            try:
                request_data_str = approval.get('Request_Data', '')
                if request_data_str:
                    edit_data = json.loads(request_data_str)
                    from app.utils.sheets import update_asset
                    success = update_asset(approval.get('Asset_ID'), edit_data)
                    if not success:
                        return JSONResponse({"status": "error", "message": "Failed to update asset"})
            except Exception as e:
                return JSONResponse({"status": "error", "message": f"Error processing edit: {str(e)}"})
        
        # Update approval status
        approval_update = {
            'Status': 'Approved',
            'Approved_By': current_user.full_name or current_user.email,
            'Approved_Date': __import__('datetime').datetime.now().strftime('%Y-%m-%d')
        }
        
        success = update_approval_status(approval_id, approval_update)
        
        if success:
            return JSONResponse({"status": "success", "message": "Request approved successfully"})
        else:
            return JSONResponse({"status": "error", "message": "Failed to update approval status"})
            
    except Exception as e:
        return JSONResponse({"status": "error", "message": f"Error processing approval: {str(e)}"})

@router.post("/reject/{approval_id}")
async def reject_request(
    approval_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Reject a request."""
    if current_user.role not in ['admin', 'manager']:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Update approval status
    approval_update = {
        'Status': 'Rejected',
        'Approved_By': current_user.full_name or current_user.email,
        'Approved_Date': __import__('datetime').datetime.now().strftime('%Y-%m-%d')
    }
    
    success = update_approval_status(approval_id, approval_update)
    
    if success:
        return JSONResponse({"status": "success", "message": "Request rejected"})
    else:
        return JSONResponse({"status": "error", "message": "Failed to update approval status"})
from fastapi import APIRouter, Request, Depends
from starlette.templating import Jinja2Templates
from app.utils.auth import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/assets")
async def assets_page(request: Request, current_user=Depends(get_current_user)):
    """Assets listing page with filtering and pagination"""
    from app.utils.sheets import get_all_assets
    
    # Ambil data asset dari Google Sheets
    all_assets = get_all_assets()
    
    # Filter hanya aset aktif (bukan Disposed)
    active_assets = [asset for asset in all_assets if asset.get("Status", "").lower() != "disposed"]
    
    return templates.TemplateResponse("assets.html", {
        "request": request,
        "user": current_user,
        "assets_data": active_assets
    })
# app/routes/asset_management.py
from fastapi import APIRouter, Depends, Request, Form, File, UploadFile, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import json
from datetime import datetime
import io

from app.database.database import get_db
from app.database.models import Profile, UserRole
from app.utils.photo import resize_and_convert_image, upload_to_drive
from app.utils.sheets import get_dropdown_options, add_asset as sheets_add_asset
from app.utils.flash import set_flash
from app.utils.auth import get_current_user, get_admin_user
from app.config import load_config

config = load_config()
router = APIRouter(prefix="/asset_management", tags=["asset_management"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/add", response_class=HTMLResponse)
async def add_asset_form(
    request: Request,
    db: Session = Depends(get_db),
    current_profile = Depends(get_current_user)
):
    """Form to add a new asset."""
    dropdown_options = get_dropdown_options()
    return templates.TemplateResponse(
        "asset_management/add.html",
        {
            "request": request,
            "user": current_profile,
            "dropdown_options": dropdown_options
        }
    )


@router.get("/list", response_class=HTMLResponse)
async def asset_list(
    request: Request,
    db: Session = Depends(get_db),
    current_profile = Depends(get_current_user)
):
    """List assets for editing (admin and manager only)."""
    if current_profile.role not in [UserRole.ADMIN, UserRole.MANAGER]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    from app.utils.sheets import get_all_assets
    assets = get_all_assets()
    
    locations = list(set(asset.get('Location', '') for asset in assets if asset.get('Location')))
    location_rooms = {}
    for asset in assets:
        location = asset.get('Location', '')
        room = asset.get('Room', '')
        if location and room:
            if location not in location_rooms:
                location_rooms[location] = set()
            location_rooms[location].add(room)
    
    for location in location_rooms:
        location_rooms[location] = list(location_rooms[location])
    
    return templates.TemplateResponse(
        "asset_management/list.html",
        {
            "request": request,
            "user": current_profile,
            "assets": assets,
            "locations": sorted(locations),
            "location_rooms": location_rooms
        }
    )


@router.get("/edit/{asset_id}", response_class=HTMLResponse)
async def edit_asset_form(
    asset_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_profile = Depends(get_current_user)
):
    """Form to edit an existing asset (admin/manager only)."""
    if current_profile.role not in [UserRole.ADMIN, UserRole.MANAGER]:
        raise HTTPException(status_code=403, detail="Access denied")

    from app.utils.sheets import get_asset_by_id
    asset = get_asset_by_id(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    dropdown_options = get_dropdown_options()
    
    return templates.TemplateResponse(
        "asset_management/edit.html",
        {
            "request": request,
            "user": current_profile,
            "asset": asset,
            "dropdown_options": dropdown_options
        }
    )


@router.post("/edit/{asset_id}")
async def update_asset(
    asset_id: str,
    request: Request,
    status: str = Form(...),
    company: str = Form(...),
    location: str = Form(...),
    room: str = Form(...),
    bisnis_unit: str = Form(None),
    edit_reason: str = Form(...),
    db: Session = Depends(get_db),
    current_profile = Depends(get_current_user)
):
    """Update existing asset (admin and manager only)."""
    if current_profile.role not in [UserRole.ADMIN, UserRole.MANAGER]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    from app.utils.sheets import update_asset as sheets_update_asset, calculate_asset_financials, get_asset_by_id
    asset = get_asset_by_id(asset_id)

    update_data = {
        "Status": status,
        "Company": company,
        "Location": location,
        "Room": room,
        "Bisnis Unit": bisnis_unit or ""
    }
    
    # Jika perlu hitung ulang nilai finansial, misalnya setelah perubahan harga
    # financials = calculate_asset_financials(purchase_cost, purchase_date, category)
    # update_data.update(financials)
    
    from app.utils.sheets import add_approval_request
    
    approval_data = {
        'type': 'edit_asset',
        'asset_id': asset_id,
        'asset_name': asset.get('Item Name', ''),
        'submitted_by': current_profile.full_name or current_profile.email,
        'submitted_date': datetime.now().strftime('%Y-%m-%d'),
        'description': f"Edit asset: {asset.get('Item Name', '')} - Reason: {edit_reason}",
        'edit_reason': edit_reason,
        'request_data': json.dumps(update_data, ensure_ascii=False)
    }
    
    approval_success = add_approval_request(approval_data)
    
    if approval_success:
        response = RedirectResponse(url="/asset_management/list", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, "Asset edit request submitted for manager approval", "success")
        return response
    else:
        dropdown_options = get_dropdown_options()
        return templates.TemplateResponse(
            "asset_management/edit.html",
            {
                "request": request,
                "user": current_profile,
                "asset": asset,
                "dropdown_options": dropdown_options,
                "error": "Error submitting edit request"
            },
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@router.post("/add")
async def add_asset(
    request: Request,
    item_name: str = Form(...),
    category: str = Form(...),
    type: str = Form(...),
    manufacture: str = Form(None),
    model: str = Form(None),
    serial_number: str = Form(None),
    company: str = Form(...),
    bisnis_unit: str = Form(None),
    location: str = Form(...),
    room: str = Form(...),
    notes: str = Form(None),
    item_condition: str = Form(None),
    purchase_date: str = Form(...),
    purchase_cost: str = Form(...),
    warranty: str = Form(None),
    supplier: str = Form(None),
    journal: str = Form(None),
    owner: str = Form(...),
    photo: UploadFile = File(None),
    db: Session = Depends(get_db),
    current_profile = Depends(get_current_user)
):
    """Process add asset form."""
    dropdown_options = get_dropdown_options()
    
    asset_data = {
        "Item Name": item_name,
        "Category": category,
        "Type": type,
        "Manufacture": manufacture or "",
        "Model": model or "",
        "Serial Number": serial_number or "",
        "Company": company,
        "Bisnis Unit": bisnis_unit or "",
        "Location": location,
        "Room": room,
        "Notes": notes or "",
        "Item Condition": item_condition or "",
        "Purchase Date": purchase_date,
        "Purchase Cost": purchase_cost,
        "Warranty": warranty or "",
        "Supplier": supplier or "",
        "Journal": journal or "",
        "Owner": owner,
        "Status": "Active"
    }
    
    photo_url = None
    if photo and photo.filename:
        try:
            contents = await photo.read()
            image_file = io.BytesIO(contents)
            processed_image = resize_and_convert_image(image_file)
            
            if processed_image:
                photo_url = upload_to_drive(processed_image, photo.filename, "new")
                if photo_url:
                    asset_data["Photo URL"] = photo_url
        except Exception as e:
            print(f"Error processing photo: {str(e)}")
    
    if current_profile.role == UserRole.ADMIN:
        success = sheets_add_asset(asset_data)
        
        if success:
            response = RedirectResponse(url="/assets/", status_code=status.HTTP_303_SEE_OTHER)
            set_flash(response, "Asset added successfully", "success")
            return response
        else:
            return templates.TemplateResponse(
                "asset_management/add.html",
                {
                    "request": request,
                    "user": current_profile,
                    "dropdown_options": dropdown_options,
                    "error": "Error adding asset to Google Sheets",
                    "form_data": asset_data
                },
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    from app.utils.sheets import add_approval_request
    
    approval_data = {
        'type': 'add_asset',
        'asset_id': 'NEW',
        'asset_name': item_name,
        'submitted_by': current_profile.full_name or current_profile.email,
        'submitted_date': datetime.now().strftime('%Y-%m-%d'),
        'description': f"Add new asset: {item_name}",
        'request_data': json.dumps(asset_data, ensure_ascii=False)
    }
    
    approval_success = add_approval_request(approval_data)
    
    if approval_success:
        response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, "Asset request submitted for approval", "success")
        return response
    else:
        return templates.TemplateResponse(
            "asset_management/add.html",
            {
                "request": request,
                "user": current_profile,
                "dropdown_options": dropdown_options,
                "error": "Error submitting approval request",
                "form_data": asset_data
            },
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
from fastapi import APIRouter, Request, Depends
from starlette.templating import Jinja2Templates
from app.utils.auth import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/")
async def damaged_assets_page(request: Request, current_user = Depends(get_current_user)):
    """Damaged assets page with search and log functionality"""
    from app.utils.sheets import get_all_assets, get_dropdown_options

    all_assets = get_all_assets()
    dropdown_options = get_dropdown_options()

    return templates.TemplateResponse("damaged_assets.html", {
        "request": request,
        "user": current_user,
        "assets_data": all_assets,
        "dropdown_options": dropdown_options
    })


@router.post("/lost")
async def submit_lost_report(request: Request, current_user = Depends(get_current_user)):
    """Submit lost report - syncs to Google Sheets"""
    from app.utils.sheets import add_lost_log, add_approval_request
    from datetime import datetime

    try:
        data = await request.json()

        lost_data = {
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'last_location': data.get('last_location'),
            'last_room': data.get('last_room', ''),
            'date_lost': data.get('date_lost'),
            'description': data.get('description'),
            'reported_by': current_user.full_name or current_user.email,
            'report_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'notes': data.get('notes', '')
        }

        log_success = add_lost_log(lost_data)

        approval_data = {
            'type': 'lost_report',
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'submitted_by': current_user.full_name or current_user.email,
            'submitted_date': datetime.now().strftime('%Y-%m-%d'),
            'description': f"Lost report: {data.get('description')}",
            'location': data.get('last_location')
        }

        approval_success = add_approval_request(approval_data)

        if log_success and approval_success:
            return {"status": "success", "message": "Lost report submitted and logged to Google Sheets"}
        else:
            return {"status": "error", "message": "Failed to sync with Google Sheets"}

    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/disposal")
async def submit_disposal_request(request: Request, current_user = Depends(get_current_user)):
    """Submit disposal request - syncs to Google Sheets"""
    from app.utils.sheets import add_disposal_log, add_approval_request
    from datetime import datetime

    try:
        data = await request.json()

        disposal_data = {
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'disposal_reason': data.get('disposal_reason'),
            'disposal_method': data.get('disposal_method', 'Standard'),
            'description': data.get('description'),
            'requested_by': current_user.full_name or current_user.email,
            'request_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'notes': data.get('notes', '')
        }

        log_success = add_disposal_log(disposal_data)

        approval_data = {
            'type': 'disposal_request',
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'submitted_by': current_user.full_name or current_user.email,
            'submitted_date': datetime.now().strftime('%Y-%m-%d'),
            'description': f"Disposal request: {data.get('description')}"
        }

        approval_success = add_approval_request(approval_data)

        if log_success and approval_success:
            return {"status": "success", "message": "Disposal request submitted and logged to Google Sheets"}
        else:
            return {"status": "error", "message": "Failed to sync with Google Sheets"}

    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/report")
async def submit_damage_report(request: Request, current_user = Depends(get_current_user)):
    """Submit damage report - syncs to Google Sheets"""
    from app.utils.sheets import add_damage_log, add_approval_request
    from datetime import datetime

    try:
        data = await request.json()

        damage_data = {
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'damage_type': data.get('damage_type'),
            'severity': data.get('severity'),
            'description': data.get('damage_description'),
            'reported_by': current_user.full_name or current_user.email,
            'report_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'location': data.get('location', ''),
            'room': data.get('room', ''),
            'notes': data.get('notes', '')
        }

        approval_data = {
            'type': 'damage_report',
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'submitted_by': current_user.full_name or current_user.email,
            'submitted_date': datetime.now().strftime('%Y-%m-%d'),
            'description': f"Damage report: {data.get('damage_description')}",
            'damage_type': data.get('damage_type'),
            'severity': data.get('severity')
        }

        approval_success = add_approval_request(approval_data)

        if approval_success:
            return {"status": "success", "message": "Damage report submitted for approval"}
        else:
            return {"status": "error", "message": "Failed to submit approval request"}

    except Exception as e:
        return {"status": "error", "message": str(e)}
# app/routes/disposal.py
from fastapi import APIRouter, Depends, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime

from app.database.database import get_db
from app.database.models import Profile
from app.utils.auth import get_admin_user
from app.utils.sheets import get_all_assets, update_asset, add_disposal_log
from app.utils.flash import set_flash

router = APIRouter(prefix="/disposal", tags=["disposal"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def disposal_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Disposal assets page (admin only)."""
    # Get assets that are ready to dispose only
    all_assets = get_all_assets()
    # Debug: check all statuses
    statuses = [str(asset.get('Status', '')).strip() for asset in all_assets]
    print(f"All statuses found: {set(statuses)}")
    
    disposable_assets = []
    for asset in all_assets:
        status = str(asset.get('Status', '')).strip()
        if status in ['To Be Disposed', 'To be Disposed', 'TO BE DISPOSED']:
            disposable_assets.append(asset)
    
    return templates.TemplateResponse(
        "disposal/index.html",
        {
            "request": request,
            "user": current_user,
            "assets": disposable_assets
        }
    )

@router.post("/dispose/{asset_id}")
async def dispose_asset(
    asset_id: str,
    request: Request,
    disposal_reason: str = Form(...),
    disposal_method: str = Form(...),
    description: str = Form(None),
    notes: str = Form(None),
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Dispose an asset (admin only)."""
    from app.utils.sheets import get_asset_by_id
    
    # Get asset data
    asset = get_asset_by_id(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    if str(asset.get('Status', '')).strip() != 'To Be Disposed':
        raise HTTPException(status_code=400, detail="Asset must be marked 'To Be Disposed' first")
    
    # Create disposal approval request
    from app.utils.sheets import add_approval_request
    
    approval_data = {
        'type': 'disposal',
        'asset_id': asset_id,
        'asset_name': asset.get('Item Name', ''),
        'submitted_by': current_user.full_name or current_user.email,
        'submitted_date': datetime.now().strftime('%Y-%m-%d'),
        'description': f"Disposal request: {disposal_reason} - {disposal_method}",
        'disposal_reason': disposal_reason,
        'disposal_method': disposal_method,
        'notes': f"Description: {description or ''} | Notes: {notes or ''}"
    }
    
    approval_success = add_approval_request(approval_data)
    
    if approval_success:
        response = RedirectResponse(url="/disposal", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, f"Disposal request for {asset.get('Item Name', '')} submitted for manager approval", "success")
        return response
    else:
        response = RedirectResponse(url="/disposal", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, "Error submitting disposal request", "error")
        return response
# app/routes/health.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
import time

from app.database.database import get_db
from app.config import load_config

router = APIRouter(tags=["health"])
config = load_config()

@router.get("/health")
async def health_check(db: Session = Depends(get_db)):
    """Health check endpoint."""
    start_time = time.time()
    
    # Check database connection
    try:
        db.execute(text("SELECT 1"))
        db_status = "healthy"
    except Exception as e:
        db_status = f"unhealthy: {str(e)}"
    
    # Check Google Sheets API
    sheets_status = "configured" if config.GOOGLE_SHEET_ID else "not configured"
    
    # Response time
    response_time = time.time() - start_time
    
    return {
        "status": "ok",
        "database": db_status,
        "google_sheets": sheets_status,
        "response_time_ms": round(response_time * 1000, 2)
    }
# /app/app/routes/home.py
import logging
from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse
from starlette.templating import Jinja2Templates
from app.utils.auth import get_current_user
from app.utils.sheets import get_summary_data, get_chart_data, get_all_assets

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=RedirectResponse)
async def redirect_root():
    return RedirectResponse("/dashboard")

@router.get("/dashboard")
async def home(request: Request, current_user = Depends(get_current_user)):
    try:
        # Summary and chart data
        summary_data = get_summary_data()
        chart_data = get_chart_data()
        all_assets = get_all_assets()

        # Filter out disposed assets for dashboard counts
        active_assets = [asset for asset in all_assets if asset.get("Status", "") != "Disposed"]
        disposed_assets = [asset for asset in all_assets if asset.get("Status", "") == "Disposed"]
        
        # Count assets by status and activity
        total_assets = len(active_assets)
        disposed_count = len(disposed_assets)
        damaged_count = len([a for a in all_assets if a.get("Status", "") == "Under Repair"])
        
        # Count assets by activity type
        relocated_count = len([a for a in all_assets if a.get("Last Activity", "") == "Relocated"])
        repaired_count = len([a for a in all_assets if a.get("Last Activity", "") == "Repaired"])
        to_be_disposed_count = len([a for a in all_assets if a.get("Status", "") == "To Be Disposed"])
        
        # Helper function to safely convert values to float
        def safe_float(value):
            if value is None or value == '':
                return 0.0
            try:
                return float(value)
            except (ValueError, TypeError):
                return 0.0
        
        # Calculate financial values directly from assets
        total_purchase_value = sum(safe_float(asset.get("Purchase Cost")) for asset in active_assets)
        total_book_value = sum(safe_float(asset.get("Book Value")) for asset in active_assets)
        # Calculate depreciation as purchase value minus book value
        total_depreciation_value = total_purchase_value - total_book_value
        category_counts = chart_data.get("category_counts", {})
        
        # Format location data
        location_data = chart_data.get("location_chart_data", {})
        location_counts = location_data.get("labels", [])
        location_values = location_data.get("values", [])
        location_counts_dict = dict(zip(location_counts, location_values))

        # Format time-based chart data
        monthly_data = chart_data.get("monthly_chart_data", {})
        monthly_chart_labels = monthly_data.get("labels", [])
        monthly_chart_values = monthly_data.get("values", [])
        
        # Generate quarterly data (last 12 quarters - 3 years)
        quarterly_chart_labels = []
        quarterly_chart_values = []
        
        # Get current year and quarter
        from datetime import datetime
        current_date = datetime.now()
        current_year = current_date.year
        current_quarter = (current_date.month - 1) // 3 + 1
        
        # Generate data for the last 12 quarters
        for i in range(11, -1, -1):
            year = current_year
            quarter = current_quarter - i
            
            # Adjust year if quarter is negative or > 4
            while quarter <= 0:
                year -= 1
                quarter += 4
            while quarter > 4:
                year += 1
                quarter -= 4
                
            quarterly_chart_labels.append(f"Q{quarter} {year}")
            
            # Count assets added in this quarter
            quarter_start_month = (quarter - 1) * 3 + 1
            quarter_end_month = quarter * 3
            
            count = 0
            for asset in all_assets:
                purchase_date = asset.get("Purchase Date", "")
                if purchase_date:
                    try:
                        date = datetime.strptime(purchase_date, "%Y-%m-%d")
                        if date.year == year and quarter_start_month <= date.month <= quarter_end_month:
                            count += 1
                    except:
                        pass
            
            quarterly_chart_values.append(count)
        
        # Generate yearly data (last 5 years)
        yearly_chart_labels = []
        yearly_chart_values = []
        
        # Generate data for the last 5 years
        for i in range(4, -1, -1):
            year = current_year - i
            yearly_chart_labels.append(str(year))
            
            # Count assets added in this year
            count = 0
            for asset in all_assets:
                purchase_date = asset.get("Purchase Date", "")
                if purchase_date:
                    try:
                        date = datetime.strptime(purchase_date, "%Y-%m-%d")
                        if date.year == year:
                            count += 1
                    except:
                        pass
            
            yearly_chart_values.append(count)

        # Format age distribution - convert to list of tuples for proper serialization
        age_distribution = chart_data.get("age_distribution", {})
        age_distribution_list = [
            {"label": str(k), "value": int(v)} 
            for k, v in age_distribution.items()
        ]

        # Format latest assets (excluding disposed assets)
        latest_assets = sorted(
            active_assets, 
            key=lambda a: a.get("Purchase Date", ""), 
            reverse=True
        )[:10]
        
        # Process assets to ensure they have a display_name field
        for asset in latest_assets:
            # Try different possible field names for the asset name
            name_fields = ["Name", "Asset Name", "AssetName", "Item Name", "Description", "Item"]
            display_name = None
            
            for field in name_fields:
                if asset.get(field):
                    display_name = asset.get(field)
                    break
            
            # If no name found, use a default
            if not display_name:
                display_name = f"Asset #{asset.get('ID', 'Unknown')}"
                
            # Add the display_name to the asset
            asset["display_name"] = display_name
            
        # Debug: Print the first asset's keys to see what fields are available
        if latest_assets:
            logging.info(f"Asset keys: {list(latest_assets[0].keys())}")
            logging.info(f"Asset display name: {latest_assets[0].get('display_name', 'Not found')}")
            logging.info(f"Original asset name fields: {[latest_assets[0].get(f, 'None') for f in name_fields]}")

        context = {
            "request": request,
            "user": current_user,
            "total_assets": total_assets,
            "total_purchase_value": total_purchase_value,
            "total_book_value": total_book_value,
            "total_depreciation_value": total_depreciation_value,
            "disposed_count": disposed_count,
            "damaged_count": damaged_count,
            "relocated_count": relocated_count,
            "repaired_count": repaired_count,
            "to_be_disposed_count": to_be_disposed_count,
            "category_counts": category_counts,
            "location_counts": location_counts_dict,
            "monthly_chart_labels": monthly_chart_labels,
            "monthly_chart_values": monthly_chart_values,
            "quarterly_chart_labels": quarterly_chart_labels,
            "quarterly_chart_values": quarterly_chart_values,
            "yearly_chart_labels": yearly_chart_labels,
            "yearly_chart_values": yearly_chart_values,
            "age_distribution": age_distribution_list,
            "latest_assets": latest_assets
        }

        return templates.TemplateResponse("dashboard.html", context)

    except Exception as e:
        logging.error("Dashboard error: %s", e, exc_info=True)
        return templates.TemplateResponse("error.html", {
            "request": request,
            "user": current_user,
            "message": "Terjadi kesalahan saat memuat dashboard.",
        })
from fastapi import APIRouter, Request, Response, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from supabase import create_client, Client
from app.config import load_config
import logging

config = load_config()
supabase: Client = create_client(config.SUPABASE_URL, config.SUPABASE_ANON_KEY)

router = APIRouter(tags=["authentication"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/login", response_class=HTMLResponse)
@router.head("/login", response_class=HTMLResponse)
async def login_page(request: Request, next: str = None):
    return templates.TemplateResponse("login_logout.html", {"request": request, "next": next})

@router.post("/login", response_class=HTMLResponse)
async def login_form(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    next: str = Form(None)
):
    try:
        # Use service key client for admin operations
        from supabase import create_client
        admin_supabase = create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_KEY)
        
        response = admin_supabase.auth.sign_in_with_password({
            "email": email,
            "password": password
        })
        
        if not response.user:
            return templates.TemplateResponse(
                "login_logout.html",
                {"request": request, "error": "Invalid email or password", "next": next},
                status_code=401
            )
        
        # Get user profile
        profile_response = admin_supabase.table('profiles').select('*').eq('id', response.user.id).single().execute()
        if not profile_response.data or not profile_response.data.get('is_active'):
            return templates.TemplateResponse(
                "login_logout.html",
                {"request": request, "error": "Account is inactive", "next": next},
                status_code=401
            )
        
        redirect_url = next if next else "/"
        redirect_response = RedirectResponse(url=redirect_url, status_code=303)
        
        redirect_response.set_cookie(
            key="sb_access_token",
            value=response.session.access_token,
            httponly=True,
            max_age=3600,
            samesite="lax",
            secure=True,
            domain=".onrender.com"
        )
        
        return redirect_response
        
    except Exception as e:
        logging.error(f"Login error: {str(e)}")
        return templates.TemplateResponse(
            "login_logout.html",
            {"request": request, "error": "Login failed", "next": next},
            status_code=401
        )

@router.get("/auth/callback")
async def auth_callback(request: Request):
    return templates.TemplateResponse("auth_callback.html", {"request": request})

@router.get("/logout")
async def logout():
    try:
        supabase.auth.sign_out()
    except:
        pass
    
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(key="sb_access_token")
    return response
# app/routes/logs.py
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.database.models import Profile
from app.utils.auth import get_current_user
from app.utils.sheets import get_all_approvals

router = APIRouter(prefix="/logs", tags=["logs"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def logs_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """View approval logs based on user role."""
    all_approvals = get_all_approvals()
    
    # Filter based on user role
    if current_user.role.value == 'staff':
        # Staff can only see their own requests
        user_identifier = current_user.full_name or current_user.email
        approvals = [a for a in all_approvals if a.get('Submitted_By') == user_identifier]
    else:
        # Manager and admin can see all approvals
        approvals = all_approvals
    
    # Separate pending and completed
    pending_approvals = [a for a in approvals if a.get('Status') == 'Pending']
    completed_approvals = [a for a in approvals if a.get('Status') in ['Approved', 'Rejected']]
    
    return templates.TemplateResponse(
        "logs/index.html",
        {
            "request": request,
            "user": current_user,
            "pending_approvals": pending_approvals,
            "completed_approvals": completed_approvals
        }
    )
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
from fastapi import APIRouter, Depends, Request, Form, UploadFile, File, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from app.database.database import get_db
from app.database.models import Profile
from app.utils.auth import get_current_user
from app.utils.photo import resize_and_convert_image, upload_to_drive
from app.utils.flash import set_flash

router = APIRouter(tags=["profile"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/profile", response_class=HTMLResponse)
async def profile_page(
    request: Request,
    current_user = Depends(get_current_user)
):
    """User profile page."""
    return templates.TemplateResponse(
        "profile/view.html",
        {
            "request": request,
            "user": current_user
        }
    )

@router.get("/profile/edit", response_class=HTMLResponse)
async def edit_profile_page(
    request: Request,
    current_user = Depends(get_current_user)
):
    """Edit user profile page."""
    return templates.TemplateResponse(
        "profile/edit.html",
        {
            "request": request,
            "user": current_user
        }
    )

@router.post("/profile/edit")
async def update_profile(
    request: Request,
    full_name: str = Form(...),
    email: str = Form(...),
    photo: UploadFile = File(None),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Update user profile."""
    # Update basic info
    current_user.full_name = full_name
    current_user.email = email
    current_user.updated_at = datetime.now(timezone.utc)
    
    # Handle photo upload if provided
    if photo and photo.filename:
        try:
            # Process image
            contents = await photo.read()
            import io
            image_file = io.BytesIO(contents)
            processed_image = resize_and_convert_image(image_file)
            
            if processed_image:
                # Upload to Google Drive
                photo_url = upload_to_drive(
                    processed_image, 
                    photo.filename, 
                    f"profile_{current_user.email}"
                )
                if photo_url:
                    current_user.photo_url = photo_url
        except Exception as e:
            return templates.TemplateResponse(
                "profile/edit.html",
                {
                    "request": request,
                    "user": current_user,
                    "error": f"Error uploading photo: {str(e)}"
                },
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    # Save changes
    db.commit()
    
    # Redirect to profile page
    response = RedirectResponse(url="/profile", status_code=status.HTTP_303_SEE_OTHER)
    set_flash(response, "Profile updated successfully", "success")
    return response
# app/routes/relocation.py
from fastapi import APIRouter, Depends, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime
import json

from app.database.database import get_db
from app.database.models import Profile
from app.utils.auth import get_current_user
from app.utils.sheets import get_all_assets, get_dropdown_options, add_approval_request
from app.utils.flash import set_flash

router = APIRouter(prefix="/relocation", tags=["relocation"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def relocation_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Asset relocation page."""
    # Get assets and dropdown options
    all_assets = get_all_assets()
    dropdown_options = get_dropdown_options()
    
    return templates.TemplateResponse(
        "relocation/index.html",
        {
            "request": request,
            "user": current_user,
            "assets": all_assets,
            "dropdown_options": dropdown_options
        }
    )

@router.post("/relocate/{asset_id}")
async def relocate_asset(
    asset_id: str,
    request: Request,
    new_location: str = Form(...),
    new_room: str = Form(...),
    reason: str = Form(...),
    notes: str = Form(None),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Submit asset relocation request."""
    from app.utils.sheets import get_asset_by_id
    
    # Get asset data
    asset = get_asset_by_id(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    # Create relocation approval request
    relocation_data = {
        'new_location': new_location,
        'new_room': new_room,
        'current_location': asset.get('Location', ''),
        'current_room': asset.get('Room', ''),
        'reason': reason,
        'notes': notes or ''
    }
    
    approval_data = {
        'type': 'relocation',
        'asset_id': asset_id,
        'asset_name': asset.get('Item Name', ''),
        'submitted_by': current_user.full_name or current_user.email,
        'submitted_date': datetime.now().strftime('%Y-%m-%d'),
        'description': f"Relocate from {asset.get('Location', '')} - {asset.get('Room', '')} to {new_location} - {new_room}",
        'request_data': json.dumps(relocation_data, ensure_ascii=False)
    }
    
    approval_success = add_approval_request(approval_data)
    
    if approval_success:
        response = RedirectResponse(url="/relocation", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, f"Relocation request for {asset.get('Item Name', '')} submitted for approval", "success")
        return response
    else:
        response = RedirectResponse(url="/relocation", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, "Error submitting relocation request", "error")
        return response
# /app/app/routes/repair.py
from fastapi import APIRouter, Request, Depends
from starlette.templating import Jinja2Templates
from app.utils.auth import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.post("/action")
async def submit_repair_action(request: Request, current_user = Depends(get_current_user)):
    """Submit repair action - creates approval request for store, direct action for allocate"""
    from app.utils.sheets import add_repair_log, update_asset, add_approval_request
    from datetime import datetime
    
    try:
        # Get JSON data
        data = await request.json()
        action_type = data.get('action_type')  # 'store' or 'allocate'
        
        if action_type == 'store':
            # Store action requires approval - only create approval request
            approval_data = {
                'type': 'repair_action',
                'asset_id': data.get('asset_id'),
                'asset_name': data.get('asset_name'),
                'submitted_by': current_user.full_name or current_user.email,
                'submitted_date': datetime.now().strftime('%Y-%m-%d'),
                'description': f"Request to store asset: {data.get('description')}",
                'action': 'Store Asset'
            }
            
            approval_success = add_approval_request(approval_data)
            
            if approval_success:
                return {"status": "success", "message": "Store request submitted for admin approval"}
            else:
                return {"status": "error", "message": "Failed to submit approval request"}
        
        else:  # allocate - direct action
            # Add to Repair_Log sheet
            repair_data = {
                'asset_id': data.get('asset_id'),
                'asset_name': data.get('asset_name'),
                'repair_action': 'Allocate Asset',
                'action_type': action_type,
                'description': data.get('description', ''),
                'performed_by': current_user.full_name or current_user.email,
                'action_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'new_location': data.get('location', ''),
                'new_room': data.get('room', ''),
                'notes': data.get('notes', '')
            }
            
            # Add to repair log
            log_success = add_repair_log(repair_data)
            
            # Update asset from Under Repair to Active
            update_data = {
                'Status': 'Active',
                'Bisnis Unit': data.get('business_unit', ''),
                'Location': data.get('location', ''),
                'Room': data.get('room', '')
            }
            
            asset_success = update_asset(data.get('asset_id'), update_data)
            
            if log_success and asset_success:
                return {"status": "success", "message": "Asset allocated successfully and synced to Google Sheets"}
            else:
                return {"status": "error", "message": "Failed to sync with Google Sheets"}
            
    except Exception as e:
        return {"status": "error", "message": str(e)}
# app/routes/user_management.py
from fastapi import APIRouter, Depends, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.database.models import Profile, UserRole
from app.utils.auth import get_current_user, get_admin_user
from app.utils.flash import set_flash

router = APIRouter(prefix="/user_management", tags=["user_management"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def user_list(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """List all users (admin only)."""
    users = db.query(Profile).all()
    
    return templates.TemplateResponse(
        "user_management/list.html",
        {
            "request": request,
            "user": current_user,
            "users": users
        }
    )

@router.get("/create", response_class=HTMLResponse)
async def create_user_form(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Create user form (admin only)."""
    return templates.TemplateResponse(
        "user_management/create.html",
        {
            "request": request,
            "user": current_user
        }
    )

@router.post("/create")
async def create_user(
    request: Request,
    email: str = Form(...),
    full_name: str = Form(...),
    role: str = Form(...),
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Create new user (admin only)."""
    # Check if user exists
    existing_user = db.query(Profile).filter(Profile.email == email).first()
    if existing_user:
        return templates.TemplateResponse(
            "user_management/create.html",
            {
                "request": request,
                "user": current_user,
                "error": "Email already exists"
            }
        )
    
    # Create user profile (Supabase handles auth)
    new_user = Profile(
        email=email,
        full_name=full_name,
        role=getattr(UserRole, role.upper()),
        is_active=True
    )
    
    db.add(new_user)
    db.commit()
    
    response = RedirectResponse(url="/user_management", status_code=status.HTTP_303_SEE_OTHER)
    set_flash(response, f"User {email} created successfully", "success")
    return response

@router.post("/reset_password/{user_id}")
async def reset_password(
    user_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Reset user password to default (admin only)."""
    user = db.query(Profile).filter(Profile.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Password reset handled by Supabase
    default_password = f"{user.email.split('@')[0]}123"
    
    response = RedirectResponse(url="/user_management", status_code=status.HTTP_303_SEE_OTHER)
    set_flash(response, f"Password reset instructions sent to {user.email}", "success")
    return response

@router.post("/toggle_status/{user_id}")
async def toggle_user_status(
    user_id: str,
    request: Request,
    is_active: bool = Form(...),
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Toggle user active status (admin only)."""
    user = db.query(Profile).filter(Profile.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Update status
    user.is_active = is_active
    db.commit()
    
    status_text = "activated" if is_active else "deactivated"
    response = RedirectResponse(url="/user_management", status_code=status.HTTP_303_SEE_OTHER)
    set_flash(response, f"User {user.email} {status_text}", "success")
    return response
# app/routes/__init__.py

# Import all route modules to make them available from app.routes
from app.routes import (
    home,
    assets,
    asset_management,
    login,
    damage,
    health,
    offline,
    profile,
    repair,
    approvals,
    disposal,
    user_management,
    logs,
    relocation
)
# app/routes/approvals.py
from fastapi import APIRouter, Depends, Request, HTTPException, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.utils.auth import get_current_user
from app.utils.sheets import get_all_approvals, update_approval_status

router = APIRouter(prefix="/approvals", tags=["approvals"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def approvals_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Approvals page for admin and manager."""
    if current_user.role not in ['admin', 'manager']:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get all approvals from Google Sheets
    all_approvals = get_all_approvals()
    
    # Filter approvals based on user role
    if current_user.role == 'admin':
        # Admin sees all approvals except disposal and edit_asset
        approvals_data = [a for a in all_approvals if a.get('Type') not in ['disposal', 'edit_asset']]
    elif current_user.role == 'manager':
        # Manager sees disposal and edit_asset approvals
        approvals_data = [a for a in all_approvals if a.get('Type') in ['disposal', 'edit_asset']]
    else:
        approvals_data = []
    
    return templates.TemplateResponse(
        "approvals/list.html",
        {
            "request": request,
            "user": current_user,
            "approvals_data": approvals_data
        }
    )

@router.post("/approve/{approval_id}")
async def approve_request(
    approval_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Approve a request."""
    if current_user.role not in ['admin', 'manager']:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get approval details
    all_approvals = get_all_approvals()
    approval = next((a for a in all_approvals if str(a.get('ID')) == str(approval_id)), None)
    
    if not approval:
        return JSONResponse({"status": "error", "message": "Approval not found"})
    
    # Process approval based on type
    try:
        if approval.get('Type') == 'damage_report':
            # Update asset status to "Under Repair"
            from app.utils.sheets import update_asset
            success = update_asset(approval.get('Asset_ID'), {'Status': 'Under Repair'})
            if not success:
                return JSONResponse({"status": "error", "message": "Failed to update asset status"})
        
        elif approval.get('Type') == 'relocation':
            # Process relocation approval
            import json
            try:
                request_data_str = approval.get('Request_Data', '')
                if request_data_str:
                    relocation_data = json.loads(request_data_str)
                    update_data = {
                        'Location': relocation_data.get('new_location'),
                        'Room': relocation_data.get('new_room')
                    }
                    from app.utils.sheets import update_asset
                    success = update_asset(approval.get('Asset_ID'), update_data)
                    if not success:
                        return JSONResponse({"status": "error", "message": "Failed to relocate asset"})
            except Exception as e:
                return JSONResponse({"status": "error", "message": f"Error processing relocation: {str(e)}"})
            
        elif approval.get('Type') == 'edit_asset':
            # Process edit asset approval
            import json
            try:
                request_data_str = approval.get('Request_Data', '')
                if request_data_str:
                    edit_data = json.loads(request_data_str)
                    from app.utils.sheets import update_asset
                    success = update_asset(approval.get('Asset_ID'), edit_data)
                    if not success:
                        return JSONResponse({"status": "error", "message": "Failed to update asset"})
            except Exception as e:
                return JSONResponse({"status": "error", "message": f"Error processing edit: {str(e)}"})
        
        # Update approval status
        approval_update = {
            'Status': 'Approved',
            'Approved_By': current_user.full_name or current_user.email,
            'Approved_Date': __import__('datetime').datetime.now().strftime('%Y-%m-%d')
        }
        
        success = update_approval_status(approval_id, approval_update)
        
        if success:
            return JSONResponse({"status": "success", "message": "Request approved successfully"})
        else:
            return JSONResponse({"status": "error", "message": "Failed to update approval status"})
            
    except Exception as e:
        return JSONResponse({"status": "error", "message": f"Error processing approval: {str(e)}"})

@router.post("/reject/{approval_id}")
async def reject_request(
    approval_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Reject a request."""
    if current_user.role not in ['admin', 'manager']:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Update approval status
    approval_update = {
        'Status': 'Rejected',
        'Approved_By': current_user.full_name or current_user.email,
        'Approved_Date': __import__('datetime').datetime.now().strftime('%Y-%m-%d')
    }
    
    success = update_approval_status(approval_id, approval_update)
    
    if success:
        return JSONResponse({"status": "success", "message": "Request rejected"})
    else:
        return JSONResponse({"status": "error", "message": "Failed to update approval status"})
from fastapi import APIRouter, Request, Depends
from starlette.templating import Jinja2Templates
from app.utils.auth import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/assets")
async def assets_page(request: Request, current_user=Depends(get_current_user)):
    """Assets listing page with filtering and pagination"""
    from app.utils.sheets import get_all_assets
    
    # Ambil data asset dari Google Sheets
    all_assets = get_all_assets()
    
    # Filter hanya aset aktif (bukan Disposed)
    active_assets = [asset for asset in all_assets if asset.get("Status", "").lower() != "disposed"]
    
    return templates.TemplateResponse("assets.html", {
        "request": request,
        "user": current_user,
        "assets_data": active_assets
    })
# app/routes/asset_management.py
from fastapi import APIRouter, Depends, Request, Form, File, UploadFile, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import json
from datetime import datetime
import io

from app.database.database import get_db
from app.database.models import Profile, UserRole
from app.utils.photo import resize_and_convert_image, upload_to_drive
from app.utils.sheets import get_dropdown_options, add_asset as sheets_add_asset
from app.utils.flash import set_flash
from app.utils.auth import get_current_user, get_admin_user
from app.config import load_config

config = load_config()
router = APIRouter(prefix="/asset_management", tags=["asset_management"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/add", response_class=HTMLResponse)
async def add_asset_form(
    request: Request,
    db: Session = Depends(get_db),
    current_profile = Depends(get_current_user)
):
    """Form to add a new asset."""
    dropdown_options = get_dropdown_options()
    return templates.TemplateResponse(
        "asset_management/add.html",
        {
            "request": request,
            "user": current_profile,
            "dropdown_options": dropdown_options
        }
    )


@router.get("/list", response_class=HTMLResponse)
async def asset_list(
    request: Request,
    db: Session = Depends(get_db),
    current_profile = Depends(get_current_user)
):
    """List assets for editing (admin and manager only)."""
    if current_profile.role not in [UserRole.ADMIN, UserRole.MANAGER]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    from app.utils.sheets import get_all_assets
    assets = get_all_assets()
    
    locations = list(set(asset.get('Location', '') for asset in assets if asset.get('Location')))
    location_rooms = {}
    for asset in assets:
        location = asset.get('Location', '')
        room = asset.get('Room', '')
        if location and room:
            if location not in location_rooms:
                location_rooms[location] = set()
            location_rooms[location].add(room)
    
    for location in location_rooms:
        location_rooms[location] = list(location_rooms[location])
    
    return templates.TemplateResponse(
        "asset_management/list.html",
        {
            "request": request,
            "user": current_profile,
            "assets": assets,
            "locations": sorted(locations),
            "location_rooms": location_rooms
        }
    )


@router.get("/edit/{asset_id}", response_class=HTMLResponse)
async def edit_asset_form(
    asset_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_profile = Depends(get_current_user)
):
    """Form to edit an existing asset (admin/manager only)."""
    if current_profile.role not in [UserRole.ADMIN, UserRole.MANAGER]:
        raise HTTPException(status_code=403, detail="Access denied")

    from app.utils.sheets import get_asset_by_id
    asset = get_asset_by_id(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    dropdown_options = get_dropdown_options()
    
    return templates.TemplateResponse(
        "asset_management/edit.html",
        {
            "request": request,
            "user": current_profile,
            "asset": asset,
            "dropdown_options": dropdown_options
        }
    )


@router.post("/edit/{asset_id}")
async def update_asset(
    asset_id: str,
    request: Request,
    status: str = Form(...),
    company: str = Form(...),
    location: str = Form(...),
    room: str = Form(...),
    bisnis_unit: str = Form(None),
    edit_reason: str = Form(...),
    db: Session = Depends(get_db),
    current_profile = Depends(get_current_user)
):
    """Update existing asset (admin and manager only)."""
    if current_profile.role not in [UserRole.ADMIN, UserRole.MANAGER]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    from app.utils.sheets import update_asset as sheets_update_asset, calculate_asset_financials, get_asset_by_id
    asset = get_asset_by_id(asset_id)

    update_data = {
        "Status": status,
        "Company": company,
        "Location": location,
        "Room": room,
        "Bisnis Unit": bisnis_unit or ""
    }
    
    # Jika perlu hitung ulang nilai finansial, misalnya setelah perubahan harga
    # financials = calculate_asset_financials(purchase_cost, purchase_date, category)
    # update_data.update(financials)
    
    from app.utils.sheets import add_approval_request
    
    approval_data = {
        'type': 'edit_asset',
        'asset_id': asset_id,
        'asset_name': asset.get('Item Name', ''),
        'submitted_by': current_profile.full_name or current_profile.email,
        'submitted_date': datetime.now().strftime('%Y-%m-%d'),
        'description': f"Edit asset: {asset.get('Item Name', '')} - Reason: {edit_reason}",
        'edit_reason': edit_reason,
        'request_data': json.dumps(update_data, ensure_ascii=False)
    }
    
    approval_success = add_approval_request(approval_data)
    
    if approval_success:
        response = RedirectResponse(url="/asset_management/list", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, "Asset edit request submitted for manager approval", "success")
        return response
    else:
        dropdown_options = get_dropdown_options()
        return templates.TemplateResponse(
            "asset_management/edit.html",
            {
                "request": request,
                "user": current_profile,
                "asset": asset,
                "dropdown_options": dropdown_options,
                "error": "Error submitting edit request"
            },
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@router.post("/add")
async def add_asset(
    request: Request,
    item_name: str = Form(...),
    category: str = Form(...),
    type: str = Form(...),
    manufacture: str = Form(None),
    model: str = Form(None),
    serial_number: str = Form(None),
    company: str = Form(...),
    bisnis_unit: str = Form(None),
    location: str = Form(...),
    room: str = Form(...),
    notes: str = Form(None),
    item_condition: str = Form(None),
    purchase_date: str = Form(...),
    purchase_cost: str = Form(...),
    warranty: str = Form(None),
    supplier: str = Form(None),
    journal: str = Form(None),
    owner: str = Form(...),
    photo: UploadFile = File(None),
    db: Session = Depends(get_db),
    current_profile = Depends(get_current_user)
):
    """Process add asset form."""
    dropdown_options = get_dropdown_options()
    
    asset_data = {
        "Item Name": item_name,
        "Category": category,
        "Type": type,
        "Manufacture": manufacture or "",
        "Model": model or "",
        "Serial Number": serial_number or "",
        "Company": company,
        "Bisnis Unit": bisnis_unit or "",
        "Location": location,
        "Room": room,
        "Notes": notes or "",
        "Item Condition": item_condition or "",
        "Purchase Date": purchase_date,
        "Purchase Cost": purchase_cost,
        "Warranty": warranty or "",
        "Supplier": supplier or "",
        "Journal": journal or "",
        "Owner": owner,
        "Status": "Active"
    }
    
    photo_url = None
    if photo and photo.filename:
        try:
            contents = await photo.read()
            image_file = io.BytesIO(contents)
            processed_image = resize_and_convert_image(image_file)
            
            if processed_image:
                photo_url = upload_to_drive(processed_image, photo.filename, "new")
                if photo_url:
                    asset_data["Photo URL"] = photo_url
        except Exception as e:
            print(f"Error processing photo: {str(e)}")
    
    if current_profile.role == UserRole.ADMIN:
        success = sheets_add_asset(asset_data)
        
        if success:
            response = RedirectResponse(url="/assets/", status_code=status.HTTP_303_SEE_OTHER)
            set_flash(response, "Asset added successfully", "success")
            return response
        else:
            return templates.TemplateResponse(
                "asset_management/add.html",
                {
                    "request": request,
                    "user": current_profile,
                    "dropdown_options": dropdown_options,
                    "error": "Error adding asset to Google Sheets",
                    "form_data": asset_data
                },
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    from app.utils.sheets import add_approval_request
    
    approval_data = {
        'type': 'add_asset',
        'asset_id': 'NEW',
        'asset_name': item_name,
        'submitted_by': current_profile.full_name or current_profile.email,
        'submitted_date': datetime.now().strftime('%Y-%m-%d'),
        'description': f"Add new asset: {item_name}",
        'request_data': json.dumps(asset_data, ensure_ascii=False)
    }
    
    approval_success = add_approval_request(approval_data)
    
    if approval_success:
        response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, "Asset request submitted for approval", "success")
        return response
    else:
        return templates.TemplateResponse(
            "asset_management/add.html",
            {
                "request": request,
                "user": current_profile,
                "dropdown_options": dropdown_options,
                "error": "Error submitting approval request",
                "form_data": asset_data
            },
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
from fastapi import APIRouter, Request, Depends
from starlette.templating import Jinja2Templates
from app.utils.auth import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/")
async def damaged_assets_page(request: Request, current_user = Depends(get_current_user)):
    """Damaged assets page with search and log functionality"""
    from app.utils.sheets import get_all_assets, get_dropdown_options

    all_assets = get_all_assets()
    dropdown_options = get_dropdown_options()

    return templates.TemplateResponse("damaged_assets.html", {
        "request": request,
        "user": current_user,
        "assets_data": all_assets,
        "dropdown_options": dropdown_options
    })


@router.post("/lost")
async def submit_lost_report(request: Request, current_user = Depends(get_current_user)):
    """Submit lost report - syncs to Google Sheets"""
    from app.utils.sheets import add_lost_log, add_approval_request
    from datetime import datetime

    try:
        data = await request.json()

        lost_data = {
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'last_location': data.get('last_location'),
            'last_room': data.get('last_room', ''),
            'date_lost': data.get('date_lost'),
            'description': data.get('description'),
            'reported_by': current_user.full_name or current_user.email,
            'report_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'notes': data.get('notes', '')
        }

        log_success = add_lost_log(lost_data)

        approval_data = {
            'type': 'lost_report',
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'submitted_by': current_user.full_name or current_user.email,
            'submitted_date': datetime.now().strftime('%Y-%m-%d'),
            'description': f"Lost report: {data.get('description')}",
            'location': data.get('last_location')
        }

        approval_success = add_approval_request(approval_data)

        if log_success and approval_success:
            return {"status": "success", "message": "Lost report submitted and logged to Google Sheets"}
        else:
            return {"status": "error", "message": "Failed to sync with Google Sheets"}

    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/disposal")
async def submit_disposal_request(request: Request, current_user = Depends(get_current_user)):
    """Submit disposal request - syncs to Google Sheets"""
    from app.utils.sheets import add_disposal_log, add_approval_request
    from datetime import datetime

    try:
        data = await request.json()

        disposal_data = {
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'disposal_reason': data.get('disposal_reason'),
            'disposal_method': data.get('disposal_method', 'Standard'),
            'description': data.get('description'),
            'requested_by': current_user.full_name or current_user.email,
            'request_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'notes': data.get('notes', '')
        }

        log_success = add_disposal_log(disposal_data)

        approval_data = {
            'type': 'disposal_request',
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'submitted_by': current_user.full_name or current_user.email,
            'submitted_date': datetime.now().strftime('%Y-%m-%d'),
            'description': f"Disposal request: {data.get('description')}"
        }

        approval_success = add_approval_request(approval_data)

        if log_success and approval_success:
            return {"status": "success", "message": "Disposal request submitted and logged to Google Sheets"}
        else:
            return {"status": "error", "message": "Failed to sync with Google Sheets"}

    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/report")
async def submit_damage_report(request: Request, current_user = Depends(get_current_user)):
    """Submit damage report - syncs to Google Sheets"""
    from app.utils.sheets import add_damage_log, add_approval_request
    from datetime import datetime

    try:
        data = await request.json()

        damage_data = {
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'damage_type': data.get('damage_type'),
            'severity': data.get('severity'),
            'description': data.get('damage_description'),
            'reported_by': current_user.full_name or current_user.email,
            'report_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'location': data.get('location', ''),
            'room': data.get('room', ''),
            'notes': data.get('notes', '')
        }

        approval_data = {
            'type': 'damage_report',
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'submitted_by': current_user.full_name or current_user.email,
            'submitted_date': datetime.now().strftime('%Y-%m-%d'),
            'description': f"Damage report: {data.get('damage_description')}",
            'damage_type': data.get('damage_type'),
            'severity': data.get('severity')
        }

        approval_success = add_approval_request(approval_data)

        if approval_success:
            return {"status": "success", "message": "Damage report submitted for approval"}
        else:
            return {"status": "error", "message": "Failed to submit approval request"}

    except Exception as e:
        return {"status": "error", "message": str(e)}
# app/routes/disposal.py
from fastapi import APIRouter, Depends, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime

from app.database.database import get_db
from app.database.models import Profile
from app.utils.auth import get_admin_user
from app.utils.sheets import get_all_assets, update_asset, add_disposal_log
from app.utils.flash import set_flash

router = APIRouter(prefix="/disposal", tags=["disposal"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def disposal_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Disposal assets page (admin only)."""
    # Get assets that are ready to dispose only
    all_assets = get_all_assets()
    # Debug: check all statuses
    statuses = [str(asset.get('Status', '')).strip() for asset in all_assets]
    print(f"All statuses found: {set(statuses)}")
    
    disposable_assets = []
    for asset in all_assets:
        status = str(asset.get('Status', '')).strip()
        if status in ['To Be Disposed', 'To be Disposed', 'TO BE DISPOSED']:
            disposable_assets.append(asset)
    
    return templates.TemplateResponse(
        "disposal/index.html",
        {
            "request": request,
            "user": current_user,
            "assets": disposable_assets
        }
    )

@router.post("/dispose/{asset_id}")
async def dispose_asset(
    asset_id: str,
    request: Request,
    disposal_reason: str = Form(...),
    disposal_method: str = Form(...),
    description: str = Form(None),
    notes: str = Form(None),
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Dispose an asset (admin only)."""
    from app.utils.sheets import get_asset_by_id
    
    # Get asset data
    asset = get_asset_by_id(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    if str(asset.get('Status', '')).strip() != 'To Be Disposed':
        raise HTTPException(status_code=400, detail="Asset must be marked 'To Be Disposed' first")
    
    # Create disposal approval request
    from app.utils.sheets import add_approval_request
    
    approval_data = {
        'type': 'disposal',
        'asset_id': asset_id,
        'asset_name': asset.get('Item Name', ''),
        'submitted_by': current_user.full_name or current_user.email,
        'submitted_date': datetime.now().strftime('%Y-%m-%d'),
        'description': f"Disposal request: {disposal_reason} - {disposal_method}",
        'disposal_reason': disposal_reason,
        'disposal_method': disposal_method,
        'notes': f"Description: {description or ''} | Notes: {notes or ''}"
    }
    
    approval_success = add_approval_request(approval_data)
    
    if approval_success:
        response = RedirectResponse(url="/disposal", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, f"Disposal request for {asset.get('Item Name', '')} submitted for manager approval", "success")
        return response
    else:
        response = RedirectResponse(url="/disposal", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, "Error submitting disposal request", "error")
        return response
# app/routes/health.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
import time

from app.database.database import get_db
from app.config import load_config

router = APIRouter(tags=["health"])
config = load_config()

@router.get("/health")
async def health_check(db: Session = Depends(get_db)):
    """Health check endpoint."""
    start_time = time.time()
    
    # Check database connection
    try:
        db.execute(text("SELECT 1"))
        db_status = "healthy"
    except Exception as e:
        db_status = f"unhealthy: {str(e)}"
    
    # Check Google Sheets API
    sheets_status = "configured" if config.GOOGLE_SHEET_ID else "not configured"
    
    # Response time
    response_time = time.time() - start_time
    
    return {
        "status": "ok",
        "database": db_status,
        "google_sheets": sheets_status,
        "response_time_ms": round(response_time * 1000, 2)
    }
# /app/app/routes/home.py
import logging
from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse
from starlette.templating import Jinja2Templates
from app.utils.auth import get_current_user
from app.utils.sheets import get_summary_data, get_chart_data, get_all_assets

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=RedirectResponse)
async def redirect_root():
    return RedirectResponse("/dashboard")

@router.get("/dashboard")
async def home(request: Request, current_user = Depends(get_current_user)):
    try:
        # Summary and chart data
        summary_data = get_summary_data()
        chart_data = get_chart_data()
        all_assets = get_all_assets()

        # Filter out disposed assets for dashboard counts
        active_assets = [asset for asset in all_assets if asset.get("Status", "") != "Disposed"]
        disposed_assets = [asset for asset in all_assets if asset.get("Status", "") == "Disposed"]
        
        # Count assets by status and activity
        total_assets = len(active_assets)
        disposed_count = len(disposed_assets)
        damaged_count = len([a for a in all_assets if a.get("Status", "") == "Under Repair"])
        
        # Count assets by activity type
        relocated_count = len([a for a in all_assets if a.get("Last Activity", "") == "Relocated"])
        repaired_count = len([a for a in all_assets if a.get("Last Activity", "") == "Repaired"])
        to_be_disposed_count = len([a for a in all_assets if a.get("Status", "") == "To Be Disposed"])
        
        # Helper function to safely convert values to float
        def safe_float(value):
            if value is None or value == '':
                return 0.0
            try:
                return float(value)
            except (ValueError, TypeError):
                return 0.0
        
        # Calculate financial values directly from assets
        total_purchase_value = sum(safe_float(asset.get("Purchase Cost")) for asset in active_assets)
        total_book_value = sum(safe_float(asset.get("Book Value")) for asset in active_assets)
        # Calculate depreciation as purchase value minus book value
        total_depreciation_value = total_purchase_value - total_book_value
        category_counts = chart_data.get("category_counts", {})
        
        # Format location data
        location_data = chart_data.get("location_chart_data", {})
        location_counts = location_data.get("labels", [])
        location_values = location_data.get("values", [])
        location_counts_dict = dict(zip(location_counts, location_values))

        # Format time-based chart data
        monthly_data = chart_data.get("monthly_chart_data", {})
        monthly_chart_labels = monthly_data.get("labels", [])
        monthly_chart_values = monthly_data.get("values", [])
        
        # Generate quarterly data (last 12 quarters - 3 years)
        quarterly_chart_labels = []
        quarterly_chart_values = []
        
        # Get current year and quarter
        from datetime import datetime
        current_date = datetime.now()
        current_year = current_date.year
        current_quarter = (current_date.month - 1) // 3 + 1
        
        # Generate data for the last 12 quarters
        for i in range(11, -1, -1):
            year = current_year
            quarter = current_quarter - i
            
            # Adjust year if quarter is negative or > 4
            while quarter <= 0:
                year -= 1
                quarter += 4
            while quarter > 4:
                year += 1
                quarter -= 4
                
            quarterly_chart_labels.append(f"Q{quarter} {year}")
            
            # Count assets added in this quarter
            quarter_start_month = (quarter - 1) * 3 + 1
            quarter_end_month = quarter * 3
            
            count = 0
            for asset in all_assets:
                purchase_date = asset.get("Purchase Date", "")
                if purchase_date:
                    try:
                        date = datetime.strptime(purchase_date, "%Y-%m-%d")
                        if date.year == year and quarter_start_month <= date.month <= quarter_end_month:
                            count += 1
                    except:
                        pass
            
            quarterly_chart_values.append(count)
        
        # Generate yearly data (last 5 years)
        yearly_chart_labels = []
        yearly_chart_values = []
        
        # Generate data for the last 5 years
        for i in range(4, -1, -1):
            year = current_year - i
            yearly_chart_labels.append(str(year))
            
            # Count assets added in this year
            count = 0
            for asset in all_assets:
                purchase_date = asset.get("Purchase Date", "")
                if purchase_date:
                    try:
                        date = datetime.strptime(purchase_date, "%Y-%m-%d")
                        if date.year == year:
                            count += 1
                    except:
                        pass
            
            yearly_chart_values.append(count)

        # Format age distribution - convert to list of tuples for proper serialization
        age_distribution = chart_data.get("age_distribution", {})
        age_distribution_list = [
            {"label": str(k), "value": int(v)} 
            for k, v in age_distribution.items()
        ]

        # Format latest assets (excluding disposed assets)
        latest_assets = sorted(
            active_assets, 
            key=lambda a: a.get("Purchase Date", ""), 
            reverse=True
        )[:10]
        
        # Process assets to ensure they have a display_name field
        for asset in latest_assets:
            # Try different possible field names for the asset name
            name_fields = ["Name", "Asset Name", "AssetName", "Item Name", "Description", "Item"]
            display_name = None
            
            for field in name_fields:
                if asset.get(field):
                    display_name = asset.get(field)
                    break
            
            # If no name found, use a default
            if not display_name:
                display_name = f"Asset #{asset.get('ID', 'Unknown')}"
                
            # Add the display_name to the asset
            asset["display_name"] = display_name
            
        # Debug: Print the first asset's keys to see what fields are available
        if latest_assets:
            logging.info(f"Asset keys: {list(latest_assets[0].keys())}")
            logging.info(f"Asset display name: {latest_assets[0].get('display_name', 'Not found')}")
            logging.info(f"Original asset name fields: {[latest_assets[0].get(f, 'None') for f in name_fields]}")

        context = {
            "request": request,
            "user": current_user,
            "total_assets": total_assets,
            "total_purchase_value": total_purchase_value,
            "total_book_value": total_book_value,
            "total_depreciation_value": total_depreciation_value,
            "disposed_count": disposed_count,
            "damaged_count": damaged_count,
            "relocated_count": relocated_count,
            "repaired_count": repaired_count,
            "to_be_disposed_count": to_be_disposed_count,
            "category_counts": category_counts,
            "location_counts": location_counts_dict,
            "monthly_chart_labels": monthly_chart_labels,
            "monthly_chart_values": monthly_chart_values,
            "quarterly_chart_labels": quarterly_chart_labels,
            "quarterly_chart_values": quarterly_chart_values,
            "yearly_chart_labels": yearly_chart_labels,
            "yearly_chart_values": yearly_chart_values,
            "age_distribution": age_distribution_list,
            "latest_assets": latest_assets
        }

        return templates.TemplateResponse("dashboard.html", context)

    except Exception as e:
        logging.error("Dashboard error: %s", e, exc_info=True)
        return templates.TemplateResponse("error.html", {
            "request": request,
            "user": current_user,
            "message": "Terjadi kesalahan saat memuat dashboard.",
        })
from fastapi import APIRouter, Request, Response, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from supabase import create_client, Client
from app.config import load_config
import logging

config = load_config()
supabase: Client = create_client(config.SUPABASE_URL, config.SUPABASE_ANON_KEY)

router = APIRouter(tags=["authentication"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/login", response_class=HTMLResponse)
@router.head("/login", response_class=HTMLResponse)
async def login_page(request: Request, next: str = None):
    return templates.TemplateResponse("login_logout.html", {"request": request, "next": next})

@router.post("/login", response_class=HTMLResponse)
async def login_form(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    next: str = Form(None)
):
    try:
        # Use service key client for admin operations
        from supabase import create_client
        admin_supabase = create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_KEY)
        
        response = admin_supabase.auth.sign_in_with_password({
            "email": email,
            "password": password
        })
        
        if not response.user:
            return templates.TemplateResponse(
                "login_logout.html",
                {"request": request, "error": "Invalid email or password", "next": next},
                status_code=401
            )
        
        # Get user profile
        profile_response = admin_supabase.table('profiles').select('*').eq('id', response.user.id).single().execute()
        if not profile_response.data or not profile_response.data.get('is_active'):
            return templates.TemplateResponse(
                "login_logout.html",
                {"request": request, "error": "Account is inactive", "next": next},
                status_code=401
            )
        
        redirect_url = next if next else "/"
        redirect_response = RedirectResponse(url=redirect_url, status_code=303)
        
        redirect_response.set_cookie(
            key="sb_access_token",
            value=response.session.access_token,
            httponly=True,
            max_age=3600,
            samesite="lax",
            secure=True,
            domain=".onrender.com"
        )
        
        return redirect_response
        
    except Exception as e:
        logging.error(f"Login error: {str(e)}")
        return templates.TemplateResponse(
            "login_logout.html",
            {"request": request, "error": "Login failed", "next": next},
            status_code=401
        )

@router.get("/auth/callback")
async def auth_callback(request: Request):
    return templates.TemplateResponse("auth_callback.html", {"request": request})

@router.get("/logout")
async def logout():
    try:
        supabase.auth.sign_out()
    except:
        pass
    
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(key="sb_access_token")
    return response
# app/routes/logs.py
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.database.models import Profile
from app.utils.auth import get_current_user
from app.utils.sheets import get_all_approvals

router = APIRouter(prefix="/logs", tags=["logs"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def logs_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """View approval logs based on user role."""
    all_approvals = get_all_approvals()
    
    # Filter based on user role
    if current_user.role.value == 'staff':
        # Staff can only see their own requests
        user_identifier = current_user.full_name or current_user.email
        approvals = [a for a in all_approvals if a.get('Submitted_By') == user_identifier]
    else:
        # Manager and admin can see all approvals
        approvals = all_approvals
    
    # Separate pending and completed
    pending_approvals = [a for a in approvals if a.get('Status') == 'Pending']
    completed_approvals = [a for a in approvals if a.get('Status') in ['Approved', 'Rejected']]
    
    return templates.TemplateResponse(
        "logs/index.html",
        {
            "request": request,
            "user": current_user,
            "pending_approvals": pending_approvals,
            "completed_approvals": completed_approvals
        }
    )
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
from fastapi import APIRouter, Depends, Request, Form, UploadFile, File, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from app.database.database import get_db
from app.database.models import Profile
from app.utils.auth import get_current_user
from app.utils.photo import resize_and_convert_image, upload_to_drive
from app.utils.flash import set_flash

router = APIRouter(tags=["profile"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/profile", response_class=HTMLResponse)
async def profile_page(
    request: Request,
    current_user = Depends(get_current_user)
):
    """User profile page."""
    return templates.TemplateResponse(
        "profile/view.html",
        {
            "request": request,
            "user": current_user
        }
    )

@router.get("/profile/edit", response_class=HTMLResponse)
async def edit_profile_page(
    request: Request,
    current_user = Depends(get_current_user)
):
    """Edit user profile page."""
    return templates.TemplateResponse(
        "profile/edit.html",
        {
            "request": request,
            "user": current_user
        }
    )

@router.post("/profile/edit")
async def update_profile(
    request: Request,
    full_name: str = Form(...),
    email: str = Form(...),
    photo: UploadFile = File(None),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Update user profile."""
    # Update basic info
    current_user.full_name = full_name
    current_user.email = email
    current_user.updated_at = datetime.now(timezone.utc)
    
    # Handle photo upload if provided
    if photo and photo.filename:
        try:
            # Process image
            contents = await photo.read()
            import io
            image_file = io.BytesIO(contents)
            processed_image = resize_and_convert_image(image_file)
            
            if processed_image:
                # Upload to Google Drive
                photo_url = upload_to_drive(
                    processed_image, 
                    photo.filename, 
                    f"profile_{current_user.email}"
                )
                if photo_url:
                    current_user.photo_url = photo_url
        except Exception as e:
            return templates.TemplateResponse(
                "profile/edit.html",
                {
                    "request": request,
                    "user": current_user,
                    "error": f"Error uploading photo: {str(e)}"
                },
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    # Save changes
    db.commit()
    
    # Redirect to profile page
    response = RedirectResponse(url="/profile", status_code=status.HTTP_303_SEE_OTHER)
    set_flash(response, "Profile updated successfully", "success")
    return response
# app/routes/relocation.py
from fastapi import APIRouter, Depends, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime
import json

from app.database.database import get_db
from app.database.models import Profile
from app.utils.auth import get_current_user
from app.utils.sheets import get_all_assets, get_dropdown_options, add_approval_request
from app.utils.flash import set_flash

router = APIRouter(prefix="/relocation", tags=["relocation"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def relocation_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Asset relocation page."""
    # Get assets and dropdown options
    all_assets = get_all_assets()
    dropdown_options = get_dropdown_options()
    
    return templates.TemplateResponse(
        "relocation/index.html",
        {
            "request": request,
            "user": current_user,
            "assets": all_assets,
            "dropdown_options": dropdown_options
        }
    )

@router.post("/relocate/{asset_id}")
async def relocate_asset(
    asset_id: str,
    request: Request,
    new_location: str = Form(...),
    new_room: str = Form(...),
    reason: str = Form(...),
    notes: str = Form(None),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Submit asset relocation request."""
    from app.utils.sheets import get_asset_by_id
    
    # Get asset data
    asset = get_asset_by_id(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    # Create relocation approval request
    relocation_data = {
        'new_location': new_location,
        'new_room': new_room,
        'current_location': asset.get('Location', ''),
        'current_room': asset.get('Room', ''),
        'reason': reason,
        'notes': notes or ''
    }
    
    approval_data = {
        'type': 'relocation',
        'asset_id': asset_id,
        'asset_name': asset.get('Item Name', ''),
        'submitted_by': current_user.full_name or current_user.email,
        'submitted_date': datetime.now().strftime('%Y-%m-%d'),
        'description': f"Relocate from {asset.get('Location', '')} - {asset.get('Room', '')} to {new_location} - {new_room}",
        'request_data': json.dumps(relocation_data, ensure_ascii=False)
    }
    
    approval_success = add_approval_request(approval_data)
    
    if approval_success:
        response = RedirectResponse(url="/relocation", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, f"Relocation request for {asset.get('Item Name', '')} submitted for approval", "success")
        return response
    else:
        response = RedirectResponse(url="/relocation", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, "Error submitting relocation request", "error")
        return response
# /app/app/routes/repair.py
from fastapi import APIRouter, Request, Depends
from starlette.templating import Jinja2Templates
from app.utils.auth import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.post("/action")
async def submit_repair_action(request: Request, current_user = Depends(get_current_user)):
    """Submit repair action - creates approval request for store, direct action for allocate"""
    from app.utils.sheets import add_repair_log, update_asset, add_approval_request
    from datetime import datetime
    
    try:
        # Get JSON data
        data = await request.json()
        action_type = data.get('action_type')  # 'store' or 'allocate'
        
        if action_type == 'store':
            # Store action requires approval - only create approval request
            approval_data = {
                'type': 'repair_action',
                'asset_id': data.get('asset_id'),
                'asset_name': data.get('asset_name'),
                'submitted_by': current_user.full_name or current_user.email,
                'submitted_date': datetime.now().strftime('%Y-%m-%d'),
                'description': f"Request to store asset: {data.get('description')}",
                'action': 'Store Asset'
            }
            
            approval_success = add_approval_request(approval_data)
            
            if approval_success:
                return {"status": "success", "message": "Store request submitted for admin approval"}
            else:
                return {"status": "error", "message": "Failed to submit approval request"}
        
        else:  # allocate - direct action
            # Add to Repair_Log sheet
            repair_data = {
                'asset_id': data.get('asset_id'),
                'asset_name': data.get('asset_name'),
                'repair_action': 'Allocate Asset',
                'action_type': action_type,
                'description': data.get('description', ''),
                'performed_by': current_user.full_name or current_user.email,
                'action_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'new_location': data.get('location', ''),
                'new_room': data.get('room', ''),
                'notes': data.get('notes', '')
            }
            
            # Add to repair log
            log_success = add_repair_log(repair_data)
            
            # Update asset from Under Repair to Active
            update_data = {
                'Status': 'Active',
                'Bisnis Unit': data.get('business_unit', ''),
                'Location': data.get('location', ''),
                'Room': data.get('room', '')
            }
            
            asset_success = update_asset(data.get('asset_id'), update_data)
            
            if log_success and asset_success:
                return {"status": "success", "message": "Asset allocated successfully and synced to Google Sheets"}
            else:
                return {"status": "error", "message": "Failed to sync with Google Sheets"}
            
    except Exception as e:
        return {"status": "error", "message": str(e)}
# app/routes/user_management.py
from fastapi import APIRouter, Depends, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.database.models import Profile, UserRole
from app.utils.auth import get_current_user, get_admin_user
from app.utils.flash import set_flash

router = APIRouter(prefix="/user_management", tags=["user_management"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def user_list(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """List all users (admin only)."""
    users = db.query(Profile).all()
    
    return templates.TemplateResponse(
        "user_management/list.html",
        {
            "request": request,
            "user": current_user,
            "users": users
        }
    )

@router.get("/create", response_class=HTMLResponse)
async def create_user_form(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Create user form (admin only)."""
    return templates.TemplateResponse(
        "user_management/create.html",
        {
            "request": request,
            "user": current_user
        }
    )

@router.post("/create")
async def create_user(
    request: Request,
    email: str = Form(...),
    full_name: str = Form(...),
    role: str = Form(...),
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Create new user (admin only)."""
    # Check if user exists
    existing_user = db.query(Profile).filter(Profile.email == email).first()
    if existing_user:
        return templates.TemplateResponse(
            "user_management/create.html",
            {
                "request": request,
                "user": current_user,
                "error": "Email already exists"
            }
        )
    
    # Create user profile (Supabase handles auth)
    new_user = Profile(
        email=email,
        full_name=full_name,
        role=getattr(UserRole, role.upper()),
        is_active=True
    )
    
    db.add(new_user)
    db.commit()
    
    response = RedirectResponse(url="/user_management", status_code=status.HTTP_303_SEE_OTHER)
    set_flash(response, f"User {email} created successfully", "success")
    return response

@router.post("/reset_password/{user_id}")
async def reset_password(
    user_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Reset user password to default (admin only)."""
    user = db.query(Profile).filter(Profile.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Password reset handled by Supabase
    default_password = f"{user.email.split('@')[0]}123"
    
    response = RedirectResponse(url="/user_management", status_code=status.HTTP_303_SEE_OTHER)
    set_flash(response, f"Password reset instructions sent to {user.email}", "success")
    return response

@router.post("/toggle_status/{user_id}")
async def toggle_user_status(
    user_id: str,
    request: Request,
    is_active: bool = Form(...),
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Toggle user active status (admin only)."""
    user = db.query(Profile).filter(Profile.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Update status
    user.is_active = is_active
    db.commit()
    
    status_text = "activated" if is_active else "deactivated"
    response = RedirectResponse(url="/user_management", status_code=status.HTTP_303_SEE_OTHER)
    set_flash(response, f"User {user.email} {status_text}", "success")
    return response
# app/routes/__init__.py

# Import all route modules to make them available from app.routes
from app.routes import (
    home,
    assets,
    asset_management,
    login,
    damage,
    health,
    offline,
    profile,
    repair,
    approvals,
    disposal,
    user_management,
    logs,
    relocation
)
# app/routes/approvals.py
from fastapi import APIRouter, Depends, Request, HTTPException, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.utils.auth import get_current_user
from app.utils.sheets import get_all_approvals, update_approval_status

router = APIRouter(prefix="/approvals", tags=["approvals"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def approvals_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Approvals page for admin and manager."""
    if current_user.role not in ['admin', 'manager']:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get all approvals from Google Sheets
    all_approvals = get_all_approvals()
    
    # Filter approvals based on user role
    if current_user.role == 'admin':
        # Admin sees all approvals except disposal and edit_asset
        approvals_data = [a for a in all_approvals if a.get('Type') not in ['disposal', 'edit_asset']]
    elif current_user.role == 'manager':
        # Manager sees disposal and edit_asset approvals
        approvals_data = [a for a in all_approvals if a.get('Type') in ['disposal', 'edit_asset']]
    else:
        approvals_data = []
    
    return templates.TemplateResponse(
        "approvals/list.html",
        {
            "request": request,
            "user": current_user,
            "approvals_data": approvals_data
        }
    )

@router.post("/approve/{approval_id}")
async def approve_request(
    approval_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Approve a request."""
    if current_user.role not in ['admin', 'manager']:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get approval details
    all_approvals = get_all_approvals()
    approval = next((a for a in all_approvals if str(a.get('ID')) == str(approval_id)), None)
    
    if not approval:
        return JSONResponse({"status": "error", "message": "Approval not found"})
    
    # Process approval based on type
    try:
        if approval.get('Type') == 'damage_report':
            # Update asset status to "Under Repair"
            from app.utils.sheets import update_asset
            success = update_asset(approval.get('Asset_ID'), {'Status': 'Under Repair'})
            if not success:
                return JSONResponse({"status": "error", "message": "Failed to update asset status"})
        
        elif approval.get('Type') == 'relocation':
            # Process relocation approval
            import json
            try:
                request_data_str = approval.get('Request_Data', '')
                if request_data_str:
                    relocation_data = json.loads(request_data_str)
                    update_data = {
                        'Location': relocation_data.get('new_location'),
                        'Room': relocation_data.get('new_room')
                    }
                    from app.utils.sheets import update_asset
                    success = update_asset(approval.get('Asset_ID'), update_data)
                    if not success:
                        return JSONResponse({"status": "error", "message": "Failed to relocate asset"})
            except Exception as e:
                return JSONResponse({"status": "error", "message": f"Error processing relocation: {str(e)}"})
            
        elif approval.get('Type') == 'edit_asset':
            # Process edit asset approval
            import json
            try:
                request_data_str = approval.get('Request_Data', '')
                if request_data_str:
                    edit_data = json.loads(request_data_str)
                    from app.utils.sheets import update_asset
                    success = update_asset(approval.get('Asset_ID'), edit_data)
                    if not success:
                        return JSONResponse({"status": "error", "message": "Failed to update asset"})
            except Exception as e:
                return JSONResponse({"status": "error", "message": f"Error processing edit: {str(e)}"})
        
        # Update approval status
        approval_update = {
            'Status': 'Approved',
            'Approved_By': current_user.full_name or current_user.email,
            'Approved_Date': __import__('datetime').datetime.now().strftime('%Y-%m-%d')
        }
        
        success = update_approval_status(approval_id, approval_update)
        
        if success:
            return JSONResponse({"status": "success", "message": "Request approved successfully"})
        else:
            return JSONResponse({"status": "error", "message": "Failed to update approval status"})
            
    except Exception as e:
        return JSONResponse({"status": "error", "message": f"Error processing approval: {str(e)}"})

@router.post("/reject/{approval_id}")
async def reject_request(
    approval_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Reject a request."""
    if current_user.role not in ['admin', 'manager']:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Update approval status
    approval_update = {
        'Status': 'Rejected',
        'Approved_By': current_user.full_name or current_user.email,
        'Approved_Date': __import__('datetime').datetime.now().strftime('%Y-%m-%d')
    }
    
    success = update_approval_status(approval_id, approval_update)
    
    if success:
        return JSONResponse({"status": "success", "message": "Request rejected"})
    else:
        return JSONResponse({"status": "error", "message": "Failed to update approval status"})
from fastapi import APIRouter, Request, Depends
from starlette.templating import Jinja2Templates
from app.utils.auth import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/assets")
async def assets_page(request: Request, current_user=Depends(get_current_user)):
    """Assets listing page with filtering and pagination"""
    from app.utils.sheets import get_all_assets
    
    # Ambil data asset dari Google Sheets
    all_assets = get_all_assets()
    
    # Filter hanya aset aktif (bukan Disposed)
    active_assets = [asset for asset in all_assets if asset.get("Status", "").lower() != "disposed"]
    
    return templates.TemplateResponse("assets.html", {
        "request": request,
        "user": current_user,
        "assets_data": active_assets
    })
# app/routes/asset_management.py
from fastapi import APIRouter, Depends, Request, Form, File, UploadFile, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import json
from datetime import datetime
import io

from app.database.database import get_db
from app.database.models import Profile, UserRole
from app.utils.photo import resize_and_convert_image, upload_to_drive
from app.utils.sheets import get_dropdown_options, add_asset as sheets_add_asset
from app.utils.flash import set_flash
from app.utils.auth import get_current_user, get_admin_user
from app.config import load_config

config = load_config()
router = APIRouter(prefix="/asset_management", tags=["asset_management"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/add", response_class=HTMLResponse)
async def add_asset_form(
    request: Request,
    db: Session = Depends(get_db),
    current_profile = Depends(get_current_user)
):
    """Form to add a new asset."""
    dropdown_options = get_dropdown_options()
    return templates.TemplateResponse(
        "asset_management/add.html",
        {
            "request": request,
            "user": current_profile,
            "dropdown_options": dropdown_options
        }
    )


@router.get("/list", response_class=HTMLResponse)
async def asset_list(
    request: Request,
    db: Session = Depends(get_db),
    current_profile = Depends(get_current_user)
):
    """List assets for editing (admin and manager only)."""
    if current_profile.role not in [UserRole.ADMIN, UserRole.MANAGER]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    from app.utils.sheets import get_all_assets
    assets = get_all_assets()
    
    locations = list(set(asset.get('Location', '') for asset in assets if asset.get('Location')))
    location_rooms = {}
    for asset in assets:
        location = asset.get('Location', '')
        room = asset.get('Room', '')
        if location and room:
            if location not in location_rooms:
                location_rooms[location] = set()
            location_rooms[location].add(room)
    
    for location in location_rooms:
        location_rooms[location] = list(location_rooms[location])
    
    return templates.TemplateResponse(
        "asset_management/list.html",
        {
            "request": request,
            "user": current_profile,
            "assets": assets,
            "locations": sorted(locations),
            "location_rooms": location_rooms
        }
    )


@router.get("/edit/{asset_id}", response_class=HTMLResponse)
async def edit_asset_form(
    asset_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_profile = Depends(get_current_user)
):
    """Form to edit an existing asset (admin/manager only)."""
    if current_profile.role not in [UserRole.ADMIN, UserRole.MANAGER]:
        raise HTTPException(status_code=403, detail="Access denied")

    from app.utils.sheets import get_asset_by_id
    asset = get_asset_by_id(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    dropdown_options = get_dropdown_options()
    
    return templates.TemplateResponse(
        "asset_management/edit.html",
        {
            "request": request,
            "user": current_profile,
            "asset": asset,
            "dropdown_options": dropdown_options
        }
    )


@router.post("/edit/{asset_id}")
async def update_asset(
    asset_id: str,
    request: Request,
    status: str = Form(...),
    company: str = Form(...),
    location: str = Form(...),
    room: str = Form(...),
    bisnis_unit: str = Form(None),
    edit_reason: str = Form(...),
    db: Session = Depends(get_db),
    current_profile = Depends(get_current_user)
):
    """Update existing asset (admin and manager only)."""
    if current_profile.role not in [UserRole.ADMIN, UserRole.MANAGER]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    from app.utils.sheets import update_asset as sheets_update_asset, calculate_asset_financials, get_asset_by_id
    asset = get_asset_by_id(asset_id)

    update_data = {
        "Status": status,
        "Company": company,
        "Location": location,
        "Room": room,
        "Bisnis Unit": bisnis_unit or ""
    }
    
    # Jika perlu hitung ulang nilai finansial, misalnya setelah perubahan harga
    # financials = calculate_asset_financials(purchase_cost, purchase_date, category)
    # update_data.update(financials)
    
    from app.utils.sheets import add_approval_request
    
    approval_data = {
        'type': 'edit_asset',
        'asset_id': asset_id,
        'asset_name': asset.get('Item Name', ''),
        'submitted_by': current_profile.full_name or current_profile.email,
        'submitted_date': datetime.now().strftime('%Y-%m-%d'),
        'description': f"Edit asset: {asset.get('Item Name', '')} - Reason: {edit_reason}",
        'edit_reason': edit_reason,
        'request_data': json.dumps(update_data, ensure_ascii=False)
    }
    
    approval_success = add_approval_request(approval_data)
    
    if approval_success:
        response = RedirectResponse(url="/asset_management/list", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, "Asset edit request submitted for manager approval", "success")
        return response
    else:
        dropdown_options = get_dropdown_options()
        return templates.TemplateResponse(
            "asset_management/edit.html",
            {
                "request": request,
                "user": current_profile,
                "asset": asset,
                "dropdown_options": dropdown_options,
                "error": "Error submitting edit request"
            },
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@router.post("/add")
async def add_asset(
    request: Request,
    item_name: str = Form(...),
    category: str = Form(...),
    type: str = Form(...),
    manufacture: str = Form(None),
    model: str = Form(None),
    serial_number: str = Form(None),
    company: str = Form(...),
    bisnis_unit: str = Form(None),
    location: str = Form(...),
    room: str = Form(...),
    notes: str = Form(None),
    item_condition: str = Form(None),
    purchase_date: str = Form(...),
    purchase_cost: str = Form(...),
    warranty: str = Form(None),
    supplier: str = Form(None),
    journal: str = Form(None),
    owner: str = Form(...),
    photo: UploadFile = File(None),
    db: Session = Depends(get_db),
    current_profile = Depends(get_current_user)
):
    """Process add asset form."""
    dropdown_options = get_dropdown_options()
    
    asset_data = {
        "Item Name": item_name,
        "Category": category,
        "Type": type,
        "Manufacture": manufacture or "",
        "Model": model or "",
        "Serial Number": serial_number or "",
        "Company": company,
        "Bisnis Unit": bisnis_unit or "",
        "Location": location,
        "Room": room,
        "Notes": notes or "",
        "Item Condition": item_condition or "",
        "Purchase Date": purchase_date,
        "Purchase Cost": purchase_cost,
        "Warranty": warranty or "",
        "Supplier": supplier or "",
        "Journal": journal or "",
        "Owner": owner,
        "Status": "Active"
    }
    
    photo_url = None
    if photo and photo.filename:
        try:
            contents = await photo.read()
            image_file = io.BytesIO(contents)
            processed_image = resize_and_convert_image(image_file)
            
            if processed_image:
                photo_url = upload_to_drive(processed_image, photo.filename, "new")
                if photo_url:
                    asset_data["Photo URL"] = photo_url
        except Exception as e:
            print(f"Error processing photo: {str(e)}")
    
    if current_profile.role == UserRole.ADMIN:
        success = sheets_add_asset(asset_data)
        
        if success:
            response = RedirectResponse(url="/assets/", status_code=status.HTTP_303_SEE_OTHER)
            set_flash(response, "Asset added successfully", "success")
            return response
        else:
            return templates.TemplateResponse(
                "asset_management/add.html",
                {
                    "request": request,
                    "user": current_profile,
                    "dropdown_options": dropdown_options,
                    "error": "Error adding asset to Google Sheets",
                    "form_data": asset_data
                },
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    from app.utils.sheets import add_approval_request
    
    approval_data = {
        'type': 'add_asset',
        'asset_id': 'NEW',
        'asset_name': item_name,
        'submitted_by': current_profile.full_name or current_profile.email,
        'submitted_date': datetime.now().strftime('%Y-%m-%d'),
        'description': f"Add new asset: {item_name}",
        'request_data': json.dumps(asset_data, ensure_ascii=False)
    }
    
    approval_success = add_approval_request(approval_data)
    
    if approval_success:
        response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, "Asset request submitted for approval", "success")
        return response
    else:
        return templates.TemplateResponse(
            "asset_management/add.html",
            {
                "request": request,
                "user": current_profile,
                "dropdown_options": dropdown_options,
                "error": "Error submitting approval request",
                "form_data": asset_data
            },
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
from fastapi import APIRouter, Request, Depends
from starlette.templating import Jinja2Templates
from app.utils.auth import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/")
async def damaged_assets_page(request: Request, current_user = Depends(get_current_user)):
    """Damaged assets page with search and log functionality"""
    from app.utils.sheets import get_all_assets, get_dropdown_options

    all_assets = get_all_assets()
    dropdown_options = get_dropdown_options()

    return templates.TemplateResponse("damaged_assets.html", {
        "request": request,
        "user": current_user,
        "assets_data": all_assets,
        "dropdown_options": dropdown_options
    })


@router.post("/lost")
async def submit_lost_report(request: Request, current_user = Depends(get_current_user)):
    """Submit lost report - syncs to Google Sheets"""
    from app.utils.sheets import add_lost_log, add_approval_request
    from datetime import datetime

    try:
        data = await request.json()

        lost_data = {
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'last_location': data.get('last_location'),
            'last_room': data.get('last_room', ''),
            'date_lost': data.get('date_lost'),
            'description': data.get('description'),
            'reported_by': current_user.full_name or current_user.email,
            'report_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'notes': data.get('notes', '')
        }

        log_success = add_lost_log(lost_data)

        approval_data = {
            'type': 'lost_report',
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'submitted_by': current_user.full_name or current_user.email,
            'submitted_date': datetime.now().strftime('%Y-%m-%d'),
            'description': f"Lost report: {data.get('description')}",
            'location': data.get('last_location')
        }

        approval_success = add_approval_request(approval_data)

        if log_success and approval_success:
            return {"status": "success", "message": "Lost report submitted and logged to Google Sheets"}
        else:
            return {"status": "error", "message": "Failed to sync with Google Sheets"}

    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/disposal")
async def submit_disposal_request(request: Request, current_user = Depends(get_current_user)):
    """Submit disposal request - syncs to Google Sheets"""
    from app.utils.sheets import add_disposal_log, add_approval_request
    from datetime import datetime

    try:
        data = await request.json()

        disposal_data = {
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'disposal_reason': data.get('disposal_reason'),
            'disposal_method': data.get('disposal_method', 'Standard'),
            'description': data.get('description'),
            'requested_by': current_user.full_name or current_user.email,
            'request_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'notes': data.get('notes', '')
        }

        log_success = add_disposal_log(disposal_data)

        approval_data = {
            'type': 'disposal_request',
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'submitted_by': current_user.full_name or current_user.email,
            'submitted_date': datetime.now().strftime('%Y-%m-%d'),
            'description': f"Disposal request: {data.get('description')}"
        }

        approval_success = add_approval_request(approval_data)

        if log_success and approval_success:
            return {"status": "success", "message": "Disposal request submitted and logged to Google Sheets"}
        else:
            return {"status": "error", "message": "Failed to sync with Google Sheets"}

    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/report")
async def submit_damage_report(request: Request, current_user = Depends(get_current_user)):
    """Submit damage report - syncs to Google Sheets"""
    from app.utils.sheets import add_damage_log, add_approval_request
    from datetime import datetime

    try:
        data = await request.json()

        damage_data = {
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'damage_type': data.get('damage_type'),
            'severity': data.get('severity'),
            'description': data.get('damage_description'),
            'reported_by': current_user.full_name or current_user.email,
            'report_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'location': data.get('location', ''),
            'room': data.get('room', ''),
            'notes': data.get('notes', '')
        }

        approval_data = {
            'type': 'damage_report',
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'submitted_by': current_user.full_name or current_user.email,
            'submitted_date': datetime.now().strftime('%Y-%m-%d'),
            'description': f"Damage report: {data.get('damage_description')}",
            'damage_type': data.get('damage_type'),
            'severity': data.get('severity')
        }

        approval_success = add_approval_request(approval_data)

        if approval_success:
            return {"status": "success", "message": "Damage report submitted for approval"}
        else:
            return {"status": "error", "message": "Failed to submit approval request"}

    except Exception as e:
        return {"status": "error", "message": str(e)}
# app/routes/disposal.py
from fastapi import APIRouter, Depends, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime

from app.database.database import get_db
from app.database.models import Profile
from app.utils.auth import get_admin_user
from app.utils.sheets import get_all_assets, update_asset, add_disposal_log
from app.utils.flash import set_flash

router = APIRouter(prefix="/disposal", tags=["disposal"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def disposal_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Disposal assets page (admin only)."""
    # Get assets that are ready to dispose only
    all_assets = get_all_assets()
    # Debug: check all statuses
    statuses = [str(asset.get('Status', '')).strip() for asset in all_assets]
    print(f"All statuses found: {set(statuses)}")
    
    disposable_assets = []
    for asset in all_assets:
        status = str(asset.get('Status', '')).strip()
        if status in ['To Be Disposed', 'To be Disposed', 'TO BE DISPOSED']:
            disposable_assets.append(asset)
    
    return templates.TemplateResponse(
        "disposal/index.html",
        {
            "request": request,
            "user": current_user,
            "assets": disposable_assets
        }
    )

@router.post("/dispose/{asset_id}")
async def dispose_asset(
    asset_id: str,
    request: Request,
    disposal_reason: str = Form(...),
    disposal_method: str = Form(...),
    description: str = Form(None),
    notes: str = Form(None),
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Dispose an asset (admin only)."""
    from app.utils.sheets import get_asset_by_id
    
    # Get asset data
    asset = get_asset_by_id(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    if str(asset.get('Status', '')).strip() != 'To Be Disposed':
        raise HTTPException(status_code=400, detail="Asset must be marked 'To Be Disposed' first")
    
    # Create disposal approval request
    from app.utils.sheets import add_approval_request
    
    approval_data = {
        'type': 'disposal',
        'asset_id': asset_id,
        'asset_name': asset.get('Item Name', ''),
        'submitted_by': current_user.full_name or current_user.email,
        'submitted_date': datetime.now().strftime('%Y-%m-%d'),
        'description': f"Disposal request: {disposal_reason} - {disposal_method}",
        'disposal_reason': disposal_reason,
        'disposal_method': disposal_method,
        'notes': f"Description: {description or ''} | Notes: {notes or ''}"
    }
    
    approval_success = add_approval_request(approval_data)
    
    if approval_success:
        response = RedirectResponse(url="/disposal", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, f"Disposal request for {asset.get('Item Name', '')} submitted for manager approval", "success")
        return response
    else:
        response = RedirectResponse(url="/disposal", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, "Error submitting disposal request", "error")
        return response
# app/routes/health.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
import time

from app.database.database import get_db
from app.config import load_config

router = APIRouter(tags=["health"])
config = load_config()

@router.get("/health")
async def health_check(db: Session = Depends(get_db)):
    """Health check endpoint."""
    start_time = time.time()
    
    # Check database connection
    try:
        db.execute(text("SELECT 1"))
        db_status = "healthy"
    except Exception as e:
        db_status = f"unhealthy: {str(e)}"
    
    # Check Google Sheets API
    sheets_status = "configured" if config.GOOGLE_SHEET_ID else "not configured"
    
    # Response time
    response_time = time.time() - start_time
    
    return {
        "status": "ok",
        "database": db_status,
        "google_sheets": sheets_status,
        "response_time_ms": round(response_time * 1000, 2)
    }
# /app/app/routes/home.py
import logging
from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse
from starlette.templating import Jinja2Templates
from app.utils.auth import get_current_user
from app.utils.sheets import get_summary_data, get_chart_data, get_all_assets

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=RedirectResponse)
async def redirect_root():
    return RedirectResponse("/dashboard")

@router.get("/dashboard")
async def home(request: Request, current_user = Depends(get_current_user)):
    try:
        # Summary and chart data
        summary_data = get_summary_data()
        chart_data = get_chart_data()
        all_assets = get_all_assets()

        # Filter out disposed assets for dashboard counts
        active_assets = [asset for asset in all_assets if asset.get("Status", "") != "Disposed"]
        disposed_assets = [asset for asset in all_assets if asset.get("Status", "") == "Disposed"]
        
        # Count assets by status and activity
        total_assets = len(active_assets)
        disposed_count = len(disposed_assets)
        damaged_count = len([a for a in all_assets if a.get("Status", "") == "Under Repair"])
        
        # Count assets by activity type
        relocated_count = len([a for a in all_assets if a.get("Last Activity", "") == "Relocated"])
        repaired_count = len([a for a in all_assets if a.get("Last Activity", "") == "Repaired"])
        to_be_disposed_count = len([a for a in all_assets if a.get("Status", "") == "To Be Disposed"])
        
        # Helper function to safely convert values to float
        def safe_float(value):
            if value is None or value == '':
                return 0.0
            try:
                return float(value)
            except (ValueError, TypeError):
                return 0.0
        
        # Calculate financial values directly from assets
        total_purchase_value = sum(safe_float(asset.get("Purchase Cost")) for asset in active_assets)
        total_book_value = sum(safe_float(asset.get("Book Value")) for asset in active_assets)
        # Calculate depreciation as purchase value minus book value
        total_depreciation_value = total_purchase_value - total_book_value
        category_counts = chart_data.get("category_counts", {})
        
        # Format location data
        location_data = chart_data.get("location_chart_data", {})
        location_counts = location_data.get("labels", [])
        location_values = location_data.get("values", [])
        location_counts_dict = dict(zip(location_counts, location_values))

        # Format time-based chart data
        monthly_data = chart_data.get("monthly_chart_data", {})
        monthly_chart_labels = monthly_data.get("labels", [])
        monthly_chart_values = monthly_data.get("values", [])
        
        # Generate quarterly data (last 12 quarters - 3 years)
        quarterly_chart_labels = []
        quarterly_chart_values = []
        
        # Get current year and quarter
        from datetime import datetime
        current_date = datetime.now()
        current_year = current_date.year
        current_quarter = (current_date.month - 1) // 3 + 1
        
        # Generate data for the last 12 quarters
        for i in range(11, -1, -1):
            year = current_year
            quarter = current_quarter - i
            
            # Adjust year if quarter is negative or > 4
            while quarter <= 0:
                year -= 1
                quarter += 4
            while quarter > 4:
                year += 1
                quarter -= 4
                
            quarterly_chart_labels.append(f"Q{quarter} {year}")
            
            # Count assets added in this quarter
            quarter_start_month = (quarter - 1) * 3 + 1
            quarter_end_month = quarter * 3
            
            count = 0
            for asset in all_assets:
                purchase_date = asset.get("Purchase Date", "")
                if purchase_date:
                    try:
                        date = datetime.strptime(purchase_date, "%Y-%m-%d")
                        if date.year == year and quarter_start_month <= date.month <= quarter_end_month:
                            count += 1
                    except:
                        pass
            
            quarterly_chart_values.append(count)
        
        # Generate yearly data (last 5 years)
        yearly_chart_labels = []
        yearly_chart_values = []
        
        # Generate data for the last 5 years
        for i in range(4, -1, -1):
            year = current_year - i
            yearly_chart_labels.append(str(year))
            
            # Count assets added in this year
            count = 0
            for asset in all_assets:
                purchase_date = asset.get("Purchase Date", "")
                if purchase_date:
                    try:
                        date = datetime.strptime(purchase_date, "%Y-%m-%d")
                        if date.year == year:
                            count += 1
                    except:
                        pass
            
            yearly_chart_values.append(count)

        # Format age distribution - convert to list of tuples for proper serialization
        age_distribution = chart_data.get("age_distribution", {})
        age_distribution_list = [
            {"label": str(k), "value": int(v)} 
            for k, v in age_distribution.items()
        ]

        # Format latest assets (excluding disposed assets)
        latest_assets = sorted(
            active_assets, 
            key=lambda a: a.get("Purchase Date", ""), 
            reverse=True
        )[:10]
        
        # Process assets to ensure they have a display_name field
        for asset in latest_assets:
            # Try different possible field names for the asset name
            name_fields = ["Name", "Asset Name", "AssetName", "Item Name", "Description", "Item"]
            display_name = None
            
            for field in name_fields:
                if asset.get(field):
                    display_name = asset.get(field)
                    break
            
            # If no name found, use a default
            if not display_name:
                display_name = f"Asset #{asset.get('ID', 'Unknown')}"
                
            # Add the display_name to the asset
            asset["display_name"] = display_name
            
        # Debug: Print the first asset's keys to see what fields are available
        if latest_assets:
            logging.info(f"Asset keys: {list(latest_assets[0].keys())}")
            logging.info(f"Asset display name: {latest_assets[0].get('display_name', 'Not found')}")
            logging.info(f"Original asset name fields: {[latest_assets[0].get(f, 'None') for f in name_fields]}")

        context = {
            "request": request,
            "user": current_user,
            "total_assets": total_assets,
            "total_purchase_value": total_purchase_value,
            "total_book_value": total_book_value,
            "total_depreciation_value": total_depreciation_value,
            "disposed_count": disposed_count,
            "damaged_count": damaged_count,
            "relocated_count": relocated_count,
            "repaired_count": repaired_count,
            "to_be_disposed_count": to_be_disposed_count,
            "category_counts": category_counts,
            "location_counts": location_counts_dict,
            "monthly_chart_labels": monthly_chart_labels,
            "monthly_chart_values": monthly_chart_values,
            "quarterly_chart_labels": quarterly_chart_labels,
            "quarterly_chart_values": quarterly_chart_values,
            "yearly_chart_labels": yearly_chart_labels,
            "yearly_chart_values": yearly_chart_values,
            "age_distribution": age_distribution_list,
            "latest_assets": latest_assets
        }

        return templates.TemplateResponse("dashboard.html", context)

    except Exception as e:
        logging.error("Dashboard error: %s", e, exc_info=True)
        return templates.TemplateResponse("error.html", {
            "request": request,
            "user": current_user,
            "message": "Terjadi kesalahan saat memuat dashboard.",
        })
from fastapi import APIRouter, Request, Response, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from supabase import create_client, Client
from app.config import load_config
import logging

config = load_config()
supabase: Client = create_client(config.SUPABASE_URL, config.SUPABASE_ANON_KEY)

router = APIRouter(tags=["authentication"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/login", response_class=HTMLResponse)
@router.head("/login", response_class=HTMLResponse)
async def login_page(request: Request, next: str = None):
    return templates.TemplateResponse("login_logout.html", {"request": request, "next": next})

@router.post("/login", response_class=HTMLResponse)
async def login_form(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    next: str = Form(None)
):
    try:
        # Use service key client for admin operations
        from supabase import create_client
        admin_supabase = create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_KEY)
        
        response = admin_supabase.auth.sign_in_with_password({
            "email": email,
            "password": password
        })
        
        if not response.user:
            return templates.TemplateResponse(
                "login_logout.html",
                {"request": request, "error": "Invalid email or password", "next": next},
                status_code=401
            )
        
        # Get user profile
        profile_response = admin_supabase.table('profiles').select('*').eq('id', response.user.id).single().execute()
        if not profile_response.data or not profile_response.data.get('is_active'):
            return templates.TemplateResponse(
                "login_logout.html",
                {"request": request, "error": "Account is inactive", "next": next},
                status_code=401
            )
        
        redirect_url = next if next else "/"
        redirect_response = RedirectResponse(url=redirect_url, status_code=303)
        
        redirect_response.set_cookie(
            key="sb_access_token",
            value=response.session.access_token,
            httponly=True,
            max_age=3600,
            samesite="lax",
            secure=True,
            domain=".onrender.com"
        )
        
        return redirect_response
        
    except Exception as e:
        logging.error(f"Login error: {str(e)}")
        return templates.TemplateResponse(
            "login_logout.html",
            {"request": request, "error": "Login failed", "next": next},
            status_code=401
        )

@router.get("/auth/callback")
async def auth_callback(request: Request):
    return templates.TemplateResponse("auth_callback.html", {"request": request})

@router.get("/logout")
async def logout():
    try:
        supabase.auth.sign_out()
    except:
        pass
    
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(key="sb_access_token")
    return response
# app/routes/logs.py
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.database.models import Profile
from app.utils.auth import get_current_user
from app.utils.sheets import get_all_approvals

router = APIRouter(prefix="/logs", tags=["logs"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def logs_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """View approval logs based on user role."""
    all_approvals = get_all_approvals()
    
    # Filter based on user role
    if current_user.role.value == 'staff':
        # Staff can only see their own requests
        user_identifier = current_user.full_name or current_user.email
        approvals = [a for a in all_approvals if a.get('Submitted_By') == user_identifier]
    else:
        # Manager and admin can see all approvals
        approvals = all_approvals
    
    # Separate pending and completed
    pending_approvals = [a for a in approvals if a.get('Status') == 'Pending']
    completed_approvals = [a for a in approvals if a.get('Status') in ['Approved', 'Rejected']]
    
    return templates.TemplateResponse(
        "logs/index.html",
        {
            "request": request,
            "user": current_user,
            "pending_approvals": pending_approvals,
            "completed_approvals": completed_approvals
        }
    )
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
from fastapi import APIRouter, Depends, Request, Form, UploadFile, File, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from app.database.database import get_db
from app.database.models import Profile
from app.utils.auth import get_current_user
from app.utils.photo import resize_and_convert_image, upload_to_drive
from app.utils.flash import set_flash

router = APIRouter(tags=["profile"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/profile", response_class=HTMLResponse)
async def profile_page(
    request: Request,
    current_user = Depends(get_current_user)
):
    """User profile page."""
    return templates.TemplateResponse(
        "profile/view.html",
        {
            "request": request,
            "user": current_user
        }
    )

@router.get("/profile/edit", response_class=HTMLResponse)
async def edit_profile_page(
    request: Request,
    current_user = Depends(get_current_user)
):
    """Edit user profile page."""
    return templates.TemplateResponse(
        "profile/edit.html",
        {
            "request": request,
            "user": current_user
        }
    )

@router.post("/profile/edit")
async def update_profile(
    request: Request,
    full_name: str = Form(...),
    email: str = Form(...),
    photo: UploadFile = File(None),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Update user profile."""
    # Update basic info
    current_user.full_name = full_name
    current_user.email = email
    current_user.updated_at = datetime.now(timezone.utc)
    
    # Handle photo upload if provided
    if photo and photo.filename:
        try:
            # Process image
            contents = await photo.read()
            import io
            image_file = io.BytesIO(contents)
            processed_image = resize_and_convert_image(image_file)
            
            if processed_image:
                # Upload to Google Drive
                photo_url = upload_to_drive(
                    processed_image, 
                    photo.filename, 
                    f"profile_{current_user.email}"
                )
                if photo_url:
                    current_user.photo_url = photo_url
        except Exception as e:
            return templates.TemplateResponse(
                "profile/edit.html",
                {
                    "request": request,
                    "user": current_user,
                    "error": f"Error uploading photo: {str(e)}"
                },
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    # Save changes
    db.commit()
    
    # Redirect to profile page
    response = RedirectResponse(url="/profile", status_code=status.HTTP_303_SEE_OTHER)
    set_flash(response, "Profile updated successfully", "success")
    return response
# app/routes/relocation.py
from fastapi import APIRouter, Depends, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime
import json

from app.database.database import get_db
from app.database.models import Profile
from app.utils.auth import get_current_user
from app.utils.sheets import get_all_assets, get_dropdown_options, add_approval_request
from app.utils.flash import set_flash

router = APIRouter(prefix="/relocation", tags=["relocation"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def relocation_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Asset relocation page."""
    # Get assets and dropdown options
    all_assets = get_all_assets()
    dropdown_options = get_dropdown_options()
    
    return templates.TemplateResponse(
        "relocation/index.html",
        {
            "request": request,
            "user": current_user,
            "assets": all_assets,
            "dropdown_options": dropdown_options
        }
    )

@router.post("/relocate/{asset_id}")
async def relocate_asset(
    asset_id: str,
    request: Request,
    new_location: str = Form(...),
    new_room: str = Form(...),
    reason: str = Form(...),
    notes: str = Form(None),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Submit asset relocation request."""
    from app.utils.sheets import get_asset_by_id
    
    # Get asset data
    asset = get_asset_by_id(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    # Create relocation approval request
    relocation_data = {
        'new_location': new_location,
        'new_room': new_room,
        'current_location': asset.get('Location', ''),
        'current_room': asset.get('Room', ''),
        'reason': reason,
        'notes': notes or ''
    }
    
    approval_data = {
        'type': 'relocation',
        'asset_id': asset_id,
        'asset_name': asset.get('Item Name', ''),
        'submitted_by': current_user.full_name or current_user.email,
        'submitted_date': datetime.now().strftime('%Y-%m-%d'),
        'description': f"Relocate from {asset.get('Location', '')} - {asset.get('Room', '')} to {new_location} - {new_room}",
        'request_data': json.dumps(relocation_data, ensure_ascii=False)
    }
    
    approval_success = add_approval_request(approval_data)
    
    if approval_success:
        response = RedirectResponse(url="/relocation", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, f"Relocation request for {asset.get('Item Name', '')} submitted for approval", "success")
        return response
    else:
        response = RedirectResponse(url="/relocation", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, "Error submitting relocation request", "error")
        return response
# /app/app/routes/repair.py
from fastapi import APIRouter, Request, Depends
from starlette.templating import Jinja2Templates
from app.utils.auth import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.post("/action")
async def submit_repair_action(request: Request, current_user = Depends(get_current_user)):
    """Submit repair action - creates approval request for store, direct action for allocate"""
    from app.utils.sheets import add_repair_log, update_asset, add_approval_request
    from datetime import datetime
    
    try:
        # Get JSON data
        data = await request.json()
        action_type = data.get('action_type')  # 'store' or 'allocate'
        
        if action_type == 'store':
            # Store action requires approval - only create approval request
            approval_data = {
                'type': 'repair_action',
                'asset_id': data.get('asset_id'),
                'asset_name': data.get('asset_name'),
                'submitted_by': current_user.full_name or current_user.email,
                'submitted_date': datetime.now().strftime('%Y-%m-%d'),
                'description': f"Request to store asset: {data.get('description')}",
                'action': 'Store Asset'
            }
            
            approval_success = add_approval_request(approval_data)
            
            if approval_success:
                return {"status": "success", "message": "Store request submitted for admin approval"}
            else:
                return {"status": "error", "message": "Failed to submit approval request"}
        
        else:  # allocate - direct action
            # Add to Repair_Log sheet
            repair_data = {
                'asset_id': data.get('asset_id'),
                'asset_name': data.get('asset_name'),
                'repair_action': 'Allocate Asset',
                'action_type': action_type,
                'description': data.get('description', ''),
                'performed_by': current_user.full_name or current_user.email,
                'action_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'new_location': data.get('location', ''),
                'new_room': data.get('room', ''),
                'notes': data.get('notes', '')
            }
            
            # Add to repair log
            log_success = add_repair_log(repair_data)
            
            # Update asset from Under Repair to Active
            update_data = {
                'Status': 'Active',
                'Bisnis Unit': data.get('business_unit', ''),
                'Location': data.get('location', ''),
                'Room': data.get('room', '')
            }
            
            asset_success = update_asset(data.get('asset_id'), update_data)
            
            if log_success and asset_success:
                return {"status": "success", "message": "Asset allocated successfully and synced to Google Sheets"}
            else:
                return {"status": "error", "message": "Failed to sync with Google Sheets"}
            
    except Exception as e:
        return {"status": "error", "message": str(e)}
# app/routes/user_management.py
from fastapi import APIRouter, Depends, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.database.models import Profile, UserRole
from app.utils.auth import get_current_user, get_admin_user
from app.utils.flash import set_flash

router = APIRouter(prefix="/user_management", tags=["user_management"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def user_list(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """List all users (admin only)."""
    users = db.query(Profile).all()
    
    return templates.TemplateResponse(
        "user_management/list.html",
        {
            "request": request,
            "user": current_user,
            "users": users
        }
    )

@router.get("/create", response_class=HTMLResponse)
async def create_user_form(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Create user form (admin only)."""
    return templates.TemplateResponse(
        "user_management/create.html",
        {
            "request": request,
            "user": current_user
        }
    )

@router.post("/create")
async def create_user(
    request: Request,
    email: str = Form(...),
    full_name: str = Form(...),
    role: str = Form(...),
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Create new user (admin only)."""
    # Check if user exists
    existing_user = db.query(Profile).filter(Profile.email == email).first()
    if existing_user:
        return templates.TemplateResponse(
            "user_management/create.html",
            {
                "request": request,
                "user": current_user,
                "error": "Email already exists"
            }
        )
    
    # Create user profile (Supabase handles auth)
    new_user = Profile(
        email=email,
        full_name=full_name,
        role=getattr(UserRole, role.upper()),
        is_active=True
    )
    
    db.add(new_user)
    db.commit()
    
    response = RedirectResponse(url="/user_management", status_code=status.HTTP_303_SEE_OTHER)
    set_flash(response, f"User {email} created successfully", "success")
    return response

@router.post("/reset_password/{user_id}")
async def reset_password(
    user_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Reset user password to default (admin only)."""
    user = db.query(Profile).filter(Profile.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Password reset handled by Supabase
    default_password = f"{user.email.split('@')[0]}123"
    
    response = RedirectResponse(url="/user_management", status_code=status.HTTP_303_SEE_OTHER)
    set_flash(response, f"Password reset instructions sent to {user.email}", "success")
    return response

@router.post("/toggle_status/{user_id}")
async def toggle_user_status(
    user_id: str,
    request: Request,
    is_active: bool = Form(...),
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Toggle user active status (admin only)."""
    user = db.query(Profile).filter(Profile.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Update status
    user.is_active = is_active
    db.commit()
    
    status_text = "activated" if is_active else "deactivated"
    response = RedirectResponse(url="/user_management", status_code=status.HTTP_303_SEE_OTHER)
    set_flash(response, f"User {user.email} {status_text}", "success")
    return response
# app/routes/__init__.py

# Import all route modules to make them available from app.routes
from app.routes import (
    home,
    assets,
    asset_management,
    login,
    damage,
    health,
    offline,
    profile,
    repair,
    approvals,
    disposal,
    user_management,
    logs,
    relocation
)
# app/routes/approvals.py
from fastapi import APIRouter, Depends, Request, HTTPException, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.utils.auth import get_current_user
from app.utils.sheets import get_all_approvals, update_approval_status

router = APIRouter(prefix="/approvals", tags=["approvals"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def approvals_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Approvals page for admin and manager."""
    if current_user.role not in ['admin', 'manager']:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get all approvals from Google Sheets
    all_approvals = get_all_approvals()
    
    # Filter approvals based on user role
    if current_user.role == 'admin':
        # Admin sees all approvals except disposal and edit_asset
        approvals_data = [a for a in all_approvals if a.get('Type') not in ['disposal', 'edit_asset']]
    elif current_user.role == 'manager':
        # Manager sees disposal and edit_asset approvals
        approvals_data = [a for a in all_approvals if a.get('Type') in ['disposal', 'edit_asset']]
    else:
        approvals_data = []
    
    return templates.TemplateResponse(
        "approvals/list.html",
        {
            "request": request,
            "user": current_user,
            "approvals_data": approvals_data
        }
    )

@router.post("/approve/{approval_id}")
async def approve_request(
    approval_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Approve a request."""
    if current_user.role not in ['admin', 'manager']:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get approval details
    all_approvals = get_all_approvals()
    approval = next((a for a in all_approvals if str(a.get('ID')) == str(approval_id)), None)
    
    if not approval:
        return JSONResponse({"status": "error", "message": "Approval not found"})
    
    # Process approval based on type
    try:
        if approval.get('Type') == 'damage_report':
            # Update asset status to "Under Repair"
            from app.utils.sheets import update_asset
            success = update_asset(approval.get('Asset_ID'), {'Status': 'Under Repair'})
            if not success:
                return JSONResponse({"status": "error", "message": "Failed to update asset status"})
        
        elif approval.get('Type') == 'relocation':
            # Process relocation approval
            import json
            try:
                request_data_str = approval.get('Request_Data', '')
                if request_data_str:
                    relocation_data = json.loads(request_data_str)
                    update_data = {
                        'Location': relocation_data.get('new_location'),
                        'Room': relocation_data.get('new_room')
                    }
                    from app.utils.sheets import update_asset
                    success = update_asset(approval.get('Asset_ID'), update_data)
                    if not success:
                        return JSONResponse({"status": "error", "message": "Failed to relocate asset"})
            except Exception as e:
                return JSONResponse({"status": "error", "message": f"Error processing relocation: {str(e)}"})
            
        elif approval.get('Type') == 'edit_asset':
            # Process edit asset approval
            import json
            try:
                request_data_str = approval.get('Request_Data', '')
                if request_data_str:
                    edit_data = json.loads(request_data_str)
                    from app.utils.sheets import update_asset
                    success = update_asset(approval.get('Asset_ID'), edit_data)
                    if not success:
                        return JSONResponse({"status": "error", "message": "Failed to update asset"})
            except Exception as e:
                return JSONResponse({"status": "error", "message": f"Error processing edit: {str(e)}"})
        
        # Update approval status
        approval_update = {
            'Status': 'Approved',
            'Approved_By': current_user.full_name or current_user.email,
            'Approved_Date': __import__('datetime').datetime.now().strftime('%Y-%m-%d')
        }
        
        success = update_approval_status(approval_id, approval_update)
        
        if success:
            return JSONResponse({"status": "success", "message": "Request approved successfully"})
        else:
            return JSONResponse({"status": "error", "message": "Failed to update approval status"})
            
    except Exception as e:
        return JSONResponse({"status": "error", "message": f"Error processing approval: {str(e)}"})

@router.post("/reject/{approval_id}")
async def reject_request(
    approval_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Reject a request."""
    if current_user.role not in ['admin', 'manager']:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Update approval status
    approval_update = {
        'Status': 'Rejected',
        'Approved_By': current_user.full_name or current_user.email,
        'Approved_Date': __import__('datetime').datetime.now().strftime('%Y-%m-%d')
    }
    
    success = update_approval_status(approval_id, approval_update)
    
    if success:
        return JSONResponse({"status": "success", "message": "Request rejected"})
    else:
        return JSONResponse({"status": "error", "message": "Failed to update approval status"})
from fastapi import APIRouter, Request, Depends
from starlette.templating import Jinja2Templates
from app.utils.auth import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/assets")
async def assets_page(request: Request, current_user=Depends(get_current_user)):
    """Assets listing page with filtering and pagination"""
    from app.utils.sheets import get_all_assets
    
    # Ambil data asset dari Google Sheets
    all_assets = get_all_assets()
    
    # Filter hanya aset aktif (bukan Disposed)
    active_assets = [asset for asset in all_assets if asset.get("Status", "").lower() != "disposed"]
    
    return templates.TemplateResponse("assets.html", {
        "request": request,
        "user": current_user,
        "assets_data": active_assets
    })
# app/routes/asset_management.py
from fastapi import APIRouter, Depends, Request, Form, File, UploadFile, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import json
from datetime import datetime
import io

from app.database.database import get_db
from app.database.models import Profile, UserRole
from app.utils.photo import resize_and_convert_image, upload_to_drive
from app.utils.sheets import get_dropdown_options, add_asset as sheets_add_asset
from app.utils.flash import set_flash
from app.utils.auth import get_current_user, get_admin_user
from app.config import load_config

config = load_config()
router = APIRouter(prefix="/asset_management", tags=["asset_management"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/add", response_class=HTMLResponse)
async def add_asset_form(
    request: Request,
    db: Session = Depends(get_db),
    current_profile = Depends(get_current_user)
):
    """Form to add a new asset."""
    dropdown_options = get_dropdown_options()
    return templates.TemplateResponse(
        "asset_management/add.html",
        {
            "request": request,
            "user": current_profile,
            "dropdown_options": dropdown_options
        }
    )


@router.get("/list", response_class=HTMLResponse)
async def asset_list(
    request: Request,
    db: Session = Depends(get_db),
    current_profile = Depends(get_current_user)
):
    """List assets for editing (admin and manager only)."""
    if current_profile.role not in [UserRole.ADMIN, UserRole.MANAGER]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    from app.utils.sheets import get_all_assets
    assets = get_all_assets()
    
    locations = list(set(asset.get('Location', '') for asset in assets if asset.get('Location')))
    location_rooms = {}
    for asset in assets:
        location = asset.get('Location', '')
        room = asset.get('Room', '')
        if location and room:
            if location not in location_rooms:
                location_rooms[location] = set()
            location_rooms[location].add(room)
    
    for location in location_rooms:
        location_rooms[location] = list(location_rooms[location])
    
    return templates.TemplateResponse(
        "asset_management/list.html",
        {
            "request": request,
            "user": current_profile,
            "assets": assets,
            "locations": sorted(locations),
            "location_rooms": location_rooms
        }
    )


@router.get("/edit/{asset_id}", response_class=HTMLResponse)
async def edit_asset_form(
    asset_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_profile = Depends(get_current_user)
):
    """Form to edit an existing asset (admin/manager only)."""
    if current_profile.role not in [UserRole.ADMIN, UserRole.MANAGER]:
        raise HTTPException(status_code=403, detail="Access denied")

    from app.utils.sheets import get_asset_by_id
    asset = get_asset_by_id(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    dropdown_options = get_dropdown_options()
    
    return templates.TemplateResponse(
        "asset_management/edit.html",
        {
            "request": request,
            "user": current_profile,
            "asset": asset,
            "dropdown_options": dropdown_options
        }
    )


@router.post("/edit/{asset_id}")
async def update_asset(
    asset_id: str,
    request: Request,
    status: str = Form(...),
    company: str = Form(...),
    location: str = Form(...),
    room: str = Form(...),
    bisnis_unit: str = Form(None),
    edit_reason: str = Form(...),
    db: Session = Depends(get_db),
    current_profile = Depends(get_current_user)
):
    """Update existing asset (admin and manager only)."""
    if current_profile.role not in [UserRole.ADMIN, UserRole.MANAGER]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    from app.utils.sheets import update_asset as sheets_update_asset, calculate_asset_financials, get_asset_by_id
    asset = get_asset_by_id(asset_id)

    update_data = {
        "Status": status,
        "Company": company,
        "Location": location,
        "Room": room,
        "Bisnis Unit": bisnis_unit or ""
    }
    
    # Jika perlu hitung ulang nilai finansial, misalnya setelah perubahan harga
    # financials = calculate_asset_financials(purchase_cost, purchase_date, category)
    # update_data.update(financials)
    
    from app.utils.sheets import add_approval_request
    
    approval_data = {
        'type': 'edit_asset',
        'asset_id': asset_id,
        'asset_name': asset.get('Item Name', ''),
        'submitted_by': current_profile.full_name or current_profile.email,
        'submitted_date': datetime.now().strftime('%Y-%m-%d'),
        'description': f"Edit asset: {asset.get('Item Name', '')} - Reason: {edit_reason}",
        'edit_reason': edit_reason,
        'request_data': json.dumps(update_data, ensure_ascii=False)
    }
    
    approval_success = add_approval_request(approval_data)
    
    if approval_success:
        response = RedirectResponse(url="/asset_management/list", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, "Asset edit request submitted for manager approval", "success")
        return response
    else:
        dropdown_options = get_dropdown_options()
        return templates.TemplateResponse(
            "asset_management/edit.html",
            {
                "request": request,
                "user": current_profile,
                "asset": asset,
                "dropdown_options": dropdown_options,
                "error": "Error submitting edit request"
            },
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@router.post("/add")
async def add_asset(
    request: Request,
    item_name: str = Form(...),
    category: str = Form(...),
    type: str = Form(...),
    manufacture: str = Form(None),
    model: str = Form(None),
    serial_number: str = Form(None),
    company: str = Form(...),
    bisnis_unit: str = Form(None),
    location: str = Form(...),
    room: str = Form(...),
    notes: str = Form(None),
    item_condition: str = Form(None),
    purchase_date: str = Form(...),
    purchase_cost: str = Form(...),
    warranty: str = Form(None),
    supplier: str = Form(None),
    journal: str = Form(None),
    owner: str = Form(...),
    photo: UploadFile = File(None),
    db: Session = Depends(get_db),
    current_profile = Depends(get_current_user)
):
    """Process add asset form."""
    dropdown_options = get_dropdown_options()
    
    asset_data = {
        "Item Name": item_name,
        "Category": category,
        "Type": type,
        "Manufacture": manufacture or "",
        "Model": model or "",
        "Serial Number": serial_number or "",
        "Company": company,
        "Bisnis Unit": bisnis_unit or "",
        "Location": location,
        "Room": room,
        "Notes": notes or "",
        "Item Condition": item_condition or "",
        "Purchase Date": purchase_date,
        "Purchase Cost": purchase_cost,
        "Warranty": warranty or "",
        "Supplier": supplier or "",
        "Journal": journal or "",
        "Owner": owner,
        "Status": "Active"
    }
    
    photo_url = None
    if photo and photo.filename:
        try:
            contents = await photo.read()
            image_file = io.BytesIO(contents)
            processed_image = resize_and_convert_image(image_file)
            
            if processed_image:
                photo_url = upload_to_drive(processed_image, photo.filename, "new")
                if photo_url:
                    asset_data["Photo URL"] = photo_url
        except Exception as e:
            print(f"Error processing photo: {str(e)}")
    
    if current_profile.role == UserRole.ADMIN:
        success = sheets_add_asset(asset_data)
        
        if success:
            response = RedirectResponse(url="/assets/", status_code=status.HTTP_303_SEE_OTHER)
            set_flash(response, "Asset added successfully", "success")
            return response
        else:
            return templates.TemplateResponse(
                "asset_management/add.html",
                {
                    "request": request,
                    "user": current_profile,
                    "dropdown_options": dropdown_options,
                    "error": "Error adding asset to Google Sheets",
                    "form_data": asset_data
                },
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    from app.utils.sheets import add_approval_request
    
    approval_data = {
        'type': 'add_asset',
        'asset_id': 'NEW',
        'asset_name': item_name,
        'submitted_by': current_profile.full_name or current_profile.email,
        'submitted_date': datetime.now().strftime('%Y-%m-%d'),
        'description': f"Add new asset: {item_name}",
        'request_data': json.dumps(asset_data, ensure_ascii=False)
    }
    
    approval_success = add_approval_request(approval_data)
    
    if approval_success:
        response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, "Asset request submitted for approval", "success")
        return response
    else:
        return templates.TemplateResponse(
            "asset_management/add.html",
            {
                "request": request,
                "user": current_profile,
                "dropdown_options": dropdown_options,
                "error": "Error submitting approval request",
                "form_data": asset_data
            },
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
from fastapi import APIRouter, Request, Depends
from starlette.templating import Jinja2Templates
from app.utils.auth import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/")
async def damaged_assets_page(request: Request, current_user = Depends(get_current_user)):
    """Damaged assets page with search and log functionality"""
    from app.utils.sheets import get_all_assets, get_dropdown_options

    all_assets = get_all_assets()
    dropdown_options = get_dropdown_options()

    return templates.TemplateResponse("damaged_assets.html", {
        "request": request,
        "user": current_user,
        "assets_data": all_assets,
        "dropdown_options": dropdown_options
    })


@router.post("/lost")
async def submit_lost_report(request: Request, current_user = Depends(get_current_user)):
    """Submit lost report - syncs to Google Sheets"""
    from app.utils.sheets import add_lost_log, add_approval_request
    from datetime import datetime

    try:
        data = await request.json()

        lost_data = {
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'last_location': data.get('last_location'),
            'last_room': data.get('last_room', ''),
            'date_lost': data.get('date_lost'),
            'description': data.get('description'),
            'reported_by': current_user.full_name or current_user.email,
            'report_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'notes': data.get('notes', '')
        }

        log_success = add_lost_log(lost_data)

        approval_data = {
            'type': 'lost_report',
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'submitted_by': current_user.full_name or current_user.email,
            'submitted_date': datetime.now().strftime('%Y-%m-%d'),
            'description': f"Lost report: {data.get('description')}",
            'location': data.get('last_location')
        }

        approval_success = add_approval_request(approval_data)

        if log_success and approval_success:
            return {"status": "success", "message": "Lost report submitted and logged to Google Sheets"}
        else:
            return {"status": "error", "message": "Failed to sync with Google Sheets"}

    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/disposal")
async def submit_disposal_request(request: Request, current_user = Depends(get_current_user)):
    """Submit disposal request - syncs to Google Sheets"""
    from app.utils.sheets import add_disposal_log, add_approval_request
    from datetime import datetime

    try:
        data = await request.json()

        disposal_data = {
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'disposal_reason': data.get('disposal_reason'),
            'disposal_method': data.get('disposal_method', 'Standard'),
            'description': data.get('description'),
            'requested_by': current_user.full_name or current_user.email,
            'request_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'notes': data.get('notes', '')
        }

        log_success = add_disposal_log(disposal_data)

        approval_data = {
            'type': 'disposal_request',
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'submitted_by': current_user.full_name or current_user.email,
            'submitted_date': datetime.now().strftime('%Y-%m-%d'),
            'description': f"Disposal request: {data.get('description')}"
        }

        approval_success = add_approval_request(approval_data)

        if log_success and approval_success:
            return {"status": "success", "message": "Disposal request submitted and logged to Google Sheets"}
        else:
            return {"status": "error", "message": "Failed to sync with Google Sheets"}

    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/report")
async def submit_damage_report(request: Request, current_user = Depends(get_current_user)):
    """Submit damage report - syncs to Google Sheets"""
    from app.utils.sheets import add_damage_log, add_approval_request
    from datetime import datetime

    try:
        data = await request.json()

        damage_data = {
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'damage_type': data.get('damage_type'),
            'severity': data.get('severity'),
            'description': data.get('damage_description'),
            'reported_by': current_user.full_name or current_user.email,
            'report_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'location': data.get('location', ''),
            'room': data.get('room', ''),
            'notes': data.get('notes', '')
        }

        approval_data = {
            'type': 'damage_report',
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'submitted_by': current_user.full_name or current_user.email,
            'submitted_date': datetime.now().strftime('%Y-%m-%d'),
            'description': f"Damage report: {data.get('damage_description')}",
            'damage_type': data.get('damage_type'),
            'severity': data.get('severity')
        }

        approval_success = add_approval_request(approval_data)

        if approval_success:
            return {"status": "success", "message": "Damage report submitted for approval"}
        else:
            return {"status": "error", "message": "Failed to submit approval request"}

    except Exception as e:
        return {"status": "error", "message": str(e)}
# app/routes/disposal.py
from fastapi import APIRouter, Depends, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime

from app.database.database import get_db
from app.database.models import Profile
from app.utils.auth import get_admin_user
from app.utils.sheets import get_all_assets, update_asset, add_disposal_log
from app.utils.flash import set_flash

router = APIRouter(prefix="/disposal", tags=["disposal"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def disposal_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Disposal assets page (admin only)."""
    # Get assets that are ready to dispose only
    all_assets = get_all_assets()
    # Debug: check all statuses
    statuses = [str(asset.get('Status', '')).strip() for asset in all_assets]
    print(f"All statuses found: {set(statuses)}")
    
    disposable_assets = []
    for asset in all_assets:
        status = str(asset.get('Status', '')).strip()
        if status in ['To Be Disposed', 'To be Disposed', 'TO BE DISPOSED']:
            disposable_assets.append(asset)
    
    return templates.TemplateResponse(
        "disposal/index.html",
        {
            "request": request,
            "user": current_user,
            "assets": disposable_assets
        }
    )

@router.post("/dispose/{asset_id}")
async def dispose_asset(
    asset_id: str,
    request: Request,
    disposal_reason: str = Form(...),
    disposal_method: str = Form(...),
    description: str = Form(None),
    notes: str = Form(None),
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Dispose an asset (admin only)."""
    from app.utils.sheets import get_asset_by_id
    
    # Get asset data
    asset = get_asset_by_id(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    if str(asset.get('Status', '')).strip() != 'To Be Disposed':
        raise HTTPException(status_code=400, detail="Asset must be marked 'To Be Disposed' first")
    
    # Create disposal approval request
    from app.utils.sheets import add_approval_request
    
    approval_data = {
        'type': 'disposal',
        'asset_id': asset_id,
        'asset_name': asset.get('Item Name', ''),
        'submitted_by': current_user.full_name or current_user.email,
        'submitted_date': datetime.now().strftime('%Y-%m-%d'),
        'description': f"Disposal request: {disposal_reason} - {disposal_method}",
        'disposal_reason': disposal_reason,
        'disposal_method': disposal_method,
        'notes': f"Description: {description or ''} | Notes: {notes or ''}"
    }
    
    approval_success = add_approval_request(approval_data)
    
    if approval_success:
        response = RedirectResponse(url="/disposal", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, f"Disposal request for {asset.get('Item Name', '')} submitted for manager approval", "success")
        return response
    else:
        response = RedirectResponse(url="/disposal", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, "Error submitting disposal request", "error")
        return response
# app/routes/health.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
import time

from app.database.database import get_db
from app.config import load_config

router = APIRouter(tags=["health"])
config = load_config()

@router.get("/health")
async def health_check(db: Session = Depends(get_db)):
    """Health check endpoint."""
    start_time = time.time()
    
    # Check database connection
    try:
        db.execute(text("SELECT 1"))
        db_status = "healthy"
    except Exception as e:
        db_status = f"unhealthy: {str(e)}"
    
    # Check Google Sheets API
    sheets_status = "configured" if config.GOOGLE_SHEET_ID else "not configured"
    
    # Response time
    response_time = time.time() - start_time
    
    return {
        "status": "ok",
        "database": db_status,
        "google_sheets": sheets_status,
        "response_time_ms": round(response_time * 1000, 2)
    }
# /app/app/routes/home.py
import logging
from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse
from starlette.templating import Jinja2Templates
from app.utils.auth import get_current_user
from app.utils.sheets import get_summary_data, get_chart_data, get_all_assets

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=RedirectResponse)
async def redirect_root():
    return RedirectResponse("/dashboard")

@router.get("/dashboard")
async def home(request: Request, current_user = Depends(get_current_user)):
    try:
        # Summary and chart data
        summary_data = get_summary_data()
        chart_data = get_chart_data()
        all_assets = get_all_assets()

        # Filter out disposed assets for dashboard counts
        active_assets = [asset for asset in all_assets if asset.get("Status", "") != "Disposed"]
        disposed_assets = [asset for asset in all_assets if asset.get("Status", "") == "Disposed"]
        
        # Count assets by status and activity
        total_assets = len(active_assets)
        disposed_count = len(disposed_assets)
        damaged_count = len([a for a in all_assets if a.get("Status", "") == "Under Repair"])
        
        # Count assets by activity type
        relocated_count = len([a for a in all_assets if a.get("Last Activity", "") == "Relocated"])
        repaired_count = len([a for a in all_assets if a.get("Last Activity", "") == "Repaired"])
        to_be_disposed_count = len([a for a in all_assets if a.get("Status", "") == "To Be Disposed"])
        
        # Helper function to safely convert values to float
        def safe_float(value):
            if value is None or value == '':
                return 0.0
            try:
                return float(value)
            except (ValueError, TypeError):
                return 0.0
        
        # Calculate financial values directly from assets
        total_purchase_value = sum(safe_float(asset.get("Purchase Cost")) for asset in active_assets)
        total_book_value = sum(safe_float(asset.get("Book Value")) for asset in active_assets)
        # Calculate depreciation as purchase value minus book value
        total_depreciation_value = total_purchase_value - total_book_value
        category_counts = chart_data.get("category_counts", {})
        
        # Format location data
        location_data = chart_data.get("location_chart_data", {})
        location_counts = location_data.get("labels", [])
        location_values = location_data.get("values", [])
        location_counts_dict = dict(zip(location_counts, location_values))

        # Format time-based chart data
        monthly_data = chart_data.get("monthly_chart_data", {})
        monthly_chart_labels = monthly_data.get("labels", [])
        monthly_chart_values = monthly_data.get("values", [])
        
        # Generate quarterly data (last 12 quarters - 3 years)
        quarterly_chart_labels = []
        quarterly_chart_values = []
        
        # Get current year and quarter
        from datetime import datetime
        current_date = datetime.now()
        current_year = current_date.year
        current_quarter = (current_date.month - 1) // 3 + 1
        
        # Generate data for the last 12 quarters
        for i in range(11, -1, -1):
            year = current_year
            quarter = current_quarter - i
            
            # Adjust year if quarter is negative or > 4
            while quarter <= 0:
                year -= 1
                quarter += 4
            while quarter > 4:
                year += 1
                quarter -= 4
                
            quarterly_chart_labels.append(f"Q{quarter} {year}")
            
            # Count assets added in this quarter
            quarter_start_month = (quarter - 1) * 3 + 1
            quarter_end_month = quarter * 3
            
            count = 0
            for asset in all_assets:
                purchase_date = asset.get("Purchase Date", "")
                if purchase_date:
                    try:
                        date = datetime.strptime(purchase_date, "%Y-%m-%d")
                        if date.year == year and quarter_start_month <= date.month <= quarter_end_month:
                            count += 1
                    except:
                        pass
            
            quarterly_chart_values.append(count)
        
        # Generate yearly data (last 5 years)
        yearly_chart_labels = []
        yearly_chart_values = []
        
        # Generate data for the last 5 years
        for i in range(4, -1, -1):
            year = current_year - i
            yearly_chart_labels.append(str(year))
            
            # Count assets added in this year
            count = 0
            for asset in all_assets:
                purchase_date = asset.get("Purchase Date", "")
                if purchase_date:
                    try:
                        date = datetime.strptime(purchase_date, "%Y-%m-%d")
                        if date.year == year:
                            count += 1
                    except:
                        pass
            
            yearly_chart_values.append(count)

        # Format age distribution - convert to list of tuples for proper serialization
        age_distribution = chart_data.get("age_distribution", {})
        age_distribution_list = [
            {"label": str(k), "value": int(v)} 
            for k, v in age_distribution.items()
        ]

        # Format latest assets (excluding disposed assets)
        latest_assets = sorted(
            active_assets, 
            key=lambda a: a.get("Purchase Date", ""), 
            reverse=True
        )[:10]
        
        # Process assets to ensure they have a display_name field
        for asset in latest_assets:
            # Try different possible field names for the asset name
            name_fields = ["Name", "Asset Name", "AssetName", "Item Name", "Description", "Item"]
            display_name = None
            
            for field in name_fields:
                if asset.get(field):
                    display_name = asset.get(field)
                    break
            
            # If no name found, use a default
            if not display_name:
                display_name = f"Asset #{asset.get('ID', 'Unknown')}"
                
            # Add the display_name to the asset
            asset["display_name"] = display_name
            
        # Debug: Print the first asset's keys to see what fields are available
        if latest_assets:
            logging.info(f"Asset keys: {list(latest_assets[0].keys())}")
            logging.info(f"Asset display name: {latest_assets[0].get('display_name', 'Not found')}")
            logging.info(f"Original asset name fields: {[latest_assets[0].get(f, 'None') for f in name_fields]}")

        context = {
            "request": request,
            "user": current_user,
            "total_assets": total_assets,
            "total_purchase_value": total_purchase_value,
            "total_book_value": total_book_value,
            "total_depreciation_value": total_depreciation_value,
            "disposed_count": disposed_count,
            "damaged_count": damaged_count,
            "relocated_count": relocated_count,
            "repaired_count": repaired_count,
            "to_be_disposed_count": to_be_disposed_count,
            "category_counts": category_counts,
            "location_counts": location_counts_dict,
            "monthly_chart_labels": monthly_chart_labels,
            "monthly_chart_values": monthly_chart_values,
            "quarterly_chart_labels": quarterly_chart_labels,
            "quarterly_chart_values": quarterly_chart_values,
            "yearly_chart_labels": yearly_chart_labels,
            "yearly_chart_values": yearly_chart_values,
            "age_distribution": age_distribution_list,
            "latest_assets": latest_assets
        }

        return templates.TemplateResponse("dashboard.html", context)

    except Exception as e:
        logging.error("Dashboard error: %s", e, exc_info=True)
        return templates.TemplateResponse("error.html", {
            "request": request,
            "user": current_user,
            "message": "Terjadi kesalahan saat memuat dashboard.",
        })
from fastapi import APIRouter, Request, Response, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from supabase import create_client, Client
from app.config import load_config
import logging

config = load_config()
supabase: Client = create_client(config.SUPABASE_URL, config.SUPABASE_ANON_KEY)

router = APIRouter(tags=["authentication"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/login", response_class=HTMLResponse)
@router.head("/login", response_class=HTMLResponse)
async def login_page(request: Request, next: str = None):
    return templates.TemplateResponse("login_logout.html", {"request": request, "next": next})

@router.post("/login", response_class=HTMLResponse)
async def login_form(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    next: str = Form(None)
):
    try:
        # Use service key client for admin operations
        from supabase import create_client
        admin_supabase = create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_KEY)
        
        response = admin_supabase.auth.sign_in_with_password({
            "email": email,
            "password": password
        })
        
        if not response.user:
            return templates.TemplateResponse(
                "login_logout.html",
                {"request": request, "error": "Invalid email or password", "next": next},
                status_code=401
            )
        
        # Get user profile
        profile_response = admin_supabase.table('profiles').select('*').eq('id', response.user.id).single().execute()
        if not profile_response.data or not profile_response.data.get('is_active'):
            return templates.TemplateResponse(
                "login_logout.html",
                {"request": request, "error": "Account is inactive", "next": next},
                status_code=401
            )
        
        redirect_url = next if next else "/"
        redirect_response = RedirectResponse(url=redirect_url, status_code=303)
        
        redirect_response.set_cookie(
            key="sb_access_token",
            value=response.session.access_token,
            httponly=True,
            max_age=3600,
            samesite="lax",
            secure=True,
            domain=".onrender.com"
        )
        
        return redirect_response
        
    except Exception as e:
        logging.error(f"Login error: {str(e)}")
        return templates.TemplateResponse(
            "login_logout.html",
            {"request": request, "error": "Login failed", "next": next},
            status_code=401
        )

@router.get("/auth/callback")
async def auth_callback(request: Request):
    return templates.TemplateResponse("auth_callback.html", {"request": request})

@router.get("/logout")
async def logout():
    try:
        supabase.auth.sign_out()
    except:
        pass
    
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(key="sb_access_token")
    return response
# app/routes/logs.py
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.database.models import Profile
from app.utils.auth import get_current_user
from app.utils.sheets import get_all_approvals

router = APIRouter(prefix="/logs", tags=["logs"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def logs_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """View approval logs based on user role."""
    all_approvals = get_all_approvals()
    
    # Filter based on user role
    if current_user.role.value == 'staff':
        # Staff can only see their own requests
        user_identifier = current_user.full_name or current_user.email
        approvals = [a for a in all_approvals if a.get('Submitted_By') == user_identifier]
    else:
        # Manager and admin can see all approvals
        approvals = all_approvals
    
    # Separate pending and completed
    pending_approvals = [a for a in approvals if a.get('Status') == 'Pending']
    completed_approvals = [a for a in approvals if a.get('Status') in ['Approved', 'Rejected']]
    
    return templates.TemplateResponse(
        "logs/index.html",
        {
            "request": request,
            "user": current_user,
            "pending_approvals": pending_approvals,
            "completed_approvals": completed_approvals
        }
    )
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
from fastapi import APIRouter, Depends, Request, Form, UploadFile, File, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from app.database.database import get_db
from app.database.models import Profile
from app.utils.auth import get_current_user
from app.utils.photo import resize_and_convert_image, upload_to_drive
from app.utils.flash import set_flash

router = APIRouter(tags=["profile"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/profile", response_class=HTMLResponse)
async def profile_page(
    request: Request,
    current_user = Depends(get_current_user)
):
    """User profile page."""
    return templates.TemplateResponse(
        "profile/view.html",
        {
            "request": request,
            "user": current_user
        }
    )

@router.get("/profile/edit", response_class=HTMLResponse)
async def edit_profile_page(
    request: Request,
    current_user = Depends(get_current_user)
):
    """Edit user profile page."""
    return templates.TemplateResponse(
        "profile/edit.html",
        {
            "request": request,
            "user": current_user
        }
    )

@router.post("/profile/edit")
async def update_profile(
    request: Request,
    full_name: str = Form(...),
    email: str = Form(...),
    photo: UploadFile = File(None),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Update user profile."""
    # Update basic info
    current_user.full_name = full_name
    current_user.email = email
    current_user.updated_at = datetime.now(timezone.utc)
    
    # Handle photo upload if provided
    if photo and photo.filename:
        try:
            # Process image
            contents = await photo.read()
            import io
            image_file = io.BytesIO(contents)
            processed_image = resize_and_convert_image(image_file)
            
            if processed_image:
                # Upload to Google Drive
                photo_url = upload_to_drive(
                    processed_image, 
                    photo.filename, 
                    f"profile_{current_user.email}"
                )
                if photo_url:
                    current_user.photo_url = photo_url
        except Exception as e:
            return templates.TemplateResponse(
                "profile/edit.html",
                {
                    "request": request,
                    "user": current_user,
                    "error": f"Error uploading photo: {str(e)}"
                },
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    # Save changes
    db.commit()
    
    # Redirect to profile page
    response = RedirectResponse(url="/profile", status_code=status.HTTP_303_SEE_OTHER)
    set_flash(response, "Profile updated successfully", "success")
    return response
# app/routes/relocation.py
from fastapi import APIRouter, Depends, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime
import json

from app.database.database import get_db
from app.database.models import Profile
from app.utils.auth import get_current_user
from app.utils.sheets import get_all_assets, get_dropdown_options, add_approval_request
from app.utils.flash import set_flash

router = APIRouter(prefix="/relocation", tags=["relocation"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def relocation_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Asset relocation page."""
    # Get assets and dropdown options
    all_assets = get_all_assets()
    dropdown_options = get_dropdown_options()
    
    return templates.TemplateResponse(
        "relocation/index.html",
        {
            "request": request,
            "user": current_user,
            "assets": all_assets,
            "dropdown_options": dropdown_options
        }
    )

@router.post("/relocate/{asset_id}")
async def relocate_asset(
    asset_id: str,
    request: Request,
    new_location: str = Form(...),
    new_room: str = Form(...),
    reason: str = Form(...),
    notes: str = Form(None),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Submit asset relocation request."""
    from app.utils.sheets import get_asset_by_id
    
    # Get asset data
    asset = get_asset_by_id(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    # Create relocation approval request
    relocation_data = {
        'new_location': new_location,
        'new_room': new_room,
        'current_location': asset.get('Location', ''),
        'current_room': asset.get('Room', ''),
        'reason': reason,
        'notes': notes or ''
    }
    
    approval_data = {
        'type': 'relocation',
        'asset_id': asset_id,
        'asset_name': asset.get('Item Name', ''),
        'submitted_by': current_user.full_name or current_user.email,
        'submitted_date': datetime.now().strftime('%Y-%m-%d'),
        'description': f"Relocate from {asset.get('Location', '')} - {asset.get('Room', '')} to {new_location} - {new_room}",
        'request_data': json.dumps(relocation_data, ensure_ascii=False)
    }
    
    approval_success = add_approval_request(approval_data)
    
    if approval_success:
        response = RedirectResponse(url="/relocation", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, f"Relocation request for {asset.get('Item Name', '')} submitted for approval", "success")
        return response
    else:
        response = RedirectResponse(url="/relocation", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, "Error submitting relocation request", "error")
        return response
# /app/app/routes/repair.py
from fastapi import APIRouter, Request, Depends
from starlette.templating import Jinja2Templates
from app.utils.auth import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.post("/action")
async def submit_repair_action(request: Request, current_user = Depends(get_current_user)):
    """Submit repair action - creates approval request for store, direct action for allocate"""
    from app.utils.sheets import add_repair_log, update_asset, add_approval_request
    from datetime import datetime
    
    try:
        # Get JSON data
        data = await request.json()
        action_type = data.get('action_type')  # 'store' or 'allocate'
        
        if action_type == 'store':
            # Store action requires approval - only create approval request
            approval_data = {
                'type': 'repair_action',
                'asset_id': data.get('asset_id'),
                'asset_name': data.get('asset_name'),
                'submitted_by': current_user.full_name or current_user.email,
                'submitted_date': datetime.now().strftime('%Y-%m-%d'),
                'description': f"Request to store asset: {data.get('description')}",
                'action': 'Store Asset'
            }
            
            approval_success = add_approval_request(approval_data)
            
            if approval_success:
                return {"status": "success", "message": "Store request submitted for admin approval"}
            else:
                return {"status": "error", "message": "Failed to submit approval request"}
        
        else:  # allocate - direct action
            # Add to Repair_Log sheet
            repair_data = {
                'asset_id': data.get('asset_id'),
                'asset_name': data.get('asset_name'),
                'repair_action': 'Allocate Asset',
                'action_type': action_type,
                'description': data.get('description', ''),
                'performed_by': current_user.full_name or current_user.email,
                'action_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'new_location': data.get('location', ''),
                'new_room': data.get('room', ''),
                'notes': data.get('notes', '')
            }
            
            # Add to repair log
            log_success = add_repair_log(repair_data)
            
            # Update asset from Under Repair to Active
            update_data = {
                'Status': 'Active',
                'Bisnis Unit': data.get('business_unit', ''),
                'Location': data.get('location', ''),
                'Room': data.get('room', '')
            }
            
            asset_success = update_asset(data.get('asset_id'), update_data)
            
            if log_success and asset_success:
                return {"status": "success", "message": "Asset allocated successfully and synced to Google Sheets"}
            else:
                return {"status": "error", "message": "Failed to sync with Google Sheets"}
            
    except Exception as e:
        return {"status": "error", "message": str(e)}
# app/routes/user_management.py
from fastapi import APIRouter, Depends, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.database.models import Profile, UserRole
from app.utils.auth import get_current_user, get_admin_user
from app.utils.flash import set_flash

router = APIRouter(prefix="/user_management", tags=["user_management"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def user_list(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """List all users (admin only)."""
    users = db.query(Profile).all()
    
    return templates.TemplateResponse(
        "user_management/list.html",
        {
            "request": request,
            "user": current_user,
            "users": users
        }
    )

@router.get("/create", response_class=HTMLResponse)
async def create_user_form(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Create user form (admin only)."""
    return templates.TemplateResponse(
        "user_management/create.html",
        {
            "request": request,
            "user": current_user
        }
    )

@router.post("/create")
async def create_user(
    request: Request,
    email: str = Form(...),
    full_name: str = Form(...),
    role: str = Form(...),
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Create new user (admin only)."""
    # Check if user exists
    existing_user = db.query(Profile).filter(Profile.email == email).first()
    if existing_user:
        return templates.TemplateResponse(
            "user_management/create.html",
            {
                "request": request,
                "user": current_user,
                "error": "Email already exists"
            }
        )
    
    # Create user profile (Supabase handles auth)
    new_user = Profile(
        email=email,
        full_name=full_name,
        role=getattr(UserRole, role.upper()),
        is_active=True
    )
    
    db.add(new_user)
    db.commit()
    
    response = RedirectResponse(url="/user_management", status_code=status.HTTP_303_SEE_OTHER)
    set_flash(response, f"User {email} created successfully", "success")
    return response

@router.post("/reset_password/{user_id}")
async def reset_password(
    user_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Reset user password to default (admin only)."""
    user = db.query(Profile).filter(Profile.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Password reset handled by Supabase
    default_password = f"{user.email.split('@')[0]}123"
    
    response = RedirectResponse(url="/user_management", status_code=status.HTTP_303_SEE_OTHER)
    set_flash(response, f"Password reset instructions sent to {user.email}", "success")
    return response

@router.post("/toggle_status/{user_id}")
async def toggle_user_status(
    user_id: str,
    request: Request,
    is_active: bool = Form(...),
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Toggle user active status (admin only)."""
    user = db.query(Profile).filter(Profile.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Update status
    user.is_active = is_active
    db.commit()
    
    status_text = "activated" if is_active else "deactivated"
    response = RedirectResponse(url="/user_management", status_code=status.HTTP_303_SEE_OTHER)
    set_flash(response, f"User {user.email} {status_text}", "success")
    return response
# app/routes/__init__.py

# Import all route modules to make them available from app.routes
from app.routes import (
    home,
    assets,
    asset_management,
    login,
    damage,
    health,
    offline,
    profile,
    repair,
    approvals,
    disposal,
    user_management,
    logs,
    relocation
)
# app/routes/approvals.py
from fastapi import APIRouter, Depends, Request, HTTPException, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.utils.auth import get_current_user
from app.utils.sheets import get_all_approvals, update_approval_status

router = APIRouter(prefix="/approvals", tags=["approvals"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def approvals_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Approvals page for admin and manager."""
    if current_user.role not in ['admin', 'manager']:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get all approvals from Google Sheets
    all_approvals = get_all_approvals()
    
    # Filter approvals based on user role
    if current_user.role == 'admin':
        # Admin sees all approvals except disposal and edit_asset
        approvals_data = [a for a in all_approvals if a.get('Type') not in ['disposal', 'edit_asset']]
    elif current_user.role == 'manager':
        # Manager sees disposal and edit_asset approvals
        approvals_data = [a for a in all_approvals if a.get('Type') in ['disposal', 'edit_asset']]
    else:
        approvals_data = []
    
    return templates.TemplateResponse(
        "approvals/list.html",
        {
            "request": request,
            "user": current_user,
            "approvals_data": approvals_data
        }
    )

@router.post("/approve/{approval_id}")
async def approve_request(
    approval_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Approve a request."""
    if current_user.role not in ['admin', 'manager']:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get approval details
    all_approvals = get_all_approvals()
    approval = next((a for a in all_approvals if str(a.get('ID')) == str(approval_id)), None)
    
    if not approval:
        return JSONResponse({"status": "error", "message": "Approval not found"})
    
    # Process approval based on type
    try:
        if approval.get('Type') == 'damage_report':
            # Update asset status to "Under Repair"
            from app.utils.sheets import update_asset
            success = update_asset(approval.get('Asset_ID'), {'Status': 'Under Repair'})
            if not success:
                return JSONResponse({"status": "error", "message": "Failed to update asset status"})
        
        elif approval.get('Type') == 'relocation':
            # Process relocation approval
            import json
            try:
                request_data_str = approval.get('Request_Data', '')
                if request_data_str:
                    relocation_data = json.loads(request_data_str)
                    update_data = {
                        'Location': relocation_data.get('new_location'),
                        'Room': relocation_data.get('new_room')
                    }
                    from app.utils.sheets import update_asset
                    success = update_asset(approval.get('Asset_ID'), update_data)
                    if not success:
                        return JSONResponse({"status": "error", "message": "Failed to relocate asset"})
            except Exception as e:
                return JSONResponse({"status": "error", "message": f"Error processing relocation: {str(e)}"})
            
        elif approval.get('Type') == 'edit_asset':
            # Process edit asset approval
            import json
            try:
                request_data_str = approval.get('Request_Data', '')
                if request_data_str:
                    edit_data = json.loads(request_data_str)
                    from app.utils.sheets import update_asset
                    success = update_asset(approval.get('Asset_ID'), edit_data)
                    if not success:
                        return JSONResponse({"status": "error", "message": "Failed to update asset"})
            except Exception as e:
                return JSONResponse({"status": "error", "message": f"Error processing edit: {str(e)}"})
        
        # Update approval status
        approval_update = {
            'Status': 'Approved',
            'Approved_By': current_user.full_name or current_user.email,
            'Approved_Date': __import__('datetime').datetime.now().strftime('%Y-%m-%d')
        }
        
        success = update_approval_status(approval_id, approval_update)
        
        if success:
            return JSONResponse({"status": "success", "message": "Request approved successfully"})
        else:
            return JSONResponse({"status": "error", "message": "Failed to update approval status"})
            
    except Exception as e:
        return JSONResponse({"status": "error", "message": f"Error processing approval: {str(e)}"})

@router.post("/reject/{approval_id}")
async def reject_request(
    approval_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Reject a request."""
    if current_user.role not in ['admin', 'manager']:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Update approval status
    approval_update = {
        'Status': 'Rejected',
        'Approved_By': current_user.full_name or current_user.email,
        'Approved_Date': __import__('datetime').datetime.now().strftime('%Y-%m-%d')
    }
    
    success = update_approval_status(approval_id, approval_update)
    
    if success:
        return JSONResponse({"status": "success", "message": "Request rejected"})
    else:
        return JSONResponse({"status": "error", "message": "Failed to update approval status"})
from fastapi import APIRouter, Request, Depends
from starlette.templating import Jinja2Templates
from app.utils.auth import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/assets")
async def assets_page(request: Request, current_user=Depends(get_current_user)):
    """Assets listing page with filtering and pagination"""
    from app.utils.sheets import get_all_assets
    
    # Ambil data asset dari Google Sheets
    all_assets = get_all_assets()
    
    # Filter hanya aset aktif (bukan Disposed)
    active_assets = [asset for asset in all_assets if asset.get("Status", "").lower() != "disposed"]
    
    return templates.TemplateResponse("assets.html", {
        "request": request,
        "user": current_user,
        "assets_data": active_assets
    })
# app/routes/asset_management.py
from fastapi import APIRouter, Depends, Request, Form, File, UploadFile, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import json
from datetime import datetime
import io

from app.database.database import get_db
from app.database.models import Profile, UserRole
from app.utils.photo import resize_and_convert_image, upload_to_drive
from app.utils.sheets import get_dropdown_options, add_asset as sheets_add_asset
from app.utils.flash import set_flash
from app.utils.auth import get_current_user, get_admin_user
from app.config import load_config

config = load_config()
router = APIRouter(prefix="/asset_management", tags=["asset_management"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/add", response_class=HTMLResponse)
async def add_asset_form(
    request: Request,
    db: Session = Depends(get_db),
    current_profile = Depends(get_current_user)
):
    """Form to add a new asset."""
    dropdown_options = get_dropdown_options()
    return templates.TemplateResponse(
        "asset_management/add.html",
        {
            "request": request,
            "user": current_profile,
            "dropdown_options": dropdown_options
        }
    )


@router.get("/list", response_class=HTMLResponse)
async def asset_list(
    request: Request,
    db: Session = Depends(get_db),
    current_profile = Depends(get_current_user)
):
    """List assets for editing (admin and manager only)."""
    if current_profile.role not in [UserRole.ADMIN, UserRole.MANAGER]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    from app.utils.sheets import get_all_assets
    assets = get_all_assets()
    
    locations = list(set(asset.get('Location', '') for asset in assets if asset.get('Location')))
    location_rooms = {}
    for asset in assets:
        location = asset.get('Location', '')
        room = asset.get('Room', '')
        if location and room:
            if location not in location_rooms:
                location_rooms[location] = set()
            location_rooms[location].add(room)
    
    for location in location_rooms:
        location_rooms[location] = list(location_rooms[location])
    
    return templates.TemplateResponse(
        "asset_management/list.html",
        {
            "request": request,
            "user": current_profile,
            "assets": assets,
            "locations": sorted(locations),
            "location_rooms": location_rooms
        }
    )


@router.get("/edit/{asset_id}", response_class=HTMLResponse)
async def edit_asset_form(
    asset_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_profile = Depends(get_current_user)
):
    """Form to edit an existing asset (admin/manager only)."""
    if current_profile.role not in [UserRole.ADMIN, UserRole.MANAGER]:
        raise HTTPException(status_code=403, detail="Access denied")

    from app.utils.sheets import get_asset_by_id
    asset = get_asset_by_id(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    dropdown_options = get_dropdown_options()
    
    return templates.TemplateResponse(
        "asset_management/edit.html",
        {
            "request": request,
            "user": current_profile,
            "asset": asset,
            "dropdown_options": dropdown_options
        }
    )


@router.post("/edit/{asset_id}")
async def update_asset(
    asset_id: str,
    request: Request,
    status: str = Form(...),
    company: str = Form(...),
    location: str = Form(...),
    room: str = Form(...),
    bisnis_unit: str = Form(None),
    edit_reason: str = Form(...),
    db: Session = Depends(get_db),
    current_profile = Depends(get_current_user)
):
    """Update existing asset (admin and manager only)."""
    if current_profile.role not in [UserRole.ADMIN, UserRole.MANAGER]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    from app.utils.sheets import update_asset as sheets_update_asset, calculate_asset_financials, get_asset_by_id
    asset = get_asset_by_id(asset_id)

    update_data = {
        "Status": status,
        "Company": company,
        "Location": location,
        "Room": room,
        "Bisnis Unit": bisnis_unit or ""
    }
    
    # Jika perlu hitung ulang nilai finansial, misalnya setelah perubahan harga
    # financials = calculate_asset_financials(purchase_cost, purchase_date, category)
    # update_data.update(financials)
    
    from app.utils.sheets import add_approval_request
    
    approval_data = {
        'type': 'edit_asset',
        'asset_id': asset_id,
        'asset_name': asset.get('Item Name', ''),
        'submitted_by': current_profile.full_name or current_profile.email,
        'submitted_date': datetime.now().strftime('%Y-%m-%d'),
        'description': f"Edit asset: {asset.get('Item Name', '')} - Reason: {edit_reason}",
        'edit_reason': edit_reason,
        'request_data': json.dumps(update_data, ensure_ascii=False)
    }
    
    approval_success = add_approval_request(approval_data)
    
    if approval_success:
        response = RedirectResponse(url="/asset_management/list", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, "Asset edit request submitted for manager approval", "success")
        return response
    else:
        dropdown_options = get_dropdown_options()
        return templates.TemplateResponse(
            "asset_management/edit.html",
            {
                "request": request,
                "user": current_profile,
                "asset": asset,
                "dropdown_options": dropdown_options,
                "error": "Error submitting edit request"
            },
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@router.post("/add")
async def add_asset(
    request: Request,
    item_name: str = Form(...),
    category: str = Form(...),
    type: str = Form(...),
    manufacture: str = Form(None),
    model: str = Form(None),
    serial_number: str = Form(None),
    company: str = Form(...),
    bisnis_unit: str = Form(None),
    location: str = Form(...),
    room: str = Form(...),
    notes: str = Form(None),
    item_condition: str = Form(None),
    purchase_date: str = Form(...),
    purchase_cost: str = Form(...),
    warranty: str = Form(None),
    supplier: str = Form(None),
    journal: str = Form(None),
    owner: str = Form(...),
    photo: UploadFile = File(None),
    db: Session = Depends(get_db),
    current_profile = Depends(get_current_user)
):
    """Process add asset form."""
    dropdown_options = get_dropdown_options()
    
    asset_data = {
        "Item Name": item_name,
        "Category": category,
        "Type": type,
        "Manufacture": manufacture or "",
        "Model": model or "",
        "Serial Number": serial_number or "",
        "Company": company,
        "Bisnis Unit": bisnis_unit or "",
        "Location": location,
        "Room": room,
        "Notes": notes or "",
        "Item Condition": item_condition or "",
        "Purchase Date": purchase_date,
        "Purchase Cost": purchase_cost,
        "Warranty": warranty or "",
        "Supplier": supplier or "",
        "Journal": journal or "",
        "Owner": owner,
        "Status": "Active"
    }
    
    photo_url = None
    if photo and photo.filename:
        try:
            contents = await photo.read()
            image_file = io.BytesIO(contents)
            processed_image = resize_and_convert_image(image_file)
            
            if processed_image:
                photo_url = upload_to_drive(processed_image, photo.filename, "new")
                if photo_url:
                    asset_data["Photo URL"] = photo_url
        except Exception as e:
            print(f"Error processing photo: {str(e)}")
    
    if current_profile.role == UserRole.ADMIN:
        success = sheets_add_asset(asset_data)
        
        if success:
            response = RedirectResponse(url="/assets/", status_code=status.HTTP_303_SEE_OTHER)
            set_flash(response, "Asset added successfully", "success")
            return response
        else:
            return templates.TemplateResponse(
                "asset_management/add.html",
                {
                    "request": request,
                    "user": current_profile,
                    "dropdown_options": dropdown_options,
                    "error": "Error adding asset to Google Sheets",
                    "form_data": asset_data
                },
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    from app.utils.sheets import add_approval_request
    
    approval_data = {
        'type': 'add_asset',
        'asset_id': 'NEW',
        'asset_name': item_name,
        'submitted_by': current_profile.full_name or current_profile.email,
        'submitted_date': datetime.now().strftime('%Y-%m-%d'),
        'description': f"Add new asset: {item_name}",
        'request_data': json.dumps(asset_data, ensure_ascii=False)
    }
    
    approval_success = add_approval_request(approval_data)
    
    if approval_success:
        response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, "Asset request submitted for approval", "success")
        return response
    else:
        return templates.TemplateResponse(
            "asset_management/add.html",
            {
                "request": request,
                "user": current_profile,
                "dropdown_options": dropdown_options,
                "error": "Error submitting approval request",
                "form_data": asset_data
            },
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
from fastapi import APIRouter, Request, Depends
from starlette.templating import Jinja2Templates
from app.utils.auth import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/")
async def damaged_assets_page(request: Request, current_user = Depends(get_current_user)):
    """Damaged assets page with search and log functionality"""
    from app.utils.sheets import get_all_assets, get_dropdown_options

    all_assets = get_all_assets()
    dropdown_options = get_dropdown_options()

    return templates.TemplateResponse("damaged_assets.html", {
        "request": request,
        "user": current_user,
        "assets_data": all_assets,
        "dropdown_options": dropdown_options
    })


@router.post("/lost")
async def submit_lost_report(request: Request, current_user = Depends(get_current_user)):
    """Submit lost report - syncs to Google Sheets"""
    from app.utils.sheets import add_lost_log, add_approval_request
    from datetime import datetime

    try:
        data = await request.json()

        lost_data = {
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'last_location': data.get('last_location'),
            'last_room': data.get('last_room', ''),
            'date_lost': data.get('date_lost'),
            'description': data.get('description'),
            'reported_by': current_user.full_name or current_user.email,
            'report_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'notes': data.get('notes', '')
        }

        log_success = add_lost_log(lost_data)

        approval_data = {
            'type': 'lost_report',
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'submitted_by': current_user.full_name or current_user.email,
            'submitted_date': datetime.now().strftime('%Y-%m-%d'),
            'description': f"Lost report: {data.get('description')}",
            'location': data.get('last_location')
        }

        approval_success = add_approval_request(approval_data)

        if log_success and approval_success:
            return {"status": "success", "message": "Lost report submitted and logged to Google Sheets"}
        else:
            return {"status": "error", "message": "Failed to sync with Google Sheets"}

    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/disposal")
async def submit_disposal_request(request: Request, current_user = Depends(get_current_user)):
    """Submit disposal request - syncs to Google Sheets"""
    from app.utils.sheets import add_disposal_log, add_approval_request
    from datetime import datetime

    try:
        data = await request.json()

        disposal_data = {
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'disposal_reason': data.get('disposal_reason'),
            'disposal_method': data.get('disposal_method', 'Standard'),
            'description': data.get('description'),
            'requested_by': current_user.full_name or current_user.email,
            'request_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'notes': data.get('notes', '')
        }

        log_success = add_disposal_log(disposal_data)

        approval_data = {
            'type': 'disposal_request',
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'submitted_by': current_user.full_name or current_user.email,
            'submitted_date': datetime.now().strftime('%Y-%m-%d'),
            'description': f"Disposal request: {data.get('description')}"
        }

        approval_success = add_approval_request(approval_data)

        if log_success and approval_success:
            return {"status": "success", "message": "Disposal request submitted and logged to Google Sheets"}
        else:
            return {"status": "error", "message": "Failed to sync with Google Sheets"}

    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/report")
async def submit_damage_report(request: Request, current_user = Depends(get_current_user)):
    """Submit damage report - syncs to Google Sheets"""
    from app.utils.sheets import add_damage_log, add_approval_request
    from datetime import datetime

    try:
        data = await request.json()

        damage_data = {
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'damage_type': data.get('damage_type'),
            'severity': data.get('severity'),
            'description': data.get('damage_description'),
            'reported_by': current_user.full_name or current_user.email,
            'report_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'location': data.get('location', ''),
            'room': data.get('room', ''),
            'notes': data.get('notes', '')
        }

        approval_data = {
            'type': 'damage_report',
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'submitted_by': current_user.full_name or current_user.email,
            'submitted_date': datetime.now().strftime('%Y-%m-%d'),
            'description': f"Damage report: {data.get('damage_description')}",
            'damage_type': data.get('damage_type'),
            'severity': data.get('severity')
        }

        approval_success = add_approval_request(approval_data)

        if approval_success:
            return {"status": "success", "message": "Damage report submitted for approval"}
        else:
            return {"status": "error", "message": "Failed to submit approval request"}

    except Exception as e:
        return {"status": "error", "message": str(e)}
# app/routes/disposal.py
from fastapi import APIRouter, Depends, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime

from app.database.database import get_db
from app.database.models import Profile
from app.utils.auth import get_admin_user
from app.utils.sheets import get_all_assets, update_asset, add_disposal_log
from app.utils.flash import set_flash

router = APIRouter(prefix="/disposal", tags=["disposal"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def disposal_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Disposal assets page (admin only)."""
    # Get assets that are ready to dispose only
    all_assets = get_all_assets()
    # Debug: check all statuses
    statuses = [str(asset.get('Status', '')).strip() for asset in all_assets]
    print(f"All statuses found: {set(statuses)}")
    
    disposable_assets = []
    for asset in all_assets:
        status = str(asset.get('Status', '')).strip()
        if status in ['To Be Disposed', 'To be Disposed', 'TO BE DISPOSED']:
            disposable_assets.append(asset)
    
    return templates.TemplateResponse(
        "disposal/index.html",
        {
            "request": request,
            "user": current_user,
            "assets": disposable_assets
        }
    )

@router.post("/dispose/{asset_id}")
async def dispose_asset(
    asset_id: str,
    request: Request,
    disposal_reason: str = Form(...),
    disposal_method: str = Form(...),
    description: str = Form(None),
    notes: str = Form(None),
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Dispose an asset (admin only)."""
    from app.utils.sheets import get_asset_by_id
    
    # Get asset data
    asset = get_asset_by_id(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    if str(asset.get('Status', '')).strip() != 'To Be Disposed':
        raise HTTPException(status_code=400, detail="Asset must be marked 'To Be Disposed' first")
    
    # Create disposal approval request
    from app.utils.sheets import add_approval_request
    
    approval_data = {
        'type': 'disposal',
        'asset_id': asset_id,
        'asset_name': asset.get('Item Name', ''),
        'submitted_by': current_user.full_name or current_user.email,
        'submitted_date': datetime.now().strftime('%Y-%m-%d'),
        'description': f"Disposal request: {disposal_reason} - {disposal_method}",
        'disposal_reason': disposal_reason,
        'disposal_method': disposal_method,
        'notes': f"Description: {description or ''} | Notes: {notes or ''}"
    }
    
    approval_success = add_approval_request(approval_data)
    
    if approval_success:
        response = RedirectResponse(url="/disposal", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, f"Disposal request for {asset.get('Item Name', '')} submitted for manager approval", "success")
        return response
    else:
        response = RedirectResponse(url="/disposal", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, "Error submitting disposal request", "error")
        return response
# app/routes/health.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
import time

from app.database.database import get_db
from app.config import load_config

router = APIRouter(tags=["health"])
config = load_config()

@router.get("/health")
async def health_check(db: Session = Depends(get_db)):
    """Health check endpoint."""
    start_time = time.time()
    
    # Check database connection
    try:
        db.execute(text("SELECT 1"))
        db_status = "healthy"
    except Exception as e:
        db_status = f"unhealthy: {str(e)}"
    
    # Check Google Sheets API
    sheets_status = "configured" if config.GOOGLE_SHEET_ID else "not configured"
    
    # Response time
    response_time = time.time() - start_time
    
    return {
        "status": "ok",
        "database": db_status,
        "google_sheets": sheets_status,
        "response_time_ms": round(response_time * 1000, 2)
    }
# /app/app/routes/home.py
import logging
from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse
from starlette.templating import Jinja2Templates
from app.utils.auth import get_current_user
from app.utils.sheets import get_summary_data, get_chart_data, get_all_assets

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=RedirectResponse)
async def redirect_root():
    return RedirectResponse("/dashboard")

@router.get("/dashboard")
async def home(request: Request, current_user = Depends(get_current_user)):
    try:
        # Summary and chart data
        summary_data = get_summary_data()
        chart_data = get_chart_data()
        all_assets = get_all_assets()

        # Filter out disposed assets for dashboard counts
        active_assets = [asset for asset in all_assets if asset.get("Status", "") != "Disposed"]
        disposed_assets = [asset for asset in all_assets if asset.get("Status", "") == "Disposed"]
        
        # Count assets by status and activity
        total_assets = len(active_assets)
        disposed_count = len(disposed_assets)
        damaged_count = len([a for a in all_assets if a.get("Status", "") == "Under Repair"])
        
        # Count assets by activity type
        relocated_count = len([a for a in all_assets if a.get("Last Activity", "") == "Relocated"])
        repaired_count = len([a for a in all_assets if a.get("Last Activity", "") == "Repaired"])
        to_be_disposed_count = len([a for a in all_assets if a.get("Status", "") == "To Be Disposed"])
        
        # Helper function to safely convert values to float
        def safe_float(value):
            if value is None or value == '':
                return 0.0
            try:
                return float(value)
            except (ValueError, TypeError):
                return 0.0
        
        # Calculate financial values directly from assets
        total_purchase_value = sum(safe_float(asset.get("Purchase Cost")) for asset in active_assets)
        total_book_value = sum(safe_float(asset.get("Book Value")) for asset in active_assets)
        # Calculate depreciation as purchase value minus book value
        total_depreciation_value = total_purchase_value - total_book_value
        category_counts = chart_data.get("category_counts", {})
        
        # Format location data
        location_data = chart_data.get("location_chart_data", {})
        location_counts = location_data.get("labels", [])
        location_values = location_data.get("values", [])
        location_counts_dict = dict(zip(location_counts, location_values))

        # Format time-based chart data
        monthly_data = chart_data.get("monthly_chart_data", {})
        monthly_chart_labels = monthly_data.get("labels", [])
        monthly_chart_values = monthly_data.get("values", [])
        
        # Generate quarterly data (last 12 quarters - 3 years)
        quarterly_chart_labels = []
        quarterly_chart_values = []
        
        # Get current year and quarter
        from datetime import datetime
        current_date = datetime.now()
        current_year = current_date.year
        current_quarter = (current_date.month - 1) // 3 + 1
        
        # Generate data for the last 12 quarters
        for i in range(11, -1, -1):
            year = current_year
            quarter = current_quarter - i
            
            # Adjust year if quarter is negative or > 4
            while quarter <= 0:
                year -= 1
                quarter += 4
            while quarter > 4:
                year += 1
                quarter -= 4
                
            quarterly_chart_labels.append(f"Q{quarter} {year}")
            
            # Count assets added in this quarter
            quarter_start_month = (quarter - 1) * 3 + 1
            quarter_end_month = quarter * 3
            
            count = 0
            for asset in all_assets:
                purchase_date = asset.get("Purchase Date", "")
                if purchase_date:
                    try:
                        date = datetime.strptime(purchase_date, "%Y-%m-%d")
                        if date.year == year and quarter_start_month <= date.month <= quarter_end_month:
                            count += 1
                    except:
                        pass
            
            quarterly_chart_values.append(count)
        
        # Generate yearly data (last 5 years)
        yearly_chart_labels = []
        yearly_chart_values = []
        
        # Generate data for the last 5 years
        for i in range(4, -1, -1):
            year = current_year - i
            yearly_chart_labels.append(str(year))
            
            # Count assets added in this year
            count = 0
            for asset in all_assets:
                purchase_date = asset.get("Purchase Date", "")
                if purchase_date:
                    try:
                        date = datetime.strptime(purchase_date, "%Y-%m-%d")
                        if date.year == year:
                            count += 1
                    except:
                        pass
            
            yearly_chart_values.append(count)

        # Format age distribution - convert to list of tuples for proper serialization
        age_distribution = chart_data.get("age_distribution", {})
        age_distribution_list = [
            {"label": str(k), "value": int(v)} 
            for k, v in age_distribution.items()
        ]

        # Format latest assets (excluding disposed assets)
        latest_assets = sorted(
            active_assets, 
            key=lambda a: a.get("Purchase Date", ""), 
            reverse=True
        )[:10]
        
        # Process assets to ensure they have a display_name field
        for asset in latest_assets:
            # Try different possible field names for the asset name
            name_fields = ["Name", "Asset Name", "AssetName", "Item Name", "Description", "Item"]
            display_name = None
            
            for field in name_fields:
                if asset.get(field):
                    display_name = asset.get(field)
                    break
            
            # If no name found, use a default
            if not display_name:
                display_name = f"Asset #{asset.get('ID', 'Unknown')}"
                
            # Add the display_name to the asset
            asset["display_name"] = display_name
            
        # Debug: Print the first asset's keys to see what fields are available
        if latest_assets:
            logging.info(f"Asset keys: {list(latest_assets[0].keys())}")
            logging.info(f"Asset display name: {latest_assets[0].get('display_name', 'Not found')}")
            logging.info(f"Original asset name fields: {[latest_assets[0].get(f, 'None') for f in name_fields]}")

        context = {
            "request": request,
            "user": current_user,
            "total_assets": total_assets,
            "total_purchase_value": total_purchase_value,
            "total_book_value": total_book_value,
            "total_depreciation_value": total_depreciation_value,
            "disposed_count": disposed_count,
            "damaged_count": damaged_count,
            "relocated_count": relocated_count,
            "repaired_count": repaired_count,
            "to_be_disposed_count": to_be_disposed_count,
            "category_counts": category_counts,
            "location_counts": location_counts_dict,
            "monthly_chart_labels": monthly_chart_labels,
            "monthly_chart_values": monthly_chart_values,
            "quarterly_chart_labels": quarterly_chart_labels,
            "quarterly_chart_values": quarterly_chart_values,
            "yearly_chart_labels": yearly_chart_labels,
            "yearly_chart_values": yearly_chart_values,
            "age_distribution": age_distribution_list,
            "latest_assets": latest_assets
        }

        return templates.TemplateResponse("dashboard.html", context)

    except Exception as e:
        logging.error("Dashboard error: %s", e, exc_info=True)
        return templates.TemplateResponse("error.html", {
            "request": request,
            "user": current_user,
            "message": "Terjadi kesalahan saat memuat dashboard.",
        })
from fastapi import APIRouter, Request, Response, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from supabase import create_client, Client
from app.config import load_config
import logging

config = load_config()
supabase: Client = create_client(config.SUPABASE_URL, config.SUPABASE_ANON_KEY)

router = APIRouter(tags=["authentication"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/login", response_class=HTMLResponse)
@router.head("/login", response_class=HTMLResponse)
async def login_page(request: Request, next: str = None):
    return templates.TemplateResponse("login_logout.html", {"request": request, "next": next})

@router.post("/login", response_class=HTMLResponse)
async def login_form(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    next: str = Form(None)
):
    try:
        # Use service key client for admin operations
        from supabase import create_client
        admin_supabase = create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_KEY)
        
        response = admin_supabase.auth.sign_in_with_password({
            "email": email,
            "password": password
        })
        
        if not response.user:
            return templates.TemplateResponse(
                "login_logout.html",
                {"request": request, "error": "Invalid email or password", "next": next},
                status_code=401
            )
        
        # Get user profile
        profile_response = admin_supabase.table('profiles').select('*').eq('id', response.user.id).single().execute()
        if not profile_response.data or not profile_response.data.get('is_active'):
            return templates.TemplateResponse(
                "login_logout.html",
                {"request": request, "error": "Account is inactive", "next": next},
                status_code=401
            )
        
        redirect_url = next if next else "/"
        redirect_response = RedirectResponse(url=redirect_url, status_code=303)
        
        redirect_response.set_cookie(
            key="sb_access_token",
            value=response.session.access_token,
            httponly=True,
            max_age=3600,
            samesite="lax",
            secure=True,
            domain=".onrender.com"
        )
        
        return redirect_response
        
    except Exception as e:
        logging.error(f"Login error: {str(e)}")
        return templates.TemplateResponse(
            "login_logout.html",
            {"request": request, "error": "Login failed", "next": next},
            status_code=401
        )

@router.get("/auth/callback")
async def auth_callback(request: Request):
    return templates.TemplateResponse("auth_callback.html", {"request": request})

@router.get("/logout")
async def logout():
    try:
        supabase.auth.sign_out()
    except:
        pass
    
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(key="sb_access_token")
    return response
# app/routes/logs.py
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.database.models import Profile
from app.utils.auth import get_current_user
from app.utils.sheets import get_all_approvals

router = APIRouter(prefix="/logs", tags=["logs"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def logs_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """View approval logs based on user role."""
    all_approvals = get_all_approvals()
    
    # Filter based on user role
    if current_user.role.value == 'staff':
        # Staff can only see their own requests
        user_identifier = current_user.full_name or current_user.email
        approvals = [a for a in all_approvals if a.get('Submitted_By') == user_identifier]
    else:
        # Manager and admin can see all approvals
        approvals = all_approvals
    
    # Separate pending and completed
    pending_approvals = [a for a in approvals if a.get('Status') == 'Pending']
    completed_approvals = [a for a in approvals if a.get('Status') in ['Approved', 'Rejected']]
    
    return templates.TemplateResponse(
        "logs/index.html",
        {
            "request": request,
            "user": current_user,
            "pending_approvals": pending_approvals,
            "completed_approvals": completed_approvals
        }
    )
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
from fastapi import APIRouter, Depends, Request, Form, UploadFile, File, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from app.database.database import get_db
from app.database.models import Profile
from app.utils.auth import get_current_user
from app.utils.photo import resize_and_convert_image, upload_to_drive
from app.utils.flash import set_flash

router = APIRouter(tags=["profile"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/profile", response_class=HTMLResponse)
async def profile_page(
    request: Request,
    current_user = Depends(get_current_user)
):
    """User profile page."""
    return templates.TemplateResponse(
        "profile/view.html",
        {
            "request": request,
            "user": current_user
        }
    )

@router.get("/profile/edit", response_class=HTMLResponse)
async def edit_profile_page(
    request: Request,
    current_user = Depends(get_current_user)
):
    """Edit user profile page."""
    return templates.TemplateResponse(
        "profile/edit.html",
        {
            "request": request,
            "user": current_user
        }
    )

@router.post("/profile/edit")
async def update_profile(
    request: Request,
    full_name: str = Form(...),
    email: str = Form(...),
    photo: UploadFile = File(None),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Update user profile."""
    # Update basic info
    current_user.full_name = full_name
    current_user.email = email
    current_user.updated_at = datetime.now(timezone.utc)
    
    # Handle photo upload if provided
    if photo and photo.filename:
        try:
            # Process image
            contents = await photo.read()
            import io
            image_file = io.BytesIO(contents)
            processed_image = resize_and_convert_image(image_file)
            
            if processed_image:
                # Upload to Google Drive
                photo_url = upload_to_drive(
                    processed_image, 
                    photo.filename, 
                    f"profile_{current_user.email}"
                )
                if photo_url:
                    current_user.photo_url = photo_url
        except Exception as e:
            return templates.TemplateResponse(
                "profile/edit.html",
                {
                    "request": request,
                    "user": current_user,
                    "error": f"Error uploading photo: {str(e)}"
                },
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    # Save changes
    db.commit()
    
    # Redirect to profile page
    response = RedirectResponse(url="/profile", status_code=status.HTTP_303_SEE_OTHER)
    set_flash(response, "Profile updated successfully", "success")
    return response
# app/routes/relocation.py
from fastapi import APIRouter, Depends, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime
import json

from app.database.database import get_db
from app.database.models import Profile
from app.utils.auth import get_current_user
from app.utils.sheets import get_all_assets, get_dropdown_options, add_approval_request
from app.utils.flash import set_flash

router = APIRouter(prefix="/relocation", tags=["relocation"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def relocation_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Asset relocation page."""
    # Get assets and dropdown options
    all_assets = get_all_assets()
    dropdown_options = get_dropdown_options()
    
    return templates.TemplateResponse(
        "relocation/index.html",
        {
            "request": request,
            "user": current_user,
            "assets": all_assets,
            "dropdown_options": dropdown_options
        }
    )

@router.post("/relocate/{asset_id}")
async def relocate_asset(
    asset_id: str,
    request: Request,
    new_location: str = Form(...),
    new_room: str = Form(...),
    reason: str = Form(...),
    notes: str = Form(None),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Submit asset relocation request."""
    from app.utils.sheets import get_asset_by_id
    
    # Get asset data
    asset = get_asset_by_id(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    # Create relocation approval request
    relocation_data = {
        'new_location': new_location,
        'new_room': new_room,
        'current_location': asset.get('Location', ''),
        'current_room': asset.get('Room', ''),
        'reason': reason,
        'notes': notes or ''
    }
    
    approval_data = {
        'type': 'relocation',
        'asset_id': asset_id,
        'asset_name': asset.get('Item Name', ''),
        'submitted_by': current_user.full_name or current_user.email,
        'submitted_date': datetime.now().strftime('%Y-%m-%d'),
        'description': f"Relocate from {asset.get('Location', '')} - {asset.get('Room', '')} to {new_location} - {new_room}",
        'request_data': json.dumps(relocation_data, ensure_ascii=False)
    }
    
    approval_success = add_approval_request(approval_data)
    
    if approval_success:
        response = RedirectResponse(url="/relocation", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, f"Relocation request for {asset.get('Item Name', '')} submitted for approval", "success")
        return response
    else:
        response = RedirectResponse(url="/relocation", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, "Error submitting relocation request", "error")
        return response
# /app/app/routes/repair.py
from fastapi import APIRouter, Request, Depends
from starlette.templating import Jinja2Templates
from app.utils.auth import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.post("/action")
async def submit_repair_action(request: Request, current_user = Depends(get_current_user)):
    """Submit repair action - creates approval request for store, direct action for allocate"""
    from app.utils.sheets import add_repair_log, update_asset, add_approval_request
    from datetime import datetime
    
    try:
        # Get JSON data
        data = await request.json()
        action_type = data.get('action_type')  # 'store' or 'allocate'
        
        if action_type == 'store':
            # Store action requires approval - only create approval request
            approval_data = {
                'type': 'repair_action',
                'asset_id': data.get('asset_id'),
                'asset_name': data.get('asset_name'),
                'submitted_by': current_user.full_name or current_user.email,
                'submitted_date': datetime.now().strftime('%Y-%m-%d'),
                'description': f"Request to store asset: {data.get('description')}",
                'action': 'Store Asset'
            }
            
            approval_success = add_approval_request(approval_data)
            
            if approval_success:
                return {"status": "success", "message": "Store request submitted for admin approval"}
            else:
                return {"status": "error", "message": "Failed to submit approval request"}
        
        else:  # allocate - direct action
            # Add to Repair_Log sheet
            repair_data = {
                'asset_id': data.get('asset_id'),
                'asset_name': data.get('asset_name'),
                'repair_action': 'Allocate Asset',
                'action_type': action_type,
                'description': data.get('description', ''),
                'performed_by': current_user.full_name or current_user.email,
                'action_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'new_location': data.get('location', ''),
                'new_room': data.get('room', ''),
                'notes': data.get('notes', '')
            }
            
            # Add to repair log
            log_success = add_repair_log(repair_data)
            
            # Update asset from Under Repair to Active
            update_data = {
                'Status': 'Active',
                'Bisnis Unit': data.get('business_unit', ''),
                'Location': data.get('location', ''),
                'Room': data.get('room', '')
            }
            
            asset_success = update_asset(data.get('asset_id'), update_data)
            
            if log_success and asset_success:
                return {"status": "success", "message": "Asset allocated successfully and synced to Google Sheets"}
            else:
                return {"status": "error", "message": "Failed to sync with Google Sheets"}
            
    except Exception as e:
        return {"status": "error", "message": str(e)}
# app/routes/user_management.py
from fastapi import APIRouter, Depends, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.database.models import Profile, UserRole
from app.utils.auth import get_current_user, get_admin_user
from app.utils.flash import set_flash

router = APIRouter(prefix="/user_management", tags=["user_management"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def user_list(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """List all users (admin only)."""
    users = db.query(Profile).all()
    
    return templates.TemplateResponse(
        "user_management/list.html",
        {
            "request": request,
            "user": current_user,
            "users": users
        }
    )

@router.get("/create", response_class=HTMLResponse)
async def create_user_form(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Create user form (admin only)."""
    return templates.TemplateResponse(
        "user_management/create.html",
        {
            "request": request,
            "user": current_user
        }
    )

@router.post("/create")
async def create_user(
    request: Request,
    email: str = Form(...),
    full_name: str = Form(...),
    role: str = Form(...),
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Create new user (admin only)."""
    # Check if user exists
    existing_user = db.query(Profile).filter(Profile.email == email).first()
    if existing_user:
        return templates.TemplateResponse(
            "user_management/create.html",
            {
                "request": request,
                "user": current_user,
                "error": "Email already exists"
            }
        )
    
    # Create user profile (Supabase handles auth)
    new_user = Profile(
        email=email,
        full_name=full_name,
        role=getattr(UserRole, role.upper()),
        is_active=True
    )
    
    db.add(new_user)
    db.commit()
    
    response = RedirectResponse(url="/user_management", status_code=status.HTTP_303_SEE_OTHER)
    set_flash(response, f"User {email} created successfully", "success")
    return response

@router.post("/reset_password/{user_id}")
async def reset_password(
    user_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Reset user password to default (admin only)."""
    user = db.query(Profile).filter(Profile.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Password reset handled by Supabase
    default_password = f"{user.email.split('@')[0]}123"
    
    response = RedirectResponse(url="/user_management", status_code=status.HTTP_303_SEE_OTHER)
    set_flash(response, f"Password reset instructions sent to {user.email}", "success")
    return response

@router.post("/toggle_status/{user_id}")
async def toggle_user_status(
    user_id: str,
    request: Request,
    is_active: bool = Form(...),
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Toggle user active status (admin only)."""
    user = db.query(Profile).filter(Profile.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Update status
    user.is_active = is_active
    db.commit()
    
    status_text = "activated" if is_active else "deactivated"
    response = RedirectResponse(url="/user_management", status_code=status.HTTP_303_SEE_OTHER)
    set_flash(response, f"User {user.email} {status_text}", "success")
    return response
# app/routes/__init__.py

# Import all route modules to make them available from app.routes
from app.routes import (
    home,
    assets,
    asset_management,
    login,
    damage,
    health,
    offline,
    profile,
    repair,
    approvals,
    disposal,
    user_management,
    logs,
    relocation
)
# app/routes/approvals.py
from fastapi import APIRouter, Depends, Request, HTTPException, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.utils.auth import get_current_user
from app.utils.sheets import get_all_approvals, update_approval_status

router = APIRouter(prefix="/approvals", tags=["approvals"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def approvals_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Approvals page for admin and manager."""
    if current_user.role not in ['admin', 'manager']:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get all approvals from Google Sheets
    all_approvals = get_all_approvals()
    
    # Filter approvals based on user role
    if current_user.role == 'admin':
        # Admin sees all approvals except disposal and edit_asset
        approvals_data = [a for a in all_approvals if a.get('Type') not in ['disposal', 'edit_asset']]
    elif current_user.role == 'manager':
        # Manager sees disposal and edit_asset approvals
        approvals_data = [a for a in all_approvals if a.get('Type') in ['disposal', 'edit_asset']]
    else:
        approvals_data = []
    
    return templates.TemplateResponse(
        "approvals/list.html",
        {
            "request": request,
            "user": current_user,
            "approvals_data": approvals_data
        }
    )

@router.post("/approve/{approval_id}")
async def approve_request(
    approval_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Approve a request."""
    if current_user.role not in ['admin', 'manager']:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get approval details
    all_approvals = get_all_approvals()
    approval = next((a for a in all_approvals if str(a.get('ID')) == str(approval_id)), None)
    
    if not approval:
        return JSONResponse({"status": "error", "message": "Approval not found"})
    
    # Process approval based on type
    try:
        if approval.get('Type') == 'damage_report':
            # Update asset status to "Under Repair"
            from app.utils.sheets import update_asset
            success = update_asset(approval.get('Asset_ID'), {'Status': 'Under Repair'})
            if not success:
                return JSONResponse({"status": "error", "message": "Failed to update asset status"})
        
        elif approval.get('Type') == 'relocation':
            # Process relocation approval
            import json
            try:
                request_data_str = approval.get('Request_Data', '')
                if request_data_str:
                    relocation_data = json.loads(request_data_str)
                    update_data = {
                        'Location': relocation_data.get('new_location'),
                        'Room': relocation_data.get('new_room')
                    }
                    from app.utils.sheets import update_asset
                    success = update_asset(approval.get('Asset_ID'), update_data)
                    if not success:
                        return JSONResponse({"status": "error", "message": "Failed to relocate asset"})
            except Exception as e:
                return JSONResponse({"status": "error", "message": f"Error processing relocation: {str(e)}"})
            
        elif approval.get('Type') == 'edit_asset':
            # Process edit asset approval
            import json
            try:
                request_data_str = approval.get('Request_Data', '')
                if request_data_str:
                    edit_data = json.loads(request_data_str)
                    from app.utils.sheets import update_asset
                    success = update_asset(approval.get('Asset_ID'), edit_data)
                    if not success:
                        return JSONResponse({"status": "error", "message": "Failed to update asset"})
            except Exception as e:
                return JSONResponse({"status": "error", "message": f"Error processing edit: {str(e)}"})
        
        # Update approval status
        approval_update = {
            'Status': 'Approved',
            'Approved_By': current_user.full_name or current_user.email,
            'Approved_Date': __import__('datetime').datetime.now().strftime('%Y-%m-%d')
        }
        
        success = update_approval_status(approval_id, approval_update)
        
        if success:
            return JSONResponse({"status": "success", "message": "Request approved successfully"})
        else:
            return JSONResponse({"status": "error", "message": "Failed to update approval status"})
            
    except Exception as e:
        return JSONResponse({"status": "error", "message": f"Error processing approval: {str(e)}"})

@router.post("/reject/{approval_id}")
async def reject_request(
    approval_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Reject a request."""
    if current_user.role not in ['admin', 'manager']:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Update approval status
    approval_update = {
        'Status': 'Rejected',
        'Approved_By': current_user.full_name or current_user.email,
        'Approved_Date': __import__('datetime').datetime.now().strftime('%Y-%m-%d')
    }
    
    success = update_approval_status(approval_id, approval_update)
    
    if success:
        return JSONResponse({"status": "success", "message": "Request rejected"})
    else:
        return JSONResponse({"status": "error", "message": "Failed to update approval status"})
from fastapi import APIRouter, Request, Depends
from starlette.templating import Jinja2Templates
from app.utils.auth import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/assets")
async def assets_page(request: Request, current_user=Depends(get_current_user)):
    """Assets listing page with filtering and pagination"""
    from app.utils.sheets import get_all_assets
    
    # Ambil data asset dari Google Sheets
    all_assets = get_all_assets()
    
    # Filter hanya aset aktif (bukan Disposed)
    active_assets = [asset for asset in all_assets if asset.get("Status", "").lower() != "disposed"]
    
    return templates.TemplateResponse("assets.html", {
        "request": request,
        "user": current_user,
        "assets_data": active_assets
    })
# app/routes/asset_management.py
from fastapi import APIRouter, Depends, Request, Form, File, UploadFile, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import json
from datetime import datetime
import io

from app.database.database import get_db
from app.database.models import Profile, UserRole
from app.utils.photo import resize_and_convert_image, upload_to_drive
from app.utils.sheets import get_dropdown_options, add_asset as sheets_add_asset
from app.utils.flash import set_flash
from app.utils.auth import get_current_user, get_admin_user
from app.config import load_config

config = load_config()
router = APIRouter(prefix="/asset_management", tags=["asset_management"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/add", response_class=HTMLResponse)
async def add_asset_form(
    request: Request,
    db: Session = Depends(get_db),
    current_profile = Depends(get_current_user)
):
    """Form to add a new asset."""
    dropdown_options = get_dropdown_options()
    return templates.TemplateResponse(
        "asset_management/add.html",
        {
            "request": request,
            "user": current_profile,
            "dropdown_options": dropdown_options
        }
    )


@router.get("/list", response_class=HTMLResponse)
async def asset_list(
    request: Request,
    db: Session = Depends(get_db),
    current_profile = Depends(get_current_user)
):
    """List assets for editing (admin and manager only)."""
    if current_profile.role not in [UserRole.ADMIN, UserRole.MANAGER]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    from app.utils.sheets import get_all_assets
    assets = get_all_assets()
    
    locations = list(set(asset.get('Location', '') for asset in assets if asset.get('Location')))
    location_rooms = {}
    for asset in assets:
        location = asset.get('Location', '')
        room = asset.get('Room', '')
        if location and room:
            if location not in location_rooms:
                location_rooms[location] = set()
            location_rooms[location].add(room)
    
    for location in location_rooms:
        location_rooms[location] = list(location_rooms[location])
    
    return templates.TemplateResponse(
        "asset_management/list.html",
        {
            "request": request,
            "user": current_profile,
            "assets": assets,
            "locations": sorted(locations),
            "location_rooms": location_rooms
        }
    )


@router.get("/edit/{asset_id}", response_class=HTMLResponse)
async def edit_asset_form(
    asset_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_profile = Depends(get_current_user)
):
    """Form to edit an existing asset (admin/manager only)."""
    if current_profile.role not in [UserRole.ADMIN, UserRole.MANAGER]:
        raise HTTPException(status_code=403, detail="Access denied")

    from app.utils.sheets import get_asset_by_id
    asset = get_asset_by_id(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    dropdown_options = get_dropdown_options()
    
    return templates.TemplateResponse(
        "asset_management/edit.html",
        {
            "request": request,
            "user": current_profile,
            "asset": asset,
            "dropdown_options": dropdown_options
        }
    )


@router.post("/edit/{asset_id}")
async def update_asset(
    asset_id: str,
    request: Request,
    status: str = Form(...),
    company: str = Form(...),
    location: str = Form(...),
    room: str = Form(...),
    bisnis_unit: str = Form(None),
    edit_reason: str = Form(...),
    db: Session = Depends(get_db),
    current_profile = Depends(get_current_user)
):
    """Update existing asset (admin and manager only)."""
    if current_profile.role not in [UserRole.ADMIN, UserRole.MANAGER]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    from app.utils.sheets import update_asset as sheets_update_asset, calculate_asset_financials, get_asset_by_id
    asset = get_asset_by_id(asset_id)

    update_data = {
        "Status": status,
        "Company": company,
        "Location": location,
        "Room": room,
        "Bisnis Unit": bisnis_unit or ""
    }
    
    # Jika perlu hitung ulang nilai finansial, misalnya setelah perubahan harga
    # financials = calculate_asset_financials(purchase_cost, purchase_date, category)
    # update_data.update(financials)
    
    from app.utils.sheets import add_approval_request
    
    approval_data = {
        'type': 'edit_asset',
        'asset_id': asset_id,
        'asset_name': asset.get('Item Name', ''),
        'submitted_by': current_profile.full_name or current_profile.email,
        'submitted_date': datetime.now().strftime('%Y-%m-%d'),
        'description': f"Edit asset: {asset.get('Item Name', '')} - Reason: {edit_reason}",
        'edit_reason': edit_reason,
        'request_data': json.dumps(update_data, ensure_ascii=False)
    }
    
    approval_success = add_approval_request(approval_data)
    
    if approval_success:
        response = RedirectResponse(url="/asset_management/list", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, "Asset edit request submitted for manager approval", "success")
        return response
    else:
        dropdown_options = get_dropdown_options()
        return templates.TemplateResponse(
            "asset_management/edit.html",
            {
                "request": request,
                "user": current_profile,
                "asset": asset,
                "dropdown_options": dropdown_options,
                "error": "Error submitting edit request"
            },
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@router.post("/add")
async def add_asset(
    request: Request,
    item_name: str = Form(...),
    category: str = Form(...),
    type: str = Form(...),
    manufacture: str = Form(None),
    model: str = Form(None),
    serial_number: str = Form(None),
    company: str = Form(...),
    bisnis_unit: str = Form(None),
    location: str = Form(...),
    room: str = Form(...),
    notes: str = Form(None),
    item_condition: str = Form(None),
    purchase_date: str = Form(...),
    purchase_cost: str = Form(...),
    warranty: str = Form(None),
    supplier: str = Form(None),
    journal: str = Form(None),
    owner: str = Form(...),
    photo: UploadFile = File(None),
    db: Session = Depends(get_db),
    current_profile = Depends(get_current_user)
):
    """Process add asset form."""
    dropdown_options = get_dropdown_options()
    
    asset_data = {
        "Item Name": item_name,
        "Category": category,
        "Type": type,
        "Manufacture": manufacture or "",
        "Model": model or "",
        "Serial Number": serial_number or "",
        "Company": company,
        "Bisnis Unit": bisnis_unit or "",
        "Location": location,
        "Room": room,
        "Notes": notes or "",
        "Item Condition": item_condition or "",
        "Purchase Date": purchase_date,
        "Purchase Cost": purchase_cost,
        "Warranty": warranty or "",
        "Supplier": supplier or "",
        "Journal": journal or "",
        "Owner": owner,
        "Status": "Active"
    }
    
    photo_url = None
    if photo and photo.filename:
        try:
            contents = await photo.read()
            image_file = io.BytesIO(contents)
            processed_image = resize_and_convert_image(image_file)
            
            if processed_image:
                photo_url = upload_to_drive(processed_image, photo.filename, "new")
                if photo_url:
                    asset_data["Photo URL"] = photo_url
        except Exception as e:
            print(f"Error processing photo: {str(e)}")
    
    if current_profile.role == UserRole.ADMIN:
        success = sheets_add_asset(asset_data)
        
        if success:
            response = RedirectResponse(url="/assets/", status_code=status.HTTP_303_SEE_OTHER)
            set_flash(response, "Asset added successfully", "success")
            return response
        else:
            return templates.TemplateResponse(
                "asset_management/add.html",
                {
                    "request": request,
                    "user": current_profile,
                    "dropdown_options": dropdown_options,
                    "error": "Error adding asset to Google Sheets",
                    "form_data": asset_data
                },
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    from app.utils.sheets import add_approval_request
    
    approval_data = {
        'type': 'add_asset',
        'asset_id': 'NEW',
        'asset_name': item_name,
        'submitted_by': current_profile.full_name or current_profile.email,
        'submitted_date': datetime.now().strftime('%Y-%m-%d'),
        'description': f"Add new asset: {item_name}",
        'request_data': json.dumps(asset_data, ensure_ascii=False)
    }
    
    approval_success = add_approval_request(approval_data)
    
    if approval_success:
        response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, "Asset request submitted for approval", "success")
        return response
    else:
        return templates.TemplateResponse(
            "asset_management/add.html",
            {
                "request": request,
                "user": current_profile,
                "dropdown_options": dropdown_options,
                "error": "Error submitting approval request",
                "form_data": asset_data
            },
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
from fastapi import APIRouter, Request, Depends
from starlette.templating import Jinja2Templates
from app.utils.auth import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/")
async def damaged_assets_page(request: Request, current_user = Depends(get_current_user)):
    """Damaged assets page with search and log functionality"""
    from app.utils.sheets import get_all_assets, get_dropdown_options

    all_assets = get_all_assets()
    dropdown_options = get_dropdown_options()

    return templates.TemplateResponse("damaged_assets.html", {
        "request": request,
        "user": current_user,
        "assets_data": all_assets,
        "dropdown_options": dropdown_options
    })


@router.post("/lost")
async def submit_lost_report(request: Request, current_user = Depends(get_current_user)):
    """Submit lost report - syncs to Google Sheets"""
    from app.utils.sheets import add_lost_log, add_approval_request
    from datetime import datetime

    try:
        data = await request.json()

        lost_data = {
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'last_location': data.get('last_location'),
            'last_room': data.get('last_room', ''),
            'date_lost': data.get('date_lost'),
            'description': data.get('description'),
            'reported_by': current_user.full_name or current_user.email,
            'report_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'notes': data.get('notes', '')
        }

        log_success = add_lost_log(lost_data)

        approval_data = {
            'type': 'lost_report',
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'submitted_by': current_user.full_name or current_user.email,
            'submitted_date': datetime.now().strftime('%Y-%m-%d'),
            'description': f"Lost report: {data.get('description')}",
            'location': data.get('last_location')
        }

        approval_success = add_approval_request(approval_data)

        if log_success and approval_success:
            return {"status": "success", "message": "Lost report submitted and logged to Google Sheets"}
        else:
            return {"status": "error", "message": "Failed to sync with Google Sheets"}

    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/disposal")
async def submit_disposal_request(request: Request, current_user = Depends(get_current_user)):
    """Submit disposal request - syncs to Google Sheets"""
    from app.utils.sheets import add_disposal_log, add_approval_request
    from datetime import datetime

    try:
        data = await request.json()

        disposal_data = {
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'disposal_reason': data.get('disposal_reason'),
            'disposal_method': data.get('disposal_method', 'Standard'),
            'description': data.get('description'),
            'requested_by': current_user.full_name or current_user.email,
            'request_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'notes': data.get('notes', '')
        }

        log_success = add_disposal_log(disposal_data)

        approval_data = {
            'type': 'disposal_request',
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'submitted_by': current_user.full_name or current_user.email,
            'submitted_date': datetime.now().strftime('%Y-%m-%d'),
            'description': f"Disposal request: {data.get('description')}"
        }

        approval_success = add_approval_request(approval_data)

        if log_success and approval_success:
            return {"status": "success", "message": "Disposal request submitted and logged to Google Sheets"}
        else:
            return {"status": "error", "message": "Failed to sync with Google Sheets"}

    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/report")
async def submit_damage_report(request: Request, current_user = Depends(get_current_user)):
    """Submit damage report - syncs to Google Sheets"""
    from app.utils.sheets import add_damage_log, add_approval_request
    from datetime import datetime

    try:
        data = await request.json()

        damage_data = {
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'damage_type': data.get('damage_type'),
            'severity': data.get('severity'),
            'description': data.get('damage_description'),
            'reported_by': current_user.full_name or current_user.email,
            'report_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'location': data.get('location', ''),
            'room': data.get('room', ''),
            'notes': data.get('notes', '')
        }

        approval_data = {
            'type': 'damage_report',
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'submitted_by': current_user.full_name or current_user.email,
            'submitted_date': datetime.now().strftime('%Y-%m-%d'),
            'description': f"Damage report: {data.get('damage_description')}",
            'damage_type': data.get('damage_type'),
            'severity': data.get('severity')
        }

        approval_success = add_approval_request(approval_data)

        if approval_success:
            return {"status": "success", "message": "Damage report submitted for approval"}
        else:
            return {"status": "error", "message": "Failed to submit approval request"}

    except Exception as e:
        return {"status": "error", "message": str(e)}
# app/routes/disposal.py
from fastapi import APIRouter, Depends, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime

from app.database.database import get_db
from app.database.models import Profile
from app.utils.auth import get_admin_user
from app.utils.sheets import get_all_assets, update_asset, add_disposal_log
from app.utils.flash import set_flash

router = APIRouter(prefix="/disposal", tags=["disposal"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def disposal_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Disposal assets page (admin only)."""
    # Get assets that are ready to dispose only
    all_assets = get_all_assets()
    # Debug: check all statuses
    statuses = [str(asset.get('Status', '')).strip() for asset in all_assets]
    print(f"All statuses found: {set(statuses)}")
    
    disposable_assets = []
    for asset in all_assets:
        status = str(asset.get('Status', '')).strip()
        if status in ['To Be Disposed', 'To be Disposed', 'TO BE DISPOSED']:
            disposable_assets.append(asset)
    
    return templates.TemplateResponse(
        "disposal/index.html",
        {
            "request": request,
            "user": current_user,
            "assets": disposable_assets
        }
    )

@router.post("/dispose/{asset_id}")
async def dispose_asset(
    asset_id: str,
    request: Request,
    disposal_reason: str = Form(...),
    disposal_method: str = Form(...),
    description: str = Form(None),
    notes: str = Form(None),
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Dispose an asset (admin only)."""
    from app.utils.sheets import get_asset_by_id
    
    # Get asset data
    asset = get_asset_by_id(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    if str(asset.get('Status', '')).strip() != 'To Be Disposed':
        raise HTTPException(status_code=400, detail="Asset must be marked 'To Be Disposed' first")
    
    # Create disposal approval request
    from app.utils.sheets import add_approval_request
    
    approval_data = {
        'type': 'disposal',
        'asset_id': asset_id,
        'asset_name': asset.get('Item Name', ''),
        'submitted_by': current_user.full_name or current_user.email,
        'submitted_date': datetime.now().strftime('%Y-%m-%d'),
        'description': f"Disposal request: {disposal_reason} - {disposal_method}",
        'disposal_reason': disposal_reason,
        'disposal_method': disposal_method,
        'notes': f"Description: {description or ''} | Notes: {notes or ''}"
    }
    
    approval_success = add_approval_request(approval_data)
    
    if approval_success:
        response = RedirectResponse(url="/disposal", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, f"Disposal request for {asset.get('Item Name', '')} submitted for manager approval", "success")
        return response
    else:
        response = RedirectResponse(url="/disposal", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, "Error submitting disposal request", "error")
        return response
# app/routes/health.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
import time

from app.database.database import get_db
from app.config import load_config

router = APIRouter(tags=["health"])
config = load_config()

@router.get("/health")
async def health_check(db: Session = Depends(get_db)):
    """Health check endpoint."""
    start_time = time.time()
    
    # Check database connection
    try:
        db.execute(text("SELECT 1"))
        db_status = "healthy"
    except Exception as e:
        db_status = f"unhealthy: {str(e)}"
    
    # Check Google Sheets API
    sheets_status = "configured" if config.GOOGLE_SHEET_ID else "not configured"
    
    # Response time
    response_time = time.time() - start_time
    
    return {
        "status": "ok",
        "database": db_status,
        "google_sheets": sheets_status,
        "response_time_ms": round(response_time * 1000, 2)
    }
# /app/app/routes/home.py
import logging
from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse
from starlette.templating import Jinja2Templates
from app.utils.auth import get_current_user
from app.utils.sheets import get_summary_data, get_chart_data, get_all_assets

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=RedirectResponse)
async def redirect_root():
    return RedirectResponse("/dashboard")

@router.get("/dashboard")
async def home(request: Request, current_user = Depends(get_current_user)):
    try:
        # Summary and chart data
        summary_data = get_summary_data()
        chart_data = get_chart_data()
        all_assets = get_all_assets()

        # Filter out disposed assets for dashboard counts
        active_assets = [asset for asset in all_assets if asset.get("Status", "") != "Disposed"]
        disposed_assets = [asset for asset in all_assets if asset.get("Status", "") == "Disposed"]
        
        # Count assets by status and activity
        total_assets = len(active_assets)
        disposed_count = len(disposed_assets)
        damaged_count = len([a for a in all_assets if a.get("Status", "") == "Under Repair"])
        
        # Count assets by activity type
        relocated_count = len([a for a in all_assets if a.get("Last Activity", "") == "Relocated"])
        repaired_count = len([a for a in all_assets if a.get("Last Activity", "") == "Repaired"])
        to_be_disposed_count = len([a for a in all_assets if a.get("Status", "") == "To Be Disposed"])
        
        # Helper function to safely convert values to float
        def safe_float(value):
            if value is None or value == '':
                return 0.0
            try:
                return float(value)
            except (ValueError, TypeError):
                return 0.0
        
        # Calculate financial values directly from assets
        total_purchase_value = sum(safe_float(asset.get("Purchase Cost")) for asset in active_assets)
        total_book_value = sum(safe_float(asset.get("Book Value")) for asset in active_assets)
        # Calculate depreciation as purchase value minus book value
        total_depreciation_value = total_purchase_value - total_book_value
        category_counts = chart_data.get("category_counts", {})
        
        # Format location data
        location_data = chart_data.get("location_chart_data", {})
        location_counts = location_data.get("labels", [])
        location_values = location_data.get("values", [])
        location_counts_dict = dict(zip(location_counts, location_values))

        # Format time-based chart data
        monthly_data = chart_data.get("monthly_chart_data", {})
        monthly_chart_labels = monthly_data.get("labels", [])
        monthly_chart_values = monthly_data.get("values", [])
        
        # Generate quarterly data (last 12 quarters - 3 years)
        quarterly_chart_labels = []
        quarterly_chart_values = []
        
        # Get current year and quarter
        from datetime import datetime
        current_date = datetime.now()
        current_year = current_date.year
        current_quarter = (current_date.month - 1) // 3 + 1
        
        # Generate data for the last 12 quarters
        for i in range(11, -1, -1):
            year = current_year
            quarter = current_quarter - i
            
            # Adjust year if quarter is negative or > 4
            while quarter <= 0:
                year -= 1
                quarter += 4
            while quarter > 4:
                year += 1
                quarter -= 4
                
            quarterly_chart_labels.append(f"Q{quarter} {year}")
            
            # Count assets added in this quarter
            quarter_start_month = (quarter - 1) * 3 + 1
            quarter_end_month = quarter * 3
            
            count = 0
            for asset in all_assets:
                purchase_date = asset.get("Purchase Date", "")
                if purchase_date:
                    try:
                        date = datetime.strptime(purchase_date, "%Y-%m-%d")
                        if date.year == year and quarter_start_month <= date.month <= quarter_end_month:
                            count += 1
                    except:
                        pass
            
            quarterly_chart_values.append(count)
        
        # Generate yearly data (last 5 years)
        yearly_chart_labels = []
        yearly_chart_values = []
        
        # Generate data for the last 5 years
        for i in range(4, -1, -1):
            year = current_year - i
            yearly_chart_labels.append(str(year))
            
            # Count assets added in this year
            count = 0
            for asset in all_assets:
                purchase_date = asset.get("Purchase Date", "")
                if purchase_date:
                    try:
                        date = datetime.strptime(purchase_date, "%Y-%m-%d")
                        if date.year == year:
                            count += 1
                    except:
                        pass
            
            yearly_chart_values.append(count)

        # Format age distribution - convert to list of tuples for proper serialization
        age_distribution = chart_data.get("age_distribution", {})
        age_distribution_list = [
            {"label": str(k), "value": int(v)} 
            for k, v in age_distribution.items()
        ]

        # Format latest assets (excluding disposed assets)
        latest_assets = sorted(
            active_assets, 
            key=lambda a: a.get("Purchase Date", ""), 
            reverse=True
        )[:10]
        
        # Process assets to ensure they have a display_name field
        for asset in latest_assets:
            # Try different possible field names for the asset name
            name_fields = ["Name", "Asset Name", "AssetName", "Item Name", "Description", "Item"]
            display_name = None
            
            for field in name_fields:
                if asset.get(field):
                    display_name = asset.get(field)
                    break
            
            # If no name found, use a default
            if not display_name:
                display_name = f"Asset #{asset.get('ID', 'Unknown')}"
                
            # Add the display_name to the asset
            asset["display_name"] = display_name
            
        # Debug: Print the first asset's keys to see what fields are available
        if latest_assets:
            logging.info(f"Asset keys: {list(latest_assets[0].keys())}")
            logging.info(f"Asset display name: {latest_assets[0].get('display_name', 'Not found')}")
            logging.info(f"Original asset name fields: {[latest_assets[0].get(f, 'None') for f in name_fields]}")

        context = {
            "request": request,
            "user": current_user,
            "total_assets": total_assets,
            "total_purchase_value": total_purchase_value,
            "total_book_value": total_book_value,
            "total_depreciation_value": total_depreciation_value,
            "disposed_count": disposed_count,
            "damaged_count": damaged_count,
            "relocated_count": relocated_count,
            "repaired_count": repaired_count,
            "to_be_disposed_count": to_be_disposed_count,
            "category_counts": category_counts,
            "location_counts": location_counts_dict,
            "monthly_chart_labels": monthly_chart_labels,
            "monthly_chart_values": monthly_chart_values,
            "quarterly_chart_labels": quarterly_chart_labels,
            "quarterly_chart_values": quarterly_chart_values,
            "yearly_chart_labels": yearly_chart_labels,
            "yearly_chart_values": yearly_chart_values,
            "age_distribution": age_distribution_list,
            "latest_assets": latest_assets
        }

        return templates.TemplateResponse("dashboard.html", context)

    except Exception as e:
        logging.error("Dashboard error: %s", e, exc_info=True)
        return templates.TemplateResponse("error.html", {
            "request": request,
            "user": current_user,
            "message": "Terjadi kesalahan saat memuat dashboard.",
        })
from fastapi import APIRouter, Request, Response, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from supabase import create_client, Client
from app.config import load_config
import logging

config = load_config()
supabase: Client = create_client(config.SUPABASE_URL, config.SUPABASE_ANON_KEY)

router = APIRouter(tags=["authentication"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/login", response_class=HTMLResponse)
@router.head("/login", response_class=HTMLResponse)
async def login_page(request: Request, next: str = None):
    return templates.TemplateResponse("login_logout.html", {"request": request, "next": next})

@router.post("/login", response_class=HTMLResponse)
async def login_form(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    next: str = Form(None)
):
    try:
        # Use service key client for admin operations
        from supabase import create_client
        admin_supabase = create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_KEY)
        
        response = admin_supabase.auth.sign_in_with_password({
            "email": email,
            "password": password
        })
        
        if not response.user:
            return templates.TemplateResponse(
                "login_logout.html",
                {"request": request, "error": "Invalid email or password", "next": next},
                status_code=401
            )
        
        # Get user profile
        profile_response = admin_supabase.table('profiles').select('*').eq('id', response.user.id).single().execute()
        if not profile_response.data or not profile_response.data.get('is_active'):
            return templates.TemplateResponse(
                "login_logout.html",
                {"request": request, "error": "Account is inactive", "next": next},
                status_code=401
            )
        
        redirect_url = next if next else "/"
        redirect_response = RedirectResponse(url=redirect_url, status_code=303)
        
        redirect_response.set_cookie(
            key="sb_access_token",
            value=response.session.access_token,
            httponly=True,
            max_age=3600,
            samesite="lax",
            secure=True,
            domain=".onrender.com"
        )
        
        return redirect_response
        
    except Exception as e:
        logging.error(f"Login error: {str(e)}")
        return templates.TemplateResponse(
            "login_logout.html",
            {"request": request, "error": "Login failed", "next": next},
            status_code=401
        )

@router.get("/auth/callback")
async def auth_callback(request: Request):
    return templates.TemplateResponse("auth_callback.html", {"request": request})

@router.get("/logout")
async def logout():
    try:
        supabase.auth.sign_out()
    except:
        pass
    
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(key="sb_access_token")
    return response
# app/routes/logs.py
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.database.models import Profile
from app.utils.auth import get_current_user
from app.utils.sheets import get_all_approvals

router = APIRouter(prefix="/logs", tags=["logs"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def logs_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """View approval logs based on user role."""
    all_approvals = get_all_approvals()
    
    # Filter based on user role
    if current_user.role.value == 'staff':
        # Staff can only see their own requests
        user_identifier = current_user.full_name or current_user.email
        approvals = [a for a in all_approvals if a.get('Submitted_By') == user_identifier]
    else:
        # Manager and admin can see all approvals
        approvals = all_approvals
    
    # Separate pending and completed
    pending_approvals = [a for a in approvals if a.get('Status') == 'Pending']
    completed_approvals = [a for a in approvals if a.get('Status') in ['Approved', 'Rejected']]
    
    return templates.TemplateResponse(
        "logs/index.html",
        {
            "request": request,
            "user": current_user,
            "pending_approvals": pending_approvals,
            "completed_approvals": completed_approvals
        }
    )
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
from fastapi import APIRouter, Depends, Request, Form, UploadFile, File, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from app.database.database import get_db
from app.database.models import Profile
from app.utils.auth import get_current_user
from app.utils.photo import resize_and_convert_image, upload_to_drive
from app.utils.flash import set_flash

router = APIRouter(tags=["profile"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/profile", response_class=HTMLResponse)
async def profile_page(
    request: Request,
    current_user = Depends(get_current_user)
):
    """User profile page."""
    return templates.TemplateResponse(
        "profile/view.html",
        {
            "request": request,
            "user": current_user
        }
    )

@router.get("/profile/edit", response_class=HTMLResponse)
async def edit_profile_page(
    request: Request,
    current_user = Depends(get_current_user)
):
    """Edit user profile page."""
    return templates.TemplateResponse(
        "profile/edit.html",
        {
            "request": request,
            "user": current_user
        }
    )

@router.post("/profile/edit")
async def update_profile(
    request: Request,
    full_name: str = Form(...),
    email: str = Form(...),
    photo: UploadFile = File(None),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Update user profile."""
    # Update basic info
    current_user.full_name = full_name
    current_user.email = email
    current_user.updated_at = datetime.now(timezone.utc)
    
    # Handle photo upload if provided
    if photo and photo.filename:
        try:
            # Process image
            contents = await photo.read()
            import io
            image_file = io.BytesIO(contents)
            processed_image = resize_and_convert_image(image_file)
            
            if processed_image:
                # Upload to Google Drive
                photo_url = upload_to_drive(
                    processed_image, 
                    photo.filename, 
                    f"profile_{current_user.email}"
                )
                if photo_url:
                    current_user.photo_url = photo_url
        except Exception as e:
            return templates.TemplateResponse(
                "profile/edit.html",
                {
                    "request": request,
                    "user": current_user,
                    "error": f"Error uploading photo: {str(e)}"
                },
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    # Save changes
    db.commit()
    
    # Redirect to profile page
    response = RedirectResponse(url="/profile", status_code=status.HTTP_303_SEE_OTHER)
    set_flash(response, "Profile updated successfully", "success")
    return response
# app/routes/relocation.py
from fastapi import APIRouter, Depends, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime
import json

from app.database.database import get_db
from app.database.models import Profile
from app.utils.auth import get_current_user
from app.utils.sheets import get_all_assets, get_dropdown_options, add_approval_request
from app.utils.flash import set_flash

router = APIRouter(prefix="/relocation", tags=["relocation"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def relocation_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Asset relocation page."""
    # Get assets and dropdown options
    all_assets = get_all_assets()
    dropdown_options = get_dropdown_options()
    
    return templates.TemplateResponse(
        "relocation/index.html",
        {
            "request": request,
            "user": current_user,
            "assets": all_assets,
            "dropdown_options": dropdown_options
        }
    )

@router.post("/relocate/{asset_id}")
async def relocate_asset(
    asset_id: str,
    request: Request,
    new_location: str = Form(...),
    new_room: str = Form(...),
    reason: str = Form(...),
    notes: str = Form(None),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Submit asset relocation request."""
    from app.utils.sheets import get_asset_by_id
    
    # Get asset data
    asset = get_asset_by_id(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    # Create relocation approval request
    relocation_data = {
        'new_location': new_location,
        'new_room': new_room,
        'current_location': asset.get('Location', ''),
        'current_room': asset.get('Room', ''),
        'reason': reason,
        'notes': notes or ''
    }
    
    approval_data = {
        'type': 'relocation',
        'asset_id': asset_id,
        'asset_name': asset.get('Item Name', ''),
        'submitted_by': current_user.full_name or current_user.email,
        'submitted_date': datetime.now().strftime('%Y-%m-%d'),
        'description': f"Relocate from {asset.get('Location', '')} - {asset.get('Room', '')} to {new_location} - {new_room}",
        'request_data': json.dumps(relocation_data, ensure_ascii=False)
    }
    
    approval_success = add_approval_request(approval_data)
    
    if approval_success:
        response = RedirectResponse(url="/relocation", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, f"Relocation request for {asset.get('Item Name', '')} submitted for approval", "success")
        return response
    else:
        response = RedirectResponse(url="/relocation", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, "Error submitting relocation request", "error")
        return response
# /app/app/routes/repair.py
from fastapi import APIRouter, Request, Depends
from starlette.templating import Jinja2Templates
from app.utils.auth import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.post("/action")
async def submit_repair_action(request: Request, current_user = Depends(get_current_user)):
    """Submit repair action - creates approval request for store, direct action for allocate"""
    from app.utils.sheets import add_repair_log, update_asset, add_approval_request
    from datetime import datetime
    
    try:
        # Get JSON data
        data = await request.json()
        action_type = data.get('action_type')  # 'store' or 'allocate'
        
        if action_type == 'store':
            # Store action requires approval - only create approval request
            approval_data = {
                'type': 'repair_action',
                'asset_id': data.get('asset_id'),
                'asset_name': data.get('asset_name'),
                'submitted_by': current_user.full_name or current_user.email,
                'submitted_date': datetime.now().strftime('%Y-%m-%d'),
                'description': f"Request to store asset: {data.get('description')}",
                'action': 'Store Asset'
            }
            
            approval_success = add_approval_request(approval_data)
            
            if approval_success:
                return {"status": "success", "message": "Store request submitted for admin approval"}
            else:
                return {"status": "error", "message": "Failed to submit approval request"}
        
        else:  # allocate - direct action
            # Add to Repair_Log sheet
            repair_data = {
                'asset_id': data.get('asset_id'),
                'asset_name': data.get('asset_name'),
                'repair_action': 'Allocate Asset',
                'action_type': action_type,
                'description': data.get('description', ''),
                'performed_by': current_user.full_name or current_user.email,
                'action_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'new_location': data.get('location', ''),
                'new_room': data.get('room', ''),
                'notes': data.get('notes', '')
            }
            
            # Add to repair log
            log_success = add_repair_log(repair_data)
            
            # Update asset from Under Repair to Active
            update_data = {
                'Status': 'Active',
                'Bisnis Unit': data.get('business_unit', ''),
                'Location': data.get('location', ''),
                'Room': data.get('room', '')
            }
            
            asset_success = update_asset(data.get('asset_id'), update_data)
            
            if log_success and asset_success:
                return {"status": "success", "message": "Asset allocated successfully and synced to Google Sheets"}
            else:
                return {"status": "error", "message": "Failed to sync with Google Sheets"}
            
    except Exception as e:
        return {"status": "error", "message": str(e)}
# app/routes/user_management.py
from fastapi import APIRouter, Depends, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.database.models import Profile, UserRole
from app.utils.auth import get_current_user, get_admin_user
from app.utils.flash import set_flash

router = APIRouter(prefix="/user_management", tags=["user_management"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def user_list(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """List all users (admin only)."""
    users = db.query(Profile).all()
    
    return templates.TemplateResponse(
        "user_management/list.html",
        {
            "request": request,
            "user": current_user,
            "users": users
        }
    )

@router.get("/create", response_class=HTMLResponse)
async def create_user_form(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Create user form (admin only)."""
    return templates.TemplateResponse(
        "user_management/create.html",
        {
            "request": request,
            "user": current_user
        }
    )

@router.post("/create")
async def create_user(
    request: Request,
    email: str = Form(...),
    full_name: str = Form(...),
    role: str = Form(...),
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Create new user (admin only)."""
    # Check if user exists
    existing_user = db.query(Profile).filter(Profile.email == email).first()
    if existing_user:
        return templates.TemplateResponse(
            "user_management/create.html",
            {
                "request": request,
                "user": current_user,
                "error": "Email already exists"
            }
        )
    
    # Create user profile (Supabase handles auth)
    new_user = Profile(
        email=email,
        full_name=full_name,
        role=getattr(UserRole, role.upper()),
        is_active=True
    )
    
    db.add(new_user)
    db.commit()
    
    response = RedirectResponse(url="/user_management", status_code=status.HTTP_303_SEE_OTHER)
    set_flash(response, f"User {email} created successfully", "success")
    return response

@router.post("/reset_password/{user_id}")
async def reset_password(
    user_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Reset user password to default (admin only)."""
    user = db.query(Profile).filter(Profile.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Password reset handled by Supabase
    default_password = f"{user.email.split('@')[0]}123"
    
    response = RedirectResponse(url="/user_management", status_code=status.HTTP_303_SEE_OTHER)
    set_flash(response, f"Password reset instructions sent to {user.email}", "success")
    return response

@router.post("/toggle_status/{user_id}")
async def toggle_user_status(
    user_id: str,
    request: Request,
    is_active: bool = Form(...),
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Toggle user active status (admin only)."""
    user = db.query(Profile).filter(Profile.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Update status
    user.is_active = is_active
    db.commit()
    
    status_text = "activated" if is_active else "deactivated"
    response = RedirectResponse(url="/user_management", status_code=status.HTTP_303_SEE_OTHER)
    set_flash(response, f"User {user.email} {status_text}", "success")
    return response
# app/routes/__init__.py

# Import all route modules to make them available from app.routes
from app.routes import (
    home,
    assets,
    asset_management,
    login,
    damage,
    health,
    offline,
    profile,
    repair,
    approvals,
    disposal,
    user_management,
    logs,
    relocation
)
# app/routes/approvals.py
from fastapi import APIRouter, Depends, Request, HTTPException, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.utils.auth import get_current_user
from app.utils.sheets import get_all_approvals, update_approval_status

router = APIRouter(prefix="/approvals", tags=["approvals"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def approvals_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Approvals page for admin and manager."""
    if current_user.role not in ['admin', 'manager']:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get all approvals from Google Sheets
    all_approvals = get_all_approvals()
    
    # Filter approvals based on user role
    if current_user.role == 'admin':
        # Admin sees all approvals except disposal and edit_asset
        approvals_data = [a for a in all_approvals if a.get('Type') not in ['disposal', 'edit_asset']]
    elif current_user.role == 'manager':
        # Manager sees disposal and edit_asset approvals
        approvals_data = [a for a in all_approvals if a.get('Type') in ['disposal', 'edit_asset']]
    else:
        approvals_data = []
    
    return templates.TemplateResponse(
        "approvals/list.html",
        {
            "request": request,
            "user": current_user,
            "approvals_data": approvals_data
        }
    )

@router.post("/approve/{approval_id}")
async def approve_request(
    approval_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Approve a request."""
    if current_user.role not in ['admin', 'manager']:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get approval details
    all_approvals = get_all_approvals()
    approval = next((a for a in all_approvals if str(a.get('ID')) == str(approval_id)), None)
    
    if not approval:
        return JSONResponse({"status": "error", "message": "Approval not found"})
    
    # Process approval based on type
    try:
        if approval.get('Type') == 'damage_report':
            # Update asset status to "Under Repair"
            from app.utils.sheets import update_asset
            success = update_asset(approval.get('Asset_ID'), {'Status': 'Under Repair'})
            if not success:
                return JSONResponse({"status": "error", "message": "Failed to update asset status"})
        
        elif approval.get('Type') == 'relocation':
            # Process relocation approval
            import json
            try:
                request_data_str = approval.get('Request_Data', '')
                if request_data_str:
                    relocation_data = json.loads(request_data_str)
                    update_data = {
                        'Location': relocation_data.get('new_location'),
                        'Room': relocation_data.get('new_room')
                    }
                    from app.utils.sheets import update_asset
                    success = update_asset(approval.get('Asset_ID'), update_data)
                    if not success:
                        return JSONResponse({"status": "error", "message": "Failed to relocate asset"})
            except Exception as e:
                return JSONResponse({"status": "error", "message": f"Error processing relocation: {str(e)}"})
            
        elif approval.get('Type') == 'edit_asset':
            # Process edit asset approval
            import json
            try:
                request_data_str = approval.get('Request_Data', '')
                if request_data_str:
                    edit_data = json.loads(request_data_str)
                    from app.utils.sheets import update_asset
                    success = update_asset(approval.get('Asset_ID'), edit_data)
                    if not success:
                        return JSONResponse({"status": "error", "message": "Failed to update asset"})
            except Exception as e:
                return JSONResponse({"status": "error", "message": f"Error processing edit: {str(e)}"})
        
        # Update approval status
        approval_update = {
            'Status': 'Approved',
            'Approved_By': current_user.full_name or current_user.email,
            'Approved_Date': __import__('datetime').datetime.now().strftime('%Y-%m-%d')
        }
        
        success = update_approval_status(approval_id, approval_update)
        
        if success:
            return JSONResponse({"status": "success", "message": "Request approved successfully"})
        else:
            return JSONResponse({"status": "error", "message": "Failed to update approval status"})
            
    except Exception as e:
        return JSONResponse({"status": "error", "message": f"Error processing approval: {str(e)}"})

@router.post("/reject/{approval_id}")
async def reject_request(
    approval_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Reject a request."""
    if current_user.role not in ['admin', 'manager']:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Update approval status
    approval_update = {
        'Status': 'Rejected',
        'Approved_By': current_user.full_name or current_user.email,
        'Approved_Date': __import__('datetime').datetime.now().strftime('%Y-%m-%d')
    }
    
    success = update_approval_status(approval_id, approval_update)
    
    if success:
        return JSONResponse({"status": "success", "message": "Request rejected"})
    else:
        return JSONResponse({"status": "error", "message": "Failed to update approval status"})
from fastapi import APIRouter, Request, Depends
from starlette.templating import Jinja2Templates
from app.utils.auth import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/assets")
async def assets_page(request: Request, current_user=Depends(get_current_user)):
    """Assets listing page with filtering and pagination"""
    from app.utils.sheets import get_all_assets
    
    # Ambil data asset dari Google Sheets
    all_assets = get_all_assets()
    
    # Filter hanya aset aktif (bukan Disposed)
    active_assets = [asset for asset in all_assets if asset.get("Status", "").lower() != "disposed"]
    
    return templates.TemplateResponse("assets.html", {
        "request": request,
        "user": current_user,
        "assets_data": active_assets
    })
# app/routes/asset_management.py
from fastapi import APIRouter, Depends, Request, Form, File, UploadFile, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import json
from datetime import datetime
import io

from app.database.database import get_db
from app.database.models import Profile, UserRole
from app.utils.photo import resize_and_convert_image, upload_to_drive
from app.utils.sheets import get_dropdown_options, add_asset as sheets_add_asset
from app.utils.flash import set_flash
from app.utils.auth import get_current_user, get_admin_user
from app.config import load_config

config = load_config()
router = APIRouter(prefix="/asset_management", tags=["asset_management"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/add", response_class=HTMLResponse)
async def add_asset_form(
    request: Request,
    db: Session = Depends(get_db),
    current_profile = Depends(get_current_user)
):
    """Form to add a new asset."""
    dropdown_options = get_dropdown_options()
    return templates.TemplateResponse(
        "asset_management/add.html",
        {
            "request": request,
            "user": current_profile,
            "dropdown_options": dropdown_options
        }
    )


@router.get("/list", response_class=HTMLResponse)
async def asset_list(
    request: Request,
    db: Session = Depends(get_db),
    current_profile = Depends(get_current_user)
):
    """List assets for editing (admin and manager only)."""
    if current_profile.role not in [UserRole.ADMIN, UserRole.MANAGER]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    from app.utils.sheets import get_all_assets
    assets = get_all_assets()
    
    locations = list(set(asset.get('Location', '') for asset in assets if asset.get('Location')))
    location_rooms = {}
    for asset in assets:
        location = asset.get('Location', '')
        room = asset.get('Room', '')
        if location and room:
            if location not in location_rooms:
                location_rooms[location] = set()
            location_rooms[location].add(room)
    
    for location in location_rooms:
        location_rooms[location] = list(location_rooms[location])
    
    return templates.TemplateResponse(
        "asset_management/list.html",
        {
            "request": request,
            "user": current_profile,
            "assets": assets,
            "locations": sorted(locations),
            "location_rooms": location_rooms
        }
    )


@router.get("/edit/{asset_id}", response_class=HTMLResponse)
async def edit_asset_form(
    asset_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_profile = Depends(get_current_user)
):
    """Form to edit an existing asset (admin/manager only)."""
    if current_profile.role not in [UserRole.ADMIN, UserRole.MANAGER]:
        raise HTTPException(status_code=403, detail="Access denied")

    from app.utils.sheets import get_asset_by_id
    asset = get_asset_by_id(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    dropdown_options = get_dropdown_options()
    
    return templates.TemplateResponse(
        "asset_management/edit.html",
        {
            "request": request,
            "user": current_profile,
            "asset": asset,
            "dropdown_options": dropdown_options
        }
    )


@router.post("/edit/{asset_id}")
async def update_asset(
    asset_id: str,
    request: Request,
    status: str = Form(...),
    company: str = Form(...),
    location: str = Form(...),
    room: str = Form(...),
    bisnis_unit: str = Form(None),
    edit_reason: str = Form(...),
    db: Session = Depends(get_db),
    current_profile = Depends(get_current_user)
):
    """Update existing asset (admin and manager only)."""
    if current_profile.role not in [UserRole.ADMIN, UserRole.MANAGER]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    from app.utils.sheets import update_asset as sheets_update_asset, calculate_asset_financials, get_asset_by_id
    asset = get_asset_by_id(asset_id)

    update_data = {
        "Status": status,
        "Company": company,
        "Location": location,
        "Room": room,
        "Bisnis Unit": bisnis_unit or ""
    }
    
    # Jika perlu hitung ulang nilai finansial, misalnya setelah perubahan harga
    # financials = calculate_asset_financials(purchase_cost, purchase_date, category)
    # update_data.update(financials)
    
    from app.utils.sheets import add_approval_request
    
    approval_data = {
        'type': 'edit_asset',
        'asset_id': asset_id,
        'asset_name': asset.get('Item Name', ''),
        'submitted_by': current_profile.full_name or current_profile.email,
        'submitted_date': datetime.now().strftime('%Y-%m-%d'),
        'description': f"Edit asset: {asset.get('Item Name', '')} - Reason: {edit_reason}",
        'edit_reason': edit_reason,
        'request_data': json.dumps(update_data, ensure_ascii=False)
    }
    
    approval_success = add_approval_request(approval_data)
    
    if approval_success:
        response = RedirectResponse(url="/asset_management/list", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, "Asset edit request submitted for manager approval", "success")
        return response
    else:
        dropdown_options = get_dropdown_options()
        return templates.TemplateResponse(
            "asset_management/edit.html",
            {
                "request": request,
                "user": current_profile,
                "asset": asset,
                "dropdown_options": dropdown_options,
                "error": "Error submitting edit request"
            },
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@router.post("/add")
async def add_asset(
    request: Request,
    item_name: str = Form(...),
    category: str = Form(...),
    type: str = Form(...),
    manufacture: str = Form(None),
    model: str = Form(None),
    serial_number: str = Form(None),
    company: str = Form(...),
    bisnis_unit: str = Form(None),
    location: str = Form(...),
    room: str = Form(...),
    notes: str = Form(None),
    item_condition: str = Form(None),
    purchase_date: str = Form(...),
    purchase_cost: str = Form(...),
    warranty: str = Form(None),
    supplier: str = Form(None),
    journal: str = Form(None),
    owner: str = Form(...),
    photo: UploadFile = File(None),
    db: Session = Depends(get_db),
    current_profile = Depends(get_current_user)
):
    """Process add asset form."""
    dropdown_options = get_dropdown_options()
    
    asset_data = {
        "Item Name": item_name,
        "Category": category,
        "Type": type,
        "Manufacture": manufacture or "",
        "Model": model or "",
        "Serial Number": serial_number or "",
        "Company": company,
        "Bisnis Unit": bisnis_unit or "",
        "Location": location,
        "Room": room,
        "Notes": notes or "",
        "Item Condition": item_condition or "",
        "Purchase Date": purchase_date,
        "Purchase Cost": purchase_cost,
        "Warranty": warranty or "",
        "Supplier": supplier or "",
        "Journal": journal or "",
        "Owner": owner,
        "Status": "Active"
    }
    
    photo_url = None
    if photo and photo.filename:
        try:
            contents = await photo.read()
            image_file = io.BytesIO(contents)
            processed_image = resize_and_convert_image(image_file)
            
            if processed_image:
                photo_url = upload_to_drive(processed_image, photo.filename, "new")
                if photo_url:
                    asset_data["Photo URL"] = photo_url
        except Exception as e:
            print(f"Error processing photo: {str(e)}")
    
    if current_profile.role == UserRole.ADMIN:
        success = sheets_add_asset(asset_data)
        
        if success:
            response = RedirectResponse(url="/assets/", status_code=status.HTTP_303_SEE_OTHER)
            set_flash(response, "Asset added successfully", "success")
            return response
        else:
            return templates.TemplateResponse(
                "asset_management/add.html",
                {
                    "request": request,
                    "user": current_profile,
                    "dropdown_options": dropdown_options,
                    "error": "Error adding asset to Google Sheets",
                    "form_data": asset_data
                },
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    from app.utils.sheets import add_approval_request
    
    approval_data = {
        'type': 'add_asset',
        'asset_id': 'NEW',
        'asset_name': item_name,
        'submitted_by': current_profile.full_name or current_profile.email,
        'submitted_date': datetime.now().strftime('%Y-%m-%d'),
        'description': f"Add new asset: {item_name}",
        'request_data': json.dumps(asset_data, ensure_ascii=False)
    }
    
    approval_success = add_approval_request(approval_data)
    
    if approval_success:
        response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, "Asset request submitted for approval", "success")
        return response
    else:
        return templates.TemplateResponse(
            "asset_management/add.html",
            {
                "request": request,
                "user": current_profile,
                "dropdown_options": dropdown_options,
                "error": "Error submitting approval request",
                "form_data": asset_data
            },
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
from fastapi import APIRouter, Request, Depends
from starlette.templating import Jinja2Templates
from app.utils.auth import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/")
async def damaged_assets_page(request: Request, current_user = Depends(get_current_user)):
    """Damaged assets page with search and log functionality"""
    from app.utils.sheets import get_all_assets, get_dropdown_options

    all_assets = get_all_assets()
    dropdown_options = get_dropdown_options()

    return templates.TemplateResponse("damaged_assets.html", {
        "request": request,
        "user": current_user,
        "assets_data": all_assets,
        "dropdown_options": dropdown_options
    })


@router.post("/lost")
async def submit_lost_report(request: Request, current_user = Depends(get_current_user)):
    """Submit lost report - syncs to Google Sheets"""
    from app.utils.sheets import add_lost_log, add_approval_request
    from datetime import datetime

    try:
        data = await request.json()

        lost_data = {
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'last_location': data.get('last_location'),
            'last_room': data.get('last_room', ''),
            'date_lost': data.get('date_lost'),
            'description': data.get('description'),
            'reported_by': current_user.full_name or current_user.email,
            'report_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'notes': data.get('notes', '')
        }

        log_success = add_lost_log(lost_data)

        approval_data = {
            'type': 'lost_report',
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'submitted_by': current_user.full_name or current_user.email,
            'submitted_date': datetime.now().strftime('%Y-%m-%d'),
            'description': f"Lost report: {data.get('description')}",
            'location': data.get('last_location')
        }

        approval_success = add_approval_request(approval_data)

        if log_success and approval_success:
            return {"status": "success", "message": "Lost report submitted and logged to Google Sheets"}
        else:
            return {"status": "error", "message": "Failed to sync with Google Sheets"}

    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/disposal")
async def submit_disposal_request(request: Request, current_user = Depends(get_current_user)):
    """Submit disposal request - syncs to Google Sheets"""
    from app.utils.sheets import add_disposal_log, add_approval_request
    from datetime import datetime

    try:
        data = await request.json()

        disposal_data = {
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'disposal_reason': data.get('disposal_reason'),
            'disposal_method': data.get('disposal_method', 'Standard'),
            'description': data.get('description'),
            'requested_by': current_user.full_name or current_user.email,
            'request_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'notes': data.get('notes', '')
        }

        log_success = add_disposal_log(disposal_data)

        approval_data = {
            'type': 'disposal_request',
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'submitted_by': current_user.full_name or current_user.email,
            'submitted_date': datetime.now().strftime('%Y-%m-%d'),
            'description': f"Disposal request: {data.get('description')}"
        }

        approval_success = add_approval_request(approval_data)

        if log_success and approval_success:
            return {"status": "success", "message": "Disposal request submitted and logged to Google Sheets"}
        else:
            return {"status": "error", "message": "Failed to sync with Google Sheets"}

    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/report")
async def submit_damage_report(request: Request, current_user = Depends(get_current_user)):
    """Submit damage report - syncs to Google Sheets"""
    from app.utils.sheets import add_damage_log, add_approval_request
    from datetime import datetime

    try:
        data = await request.json()

        damage_data = {
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'damage_type': data.get('damage_type'),
            'severity': data.get('severity'),
            'description': data.get('damage_description'),
            'reported_by': current_user.full_name or current_user.email,
            'report_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'location': data.get('location', ''),
            'room': data.get('room', ''),
            'notes': data.get('notes', '')
        }

        approval_data = {
            'type': 'damage_report',
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'submitted_by': current_user.full_name or current_user.email,
            'submitted_date': datetime.now().strftime('%Y-%m-%d'),
            'description': f"Damage report: {data.get('damage_description')}",
            'damage_type': data.get('damage_type'),
            'severity': data.get('severity')
        }

        approval_success = add_approval_request(approval_data)

        if approval_success:
            return {"status": "success", "message": "Damage report submitted for approval"}
        else:
            return {"status": "error", "message": "Failed to submit approval request"}

    except Exception as e:
        return {"status": "error", "message": str(e)}
# app/routes/disposal.py
from fastapi import APIRouter, Depends, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime

from app.database.database import get_db
from app.database.models import Profile
from app.utils.auth import get_admin_user
from app.utils.sheets import get_all_assets, update_asset, add_disposal_log
from app.utils.flash import set_flash

router = APIRouter(prefix="/disposal", tags=["disposal"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def disposal_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Disposal assets page (admin only)."""
    # Get assets that are ready to dispose only
    all_assets = get_all_assets()
    # Debug: check all statuses
    statuses = [str(asset.get('Status', '')).strip() for asset in all_assets]
    print(f"All statuses found: {set(statuses)}")
    
    disposable_assets = []
    for asset in all_assets:
        status = str(asset.get('Status', '')).strip()
        if status in ['To Be Disposed', 'To be Disposed', 'TO BE DISPOSED']:
            disposable_assets.append(asset)
    
    return templates.TemplateResponse(
        "disposal/index.html",
        {
            "request": request,
            "user": current_user,
            "assets": disposable_assets
        }
    )

@router.post("/dispose/{asset_id}")
async def dispose_asset(
    asset_id: str,
    request: Request,
    disposal_reason: str = Form(...),
    disposal_method: str = Form(...),
    description: str = Form(None),
    notes: str = Form(None),
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Dispose an asset (admin only)."""
    from app.utils.sheets import get_asset_by_id
    
    # Get asset data
    asset = get_asset_by_id(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    if str(asset.get('Status', '')).strip() != 'To Be Disposed':
        raise HTTPException(status_code=400, detail="Asset must be marked 'To Be Disposed' first")
    
    # Create disposal approval request
    from app.utils.sheets import add_approval_request
    
    approval_data = {
        'type': 'disposal',
        'asset_id': asset_id,
        'asset_name': asset.get('Item Name', ''),
        'submitted_by': current_user.full_name or current_user.email,
        'submitted_date': datetime.now().strftime('%Y-%m-%d'),
        'description': f"Disposal request: {disposal_reason} - {disposal_method}",
        'disposal_reason': disposal_reason,
        'disposal_method': disposal_method,
        'notes': f"Description: {description or ''} | Notes: {notes or ''}"
    }
    
    approval_success = add_approval_request(approval_data)
    
    if approval_success:
        response = RedirectResponse(url="/disposal", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, f"Disposal request for {asset.get('Item Name', '')} submitted for manager approval", "success")
        return response
    else:
        response = RedirectResponse(url="/disposal", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, "Error submitting disposal request", "error")
        return response
# app/routes/health.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
import time

from app.database.database import get_db
from app.config import load_config

router = APIRouter(tags=["health"])
config = load_config()

@router.get("/health")
async def health_check(db: Session = Depends(get_db)):
    """Health check endpoint."""
    start_time = time.time()
    
    # Check database connection
    try:
        db.execute(text("SELECT 1"))
        db_status = "healthy"
    except Exception as e:
        db_status = f"unhealthy: {str(e)}"
    
    # Check Google Sheets API
    sheets_status = "configured" if config.GOOGLE_SHEET_ID else "not configured"
    
    # Response time
    response_time = time.time() - start_time
    
    return {
        "status": "ok",
        "database": db_status,
        "google_sheets": sheets_status,
        "response_time_ms": round(response_time * 1000, 2)
    }
# /app/app/routes/home.py
import logging
from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse
from starlette.templating import Jinja2Templates
from app.utils.auth import get_current_user
from app.utils.sheets import get_summary_data, get_chart_data, get_all_assets

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=RedirectResponse)
async def redirect_root():
    return RedirectResponse("/dashboard")

@router.get("/dashboard")
async def home(request: Request, current_user = Depends(get_current_user)):
    try:
        # Summary and chart data
        summary_data = get_summary_data()
        chart_data = get_chart_data()
        all_assets = get_all_assets()

        # Filter out disposed assets for dashboard counts
        active_assets = [asset for asset in all_assets if asset.get("Status", "") != "Disposed"]
        disposed_assets = [asset for asset in all_assets if asset.get("Status", "") == "Disposed"]
        
        # Count assets by status and activity
        total_assets = len(active_assets)
        disposed_count = len(disposed_assets)
        damaged_count = len([a for a in all_assets if a.get("Status", "") == "Under Repair"])
        
        # Count assets by activity type
        relocated_count = len([a for a in all_assets if a.get("Last Activity", "") == "Relocated"])
        repaired_count = len([a for a in all_assets if a.get("Last Activity", "") == "Repaired"])
        to_be_disposed_count = len([a for a in all_assets if a.get("Status", "") == "To Be Disposed"])
        
        # Helper function to safely convert values to float
        def safe_float(value):
            if value is None or value == '':
                return 0.0
            try:
                return float(value)
            except (ValueError, TypeError):
                return 0.0
        
        # Calculate financial values directly from assets
        total_purchase_value = sum(safe_float(asset.get("Purchase Cost")) for asset in active_assets)
        total_book_value = sum(safe_float(asset.get("Book Value")) for asset in active_assets)
        # Calculate depreciation as purchase value minus book value
        total_depreciation_value = total_purchase_value - total_book_value
        category_counts = chart_data.get("category_counts", {})
        
        # Format location data
        location_data = chart_data.get("location_chart_data", {})
        location_counts = location_data.get("labels", [])
        location_values = location_data.get("values", [])
        location_counts_dict = dict(zip(location_counts, location_values))

        # Format time-based chart data
        monthly_data = chart_data.get("monthly_chart_data", {})
        monthly_chart_labels = monthly_data.get("labels", [])
        monthly_chart_values = monthly_data.get("values", [])
        
        # Generate quarterly data (last 12 quarters - 3 years)
        quarterly_chart_labels = []
        quarterly_chart_values = []
        
        # Get current year and quarter
        from datetime import datetime
        current_date = datetime.now()
        current_year = current_date.year
        current_quarter = (current_date.month - 1) // 3 + 1
        
        # Generate data for the last 12 quarters
        for i in range(11, -1, -1):
            year = current_year
            quarter = current_quarter - i
            
            # Adjust year if quarter is negative or > 4
            while quarter <= 0:
                year -= 1
                quarter += 4
            while quarter > 4:
                year += 1
                quarter -= 4
                
            quarterly_chart_labels.append(f"Q{quarter} {year}")
            
            # Count assets added in this quarter
            quarter_start_month = (quarter - 1) * 3 + 1
            quarter_end_month = quarter * 3
            
            count = 0
            for asset in all_assets:
                purchase_date = asset.get("Purchase Date", "")
                if purchase_date:
                    try:
                        date = datetime.strptime(purchase_date, "%Y-%m-%d")
                        if date.year == year and quarter_start_month <= date.month <= quarter_end_month:
                            count += 1
                    except:
                        pass
            
            quarterly_chart_values.append(count)
        
        # Generate yearly data (last 5 years)
        yearly_chart_labels = []
        yearly_chart_values = []
        
        # Generate data for the last 5 years
        for i in range(4, -1, -1):
            year = current_year - i
            yearly_chart_labels.append(str(year))
            
            # Count assets added in this year
            count = 0
            for asset in all_assets:
                purchase_date = asset.get("Purchase Date", "")
                if purchase_date:
                    try:
                        date = datetime.strptime(purchase_date, "%Y-%m-%d")
                        if date.year == year:
                            count += 1
                    except:
                        pass
            
            yearly_chart_values.append(count)

        # Format age distribution - convert to list of tuples for proper serialization
        age_distribution = chart_data.get("age_distribution", {})
        age_distribution_list = [
            {"label": str(k), "value": int(v)} 
            for k, v in age_distribution.items()
        ]

        # Format latest assets (excluding disposed assets)
        latest_assets = sorted(
            active_assets, 
            key=lambda a: a.get("Purchase Date", ""), 
            reverse=True
        )[:10]
        
        # Process assets to ensure they have a display_name field
        for asset in latest_assets:
            # Try different possible field names for the asset name
            name_fields = ["Name", "Asset Name", "AssetName", "Item Name", "Description", "Item"]
            display_name = None
            
            for field in name_fields:
                if asset.get(field):
                    display_name = asset.get(field)
                    break
            
            # If no name found, use a default
            if not display_name:
                display_name = f"Asset #{asset.get('ID', 'Unknown')}"
                
            # Add the display_name to the asset
            asset["display_name"] = display_name
            
        # Debug: Print the first asset's keys to see what fields are available
        if latest_assets:
            logging.info(f"Asset keys: {list(latest_assets[0].keys())}")
            logging.info(f"Asset display name: {latest_assets[0].get('display_name', 'Not found')}")
            logging.info(f"Original asset name fields: {[latest_assets[0].get(f, 'None') for f in name_fields]}")

        context = {
            "request": request,
            "user": current_user,
            "total_assets": total_assets,
            "total_purchase_value": total_purchase_value,
            "total_book_value": total_book_value,
            "total_depreciation_value": total_depreciation_value,
            "disposed_count": disposed_count,
            "damaged_count": damaged_count,
            "relocated_count": relocated_count,
            "repaired_count": repaired_count,
            "to_be_disposed_count": to_be_disposed_count,
            "category_counts": category_counts,
            "location_counts": location_counts_dict,
            "monthly_chart_labels": monthly_chart_labels,
            "monthly_chart_values": monthly_chart_values,
            "quarterly_chart_labels": quarterly_chart_labels,
            "quarterly_chart_values": quarterly_chart_values,
            "yearly_chart_labels": yearly_chart_labels,
            "yearly_chart_values": yearly_chart_values,
            "age_distribution": age_distribution_list,
            "latest_assets": latest_assets
        }

        return templates.TemplateResponse("dashboard.html", context)

    except Exception as e:
        logging.error("Dashboard error: %s", e, exc_info=True)
        return templates.TemplateResponse("error.html", {
            "request": request,
            "user": current_user,
            "message": "Terjadi kesalahan saat memuat dashboard.",
        })
from fastapi import APIRouter, Request, Response, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from supabase import create_client, Client
from app.config import load_config
import logging

config = load_config()
supabase: Client = create_client(config.SUPABASE_URL, config.SUPABASE_ANON_KEY)

router = APIRouter(tags=["authentication"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/login", response_class=HTMLResponse)
@router.head("/login", response_class=HTMLResponse)
async def login_page(request: Request, next: str = None):
    return templates.TemplateResponse("login_logout.html", {"request": request, "next": next})

@router.post("/login", response_class=HTMLResponse)
async def login_form(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    next: str = Form(None)
):
    try:
        # Use service key client for admin operations
        from supabase import create_client
        admin_supabase = create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_KEY)
        
        response = admin_supabase.auth.sign_in_with_password({
            "email": email,
            "password": password
        })
        
        if not response.user:
            return templates.TemplateResponse(
                "login_logout.html",
                {"request": request, "error": "Invalid email or password", "next": next},
                status_code=401
            )
        
        # Get user profile
        profile_response = admin_supabase.table('profiles').select('*').eq('id', response.user.id).single().execute()
        if not profile_response.data or not profile_response.data.get('is_active'):
            return templates.TemplateResponse(
                "login_logout.html",
                {"request": request, "error": "Account is inactive", "next": next},
                status_code=401
            )
        
        redirect_url = next if next else "/"
        redirect_response = RedirectResponse(url=redirect_url, status_code=303)
        
        redirect_response.set_cookie(
            key="sb_access_token",
            value=response.session.access_token,
            httponly=True,
            max_age=3600,
            samesite="lax",
            secure=True,
            domain=".onrender.com"
        )
        
        return redirect_response
        
    except Exception as e:
        logging.error(f"Login error: {str(e)}")
        return templates.TemplateResponse(
            "login_logout.html",
            {"request": request, "error": "Login failed", "next": next},
            status_code=401
        )

@router.get("/auth/callback")
async def auth_callback(request: Request):
    return templates.TemplateResponse("auth_callback.html", {"request": request})

@router.get("/logout")
async def logout():
    try:
        supabase.auth.sign_out()
    except:
        pass
    
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(key="sb_access_token")
    return response
# app/routes/logs.py
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.database.models import Profile
from app.utils.auth import get_current_user
from app.utils.sheets import get_all_approvals

router = APIRouter(prefix="/logs", tags=["logs"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def logs_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """View approval logs based on user role."""
    all_approvals = get_all_approvals()
    
    # Filter based on user role
    if current_user.role.value == 'staff':
        # Staff can only see their own requests
        user_identifier = current_user.full_name or current_user.email
        approvals = [a for a in all_approvals if a.get('Submitted_By') == user_identifier]
    else:
        # Manager and admin can see all approvals
        approvals = all_approvals
    
    # Separate pending and completed
    pending_approvals = [a for a in approvals if a.get('Status') == 'Pending']
    completed_approvals = [a for a in approvals if a.get('Status') in ['Approved', 'Rejected']]
    
    return templates.TemplateResponse(
        "logs/index.html",
        {
            "request": request,
            "user": current_user,
            "pending_approvals": pending_approvals,
            "completed_approvals": completed_approvals
        }
    )
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
from fastapi import APIRouter, Depends, Request, Form, UploadFile, File, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from app.database.database import get_db
from app.database.models import Profile
from app.utils.auth import get_current_user
from app.utils.photo import resize_and_convert_image, upload_to_drive
from app.utils.flash import set_flash

router = APIRouter(tags=["profile"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/profile", response_class=HTMLResponse)
async def profile_page(
    request: Request,
    current_user = Depends(get_current_user)
):
    """User profile page."""
    return templates.TemplateResponse(
        "profile/view.html",
        {
            "request": request,
            "user": current_user
        }
    )

@router.get("/profile/edit", response_class=HTMLResponse)
async def edit_profile_page(
    request: Request,
    current_user = Depends(get_current_user)
):
    """Edit user profile page."""
    return templates.TemplateResponse(
        "profile/edit.html",
        {
            "request": request,
            "user": current_user
        }
    )

@router.post("/profile/edit")
async def update_profile(
    request: Request,
    full_name: str = Form(...),
    email: str = Form(...),
    photo: UploadFile = File(None),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Update user profile."""
    # Update basic info
    current_user.full_name = full_name
    current_user.email = email
    current_user.updated_at = datetime.now(timezone.utc)
    
    # Handle photo upload if provided
    if photo and photo.filename:
        try:
            # Process image
            contents = await photo.read()
            import io
            image_file = io.BytesIO(contents)
            processed_image = resize_and_convert_image(image_file)
            
            if processed_image:
                # Upload to Google Drive
                photo_url = upload_to_drive(
                    processed_image, 
                    photo.filename, 
                    f"profile_{current_user.email}"
                )
                if photo_url:
                    current_user.photo_url = photo_url
        except Exception as e:
            return templates.TemplateResponse(
                "profile/edit.html",
                {
                    "request": request,
                    "user": current_user,
                    "error": f"Error uploading photo: {str(e)}"
                },
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    # Save changes
    db.commit()
    
    # Redirect to profile page
    response = RedirectResponse(url="/profile", status_code=status.HTTP_303_SEE_OTHER)
    set_flash(response, "Profile updated successfully", "success")
    return response
# app/routes/relocation.py
from fastapi import APIRouter, Depends, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime
import json

from app.database.database import get_db
from app.database.models import Profile
from app.utils.auth import get_current_user
from app.utils.sheets import get_all_assets, get_dropdown_options, add_approval_request
from app.utils.flash import set_flash

router = APIRouter(prefix="/relocation", tags=["relocation"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def relocation_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Asset relocation page."""
    # Get assets and dropdown options
    all_assets = get_all_assets()
    dropdown_options = get_dropdown_options()
    
    return templates.TemplateResponse(
        "relocation/index.html",
        {
            "request": request,
            "user": current_user,
            "assets": all_assets,
            "dropdown_options": dropdown_options
        }
    )

@router.post("/relocate/{asset_id}")
async def relocate_asset(
    asset_id: str,
    request: Request,
    new_location: str = Form(...),
    new_room: str = Form(...),
    reason: str = Form(...),
    notes: str = Form(None),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Submit asset relocation request."""
    from app.utils.sheets import get_asset_by_id
    
    # Get asset data
    asset = get_asset_by_id(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    # Create relocation approval request
    relocation_data = {
        'new_location': new_location,
        'new_room': new_room,
        'current_location': asset.get('Location', ''),
        'current_room': asset.get('Room', ''),
        'reason': reason,
        'notes': notes or ''
    }
    
    approval_data = {
        'type': 'relocation',
        'asset_id': asset_id,
        'asset_name': asset.get('Item Name', ''),
        'submitted_by': current_user.full_name or current_user.email,
        'submitted_date': datetime.now().strftime('%Y-%m-%d'),
        'description': f"Relocate from {asset.get('Location', '')} - {asset.get('Room', '')} to {new_location} - {new_room}",
        'request_data': json.dumps(relocation_data, ensure_ascii=False)
    }
    
    approval_success = add_approval_request(approval_data)
    
    if approval_success:
        response = RedirectResponse(url="/relocation", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, f"Relocation request for {asset.get('Item Name', '')} submitted for approval", "success")
        return response
    else:
        response = RedirectResponse(url="/relocation", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, "Error submitting relocation request", "error")
        return response
# /app/app/routes/repair.py
from fastapi import APIRouter, Request, Depends
from starlette.templating import Jinja2Templates
from app.utils.auth import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.post("/action")
async def submit_repair_action(request: Request, current_user = Depends(get_current_user)):
    """Submit repair action - creates approval request for store, direct action for allocate"""
    from app.utils.sheets import add_repair_log, update_asset, add_approval_request
    from datetime import datetime
    
    try:
        # Get JSON data
        data = await request.json()
        action_type = data.get('action_type')  # 'store' or 'allocate'
        
        if action_type == 'store':
            # Store action requires approval - only create approval request
            approval_data = {
                'type': 'repair_action',
                'asset_id': data.get('asset_id'),
                'asset_name': data.get('asset_name'),
                'submitted_by': current_user.full_name or current_user.email,
                'submitted_date': datetime.now().strftime('%Y-%m-%d'),
                'description': f"Request to store asset: {data.get('description')}",
                'action': 'Store Asset'
            }
            
            approval_success = add_approval_request(approval_data)
            
            if approval_success:
                return {"status": "success", "message": "Store request submitted for admin approval"}
            else:
                return {"status": "error", "message": "Failed to submit approval request"}
        
        else:  # allocate - direct action
            # Add to Repair_Log sheet
            repair_data = {
                'asset_id': data.get('asset_id'),
                'asset_name': data.get('asset_name'),
                'repair_action': 'Allocate Asset',
                'action_type': action_type,
                'description': data.get('description', ''),
                'performed_by': current_user.full_name or current_user.email,
                'action_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'new_location': data.get('location', ''),
                'new_room': data.get('room', ''),
                'notes': data.get('notes', '')
            }
            
            # Add to repair log
            log_success = add_repair_log(repair_data)
            
            # Update asset from Under Repair to Active
            update_data = {
                'Status': 'Active',
                'Bisnis Unit': data.get('business_unit', ''),
                'Location': data.get('location', ''),
                'Room': data.get('room', '')
            }
            
            asset_success = update_asset(data.get('asset_id'), update_data)
            
            if log_success and asset_success:
                return {"status": "success", "message": "Asset allocated successfully and synced to Google Sheets"}
            else:
                return {"status": "error", "message": "Failed to sync with Google Sheets"}
            
    except Exception as e:
        return {"status": "error", "message": str(e)}
# app/routes/user_management.py
from fastapi import APIRouter, Depends, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.database.models import Profile, UserRole
from app.utils.auth import get_current_user, get_admin_user
from app.utils.flash import set_flash

router = APIRouter(prefix="/user_management", tags=["user_management"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def user_list(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """List all users (admin only)."""
    users = db.query(Profile).all()
    
    return templates.TemplateResponse(
        "user_management/list.html",
        {
            "request": request,
            "user": current_user,
            "users": users
        }
    )

@router.get("/create", response_class=HTMLResponse)
async def create_user_form(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Create user form (admin only)."""
    return templates.TemplateResponse(
        "user_management/create.html",
        {
            "request": request,
            "user": current_user
        }
    )

@router.post("/create")
async def create_user(
    request: Request,
    email: str = Form(...),
    full_name: str = Form(...),
    role: str = Form(...),
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Create new user (admin only)."""
    # Check if user exists
    existing_user = db.query(Profile).filter(Profile.email == email).first()
    if existing_user:
        return templates.TemplateResponse(
            "user_management/create.html",
            {
                "request": request,
                "user": current_user,
                "error": "Email already exists"
            }
        )
    
    # Create user profile (Supabase handles auth)
    new_user = Profile(
        email=email,
        full_name=full_name,
        role=getattr(UserRole, role.upper()),
        is_active=True
    )
    
    db.add(new_user)
    db.commit()
    
    response = RedirectResponse(url="/user_management", status_code=status.HTTP_303_SEE_OTHER)
    set_flash(response, f"User {email} created successfully", "success")
    return response

@router.post("/reset_password/{user_id}")
async def reset_password(
    user_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Reset user password to default (admin only)."""
    user = db.query(Profile).filter(Profile.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Password reset handled by Supabase
    default_password = f"{user.email.split('@')[0]}123"
    
    response = RedirectResponse(url="/user_management", status_code=status.HTTP_303_SEE_OTHER)
    set_flash(response, f"Password reset instructions sent to {user.email}", "success")
    return response

@router.post("/toggle_status/{user_id}")
async def toggle_user_status(
    user_id: str,
    request: Request,
    is_active: bool = Form(...),
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Toggle user active status (admin only)."""
    user = db.query(Profile).filter(Profile.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Update status
    user.is_active = is_active
    db.commit()
    
    status_text = "activated" if is_active else "deactivated"
    response = RedirectResponse(url="/user_management", status_code=status.HTTP_303_SEE_OTHER)
    set_flash(response, f"User {user.email} {status_text}", "success")
    return response
# app/routes/__init__.py

# Import all route modules to make them available from app.routes
from app.routes import (
    home,
    assets,
    asset_management,
    login,
    damage,
    health,
    offline,
    profile,
    repair,
    approvals,
    disposal,
    user_management,
    logs,
    relocation
)
# app/routes/approvals.py
from fastapi import APIRouter, Depends, Request, HTTPException, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.utils.auth import get_current_user
from app.utils.sheets import get_all_approvals, update_approval_status

router = APIRouter(prefix="/approvals", tags=["approvals"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def approvals_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Approvals page for admin and manager."""
    if current_user.role not in ['admin', 'manager']:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get all approvals from Google Sheets
    all_approvals = get_all_approvals()
    
    # Filter approvals based on user role
    if current_user.role == 'admin':
        # Admin sees all approvals except disposal and edit_asset
        approvals_data = [a for a in all_approvals if a.get('Type') not in ['disposal', 'edit_asset']]
    elif current_user.role == 'manager':
        # Manager sees disposal and edit_asset approvals
        approvals_data = [a for a in all_approvals if a.get('Type') in ['disposal', 'edit_asset']]
    else:
        approvals_data = []
    
    return templates.TemplateResponse(
        "approvals/list.html",
        {
            "request": request,
            "user": current_user,
            "approvals_data": approvals_data
        }
    )

@router.post("/approve/{approval_id}")
async def approve_request(
    approval_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Approve a request."""
    if current_user.role not in ['admin', 'manager']:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get approval details
    all_approvals = get_all_approvals()
    approval = next((a for a in all_approvals if str(a.get('ID')) == str(approval_id)), None)
    
    if not approval:
        return JSONResponse({"status": "error", "message": "Approval not found"})
    
    # Process approval based on type
    try:
        if approval.get('Type') == 'damage_report':
            # Update asset status to "Under Repair"
            from app.utils.sheets import update_asset
            success = update_asset(approval.get('Asset_ID'), {'Status': 'Under Repair'})
            if not success:
                return JSONResponse({"status": "error", "message": "Failed to update asset status"})
        
        elif approval.get('Type') == 'relocation':
            # Process relocation approval
            import json
            try:
                request_data_str = approval.get('Request_Data', '')
                if request_data_str:
                    relocation_data = json.loads(request_data_str)
                    update_data = {
                        'Location': relocation_data.get('new_location'),
                        'Room': relocation_data.get('new_room')
                    }
                    from app.utils.sheets import update_asset
                    success = update_asset(approval.get('Asset_ID'), update_data)
                    if not success:
                        return JSONResponse({"status": "error", "message": "Failed to relocate asset"})
            except Exception as e:
                return JSONResponse({"status": "error", "message": f"Error processing relocation: {str(e)}"})
            
        elif approval.get('Type') == 'edit_asset':
            # Process edit asset approval
            import json
            try:
                request_data_str = approval.get('Request_Data', '')
                if request_data_str:
                    edit_data = json.loads(request_data_str)
                    from app.utils.sheets import update_asset
                    success = update_asset(approval.get('Asset_ID'), edit_data)
                    if not success:
                        return JSONResponse({"status": "error", "message": "Failed to update asset"})
            except Exception as e:
                return JSONResponse({"status": "error", "message": f"Error processing edit: {str(e)}"})
        
        # Update approval status
        approval_update = {
            'Status': 'Approved',
            'Approved_By': current_user.full_name or current_user.email,
            'Approved_Date': __import__('datetime').datetime.now().strftime('%Y-%m-%d')
        }
        
        success = update_approval_status(approval_id, approval_update)
        
        if success:
            return JSONResponse({"status": "success", "message": "Request approved successfully"})
        else:
            return JSONResponse({"status": "error", "message": "Failed to update approval status"})
            
    except Exception as e:
        return JSONResponse({"status": "error", "message": f"Error processing approval: {str(e)}"})

@router.post("/reject/{approval_id}")
async def reject_request(
    approval_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Reject a request."""
    if current_user.role not in ['admin', 'manager']:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Update approval status
    approval_update = {
        'Status': 'Rejected',
        'Approved_By': current_user.full_name or current_user.email,
        'Approved_Date': __import__('datetime').datetime.now().strftime('%Y-%m-%d')
    }
    
    success = update_approval_status(approval_id, approval_update)
    
    if success:
        return JSONResponse({"status": "success", "message": "Request rejected"})
    else:
        return JSONResponse({"status": "error", "message": "Failed to update approval status"})
from fastapi import APIRouter, Request, Depends
from starlette.templating import Jinja2Templates
from app.utils.auth import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/assets")
async def assets_page(request: Request, current_user=Depends(get_current_user)):
    """Assets listing page with filtering and pagination"""
    from app.utils.sheets import get_all_assets
    
    # Ambil data asset dari Google Sheets
    all_assets = get_all_assets()
    
    # Filter hanya aset aktif (bukan Disposed)
    active_assets = [asset for asset in all_assets if asset.get("Status", "").lower() != "disposed"]
    
    return templates.TemplateResponse("assets.html", {
        "request": request,
        "user": current_user,
        "assets_data": active_assets
    })
# app/routes/asset_management.py
from fastapi import APIRouter, Depends, Request, Form, File, UploadFile, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import json
from datetime import datetime
import io

from app.database.database import get_db
from app.database.models import Profile, UserRole
from app.utils.photo import resize_and_convert_image, upload_to_drive
from app.utils.sheets import get_dropdown_options, add_asset as sheets_add_asset
from app.utils.flash import set_flash
from app.utils.auth import get_current_user, get_admin_user
from app.config import load_config

config = load_config()
router = APIRouter(prefix="/asset_management", tags=["asset_management"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/add", response_class=HTMLResponse)
async def add_asset_form(
    request: Request,
    db: Session = Depends(get_db),
    current_profile = Depends(get_current_user)
):
    """Form to add a new asset."""
    dropdown_options = get_dropdown_options()
    return templates.TemplateResponse(
        "asset_management/add.html",
        {
            "request": request,
            "user": current_profile,
            "dropdown_options": dropdown_options
        }
    )


@router.get("/list", response_class=HTMLResponse)
async def asset_list(
    request: Request,
    db: Session = Depends(get_db),
    current_profile = Depends(get_current_user)
):
    """List assets for editing (admin and manager only)."""
    if current_profile.role not in [UserRole.ADMIN, UserRole.MANAGER]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    from app.utils.sheets import get_all_assets
    assets = get_all_assets()
    
    locations = list(set(asset.get('Location', '') for asset in assets if asset.get('Location')))
    location_rooms = {}
    for asset in assets:
        location = asset.get('Location', '')
        room = asset.get('Room', '')
        if location and room:
            if location not in location_rooms:
                location_rooms[location] = set()
            location_rooms[location].add(room)
    
    for location in location_rooms:
        location_rooms[location] = list(location_rooms[location])
    
    return templates.TemplateResponse(
        "asset_management/list.html",
        {
            "request": request,
            "user": current_profile,
            "assets": assets,
            "locations": sorted(locations),
            "location_rooms": location_rooms
        }
    )


@router.get("/edit/{asset_id}", response_class=HTMLResponse)
async def edit_asset_form(
    asset_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_profile = Depends(get_current_user)
):
    """Form to edit an existing asset (admin/manager only)."""
    if current_profile.role not in [UserRole.ADMIN, UserRole.MANAGER]:
        raise HTTPException(status_code=403, detail="Access denied")

    from app.utils.sheets import get_asset_by_id
    asset = get_asset_by_id(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    dropdown_options = get_dropdown_options()
    
    return templates.TemplateResponse(
        "asset_management/edit.html",
        {
            "request": request,
            "user": current_profile,
            "asset": asset,
            "dropdown_options": dropdown_options
        }
    )


@router.post("/edit/{asset_id}")
async def update_asset(
    asset_id: str,
    request: Request,
    status: str = Form(...),
    company: str = Form(...),
    location: str = Form(...),
    room: str = Form(...),
    bisnis_unit: str = Form(None),
    edit_reason: str = Form(...),
    db: Session = Depends(get_db),
    current_profile = Depends(get_current_user)
):
    """Update existing asset (admin and manager only)."""
    if current_profile.role not in [UserRole.ADMIN, UserRole.MANAGER]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    from app.utils.sheets import update_asset as sheets_update_asset, calculate_asset_financials, get_asset_by_id
    asset = get_asset_by_id(asset_id)

    update_data = {
        "Status": status,
        "Company": company,
        "Location": location,
        "Room": room,
        "Bisnis Unit": bisnis_unit or ""
    }
    
    # Jika perlu hitung ulang nilai finansial, misalnya setelah perubahan harga
    # financials = calculate_asset_financials(purchase_cost, purchase_date, category)
    # update_data.update(financials)
    
    from app.utils.sheets import add_approval_request
    
    approval_data = {
        'type': 'edit_asset',
        'asset_id': asset_id,
        'asset_name': asset.get('Item Name', ''),
        'submitted_by': current_profile.full_name or current_profile.email,
        'submitted_date': datetime.now().strftime('%Y-%m-%d'),
        'description': f"Edit asset: {asset.get('Item Name', '')} - Reason: {edit_reason}",
        'edit_reason': edit_reason,
        'request_data': json.dumps(update_data, ensure_ascii=False)
    }
    
    approval_success = add_approval_request(approval_data)
    
    if approval_success:
        response = RedirectResponse(url="/asset_management/list", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, "Asset edit request submitted for manager approval", "success")
        return response
    else:
        dropdown_options = get_dropdown_options()
        return templates.TemplateResponse(
            "asset_management/edit.html",
            {
                "request": request,
                "user": current_profile,
                "asset": asset,
                "dropdown_options": dropdown_options,
                "error": "Error submitting edit request"
            },
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@router.post("/add")
async def add_asset(
    request: Request,
    item_name: str = Form(...),
    category: str = Form(...),
    type: str = Form(...),
    manufacture: str = Form(None),
    model: str = Form(None),
    serial_number: str = Form(None),
    company: str = Form(...),
    bisnis_unit: str = Form(None),
    location: str = Form(...),
    room: str = Form(...),
    notes: str = Form(None),
    item_condition: str = Form(None),
    purchase_date: str = Form(...),
    purchase_cost: str = Form(...),
    warranty: str = Form(None),
    supplier: str = Form(None),
    journal: str = Form(None),
    owner: str = Form(...),
    photo: UploadFile = File(None),
    db: Session = Depends(get_db),
    current_profile = Depends(get_current_user)
):
    """Process add asset form."""
    dropdown_options = get_dropdown_options()
    
    asset_data = {
        "Item Name": item_name,
        "Category": category,
        "Type": type,
        "Manufacture": manufacture or "",
        "Model": model or "",
        "Serial Number": serial_number or "",
        "Company": company,
        "Bisnis Unit": bisnis_unit or "",
        "Location": location,
        "Room": room,
        "Notes": notes or "",
        "Item Condition": item_condition or "",
        "Purchase Date": purchase_date,
        "Purchase Cost": purchase_cost,
        "Warranty": warranty or "",
        "Supplier": supplier or "",
        "Journal": journal or "",
        "Owner": owner,
        "Status": "Active"
    }
    
    photo_url = None
    if photo and photo.filename:
        try:
            contents = await photo.read()
            image_file = io.BytesIO(contents)
            processed_image = resize_and_convert_image(image_file)
            
            if processed_image:
                photo_url = upload_to_drive(processed_image, photo.filename, "new")
                if photo_url:
                    asset_data["Photo URL"] = photo_url
        except Exception as e:
            print(f"Error processing photo: {str(e)}")
    
    if current_profile.role == UserRole.ADMIN:
        success = sheets_add_asset(asset_data)
        
        if success:
            response = RedirectResponse(url="/assets/", status_code=status.HTTP_303_SEE_OTHER)
            set_flash(response, "Asset added successfully", "success")
            return response
        else:
            return templates.TemplateResponse(
                "asset_management/add.html",
                {
                    "request": request,
                    "user": current_profile,
                    "dropdown_options": dropdown_options,
                    "error": "Error adding asset to Google Sheets",
                    "form_data": asset_data
                },
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    from app.utils.sheets import add_approval_request
    
    approval_data = {
        'type': 'add_asset',
        'asset_id': 'NEW',
        'asset_name': item_name,
        'submitted_by': current_profile.full_name or current_profile.email,
        'submitted_date': datetime.now().strftime('%Y-%m-%d'),
        'description': f"Add new asset: {item_name}",
        'request_data': json.dumps(asset_data, ensure_ascii=False)
    }
    
    approval_success = add_approval_request(approval_data)
    
    if approval_success:
        response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, "Asset request submitted for approval", "success")
        return response
    else:
        return templates.TemplateResponse(
            "asset_management/add.html",
            {
                "request": request,
                "user": current_profile,
                "dropdown_options": dropdown_options,
                "error": "Error submitting approval request",
                "form_data": asset_data
            },
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
from fastapi import APIRouter, Request, Depends
from starlette.templating import Jinja2Templates
from app.utils.auth import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/")
async def damaged_assets_page(request: Request, current_user = Depends(get_current_user)):
    """Damaged assets page with search and log functionality"""
    from app.utils.sheets import get_all_assets, get_dropdown_options

    all_assets = get_all_assets()
    dropdown_options = get_dropdown_options()

    return templates.TemplateResponse("damaged_assets.html", {
        "request": request,
        "user": current_user,
        "assets_data": all_assets,
        "dropdown_options": dropdown_options
    })


@router.post("/lost")
async def submit_lost_report(request: Request, current_user = Depends(get_current_user)):
    """Submit lost report - syncs to Google Sheets"""
    from app.utils.sheets import add_lost_log, add_approval_request
    from datetime import datetime

    try:
        data = await request.json()

        lost_data = {
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'last_location': data.get('last_location'),
            'last_room': data.get('last_room', ''),
            'date_lost': data.get('date_lost'),
            'description': data.get('description'),
            'reported_by': current_user.full_name or current_user.email,
            'report_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'notes': data.get('notes', '')
        }

        log_success = add_lost_log(lost_data)

        approval_data = {
            'type': 'lost_report',
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'submitted_by': current_user.full_name or current_user.email,
            'submitted_date': datetime.now().strftime('%Y-%m-%d'),
            'description': f"Lost report: {data.get('description')}",
            'location': data.get('last_location')
        }

        approval_success = add_approval_request(approval_data)

        if log_success and approval_success:
            return {"status": "success", "message": "Lost report submitted and logged to Google Sheets"}
        else:
            return {"status": "error", "message": "Failed to sync with Google Sheets"}

    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/disposal")
async def submit_disposal_request(request: Request, current_user = Depends(get_current_user)):
    """Submit disposal request - syncs to Google Sheets"""
    from app.utils.sheets import add_disposal_log, add_approval_request
    from datetime import datetime

    try:
        data = await request.json()

        disposal_data = {
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'disposal_reason': data.get('disposal_reason'),
            'disposal_method': data.get('disposal_method', 'Standard'),
            'description': data.get('description'),
            'requested_by': current_user.full_name or current_user.email,
            'request_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'notes': data.get('notes', '')
        }

        log_success = add_disposal_log(disposal_data)

        approval_data = {
            'type': 'disposal_request',
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'submitted_by': current_user.full_name or current_user.email,
            'submitted_date': datetime.now().strftime('%Y-%m-%d'),
            'description': f"Disposal request: {data.get('description')}"
        }

        approval_success = add_approval_request(approval_data)

        if log_success and approval_success:
            return {"status": "success", "message": "Disposal request submitted and logged to Google Sheets"}
        else:
            return {"status": "error", "message": "Failed to sync with Google Sheets"}

    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/report")
async def submit_damage_report(request: Request, current_user = Depends(get_current_user)):
    """Submit damage report - syncs to Google Sheets"""
    from app.utils.sheets import add_damage_log, add_approval_request
    from datetime import datetime

    try:
        data = await request.json()

        damage_data = {
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'damage_type': data.get('damage_type'),
            'severity': data.get('severity'),
            'description': data.get('damage_description'),
            'reported_by': current_user.full_name or current_user.email,
            'report_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'location': data.get('location', ''),
            'room': data.get('room', ''),
            'notes': data.get('notes', '')
        }

        approval_data = {
            'type': 'damage_report',
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'submitted_by': current_user.full_name or current_user.email,
            'submitted_date': datetime.now().strftime('%Y-%m-%d'),
            'description': f"Damage report: {data.get('damage_description')}",
            'damage_type': data.get('damage_type'),
            'severity': data.get('severity')
        }

        approval_success = add_approval_request(approval_data)

        if approval_success:
            return {"status": "success", "message": "Damage report submitted for approval"}
        else:
            return {"status": "error", "message": "Failed to submit approval request"}

    except Exception as e:
        return {"status": "error", "message": str(e)}
# app/routes/disposal.py
from fastapi import APIRouter, Depends, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime

from app.database.database import get_db
from app.database.models import Profile
from app.utils.auth import get_admin_user
from app.utils.sheets import get_all_assets, update_asset, add_disposal_log
from app.utils.flash import set_flash

router = APIRouter(prefix="/disposal", tags=["disposal"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def disposal_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Disposal assets page (admin only)."""
    # Get assets that are ready to dispose only
    all_assets = get_all_assets()
    # Debug: check all statuses
    statuses = [str(asset.get('Status', '')).strip() for asset in all_assets]
    print(f"All statuses found: {set(statuses)}")
    
    disposable_assets = []
    for asset in all_assets:
        status = str(asset.get('Status', '')).strip()
        if status in ['To Be Disposed', 'To be Disposed', 'TO BE DISPOSED']:
            disposable_assets.append(asset)
    
    return templates.TemplateResponse(
        "disposal/index.html",
        {
            "request": request,
            "user": current_user,
            "assets": disposable_assets
        }
    )

@router.post("/dispose/{asset_id}")
async def dispose_asset(
    asset_id: str,
    request: Request,
    disposal_reason: str = Form(...),
    disposal_method: str = Form(...),
    description: str = Form(None),
    notes: str = Form(None),
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Dispose an asset (admin only)."""
    from app.utils.sheets import get_asset_by_id
    
    # Get asset data
    asset = get_asset_by_id(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    if str(asset.get('Status', '')).strip() != 'To Be Disposed':
        raise HTTPException(status_code=400, detail="Asset must be marked 'To Be Disposed' first")
    
    # Create disposal approval request
    from app.utils.sheets import add_approval_request
    
    approval_data = {
        'type': 'disposal',
        'asset_id': asset_id,
        'asset_name': asset.get('Item Name', ''),
        'submitted_by': current_user.full_name or current_user.email,
        'submitted_date': datetime.now().strftime('%Y-%m-%d'),
        'description': f"Disposal request: {disposal_reason} - {disposal_method}",
        'disposal_reason': disposal_reason,
        'disposal_method': disposal_method,
        'notes': f"Description: {description or ''} | Notes: {notes or ''}"
    }
    
    approval_success = add_approval_request(approval_data)
    
    if approval_success:
        response = RedirectResponse(url="/disposal", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, f"Disposal request for {asset.get('Item Name', '')} submitted for manager approval", "success")
        return response
    else:
        response = RedirectResponse(url="/disposal", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, "Error submitting disposal request", "error")
        return response
# app/routes/health.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
import time

from app.database.database import get_db
from app.config import load_config

router = APIRouter(tags=["health"])
config = load_config()

@router.get("/health")
async def health_check(db: Session = Depends(get_db)):
    """Health check endpoint."""
    start_time = time.time()
    
    # Check database connection
    try:
        db.execute(text("SELECT 1"))
        db_status = "healthy"
    except Exception as e:
        db_status = f"unhealthy: {str(e)}"
    
    # Check Google Sheets API
    sheets_status = "configured" if config.GOOGLE_SHEET_ID else "not configured"
    
    # Response time
    response_time = time.time() - start_time
    
    return {
        "status": "ok",
        "database": db_status,
        "google_sheets": sheets_status,
        "response_time_ms": round(response_time * 1000, 2)
    }
# /app/app/routes/home.py
import logging
from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse
from starlette.templating import Jinja2Templates
from app.utils.auth import get_current_user
from app.utils.sheets import get_summary_data, get_chart_data, get_all_assets

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=RedirectResponse)
async def redirect_root():
    return RedirectResponse("/dashboard")

@router.get("/dashboard")
async def home(request: Request, current_user = Depends(get_current_user)):
    try:
        # Summary and chart data
        summary_data = get_summary_data()
        chart_data = get_chart_data()
        all_assets = get_all_assets()

        # Filter out disposed assets for dashboard counts
        active_assets = [asset for asset in all_assets if asset.get("Status", "") != "Disposed"]
        disposed_assets = [asset for asset in all_assets if asset.get("Status", "") == "Disposed"]
        
        # Count assets by status and activity
        total_assets = len(active_assets)
        disposed_count = len(disposed_assets)
        damaged_count = len([a for a in all_assets if a.get("Status", "") == "Under Repair"])
        
        # Count assets by activity type
        relocated_count = len([a for a in all_assets if a.get("Last Activity", "") == "Relocated"])
        repaired_count = len([a for a in all_assets if a.get("Last Activity", "") == "Repaired"])
        to_be_disposed_count = len([a for a in all_assets if a.get("Status", "") == "To Be Disposed"])
        
        # Helper function to safely convert values to float
        def safe_float(value):
            if value is None or value == '':
                return 0.0
            try:
                return float(value)
            except (ValueError, TypeError):
                return 0.0
        
        # Calculate financial values directly from assets
        total_purchase_value = sum(safe_float(asset.get("Purchase Cost")) for asset in active_assets)
        total_book_value = sum(safe_float(asset.get("Book Value")) for asset in active_assets)
        # Calculate depreciation as purchase value minus book value
        total_depreciation_value = total_purchase_value - total_book_value
        category_counts = chart_data.get("category_counts", {})
        
        # Format location data
        location_data = chart_data.get("location_chart_data", {})
        location_counts = location_data.get("labels", [])
        location_values = location_data.get("values", [])
        location_counts_dict = dict(zip(location_counts, location_values))

        # Format time-based chart data
        monthly_data = chart_data.get("monthly_chart_data", {})
        monthly_chart_labels = monthly_data.get("labels", [])
        monthly_chart_values = monthly_data.get("values", [])
        
        # Generate quarterly data (last 12 quarters - 3 years)
        quarterly_chart_labels = []
        quarterly_chart_values = []
        
        # Get current year and quarter
        from datetime import datetime
        current_date = datetime.now()
        current_year = current_date.year
        current_quarter = (current_date.month - 1) // 3 + 1
        
        # Generate data for the last 12 quarters
        for i in range(11, -1, -1):
            year = current_year
            quarter = current_quarter - i
            
            # Adjust year if quarter is negative or > 4
            while quarter <= 0:
                year -= 1
                quarter += 4
            while quarter > 4:
                year += 1
                quarter -= 4
                
            quarterly_chart_labels.append(f"Q{quarter} {year}")
            
            # Count assets added in this quarter
            quarter_start_month = (quarter - 1) * 3 + 1
            quarter_end_month = quarter * 3
            
            count = 0
            for asset in all_assets:
                purchase_date = asset.get("Purchase Date", "")
                if purchase_date:
                    try:
                        date = datetime.strptime(purchase_date, "%Y-%m-%d")
                        if date.year == year and quarter_start_month <= date.month <= quarter_end_month:
                            count += 1
                    except:
                        pass
            
            quarterly_chart_values.append(count)
        
        # Generate yearly data (last 5 years)
        yearly_chart_labels = []
        yearly_chart_values = []
        
        # Generate data for the last 5 years
        for i in range(4, -1, -1):
            year = current_year - i
            yearly_chart_labels.append(str(year))
            
            # Count assets added in this year
            count = 0
            for asset in all_assets:
                purchase_date = asset.get("Purchase Date", "")
                if purchase_date:
                    try:
                        date = datetime.strptime(purchase_date, "%Y-%m-%d")
                        if date.year == year:
                            count += 1
                    except:
                        pass
            
            yearly_chart_values.append(count)

        # Format age distribution - convert to list of tuples for proper serialization
        age_distribution = chart_data.get("age_distribution", {})
        age_distribution_list = [
            {"label": str(k), "value": int(v)} 
            for k, v in age_distribution.items()
        ]

        # Format latest assets (excluding disposed assets)
        latest_assets = sorted(
            active_assets, 
            key=lambda a: a.get("Purchase Date", ""), 
            reverse=True
        )[:10]
        
        # Process assets to ensure they have a display_name field
        for asset in latest_assets:
            # Try different possible field names for the asset name
            name_fields = ["Name", "Asset Name", "AssetName", "Item Name", "Description", "Item"]
            display_name = None
            
            for field in name_fields:
                if asset.get(field):
                    display_name = asset.get(field)
                    break
            
            # If no name found, use a default
            if not display_name:
                display_name = f"Asset #{asset.get('ID', 'Unknown')}"
                
            # Add the display_name to the asset
            asset["display_name"] = display_name
            
        # Debug: Print the first asset's keys to see what fields are available
        if latest_assets:
            logging.info(f"Asset keys: {list(latest_assets[0].keys())}")
            logging.info(f"Asset display name: {latest_assets[0].get('display_name', 'Not found')}")
            logging.info(f"Original asset name fields: {[latest_assets[0].get(f, 'None') for f in name_fields]}")

        context = {
            "request": request,
            "user": current_user,
            "total_assets": total_assets,
            "total_purchase_value": total_purchase_value,
            "total_book_value": total_book_value,
            "total_depreciation_value": total_depreciation_value,
            "disposed_count": disposed_count,
            "damaged_count": damaged_count,
            "relocated_count": relocated_count,
            "repaired_count": repaired_count,
            "to_be_disposed_count": to_be_disposed_count,
            "category_counts": category_counts,
            "location_counts": location_counts_dict,
            "monthly_chart_labels": monthly_chart_labels,
            "monthly_chart_values": monthly_chart_values,
            "quarterly_chart_labels": quarterly_chart_labels,
            "quarterly_chart_values": quarterly_chart_values,
            "yearly_chart_labels": yearly_chart_labels,
            "yearly_chart_values": yearly_chart_values,
            "age_distribution": age_distribution_list,
            "latest_assets": latest_assets
        }

        return templates.TemplateResponse("dashboard.html", context)

    except Exception as e:
        logging.error("Dashboard error: %s", e, exc_info=True)
        return templates.TemplateResponse("error.html", {
            "request": request,
            "user": current_user,
            "message": "Terjadi kesalahan saat memuat dashboard.",
        })
from fastapi import APIRouter, Request, Response, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from supabase import create_client, Client
from app.config import load_config
import logging

config = load_config()
supabase: Client = create_client(config.SUPABASE_URL, config.SUPABASE_ANON_KEY)

router = APIRouter(tags=["authentication"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/login", response_class=HTMLResponse)
@router.head("/login", response_class=HTMLResponse)
async def login_page(request: Request, next: str = None):
    return templates.TemplateResponse("login_logout.html", {"request": request, "next": next})

@router.post("/login", response_class=HTMLResponse)
async def login_form(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    next: str = Form(None)
):
    try:
        # Use service key client for admin operations
        from supabase import create_client
        admin_supabase = create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_KEY)
        
        response = admin_supabase.auth.sign_in_with_password({
            "email": email,
            "password": password
        })
        
        if not response.user:
            return templates.TemplateResponse(
                "login_logout.html",
                {"request": request, "error": "Invalid email or password", "next": next},
                status_code=401
            )
        
        # Get user profile
        profile_response = admin_supabase.table('profiles').select('*').eq('id', response.user.id).single().execute()
        if not profile_response.data or not profile_response.data.get('is_active'):
            return templates.TemplateResponse(
                "login_logout.html",
                {"request": request, "error": "Account is inactive", "next": next},
                status_code=401
            )
        
        redirect_url = next if next else "/"
        redirect_response = RedirectResponse(url=redirect_url, status_code=303)
        
        redirect_response.set_cookie(
            key="sb_access_token",
            value=response.session.access_token,
            httponly=True,
            max_age=3600,
            samesite="lax",
            secure=True,
            domain=".onrender.com"
        )
        
        return redirect_response
        
    except Exception as e:
        logging.error(f"Login error: {str(e)}")
        return templates.TemplateResponse(
            "login_logout.html",
            {"request": request, "error": "Login failed", "next": next},
            status_code=401
        )

@router.get("/auth/callback")
async def auth_callback(request: Request):
    return templates.TemplateResponse("auth_callback.html", {"request": request})

@router.get("/logout")
async def logout():
    try:
        supabase.auth.sign_out()
    except:
        pass
    
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(key="sb_access_token")
    return response
# app/routes/logs.py
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.database.models import Profile
from app.utils.auth import get_current_user
from app.utils.sheets import get_all_approvals

router = APIRouter(prefix="/logs", tags=["logs"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def logs_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """View approval logs based on user role."""
    all_approvals = get_all_approvals()
    
    # Filter based on user role
    if current_user.role.value == 'staff':
        # Staff can only see their own requests
        user_identifier = current_user.full_name or current_user.email
        approvals = [a for a in all_approvals if a.get('Submitted_By') == user_identifier]
    else:
        # Manager and admin can see all approvals
        approvals = all_approvals
    
    # Separate pending and completed
    pending_approvals = [a for a in approvals if a.get('Status') == 'Pending']
    completed_approvals = [a for a in approvals if a.get('Status') in ['Approved', 'Rejected']]
    
    return templates.TemplateResponse(
        "logs/index.html",
        {
            "request": request,
            "user": current_user,
            "pending_approvals": pending_approvals,
            "completed_approvals": completed_approvals
        }
    )
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
from fastapi import APIRouter, Depends, Request, Form, UploadFile, File, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from app.database.database import get_db
from app.database.models import Profile
from app.utils.auth import get_current_user
from app.utils.photo import resize_and_convert_image, upload_to_drive
from app.utils.flash import set_flash

router = APIRouter(tags=["profile"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/profile", response_class=HTMLResponse)
async def profile_page(
    request: Request,
    current_user = Depends(get_current_user)
):
    """User profile page."""
    return templates.TemplateResponse(
        "profile/view.html",
        {
            "request": request,
            "user": current_user
        }
    )

@router.get("/profile/edit", response_class=HTMLResponse)
async def edit_profile_page(
    request: Request,
    current_user = Depends(get_current_user)
):
    """Edit user profile page."""
    return templates.TemplateResponse(
        "profile/edit.html",
        {
            "request": request,
            "user": current_user
        }
    )

@router.post("/profile/edit")
async def update_profile(
    request: Request,
    full_name: str = Form(...),
    email: str = Form(...),
    photo: UploadFile = File(None),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Update user profile."""
    # Update basic info
    current_user.full_name = full_name
    current_user.email = email
    current_user.updated_at = datetime.now(timezone.utc)
    
    # Handle photo upload if provided
    if photo and photo.filename:
        try:
            # Process image
            contents = await photo.read()
            import io
            image_file = io.BytesIO(contents)
            processed_image = resize_and_convert_image(image_file)
            
            if processed_image:
                # Upload to Google Drive
                photo_url = upload_to_drive(
                    processed_image, 
                    photo.filename, 
                    f"profile_{current_user.email}"
                )
                if photo_url:
                    current_user.photo_url = photo_url
        except Exception as e:
            return templates.TemplateResponse(
                "profile/edit.html",
                {
                    "request": request,
                    "user": current_user,
                    "error": f"Error uploading photo: {str(e)}"
                },
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    # Save changes
    db.commit()
    
    # Redirect to profile page
    response = RedirectResponse(url="/profile", status_code=status.HTTP_303_SEE_OTHER)
    set_flash(response, "Profile updated successfully", "success")
    return response
# app/routes/relocation.py
from fastapi import APIRouter, Depends, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime
import json

from app.database.database import get_db
from app.database.models import Profile
from app.utils.auth import get_current_user
from app.utils.sheets import get_all_assets, get_dropdown_options, add_approval_request
from app.utils.flash import set_flash

router = APIRouter(prefix="/relocation", tags=["relocation"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def relocation_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Asset relocation page."""
    # Get assets and dropdown options
    all_assets = get_all_assets()
    dropdown_options = get_dropdown_options()
    
    return templates.TemplateResponse(
        "relocation/index.html",
        {
            "request": request,
            "user": current_user,
            "assets": all_assets,
            "dropdown_options": dropdown_options
        }
    )

@router.post("/relocate/{asset_id}")
async def relocate_asset(
    asset_id: str,
    request: Request,
    new_location: str = Form(...),
    new_room: str = Form(...),
    reason: str = Form(...),
    notes: str = Form(None),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Submit asset relocation request."""
    from app.utils.sheets import get_asset_by_id
    
    # Get asset data
    asset = get_asset_by_id(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    # Create relocation approval request
    relocation_data = {
        'new_location': new_location,
        'new_room': new_room,
        'current_location': asset.get('Location', ''),
        'current_room': asset.get('Room', ''),
        'reason': reason,
        'notes': notes or ''
    }
    
    approval_data = {
        'type': 'relocation',
        'asset_id': asset_id,
        'asset_name': asset.get('Item Name', ''),
        'submitted_by': current_user.full_name or current_user.email,
        'submitted_date': datetime.now().strftime('%Y-%m-%d'),
        'description': f"Relocate from {asset.get('Location', '')} - {asset.get('Room', '')} to {new_location} - {new_room}",
        'request_data': json.dumps(relocation_data, ensure_ascii=False)
    }
    
    approval_success = add_approval_request(approval_data)
    
    if approval_success:
        response = RedirectResponse(url="/relocation", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, f"Relocation request for {asset.get('Item Name', '')} submitted for approval", "success")
        return response
    else:
        response = RedirectResponse(url="/relocation", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, "Error submitting relocation request", "error")
        return response
# /app/app/routes/repair.py
from fastapi import APIRouter, Request, Depends
from starlette.templating import Jinja2Templates
from app.utils.auth import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.post("/action")
async def submit_repair_action(request: Request, current_user = Depends(get_current_user)):
    """Submit repair action - creates approval request for store, direct action for allocate"""
    from app.utils.sheets import add_repair_log, update_asset, add_approval_request
    from datetime import datetime
    
    try:
        # Get JSON data
        data = await request.json()
        action_type = data.get('action_type')  # 'store' or 'allocate'
        
        if action_type == 'store':
            # Store action requires approval - only create approval request
            approval_data = {
                'type': 'repair_action',
                'asset_id': data.get('asset_id'),
                'asset_name': data.get('asset_name'),
                'submitted_by': current_user.full_name or current_user.email,
                'submitted_date': datetime.now().strftime('%Y-%m-%d'),
                'description': f"Request to store asset: {data.get('description')}",
                'action': 'Store Asset'
            }
            
            approval_success = add_approval_request(approval_data)
            
            if approval_success:
                return {"status": "success", "message": "Store request submitted for admin approval"}
            else:
                return {"status": "error", "message": "Failed to submit approval request"}
        
        else:  # allocate - direct action
            # Add to Repair_Log sheet
            repair_data = {
                'asset_id': data.get('asset_id'),
                'asset_name': data.get('asset_name'),
                'repair_action': 'Allocate Asset',
                'action_type': action_type,
                'description': data.get('description', ''),
                'performed_by': current_user.full_name or current_user.email,
                'action_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'new_location': data.get('location', ''),
                'new_room': data.get('room', ''),
                'notes': data.get('notes', '')
            }
            
            # Add to repair log
            log_success = add_repair_log(repair_data)
            
            # Update asset from Under Repair to Active
            update_data = {
                'Status': 'Active',
                'Bisnis Unit': data.get('business_unit', ''),
                'Location': data.get('location', ''),
                'Room': data.get('room', '')
            }
            
            asset_success = update_asset(data.get('asset_id'), update_data)
            
            if log_success and asset_success:
                return {"status": "success", "message": "Asset allocated successfully and synced to Google Sheets"}
            else:
                return {"status": "error", "message": "Failed to sync with Google Sheets"}
            
    except Exception as e:
        return {"status": "error", "message": str(e)}
# app/routes/user_management.py
from fastapi import APIRouter, Depends, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.database.models import Profile, UserRole
from app.utils.auth import get_current_user, get_admin_user
from app.utils.flash import set_flash

router = APIRouter(prefix="/user_management", tags=["user_management"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def user_list(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """List all users (admin only)."""
    users = db.query(Profile).all()
    
    return templates.TemplateResponse(
        "user_management/list.html",
        {
            "request": request,
            "user": current_user,
            "users": users
        }
    )

@router.get("/create", response_class=HTMLResponse)
async def create_user_form(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Create user form (admin only)."""
    return templates.TemplateResponse(
        "user_management/create.html",
        {
            "request": request,
            "user": current_user
        }
    )

@router.post("/create")
async def create_user(
    request: Request,
    email: str = Form(...),
    full_name: str = Form(...),
    role: str = Form(...),
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Create new user (admin only)."""
    # Check if user exists
    existing_user = db.query(Profile).filter(Profile.email == email).first()
    if existing_user:
        return templates.TemplateResponse(
            "user_management/create.html",
            {
                "request": request,
                "user": current_user,
                "error": "Email already exists"
            }
        )
    
    # Create user profile (Supabase handles auth)
    new_user = Profile(
        email=email,
        full_name=full_name,
        role=getattr(UserRole, role.upper()),
        is_active=True
    )
    
    db.add(new_user)
    db.commit()
    
    response = RedirectResponse(url="/user_management", status_code=status.HTTP_303_SEE_OTHER)
    set_flash(response, f"User {email} created successfully", "success")
    return response

@router.post("/reset_password/{user_id}")
async def reset_password(
    user_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Reset user password to default (admin only)."""
    user = db.query(Profile).filter(Profile.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Password reset handled by Supabase
    default_password = f"{user.email.split('@')[0]}123"
    
    response = RedirectResponse(url="/user_management", status_code=status.HTTP_303_SEE_OTHER)
    set_flash(response, f"Password reset instructions sent to {user.email}", "success")
    return response

@router.post("/toggle_status/{user_id}")
async def toggle_user_status(
    user_id: str,
    request: Request,
    is_active: bool = Form(...),
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Toggle user active status (admin only)."""
    user = db.query(Profile).filter(Profile.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Update status
    user.is_active = is_active
    db.commit()
    
    status_text = "activated" if is_active else "deactivated"
    response = RedirectResponse(url="/user_management", status_code=status.HTTP_303_SEE_OTHER)
    set_flash(response, f"User {user.email} {status_text}", "success")
    return response
# app/routes/__init__.py

# Import all route modules to make them available from app.routes
from app.routes import (
    home,
    assets,
    asset_management,
    login,
    damage,
    health,
    offline,
    profile,
    repair,
    approvals,
    disposal,
    user_management,
    logs,
    relocation
)
# app/routes/approvals.py
from fastapi import APIRouter, Depends, Request, HTTPException, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.utils.auth import get_current_user
from app.utils.sheets import get_all_approvals, update_approval_status

router = APIRouter(prefix="/approvals", tags=["approvals"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def approvals_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Approvals page for admin and manager."""
    if current_user.role not in ['admin', 'manager']:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get all approvals from Google Sheets
    all_approvals = get_all_approvals()
    
    # Filter approvals based on user role
    if current_user.role == 'admin':
        # Admin sees all approvals except disposal and edit_asset
        approvals_data = [a for a in all_approvals if a.get('Type') not in ['disposal', 'edit_asset']]
    elif current_user.role == 'manager':
        # Manager sees disposal and edit_asset approvals
        approvals_data = [a for a in all_approvals if a.get('Type') in ['disposal', 'edit_asset']]
    else:
        approvals_data = []
    
    return templates.TemplateResponse(
        "approvals/list.html",
        {
            "request": request,
            "user": current_user,
            "approvals_data": approvals_data
        }
    )

@router.post("/approve/{approval_id}")
async def approve_request(
    approval_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Approve a request."""
    if current_user.role not in ['admin', 'manager']:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get approval details
    all_approvals = get_all_approvals()
    approval = next((a for a in all_approvals if str(a.get('ID')) == str(approval_id)), None)
    
    if not approval:
        return JSONResponse({"status": "error", "message": "Approval not found"})
    
    # Process approval based on type
    try:
        if approval.get('Type') == 'damage_report':
            # Update asset status to "Under Repair"
            from app.utils.sheets import update_asset
            success = update_asset(approval.get('Asset_ID'), {'Status': 'Under Repair'})
            if not success:
                return JSONResponse({"status": "error", "message": "Failed to update asset status"})
        
        elif approval.get('Type') == 'relocation':
            # Process relocation approval
            import json
            try:
                request_data_str = approval.get('Request_Data', '')
                if request_data_str:
                    relocation_data = json.loads(request_data_str)
                    update_data = {
                        'Location': relocation_data.get('new_location'),
                        'Room': relocation_data.get('new_room')
                    }
                    from app.utils.sheets import update_asset
                    success = update_asset(approval.get('Asset_ID'), update_data)
                    if not success:
                        return JSONResponse({"status": "error", "message": "Failed to relocate asset"})
            except Exception as e:
                return JSONResponse({"status": "error", "message": f"Error processing relocation: {str(e)}"})
            
        elif approval.get('Type') == 'edit_asset':
            # Process edit asset approval
            import json
            try:
                request_data_str = approval.get('Request_Data', '')
                if request_data_str:
                    edit_data = json.loads(request_data_str)
                    from app.utils.sheets import update_asset
                    success = update_asset(approval.get('Asset_ID'), edit_data)
                    if not success:
                        return JSONResponse({"status": "error", "message": "Failed to update asset"})
            except Exception as e:
                return JSONResponse({"status": "error", "message": f"Error processing edit: {str(e)}"})
        
        # Update approval status
        approval_update = {
            'Status': 'Approved',
            'Approved_By': current_user.full_name or current_user.email,
            'Approved_Date': __import__('datetime').datetime.now().strftime('%Y-%m-%d')
        }
        
        success = update_approval_status(approval_id, approval_update)
        
        if success:
            return JSONResponse({"status": "success", "message": "Request approved successfully"})
        else:
            return JSONResponse({"status": "error", "message": "Failed to update approval status"})
            
    except Exception as e:
        return JSONResponse({"status": "error", "message": f"Error processing approval: {str(e)}"})

@router.post("/reject/{approval_id}")
async def reject_request(
    approval_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Reject a request."""
    if current_user.role not in ['admin', 'manager']:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Update approval status
    approval_update = {
        'Status': 'Rejected',
        'Approved_By': current_user.full_name or current_user.email,
        'Approved_Date': __import__('datetime').datetime.now().strftime('%Y-%m-%d')
    }
    
    success = update_approval_status(approval_id, approval_update)
    
    if success:
        return JSONResponse({"status": "success", "message": "Request rejected"})
    else:
        return JSONResponse({"status": "error", "message": "Failed to update approval status"})
from fastapi import APIRouter, Request, Depends
from starlette.templating import Jinja2Templates
from app.utils.auth import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/assets")
async def assets_page(request: Request, current_user=Depends(get_current_user)):
    """Assets listing page with filtering and pagination"""
    from app.utils.sheets import get_all_assets
    
    # Ambil data asset dari Google Sheets
    all_assets = get_all_assets()
    
    # Filter hanya aset aktif (bukan Disposed)
    active_assets = [asset for asset in all_assets if asset.get("Status", "").lower() != "disposed"]
    
    return templates.TemplateResponse("assets.html", {
        "request": request,
        "user": current_user,
        "assets_data": active_assets
    })
# app/routes/asset_management.py
from fastapi import APIRouter, Depends, Request, Form, File, UploadFile, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import json
from datetime import datetime
import io

from app.database.database import get_db
from app.database.models import Profile, UserRole
from app.utils.photo import resize_and_convert_image, upload_to_drive
from app.utils.sheets import get_dropdown_options, add_asset as sheets_add_asset
from app.utils.flash import set_flash
from app.utils.auth import get_current_user, get_admin_user
from app.config import load_config

config = load_config()
router = APIRouter(prefix="/asset_management", tags=["asset_management"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/add", response_class=HTMLResponse)
async def add_asset_form(
    request: Request,
    db: Session = Depends(get_db),
    current_profile = Depends(get_current_user)
):
    """Form to add a new asset."""
    dropdown_options = get_dropdown_options()
    return templates.TemplateResponse(
        "asset_management/add.html",
        {
            "request": request,
            "user": current_profile,
            "dropdown_options": dropdown_options
        }
    )


@router.get("/list", response_class=HTMLResponse)
async def asset_list(
    request: Request,
    db: Session = Depends(get_db),
    current_profile = Depends(get_current_user)
):
    """List assets for editing (admin and manager only)."""
    if current_profile.role not in [UserRole.ADMIN, UserRole.MANAGER]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    from app.utils.sheets import get_all_assets
    assets = get_all_assets()
    
    locations = list(set(asset.get('Location', '') for asset in assets if asset.get('Location')))
    location_rooms = {}
    for asset in assets:
        location = asset.get('Location', '')
        room = asset.get('Room', '')
        if location and room:
            if location not in location_rooms:
                location_rooms[location] = set()
            location_rooms[location].add(room)
    
    for location in location_rooms:
        location_rooms[location] = list(location_rooms[location])
    
    return templates.TemplateResponse(
        "asset_management/list.html",
        {
            "request": request,
            "user": current_profile,
            "assets": assets,
            "locations": sorted(locations),
            "location_rooms": location_rooms
        }
    )


@router.get("/edit/{asset_id}", response_class=HTMLResponse)
async def edit_asset_form(
    asset_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_profile = Depends(get_current_user)
):
    """Form to edit an existing asset (admin/manager only)."""
    if current_profile.role not in [UserRole.ADMIN, UserRole.MANAGER]:
        raise HTTPException(status_code=403, detail="Access denied")

    from app.utils.sheets import get_asset_by_id
    asset = get_asset_by_id(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    dropdown_options = get_dropdown_options()
    
    return templates.TemplateResponse(
        "asset_management/edit.html",
        {
            "request": request,
            "user": current_profile,
            "asset": asset,
            "dropdown_options": dropdown_options
        }
    )


@router.post("/edit/{asset_id}")
async def update_asset(
    asset_id: str,
    request: Request,
    status: str = Form(...),
    company: str = Form(...),
    location: str = Form(...),
    room: str = Form(...),
    bisnis_unit: str = Form(None),
    edit_reason: str = Form(...),
    db: Session = Depends(get_db),
    current_profile = Depends(get_current_user)
):
    """Update existing asset (admin and manager only)."""
    if current_profile.role not in [UserRole.ADMIN, UserRole.MANAGER]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    from app.utils.sheets import update_asset as sheets_update_asset, calculate_asset_financials, get_asset_by_id
    asset = get_asset_by_id(asset_id)

    update_data = {
        "Status": status,
        "Company": company,
        "Location": location,
        "Room": room,
        "Bisnis Unit": bisnis_unit or ""
    }
    
    # Jika perlu hitung ulang nilai finansial, misalnya setelah perubahan harga
    # financials = calculate_asset_financials(purchase_cost, purchase_date, category)
    # update_data.update(financials)
    
    from app.utils.sheets import add_approval_request
    
    approval_data = {
        'type': 'edit_asset',
        'asset_id': asset_id,
        'asset_name': asset.get('Item Name', ''),
        'submitted_by': current_profile.full_name or current_profile.email,
        'submitted_date': datetime.now().strftime('%Y-%m-%d'),
        'description': f"Edit asset: {asset.get('Item Name', '')} - Reason: {edit_reason}",
        'edit_reason': edit_reason,
        'request_data': json.dumps(update_data, ensure_ascii=False)
    }
    
    approval_success = add_approval_request(approval_data)
    
    if approval_success:
        response = RedirectResponse(url="/asset_management/list", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, "Asset edit request submitted for manager approval", "success")
        return response
    else:
        dropdown_options = get_dropdown_options()
        return templates.TemplateResponse(
            "asset_management/edit.html",
            {
                "request": request,
                "user": current_profile,
                "asset": asset,
                "dropdown_options": dropdown_options,
                "error": "Error submitting edit request"
            },
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@router.post("/add")
async def add_asset(
    request: Request,
    item_name: str = Form(...),
    category: str = Form(...),
    type: str = Form(...),
    manufacture: str = Form(None),
    model: str = Form(None),
    serial_number: str = Form(None),
    company: str = Form(...),
    bisnis_unit: str = Form(None),
    location: str = Form(...),
    room: str = Form(...),
    notes: str = Form(None),
    item_condition: str = Form(None),
    purchase_date: str = Form(...),
    purchase_cost: str = Form(...),
    warranty: str = Form(None),
    supplier: str = Form(None),
    journal: str = Form(None),
    owner: str = Form(...),
    photo: UploadFile = File(None),
    db: Session = Depends(get_db),
    current_profile = Depends(get_current_user)
):
    """Process add asset form."""
    dropdown_options = get_dropdown_options()
    
    asset_data = {
        "Item Name": item_name,
        "Category": category,
        "Type": type,
        "Manufacture": manufacture or "",
        "Model": model or "",
        "Serial Number": serial_number or "",
        "Company": company,
        "Bisnis Unit": bisnis_unit or "",
        "Location": location,
        "Room": room,
        "Notes": notes or "",
        "Item Condition": item_condition or "",
        "Purchase Date": purchase_date,
        "Purchase Cost": purchase_cost,
        "Warranty": warranty or "",
        "Supplier": supplier or "",
        "Journal": journal or "",
        "Owner": owner,
        "Status": "Active"
    }
    
    photo_url = None
    if photo and photo.filename:
        try:
            contents = await photo.read()
            image_file = io.BytesIO(contents)
            processed_image = resize_and_convert_image(image_file)
            
            if processed_image:
                photo_url = upload_to_drive(processed_image, photo.filename, "new")
                if photo_url:
                    asset_data["Photo URL"] = photo_url
        except Exception as e:
            print(f"Error processing photo: {str(e)}")
    
    if current_profile.role == UserRole.ADMIN:
        success = sheets_add_asset(asset_data)
        
        if success:
            response = RedirectResponse(url="/assets/", status_code=status.HTTP_303_SEE_OTHER)
            set_flash(response, "Asset added successfully", "success")
            return response
        else:
            return templates.TemplateResponse(
                "asset_management/add.html",
                {
                    "request": request,
                    "user": current_profile,
                    "dropdown_options": dropdown_options,
                    "error": "Error adding asset to Google Sheets",
                    "form_data": asset_data
                },
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    from app.utils.sheets import add_approval_request
    
    approval_data = {
        'type': 'add_asset',
        'asset_id': 'NEW',
        'asset_name': item_name,
        'submitted_by': current_profile.full_name or current_profile.email,
        'submitted_date': datetime.now().strftime('%Y-%m-%d'),
        'description': f"Add new asset: {item_name}",
        'request_data': json.dumps(asset_data, ensure_ascii=False)
    }
    
    approval_success = add_approval_request(approval_data)
    
    if approval_success:
        response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, "Asset request submitted for approval", "success")
        return response
    else:
        return templates.TemplateResponse(
            "asset_management/add.html",
            {
                "request": request,
                "user": current_profile,
                "dropdown_options": dropdown_options,
                "error": "Error submitting approval request",
                "form_data": asset_data
            },
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
from fastapi import APIRouter, Request, Depends
from starlette.templating import Jinja2Templates
from app.utils.auth import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/")
async def damaged_assets_page(request: Request, current_user = Depends(get_current_user)):
    """Damaged assets page with search and log functionality"""
    from app.utils.sheets import get_all_assets, get_dropdown_options

    all_assets = get_all_assets()
    dropdown_options = get_dropdown_options()

    return templates.TemplateResponse("damaged_assets.html", {
        "request": request,
        "user": current_user,
        "assets_data": all_assets,
        "dropdown_options": dropdown_options
    })


@router.post("/lost")
async def submit_lost_report(request: Request, current_user = Depends(get_current_user)):
    """Submit lost report - syncs to Google Sheets"""
    from app.utils.sheets import add_lost_log, add_approval_request
    from datetime import datetime

    try:
        data = await request.json()

        lost_data = {
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'last_location': data.get('last_location'),
            'last_room': data.get('last_room', ''),
            'date_lost': data.get('date_lost'),
            'description': data.get('description'),
            'reported_by': current_user.full_name or current_user.email,
            'report_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'notes': data.get('notes', '')
        }

        log_success = add_lost_log(lost_data)

        approval_data = {
            'type': 'lost_report',
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'submitted_by': current_user.full_name or current_user.email,
            'submitted_date': datetime.now().strftime('%Y-%m-%d'),
            'description': f"Lost report: {data.get('description')}",
            'location': data.get('last_location')
        }

        approval_success = add_approval_request(approval_data)

        if log_success and approval_success:
            return {"status": "success", "message": "Lost report submitted and logged to Google Sheets"}
        else:
            return {"status": "error", "message": "Failed to sync with Google Sheets"}

    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/disposal")
async def submit_disposal_request(request: Request, current_user = Depends(get_current_user)):
    """Submit disposal request - syncs to Google Sheets"""
    from app.utils.sheets import add_disposal_log, add_approval_request
    from datetime import datetime

    try:
        data = await request.json()

        disposal_data = {
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'disposal_reason': data.get('disposal_reason'),
            'disposal_method': data.get('disposal_method', 'Standard'),
            'description': data.get('description'),
            'requested_by': current_user.full_name or current_user.email,
            'request_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'notes': data.get('notes', '')
        }

        log_success = add_disposal_log(disposal_data)

        approval_data = {
            'type': 'disposal_request',
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'submitted_by': current_user.full_name or current_user.email,
            'submitted_date': datetime.now().strftime('%Y-%m-%d'),
            'description': f"Disposal request: {data.get('description')}"
        }

        approval_success = add_approval_request(approval_data)

        if log_success and approval_success:
            return {"status": "success", "message": "Disposal request submitted and logged to Google Sheets"}
        else:
            return {"status": "error", "message": "Failed to sync with Google Sheets"}

    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/report")
async def submit_damage_report(request: Request, current_user = Depends(get_current_user)):
    """Submit damage report - syncs to Google Sheets"""
    from app.utils.sheets import add_damage_log, add_approval_request
    from datetime import datetime

    try:
        data = await request.json()

        damage_data = {
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'damage_type': data.get('damage_type'),
            'severity': data.get('severity'),
            'description': data.get('damage_description'),
            'reported_by': current_user.full_name or current_user.email,
            'report_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'location': data.get('location', ''),
            'room': data.get('room', ''),
            'notes': data.get('notes', '')
        }

        approval_data = {
            'type': 'damage_report',
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'submitted_by': current_user.full_name or current_user.email,
            'submitted_date': datetime.now().strftime('%Y-%m-%d'),
            'description': f"Damage report: {data.get('damage_description')}",
            'damage_type': data.get('damage_type'),
            'severity': data.get('severity')
        }

        approval_success = add_approval_request(approval_data)

        if approval_success:
            return {"status": "success", "message": "Damage report submitted for approval"}
        else:
            return {"status": "error", "message": "Failed to submit approval request"}

    except Exception as e:
        return {"status": "error", "message": str(e)}
# app/routes/disposal.py
from fastapi import APIRouter, Depends, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime

from app.database.database import get_db
from app.database.models import Profile
from app.utils.auth import get_admin_user
from app.utils.sheets import get_all_assets, update_asset, add_disposal_log
from app.utils.flash import set_flash

router = APIRouter(prefix="/disposal", tags=["disposal"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def disposal_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Disposal assets page (admin only)."""
    # Get assets that are ready to dispose only
    all_assets = get_all_assets()
    # Debug: check all statuses
    statuses = [str(asset.get('Status', '')).strip() for asset in all_assets]
    print(f"All statuses found: {set(statuses)}")
    
    disposable_assets = []
    for asset in all_assets:
        status = str(asset.get('Status', '')).strip()
        if status in ['To Be Disposed', 'To be Disposed', 'TO BE DISPOSED']:
            disposable_assets.append(asset)
    
    return templates.TemplateResponse(
        "disposal/index.html",
        {
            "request": request,
            "user": current_user,
            "assets": disposable_assets
        }
    )

@router.post("/dispose/{asset_id}")
async def dispose_asset(
    asset_id: str,
    request: Request,
    disposal_reason: str = Form(...),
    disposal_method: str = Form(...),
    description: str = Form(None),
    notes: str = Form(None),
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Dispose an asset (admin only)."""
    from app.utils.sheets import get_asset_by_id
    
    # Get asset data
    asset = get_asset_by_id(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    if str(asset.get('Status', '')).strip() != 'To Be Disposed':
        raise HTTPException(status_code=400, detail="Asset must be marked 'To Be Disposed' first")
    
    # Create disposal approval request
    from app.utils.sheets import add_approval_request
    
    approval_data = {
        'type': 'disposal',
        'asset_id': asset_id,
        'asset_name': asset.get('Item Name', ''),
        'submitted_by': current_user.full_name or current_user.email,
        'submitted_date': datetime.now().strftime('%Y-%m-%d'),
        'description': f"Disposal request: {disposal_reason} - {disposal_method}",
        'disposal_reason': disposal_reason,
        'disposal_method': disposal_method,
        'notes': f"Description: {description or ''} | Notes: {notes or ''}"
    }
    
    approval_success = add_approval_request(approval_data)
    
    if approval_success:
        response = RedirectResponse(url="/disposal", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, f"Disposal request for {asset.get('Item Name', '')} submitted for manager approval", "success")
        return response
    else:
        response = RedirectResponse(url="/disposal", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, "Error submitting disposal request", "error")
        return response
# app/routes/health.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
import time

from app.database.database import get_db
from app.config import load_config

router = APIRouter(tags=["health"])
config = load_config()

@router.get("/health")
async def health_check(db: Session = Depends(get_db)):
    """Health check endpoint."""
    start_time = time.time()
    
    # Check database connection
    try:
        db.execute(text("SELECT 1"))
        db_status = "healthy"
    except Exception as e:
        db_status = f"unhealthy: {str(e)}"
    
    # Check Google Sheets API
    sheets_status = "configured" if config.GOOGLE_SHEET_ID else "not configured"
    
    # Response time
    response_time = time.time() - start_time
    
    return {
        "status": "ok",
        "database": db_status,
        "google_sheets": sheets_status,
        "response_time_ms": round(response_time * 1000, 2)
    }
# /app/app/routes/home.py
import logging
from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse
from starlette.templating import Jinja2Templates
from app.utils.auth import get_current_user
from app.utils.sheets import get_summary_data, get_chart_data, get_all_assets

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=RedirectResponse)
async def redirect_root():
    return RedirectResponse("/dashboard")

@router.get("/dashboard")
async def home(request: Request, current_user = Depends(get_current_user)):
    try:
        # Summary and chart data
        summary_data = get_summary_data()
        chart_data = get_chart_data()
        all_assets = get_all_assets()

        # Filter out disposed assets for dashboard counts
        active_assets = [asset for asset in all_assets if asset.get("Status", "") != "Disposed"]
        disposed_assets = [asset for asset in all_assets if asset.get("Status", "") == "Disposed"]
        
        # Count assets by status and activity
        total_assets = len(active_assets)
        disposed_count = len(disposed_assets)
        damaged_count = len([a for a in all_assets if a.get("Status", "") == "Under Repair"])
        
        # Count assets by activity type
        relocated_count = len([a for a in all_assets if a.get("Last Activity", "") == "Relocated"])
        repaired_count = len([a for a in all_assets if a.get("Last Activity", "") == "Repaired"])
        to_be_disposed_count = len([a for a in all_assets if a.get("Status", "") == "To Be Disposed"])
        
        # Helper function to safely convert values to float
        def safe_float(value):
            if value is None or value == '':
                return 0.0
            try:
                return float(value)
            except (ValueError, TypeError):
                return 0.0
        
        # Calculate financial values directly from assets
        total_purchase_value = sum(safe_float(asset.get("Purchase Cost")) for asset in active_assets)
        total_book_value = sum(safe_float(asset.get("Book Value")) for asset in active_assets)
        # Calculate depreciation as purchase value minus book value
        total_depreciation_value = total_purchase_value - total_book_value
        category_counts = chart_data.get("category_counts", {})
        
        # Format location data
        location_data = chart_data.get("location_chart_data", {})
        location_counts = location_data.get("labels", [])
        location_values = location_data.get("values", [])
        location_counts_dict = dict(zip(location_counts, location_values))

        # Format time-based chart data
        monthly_data = chart_data.get("monthly_chart_data", {})
        monthly_chart_labels = monthly_data.get("labels", [])
        monthly_chart_values = monthly_data.get("values", [])
        
        # Generate quarterly data (last 12 quarters - 3 years)
        quarterly_chart_labels = []
        quarterly_chart_values = []
        
        # Get current year and quarter
        from datetime import datetime
        current_date = datetime.now()
        current_year = current_date.year
        current_quarter = (current_date.month - 1) // 3 + 1
        
        # Generate data for the last 12 quarters
        for i in range(11, -1, -1):
            year = current_year
            quarter = current_quarter - i
            
            # Adjust year if quarter is negative or > 4
            while quarter <= 0:
                year -= 1
                quarter += 4
            while quarter > 4:
                year += 1
                quarter -= 4
                
            quarterly_chart_labels.append(f"Q{quarter} {year}")
            
            # Count assets added in this quarter
            quarter_start_month = (quarter - 1) * 3 + 1
            quarter_end_month = quarter * 3
            
            count = 0
            for asset in all_assets:
                purchase_date = asset.get("Purchase Date", "")
                if purchase_date:
                    try:
                        date = datetime.strptime(purchase_date, "%Y-%m-%d")
                        if date.year == year and quarter_start_month <= date.month <= quarter_end_month:
                            count += 1
                    except:
                        pass
            
            quarterly_chart_values.append(count)
        
        # Generate yearly data (last 5 years)
        yearly_chart_labels = []
        yearly_chart_values = []
        
        # Generate data for the last 5 years
        for i in range(4, -1, -1):
            year = current_year - i
            yearly_chart_labels.append(str(year))
            
            # Count assets added in this year
            count = 0
            for asset in all_assets:
                purchase_date = asset.get("Purchase Date", "")
                if purchase_date:
                    try:
                        date = datetime.strptime(purchase_date, "%Y-%m-%d")
                        if date.year == year:
                            count += 1
                    except:
                        pass
            
            yearly_chart_values.append(count)

        # Format age distribution - convert to list of tuples for proper serialization
        age_distribution = chart_data.get("age_distribution", {})
        age_distribution_list = [
            {"label": str(k), "value": int(v)} 
            for k, v in age_distribution.items()
        ]

        # Format latest assets (excluding disposed assets)
        latest_assets = sorted(
            active_assets, 
            key=lambda a: a.get("Purchase Date", ""), 
            reverse=True
        )[:10]
        
        # Process assets to ensure they have a display_name field
        for asset in latest_assets:
            # Try different possible field names for the asset name
            name_fields = ["Name", "Asset Name", "AssetName", "Item Name", "Description", "Item"]
            display_name = None
            
            for field in name_fields:
                if asset.get(field):
                    display_name = asset.get(field)
                    break
            
            # If no name found, use a default
            if not display_name:
                display_name = f"Asset #{asset.get('ID', 'Unknown')}"
                
            # Add the display_name to the asset
            asset["display_name"] = display_name
            
        # Debug: Print the first asset's keys to see what fields are available
        if latest_assets:
            logging.info(f"Asset keys: {list(latest_assets[0].keys())}")
            logging.info(f"Asset display name: {latest_assets[0].get('display_name', 'Not found')}")
            logging.info(f"Original asset name fields: {[latest_assets[0].get(f, 'None') for f in name_fields]}")

        context = {
            "request": request,
            "user": current_user,
            "total_assets": total_assets,
            "total_purchase_value": total_purchase_value,
            "total_book_value": total_book_value,
            "total_depreciation_value": total_depreciation_value,
            "disposed_count": disposed_count,
            "damaged_count": damaged_count,
            "relocated_count": relocated_count,
            "repaired_count": repaired_count,
            "to_be_disposed_count": to_be_disposed_count,
            "category_counts": category_counts,
            "location_counts": location_counts_dict,
            "monthly_chart_labels": monthly_chart_labels,
            "monthly_chart_values": monthly_chart_values,
            "quarterly_chart_labels": quarterly_chart_labels,
            "quarterly_chart_values": quarterly_chart_values,
            "yearly_chart_labels": yearly_chart_labels,
            "yearly_chart_values": yearly_chart_values,
            "age_distribution": age_distribution_list,
            "latest_assets": latest_assets
        }

        return templates.TemplateResponse("dashboard.html", context)

    except Exception as e:
        logging.error("Dashboard error: %s", e, exc_info=True)
        return templates.TemplateResponse("error.html", {
            "request": request,
            "user": current_user,
            "message": "Terjadi kesalahan saat memuat dashboard.",
        })
from fastapi import APIRouter, Request, Response, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from supabase import create_client, Client
from app.config import load_config
import logging

config = load_config()
supabase: Client = create_client(config.SUPABASE_URL, config.SUPABASE_ANON_KEY)

router = APIRouter(tags=["authentication"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/login", response_class=HTMLResponse)
@router.head("/login", response_class=HTMLResponse)
async def login_page(request: Request, next: str = None):
    return templates.TemplateResponse("login_logout.html", {"request": request, "next": next})

@router.post("/login", response_class=HTMLResponse)
async def login_form(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    next: str = Form(None)
):
    try:
        # Use service key client for admin operations
        from supabase import create_client
        admin_supabase = create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_KEY)
        
        response = admin_supabase.auth.sign_in_with_password({
            "email": email,
            "password": password
        })
        
        if not response.user:
            return templates.TemplateResponse(
                "login_logout.html",
                {"request": request, "error": "Invalid email or password", "next": next},
                status_code=401
            )
        
        # Get user profile
        profile_response = admin_supabase.table('profiles').select('*').eq('id', response.user.id).single().execute()
        if not profile_response.data or not profile_response.data.get('is_active'):
            return templates.TemplateResponse(
                "login_logout.html",
                {"request": request, "error": "Account is inactive", "next": next},
                status_code=401
            )
        
        redirect_url = next if next else "/"
        redirect_response = RedirectResponse(url=redirect_url, status_code=303)
        
        redirect_response.set_cookie(
            key="sb_access_token",
            value=response.session.access_token,
            httponly=True,
            max_age=3600,
            samesite="lax",
            secure=True,
            domain=".onrender.com"
        )
        
        return redirect_response
        
    except Exception as e:
        logging.error(f"Login error: {str(e)}")
        return templates.TemplateResponse(
            "login_logout.html",
            {"request": request, "error": "Login failed", "next": next},
            status_code=401
        )

@router.get("/auth/callback")
async def auth_callback(request: Request):
    return templates.TemplateResponse("auth_callback.html", {"request": request})

@router.get("/logout")
async def logout():
    try:
        supabase.auth.sign_out()
    except:
        pass
    
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(key="sb_access_token")
    return response
# app/routes/logs.py
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.database.models import Profile
from app.utils.auth import get_current_user
from app.utils.sheets import get_all_approvals

router = APIRouter(prefix="/logs", tags=["logs"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def logs_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """View approval logs based on user role."""
    all_approvals = get_all_approvals()
    
    # Filter based on user role
    if current_user.role.value == 'staff':
        # Staff can only see their own requests
        user_identifier = current_user.full_name or current_user.email
        approvals = [a for a in all_approvals if a.get('Submitted_By') == user_identifier]
    else:
        # Manager and admin can see all approvals
        approvals = all_approvals
    
    # Separate pending and completed
    pending_approvals = [a for a in approvals if a.get('Status') == 'Pending']
    completed_approvals = [a for a in approvals if a.get('Status') in ['Approved', 'Rejected']]
    
    return templates.TemplateResponse(
        "logs/index.html",
        {
            "request": request,
            "user": current_user,
            "pending_approvals": pending_approvals,
            "completed_approvals": completed_approvals
        }
    )
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
from fastapi import APIRouter, Depends, Request, Form, UploadFile, File, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from app.database.database import get_db
from app.database.models import Profile
from app.utils.auth import get_current_user
from app.utils.photo import resize_and_convert_image, upload_to_drive
from app.utils.flash import set_flash

router = APIRouter(tags=["profile"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/profile", response_class=HTMLResponse)
async def profile_page(
    request: Request,
    current_user = Depends(get_current_user)
):
    """User profile page."""
    return templates.TemplateResponse(
        "profile/view.html",
        {
            "request": request,
            "user": current_user
        }
    )

@router.get("/profile/edit", response_class=HTMLResponse)
async def edit_profile_page(
    request: Request,
    current_user = Depends(get_current_user)
):
    """Edit user profile page."""
    return templates.TemplateResponse(
        "profile/edit.html",
        {
            "request": request,
            "user": current_user
        }
    )

@router.post("/profile/edit")
async def update_profile(
    request: Request,
    full_name: str = Form(...),
    email: str = Form(...),
    photo: UploadFile = File(None),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Update user profile."""
    # Update basic info
    current_user.full_name = full_name
    current_user.email = email
    current_user.updated_at = datetime.now(timezone.utc)
    
    # Handle photo upload if provided
    if photo and photo.filename:
        try:
            # Process image
            contents = await photo.read()
            import io
            image_file = io.BytesIO(contents)
            processed_image = resize_and_convert_image(image_file)
            
            if processed_image:
                # Upload to Google Drive
                photo_url = upload_to_drive(
                    processed_image, 
                    photo.filename, 
                    f"profile_{current_user.email}"
                )
                if photo_url:
                    current_user.photo_url = photo_url
        except Exception as e:
            return templates.TemplateResponse(
                "profile/edit.html",
                {
                    "request": request,
                    "user": current_user,
                    "error": f"Error uploading photo: {str(e)}"
                },
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    # Save changes
    db.commit()
    
    # Redirect to profile page
    response = RedirectResponse(url="/profile", status_code=status.HTTP_303_SEE_OTHER)
    set_flash(response, "Profile updated successfully", "success")
    return response
# app/routes/relocation.py
from fastapi import APIRouter, Depends, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime
import json

from app.database.database import get_db
from app.database.models import Profile
from app.utils.auth import get_current_user
from app.utils.sheets import get_all_assets, get_dropdown_options, add_approval_request
from app.utils.flash import set_flash

router = APIRouter(prefix="/relocation", tags=["relocation"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def relocation_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Asset relocation page."""
    # Get assets and dropdown options
    all_assets = get_all_assets()
    dropdown_options = get_dropdown_options()
    
    return templates.TemplateResponse(
        "relocation/index.html",
        {
            "request": request,
            "user": current_user,
            "assets": all_assets,
            "dropdown_options": dropdown_options
        }
    )

@router.post("/relocate/{asset_id}")
async def relocate_asset(
    asset_id: str,
    request: Request,
    new_location: str = Form(...),
    new_room: str = Form(...),
    reason: str = Form(...),
    notes: str = Form(None),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Submit asset relocation request."""
    from app.utils.sheets import get_asset_by_id
    
    # Get asset data
    asset = get_asset_by_id(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    # Create relocation approval request
    relocation_data = {
        'new_location': new_location,
        'new_room': new_room,
        'current_location': asset.get('Location', ''),
        'current_room': asset.get('Room', ''),
        'reason': reason,
        'notes': notes or ''
    }
    
    approval_data = {
        'type': 'relocation',
        'asset_id': asset_id,
        'asset_name': asset.get('Item Name', ''),
        'submitted_by': current_user.full_name or current_user.email,
        'submitted_date': datetime.now().strftime('%Y-%m-%d'),
        'description': f"Relocate from {asset.get('Location', '')} - {asset.get('Room', '')} to {new_location} - {new_room}",
        'request_data': json.dumps(relocation_data, ensure_ascii=False)
    }
    
    approval_success = add_approval_request(approval_data)
    
    if approval_success:
        response = RedirectResponse(url="/relocation", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, f"Relocation request for {asset.get('Item Name', '')} submitted for approval", "success")
        return response
    else:
        response = RedirectResponse(url="/relocation", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, "Error submitting relocation request", "error")
        return response
# /app/app/routes/repair.py
from fastapi import APIRouter, Request, Depends
from starlette.templating import Jinja2Templates
from app.utils.auth import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.post("/action")
async def submit_repair_action(request: Request, current_user = Depends(get_current_user)):
    """Submit repair action - creates approval request for store, direct action for allocate"""
    from app.utils.sheets import add_repair_log, update_asset, add_approval_request
    from datetime import datetime
    
    try:
        # Get JSON data
        data = await request.json()
        action_type = data.get('action_type')  # 'store' or 'allocate'
        
        if action_type == 'store':
            # Store action requires approval - only create approval request
            approval_data = {
                'type': 'repair_action',
                'asset_id': data.get('asset_id'),
                'asset_name': data.get('asset_name'),
                'submitted_by': current_user.full_name or current_user.email,
                'submitted_date': datetime.now().strftime('%Y-%m-%d'),
                'description': f"Request to store asset: {data.get('description')}",
                'action': 'Store Asset'
            }
            
            approval_success = add_approval_request(approval_data)
            
            if approval_success:
                return {"status": "success", "message": "Store request submitted for admin approval"}
            else:
                return {"status": "error", "message": "Failed to submit approval request"}
        
        else:  # allocate - direct action
            # Add to Repair_Log sheet
            repair_data = {
                'asset_id': data.get('asset_id'),
                'asset_name': data.get('asset_name'),
                'repair_action': 'Allocate Asset',
                'action_type': action_type,
                'description': data.get('description', ''),
                'performed_by': current_user.full_name or current_user.email,
                'action_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'new_location': data.get('location', ''),
                'new_room': data.get('room', ''),
                'notes': data.get('notes', '')
            }
            
            # Add to repair log
            log_success = add_repair_log(repair_data)
            
            # Update asset from Under Repair to Active
            update_data = {
                'Status': 'Active',
                'Bisnis Unit': data.get('business_unit', ''),
                'Location': data.get('location', ''),
                'Room': data.get('room', '')
            }
            
            asset_success = update_asset(data.get('asset_id'), update_data)
            
            if log_success and asset_success:
                return {"status": "success", "message": "Asset allocated successfully and synced to Google Sheets"}
            else:
                return {"status": "error", "message": "Failed to sync with Google Sheets"}
            
    except Exception as e:
        return {"status": "error", "message": str(e)}
# app/routes/user_management.py
from fastapi import APIRouter, Depends, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.database.models import Profile, UserRole
from app.utils.auth import get_current_user, get_admin_user
from app.utils.flash import set_flash

router = APIRouter(prefix="/user_management", tags=["user_management"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def user_list(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """List all users (admin only)."""
    users = db.query(Profile).all()
    
    return templates.TemplateResponse(
        "user_management/list.html",
        {
            "request": request,
            "user": current_user,
            "users": users
        }
    )

@router.get("/create", response_class=HTMLResponse)
async def create_user_form(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Create user form (admin only)."""
    return templates.TemplateResponse(
        "user_management/create.html",
        {
            "request": request,
            "user": current_user
        }
    )

@router.post("/create")
async def create_user(
    request: Request,
    email: str = Form(...),
    full_name: str = Form(...),
    role: str = Form(...),
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Create new user (admin only)."""
    # Check if user exists
    existing_user = db.query(Profile).filter(Profile.email == email).first()
    if existing_user:
        return templates.TemplateResponse(
            "user_management/create.html",
            {
                "request": request,
                "user": current_user,
                "error": "Email already exists"
            }
        )
    
    # Create user profile (Supabase handles auth)
    new_user = Profile(
        email=email,
        full_name=full_name,
        role=getattr(UserRole, role.upper()),
        is_active=True
    )
    
    db.add(new_user)
    db.commit()
    
    response = RedirectResponse(url="/user_management", status_code=status.HTTP_303_SEE_OTHER)
    set_flash(response, f"User {email} created successfully", "success")
    return response

@router.post("/reset_password/{user_id}")
async def reset_password(
    user_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Reset user password to default (admin only)."""
    user = db.query(Profile).filter(Profile.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Password reset handled by Supabase
    default_password = f"{user.email.split('@')[0]}123"
    
    response = RedirectResponse(url="/user_management", status_code=status.HTTP_303_SEE_OTHER)
    set_flash(response, f"Password reset instructions sent to {user.email}", "success")
    return response

@router.post("/toggle_status/{user_id}")
async def toggle_user_status(
    user_id: str,
    request: Request,
    is_active: bool = Form(...),
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Toggle user active status (admin only)."""
    user = db.query(Profile).filter(Profile.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Update status
    user.is_active = is_active
    db.commit()
    
    status_text = "activated" if is_active else "deactivated"
    response = RedirectResponse(url="/user_management", status_code=status.HTTP_303_SEE_OTHER)
    set_flash(response, f"User {user.email} {status_text}", "success")
    return response
# app/routes/__init__.py

# Import all route modules to make them available from app.routes
from app.routes import (
    home,
    assets,
    asset_management,
    login,
    damage,
    health,
    offline,
    profile,
    repair,
    approvals,
    disposal,
    user_management,
    logs,
    relocation
)
# app/routes/approvals.py
from fastapi import APIRouter, Depends, Request, HTTPException, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.utils.auth import get_current_user
from app.utils.sheets import get_all_approvals, update_approval_status

router = APIRouter(prefix="/approvals", tags=["approvals"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def approvals_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Approvals page for admin and manager."""
    if current_user.role not in ['admin', 'manager']:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get all approvals from Google Sheets
    all_approvals = get_all_approvals()
    
    # Filter approvals based on user role
    if current_user.role == 'admin':
        # Admin sees all approvals except disposal and edit_asset
        approvals_data = [a for a in all_approvals if a.get('Type') not in ['disposal', 'edit_asset']]
    elif current_user.role == 'manager':
        # Manager sees disposal and edit_asset approvals
        approvals_data = [a for a in all_approvals if a.get('Type') in ['disposal', 'edit_asset']]
    else:
        approvals_data = []
    
    return templates.TemplateResponse(
        "approvals/list.html",
        {
            "request": request,
            "user": current_user,
            "approvals_data": approvals_data
        }
    )

@router.post("/approve/{approval_id}")
async def approve_request(
    approval_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Approve a request."""
    if current_user.role not in ['admin', 'manager']:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get approval details
    all_approvals = get_all_approvals()
    approval = next((a for a in all_approvals if str(a.get('ID')) == str(approval_id)), None)
    
    if not approval:
        return JSONResponse({"status": "error", "message": "Approval not found"})
    
    # Process approval based on type
    try:
        if approval.get('Type') == 'damage_report':
            # Update asset status to "Under Repair"
            from app.utils.sheets import update_asset
            success = update_asset(approval.get('Asset_ID'), {'Status': 'Under Repair'})
            if not success:
                return JSONResponse({"status": "error", "message": "Failed to update asset status"})
        
        elif approval.get('Type') == 'relocation':
            # Process relocation approval
            import json
            try:
                request_data_str = approval.get('Request_Data', '')
                if request_data_str:
                    relocation_data = json.loads(request_data_str)
                    update_data = {
                        'Location': relocation_data.get('new_location'),
                        'Room': relocation_data.get('new_room')
                    }
                    from app.utils.sheets import update_asset
                    success = update_asset(approval.get('Asset_ID'), update_data)
                    if not success:
                        return JSONResponse({"status": "error", "message": "Failed to relocate asset"})
            except Exception as e:
                return JSONResponse({"status": "error", "message": f"Error processing relocation: {str(e)}"})
            
        elif approval.get('Type') == 'edit_asset':
            # Process edit asset approval
            import json
            try:
                request_data_str = approval.get('Request_Data', '')
                if request_data_str:
                    edit_data = json.loads(request_data_str)
                    from app.utils.sheets import update_asset
                    success = update_asset(approval.get('Asset_ID'), edit_data)
                    if not success:
                        return JSONResponse({"status": "error", "message": "Failed to update asset"})
            except Exception as e:
                return JSONResponse({"status": "error", "message": f"Error processing edit: {str(e)}"})
        
        # Update approval status
        approval_update = {
            'Status': 'Approved',
            'Approved_By': current_user.full_name or current_user.email,
            'Approved_Date': __import__('datetime').datetime.now().strftime('%Y-%m-%d')
        }
        
        success = update_approval_status(approval_id, approval_update)
        
        if success:
            return JSONResponse({"status": "success", "message": "Request approved successfully"})
        else:
            return JSONResponse({"status": "error", "message": "Failed to update approval status"})
            
    except Exception as e:
        return JSONResponse({"status": "error", "message": f"Error processing approval: {str(e)}"})

@router.post("/reject/{approval_id}")
async def reject_request(
    approval_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Reject a request."""
    if current_user.role not in ['admin', 'manager']:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Update approval status
    approval_update = {
        'Status': 'Rejected',
        'Approved_By': current_user.full_name or current_user.email,
        'Approved_Date': __import__('datetime').datetime.now().strftime('%Y-%m-%d')
    }
    
    success = update_approval_status(approval_id, approval_update)
    
    if success:
        return JSONResponse({"status": "success", "message": "Request rejected"})
    else:
        return JSONResponse({"status": "error", "message": "Failed to update approval status"})
from fastapi import APIRouter, Request, Depends
from starlette.templating import Jinja2Templates
from app.utils.auth import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/assets")
async def assets_page(request: Request, current_user=Depends(get_current_user)):
    """Assets listing page with filtering and pagination"""
    from app.utils.sheets import get_all_assets
    
    # Ambil data asset dari Google Sheets
    all_assets = get_all_assets()
    
    # Filter hanya aset aktif (bukan Disposed)
    active_assets = [asset for asset in all_assets if asset.get("Status", "").lower() != "disposed"]
    
    return templates.TemplateResponse("assets.html", {
        "request": request,
        "user": current_user,
        "assets_data": active_assets
    })
# app/routes/asset_management.py
from fastapi import APIRouter, Depends, Request, Form, File, UploadFile, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import json
from datetime import datetime
import io

from app.database.database import get_db
from app.database.models import Profile, UserRole
from app.utils.photo import resize_and_convert_image, upload_to_drive
from app.utils.sheets import get_dropdown_options, add_asset as sheets_add_asset
from app.utils.flash import set_flash
from app.utils.auth import get_current_user, get_admin_user
from app.config import load_config

config = load_config()
router = APIRouter(prefix="/asset_management", tags=["asset_management"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/add", response_class=HTMLResponse)
async def add_asset_form(
    request: Request,
    db: Session = Depends(get_db),
    current_profile = Depends(get_current_user)
):
    """Form to add a new asset."""
    dropdown_options = get_dropdown_options()
    return templates.TemplateResponse(
        "asset_management/add.html",
        {
            "request": request,
            "user": current_profile,
            "dropdown_options": dropdown_options
        }
    )


@router.get("/list", response_class=HTMLResponse)
async def asset_list(
    request: Request,
    db: Session = Depends(get_db),
    current_profile = Depends(get_current_user)
):
    """List assets for editing (admin and manager only)."""
    if current_profile.role not in [UserRole.ADMIN, UserRole.MANAGER]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    from app.utils.sheets import get_all_assets
    assets = get_all_assets()
    
    locations = list(set(asset.get('Location', '') for asset in assets if asset.get('Location')))
    location_rooms = {}
    for asset in assets:
        location = asset.get('Location', '')
        room = asset.get('Room', '')
        if location and room:
            if location not in location_rooms:
                location_rooms[location] = set()
            location_rooms[location].add(room)
    
    for location in location_rooms:
        location_rooms[location] = list(location_rooms[location])
    
    return templates.TemplateResponse(
        "asset_management/list.html",
        {
            "request": request,
            "user": current_profile,
            "assets": assets,
            "locations": sorted(locations),
            "location_rooms": location_rooms
        }
    )


@router.get("/edit/{asset_id}", response_class=HTMLResponse)
async def edit_asset_form(
    asset_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_profile = Depends(get_current_user)
):
    """Form to edit an existing asset (admin/manager only)."""
    if current_profile.role not in [UserRole.ADMIN, UserRole.MANAGER]:
        raise HTTPException(status_code=403, detail="Access denied")

    from app.utils.sheets import get_asset_by_id
    asset = get_asset_by_id(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    dropdown_options = get_dropdown_options()
    
    return templates.TemplateResponse(
        "asset_management/edit.html",
        {
            "request": request,
            "user": current_profile,
            "asset": asset,
            "dropdown_options": dropdown_options
        }
    )


@router.post("/edit/{asset_id}")
async def update_asset(
    asset_id: str,
    request: Request,
    status: str = Form(...),
    company: str = Form(...),
    location: str = Form(...),
    room: str = Form(...),
    bisnis_unit: str = Form(None),
    edit_reason: str = Form(...),
    db: Session = Depends(get_db),
    current_profile = Depends(get_current_user)
):
    """Update existing asset (admin and manager only)."""
    if current_profile.role not in [UserRole.ADMIN, UserRole.MANAGER]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    from app.utils.sheets import update_asset as sheets_update_asset, calculate_asset_financials, get_asset_by_id
    asset = get_asset_by_id(asset_id)

    update_data = {
        "Status": status,
        "Company": company,
        "Location": location,
        "Room": room,
        "Bisnis Unit": bisnis_unit or ""
    }
    
    # Jika perlu hitung ulang nilai finansial, misalnya setelah perubahan harga
    # financials = calculate_asset_financials(purchase_cost, purchase_date, category)
    # update_data.update(financials)
    
    from app.utils.sheets import add_approval_request
    
    approval_data = {
        'type': 'edit_asset',
        'asset_id': asset_id,
        'asset_name': asset.get('Item Name', ''),
        'submitted_by': current_profile.full_name or current_profile.email,
        'submitted_date': datetime.now().strftime('%Y-%m-%d'),
        'description': f"Edit asset: {asset.get('Item Name', '')} - Reason: {edit_reason}",
        'edit_reason': edit_reason,
        'request_data': json.dumps(update_data, ensure_ascii=False)
    }
    
    approval_success = add_approval_request(approval_data)
    
    if approval_success:
        response = RedirectResponse(url="/asset_management/list", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, "Asset edit request submitted for manager approval", "success")
        return response
    else:
        dropdown_options = get_dropdown_options()
        return templates.TemplateResponse(
            "asset_management/edit.html",
            {
                "request": request,
                "user": current_profile,
                "asset": asset,
                "dropdown_options": dropdown_options,
                "error": "Error submitting edit request"
            },
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@router.post("/add")
async def add_asset(
    request: Request,
    item_name: str = Form(...),
    category: str = Form(...),
    type: str = Form(...),
    manufacture: str = Form(None),
    model: str = Form(None),
    serial_number: str = Form(None),
    company: str = Form(...),
    bisnis_unit: str = Form(None),
    location: str = Form(...),
    room: str = Form(...),
    notes: str = Form(None),
    item_condition: str = Form(None),
    purchase_date: str = Form(...),
    purchase_cost: str = Form(...),
    warranty: str = Form(None),
    supplier: str = Form(None),
    journal: str = Form(None),
    owner: str = Form(...),
    photo: UploadFile = File(None),
    db: Session = Depends(get_db),
    current_profile = Depends(get_current_user)
):
    """Process add asset form."""
    dropdown_options = get_dropdown_options()
    
    asset_data = {
        "Item Name": item_name,
        "Category": category,
        "Type": type,
        "Manufacture": manufacture or "",
        "Model": model or "",
        "Serial Number": serial_number or "",
        "Company": company,
        "Bisnis Unit": bisnis_unit or "",
        "Location": location,
        "Room": room,
        "Notes": notes or "",
        "Item Condition": item_condition or "",
        "Purchase Date": purchase_date,
        "Purchase Cost": purchase_cost,
        "Warranty": warranty or "",
        "Supplier": supplier or "",
        "Journal": journal or "",
        "Owner": owner,
        "Status": "Active"
    }
    
    photo_url = None
    if photo and photo.filename:
        try:
            contents = await photo.read()
            image_file = io.BytesIO(contents)
            processed_image = resize_and_convert_image(image_file)
            
            if processed_image:
                photo_url = upload_to_drive(processed_image, photo.filename, "new")
                if photo_url:
                    asset_data["Photo URL"] = photo_url
        except Exception as e:
            print(f"Error processing photo: {str(e)}")
    
    if current_profile.role == UserRole.ADMIN:
        success = sheets_add_asset(asset_data)
        
        if success:
            response = RedirectResponse(url="/assets/", status_code=status.HTTP_303_SEE_OTHER)
            set_flash(response, "Asset added successfully", "success")
            return response
        else:
            return templates.TemplateResponse(
                "asset_management/add.html",
                {
                    "request": request,
                    "user": current_profile,
                    "dropdown_options": dropdown_options,
                    "error": "Error adding asset to Google Sheets",
                    "form_data": asset_data
                },
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    from app.utils.sheets import add_approval_request
    
    approval_data = {
        'type': 'add_asset',
        'asset_id': 'NEW',
        'asset_name': item_name,
        'submitted_by': current_profile.full_name or current_profile.email,
        'submitted_date': datetime.now().strftime('%Y-%m-%d'),
        'description': f"Add new asset: {item_name}",
        'request_data': json.dumps(asset_data, ensure_ascii=False)
    }
    
    approval_success = add_approval_request(approval_data)
    
    if approval_success:
        response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, "Asset request submitted for approval", "success")
        return response
    else:
        return templates.TemplateResponse(
            "asset_management/add.html",
            {
                "request": request,
                "user": current_profile,
                "dropdown_options": dropdown_options,
                "error": "Error submitting approval request",
                "form_data": asset_data
            },
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
from fastapi import APIRouter, Request, Depends
from starlette.templating import Jinja2Templates
from app.utils.auth import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/")
async def damaged_assets_page(request: Request, current_user = Depends(get_current_user)):
    """Damaged assets page with search and log functionality"""
    from app.utils.sheets import get_all_assets, get_dropdown_options

    all_assets = get_all_assets()
    dropdown_options = get_dropdown_options()

    return templates.TemplateResponse("damaged_assets.html", {
        "request": request,
        "user": current_user,
        "assets_data": all_assets,
        "dropdown_options": dropdown_options
    })


@router.post("/lost")
async def submit_lost_report(request: Request, current_user = Depends(get_current_user)):
    """Submit lost report - syncs to Google Sheets"""
    from app.utils.sheets import add_lost_log, add_approval_request
    from datetime import datetime

    try:
        data = await request.json()

        lost_data = {
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'last_location': data.get('last_location'),
            'last_room': data.get('last_room', ''),
            'date_lost': data.get('date_lost'),
            'description': data.get('description'),
            'reported_by': current_user.full_name or current_user.email,
            'report_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'notes': data.get('notes', '')
        }

        log_success = add_lost_log(lost_data)

        approval_data = {
            'type': 'lost_report',
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'submitted_by': current_user.full_name or current_user.email,
            'submitted_date': datetime.now().strftime('%Y-%m-%d'),
            'description': f"Lost report: {data.get('description')}",
            'location': data.get('last_location')
        }

        approval_success = add_approval_request(approval_data)

        if log_success and approval_success:
            return {"status": "success", "message": "Lost report submitted and logged to Google Sheets"}
        else:
            return {"status": "error", "message": "Failed to sync with Google Sheets"}

    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/disposal")
async def submit_disposal_request(request: Request, current_user = Depends(get_current_user)):
    """Submit disposal request - syncs to Google Sheets"""
    from app.utils.sheets import add_disposal_log, add_approval_request
    from datetime import datetime

    try:
        data = await request.json()

        disposal_data = {
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'disposal_reason': data.get('disposal_reason'),
            'disposal_method': data.get('disposal_method', 'Standard'),
            'description': data.get('description'),
            'requested_by': current_user.full_name or current_user.email,
            'request_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'notes': data.get('notes', '')
        }

        log_success = add_disposal_log(disposal_data)

        approval_data = {
            'type': 'disposal_request',
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'submitted_by': current_user.full_name or current_user.email,
            'submitted_date': datetime.now().strftime('%Y-%m-%d'),
            'description': f"Disposal request: {data.get('description')}"
        }

        approval_success = add_approval_request(approval_data)

        if log_success and approval_success:
            return {"status": "success", "message": "Disposal request submitted and logged to Google Sheets"}
        else:
            return {"status": "error", "message": "Failed to sync with Google Sheets"}

    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/report")
async def submit_damage_report(request: Request, current_user = Depends(get_current_user)):
    """Submit damage report - syncs to Google Sheets"""
    from app.utils.sheets import add_damage_log, add_approval_request
    from datetime import datetime

    try:
        data = await request.json()

        damage_data = {
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'damage_type': data.get('damage_type'),
            'severity': data.get('severity'),
            'description': data.get('damage_description'),
            'reported_by': current_user.full_name or current_user.email,
            'report_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'location': data.get('location', ''),
            'room': data.get('room', ''),
            'notes': data.get('notes', '')
        }

        approval_data = {
            'type': 'damage_report',
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'submitted_by': current_user.full_name or current_user.email,
            'submitted_date': datetime.now().strftime('%Y-%m-%d'),
            'description': f"Damage report: {data.get('damage_description')}",
            'damage_type': data.get('damage_type'),
            'severity': data.get('severity')
        }

        approval_success = add_approval_request(approval_data)

        if approval_success:
            return {"status": "success", "message": "Damage report submitted for approval"}
        else:
            return {"status": "error", "message": "Failed to submit approval request"}

    except Exception as e:
        return {"status": "error", "message": str(e)}
# app/routes/disposal.py
from fastapi import APIRouter, Depends, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime

from app.database.database import get_db
from app.database.models import Profile
from app.utils.auth import get_admin_user
from app.utils.sheets import get_all_assets, update_asset, add_disposal_log
from app.utils.flash import set_flash

router = APIRouter(prefix="/disposal", tags=["disposal"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def disposal_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Disposal assets page (admin only)."""
    # Get assets that are ready to dispose only
    all_assets = get_all_assets()
    # Debug: check all statuses
    statuses = [str(asset.get('Status', '')).strip() for asset in all_assets]
    print(f"All statuses found: {set(statuses)}")
    
    disposable_assets = []
    for asset in all_assets:
        status = str(asset.get('Status', '')).strip()
        if status in ['To Be Disposed', 'To be Disposed', 'TO BE DISPOSED']:
            disposable_assets.append(asset)
    
    return templates.TemplateResponse(
        "disposal/index.html",
        {
            "request": request,
            "user": current_user,
            "assets": disposable_assets
        }
    )

@router.post("/dispose/{asset_id}")
async def dispose_asset(
    asset_id: str,
    request: Request,
    disposal_reason: str = Form(...),
    disposal_method: str = Form(...),
    description: str = Form(None),
    notes: str = Form(None),
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Dispose an asset (admin only)."""
    from app.utils.sheets import get_asset_by_id
    
    # Get asset data
    asset = get_asset_by_id(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    if str(asset.get('Status', '')).strip() != 'To Be Disposed':
        raise HTTPException(status_code=400, detail="Asset must be marked 'To Be Disposed' first")
    
    # Create disposal approval request
    from app.utils.sheets import add_approval_request
    
    approval_data = {
        'type': 'disposal',
        'asset_id': asset_id,
        'asset_name': asset.get('Item Name', ''),
        'submitted_by': current_user.full_name or current_user.email,
        'submitted_date': datetime.now().strftime('%Y-%m-%d'),
        'description': f"Disposal request: {disposal_reason} - {disposal_method}",
        'disposal_reason': disposal_reason,
        'disposal_method': disposal_method,
        'notes': f"Description: {description or ''} | Notes: {notes or ''}"
    }
    
    approval_success = add_approval_request(approval_data)
    
    if approval_success:
        response = RedirectResponse(url="/disposal", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, f"Disposal request for {asset.get('Item Name', '')} submitted for manager approval", "success")
        return response
    else:
        response = RedirectResponse(url="/disposal", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, "Error submitting disposal request", "error")
        return response
# app/routes/health.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
import time

from app.database.database import get_db
from app.config import load_config

router = APIRouter(tags=["health"])
config = load_config()

@router.get("/health")
async def health_check(db: Session = Depends(get_db)):
    """Health check endpoint."""
    start_time = time.time()
    
    # Check database connection
    try:
        db.execute(text("SELECT 1"))
        db_status = "healthy"
    except Exception as e:
        db_status = f"unhealthy: {str(e)}"
    
    # Check Google Sheets API
    sheets_status = "configured" if config.GOOGLE_SHEET_ID else "not configured"
    
    # Response time
    response_time = time.time() - start_time
    
    return {
        "status": "ok",
        "database": db_status,
        "google_sheets": sheets_status,
        "response_time_ms": round(response_time * 1000, 2)
    }
# /app/app/routes/home.py
import logging
from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse
from starlette.templating import Jinja2Templates
from app.utils.auth import get_current_user
from app.utils.sheets import get_summary_data, get_chart_data, get_all_assets

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=RedirectResponse)
async def redirect_root():
    return RedirectResponse("/dashboard")

@router.get("/dashboard")
async def home(request: Request, current_user = Depends(get_current_user)):
    try:
        # Summary and chart data
        summary_data = get_summary_data()
        chart_data = get_chart_data()
        all_assets = get_all_assets()

        # Filter out disposed assets for dashboard counts
        active_assets = [asset for asset in all_assets if asset.get("Status", "") != "Disposed"]
        disposed_assets = [asset for asset in all_assets if asset.get("Status", "") == "Disposed"]
        
        # Count assets by status and activity
        total_assets = len(active_assets)
        disposed_count = len(disposed_assets)
        damaged_count = len([a for a in all_assets if a.get("Status", "") == "Under Repair"])
        
        # Count assets by activity type
        relocated_count = len([a for a in all_assets if a.get("Last Activity", "") == "Relocated"])
        repaired_count = len([a for a in all_assets if a.get("Last Activity", "") == "Repaired"])
        to_be_disposed_count = len([a for a in all_assets if a.get("Status", "") == "To Be Disposed"])
        
        # Helper function to safely convert values to float
        def safe_float(value):
            if value is None or value == '':
                return 0.0
            try:
                return float(value)
            except (ValueError, TypeError):
                return 0.0
        
        # Calculate financial values directly from assets
        total_purchase_value = sum(safe_float(asset.get("Purchase Cost")) for asset in active_assets)
        total_book_value = sum(safe_float(asset.get("Book Value")) for asset in active_assets)
        # Calculate depreciation as purchase value minus book value
        total_depreciation_value = total_purchase_value - total_book_value
        category_counts = chart_data.get("category_counts", {})
        
        # Format location data
        location_data = chart_data.get("location_chart_data", {})
        location_counts = location_data.get("labels", [])
        location_values = location_data.get("values", [])
        location_counts_dict = dict(zip(location_counts, location_values))

        # Format time-based chart data
        monthly_data = chart_data.get("monthly_chart_data", {})
        monthly_chart_labels = monthly_data.get("labels", [])
        monthly_chart_values = monthly_data.get("values", [])
        
        # Generate quarterly data (last 12 quarters - 3 years)
        quarterly_chart_labels = []
        quarterly_chart_values = []
        
        # Get current year and quarter
        from datetime import datetime
        current_date = datetime.now()
        current_year = current_date.year
        current_quarter = (current_date.month - 1) // 3 + 1
        
        # Generate data for the last 12 quarters
        for i in range(11, -1, -1):
            year = current_year
            quarter = current_quarter - i
            
            # Adjust year if quarter is negative or > 4
            while quarter <= 0:
                year -= 1
                quarter += 4
            while quarter > 4:
                year += 1
                quarter -= 4
                
            quarterly_chart_labels.append(f"Q{quarter} {year}")
            
            # Count assets added in this quarter
            quarter_start_month = (quarter - 1) * 3 + 1
            quarter_end_month = quarter * 3
            
            count = 0
            for asset in all_assets:
                purchase_date = asset.get("Purchase Date", "")
                if purchase_date:
                    try:
                        date = datetime.strptime(purchase_date, "%Y-%m-%d")
                        if date.year == year and quarter_start_month <= date.month <= quarter_end_month:
                            count += 1
                    except:
                        pass
            
            quarterly_chart_values.append(count)
        
        # Generate yearly data (last 5 years)
        yearly_chart_labels = []
        yearly_chart_values = []
        
        # Generate data for the last 5 years
        for i in range(4, -1, -1):
            year = current_year - i
            yearly_chart_labels.append(str(year))
            
            # Count assets added in this year
            count = 0
            for asset in all_assets:
                purchase_date = asset.get("Purchase Date", "")
                if purchase_date:
                    try:
                        date = datetime.strptime(purchase_date, "%Y-%m-%d")
                        if date.year == year:
                            count += 1
                    except:
                        pass
            
            yearly_chart_values.append(count)

        # Format age distribution - convert to list of tuples for proper serialization
        age_distribution = chart_data.get("age_distribution", {})
        age_distribution_list = [
            {"label": str(k), "value": int(v)} 
            for k, v in age_distribution.items()
        ]

        # Format latest assets (excluding disposed assets)
        latest_assets = sorted(
            active_assets, 
            key=lambda a: a.get("Purchase Date", ""), 
            reverse=True
        )[:10]
        
        # Process assets to ensure they have a display_name field
        for asset in latest_assets:
            # Try different possible field names for the asset name
            name_fields = ["Name", "Asset Name", "AssetName", "Item Name", "Description", "Item"]
            display_name = None
            
            for field in name_fields:
                if asset.get(field):
                    display_name = asset.get(field)
                    break
            
            # If no name found, use a default
            if not display_name:
                display_name = f"Asset #{asset.get('ID', 'Unknown')}"
                
            # Add the display_name to the asset
            asset["display_name"] = display_name
            
        # Debug: Print the first asset's keys to see what fields are available
        if latest_assets:
            logging.info(f"Asset keys: {list(latest_assets[0].keys())}")
            logging.info(f"Asset display name: {latest_assets[0].get('display_name', 'Not found')}")
            logging.info(f"Original asset name fields: {[latest_assets[0].get(f, 'None') for f in name_fields]}")

        context = {
            "request": request,
            "user": current_user,
            "total_assets": total_assets,
            "total_purchase_value": total_purchase_value,
            "total_book_value": total_book_value,
            "total_depreciation_value": total_depreciation_value,
            "disposed_count": disposed_count,
            "damaged_count": damaged_count,
            "relocated_count": relocated_count,
            "repaired_count": repaired_count,
            "to_be_disposed_count": to_be_disposed_count,
            "category_counts": category_counts,
            "location_counts": location_counts_dict,
            "monthly_chart_labels": monthly_chart_labels,
            "monthly_chart_values": monthly_chart_values,
            "quarterly_chart_labels": quarterly_chart_labels,
            "quarterly_chart_values": quarterly_chart_values,
            "yearly_chart_labels": yearly_chart_labels,
            "yearly_chart_values": yearly_chart_values,
            "age_distribution": age_distribution_list,
            "latest_assets": latest_assets
        }

        return templates.TemplateResponse("dashboard.html", context)

    except Exception as e:
        logging.error("Dashboard error: %s", e, exc_info=True)
        return templates.TemplateResponse("error.html", {
            "request": request,
            "user": current_user,
            "message": "Terjadi kesalahan saat memuat dashboard.",
        })
from fastapi import APIRouter, Request, Response, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from supabase import create_client, Client
from app.config import load_config
import logging

config = load_config()
supabase: Client = create_client(config.SUPABASE_URL, config.SUPABASE_ANON_KEY)

router = APIRouter(tags=["authentication"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/login", response_class=HTMLResponse)
@router.head("/login", response_class=HTMLResponse)
async def login_page(request: Request, next: str = None):
    return templates.TemplateResponse("login_logout.html", {"request": request, "next": next})

@router.post("/login", response_class=HTMLResponse)
async def login_form(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    next: str = Form(None)
):
    try:
        # Use service key client for admin operations
        from supabase import create_client
        admin_supabase = create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_KEY)
        
        response = admin_supabase.auth.sign_in_with_password({
            "email": email,
            "password": password
        })
        
        if not response.user:
            return templates.TemplateResponse(
                "login_logout.html",
                {"request": request, "error": "Invalid email or password", "next": next},
                status_code=401
            )
        
        # Get user profile
        profile_response = admin_supabase.table('profiles').select('*').eq('id', response.user.id).single().execute()
        if not profile_response.data or not profile_response.data.get('is_active'):
            return templates.TemplateResponse(
                "login_logout.html",
                {"request": request, "error": "Account is inactive", "next": next},
                status_code=401
            )
        
        redirect_url = next if next else "/"
        redirect_response = RedirectResponse(url=redirect_url, status_code=303)
        
        redirect_response.set_cookie(
            key="sb_access_token",
            value=response.session.access_token,
            httponly=True,
            max_age=3600,
            samesite="lax",
            secure=True,
            domain=".onrender.com"
        )
        
        return redirect_response
        
    except Exception as e:
        logging.error(f"Login error: {str(e)}")
        return templates.TemplateResponse(
            "login_logout.html",
            {"request": request, "error": "Login failed", "next": next},
            status_code=401
        )

@router.get("/auth/callback")
async def auth_callback(request: Request):
    return templates.TemplateResponse("auth_callback.html", {"request": request})

@router.get("/logout")
async def logout():
    try:
        supabase.auth.sign_out()
    except:
        pass
    
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(key="sb_access_token")
    return response
# app/routes/logs.py
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.database.models import Profile
from app.utils.auth import get_current_user
from app.utils.sheets import get_all_approvals

router = APIRouter(prefix="/logs", tags=["logs"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def logs_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """View approval logs based on user role."""
    all_approvals = get_all_approvals()
    
    # Filter based on user role
    if current_user.role.value == 'staff':
        # Staff can only see their own requests
        user_identifier = current_user.full_name or current_user.email
        approvals = [a for a in all_approvals if a.get('Submitted_By') == user_identifier]
    else:
        # Manager and admin can see all approvals
        approvals = all_approvals
    
    # Separate pending and completed
    pending_approvals = [a for a in approvals if a.get('Status') == 'Pending']
    completed_approvals = [a for a in approvals if a.get('Status') in ['Approved', 'Rejected']]
    
    return templates.TemplateResponse(
        "logs/index.html",
        {
            "request": request,
            "user": current_user,
            "pending_approvals": pending_approvals,
            "completed_approvals": completed_approvals
        }
    )
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
from fastapi import APIRouter, Depends, Request, Form, UploadFile, File, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from app.database.database import get_db
from app.database.models import Profile
from app.utils.auth import get_current_user
from app.utils.photo import resize_and_convert_image, upload_to_drive
from app.utils.flash import set_flash

router = APIRouter(tags=["profile"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/profile", response_class=HTMLResponse)
async def profile_page(
    request: Request,
    current_user = Depends(get_current_user)
):
    """User profile page."""
    return templates.TemplateResponse(
        "profile/view.html",
        {
            "request": request,
            "user": current_user
        }
    )

@router.get("/profile/edit", response_class=HTMLResponse)
async def edit_profile_page(
    request: Request,
    current_user = Depends(get_current_user)
):
    """Edit user profile page."""
    return templates.TemplateResponse(
        "profile/edit.html",
        {
            "request": request,
            "user": current_user
        }
    )

@router.post("/profile/edit")
async def update_profile(
    request: Request,
    full_name: str = Form(...),
    email: str = Form(...),
    photo: UploadFile = File(None),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Update user profile."""
    # Update basic info
    current_user.full_name = full_name
    current_user.email = email
    current_user.updated_at = datetime.now(timezone.utc)
    
    # Handle photo upload if provided
    if photo and photo.filename:
        try:
            # Process image
            contents = await photo.read()
            import io
            image_file = io.BytesIO(contents)
            processed_image = resize_and_convert_image(image_file)
            
            if processed_image:
                # Upload to Google Drive
                photo_url = upload_to_drive(
                    processed_image, 
                    photo.filename, 
                    f"profile_{current_user.email}"
                )
                if photo_url:
                    current_user.photo_url = photo_url
        except Exception as e:
            return templates.TemplateResponse(
                "profile/edit.html",
                {
                    "request": request,
                    "user": current_user,
                    "error": f"Error uploading photo: {str(e)}"
                },
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    # Save changes
    db.commit()
    
    # Redirect to profile page
    response = RedirectResponse(url="/profile", status_code=status.HTTP_303_SEE_OTHER)
    set_flash(response, "Profile updated successfully", "success")
    return response
# app/routes/relocation.py
from fastapi import APIRouter, Depends, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime
import json

from app.database.database import get_db
from app.database.models import Profile
from app.utils.auth import get_current_user
from app.utils.sheets import get_all_assets, get_dropdown_options, add_approval_request
from app.utils.flash import set_flash

router = APIRouter(prefix="/relocation", tags=["relocation"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def relocation_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Asset relocation page."""
    # Get assets and dropdown options
    all_assets = get_all_assets()
    dropdown_options = get_dropdown_options()
    
    return templates.TemplateResponse(
        "relocation/index.html",
        {
            "request": request,
            "user": current_user,
            "assets": all_assets,
            "dropdown_options": dropdown_options
        }
    )

@router.post("/relocate/{asset_id}")
async def relocate_asset(
    asset_id: str,
    request: Request,
    new_location: str = Form(...),
    new_room: str = Form(...),
    reason: str = Form(...),
    notes: str = Form(None),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Submit asset relocation request."""
    from app.utils.sheets import get_asset_by_id
    
    # Get asset data
    asset = get_asset_by_id(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    # Create relocation approval request
    relocation_data = {
        'new_location': new_location,
        'new_room': new_room,
        'current_location': asset.get('Location', ''),
        'current_room': asset.get('Room', ''),
        'reason': reason,
        'notes': notes or ''
    }
    
    approval_data = {
        'type': 'relocation',
        'asset_id': asset_id,
        'asset_name': asset.get('Item Name', ''),
        'submitted_by': current_user.full_name or current_user.email,
        'submitted_date': datetime.now().strftime('%Y-%m-%d'),
        'description': f"Relocate from {asset.get('Location', '')} - {asset.get('Room', '')} to {new_location} - {new_room}",
        'request_data': json.dumps(relocation_data, ensure_ascii=False)
    }
    
    approval_success = add_approval_request(approval_data)
    
    if approval_success:
        response = RedirectResponse(url="/relocation", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, f"Relocation request for {asset.get('Item Name', '')} submitted for approval", "success")
        return response
    else:
        response = RedirectResponse(url="/relocation", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, "Error submitting relocation request", "error")
        return response
# /app/app/routes/repair.py
from fastapi import APIRouter, Request, Depends
from starlette.templating import Jinja2Templates
from app.utils.auth import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.post("/action")
async def submit_repair_action(request: Request, current_user = Depends(get_current_user)):
    """Submit repair action - creates approval request for store, direct action for allocate"""
    from app.utils.sheets import add_repair_log, update_asset, add_approval_request
    from datetime import datetime
    
    try:
        # Get JSON data
        data = await request.json()
        action_type = data.get('action_type')  # 'store' or 'allocate'
        
        if action_type == 'store':
            # Store action requires approval - only create approval request
            approval_data = {
                'type': 'repair_action',
                'asset_id': data.get('asset_id'),
                'asset_name': data.get('asset_name'),
                'submitted_by': current_user.full_name or current_user.email,
                'submitted_date': datetime.now().strftime('%Y-%m-%d'),
                'description': f"Request to store asset: {data.get('description')}",
                'action': 'Store Asset'
            }
            
            approval_success = add_approval_request(approval_data)
            
            if approval_success:
                return {"status": "success", "message": "Store request submitted for admin approval"}
            else:
                return {"status": "error", "message": "Failed to submit approval request"}
        
        else:  # allocate - direct action
            # Add to Repair_Log sheet
            repair_data = {
                'asset_id': data.get('asset_id'),
                'asset_name': data.get('asset_name'),
                'repair_action': 'Allocate Asset',
                'action_type': action_type,
                'description': data.get('description', ''),
                'performed_by': current_user.full_name or current_user.email,
                'action_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'new_location': data.get('location', ''),
                'new_room': data.get('room', ''),
                'notes': data.get('notes', '')
            }
            
            # Add to repair log
            log_success = add_repair_log(repair_data)
            
            # Update asset from Under Repair to Active
            update_data = {
                'Status': 'Active',
                'Bisnis Unit': data.get('business_unit', ''),
                'Location': data.get('location', ''),
                'Room': data.get('room', '')
            }
            
            asset_success = update_asset(data.get('asset_id'), update_data)
            
            if log_success and asset_success:
                return {"status": "success", "message": "Asset allocated successfully and synced to Google Sheets"}
            else:
                return {"status": "error", "message": "Failed to sync with Google Sheets"}
            
    except Exception as e:
        return {"status": "error", "message": str(e)}
# app/routes/user_management.py
from fastapi import APIRouter, Depends, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.database.models import Profile, UserRole
from app.utils.auth import get_current_user, get_admin_user
from app.utils.flash import set_flash

router = APIRouter(prefix="/user_management", tags=["user_management"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def user_list(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """List all users (admin only)."""
    users = db.query(Profile).all()
    
    return templates.TemplateResponse(
        "user_management/list.html",
        {
            "request": request,
            "user": current_user,
            "users": users
        }
    )

@router.get("/create", response_class=HTMLResponse)
async def create_user_form(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Create user form (admin only)."""
    return templates.TemplateResponse(
        "user_management/create.html",
        {
            "request": request,
            "user": current_user
        }
    )

@router.post("/create")
async def create_user(
    request: Request,
    email: str = Form(...),
    full_name: str = Form(...),
    role: str = Form(...),
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Create new user (admin only)."""
    # Check if user exists
    existing_user = db.query(Profile).filter(Profile.email == email).first()
    if existing_user:
        return templates.TemplateResponse(
            "user_management/create.html",
            {
                "request": request,
                "user": current_user,
                "error": "Email already exists"
            }
        )
    
    # Create user profile (Supabase handles auth)
    new_user = Profile(
        email=email,
        full_name=full_name,
        role=getattr(UserRole, role.upper()),
        is_active=True
    )
    
    db.add(new_user)
    db.commit()
    
    response = RedirectResponse(url="/user_management", status_code=status.HTTP_303_SEE_OTHER)
    set_flash(response, f"User {email} created successfully", "success")
    return response

@router.post("/reset_password/{user_id}")
async def reset_password(
    user_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Reset user password to default (admin only)."""
    user = db.query(Profile).filter(Profile.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Password reset handled by Supabase
    default_password = f"{user.email.split('@')[0]}123"
    
    response = RedirectResponse(url="/user_management", status_code=status.HTTP_303_SEE_OTHER)
    set_flash(response, f"Password reset instructions sent to {user.email}", "success")
    return response

@router.post("/toggle_status/{user_id}")
async def toggle_user_status(
    user_id: str,
    request: Request,
    is_active: bool = Form(...),
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Toggle user active status (admin only)."""
    user = db.query(Profile).filter(Profile.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Update status
    user.is_active = is_active
    db.commit()
    
    status_text = "activated" if is_active else "deactivated"
    response = RedirectResponse(url="/user_management", status_code=status.HTTP_303_SEE_OTHER)
    set_flash(response, f"User {user.email} {status_text}", "success")
    return response
# app/routes/__init__.py

# Import all route modules to make them available from app.routes
from app.routes import (
    home,
    assets,
    asset_management,
    login,
    damage,
    health,
    offline,
    profile,
    repair,
    approvals,
    disposal,
    user_management,
    logs,
    relocation
)
# app/routes/approvals.py
from fastapi import APIRouter, Depends, Request, HTTPException, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.utils.auth import get_current_user
from app.utils.sheets import get_all_approvals, update_approval_status

router = APIRouter(prefix="/approvals", tags=["approvals"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def approvals_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Approvals page for admin and manager."""
    if current_user.role not in ['admin', 'manager']:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get all approvals from Google Sheets
    all_approvals = get_all_approvals()
    
    # Filter approvals based on user role
    if current_user.role == 'admin':
        # Admin sees all approvals except disposal and edit_asset
        approvals_data = [a for a in all_approvals if a.get('Type') not in ['disposal', 'edit_asset']]
    elif current_user.role == 'manager':
        # Manager sees disposal and edit_asset approvals
        approvals_data = [a for a in all_approvals if a.get('Type') in ['disposal', 'edit_asset']]
    else:
        approvals_data = []
    
    return templates.TemplateResponse(
        "approvals/list.html",
        {
            "request": request,
            "user": current_user,
            "approvals_data": approvals_data
        }
    )

@router.post("/approve/{approval_id}")
async def approve_request(
    approval_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Approve a request."""
    if current_user.role not in ['admin', 'manager']:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get approval details
    all_approvals = get_all_approvals()
    approval = next((a for a in all_approvals if str(a.get('ID')) == str(approval_id)), None)
    
    if not approval:
        return JSONResponse({"status": "error", "message": "Approval not found"})
    
    # Process approval based on type
    try:
        if approval.get('Type') == 'damage_report':
            # Update asset status to "Under Repair"
            from app.utils.sheets import update_asset
            success = update_asset(approval.get('Asset_ID'), {'Status': 'Under Repair'})
            if not success:
                return JSONResponse({"status": "error", "message": "Failed to update asset status"})
        
        elif approval.get('Type') == 'relocation':
            # Process relocation approval
            import json
            try:
                request_data_str = approval.get('Request_Data', '')
                if request_data_str:
                    relocation_data = json.loads(request_data_str)
                    update_data = {
                        'Location': relocation_data.get('new_location'),
                        'Room': relocation_data.get('new_room')
                    }
                    from app.utils.sheets import update_asset
                    success = update_asset(approval.get('Asset_ID'), update_data)
                    if not success:
                        return JSONResponse({"status": "error", "message": "Failed to relocate asset"})
            except Exception as e:
                return JSONResponse({"status": "error", "message": f"Error processing relocation: {str(e)}"})
            
        elif approval.get('Type') == 'edit_asset':
            # Process edit asset approval
            import json
            try:
                request_data_str = approval.get('Request_Data', '')
                if request_data_str:
                    edit_data = json.loads(request_data_str)
                    from app.utils.sheets import update_asset
                    success = update_asset(approval.get('Asset_ID'), edit_data)
                    if not success:
                        return JSONResponse({"status": "error", "message": "Failed to update asset"})
            except Exception as e:
                return JSONResponse({"status": "error", "message": f"Error processing edit: {str(e)}"})
        
        # Update approval status
        approval_update = {
            'Status': 'Approved',
            'Approved_By': current_user.full_name or current_user.email,
            'Approved_Date': __import__('datetime').datetime.now().strftime('%Y-%m-%d')
        }
        
        success = update_approval_status(approval_id, approval_update)
        
        if success:
            return JSONResponse({"status": "success", "message": "Request approved successfully"})
        else:
            return JSONResponse({"status": "error", "message": "Failed to update approval status"})
            
    except Exception as e:
        return JSONResponse({"status": "error", "message": f"Error processing approval: {str(e)}"})

@router.post("/reject/{approval_id}")
async def reject_request(
    approval_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Reject a request."""
    if current_user.role not in ['admin', 'manager']:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Update approval status
    approval_update = {
        'Status': 'Rejected',
        'Approved_By': current_user.full_name or current_user.email,
        'Approved_Date': __import__('datetime').datetime.now().strftime('%Y-%m-%d')
    }
    
    success = update_approval_status(approval_id, approval_update)
    
    if success:
        return JSONResponse({"status": "success", "message": "Request rejected"})
    else:
        return JSONResponse({"status": "error", "message": "Failed to update approval status"})
from fastapi import APIRouter, Request, Depends
from starlette.templating import Jinja2Templates
from app.utils.auth import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/assets")
async def assets_page(request: Request, current_user=Depends(get_current_user)):
    """Assets listing page with filtering and pagination"""
    from app.utils.sheets import get_all_assets
    
    # Ambil data asset dari Google Sheets
    all_assets = get_all_assets()
    
    # Filter hanya aset aktif (bukan Disposed)
    active_assets = [asset for asset in all_assets if asset.get("Status", "").lower() != "disposed"]
    
    return templates.TemplateResponse("assets.html", {
        "request": request,
        "user": current_user,
        "assets_data": active_assets
    })
# app/routes/asset_management.py
from fastapi import APIRouter, Depends, Request, Form, File, UploadFile, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import json
from datetime import datetime
import io

from app.database.database import get_db
from app.database.models import Profile, UserRole
from app.utils.photo import resize_and_convert_image, upload_to_drive
from app.utils.sheets import get_dropdown_options, add_asset as sheets_add_asset
from app.utils.flash import set_flash
from app.utils.auth import get_current_user, get_admin_user
from app.config import load_config

config = load_config()
router = APIRouter(prefix="/asset_management", tags=["asset_management"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/add", response_class=HTMLResponse)
async def add_asset_form(
    request: Request,
    db: Session = Depends(get_db),
    current_profile = Depends(get_current_user)
):
    """Form to add a new asset."""
    dropdown_options = get_dropdown_options()
    return templates.TemplateResponse(
        "asset_management/add.html",
        {
            "request": request,
            "user": current_profile,
            "dropdown_options": dropdown_options
        }
    )


@router.get("/list", response_class=HTMLResponse)
async def asset_list(
    request: Request,
    db: Session = Depends(get_db),
    current_profile = Depends(get_current_user)
):
    """List assets for editing (admin and manager only)."""
    if current_profile.role not in [UserRole.ADMIN, UserRole.MANAGER]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    from app.utils.sheets import get_all_assets
    assets = get_all_assets()
    
    locations = list(set(asset.get('Location', '') for asset in assets if asset.get('Location')))
    location_rooms = {}
    for asset in assets:
        location = asset.get('Location', '')
        room = asset.get('Room', '')
        if location and room:
            if location not in location_rooms:
                location_rooms[location] = set()
            location_rooms[location].add(room)
    
    for location in location_rooms:
        location_rooms[location] = list(location_rooms[location])
    
    return templates.TemplateResponse(
        "asset_management/list.html",
        {
            "request": request,
            "user": current_profile,
            "assets": assets,
            "locations": sorted(locations),
            "location_rooms": location_rooms
        }
    )


@router.get("/edit/{asset_id}", response_class=HTMLResponse)
async def edit_asset_form(
    asset_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_profile = Depends(get_current_user)
):
    """Form to edit an existing asset (admin/manager only)."""
    if current_profile.role not in [UserRole.ADMIN, UserRole.MANAGER]:
        raise HTTPException(status_code=403, detail="Access denied")

    from app.utils.sheets import get_asset_by_id
    asset = get_asset_by_id(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    dropdown_options = get_dropdown_options()
    
    return templates.TemplateResponse(
        "asset_management/edit.html",
        {
            "request": request,
            "user": current_profile,
            "asset": asset,
            "dropdown_options": dropdown_options
        }
    )


@router.post("/edit/{asset_id}")
async def update_asset(
    asset_id: str,
    request: Request,
    status: str = Form(...),
    company: str = Form(...),
    location: str = Form(...),
    room: str = Form(...),
    bisnis_unit: str = Form(None),
    edit_reason: str = Form(...),
    db: Session = Depends(get_db),
    current_profile = Depends(get_current_user)
):
    """Update existing asset (admin and manager only)."""
    if current_profile.role not in [UserRole.ADMIN, UserRole.MANAGER]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    from app.utils.sheets import update_asset as sheets_update_asset, calculate_asset_financials, get_asset_by_id
    asset = get_asset_by_id(asset_id)

    update_data = {
        "Status": status,
        "Company": company,
        "Location": location,
        "Room": room,
        "Bisnis Unit": bisnis_unit or ""
    }
    
    # Jika perlu hitung ulang nilai finansial, misalnya setelah perubahan harga
    # financials = calculate_asset_financials(purchase_cost, purchase_date, category)
    # update_data.update(financials)
    
    from app.utils.sheets import add_approval_request
    
    approval_data = {
        'type': 'edit_asset',
        'asset_id': asset_id,
        'asset_name': asset.get('Item Name', ''),
        'submitted_by': current_profile.full_name or current_profile.email,
        'submitted_date': datetime.now().strftime('%Y-%m-%d'),
        'description': f"Edit asset: {asset.get('Item Name', '')} - Reason: {edit_reason}",
        'edit_reason': edit_reason,
        'request_data': json.dumps(update_data, ensure_ascii=False)
    }
    
    approval_success = add_approval_request(approval_data)
    
    if approval_success:
        response = RedirectResponse(url="/asset_management/list", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, "Asset edit request submitted for manager approval", "success")
        return response
    else:
        dropdown_options = get_dropdown_options()
        return templates.TemplateResponse(
            "asset_management/edit.html",
            {
                "request": request,
                "user": current_profile,
                "asset": asset,
                "dropdown_options": dropdown_options,
                "error": "Error submitting edit request"
            },
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@router.post("/add")
async def add_asset(
    request: Request,
    item_name: str = Form(...),
    category: str = Form(...),
    type: str = Form(...),
    manufacture: str = Form(None),
    model: str = Form(None),
    serial_number: str = Form(None),
    company: str = Form(...),
    bisnis_unit: str = Form(None),
    location: str = Form(...),
    room: str = Form(...),
    notes: str = Form(None),
    item_condition: str = Form(None),
    purchase_date: str = Form(...),
    purchase_cost: str = Form(...),
    warranty: str = Form(None),
    supplier: str = Form(None),
    journal: str = Form(None),
    owner: str = Form(...),
    photo: UploadFile = File(None),
    db: Session = Depends(get_db),
    current_profile = Depends(get_current_user)
):
    """Process add asset form."""
    dropdown_options = get_dropdown_options()
    
    asset_data = {
        "Item Name": item_name,
        "Category": category,
        "Type": type,
        "Manufacture": manufacture or "",
        "Model": model or "",
        "Serial Number": serial_number or "",
        "Company": company,
        "Bisnis Unit": bisnis_unit or "",
        "Location": location,
        "Room": room,
        "Notes": notes or "",
        "Item Condition": item_condition or "",
        "Purchase Date": purchase_date,
        "Purchase Cost": purchase_cost,
        "Warranty": warranty or "",
        "Supplier": supplier or "",
        "Journal": journal or "",
        "Owner": owner,
        "Status": "Active"
    }
    
    photo_url = None
    if photo and photo.filename:
        try:
            contents = await photo.read()
            image_file = io.BytesIO(contents)
            processed_image = resize_and_convert_image(image_file)
            
            if processed_image:
                photo_url = upload_to_drive(processed_image, photo.filename, "new")
                if photo_url:
                    asset_data["Photo URL"] = photo_url
        except Exception as e:
            print(f"Error processing photo: {str(e)}")
    
    if current_profile.role == UserRole.ADMIN:
        success = sheets_add_asset(asset_data)
        
        if success:
            response = RedirectResponse(url="/assets/", status_code=status.HTTP_303_SEE_OTHER)
            set_flash(response, "Asset added successfully", "success")
            return response
        else:
            return templates.TemplateResponse(
                "asset_management/add.html",
                {
                    "request": request,
                    "user": current_profile,
                    "dropdown_options": dropdown_options,
                    "error": "Error adding asset to Google Sheets",
                    "form_data": asset_data
                },
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    from app.utils.sheets import add_approval_request
    
    approval_data = {
        'type': 'add_asset',
        'asset_id': 'NEW',
        'asset_name': item_name,
        'submitted_by': current_profile.full_name or current_profile.email,
        'submitted_date': datetime.now().strftime('%Y-%m-%d'),
        'description': f"Add new asset: {item_name}",
        'request_data': json.dumps(asset_data, ensure_ascii=False)
    }
    
    approval_success = add_approval_request(approval_data)
    
    if approval_success:
        response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, "Asset request submitted for approval", "success")
        return response
    else:
        return templates.TemplateResponse(
            "asset_management/add.html",
            {
                "request": request,
                "user": current_profile,
                "dropdown_options": dropdown_options,
                "error": "Error submitting approval request",
                "form_data": asset_data
            },
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
from fastapi import APIRouter, Request, Depends
from starlette.templating import Jinja2Templates
from app.utils.auth import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/")
async def damaged_assets_page(request: Request, current_user = Depends(get_current_user)):
    """Damaged assets page with search and log functionality"""
    from app.utils.sheets import get_all_assets, get_dropdown_options

    all_assets = get_all_assets()
    dropdown_options = get_dropdown_options()

    return templates.TemplateResponse("damaged_assets.html", {
        "request": request,
        "user": current_user,
        "assets_data": all_assets,
        "dropdown_options": dropdown_options
    })


@router.post("/lost")
async def submit_lost_report(request: Request, current_user = Depends(get_current_user)):
    """Submit lost report - syncs to Google Sheets"""
    from app.utils.sheets import add_lost_log, add_approval_request
    from datetime import datetime

    try:
        data = await request.json()

        lost_data = {
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'last_location': data.get('last_location'),
            'last_room': data.get('last_room', ''),
            'date_lost': data.get('date_lost'),
            'description': data.get('description'),
            'reported_by': current_user.full_name or current_user.email,
            'report_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'notes': data.get('notes', '')
        }

        log_success = add_lost_log(lost_data)

        approval_data = {
            'type': 'lost_report',
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'submitted_by': current_user.full_name or current_user.email,
            'submitted_date': datetime.now().strftime('%Y-%m-%d'),
            'description': f"Lost report: {data.get('description')}",
            'location': data.get('last_location')
        }

        approval_success = add_approval_request(approval_data)

        if log_success and approval_success:
            return {"status": "success", "message": "Lost report submitted and logged to Google Sheets"}
        else:
            return {"status": "error", "message": "Failed to sync with Google Sheets"}

    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/disposal")
async def submit_disposal_request(request: Request, current_user = Depends(get_current_user)):
    """Submit disposal request - syncs to Google Sheets"""
    from app.utils.sheets import add_disposal_log, add_approval_request
    from datetime import datetime

    try:
        data = await request.json()

        disposal_data = {
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'disposal_reason': data.get('disposal_reason'),
            'disposal_method': data.get('disposal_method', 'Standard'),
            'description': data.get('description'),
            'requested_by': current_user.full_name or current_user.email,
            'request_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'notes': data.get('notes', '')
        }

        log_success = add_disposal_log(disposal_data)

        approval_data = {
            'type': 'disposal_request',
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'submitted_by': current_user.full_name or current_user.email,
            'submitted_date': datetime.now().strftime('%Y-%m-%d'),
            'description': f"Disposal request: {data.get('description')}"
        }

        approval_success = add_approval_request(approval_data)

        if log_success and approval_success:
            return {"status": "success", "message": "Disposal request submitted and logged to Google Sheets"}
        else:
            return {"status": "error", "message": "Failed to sync with Google Sheets"}

    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/report")
async def submit_damage_report(request: Request, current_user = Depends(get_current_user)):
    """Submit damage report - syncs to Google Sheets"""
    from app.utils.sheets import add_damage_log, add_approval_request
    from datetime import datetime

    try:
        data = await request.json()

        damage_data = {
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'damage_type': data.get('damage_type'),
            'severity': data.get('severity'),
            'description': data.get('damage_description'),
            'reported_by': current_user.full_name or current_user.email,
            'report_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'location': data.get('location', ''),
            'room': data.get('room', ''),
            'notes': data.get('notes', '')
        }

        approval_data = {
            'type': 'damage_report',
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'submitted_by': current_user.full_name or current_user.email,
            'submitted_date': datetime.now().strftime('%Y-%m-%d'),
            'description': f"Damage report: {data.get('damage_description')}",
            'damage_type': data.get('damage_type'),
            'severity': data.get('severity')
        }

        approval_success = add_approval_request(approval_data)

        if approval_success:
            return {"status": "success", "message": "Damage report submitted for approval"}
        else:
            return {"status": "error", "message": "Failed to submit approval request"}

    except Exception as e:
        return {"status": "error", "message": str(e)}
# app/routes/disposal.py
from fastapi import APIRouter, Depends, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime

from app.database.database import get_db
from app.database.models import Profile
from app.utils.auth import get_admin_user
from app.utils.sheets import get_all_assets, update_asset, add_disposal_log
from app.utils.flash import set_flash

router = APIRouter(prefix="/disposal", tags=["disposal"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def disposal_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Disposal assets page (admin only)."""
    # Get assets that are ready to dispose only
    all_assets = get_all_assets()
    # Debug: check all statuses
    statuses = [str(asset.get('Status', '')).strip() for asset in all_assets]
    print(f"All statuses found: {set(statuses)}")
    
    disposable_assets = []
    for asset in all_assets:
        status = str(asset.get('Status', '')).strip()
        if status in ['To Be Disposed', 'To be Disposed', 'TO BE DISPOSED']:
            disposable_assets.append(asset)
    
    return templates.TemplateResponse(
        "disposal/index.html",
        {
            "request": request,
            "user": current_user,
            "assets": disposable_assets
        }
    )

@router.post("/dispose/{asset_id}")
async def dispose_asset(
    asset_id: str,
    request: Request,
    disposal_reason: str = Form(...),
    disposal_method: str = Form(...),
    description: str = Form(None),
    notes: str = Form(None),
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Dispose an asset (admin only)."""
    from app.utils.sheets import get_asset_by_id
    
    # Get asset data
    asset = get_asset_by_id(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    if str(asset.get('Status', '')).strip() != 'To Be Disposed':
        raise HTTPException(status_code=400, detail="Asset must be marked 'To Be Disposed' first")
    
    # Create disposal approval request
    from app.utils.sheets import add_approval_request
    
    approval_data = {
        'type': 'disposal',
        'asset_id': asset_id,
        'asset_name': asset.get('Item Name', ''),
        'submitted_by': current_user.full_name or current_user.email,
        'submitted_date': datetime.now().strftime('%Y-%m-%d'),
        'description': f"Disposal request: {disposal_reason} - {disposal_method}",
        'disposal_reason': disposal_reason,
        'disposal_method': disposal_method,
        'notes': f"Description: {description or ''} | Notes: {notes or ''}"
    }
    
    approval_success = add_approval_request(approval_data)
    
    if approval_success:
        response = RedirectResponse(url="/disposal", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, f"Disposal request for {asset.get('Item Name', '')} submitted for manager approval", "success")
        return response
    else:
        response = RedirectResponse(url="/disposal", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, "Error submitting disposal request", "error")
        return response
# app/routes/health.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
import time

from app.database.database import get_db
from app.config import load_config

router = APIRouter(tags=["health"])
config = load_config()

@router.get("/health")
async def health_check(db: Session = Depends(get_db)):
    """Health check endpoint."""
    start_time = time.time()
    
    # Check database connection
    try:
        db.execute(text("SELECT 1"))
        db_status = "healthy"
    except Exception as e:
        db_status = f"unhealthy: {str(e)}"
    
    # Check Google Sheets API
    sheets_status = "configured" if config.GOOGLE_SHEET_ID else "not configured"
    
    # Response time
    response_time = time.time() - start_time
    
    return {
        "status": "ok",
        "database": db_status,
        "google_sheets": sheets_status,
        "response_time_ms": round(response_time * 1000, 2)
    }
# /app/app/routes/home.py
import logging
from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse
from starlette.templating import Jinja2Templates
from app.utils.auth import get_current_user
from app.utils.sheets import get_summary_data, get_chart_data, get_all_assets

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=RedirectResponse)
async def redirect_root():
    return RedirectResponse("/dashboard")

@router.get("/dashboard")
async def home(request: Request, current_user = Depends(get_current_user)):
    try:
        # Summary and chart data
        summary_data = get_summary_data()
        chart_data = get_chart_data()
        all_assets = get_all_assets()

        # Filter out disposed assets for dashboard counts
        active_assets = [asset for asset in all_assets if asset.get("Status", "") != "Disposed"]
        disposed_assets = [asset for asset in all_assets if asset.get("Status", "") == "Disposed"]
        
        # Count assets by status and activity
        total_assets = len(active_assets)
        disposed_count = len(disposed_assets)
        damaged_count = len([a for a in all_assets if a.get("Status", "") == "Under Repair"])
        
        # Count assets by activity type
        relocated_count = len([a for a in all_assets if a.get("Last Activity", "") == "Relocated"])
        repaired_count = len([a for a in all_assets if a.get("Last Activity", "") == "Repaired"])
        to_be_disposed_count = len([a for a in all_assets if a.get("Status", "") == "To Be Disposed"])
        
        # Helper function to safely convert values to float
        def safe_float(value):
            if value is None or value == '':
                return 0.0
            try:
                return float(value)
            except (ValueError, TypeError):
                return 0.0
        
        # Calculate financial values directly from assets
        total_purchase_value = sum(safe_float(asset.get("Purchase Cost")) for asset in active_assets)
        total_book_value = sum(safe_float(asset.get("Book Value")) for asset in active_assets)
        # Calculate depreciation as purchase value minus book value
        total_depreciation_value = total_purchase_value - total_book_value
        category_counts = chart_data.get("category_counts", {})
        
        # Format location data
        location_data = chart_data.get("location_chart_data", {})
        location_counts = location_data.get("labels", [])
        location_values = location_data.get("values", [])
        location_counts_dict = dict(zip(location_counts, location_values))

        # Format time-based chart data
        monthly_data = chart_data.get("monthly_chart_data", {})
        monthly_chart_labels = monthly_data.get("labels", [])
        monthly_chart_values = monthly_data.get("values", [])
        
        # Generate quarterly data (last 12 quarters - 3 years)
        quarterly_chart_labels = []
        quarterly_chart_values = []
        
        # Get current year and quarter
        from datetime import datetime
        current_date = datetime.now()
        current_year = current_date.year
        current_quarter = (current_date.month - 1) // 3 + 1
        
        # Generate data for the last 12 quarters
        for i in range(11, -1, -1):
            year = current_year
            quarter = current_quarter - i
            
            # Adjust year if quarter is negative or > 4
            while quarter <= 0:
                year -= 1
                quarter += 4
            while quarter > 4:
                year += 1
                quarter -= 4
                
            quarterly_chart_labels.append(f"Q{quarter} {year}")
            
            # Count assets added in this quarter
            quarter_start_month = (quarter - 1) * 3 + 1
            quarter_end_month = quarter * 3
            
            count = 0
            for asset in all_assets:
                purchase_date = asset.get("Purchase Date", "")
                if purchase_date:
                    try:
                        date = datetime.strptime(purchase_date, "%Y-%m-%d")
                        if date.year == year and quarter_start_month <= date.month <= quarter_end_month:
                            count += 1
                    except:
                        pass
            
            quarterly_chart_values.append(count)
        
        # Generate yearly data (last 5 years)
        yearly_chart_labels = []
        yearly_chart_values = []
        
        # Generate data for the last 5 years
        for i in range(4, -1, -1):
            year = current_year - i
            yearly_chart_labels.append(str(year))
            
            # Count assets added in this year
            count = 0
            for asset in all_assets:
                purchase_date = asset.get("Purchase Date", "")
                if purchase_date:
                    try:
                        date = datetime.strptime(purchase_date, "%Y-%m-%d")
                        if date.year == year:
                            count += 1
                    except:
                        pass
            
            yearly_chart_values.append(count)

        # Format age distribution - convert to list of tuples for proper serialization
        age_distribution = chart_data.get("age_distribution", {})
        age_distribution_list = [
            {"label": str(k), "value": int(v)} 
            for k, v in age_distribution.items()
        ]

        # Format latest assets (excluding disposed assets)
        latest_assets = sorted(
            active_assets, 
            key=lambda a: a.get("Purchase Date", ""), 
            reverse=True
        )[:10]
        
        # Process assets to ensure they have a display_name field
        for asset in latest_assets:
            # Try different possible field names for the asset name
            name_fields = ["Name", "Asset Name", "AssetName", "Item Name", "Description", "Item"]
            display_name = None
            
            for field in name_fields:
                if asset.get(field):
                    display_name = asset.get(field)
                    break
            
            # If no name found, use a default
            if not display_name:
                display_name = f"Asset #{asset.get('ID', 'Unknown')}"
                
            # Add the display_name to the asset
            asset["display_name"] = display_name
            
        # Debug: Print the first asset's keys to see what fields are available
        if latest_assets:
            logging.info(f"Asset keys: {list(latest_assets[0].keys())}")
            logging.info(f"Asset display name: {latest_assets[0].get('display_name', 'Not found')}")
            logging.info(f"Original asset name fields: {[latest_assets[0].get(f, 'None') for f in name_fields]}")

        context = {
            "request": request,
            "user": current_user,
            "total_assets": total_assets,
            "total_purchase_value": total_purchase_value,
            "total_book_value": total_book_value,
            "total_depreciation_value": total_depreciation_value,
            "disposed_count": disposed_count,
            "damaged_count": damaged_count,
            "relocated_count": relocated_count,
            "repaired_count": repaired_count,
            "to_be_disposed_count": to_be_disposed_count,
            "category_counts": category_counts,
            "location_counts": location_counts_dict,
            "monthly_chart_labels": monthly_chart_labels,
            "monthly_chart_values": monthly_chart_values,
            "quarterly_chart_labels": quarterly_chart_labels,
            "quarterly_chart_values": quarterly_chart_values,
            "yearly_chart_labels": yearly_chart_labels,
            "yearly_chart_values": yearly_chart_values,
            "age_distribution": age_distribution_list,
            "latest_assets": latest_assets
        }

        return templates.TemplateResponse("dashboard.html", context)

    except Exception as e:
        logging.error("Dashboard error: %s", e, exc_info=True)
        return templates.TemplateResponse("error.html", {
            "request": request,
            "user": current_user,
            "message": "Terjadi kesalahan saat memuat dashboard.",
        })
from fastapi import APIRouter, Request, Response, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from supabase import create_client, Client
from app.config import load_config
import logging

config = load_config()
supabase: Client = create_client(config.SUPABASE_URL, config.SUPABASE_ANON_KEY)

router = APIRouter(tags=["authentication"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/login", response_class=HTMLResponse)
@router.head("/login", response_class=HTMLResponse)
async def login_page(request: Request, next: str = None):
    return templates.TemplateResponse("login_logout.html", {"request": request, "next": next})

@router.post("/login", response_class=HTMLResponse)
async def login_form(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    next: str = Form(None)
):
    try:
        # Use service key client for admin operations
        from supabase import create_client
        admin_supabase = create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_KEY)
        
        response = admin_supabase.auth.sign_in_with_password({
            "email": email,
            "password": password
        })
        
        if not response.user:
            return templates.TemplateResponse(
                "login_logout.html",
                {"request": request, "error": "Invalid email or password", "next": next},
                status_code=401
            )
        
        # Get user profile
        profile_response = admin_supabase.table('profiles').select('*').eq('id', response.user.id).single().execute()
        if not profile_response.data or not profile_response.data.get('is_active'):
            return templates.TemplateResponse(
                "login_logout.html",
                {"request": request, "error": "Account is inactive", "next": next},
                status_code=401
            )
        
        redirect_url = next if next else "/"
        redirect_response = RedirectResponse(url=redirect_url, status_code=303)
        
        redirect_response.set_cookie(
            key="sb_access_token",
            value=response.session.access_token,
            httponly=True,
            max_age=3600,
            samesite="lax",
            secure=True,
            domain=".onrender.com"
        )
        
        return redirect_response
        
    except Exception as e:
        logging.error(f"Login error: {str(e)}")
        return templates.TemplateResponse(
            "login_logout.html",
            {"request": request, "error": "Login failed", "next": next},
            status_code=401
        )

@router.get("/auth/callback")
async def auth_callback(request: Request):
    return templates.TemplateResponse("auth_callback.html", {"request": request})

@router.get("/logout")
async def logout():
    try:
        supabase.auth.sign_out()
    except:
        pass
    
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(key="sb_access_token")
    return response
# app/routes/logs.py
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.database.models import Profile
from app.utils.auth import get_current_user
from app.utils.sheets import get_all_approvals

router = APIRouter(prefix="/logs", tags=["logs"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def logs_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """View approval logs based on user role."""
    all_approvals = get_all_approvals()
    
    # Filter based on user role
    if current_user.role.value == 'staff':
        # Staff can only see their own requests
        user_identifier = current_user.full_name or current_user.email
        approvals = [a for a in all_approvals if a.get('Submitted_By') == user_identifier]
    else:
        # Manager and admin can see all approvals
        approvals = all_approvals
    
    # Separate pending and completed
    pending_approvals = [a for a in approvals if a.get('Status') == 'Pending']
    completed_approvals = [a for a in approvals if a.get('Status') in ['Approved', 'Rejected']]
    
    return templates.TemplateResponse(
        "logs/index.html",
        {
            "request": request,
            "user": current_user,
            "pending_approvals": pending_approvals,
            "completed_approvals": completed_approvals
        }
    )
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
from fastapi import APIRouter, Depends, Request, Form, UploadFile, File, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from app.database.database import get_db
from app.database.models import Profile
from app.utils.auth import get_current_user
from app.utils.photo import resize_and_convert_image, upload_to_drive
from app.utils.flash import set_flash

router = APIRouter(tags=["profile"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/profile", response_class=HTMLResponse)
async def profile_page(
    request: Request,
    current_user = Depends(get_current_user)
):
    """User profile page."""
    return templates.TemplateResponse(
        "profile/view.html",
        {
            "request": request,
            "user": current_user
        }
    )

@router.get("/profile/edit", response_class=HTMLResponse)
async def edit_profile_page(
    request: Request,
    current_user = Depends(get_current_user)
):
    """Edit user profile page."""
    return templates.TemplateResponse(
        "profile/edit.html",
        {
            "request": request,
            "user": current_user
        }
    )

@router.post("/profile/edit")
async def update_profile(
    request: Request,
    full_name: str = Form(...),
    email: str = Form(...),
    photo: UploadFile = File(None),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Update user profile."""
    # Update basic info
    current_user.full_name = full_name
    current_user.email = email
    current_user.updated_at = datetime.now(timezone.utc)
    
    # Handle photo upload if provided
    if photo and photo.filename:
        try:
            # Process image
            contents = await photo.read()
            import io
            image_file = io.BytesIO(contents)
            processed_image = resize_and_convert_image(image_file)
            
            if processed_image:
                # Upload to Google Drive
                photo_url = upload_to_drive(
                    processed_image, 
                    photo.filename, 
                    f"profile_{current_user.email}"
                )
                if photo_url:
                    current_user.photo_url = photo_url
        except Exception as e:
            return templates.TemplateResponse(
                "profile/edit.html",
                {
                    "request": request,
                    "user": current_user,
                    "error": f"Error uploading photo: {str(e)}"
                },
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    # Save changes
    db.commit()
    
    # Redirect to profile page
    response = RedirectResponse(url="/profile", status_code=status.HTTP_303_SEE_OTHER)
    set_flash(response, "Profile updated successfully", "success")
    return response
# app/routes/relocation.py
from fastapi import APIRouter, Depends, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime
import json

from app.database.database import get_db
from app.database.models import Profile
from app.utils.auth import get_current_user
from app.utils.sheets import get_all_assets, get_dropdown_options, add_approval_request
from app.utils.flash import set_flash

router = APIRouter(prefix="/relocation", tags=["relocation"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def relocation_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Asset relocation page."""
    # Get assets and dropdown options
    all_assets = get_all_assets()
    dropdown_options = get_dropdown_options()
    
    return templates.TemplateResponse(
        "relocation/index.html",
        {
            "request": request,
            "user": current_user,
            "assets": all_assets,
            "dropdown_options": dropdown_options
        }
    )

@router.post("/relocate/{asset_id}")
async def relocate_asset(
    asset_id: str,
    request: Request,
    new_location: str = Form(...),
    new_room: str = Form(...),
    reason: str = Form(...),
    notes: str = Form(None),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Submit asset relocation request."""
    from app.utils.sheets import get_asset_by_id
    
    # Get asset data
    asset = get_asset_by_id(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    # Create relocation approval request
    relocation_data = {
        'new_location': new_location,
        'new_room': new_room,
        'current_location': asset.get('Location', ''),
        'current_room': asset.get('Room', ''),
        'reason': reason,
        'notes': notes or ''
    }
    
    approval_data = {
        'type': 'relocation',
        'asset_id': asset_id,
        'asset_name': asset.get('Item Name', ''),
        'submitted_by': current_user.full_name or current_user.email,
        'submitted_date': datetime.now().strftime('%Y-%m-%d'),
        'description': f"Relocate from {asset.get('Location', '')} - {asset.get('Room', '')} to {new_location} - {new_room}",
        'request_data': json.dumps(relocation_data, ensure_ascii=False)
    }
    
    approval_success = add_approval_request(approval_data)
    
    if approval_success:
        response = RedirectResponse(url="/relocation", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, f"Relocation request for {asset.get('Item Name', '')} submitted for approval", "success")
        return response
    else:
        response = RedirectResponse(url="/relocation", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, "Error submitting relocation request", "error")
        return response
# /app/app/routes/repair.py
from fastapi import APIRouter, Request, Depends
from starlette.templating import Jinja2Templates
from app.utils.auth import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.post("/action")
async def submit_repair_action(request: Request, current_user = Depends(get_current_user)):
    """Submit repair action - creates approval request for store, direct action for allocate"""
    from app.utils.sheets import add_repair_log, update_asset, add_approval_request
    from datetime import datetime
    
    try:
        # Get JSON data
        data = await request.json()
        action_type = data.get('action_type')  # 'store' or 'allocate'
        
        if action_type == 'store':
            # Store action requires approval - only create approval request
            approval_data = {
                'type': 'repair_action',
                'asset_id': data.get('asset_id'),
                'asset_name': data.get('asset_name'),
                'submitted_by': current_user.full_name or current_user.email,
                'submitted_date': datetime.now().strftime('%Y-%m-%d'),
                'description': f"Request to store asset: {data.get('description')}",
                'action': 'Store Asset'
            }
            
            approval_success = add_approval_request(approval_data)
            
            if approval_success:
                return {"status": "success", "message": "Store request submitted for admin approval"}
            else:
                return {"status": "error", "message": "Failed to submit approval request"}
        
        else:  # allocate - direct action
            # Add to Repair_Log sheet
            repair_data = {
                'asset_id': data.get('asset_id'),
                'asset_name': data.get('asset_name'),
                'repair_action': 'Allocate Asset',
                'action_type': action_type,
                'description': data.get('description', ''),
                'performed_by': current_user.full_name or current_user.email,
                'action_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'new_location': data.get('location', ''),
                'new_room': data.get('room', ''),
                'notes': data.get('notes', '')
            }
            
            # Add to repair log
            log_success = add_repair_log(repair_data)
            
            # Update asset from Under Repair to Active
            update_data = {
                'Status': 'Active',
                'Bisnis Unit': data.get('business_unit', ''),
                'Location': data.get('location', ''),
                'Room': data.get('room', '')
            }
            
            asset_success = update_asset(data.get('asset_id'), update_data)
            
            if log_success and asset_success:
                return {"status": "success", "message": "Asset allocated successfully and synced to Google Sheets"}
            else:
                return {"status": "error", "message": "Failed to sync with Google Sheets"}
            
    except Exception as e:
        return {"status": "error", "message": str(e)}
# app/routes/user_management.py
from fastapi import APIRouter, Depends, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.database.models import Profile, UserRole
from app.utils.auth import get_current_user, get_admin_user
from app.utils.flash import set_flash

router = APIRouter(prefix="/user_management", tags=["user_management"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def user_list(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """List all users (admin only)."""
    users = db.query(Profile).all()
    
    return templates.TemplateResponse(
        "user_management/list.html",
        {
            "request": request,
            "user": current_user,
            "users": users
        }
    )

@router.get("/create", response_class=HTMLResponse)
async def create_user_form(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Create user form (admin only)."""
    return templates.TemplateResponse(
        "user_management/create.html",
        {
            "request": request,
            "user": current_user
        }
    )

@router.post("/create")
async def create_user(
    request: Request,
    email: str = Form(...),
    full_name: str = Form(...),
    role: str = Form(...),
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Create new user (admin only)."""
    # Check if user exists
    existing_user = db.query(Profile).filter(Profile.email == email).first()
    if existing_user:
        return templates.TemplateResponse(
            "user_management/create.html",
            {
                "request": request,
                "user": current_user,
                "error": "Email already exists"
            }
        )
    
    # Create user profile (Supabase handles auth)
    new_user = Profile(
        email=email,
        full_name=full_name,
        role=getattr(UserRole, role.upper()),
        is_active=True
    )
    
    db.add(new_user)
    db.commit()
    
    response = RedirectResponse(url="/user_management", status_code=status.HTTP_303_SEE_OTHER)
    set_flash(response, f"User {email} created successfully", "success")
    return response

@router.post("/reset_password/{user_id}")
async def reset_password(
    user_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Reset user password to default (admin only)."""
    user = db.query(Profile).filter(Profile.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Password reset handled by Supabase
    default_password = f"{user.email.split('@')[0]}123"
    
    response = RedirectResponse(url="/user_management", status_code=status.HTTP_303_SEE_OTHER)
    set_flash(response, f"Password reset instructions sent to {user.email}", "success")
    return response

@router.post("/toggle_status/{user_id}")
async def toggle_user_status(
    user_id: str,
    request: Request,
    is_active: bool = Form(...),
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Toggle user active status (admin only)."""
    user = db.query(Profile).filter(Profile.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Update status
    user.is_active = is_active
    db.commit()
    
    status_text = "activated" if is_active else "deactivated"
    response = RedirectResponse(url="/user_management", status_code=status.HTTP_303_SEE_OTHER)
    set_flash(response, f"User {user.email} {status_text}", "success")
    return response
# app/routes/__init__.py

# Import all route modules to make them available from app.routes
from app.routes import (
    home,
    assets,
    asset_management,
    login,
    damage,
    health,
    offline,
    profile,
    repair,
    approvals,
    disposal,
    user_management,
    logs,
    relocation
)
# app/routes/approvals.py
from fastapi import APIRouter, Depends, Request, HTTPException, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.utils.auth import get_current_user
from app.utils.sheets import get_all_approvals, update_approval_status

router = APIRouter(prefix="/approvals", tags=["approvals"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def approvals_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Approvals page for admin and manager."""
    if current_user.role not in ['admin', 'manager']:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get all approvals from Google Sheets
    all_approvals = get_all_approvals()
    
    # Filter approvals based on user role
    if current_user.role == 'admin':
        # Admin sees all approvals except disposal and edit_asset
        approvals_data = [a for a in all_approvals if a.get('Type') not in ['disposal', 'edit_asset']]
    elif current_user.role == 'manager':
        # Manager sees disposal and edit_asset approvals
        approvals_data = [a for a in all_approvals if a.get('Type') in ['disposal', 'edit_asset']]
    else:
        approvals_data = []
    
    return templates.TemplateResponse(
        "approvals/list.html",
        {
            "request": request,
            "user": current_user,
            "approvals_data": approvals_data
        }
    )

@router.post("/approve/{approval_id}")
async def approve_request(
    approval_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Approve a request."""
    if current_user.role not in ['admin', 'manager']:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get approval details
    all_approvals = get_all_approvals()
    approval = next((a for a in all_approvals if str(a.get('ID')) == str(approval_id)), None)
    
    if not approval:
        return JSONResponse({"status": "error", "message": "Approval not found"})
    
    # Process approval based on type
    try:
        if approval.get('Type') == 'damage_report':
            # Update asset status to "Under Repair"
            from app.utils.sheets import update_asset
            success = update_asset(approval.get('Asset_ID'), {'Status': 'Under Repair'})
            if not success:
                return JSONResponse({"status": "error", "message": "Failed to update asset status"})
        
        elif approval.get('Type') == 'relocation':
            # Process relocation approval
            import json
            try:
                request_data_str = approval.get('Request_Data', '')
                if request_data_str:
                    relocation_data = json.loads(request_data_str)
                    update_data = {
                        'Location': relocation_data.get('new_location'),
                        'Room': relocation_data.get('new_room')
                    }
                    from app.utils.sheets import update_asset
                    success = update_asset(approval.get('Asset_ID'), update_data)
                    if not success:
                        return JSONResponse({"status": "error", "message": "Failed to relocate asset"})
            except Exception as e:
                return JSONResponse({"status": "error", "message": f"Error processing relocation: {str(e)}"})
            
        elif approval.get('Type') == 'edit_asset':
            # Process edit asset approval
            import json
            try:
                request_data_str = approval.get('Request_Data', '')
                if request_data_str:
                    edit_data = json.loads(request_data_str)
                    from app.utils.sheets import update_asset
                    success = update_asset(approval.get('Asset_ID'), edit_data)
                    if not success:
                        return JSONResponse({"status": "error", "message": "Failed to update asset"})
            except Exception as e:
                return JSONResponse({"status": "error", "message": f"Error processing edit: {str(e)}"})
        
        # Update approval status
        approval_update = {
            'Status': 'Approved',
            'Approved_By': current_user.full_name or current_user.email,
            'Approved_Date': __import__('datetime').datetime.now().strftime('%Y-%m-%d')
        }
        
        success = update_approval_status(approval_id, approval_update)
        
        if success:
            return JSONResponse({"status": "success", "message": "Request approved successfully"})
        else:
            return JSONResponse({"status": "error", "message": "Failed to update approval status"})
            
    except Exception as e:
        return JSONResponse({"status": "error", "message": f"Error processing approval: {str(e)}"})

@router.post("/reject/{approval_id}")
async def reject_request(
    approval_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Reject a request."""
    if current_user.role not in ['admin', 'manager']:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Update approval status
    approval_update = {
        'Status': 'Rejected',
        'Approved_By': current_user.full_name or current_user.email,
        'Approved_Date': __import__('datetime').datetime.now().strftime('%Y-%m-%d')
    }
    
    success = update_approval_status(approval_id, approval_update)
    
    if success:
        return JSONResponse({"status": "success", "message": "Request rejected"})
    else:
        return JSONResponse({"status": "error", "message": "Failed to update approval status"})
from fastapi import APIRouter, Request, Depends
from starlette.templating import Jinja2Templates
from app.utils.auth import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/assets")
async def assets_page(request: Request, current_user=Depends(get_current_user)):
    """Assets listing page with filtering and pagination"""
    from app.utils.sheets import get_all_assets
    
    # Ambil data asset dari Google Sheets
    all_assets = get_all_assets()
    
    # Filter hanya aset aktif (bukan Disposed)
    active_assets = [asset for asset in all_assets if asset.get("Status", "").lower() != "disposed"]
    
    return templates.TemplateResponse("assets.html", {
        "request": request,
        "user": current_user,
        "assets_data": active_assets
    })
# app/routes/asset_management.py
from fastapi import APIRouter, Depends, Request, Form, File, UploadFile, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import json
from datetime import datetime
import io

from app.database.database import get_db
from app.database.models import Profile, UserRole
from app.utils.photo import resize_and_convert_image, upload_to_drive
from app.utils.sheets import get_dropdown_options, add_asset as sheets_add_asset
from app.utils.flash import set_flash
from app.utils.auth import get_current_user, get_admin_user
from app.config import load_config

config = load_config()
router = APIRouter(prefix="/asset_management", tags=["asset_management"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/add", response_class=HTMLResponse)
async def add_asset_form(
    request: Request,
    db: Session = Depends(get_db),
    current_profile = Depends(get_current_user)
):
    """Form to add a new asset."""
    dropdown_options = get_dropdown_options()
    return templates.TemplateResponse(
        "asset_management/add.html",
        {
            "request": request,
            "user": current_profile,
            "dropdown_options": dropdown_options
        }
    )


@router.get("/list", response_class=HTMLResponse)
async def asset_list(
    request: Request,
    db: Session = Depends(get_db),
    current_profile = Depends(get_current_user)
):
    """List assets for editing (admin and manager only)."""
    if current_profile.role not in [UserRole.ADMIN, UserRole.MANAGER]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    from app.utils.sheets import get_all_assets
    assets = get_all_assets()
    
    locations = list(set(asset.get('Location', '') for asset in assets if asset.get('Location')))
    location_rooms = {}
    for asset in assets:
        location = asset.get('Location', '')
        room = asset.get('Room', '')
        if location and room:
            if location not in location_rooms:
                location_rooms[location] = set()
            location_rooms[location].add(room)
    
    for location in location_rooms:
        location_rooms[location] = list(location_rooms[location])
    
    return templates.TemplateResponse(
        "asset_management/list.html",
        {
            "request": request,
            "user": current_profile,
            "assets": assets,
            "locations": sorted(locations),
            "location_rooms": location_rooms
        }
    )


@router.get("/edit/{asset_id}", response_class=HTMLResponse)
async def edit_asset_form(
    asset_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_profile = Depends(get_current_user)
):
    """Form to edit an existing asset (admin/manager only)."""
    if current_profile.role not in [UserRole.ADMIN, UserRole.MANAGER]:
        raise HTTPException(status_code=403, detail="Access denied")

    from app.utils.sheets import get_asset_by_id
    asset = get_asset_by_id(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    dropdown_options = get_dropdown_options()
    
    return templates.TemplateResponse(
        "asset_management/edit.html",
        {
            "request": request,
            "user": current_profile,
            "asset": asset,
            "dropdown_options": dropdown_options
        }
    )


@router.post("/edit/{asset_id}")
async def update_asset(
    asset_id: str,
    request: Request,
    status: str = Form(...),
    company: str = Form(...),
    location: str = Form(...),
    room: str = Form(...),
    bisnis_unit: str = Form(None),
    edit_reason: str = Form(...),
    db: Session = Depends(get_db),
    current_profile = Depends(get_current_user)
):
    """Update existing asset (admin and manager only)."""
    if current_profile.role not in [UserRole.ADMIN, UserRole.MANAGER]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    from app.utils.sheets import update_asset as sheets_update_asset, calculate_asset_financials, get_asset_by_id
    asset = get_asset_by_id(asset_id)

    update_data = {
        "Status": status,
        "Company": company,
        "Location": location,
        "Room": room,
        "Bisnis Unit": bisnis_unit or ""
    }
    
    # Jika perlu hitung ulang nilai finansial, misalnya setelah perubahan harga
    # financials = calculate_asset_financials(purchase_cost, purchase_date, category)
    # update_data.update(financials)
    
    from app.utils.sheets import add_approval_request
    
    approval_data = {
        'type': 'edit_asset',
        'asset_id': asset_id,
        'asset_name': asset.get('Item Name', ''),
        'submitted_by': current_profile.full_name or current_profile.email,
        'submitted_date': datetime.now().strftime('%Y-%m-%d'),
        'description': f"Edit asset: {asset.get('Item Name', '')} - Reason: {edit_reason}",
        'edit_reason': edit_reason,
        'request_data': json.dumps(update_data, ensure_ascii=False)
    }
    
    approval_success = add_approval_request(approval_data)
    
    if approval_success:
        response = RedirectResponse(url="/asset_management/list", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, "Asset edit request submitted for manager approval", "success")
        return response
    else:
        dropdown_options = get_dropdown_options()
        return templates.TemplateResponse(
            "asset_management/edit.html",
            {
                "request": request,
                "user": current_profile,
                "asset": asset,
                "dropdown_options": dropdown_options,
                "error": "Error submitting edit request"
            },
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@router.post("/add")
async def add_asset(
    request: Request,
    item_name: str = Form(...),
    category: str = Form(...),
    type: str = Form(...),
    manufacture: str = Form(None),
    model: str = Form(None),
    serial_number: str = Form(None),
    company: str = Form(...),
    bisnis_unit: str = Form(None),
    location: str = Form(...),
    room: str = Form(...),
    notes: str = Form(None),
    item_condition: str = Form(None),
    purchase_date: str = Form(...),
    purchase_cost: str = Form(...),
    warranty: str = Form(None),
    supplier: str = Form(None),
    journal: str = Form(None),
    owner: str = Form(...),
    photo: UploadFile = File(None),
    db: Session = Depends(get_db),
    current_profile = Depends(get_current_user)
):
    """Process add asset form."""
    dropdown_options = get_dropdown_options()
    
    asset_data = {
        "Item Name": item_name,
        "Category": category,
        "Type": type,
        "Manufacture": manufacture or "",
        "Model": model or "",
        "Serial Number": serial_number or "",
        "Company": company,
        "Bisnis Unit": bisnis_unit or "",
        "Location": location,
        "Room": room,
        "Notes": notes or "",
        "Item Condition": item_condition or "",
        "Purchase Date": purchase_date,
        "Purchase Cost": purchase_cost,
        "Warranty": warranty or "",
        "Supplier": supplier or "",
        "Journal": journal or "",
        "Owner": owner,
        "Status": "Active"
    }
    
    photo_url = None
    if photo and photo.filename:
        try:
            contents = await photo.read()
            image_file = io.BytesIO(contents)
            processed_image = resize_and_convert_image(image_file)
            
            if processed_image:
                photo_url = upload_to_drive(processed_image, photo.filename, "new")
                if photo_url:
                    asset_data["Photo URL"] = photo_url
        except Exception as e:
            print(f"Error processing photo: {str(e)}")
    
    if current_profile.role == UserRole.ADMIN:
        success = sheets_add_asset(asset_data)
        
        if success:
            response = RedirectResponse(url="/assets/", status_code=status.HTTP_303_SEE_OTHER)
            set_flash(response, "Asset added successfully", "success")
            return response
        else:
            return templates.TemplateResponse(
                "asset_management/add.html",
                {
                    "request": request,
                    "user": current_profile,
                    "dropdown_options": dropdown_options,
                    "error": "Error adding asset to Google Sheets",
                    "form_data": asset_data
                },
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    from app.utils.sheets import add_approval_request
    
    approval_data = {
        'type': 'add_asset',
        'asset_id': 'NEW',
        'asset_name': item_name,
        'submitted_by': current_profile.full_name or current_profile.email,
        'submitted_date': datetime.now().strftime('%Y-%m-%d'),
        'description': f"Add new asset: {item_name}",
        'request_data': json.dumps(asset_data, ensure_ascii=False)
    }
    
    approval_success = add_approval_request(approval_data)
    
    if approval_success:
        response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, "Asset request submitted for approval", "success")
        return response
    else:
        return templates.TemplateResponse(
            "asset_management/add.html",
            {
                "request": request,
                "user": current_profile,
                "dropdown_options": dropdown_options,
                "error": "Error submitting approval request",
                "form_data": asset_data
            },
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
from fastapi import APIRouter, Request, Depends
from starlette.templating import Jinja2Templates
from app.utils.auth import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/")
async def damaged_assets_page(request: Request, current_user = Depends(get_current_user)):
    """Damaged assets page with search and log functionality"""
    from app.utils.sheets import get_all_assets, get_dropdown_options

    all_assets = get_all_assets()
    dropdown_options = get_dropdown_options()

    return templates.TemplateResponse("damaged_assets.html", {
        "request": request,
        "user": current_user,
        "assets_data": all_assets,
        "dropdown_options": dropdown_options
    })


@router.post("/lost")
async def submit_lost_report(request: Request, current_user = Depends(get_current_user)):
    """Submit lost report - syncs to Google Sheets"""
    from app.utils.sheets import add_lost_log, add_approval_request
    from datetime import datetime

    try:
        data = await request.json()

        lost_data = {
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'last_location': data.get('last_location'),
            'last_room': data.get('last_room', ''),
            'date_lost': data.get('date_lost'),
            'description': data.get('description'),
            'reported_by': current_user.full_name or current_user.email,
            'report_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'notes': data.get('notes', '')
        }

        log_success = add_lost_log(lost_data)

        approval_data = {
            'type': 'lost_report',
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'submitted_by': current_user.full_name or current_user.email,
            'submitted_date': datetime.now().strftime('%Y-%m-%d'),
            'description': f"Lost report: {data.get('description')}",
            'location': data.get('last_location')
        }

        approval_success = add_approval_request(approval_data)

        if log_success and approval_success:
            return {"status": "success", "message": "Lost report submitted and logged to Google Sheets"}
        else:
            return {"status": "error", "message": "Failed to sync with Google Sheets"}

    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/disposal")
async def submit_disposal_request(request: Request, current_user = Depends(get_current_user)):
    """Submit disposal request - syncs to Google Sheets"""
    from app.utils.sheets import add_disposal_log, add_approval_request
    from datetime import datetime

    try:
        data = await request.json()

        disposal_data = {
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'disposal_reason': data.get('disposal_reason'),
            'disposal_method': data.get('disposal_method', 'Standard'),
            'description': data.get('description'),
            'requested_by': current_user.full_name or current_user.email,
            'request_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'notes': data.get('notes', '')
        }

        log_success = add_disposal_log(disposal_data)

        approval_data = {
            'type': 'disposal_request',
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'submitted_by': current_user.full_name or current_user.email,
            'submitted_date': datetime.now().strftime('%Y-%m-%d'),
            'description': f"Disposal request: {data.get('description')}"
        }

        approval_success = add_approval_request(approval_data)

        if log_success and approval_success:
            return {"status": "success", "message": "Disposal request submitted and logged to Google Sheets"}
        else:
            return {"status": "error", "message": "Failed to sync with Google Sheets"}

    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/report")
async def submit_damage_report(request: Request, current_user = Depends(get_current_user)):
    """Submit damage report - syncs to Google Sheets"""
    from app.utils.sheets import add_damage_log, add_approval_request
    from datetime import datetime

    try:
        data = await request.json()

        damage_data = {
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'damage_type': data.get('damage_type'),
            'severity': data.get('severity'),
            'description': data.get('damage_description'),
            'reported_by': current_user.full_name or current_user.email,
            'report_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'location': data.get('location', ''),
            'room': data.get('room', ''),
            'notes': data.get('notes', '')
        }

        approval_data = {
            'type': 'damage_report',
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'submitted_by': current_user.full_name or current_user.email,
            'submitted_date': datetime.now().strftime('%Y-%m-%d'),
            'description': f"Damage report: {data.get('damage_description')}",
            'damage_type': data.get('damage_type'),
            'severity': data.get('severity')
        }

        approval_success = add_approval_request(approval_data)

        if approval_success:
            return {"status": "success", "message": "Damage report submitted for approval"}
        else:
            return {"status": "error", "message": "Failed to submit approval request"}

    except Exception as e:
        return {"status": "error", "message": str(e)}
# app/routes/disposal.py
from fastapi import APIRouter, Depends, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime

from app.database.database import get_db
from app.database.models import Profile
from app.utils.auth import get_admin_user
from app.utils.sheets import get_all_assets, update_asset, add_disposal_log
from app.utils.flash import set_flash

router = APIRouter(prefix="/disposal", tags=["disposal"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def disposal_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Disposal assets page (admin only)."""
    # Get assets that are ready to dispose only
    all_assets = get_all_assets()
    # Debug: check all statuses
    statuses = [str(asset.get('Status', '')).strip() for asset in all_assets]
    print(f"All statuses found: {set(statuses)}")
    
    disposable_assets = []
    for asset in all_assets:
        status = str(asset.get('Status', '')).strip()
        if status in ['To Be Disposed', 'To be Disposed', 'TO BE DISPOSED']:
            disposable_assets.append(asset)
    
    return templates.TemplateResponse(
        "disposal/index.html",
        {
            "request": request,
            "user": current_user,
            "assets": disposable_assets
        }
    )

@router.post("/dispose/{asset_id}")
async def dispose_asset(
    asset_id: str,
    request: Request,
    disposal_reason: str = Form(...),
    disposal_method: str = Form(...),
    description: str = Form(None),
    notes: str = Form(None),
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Dispose an asset (admin only)."""
    from app.utils.sheets import get_asset_by_id
    
    # Get asset data
    asset = get_asset_by_id(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    if str(asset.get('Status', '')).strip() != 'To Be Disposed':
        raise HTTPException(status_code=400, detail="Asset must be marked 'To Be Disposed' first")
    
    # Create disposal approval request
    from app.utils.sheets import add_approval_request
    
    approval_data = {
        'type': 'disposal',
        'asset_id': asset_id,
        'asset_name': asset.get('Item Name', ''),
        'submitted_by': current_user.full_name or current_user.email,
        'submitted_date': datetime.now().strftime('%Y-%m-%d'),
        'description': f"Disposal request: {disposal_reason} - {disposal_method}",
        'disposal_reason': disposal_reason,
        'disposal_method': disposal_method,
        'notes': f"Description: {description or ''} | Notes: {notes or ''}"
    }
    
    approval_success = add_approval_request(approval_data)
    
    if approval_success:
        response = RedirectResponse(url="/disposal", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, f"Disposal request for {asset.get('Item Name', '')} submitted for manager approval", "success")
        return response
    else:
        response = RedirectResponse(url="/disposal", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, "Error submitting disposal request", "error")
        return response
# app/routes/health.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
import time

from app.database.database import get_db
from app.config import load_config

router = APIRouter(tags=["health"])
config = load_config()

@router.get("/health")
async def health_check(db: Session = Depends(get_db)):
    """Health check endpoint."""
    start_time = time.time()
    
    # Check database connection
    try:
        db.execute(text("SELECT 1"))
        db_status = "healthy"
    except Exception as e:
        db_status = f"unhealthy: {str(e)}"
    
    # Check Google Sheets API
    sheets_status = "configured" if config.GOOGLE_SHEET_ID else "not configured"
    
    # Response time
    response_time = time.time() - start_time
    
    return {
        "status": "ok",
        "database": db_status,
        "google_sheets": sheets_status,
        "response_time_ms": round(response_time * 1000, 2)
    }
# /app/app/routes/home.py
import logging
from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse
from starlette.templating import Jinja2Templates
from app.utils.auth import get_current_user
from app.utils.sheets import get_summary_data, get_chart_data, get_all_assets

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=RedirectResponse)
async def redirect_root():
    return RedirectResponse("/dashboard")

@router.get("/dashboard")
async def home(request: Request, current_user = Depends(get_current_user)):
    try:
        # Summary and chart data
        summary_data = get_summary_data()
        chart_data = get_chart_data()
        all_assets = get_all_assets()

        # Filter out disposed assets for dashboard counts
        active_assets = [asset for asset in all_assets if asset.get("Status", "") != "Disposed"]
        disposed_assets = [asset for asset in all_assets if asset.get("Status", "") == "Disposed"]
        
        # Count assets by status and activity
        total_assets = len(active_assets)
        disposed_count = len(disposed_assets)
        damaged_count = len([a for a in all_assets if a.get("Status", "") == "Under Repair"])
        
        # Count assets by activity type
        relocated_count = len([a for a in all_assets if a.get("Last Activity", "") == "Relocated"])
        repaired_count = len([a for a in all_assets if a.get("Last Activity", "") == "Repaired"])
        to_be_disposed_count = len([a for a in all_assets if a.get("Status", "") == "To Be Disposed"])
        
        # Helper function to safely convert values to float
        def safe_float(value):
            if value is None or value == '':
                return 0.0
            try:
                return float(value)
            except (ValueError, TypeError):
                return 0.0
        
        # Calculate financial values directly from assets
        total_purchase_value = sum(safe_float(asset.get("Purchase Cost")) for asset in active_assets)
        total_book_value = sum(safe_float(asset.get("Book Value")) for asset in active_assets)
        # Calculate depreciation as purchase value minus book value
        total_depreciation_value = total_purchase_value - total_book_value
        category_counts = chart_data.get("category_counts", {})
        
        # Format location data
        location_data = chart_data.get("location_chart_data", {})
        location_counts = location_data.get("labels", [])
        location_values = location_data.get("values", [])
        location_counts_dict = dict(zip(location_counts, location_values))

        # Format time-based chart data
        monthly_data = chart_data.get("monthly_chart_data", {})
        monthly_chart_labels = monthly_data.get("labels", [])
        monthly_chart_values = monthly_data.get("values", [])
        
        # Generate quarterly data (last 12 quarters - 3 years)
        quarterly_chart_labels = []
        quarterly_chart_values = []
        
        # Get current year and quarter
        from datetime import datetime
        current_date = datetime.now()
        current_year = current_date.year
        current_quarter = (current_date.month - 1) // 3 + 1
        
        # Generate data for the last 12 quarters
        for i in range(11, -1, -1):
            year = current_year
            quarter = current_quarter - i
            
            # Adjust year if quarter is negative or > 4
            while quarter <= 0:
                year -= 1
                quarter += 4
            while quarter > 4:
                year += 1
                quarter -= 4
                
            quarterly_chart_labels.append(f"Q{quarter} {year}")
            
            # Count assets added in this quarter
            quarter_start_month = (quarter - 1) * 3 + 1
            quarter_end_month = quarter * 3
            
            count = 0
            for asset in all_assets:
                purchase_date = asset.get("Purchase Date", "")
                if purchase_date:
                    try:
                        date = datetime.strptime(purchase_date, "%Y-%m-%d")
                        if date.year == year and quarter_start_month <= date.month <= quarter_end_month:
                            count += 1
                    except:
                        pass
            
            quarterly_chart_values.append(count)
        
        # Generate yearly data (last 5 years)
        yearly_chart_labels = []
        yearly_chart_values = []
        
        # Generate data for the last 5 years
        for i in range(4, -1, -1):
            year = current_year - i
            yearly_chart_labels.append(str(year))
            
            # Count assets added in this year
            count = 0
            for asset in all_assets:
                purchase_date = asset.get("Purchase Date", "")
                if purchase_date:
                    try:
                        date = datetime.strptime(purchase_date, "%Y-%m-%d")
                        if date.year == year:
                            count += 1
                    except:
                        pass
            
            yearly_chart_values.append(count)

        # Format age distribution - convert to list of tuples for proper serialization
        age_distribution = chart_data.get("age_distribution", {})
        age_distribution_list = [
            {"label": str(k), "value": int(v)} 
            for k, v in age_distribution.items()
        ]

        # Format latest assets (excluding disposed assets)
        latest_assets = sorted(
            active_assets, 
            key=lambda a: a.get("Purchase Date", ""), 
            reverse=True
        )[:10]
        
        # Process assets to ensure they have a display_name field
        for asset in latest_assets:
            # Try different possible field names for the asset name
            name_fields = ["Name", "Asset Name", "AssetName", "Item Name", "Description", "Item"]
            display_name = None
            
            for field in name_fields:
                if asset.get(field):
                    display_name = asset.get(field)
                    break
            
            # If no name found, use a default
            if not display_name:
                display_name = f"Asset #{asset.get('ID', 'Unknown')}"
                
            # Add the display_name to the asset
            asset["display_name"] = display_name
            
        # Debug: Print the first asset's keys to see what fields are available
        if latest_assets:
            logging.info(f"Asset keys: {list(latest_assets[0].keys())}")
            logging.info(f"Asset display name: {latest_assets[0].get('display_name', 'Not found')}")
            logging.info(f"Original asset name fields: {[latest_assets[0].get(f, 'None') for f in name_fields]}")

        context = {
            "request": request,
            "user": current_user,
            "total_assets": total_assets,
            "total_purchase_value": total_purchase_value,
            "total_book_value": total_book_value,
            "total_depreciation_value": total_depreciation_value,
            "disposed_count": disposed_count,
            "damaged_count": damaged_count,
            "relocated_count": relocated_count,
            "repaired_count": repaired_count,
            "to_be_disposed_count": to_be_disposed_count,
            "category_counts": category_counts,
            "location_counts": location_counts_dict,
            "monthly_chart_labels": monthly_chart_labels,
            "monthly_chart_values": monthly_chart_values,
            "quarterly_chart_labels": quarterly_chart_labels,
            "quarterly_chart_values": quarterly_chart_values,
            "yearly_chart_labels": yearly_chart_labels,
            "yearly_chart_values": yearly_chart_values,
            "age_distribution": age_distribution_list,
            "latest_assets": latest_assets
        }

        return templates.TemplateResponse("dashboard.html", context)

    except Exception as e:
        logging.error("Dashboard error: %s", e, exc_info=True)
        return templates.TemplateResponse("error.html", {
            "request": request,
            "user": current_user,
            "message": "Terjadi kesalahan saat memuat dashboard.",
        })
from fastapi import APIRouter, Request, Response, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from supabase import create_client, Client
from app.config import load_config
import logging

config = load_config()
supabase: Client = create_client(config.SUPABASE_URL, config.SUPABASE_ANON_KEY)

router = APIRouter(tags=["authentication"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/login", response_class=HTMLResponse)
@router.head("/login", response_class=HTMLResponse)
async def login_page(request: Request, next: str = None):
    return templates.TemplateResponse("login_logout.html", {"request": request, "next": next})

@router.post("/login", response_class=HTMLResponse)
async def login_form(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    next: str = Form(None)
):
    try:
        # Use service key client for admin operations
        from supabase import create_client
        admin_supabase = create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_KEY)
        
        response = admin_supabase.auth.sign_in_with_password({
            "email": email,
            "password": password
        })
        
        if not response.user:
            return templates.TemplateResponse(
                "login_logout.html",
                {"request": request, "error": "Invalid email or password", "next": next},
                status_code=401
            )
        
        # Get user profile
        profile_response = admin_supabase.table('profiles').select('*').eq('id', response.user.id).single().execute()
        if not profile_response.data or not profile_response.data.get('is_active'):
            return templates.TemplateResponse(
                "login_logout.html",
                {"request": request, "error": "Account is inactive", "next": next},
                status_code=401
            )
        
        redirect_url = next if next else "/"
        redirect_response = RedirectResponse(url=redirect_url, status_code=303)
        
        redirect_response.set_cookie(
            key="sb_access_token",
            value=response.session.access_token,
            httponly=True,
            max_age=3600,
            samesite="lax",
            secure=True,
            domain=".onrender.com"
        )
        
        return redirect_response
        
    except Exception as e:
        logging.error(f"Login error: {str(e)}")
        return templates.TemplateResponse(
            "login_logout.html",
            {"request": request, "error": "Login failed", "next": next},
            status_code=401
        )

@router.get("/auth/callback")
async def auth_callback(request: Request):
    return templates.TemplateResponse("auth_callback.html", {"request": request})

@router.get("/logout")
async def logout():
    try:
        supabase.auth.sign_out()
    except:
        pass
    
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(key="sb_access_token")
    return response
# app/routes/logs.py
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.database.models import Profile
from app.utils.auth import get_current_user
from app.utils.sheets import get_all_approvals

router = APIRouter(prefix="/logs", tags=["logs"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def logs_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """View approval logs based on user role."""
    all_approvals = get_all_approvals()
    
    # Filter based on user role
    if current_user.role.value == 'staff':
        # Staff can only see their own requests
        user_identifier = current_user.full_name or current_user.email
        approvals = [a for a in all_approvals if a.get('Submitted_By') == user_identifier]
    else:
        # Manager and admin can see all approvals
        approvals = all_approvals
    
    # Separate pending and completed
    pending_approvals = [a for a in approvals if a.get('Status') == 'Pending']
    completed_approvals = [a for a in approvals if a.get('Status') in ['Approved', 'Rejected']]
    
    return templates.TemplateResponse(
        "logs/index.html",
        {
            "request": request,
            "user": current_user,
            "pending_approvals": pending_approvals,
            "completed_approvals": completed_approvals
        }
    )
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
from fastapi import APIRouter, Depends, Request, Form, UploadFile, File, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from app.database.database import get_db
from app.database.models import Profile
from app.utils.auth import get_current_user
from app.utils.photo import resize_and_convert_image, upload_to_drive
from app.utils.flash import set_flash

router = APIRouter(tags=["profile"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/profile", response_class=HTMLResponse)
async def profile_page(
    request: Request,
    current_user = Depends(get_current_user)
):
    """User profile page."""
    return templates.TemplateResponse(
        "profile/view.html",
        {
            "request": request,
            "user": current_user
        }
    )

@router.get("/profile/edit", response_class=HTMLResponse)
async def edit_profile_page(
    request: Request,
    current_user = Depends(get_current_user)
):
    """Edit user profile page."""
    return templates.TemplateResponse(
        "profile/edit.html",
        {
            "request": request,
            "user": current_user
        }
    )

@router.post("/profile/edit")
async def update_profile(
    request: Request,
    full_name: str = Form(...),
    email: str = Form(...),
    photo: UploadFile = File(None),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Update user profile."""
    # Update basic info
    current_user.full_name = full_name
    current_user.email = email
    current_user.updated_at = datetime.now(timezone.utc)
    
    # Handle photo upload if provided
    if photo and photo.filename:
        try:
            # Process image
            contents = await photo.read()
            import io
            image_file = io.BytesIO(contents)
            processed_image = resize_and_convert_image(image_file)
            
            if processed_image:
                # Upload to Google Drive
                photo_url = upload_to_drive(
                    processed_image, 
                    photo.filename, 
                    f"profile_{current_user.email}"
                )
                if photo_url:
                    current_user.photo_url = photo_url
        except Exception as e:
            return templates.TemplateResponse(
                "profile/edit.html",
                {
                    "request": request,
                    "user": current_user,
                    "error": f"Error uploading photo: {str(e)}"
                },
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    # Save changes
    db.commit()
    
    # Redirect to profile page
    response = RedirectResponse(url="/profile", status_code=status.HTTP_303_SEE_OTHER)
    set_flash(response, "Profile updated successfully", "success")
    return response
# app/routes/relocation.py
from fastapi import APIRouter, Depends, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime
import json

from app.database.database import get_db
from app.database.models import Profile
from app.utils.auth import get_current_user
from app.utils.sheets import get_all_assets, get_dropdown_options, add_approval_request
from app.utils.flash import set_flash

router = APIRouter(prefix="/relocation", tags=["relocation"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def relocation_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Asset relocation page."""
    # Get assets and dropdown options
    all_assets = get_all_assets()
    dropdown_options = get_dropdown_options()
    
    return templates.TemplateResponse(
        "relocation/index.html",
        {
            "request": request,
            "user": current_user,
            "assets": all_assets,
            "dropdown_options": dropdown_options
        }
    )

@router.post("/relocate/{asset_id}")
async def relocate_asset(
    asset_id: str,
    request: Request,
    new_location: str = Form(...),
    new_room: str = Form(...),
    reason: str = Form(...),
    notes: str = Form(None),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Submit asset relocation request."""
    from app.utils.sheets import get_asset_by_id
    
    # Get asset data
    asset = get_asset_by_id(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    # Create relocation approval request
    relocation_data = {
        'new_location': new_location,
        'new_room': new_room,
        'current_location': asset.get('Location', ''),
        'current_room': asset.get('Room', ''),
        'reason': reason,
        'notes': notes or ''
    }
    
    approval_data = {
        'type': 'relocation',
        'asset_id': asset_id,
        'asset_name': asset.get('Item Name', ''),
        'submitted_by': current_user.full_name or current_user.email,
        'submitted_date': datetime.now().strftime('%Y-%m-%d'),
        'description': f"Relocate from {asset.get('Location', '')} - {asset.get('Room', '')} to {new_location} - {new_room}",
        'request_data': json.dumps(relocation_data, ensure_ascii=False)
    }
    
    approval_success = add_approval_request(approval_data)
    
    if approval_success:
        response = RedirectResponse(url="/relocation", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, f"Relocation request for {asset.get('Item Name', '')} submitted for approval", "success")
        return response
    else:
        response = RedirectResponse(url="/relocation", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, "Error submitting relocation request", "error")
        return response
# /app/app/routes/repair.py
from fastapi import APIRouter, Request, Depends
from starlette.templating import Jinja2Templates
from app.utils.auth import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.post("/action")
async def submit_repair_action(request: Request, current_user = Depends(get_current_user)):
    """Submit repair action - creates approval request for store, direct action for allocate"""
    from app.utils.sheets import add_repair_log, update_asset, add_approval_request
    from datetime import datetime
    
    try:
        # Get JSON data
        data = await request.json()
        action_type = data.get('action_type')  # 'store' or 'allocate'
        
        if action_type == 'store':
            # Store action requires approval - only create approval request
            approval_data = {
                'type': 'repair_action',
                'asset_id': data.get('asset_id'),
                'asset_name': data.get('asset_name'),
                'submitted_by': current_user.full_name or current_user.email,
                'submitted_date': datetime.now().strftime('%Y-%m-%d'),
                'description': f"Request to store asset: {data.get('description')}",
                'action': 'Store Asset'
            }
            
            approval_success = add_approval_request(approval_data)
            
            if approval_success:
                return {"status": "success", "message": "Store request submitted for admin approval"}
            else:
                return {"status": "error", "message": "Failed to submit approval request"}
        
        else:  # allocate - direct action
            # Add to Repair_Log sheet
            repair_data = {
                'asset_id': data.get('asset_id'),
                'asset_name': data.get('asset_name'),
                'repair_action': 'Allocate Asset',
                'action_type': action_type,
                'description': data.get('description', ''),
                'performed_by': current_user.full_name or current_user.email,
                'action_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'new_location': data.get('location', ''),
                'new_room': data.get('room', ''),
                'notes': data.get('notes', '')
            }
            
            # Add to repair log
            log_success = add_repair_log(repair_data)
            
            # Update asset from Under Repair to Active
            update_data = {
                'Status': 'Active',
                'Bisnis Unit': data.get('business_unit', ''),
                'Location': data.get('location', ''),
                'Room': data.get('room', '')
            }
            
            asset_success = update_asset(data.get('asset_id'), update_data)
            
            if log_success and asset_success:
                return {"status": "success", "message": "Asset allocated successfully and synced to Google Sheets"}
            else:
                return {"status": "error", "message": "Failed to sync with Google Sheets"}
            
    except Exception as e:
        return {"status": "error", "message": str(e)}
# app/routes/user_management.py
from fastapi import APIRouter, Depends, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.database.models import Profile, UserRole
from app.utils.auth import get_current_user, get_admin_user
from app.utils.flash import set_flash

router = APIRouter(prefix="/user_management", tags=["user_management"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def user_list(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """List all users (admin only)."""
    users = db.query(Profile).all()
    
    return templates.TemplateResponse(
        "user_management/list.html",
        {
            "request": request,
            "user": current_user,
            "users": users
        }
    )

@router.get("/create", response_class=HTMLResponse)
async def create_user_form(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Create user form (admin only)."""
    return templates.TemplateResponse(
        "user_management/create.html",
        {
            "request": request,
            "user": current_user
        }
    )

@router.post("/create")
async def create_user(
    request: Request,
    email: str = Form(...),
    full_name: str = Form(...),
    role: str = Form(...),
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Create new user (admin only)."""
    # Check if user exists
    existing_user = db.query(Profile).filter(Profile.email == email).first()
    if existing_user:
        return templates.TemplateResponse(
            "user_management/create.html",
            {
                "request": request,
                "user": current_user,
                "error": "Email already exists"
            }
        )
    
    # Create user profile (Supabase handles auth)
    new_user = Profile(
        email=email,
        full_name=full_name,
        role=getattr(UserRole, role.upper()),
        is_active=True
    )
    
    db.add(new_user)
    db.commit()
    
    response = RedirectResponse(url="/user_management", status_code=status.HTTP_303_SEE_OTHER)
    set_flash(response, f"User {email} created successfully", "success")
    return response

@router.post("/reset_password/{user_id}")
async def reset_password(
    user_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Reset user password to default (admin only)."""
    user = db.query(Profile).filter(Profile.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Password reset handled by Supabase
    default_password = f"{user.email.split('@')[0]}123"
    
    response = RedirectResponse(url="/user_management", status_code=status.HTTP_303_SEE_OTHER)
    set_flash(response, f"Password reset instructions sent to {user.email}", "success")
    return response

@router.post("/toggle_status/{user_id}")
async def toggle_user_status(
    user_id: str,
    request: Request,
    is_active: bool = Form(...),
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Toggle user active status (admin only)."""
    user = db.query(Profile).filter(Profile.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Update status
    user.is_active = is_active
    db.commit()
    
    status_text = "activated" if is_active else "deactivated"
    response = RedirectResponse(url="/user_management", status_code=status.HTTP_303_SEE_OTHER)
    set_flash(response, f"User {user.email} {status_text}", "success")
    return response
# app/routes/__init__.py

# Import all route modules to make them available from app.routes
from app.routes import (
    home,
    assets,
    asset_management,
    login,
    damage,
    health,
    offline,
    profile,
    repair,
    approvals,
    disposal,
    user_management,
    logs,
    relocation
)
# app/routes/approvals.py
from fastapi import APIRouter, Depends, Request, HTTPException, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.utils.auth import get_current_user
from app.utils.sheets import get_all_approvals, update_approval_status

router = APIRouter(prefix="/approvals", tags=["approvals"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def approvals_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Approvals page for admin and manager."""
    if current_user.role not in ['admin', 'manager']:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get all approvals from Google Sheets
    all_approvals = get_all_approvals()
    
    # Filter approvals based on user role
    if current_user.role == 'admin':
        # Admin sees all approvals except disposal and edit_asset
        approvals_data = [a for a in all_approvals if a.get('Type') not in ['disposal', 'edit_asset']]
    elif current_user.role == 'manager':
        # Manager sees disposal and edit_asset approvals
        approvals_data = [a for a in all_approvals if a.get('Type') in ['disposal', 'edit_asset']]
    else:
        approvals_data = []
    
    return templates.TemplateResponse(
        "approvals/list.html",
        {
            "request": request,
            "user": current_user,
            "approvals_data": approvals_data
        }
    )

@router.post("/approve/{approval_id}")
async def approve_request(
    approval_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Approve a request."""
    if current_user.role not in ['admin', 'manager']:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get approval details
    all_approvals = get_all_approvals()
    approval = next((a for a in all_approvals if str(a.get('ID')) == str(approval_id)), None)
    
    if not approval:
        return JSONResponse({"status": "error", "message": "Approval not found"})
    
    # Process approval based on type
    try:
        if approval.get('Type') == 'damage_report':
            # Update asset status to "Under Repair"
            from app.utils.sheets import update_asset
            success = update_asset(approval.get('Asset_ID'), {'Status': 'Under Repair'})
            if not success:
                return JSONResponse({"status": "error", "message": "Failed to update asset status"})
        
        elif approval.get('Type') == 'relocation':
            # Process relocation approval
            import json
            try:
                request_data_str = approval.get('Request_Data', '')
                if request_data_str:
                    relocation_data = json.loads(request_data_str)
                    update_data = {
                        'Location': relocation_data.get('new_location'),
                        'Room': relocation_data.get('new_room')
                    }
                    from app.utils.sheets import update_asset
                    success = update_asset(approval.get('Asset_ID'), update_data)
                    if not success:
                        return JSONResponse({"status": "error", "message": "Failed to relocate asset"})
            except Exception as e:
                return JSONResponse({"status": "error", "message": f"Error processing relocation: {str(e)}"})
            
        elif approval.get('Type') == 'edit_asset':
            # Process edit asset approval
            import json
            try:
                request_data_str = approval.get('Request_Data', '')
                if request_data_str:
                    edit_data = json.loads(request_data_str)
                    from app.utils.sheets import update_asset
                    success = update_asset(approval.get('Asset_ID'), edit_data)
                    if not success:
                        return JSONResponse({"status": "error", "message": "Failed to update asset"})
            except Exception as e:
                return JSONResponse({"status": "error", "message": f"Error processing edit: {str(e)}"})
        
        # Update approval status
        approval_update = {
            'Status': 'Approved',
            'Approved_By': current_user.full_name or current_user.email,
            'Approved_Date': __import__('datetime').datetime.now().strftime('%Y-%m-%d')
        }
        
        success = update_approval_status(approval_id, approval_update)
        
        if success:
            return JSONResponse({"status": "success", "message": "Request approved successfully"})
        else:
            return JSONResponse({"status": "error", "message": "Failed to update approval status"})
            
    except Exception as e:
        return JSONResponse({"status": "error", "message": f"Error processing approval: {str(e)}"})

@router.post("/reject/{approval_id}")
async def reject_request(
    approval_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Reject a request."""
    if current_user.role not in ['admin', 'manager']:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Update approval status
    approval_update = {
        'Status': 'Rejected',
        'Approved_By': current_user.full_name or current_user.email,
        'Approved_Date': __import__('datetime').datetime.now().strftime('%Y-%m-%d')
    }
    
    success = update_approval_status(approval_id, approval_update)
    
    if success:
        return JSONResponse({"status": "success", "message": "Request rejected"})
    else:
        return JSONResponse({"status": "error", "message": "Failed to update approval status"})
from fastapi import APIRouter, Request, Depends
from starlette.templating import Jinja2Templates
from app.utils.auth import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/assets")
async def assets_page(request: Request, current_user=Depends(get_current_user)):
    """Assets listing page with filtering and pagination"""
    from app.utils.sheets import get_all_assets
    
    # Ambil data asset dari Google Sheets
    all_assets = get_all_assets()
    
    # Filter hanya aset aktif (bukan Disposed)
    active_assets = [asset for asset in all_assets if asset.get("Status", "").lower() != "disposed"]
    
    return templates.TemplateResponse("assets.html", {
        "request": request,
        "user": current_user,
        "assets_data": active_assets
    })
# app/routes/asset_management.py
from fastapi import APIRouter, Depends, Request, Form, File, UploadFile, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import json
from datetime import datetime
import io

from app.database.database import get_db
from app.database.models import Profile, UserRole
from app.utils.photo import resize_and_convert_image, upload_to_drive
from app.utils.sheets import get_dropdown_options, add_asset as sheets_add_asset
from app.utils.flash import set_flash
from app.utils.auth import get_current_user, get_admin_user
from app.config import load_config

config = load_config()
router = APIRouter(prefix="/asset_management", tags=["asset_management"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/add", response_class=HTMLResponse)
async def add_asset_form(
    request: Request,
    db: Session = Depends(get_db),
    current_profile = Depends(get_current_user)
):
    """Form to add a new asset."""
    dropdown_options = get_dropdown_options()
    return templates.TemplateResponse(
        "asset_management/add.html",
        {
            "request": request,
            "user": current_profile,
            "dropdown_options": dropdown_options
        }
    )


@router.get("/list", response_class=HTMLResponse)
async def asset_list(
    request: Request,
    db: Session = Depends(get_db),
    current_profile = Depends(get_current_user)
):
    """List assets for editing (admin and manager only)."""
    if current_profile.role not in [UserRole.ADMIN, UserRole.MANAGER]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    from app.utils.sheets import get_all_assets
    assets = get_all_assets()
    
    locations = list(set(asset.get('Location', '') for asset in assets if asset.get('Location')))
    location_rooms = {}
    for asset in assets:
        location = asset.get('Location', '')
        room = asset.get('Room', '')
        if location and room:
            if location not in location_rooms:
                location_rooms[location] = set()
            location_rooms[location].add(room)
    
    for location in location_rooms:
        location_rooms[location] = list(location_rooms[location])
    
    return templates.TemplateResponse(
        "asset_management/list.html",
        {
            "request": request,
            "user": current_profile,
            "assets": assets,
            "locations": sorted(locations),
            "location_rooms": location_rooms
        }
    )


@router.get("/edit/{asset_id}", response_class=HTMLResponse)
async def edit_asset_form(
    asset_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_profile = Depends(get_current_user)
):
    """Form to edit an existing asset (admin/manager only)."""
    if current_profile.role not in [UserRole.ADMIN, UserRole.MANAGER]:
        raise HTTPException(status_code=403, detail="Access denied")

    from app.utils.sheets import get_asset_by_id
    asset = get_asset_by_id(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    dropdown_options = get_dropdown_options()
    
    return templates.TemplateResponse(
        "asset_management/edit.html",
        {
            "request": request,
            "user": current_profile,
            "asset": asset,
            "dropdown_options": dropdown_options
        }
    )


@router.post("/edit/{asset_id}")
async def update_asset(
    asset_id: str,
    request: Request,
    status: str = Form(...),
    company: str = Form(...),
    location: str = Form(...),
    room: str = Form(...),
    bisnis_unit: str = Form(None),
    edit_reason: str = Form(...),
    db: Session = Depends(get_db),
    current_profile = Depends(get_current_user)
):
    """Update existing asset (admin and manager only)."""
    if current_profile.role not in [UserRole.ADMIN, UserRole.MANAGER]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    from app.utils.sheets import update_asset as sheets_update_asset, calculate_asset_financials, get_asset_by_id
    asset = get_asset_by_id(asset_id)

    update_data = {
        "Status": status,
        "Company": company,
        "Location": location,
        "Room": room,
        "Bisnis Unit": bisnis_unit or ""
    }
    
    # Jika perlu hitung ulang nilai finansial, misalnya setelah perubahan harga
    # financials = calculate_asset_financials(purchase_cost, purchase_date, category)
    # update_data.update(financials)
    
    from app.utils.sheets import add_approval_request
    
    approval_data = {
        'type': 'edit_asset',
        'asset_id': asset_id,
        'asset_name': asset.get('Item Name', ''),
        'submitted_by': current_profile.full_name or current_profile.email,
        'submitted_date': datetime.now().strftime('%Y-%m-%d'),
        'description': f"Edit asset: {asset.get('Item Name', '')} - Reason: {edit_reason}",
        'edit_reason': edit_reason,
        'request_data': json.dumps(update_data, ensure_ascii=False)
    }
    
    approval_success = add_approval_request(approval_data)
    
    if approval_success:
        response = RedirectResponse(url="/asset_management/list", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, "Asset edit request submitted for manager approval", "success")
        return response
    else:
        dropdown_options = get_dropdown_options()
        return templates.TemplateResponse(
            "asset_management/edit.html",
            {
                "request": request,
                "user": current_profile,
                "asset": asset,
                "dropdown_options": dropdown_options,
                "error": "Error submitting edit request"
            },
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@router.post("/add")
async def add_asset(
    request: Request,
    item_name: str = Form(...),
    category: str = Form(...),
    type: str = Form(...),
    manufacture: str = Form(None),
    model: str = Form(None),
    serial_number: str = Form(None),
    company: str = Form(...),
    bisnis_unit: str = Form(None),
    location: str = Form(...),
    room: str = Form(...),
    notes: str = Form(None),
    item_condition: str = Form(None),
    purchase_date: str = Form(...),
    purchase_cost: str = Form(...),
    warranty: str = Form(None),
    supplier: str = Form(None),
    journal: str = Form(None),
    owner: str = Form(...),
    photo: UploadFile = File(None),
    db: Session = Depends(get_db),
    current_profile = Depends(get_current_user)
):
    """Process add asset form."""
    dropdown_options = get_dropdown_options()
    
    asset_data = {
        "Item Name": item_name,
        "Category": category,
        "Type": type,
        "Manufacture": manufacture or "",
        "Model": model or "",
        "Serial Number": serial_number or "",
        "Company": company,
        "Bisnis Unit": bisnis_unit or "",
        "Location": location,
        "Room": room,
        "Notes": notes or "",
        "Item Condition": item_condition or "",
        "Purchase Date": purchase_date,
        "Purchase Cost": purchase_cost,
        "Warranty": warranty or "",
        "Supplier": supplier or "",
        "Journal": journal or "",
        "Owner": owner,
        "Status": "Active"
    }
    
    photo_url = None
    if photo and photo.filename:
        try:
            contents = await photo.read()
            image_file = io.BytesIO(contents)
            processed_image = resize_and_convert_image(image_file)
            
            if processed_image:
                photo_url = upload_to_drive(processed_image, photo.filename, "new")
                if photo_url:
                    asset_data["Photo URL"] = photo_url
        except Exception as e:
            print(f"Error processing photo: {str(e)}")
    
    if current_profile.role == UserRole.ADMIN:
        success = sheets_add_asset(asset_data)
        
        if success:
            response = RedirectResponse(url="/assets/", status_code=status.HTTP_303_SEE_OTHER)
            set_flash(response, "Asset added successfully", "success")
            return response
        else:
            return templates.TemplateResponse(
                "asset_management/add.html",
                {
                    "request": request,
                    "user": current_profile,
                    "dropdown_options": dropdown_options,
                    "error": "Error adding asset to Google Sheets",
                    "form_data": asset_data
                },
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    from app.utils.sheets import add_approval_request
    
    approval_data = {
        'type': 'add_asset',
        'asset_id': 'NEW',
        'asset_name': item_name,
        'submitted_by': current_profile.full_name or current_profile.email,
        'submitted_date': datetime.now().strftime('%Y-%m-%d'),
        'description': f"Add new asset: {item_name}",
        'request_data': json.dumps(asset_data, ensure_ascii=False)
    }
    
    approval_success = add_approval_request(approval_data)
    
    if approval_success:
        response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, "Asset request submitted for approval", "success")
        return response
    else:
        return templates.TemplateResponse(
            "asset_management/add.html",
            {
                "request": request,
                "user": current_profile,
                "dropdown_options": dropdown_options,
                "error": "Error submitting approval request",
                "form_data": asset_data
            },
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
from fastapi import APIRouter, Request, Depends
from starlette.templating import Jinja2Templates
from app.utils.auth import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/")
async def damaged_assets_page(request: Request, current_user = Depends(get_current_user)):
    """Damaged assets page with search and log functionality"""
    from app.utils.sheets import get_all_assets, get_dropdown_options

    all_assets = get_all_assets()
    dropdown_options = get_dropdown_options()

    return templates.TemplateResponse("damaged_assets.html", {
        "request": request,
        "user": current_user,
        "assets_data": all_assets,
        "dropdown_options": dropdown_options
    })


@router.post("/lost")
async def submit_lost_report(request: Request, current_user = Depends(get_current_user)):
    """Submit lost report - syncs to Google Sheets"""
    from app.utils.sheets import add_lost_log, add_approval_request
    from datetime import datetime

    try:
        data = await request.json()

        lost_data = {
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'last_location': data.get('last_location'),
            'last_room': data.get('last_room', ''),
            'date_lost': data.get('date_lost'),
            'description': data.get('description'),
            'reported_by': current_user.full_name or current_user.email,
            'report_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'notes': data.get('notes', '')
        }

        log_success = add_lost_log(lost_data)

        approval_data = {
            'type': 'lost_report',
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'submitted_by': current_user.full_name or current_user.email,
            'submitted_date': datetime.now().strftime('%Y-%m-%d'),
            'description': f"Lost report: {data.get('description')}",
            'location': data.get('last_location')
        }

        approval_success = add_approval_request(approval_data)

        if log_success and approval_success:
            return {"status": "success", "message": "Lost report submitted and logged to Google Sheets"}
        else:
            return {"status": "error", "message": "Failed to sync with Google Sheets"}

    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/disposal")
async def submit_disposal_request(request: Request, current_user = Depends(get_current_user)):
    """Submit disposal request - syncs to Google Sheets"""
    from app.utils.sheets import add_disposal_log, add_approval_request
    from datetime import datetime

    try:
        data = await request.json()

        disposal_data = {
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'disposal_reason': data.get('disposal_reason'),
            'disposal_method': data.get('disposal_method', 'Standard'),
            'description': data.get('description'),
            'requested_by': current_user.full_name or current_user.email,
            'request_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'notes': data.get('notes', '')
        }

        log_success = add_disposal_log(disposal_data)

        approval_data = {
            'type': 'disposal_request',
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'submitted_by': current_user.full_name or current_user.email,
            'submitted_date': datetime.now().strftime('%Y-%m-%d'),
            'description': f"Disposal request: {data.get('description')}"
        }

        approval_success = add_approval_request(approval_data)

        if log_success and approval_success:
            return {"status": "success", "message": "Disposal request submitted and logged to Google Sheets"}
        else:
            return {"status": "error", "message": "Failed to sync with Google Sheets"}

    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/report")
async def submit_damage_report(request: Request, current_user = Depends(get_current_user)):
    """Submit damage report - syncs to Google Sheets"""
    from app.utils.sheets import add_damage_log, add_approval_request
    from datetime import datetime

    try:
        data = await request.json()

        damage_data = {
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'damage_type': data.get('damage_type'),
            'severity': data.get('severity'),
            'description': data.get('damage_description'),
            'reported_by': current_user.full_name or current_user.email,
            'report_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'location': data.get('location', ''),
            'room': data.get('room', ''),
            'notes': data.get('notes', '')
        }

        approval_data = {
            'type': 'damage_report',
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'submitted_by': current_user.full_name or current_user.email,
            'submitted_date': datetime.now().strftime('%Y-%m-%d'),
            'description': f"Damage report: {data.get('damage_description')}",
            'damage_type': data.get('damage_type'),
            'severity': data.get('severity')
        }

        approval_success = add_approval_request(approval_data)

        if approval_success:
            return {"status": "success", "message": "Damage report submitted for approval"}
        else:
            return {"status": "error", "message": "Failed to submit approval request"}

    except Exception as e:
        return {"status": "error", "message": str(e)}
# app/routes/disposal.py
from fastapi import APIRouter, Depends, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime

from app.database.database import get_db
from app.database.models import Profile
from app.utils.auth import get_admin_user
from app.utils.sheets import get_all_assets, update_asset, add_disposal_log
from app.utils.flash import set_flash

router = APIRouter(prefix="/disposal", tags=["disposal"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def disposal_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Disposal assets page (admin only)."""
    # Get assets that are ready to dispose only
    all_assets = get_all_assets()
    # Debug: check all statuses
    statuses = [str(asset.get('Status', '')).strip() for asset in all_assets]
    print(f"All statuses found: {set(statuses)}")
    
    disposable_assets = []
    for asset in all_assets:
        status = str(asset.get('Status', '')).strip()
        if status in ['To Be Disposed', 'To be Disposed', 'TO BE DISPOSED']:
            disposable_assets.append(asset)
    
    return templates.TemplateResponse(
        "disposal/index.html",
        {
            "request": request,
            "user": current_user,
            "assets": disposable_assets
        }
    )

@router.post("/dispose/{asset_id}")
async def dispose_asset(
    asset_id: str,
    request: Request,
    disposal_reason: str = Form(...),
    disposal_method: str = Form(...),
    description: str = Form(None),
    notes: str = Form(None),
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Dispose an asset (admin only)."""
    from app.utils.sheets import get_asset_by_id
    
    # Get asset data
    asset = get_asset_by_id(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    if str(asset.get('Status', '')).strip() != 'To Be Disposed':
        raise HTTPException(status_code=400, detail="Asset must be marked 'To Be Disposed' first")
    
    # Create disposal approval request
    from app.utils.sheets import add_approval_request
    
    approval_data = {
        'type': 'disposal',
        'asset_id': asset_id,
        'asset_name': asset.get('Item Name', ''),
        'submitted_by': current_user.full_name or current_user.email,
        'submitted_date': datetime.now().strftime('%Y-%m-%d'),
        'description': f"Disposal request: {disposal_reason} - {disposal_method}",
        'disposal_reason': disposal_reason,
        'disposal_method': disposal_method,
        'notes': f"Description: {description or ''} | Notes: {notes or ''}"
    }
    
    approval_success = add_approval_request(approval_data)
    
    if approval_success:
        response = RedirectResponse(url="/disposal", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, f"Disposal request for {asset.get('Item Name', '')} submitted for manager approval", "success")
        return response
    else:
        response = RedirectResponse(url="/disposal", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, "Error submitting disposal request", "error")
        return response
# app/routes/health.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
import time

from app.database.database import get_db
from app.config import load_config

router = APIRouter(tags=["health"])
config = load_config()

@router.get("/health")
async def health_check(db: Session = Depends(get_db)):
    """Health check endpoint."""
    start_time = time.time()
    
    # Check database connection
    try:
        db.execute(text("SELECT 1"))
        db_status = "healthy"
    except Exception as e:
        db_status = f"unhealthy: {str(e)}"
    
    # Check Google Sheets API
    sheets_status = "configured" if config.GOOGLE_SHEET_ID else "not configured"
    
    # Response time
    response_time = time.time() - start_time
    
    return {
        "status": "ok",
        "database": db_status,
        "google_sheets": sheets_status,
        "response_time_ms": round(response_time * 1000, 2)
    }
# /app/app/routes/home.py
import logging
from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse
from starlette.templating import Jinja2Templates
from app.utils.auth import get_current_user
from app.utils.sheets import get_summary_data, get_chart_data, get_all_assets

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=RedirectResponse)
async def redirect_root():
    return RedirectResponse("/dashboard")

@router.get("/dashboard")
async def home(request: Request, current_user = Depends(get_current_user)):
    try:
        # Summary and chart data
        summary_data = get_summary_data()
        chart_data = get_chart_data()
        all_assets = get_all_assets()

        # Filter out disposed assets for dashboard counts
        active_assets = [asset for asset in all_assets if asset.get("Status", "") != "Disposed"]
        disposed_assets = [asset for asset in all_assets if asset.get("Status", "") == "Disposed"]
        
        # Count assets by status and activity
        total_assets = len(active_assets)
        disposed_count = len(disposed_assets)
        damaged_count = len([a for a in all_assets if a.get("Status", "") == "Under Repair"])
        
        # Count assets by activity type
        relocated_count = len([a for a in all_assets if a.get("Last Activity", "") == "Relocated"])
        repaired_count = len([a for a in all_assets if a.get("Last Activity", "") == "Repaired"])
        to_be_disposed_count = len([a for a in all_assets if a.get("Status", "") == "To Be Disposed"])
        
        # Helper function to safely convert values to float
        def safe_float(value):
            if value is None or value == '':
                return 0.0
            try:
                return float(value)
            except (ValueError, TypeError):
                return 0.0
        
        # Calculate financial values directly from assets
        total_purchase_value = sum(safe_float(asset.get("Purchase Cost")) for asset in active_assets)
        total_book_value = sum(safe_float(asset.get("Book Value")) for asset in active_assets)
        # Calculate depreciation as purchase value minus book value
        total_depreciation_value = total_purchase_value - total_book_value
        category_counts = chart_data.get("category_counts", {})
        
        # Format location data
        location_data = chart_data.get("location_chart_data", {})
        location_counts = location_data.get("labels", [])
        location_values = location_data.get("values", [])
        location_counts_dict = dict(zip(location_counts, location_values))

        # Format time-based chart data
        monthly_data = chart_data.get("monthly_chart_data", {})
        monthly_chart_labels = monthly_data.get("labels", [])
        monthly_chart_values = monthly_data.get("values", [])
        
        # Generate quarterly data (last 12 quarters - 3 years)
        quarterly_chart_labels = []
        quarterly_chart_values = []
        
        # Get current year and quarter
        from datetime import datetime
        current_date = datetime.now()
        current_year = current_date.year
        current_quarter = (current_date.month - 1) // 3 + 1
        
        # Generate data for the last 12 quarters
        for i in range(11, -1, -1):
            year = current_year
            quarter = current_quarter - i
            
            # Adjust year if quarter is negative or > 4
            while quarter <= 0:
                year -= 1
                quarter += 4
            while quarter > 4:
                year += 1
                quarter -= 4
                
            quarterly_chart_labels.append(f"Q{quarter} {year}")
            
            # Count assets added in this quarter
            quarter_start_month = (quarter - 1) * 3 + 1
            quarter_end_month = quarter * 3
            
            count = 0
            for asset in all_assets:
                purchase_date = asset.get("Purchase Date", "")
                if purchase_date:
                    try:
                        date = datetime.strptime(purchase_date, "%Y-%m-%d")
                        if date.year == year and quarter_start_month <= date.month <= quarter_end_month:
                            count += 1
                    except:
                        pass
            
            quarterly_chart_values.append(count)
        
        # Generate yearly data (last 5 years)
        yearly_chart_labels = []
        yearly_chart_values = []
        
        # Generate data for the last 5 years
        for i in range(4, -1, -1):
            year = current_year - i
            yearly_chart_labels.append(str(year))
            
            # Count assets added in this year
            count = 0
            for asset in all_assets:
                purchase_date = asset.get("Purchase Date", "")
                if purchase_date:
                    try:
                        date = datetime.strptime(purchase_date, "%Y-%m-%d")
                        if date.year == year:
                            count += 1
                    except:
                        pass
            
            yearly_chart_values.append(count)

        # Format age distribution - convert to list of tuples for proper serialization
        age_distribution = chart_data.get("age_distribution", {})
        age_distribution_list = [
            {"label": str(k), "value": int(v)} 
            for k, v in age_distribution.items()
        ]

        # Format latest assets (excluding disposed assets)
        latest_assets = sorted(
            active_assets, 
            key=lambda a: a.get("Purchase Date", ""), 
            reverse=True
        )[:10]
        
        # Process assets to ensure they have a display_name field
        for asset in latest_assets:
            # Try different possible field names for the asset name
            name_fields = ["Name", "Asset Name", "AssetName", "Item Name", "Description", "Item"]
            display_name = None
            
            for field in name_fields:
                if asset.get(field):
                    display_name = asset.get(field)
                    break
            
            # If no name found, use a default
            if not display_name:
                display_name = f"Asset #{asset.get('ID', 'Unknown')}"
                
            # Add the display_name to the asset
            asset["display_name"] = display_name
            
        # Debug: Print the first asset's keys to see what fields are available
        if latest_assets:
            logging.info(f"Asset keys: {list(latest_assets[0].keys())}")
            logging.info(f"Asset display name: {latest_assets[0].get('display_name', 'Not found')}")
            logging.info(f"Original asset name fields: {[latest_assets[0].get(f, 'None') for f in name_fields]}")

        context = {
            "request": request,
            "user": current_user,
            "total_assets": total_assets,
            "total_purchase_value": total_purchase_value,
            "total_book_value": total_book_value,
            "total_depreciation_value": total_depreciation_value,
            "disposed_count": disposed_count,
            "damaged_count": damaged_count,
            "relocated_count": relocated_count,
            "repaired_count": repaired_count,
            "to_be_disposed_count": to_be_disposed_count,
            "category_counts": category_counts,
            "location_counts": location_counts_dict,
            "monthly_chart_labels": monthly_chart_labels,
            "monthly_chart_values": monthly_chart_values,
            "quarterly_chart_labels": quarterly_chart_labels,
            "quarterly_chart_values": quarterly_chart_values,
            "yearly_chart_labels": yearly_chart_labels,
            "yearly_chart_values": yearly_chart_values,
            "age_distribution": age_distribution_list,
            "latest_assets": latest_assets
        }

        return templates.TemplateResponse("dashboard.html", context)

    except Exception as e:
        logging.error("Dashboard error: %s", e, exc_info=True)
        return templates.TemplateResponse("error.html", {
            "request": request,
            "user": current_user,
            "message": "Terjadi kesalahan saat memuat dashboard.",
        })
from fastapi import APIRouter, Request, Response, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from supabase import create_client, Client
from app.config import load_config
import logging

config = load_config()
supabase: Client = create_client(config.SUPABASE_URL, config.SUPABASE_ANON_KEY)

router = APIRouter(tags=["authentication"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/login", response_class=HTMLResponse)
@router.head("/login", response_class=HTMLResponse)
async def login_page(request: Request, next: str = None):
    return templates.TemplateResponse("login_logout.html", {"request": request, "next": next})

@router.post("/login", response_class=HTMLResponse)
async def login_form(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    next: str = Form(None)
):
    try:
        # Use service key client for admin operations
        from supabase import create_client
        admin_supabase = create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_KEY)
        
        response = admin_supabase.auth.sign_in_with_password({
            "email": email,
            "password": password
        })
        
        if not response.user:
            return templates.TemplateResponse(
                "login_logout.html",
                {"request": request, "error": "Invalid email or password", "next": next},
                status_code=401
            )
        
        # Get user profile
        profile_response = admin_supabase.table('profiles').select('*').eq('id', response.user.id).single().execute()
        if not profile_response.data or not profile_response.data.get('is_active'):
            return templates.TemplateResponse(
                "login_logout.html",
                {"request": request, "error": "Account is inactive", "next": next},
                status_code=401
            )
        
        redirect_url = next if next else "/"
        redirect_response = RedirectResponse(url=redirect_url, status_code=303)
        
        redirect_response.set_cookie(
            key="sb_access_token",
            value=response.session.access_token,
            httponly=True,
            max_age=3600,
            samesite="lax",
            secure=True,
            domain=".onrender.com"
        )
        
        return redirect_response
        
    except Exception as e:
        logging.error(f"Login error: {str(e)}")
        return templates.TemplateResponse(
            "login_logout.html",
            {"request": request, "error": "Login failed", "next": next},
            status_code=401
        )

@router.get("/auth/callback")
async def auth_callback(request: Request):
    return templates.TemplateResponse("auth_callback.html", {"request": request})

@router.get("/logout")
async def logout():
    try:
        supabase.auth.sign_out()
    except:
        pass
    
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(key="sb_access_token")
    return response
# app/routes/logs.py
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.database.models import Profile
from app.utils.auth import get_current_user
from app.utils.sheets import get_all_approvals

router = APIRouter(prefix="/logs", tags=["logs"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def logs_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """View approval logs based on user role."""
    all_approvals = get_all_approvals()
    
    # Filter based on user role
    if current_user.role.value == 'staff':
        # Staff can only see their own requests
        user_identifier = current_user.full_name or current_user.email
        approvals = [a for a in all_approvals if a.get('Submitted_By') == user_identifier]
    else:
        # Manager and admin can see all approvals
        approvals = all_approvals
    
    # Separate pending and completed
    pending_approvals = [a for a in approvals if a.get('Status') == 'Pending']
    completed_approvals = [a for a in approvals if a.get('Status') in ['Approved', 'Rejected']]
    
    return templates.TemplateResponse(
        "logs/index.html",
        {
            "request": request,
            "user": current_user,
            "pending_approvals": pending_approvals,
            "completed_approvals": completed_approvals
        }
    )
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
from fastapi import APIRouter, Depends, Request, Form, UploadFile, File, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from app.database.database import get_db
from app.database.models import Profile
from app.utils.auth import get_current_user
from app.utils.photo import resize_and_convert_image, upload_to_drive
from app.utils.flash import set_flash

router = APIRouter(tags=["profile"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/profile", response_class=HTMLResponse)
async def profile_page(
    request: Request,
    current_user = Depends(get_current_user)
):
    """User profile page."""
    return templates.TemplateResponse(
        "profile/view.html",
        {
            "request": request,
            "user": current_user
        }
    )

@router.get("/profile/edit", response_class=HTMLResponse)
async def edit_profile_page(
    request: Request,
    current_user = Depends(get_current_user)
):
    """Edit user profile page."""
    return templates.TemplateResponse(
        "profile/edit.html",
        {
            "request": request,
            "user": current_user
        }
    )

@router.post("/profile/edit")
async def update_profile(
    request: Request,
    full_name: str = Form(...),
    email: str = Form(...),
    photo: UploadFile = File(None),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Update user profile."""
    # Update basic info
    current_user.full_name = full_name
    current_user.email = email
    current_user.updated_at = datetime.now(timezone.utc)
    
    # Handle photo upload if provided
    if photo and photo.filename:
        try:
            # Process image
            contents = await photo.read()
            import io
            image_file = io.BytesIO(contents)
            processed_image = resize_and_convert_image(image_file)
            
            if processed_image:
                # Upload to Google Drive
                photo_url = upload_to_drive(
                    processed_image, 
                    photo.filename, 
                    f"profile_{current_user.email}"
                )
                if photo_url:
                    current_user.photo_url = photo_url
        except Exception as e:
            return templates.TemplateResponse(
                "profile/edit.html",
                {
                    "request": request,
                    "user": current_user,
                    "error": f"Error uploading photo: {str(e)}"
                },
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    # Save changes
    db.commit()
    
    # Redirect to profile page
    response = RedirectResponse(url="/profile", status_code=status.HTTP_303_SEE_OTHER)
    set_flash(response, "Profile updated successfully", "success")
    return response
# app/routes/relocation.py
from fastapi import APIRouter, Depends, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime
import json

from app.database.database import get_db
from app.database.models import Profile
from app.utils.auth import get_current_user
from app.utils.sheets import get_all_assets, get_dropdown_options, add_approval_request
from app.utils.flash import set_flash

router = APIRouter(prefix="/relocation", tags=["relocation"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def relocation_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Asset relocation page."""
    # Get assets and dropdown options
    all_assets = get_all_assets()
    dropdown_options = get_dropdown_options()
    
    return templates.TemplateResponse(
        "relocation/index.html",
        {
            "request": request,
            "user": current_user,
            "assets": all_assets,
            "dropdown_options": dropdown_options
        }
    )

@router.post("/relocate/{asset_id}")
async def relocate_asset(
    asset_id: str,
    request: Request,
    new_location: str = Form(...),
    new_room: str = Form(...),
    reason: str = Form(...),
    notes: str = Form(None),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Submit asset relocation request."""
    from app.utils.sheets import get_asset_by_id
    
    # Get asset data
    asset = get_asset_by_id(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    # Create relocation approval request
    relocation_data = {
        'new_location': new_location,
        'new_room': new_room,
        'current_location': asset.get('Location', ''),
        'current_room': asset.get('Room', ''),
        'reason': reason,
        'notes': notes or ''
    }
    
    approval_data = {
        'type': 'relocation',
        'asset_id': asset_id,
        'asset_name': asset.get('Item Name', ''),
        'submitted_by': current_user.full_name or current_user.email,
        'submitted_date': datetime.now().strftime('%Y-%m-%d'),
        'description': f"Relocate from {asset.get('Location', '')} - {asset.get('Room', '')} to {new_location} - {new_room}",
        'request_data': json.dumps(relocation_data, ensure_ascii=False)
    }
    
    approval_success = add_approval_request(approval_data)
    
    if approval_success:
        response = RedirectResponse(url="/relocation", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, f"Relocation request for {asset.get('Item Name', '')} submitted for approval", "success")
        return response
    else:
        response = RedirectResponse(url="/relocation", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, "Error submitting relocation request", "error")
        return response
# /app/app/routes/repair.py
from fastapi import APIRouter, Request, Depends
from starlette.templating import Jinja2Templates
from app.utils.auth import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.post("/action")
async def submit_repair_action(request: Request, current_user = Depends(get_current_user)):
    """Submit repair action - creates approval request for store, direct action for allocate"""
    from app.utils.sheets import add_repair_log, update_asset, add_approval_request
    from datetime import datetime
    
    try:
        # Get JSON data
        data = await request.json()
        action_type = data.get('action_type')  # 'store' or 'allocate'
        
        if action_type == 'store':
            # Store action requires approval - only create approval request
            approval_data = {
                'type': 'repair_action',
                'asset_id': data.get('asset_id'),
                'asset_name': data.get('asset_name'),
                'submitted_by': current_user.full_name or current_user.email,
                'submitted_date': datetime.now().strftime('%Y-%m-%d'),
                'description': f"Request to store asset: {data.get('description')}",
                'action': 'Store Asset'
            }
            
            approval_success = add_approval_request(approval_data)
            
            if approval_success:
                return {"status": "success", "message": "Store request submitted for admin approval"}
            else:
                return {"status": "error", "message": "Failed to submit approval request"}
        
        else:  # allocate - direct action
            # Add to Repair_Log sheet
            repair_data = {
                'asset_id': data.get('asset_id'),
                'asset_name': data.get('asset_name'),
                'repair_action': 'Allocate Asset',
                'action_type': action_type,
                'description': data.get('description', ''),
                'performed_by': current_user.full_name or current_user.email,
                'action_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'new_location': data.get('location', ''),
                'new_room': data.get('room', ''),
                'notes': data.get('notes', '')
            }
            
            # Add to repair log
            log_success = add_repair_log(repair_data)
            
            # Update asset from Under Repair to Active
            update_data = {
                'Status': 'Active',
                'Bisnis Unit': data.get('business_unit', ''),
                'Location': data.get('location', ''),
                'Room': data.get('room', '')
            }
            
            asset_success = update_asset(data.get('asset_id'), update_data)
            
            if log_success and asset_success:
                return {"status": "success", "message": "Asset allocated successfully and synced to Google Sheets"}
            else:
                return {"status": "error", "message": "Failed to sync with Google Sheets"}
            
    except Exception as e:
        return {"status": "error", "message": str(e)}
# app/routes/user_management.py
from fastapi import APIRouter, Depends, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.database.models import Profile, UserRole
from app.utils.auth import get_current_user, get_admin_user
from app.utils.flash import set_flash

router = APIRouter(prefix="/user_management", tags=["user_management"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def user_list(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """List all users (admin only)."""
    users = db.query(Profile).all()
    
    return templates.TemplateResponse(
        "user_management/list.html",
        {
            "request": request,
            "user": current_user,
            "users": users
        }
    )

@router.get("/create", response_class=HTMLResponse)
async def create_user_form(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Create user form (admin only)."""
    return templates.TemplateResponse(
        "user_management/create.html",
        {
            "request": request,
            "user": current_user
        }
    )

@router.post("/create")
async def create_user(
    request: Request,
    email: str = Form(...),
    full_name: str = Form(...),
    role: str = Form(...),
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Create new user (admin only)."""
    # Check if user exists
    existing_user = db.query(Profile).filter(Profile.email == email).first()
    if existing_user:
        return templates.TemplateResponse(
            "user_management/create.html",
            {
                "request": request,
                "user": current_user,
                "error": "Email already exists"
            }
        )
    
    # Create user profile (Supabase handles auth)
    new_user = Profile(
        email=email,
        full_name=full_name,
        role=getattr(UserRole, role.upper()),
        is_active=True
    )
    
    db.add(new_user)
    db.commit()
    
    response = RedirectResponse(url="/user_management", status_code=status.HTTP_303_SEE_OTHER)
    set_flash(response, f"User {email} created successfully", "success")
    return response

@router.post("/reset_password/{user_id}")
async def reset_password(
    user_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Reset user password to default (admin only)."""
    user = db.query(Profile).filter(Profile.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Password reset handled by Supabase
    default_password = f"{user.email.split('@')[0]}123"
    
    response = RedirectResponse(url="/user_management", status_code=status.HTTP_303_SEE_OTHER)
    set_flash(response, f"Password reset instructions sent to {user.email}", "success")
    return response

@router.post("/toggle_status/{user_id}")
async def toggle_user_status(
    user_id: str,
    request: Request,
    is_active: bool = Form(...),
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Toggle user active status (admin only)."""
    user = db.query(Profile).filter(Profile.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Update status
    user.is_active = is_active
    db.commit()
    
    status_text = "activated" if is_active else "deactivated"
    response = RedirectResponse(url="/user_management", status_code=status.HTTP_303_SEE_OTHER)
    set_flash(response, f"User {user.email} {status_text}", "success")
    return response
# app/routes/__init__.py

# Import all route modules to make them available from app.routes
from app.routes import (
    home,
    assets,
    asset_management,
    login,
    damage,
    health,
    offline,
    profile,
    repair,
    approvals,
    disposal,
    user_management,
    logs,
    relocation
)
# app/routes/approvals.py
from fastapi import APIRouter, Depends, Request, HTTPException, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.utils.auth import get_current_user
from app.utils.sheets import get_all_approvals, update_approval_status

router = APIRouter(prefix="/approvals", tags=["approvals"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def approvals_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Approvals page for admin and manager."""
    if current_user.role not in ['admin', 'manager']:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get all approvals from Google Sheets
    all_approvals = get_all_approvals()
    
    # Filter approvals based on user role
    if current_user.role == 'admin':
        # Admin sees all approvals except disposal and edit_asset
        approvals_data = [a for a in all_approvals if a.get('Type') not in ['disposal', 'edit_asset']]
    elif current_user.role == 'manager':
        # Manager sees disposal and edit_asset approvals
        approvals_data = [a for a in all_approvals if a.get('Type') in ['disposal', 'edit_asset']]
    else:
        approvals_data = []
    
    return templates.TemplateResponse(
        "approvals/list.html",
        {
            "request": request,
            "user": current_user,
            "approvals_data": approvals_data
        }
    )

@router.post("/approve/{approval_id}")
async def approve_request(
    approval_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Approve a request."""
    if current_user.role not in ['admin', 'manager']:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get approval details
    all_approvals = get_all_approvals()
    approval = next((a for a in all_approvals if str(a.get('ID')) == str(approval_id)), None)
    
    if not approval:
        return JSONResponse({"status": "error", "message": "Approval not found"})
    
    # Process approval based on type
    try:
        if approval.get('Type') == 'damage_report':
            # Update asset status to "Under Repair"
            from app.utils.sheets import update_asset
            success = update_asset(approval.get('Asset_ID'), {'Status': 'Under Repair'})
            if not success:
                return JSONResponse({"status": "error", "message": "Failed to update asset status"})
        
        elif approval.get('Type') == 'relocation':
            # Process relocation approval
            import json
            try:
                request_data_str = approval.get('Request_Data', '')
                if request_data_str:
                    relocation_data = json.loads(request_data_str)
                    update_data = {
                        'Location': relocation_data.get('new_location'),
                        'Room': relocation_data.get('new_room')
                    }
                    from app.utils.sheets import update_asset
                    success = update_asset(approval.get('Asset_ID'), update_data)
                    if not success:
                        return JSONResponse({"status": "error", "message": "Failed to relocate asset"})
            except Exception as e:
                return JSONResponse({"status": "error", "message": f"Error processing relocation: {str(e)}"})
            
        elif approval.get('Type') == 'edit_asset':
            # Process edit asset approval
            import json
            try:
                request_data_str = approval.get('Request_Data', '')
                if request_data_str:
                    edit_data = json.loads(request_data_str)
                    from app.utils.sheets import update_asset
                    success = update_asset(approval.get('Asset_ID'), edit_data)
                    if not success:
                        return JSONResponse({"status": "error", "message": "Failed to update asset"})
            except Exception as e:
                return JSONResponse({"status": "error", "message": f"Error processing edit: {str(e)}"})
        
        # Update approval status
        approval_update = {
            'Status': 'Approved',
            'Approved_By': current_user.full_name or current_user.email,
            'Approved_Date': __import__('datetime').datetime.now().strftime('%Y-%m-%d')
        }
        
        success = update_approval_status(approval_id, approval_update)
        
        if success:
            return JSONResponse({"status": "success", "message": "Request approved successfully"})
        else:
            return JSONResponse({"status": "error", "message": "Failed to update approval status"})
            
    except Exception as e:
        return JSONResponse({"status": "error", "message": f"Error processing approval: {str(e)}"})

@router.post("/reject/{approval_id}")
async def reject_request(
    approval_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Reject a request."""
    if current_user.role not in ['admin', 'manager']:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Update approval status
    approval_update = {
        'Status': 'Rejected',
        'Approved_By': current_user.full_name or current_user.email,
        'Approved_Date': __import__('datetime').datetime.now().strftime('%Y-%m-%d')
    }
    
    success = update_approval_status(approval_id, approval_update)
    
    if success:
        return JSONResponse({"status": "success", "message": "Request rejected"})
    else:
        return JSONResponse({"status": "error", "message": "Failed to update approval status"})
from fastapi import APIRouter, Request, Depends
from starlette.templating import Jinja2Templates
from app.utils.auth import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/assets")
async def assets_page(request: Request, current_user=Depends(get_current_user)):
    """Assets listing page with filtering and pagination"""
    from app.utils.sheets import get_all_assets
    
    # Ambil data asset dari Google Sheets
    all_assets = get_all_assets()
    
    # Filter hanya aset aktif (bukan Disposed)
    active_assets = [asset for asset in all_assets if asset.get("Status", "").lower() != "disposed"]
    
    return templates.TemplateResponse("assets.html", {
        "request": request,
        "user": current_user,
        "assets_data": active_assets
    })
# app/routes/asset_management.py
from fastapi import APIRouter, Depends, Request, Form, File, UploadFile, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import json
from datetime import datetime
import io

from app.database.database import get_db
from app.database.models import Profile, UserRole
from app.utils.photo import resize_and_convert_image, upload_to_drive
from app.utils.sheets import get_dropdown_options, add_asset as sheets_add_asset
from app.utils.flash import set_flash
from app.utils.auth import get_current_user, get_admin_user
from app.config import load_config

config = load_config()
router = APIRouter(prefix="/asset_management", tags=["asset_management"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/add", response_class=HTMLResponse)
async def add_asset_form(
    request: Request,
    db: Session = Depends(get_db),
    current_profile = Depends(get_current_user)
):
    """Form to add a new asset."""
    dropdown_options = get_dropdown_options()
    return templates.TemplateResponse(
        "asset_management/add.html",
        {
            "request": request,
            "user": current_profile,
            "dropdown_options": dropdown_options
        }
    )


@router.get("/list", response_class=HTMLResponse)
async def asset_list(
    request: Request,
    db: Session = Depends(get_db),
    current_profile = Depends(get_current_user)
):
    """List assets for editing (admin and manager only)."""
    if current_profile.role not in [UserRole.ADMIN, UserRole.MANAGER]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    from app.utils.sheets import get_all_assets
    assets = get_all_assets()
    
    locations = list(set(asset.get('Location', '') for asset in assets if asset.get('Location')))
    location_rooms = {}
    for asset in assets:
        location = asset.get('Location', '')
        room = asset.get('Room', '')
        if location and room:
            if location not in location_rooms:
                location_rooms[location] = set()
            location_rooms[location].add(room)
    
    for location in location_rooms:
        location_rooms[location] = list(location_rooms[location])
    
    return templates.TemplateResponse(
        "asset_management/list.html",
        {
            "request": request,
            "user": current_profile,
            "assets": assets,
            "locations": sorted(locations),
            "location_rooms": location_rooms
        }
    )


@router.get("/edit/{asset_id}", response_class=HTMLResponse)
async def edit_asset_form(
    asset_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_profile = Depends(get_current_user)
):
    """Form to edit an existing asset (admin/manager only)."""
    if current_profile.role not in [UserRole.ADMIN, UserRole.MANAGER]:
        raise HTTPException(status_code=403, detail="Access denied")

    from app.utils.sheets import get_asset_by_id
    asset = get_asset_by_id(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    dropdown_options = get_dropdown_options()
    
    return templates.TemplateResponse(
        "asset_management/edit.html",
        {
            "request": request,
            "user": current_profile,
            "asset": asset,
            "dropdown_options": dropdown_options
        }
    )


@router.post("/edit/{asset_id}")
async def update_asset(
    asset_id: str,
    request: Request,
    status: str = Form(...),
    company: str = Form(...),
    location: str = Form(...),
    room: str = Form(...),
    bisnis_unit: str = Form(None),
    edit_reason: str = Form(...),
    db: Session = Depends(get_db),
    current_profile = Depends(get_current_user)
):
    """Update existing asset (admin and manager only)."""
    if current_profile.role not in [UserRole.ADMIN, UserRole.MANAGER]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    from app.utils.sheets import update_asset as sheets_update_asset, calculate_asset_financials, get_asset_by_id
    asset = get_asset_by_id(asset_id)

    update_data = {
        "Status": status,
        "Company": company,
        "Location": location,
        "Room": room,
        "Bisnis Unit": bisnis_unit or ""
    }
    
    # Jika perlu hitung ulang nilai finansial, misalnya setelah perubahan harga
    # financials = calculate_asset_financials(purchase_cost, purchase_date, category)
    # update_data.update(financials)
    
    from app.utils.sheets import add_approval_request
    
    approval_data = {
        'type': 'edit_asset',
        'asset_id': asset_id,
        'asset_name': asset.get('Item Name', ''),
        'submitted_by': current_profile.full_name or current_profile.email,
        'submitted_date': datetime.now().strftime('%Y-%m-%d'),
        'description': f"Edit asset: {asset.get('Item Name', '')} - Reason: {edit_reason}",
        'edit_reason': edit_reason,
        'request_data': json.dumps(update_data, ensure_ascii=False)
    }
    
    approval_success = add_approval_request(approval_data)
    
    if approval_success:
        response = RedirectResponse(url="/asset_management/list", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, "Asset edit request submitted for manager approval", "success")
        return response
    else:
        dropdown_options = get_dropdown_options()
        return templates.TemplateResponse(
            "asset_management/edit.html",
            {
                "request": request,
                "user": current_profile,
                "asset": asset,
                "dropdown_options": dropdown_options,
                "error": "Error submitting edit request"
            },
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@router.post("/add")
async def add_asset(
    request: Request,
    item_name: str = Form(...),
    category: str = Form(...),
    type: str = Form(...),
    manufacture: str = Form(None),
    model: str = Form(None),
    serial_number: str = Form(None),
    company: str = Form(...),
    bisnis_unit: str = Form(None),
    location: str = Form(...),
    room: str = Form(...),
    notes: str = Form(None),
    item_condition: str = Form(None),
    purchase_date: str = Form(...),
    purchase_cost: str = Form(...),
    warranty: str = Form(None),
    supplier: str = Form(None),
    journal: str = Form(None),
    owner: str = Form(...),
    photo: UploadFile = File(None),
    db: Session = Depends(get_db),
    current_profile = Depends(get_current_user)
):
    """Process add asset form."""
    dropdown_options = get_dropdown_options()
    
    asset_data = {
        "Item Name": item_name,
        "Category": category,
        "Type": type,
        "Manufacture": manufacture or "",
        "Model": model or "",
        "Serial Number": serial_number or "",
        "Company": company,
        "Bisnis Unit": bisnis_unit or "",
        "Location": location,
        "Room": room,
        "Notes": notes or "",
        "Item Condition": item_condition or "",
        "Purchase Date": purchase_date,
        "Purchase Cost": purchase_cost,
        "Warranty": warranty or "",
        "Supplier": supplier or "",
        "Journal": journal or "",
        "Owner": owner,
        "Status": "Active"
    }
    
    photo_url = None
    if photo and photo.filename:
        try:
            contents = await photo.read()
            image_file = io.BytesIO(contents)
            processed_image = resize_and_convert_image(image_file)
            
            if processed_image:
                photo_url = upload_to_drive(processed_image, photo.filename, "new")
                if photo_url:
                    asset_data["Photo URL"] = photo_url
        except Exception as e:
            print(f"Error processing photo: {str(e)}")
    
    if current_profile.role == UserRole.ADMIN:
        success = sheets_add_asset(asset_data)
        
        if success:
            response = RedirectResponse(url="/assets/", status_code=status.HTTP_303_SEE_OTHER)
            set_flash(response, "Asset added successfully", "success")
            return response
        else:
            return templates.TemplateResponse(
                "asset_management/add.html",
                {
                    "request": request,
                    "user": current_profile,
                    "dropdown_options": dropdown_options,
                    "error": "Error adding asset to Google Sheets",
                    "form_data": asset_data
                },
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    from app.utils.sheets import add_approval_request
    
    approval_data = {
        'type': 'add_asset',
        'asset_id': 'NEW',
        'asset_name': item_name,
        'submitted_by': current_profile.full_name or current_profile.email,
        'submitted_date': datetime.now().strftime('%Y-%m-%d'),
        'description': f"Add new asset: {item_name}",
        'request_data': json.dumps(asset_data, ensure_ascii=False)
    }
    
    approval_success = add_approval_request(approval_data)
    
    if approval_success:
        response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, "Asset request submitted for approval", "success")
        return response
    else:
        return templates.TemplateResponse(
            "asset_management/add.html",
            {
                "request": request,
                "user": current_profile,
                "dropdown_options": dropdown_options,
                "error": "Error submitting approval request",
                "form_data": asset_data
            },
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
from fastapi import APIRouter, Request, Depends
from starlette.templating import Jinja2Templates
from app.utils.auth import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/")
async def damaged_assets_page(request: Request, current_user = Depends(get_current_user)):
    """Damaged assets page with search and log functionality"""
    from app.utils.sheets import get_all_assets, get_dropdown_options

    all_assets = get_all_assets()
    dropdown_options = get_dropdown_options()

    return templates.TemplateResponse("damaged_assets.html", {
        "request": request,
        "user": current_user,
        "assets_data": all_assets,
        "dropdown_options": dropdown_options
    })


@router.post("/lost")
async def submit_lost_report(request: Request, current_user = Depends(get_current_user)):
    """Submit lost report - syncs to Google Sheets"""
    from app.utils.sheets import add_lost_log, add_approval_request
    from datetime import datetime

    try:
        data = await request.json()

        lost_data = {
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'last_location': data.get('last_location'),
            'last_room': data.get('last_room', ''),
            'date_lost': data.get('date_lost'),
            'description': data.get('description'),
            'reported_by': current_user.full_name or current_user.email,
            'report_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'notes': data.get('notes', '')
        }

        log_success = add_lost_log(lost_data)

        approval_data = {
            'type': 'lost_report',
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'submitted_by': current_user.full_name or current_user.email,
            'submitted_date': datetime.now().strftime('%Y-%m-%d'),
            'description': f"Lost report: {data.get('description')}",
            'location': data.get('last_location')
        }

        approval_success = add_approval_request(approval_data)

        if log_success and approval_success:
            return {"status": "success", "message": "Lost report submitted and logged to Google Sheets"}
        else:
            return {"status": "error", "message": "Failed to sync with Google Sheets"}

    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/disposal")
async def submit_disposal_request(request: Request, current_user = Depends(get_current_user)):
    """Submit disposal request - syncs to Google Sheets"""
    from app.utils.sheets import add_disposal_log, add_approval_request
    from datetime import datetime

    try:
        data = await request.json()

        disposal_data = {
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'disposal_reason': data.get('disposal_reason'),
            'disposal_method': data.get('disposal_method', 'Standard'),
            'description': data.get('description'),
            'requested_by': current_user.full_name or current_user.email,
            'request_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'notes': data.get('notes', '')
        }

        log_success = add_disposal_log(disposal_data)

        approval_data = {
            'type': 'disposal_request',
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'submitted_by': current_user.full_name or current_user.email,
            'submitted_date': datetime.now().strftime('%Y-%m-%d'),
            'description': f"Disposal request: {data.get('description')}"
        }

        approval_success = add_approval_request(approval_data)

        if log_success and approval_success:
            return {"status": "success", "message": "Disposal request submitted and logged to Google Sheets"}
        else:
            return {"status": "error", "message": "Failed to sync with Google Sheets"}

    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/report")
async def submit_damage_report(request: Request, current_user = Depends(get_current_user)):
    """Submit damage report - syncs to Google Sheets"""
    from app.utils.sheets import add_damage_log, add_approval_request
    from datetime import datetime

    try:
        data = await request.json()

        damage_data = {
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'damage_type': data.get('damage_type'),
            'severity': data.get('severity'),
            'description': data.get('damage_description'),
            'reported_by': current_user.full_name or current_user.email,
            'report_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'location': data.get('location', ''),
            'room': data.get('room', ''),
            'notes': data.get('notes', '')
        }

        approval_data = {
            'type': 'damage_report',
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'submitted_by': current_user.full_name or current_user.email,
            'submitted_date': datetime.now().strftime('%Y-%m-%d'),
            'description': f"Damage report: {data.get('damage_description')}",
            'damage_type': data.get('damage_type'),
            'severity': data.get('severity')
        }

        approval_success = add_approval_request(approval_data)

        if approval_success:
            return {"status": "success", "message": "Damage report submitted for approval"}
        else:
            return {"status": "error", "message": "Failed to submit approval request"}

    except Exception as e:
        return {"status": "error", "message": str(e)}
# app/routes/disposal.py
from fastapi import APIRouter, Depends, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime

from app.database.database import get_db
from app.database.models import Profile
from app.utils.auth import get_admin_user
from app.utils.sheets import get_all_assets, update_asset, add_disposal_log
from app.utils.flash import set_flash

router = APIRouter(prefix="/disposal", tags=["disposal"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def disposal_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Disposal assets page (admin only)."""
    # Get assets that are ready to dispose only
    all_assets = get_all_assets()
    # Debug: check all statuses
    statuses = [str(asset.get('Status', '')).strip() for asset in all_assets]
    print(f"All statuses found: {set(statuses)}")
    
    disposable_assets = []
    for asset in all_assets:
        status = str(asset.get('Status', '')).strip()
        if status in ['To Be Disposed', 'To be Disposed', 'TO BE DISPOSED']:
            disposable_assets.append(asset)
    
    return templates.TemplateResponse(
        "disposal/index.html",
        {
            "request": request,
            "user": current_user,
            "assets": disposable_assets
        }
    )

@router.post("/dispose/{asset_id}")
async def dispose_asset(
    asset_id: str,
    request: Request,
    disposal_reason: str = Form(...),
    disposal_method: str = Form(...),
    description: str = Form(None),
    notes: str = Form(None),
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Dispose an asset (admin only)."""
    from app.utils.sheets import get_asset_by_id
    
    # Get asset data
    asset = get_asset_by_id(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    if str(asset.get('Status', '')).strip() != 'To Be Disposed':
        raise HTTPException(status_code=400, detail="Asset must be marked 'To Be Disposed' first")
    
    # Create disposal approval request
    from app.utils.sheets import add_approval_request
    
    approval_data = {
        'type': 'disposal',
        'asset_id': asset_id,
        'asset_name': asset.get('Item Name', ''),
        'submitted_by': current_user.full_name or current_user.email,
        'submitted_date': datetime.now().strftime('%Y-%m-%d'),
        'description': f"Disposal request: {disposal_reason} - {disposal_method}",
        'disposal_reason': disposal_reason,
        'disposal_method': disposal_method,
        'notes': f"Description: {description or ''} | Notes: {notes or ''}"
    }
    
    approval_success = add_approval_request(approval_data)
    
    if approval_success:
        response = RedirectResponse(url="/disposal", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, f"Disposal request for {asset.get('Item Name', '')} submitted for manager approval", "success")
        return response
    else:
        response = RedirectResponse(url="/disposal", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, "Error submitting disposal request", "error")
        return response
# app/routes/health.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
import time

from app.database.database import get_db
from app.config import load_config

router = APIRouter(tags=["health"])
config = load_config()

@router.get("/health")
async def health_check(db: Session = Depends(get_db)):
    """Health check endpoint."""
    start_time = time.time()
    
    # Check database connection
    try:
        db.execute(text("SELECT 1"))
        db_status = "healthy"
    except Exception as e:
        db_status = f"unhealthy: {str(e)}"
    
    # Check Google Sheets API
    sheets_status = "configured" if config.GOOGLE_SHEET_ID else "not configured"
    
    # Response time
    response_time = time.time() - start_time
    
    return {
        "status": "ok",
        "database": db_status,
        "google_sheets": sheets_status,
        "response_time_ms": round(response_time * 1000, 2)
    }
# /app/app/routes/home.py
import logging
from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse
from starlette.templating import Jinja2Templates
from app.utils.auth import get_current_user
from app.utils.sheets import get_summary_data, get_chart_data, get_all_assets

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=RedirectResponse)
async def redirect_root():
    return RedirectResponse("/dashboard")

@router.get("/dashboard")
async def home(request: Request, current_user = Depends(get_current_user)):
    try:
        # Summary and chart data
        summary_data = get_summary_data()
        chart_data = get_chart_data()
        all_assets = get_all_assets()

        # Filter out disposed assets for dashboard counts
        active_assets = [asset for asset in all_assets if asset.get("Status", "") != "Disposed"]
        disposed_assets = [asset for asset in all_assets if asset.get("Status", "") == "Disposed"]
        
        # Count assets by status and activity
        total_assets = len(active_assets)
        disposed_count = len(disposed_assets)
        damaged_count = len([a for a in all_assets if a.get("Status", "") == "Under Repair"])
        
        # Count assets by activity type
        relocated_count = len([a for a in all_assets if a.get("Last Activity", "") == "Relocated"])
        repaired_count = len([a for a in all_assets if a.get("Last Activity", "") == "Repaired"])
        to_be_disposed_count = len([a for a in all_assets if a.get("Status", "") == "To Be Disposed"])
        
        # Helper function to safely convert values to float
        def safe_float(value):
            if value is None or value == '':
                return 0.0
            try:
                return float(value)
            except (ValueError, TypeError):
                return 0.0
        
        # Calculate financial values directly from assets
        total_purchase_value = sum(safe_float(asset.get("Purchase Cost")) for asset in active_assets)
        total_book_value = sum(safe_float(asset.get("Book Value")) for asset in active_assets)
        # Calculate depreciation as purchase value minus book value
        total_depreciation_value = total_purchase_value - total_book_value
        category_counts = chart_data.get("category_counts", {})
        
        # Format location data
        location_data = chart_data.get("location_chart_data", {})
        location_counts = location_data.get("labels", [])
        location_values = location_data.get("values", [])
        location_counts_dict = dict(zip(location_counts, location_values))

        # Format time-based chart data
        monthly_data = chart_data.get("monthly_chart_data", {})
        monthly_chart_labels = monthly_data.get("labels", [])
        monthly_chart_values = monthly_data.get("values", [])
        
        # Generate quarterly data (last 12 quarters - 3 years)
        quarterly_chart_labels = []
        quarterly_chart_values = []
        
        # Get current year and quarter
        from datetime import datetime
        current_date = datetime.now()
        current_year = current_date.year
        current_quarter = (current_date.month - 1) // 3 + 1
        
        # Generate data for the last 12 quarters
        for i in range(11, -1, -1):
            year = current_year
            quarter = current_quarter - i
            
            # Adjust year if quarter is negative or > 4
            while quarter <= 0:
                year -= 1
                quarter += 4
            while quarter > 4:
                year += 1
                quarter -= 4
                
            quarterly_chart_labels.append(f"Q{quarter} {year}")
            
            # Count assets added in this quarter
            quarter_start_month = (quarter - 1) * 3 + 1
            quarter_end_month = quarter * 3
            
            count = 0
            for asset in all_assets:
                purchase_date = asset.get("Purchase Date", "")
                if purchase_date:
                    try:
                        date = datetime.strptime(purchase_date, "%Y-%m-%d")
                        if date.year == year and quarter_start_month <= date.month <= quarter_end_month:
                            count += 1
                    except:
                        pass
            
            quarterly_chart_values.append(count)
        
        # Generate yearly data (last 5 years)
        yearly_chart_labels = []
        yearly_chart_values = []
        
        # Generate data for the last 5 years
        for i in range(4, -1, -1):
            year = current_year - i
            yearly_chart_labels.append(str(year))
            
            # Count assets added in this year
            count = 0
            for asset in all_assets:
                purchase_date = asset.get("Purchase Date", "")
                if purchase_date:
                    try:
                        date = datetime.strptime(purchase_date, "%Y-%m-%d")
                        if date.year == year:
                            count += 1
                    except:
                        pass
            
            yearly_chart_values.append(count)

        # Format age distribution - convert to list of tuples for proper serialization
        age_distribution = chart_data.get("age_distribution", {})
        age_distribution_list = [
            {"label": str(k), "value": int(v)} 
            for k, v in age_distribution.items()
        ]

        # Format latest assets (excluding disposed assets)
        latest_assets = sorted(
            active_assets, 
            key=lambda a: a.get("Purchase Date", ""), 
            reverse=True
        )[:10]
        
        # Process assets to ensure they have a display_name field
        for asset in latest_assets:
            # Try different possible field names for the asset name
            name_fields = ["Name", "Asset Name", "AssetName", "Item Name", "Description", "Item"]
            display_name = None
            
            for field in name_fields:
                if asset.get(field):
                    display_name = asset.get(field)
                    break
            
            # If no name found, use a default
            if not display_name:
                display_name = f"Asset #{asset.get('ID', 'Unknown')}"
                
            # Add the display_name to the asset
            asset["display_name"] = display_name
            
        # Debug: Print the first asset's keys to see what fields are available
        if latest_assets:
            logging.info(f"Asset keys: {list(latest_assets[0].keys())}")
            logging.info(f"Asset display name: {latest_assets[0].get('display_name', 'Not found')}")
            logging.info(f"Original asset name fields: {[latest_assets[0].get(f, 'None') for f in name_fields]}")

        context = {
            "request": request,
            "user": current_user,
            "total_assets": total_assets,
            "total_purchase_value": total_purchase_value,
            "total_book_value": total_book_value,
            "total_depreciation_value": total_depreciation_value,
            "disposed_count": disposed_count,
            "damaged_count": damaged_count,
            "relocated_count": relocated_count,
            "repaired_count": repaired_count,
            "to_be_disposed_count": to_be_disposed_count,
            "category_counts": category_counts,
            "location_counts": location_counts_dict,
            "monthly_chart_labels": monthly_chart_labels,
            "monthly_chart_values": monthly_chart_values,
            "quarterly_chart_labels": quarterly_chart_labels,
            "quarterly_chart_values": quarterly_chart_values,
            "yearly_chart_labels": yearly_chart_labels,
            "yearly_chart_values": yearly_chart_values,
            "age_distribution": age_distribution_list,
            "latest_assets": latest_assets
        }

        return templates.TemplateResponse("dashboard.html", context)

    except Exception as e:
        logging.error("Dashboard error: %s", e, exc_info=True)
        return templates.TemplateResponse("error.html", {
            "request": request,
            "user": current_user,
            "message": "Terjadi kesalahan saat memuat dashboard.",
        })
from fastapi import APIRouter, Request, Response, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from supabase import create_client, Client
from app.config import load_config
import logging

config = load_config()
supabase: Client = create_client(config.SUPABASE_URL, config.SUPABASE_ANON_KEY)

router = APIRouter(tags=["authentication"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/login", response_class=HTMLResponse)
@router.head("/login", response_class=HTMLResponse)
async def login_page(request: Request, next: str = None):
    return templates.TemplateResponse("login_logout.html", {"request": request, "next": next})

@router.post("/login", response_class=HTMLResponse)
async def login_form(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    next: str = Form(None)
):
    try:
        # Use service key client for admin operations
        from supabase import create_client
        admin_supabase = create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_KEY)
        
        response = admin_supabase.auth.sign_in_with_password({
            "email": email,
            "password": password
        })
        
        if not response.user:
            return templates.TemplateResponse(
                "login_logout.html",
                {"request": request, "error": "Invalid email or password", "next": next},
                status_code=401
            )
        
        # Get user profile
        profile_response = admin_supabase.table('profiles').select('*').eq('id', response.user.id).single().execute()
        if not profile_response.data or not profile_response.data.get('is_active'):
            return templates.TemplateResponse(
                "login_logout.html",
                {"request": request, "error": "Account is inactive", "next": next},
                status_code=401
            )
        
        redirect_url = next if next else "/"
        redirect_response = RedirectResponse(url=redirect_url, status_code=303)
        
        redirect_response.set_cookie(
            key="sb_access_token",
            value=response.session.access_token,
            httponly=True,
            max_age=3600,
            samesite="lax",
            secure=True,
            domain=".onrender.com"
        )
        
        return redirect_response
        
    except Exception as e:
        logging.error(f"Login error: {str(e)}")
        return templates.TemplateResponse(
            "login_logout.html",
            {"request": request, "error": "Login failed", "next": next},
            status_code=401
        )

@router.get("/auth/callback")
async def auth_callback(request: Request):
    return templates.TemplateResponse("auth_callback.html", {"request": request})

@router.get("/logout")
async def logout():
    try:
        supabase.auth.sign_out()
    except:
        pass
    
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(key="sb_access_token")
    return response
# app/routes/logs.py
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.database.models import Profile
from app.utils.auth import get_current_user
from app.utils.sheets import get_all_approvals

router = APIRouter(prefix="/logs", tags=["logs"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def logs_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """View approval logs based on user role."""
    all_approvals = get_all_approvals()
    
    # Filter based on user role
    if current_user.role.value == 'staff':
        # Staff can only see their own requests
        user_identifier = current_user.full_name or current_user.email
        approvals = [a for a in all_approvals if a.get('Submitted_By') == user_identifier]
    else:
        # Manager and admin can see all approvals
        approvals = all_approvals
    
    # Separate pending and completed
    pending_approvals = [a for a in approvals if a.get('Status') == 'Pending']
    completed_approvals = [a for a in approvals if a.get('Status') in ['Approved', 'Rejected']]
    
    return templates.TemplateResponse(
        "logs/index.html",
        {
            "request": request,
            "user": current_user,
            "pending_approvals": pending_approvals,
            "completed_approvals": completed_approvals
        }
    )
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
from fastapi import APIRouter, Depends, Request, Form, UploadFile, File, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from app.database.database import get_db
from app.database.models import Profile
from app.utils.auth import get_current_user
from app.utils.photo import resize_and_convert_image, upload_to_drive
from app.utils.flash import set_flash

router = APIRouter(tags=["profile"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/profile", response_class=HTMLResponse)
async def profile_page(
    request: Request,
    current_user = Depends(get_current_user)
):
    """User profile page."""
    return templates.TemplateResponse(
        "profile/view.html",
        {
            "request": request,
            "user": current_user
        }
    )

@router.get("/profile/edit", response_class=HTMLResponse)
async def edit_profile_page(
    request: Request,
    current_user = Depends(get_current_user)
):
    """Edit user profile page."""
    return templates.TemplateResponse(
        "profile/edit.html",
        {
            "request": request,
            "user": current_user
        }
    )

@router.post("/profile/edit")
async def update_profile(
    request: Request,
    full_name: str = Form(...),
    email: str = Form(...),
    photo: UploadFile = File(None),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Update user profile."""
    # Update basic info
    current_user.full_name = full_name
    current_user.email = email
    current_user.updated_at = datetime.now(timezone.utc)
    
    # Handle photo upload if provided
    if photo and photo.filename:
        try:
            # Process image
            contents = await photo.read()
            import io
            image_file = io.BytesIO(contents)
            processed_image = resize_and_convert_image(image_file)
            
            if processed_image:
                # Upload to Google Drive
                photo_url = upload_to_drive(
                    processed_image, 
                    photo.filename, 
                    f"profile_{current_user.email}"
                )
                if photo_url:
                    current_user.photo_url = photo_url
        except Exception as e:
            return templates.TemplateResponse(
                "profile/edit.html",
                {
                    "request": request,
                    "user": current_user,
                    "error": f"Error uploading photo: {str(e)}"
                },
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    # Save changes
    db.commit()
    
    # Redirect to profile page
    response = RedirectResponse(url="/profile", status_code=status.HTTP_303_SEE_OTHER)
    set_flash(response, "Profile updated successfully", "success")
    return response
# app/routes/relocation.py
from fastapi import APIRouter, Depends, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime
import json

from app.database.database import get_db
from app.database.models import Profile
from app.utils.auth import get_current_user
from app.utils.sheets import get_all_assets, get_dropdown_options, add_approval_request
from app.utils.flash import set_flash

router = APIRouter(prefix="/relocation", tags=["relocation"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def relocation_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Asset relocation page."""
    # Get assets and dropdown options
    all_assets = get_all_assets()
    dropdown_options = get_dropdown_options()
    
    return templates.TemplateResponse(
        "relocation/index.html",
        {
            "request": request,
            "user": current_user,
            "assets": all_assets,
            "dropdown_options": dropdown_options
        }
    )

@router.post("/relocate/{asset_id}")
async def relocate_asset(
    asset_id: str,
    request: Request,
    new_location: str = Form(...),
    new_room: str = Form(...),
    reason: str = Form(...),
    notes: str = Form(None),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Submit asset relocation request."""
    from app.utils.sheets import get_asset_by_id
    
    # Get asset data
    asset = get_asset_by_id(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    # Create relocation approval request
    relocation_data = {
        'new_location': new_location,
        'new_room': new_room,
        'current_location': asset.get('Location', ''),
        'current_room': asset.get('Room', ''),
        'reason': reason,
        'notes': notes or ''
    }
    
    approval_data = {
        'type': 'relocation',
        'asset_id': asset_id,
        'asset_name': asset.get('Item Name', ''),
        'submitted_by': current_user.full_name or current_user.email,
        'submitted_date': datetime.now().strftime('%Y-%m-%d'),
        'description': f"Relocate from {asset.get('Location', '')} - {asset.get('Room', '')} to {new_location} - {new_room}",
        'request_data': json.dumps(relocation_data, ensure_ascii=False)
    }
    
    approval_success = add_approval_request(approval_data)
    
    if approval_success:
        response = RedirectResponse(url="/relocation", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, f"Relocation request for {asset.get('Item Name', '')} submitted for approval", "success")
        return response
    else:
        response = RedirectResponse(url="/relocation", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, "Error submitting relocation request", "error")
        return response
# /app/app/routes/repair.py
from fastapi import APIRouter, Request, Depends
from starlette.templating import Jinja2Templates
from app.utils.auth import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.post("/action")
async def submit_repair_action(request: Request, current_user = Depends(get_current_user)):
    """Submit repair action - creates approval request for store, direct action for allocate"""
    from app.utils.sheets import add_repair_log, update_asset, add_approval_request
    from datetime import datetime
    
    try:
        # Get JSON data
        data = await request.json()
        action_type = data.get('action_type')  # 'store' or 'allocate'
        
        if action_type == 'store':
            # Store action requires approval - only create approval request
            approval_data = {
                'type': 'repair_action',
                'asset_id': data.get('asset_id'),
                'asset_name': data.get('asset_name'),
                'submitted_by': current_user.full_name or current_user.email,
                'submitted_date': datetime.now().strftime('%Y-%m-%d'),
                'description': f"Request to store asset: {data.get('description')}",
                'action': 'Store Asset'
            }
            
            approval_success = add_approval_request(approval_data)
            
            if approval_success:
                return {"status": "success", "message": "Store request submitted for admin approval"}
            else:
                return {"status": "error", "message": "Failed to submit approval request"}
        
        else:  # allocate - direct action
            # Add to Repair_Log sheet
            repair_data = {
                'asset_id': data.get('asset_id'),
                'asset_name': data.get('asset_name'),
                'repair_action': 'Allocate Asset',
                'action_type': action_type,
                'description': data.get('description', ''),
                'performed_by': current_user.full_name or current_user.email,
                'action_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'new_location': data.get('location', ''),
                'new_room': data.get('room', ''),
                'notes': data.get('notes', '')
            }
            
            # Add to repair log
            log_success = add_repair_log(repair_data)
            
            # Update asset from Under Repair to Active
            update_data = {
                'Status': 'Active',
                'Bisnis Unit': data.get('business_unit', ''),
                'Location': data.get('location', ''),
                'Room': data.get('room', '')
            }
            
            asset_success = update_asset(data.get('asset_id'), update_data)
            
            if log_success and asset_success:
                return {"status": "success", "message": "Asset allocated successfully and synced to Google Sheets"}
            else:
                return {"status": "error", "message": "Failed to sync with Google Sheets"}
            
    except Exception as e:
        return {"status": "error", "message": str(e)}
# app/routes/user_management.py
from fastapi import APIRouter, Depends, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.database.models import Profile, UserRole
from app.utils.auth import get_current_user, get_admin_user
from app.utils.flash import set_flash

router = APIRouter(prefix="/user_management", tags=["user_management"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def user_list(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """List all users (admin only)."""
    users = db.query(Profile).all()
    
    return templates.TemplateResponse(
        "user_management/list.html",
        {
            "request": request,
            "user": current_user,
            "users": users
        }
    )

@router.get("/create", response_class=HTMLResponse)
async def create_user_form(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Create user form (admin only)."""
    return templates.TemplateResponse(
        "user_management/create.html",
        {
            "request": request,
            "user": current_user
        }
    )

@router.post("/create")
async def create_user(
    request: Request,
    email: str = Form(...),
    full_name: str = Form(...),
    role: str = Form(...),
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Create new user (admin only)."""
    # Check if user exists
    existing_user = db.query(Profile).filter(Profile.email == email).first()
    if existing_user:
        return templates.TemplateResponse(
            "user_management/create.html",
            {
                "request": request,
                "user": current_user,
                "error": "Email already exists"
            }
        )
    
    # Create user profile (Supabase handles auth)
    new_user = Profile(
        email=email,
        full_name=full_name,
        role=getattr(UserRole, role.upper()),
        is_active=True
    )
    
    db.add(new_user)
    db.commit()
    
    response = RedirectResponse(url="/user_management", status_code=status.HTTP_303_SEE_OTHER)
    set_flash(response, f"User {email} created successfully", "success")
    return response

@router.post("/reset_password/{user_id}")
async def reset_password(
    user_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Reset user password to default (admin only)."""
    user = db.query(Profile).filter(Profile.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Password reset handled by Supabase
    default_password = f"{user.email.split('@')[0]}123"
    
    response = RedirectResponse(url="/user_management", status_code=status.HTTP_303_SEE_OTHER)
    set_flash(response, f"Password reset instructions sent to {user.email}", "success")
    return response

@router.post("/toggle_status/{user_id}")
async def toggle_user_status(
    user_id: str,
    request: Request,
    is_active: bool = Form(...),
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Toggle user active status (admin only)."""
    user = db.query(Profile).filter(Profile.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Update status
    user.is_active = is_active
    db.commit()
    
    status_text = "activated" if is_active else "deactivated"
    response = RedirectResponse(url="/user_management", status_code=status.HTTP_303_SEE_OTHER)
    set_flash(response, f"User {user.email} {status_text}", "success")
    return response
# app/routes/__init__.py

# Import all route modules to make them available from app.routes
from app.routes import (
    home,
    assets,
    asset_management,
    login,
    damage,
    health,
    offline,
    profile,
    repair,
    approvals,
    disposal,
    user_management,
    logs,
    relocation
)
