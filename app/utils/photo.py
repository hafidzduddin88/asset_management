# app/utils/photo.py
import io
import os
import json
import logging
import requests
from PIL import Image
from google.oauth2.service_account import Credentials
from google.auth.transport.requests import Request

# Constants
DRIVE_SCOPE = ['https://www.googleapis.com/auth/drive.file']
MAX_IMAGE_SIZE = (800, 600)
WEBP_QUALITY = 85

def get_access_token():
    """Get Google Drive access token"""
    try:
        from app.config import load_config
        config = load_config()
        creds_json = config.GOOGLE_CREDS_JSON
        
        credentials = Credentials.from_service_account_info(creds_json, scopes=DRIVE_SCOPE)
        credentials.refresh(Request())
        return credentials.token
    except Exception as e:
        logging.error(f"Token error: {e}")
        return None

def resize_and_convert_image(image_file, max_size=MAX_IMAGE_SIZE, quality=WEBP_QUALITY):
    """Resize image and convert to WebP"""
    try:
        image = Image.open(image_file)
        if image.mode in ('RGBA', 'LA', 'P'):
            image = image.convert('RGB')

        image.thumbnail(max_size, Image.Resampling.LANCZOS)

        output = io.BytesIO()
        image.save(output, format='WEBP', quality=quality, optimize=True)
        output.seek(0)
        return output
    except Exception as e:
        logging.error(f"Image processing error: {e}")
        return None

def upload_to_drive(image_data, filename, asset_id):
    """Upload image to Google Drive and return preview link"""
    try:
        # Process image if it's raw bytes
        if isinstance(image_data, bytes):
            image_file = io.BytesIO(image_data)
            processed_image = resize_and_convert_image(image_file)
        else:
            processed_image = resize_and_convert_image(image_data)
            
        if not processed_image:
            return None
            
        access_token = get_access_token()
        if not access_token:
            return None
        
        folder_id = os.getenv("DRIVE_FOLDER_ID")
        shared_drive_id = os.getenv("DRIVE_SHARED_ID")
        if not folder_id or not shared_drive_id:
            logging.error("Missing DRIVE_FOLDER_ID or DRIVE_SHARED_ID")
            return None
        
        # Step 1: Initiate upload session
        upload_url = _initiate_upload(access_token, filename, asset_id, processed_image, folder_id, shared_drive_id)
        if not upload_url:
            return None

        # Step 2: Upload file data
        file_id = _upload_file_data(upload_url, processed_image)
        if not file_id:
            return None

        # Step 3: Set public permissions
        _set_public_permission(access_token, file_id)

        # Return preview link
        return f"https://drive.google.com/thumbnail?id={file_id}&sz=w400-h300"

    except Exception as e:
        logging.error(f"Upload error: {e}")
        return None

def _initiate_upload(access_token, filename, asset_id, image_data, folder_id, shared_drive_id):
    """Initiate resumable upload session"""
    file_metadata = {
        'name': f"AMBP_{asset_id}_{filename}.webp",
        'parents': [folder_id],
        'driveId': shared_drive_id
    }

    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json',
        'X-Upload-Content-Type': 'image/webp',
        'X-Upload-Content-Length': str(len(image_data.getvalue()))
    }

    response = requests.post(
        'https://www.googleapis.com/upload/drive/v3/files?uploadType=resumable&supportsAllDrives=true',
        headers=headers,
        json=file_metadata,
        timeout=30
    )

    if response.status_code == 200:
        return response.headers.get('Location')
    else:
        logging.error(f"Failed to initiate upload: {response.status_code} - {response.text}")
        return None

def _upload_file_data(upload_url, image_data):
    """Upload file data to resumable URL"""
    image_data.seek(0)
    headers = {
        'Content-Type': 'image/webp',
        'Content-Length': str(len(image_data.getvalue()))
    }

    response = requests.put(
        upload_url,
        headers=headers,
        data=image_data.getvalue(),
        timeout=60
    )

    if response.status_code in [200, 201]:
        return response.json().get('id')
    else:
        logging.error(f"Upload failed: {response.status_code} - {response.text}")
        return None

def _set_public_permission(access_token, file_id):
    """Set file to public readable"""
    try:
        requests.post(
            f"https://www.googleapis.com/drive/v3/files/{file_id}/permissions?supportsAllDrives=true",
            headers={
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json'
            },
            json={'role': 'reader', 'type': 'anyone'},
            timeout=30
        )
    except Exception as e:
        logging.error(f"Permission error: {e}")

def delete_from_drive(image_url):
    """Delete image from Google Drive"""
    try:
        if not image_url or 'drive.google.com' not in image_url:
            return False

        file_id = image_url.split('id=')[1] if 'id=' in image_url else None
        if not file_id:
            return False

        access_token = get_access_token()
        if not access_token:
            return False

        response = requests.delete(
            f"https://www.googleapis.com/drive/v3/files/{file_id}?supportsAllDrives=true",
            headers={'Authorization': f'Bearer {access_token}'},
            timeout=30
        )

        return response.status_code == 204

    except Exception as e:
        logging.error(f"Delete error: {e}")
        return False