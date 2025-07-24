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

        # Format monthly chart data
        monthly_data = chart_data.get("monthly_chart_data", {})
        monthly_chart_labels = monthly_data.get("labels", [])
        monthly_chart_values = monthly_data.get("values", [])

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