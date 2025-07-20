#!/usr/bin/env python
# clean.py - Script to optimize repository size

import os
import shutil
import glob
import subprocess

def optimize_repo_size():
    """Optimize repository size by removing unnecessary files."""
    print("🧹 Optimizing repository size...")
    
    # Track statistics
    removed_count = 0
    freed_bytes = 0
    
    # Files and directories to clean up
    patterns_to_remove = [
        # Python cache
        "**/__pycache__",
        "**/*.pyc",
        "**/*.pyo",
        "**/*.pyd",
        "**/.pytest_cache",
        "**/.mypy_cache",
        
        # Temporary files
        "**/*.log",
        "**/*.tmp",
        "**/*.bak",
        
        # Development files
        "**/.DS_Store",
        "**/Thumbs.db",
        
        # Git related (be careful with these)
        ".git/objects/pack/*.pack",
        ".git/objects/pack/*.idx",
    ]
    
    # Process each pattern
    for pattern in patterns_to_remove:
        for path in glob.glob(pattern, recursive=True):
            if os.path.exists(path):
                size = 0
                try:
                    if os.path.isfile(path):
                        size = os.path.getsize(path)
                        os.remove(path)
                        removed_count += 1
                        freed_bytes += size
                        print(f"  ✓ Removed file: {path} ({size/1024:.1f} KB)")
                    elif os.path.isdir(path):
                        for root, _, files in os.walk(path):
                            for file in files:
                                file_path = os.path.join(root, file)
                                if os.path.exists(file_path):
                                    size += os.path.getsize(file_path)
                        shutil.rmtree(path)
                        removed_count += 1
                        freed_bytes += size
                        print(f"  ✓ Removed directory: {path} ({size/1024:.1f} KB)")
                except Exception as e:
                    print(f"  ✗ Failed to remove {path}: {e}")
    
    # Optimize static image files
    print("\n🖼️ Optimizing image files...")
    try:
        # This requires PIL/Pillow which is already in requirements.txt
        from PIL import Image
        
        img_dir = "app/static/img"
        if os.path.exists(img_dir):
            for img_file in os.listdir(img_dir):
                if img_file.lower().endswith(('.png', '.jpg', '.jpeg')):
                    img_path = os.path.join(img_dir, img_file)
                    try:
                        original_size = os.path.getsize(img_path)
                        # Open and save with optimization
                        with Image.open(img_path) as img:
                            # Resize if too large (e.g., over 1000px)
                            if max(img.size) > 1000:
                                ratio = 1000 / max(img.size)
                                new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
                                img = img.resize(new_size, Image.LANCZOS)
                            
                            # Save with optimization
                            if img_file.lower().endswith('.png'):
                                img.save(img_path, optimize=True, quality=85)
                            else:  # JPEG
                                img.save(img_path, optimize=True, quality=85)
                                
                        new_size = os.path.getsize(img_path)
                        saved = original_size - new_size
                        if saved > 0:
                            print(f"  ✓ Optimized {img_file}: {saved/1024:.1f} KB saved")
                            freed_bytes += saved
                    except Exception as e:
                        print(f"  ✗ Failed to optimize {img_file}: {e}")
    except ImportError:
        print("  ✗ PIL/Pillow not available, skipping image optimization")
    
    # Optimize Git repository if git is available
    print("\n🔄 Optimizing Git repository...")
    try:
        if os.path.exists(".git"):
            subprocess.run(["git", "gc", "--aggressive", "--prune=now"], 
                          check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            print("  ✓ Git repository optimized")
    except Exception as e:
        print(f"  ✗ Failed to optimize Git repository: {e}")
    
    # Create .dockerignore if it doesn't exist
    if not os.path.exists(".dockerignore"):
        print("\n📄 Creating .dockerignore file...")
        with open(".dockerignore", "w") as f:
            f.write("""# Byte-compiled / cache files
__pycache__/
*.py[cod]
*.pyo
*.pyd
.pytest_cache/

# Virtual environments
venv/
env/
.venv/
.env/

# Git
.git/
.gitignore
.github/

# Editor configs
.vscode/
.idea/

# Logs and temp files
*.log
*.tmp

# Documentation
docs/
*.md
!README.md

# Development files
tests/
.dockerignore
Dockerfile*
render.yaml
""")
        print("  ✓ Created .dockerignore")
    
    # Print summary
    print(f"\n✅ Optimization complete!")
    print(f"   Removed {removed_count} files/directories")
    print(f"   Freed approximately {freed_bytes / (1024*1024):.2f} MB")

if __name__ == "__main__":
    optimize_repo_size()