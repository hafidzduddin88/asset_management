<div align="center">

# 🏢 Asset Management System (AMBP)

[![Live Demo](https://img.shields.io/badge/🌐_Live_Demo-Visit_Site-blue?style=for-the-badge)](https://ambp.onrender.com)
[![GitHub](https://img.shields.io/badge/GitHub-Repository-black?style=for-the-badge&logo=github)](https://github.com/hafidzduddin88/asset_management)
[![Docker](https://img.shields.io/badge/Docker-GHCR-2496ED?style=for-the-badge&logo=docker)](https://github.com/hafidzduddin88/asset_management/pkgs/container/ambp)

**Modern web-based asset management with role-based authentication & approval workflows**

*Created by Asset Management & Business Process Department*

</div>

---

## ✨ Features

### 🎯 Core Features
- 📝 **Asset Management** - Add/Edit/Relocate with direct action buttons
- 🏢 **Owner System** - GA (room-based) vs IT (user-based) assignment
- 🔧 **Asset Issues** - Damage/Lost/Disposal with single approval
- 🛠️ **Asset Repair** - Workflow for damaged assets
- 💰 **Depreciation** - SuperAdmin value recalculation
- 📦 **Bulk Update** - 3-step workflow with Excel import
- 👥 **Role-based Auth** - Admin/Manager/Staff with JWT
- 🔐 **Password Recovery** - Email-based with secure token
- ✅ **Approval System** - Hierarchical Admin ↔ Manager
- 👤 **User Management** - Business unit integration

### 🚀 Advanced Features
- 📱 **PWA Support** - Offline-ready with install prompts
- 📄 **Excel Export** - Optimized with owner & user columns
- 📈 **Dashboard** - Monthly/Quarterly/Yearly analytics
- 🔗 **Google Drive** - Asset photo storage with zoom
- 📋 **Audit Trail** - Comprehensive logging
- 💱 **Rupiah Format** - Local currency display
- 🔍 **Smart Filters** - GA/IT filtering in all pages

---

## 🛠️ Tech Stack

**Backend:** FastAPI • Supabase PostgreSQL • JWT • Python 3.12  
**Frontend:** Tailwind CSS • Alpine.js • HTMX • Chart.js • PWA  
**DevOps:** Docker • GitHub Actions • Render • GHCR

---

## 🚀 Quick Start

```bash
# Local Development
git clone https://github.com/hafidzduddin88/asset_management.git
cd asset_management
python -m venv venv && source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env  # Edit with your credentials
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Docker
docker run -p 8000:8000 --env-file .env ghcr.io/hafidzduddin88/ambp:latest
```

---

## ⚙️ Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `SUPABASE_URL` | Supabase project URL | ✅ |
| `SUPABASE_ANON_KEY` | Supabase anonymous key | ✅ |
| `SUPABASE_SERVICE_KEY` | Supabase service role key | ✅ |
| `GOOGLE_CREDS_JSON` | Google Service Account credentials | ✅ |
| `DRIVE_FOLDER_ID` | Google Drive folder ID | ❌ |
| `PORT` | Application port (default: 8000) | ❌ |

---

## 🏢 Owner System

**GA vs IT Asset Assignment:**

| Owner | Type | Required Fields | Use Case |
|-------|------|-----------------|----------|
| **GA** | Room-based | Location + Room | Fixed assets (furniture, equipment) |
| **IT** | User-based | Assigned User | Mobile assets (laptops, phones) |

**Features:**
- ✅ Conditional form fields based on owner selection
- ✅ Auto-resolution: User name → UUID (full_name → username)
- ✅ Owner filter in list pages and bulk update
- ✅ Excel export includes owner and assigned user

---

## 👥 User Roles

| Role | Permissions | Approval |
|------|-------------|----------|
| **Admin** | Full system access, User management | Manager approval |
| **Manager** | Asset operations, Approve admin requests | Admin approval |
| **Staff** | Basic operations, Submit requests | Admin approval |

---

## 🔄 Workflows

**Asset Lifecycle:**
```
Registration → Active → Damaged → Repair → Active/Disposed
                    ↓
                  Lost/Disposal
```

**Approval Flow:**
- Staff/Manager → Admin approval
- Admin → Manager approval
- Single approval for disposal (no execution step)

---



---

## 🔗 Architecture

**Database:** Supabase PostgreSQL with foreign keys, log tables, JWT auth  
**Storage:** Google Drive for asset photos  
**Deployment:** Docker → GHCR → Render (auto-deploy)  
**Templates:** Dual system (desktop/mobile) with device detection

---

## ⚡ Optimizations

**Performance:**
- 11 essential packages (reduced from 25+)
- Python 3.12-slim Docker image (faster builds)
- Smart caching with 10s TTL
- Single worker for faster startup
- Path-based GitHub Actions triggers

**Security:**
- JWT session with auto-refresh
- Email-based password recovery
- Profile protection against overwrites
- Role-based access control

**UX:**
- Direct action buttons (no dropdowns)
- Conditional forms (GA/IT)
- PWA with offline support
- Responsive dual templates

---



---



---



---

<div align="center">

### 🌟 Star this project if you find it helpful!

[![GitHub stars](https://img.shields.io/github/stars/hafidzduddin88/asset_management?style=social)](https://github.com/hafidzduddin88/asset_management/stargazers)
[![GitHub forks](https://img.shields.io/github/forks/hafidzduddin88/asset_management?style=social)](https://github.com/hafidzduddin88/asset_management/network/members)

**Made with ❤️ by Asset Management & Business Process Department**

</div>