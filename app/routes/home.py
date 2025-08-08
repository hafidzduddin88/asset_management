# /app/app/routes/home.py
import logging
from datetime import datetime
from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from app.utils.auth import get_current_profile
from app.utils.database_manager import get_summary_data, get_chart_data, get_all_assets

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=RedirectResponse)
async def redirect_root():
    return RedirectResponse("/dashboard")

@router.get("/dashboard", response_model=None)
async def home(request: Request, current_profile = Depends(get_current_profile), error: str = None, error_description: str = None):
    try:
        # Summary and chart data
        summary_data = get_summary_data()
        chart_data = get_chart_data()
        all_assets = get_all_assets()

        # Filter out disposed assets for dashboard counts
        active_assets = [asset for asset in all_assets if asset.get("status", "") != "Disposed"]
        disposed_assets = [asset for asset in all_assets if asset.get("status", "") == "Disposed"]
        
        # Count assets by status and activity
        total_assets = len(active_assets)
        disposed_count = len(disposed_assets)
        damaged_count = len([a for a in all_assets if a.get("status", "") == "Under Repair"])
        
        # Count assets by activity type
        relocated_count = 0  # Will need to get from logs
        repaired_count = 0   # Will need to get from logs
        to_be_disposed_count = len([a for a in all_assets if a.get("status", "") == "To be Disposed"])
        
        # Helper function to safely convert values to float
        def safe_float(value):
            if value is None or value == '':
                return 0.0
            try:
                return float(value)
            except (ValueError, TypeError):
                return 0.0
        
        # Calculate financial values directly from assets
        total_purchase_value = sum(safe_float(asset.get("purchase_cost")) for asset in active_assets)
        total_book_value = sum(safe_float(asset.get("book_value")) for asset in active_assets)
        # Calculate depreciation as purchase value minus book value
        total_depreciation_value = total_purchase_value - total_book_value
        category_counts = chart_data.get("category_counts", {})
        
        # Get chart data directly
        location_counts_dict = chart_data.get("location_counts", {})
        monthly_counts = chart_data.get("monthly_counts", {})
        quarterly_counts = chart_data.get("quarterly_counts", {})
        yearly_counts = chart_data.get("yearly_counts", {})
        
        monthly_chart_labels = list(monthly_counts.keys())
        monthly_chart_values = list(monthly_counts.values())
        quarterly_chart_labels = list(quarterly_counts.keys())
        quarterly_chart_values = list(quarterly_counts.values())
        yearly_chart_labels = list(yearly_counts.keys())
        yearly_chart_values = list(yearly_counts.values())
        

        


        # Calculate age distribution
        age_distribution = {"0-1 years": 0, "1-3 years": 0, "3-5 years": 0, "5+ years": 0}
        current_year = datetime.now().year
        
        for asset in all_assets:
            purchase_date = asset.get("purchase_date")
            if purchase_date:
                try:
                    if isinstance(purchase_date, str):
                        date = datetime.strptime(purchase_date, "%Y-%m-%d")
                    else:
                        date = purchase_date
                    age = current_year - date.year
                    
                    if age <= 1:
                        age_distribution["0-1 years"] += 1
                    elif age <= 3:
                        age_distribution["1-3 years"] += 1
                    elif age <= 5:
                        age_distribution["3-5 years"] += 1
                    else:
                        age_distribution["5+ years"] += 1
                except:
                    pass
        
        age_distribution_list = [
            {"label": k, "value": v} for k, v in age_distribution.items()
        ]

        # Format latest assets (excluding disposed assets)
        latest_assets = sorted(
            active_assets, 
            key=lambda a: a.get("purchase_date", ""), 
            reverse=True
        )[:10]
        
        # Process assets for display
        for asset in latest_assets:
            asset["display_name"] = asset.get("asset_name", f"Asset #{asset.get('asset_id', 'Unknown')}")
            asset["category_display"] = asset.get("ref_categories", {}).get("category_name", "Not specified") if asset.get("ref_categories") else "Not specified"
            asset["location_display"] = asset.get("ref_locations", {}).get("location_name", "Not specified") if asset.get("ref_locations") else "Not specified"
            asset["business_unit_display"] = asset.get("ref_business_units", {}).get("business_unit_name", "Not specified") if asset.get("ref_business_units") else "Not specified"
            asset["company_display"] = asset.get("ref_companies", {}).get("company_name", "Not specified") if asset.get("ref_companies") else "Not specified"
            asset["owner_display"] = asset.get("ref_owners", {}).get("owner_name", "Not specified") if asset.get("ref_owners") else "Not specified"
            # Format purchase date
            if asset.get("purchase_date"):
                try:
                    if isinstance(asset["purchase_date"], str):
                        date_obj = datetime.strptime(asset["purchase_date"], "%Y-%m-%d")
                        asset["purchase_date_display"] = date_obj.strftime("%B %d, %Y")
                    else:
                        asset["purchase_date_display"] = asset["purchase_date"].strftime("%B %d, %Y")
                except:
                    asset["purchase_date_display"] = "Not specified"
            else:
                asset["purchase_date_display"] = "Not specified"
            # Format purchase cost
            if asset.get("purchase_cost"):
                try:
                    cost = float(asset["purchase_cost"])
                    asset["purchase_cost_display"] = f"${cost:,.2f}"
                except:
                    asset["purchase_cost_display"] = "Not specified"
            else:
                asset["purchase_cost_display"] = "Not specified"


        # Handle email verification errors
        error_message = None
        if error == "access_denied" and "otp_expired" in str(error_description):
            error_message = "Email verification link has expired. Please request a new one."
        elif error:
            error_message = "Authentication error occurred. Please try logging in again."

        context = {
            "request": request,
            "user": current_profile,
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
            "latest_assets": latest_assets,
            "activity_data": chart_data.get("activity_data", {}),
            "error_message": error_message
        }

        return templates.TemplateResponse("dashboard.html", context)

    except Exception as e:
        logging.error("Dashboard error: %s", e, exc_info=True)
        return templates.TemplateResponse("dashboard.html", {
            "request": request,
            "user": current_profile,
            "total_assets": 0,
            "total_purchase_value": 0,
            "total_book_value": 0,
            "total_depreciation_value": 0,
            "disposed_count": 0,
            "damaged_count": 0,
            "relocated_count": 0,
            "repaired_count": 0,
            "to_be_disposed_count": 0,
            "category_counts": {},
            "location_counts": {},
            "monthly_chart_labels": [],
            "monthly_chart_values": [],
            "quarterly_chart_labels": [],
            "quarterly_chart_values": [],
            "yearly_chart_labels": [],
            "yearly_chart_values": [],
            "age_distribution": [],
            "latest_assets": [],
            "activity_data": {},
            "error": "Error loading dashboard data"
        })