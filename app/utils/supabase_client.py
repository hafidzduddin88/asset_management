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
            # Create table SQL
            columns_sql = ", ".join([f"{col} {dtype}" for col, dtype in columns.items()])
            create_table_sql = f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
                id SERIAL PRIMARY KEY,
                {columns_sql},
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                created_by TEXT,
                updated_by TEXT
            );
            """
            
            # Enable RLS
            rls_sql = f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY;"
            
            # Create RLS policy - only admin and manager can modify
            policy_sql = f"""
            CREATE POLICY IF NOT EXISTS "{table_name}_policy" ON {table_name}
            FOR ALL USING (
                auth.jwt() ->> 'role' IN ('admin', 'manager')
            );
            """
            
            self.client.rpc('exec_sql', {'sql': create_table_sql}).execute()
            self.client.rpc('exec_sql', {'sql': rls_sql}).execute()
            self.client.rpc('exec_sql', {'sql': policy_sql}).execute()
            
            return True
        except Exception as e:
            print(f"Error creating table: {e}")
            return False
    
    def insert_data(self, table_name: str, data: List[Dict[str, Any]], user_email: str) -> bool:
        """Insert data to table"""
        try:
            # Add metadata
            for row in data:
                row['created_by'] = user_email
                row['updated_by'] = user_email
            
            result = self.client.table(table_name).insert(data).execute()
            return True
        except Exception as e:
            print(f"Error inserting data: {e}")
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