"""
Simple in-memory cache implementation.
"""
import time
from typing import Dict, Any, Optional, Callable, Tuple

class Cache:
    """Simple in-memory cache with expiration."""
    
    def __init__(self, default_ttl: int = 300):
        """Initialize cache with default TTL in seconds."""
        self._cache: Dict[str, Tuple[Any, float]] = {}
        self._default_ttl = default_ttl
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache if it exists and is not expired."""
        if key not in self._cache:
            return None
        
        value, expiry = self._cache[key]
        if expiry < time.time():
            # Expired
            del self._cache[key]
            return None
            
        return value
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Set value in cache with expiration time."""
        ttl = ttl if ttl is not None else self._default_ttl
        expiry = time.time() + ttl
        self._cache[key] = (value, expiry)
    
    def delete(self, key: str) -> None:
        """Delete key from cache."""
        if key in self._cache:
            del self._cache[key]
    
    def clear(self) -> None:
        """Clear all cache."""
        self._cache.clear()
        
    def invalidate_all(self) -> None:
        """Alias for clear() to invalidate all cache entries."""
        self.clear()
    
    def get_or_set(self, key: str, getter: Callable[[], Any], ttl: Optional[int] = None) -> Any:
        """Get value from cache or set it if not exists."""
        value = self.get(key)
        if value is None:
            value = getter()
            self.set(key, value, ttl)
        return value

# Create global cache instance
cache = Cache()