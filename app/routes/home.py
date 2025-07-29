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

        # Format time-based chart data
        monthly_data = chart_data.get("monthly_chart_data", {})
        monthly_chart_labels = monthly_data.get("labels", [])
        monthly_chart_values = monthly_data.get("values", [])
        
        # Generate quarterly data (last 12 quarters - 3 years)
        quarterly_chart_labels = []
        quarterly_chart_values = []
        
        # Get current year and quarter
        from datetime import datetime
        current_date = datetime.now()
        current_year = current_date.year
        current_quarter = (current_date.month - 1) // 3 + 1
        
        # Generate data for the last 12 quarters
        for i in range(11, -1, -1):
            year = current_year
            quarter = current_quarter - i
            
            # Adjust year if quarter is negative or > 4
            while quarter <= 0:
                year -= 1
                quarter += 4
            while quarter > 4:
                year += 1
                quarter -= 4
                
            quarterly_chart_labels.append(f"Q{quarter} {year}")
            
            # Count assets added in this quarter
            quarter_start_month = (quarter - 1) * 3 + 1
            quarter_end_month = quarter * 3
            
            count = 0
            for asset in all_assets:
                purchase_date = asset.get("Purchase Date", "")
                if purchase_date:
                    try:
                        date = datetime.strptime(purchase_date, "%Y-%m-%d")
                        if date.year == year and quarter_start_month <= date.month <= quarter_end_month:
                            count += 1
                    except:
                        pass
            
            quarterly_chart_values.append(count)
        
        # Generate yearly data (last 5 years)
        yearly_chart_labels = []
        yearly_chart_values = []
        
        # Generate data for the last 5 years
        for i in range(4, -1, -1):
            year = current_year - i
            yearly_chart_labels.append(str(year))
            
            # Count assets added in this year
            count = 0
            for asset in all_assets:
                purchase_date = asset.get("Purchase Date", "")
                if purchase_date:
                    try:
                        date = datetime.strptime(purchase_date, "%Y-%m-%d")
                        if date.year == year:
                            count += 1
                    except:
                        pass
            
            yearly_chart_values.append(count)

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
        
        # Process assets to ensure they have a display_name field
        for asset in latest_assets:
            # Try different possible field names for the asset name
            name_fields = ["Name", "Asset Name", "AssetName", "Item Name", "Description", "Item"]
            display_name = None
            
            for field in name_fields:
                if asset.get(field):
                    display_name = asset.get(field)
                    break
            
            # If no name found, use a default
            if not display_name:
                display_name = f"Asset #{asset.get('ID', 'Unknown')}"
                
            # Add the display_name to the asset
            asset["display_name"] = display_name
            
        # Debug: Print the first asset's keys to see what fields are available
        if latest_assets:
            logging.info(f"Asset keys: {list(latest_assets[0].keys())}")
            logging.info(f"Asset display name: {latest_assets[0].get('display_name', 'Not found')}")
            logging.info(f"Original asset name fields: {[latest_assets[0].get(f, 'None') for f in name_fields]}")

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
            "user": current_user,
            "message": "Terjadi kesalahan saat memuat dashboard.",
        })