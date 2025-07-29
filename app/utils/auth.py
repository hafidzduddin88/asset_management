from fastapi import Depends, HTTPException, status, Request
from supabase import create_client, Client
from app.config import load_config
import logging

config = load_config()
supabase: Client = create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_KEY)

class CurrentUser:
    def __init__(self, id: str, email: str, username: str, role: str, full_name: str = None):
        self.id = id
        self.email = email
        self.username = username
        self.role = role
        self.full_name = full_name

async def get_current_user(request: Request) -> CurrentUser:
    token = request.cookies.get("sb_access_token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )
    
    try:
        # Verify JWT token with Supabase secret
        from jose import jwt
        payload = jwt.decode(token, config.SECRET_KEY, algorithms=["HS256"])
        user_id = payload.get("sub")
        
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token"
            )
        
        profile_response = supabase.table('profiles').select('*').eq('id', user_id).single().execute()
        if not profile_response.data or not profile_response.data.get('is_active'):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Account inactive"
            )
        
        return CurrentUser(
            id=user_id,
            email=payload.get('email', ''),
            username=profile_response.data.get('username', payload.get('email', '')),
            role=profile_response.data.get('role', 'staff'),
            full_name=profile_response.data.get('full_name')
        )
    except Exception as e:
        logging.error(f"Auth error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed"
        )

def get_admin_user(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if current_user.role != 'admin':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    return current_user