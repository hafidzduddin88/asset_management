# Web-Based Asset Management System

Features

- Add/Edit/Relocate/Dispose Assets (with Admin Approval)
- Role-based Authentication (Admin & Staff)
- Card-style Asset UI with Photo Previews (Google Drive)
- PWA Support (Offline-friendly, Mobile-ready)
- Export Reports to Excel and PDF
- Google Sheets & Drive API Integration
- Admin Approval Workflow for all critical actions

Backend:
- FastAPI + Uvicorn
- SQLAlchemy (PostgreSQL)
- Google Sheets API (gspread)
- Google Drive API
- JWT Authentication
- Argon2 Password Hashing

Frontend:
- Tailwind CSS
- Alpine.js
- HTMX
- Jinja2
- Client-side filtering, responsive design
- PWA (Service Worker + Web Manifest)

Google Drive Integration
- Upload asset photos via form (Admin only)
- Stored in structured folders by asset tag
- Public preview via Google Drive viewer
- File metadata saved to backend

Authentication & Role
- JWT-based Auth
- Argon2 password hashing
- Role-Based Access:
  - **Admin:** Full control, approves changes
  - **Staff:** Submit requests

Admin Approval Workflow
All critical actions require admin approval:
- Adding Assets
- Damaged Assets
- Repaired Assets
- Relocation
- Disposal
- Upload/Change Photos Assets

Flow:
1. Staff submits request
2. Stored in pending approvals
3. Admin dashboard to approve/reject
4. Decisions logged in audit trail

Disposal Management

- Admin only
- Stores:
  - Disposal Date
  - Reason
  - Notes/Evidence
  - Disposed By
- Asset archived (not deleted)

---

Reporting

- Reports include:
  - New, Damaged, Repaired, Relocated, Disposed
- Export options:
  - Excel (.xlsx)
  - PDF
- Include asset photo URLs, approval metadata

---

Dev Guidelines

- Modular Code (Separation of concerns)
- Follow REST API standard
- Form + API validation
- Secure Service Account setup
- Use Conventional Commits

---

Commit Example

```bash
feat: implement admin approval workflow with audit trail
```
