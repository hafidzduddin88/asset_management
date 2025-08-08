from supabase import create_client
from app.config import load_config
import logging

config = load_config()

def create_profile_if_not_exists(user_id: str, user_email: str, user_metadata: dict = None) -> bool:
    """Create profile only when explicitly needed (e.g., first login)."""
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
            
            # Create profile with basic data
            profile_data = {
                "id": user_id,
                "username": user_email,
                "full_name": user_metadata.get('full_name', '') if user_metadata else '',
                "role": "staff",
                "is_active": True,
                "business_unit_id": business_unit_id,
                "business_unit_name": business_unit_name
            }
            admin_supabase.table("profiles").insert(profile_data).execute()
            logging.info("Profile created successfully")
            return True
        
        return False
        
    except Exception as e:
        logging.error(f"Failed to create profile: {type(e).__name__}")
        return False