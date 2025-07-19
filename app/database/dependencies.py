from fastapi import Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from jose import JWTError, jwt
import logging

from app.database.database import get_db
from app.database.models import User, UserRole
from app.config import load_config

# Load configuration
config = load_config()

def get_token_from_request(request: Request) -> str:
    """Get token from request headers or cookies."""
    # Try to get token from Authorization header
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header.split(" ", 1)[1]
    
    # Try to get token from cookies
    token = request.cookies.get("access_token")
    return token

def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """Get current user from JWT token."""
    token = get_token_from_request(request)
    
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    if not token:
        logging.warning("No token found in request")
        raise credentials_exception
    
    try:
        # Decode token
        payload = jwt.decode(
            token, 
            config.SECRET_KEY, 
            algorithms=["HS256"]
        )
        
        username: str = payload.get("sub")
        if username is None:
            logging.warning("No username in token payload")
            raise credentials_exception
            
    except JWTError as e:
        logging.error(f"JWT Error: {str(e)}")
        raise credentials_exception
    
    # Get user from database
    user = db.query(User).filter(User.username == username).first()
    
    if user is None:
        logging.warning(f"User {username} not found in database")
        raise credentials_exception
    
    if not user.is_active:
        logging.warning(f"User {username} is inactive")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user"
        )
    
    return user

def get_current_active_user(current_user: User = Depends(get_current_user)) -> User:
    """Get current active user."""
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user

def get_admin_user(current_user: User = Depends(get_current_user)) -> User:
    """Get current admin user."""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    return current_user