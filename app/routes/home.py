# /app/app/routes/home.py
import logging
from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse
from starlette.templating import Jinja2Templates
from app.utils.auth import get_current_profile
from app.utils.database_manager import get_summary_data, get_chart_data, get_all_assets

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=RedirectResponse)
async def redirect_root():
    return RedirectResponse("/dashboard")

@router.get("/dashboard", response_model=None)
async def home(request: Request, current_profile = Depends(get_current_profile)):
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
        monthly_chart_labels = list(monthly_counts.keys())
        monthly_chart_values = list(monthly_counts.values())
        
        # Generate quarterly data
        from datetime import datetime
        current_date = datetime.now()
        quarterly_chart_labels = []
        quarterly_chart_values = []
        
        for i in range(3, -1, -1):
            year = current_date.year
            quarter = ((current_date.month - 1) // 3 + 1) - i
            if quarter <= 0:
                year -= 1
                quarter += 4
            
            quarterly_chart_labels.append(f"Q{quarter} {year}")
            
            # Count assets in this quarter
            start_month = (quarter - 1) * 3 + 1
            end_month = quarter * 3
            count = 0
            
            for asset in all_assets:
                purchase_date = asset.get("purchase_date")
                if purchase_date:
                    try:
                        if isinstance(purchase_date, str):
                            date = datetime.strptime(purchase_date, "%Y-%m-%d")
                        else:
                            date = purchase_date
                        if date.year == year and start_month <= date.month <= end_month:
                            count += 1
                    except:
                        pass
            
            quarterly_chart_values.append(count)
        
        # Generate yearly data
        yearly_chart_labels = []
        yearly_chart_values = []
        
        for i in range(4, -1, -1):
            year = current_date.year - i
            yearly_chart_labels.append(str(year))
            
            count = 0
            for asset in all_assets:
                purchase_date = asset.get("purchase_date")
                if purchase_date:
                    try:
                        if isinstance(purchase_date, str):
                            date = datetime.strptime(purchase_date, "%Y-%m-%d")
                        else:
                            date = purchase_date
                        if date.year == year:
                            count += 1
                    except:
                        pass
            
            yearly_chart_values.append(count)

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
            asset["category_display"] = asset.get("ref_categories", {}).get("category_name", "Unknown") if asset.get("ref_categories") else "Unknown"
            asset["location_display"] = asset.get("ref_locations", {}).get("location_name", "Unknown") if asset.get("ref_locations") else "Unknown"
            asset["business_unit_display"] = asset.get("ref_business_units", {}).get("business_unit_name", "Unknown") if asset.get("ref_business_units") else "Unknown"


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
            "latest_assets": latest_assets
        }

        return templates.TemplateResponse("dashboard.html", context)

    except Exception as e:
        logging.error("Dashboard error: %s", e, exc_info=True)
        return templates.TemplateResponse("error.html", {
            "request": request,
            "user": current_profile,
            "message": "Terjadi kesalahan saat memuat dashboard.",
        })