"""
Database Manager - Replace Google Sheets with Supabase operations
"""
import logging
from datetime import datetime
from dateutil.relativedelta import relativedelta
from app.utils.supabase_client import supabase_client
from app.utils.cache import cache
from typing import List, Dict, Any, Optional

TABLES = {
    'ASSETS': 'assets',
    'APPROVALS': 'approvals',
    'DAMAGE_LOG': 'damage_log',
    'REPAIR_LOG': 'repair_log',
    'LOST_LOG': 'lost_log',
    'DISPOSAL_LOG': 'disposal_log',
    'REF_CATEGORIES': 'ref_categories',
    'REF_TYPES': 'ref_asset_types',
    'REF_COMPANIES': 'ref_companies',
    'REF_OWNERS': 'ref_owners',
    'REF_LOCATION': 'ref_locations',
    'REF_BISNIS_UNIT': 'ref_business_units'
}

CACHE_TTL = {
    'assets': 60,
    'reference': 60
}

def get_supabase():
    return supabase_client.client

def get_all_assets():
    return cache.get_or_set('all_assets', _get_all_assets, CACHE_TTL['assets'])

def _get_all_assets():
    try:
        supabase = get_supabase()
        response = supabase.table(TABLES['ASSETS']).select('''
            asset_id, asset_name, manufacture, model, serial_number, asset_tag,
            room_name, notes, item_condition, purchase_date, purchase_cost,
            warranty, supplier, journal, depreciation_value, residual_percent,
            residual_value, useful_life, book_value, status, year, photo_url,
            ref_categories(category_name),
            ref_asset_types(type_name),
            ref_companies(company_name),
            ref_business_units(business_unit_name),
            ref_locations(location_name, room_name),
            ref_owners(owner_name)
        ''').execute()
        return response.data
    except Exception as e:
        logging.error(f"Error getting assets from database: {str(e)}")
        return []

def get_asset_by_id(asset_id):
    try:
        supabase = get_supabase()
        response = supabase.table(TABLES['ASSETS']).select('''
            asset_id, asset_name, manufacture, model, serial_number, asset_tag,
            room_name, notes, item_condition, purchase_date, purchase_cost,
            warranty, supplier, journal, depreciation_value, residual_percent,
            residual_value, useful_life, book_value, status, year, photo_url,
            ref_categories(category_name),
            ref_asset_types(type_name),
            ref_companies(company_name),
            ref_business_units(unit_name),
            ref_locations(location_name, room_name),
            ref_owners(owner_name)
        ''').eq('asset_id', asset_id).execute()
        return response.data[0] if response.data else None
    except Exception as e:
        logging.error(f"Error getting asset {asset_id}: {str(e)}")
        return None

def get_reference_data(table_name):
    cache_key = f'reference_{table_name}'
    return cache.get_or_set(cache_key, lambda: _get_reference_data(table_name), CACHE_TTL['reference'])

def _get_reference_data(table_name):
    try:
        supabase = get_supabase()
        response = supabase.table(table_name).select('*').execute()
        return response.data
    except Exception as e:
        logging.error(f"Error getting reference data from {table_name}: {str(e)}")
        return []

def get_dropdown_options():
    return cache.get_or_set('dropdown_options', _get_dropdown_options, CACHE_TTL['reference'])

def _get_dropdown_options():
    try:
        categories = get_reference_data(TABLES['REF_CATEGORIES'])
        # Get types with category relationship
        supabase = get_supabase()
        types_response = supabase.table(TABLES['REF_TYPES']).select('type_name, ref_categories(category_name)').execute()
        types = []
        for t in types_response.data:
            types.append({
                'type_name': t['type_name'],
                'category_name': t['ref_categories']['category_name'] if t.get('ref_categories') else None
            })
        companies = get_reference_data(TABLES['REF_COMPANIES'])
        owners = get_reference_data(TABLES['REF_OWNERS'])
        locations = get_reference_data(TABLES['REF_LOCATION'])
        business_units = get_reference_data(TABLES['REF_BISNIS_UNIT'])

        category_names = [c.get('category_name', '') for c in categories]
        company_names = [c.get('company_name', '') for c in companies]
        owner_names = [o.get('owner_name', '') for o in owners]
        business_unit_names = [b.get('business_unit_name', '') for b in business_units]
        location_dict = {}
        for loc in locations:
            location_name = loc.get('location_name')
            if location_name:
                location_dict.setdefault(location_name, []).append(loc.get('room_name', ''))
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

def get_reference_value(table_name, lookup_column, lookup_value, return_column):
    try:
        supabase = get_supabase()
        response = supabase.table(table_name).select(return_column).eq(lookup_column, lookup_value).execute()
        return response.data[0][return_column] if response.data else None
    except Exception as e:
        logging.error(f"Error getting reference value: {str(e)}")
        return None

def add_asset(asset_data):
    try:
        supabase = get_supabase()
        
        # Convert name fields to IDs for foreign keys
        processed_data = {}
        
        # Get foreign key IDs
        if asset_data.get('category_name'):
            cat_response = supabase.table('ref_categories').select('category_id').eq('category_name', asset_data['category_name']).execute()
            if cat_response.data:
                processed_data['category_id'] = cat_response.data[0]['category_id']
        
        if asset_data.get('type_name'):
            type_response = supabase.table('ref_asset_types').select('asset_type_id').eq('type_name', asset_data['type_name']).execute()
            if type_response.data:
                processed_data['asset_type_id'] = type_response.data[0]['asset_type_id']
        
        if asset_data.get('company_name'):
            comp_response = supabase.table('ref_companies').select('company_id').eq('company_name', asset_data['company_name']).execute()
            if comp_response.data:
                processed_data['company_id'] = comp_response.data[0]['company_id']
        
        if asset_data.get('business_unit_name'):
            unit_response = supabase.table('ref_business_units').select('business_unit_id').eq('business_unit_name', asset_data['business_unit_name']).execute()
            if unit_response.data:
                processed_data['business_unit_id'] = unit_response.data[0]['business_unit_id']
        
        if asset_data.get('location_name') and asset_data.get('room_name'):
            loc_response = supabase.table('ref_locations').select('location_id').eq('location_name', asset_data['location_name']).eq('room_name', asset_data['room_name']).execute()
            if loc_response.data:
                processed_data['location_id'] = loc_response.data[0]['location_id']
        
        if asset_data.get('owner_name'):
            owner_response = supabase.table('ref_owners').select('owner_id').eq('owner_name', asset_data['owner_name']).execute()
            if owner_response.data:
                processed_data['owner_id'] = owner_response.data[0]['owner_id']
        
        # Generate asset_tag using existing format
        def generate_asset_tag(company_name, category_name, type_name, owner_name, purchase_date):
            try:
                # Get codes from reference tables
                code_company = get_reference_value('ref_companies', 'company_name', company_name, 'company_code')
                code_category = get_reference_value('ref_categories', 'category_name', category_name, 'category_code')
                code_type = get_reference_value('ref_asset_types', 'type_name', type_name, 'type_code')
                code_owner = get_reference_value('ref_owners', 'owner_name', owner_name, 'owner_code')
                
                year = datetime.strptime(purchase_date, "%Y-%m-%d").year if isinstance(purchase_date, str) else purchase_date.year
                year_2digit = str(year)[-2:]
                
                if all([code_company, code_category, code_type, code_owner]):
                    # Get sequence number for this combination
                    pattern = f"{code_company}-{code_category}{code_type}.{code_owner}{year_2digit}.%"
                    existing = supabase.table(TABLES['ASSETS']).select('asset_tag').like('asset_tag', pattern).execute()
                    seq_num = str(len(existing.data) + 1).zfill(3)
                    return f"{code_company}-{code_category}{code_type}.{code_owner}{year_2digit}.{seq_num}"
            except Exception as e:
                logging.error(f"Error generating asset tag: {str(e)}")
            return None
        
        processed_data['asset_tag'] = generate_asset_tag(
            asset_data.get('company_name'),
            asset_data.get('category_name'), 
            asset_data.get('type_name'),
            asset_data.get('owner_name'),
            asset_data.get('purchase_date')
        )
        
        # Calculate financial values
        def calculate_asset_financials(purchase_cost, purchase_date, category_name):
            try:
                residual_percent = float(get_reference_value('ref_categories', 'category_name', category_name, 'residual_percent') or 0)
                useful_life = int(get_reference_value('ref_categories', 'category_name', category_name, 'useful_life') or 0)
                purchase_year = datetime.strptime(purchase_date, "%Y-%m-%d").year if isinstance(purchase_date, str) else purchase_date.year
                current_year = datetime.now().year
                years_used = current_year - purchase_year
                purchase_cost = float(purchase_cost)
                residual_value = purchase_cost * (residual_percent / 100)
                depreciation = ((purchase_cost - residual_value) / useful_life) * years_used if years_used < useful_life else (purchase_cost - residual_value)
                book_value = purchase_cost - depreciation
                return {
                    'residual_percent': residual_percent,
                    'residual_value': round(residual_value, 2),
                    'useful_life': useful_life,
                    'depreciation_value': round(depreciation, 2),
                    'book_value': round(book_value, 2),
                    'year': purchase_year
                }
            except Exception as e:
                logging.error(f"Error calculating financials: {str(e)}")
                return {}
        
        # Add financial calculations
        if asset_data.get('purchase_cost') and asset_data.get('purchase_date') and asset_data.get('category_name'):
            financials = calculate_asset_financials(
                asset_data.get('purchase_cost'),
                asset_data.get('purchase_date'),
                asset_data.get('category_name')
            )
            processed_data.update(financials)
        
        # Copy other fields (only fields that exist in assets table)
        valid_fields = ['asset_name', 'manufacture', 'model', 'serial_number', 'room_name', 'notes', 'item_condition', 'purchase_date', 'purchase_cost', 'warranty', 'supplier', 'journal', 'status', 'photo_url']
        for field in valid_fields:
            if field in asset_data:
                processed_data[field] = asset_data[field]
        
        response = supabase.table(TABLES['ASSETS']).insert(processed_data).execute()
        invalidate_cache()
        return True
    except Exception as e:
        logging.error(f"Error adding asset: {str(e)}")
        return False

def update_asset(asset_id, update_data):
    try:
        supabase = get_supabase()
        response = supabase.table(TABLES['ASSETS']).update(update_data).eq('asset_id', asset_id).execute()
        invalidate_cache()
        return True
    except Exception as e:
        logging.error(f"Error updating asset: {str(e)}")
        return False

def get_all_approvals():
    try:
        supabase = get_supabase()
        response = supabase.table(TABLES['APPROVALS']).select('*').execute()
        return response.data
    except Exception as e:
        logging.error(f"Error getting approvals: {str(e)}")
        return []

def add_approval_request(approval_data):
    try:
        supabase = get_supabase()
        response = supabase.table(TABLES['APPROVALS']).insert(approval_data).execute()
        return True
    except Exception as e:
        logging.error(f"Error adding approval request: {str(e)}")
        return False

def update_approval_status(approval_id, status, approved_by, notes=''):
    try:
        supabase = get_supabase()
        update_data = {
            'status': status,
            'approved_by': approved_by,
            'approved_date': datetime.now().isoformat(),
            'notes': notes
        }
        response = supabase.table(TABLES['APPROVALS']).update(update_data).eq('approval_id', approval_id).execute()
        return True
    except Exception as e:
        logging.error(f"Error updating approval status: {str(e)}")
        return False

def add_damage_log(damage_data):
    try:
        supabase = get_supabase()
        response = supabase.table(TABLES['DAMAGE_LOG']).insert(damage_data).execute()
        return True
    except Exception as e:
        logging.error(f"Error adding damage log: {str(e)}")
        return False

def add_repair_log(repair_data):
    try:
        supabase = get_supabase()
        response = supabase.table(TABLES['REPAIR_LOG']).insert(repair_data).execute()
        return True
    except Exception as e:
        logging.error(f"Error adding repair log: {str(e)}")
        return False

def get_damage_logs():
    try:
        supabase = get_supabase()
        response = supabase.table(TABLES['DAMAGE_LOG']).select('*').execute()
        return response.data
    except Exception as e:
        logging.error(f"Error getting damage logs: {str(e)}")
        return []

def get_repair_logs():
    try:
        supabase = get_supabase()
        response = supabase.table(TABLES['REPAIR_LOG']).select('*').execute()
        return response.data
    except Exception as e:
        logging.error(f"Error getting repair logs: {str(e)}")
        return []

def get_summary_data():
    assets = get_all_assets()
    total_purchase_value = 0
    for asset in assets:
        try:
            purchase_cost = float(asset.get("purchase_cost", 0) or 0)
            total_purchase_value += purchase_cost
        except Exception:
            continue
    return {
        "total_purchase_value": total_purchase_value,
        "total_assets": len(assets)
    }

def get_chart_data():
    assets = get_all_assets()
    now = datetime.now()
    
    # Status counts
    status_counts = {"Active": 0, "Damaged": 0, "Disposed": 0, "Lost": 0}
    for asset in assets:
        status = asset.get("status", "Active")
        status_counts[status] = status_counts.get(status, 0) + 1

    # Category counts
    category_counts = {}
    for asset in assets:
        cat_data = asset.get("ref_categories")
        if cat_data:
            cat_name = cat_data.get("category_name", "Unknown") if isinstance(cat_data, dict) else "Unknown"
        else:
            cat_name = "Unknown"
        category_counts[cat_name] = category_counts.get(cat_name, 0) + 1

    # Location counts
    location_counts = {}
    for asset in assets:
        loc_data = asset.get("ref_locations")
        if loc_data:
            loc_name = loc_data.get("location_name", "Unknown") if isinstance(loc_data, dict) else "Unknown"
        else:
            loc_name = "Unknown"
        location_counts[loc_name] = location_counts.get(loc_name, 0) + 1

    # Monthly chart (last 12 months)
    monthly_counts = {}
    for i in range(11, -1, -1):
        month = (now.replace(day=1) - relativedelta(months=i)).strftime("%b %Y")
        monthly_counts[month] = 0

    # Quarterly chart (last 4 quarters)
    quarterly_counts = {}
    for i in range(3, -1, -1):
        year = now.year
        quarter = ((now.month - 1) // 3 + 1) - i
        if quarter <= 0:
            year -= 1
            quarter += 4
        quarterly_counts[f"Q{quarter} {year}"] = 0

    # Yearly chart - will be populated with actual data
    yearly_counts = {}

    # Count assets by purchase_date
    for asset in assets:
        purchase_date = asset.get("purchase_date")
        if purchase_date:
            try:
                if isinstance(purchase_date, str):
                    dt = datetime.strptime(purchase_date, "%Y-%m-%d")
                else:
                    dt = purchase_date
                
                # Monthly count
                month_key = dt.strftime("%b %Y")
                if month_key in monthly_counts:
                    monthly_counts[month_key] += 1
                
                # Quarterly count
                quarter = (dt.month - 1) // 3 + 1
                quarter_key = f"Q{quarter} {dt.year}"
                if quarter_key in quarterly_counts:
                    quarterly_counts[quarter_key] += 1
                
                # Yearly count - add all years found in data
                year_key = str(dt.year)
                if year_key not in yearly_counts:
                    yearly_counts[year_key] = 0
                yearly_counts[year_key] += 1
                    
            except Exception as e:
                logging.error(f"Error parsing date {purchase_date}: {str(e)}")
                continue
    
    # Sort yearly data by year and keep only relevant years
    sorted_years = sorted([int(year) for year in yearly_counts.keys()])
    if sorted_years:
        # Keep from earliest year to current year, but limit to reasonable range
        min_year = max(sorted_years[0], now.year - 10)  # Max 10 years back
        max_year = now.year
        
        filtered_yearly = {}
        for year in range(min_year, max_year + 1):
            filtered_yearly[str(year)] = yearly_counts.get(str(year), 0)
        yearly_counts = filtered_yearly

    return {
        "status_counts": status_counts,
        "category_counts": category_counts,
        "location_counts": location_counts,
        "monthly_counts": monthly_counts,
        "quarterly_counts": quarterly_counts,
        "yearly_counts": yearly_counts
    }

def invalidate_cache():
    cache.invalidate_all()
    logging.info("Cache invalidated, data will be refreshed from database")