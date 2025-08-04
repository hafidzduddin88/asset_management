"""
Migrate data directly from Google Sheets to Supabase
"""
import os
import gspread
import pandas as pd
from google.oauth2.service_account import Credentials
from supabase import create_client, Client
import logging
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SheetsToSupabaseMigrator:
    def __init__(self):
        # Supabase client
        self.supabase: Client = create_client(
            os.getenv("SUPABASE_URL"),
            os.getenv("SUPABASE_SERVICE_KEY")
        )
        
        # Google Sheets client
        creds = Credentials.from_service_account_info(
            json.loads(os.getenv("GOOGLE_CREDS_JSON")),
            scopes=[
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive"
            ]
        )
        self.sheets_client = gspread.authorize(creds)
        self.spreadsheet = self.sheets_client.open_by_key(os.getenv("GOOGLE_SHEET_ID"))
        self.id_mappings = {}
    
    def get_sheet_data(self, sheet_name):
        """Get data from Google Sheet"""
        try:
            worksheet = self.spreadsheet.worksheet(sheet_name)
            return pd.DataFrame(worksheet.get_all_records())
        except Exception as e:
            logger.error(f"Error getting sheet {sheet_name}: {e}")
            return pd.DataFrame()
    
    def migrate_all(self):
        """Migrate all data from Google Sheets to Supabase"""
        try:
            # Reference data first
            self.migrate_companies()
            self.migrate_categories()
            self.migrate_owners()
            self.migrate_locations()
            self.migrate_business_units()
            self.migrate_asset_types()
            
            # Main data
            self.migrate_assets()
            self.migrate_approvals()
            self.migrate_damage_log()
            self.migrate_repair_log()
            
            logger.info("Migration completed successfully")
            
        except Exception as e:
            logger.error(f"Migration failed: {e}")
            raise
    
    def migrate_companies(self):
        """Migrate companies from Google Sheets"""
        df = self.get_sheet_data("Ref_Companies")
        if df.empty:
            return
        
        self.supabase.table("ref_companies").delete().neq("company_id", 0).execute()
        
        for _, row in df.iterrows():
            data = {
                "company_name": row["Company"],
                "company_code": row["Code Company"]
            }
            response = self.supabase.table("ref_companies").insert(data).execute()
            if response.data:
                self.id_mappings[f"company_{row['Company']}"] = response.data[0]['company_id']
        
        logger.info(f"Migrated {len(df)} companies")
    
    def migrate_categories(self):
        """Migrate categories from Google Sheets"""
        df = self.get_sheet_data("Ref_Categories")
        if df.empty:
            return
        
        self.supabase.table("ref_categories").delete().neq("category_id", 0).execute()
        
        for _, row in df.iterrows():
            data = {
                "category_name": row["Category"],
                "category_code": str(row["Code Category"]),
                "residual_percent": float(row["Residual Percent"]),
                "useful_life": int(row["Useful Life"])
            }
            response = self.supabase.table("ref_categories").insert(data).execute()
            if response.data:
                self.id_mappings[f"category_{row['Category']}"] = response.data[0]['category_id']
        
        logger.info(f"Migrated {len(df)} categories")
    
    def migrate_owners(self):
        """Migrate owners from Google Sheets"""
        df = self.get_sheet_data("Ref_Owners")
        if df.empty:
            return
        
        self.supabase.table("ref_owners").delete().neq("owner_id", 0).execute()
        
        for _, row in df.iterrows():
            data = {
                "owner_name": row["Owner"],
                "owner_code": row["Code Owner"]
            }
            response = self.supabase.table("ref_owners").insert(data).execute()
            if response.data:
                self.id_mappings[f"owner_{row['Owner']}"] = response.data[0]['owner_id']
        
        logger.info(f"Migrated {len(df)} owners")
    
    def migrate_locations(self):
        """Migrate locations from Google Sheets"""
        df = self.get_sheet_data("Ref_Location")
        if df.empty:
            return
        
        self.supabase.table("ref_locations").delete().neq("location_id", 0).execute()
        
        for _, row in df.iterrows():
            data = {
                "location_name": row["Location"],
                "room_name": row["Room"]
            }
            response = self.supabase.table("ref_locations").insert(data).execute()
            if response.data:
                key = f"location_{row['Location']}_{row['Room']}"
                self.id_mappings[key] = response.data[0]['location_id']
        
        logger.info(f"Migrated {len(df)} locations")
    
    def migrate_business_units(self):
        """Migrate business units from Google Sheets"""
        df = self.get_sheet_data("Ref_Bisnis_Unit")
        if df.empty:
            return
        
        self.supabase.table("ref_business_units").delete().neq("business_unit_id", 0).execute()
        
        for _, row in df.iterrows():
            company_id = self.id_mappings.get(f"company_{row['Company']}")
            if company_id:
                data = {
                    "unit_name": row["Bisnis Unit"],
                    "company_id": company_id
                }
                response = self.supabase.table("ref_business_units").insert(data).execute()
                if response.data:
                    self.id_mappings[f"business_unit_{row['Bisnis Unit']}"] = response.data[0]['business_unit_id']
        
        logger.info(f"Migrated {len(df)} business units")
    
    def migrate_asset_types(self):
        """Migrate asset types from Google Sheets"""
        df = self.get_sheet_data("Ref_Types")
        if df.empty:
            return
        
        self.supabase.table("ref_asset_types").delete().neq("asset_type_id", 0).execute()
        
        for _, row in df.iterrows():
            category_id = self.id_mappings.get(f"category_{row['Category']}")
            if category_id:
                data = {
                    "type_name": row["Type"],
                    "type_code": str(row["Code Type"]) if pd.notna(row["Code Type"]) else None,
                    "category_id": category_id
                }
                response = self.supabase.table("ref_asset_types").insert(data).execute()
                if response.data:
                    self.id_mappings[f"asset_type_{row['Type']}"] = response.data[0]['asset_type_id']
        
        logger.info(f"Migrated {len(df)} asset types")
    
    def migrate_assets(self):
        """Migrate assets from Google Sheets"""
        df = self.get_sheet_data("Assets")
        if df.empty:
            return
        
        self.supabase.table("assets").delete().neq("asset_id", 0).execute()
        
        batch_size = 50
        for i in range(0, len(df), batch_size):
            batch = df.iloc[i:i+batch_size]
            batch_data = []
            
            for _, row in batch.iterrows():
                # Get foreign key IDs
                category_id = self.id_mappings.get(f"category_{row['Category']}")
                asset_type_id = self.id_mappings.get(f"asset_type_{row['Type']}")
                company_id = self.id_mappings.get(f"company_{row['Company']}")
                business_unit_id = self.id_mappings.get(f"business_unit_{row['Bisnis Unit']}")
                owner_id = self.id_mappings.get(f"owner_{row['Owner']}")
                location_id = self.id_mappings.get(f"location_{row['Location']}_{row['Room']}")
                
                data = {
                    "asset_name": row["Item Name"],
                    "category_id": category_id,
                    "asset_type_id": asset_type_id,
                    "manufacture": row["Manufacture"] if pd.notna(row["Manufacture"]) else None,
                    "model": row["Model"] if pd.notna(row["Model"]) else None,
                    "serial_number": row["Serial Number"] if pd.notna(row["Serial Number"]) else None,
                    "asset_tag": row["Asset Tag"],
                    "company_id": company_id,
                    "business_unit_id": business_unit_id,
                    "location_id": location_id,
                    "room_name": row["Room"] if pd.notna(row["Room"]) else None,
                    "notes": row["Notes"] if pd.notna(row["Notes"]) else None,
                    "item_condition": row["Item Condition"],
                    "purchase_date": row["Purchase Date"] if pd.notna(row["Purchase Date"]) else None,
                    "purchase_cost": float(row["Purchase Cost"]) if pd.notna(row["Purchase Cost"]) else None,
                    "warranty": row["Warranty"] if pd.notna(row["Warranty"]) else None,
                    "supplier": row["Supplier"] if pd.notna(row["Supplier"]) else None,
                    "journal": row["Journal"] if pd.notna(row["Journal"]) else None,
                    "owner_id": owner_id,
                    "depreciation_value": float(row["Depreciation Value"]) if pd.notna(row["Depreciation Value"]) else None,
                    "residual_percent": float(row["Residual Percent"]) if pd.notna(row["Residual Percent"]) else None,
                    "residual_value": float(row["Residual Value"]) if pd.notna(row["Residual Value"]) else None,
                    "useful_life": int(row["Useful Life"]) if pd.notna(row["Useful Life"]) else None,
                    "book_value": float(row["Book Value"]) if pd.notna(row["Book Value"]) else None,
                    "status": row["Status"],
                    "year": int(row["Tahun"]) if pd.notna(row["Tahun"]) else None,
                    "photo_url": row["Photo URL"] if pd.notna(row["Photo URL"]) else None
                }
                batch_data.append(data)
            
            if batch_data:
                self.supabase.table("assets").insert(batch_data).execute()
        
        logger.info(f"Migrated {len(df)} assets")
    
    def migrate_approvals(self):
        """Migrate approvals from Google Sheets"""
        df = self.get_sheet_data("Approvals")
        if df.empty:
            logger.info("No approvals data to migrate")
            return
        
        self.supabase.table("approvals").delete().neq("approval_id", 0).execute()
        
        for _, row in df.iterrows():
            data = {
                "type": row["Type"],
                "asset_id": int(row["Asset_ID"]) if pd.notna(row["Asset_ID"]) else None,
                "asset_name": row["Asset_Name"],
                "status": row["Status"],
                "submitted_by": None,  # Will need user mapping
                "submitted_date": row["Submitted_Date"] if pd.notna(row["Submitted_Date"]) else None,
                "description": row["Description"] if pd.notna(row["Description"]) else None,
                "approved_by": None,  # Will need user mapping
                "approved_date": row["Approved_Date"] if pd.notna(row["Approved_Date"]) else None,
                "notes": row["Notes"] if pd.notna(row["Notes"]) else None
            }
            self.supabase.table("approvals").insert(data).execute()
        
        logger.info(f"Migrated {len(df)} approvals")
    
    def migrate_damage_log(self):
        """Migrate damage log from Google Sheets"""
        df = self.get_sheet_data("Damage_Log")
        if df.empty:
            logger.info("No damage log data to migrate")
            return
        
        self.supabase.table("damage_log").delete().neq("damage_log_id", 0).execute()
        
        for _, row in df.iterrows():
            data = {
                "asset_id": int(row["Asset_ID"]) if pd.notna(row["Asset_ID"]) else None,
                "asset_name": row["Asset_Name"],
                "damage_type": row["Damage_Type"] if pd.notna(row["Damage_Type"]) else None,
                "severity": row["Severity"] if pd.notna(row["Severity"]) else None,
                "description": row["Description"] if pd.notna(row["Description"]) else None,
                "reported_by": None,  # Will need user mapping
                "report_date": row["Report_Date"] if pd.notna(row["Report_Date"]) else None,
                "status": row["Status"],
                "notes": row["Notes"] if pd.notna(row["Notes"]) else None
            }
            self.supabase.table("damage_log").insert(data).execute()
        
        logger.info(f"Migrated {len(df)} damage logs")
    
    def migrate_repair_log(self):
        """Migrate repair log from Google Sheets"""
        df = self.get_sheet_data("Repair_Log")
        if df.empty:
            logger.info("No repair log data to migrate")
            return
        
        self.supabase.table("repair_log").delete().neq("repair_log_id", 0).execute()
        
        for _, row in df.iterrows():
            data = {
                "asset_id": int(row["Asset_ID"]) if pd.notna(row["Asset_ID"]) else None,
                "asset_name": row["Asset_Name"] if pd.notna(row["Asset_Name"]) else None,
                "repair_action": row["Repair_Action"] if pd.notna(row["Repair_Action"]) else None,
                "action_type": row["Action_Type"] if pd.notna(row["Action_Type"]) else None,
                "description": row["Description"] if pd.notna(row["Description"]) else None,
                "performed_by": None,  # Will need user mapping
                "action_date": row["Action_Date"] if pd.notna(row["Action_Date"]) else None,
                "status": row["Status"],
                "new_location_id": None,  # Will need location mapping
                "notes": row["Notes"] if pd.notna(row["Notes"]) else None
            }
            self.supabase.table("repair_log").insert(data).execute()
        
        logger.info(f"Migrated {len(df)} repair logs")

def main():
    """Run migration"""
    migrator = SheetsToSupabaseMigrator()
    migrator.migrate_all()
    print("Migration completed successfully!")

if __name__ == "__main__":
    main()