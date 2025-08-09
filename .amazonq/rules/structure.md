# AMBP - Asset Management Business Platform Structure

```
ambp/
├── .amazonq/                     # Amazon Q AI Assistant rules
│   └── rules/                    # Project-specific AI rules
│       ├── Rules_Create.md       # System features and guidelines
│       └── structure.md          # Project structure documentation
│
├── app/                          # Main application directory
│   ├── middleware/               # FastAPI middleware
│   │   ├── __init__.py
│   │   └── session_auth.py       # JWT session authentication
│   │
│   ├── routes/                   # API routes (modular organization)
│   │   ├── __init__.py
│   │   ├── approvals.py          # Approval workflow management
│   │   ├── asset_management.py   # Asset CRUD operations
│   │   ├── assets.py             # Asset listing and search
│   │   ├── damage.py             # Asset issues (damage/lost/disposal)
│   │   ├── disposal.py           # Asset disposal (admin only)
│   │   ├── export.py             # Excel/PDF export functionality
│   │   ├── health.py             # Health checks and monitoring
│   │   ├── home.py               # Dashboard with analytics
│   │   ├── login.py              # Authentication endpoints
│   │   ├── logs.py               # Audit trail and activity logs
│   │   ├── offline.py            # PWA offline support
│   │   ├── profile.py            # User profile management
│   │   ├── relocation.py         # Asset relocation workflow
│   │   ├── repair.py             # Asset repair completion reporting
│   │   └── user_management.py    # User administration (admin only)
│   │
│   ├── schemas/                  # Pydantic data models
│   │   ├── __init__.py
│   │   └── profile.py            # User profile schemas
│   │
│   ├── static/                   # Static assets
│   │   ├── css/                  # Custom CSS files
│   │   ├── js/                   # JavaScript files
│   │   ├── img/                  # Images and icons
│   │   ├── manifest.json         # PWA manifest
│   │   └── service-worker.js     # Service worker for offline support
│   │
│   ├── templates/                # Jinja2 templates (responsive design)
│   │   ├── templates_desktop/    # Desktop-optimized templates
│   │   │   ├── components/       # Reusable UI components
│   │   │   ├── layouts/          # Base layout templates
│   │   │   ├── approvals/        # Approval management pages
│   │   │   ├── assets/           # Asset listing and details
│   │   │   ├── damage/           # Asset issues reporting
│   │   │   ├── repair/           # Asset repair completion
│   │   │   ├── relocation/       # Asset relocation pages
│   │   │   └── ...               # Other feature pages
│   │   │
│   │   └── templates_mobile/     # Mobile-optimized templates
│   │       ├── components/       # Mobile UI components
│   │       ├── layouts/          # Mobile layout templates
│   │       └── ...               # Mirror of desktop structure
│   │
│   ├── utils/                    # Utility functions
│   │   ├── __init__.py
│   │   ├── auth.py               # Authentication utilities
│   │   ├── cache.py              # Caching mechanisms
│   │   ├── database_manager.py   # Supabase database operations
│   │   ├── device_detector.py    # Mobile/desktop template routing
│   │   ├── flash.py              # Flash message handling
│   │   ├── pagination.py         # Pagination utilities
│   │   ├── photo.py              # Google Drive photo handling
│   │   ├── profile_utils.py      # User profile utilities
│   │   └── supabase_client.py    # Supabase client configuration
│   │
│   ├── __init__.py
│   ├── config.py                 # Application configuration
│   └── main.py                   # FastAPI application entry point
│
├── .env                          # Environment variables (not in repo)
├── .gitignore                    # Git ignore rules
├── Dockerfile                    # Container configuration
├── render.yaml                   # Render.com deployment config
├── requirements.txt              # Python dependencies (optimized)
└── README.md                     # Project documentation
```

## Key Components

### Backend Architecture
- **FastAPI Routes**: Modular organization by feature (12+ route modules)
- **Database**: Supabase PostgreSQL with foreign key relationships
- **Authentication**: JWT-based session middleware with Argon2 hashing
- **Google Integration**: Drive API for asset photo storage
- **Caching**: Smart caching for reference data and performance

### Frontend Stack
- **Templates**: Dual template system (desktop/mobile) with Jinja2
- **Reactivity**: Alpine.js for dynamic interactions
- **Styling**: TailwindCSS with custom gradients and animations
- **Charts**: Chart.js for dashboard analytics
- **PWA**: Complete offline support with service worker
- **Device Detection**: Automatic template routing based on device type

### Core Features
- **Asset Registration**: Add/Edit with approval workflow
- **Asset Issues**: Integrated damage/lost/disposal reporting
- **Asset Repair**: Separate repair completion workflow
- **Dashboard Analytics**: Real-time charts and metrics
- **User Management**: Role-based access with business unit integration
- **Export System**: Excel/PDF with customizable options
- **Approval Workflows**: Hierarchical approval system (Admin ↔ Manager)

### Database Schema
- **Assets Table**: Core asset data with foreign key relationships
- **Log Tables**: Comprehensive audit trail (damage_log, repair_log, etc.)
- **Reference Tables**: Categories, locations, business units, companies
- **Approvals Table**: Workflow management with role-based routing
- **Profiles Table**: User management with business unit integration

### Deployment
- **Containerized**: Docker with multi-stage builds
- **Cloud Hosting**: Render.com with auto-deployment
- **Database**: Supabase managed PostgreSQL
- **CDN**: Static assets served efficiently
- **Health Monitoring**: Built-in health checks and monitoring

## Development Workflow

### File Organization Principles
1. **Route Modules**: Each major feature has its own route file
2. **Template Separation**: Desktop and mobile templates maintained separately
3. **Utility Functions**: Shared logic in utils/ directory
4. **Component Reuse**: Shared components in templates/components/
5. **Static Assets**: Organized by type (css/, js/, img/)

### Key Directories Explained
- **`/routes`**: All API endpoints organized by feature
- **`/templates_desktop`**: Full-featured desktop interface
- **`/templates_mobile`**: Optimized mobile interface
- **`/utils`**: Database operations, auth, caching, etc.
- **`/middleware`**: Request/response processing
- **`/static`**: CSS, JS, images, PWA files

### Integration Points
- **Supabase**: Primary database with real-time capabilities
- **Google Drive**: Asset photo storage and management
- **Chart.js**: Dashboard analytics and visualizations
- **Alpine.js**: Client-side reactivity and interactions
- **HTMX**: Dynamic content loading without full page refreshes