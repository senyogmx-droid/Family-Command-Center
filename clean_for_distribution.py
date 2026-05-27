#!/usr/bin/env python3
"""
Family Command Center - Distribution Cleanup Script
Removes all personal/family data and resets project to fresh state.
Run this BEFORE packaging for distribution.
"""

import os
import json
import sqlite3
import shutil
import hashlib
from pathlib import Path

# ============================================================
# CONFIGURATION - Adjust these paths if needed
# ============================================================
PROJECT_ROOT = Path(__file__).parent
DB_FILE = PROJECT_ROOT / "database.db"
CALENDAR_FILE = PROJECT_ROOT / "calendar.json"
PHOTOS_FILE = PROJECT_ROOT / "photos.json"
SOLAR_FILE = PROJECT_ROOT / "solar.json"
DELETED_PHOTOS_FILE = PROJECT_ROOT / "deleted_photos.json"
SOLAR_TOKEN_FILE = PROJECT_ROOT / "solar_token.txt"

# Directories to clean (keep the folders, delete contents)
MEDIA_DIRS = [
    PROJECT_ROOT / "static" / "media" / "child_photos",
    PROJECT_ROOT / "static" / "media" / "manual_uploads",
    PROJECT_ROOT / "static" / "media" / "submissions",
    PROJECT_ROOT / "photos",  # Google Photos cache
]

# Files to delete entirely (unused or test files)
FILES_TO_DELETE = [
    PROJECT_ROOT / "router.py",
    PROJECT_ROOT / "deploy.ps1",
    PROJECT_ROOT / "deploy_to_linux.bat",
    PROJECT_ROOT / "deploy_to_pi.sh",
    PROJECT_ROOT / "setup_scheduler.ps1",
    PROJECT_ROOT / "fetch_enphase_token.py",
    PROJECT_ROOT / "handoff_next_session.md",
    PROJECT_ROOT / "project_overview.md",
    PROJECT_ROOT / "project_task_overview.md",
    PROJECT_ROOT / "walkthrough_2026_05_24.md",
    PROJECT_ROOT / "DEVELOPER_NOTES.md",
    # Any backup/temp files
    *PROJECT_ROOT.glob("*.recovered"),
    *PROJECT_ROOT.glob("*.temp"),
    *PROJECT_ROOT.glob("*.backup"),
    *PROJECT_ROOT.glob("*_backup.db"),
    *PROJECT_ROOT.glob("*_test_*.db"),
    *PROJECT_ROOT.glob("remote_*.db"),
    PROJECT_ROOT / "family_dashboard.db",
]

# ============================================================
# FUNCTIONS
# ============================================================

def clean_database():
    """Reset database to fresh state with default admin user only."""
    if not DB_FILE.exists():
        print("[!] database.db not found. Skipping.")
        return
    
    print("[*] Cleaning database...")
    conn = sqlite3.connect(str(DB_FILE))
    cursor = conn.cursor()
    
    # Clear all user/child data
    cursor.execute("DELETE FROM children")
    cursor.execute("DELETE FROM chores")
    cursor.execute("DELETE FROM chore_history")
    cursor.execute("DELETE FROM chore_submissions")
    cursor.execute("DELETE FROM parent_spotlights")
    cursor.execute("DELETE FROM habit_reminders")
    cursor.execute("DELETE FROM rewards")
    
    # Reset system_config to defaults
    cursor.execute("DELETE FROM system_config")
    default_configs = [
        ("admin_configured", "false"),
        ("photo_source_mode", "default"),
        ("solar_enabled", "false"),
        ("peak_hour_mode", "false"),
        ("star_of_the_day", ""),
        ("weather_location_name", "Stafford, VA 22554"),
        ("weather_latitude", "38.4232"),
        ("weather_longitude", "-77.4080"),
        ("quote_refresh", "daily"),
        ("quote_category", "general"),
        ("timezone", "America/New_York"),
    ]
    for key, value in default_configs:
        cursor.execute("INSERT OR REPLACE INTO system_config (key, value) VALUES (?, ?)", (key, value))
    
    # Reset users table (keep only default admin)
    cursor.execute("DELETE FROM users")
    default_hash = hashlib.sha256("admin".encode('utf-8')).hexdigest()
    cursor.execute("INSERT INTO users (username, password_hash) VALUES ('parent', ?)", (default_hash,))
    
    # Reset users table columns to defaults
    cursor.execute("UPDATE users SET main_page_privacy = 0")
    
    conn.commit()
    conn.close()
    print("[+] Database cleaned successfully.")

def clean_json_files():
    """Reset JSON cache files to empty/default state."""
    # calendar.json -> empty array
    with open(CALENDAR_FILE, 'w') as f:
        json.dump([], f)
    print("[+] calendar.json reset to []")
    
    # photos.json -> empty array
    with open(PHOTOS_FILE, 'w') as f:
        json.dump([], f)
    print("[+] photos.json reset to []")
    
    # solar.json -> empty object
    with open(SOLAR_FILE, 'w') as f:
        json.dump({}, f)
    print("[+] solar.json reset to {}")
    
    # deleted_photos.json -> empty array (if exists)
    if DELETED_PHOTOS_FILE.exists():
        with open(DELETED_PHOTOS_FILE, 'w') as f:
            json.dump([], f)
        print("[+] deleted_photos.json reset to []")

def clean_media_folders():
    """Delete all files inside media folders but keep the folders themselves."""
    for folder in MEDIA_DIRS:
        if folder.exists():
            for item in folder.iterdir():
                if item.is_file():
                    item.unlink()
                elif item.is_dir():
                    shutil.rmtree(item)
            print(f"[+] Cleaned: {folder}")
        else:
            folder.mkdir(parents=True, exist_ok=True)
            print(f"[+] Created: {folder}")

def delete_unused_files():
    """Remove files that are not needed for distribution."""
    for file_path in FILES_TO_DELETE:
        if file_path.exists():
            file_path.unlink()
            print(f"[+] Deleted: {file_path.name}")
        else:
            print(f"[-] Not found: {file_path.name}")

def clean_solar_token():
    """Remove solar token file if it exists."""
    if SOLAR_TOKEN_FILE.exists():
        SOLAR_TOKEN_FILE.unlink()
        print("[+] Deleted: solar_token.txt")

def verify_landscapes():
    """Ensure the 4 default landscape images exist (optional but safe)."""
    landscape_folder = PROJECT_ROOT / "static" / "media" / "landscapes"
    expected_files = [
        "mountain_sunset.jpg",
        "forest_lake.jpg",
        "misty_canyon.jpg",
        "snowy_peaks.jpg"
    ]
    if not landscape_folder.exists():
        landscape_folder.mkdir(parents=True, exist_ok=True)
        print("[!] Landscapes folder was missing – created it.")
    for filename in expected_files:
        filepath = landscape_folder / filename
        if not filepath.exists():
            print(f"[!] Warning: Missing default landscape: {filename}")
        else:
            print(f"[✓] Found: {filename}")

def main():
    print("=" * 60)
    print("Family Command Center - Distribution Cleanup Script")
    print("=" * 60)
    print()
    
    confirm = input("⚠️  This will DELETE ALL personal/family data. Continue? (yes/no): ")
    if confirm.lower() != 'yes':
        print("Aborted.")
        return
    
    print()
    clean_database()
    clean_json_files()
    clean_media_folders()
    delete_unused_files()
    clean_solar_token()
    verify_landscapes()
    
    print()
    print("=" * 60)
    print("✅ Cleanup complete! Your project is now ready for distribution.")
    print("   - Database reset (admin/admin)")
    print("   - All JSON caches emptied")
    print("   - All media files deleted")
    print("   - Unused/test files removed")
    print("   - 4 default landscape images verified")
    print("=" * 60)

if __name__ == "__main__":
    main()