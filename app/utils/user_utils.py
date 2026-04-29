"""
User utilities for IT asset assignment
"""
import logging
from app.utils.supabase_client import supabase_client

def get_all_users():
    """Get all active users for IT asset assignment"""
    try:
        supabase = supabase_client.client
        response = supabase.table('profiles').select('id, full_name, username, email, business_unit_name, role').eq('is_active', True).order('full_name').execute()
        return response.data
    except Exception as e:
        logging.error(f"Error getting users: {str(e)}")
        return []

def get_user_by_id(user_id):
    """Get user details by ID"""
    try:
        supabase = supabase_client.client
        response = supabase.table('profiles').select('id, full_name, username, email, business_unit_name, role').eq('id', user_id).execute()
        return response.data[0] if response.data else None
    except Exception as e:
        logging.error(f"Error getting user {user_id}: {str(e)}")
        return None

def get_user_assets(user_id):
    """Get all assets assigned to a specific user"""
    try:
        supabase = supabase_client.client
        response = supabase.table('assets').select('''
            asset_id, asset_name, asset_tag, status,
            ref_categories(category_name),
            ref_asset_types(type_name)
        ''').eq('assigned_user_id', user_id).eq('owner_type', 'IT').execute()
        return response.data
    except Exception as e:
        logging.error(f"Error getting user assets: {str(e)}")
        return []
