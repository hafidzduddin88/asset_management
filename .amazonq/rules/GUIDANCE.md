# Amazon Q Developer Guidance for AMBP

## Quick Start for New Amazon Q Sessions

### 1. Project Overview
**AMBP (Asset Management Business Platform)** is a modern web-based asset management system built with:
- **Backend**: FastAPI + Supabase PostgreSQL (11 optimized packages)
- **Frontend**: Tailwind CSS + Alpine.js + HTMX + Jinja2
- **Features**: Asset management with GA/IT differentiation, issue reporting, repair workflows, bulk update, compact analytics dashboard
- **Authentication**: JWT-based with profile protection system

### 2. Key System Concepts

#### Asset Lifecycle
```
Registration → Active → Damaged → Repair → Active/Disposed
                    ↓
                  Lost/Disposal
```

#### User Roles & Permissions
- **Admin**: Full system access, approves staff/manager requests, manages assigned users, can edit assets
- **Manager**: Asset operations, approves admin requests  
- **Staff**: Basic operations, submit requests for approval

#### Authentication & Security
- **JWT Session**: Token-based auth with auto-refresh via supabase-py v2 SDK method
- **Forgot Password**: Email recovery → Token verification → Session-based reset
- **Profile Protection**: Prevents data overwrites during token refresh
- **Token Refresh**: Uses supabase-py v2 `refresh_session()` for reliability (~20-30% faster)
- **Error Handling**: Graceful redirect to login on refresh failure with cookie cleanup

#### Core Workflows
1. **Asset Registration**: Add/Edit assets with approval and owner selection
2. **Owner System**: GA (room-based) vs IT (user-based) asset assignment
3. **Asset Issues**: Report damage/lost/disposal requests (single approval)
4. **Asset Repair**: Report repair completion for damaged assets
5. **Asset Depreciation**: SuperAdmin value recalculation
6. **Bulk Update**: 3-step workflow with filters and Excel import
7. **Forgot Password**: Email recovery with secure token verification
8. **Approval System**: Hierarchical approval workflow (single approval for disposal)
9. **Assigned Users Management**: Admin-only CRUD for IT user database

### 3. Architecture Patterns

#### Route Organization
```
/routes/
├── asset_management.py # Asset CRUD with owner support
├── assigned_user.py    # Assigned user CRUD (admin only)
├── damage.py          # Asset Issues (damage/lost/disposal pages)
├── disposal.py        # Disposal requests & disposed assets list
├── repair.py          # Asset Repair completion
├── depreciation.py    # SuperAdmin depreciation updates
├── bulk_update.py     # 3-step bulk update workflow
├── forgot_password.py # Email-based password recovery
├── approvals.py       # Approval workflow
└── ...
```

#### Template Structure
```
/templates/
├── templates_desktop/  # Full-featured desktop UI
│   └── assigned_user/  # Assigned user management pages
└── templates_mobile/   # Optimized mobile UI
    └── assigned_user/  # Mobile assigned user pages
```

#### Database Integration
- **Primary DB**: Supabase PostgreSQL with foreign keys
- **Owner Type Fields**: owner_type, assigned_user_id, assigned_user_name
- **Log Tables**: Comprehensive audit trail (damage_log, repair_log, etc.)
- **Reference Tables**: Categories, locations, business units, assigned_users
- **Auto-resolution**: User names resolve to UUIDs (full_name → username)

### 4. Development Guidelines

#### Owner System (IMPORTANT)
- **Owner GA**: Room-based assignment (location + room required)
- **Owner IT**: User-based assignment (assigned_user_name required)
- **Conditional Fields**: Forms dynamically show GA or IT fields based on owner selection
- **Auto-resolution**: assigned_user_name resolves to assigned_user_id UUID
  - Try full_name first, then username
  - Validation in database_manager.py prepare_asset_data()
- **Filter Support**: Owner filter in list pages and bulk update
- **Export Integration**: Excel exports include owner and assigned_user_name columns
- **UI Labels**: "Owner" field with "GA" or "IT" options (help text: "GA: Room-based | IT: User-based")
- **Assigned Users Database**: Admin-only management of IT user database
  - Add/Edit/Delete assigned users with company and business unit
  - Used for IT asset owner assignment
  - Searchable list with view details modal

#### Bulk Update Workflow (IMPORTANT)
- **Step 1**: Export assets with filters (category, type, location, room, owner, status)
- **Step 2**: Import Excel file with modifications
- **Step 3**: Confirm and apply updates with approval workflow
- **Auto-resolution**: assigned_user_name in Excel resolves to assigned_user_id
- **Validation**: Checks for required fields and valid references

#### Disposal Workflow (IMPORTANT)
- **Single Approval Flow**: User → Request Disposal → Admin/Manager Approve → Status: Disposed
- **Disposal Request**: User requests disposal via `/disposal/form?asset_id=***` → Creates approval request
- **Disposal Page**: Shows list of disposed assets (view only)
- **No Execution Step**: Approval directly sets status to "Disposed"
- **Status**: "Damaged" (not "Under Repair"), no "To be Disposed" status

#### Edit Asset Modal (IMPORTANT)
- **Location**: Inside asset view detail modal (footer, left side)
- **Visibility**: Admin-only, only when asset status is NOT Disposed/Lost
- **Functionality**: Direct edit button replaces need to navigate to separate edit page
- **Conditional Display**: Jinja2 conditional checks role and asset status
- **Template Variable Handling**: Pass `current_profile` as `user` for navbar, separate data objects for form pre-fill

#### Code Style
- **Modular**: Each feature in separate route file
- **Responsive**: Desktop and mobile templates
- **Secure**: Role-based access control
- **Cached**: Reference data caching for performance

#### Key Files to Understand
1. **`main.py`**: Application entry point and route registration
2. **`database_manager.py`**: All Supabase operations including assigned user CRUD
3. **`session_auth.py`**: JWT authentication middleware
4. **`device_detector.py`**: Mobile/desktop template routing
5. **`assigned_user.py`**: Assigned user management routes

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

# Template variable handling for forms
return templates.TemplateResponse(template_path, {
    "user": current_profile,  # For navbar display
    "assigned_user": assigned_user_data,  # For form pre-fill
    "request": request
})
```

### 5. Current System State

#### Implemented Features ✅
- Asset Registration with approval workflow and owner selection
- Owner System: GA (room-based) vs IT (user-based) asset assignment
- Asset Issues (damage/lost/disposal) with single approval flow
- Asset Repair workflow for damaged assets
- Asset Depreciation with SuperAdmin value recalculation
- Bulk Update Assets with 3-step workflow and Excel import
- Disposal with single approval (no execution step)
- Forgot Password with email recovery and secure token verification
- **Token Refresh**: supabase-py v2 SDK method with improved error handling
- Direct action buttons replacing dropdown menus
- Dedicated asset view pages with image zoom functionality
- **Edit Asset Modal**: Direct edit button in asset view (admin only, non-disposed assets)
- Compact dashboard with monthly/quarterly/yearly analytics
- User management with business unit terminology
- **Assigned Users Management**: Admin-only CRUD for IT user database
- Export to Excel with owner and assigned_user_name columns
- PWA support with offline capability
- Profile protection against overwrites during authentication
- Mobile-optimized templates with scrollable lists
- Rupiah currency format throughout application
- Owner filter in list pages and bulk update
- Optimized build: Python 3.12-slim, faster Docker builds (2-4 min)

#### Key Integrations
- **Supabase**: Primary database with foreign key relationships and log tables
- **Google Drive**: Asset photo storage with organized folder structure
- **Chart.js**: Dashboard analytics with activity data from log tables
- **Alpine.js**: Client-side reactivity
- **Database Triggers**: Auto-sync auth.users with public.profiles

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

# Assigned user operations
assigned_users = get_assigned_users()
assigned_user = get_assigned_user_by_id(user_id)
add_assigned_user(name, company, business_unit)
update_assigned_user(user_id, name, company, business_unit)
delete_assigned_user(user_id)
```

#### Template Updates
- Always update both desktop and mobile versions
- Use `get_template(request, "path")` for device detection
- Follow existing component patterns
- Distinguish between `user` (current_profile) and data objects for form pre-fill

### 7. Troubleshooting

#### Common Issues
- **Template not found**: Check desktop/mobile template paths
- **Database errors**: Verify foreign key relationships
- **Auth issues**: Check role-based access in routes
- **Chart errors**: Ensure data format matches Chart.js requirements
- **Profile overwrites**: Check profile protection in auth.py and middleware
- **Full name changes**: Verify last_login_at updates preserve existing full_name
- **Template variable errors**: Ensure navbar receives `user` (current_profile) and forms receive separate data objects

#### Debug Steps
1. Check logs for specific error messages
2. Verify database schema matches code expectations
3. Test with different user roles
4. Check both desktop and mobile templates
5. Verify profile protection mechanisms are working
6. Verify template variable naming (user vs data objects)

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
- **Forgot Password**: `app/routes/forgot_password.py` - Email recovery flow
- **Assigned Users**: `app/routes/assigned_user.py` - User management routes

### Key Concepts
- **Owner System**: GA (room-based) vs IT (user-based) asset assignment
- **Auto-resolution**: User names resolve to UUIDs (full_name → username)
- **Bulk Update**: 3-step workflow with filters and Excel import
- **Asset Issues**: Damage/Lost/Disposal with single approval
- **Asset Repair**: Workflow for damaged assets (status: "Damaged")
- **Disposal Flow**: Single approval (User → Request → Approve → Disposed)
- **Forgot Password**: Email recovery → Token verification → Session-based reset
- **Dual Templates**: Desktop and mobile versions (always update both)
- **Approval Workflow**: Role-based hierarchical approvals
- **Supabase Integration**: PostgreSQL with foreign keys and comprehensive logging
- **Profile Protection**: Prevents full_name overwrites during authentication
- **Compact Design**: Optimized spacing and sizing for better UX
- **Assigned Users**: Admin-only IT user database for asset assignment
- **Edit Asset Modal**: Direct edit in asset view (admin only, non-disposed)

### Recent Optimizations
- **Requirements**: Reduced from 25+ to 11 essential packages
- **Owner System**: GA (room-based) vs IT (user-based) asset differentiation
- **Bulk Update**: 3-step workflow with filters and Excel import
- **UI/UX**: Direct action buttons replacing dropdown menus
- **Asset Views**: Dedicated view pages with comprehensive details
- **Modal Cleanup**: Removed unused components for cleaner codebase
- **Currency Format**: Changed to Rupiah (Rp) throughout application
- **Depreciation**: Added SuperAdmin value recalculation functionality
- **Export**: Optimized column ordering with owner_type and assigned_user_name
- **Approval System**: Fixed role-based filtering and notes column usage
- **Authentication**: Fixed full_name preservation during login
- **Forgot Password**: Email recovery with secure token verification flow
- **Mobile**: Added scrollable lists and compact filters
- **Asset Issues**: Separated into individual pages (/damage, /lost, /disposal)
- **Owner Filter**: Added to list pages and bulk update for GA/IT filtering
- **Token Refresh**: Migrated from manual HTTP to supabase-py v2 SDK method
  - ✅ ~20-30% faster token refresh
  - ✅ Better error handling with automatic redirect to login
  - ✅ Graceful cookie cleanup on refresh failure
  - ✅ No schema changes required
  - ✅ Fully backward compatible
- **Assigned Users Management**: Admin-only CRUD for IT user database
  - ✅ Add/Edit/Delete assigned users
  - ✅ Company and business unit integration
  - ✅ Searchable list with view details modal
  - ✅ Desktop and mobile templates
- **Edit Asset Modal**: Direct edit button in asset view
  - ✅ Admin-only visibility
  - ✅ Conditional display based on asset status
  - ✅ Positioned in modal footer (left side)

This guidance should help you quickly understand and work with the AMBP system effectively.
