# Legacy Google Sheets integration - DEPRECATED
# This module has been replaced by database_manager.py using Supabase
# Kept for compatibility but not actively used

import logging

def invalidate_cache():
    """Legacy function - now handled by database_manager"""
    logging.warning("sheets.py is deprecated - use database_manager.py instead")
    pass