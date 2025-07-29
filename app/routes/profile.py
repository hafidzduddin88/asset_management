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