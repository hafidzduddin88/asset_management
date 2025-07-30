# app/routes/profile.py
from fastapi import APIRouter, Depends, Request, Form, UploadFile, File, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from app.database.database import get_db
from app.database.models import Profile
from app.utils.auth import get_current_profile
from app.utils.photo import resize_and_convert_image, upload_to_drive
from app.utils.flash import set_flash

router = APIRouter(tags=["profile"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/profile", response_class=HTMLResponse)
async def profile_page(
    request: Request,
    current_profile = Depends(get_current_profile)
):
    """User profile page."""
    return templates.TemplateResponse(
        "profile/view.html",
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
    return templates.TemplateResponse(
        "profile/edit.html",
        {
            "request": request,
            "user": current_profile
        }
    )

@router.post("/profile/edit")
async def update_profile(
    request: Request,
    username: str = Form(...),
    full_name: str = Form(...),
    photo: UploadFile = File(None),
    current_profile = Depends(get_current_profile)
):
    """Update user profile."""
    # Update profile via Supabase
    from supabase import create_client
    from app.config import load_config
    
    config = load_config()
    admin_supabase = create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_KEY)
    
    # Update profile data
    update_data = {
        "username": username,
        "full_name": full_name,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
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
            return templates.TemplateResponse(
                "profile/edit.html",
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