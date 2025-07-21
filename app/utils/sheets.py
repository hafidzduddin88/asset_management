# app/utils/sheets.py
import gspread
import logging
import json
from datetime import datetime
from dateutil.relativedelta import relativedelta
from google.oauth2.service_account import Credentials
from app.config import load_config
from app.utils.cache import cache
from typing import List, Dict, Any, Optional, Tuple

config = load_config()

SHEETS = {
    'ASSETS': 'Assets',
    'REF_CATEGORIES': 'Ref_Categories',
    'REF_TYPES': 'Ref_Types',
    'REF_COMPANIES': 'Ref_Companies',
    'REF_OWNERS': 'Ref_Owners',
    'REF_LOCATION': 'Ref_Location'
}

# Set all cache TTLs to 60 seconds for frequent auto-refresh
CACHE_TTL = {
    'client': 60,
    'sheet': 60,
    'assets': 60,
    'reference': 60
}

_sequence_tracker = None

def get_sheets_client():
    return cache.get_or_set('sheets_client', _create_sheets_client, CACHE_TTL['client'])

def _create_sheets_client():
    try:
        creds_debug = config.GOOGLE_CREDS_JSON.copy()
        creds_debug['private_key'] = '[REDACTED]'
        logging.info(f"Using Google credentials: {json.dumps(creds_debug)}")
        creds = Credentials.from_service_account_info(
            config.GOOGLE_CREDS_JSON,
            scopes=[
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive"
            ]
        )
        client = gspread.authorize(creds)
        logging.info("Successfully created Google Sheets client")
        return client
    except Exception as e:
        logging.error(f"Error creating sheets client: {str(e)}")
        return None

def get_sheet(sheet_name):
    cache_key = f'sheet_{sheet_name}'
    return cache.get_or_set(cache_key, lambda: _get_sheet(sheet_name), CACHE_TTL['sheet'])

def _get_sheet(sheet_name):
    try:
        client = get_sheets_client()
        if not client:
            return None
        spreadsheet = client.open_by_key(config.GOOGLE_SHEET_ID)
        return spreadsheet.worksheet(sheet_name)
    except Exception as e:
        logging.error(f"Error getting sheet {sheet_name}: {str(e)}")
        return None

def get_reference_data(sheet_name):
    cache_key = f'reference_{sheet_name}'
    return cache.get_or_set(cache_key, lambda: _get_reference_data(sheet_name), CACHE_TTL['reference'])

def _get_reference_data(sheet_name):
    sheet = get_sheet(sheet_name)
    return sheet.get_all_records() if sheet else []

def get_dropdown_options():
    return cache.get_or_set('dropdown_options', _get_dropdown_options, CACHE_TTL['reference'])

def _get_dropdown_options():
    try:
        categories = get_reference_data(SHEETS['REF_CATEGORIES'])
        types = get_reference_data(SHEETS['REF_TYPES'])
        companies = get_reference_data(SHEETS['REF_COMPANIES'])
        owners = get_reference_data(SHEETS['REF_OWNERS'])
        locations = get_reference_data(SHEETS['REF_LOCATION'])

        category_names = [c.get('Category', '') for c in categories if 'Category' in c]
        company_names = [c.get('Company', '') for c in companies if 'Company' in c]
        owner_names = [o.get('Owner', '') for o in owners if 'Owner' in o]
        location_dict = {}
        for loc in locations:
            location_name = loc.get('Location')
            if location_name:
                location_dict.setdefault(location_name, []).append(loc.get('Room', ''))
        return {
            'categories': category_names,
            'types': types,
            'companies': company_names,
            'owners': owner_names,
            'locations': location_dict
        }
    except Exception as e:
        logging.error(f"Error getting dropdown options: {str(e)}")
        return {
            'categories': [], 'types': [], 'companies': [],
            'owners': [], 'locations': {}
        }

def get_reference_value(sheet_name, lookup_column, lookup_value, return_column):
    data = get_reference_data(sheet_name)
    for row in data:
        if row.get(lookup_column) == lookup_value:
            return row.get(return_column)
    return None

def _ensure_sequence_tracker():
    global _sequence_tracker
    if _sequence_tracker is None:
        _sequence_tracker = {}
        assets = get_all_assets()
        for asset in assets:
            company_code = asset.get('Code Company')
            type_code = asset.get('Code Type')
            year = asset.get('Tahun')
            if company_code and type_code and year:
                key = (company_code, type_code, str(year))
                asset_tag = asset.get('Asset Tag', '')
                if asset_tag and '.' in asset_tag:
                    try:
                        seq_num = int(asset_tag.split('.')[-1])
                        _sequence_tracker[key] = max(_sequence_tracker.get(key, 0), seq_num)
                    except Exception:
                        pass

def generate_asset_tag(company, category, type_val, owner, purchase_date):
    try:
        code_company = get_reference_value(SHEETS['REF_COMPANIES'], 'Company', company, 'Code Company')
        code_category = get_reference_value(SHEETS['REF_CATEGORIES'], 'Category', category, 'Code Category')
        code_type = get_reference_value(SHEETS['REF_TYPES'], 'Type', type_val, 'Code Type')
        code_owner = get_reference_value(SHEETS['REF_OWNERS'], 'Owner', owner, 'Code Owner')
        year = datetime.strptime(purchase_date, "%Y-%m-%d").year if isinstance(purchase_date, str) else purchase_date.year
        year_2digit = str(year)[-2:]

        if all([code_company, code_category, code_type, code_owner]):
            key = (code_company, code_type, str(year))
            _ensure_sequence_tracker()
            _sequence_tracker[key] = _sequence_tracker.get(key, 0) + 1
            seq_num = str(_sequence_tracker[key]).zfill(3)
            return f"{code_company}-{code_category}.{code_type}.{code_owner}{year_2digit}.{seq_num}"
    except Exception as e:
        logging.error(f"Error generating asset tag: {str(e)}")
    return None

def calculate_asset_financials(purchase_cost, purchase_date, category):
    try:
        residual_percent = float(get_reference_value(
            SHEETS['REF_CATEGORIES'], 'Category', category, 'Residual Percent') or 0)
        useful_life = int(get_reference_value(
            SHEETS['REF_CATEGORIES'], 'Category', category, 'Useful Life') or 0)
        purchase_year = datetime.strptime(purchase_date, "%Y-%m-%d").year if isinstance(purchase_date, str) else purchase_date.year
        current_year = datetime.now().year
        years_used = current_year - purchase_year
        purchase_cost = float(purchase_cost)
        residual_value = purchase_cost * (residual_percent / 100)
        depreciation = ((purchase_cost - residual_value) / useful_life) * years_used if years_used < useful_life else (purchase_cost - residual_value)
        book_value = purchase_cost - depreciation
        return {
            'Residual Percent': residual_percent,
            'Residual Value': round(residual_value, 2),
            'Useful Life': useful_life,
            'Depreciation Value': round(depreciation, 2),
            'Book Value': round(book_value, 2),
            'Tahun': purchase_year
        }
    except Exception as e:
        logging.error(f"Error calculating asset financials: {str(e)}")
        return {
            'Residual Percent': 0,
            'Residual Value': 0,
            'Useful Life': 0,
            'Depreciation Value': 0,
            'Book Value': 0,
            'Tahun': datetime.now().year
        }

def get_all_assets():
    return cache.get_or_set('all_assets', _get_all_assets, CACHE_TTL['assets'])

def _get_all_assets():
    sheet = get_sheet(SHEETS['ASSETS'])
    if not sheet:
        logging.error("Could not get Assets sheet")
        return []
    try:
        records = sheet.get_all_records()
        logging.info(f"Retrieved {len(records)} assets from sheet")
        return records
    except Exception as e:
        logging.error(f"Error getting records from Assets sheet: {str(e)}")
        return []

def get_asset_by_id(asset_id):
    cache_key = f'asset_{asset_id}'
    return cache.get_or_set(cache_key, lambda: _get_asset_by_id(asset_id), CACHE_TTL['assets'])

def _get_asset_by_id(asset_id):
    assets = get_all_assets()
    asset_id_str = str(asset_id)
    for asset in assets:
        if str(asset.get('ID', '')) == asset_id_str:
            return asset
    return None

def get_valid_asset_statuses():
    """
    Returns a dictionary of valid asset statuses and their descriptions.
    """
    return {
        'Active': 'Asset is currently in use',
        'Disposed': 'Telah di Disposal',
        'In Storage': 'Barang Aktif berada di Gudang',
        'To Be Disposed': 'Masuk List yang akan di disposal',
        'Under Repair': 'Masuk List Barang Damage / Rusak'
    }

# Add a function to get asset statistics
def get_asset_statistics():
    """
    Calculate statistics about assets including status counts and financial summary.
    """
    assets = get_all_assets()
    
    # Count assets by status
    status_counts = {}
    for asset in assets:
        status = asset.get('Status', 'Unknown')
        status_counts[status] = status_counts.get(status, 0) + 1
    
    # Calculate financial summary
    total_purchase_cost = 0
    total_book_value = 0
    total_depreciation = 0
    
    for asset in assets:
        purchase_cost = safe_float(asset.get('Purchase Cost', 0))
        book_value = safe_float(asset.get('Book Value', 0))
        depreciation = safe_float(asset.get('Depreciation Value', 0))
        
        total_purchase_cost += purchase_cost
        total_book_value += book_value
        total_depreciation += depreciation
    
    return {
        'status_counts': status_counts,
        'financial_summary': {
            'total_purchase_cost': round(total_purchase_cost, 2),
            'total_book_value': round(total_book_value, 2),
            'total_depreciation': round(total_depreciation, 2)
        }
    }

# Add a function to get chart data
def get_chart_data():
    """
    Prepare data for dashboard charts.
    """
    assets = get_all_assets()
    
    # Status chart data
    status_counts = {}
    for asset in assets:
        status = asset.get('Status', 'Unknown')
        status_counts[status] = status_counts.get(status, 0) + 1
    
    status_colors = {
        'Active': '#10B981',  # green
        'Under Repair': '#EF4444',  # red
        'In Storage': '#3B82F6',  # blue
        'To Be Disposed': '#F59E0B',  # yellow
        'Disposed': '#6B7280',  # gray
        'Unknown': '#9CA3AF'  # light gray
    }
    
    status_chart_data = {
        'labels': list(status_counts.keys()),
        'values': list(status_counts.values()),
        'colors': [status_colors.get(status, '#9CA3AF') for status in status_counts.keys()]
    }
    
    # Category chart data
    category_counts = {}
    for asset in assets:
        category = asset.get('Category', 'Unknown')
        category_counts[category] = category_counts.get(category, 0) + 1
    
    category_chart_data = {
        'labels': list(category_counts.keys()),
        'values': list(category_counts.values())
    }
    
    # Location chart data
    location_counts = {}
    for asset in assets:
        location = asset.get('Location', 'Unknown')
        location_counts[location] = location_counts.get(location, 0) + 1
    
    # Sort locations by count (descending)
    sorted_locations = sorted(location_counts.items(), key=lambda x: x[1], reverse=True)
    location_labels = [loc[0] for loc in sorted_locations[:10]]  # Top 10 locations
    location_values = [loc[1] for loc in sorted_locations[:10]]
    
    location_chart_data = {
        'labels': location_labels,
        'values': location_values
    }
    
    # Monthly additions chart data
    monthly_counts = {}
    current_date = datetime.now()
    
    # Initialize with last 12 months
    for i in range(11, -1, -1):
        month_date = current_date.replace(day=1) - relativedelta(months=i)
        month_key = month_date.strftime('%b %Y')
        monthly_counts[month_key] = 0
    
    # Count assets by purchase month
    for asset in assets:
        purchase_date = asset.get('Purchase Date', '')
        if purchase_date:
            try:
                date = datetime.strptime(purchase_date, '%Y-%m-%d')
                month_key = date.strftime('%b %Y')
                if month_key in monthly_counts:
                    monthly_counts[month_key] += 1
            except Exception:
                pass
    
    monthly_chart_data = {
        'labels': list(monthly_counts.keys()),
        'values': list(monthly_counts.values())
    }
    
    return {
        'status_chart_data': status_chart_data,
        'category_chart_data': category_chart_data,
        'location_chart_data': location_chart_data,
        'monthly_chart_data': monthly_chart_data
    }

def safe_float(value):
    """
    Safely convert a value to float, returning 0 if conversion fails.
    """
    if value is None or value == '':
        return 0
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0

def invalidate_cache():
    """
    Invalidate all cached data to force refresh from Google Sheets.
    """
    cache.invalidate_all()
    logging.info("Cache invalidated, data will be refreshed from Google Sheets")