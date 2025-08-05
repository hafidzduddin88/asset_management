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
            ref_business_units(unit_name),
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
        types_response = supabase.table(TABLES['REF_TYPES']).select('type_name, category_name').execute()
        types = types_response.data if types_response.data else []
        companies = get_reference_data(TABLES['REF_COMPANIES'])
        owners = get_reference_data(TABLES['REF_OWNERS'])
        locations = get_reference_data(TABLES['REF_LOCATION'])
        business_units = get_reference_data(TABLES['REF_BISNIS_UNIT'])

        category_names = [c.get('category_name', '') for c in categories]
        company_names = [c.get('company_name', '') for c in companies]
        owner_names = [o.get('owner_name', '') for o in owners]
        business_unit_names = [b.get('unit_name', '') for b in business_units]
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
    data = get_reference_data(table_name)
    for row in data:
        if row.get(lookup_column) == lookup_value:
            return row.get(return_column)
    return None

def add_asset(asset_data):
    try:
        supabase = get_supabase()
        response = supabase.table(TABLES['ASSETS']).insert(asset_data).execute()
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

    # Monthly purchase chart (last 12 months)
    monthly_counts = {}
    now = datetime.now()
    for i in range(11, -1, -1):
        month = (now.replace(day=1) - relativedelta(months=i)).strftime("%b %Y")
        monthly_counts[month] = 0

    for asset in assets:
        purchase_date = asset.get("purchase_date")
        if purchase_date:
            try:
                if isinstance(purchase_date, str):
                    dt = datetime.strptime(purchase_date, "%Y-%m-%d")
                else:
                    dt = purchase_date
                month_key = dt.strftime("%b %Y")
                if month_key in monthly_counts:
                    monthly_counts[month_key] += 1
            except Exception:
                continue

    return {
        "status_counts": status_counts,
        "category_counts": category_counts,
        "location_counts": location_counts,
        "monthly_counts": monthly_counts
    }

def invalidate_cache():
    cache.invalidate_all()
    logging.info("Cache invalidated, data will be refreshed from database")