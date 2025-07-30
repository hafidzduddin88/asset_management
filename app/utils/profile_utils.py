from supabase import create_client
from app.config import load_config
import logging

config = load_config()

def create_profile_if_not_exists(user_id: str, user_email: str) -> bool:
    """Create profile only when explicitly needed (e.g., first login)."""
    try:
        admin_supabase = create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_KEY)
        
        # Check if profile exists
        response = admin_supabase.table("profiles").select("id").eq("id", user_id).execute()
        
        if not response.data:
            # Create profile with basic data
            profile_data = {
                "id": user_id,
                "username": user_email,
                "full_name": "",
                "role": "staff",
                "is_active": True
            }
            admin_supabase.table("profiles").insert(profile_data).execute()
            logging.info(f"Profile created for user {user_email}")
            return True
        
        return False
        
    except Exception as e:
        logging.error(f"Failed to create profile: {e}")
        return False