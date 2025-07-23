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

        # Prepare variables for dashboard.html
        total_assets = len(all_assets)
        total_purchase_value = summary_data.get("total_purchase_value", 0)
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

        # Format latest assets
        latest_assets = sorted(
            all_assets, 
            key=lambda a: a.get("Purchase Date", ""), 
            reverse=True
        )[:10]

        context = {
            "request": request,
            "user": current_user,
            "total_assets": total_assets,
            "total_purchase_value": total_purchase_value,
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