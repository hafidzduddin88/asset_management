#!/usr/bin/env python
# clean.py - Script to clean up unnecessary files

import os
import shutil
import sys

def clean_build():
    print("🧹 Cleaning up unnecessary files...")
    
    # Remove unnecessary files
    dirs_to_remove = [
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".coverage"
    ]
    
    for root, dirs, files in os.walk("."):
        for dir_name in dirs:
            if dir_name in dirs_to_remove:
                try:
                    shutil.rmtree(os.path.join(root, dir_name))
                    print(f"  ✓ Removed {os.path.join(root, dir_name)}")
                except:
                    print(f"  ✗ Failed to remove {os.path.join(root, dir_name)}")
    
    # Create .renderignore file
    print("Creating .renderignore file...")
    with open(".renderignore", "w") as f:
        f.write("""# Files to ignore during deployment
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
.env.local
.venv
env/
venv/
ENV/
.coverage
htmlcov/
.pytest_cache/
.mypy_cache/
.git/
.github/
tests/
docs/
*.md
!README.md
""")
    print("  ✓ Created .renderignore")
    
    print("\n✅ Cleanup complete!")

if __name__ == "__main__":
    clean_build()