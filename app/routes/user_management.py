# app/routes/user_management.py
from fastapi import APIRouter, Depends, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from supabase import create_client
from app.config import load_config
from app.database.models import UserRole
from app.utils.auth import get_current_profile, get_admin_user
from app.utils.flash import set_flash
from app.utils.database_manager import get_dropdown_options
import logging

router = APIRouter(prefix="/user_management", tags=["user_management"])
templates = Jinja2Templates(directory="app/templates")

config = load_config()
supabase = create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_KEY)

@router.get("/", response_class=HTMLResponse)
async def user_list(
    request: Request,
    current_profile = Depends(get_admin_user)
):
    """List all users (admin only)."""
    try:
        response = supabase.table("profiles").select("""
            id, username, full_name, role, is_active, created_at, updated_at,
            photo_url, business_unit_id, last_login_at, email_verified, business_unit_name,
            ref_business_units(business_unit_name)
        """).execute()
        users = response.data or []
        
        # Ensure business_unit_name is populated from relationship if missing
        for user in users:
            if not user.get('business_unit_name') and user.get('ref_business_units'):
                user['business_unit_name'] = user['ref_business_units']['business_unit_name']
        
        return templates.TemplateResponse(
            "user_management/list.html",
            {
                "request": request,
                "user": current_profile,
                "users": users
            }
        )
    except Exception as e:
        logging.error(f"Failed to get users: {e}")
        return templates.TemplateResponse(
            "user_management/list.html",
            {
                "request": request,
                "user": current_profile,
                "users": [],
                "error": "Failed to load users"
            }
        )

@router.get("/create", response_class=HTMLResponse)
async def create_user_form(
    request: Request,
    current_profile = Depends(get_admin_user)
):
    """Create user form (admin only)."""
    dropdown_options = get_dropdown_options()
    return templates.TemplateResponse(
        "user_management/create.html",
        {
            "request": request,
            "user": current_profile,
            "business_units": dropdown_options.get('business_units', [])
        }
    )

@router.post("/create")
async def create_user(
    request: Request,
    email: str = Form(...),
    full_name: str = Form(...),
    role: str = Form(...),
    business_unit_name: str = Form(None),
    current_profile = Depends(get_admin_user)
):
    """Create new user (admin only)."""
    try:
        logging.info(f"Creating user - Email: {email}, Full Name: {full_name}, Role: {role}, Department: {business_unit_name}")
        # Check if user exists
        existing = supabase.table("profiles").select("username").eq("username", email).execute()
        if existing.data:
            return templates.TemplateResponse(
                "user_management/create.html",
                {
                    "request": request,
                    "user": current_profile,
                    "error": "Email already exists"
                }
            )
        
        # Create user in Supabase Auth
        auth_response = supabase.auth.admin.create_user({
            "email": email,
            "password": "54321",  # Default password
            "email_confirm": True
        })
        
        if auth_response.user:
            # Check if profile already exists
            existing_profile = supabase.table("profiles").select("id").eq("id", auth_response.user.id).execute()
            
            if not existing_profile.data:
                # Get business_unit_id from name
                business_unit_id = None
                if business_unit_name:
                    bu_response = supabase.table("ref_business_units").select("business_unit_id").eq("business_unit_name", business_unit_name).execute()
                    if bu_response.data:
                        business_unit_id = bu_response.data[0]['business_unit_id']
                
                # Create profile only if doesn't exist
                profile_data = {
                    "id": auth_response.user.id,
                    "username": email,
                    "full_name": full_name,
                    "role": role.lower(),
                    "is_active": True,
                    "email_verified": True,
                    "business_unit_id": business_unit_id,
                    "business_unit_name": business_unit_name
                }
                logging.info(f"Profile data to insert: {profile_data}")
                supabase.table("profiles").insert(profile_data).execute()
            
            # Log user creation
            supabase.table("user_management_logs").insert({
                "admin_id": current_profile.id,
                "target_user_id": auth_response.user.id,
                "action": "CREATE_USER",
                "details": f"Created user {email} with role {role}"
            }).execute()
            
            response = RedirectResponse(url="/user_management", status_code=status.HTTP_303_SEE_OTHER)
            set_flash(response, f"User {email} created successfully with password: 54321", "success")
            return response
        else:
            raise Exception("Failed to create user")
            
    except Exception as e:
        logging.error(f"Failed to create user: {e}")
        return templates.TemplateResponse(
            "user_management/create.html",
            {
                "request": request,
                "user": current_profile,
                "error": "Failed to create user"
            }
        )

@router.post("/reset_password/{user_id}")
async def reset_password(
    user_id: str,
    request: Request,
    current_profile = Depends(get_admin_user)
):
    """Reset user password to default (admin only)."""
    try:
        # Get user from profiles
        user_response = supabase.table("profiles").select("username").eq("id", user_id).execute()
        if not user_response.data:
            raise HTTPException(status_code=404, detail="User not found")
        
        user_email = user_response.data[0]["username"]
        
        # Reset password to default
        supabase.auth.admin.update_user_by_id(user_id, {"password": "54321"})
        
        # Log password reset
        supabase.table("user_management_logs").insert({
            "admin_id": current_profile.id,
            "target_user_id": user_id,
            "action": "RESET_PASSWORD",
            "details": f"Reset password for {user_email} to default"
        }).execute()
        
        response = RedirectResponse(url="/user_management", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, f"Password reset to 54321 for {user_email}", "success")
        return response
        
    except Exception as e:
        logging.error(f"Failed to reset password: {e}")
        response = RedirectResponse(url="/user_management", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, "Failed to send reset email", "error")
        return response

@router.post("/toggle_status/{user_id}")
async def toggle_user_status(
    user_id: str,
    request: Request,
    is_active: bool = Form(...),
    current_profile = Depends(get_admin_user)
):
    """Toggle user active status (admin only)."""
    try:
        # Update profile status
        response = supabase.table("profiles").update({
            "is_active": is_active
        }).eq("id", user_id).execute()
        
        if response.data:
            status_text = "activated" if is_active else "deactivated"
            
            # Log status change
            supabase.table("user_management_logs").insert({
                "admin_id": current_profile.id,
                "target_user_id": user_id,
                "action": "TOGGLE_STATUS",
                "details": f"User {status_text}"
            }).execute()
            
            redirect_response = RedirectResponse(url="/user_management", status_code=status.HTTP_303_SEE_OTHER)
            set_flash(redirect_response, f"User {status_text} successfully", "success")
            return redirect_response
        else:
            raise HTTPException(status_code=404, detail="User not found")
            
    except Exception as e:
        logging.error(f"Failed to toggle user status: {e}")
        redirect_response = RedirectResponse(url="/user_management", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(redirect_response, "Failed to update user status", "error")
        return redirect_response

@router.post("/verify_email/{user_id}")
async def verify_email(
    user_id: str,
    request: Request,
    current_profile = Depends(get_admin_user)
):
    """Manually verify user email (admin only)."""
    try:
        # Update email_verified status
        response = supabase.table("profiles").update({
            "email_verified": True
        }).eq("id", user_id).execute()
        
        if response.data:
            user_email = response.data[0].get("username", "Unknown")
            
            # Log email verification
            supabase.table("user_management_logs").insert({
                "admin_id": current_profile.id,
                "target_user_id": user_id,
                "action": "VERIFY_EMAIL",
                "details": f"Manually verified email for {user_email}"
            }).execute()
            
            redirect_response = RedirectResponse(url="/user_management", status_code=status.HTTP_303_SEE_OTHER)
            set_flash(redirect_response, f"Email verified for {user_email}", "success")
            return redirect_response
        else:
            raise HTTPException(status_code=404, detail="User not found")
            
    except Exception as e:
        logging.error(f"Failed to verify email: {e}")
        redirect_response = RedirectResponse(url="/user_management", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(redirect_response, "Failed to verify email", "error")
        return redirect_response

@router.post("/change_role/{user_id}")
async def change_role(
    user_id: str,
    request: Request,
    new_role: str = Form(...),
    current_profile = Depends(get_admin_user)
):
    """Change user role (admin only)."""
    try:
        # Update user role
        response = supabase.table("profiles").update({
            "role": new_role.lower()
        }).eq("id", user_id).execute()
        
        if response.data:
            user_email = response.data[0].get("username", "Unknown")
            
            # Log role change
            supabase.table("user_management_logs").insert({
                "admin_id": current_profile.id,
                "target_user_id": user_id,
                "action": "CHANGE_ROLE",
                "details": f"Changed role to {new_role} for {user_email}"
            }).execute()
            
            redirect_response = RedirectResponse(url="/user_management", status_code=status.HTTP_303_SEE_OTHER)
            set_flash(redirect_response, f"Role changed to {new_role} for {user_email}", "success")
            return redirect_response
        else:
            raise HTTPException(status_code=404, detail="User not found")
            
    except Exception as e:
        logging.error(f"Failed to change role: {e}")
        redirect_response = RedirectResponse(url="/user_management", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(redirect_response, "Failed to change role", "error")
        return redirect_response

@router.post("/change_department/{user_id}")
async def change_department(
    user_id: str,
    request: Request,
    business_unit_name: str = Form(...),
    current_profile = Depends(get_admin_user)
):
    """Change user department (admin only)."""
    try:
        # Get business_unit_id from name
        business_unit_id = None
        if business_unit_name:
            bu_response = supabase.table("ref_business_units").select("business_unit_id").eq("business_unit_name", business_unit_name).execute()
            if bu_response.data:
                business_unit_id = bu_response.data[0]['business_unit_id']
        
        # Update user department
        response = supabase.table("profiles").update({
            "business_unit_id": business_unit_id,
            "business_unit_name": business_unit_name
        }).eq("id", user_id).execute()
        
        if response.data:
            user_email = response.data[0].get("username", "Unknown")
            
            # Log department change
            supabase.table("user_management_logs").insert({
                "admin_id": current_profile.id,
                "target_user_id": user_id,
                "action": "CHANGE_DEPARTMENT",
                "details": f"Changed department to {business_unit_name} for {user_email}"
            }).execute()
            
            redirect_response = RedirectResponse(url="/user_management", status_code=status.HTTP_303_SEE_OTHER)
            set_flash(redirect_response, f"Department changed to {business_unit_name} for {user_email}", "success")
            return redirect_response
        else:
            raise HTTPException(status_code=404, detail="User not found")
            
    except Exception as e:
        logging.error(f"Failed to change department: {e}")
        redirect_response = RedirectResponse(url="/user_management", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(redirect_response, "Failed to change department", "error")
        return redirect_response