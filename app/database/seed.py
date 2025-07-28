import logging
from supabase import create_client
from app.config import load_config

config = load_config()
supabase = create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_KEY)

def run_seed():
    logging.info("Running user seeding...")

    try:
        # ✅ Ambil daftar user dari Supabase Auth
        response = supabase.auth.admin.list_users()
        if not hasattr(response, "users"):
            raise ValueError("Unexpected response format from Supabase")

        existing_emails = [u.email for u in response.users]

        # ✅ Data user default
        users = [
            {"email": "m.hafidz@tog.co.id", "password": "Admin123!", "role": "admin"},
            {"email": "hafidzduddin@gmail.com", "password": "Manager123!", "role": "manager"},
            {"email": "hafidzduddin85@gmail.com", "password": "Staff123!", "role": "staff"},
        ]

        for user in users:
            if user["email"] in existing_emails:
                logging.info(f"User {user['email']} already exists.")
                continue

            # ✅ Buat user di Auth
            created = supabase.auth.admin.create_user({
                "email": user["email"],
                "password": user["password"],
                "email_confirm": True
            })

            if not created.user:
                logging.error(f"Failed to create user {user['email']}")
                continue

            user_id = created.user.id
            logging.info(f"Created user {user['email']} with ID {user_id}")

            # ✅ Tambahkan ke tabel profiles
            supabase.table("profiles").insert({
                "auth_user_id": user_id,
                "role": user["role"],
                "is_active": True
            }).execute()

        logging.info("✅ User seeding completed.")

    except Exception as e:
        logging.error(f"❌ Error seeding users: {str(e)}")