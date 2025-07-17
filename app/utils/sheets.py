# app/utils/sheets.py
import gspread
from google.oauth2.service_account import Credentials
from app.config import load_config
from typing import List, Dict, Any

config = load_config()

def get_sheets_client():
    """Get Google Sheets client."""
    creds = Credentials.from_service_account_info(
        config.GOOGLE_CREDS_JSON,
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
    )
    
    return gspread.authorize(creds)

def get_assets_from_sheet() -> List[Dict[str, Any]]:
    """Get assets from Google Sheet."""
    if not config.GOOGLE_SHEET_ID:
        return []
    
    try:
        client = get_sheets_client()
        sheet = client.open_by_key(config.GOOGLE_SHEET_ID).sheet1
        
        # Get all records
        records = sheet.get_all_records()
        return records
    except Exception as e:
        print(f"Error getting assets from sheet: {str(e)}")
        return []

def add_asset_to_sheet(asset_data: Dict[str, Any]) -> bool:
    """Add asset to Google Sheet."""
    if not config.GOOGLE_SHEET_ID:
        return False
    
    try:
        client = get_sheets_client()
        sheet = client.open_by_key(config.GOOGLE_SHEET_ID).sheet1
        
        # Get headers
        headers = sheet.row_values(1)
        
        # Prepare row data
        row_data = []
        for header in headers:
            if header in asset_data:
                row_data.append(asset_data[header])
            else:
                row_data.append("")
        
        # Append row
        sheet.append_row(row_data)
        return True
    except Exception as e:
        print(f"Error adding asset to sheet: {str(e)}")
        return False

def update_asset_in_sheet(asset_tag: str, asset_data: Dict[str, Any]) -> bool:
    """Update asset in Google Sheet."""
    if not config.GOOGLE_SHEET_ID:
        return False
    
    try:
        client = get_sheets_client()
        sheet = client.open_by_key(config.GOOGLE_SHEET_ID).sheet1
        
        # Get headers
        headers = sheet.row_values(1)
        
        # Find asset by tag
        cell = sheet.find(asset_tag)
        if not cell:
            return False
        
        # Update row
        for i, header in enumerate(headers):
            if header in asset_data:
                sheet.update_cell(cell.row, i + 1, asset_data[header])
        
        return True
    except Exception as e:
        print(f"Error updating asset in sheet: {str(e)}")
        return False