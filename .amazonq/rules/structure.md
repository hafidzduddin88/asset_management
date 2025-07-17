# AMBP - Asset Management Business Platform Structure

```
ambp/
├── app/                          # Main application directory
│   ├── database/                 # Database related code
│   │   ├── __init__.py
│   │   ├── database.py           # SQLAlchemy setup
│   │   ├── dependencies.py       # Auth dependencies
│   │   └── migrations.py         # DB migrations
│   │
│   ├── middleware/               # FastAPI middleware
│   │   ├── __init__.py
│   │   └── session_auth.py       # Session authentication
│   │
│   ├── routes/                   # API routes
│   │   ├── __init__.py
│   │   ├── api.py                # API endpoints
│   │   ├── approvals.py          # Approval workflows
│   │   ├── asset_management.py   # Asset management
│   │   ├── assets.py             # Asset listing/details
│   │   ├── login.py               # Authentication
│   │   ├── damage.py             # Damage reporting
│   │   ├── export.py             # Export to Excel/PDF
│   │   ├── health.py             # Health checks
│   │   ├── home.py               # Home/dashboard
│   │   ├── offline.py            # Offline support
│   │   └── relocation.py         # Asset relocation
│   │
│   ├── static/                   # Static assets
│   │   ├── css/                  # CSS files
│   │   ├── js/                   # JavaScript files
│   │   ├── img/                  # Images
│   │   ├── manifest.json         # PWA manifest
│   │   ├── offline.js            # Offline support
│   │   └── service-worker.js     # Service worker
│   │
│   ├── templates/                # Jinja2 templates
│   │   ├── components/           # Reusable components
│   │   │   ├── asset_quick_info.html
│   │   │   ├── confirmation_modal.html
│   │   │   ├── dashboard_stats.html
│   │   │   ├── search_results.html
│   │   │   └── toast_notification.html
│   │   │
│   │   ├── layouts/              # Layout templates
│   │   │   ├── feature_layout.html
│   │   │   └── modern_layout.html
│   │   │
│   │   ├── dashboard_modern.html # Modern dashboard
│   │   ├── login_logout.html     # Login page
│   │   └── ...                   # Other templates
│   │
│   ├── utils/                    # Utility functions
│   │   ├── __init__.py
│   │   ├── auth.py               # Auth utilities
│   │   ├── cache.py              # Caching
│   │   ├── flash.py              # Flash messages
│   │   ├── pagination.py         # Pagination
│   │   ├── photo.py              # Photo handling
│   │   ├── sheets.py             # Google Sheets API
│   │   └── ...                   # Other utilities
│   │
│   ├── __init__.py
│   ├── config.py                 # Configuration
│   ├── init.py                   # App initialization
│   └── main.py                   # Entry point
│
├── .env                          # Environment variables
├── .gitignore                    # Git ignore file
├── requirements.txt              # Python dependencies
└── README.md                     # Project documentation
```

## Key Components

### Backend
- **FastAPI Routes**: Organized by feature (assets, damage, relocation)
- **Database**: PostgreSQL with SQLAlchemy ORM
- **Authentication**: JWT-based with Argon2 password hashing
- **Google Integration**: Sheets API for asset data, Drive API for photos

### Frontend
- **Templates**: Jinja2 with component-based architecture
- **Modern UI**: Alpine.js for reactivity + HTMX for dynamic content
- **Styling**: TailwindCSS for consistent design
- **Offline Support**: Service Worker + PWA manifest

### Features
- **Asset Management**: Add, view, relocate, dispose, damaged, repaired
- **Approval Workflow**: Admin approval for critical actions
- **Reporting**: Export to Excel/PDF
- **Photo Integration**: Upload and view asset photos
- **Responsive Design**: Mobile-friendly interface