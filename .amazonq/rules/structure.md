# AMBP - Asset Management Business Platform Structure

```
ambp/
├── .amazonq/                     # Amazon Q AI Assistant rules
│   └── rules/                    # Project-specific AI rules
│       ├── Rules_Create.md       # System features and guidelines
│       ├── GUIDANCE.md           # Amazon Q guidance for new sessions
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
│   │   ├── asset_management.py   # Asset CRUD with owner_type support
│   │   ├── assigned_user.py      # Assigned user CRUD (admin only)
│   │   ├── assets.py             # Asset listing and search
│   │   ├── bulk_update.py        # 3-step bulk update workflow
│   │   ├── damage.py             # Asset issues (damage/lost/disposal)
│   │   ├── depreciation.py       # SuperAdmin depreciation updates
│   │   ├── disposal.py           # Asset disposal (admin only)
│   │   ├── export.py             # Excel export with owner_type columns
│   │   ├── forgot_password.py    # Email-based password recovery
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
│   │   │   ├── assigned_user/    # Assigned user management pages
│   │   │   ├── assets/           # Asset listing and details
│   │   │   ├── damage/           # Asset issues reporting
│   │   │   ├── repair/           # Asset repair completion
│   │   │   ├── relocation/       # Asset relocation pages
│   │   │   └── ...               # Other feature pages
│   │   │
│   │   └── templates_mobile/     # Mobile-optimized templates
│   │       ├── components/       # Mobile UI components
│   │       ├── layouts/          # Mobile layout templates
│   │       ├── assigned_user/    # Mobile assigned user pages
│   │       └── ...               # Mirror of desktop structure
│   │
│   ├── utils/                    # Utility functions
│   │   ├── __init__.py
│   │   ├── assigned_user_helper.py # Batch user name fetching
│   │   ├── auth.py               # Authentication utilities
│   │   ├── cache.py              # Caching mechanisms
│   │   ├── database_manager.py   # Supabase operations with owner_type
│   │   ├── device_detector.py    # Mobile/desktop template routing
│   │   ├── flash.py              # Flash message handling
│   │   ├── pagination.py         # Pagination utilities
│   │   ├── photo.py              # Google Drive photo handling
│   │   ├── profile_utils.py      # User profile utilities
│   │   ├── supabase_client.py    # Supabase client configuration
│   │   └── user_utils.py         # User management helpers
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
- **FastAPI Routes**: Modular organization by feature (19+ route modules)
- **Database**: Supabase PostgreSQL with foreign key relationships
- **Owner Type System**: GA (room-based) vs IT (user-based) asset assignment
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
- **Asset Registration**: Add/Edit with approval workflow and owner type selection
- **Owner Type System**: GA (room-based) vs IT (user-based) asset assignment
- **Asset Issues**: Separate pages for damage/lost/disposal reporting
- **Asset Repair**: Separate repair completion workflow
- **Asset Depreciation**: SuperAdmin value recalculation system
- **Bulk Update**: 3-step workflow with filters and Excel import
- **Forgot Password**: Email-based password recovery with secure token verification
- **Dashboard Analytics**: Real-time charts and metrics
- **User Management**: Role-based access with business unit integration
- **Assigned Users Management**: Admin-only IT user database for asset assignment
- **Export System**: Excel with owner_type and assigned_user_name columns
- **Approval Workflows**: Hierarchical approval system (Admin ↔ Manager)
- **Edit Asset Modal**: Direct edit button in asset view (admin only, non-disposed)
- **Direct Actions**: Clean UI with dedicated view pages

### Database Schema
- **Assets Table**: Core asset data with owner_type, assigned_user_id, assigned_user_name
- **Assigned Users Table**: IT user database with company and business unit
- **Log Tables**: Comprehensive audit trail (damage_log, repair_log, etc.)
- **Reference Tables**: Categories, locations, business units, companies
- **Approvals Table**: Workflow management with role-based routing
- **Profiles Table**: User management with business unit integration
- **Auto-resolution**: User names resolve to UUIDs (full_name → username)

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

### Route Modules Overview
- **`assigned_user.py`**: Admin-only CRUD for IT user database (list, add, edit, delete)
- **`asset_management.py`**: Asset CRUD with owner type support and approval workflow
- **`assets.py`**: Asset listing, search, and filtering
- **`approvals.py`**: Approval workflow management and routing
- **`bulk_update.py`**: 3-step bulk update workflow with Excel import
- **`damage.py`**: Asset damage reporting with approval
- **`disposal.py`**: Asset disposal requests and disposed assets list
- **`repair.py`**: Asset repair completion reporting
- **`depreciation.py`**: SuperAdmin depreciation value updates
- **`export.py`**: Excel export with optimized columns
- **`forgot_password.py`**: Email-based password recovery flow
- **`home.py`**: Dashboard with analytics and charts
- **`login.py`**: Authentication and session management
- **`user_management.py`**: User administration (admin only)
- **`profile.py`**: User profile management
- **`relocation.py`**: Asset relocation workflow
- **`logs.py`**: Audit trail and activity logs
- **`health.py`**: Health checks and monitoring
- **`offline.py`**: PWA offline support

### Template Organization
**Desktop Templates** (`templates_desktop/`):
- `assigned_user/list.html` - Assigned users list with Name, Company, Business Unit
- `assigned_user/form.html` - Add/Edit assigned user form
- `assets/view.html` - Asset detail view with edit modal (admin only)
- `assets/list.html` - Asset listing with filters
- `damage/index.html` - Damage reporting page
- `repair/index.html` - Repair completion page
- `disposal/form.html` - Disposal request form
- `approvals/index.html` - Approval management
- `layouts/modern_layout.html` - Modern menu layout for management pages

**Mobile Templates** (`templates_mobile/`):
- Mirror structure of desktop with optimized layouts
- Card-based UI for better mobile experience
- Touch-friendly buttons and interactions

### Integration Points
- **Supabase**: Primary database with real-time capabilities
- **Google Drive**: Asset photo storage and management
- **Chart.js**: Dashboard analytics and visualizations
- **Alpine.js**: Client-side reactivity and interactions
- **HTMX**: Dynamic content loading without full page refreshes
- **Jinja2**: Server-side template rendering with conditional logic
