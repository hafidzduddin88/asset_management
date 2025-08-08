"""
Example of how to update your routes to use device detection
This shows the pattern for updating your existing route files
"""

from fastapi import APIRouter, Request, Depends
from fastapi.templating import Jinja2Templates
from app.utils.device_detector import get_template, get_device_info, is_mobile

# Your existing router setup
router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

# Example 1: Assets route with device detection
@router.get("/assets")
async def assets_page(request: Request, user=Depends(get_current_user)):
    """Assets page with automatic mobile/desktop template selection"""
    
    # Your existing data fetching logic
    assets = await get_all_assets()
    dropdown_options = await get_dropdown_options()
    
    # Get device-appropriate template
    template_path = get_template(request, "assets.html")
    
    # Add device info to context (optional)
    device_info = get_device_info(request)
    
    return templates.TemplateResponse(template_path, {
        "request": request,
        "user": user,
        "assets": assets,
        "dropdown_options": dropdown_options,
        "device_info": device_info  # Optional: pass device info to template
    })

# Example 2: Dashboard route
@router.get("/")
@router.get("/dashboard")
async def dashboard(request: Request, user=Depends(get_current_user)):
    """Dashboard with device-specific templates"""
    
    # Your existing dashboard data logic
    dashboard_data = await get_dashboard_data()
    
    # Automatically select template based on device
    template_path = get_template(request, "dashboard.html")
    
    return templates.TemplateResponse(template_path, {
        "request": request,
        "user": user,
        **dashboard_data,  # Spread your dashboard data
        "is_mobile_device": is_mobile(request)  # Optional flag
    })

# Example 3: Asset Management Add route
@router.get("/asset_management/add")
async def add_asset_page(request: Request, user=Depends(get_current_user)):
    """Add asset page with device detection"""
    
    dropdown_options = await get_dropdown_options()
    
    # Get appropriate template
    template_path = get_template(request, "asset_management/add.html")
    
    return templates.TemplateResponse(template_path, {
        "request": request,
        "user": user,
        "dropdown_options": dropdown_options
    })

# Example 4: Force specific device type (for testing)
@router.get("/assets/mobile")
async def assets_mobile_force(request: Request, user=Depends(get_current_user)):
    """Force mobile template for testing"""
    
    assets = await get_all_assets()
    dropdown_options = await get_dropdown_options()
    
    # Force mobile template
    template_path = get_template(request, "assets.html", force_device="mobile")
    
    return templates.TemplateResponse(template_path, {
        "request": request,
        "user": user,
        "assets": assets,
        "dropdown_options": dropdown_options
    })

@router.get("/assets/desktop")
async def assets_desktop_force(request: Request, user=Depends(get_current_user)):
    """Force desktop template for testing"""
    
    assets = await get_all_assets()
    dropdown_options = await get_dropdown_options()
    
    # Force desktop template
    template_path = get_template(request, "assets.html", force_device="desktop")
    
    return templates.TemplateResponse(template_path, {
        "request": request,
        "user": user,
        "assets": assets,
        "dropdown_options": dropdown_options
    })

# Example 5: API endpoint to get device info
@router.get("/api/device-info")
async def get_device_info_api(request: Request):
    """API endpoint to get device information"""
    return get_device_info(request)

"""
MIGRATION STEPS:

1. Import the device detection utilities:
   from app.utils.device_detector import get_template, get_device_info, is_mobile

2. Update each route handler:
   - Replace hardcoded template names with get_template(request, "template_name.html")
   - Optionally add device info to template context

3. Test both mobile and desktop versions:
   - Use browser dev tools to simulate mobile devices
   - Create force routes for testing specific versions

4. Update your existing route files one by one:
   - app/routes/assets.py
   - app/routes/dashboard.py (or wherever dashboard is)
   - app/routes/asset_management.py
   - app/routes/approvals.py
   - app/routes/damage.py
   - etc.

EXAMPLE PATTERN FOR EACH ROUTE:

# Before:
return templates.TemplateResponse("assets.html", context)

# After:
template_path = get_template(request, "assets.html")
return templates.TemplateResponse(template_path, context)
"""