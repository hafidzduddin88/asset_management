# Amazon Q Developer Guidance for AMBP

## Quick Start for New Amazon Q Sessions

### 1. Project Overview
**AMBP (Asset Management Business Platform)** is a modern web-based asset management system built with:
- **Backend**: FastAPI + Supabase PostgreSQL
- **Frontend**: Tailwind CSS + Alpine.js + HTMX + Jinja2
- **Features**: Asset management, issue reporting, repair workflows, analytics dashboard

### 2. Key System Concepts

#### Asset Lifecycle
```
Registration → Active → Issues (Damage/Lost) → Repair → Active/Disposed
```

#### User Roles & Permissions
- **Admin**: Full system access, approves staff/manager requests
- **Manager**: Asset operations, approves admin requests  
- **Staff**: Basic operations, submit requests for approval

#### Core Workflows
1. **Asset Registration**: Add/Edit assets with approval
2. **Asset Issues**: Report damage/lost/disposal (integrated in `/damage` route)
3. **Asset Repair**: Report repair completion (separate `/repair` route)
4. **Approval System**: Hierarchical approval workflow

### 3. Architecture Patterns

#### Route Organization
```
/routes/
├── damage.py          # Asset Issues (damage/lost/disposal)
├── repair.py          # Asset Repair completion
├── asset_management.py # Asset CRUD operations
├── approvals.py       # Approval workflow
└── ...
```

#### Template Structure
```
/templates/
├── templates_desktop/  # Full-featured desktop UI
└── templates_mobile/   # Optimized mobile UI
```

#### Database Integration
- **Primary DB**: Supabase PostgreSQL with foreign keys
- **Log Tables**: Comprehensive audit trail (damage_log, repair_log, etc.)
- **Reference Tables**: Categories, locations, business units

### 4. Development Guidelines

#### Code Style
- **Modular**: Each feature in separate route file
- **Responsive**: Desktop and mobile templates
- **Secure**: Role-based access control
- **Cached**: Reference data caching for performance

#### Key Files to Understand
1. **`main.py`**: Application entry point and route registration
2. **`database_manager.py`**: All Supabase operations
3. **`session_auth.py`**: JWT authentication middleware
4. **`device_detector.py`**: Mobile/desktop template routing

#### Common Patterns
```python
# Route structure
@router.get("/")
async def page(request: Request, current_profile = Depends(get_current_profile)):
    template_path = get_template(request, "feature/index.html")
    return templates.TemplateResponse(template_path, {...})

# Database operations
supabase = get_supabase()
response = supabase.table('table_name').select('*').execute()

# Approval workflow
approval_data = {
    "type": "request_type",
    "requires_admin_approval": True if role in ['staff', 'manager'] else False,
    "requires_manager_approval": True if role == 'admin' else False
}
```

### 5. Current System State

#### Implemented Features ✅
- Asset Registration with approval workflow
- Asset Issues (damage/lost/disposal) in single page
- Asset Repair as separate workflow
- Dashboard with real-time analytics
- User management with business units
- Export to Excel/PDF
- PWA support with offline capability

#### Key Integrations
- **Supabase**: Primary database with real-time features
- **Google Drive**: Asset photo storage
- **Chart.js**: Dashboard analytics
- **Alpine.js**: Client-side reactivity

### 6. Common Tasks

#### Adding New Feature
1. Create route file in `/routes/`
2. Add desktop template in `/templates_desktop/`
3. Add mobile template in `/templates_mobile/`
4. Update navigation in layout templates
5. Register route in `main.py`

#### Database Operations
```python
# Get data with relationships
response = supabase.table('assets').select('''
    asset_id, asset_name,
    ref_categories(category_name),
    ref_locations(location_name, room_name)
''').execute()

# Insert with approval workflow
approval_data = {...}
add_approval_request(approval_data)
```

#### Template Updates
- Always update both desktop and mobile versions
- Use `get_template(request, "path")` for device detection
- Follow existing component patterns

### 7. Troubleshooting

#### Common Issues
- **Template not found**: Check desktop/mobile template paths
- **Database errors**: Verify foreign key relationships
- **Auth issues**: Check role-based access in routes
- **Chart errors**: Ensure data format matches Chart.js requirements

#### Debug Steps
1. Check logs for specific error messages
2. Verify database schema matches code expectations
3. Test with different user roles
4. Check both desktop and mobile templates

### 8. Environment Setup

#### Required Environment Variables
```
SUPABASE_URL=your_supabase_url
SUPABASE_ANON_KEY=your_anon_key
SUPABASE_SERVICE_KEY=your_service_key
GOOGLE_CREDS_JSON=your_google_credentials
```

#### Development Commands
```bash
# Install dependencies
pip install -r requirements.txt

# Run development server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Docker build
docker build -t ambp .
```

## Quick Reference

### Important Files
- **Rules**: `.amazonq/rules/Rules_Create.md` - System features
- **Structure**: `.amazonq/rules/structure.md` - Project organization
- **Main App**: `app/main.py` - Entry point
- **Database**: `app/utils/database_manager.py` - All DB operations
- **Auth**: `app/middleware/session_auth.py` - Authentication

### Key Concepts
- **Asset Issues**: Damage/Lost/Disposal in single workflow
- **Asset Repair**: Separate workflow for repair completion
- **Dual Templates**: Desktop and mobile versions
- **Approval Workflow**: Role-based hierarchical approvals
- **Supabase Integration**: PostgreSQL with foreign keys

This guidance should help you quickly understand and work with the AMBP system effectively.