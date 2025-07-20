# Asset Management System

A modern, web-based asset management system with role-based authentication, approval workflows, and offline support.

Created by: Asset Management & Business Process Department

## Features

- Add/Edit/Relocate/Dispose Assets (with Admin Approval)
- Role-based Authentication (Admin & Staff)
- Card-style Asset UI with Photo Previews (Google Drive)
- PWA Support (Offline-friendly, Mobile-ready)
- Export Reports to Excel and PDF
- Google Sheets & Drive API Integration
- Admin Approval Workflow for all critical actions

## Tech Stack

### Backend
- FastAPI + Uvicorn
- SQLAlchemy (PostgreSQL)
- Google Sheets API (gspread)
- Google Drive API
- JWT Authentication
- Argon2 Password Hashing

### Frontend
- Tailwind CSS
- Alpine.js
- HTMX
- Jinja2
- Client-side filtering, responsive design
- PWA (Service Worker + Web Manifest)

## Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/ambp.git
cd ambp
```

2. Create a virtual environment and install dependencies:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

3. Set up environment variables:
```bash
cp .env.example .env
# Edit .env with your configuration
```

4. Run the application:
```bash
uvicorn app.main:app --reload
```

## Environment Variables

- `DATABASE_URL`: PostgreSQL connection string
- `SECRET_KEY`: JWT secret key
- `GOOGLE_CREDS_JSON`: Google API credentials JSON
- `GOOGLE_SHEET_ID`: Google Sheet ID for asset data
- `APP_URL`: Application URL for external services
- `SUPABASE_SERVICE_KEY`: Supabase Service Role Key (optional)
- `SUPABASE_ANON_KEY`: Supabase Anonymous Key (optional)

## Development

### Project Structure

```
ambp/
├── app/                          # Main application directory
│   ├── database/                 # Database related code
│   ├── middleware/               # FastAPI middleware
│   ├── routes/                   # API routes
│   ├── static/                   # Static assets
│   ├── templates/                # Jinja2 templates
│   ├── utils/                    # Utility functions
│   ├── config.py                 # Configuration
│   └── main.py                   # Entry point
├── .env                          # Environment variables
└── requirements.txt              # Python dependencies
```

### Running Tests

```bash
pytest
```

## Deployment

The application can be deployed to various platforms:

### Render.com

A `render.yaml` file is included for easy deployment to Render.com.

### Docker

A `Dockerfile` is included for containerized deployment.

```bash
docker build -t ambp .
docker run -p 8000:8000 ambp
```

## License

MIT