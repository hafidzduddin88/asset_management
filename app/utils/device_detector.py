"""
Device Detection Utility for Template Routing
Detects mobile vs desktop devices and routes to appropriate templates
"""

import re
from typing import Optional
from fastapi import Request

class DeviceDetector:
    """Utility class to detect device type and route templates accordingly"""
    
    # Mobile user agent patterns
    MOBILE_PATTERNS = [
        r'Mobile', r'Android', r'iPhone', r'iPad', r'iPod',
        r'BlackBerry', r'Windows Phone', r'Opera Mini',
        r'IEMobile', r'Mobile Safari', r'webOS'
    ]
    
    # Tablet patterns (treated as mobile for our purposes)
    TABLET_PATTERNS = [
        r'iPad', r'Android.*Tablet', r'Kindle', r'Silk',
        r'PlayBook', r'Tablet'
    ]
    
    @classmethod
    def is_mobile_device(cls, request: Request) -> bool:
        """
        Detect if the request is from a mobile device
        
        Args:
            request: FastAPI Request object
            
        Returns:
            bool: True if mobile device, False otherwise
        """
        user_agent = request.headers.get('user-agent', '').lower()
        
        # Check for mobile patterns
        mobile_patterns = cls.MOBILE_PATTERNS + cls.TABLET_PATTERNS
        for pattern in mobile_patterns:
            if re.search(pattern.lower(), user_agent):
                return True
        
        # Check screen width if available (from JavaScript)
        screen_width = request.headers.get('x-screen-width')
        if screen_width and int(screen_width) < 768:
            return True
            
        return False
    
    @classmethod
    def get_template_path(cls, request: Request, base_template: str) -> str:
        """
        Get the appropriate template path based on device type
        
        Args:
            request: FastAPI Request object
            base_template: Base template name (e.g., 'assets.html')
            
        Returns:
            str: Full template path for the device type
        """
        if cls.is_mobile_device(request):
            return f"templates_mobile/{base_template}"
        else:
            return f"templates_desktop/{base_template}"
    
    @classmethod
    def get_device_type(cls, request: Request) -> str:
        """
        Get device type as string
        
        Args:
            request: FastAPI Request object
            
        Returns:
            str: 'mobile' or 'desktop'
        """
        return 'mobile' if cls.is_mobile_device(request) else 'desktop'
    
    @classmethod
    def force_device_type(cls, request: Request, force_type: Optional[str] = None) -> str:
        """
        Force a specific device type (useful for testing)
        
        Args:
            request: FastAPI Request object
            force_type: 'mobile' or 'desktop' to force specific type
            
        Returns:
            str: Device type
        """
        if force_type and force_type in ['mobile', 'desktop']:
            return force_type
        
        return cls.get_device_type(request)

# Convenience functions for route handlers
def get_template(request: Request, template_name: str, force_device: Optional[str] = None) -> str:
    """
    Convenience function to get template path
    
    Args:
        request: FastAPI Request object
        template_name: Template name (e.g., 'assets.html')
        force_device: Optional device type to force
        
    Returns:
        str: Template path
    """
    device_type = DeviceDetector.force_device_type(request, force_device)
    return f"templates_{device_type}/{template_name}"

def is_mobile(request: Request) -> bool:
    """
    Convenience function to check if mobile
    
    Args:
        request: FastAPI Request object
        
    Returns:
        bool: True if mobile
    """
    return DeviceDetector.is_mobile_device(request)

def get_device_info(request: Request) -> dict:
    """
    Get comprehensive device information
    
    Args:
        request: FastAPI Request object
        
    Returns:
        dict: Device information
    """
    user_agent = request.headers.get('user-agent', '')
    device_type = DeviceDetector.get_device_type(request)
    
    return {
        'device_type': device_type,
        'is_mobile': device_type == 'mobile',
        'user_agent': user_agent,
        'template_prefix': f'templates_{device_type}'
    }