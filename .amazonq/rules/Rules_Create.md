# Asset Management Business Platform (AMBP)

## Core Features

- **Asset Registration** - Add/Edit/Relocate assets with approval workflow
- **Asset Issues** - Report Damage/Lost/Disposal requests
- **Asset Repair** - Report repair completion for damaged assets
- **Role-based Authentication** - Admin/Manager/Staff with hierarchical approvals
- **Dashboard Analytics** - Real-time charts and metrics
- **PWA Support** - Offline-friendly, mobile-ready application
- **Export Reports** - Excel and PDF generation
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
- **Excel Export** - Customizable table and column selection
- **PDF Reports** - Formatted reports with asset details
- **Role-based Access** - Admin-only for sensitive data
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

Use Conventional Commits format:

```bash
# Feature additions
feat: add asset repair completion workflow

# Bug fixes
fix: resolve chart data persistence issue

# Documentation
docs: update API documentation

# Refactoring
refactor: optimize database queries

# Performance improvements
perf: implement caching for reference data
```
