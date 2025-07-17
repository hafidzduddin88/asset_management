# app/utils/photo.py
import os
import tempfile
from fastapi import UploadFile
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import mimetypes
from app.config import load_config

config = load_config()

async def upload_photo_to_drive(photo: UploadFile, asset_tag: str):
    """Upload photo to Google Drive and return file ID and public URL."""
    # Create credentials from service account info
    creds = Credentials.from_service_account_info(
        config.GOOGLE_CREDS_JSON,
        scopes=["https://www.googleapis.com/auth/drive"]
    )
    
    # Build the Drive API client
    drive_service = build("drive", "v3", credentials=creds)
    
    # Create a temporary file
    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
        # Write the uploaded file to the temporary file
        content = await photo.read()
        temp_file.write(content)
        temp_file_path = temp_file.name
    
    try:
        # Get MIME type
        mime_type, _ = mimetypes.guess_type(photo.filename)
        if not mime_type:
            mime_type = "application/octet-stream"
        
        # Create file metadata
        file_metadata = {
            "name": f"{asset_tag}_{photo.filename}",
            "parents": [config.GOOGLE_DRIVE_FOLDER_ID] if config.GOOGLE_DRIVE_FOLDER_ID else None
        }
        
        # Upload file
        media = MediaFileUpload(temp_file_path, mimetype=mime_type, resumable=True)
        file = drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields="id,webViewLink"
        ).execute()
        
        # Make the file publicly accessible
        drive_service.permissions().create(
            fileId=file.get("id"),
            body={"role": "reader", "type": "anyone"}
        ).execute()
        
        # Return file ID and web view link
        return file.get("id"), file.get("webViewLink")
    
    finally:
        # Clean up the temporary file
        os.unlink(temp_file_path)