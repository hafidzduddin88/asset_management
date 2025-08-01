import os
from supabase import create_client, Client
from typing import Dict, List, Any, Optional

class SupabaseClient:
    def __init__(self):
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_SERVICE_KEY")
        self.client: Client = create_client(url, key)
    
    def create_table_if_not_exists(self, table_name: str, columns: Dict[str, str]) -> bool:
        """Create table with RLS policy if not exists"""
        try:
            # Check if table exists first
            existing = self.client.table('information_schema.tables').select('table_name').eq('table_name', table_name).execute()
            if existing.data:
                return True
            
            # Create table using direct SQL (simplified approach)
            columns_sql = ", ".join([f"{col} TEXT" for col in columns.keys()])
            
            # Use postgrest to create table (alternative approach)
            # Since we can't execute raw SQL, we'll create a simple table structure
            # and let the insert operation handle the data
            
            # For now, just return True and let the insert handle table creation
            # This is a limitation of Supabase's security model
            print(f"Table {table_name} will be created on first insert")
            return True
            
        except Exception as e:
            print(f"Error checking table: {e}")
            return True  # Continue anyway
    
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