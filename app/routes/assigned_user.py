from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from app.utils.auth import get_current_profile
from app.utils.database_manager import (
    get_assigned_users, get_assigned_user_by_id, add_assigned_user,
    update_assigned_user, delete_assigned_user, get_dropdown_options
)
from app.utils.device_detector import get_template
import logging

router = APIRouter(prefix="/assigned-users", tags=["assigned_users"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/")
async def assigned_users_list(request: Request, current_profile = Depends(get_current_profile)):
    """List all assigned users (admin only)"""
    if current_profile.role != "admin":
        return RedirectResponse("/", status_code=303)
    
    try:
        users = get_assigned_users()
        dropdown_options = get_dropdown_options()
        
        template_path = get_template(request, "assigned_user/list.html")
        return templates.TemplateResponse(template_path, {
            "request": request,
            "user": current_profile,
            "users": users,
            "companies": dropdown_options.get("companies", []),
            "business_units": dropdown_options.get("business_units", [])
        })
    except Exception as e:
        logging.error(f"Error loading assigned users: {str(e)}")
        template_path = get_template(request, "assigned_user/list.html")
        return templates.TemplateResponse(template_path, {
            "request": request,
            "user": current_profile,
            "users": [],
            "error": "Error loading assigned users"
        })

@router.get("/add")
@router.get("/form")
async def add_assigned_user_page(request: Request, current_profile = Depends(get_current_profile)):
    """Display add assigned user form"""
    if current_profile.role != "admin":
        return RedirectResponse("/", status_code=303)
    
    dropdown_options = get_dropdown_options()
    template_path = get_template(request, "assigned_user/form.html")
    return templates.TemplateResponse(template_path, {
        "request": request,
        "user": current_profile,
        "companies": dropdown_options.get("companies", []),
        "business_units": dropdown_options.get("business_units", []),
        "mode": "add"
    })

@router.post("/add")
async def add_assigned_user_submit(
    request: Request,
    current_profile = Depends(get_current_profile),
    assigned_user_name: str = Form(...),
    email: str = Form(None),
    phone: str = Form(None),
    company_name: str = Form(None),
    business_unit_name: str = Form(None),
    status: str = Form("active")
):
    """Add new assigned user"""
    if current_profile.role != "admin":
        return RedirectResponse("/", status_code=303)
    
    try:
        from app.utils.database_manager import get_supabase
        supabase = get_supabase()
        
        # Resolve company_name to company_id
        company_id = None
        if company_name:
            comp_response = supabase.table('ref_companies').select('company_id').eq('company_name', company_name).execute()
            if comp_response.data:
                company_id = comp_response.data[0]['company_id']
        
        # Resolve business_unit_name to business_unit_id
        business_unit_id = None
        if business_unit_name:
            unit_response = supabase.table('ref_business_units').select('business_unit_id').eq('business_unit_name', business_unit_name).execute()
            if unit_response.data:
                business_unit_id = unit_response.data[0]['business_unit_id']
        
        user_data = {
            "assigned_user_name": assigned_user_name,
            "email": email,
            "phone": phone,
            "company_id": company_id,
            "business_unit_id": business_unit_id,
            "status": status
        }
        
        add_assigned_user(user_data)
        logging.info(f"Assigned user added: {assigned_user_name}")
        return RedirectResponse("/assigned-users?success=User+added+successfully", status_code=303)
    except Exception as e:
        logging.error(f"Error adding assigned user: {str(e)}")
        dropdown_options = get_dropdown_options()
        template_path = get_template(request, "assigned_user/form.html")
        return templates.TemplateResponse(template_path, {
            "request": request,
            "user": current_profile,
            "companies": dropdown_options.get("companies", []),
            "business_units": dropdown_options.get("business_units", []),
            "mode": "add",
            "error": str(e)
        })

@router.get("/edit/{assigned_user_id}")
async def edit_assigned_user_page(
    request: Request,
    assigned_user_id: str,
    current_profile = Depends(get_current_profile)
):
    """Display edit assigned user form"""
    if current_profile.role != "admin":
        return RedirectResponse("/", status_code=303)
    
    try:
        user = get_assigned_user_by_id(assigned_user_id)
        if not user:
            return RedirectResponse("/assigned-users?error=User+not+found", status_code=303)
        
        dropdown_options = get_dropdown_options()
        template_path = get_template(request, "assigned_user/form.html")
        return templates.TemplateResponse(template_path, {
            "request": request,
            "user": current_profile,
            "users": [user],
            "companies": dropdown_options.get("companies", []),
            "business_units": dropdown_options.get("business_units", []),
            "mode": "edit"
        })
    except Exception as e:
        logging.error(f"Error loading assigned user: {str(e)}")
        return RedirectResponse("/assigned-users?error=Error+loading+user", status_code=303)

@router.post("/edit/{assigned_user_id}")
async def edit_assigned_user_submit(
    request: Request,
    assigned_user_id: str,
    current_profile = Depends(get_current_profile),
    assigned_user_name: str = Form(...),
    email: str = Form(None),
    phone: str = Form(None),
    company_name: str = Form(None),
    business_unit_name: str = Form(None),
    status: str = Form("active")
):
    """Update assigned user"""
    if current_profile.role != "admin":
        return RedirectResponse("/", status_code=303)
    
    try:
        from app.utils.database_manager import get_supabase
        supabase = get_supabase()
        
        # Resolve company_name to company_id
        company_id = None
        if company_name:
            comp_response = supabase.table('ref_companies').select('company_id').eq('company_name', company_name).execute()
            if comp_response.data:
                company_id = comp_response.data[0]['company_id']
        
        # Resolve business_unit_name to business_unit_id
        business_unit_id = None
        if business_unit_name:
            unit_response = supabase.table('ref_business_units').select('business_unit_id').eq('business_unit_name', business_unit_name).execute()
            if unit_response.data:
                business_unit_id = unit_response.data[0]['business_unit_id']
        
        user_data = {
            "assigned_user_name": assigned_user_name,
            "email": email,
            "phone": phone,
            "company_id": company_id,
            "business_unit_id": business_unit_id,
            "status": status
        }
        
        update_assigned_user(assigned_user_id, user_data)
        logging.info(f"Assigned user updated: {assigned_user_name}")
        return RedirectResponse("/assigned-users?success=User+updated+successfully", status_code=303)
    except Exception as e:
        logging.error(f"Error updating assigned user: {str(e)}")
        dropdown_options = get_dropdown_options()
        user = get_assigned_user_by_id(assigned_user_id)
        template_path = get_template(request, "assigned_user/form.html")
        return templates.TemplateResponse(template_path, {
            "request": request,
            "user": current_profile,
            "users": [user],
            "companies": dropdown_options.get("companies", []),
            "business_units": dropdown_options.get("business_units", []),
            "mode": "edit",
            "error": str(e)
        })

@router.post("/delete/{assigned_user_id}")
async def delete_assigned_user_submit(
    request: Request,
    assigned_user_id: str,
    current_profile = Depends(get_current_profile)
):
    """Delete assigned user"""
    if current_profile.role != "admin":
        return RedirectResponse("/", status_code=303)
    
    try:
        delete_assigned_user(assigned_user_id)
        logging.info(f"Assigned user deleted: {assigned_user_id}")
        return RedirectResponse("/assigned-users?success=User+deleted+successfully", status_code=303)
    except Exception as e:
        logging.error(f"Error deleting assigned user: {str(e)}")
        return RedirectResponse("/assigned-users?error=Error+deleting+user", status_code=303)
