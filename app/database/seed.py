"""
Seed script untuk membuat user admin default.
"""
from sqlalchemy.orm import Session
from app.database.database import SessionLocal
from app.database.models import User, UserRole
from app.utils.auth import get_password_hash

def create_admin_user():
    """Membuat user admin default jika belum ada."""
    db = SessionLocal()
    try:
        # Cek apakah admin sudah ada
        admin = db.query(User).filter(User.username == "admin").first()
        if not admin:
            # Buat user admin baru
            admin_user = User(
                username="admin",
                password_hash=get_password_hash("admin123"),  # Ganti dengan password yang lebih aman
                email="admin@example.com",
                full_name="Admin User",
                role=UserRole.ADMIN,
                is_active=True
            )
            db.add(admin_user)
            db.commit()
            print("Admin user created successfully")
        else:
            print("Admin user already exists")
    except Exception as e:
        db.rollback()
        print(f"Error creating admin user: {e}")
    finally:
        db.close()

def create_manager_user():
    """Membuat user manager default jika belum ada."""
    db = SessionLocal()
    try:
        # Cek apakah manager sudah ada
        manager = db.query(User).filter(User.username == "manager").first()
        if not manager:
            # Buat user manager baru
            manager_user = User(
                username="manager",
                password_hash=get_password_hash("manager123"),  # Ganti dengan password yang lebih aman
                email="manager@example.com",
                full_name="Manager User",
                role=UserRole.MANAGER,
                is_active=True
            )
            db.add(manager_user)
            db.commit()
            print("Manager user created successfully")
        else:
            print("Manager user already exists")
    except Exception as e:
        db.rollback()
        print(f"Error creating manager user: {e}")
    finally:
        db.close()

def create_staff_user():
    """Membuat user staff default jika belum ada."""
    db = SessionLocal()
    try:
        # Cek apakah staff sudah ada
        staff = db.query(User).filter(User.username == "staff").first()
        if not staff:
            # Buat user staff baru
            staff_user = User(
                username="staff",
                password_hash=get_password_hash("staff123"),  # Ganti dengan password yang lebih aman
                email="staff@example.com",
                full_name="Staff User",
                role=UserRole.STAFF,
                is_active=True
            )
            db.add(staff_user)
            db.commit()
            print("Staff user created successfully")
        else:
            print("Staff user already exists")
    except Exception as e:
        db.rollback()
        print(f"Error creating staff user: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    create_admin_user()
    create_manager_user()
    create_staff_user()