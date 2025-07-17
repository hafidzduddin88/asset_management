# app/database/migrations.py
from alembic import command
from alembic.config import Config
import os
import logging

logger = logging.getLogger(__name__)

def run_migrations(alembic_cfg_path="alembic.ini"):
    """Run database migrations using Alembic."""
    try:
        # Check if alembic.ini exists
        if not os.path.exists(alembic_cfg_path):
            logger.error(f"Alembic config file not found: {alembic_cfg_path}")
            return False
        
        # Load Alembic configuration
        alembic_cfg = Config(alembic_cfg_path)
        
        # Run migrations
        command.upgrade(alembic_cfg, "head")
        logger.info("Database migrations completed successfully")
        return True
    except Exception as e:
        logger.error(f"Error running database migrations: {str(e)}")
        return False

def create_initial_migration(alembic_cfg_path="alembic.ini", message="Initial migration"):
    """Create initial migration."""
    try:
        # Check if alembic.ini exists
        if not os.path.exists(alembic_cfg_path):
            logger.error(f"Alembic config file not found: {alembic_cfg_path}")
            return False
        
        # Load Alembic configuration
        alembic_cfg = Config(alembic_cfg_path)
        
        # Create migration
        command.revision(alembic_cfg, message=message, autogenerate=True)
        logger.info(f"Created migration: {message}")
        return True
    except Exception as e:
        logger.error(f"Error creating migration: {str(e)}")
        return False