from fastapi import APIRouter, Request, UploadFile, File, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
import pandas as pd
import io
from typing import Dict, Any
from app.database.dependencies import get_current_user
from app.utils.supabase_client import supabase_client
from app.utils.sheets import get_all_sheets_data

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/import", response_class=HTMLResponse)
async def import_page(request: Request, current_user: Dict[str, Any] = Depends(get_current_user)):
    if current_user["role"] not in ["admin"]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    return templates.TemplateResponse("import_data/import.html", {
        "request": request,
        "current_user": current_user
    })

@router.post("/import/excel")
async def import_excel(
    request: Request,
    file: UploadFile = File(...),
    table_name: str = Form(...),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    if current_user["role"] not in ["admin"]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    try:
        # Read Excel file
        contents = await file.read()
        df = pd.read_excel(io.BytesIO(contents))
        
        # Convert to dict and clean data
        data = df.fillna("").to_dict('records')
        
        # Infer column types from data
        columns = {}
        for col in df.columns:
            if df[col].dtype == 'object':
                columns[col.lower().replace(' ', '_')] = 'TEXT'
            elif df[col].dtype in ['int64', 'int32']:
                columns[col.lower().replace(' ', '_')] = 'INTEGER'
            elif df[col].dtype in ['float64', 'float32']:
                columns[col.lower().replace(' ', '_')] = 'DECIMAL'
            else:
                columns[col.lower().replace(' ', '_')] = 'TEXT'
        
        # Create table if not exists
        success = supabase_client.create_table_if_not_exists(table_name, columns)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to create table")
        
        # Clean column names in data
        clean_data = []
        for row in data:
            clean_row = {}
            for key, value in row.items():
                clean_key = key.lower().replace(' ', '_')
                clean_row[clean_key] = str(value) if value != "" else None
            clean_data.append(clean_row)
        
        # Insert data
        success = supabase_client.insert_data(table_name, clean_data, current_user["email"])
        if not success:
            raise HTTPException(status_code=500, detail="Failed to insert data")
        
        return RedirectResponse(url=f"/import?success=1&table={table_name}&rows={len(clean_data)}", status_code=303)
        
    except Exception as e:
        return RedirectResponse(url=f"/import?error={str(e)}", status_code=303)

@router.post("/import/sheets")
async def import_from_sheets(
    request: Request,
    sheet_name: str = Form(...),
    table_name: str = Form(...),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    if current_user["role"] not in ["admin"]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    try:
        # Get data from Google Sheets
        sheets_data = get_all_sheets_data()
        if sheet_name not in sheets_data:
            raise HTTPException(status_code=404, detail="Sheet not found")
        
        data = sheets_data[sheet_name]
        if not data:
            raise HTTPException(status_code=400, detail="No data found in sheet")
        
        # Infer column types
        columns = {}
        for key in data[0].keys():
            columns[key.lower().replace(' ', '_')] = 'TEXT'
        
        # Create table
        success = supabase_client.create_table_if_not_exists(table_name, columns)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to create table")
        
        # Clean data
        clean_data = []
        for row in data:
            clean_row = {}
            for key, value in row.items():
                clean_key = key.lower().replace(' ', '_')
                clean_row[clean_key] = str(value) if value else None
            clean_data.append(clean_row)
        
        # Insert data
        success = supabase_client.insert_data(table_name, clean_data, current_user["email"])
        if not success:
            raise HTTPException(status_code=500, detail="Failed to insert data")
        
        return RedirectResponse(url=f"/import?success=1&table={table_name}&rows={len(clean_data)}", status_code=303)
        
    except Exception as e:
        return RedirectResponse(url=f"/import?error={str(e)}", status_code=303)