from sqlalchemy import text
from app.database.database import engine

def migrate_user_role():
    with engine.connect() as conn:
        # 1. Konversi data lama ke lowercase
        conn.execute(text("""
            UPDATE users
            SET role = LOWER(role);
        """))
        
        # Commit perubahan
        conn.commit()

if __name__ == "__main__":
    print("Running migration for user roles...")
    migrate_user_role()
    print("Migration completed.")