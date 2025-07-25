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
    'APPROVALS': 'Approvals',
    'DAMAGE_LOG': 'Damage_Log',
    'REPAIR_LOG': 'Repair_Log',
    'LOST_LOG': 'Lost_Log',
    'DISPOSAL_LOG': 'Disposal_Log',
    'REF_CATEGORIES': 'Ref_Categories',
    'REF_TYPES': 'Ref_Types',
    'REF_COMPANIES': 'Ref_Companies',
    'REF_OWNERS': 'Ref_Owners',
    'REF_LOCATION': 'Ref_Location',
    'REF_BISNIS_UNIT': 'Ref_Bisnis_Unit'
}

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
        
        try:
            return spreadsheet.worksheet(sheet_name)
        except Exception:
            # Sheet doesn't exist, create it
            if sheet_name == SHEETS['APPROVALS']:
                return _create_approvals_sheet(spreadsheet)
            elif sheet_name == SHEETS['DAMAGE_LOG']:
                return _create_damage_log_sheet(spreadsheet)
            elif sheet_name == SHEETS['REPAIR_LOG']:
                return _create_repair_log_sheet(spreadsheet)
            elif sheet_name == SHEETS['LOST_LOG']:
                return _create_lost_log_sheet(spreadsheet)
            elif sheet_name == SHEETS['DISPOSAL_LOG']:
                return _create_disposal_log_sheet(spreadsheet)
            else:
                raise
    except Exception as e:
        logging.error(f"Error getting sheet {sheet_name}: {str(e)}")
        return None

def _create_approvals_sheet(spreadsheet):
    """Create Approvals sheet with headers"""
    try:
        sheet = spreadsheet.add_worksheet(title=SHEETS['APPROVALS'], rows=1000, cols=15)
        
        # Add headers
        headers = [
            'ID', 'Type', 'Asset_ID', 'Asset_Name', 'Status', 
            'Submitted_By', 'Submitted_Date', 'Description', 
            'Damage_Type', 'Severity', 'Action', 'Location', 
            'Approved_By', 'Approved_Date', 'Notes'
        ]
        
        sheet.append_row(headers)
        logging.info(f"Created {SHEETS['APPROVALS']} sheet with headers")
        return sheet
    except Exception as e:
        logging.error(f"Error creating Approvals sheet: {str(e)}")
        return None

def _create_damage_log_sheet(spreadsheet):
    """Create Damage_Log sheet with headers"""
    try:
        sheet = spreadsheet.add_worksheet(title=SHEETS['DAMAGE_LOG'], rows=1000, cols=12)
        
        # Add headers
        headers = [
            'ID', 'Asset_ID', 'Asset_Name', 'Damage_Type', 'Severity',
            'Description', 'Reported_By', 'Report_Date', 'Status',
            'Location', 'Room', 'Notes'
        ]
        
        sheet.append_row(headers)
        logging.info(f"Created {SHEETS['DAMAGE_LOG']} sheet with headers")
        return sheet
    except Exception as e:
        logging.error(f"Error creating Damage_Log sheet: {str(e)}")
        return None

def _create_repair_log_sheet(spreadsheet):
    """Create Repair_Log sheet with headers"""
    try:
        sheet = spreadsheet.add_worksheet(title=SHEETS['REPAIR_LOG'], rows=1000, cols=12)
        
        # Add headers
        headers = [
            'ID', 'Asset_ID', 'Asset_Name', 'Repair_Action', 'Action_Type',
            'Description', 'Performed_By', 'Action_Date', 'Status',
            'New_Location', 'New_Room', 'Notes'
        ]
        
        sheet.append_row(headers)
        logging.info(f"Created {SHEETS['REPAIR_LOG']} sheet with headers")
        return sheet
    except Exception as e:
        logging.error(f"Error creating Repair_Log sheet: {str(e)}")
        return None

def get_all_assets():
    return cache.get_or_set('all_assets', _get_all_assets, CACHE_TTL['assets'])

def _get_all_assets():
    sheet = get_sheet(SHEETS['ASSETS'])
    if not sheet:
        logging.error("Could not get Assets sheet")
        return []
    try:
        records = sheet.get_all_records()
        return records
    except Exception as e:
        logging.error(f"Error getting records from Assets sheet: {str(e)}")
        return []

def get_summary_data():
    assets = get_all_assets()
    total_purchase_value = 0
    for asset in assets:
        try:
            purchase_cost = float(asset.get("Purchase Cost", 0) or 0)
            total_purchase_value += purchase_cost
        except Exception:
            continue
    return {
        "total_purchase_value": total_purchase_value
    }

def get_chart_data():
    assets = get_all_assets()

    # Category counts
    category_counts = {}
    for asset in assets:
        cat = asset.get("Category", "Unknown")
        category_counts[cat] = category_counts.get(cat, 0) + 1

    # Location counts
    location_counts = {}
    for asset in assets:
        loc = asset.get("Location", "Unknown")
        location_counts[loc] = location_counts.get(loc, 0) + 1

    # Monthly chart
    monthly_counts = {}
    now = datetime.now()
    for i in range(11, -1, -1):
        month = (now.replace(day=1) - relativedelta(months=i)).strftime("%b %Y")
        monthly_counts[month] = 0

    for asset in assets:
        date_str = asset.get("Purchase Date", "")
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            key = dt.strftime("%b %Y")
            if key in monthly_counts:
                monthly_counts[key] += 1
        except Exception:
            continue

    # Age distribution
    age_distribution = {}
    current_year = datetime.now().year
    for asset in assets:
        try:
            year = datetime.strptime(asset.get("Purchase Date", ""), "%Y-%m-%d").year
            age = current_year - year
            age_str = f"{age} tahun"
            age_distribution[age_str] = age_distribution.get(age_str, 0) + 1
        except:
            continue

    return {
        "category_counts": category_counts,
        "location_chart_data": {
            "labels": list(location_counts.keys()),
            "values": list(location_counts.values())
        },
        "monthly_chart_data": {
            "labels": list(monthly_counts.keys()),
            "values": list(monthly_counts.values())
        },
        "age_distribution": age_distribution
    }

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
        business_units = get_reference_data(SHEETS['REF_BISNIS_UNIT'])

        category_names = [c.get('Category', '') for c in categories if 'Category' in c]
        company_names = [c.get('Company', '') for c in companies if 'Company' in c]
        owner_names = [o.get('Owner', '') for o in owners if 'Owner' in o]
        business_unit_names = [b.get('Bisnis Unit', '') for b in business_units if 'Bisnis Unit' in b]
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
            'business_units': business_unit_names,
            'locations': location_dict
        }
    except Exception as e:
        logging.error(f"Error getting dropdown options: {str(e)}")
        return {
            'categories': [], 'types': [], 'companies': [],
            'owners': [], 'business_units': [], 'locations': {}
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
def get_chart_data(year=None, category=None):
    """
    Prepare data for dashboard charts.
    
    Args:
        year: Optional filter by year
        category: Optional filter by category
        
    Returns:
        Dictionary with chart data (all values are JSON serializable)
    """
    assets = get_all_assets()
    
    # Apply filters if provided
    if year or category:
        filtered_assets = []
        for asset in assets:
            include = True
            
            if year and asset.get('Purchase Date'):
                try:
                    asset_year = datetime.strptime(asset.get('Purchase Date'), '%Y-%m-%d').year
                    if str(asset_year) != str(year):
                        include = False
                except:
                    pass
                    
            if category and asset.get('Category') != category:
                include = False
                
            if include:
                filtered_assets.append(asset)
        assets = filtered_assets
    
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
    
    # Company chart data
    company_counts = {}
    for asset in assets:
        company = asset.get('Company', 'Unknown')
        company_counts[company] = company_counts.get(company, 0) + 1
    
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
    
    # Explicitly convert to lists to ensure JSON serialization works
    monthly_labels = list(monthly_counts.keys())
    monthly_values = list(monthly_counts.values())
    
    monthly_chart_data = {
        'labels': monthly_labels,
        'values': monthly_values
    }
    
    # Create a safe, serializable result
    try:
        result = {
            'status_counts': dict(status_counts),
            'category_counts': dict(category_counts),
            'company_counts': dict(company_counts),
            'location_chart_data': {
                'labels': list(location_chart_data['labels']),
                'values': list(location_chart_data['values'])
            },
            'monthly_chart_data': {
                'labels': list(monthly_chart_data['labels']),
                'values': list(monthly_chart_data['values'])
            }
        }
        return result
    except Exception as e:
        logging.error(f"Error preparing chart data: {str(e)}")
        # Return safe defaults if anything goes wrong
        return {
            'status_counts': {},
            'category_counts': {},
            'company_counts': {},
            'location_chart_data': {'labels': [], 'values': []},
            'monthly_chart_data': {'labels': [], 'values': []}
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

def add_asset(asset_data):
    """
    Add a new asset to the Google Sheet.
    
    Args:
        asset_data: Dictionary containing asset information
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Get the assets sheet
        sheet = get_sheet(SHEETS['ASSETS'])
        if not sheet:
            logging.error("Could not get Assets sheet")
            return False
            
        # Get all assets to determine next ID
        assets = get_all_assets()
        next_id = 1
        if assets:
            try:
                # Find the highest ID and increment by 1
                max_id = max(int(asset.get('ID', 0)) for asset in assets)
                next_id = max_id + 1
            except Exception as e:
                logging.error(f"Error determining next ID: {str(e)}")
                next_id = len(assets) + 1
        
        # Add ID to asset data
        asset_data['ID'] = str(next_id)
        
        # Generate asset tag if not provided
        if not asset_data.get('Asset Tag'):
            asset_tag = generate_asset_tag(
                asset_data.get('Company', ''),
                asset_data.get('Category', ''),
                asset_data.get('Type', ''),
                asset_data.get('Owner', ''),
                asset_data.get('Purchase Date', '')
            )
            if asset_tag:
                asset_data['Asset Tag'] = asset_tag
        
        # Calculate financial values
        financials = calculate_asset_financials(
            asset_data.get('Purchase Cost', 0),
            asset_data.get('Purchase Date', ''),
            asset_data.get('Category', '')
        )
        
        # Add financial data to asset
        for key, value in financials.items():
            asset_data[key] = value
        
        # Get all headers from the sheet
        headers = sheet.row_values(1)
        
        # Prepare row data in the correct order
        row_data = [asset_data.get(header, '') for header in headers]
        
        # Append the new row
        sheet.append_row(row_data)
        logging.info(f"Added new asset with ID {next_id}")
        
        # Invalidate cache to refresh data
        invalidate_cache()
        
        return True
    except Exception as e:
        logging.error(f"Error adding asset: {str(e)}")
        return False

def update_asset(asset_id, update_data):
    """
    Update an existing asset in the Google Sheet.
    
    Args:
        asset_id: ID of the asset to update
        update_data: Dictionary containing fields to update
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Get the assets sheet
        sheet = get_sheet(SHEETS['ASSETS'])
        if not sheet:
            logging.error("Could not get Assets sheet")
            return False
        
        # Get all assets to find the one to update
        assets = get_all_assets()
        asset_id_str = str(asset_id)
        
        # Find the asset and its row index
        row_index = None
        for i, asset in enumerate(assets):
            if str(asset.get('ID', '')) == asset_id_str:
                row_index = i + 2  # +2 because Google Sheets is 1-indexed and we have a header row
                break
        
        if row_index is None:
            logging.error(f"Asset with ID {asset_id} not found")
            return False
        
        # Get headers to determine column indices
        headers = sheet.row_values(1)
        
        # Update each field
        for field, value in update_data.items():
            if field in headers:
                col_index = headers.index(field) + 1  # +1 because Google Sheets is 1-indexed
                sheet.update_cell(row_index, col_index, value)
                logging.info(f"Updated {field} to {value} for asset {asset_id}")
        
        # Invalidate cache to refresh data
        invalidate_cache()
        
        return True
    except Exception as e:
        logging.error(f"Error updating asset: {str(e)}")
        return False

def get_all_approvals():
    """Get all approval requests from Google Sheets"""
    return cache.get_or_set('all_approvals', _get_all_approvals, CACHE_TTL['assets'])

def _get_all_approvals():
    sheet = get_sheet(SHEETS['APPROVALS'])
    if not sheet:
        return []
    try:
        records = sheet.get_all_records()
        return records
    except Exception as e:
        logging.error(f"Error getting approvals: {str(e)}")
        return []

def add_approval_request(approval_data):
    """Add new approval request to Google Sheets"""
    try:
        sheet = get_sheet(SHEETS['APPROVALS'])
        if not sheet:
            return False
        
        # Get next ID
        approvals = get_all_approvals()
        next_id = len(approvals) + 1
        
        # Prepare row data
        row_data = [
            str(next_id),
            approval_data.get('type', ''),
            approval_data.get('asset_id', ''),
            approval_data.get('asset_name', ''),
            'Pending',
            approval_data.get('submitted_by', ''),
            approval_data.get('submitted_date', ''),
            approval_data.get('description', ''),
            approval_data.get('damage_type', ''),
            approval_data.get('severity', ''),
            approval_data.get('action', ''),
            approval_data.get('location', ''),
            '',  # Approved_By
            '',  # Approved_Date
            ''   # Notes
        ]
        
        sheet.append_row(row_data)
        invalidate_cache()
        return True
    except Exception as e:
        logging.error(f"Error adding approval request: {str(e)}")
        return False

def update_approval_status(approval_id, status, approved_by, notes=''):
    """Update approval status in Google Sheets"""
    try:
        sheet = get_sheet(SHEETS['APPROVALS'])
        if not sheet:
            return False
        
        approvals = get_all_approvals()
        row_index = None
        
        for i, approval in enumerate(approvals):
            if str(approval.get('ID', '')) == str(approval_id):
                row_index = i + 2  # +2 for header and 1-based indexing
                break
        
        if row_index is None:
            return False
        
        # Update status, approved_by, approved_date
        from datetime import datetime
        approved_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        sheet.update_cell(row_index, 5, status)  # Status column
        sheet.update_cell(row_index, 13, approved_by)  # Approved_By column
        sheet.update_cell(row_index, 14, approved_date)  # Approved_Date column
        sheet.update_cell(row_index, 15, notes)  # Notes column
        
        invalidate_cache()
        return True
    except Exception as e:
        logging.error(f"Error updating approval status: {str(e)}")
        return False

def add_damage_log(damage_data):
    """Add damage report to Damage_Log sheet"""
    try:
        sheet = get_sheet(SHEETS['DAMAGE_LOG'])
        if not sheet:
            return False
        
        # Get next ID
        records = sheet.get_all_records()
        next_id = len(records) + 1
        
        # Prepare row data
        row_data = [
            str(next_id),
            damage_data.get('asset_id', ''),
            damage_data.get('asset_name', ''),
            damage_data.get('damage_type', ''),
            damage_data.get('severity', ''),
            damage_data.get('description', ''),
            damage_data.get('reported_by', ''),
            damage_data.get('report_date', ''),
            'Reported',
            damage_data.get('location', ''),
            damage_data.get('room', ''),
            damage_data.get('notes', '')
        ]
        
        sheet.append_row(row_data)
        invalidate_cache()
        return True
    except Exception as e:
        logging.error(f"Error adding damage log: {str(e)}")
        return False

def add_repair_log(repair_data):
    """Add repair action to Repair_Log sheet"""
    try:
        sheet = get_sheet(SHEETS['REPAIR_LOG'])
        if not sheet:
            return False
        
        # Get next ID
        records = sheet.get_all_records()
        next_id = len(records) + 1
        
        # Prepare row data
        row_data = [
            str(next_id),
            repair_data.get('asset_id', ''),
            repair_data.get('asset_name', ''),
            repair_data.get('repair_action', ''),
            repair_data.get('action_type', ''),
            repair_data.get('description', ''),
            repair_data.get('performed_by', ''),
            repair_data.get('action_date', ''),
            'Completed',
            repair_data.get('new_location', ''),
            repair_data.get('new_room', ''),
            repair_data.get('notes', '')
        ]
        
        sheet.append_row(row_data)
        invalidate_cache()
        return True
    except Exception as e:
        logging.error(f"Error adding repair log: {str(e)}")
        return False

def get_damage_logs():
    """Get all damage logs from Google Sheets"""
    sheet = get_sheet(SHEETS['DAMAGE_LOG'])
    if not sheet:
        return []
    try:
        return sheet.get_all_records()
    except Exception as e:
        logging.error(f"Error getting damage logs: {str(e)}")
        return []

def get_repair_logs():
    """Get all repair logs from Google Sheets"""
    sheet = get_sheet(SHEETS['REPAIR_LOG'])
    if not sheet:
        return []
    try:
        return sheet.get_all_records()
    except Exception as e:
        logging.error(f"Error getting repair logs: {str(e)}")
        return []

def _create_lost_log_sheet(spreadsheet):
    """Create Lost_Log sheet with headers"""
    try:
        sheet = spreadsheet.add_worksheet(title=SHEETS['LOST_LOG'], rows=1000, cols=12)
        
        # Add headers
        headers = [
            'ID', 'Asset_ID', 'Asset_Name', 'Last_Location', 'Last_Room',
            'Date_Lost', 'Description', 'Reported_By', 'Report_Date', 
            'Status', 'Investigation_Notes', 'Resolution'
        ]
        
        sheet.append_row(headers)
        logging.info(f"Created {SHEETS['LOST_LOG']} sheet with headers")
        return sheet
    except Exception as e:
        logging.error(f"Error creating Lost_Log sheet: {str(e)}")
        return None

def _create_disposal_log_sheet(spreadsheet):
    """Create Disposal_Log sheet with headers"""
    try:
        sheet = spreadsheet.add_worksheet(title=SHEETS['DISPOSAL_LOG'], rows=1000, cols=12)
        
        # Add headers
        headers = [
            'ID', 'Asset_ID', 'Asset_Name', 'Disposal_Reason', 'Disposal_Method',
            'Description', 'Requested_By', 'Request_Date', 'Status',
            'Disposal_Date', 'Disposed_By', 'Notes'
        ]
        
        sheet.append_row(headers)
        logging.info(f"Created {SHEETS['DISPOSAL_LOG']} sheet with headers")
        return sheet
    except Exception as e:
        logging.error(f"Error creating Disposal_Log sheet: {str(e)}")
        return None

def add_lost_log(lost_data):
    """Add lost report to Lost_Log sheet"""
    try:
        sheet = get_sheet(SHEETS['LOST_LOG'])
        if not sheet:
            return False
        
        # Get next ID
        records = sheet.get_all_records()
        next_id = len(records) + 1
        
        # Prepare row data
        row_data = [
            str(next_id),
            lost_data.get('asset_id', ''),
            lost_data.get('asset_name', ''),
            lost_data.get('last_location', ''),
            lost_data.get('last_room', ''),
            lost_data.get('date_lost', ''),
            lost_data.get('description', ''),
            lost_data.get('reported_by', ''),
            lost_data.get('report_date', ''),
            'Reported',
            lost_data.get('notes', ''),
            ''
        ]
        
        sheet.append_row(row_data)
        invalidate_cache()
        return True
    except Exception as e:
        logging.error(f"Error adding lost log: {str(e)}")
        return False

def add_disposal_log(disposal_data):
    """Add disposal request to Disposal_Log sheet"""
    try:
        sheet = get_sheet(SHEETS['DISPOSAL_LOG'])
        if not sheet:
            return False
        
        # Get next ID
        records = sheet.get_all_records()
        next_id = len(records) + 1
        
        # Prepare row data
        row_data = [
            str(next_id),
            disposal_data.get('asset_id', ''),
            disposal_data.get('asset_name', ''),
            disposal_data.get('disposal_reason', ''),
            disposal_data.get('disposal_method', ''),
            disposal_data.get('description', ''),
            disposal_data.get('requested_by', ''),
            disposal_data.get('request_date', ''),
            'Requested',
            '',  # Disposal_Date
            '',  # Disposed_By
            disposal_data.get('notes', '')
        ]
        
        sheet.append_row(row_data)
        invalidate_cache()
        return True
    except Exception as e:
        logging.error(f"Error adding disposal log: {str(e)}")
        return False