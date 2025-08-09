# app/routes/profile.py
from fastapi import APIRouter, Depends, Request, Form, UploadFile, File, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime, timezone

from app.utils.auth import get_current_profile
from app.utils.photo import resize_and_convert_image, upload_to_drive
from app.utils.flash import set_flash
from app.utils.database_manager import get_dropdown_options
from app.utils.device_detector import get_template

router = APIRouter(tags=["profile"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/profile", response_class=HTMLResponse)
async def profile_page(
    request: Request,
    current_profile = Depends(get_current_profile)
):
    """User profile page."""
    template_path = get_template(request, "profile/view.html")
    return templates.TemplateResponse(
        template_path,
        {
            "request": request,
            "user": current_profile
        }
    )

@router.get("/profile/edit", response_class=HTMLResponse)
async def edit_profile_page(
    request: Request,
    current_profile = Depends(get_current_profile)
):
    """Edit user profile page."""
    dropdown_options = get_dropdown_options()
    template_path = get_template(request, "profile/edit.html")
    return templates.TemplateResponse(
        template_path,
        {
            "request": request,
            "user": current_profile,
            "business_units": dropdown_options.get('business_units', [])
        }
    )

@router.post("/profile/edit")
async def update_profile(
    request: Request,
    full_name: str = Form(...),
    business_unit_name: str = Form(...),
    role: str = Form(None),
    photo: UploadFile = File(None),
    current_profile = Depends(get_current_profile)
):
    """Update user profile."""
    # Update profile via Supabase
    from supabase import create_client
    from app.config import load_config
    
    config = load_config()
    admin_supabase = create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_KEY)
    
    # Get business_unit_id from name
    business_unit_id = None
    if business_unit_name:
        bu_response = admin_supabase.table("ref_business_units").select("business_unit_id").eq("business_unit_name", business_unit_name).execute()
        if bu_response.data:
            business_unit_id = bu_response.data[0]['business_unit_id']
    
    # Update profile data - only update full_name if it's different and not empty
    update_data = {
        "business_unit_id": business_unit_id,
        "business_unit_name": business_unit_name,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    # Only update full_name if it's provided and different from current
    if full_name and full_name.strip() and full_name != current_profile.full_name:
        update_data["full_name"] = full_name
    
    # Only admin can update role
    if current_profile.role == "admin" and role:
        update_data["role"] = role
    
    admin_supabase.table("profiles").update(update_data).eq("id", current_profile.id).execute()
    
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
                    f"profile_{current_profile.email}"
                )
                if photo_url:
                    update_data["photo_url"] = photo_url
        except Exception as e:
            template_path = get_template(request, "profile/edit.html")
            return templates.TemplateResponse(
                template_path,
                {
                    "request": request,
                    "user": current_profile,
                    "error": f"Error uploading photo: {str(e)}"
                },
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    # Update photo if processed
    if photo and photo.filename and "photo_url" in update_data:
        admin_supabase.table("profiles").update({"photo_url": update_data["photo_url"]}).eq("id", current_profile.id).execute()
    
    # Redirect to profile page
    response = RedirectResponse(url="/profile", status_code=status.HTTP_303_SEE_OTHER)
    set_flash(response, "Profile updated successfully", "success")
    return response