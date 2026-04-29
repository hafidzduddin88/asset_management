"""
Helper function to get assigned user name for assets
"""
import logging
from app.utils.supabase_client import supabase_client

def get_assigned_user_name(user_id):
    """Get user full name by ID for display"""
    if not user_id:
        return None
    
    try:
        supabase = supabase_client.client
        response = supabase.table('profiles').select('full_name, username').eq('id', user_id).execute()
        if response.data:
            user = response.data[0]
            return user.get('full_name') or user.get('username')
        return None
    except Exception as e:
        logging.error(f"Error getting user name for {user_id}: {str(e)}")
        return None

def enrich_assets_with_user_names(assets):
    """
    Enrich list of assets with assigned user names
    More efficient than individual queries
    """
    if not assets:
        return assets
    
    try:
        supabase = supabase_client.client
        
        # Collect all unique user IDs
        user_ids = list(set([
            asset.get('assigned_user_id') 
            for asset in assets 
            if asset.get('assigned_user_id')
        ]))
        
        if not user_ids:
            return assets
        
        # Fetch all users in one query
        users_response = supabase.table('profiles').select('id, full_name, username').in_('id', user_ids).execute()
        users_dict = {user['id']: user for user in users_response.data}
        
        # Attach user info to each asset
        for asset in assets:
            user_id = asset.get('assigned_user_id')
            if user_id and user_id in users_dict:
                asset['assigned_user'] = users_dict[user_id]
                asset['assigned_user_name'] = users_dict[user_id].get('full_name') or users_dict[user_id].get('username')
        
        return assets
    except Exception as e:
        logging.error(f"Error enriching assets with user names: {str(e)}")
        return assets
