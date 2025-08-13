# Asset Management Business Platform (AMBP)

## Core Features

- **Asset Registration** - Add/Edit/Relocate assets with approval workflow
- **Asset Issues** - Report Damage/Lost/Disposal requests via dedicated pages
- **Asset Repair** - Report repair completion for damaged assets
- **Asset Depreciation** - SuperAdmin value recalculation system
- **Role-based Authentication** - Admin/Manager/Staff with hierarchical approvals
- **Dashboard Analytics** - Real-time charts and metrics
- **PWA Support** - Offline-friendly, mobile-ready application
- **Export Reports** - Excel with optimized column ordering
- **Google Drive Integration** - Asset photo storage and management

## Backend Architecture
- **FastAPI + Uvicorn** - Modern Python web framework
- **Supabase PostgreSQL** - Primary database with foreign key relationships
- **Google Drive API** - Asset photo storage
- **JWT Authentication** - Session-based auth with middleware
- **Argon2 Password Hashing** - Secure password storage

## Frontend Stack
- **Tailwind CSS** - Utility-first styling
- **Alpine.js** - Reactive JavaScript framework
- **HTMX** - Dynamic content loading
- **Jinja2** - Server-side templating
- **Chart.js** - Dashboard analytics
- **PWA** - Service Worker + Web Manifest for offline support
- **Responsive Design** - Desktop and mobile templates

## Google Drive Integration
- Asset photo upload and storage
- Organized folder structure by asset tag
- Public preview via Google Drive viewer
- Secure file handling with service account

## Authentication & Roles
- **JWT-based Authentication** with session middleware
- **Argon2 Password Hashing** for security
- **Role-Based Access Control:**
  - **Admin:** Full system access, user management, approves staff/manager requests
  - **Manager:** Asset operations, approves admin requests
  - **Staff:** Basic operations, submit requests for approval

## Approval Workflow System
**Hierarchical Approval Process:**
- **Staff/Manager → Admin:** Asset registration, damage reports, repairs, relocations, disposals
- **Admin → Manager:** Admin-initiated requests require manager approval

**Critical Actions Requiring Approval:**
- Asset Registration (Add/Edit)
- Asset Issues (Damage/Lost/Disposal)
- Asset Repair Completion
- Asset Relocation
- Asset Depreciation Updates (SuperAdmin only)

**Workflow Process:**
1. User submits request
2. Stored in approvals table with proper role routing
3. Approver reviews and approves/rejects
4. System updates asset status and logs action
5. Complete audit trail maintained

## Asset Issue Management
**Integrated Issue Reporting:**
- **Damage Reports** - Report asset damage with severity levels
- **Lost Assets** - Report missing assets with circumstances
- **Disposal Requests** - Request asset disposal with reasons

**Issue Processing:**
- All issues require approval workflow
- Comprehensive logging in dedicated log tables
- Asset status automatically updated upon approval
- Complete audit trail with timestamps and approvers

---

## Reporting & Analytics
**Dashboard Features:**
- Real-time asset metrics and summaries
- Interactive charts (monthly/quarterly/yearly views)
- Activity tracking for all asset operations
- Financial summaries (purchase value, book value, depreciation)

**Export Capabilities:**
- **Excel Export** - Optimized column ordering and data sorting
- **PDF Reports** - Formatted reports with asset details
- **Role-based Access** - Available to all users with restrictions
- Include asset photos, approval metadata, and audit trails

---

## Development Guidelines

**Code Organization:**
- Modular architecture with clear separation of concerns
- Route-based organization (`/routes` directory)
- Utility functions in `/utils` directory
- Template separation for desktop and mobile

**API Standards:**
- RESTful API design
- Proper HTTP status codes
- JSON request/response format
- Form and API validation

**Security:**
- Secure service account setup for Google APIs
- Role-based access control
- Input validation and sanitization
- Proper error handling

**Database:**
- Foreign key relationships for data integrity
- Comprehensive logging tables
- Proper indexing for performance
- Cache management for reference data

---

## Commit Standards

**IMPORTANT: Always provide commit message suggestions before any explanation or implementation.**

Always use Conventional Commits format with these suggestions:

### Feature Development
```bash
# New features
feat: add asset repair completion workflow
feat: implement lost asset reporting system
feat: create dashboard analytics charts
feat: add Excel export functionality

# Feature enhancements
feat: enhance approval workflow with role-based routing
feat: add mobile template for asset issues
feat: integrate Google Drive photo storage
feat: add direct action buttons replacing dropdown menus
feat: implement dedicated asset view pages with image zoom
```

### Bug Fixes
```bash
# Critical fixes
fix: resolve chart data persistence issue
fix: correct asset status update in approval workflow
fix: prevent duplicate asset registration

# UI/UX fixes
fix: mobile navigation menu not closing
fix: asset search pagination limit
fix: template path resolution for mobile devices
fix: modal cleanup and unused component removal
fix: currency format display to Rupiah throughout application
```

### Code Quality
```bash
# Refactoring
refactor: optimize database queries for asset listing
refactor: consolidate template components
refactor: simplify approval workflow logic
refactor: replace dropdown menus with direct action buttons
refactor: clean up unused modal components from templates

# Performance improvements
perf: implement caching for reference data
perf: optimize chart rendering performance
perf: reduce database query count in dashboard
```

### Documentation & Configuration
```bash
# Documentation
docs: update API documentation
docs: add Amazon Q guidance for new sessions
docs: update README with current features

# Configuration changes
chore: update dependencies to latest versions
chore: configure Docker for production deployment
chore: add environment variables for Supabase
```

### Database & Schema
```bash
# Database changes
feat: add comprehensive logging tables
feat: implement foreign key relationships
fix: correct database schema for user profiles

# Migration related
chore: migrate from Google Sheets to Supabase
feat: add audit trail tables for all operations
```

### Testing & CI/CD
```bash
# Testing
test: add unit tests for approval workflow
test: implement integration tests for asset operations

# CI/CD
ci: configure GitHub Actions for auto-deployment
ci: add Docker build optimization
```

### Breaking Changes
```bash
# Breaking changes (use ! after type)
feat!: migrate authentication to JWT-based system
refactor!: restructure template organization
```
