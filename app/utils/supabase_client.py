import os
from supabase import create_client, Client
from typing import Dict, List, Any, Optional

class SupabaseClient:
    def __init__(self):
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_SERVICE_KEY")
        self.client: Client = create_client(url, key)
    
    def create_table_if_not_exists(self, table_name: str, columns: Dict[str, str]) -> bool:
        """Check if table exists - Supabase tables must be created manually"""
        try:
            # Try a simple select to check if table exists
            result = self.client.table(table_name).select('*').limit(1).execute()
            print(f"Table {table_name} exists and is accessible")
            return True
        except Exception as e:
            print(f"Table {table_name} does not exist or is not accessible: {e}")
            return False
    
    def insert_data(self, table_name: str, data: List[Dict[str, Any]], user_email: str) -> bool:
        """Insert data to table"""
        try:
            # Add metadata
            for row in data:
                row['created_by'] = user_email
                row['updated_by'] = user_email
                row['created_at'] = 'now()'
                row['updated_at'] = 'now()'
            
            # Try to insert data - Supabase will auto-create table if it doesn't exist
            # when using the dashboard or if you have the right permissions
            result = self.client.table(table_name).insert(data).execute()
            print(f"Successfully inserted {len(data)} rows to {table_name}")
            return True
        except Exception as e:
            print(f"Error inserting data to {table_name}: {e}")
            # If table doesn't exist, provide helpful error message
            if "relation" in str(e) and "does not exist" in str(e):
                print(f"Please create table '{table_name}' manually in Supabase dashboard first")
            return False
    
    def get_table_data(self, table_name: str) -> List[Dict[str, Any]]:
        """Get all data from table"""
        try:
            result = self.client.table(table_name).select("*").execute()
            return result.data
        except Exception as e:
            print(f"Error getting data: {e}")
            return []

supabase_client = SupabaseClient()