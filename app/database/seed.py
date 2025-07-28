# seed.py
from supabase import create_client
import os

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

USERS = [
    {
        "email": "admin@yourdomain.com",
        "password": "AdminPass123",
        "full_name": "Super Admin",
        "role": "admin"
    },
    {
        "email": "manager@yourdomain.com",
        "password": "ManagerPass123",
        "full_name": "Project Manager",
        "role": "manager"
    },
    {
        "email": "staff@yourdomain.com",
        "password": "StaffPass123",
        "full_name": "Staff Member",
        "role": "staff"
    }
]

def run_seed():
    print("🔍 Running user seeding...")
    try:
        existing_users = supabase.auth.admin.list_users()
        existing_emails = [user.email for user in existing_users.users]

        for user in USERS:
            if user["email"] in existing_emails:
                print(f"✅ User already exists: {user['email']}")
                continue

            response = supabase.auth.admin.create_user({
                "email": user["email"],
                "password": user["password"],
                "email_confirm": True,
                "user_metadata": {
                    "full_name": user["full_name"],
                    "role": user["role"]
                }
            })
            print(f"✅ Created {user['role']} user: {user['email']}")

    except Exception as e:
        print(f"❌ Error seeding users: {str(e)}")