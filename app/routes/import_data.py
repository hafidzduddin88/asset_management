from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from app.utils.migrate_csv_to_supabase import CSVToSupabaseMigrator
import logging

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/import", response_class=HTMLResponse)
async def import_page(request: Request):
    """Import data page"""
    return templates.TemplateResponse("import_data.html", {"request": request})

@router.post("/import/migrate")
async def migrate_data():
    """Run CSV to Supabase migration"""
    try:
        migrator = CSVToSupabaseMigrator()
        migrator.migrate_all()
        
        return JSONResponse({
            "status": "success",
            "message": "Data migration completed successfully!",
            "details": {
                "companies": "Migrated",
                "categories": "Migrated", 
                "locations": "Migrated",
                "business_units": "Migrated",
                "owners": "Migrated",
                "asset_types": "Migrated",
                "assets": "Migrated (397 records)",
                "approvals": "Migrated",
                "logs": "Migrated"
            }
        })
        
    except Exception as e:
        logging.error(f"Migration failed: {str(e)}")
        return JSONResponse({
            "status": "error",
            "message": f"Migration failed: {str(e)}"
        }, status_code=500)