# app/utils/cache.py
from functools import wraps
import time
from typing import Any, Callable, Dict, Optional, TypeVar, cast

T = TypeVar("T")

# Simple in-memory cache
_cache: Dict[str, Dict[str, Any]] = {}

def cache(ttl_seconds: int = 300):
    """Cache decorator with TTL."""
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            # Create cache key from function name and arguments
            key = f"{func.__name__}:{str(args)}:{str(kwargs)}"
            
            # Check if result is in cache and not expired
            if key in _cache:
                entry = _cache[key]
                if entry["expires"] > time.time():
                    return cast(T, entry["value"])
            
            # Call function and cache result
            result = func(*args, **kwargs)
            _cache[key] = {
                "value": result,
                "expires": time.time() + ttl_seconds
            }
            
            return result
        return wrapper
    return decorator

def clear_cache(prefix: Optional[str] = None) -> int:
    """Clear cache entries with optional prefix."""
    global _cache
    
    if prefix is None:
        count = len(_cache)
        _cache = {}
        return count
    
    keys_to_delete = [key for key in _cache if key.startswith(prefix)]
    for key in keys_to_delete:
        del _cache[key]
    
    return len(keys_to_delete)