# app/utils/sheets.py
import gspread
import logging
from datetime import datetime
from google.oauth2.service_account import Credentials
from app.config import load_config
from typing import List, Dict, Any, Optional, Tuple

# Load configuration
config = load_config()

# Constants
SHEETS = {
    'ASSETS': 'Assets',
    'REF_CATEGORIES': 'Ref_Categories',
    'REF_TYPES': 'Ref_Types',
    'REF_COMPANIES': 'Ref_Companies',
    'REF_OWNERS': 'Ref_Owners',
    'REF_LOCATION': 'Ref_Location'
}

# Asset tag sequence tracker
sequence_tracker = {}

def get_sheets_client():
    """Get Google Sheets client."""
    try:
        creds = Credentials.from_service_account_info(
            config.GOOGLE_CREDS_JSON,
            scopes=[
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive"
            ]
        )
        return gspread.authorize(creds)
    except Exception as e:
        logging.error(f"Error creating sheets client: {str(e)}")
        return None

def get_sheet(sheet_name):
    """Get specific worksheet from the spreadsheet."""
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
    """Get reference data from specified sheet."""
    sheet = get_sheet(sheet_name)
    if not sheet:
        return []
    
    return sheet.get_all_records()

def get_dropdown_options():
    """Get all dropdown options for forms."""
    try:
        categories = get_reference_data(SHEETS['REF_CATEGORIES'])
        types = get_reference_data(SHEETS['REF_TYPES'])
        companies = get_reference_data(SHEETS['REF_COMPANIES'])
        owners = get_reference_data(SHEETS['REF_OWNERS'])
        locations = get_reference_data(SHEETS['REF_LOCATION'])
        
        return {
            'categories': [c['Category'] for c in categories],
            'types': types,  # Keep full records for filtering by category
            'companies': [c['Company'] for c in companies],
            'owners': [o['Owner'] for o in owners],
            'locations': {
                loc['Location']: [r['Room'] for r in locations if r['Location'] == loc['Location']]
                for loc in {r['Location']: None for r in locations}.keys()
            }
        }
    except Exception as e:
        logging.error(f"Error getting dropdown options: {str(e)}")
        return {
            'categories': [], 'types': [], 'companies': [], 
            'owners': [], 'locations': {}
        }

def get_reference_value(sheet_name, lookup_column, lookup_value, return_column):
    """Get a specific value from reference sheets."""
    try:
        data = get_reference_data(sheet_name)
        for row in data:
            if row.get(lookup_column) == lookup_value:
                return row.get(return_column)
        return None
    except Exception as e:
        logging.error(f"Error in get_reference_value: {str(e)}")
        return None

def generate_asset_tag(company, category, type_val, owner, purchase_date):
    """Generate asset tag based on specified format."""
    try:
        # Get codes from reference sheets
        code_company = get_reference_value(SHEETS['REF_COMPANIES'], 'Company', company, 'Code Company')
        code_category = get_reference_value(SHEETS['REF_CATEGORIES'], 'Category', category, 'Code Category')
        code_type = get_reference_value(SHEETS['REF_TYPES'], 'Type', type_val, 'Code Type')
        code_owner = get_reference_value(SHEETS['REF_OWNERS'], 'Owner', owner, 'Code Owner')
        
        # Parse year from purchase date
        if isinstance(purchase_date, str):
            year = datetime.strptime(purchase_date, "%Y-%m-%d").year
        else:
            year = purchase_date.year
            
        year_2digit = str(year)[-2:]
        
        # Generate sequence number
        if code_company and code_category and code_type and code_owner:
            key = (code_company, code_type, str(year))
            
            # Initialize tracker if needed
            global sequence_tracker
            if not sequence_tracker:
                _initialize_sequence_tracker()
                
            if key not in sequence_tracker:
                sequence_tracker[key] = 1
            else:
                sequence_tracker[key] += 1
                
            seq_num = str(sequence_tracker[key]).zfill(3)
            
            # Format: (code_company)-(code_category).(code_type).(code_owner)(year_2digit).(seq_num)
            asset_tag = f"{code_company}-{code_category}.{code_type}.{code_owner}{year_2digit}.{seq_num}"
            return asset_tag
            
    except Exception as e:
        logging.error(f"Error generating asset tag: {str(e)}")
    
    return None

def _initialize_sequence_tracker():
    """Initialize sequence tracker from existing assets."""
    try:
        assets = get_all_assets()
        global sequence_tracker
        sequence_tracker = {}
        
        for asset in assets:
            company_code = asset.get('Code Company')
            type_code = asset.get('Code Type')
            year = asset.get('Tahun')
            
            if company_code and type_code and year:
                key = (company_code, type_code, str(year))
                asset_tag = asset.get('Asset Tag', '')
                
                if asset_tag and '.' in asset_tag:
                    # Extract sequence number from asset tag
                    try:
                        seq_part = asset_tag.split('.')[-1]
                        seq_num = int(seq_part)
                        
                        if key not in sequence_tracker or sequence_tracker[key] < seq_num:
                            sequence_tracker[key] = seq_num
                    except (ValueError, IndexError):
                        pass
    except Exception as e:
        logging.error(f"Error initializing sequence tracker: {str(e)}")

def calculate_asset_financials(purchase_cost, purchase_date, category):
    """Calculate financial values for an asset."""
    try:
        # Get residual percent and useful life from category
        residual_percent = float(get_reference_value(
            SHEETS['REF_CATEGORIES'], 'Category', category, 'Residual Percent') or 0)
        useful_life = int(get_reference_value(
            SHEETS['REF_CATEGORIES'], 'Category', category, 'Useful Life') or 0)
        
        # Parse purchase date
        if isinstance(purchase_date, str):
            purchase_year = datetime.strptime(purchase_date, "%Y-%m-%d").year
        else:
            purchase_year = purchase_date.year
            
        current_year = datetime.now().year
        years_used = current_year - purchase_year
        
        # Calculate values
        purchase_cost = float(purchase_cost)
        residual_value = purchase_cost * (residual_percent / 100)
        
        # Calculate depreciation
        if years_used < useful_life:
            depreciation = ((purchase_cost - residual_value) / useful_life) * years_used
        else:
            depreciation = (purchase_cost - residual_value)
            
        # Calculate book value
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
    """Get all assets from the sheet."""
    try:
        sheet = get_sheet(SHEETS['ASSETS'])
        if not sheet:
            return []
        
        return sheet.get_all_records()
    except Exception as e:
        logging.error(f"Error getting assets: {str(e)}")
        return []

def get_asset_by_id(asset_id):
    """Get asset by ID."""
    try:
        assets = get_all_assets()
        for asset in assets:
            if asset.get('ID') == asset_id:
                return asset
        return None
    except Exception as e:
        logging.error(f"Error getting asset by ID: {str(e)}")
        return None

def add_asset(asset_data):
    """Add new asset to the sheet."""
    try:
        sheet = get_sheet(SHEETS['ASSETS'])
        if not sheet:
            return False
            
        # Get next ID
        assets = sheet.get_all_records()
        next_id = str(len(assets) + 1).zfill(3)
        
        # Generate asset tag if not provided
        if 'Asset Tag' not in asset_data or not asset_data['Asset Tag']:
            asset_tag = generate_asset_tag(
                asset_data.get('Company'),
                asset_data.get('Category'),
                asset_data.get('Type'),
                asset_data.get('Owner'),
                asset_data.get('Purchase Date')
            )
            if asset_tag:
                asset_data['Asset Tag'] = asset_tag
        
        # Calculate financial values
        financials = calculate_asset_financials(
            asset_data.get('Purchase Cost', 0),
            asset_data.get('Purchase Date'),
            asset_data.get('Category')
        )
        
        # Merge data
        asset_data.update(financials)
        asset_data['ID'] = next_id
        
        # Get codes
        asset_data['Code Category'] = get_reference_value(
            SHEETS['REF_CATEGORIES'], 'Category', asset_data.get('Category'), 'Code Category')
        asset_data['Code Company'] = get_reference_value(
            SHEETS['REF_COMPANIES'], 'Company', asset_data.get('Company'), 'Code Company')
        asset_data['Code Type'] = get_reference_value(
            SHEETS['REF_TYPES'], 'Type', asset_data.get('Type'), 'Code Type')
        asset_data['Code Owner'] = get_reference_value(
            SHEETS['REF_OWNERS'], 'Owner', asset_data.get('Owner'), 'Code Owner')
        
        # Set default status if not provided
        if 'Status' not in asset_data:
            asset_data['Status'] = 'Active'
        
        # Get headers and prepare row
        headers = sheet.row_values(1)
        row_data = []
        for header in headers:
            row_data.append(asset_data.get(header, ''))
        
        # Append row
        sheet.append_row(row_data)
        return True
    except Exception as e:
        logging.error(f"Error adding asset: {str(e)}")
        return False

def update_asset(asset_id, asset_data):
    """Update asset in the sheet."""
    try:
        sheet = get_sheet(SHEETS['ASSETS'])
        if not sheet:
            return False
            
        # Find asset row
        cell = sheet.find(asset_id)
        if not cell:
            return False
            
        # Get headers
        headers = sheet.row_values(1)
        
        # Recalculate financials if needed
        if 'Purchase Cost' in asset_data or 'Purchase Date' in asset_data or 'Category' in asset_data:
            # Get current asset data
            current_asset = get_asset_by_id(asset_id)
            if current_asset:
                # Use updated values or current values
                purchase_cost = asset_data.get('Purchase Cost', current_asset.get('Purchase Cost'))
                purchase_date = asset_data.get('Purchase Date', current_asset.get('Purchase Date'))
                category = asset_data.get('Category', current_asset.get('Category'))
                
                # Calculate new financials
                financials = calculate_asset_financials(purchase_cost, purchase_date, category)
                asset_data.update(financials)
        
        # Update row
        for i, header in enumerate(headers):
            if header in asset_data:
                sheet.update_cell(cell.row, i + 1, asset_data[header])
        
        return True
    except Exception as e:
        logging.error(f"Error updating asset: {str(e)}")
        return False

def delete_asset(asset_id):
    """Delete asset from sheet (mark as deleted)."""
    try:
        return update_asset(asset_id, {'Status': 'Deleted'})
    except Exception as e:
        logging.error(f"Error deleting asset: {str(e)}")
        return False