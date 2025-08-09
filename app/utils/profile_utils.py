from supabase import create_client
from app.config import load_config
import logging

config = load_config()

def create_profile_if_not_exists(user_id: str, user_email: str, user_metadata: dict = None) -> bool:
    """Create profile only when explicitly needed (e.g., first login). Never updates existing profiles."""
    try:
        admin_supabase = create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_KEY)
        
        # Check if profile exists
        response = admin_supabase.table("profiles").select("id").eq("id", user_id).execute()
        
        if not response.data:
            # Get business_unit_id from name if provided
            business_unit_id = None
            business_unit_name = user_metadata.get('business_unit_name') if user_metadata else None
            
            if business_unit_name:
                bu_response = admin_supabase.table("ref_business_units").select("business_unit_id").eq("business_unit_name", business_unit_name).execute()
                if bu_response.data:
                    business_unit_id = bu_response.data[0]['business_unit_id']
            
            profile_data = {
                "id": user_id,
                "username": user_email,
                "full_name": user_metadata.get('full_name') if user_metadata else None,
                "role": "staff",
                "is_active": True,
                "business_unit_id": business_unit_id,
                "business_unit_name": business_unit_name,
                "email_verified": False
            }
            admin_supabase.table("profiles").insert(profile_data).execute()
            logging.info("Profile created successfully")
            return True
        else:
            logging.info(f"Profile already exists for user {user_id} - no operations performed")
            return False
        
    except Exception as e:
        logging.error(f"Failed to create profile: {type(e).__name__}")
        return False

# Cache to store original full_name values to prevent overwrites
_profile_cache = {}

def protect_profile_data(user_id: str) -> bool:
    """Ensure profile data is not overwritten by external sources"""
    try:
        admin_supabase = create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_KEY)
        
        # Get current profile
        response = admin_supabase.table("profiles").select("full_name, username, updated_at").eq("id", user_id).execute()
        
        if response.data:
            profile = response.data[0]
            current_full_name = profile.get('full_name')
            username = profile.get('username')
            updated_at = profile.get('updated_at')
            
            # Store original full_name in cache if not already stored
            if user_id not in _profile_cache and current_full_name and current_full_name != username:
                _profile_cache[user_id] = current_full_name
            
            # Check if full_name was overwritten with username (which contains email)
            needs_protection = (current_full_name == username)
            
            if needs_protection:
                # Restore from cache if available, otherwise set to None
                restore_value = _profile_cache.get(user_id)
                admin_supabase.table("profiles").update({
                    "full_name": restore_value
                }).eq("id", user_id).execute()
                return True
        
        return False
        
    except Exception as e:
        logging.error(f"Failed to protect profile data: {type(e).__name__}")
        return False