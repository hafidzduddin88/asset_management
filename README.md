# Asset Management System (AMBP)

A modern, web-based asset management system with role-based authentication, approval workflows, and offline support.

Created by: Asset Management & Business Process Department

## Features

- **Asset Registration** - Add/Edit/Relocate/Dispose Assets with approval workflows
- **Role-based Authentication** - Admin, Manager & Staff with different permissions
- **Approval Workflows** - Admin needs manager approval, Manager/Staff need admin approval
- **Asset Issue Management** - Report damage, lost assets, and disposal requests
- **User Management** - Create users, reset passwords, change roles (Admin only)
- **Card-style Asset UI** - Photo previews via Google Drive integration
- **PWA Support** - Offline-friendly, mobile-ready progressive web app
- **Export Reports** - Excel and PDF export capabilities
- **Google Integration** - Sheets API for data storage, Drive API for photos
- **Audit Trail** - Complete logging of all user management actions

## Tech Stack

### Backend
- **FastAPI + Uvicorn** - Modern Python web framework
- **Supabase** - PostgreSQL database with real-time features
- **Google Sheets API** - Data storage and management
- **Google Drive API** - Asset photo storage
- **JWT Authentication** - Secure token-based auth
- **Argon2 Password Hashing** - Secure password storage

### Frontend
- **Tailwind CSS** - Utility-first CSS framework
- **Alpine.js** - Lightweight JavaScript framework
- **HTMX** - Modern HTML interactions
- **Jinja2** - Server-side templating
- **PWA** - Service Worker + Web Manifest for offline support
- **Responsive Design** - Mobile-first approach

### DevOps
- **GitHub Container Registry (GHCR)** - Container image storage
- **Render.com** - Cloud deployment platform
- **GitHub Actions** - CI/CD pipeline with automated builds
- **Docker** - Containerized deployment

## Quick Start

### Local Development

1. **Clone the repository:**
```bash
git clone https://github.com/hafidzduddin88/asset_management.git
cd asset_management
```

2. **Set up environment:**
```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

3. **Configure environment variables:**
```bash
cp .env.example .env
# Edit .env with your credentials
```

4. **Run the application:**
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Docker Deployment

```bash
# Build and run with Docker
docker build -t ambp .
docker run -p 8000:8000 --env-file .env ambp
```

### Production Deployment

The application is automatically deployed to Render.com via GitHub Actions when pushing to the main branch.

## Environment Variables

### Required
- `SECRET_KEY` - JWT secret key for authentication
- `GOOGLE_CREDS_JSON` - Google Service Account credentials (JSON)
- `GOOGLE_SHEET_ID` - Google Sheets ID for asset data storage
- `SUPABASE_URL` - Supabase project URL
- `SUPABASE_ANON_KEY` - Supabase anonymous key
- `SUPABASE_SERVICE_KEY` - Supabase service role key

### Optional
- `PORT` - Application port (default: 8000)
- `APP_URL` - Application URL for external services
- `DATABASE_URL` - Legacy PostgreSQL connection (if not using Supabase)

## Project Structure

```
asset_management/
├── app/
│   ├── database/                 # Database models and connections
│   ├── middleware/               # Authentication middleware
│   ├── routes/                   # API endpoints and page routes
│   │   ├── asset_management.py   # Asset CRUD operations
│   │   ├── user_management.py    # User management (Admin only)
│   │   ├── damage.py            # Asset issue reporting
│   │   ├── approvals.py         # Approval workflow management
│   │   └── ...                  # Other route modules
│   ├── static/                   # Static assets (CSS, JS, images)
│   ├── templates/                # Jinja2 HTML templates
│   ├── utils/                    # Utility functions
│   │   ├── sheets.py            # Google Sheets integration
│   │   ├── auth.py              # Authentication helpers
│   │   └── photo.py             # Image processing
│   ├── config.py                 # Configuration management
│   └── main.py                   # FastAPI application entry point
├── .github/workflows/            # CI/CD pipeline
├── Dockerfile                    # Container configuration
├── requirements.txt              # Python dependencies
└── render.yaml                   # Render.com deployment config
```

## Deployment

### Automated Deployment

The application uses GitHub Actions for automated CI/CD:

1. **Push to main branch** triggers the build pipeline
2. **Docker image** is built and pushed to GitHub Container Registry (GHCR)
3. **Render.com** automatically deploys the new image
4. **Cache cleanup** removes old images and build cache

### Manual Deployment

#### Render.com Setup
1. Create a new Web Service on Render.com
2. Connect to GitHub repository
3. Use Docker image: `ghcr.io/hafidzduddin88/ambp:latest`
4. Set environment variables
5. Enable auto-deploy

#### GitHub Secrets Required
- `RENDER_SERVICE_ID` - Render service ID
- `RENDER_API_KEY` - Render API key for deployment triggers

### Container Registry

Images are stored in GitHub Container Registry:
- **Latest**: `ghcr.io/hafidzduddin88/ambp:latest`
- **Tagged**: `ghcr.io/hafidzduddin88/ambp:<commit-sha>`

## User Roles & Permissions

### Admin
- Full system access
- User management (create, edit, reset passwords)
- Asset approval (for Manager/Staff requests)
- Direct asset operations
- System configuration

### Manager
- Asset management operations
- Approve admin asset requests
- View all assets and reports
- Submit requests requiring admin approval

### Staff
- Basic asset operations
- Submit asset requests for approval
- Report asset issues (damage, lost)
- View assigned assets

## Approval Workflows

- **Admin** → Requires **Manager approval**
- **Manager/Staff** → Requires **Admin approval**
- All critical operations logged for audit trail

## API Integration

### Google Sheets
- Asset data storage and management
- Real-time data synchronization
- Reference data (categories, locations, etc.)

### Google Drive
- Asset photo storage
- Organized folder structure
- Public preview URLs

### Supabase
- User authentication and profiles
- Real-time database features
- Row-level security

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## Support

For support and questions, please contact the Asset Management & Business Process Department.

## License

MIT License - See LICENSE file for details

---

**Live Demo**: [https://ambp.onrender.com](https://ambp.onrender.com)

**Repository**: [https://github.com/hafidzduddin88/asset_management](https://github.com/hafidzduddin88/asset_management)