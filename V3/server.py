import os
import json
import sqlite3
import hashlib
import queue
import math
import random
import logging
import base64
import sys
import subprocess
import mimetypes
from collections import defaultdict
from logging.handlers import RotatingFileHandler

# Explicitly register standard MIME types to prevent Windows Registry corruption from breaking "nosniff" headers
mimetypes.add_type('application/javascript', '.js')
mimetypes.add_type('text/css', '.css')
mimetypes.add_type('image/png', '.png')
mimetypes.add_type('image/jpeg', '.jpg')
mimetypes.add_type('image/jpeg', '.jpeg')
mimetypes.add_type('image/svg+xml', '.svg')
mimetypes.add_type('image/webp', '.webp')
mimetypes.add_type('audio/wav', '.wav')


# -------------------------------------------------------------
# DOTENV FAIL-SAFE LOADER HOOK
# -------------------------------------------------------------
def load_env_file():
    """
    Attempts to read and parse the local .env configuration file into os.environ.
    This provides a zero-dependency fallback for loading keys during direct runs.
    """
    env_path = '.env'
    if not os.path.exists(env_path):
        env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
    if os.path.exists(env_path):
        try:
            with open(env_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        k, v = line.split('=', 1)
                        k = k.strip()
                        v = v.strip()
                        # Strip optional quotes
                        if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
                            v = v[1:-1]
                        os.environ.setdefault(k, v)
        except Exception as e:
            print(f"[!] Warning: Failed to parse .env file: {e}")

load_env_file()

# -------------------------------------------------------------
# DYNAMIC CROSS-PLATFORM DEPENDENCY INSTALLER HOOK
# -------------------------------------------------------------
def auto_align_dependencies():
    """
    Scans for required external dependencies at start.
    If running natively (and not in Docker) and packages are missing, 
    attempts to dynamically align and install requirements based on host OS.
    """
    required_imports = {
        "flask": "Flask==2.3.3",
        "flask_compress": "flask-compress==1.14",
        "cryptography": "cryptography==41.0.7",
        "feedparser": "feedparser==6.0.10",
        "requests": "requests==2.31.0",
        "simplejson": "simplejson==3.19.2",
    }
    
    # On Windows, if running natively (not in Docker), also check tray app dependencies optionally
    if sys.platform.startswith("win32") and not os.environ.get("PRODUCTION"):
        required_imports.update({
            "pystray": "pystray==0.19.0",
            "PIL": "pillow==10.1.0",
            "psutil": "psutil==5.9.6",
        })

    missing_packages = []
    for module_name, package_spec in required_imports.items():
        try:
            __import__(module_name)
        except ImportError:
            missing_packages.append(package_spec)

    if missing_packages:
        print(f"[*] Missing dependencies detected at startup: {', '.join(missing_packages)}")
        print("[*] Attempting to auto-align and install missing requirements...")
        try:
            if os.path.exists("requirements.txt"):
                subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
            else:
                subprocess.check_call([sys.executable, "-m", "pip", "install"] + missing_packages)
            print("[*] Success! Dependencies successfully installed.")
        except Exception as e:
            print(f"[!] Failed to auto-install dependencies: {e}")
            print("[!] Please run: pip install -r requirements.txt manually.")

# Execute dependency alignment before importing third-party libraries (skip if compiled PyInstaller bundle)
if not getattr(sys, 'frozen', False):
    auto_align_dependencies()

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from flask import Flask, jsonify, request, Response, send_from_directory, session, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash

import datetime
from time import time

try:
    from flask_compress import Compress
    HAS_FLASK_COMPRESS = True
except ImportError:
    HAS_FLASK_COMPRESS = False

# Resolve static folder relative to current working directory or where server.py is
script_dir = os.path.dirname(os.path.abspath(__file__))
if getattr(sys, 'frozen', False):
    static_folder = "static"
else:
    dist_static = os.path.join(script_dir, "dist", "static")
    if os.path.exists(dist_static):
        static_folder = dist_static
    else:
        static_folder = os.path.join(script_dir, "static")

app = Flask(__name__, static_folder=static_folder, static_url_path="")

# Load Flask secret key from environment variable with a dev-only fallback
flask_secret = os.environ.get('FLASK_SECRET_KEY')
if not flask_secret:
    if os.environ.get('PRODUCTION', '').lower() == 'true':
        raise RuntimeError("CRITICAL SECURITY ERROR: FLASK_SECRET_KEY must be set in PRODUCTION environment!")
    else:
        flask_secret = "family_command_center_v2_secret_key"

app.config.update(
    SECRET_KEY=flask_secret,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    MAX_CONTENT_LENGTH=16 * 1024 * 1024  # Enforce 16 MB maximum file upload size
)

# Enforce secure cookies only over HTTPS in production
if os.environ.get('PRODUCTION', '').lower() == 'true':
    app.config['SESSION_COOKIE_SECURE'] = True

app.config['PERMANENT_SESSION_LIFETIME'] = datetime.timedelta(minutes=5)
app.config['SESSION_REFRESH_EACH_REQUEST'] = True

if HAS_FLASK_COMPRESS:
    Compress(app)
    app.config['COMPRESS_MIMETYPES'] = ['text/html', 'text/css', 'text/xml', 'application/json', 'application/javascript']
    app.config['COMPRESS_LEVEL'] = 6
    app.config['COMPRESS_MIN_SIZE'] = 500
else:
    print("[!] NOTE: 'flask-compress' package is not installed. Automated Gzip compression is disabled.")
    print("    To enable compression (highly recommended for high-performance dashboards), run: pip install flask-compress")

# Disable caching for static/dynamic files to prevent dashboard/kiosk cache issues and apply security headers
@app.after_request
def add_header(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    
    # Inject security headers (HSTS, X-Content-Type-Options, X-Frame-Options)
    if os.environ.get('PRODUCTION', '').lower() == 'true':
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    
    return response

@app.before_request
def redirect_http_to_https():
    # Only enforce if PRODUCTION environment variable is set to 'true'
    if os.environ.get('PRODUCTION', '').lower() == 'true':
        # Do not redirect if already secure natively or via proxy header
        if request.is_secure or request.headers.get('X-Forwarded-Proto', '').lower() == 'https':
            return
        # Only redirect if standard HTTP request
        url = request.url.replace('http://', 'https://', 1)
        return redirect(url, code=301)

@app.before_request
def refresh_session():
    if session.get('parent_auth'):
        session.permanent = True

login_attempts = defaultdict(list)

def is_rate_limited(ip):
    now = datetime.datetime.now()
    # Clean old attempts
    login_attempts[ip] = [t for t in login_attempts[ip] if now - t < datetime.timedelta(minutes=5)]
    if len(login_attempts[ip]) >= 5:
        return True
    login_attempts[ip].append(now)
    return False

DB_FILE = "data/database.db"

# Auto-migrate legacy database from root directory if present
if os.path.exists("database.db") and not os.path.exists(DB_FILE):
    os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
    import shutil
    try:
        shutil.move("database.db", DB_FILE)
        print(f"[*] Successfully migrated legacy database.db to new persistent path: {DB_FILE}")
    except Exception as e:
        print(f"[!] Warning: Failed to move legacy database.db: {e}")
else:
    os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)

def get_active_log_dir():
    """Dynamically resolves the active background daemon log directory (with /home/senyog/logs prioritised)."""
    from pathlib import Path
    log_dirs = [
        Path("/home/senyog/logs"),
        Path(os.path.dirname(os.path.abspath(__file__))) / "logs",
        Path(os.path.dirname(os.path.abspath(__file__))).parent / "logs",
        Path("logs")
    ]
    for d in log_dirs:
        if d.exists():
            return d
    # Fallback log directory relative to server.py
    fallback_dir = Path(os.path.dirname(os.path.abspath(__file__))) / "logs"
    fallback_dir.mkdir(exist_ok=True)
    return fallback_dir

LOG_DIR = str(get_active_log_dir())

# Configure rotating file logging handler
file_handler = RotatingFileHandler(os.path.join(LOG_DIR, 'server.log'), maxBytes=10*1024*1024, backupCount=5)
file_formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s')
file_handler.setFormatter(file_formatter)
logging.getLogger().addHandler(file_handler)
logging.getLogger().setLevel(logging.INFO)
# Read AES key from environment variable (must be 32 bytes base64 encoded)
AES_KEY_B64 = os.environ.get('FAMILY_DASHBOARD_AES_KEY') or os.environ.get('AES_KEY')
if not AES_KEY_B64:
    # Generate a random key on first run and print it (user must store it)
    import secrets
    new_key = secrets.token_bytes(32)
    AES_KEY_B64 = base64.b64encode(new_key).decode('utf-8')
    print(f"[!] WARNING: No AES key found in environment. Generated new key:\n{AES_KEY_B64}\n"
          "Please set FAMILY_DASHBOARD_AES_KEY environment variable to this value.")
    # Still use it for this session
else:
    new_key = base64.b64decode(AES_KEY_B64)

AES_KEY = new_key  # 32 bytes
APP_VERSION = "v3.7.1"

REWARD_POOL = [
    {"name": "🔥 Fire Trail", "weight": 10, "type": "cosmetic"},
    {"name": "✨ Sparkle Dust", "weight": 10, "type": "cosmetic"},
    {"name": "🚀 Comet Speed Boost", "weight": 8, "type": "cosmetic"},
    {"name": "🍕 Victory Pizza", "weight": 6, "type": "consumable"},
    {"name": "🐱 Neko Companion", "weight": 5, "type": "cosmetic"},
    {"name": "⏰ 15-Min Bedtime Extension", "weight": 4, "type": "privilege"},
    {"name": "🎮 30-Min Extra Screen Time", "weight": 4, "type": "privilege"},
    {"name": "🧹 Skip Chore Coupon", "weight": 5, "type": "consumable"},
    {"name": "🌌 Cosmic Custom UI Theme", "weight": 3, "type": "cosmetic"},
    {"name": "👑 Rare Gold Card Profile Frame", "weight": 2, "type": "cosmetic"},
    {"name": "🍔 Select Dinner of Choice", "weight": 3, "type": "real_world"},
    {"name": "🎬 Pick Family Movie Night", "weight": 3, "type": "real_world"},
    {"name": "🍦 Double Scoop Ice Cream Treat", "weight": 4, "type": "real_world"},
    {"name": "🔑 +1 Vault Key", "weight": 6, "type": "key"},
    {"name": "⭐ Bonus 25 XP", "weight": 8, "type": "xp"}
]

def get_random_reward():
    total_weight = sum(r["weight"] for r in REWARD_POOL)
    r = random.randint(1, total_weight)
    for reward in REWARD_POOL:
        if r <= reward["weight"]:
            return reward["name"]
        r -= reward["weight"]
    return REWARD_POOL[0]["name"]

def check_and_award_milestones(child_id, chore_id, conn):
    cursor = conn.cursor()
    
    chore = cursor.execute("SELECT name FROM chores WHERE id = ?", (chore_id,)).fetchone()
    if not chore:
        return None
    chore_name = chore["name"]
    
    # 1. 7-day streak for this specific chore
    streak_dates = cursor.execute("""
        SELECT completed_date FROM chore_history
        WHERE child_id = ? AND chore_id = ?
        ORDER BY completed_date DESC LIMIT 7
    """, (child_id, chore_id)).fetchall()
    
    streak = 0
    check_date = datetime.date.today()
    for _ in range(7):
        date_str = check_date.isoformat()
        if any(d["completed_date"] == date_str for d in streak_dates):
            streak += 1
            check_date -= datetime.timedelta(days=1)
        else:
            break
    
    if streak >= 7:
        reward = get_random_reward()
        child = cursor.execute("SELECT unlocked_assets FROM children WHERE id = ?", (child_id,)).fetchone()
        assets = json.loads(child["unlocked_assets"]) if (child and child["unlocked_assets"]) else []
        if reward not in assets:
            assets.append(reward)
            cursor.execute("UPDATE children SET unlocked_assets = ? WHERE id = ?", (json.dumps(assets), child_id))
            return {"type": "streak", "chore": chore_name, "reward": reward}
    
    # 2. Weekly accumulation (20 chores in 7 days)
    week_ago = (datetime.date.today() - datetime.timedelta(days=7)).isoformat()
    total_weekly = cursor.execute("""
        SELECT COUNT(*) as cnt FROM chore_history
        WHERE child_id = ? AND completed_date >= ?
    """, (child_id, week_ago)).fetchone()["cnt"]
    
    week_number = datetime.date.today().isocalendar()[1]
    last_weekly = cursor.execute("SELECT value FROM system_config WHERE key = ?", (f"weekly_bonus_{child_id}_{week_number}",)).fetchone()
    
    if total_weekly >= 20 and not last_weekly:
        reward = get_random_reward()
        child = cursor.execute("SELECT unlocked_assets FROM children WHERE id = ?", (child_id,)).fetchone()
        assets = json.loads(child["unlocked_assets"]) if (child and child["unlocked_assets"]) else []
        if reward not in assets:
            assets.append(reward)
            cursor.execute("UPDATE children SET unlocked_assets = ? WHERE id = ?", (json.dumps(assets), child_id))
            cursor.execute("INSERT OR REPLACE INTO system_config (key, value) VALUES (?, 'true')", (f"weekly_bonus_{child_id}_{week_number}",))
            return {"type": "weekly", "count": total_weekly, "reward": reward}
    
    return None

def get_db():
    """
    Establishes a hardened, concurrency-safe SQLite database connection link.
    Enables WAL mode to completely eliminate multi-device kiosk tablet lockups.
    """
    import sqlite3
    
    # Increase the busy timeout threshold from default 5.0 to 10.0 seconds
    conn = sqlite3.connect(DB_FILE, timeout=10.0)
    
    # Configure connection behaviors to treat rows like dictionary objects safely
    conn.row_factory = sqlite3.Row
    
    cursor = conn.cursor()
    try:
        # Enforce Write-Ahead Logging for high-concurrency smart home setups
        cursor.execute("PRAGMA journal_mode=WAL;")
        
        # Explicitly activate foreign key structural constraint enforcement
        cursor.execute("PRAGMA foreign_keys = ON;")
        
    except sqlite3.OperationalError as e:
        print(f"[!] Warning: Could not initialize database optimization pragmas: {e}")
        
    return conn

def encrypt_val(plain_text: str) -> str:
    if not plain_text:
        return ""
    iv = os.urandom(12)  # 96-bit IV for GCM
    cipher = Cipher(algorithms.AES(AES_KEY), modes.GCM(iv), backend=default_backend())
    encryptor = cipher.encryptor()
    ciphertext = encryptor.update(plain_text.encode('utf-8')) + encryptor.finalize()
    # Combine IV, tag, ciphertext
    combined = iv + encryptor.tag + ciphertext
    return base64.b64encode(combined).decode('utf-8')

def decrypt_val(cipher_text: str) -> str:
    if not cipher_text:
        return ""
    
    # 1. Try to decrypt using the new AES-GCM method
    try:
        combined = base64.b64decode(cipher_text.encode('utf-8'))
        if len(combined) > 28:  # 12 byte IV + 16 byte tag + at least 1 byte ciphertext
            iv = combined[:12]
            tag = combined[12:28]
            ciphertext = combined[28:]
            cipher = Cipher(algorithms.AES(AES_KEY), modes.GCM(iv, tag), backend=default_backend())
            decryptor = cipher.decryptor()
            plain = decryptor.update(ciphertext) + decryptor.finalize()
            return plain.decode('utf-8')
    except Exception:
        pass
        
    # 2. Fallback to old XOR decryption so existing database values do not break
    try:
        old_key = "EnphaseDashboardSecretKey123"
        xor_bytes = base64.b64decode(cipher_text.encode('utf-8'))
        key_len = len(old_key)
        plain_bytes = bytearray(xor_bytes[i] ^ ord(old_key[i % key_len]) for i in range(len(xor_bytes)))
        return plain_bytes.decode('utf-8')
    except Exception:
        return ""

def is_system_initialized():
    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        # Check if a valid admin user exists in users table
        cursor.execute("SELECT COUNT(*) FROM users")
        user_count = cursor.fetchone()[0]
        # Check if admin is configured
        cursor.execute("SELECT value FROM system_config WHERE key = 'admin_configured'")
        configured_row = cursor.fetchone()
        configured = configured_row and configured_row[0] == 'true'
        return user_count > 0 and configured
    except Exception:
        return False
    finally:
        if conn:
            conn.close()

def init_db():
    print("[*] Initializing SQLite database schema and checking migrations...")
    conn = get_db()
    cursor = conn.cursor()
    
    # 1. Users Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        child_font TEXT DEFAULT 'Quicksand',
        child_theme TEXT DEFAULT 'dino',
        main_page_privacy INTEGER DEFAULT 0,
        lifetime_xp INTEGER DEFAULT 0,
        current_level INTEGER DEFAULT 1,
        vault_keys_available INTEGER DEFAULT 0,
        unlocked_assets TEXT DEFAULT '[]'
    )""")
    
    # 2. Children Profiles Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS children (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        age INTEGER NOT NULL,
        theme TEXT NOT NULL,
        points INTEGER DEFAULT 0,
        bankable_balance INTEGER DEFAULT 0,
        lifetime_xp INTEGER DEFAULT 0,
        level INTEGER DEFAULT 1,
        status TEXT DEFAULT 'active',
        deleted_at TEXT,
        font TEXT DEFAULT 'fredoka',
        current_level INTEGER DEFAULT 1,
        vault_keys_available INTEGER DEFAULT 0,
        unlocked_assets TEXT DEFAULT '[]',
        avatar_path TEXT,
        profile_photo_path TEXT
    )""")
    
    # 3. Chores Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS chores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        points INTEGER NOT NULL,
        frequency TEXT NOT NULL,
        assigned_child_id INTEGER,
        time_block TEXT DEFAULT 'morning',
        is_enrichment INTEGER DEFAULT 0,
        validation_type TEXT DEFAULT 'simple',
        example_photo_path TEXT,
        instructions TEXT,
        active_days TEXT DEFAULT 'all',
        enrichment_log TEXT,
        FOREIGN KEY (assigned_child_id) REFERENCES children(id) ON DELETE SET NULL
    )""")
    
    # 4. Chore History
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS chore_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chore_id INTEGER NOT NULL,
        child_id INTEGER NOT NULL,
        completed_date TEXT NOT NULL,
        FOREIGN KEY (chore_id) REFERENCES chores(id) ON DELETE CASCADE,
        FOREIGN KEY (child_id) REFERENCES children(id) ON DELETE CASCADE
    )""")
    
    # 5. System Configuration Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS system_config (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )""")
    
    # 6. Chore Submissions (Enrichments / Photo validations)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS chore_submissions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chore_id INTEGER,
        child_id INTEGER,
        audio_path_1 TEXT,
        audio_path_2 TEXT,
        audio_path_3 TEXT,
        transcript TEXT,
        photo_path TEXT,
        status TEXT DEFAULT 'pending',
        parent_feedback TEXT,
        submitted_date TEXT,
        FOREIGN KEY (chore_id) REFERENCES chores(id) ON DELETE CASCADE,
        FOREIGN KEY (child_id) REFERENCES children(id) ON DELETE CASCADE
    )""")
    
    # 7. Habit Reminders (Corrective Actions)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS habit_reminders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        child_id INTEGER,
        photo_path TEXT,
        note TEXT,
        deduction_points INTEGER DEFAULT 5,
        refunded_points INTEGER DEFAULT 0,
        status TEXT DEFAULT 'active',
        created_at TEXT,
        FOREIGN KEY (child_id) REFERENCES children(id) ON DELETE CASCADE
    )""")
    
    # 8. Parent Spotlights
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS parent_spotlights (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        child_id INTEGER,
        giver_name TEXT DEFAULT 'Parent',
        note TEXT,
        bonus_points INTEGER DEFAULT 3,
        status TEXT DEFAULT 'pending_popup',
        created_at TEXT,
        FOREIGN KEY (child_id) REFERENCES children(id) ON DELETE CASCADE
    )""")

    # 10. Security Audit Log
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS security_audit (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_type TEXT NOT NULL,
        details TEXT,
        ip_address TEXT,
        created_at TEXT
    )
    """)

    # 9. Point-based Rewards Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS rewards (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        description TEXT,
        points_cost INTEGER NOT NULL,
        child_id INTEGER,  -- NULL = available to all children, otherwise specific child
        active INTEGER DEFAULT 1,
        image_path TEXT,
        created_at TEXT
    )""")
    
    # Seeding parent user if none exist with a secure Werkzeug hash
    cursor.execute("SELECT COUNT(*) FROM users")
    if cursor.fetchone()[0] == 0:
        default_hash = generate_password_hash("admin")
        cursor.execute("INSERT INTO users (username, password_hash) VALUES ('parent', ?)", (default_hash,))
        
    # --- SELF-HEALING DATABASE MIGRATIONS (V2 to V3.5.3) ---
    try:
        # 1. Audit and patch 'users' table (Parent/Admin configurations only)
        cursor.execute("PRAGMA table_info(users)")
        users_cols = [row[1] for row in cursor.fetchall()]
        users_migrations = [
            ("main_page_privacy", "INTEGER DEFAULT 0"),
            ("security_q1", "TEXT"),
            ("security_a1", "TEXT"),
            ("security_q2", "TEXT"),
            ("security_a2", "TEXT")
        ]
        for col, definition in users_migrations:
            if col not in users_cols:
                print(f"[*] Migrating 'users': Adding missing column '{col}'")
                cursor.execute(f"ALTER TABLE users ADD COLUMN {col} {definition}")
                
        # 2. Audit and patch 'children' table (Roster metrics, styles, and progression tokens)
        cursor.execute("PRAGMA table_info(children)")
        children_cols = [row[1] for row in cursor.fetchall()]
        children_migrations = [
            ("status", "TEXT DEFAULT 'active'"),
            ("deleted_at", "TEXT"),
            ("theme", "TEXT DEFAULT 'dinosaur'"),
            ("font", "TEXT DEFAULT 'fredoka'"),
            ("lifetime_xp", "INTEGER DEFAULT 0"),
            ("level", "INTEGER DEFAULT 1"),
            ("current_level", "INTEGER DEFAULT 1"),
            ("vault_keys_available", "INTEGER DEFAULT 0"),
            ("unlocked_assets", "TEXT DEFAULT '[]'"),
            ("avatar_path", "TEXT"),
            ("profile_photo_path", "TEXT")
        ]
        for col, definition in children_migrations:
            if col not in children_cols:
                print(f"[*] Migrating 'children': Adding missing column '{col}'")
                cursor.execute(f"ALTER TABLE children ADD COLUMN {col} {definition}")
                
        # 2.5 Audit and patch 'chores' table (Enrichment logs)
        cursor.execute("PRAGMA table_info(chores)")
        chores_cols = [row[1] for row in cursor.fetchall()]
        if "enrichment_log" not in chores_cols:
            print("[*] Migrating 'chores': Adding missing column 'enrichment_log'")
            cursor.execute("ALTER TABLE chores ADD COLUMN enrichment_log TEXT")

        if "image_path" not in chores_cols:
            print("[*] Migrating 'chores': Adding missing column 'image_path'")
            cursor.execute("ALTER TABLE chores ADD COLUMN image_path TEXT")

        # 2.8 Audit and patch 'rewards' table
        cursor.execute("PRAGMA table_info(rewards)")
        rewards_cols = [row[1] for row in cursor.fetchall()]
        if rewards_cols:
            if "description" not in rewards_cols:
                cursor.execute("ALTER TABLE rewards ADD COLUMN description TEXT")
            if "active" not in rewards_cols:
                cursor.execute("ALTER TABLE rewards ADD COLUMN active INTEGER DEFAULT 1")
            if "image_path" not in rewards_cols:
                cursor.execute("ALTER TABLE rewards ADD COLUMN image_path TEXT")
            
        # 3. Seed default system configs if missing
        cursor.execute("SELECT COUNT(*) FROM system_config WHERE key = 'photo_source_mode'")
        if cursor.fetchone()[0] == 0:
            cursor.execute("INSERT INTO system_config (key, value) VALUES ('photo_source_mode', 'default')")
        
        cursor.execute("INSERT OR IGNORE INTO system_config (key, value) VALUES ('solar_enabled', 'false')")
                
    except Exception as e:
        print(f"[!] Migration Error: {e}")
        
    conn.commit()
    conn.close()
    
    # Seamlessly trigger high-performance query index provisioning
    add_missing_indexes()

def add_missing_indexes():
    conn = get_db()
    cursor = conn.cursor()
    try:
        # Check existing indexes (SQLite master table)
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index'")
        existing = [row[0] for row in cursor.fetchall()]
        
        indexes = [
            ("idx_chore_history_child_date", "chore_history", "child_id, completed_date"),
            ("idx_chore_history_date", "chore_history", "completed_date"),
            ("idx_children_status", "children", "status"),
            ("idx_chore_submissions_status", "chore_submissions", "status"),
            ("idx_chore_submissions_date", "chore_submissions", "submitted_date"),
            ("idx_chore_history_chore_child", "chore_history", "chore_id, child_id"),
        ]
        
        for idx_name, table, columns in indexes:
            if idx_name not in existing:
                print(f"[*] Creating index {idx_name} on {table}({columns})")
                cursor.execute(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table} ({columns})")
        
        conn.commit()
    except Exception as e:
        print(f"[!] Error creating database indexes: {e}")
        conn.rollback()
    finally:
        conn.close()

# -------------------------------------------------------------
# CLIENT SSE BROADCAST UTILITY
# -------------------------------------------------------------
clients = []

def broadcast_event(event_type, data):
    event = {'type': event_type, 'data': data}
    for q in clients:
        try:
            q.put(event)
        except Exception:
            pass

# -------------------------------------------------------------
# AUTOMATED SEASONAL STYLING
# -------------------------------------------------------------
def get_seasonal_styles():
    today = datetime.date.today()
    month, day = today.month, today.day
    if (month == 3 and day >= 20) or (month in [4, 5]) or (month == 6 and day < 21):
        season = "Spring"
        colors = {"season": season, "accent_blue": "#4ade80", "text_glow": "rgba(74, 222, 128, 0.4)", "body_tint": "#0a2214"}
    elif (month == 6 and day >= 21) or (month in [7, 8]) or (month == 9 and day < 22):
        season = "Summer"
        colors = {"season": season, "accent_blue": "#0ea5e9", "text_glow": "rgba(14, 165, 233, 0.4)", "body_tint": "#041626"}
    elif (month == 9 and day >= 22) or (month in [10, 11]) or (month == 12 and day < 21):
        season = "Autumn"
        colors = {"season": season, "accent_blue": "#f97316", "text_glow": "rgba(249, 115, 22, 0.4)", "body_tint": "#1a0f07"}
    else:
        season = "Winter"
        colors = {"season": season, "accent_blue": "#38bdf8", "text_glow": "rgba(56, 189, 248, 0.4)", "body_tint": "#060f1c"}
    return colors

def log_security_event(event_type, details, ip=None):
    conn = get_db()
    conn.execute("INSERT INTO security_audit (event_type, details, ip_address, created_at) VALUES (?, ?, ?, ?)",
                 (event_type, details, ip or request.remote_addr, datetime.datetime.now().isoformat()))
    conn.commit()
    conn.close()

# -------------------------------------------------------------
# AUTHENTICATION ROUTING
# -------------------------------------------------------------
def verify_password(stored_hash: str, input_password: str) -> bool:
    """
    Verifies input password against stored hash with modern PBKDF2/scrypt check
    and backward-compatibility fallback to legacy unsalted SHA-256.
    """
    if not stored_hash or not input_password:
        return False
    if stored_hash.startswith(('pbkdf2:', 'scrypt:', 'argon2:', 'sha256$')):
        return check_password_hash(stored_hash, input_password)
    legacy_hash = hashlib.sha256(input_password.encode('utf-8')).hexdigest()
    return legacy_hash == stored_hash

@app.route('/api/auth/login', methods=['POST'])
def api_login():
    client_ip = request.remote_addr
    if is_rate_limited(client_ip):
        log_security_event("LOGIN_RATE_LIMIT", f"Rate limit exceeded for IP: {client_ip}", client_ip)
        return jsonify({"success": False, "message": "Too many attempts. Try again in 5 minutes."}), 429

    # Add artificial delay to mitigate brute force attacks
    import time
    time.sleep(0.5)

    data = request.json or {}
    password = data.get("password", "")
    
    conn = get_db()
    user = conn.execute("SELECT * FROM users LIMIT 1").fetchone()
    conn.close()
    
    if user and verify_password(user["password_hash"], password):
        # Seamlessly auto-upgrade legacy password hashes to modern secure PBKDF2/scrypt on login
        if not user["password_hash"].startswith(('pbkdf2:', 'scrypt:', 'argon2:', 'sha256$')):
            new_hash = generate_password_hash(password)
            try:
                conn_up = get_db()
                conn_up.execute("UPDATE users SET password_hash = ? WHERE id = ?", (new_hash, user["id"]))
                conn_up.commit()
                conn_up.close()
                print(f"[*] Successfully upgraded password hash format to secure Werkzeug hash for user: {user['username']}")
            except Exception as e:
                print(f"[!] Warning: Failed to auto-upgrade legacy password hash format: {e}")

        session["parent_auth"] = True
        log_security_event("LOGIN_SUCCESS", f"Successful login for user: {user['username']}", client_ip)
        return jsonify({"success": True})
        
    log_security_event("LOGIN_FAILURE", f"Failed login attempt for user: {user['username'] if user else 'N/A'}", client_ip)
    return jsonify({"success": False, "message": "Invalid password"}), 401

@app.route('/api/auth/request-password-reset', methods=['POST'])
def request_password_reset():
    client_ip = request.remote_addr
    if is_rate_limited(client_ip):
        log_security_event("PASSWORD_RESET_RATE_LIMIT", f"Password reset rate limit exceeded for IP: {client_ip}", client_ip)
        return jsonify({"success": False, "message": "Too many attempts. Try again in 5 minutes."}), 429
        
    token_file = "reset_password.token"
    if os.path.exists(token_file):
        try:
            # Reset password to secure hash format
            pw_hash = generate_password_hash("admin")
            conn = get_db()
            conn.execute("UPDATE users SET password_hash = ?", (pw_hash,))
            conn.commit()

            # Get parent email for notification
            parent_email_row = conn.execute("SELECT value FROM system_config WHERE key = 'smtp_to_email'").fetchone()
            parent_email = parent_email_row['value'] if parent_email_row and parent_email_row['value'] else None

            conn.close()
            
            # Remove the token file
            os.remove(token_file)
            
            log_security_event("PASSWORD_RESET_TOKEN", "Password reset via token file.", request.remote_addr)
            if parent_email:
                threading.Thread(target=send_password_change_notification, args=(parent_email,), daemon=True).start()

            return jsonify({"success": True})
        except Exception as e:
            return jsonify({"success": False, "message": f"An internal error occurred: {str(e)}"}), 500
    else:
        log_security_event("PASSWORD_RESET_TOKEN_FAIL", "Failed password reset attempt: token file not found.", request.remote_addr)
        return jsonify({"success": False, "message": "Reset token not found on server."}), 400

@app.route('/api/auth/send-recovery-email', methods=['POST'])
def send_recovery_email():
    client_ip = request.remote_addr
    if is_rate_limited(client_ip):
        log_security_event("RECOVERY_EMAIL_RATE_LIMIT", f"Recovery email rate limit exceeded for IP: {client_ip}", client_ip)
        return jsonify({"success": False, "message": "Too many attempts. Try again in 5 minutes."}), 429
        
    data = request.json
    to_email = data.get('to_email')
    from_email = data.get('from_email')
    recovery_code = data.get('recovery_code')
    
    # Get SMTP creds from request body since they are not in DB yet
    smtp_server = data.get('smtp_server', 'smtp.gmail.com')
    smtp_port = data.get('smtp_port', 587)
    smtp_username = data.get('smtp_username')
    smtp_password = data.get('smtp_password')
    
    if not to_email or not recovery_code or not smtp_username or not smtp_password:
        return jsonify({"success": False, "message": "Missing required fields for sending email"}), 400
    
    subject = "Family Dashboard Emergency Recovery Key"
    body = f"""
    <html>
    <body style="font-family: Arial, sans-serif;">
        <h2>Family Command Center - Emergency Recovery Key</h2>
        <p>You requested an emergency recovery code for your Family Dashboard.</p>
        <p><strong style="font-size: 1.2rem;">{recovery_code}</strong></p>
        <p>Please store this code in a safe place (password manager, printed copy, etc.).</p>
        <p>If you ever lose your password AND forget your security answers, you can use this code to reset your admin password.</p>
        <hr>
        <p style="font-size: 0.8rem; color: #666;">This is an automated message. Do not reply.</p>
    </body>
    </html>
    """
    
    try:
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText
        
        msg = MIMEMultipart()
        msg['From'] = from_email or smtp_username
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'html'))
        
        server = smtplib.SMTP(smtp_server, int(smtp_port))
        server.starttls()
        server.login(smtp_username, smtp_password)
        server.send_message(msg)
        server.quit()
        return jsonify({"success": True, "message": "Recovery email sent"})
    except Exception as e:
        print(f"Failed to send recovery email: {e}")
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/auth/emergency-recovery', methods=['POST'])
def emergency_recovery():
    client_ip = request.remote_addr
    if is_rate_limited(client_ip):
        log_security_event("EMERGENCY_RECOVERY_RATE_LIMIT", f"Emergency recovery rate limit exceeded for IP: {client_ip}", client_ip)
        return jsonify({"success": False, "message": "Too many attempts. Try again in 5 minutes."}), 429
        
    data = request.json
    recovery_code = data.get('recovery_code', '').upper()
    new_password = data.get('new_password', '')
    
    conn = get_db()
    stored_hash = conn.execute("SELECT value FROM system_config WHERE key = 'emergency_recovery_hash'").fetchone()
    if not stored_hash:
        conn.close()
        log_security_event("EMERGENCY_RECOVERY_FAIL", "Attempted recovery, but not configured.", client_ip)
        return jsonify({"success": False, "message": "Emergency recovery not configured."}), 403
    
    input_hash = hashlib.sha256(recovery_code.encode('utf-8')).hexdigest()
    if input_hash != stored_hash['value']:
        conn.close()
        log_security_event("EMERGENCY_RECOVERY_FAIL", "Invalid recovery code provided.", client_ip)
        return jsonify({"success": False, "message": "Invalid emergency recovery code."}), 403
    
    if not new_password or len(new_password) < 4:
        conn.close()
        return jsonify({"success": False, "message": "Password must be at least 4 characters."}), 400
    
    pw_hash = generate_password_hash(new_password)
    conn.execute("UPDATE users SET password_hash = ?", (pw_hash,))
    # Clear security questions so they are re-set on next wizard run
    conn.execute("UPDATE users SET security_q1 = NULL, security_a1 = NULL, security_q2 = NULL, security_a2 = NULL")
    conn.commit()

    # Get parent email for notification
    parent_email_row = conn.execute("SELECT value FROM system_config WHERE key = 'smtp_to_email'").fetchone()
    parent_email = parent_email_row['value'] if parent_email_row and parent_email_row['value'] else None

    conn.close()
    
    log_security_event("EMERGENCY_RECOVERY_SUCCESS", "Password reset via emergency code.", client_ip)
    if parent_email:
        threading.Thread(target=send_password_change_notification, args=(parent_email,), daemon=True).start()

    return jsonify({"success": True, "message": "Password reset successful. You can now log in. Please re-set your security questions."})

@app.route('/api/auth/status', methods=['GET'])
def api_auth_status():
    return jsonify({"authenticated": session.get("parent_auth", False)})

@app.route('/api/auth/logout', methods=['POST'])
def api_logout():
    session.pop("parent_auth", None)
    return jsonify({"success": True})

def require_parent():
    return session.get("parent_auth", False)

# Helper for age tier styling rules
def get_age_tier_config(age):
    if age <= 4:
        return {"tier": "toddler", "focus": "Self-Care & Basic Habits", "validation_default": "simple", "themes": ["princess", "dinosaur", "mecha", "gamer"]}
    elif age <= 8:
        return {"tier": "young_child", "focus": "Transition & Responsibility", "validation_default": "simple", "themes": ["dinosaur", "princess", "gamer", "mecha"]}
    elif age <= 12:
        return {"tier": "youth", "focus": "Independence & Accountability", "validation_default": "simple", "themes": ["gamer", "mecha", "dinosaur", "princess"]}
    else:
        return {"tier": "teenager", "focus": "Leadership & Complex Chores", "validation_default": "photo_upload", "themes": ["teen-dark", "gamer", "mecha"]}

# -------------------------------------------------------------
# CHORES CORE API
# -------------------------------------------------------------
@app.route('/api/chores', methods=['GET'])
def get_chores():
    target_date_str = request.args.get("date") or datetime.date.today().isoformat()
    if target_date_str == "today":
        target_date_str = datetime.date.today().isoformat()
    elif target_date_str == "yesterday":
        target_date_str = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    child_id_param = request.args.get("child_id")
    child_name_param = request.args.get("child_name")
    conn = get_db()
    
    # Resolve child ID if possible
    cid = None
    if child_id_param:
        try:
            cid = int(child_id_param)
        except ValueError:
            pass
    elif child_name_param:
        child_row = conn.execute("SELECT id FROM children WHERE LOWER(name) = ?", (child_name_param.lower(),)).fetchone()
        if child_row:
            cid = child_row["id"]
            
    # 1. Fetch profiles based on access levels
    if require_parent():
        children_rows = conn.execute("SELECT * FROM children").fetchall()
    else:
        children_rows = conn.execute("SELECT * FROM children WHERE status = 'active'").fetchall()
        
    children_list = [dict(c) for c in children_rows]
    for c in children_list:
        c["age_tier"] = get_age_tier_config(c["age"])
        
    # 2. Fetch all chores
    if require_parent():
        chores_rows = conn.execute("""
            SELECT c.*, ch.name as child_name, ch.status as child_status
            FROM chores c
            LEFT JOIN children ch ON c.assigned_child_id = ch.id
        """).fetchall()
    else:
        chores_rows = conn.execute("""
            SELECT c.*, ch.name as child_name, ch.status as child_status
            FROM chores c
            LEFT JOIN children ch ON c.assigned_child_id = ch.id
            WHERE ch.id IS NULL OR ch.status = 'active'
        """).fetchall()
        
    # 3. Fetch completions (chore_id and child_id to handle multi-user completions)
    history_rows = conn.execute("SELECT chore_id, child_id FROM chore_history WHERE completed_date = ?", (target_date_str,)).fetchall()
    
    # Build a map of chore_id -> set of child_ids who completed it
    completions_map = {}
    for row in history_rows:
        completions_map.setdefault(row["chore_id"], set()).add(row["child_id"])
    
    # Determine the day name
    try:
        target_date = datetime.date.fromisoformat(target_date_str)
        day_name = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"][target_date.weekday()]
    except Exception:
        day_name = "mon"
        
    chores_list = []
    for r in chores_rows:
        chore_dict = dict(r)
        
        # Filter chores by day scheduler
        active_days_str = r["active_days"] or "all"
        if active_days_str != "all" and not require_parent():
            active_days = [d.strip().lower() for d in active_days_str.split(",") if d.strip()]
            if day_name not in active_days:
                continue
                
        completed_child_ids = completions_map.get(r["id"], set())
        chore_dict["completed_by"] = list(completed_child_ids)
        
        # Check if there is a pending yesterday submission status for this child
        if cid is not None:
            sub_status = conn.execute("SELECT status FROM chore_submissions WHERE chore_id = ? AND child_id = ? AND submitted_date = ?", (r["id"], cid, target_date_str)).fetchone()
            if sub_status:
                chore_dict["status"] = sub_status["status"]
        
        if cid is not None:
            chore_dict["completed_today"] = cid in completed_child_ids
        else:
            # Fallback backward compatibility:
            # If assigned to a child, check if that child completed it.
            # If assigned to everybody (null), check if anyone completed it.
            assigned_cid = r["assigned_child_id"]
            if assigned_cid:
                chore_dict["completed_today"] = assigned_cid in completed_child_ids
            else:
                chore_dict["completed_today"] = len(completed_child_ids) > 0

        # Calculate streak for this chore and child
        if cid:
            streak_dates = conn.execute("""
                SELECT completed_date FROM chore_history
                WHERE chore_id = ? AND child_id = ?
                ORDER BY completed_date DESC LIMIT 7
            """, (r["id"], cid)).fetchall()
            
            streak = 0
            check_date = datetime.date.today()
            for _ in range(7):
                date_str = check_date.isoformat()
                if any(d["completed_date"] == date_str for d in streak_dates):
                    streak += 1
                    check_date -= datetime.timedelta(days=1)
                else:
                    break
            chore_dict["streak"] = streak
        else:
            chore_dict["streak"] = 0

        chores_list.append(chore_dict)
        
    # 4. Fetch submissions
    submissions_rows = conn.execute("SELECT * FROM chore_submissions WHERE submitted_date = ?", (target_date_str,)).fetchall()
    submissions_list = [dict(sub) for sub in submissions_rows]
    
    # 5. Fetch habit reminders & parent spotlights
    habit_reminders_rows = conn.execute("SELECT * FROM habit_reminders WHERE status = 'active'").fetchall()
    habit_reminders_list = [dict(hr) for hr in habit_reminders_rows]
    
    parent_spotlights_rows = conn.execute("SELECT * FROM parent_spotlights WHERE status = 'pending_popup'").fetchall()
    parent_spotlights_list = [dict(ps) for ps in parent_spotlights_rows]
    
    conn.close()
    
    return jsonify({
        "children": children_list,
        "chores": chores_list,
        "habit_reminders": habit_reminders_list,
        "parent_spotlights": parent_spotlights_list,
        "chore_submissions": submissions_list,
        "today": target_date_str
    })

@app.route('/api/chores/toggle', methods=['POST'])
def toggle_chore():
    data = request.json or {}
    chore_id = data.get("chore_id")
    child_id = data.get("child_id")
    date_context = data.get("date_context", "today")
    forced_status = data.get("forced_status")
    
    if not chore_id or not child_id:
        return jsonify({"success": False, "message": "Missing chore_id or child_id"}), 400
        
    import datetime
    target_date = datetime.date.today()
    if date_context == "yesterday":
        target_date = target_date - datetime.timedelta(days=1)
    target_date_str = target_date.strftime("%Y-%m-%d")
        
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        cursor.execute("BEGIN IMMEDIATE")   # Acquire write lock immediately
        
        chore = cursor.execute("SELECT * FROM chores WHERE id = ?", (chore_id,)).fetchone()
        child = cursor.execute("SELECT * FROM children WHERE id = ?", (child_id,)).fetchone()
        
        if not chore or not child:
            conn.rollback()
            conn.close()
            return jsonify({"success": False, "message": "Chore or child not found"}), 404
            
        is_teen = child["age"] >= 13
        if is_teen and chore["is_enrichment"] == 0 and date_context != "yesterday":
            # Teenager chores require review (except enrichments that might have separate submit)
            conn.rollback()
            conn.close()
            return jsonify({"success": False, "message": "Teenager chores require parent approval."}), 400
            
        pts = chore["points"]
        completed = False
        
        if date_context == "yesterday" or forced_status == "pending_approval":
            # Check if already completed yesterday in history
            history_record = cursor.execute(
                "SELECT * FROM chore_history WHERE chore_id = ? AND child_id = ? AND completed_date = ?",
                (chore_id, child_id, target_date_str)
            ).fetchone()
            if history_record:
                conn.rollback()
                conn.close()
                return jsonify({"success": False, "message": "Chore already completed yesterday."}), 400
                
            # Check if already submitted in submissions (excluding rejected)
            sub_record = cursor.execute(
                "SELECT * FROM chore_submissions WHERE chore_id = ? AND child_id = ? AND submitted_date = ? AND status != 'rejected'",
                (chore_id, child_id, target_date_str)
            ).fetchone()
            if sub_record:
                conn.rollback()
                conn.close()
                return jsonify({"success": False, "message": "Chore already submitted for yesterday."}), 400
                
            # Clean up any previously rejected submission for this chore and date
            cursor.execute("DELETE FROM chore_submissions WHERE chore_id = ? AND child_id = ? AND submitted_date = ?", (chore_id, child_id, target_date_str))
            
            # Insert a submission entry with pending_approval status
            cursor.execute("""
                INSERT INTO chore_submissions (chore_id, child_id, transcript, status, submitted_date)
                VALUES (?, ?, 'Grace Period Late Completion Checkoff', 'pending_approval', ?)
            """, (chore_id, child_id, target_date_str))
            
            # (Points for 'yesterday' are skipped until parent processes via /approve-action)
            completed = False
            
            # Fire background email alert asynchronously
            threading.Thread(target=trigger_parent_email_alert, args=(child["name"], chore["name"]), daemon=True).start()
        else:
            history_record = cursor.execute(
                "SELECT * FROM chore_history WHERE chore_id = ? AND child_id = ? AND completed_date = ?",
                (chore_id, child_id, target_date_str)
            ).fetchone()
            
            if history_record:
                cursor.execute("DELETE FROM chore_history WHERE id = ?", (history_record["id"],))
                cursor.execute("UPDATE children SET points = MAX(0, points - ?), bankable_balance = MAX(0, bankable_balance - ?), lifetime_xp = MAX(0, lifetime_xp - ?) WHERE id = ?", (pts, pts, pts, child_id))
            else:
                cursor.execute("INSERT INTO chore_history (chore_id, child_id, completed_date) VALUES (?, ?, ?)", (chore_id, child_id, target_date_str))
                cursor.execute("UPDATE children SET points = points + ?, bankable_balance = bankable_balance + ?, lifetime_xp = lifetime_xp + ? WHERE id = ?", (pts, pts, pts, child_id))
                completed = True
                
                # Level up check (every 100 XP)
                child_row = cursor.execute("SELECT name, lifetime_xp, level, vault_keys_available FROM children WHERE id = ?", (child_id,)).fetchone()
                if child_row:
                    new_level = (child_row["lifetime_xp"] // 100) + 1
                    if new_level > child_row["level"]:
                        new_keys = child_row["vault_keys_available"] + (new_level - child_row["level"])
                        cursor.execute("UPDATE children SET level = ?, current_level = ?, vault_keys_available = ? WHERE id = ?", (new_level, new_level, new_keys, child_id))
                        broadcast_event("level_up", {
                            "child_id": child_id,
                            "name": child_row["name"],
                            "level": new_level
                        })
                    
        # Recalculate dynamic Star of the Day
        top_child = cursor.execute("SELECT name FROM children WHERE status = 'active' ORDER BY points DESC, name ASC LIMIT 1").fetchone()
        if top_child:
            cursor.execute("INSERT OR REPLACE INTO system_config (key, value) VALUES ('star_of_the_day', ?)", (top_child["name"],))
            
        conn.commit()
    
        # Check and award milestone rewards
        milestone = check_and_award_milestones(child_id, chore_id, conn)
        if milestone:
            conn.commit()
            broadcast_event("milestone_unlocked", {
                "child_id": child_id,
                "type": milestone["type"],
                "reward": milestone["reward"],
                "chore": milestone.get("chore", "")
            })
            
    except Exception as e:
        conn.rollback()
        conn.close()
        print(f"Error toggling chore: {e}")
        return jsonify({"success": False, "message": str(e)}), 500
        
    conn.close()
    
    # Leaderboard broadcast
    leaderboard_payload = get_leaderboard_payload()
    broadcast_event("chore_update", {
        "chore_id": chore_id,
        "completed": completed,
        "leaderboard": leaderboard_payload
    })
    
    return jsonify({"success": True, "completed": completed, "leaderboard": leaderboard_payload})

@app.before_request
def invalidate_leaderboard_cache_on_post():
    if request.method in ['POST', 'PUT', 'DELETE']:
        _leaderboard_cache["expires"] = 0

# Helper to load leaderboard metrics (raw database query)
def _get_leaderboard_payload_raw():
    conn = get_db()
    children_rows = conn.execute("SELECT id, name, age, points, bankable_balance, lifetime_xp, level, theme, font, vault_keys_available, unlocked_assets, avatar_path, profile_photo_path FROM children WHERE status = 'active' ORDER BY points DESC, name ASC").fetchall()
    
    star_row = conn.execute("SELECT value FROM system_config WHERE key = 'star_of_the_day'").fetchone()
    star_of_day = star_row["value"] if star_row else "Axel"
    
    peak_row = conn.execute("SELECT value FROM system_config WHERE key = 'peak_hour_mode'").fetchone()
    peak_hour = (peak_row["value"] == "true") if peak_row else False
    
    privacy_row = conn.execute("SELECT main_page_privacy FROM users").fetchone()
    main_page_privacy = privacy_row["main_page_privacy"] if privacy_row else 0
    
    # Fetch weather & solar configs
    loc_row = conn.execute("SELECT value FROM system_config WHERE key = 'weather_location_name'").fetchone()
    lat_row = conn.execute("SELECT value FROM system_config WHERE key = 'weather_latitude'").fetchone()
    lon_row = conn.execute("SELECT value FROM system_config WHERE key = 'weather_longitude'").fetchone()
    solar_enabled_row = conn.execute("SELECT value FROM system_config WHERE key = 'solar_enabled'").fetchone()
    
    weather_loc = loc_row["value"] if loc_row else "Stafford, VA 22554"
    weather_lat = lat_row["value"] if lat_row else "38.4232"
    weather_lon = lon_row["value"] if lon_row else "-77.4080"
    solar_enabled = (solar_enabled_row["value"] == "true") if solar_enabled_row else True
    
    conn.close()
    
    children_list = [dict(c) for c in children_rows]
    for c in children_list:
        c["age_tier"] = get_age_tier_config(c["age"])
        
    return {
        "leaderboard": children_list,
        "star_of_the_day": star_of_day,
        "peak_hour_mode": peak_hour,
        "main_page_privacy": main_page_privacy,
        "solar_enabled": solar_enabled,
        "seasonal": get_seasonal_styles(),
        "weather_location_name": weather_loc,
        "weather_latitude": weather_lat,
        "weather_longitude": weather_lon
    }

_leaderboard_cache = {"data": None, "expires": 0}

def get_leaderboard_payload(force_refresh=False):
    now = time()
    if not force_refresh and now < _leaderboard_cache["expires"] and _leaderboard_cache["data"] is not None:
        return _leaderboard_cache["data"]
    data = _get_leaderboard_payload_raw()
    _leaderboard_cache["data"] = data
    _leaderboard_cache["expires"] = now + 5  # 5 seconds
    return data

@app.route('/api/leaderboard', methods=['GET'])
def get_leaderboard():
    return jsonify(get_leaderboard_payload())

@app.route('/api/chores/history/<child_name>', methods=['GET'])
def get_child_point_history(child_name):
    conn = get_db()
    child = conn.execute("SELECT id, name FROM children WHERE LOWER(name) = ?", (child_name.lower(),)).fetchone()
    if not child:
        conn.close()
        return jsonify({"success": False, "message": "Child not found"}), 404
        
    child_id = child["id"]
    
    # 1. Chore points per date
    chore_rows = conn.execute("""
        SELECT ch.completed_date as date_str, SUM(c.points) as total
        FROM chore_history ch
        JOIN chores c ON ch.chore_id = c.id
        WHERE ch.child_id = ?
        GROUP BY ch.completed_date
    """, (child_id,)).fetchall()
    
    # 2. Spotlight points per date
    spotlight_rows = conn.execute("""
        SELECT SUBSTR(created_at, 1, 10) as date_str, SUM(bonus_points) as total
        FROM parent_spotlights
        WHERE child_id = ?
        GROUP BY date_str
    """, (child_id,)).fetchall()
    
    # 3. Habit deductions
    habit_rows = conn.execute("""
        SELECT SUBSTR(created_at, 1, 10) as date_str, SUM(deduction_points - refunded_points) as total
        FROM habit_reminders
        WHERE child_id = ?
        GROUP BY date_str
    """, (child_id,)).fetchall()
    
    conn.close()
    
    points_by_date = {}
    for r in chore_rows:
        points_by_date[r["date_str"]] = r["total"] or 0
    for r in spotlight_rows:
        points_by_date[r["date_str"]] = points_by_date.get(r["date_str"], 0) + (r["total"] or 0)
    for r in habit_rows:
        points_by_date[r["date_str"]] = points_by_date.get(r["date_str"], 0) - (r["total"] or 0)
        
    # Generate weekly, monthly, and yearly time series
    today = datetime.date.today()
    
    # Weekly: last 7 days of the week (Mon, Tue, etc.)
    weekly_list = []
    for i in range(6, -1, -1):
        day_date = today - datetime.timedelta(days=i)
        date_str = day_date.isoformat()
        day_name = day_date.strftime("%a")
        pts = max(0, points_by_date.get(date_str, 0))
        weekly_list.append({"day": day_name, "date": date_str, "points": pts})

    # Monthly & Yearly: Jan through Dec (the 12 months)
    twelve_months_list = []
    current_year = today.year
    for m in range(1, 13):
        month_str = f"{current_year}-{m:02d}"
        month_pts = 0
        for d_str, pts in points_by_date.items():
            if d_str.startswith(month_str):
                month_pts += max(0, pts)
        month_name = datetime.date(current_year, m, 1).strftime("%b")
        twelve_months_list.append({"day": month_name, "points": month_pts})
        
    return jsonify({
        "success": True,
        "weekly_history": weekly_list,
        "monthly_history": twelve_months_list,
        "yearly_history": twelve_months_list,
        "weekly": weekly_list,
        "monthly": twelve_months_list,
        "yearly": twelve_months_list
    })

# -------------------------------------------------------------
# EMAIL NOTIFICATIONS & YESTERDAY GRACE PERIOD API
# -------------------------------------------------------------
import smtplib
from email.mime.text import MIMEText
import threading

def send_password_change_notification(to_email):
    """Sends an email alert that the password has been changed."""
    conn = None
    try:
        conn = get_db()
        rows = conn.execute("SELECT key, value FROM system_config WHERE key LIKE 'smtp_%'").fetchall()
        config = {r['key']: r['value'] for r in rows}
        conn.close()
        conn = None

        username = config.get('smtp_username')
        password = decrypt_val(config.get('smtp_password', ''))
        server_host = config.get('smtp_server', 'localhost')
        server_port = int(config.get('smtp_port', 587))

        if not to_email or not username or not password or not server_host:
            print("[-] Password change email not sent: SMTP settings are incomplete.")
            return

        subject = "Security Alert: Family Dashboard Password Changed"
        body = f"""
        <html>
        <body>
            <h2>Security Alert</h2>
            <p>This is a notification that the parent password for your Family Command Center was recently changed.</p>
            <p>If you did not authorize this change, please take immediate action to secure your system.</p>
            <p>Time of change: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        </body>
        </html>
        """
        
        from email.mime.multipart import MIMEMultipart
        msg = MIMEMultipart()
        msg['Subject'] = subject
        msg['From'] = username
        msg['To'] = to_email
        msg.attach(MIMEText(body, 'html'))

        with smtplib.SMTP(server_host, server_port) as server:
            server.starttls()
            server.login(username, password)
            server.send_message(msg)
        print(f"[+] Password change notification sent to {to_email}")
    except Exception as ex:
        print(f"[-] Background password change notification failed: {ex}")
    finally:
        if conn:
            conn.close()

def trigger_parent_email_alert(child_name, chore_name, is_grace_period=True):
    """Fires an asynchronous email notification to the parent using configured SMTP settings."""
    conn = None
    try:
        conn = get_db()
        rows = conn.execute("SELECT key, value FROM system_config WHERE key LIKE 'smtp_%'").fetchall()
        config = {r['key']: r['value'] for r in rows}
        conn.close()
        conn = None

        to_email = config.get('smtp_to_email')
        username = config.get('smtp_username')
        password = decrypt_val(config.get('smtp_password', ''))
        server_host = config.get('smtp_server', 'localhost')
        server_port = int(config.get('smtp_port', 587))

        if not to_email or not username or not password or not server_host:
            print("[-] Email alert not sent: SMTP settings are incomplete.")
            return

        if is_grace_period:
            body = f"⏳ Grace Period Notification: {child_name} has submitted a late completion request for yesterday's chore: '{chore_name}'. Please review this request on your Admin Panel Dashboard."
            subject = f"⏳ Pending Late Chore Action - {child_name}"
        else:
            body = f"🔔 Verification Approval Needed: {child_name} has submitted a task verification request for: '{chore_name}'. Please review the photo/audio/notes submission on your Admin Panel Dashboard."
            subject = f"🔔 Task Verification Pending - {child_name}"

        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = username
        msg['To'] = to_email

        with smtplib.SMTP(server_host, server_port) as server:
            server.starttls()
            server.login(username, password)
            server.send_message(msg)
        print(f"[+] Email alert sent to {to_email}")
    except Exception as ex:
        print(f"[-] Background email relay notification failed: {ex}")
    finally:
        if conn:
            conn.close()

@app.route('/api/chores/submit-yesterday', methods=['POST'])
def submit_yesterday_chore():
    data = request.json or {}
    chore_id = data.get("chore_id")
    child_id = data.get("child_id")
    notes = data.get("notes", "")
    
    if not chore_id or not child_id:
        return jsonify({"success": False, "message": "Missing chore_id or child_id"}), 400
        
    conn = get_db()
    cursor = conn.cursor()
    
    chore = cursor.execute("SELECT * FROM chores WHERE id = ?", (chore_id,)).fetchone()
    child = cursor.execute("SELECT * FROM children WHERE id = ?", (child_id,)).fetchone()
    
    if not chore or not child:
        conn.close()
        return jsonify({"success": False, "message": "Chore or child not found"}), 404
        
    yesterday_str = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    
    # Check if already completed yesterday
    history_record = cursor.execute(
        "SELECT * FROM chore_history WHERE chore_id = ? AND child_id = ? AND completed_date = ?",
        (chore_id, child_id, yesterday_str)
    ).fetchone()
    
    if history_record:
        conn.close()
        return jsonify({"success": False, "message": "Chore already completed yesterday."}), 400
        
    # Check if already submitted yesterday (excluding rejected)
    sub_record = cursor.execute(
        "SELECT * FROM chore_submissions WHERE chore_id = ? AND child_id = ? AND submitted_date = ? AND status != 'rejected'",
        (chore_id, child_id, yesterday_str)
    ).fetchone()
    
    if sub_record:
        conn.close()
        return jsonify({"success": False, "message": "Chore already submitted for yesterday."}), 400
        
    # Clean up any previously rejected submission for this chore and date
    cursor.execute("DELETE FROM chore_submissions WHERE chore_id = ? AND child_id = ? AND submitted_date = ?", (chore_id, child_id, yesterday_str))
    
    # Create submission with status='pending_approval'
    cursor.execute("""
        INSERT INTO chore_submissions (chore_id, child_id, transcript, status, submitted_date)
        VALUES (?, ?, ?, 'pending_approval', ?)
    """, (chore_id, child_id, notes, yesterday_str))
    
    # (Points for 'yesterday' are skipped until parent processes via /approve-action)
    
    conn.commit()
    conn.close()
    
    # Trigger background email alert asynchronously
    threading.Thread(target=trigger_parent_email_alert, args=(child["name"], chore["name"]), daemon=True).start()
    
    # Broadcast hot-reload
    payload = get_leaderboard_payload()
    broadcast_event("chore_update", {"leaderboard": payload})
    
    return jsonify({"success": True})

# -------------------------------------------------------------
# PARENT PORTAL CONFIGURATION ADMIN APIS
# -------------------------------------------------------------
@app.route('/api/admin/change-password', methods=['POST'])
def admin_change_password():
    if not require_parent():
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    client_ip = request.remote_addr
    if is_rate_limited(client_ip):
        log_security_event("PASSWORD_CHANGE_RATE_LIMIT", f"Password change rate limit exceeded for IP: {client_ip}", client_ip)
        return jsonify({"success": False, "message": "Too many attempts. Try again in 5 minutes."}), 429
        
    data = request.json or {}
    new_password = data.get("new_password", "")
    if not new_password or len(new_password.strip()) < 4:
        return jsonify({"success": False, "message": "Password must be >= 4 chars"}), 400
        
    pw_hash = generate_password_hash(new_password)
    conn = get_db()
    conn.execute("UPDATE users SET password_hash = ?", (pw_hash,))
    conn.commit()

    # Get parent email for notification
    parent_email_row = conn.execute("SELECT value FROM system_config WHERE key = 'smtp_to_email'").fetchone()
    parent_email = parent_email_row['value'] if parent_email_row and parent_email_row['value'] else None

    conn.close()

    log_security_event("PASSWORD_CHANGE_SUCCESS", "Parent changed password via admin panel.", client_ip)
    if parent_email:
        threading.Thread(target=send_password_change_notification, args=(parent_email,), daemon=True).start()
    session.clear()
    return jsonify({"success": True})

@app.route('/api/admin/chores', methods=['POST'])
def admin_add_chore():
    if not require_parent():
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    
    # Handle both JSON and multipart/form-data payloads safely
    if request.is_json:
        data = request.get_json() or {}
        name = data.get("name")
        points = data.get("points")
        frequency = data.get("frequency", "daily")
        assigned_child_id_str = data.get("assigned_child_id")
        time_block = data.get("time_block", "morning")
        active_days = data.get("active_days", "all")
    else:
        name = request.form.get("name")
        points = request.form.get("points")
        frequency = request.form.get("frequency", "daily")
        assigned_child_id_str = request.form.get("assigned_child_id")
        time_block = request.form.get("time_block", "morning")
        active_days = request.form.get("active_days", "all")
    
    # Default values for columns not in the form
    is_enrichment = 0
    validation_type = "simple"
    
    if not name or points is None:
        return jsonify({"success": False, "message": "Name and points are required"}), 400
    
    assigned_child_id = None
    if assigned_child_id_str is not None:
        if isinstance(assigned_child_id_str, int):
            assigned_child_id = assigned_child_id_str
        elif isinstance(assigned_child_id_str, str) and assigned_child_id_str.isdigit():
            assigned_child_id = int(assigned_child_id_str)
        elif isinstance(assigned_child_id_str, str) and assigned_child_id_str.strip().lower() == 'everybody':
            assigned_child_id = None

    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO chores (name, points, frequency, assigned_child_id, time_block, is_enrichment, validation_type, active_days)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (name, int(points), frequency, assigned_child_id, time_block, int(is_enrichment), validation_type, active_days))
    
    chore_id = cursor.lastrowid

    # Handle image upload
    if 'image' in request.files:
        file = request.files['image']
        if file and file.filename != '':
            import uuid
            from werkzeug.utils import secure_filename
            filename = f"chore_{chore_id}_{uuid.uuid4().hex}_{secure_filename(file.filename)}"
            upload_dir = os.path.join('static', 'chore_images')
            os.makedirs(upload_dir, exist_ok=True)
            path = os.path.join(upload_dir, filename)
            web_path = f"chore_images/{filename}"
            file.save(path)
            cursor.execute("UPDATE chores SET image_path = ? WHERE id = ?", (web_path, chore_id))

    conn.commit()
    conn.close()
    
    broadcast_event("admin_config_change", {})
    return jsonify({"success": True, "chore_id": chore_id})

@app.route('/api/admin/chores/<int:chore_id>', methods=['DELETE'])
def admin_delete_chore(chore_id):
    if not require_parent():
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    conn = get_db()
    conn.execute("DELETE FROM chores WHERE id = ?", (chore_id,))
    conn.commit()
    conn.close()
    broadcast_event("admin_config_change", {})
    return jsonify({"success": True})

@app.route('/api/admin/chores/<int:chore_id>/upload-image', methods=['POST'])
def upload_chore_image(chore_id):
    if not require_parent():
        return jsonify({"error": "Unauthorized"}), 403
    if 'image' not in request.files:
        return jsonify({"error": "No file"}), 400
    file = request.files['image']
    if file.filename == '':
        return jsonify({"error": "Empty filename"}), 400
    
    import os
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ['.jpg', '.jpeg', '.png', '.gif', '.webp'] or not (file.content_type and file.content_type.startswith('image/')):
        return jsonify({"error": "Invalid format. Supported: JPG, PNG, WEBP, GIF"}), 400
        
    import uuid
    from werkzeug.utils import secure_filename
    filename = f"chore_{chore_id}_{uuid.uuid4().hex}_{secure_filename(file.filename)}"
    upload_dir = os.path.join('static', 'chore_images')
    os.makedirs(upload_dir, exist_ok=True)
    path = os.path.join(upload_dir, filename)
    web_path = f"chore_images/{filename}"
    file.save(path)
    conn = get_db()
    conn.execute("UPDATE chores SET image_path = ? WHERE id = ?", (web_path, chore_id))
    conn.commit()
    conn.close()
    return jsonify({"success": True, "image_path": web_path})

@app.route('/api/admin/chores/<int:chore_id>/remove-image', methods=['DELETE'])
def remove_chore_image(chore_id):
    if not require_parent():
        return jsonify({"error": "Unauthorized"}), 403
    conn = get_db()
    row = conn.execute("SELECT image_path FROM chores WHERE id = ?", (chore_id,)).fetchone()
    if row and row['image_path']:
        import os
        image_path = row['image_path'].replace('\\', '/')
        file_path = image_path if image_path.startswith('static/') else os.path.join('static', image_path)
        if os.path.exists(file_path):
            os.remove(file_path)
        conn.execute("UPDATE chores SET image_path = NULL WHERE id = ?", (chore_id,))
        conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route('/api/admin/config', methods=['POST'])
def admin_set_config():
    if not require_parent():
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    data = request.json or {}
    peak_hour = data.get("peak_hour_mode")
    star_override = data.get("star_override")
    reset_points = data.get("reset_points")
    main_page_privacy = data.get("main_page_privacy")
    solar_enabled = data.get("solar_enabled")
    photo_source_mode = data.get("photo_source_mode")
    
    conn = get_db()
    cursor = conn.cursor()
    
    if peak_hour is not None:
        val_str = "true" if peak_hour else "false"
        cursor.execute("INSERT OR REPLACE INTO system_config (key, value) VALUES ('peak_hour_mode', ?)", (val_str,))
        
    if star_override:
        cursor.execute("INSERT OR REPLACE INTO system_config (key, value) VALUES ('star_of_the_day', ?)", (star_override,))
        
    if reset_points:
        cursor.execute("UPDATE children SET points = 0, bankable_balance = 0")
        
    if main_page_privacy is not None:
        cursor.execute("UPDATE users SET main_page_privacy = ?", (int(main_page_privacy),))
        
    if solar_enabled is not None:
        val_str = "true" if solar_enabled else "false"
        cursor.execute("INSERT OR REPLACE INTO system_config (key, value) VALUES ('solar_enabled', ?)", (val_str,))
        
    if photo_source_mode is not None:
        cursor.execute("INSERT OR REPLACE INTO system_config (key, value) VALUES ('photo_source_mode', ?)", (photo_source_mode,))
        
    conn.commit()
    conn.close()
    
    payload = get_leaderboard_payload()
    broadcast_event("admin_config_change", payload)
    return jsonify({"success": True, "config": payload})

@app.route('/api/admin/reset-daily-progress', methods=['POST'])
def reset_daily_progress():
    if not require_parent():
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    data = request.json or {}
    target_date = data.get("date")  # YYYY-MM-DD
    if not target_date:
        target_date = datetime.datetime.now().date().isoformat()
    conn = get_db()
    try:
        conn.execute("DELETE FROM chore_history WHERE completed_date = ?", (target_date,))
        conn.commit()
        broadcast_event("admin_config_change", get_leaderboard_payload())
        return jsonify({"success": True}) 
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        conn.close()


# -------------------------------------------------------------
# REAL-TIME SERVER-SENT EVENTS STREAM
# -------------------------------------------------------------
@app.route('/api/events')
def events():
    def event_stream():
        q = queue.Queue()
        clients.append(q)
        try:
            yield f"data: {json.dumps({'type': 'connected', 'seasonal': get_seasonal_styles()})}\n\n"
            while True:
                event_data = q.get()
                event_type = event_data.get('type', 'message')
                event_body = event_data.get('data', {})
                yield f"event: {event_type}\ndata: {json.dumps(event_body)}\n\n"
        except GeneratorExit:
            if q in clients:
                clients.remove(q)
    return Response(event_stream(), mimetype="text/event-stream")

# -------------------------------------------------------------
# PHOTO, CALENDAR & SOLAR EXTERNAL CACHE INTEGRATIONS
# -------------------------------------------------------------
@app.route('/api/photos')
def api_photos():
    try:
        # 1. Query current photo_source_mode from SQLite database
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM system_config WHERE key = 'photo_source_mode'")
        row = cursor.fetchone()
        conn.close()
        
        source_mode = row[0] if row else 'default'
        
        # 2. Premium landscapes array (exactly 4 high-res assets)
        default_landscapes = [
            {"src": "media/landscapes/mountain_sunset.jpg", "ratio": 1.0, "orientation": "square"},
            {"src": "media/landscapes/forest_lake.jpg", "ratio": 1.0, "orientation": "square"},
            {"src": "media/landscapes/misty_canyon.jpg", "ratio": 1.0, "orientation": "square"},
            {"src": "media/landscapes/snowy_peaks.jpg", "ratio": 1.0, "orientation": "square"}
        ]
        
        # 3. Handle routing choices
        if source_mode == 'default':
            return jsonify(default_landscapes)
            
        elif source_mode == 'manual' or source_mode == 'google':
            if os.path.exists('photos.json'):
                with open('photos.json', 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, list) and len(data) > 0:
                        # Ensure each photo has a 'src' property for the frontend
                        for photo in data:
                            if 'src' not in photo:
                                if 'filename' in photo:
                                    photo['src'] = f"/photos/{photo['filename']}"
                                elif 'url' in photo:
                                    photo['src'] = photo['url']
                                else:
                                    photo['src'] = "#"
                        return jsonify(data)
            # If manual/google list is empty or file doesn't exist, return landscapes fallback
            return jsonify(default_landscapes)
            
    except Exception as e:
        print(f"Error loading photos: {e}")
        
    return jsonify([])

@app.route('/api/calendar', methods=['GET', 'POST'])
def api_calendar():
    if request.method == 'POST':
        if not require_parent():
            return jsonify({"success": False, "message": "Unauthorized"}), 403
        data = request.json
        if isinstance(data, list):
            try:
                with open('calendar.json', 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=4)
                # Broadcast configuration update
                payload = get_leaderboard_payload()
                broadcast_event("admin_config_change", payload)
                return jsonify({"success": True})
            except Exception as e:
                return jsonify({"success": False, "message": str(e)}), 500
        else:
            return jsonify({"success": False, "message": "Expected an array of events"}), 400
            
    try:
        if os.path.exists('calendar.json'):
            with open('calendar.json', 'r', encoding='utf-8') as f:
                return jsonify(json.load(f))
    except Exception as e:
        print(f"Error loading calendar: {e}")
    return jsonify([])

@app.route('/api/solar')
def api_solar():
    # Check if solar is enabled in system_config
    conn = get_db()
    enabled_row = conn.execute("SELECT value FROM system_config WHERE key = 'solar_enabled'").fetchone()
    conn.close()
    solar_enabled = enabled_row and enabled_row[0] == 'true'

    if not solar_enabled:
        return jsonify({"disabled": True})

    # Try to read live solar data from solar.json (generated by sync_solar.py)
    solar_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'solar.json')
    if os.path.exists(solar_file):
        try:
            with open(solar_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # Ensure it has the expected keys before serving
                if all(k in data for k in ('current_power', 'produced_today', 'current_consumption', 'consumed_today', 'net_power', 'net_today')):
                    return jsonify(data)
        except Exception:
            pass

    # Solar is enabled but no live data yet — return zeros (not simulated)
    return jsonify({
        "error": "No live solar data available",
        "current_power": "0.0 kW",
        "produced_today": "0.0 kWh",
        "current_consumption": "0.0 kW",
        "consumed_today": "0.0 kWh",
        "net_power": "0.0 kW",
        "net_today": "0.0 kWh"
    })

@app.route('/api/quote', methods=['GET'])
def get_daily_quote():
    """
    Serves a beautiful, category-curated quote deterministic by date/hour/week.
    """
    # Load settings from db
    conn = get_db()
    cursor = conn.cursor()
    refresh_row = cursor.execute("SELECT value FROM system_config WHERE key = 'quote_refresh'").fetchone()
    category_row = cursor.execute("SELECT value FROM system_config WHERE key = 'quote_category'").fetchone()
    conn.close()
    
    refresh = refresh_row[0] if refresh_row else 'daily'
    category = category_row[0] if category_row else 'general'
    
    # Curated quote lists
    quotes_general = [
        "Believe you can and you're halfway there.",
        "Small steps every day lead to big changes.",
        "You are capable of more than you know.",
        "Make today amazing!",
        "Dream big, work hard!",
        "The secret of getting ahead is getting started.",
        "Positive thoughts breed positive outcomes.",
        "Do what you can, with what you have, where you are."
    ]
    
    quotes_bible = [
        "I can do all things through Christ who strengthens me. - Philippians 4:13",
        "The Lord is my shepherd; I shall not want. - Psalm 23:1",
        "Be strong and courageous. Do not be afraid; for the Lord your God is with you. - Joshua 1:9",
        "Plans to prosper you and not to harm you, plans to give you hope and a future. - Jeremiah 29:11",
        "Trust in the Lord with all your heart and lean not on your own understanding. - Proverbs 3:5",
        "A joyful heart is good medicine. - Proverbs 17:22",
        "Set your minds on things above, not on earthly things. - Colossians 3:2"
    ]
    
    quotes_kids = [
        "You are awesome just the way you are!",
        "Be kind to one another.",
        "Mistakes help us learn and grow.",
        "Your smile makes the world brighter!",
        "Choose happy, be friendly, and shine bright!",
        "You are a helper, a thinker, and a creator.",
        "Every day is a fresh start to try your best!",
        "You've got this!"
    ]
    
    # Select target list
    if category == 'bible':
        quotes = quotes_bible
    elif category == 'kids':
        quotes = quotes_kids
    else:
        quotes = quotes_general
        
    # Apply deterministic seed based on refresh frequency
    import random
    import datetime
    now = datetime.datetime.now()
    if refresh == 'hourly':
        seed_val = now.year * 1000000 + now.month * 10000 + now.day * 100 + now.hour
    elif refresh == 'weekly':
        iso = now.isocalendar()
        seed_val = iso[0] * 100 + iso[1]
    else:  # daily
        seed_val = now.year * 10000 + now.month * 100 + now.day
        
    # Temporary seed to select deterministic quote
    state = random.getstate()
    random.seed(seed_val)
    selected_quote = random.choice(quotes)
    random.setstate(state)
    
    return jsonify({"quote": selected_quote})

@app.route('/api/solar/toggle-status', methods=['GET'])
def get_solar_toggle_status():
    conn = get_db()
    row = conn.execute("SELECT value FROM system_config WHERE key='solar_enabled'").fetchone()
    conn.close()
    enabled = row['value'].lower() == 'true' if row else False
    return jsonify({"solar_enabled": enabled})

# -------------------------------------------------------------
# DYNAMIC PREVIOUS-WEEK PERFORMANCE telemetry
# -------------------------------------------------------------
def get_scheduled_count(chore, start_date, end_date):
    active_days_str = chore.get("active_days") or "all"
    if active_days_str == "all":
        active_days = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    else:
        active_days = [d.strip().lower() for d in active_days_str.split(",") if d.strip()]
        
    count = 0
    curr = start_date
    while curr <= end_date:
        day_name = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"][curr.weekday()]
        if day_name in active_days:
            count += 1
        curr += datetime.timedelta(days=1)
    return count

@app.route('/api/performance/last-week', methods=['GET'])
def get_performance_last_week():
    today = datetime.date.today()
    # Sunday is start of previous week
    current_week_sunday = today - datetime.timedelta(days=(today.weekday() + 1) % 7)
    last_week_sunday = current_week_sunday - datetime.timedelta(days=7)
    last_week_saturday = current_week_sunday - datetime.timedelta(days=1)
    
    date_range_str = f"{last_week_sunday.strftime('%b %d')} - {last_week_saturday.strftime('%b %d, %Y')}"
    
    conn = get_db()
    # Fetch active children
    children = conn.execute("SELECT * FROM children WHERE status = 'active'").fetchall()
    
    result = []
    for c in children:
        child_id = c["id"]
        
        # Fetch chores for this child
        chores = conn.execute("SELECT * FROM chores WHERE assigned_child_id = ?", (child_id,)).fetchall()
        
        chores_report = []
        total_xp = 0
        completions_total = 0
        scheduled_total = 0
        
        for chore in chores:
            chore_id = chore["id"]
            # completions
            comp_rows = conn.execute("""
                SELECT COUNT(*) FROM chore_history 
                WHERE chore_id = ? AND child_id = ? AND completed_date BETWEEN ? AND ?
            """, (chore_id, child_id, last_week_sunday.isoformat(), last_week_saturday.isoformat())).fetchone()
            completions = comp_rows[0] if comp_rows else 0
            
            scheduled = get_scheduled_count(dict(chore), last_week_sunday, last_week_saturday)
            
            completions_total += completions
            scheduled_total += scheduled
            xp_earned = completions * chore["points"]
            total_xp += xp_earned
            
            chores_report.append({
                "name": chore["name"],
                "completions": completions,
                "scheduled": scheduled,
                "points": xp_earned
            })
            
        # Spotlights
        spotlights = conn.execute("""
            SELECT * FROM parent_spotlights 
            WHERE child_id = ? AND SUBSTR(created_at, 1, 10) BETWEEN ? AND ?
        """, (child_id, last_week_sunday.isoformat(), last_week_saturday.isoformat())).fetchall()
        
        spotlights_report = []
        for s in spotlights:
            total_xp += s["bonus_points"]
            spotlights_report.append({
                "giver": s["giver_name"],
                "note": s["note"],
                "points": s["bonus_points"]
            })
            
        # Accolades Badges
        accolades = []
        ratio = (completions_total / scheduled_total) if scheduled_total > 0 else 0
        
        # Perfect streak
        if ratio >= 1.0 and scheduled_total >= 5:
            accolades.append({"badge": "🏆 Perfect Streak", "desc": "Completed 100% of daily chores last week!"})
        # Chore Champion
        if ratio >= 1.0:
            accolades.append({"badge": "⚡ Chore Champion", "desc": "100% completions of all scheduled chores!"})
        # Super Helper
        elif ratio >= 0.8:
            accolades.append({"badge": "🌟 Super Star Helper", "desc": "Completed over 80% of all tasks!"})
            
        # Elite XP
        if total_xp >= 40:
            accolades.append({"badge": "👑 Elite XP Earner", "desc": f"Earned an amazing {total_xp} XP last week!"})
        elif total_xp >= 20:
            accolades.append({"badge": "🚀 Rising Star", "desc": f"Gathered {total_xp} XP for the honor roll!"})
            
        result.append({
            "name": c["name"],
            "theme": c["theme"],
            "font": c["font"] or "fredoka",
            "avatar_path": c["avatar_path"],
            "profile_photo_path": c["profile_photo_path"],
            "total_xp": total_xp,
            "level": c["level"] or 1,
            "completion_ratio": f"{completions_total}/{scheduled_total}",
            "completion_percent": int(ratio * 100),
            "chores": chores_report,
            "spotlights": spotlights_report,
            "accolades": accolades
        })
        
    conn.close()
    
    return jsonify({
        "success": True,
        "date_range": date_range_str,
        "children": result
    })

# -------------------------------------------------------------
# SYSTEM ONBOARDING SETUP INITIALIZE APIS
# -------------------------------------------------------------
@app.route('/api/system/config', methods=['GET'])
def api_system_get_config():
    conn = get_db()
    cursor = conn.cursor()
    
    # 1. Fetch SMTP configs from SQLite
    cursor.execute("CREATE TABLE IF NOT EXISTS system_config (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    rows = cursor.execute("SELECT * FROM system_config").fetchall()
    db_config = {r["key"]: r["value"] for r in rows}
    
    # Decrypt sensitive ciphers
    smtp_pass = decrypt_val(db_config.get("smtp_password", ""))
    enphase_pass = decrypt_val(db_config.get("enphase_password", ""))
    
    # Mask passwords inside JSON payload for secure API responses
    smtp_pass_masked = "••••••••" if smtp_pass else ""
    enphase_pass_masked = "••••••••" if enphase_pass else ""
    
    # Fetch crew roster
    children_rows = cursor.execute("SELECT name, age, theme, font, avatar_path FROM children WHERE status = 'active'").fetchall()
    crew_list = [dict(c) for c in children_rows]
    
    cursor.execute("SELECT username FROM users LIMIT 1")
    user_row = cursor.fetchone()
    parent_username = user_row["username"] if user_row else "parent"
    
    conn.close()
    
    return jsonify({
        "success": True,
        "parent_username": parent_username,
        "smtp_server": db_config.get("smtp_server", ""),
        "smtp_port": db_config.get("smtp_port", "587"),
        "smtp_username": db_config.get("smtp_username", ""),
        "smtp_password": smtp_pass_masked,
        "smtp_to_email": db_config.get("smtp_to_email", ""),
        "ical_feed_url": db_config.get("ical_feed_url", ""),
        "solar_enabled": db_config.get("solar_enabled", "true") == "true",
        "enphase_username": db_config.get("enphase_username", ""),
        "enphase_password": enphase_pass_masked,
        "enphase_system_name": db_config.get("enphase_system_name", "John"),
        "enphase_serial_num": db_config.get("enphase_serial_num", "123456789102"),
        "weather_location_name": db_config.get("weather_location_name", "Stafford, VA 22554"),
        "weather_latitude": db_config.get("weather_latitude", "38.4232"),
        "weather_longitude": db_config.get("weather_longitude", "-77.4080"),
        "google_photos_url": db_config.get("google_photos_url", ""),
        "timezone": db_config.get("timezone", "America/New_York"),
        "quote_refresh": db_config.get("quote_refresh", "daily"),
        "quote_category": db_config.get("quote_category", "general"),
        "crew": crew_list
    })

def get_seed_chores_config():
    filepath = os.path.join(os.path.dirname(os.path.abspath(__file__)), "seed_chores.json")
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error reading seed_chores.json: {e}")
            
    # Default fallbacks
    defaults = {
        "toddler": [
            {"name": "Brush Teeth (Morning) 🪥", "points": 2, "time_block": "morning"},
            {"name": "Brush Teeth (Night) 🪥", "points": 2, "time_block": "evening"},
            {"name": "Pick up Toys 🧸", "points": 2, "time_block": "afternoon"}
        ],
        "young": [
            {"name": "Brush Teeth 🪥", "points": 5, "time_block": "morning"},
            {"name": "Pick up Toys 🧸", "points": 5, "time_block": "afternoon"},
            {"name": "Shower 🚿", "points": 5, "time_block": "evening"},
            {"name": "Put away Shoes 👟", "points": 5, "time_block": "afternoon"}
        ],
        "youth": [
            {"name": "Brush Teeth 🪥", "points": 5, "time_block": "morning"},
            {"name": "Shower 🚿", "points": 5, "time_block": "evening"},
            {"name": "Make Bed 🛏️", "points": 5, "time_block": "morning"},
            {"name": "Do Homework 📚", "points": 10, "time_block": "afternoon"},
            {"name": "Clean Room 🧹", "points": 15, "time_block": "afternoon"}
        ],
        "teen": [
            {"name": "Brush Teeth 🪥", "points": 5, "time_block": "morning"},
            {"name": "Shower 🚿", "points": 5, "time_block": "evening"},
            {"name": "Make Bed 🛏️", "points": 5, "time_block": "morning"},
            {"name": "Deep Clean Room 🧹", "points": 25, "time_block": "afternoon"},
            {"name": "Dishwasher Load/Empty 🍽️", "points": 10, "time_block": "evening"}
        ]
    }
    
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(defaults, f, indent=4)
    except Exception as e:
        print(f"Error writing seed_chores.json: {e}")
        
    return defaults

@app.route('/api/admin/seed-chores', methods=['GET', 'POST'])
def admin_seed_chores():
    if not require_parent():
        return jsonify({"success": False, "message": "Unauthorized"}), 403
        
    filepath = os.path.join(os.path.dirname(os.path.abspath(__file__)), "seed_chores.json")
    
    if request.method == 'POST':
        data = request.json
        if not data or not isinstance(data, dict):
            return jsonify({"success": False, "message": "Invalid configuration payload"}), 400
            
        for tier in ["toddler", "young", "youth", "teen"]:
            if tier not in data or not isinstance(data[tier], list):
                return jsonify({"success": False, "message": f"Missing or invalid array for tier '{tier}'"}), 400
                
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
            return jsonify({"success": True})
        except Exception as e:
            return jsonify({"success": False, "message": str(e)}), 500
            
    config = get_seed_chores_config()
    return jsonify(config)

@app.route('/api/system/initialize', methods=['POST'])
def api_system_initialize():
    if is_system_initialized() and not require_parent():
        return jsonify({"success": False, "message": "Unauthorized. System is already initialized."}), 403
    data = request.json or {}
    
    parent_password = data.get("parent_password")
    crew = data.get("crew", [])
    
    smtp_server = data.get("smtp_server", "")
    smtp_port = data.get("smtp_port", "587")
    smtp_username = data.get("smtp_username", "")
    smtp_password = data.get("smtp_password", "")
    smtp_to_email = data.get("smtp_to_email", "")
    
    ical_feed_url = data.get("ical_feed_url", "")
    solar_enabled = "true" if data.get("solar_enabled", True) else "false"
    enphase_username = data.get("enphase_username", "")
    enphase_password = data.get("enphase_password", "")
    enphase_system_name = data.get("enphase_system_name", "John")
    enphase_serial_num = data.get("enphase_serial_num", "123456789102")
    photo_source_mode = data.get("photo_source_mode", "default")
    
    weather_location_name = data.get("weather_location_name", "Stafford, VA 22554")
    weather_latitude = data.get("weather_latitude", "38.4232")
    weather_longitude = data.get("weather_longitude", "-77.4080")
    security_q1 = data.get("security_q1", "")
    security_a1_raw = data.get("security_a1", "").lower().strip()
    security_q2 = data.get("security_q2", "")
    security_a2_raw = data.get("security_a2", "").lower().strip()
    emergency_recovery_code = data.get("emergency_recovery_code")
    
    conn = get_db()
    cursor = conn.cursor()
    
    # 0. Clear out old configuration leftovers to start completely fresh!
    cursor.execute("DELETE FROM children")
    cursor.execute("DELETE FROM chores")
    cursor.execute("DELETE FROM chore_history")
    cursor.execute("DELETE FROM chore_submissions")
    cursor.execute("DELETE FROM parent_spotlights")
    cursor.execute("DELETE FROM habit_reminders")
    cursor.execute("DELETE FROM system_config")
    cursor.execute("DELETE FROM users")
    
    # 1. Register Parent Account Credentials with hashed password
    parent_username = data.get("parent_username", "parent") or "parent"
    if parent_password and parent_password != "••••••••":
        parent_hash = generate_password_hash(parent_password)
    else:
        parent_hash = generate_password_hash("admin")
    cursor.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", (parent_username, parent_hash))

    # Update with security questions
    security_a1 = hashlib.sha256(security_a1_raw.encode('utf-8')).hexdigest()
    security_a2 = hashlib.sha256(security_a2_raw.encode('utf-8')).hexdigest()
    cursor.execute("UPDATE users SET security_q1 = ?, security_a1 = ?, security_q2 = ?, security_a2 = ? WHERE username = ?",
                   (security_q1, security_a1, security_q2, security_a2, parent_username))
        
    # 2. Update system configs
    cursor.execute("INSERT OR REPLACE INTO system_config (key, value) VALUES ('admin_configured', 'true')")
    cursor.execute("INSERT OR REPLACE INTO system_config (key, value) VALUES ('smtp_server', ?)", (smtp_server,))
    cursor.execute("INSERT OR REPLACE INTO system_config (key, value) VALUES ('smtp_port', ?)", (smtp_port,))
    cursor.execute("INSERT OR REPLACE INTO system_config (key, value) VALUES ('smtp_username', ?)", (smtp_username,))
    
    # Sentinel preservation checks
    if smtp_password and smtp_password != "••••••••":
        enc_smtp = encrypt_val(smtp_password)
        cursor.execute("INSERT OR REPLACE INTO system_config (key, value) VALUES ('smtp_password', ?)", (enc_smtp,))
        
    cursor.execute("INSERT OR REPLACE INTO system_config (key, value) VALUES ('smtp_to_email', ?)", (smtp_to_email,))
    cursor.execute("INSERT OR REPLACE INTO system_config (key, value) VALUES ('ical_feed_url', ?)", (ical_feed_url,))
    cursor.execute("INSERT OR REPLACE INTO system_config (key, value) VALUES ('solar_enabled', ?)", (solar_enabled,))
    cursor.execute("INSERT OR REPLACE INTO system_config (key, value) VALUES ('enphase_username', ?)", (enphase_username,))
    
    if enphase_password and enphase_password != "••••••••":
        enc_enphase = encrypt_val(enphase_password)
        cursor.execute("INSERT OR REPLACE INTO system_config (key, value) VALUES ('enphase_password', ?)", (enc_enphase,))
        
    cursor.execute("INSERT OR REPLACE INTO system_config (key, value) VALUES ('enphase_system_name', ?)", (enphase_system_name,))
    cursor.execute("INSERT OR REPLACE INTO system_config (key, value) VALUES ('enphase_serial_num', ?)", (enphase_serial_num,))
    cursor.execute("INSERT OR REPLACE INTO system_config (key, value) VALUES ('photo_source_mode', ?)", (photo_source_mode,))
    cursor.execute("INSERT OR REPLACE INTO system_config (key, value) VALUES ('weather_location_name', ?)", (weather_location_name,))
    cursor.execute("INSERT OR REPLACE INTO system_config (key, value) VALUES ('weather_latitude', ?)", (weather_latitude,))
    cursor.execute("INSERT OR REPLACE INTO system_config (key, value) VALUES ('weather_longitude', ?)", (weather_longitude,))
    
    if emergency_recovery_code:
        recovery_hash = hashlib.sha256(emergency_recovery_code.encode('utf-8')).hexdigest()
        cursor.execute("INSERT OR REPLACE INTO system_config (key, value) VALUES ('emergency_recovery_hash', ?)", (recovery_hash,))
        
    # 3. Process Crew Roster and seed dynamic baseline chores
    for c in crew:
        name = c.get("name")
        age = int(c.get("age", 6))
        theme = c.get("theme", "dinosaur")
        font = c.get("font", "fredoka")
        avatar_path = c.get("avatar_path", "")
        profile_photo_path = c.get("profile_photo_path", "")
        seed_chores = c.get("seed_chores", True)
        
        cursor.execute("""
            INSERT INTO children (name, age, theme, font, points, bankable_balance, lifetime_xp, level, current_level, status, avatar_path, profile_photo_path)
            VALUES (?, ?, ?, ?, 0, 0, 0, 1, 1, 'active', ?, ?)
        """, (name, age, theme, font, avatar_path, profile_photo_path))
        child_id = cursor.lastrowid
        
        # Programmatically seed age-appropriate baseline chores based on customized guidelines if toggled
        if seed_chores:
            config = get_seed_chores_config()
            tier = "toddler" if age <= 4 else ("young" if age <= 8 else ("youth" if age <= 12 else "teen"))
            tier_chores = config.get(tier, [])
            for tc in tier_chores:
                cursor.execute("""
                    INSERT INTO chores (name, points, frequency, assigned_child_id, time_block, active_days, image_path)
                    VALUES (?, ?, 'daily', ?, ?, 'all', ?)
                """, (tc["name"], int(tc["points"]), child_id, tc.get("time_block", "morning"), tc.get("image_path")))
            
    conn.commit()
    conn.close()
    
    # Broadcast hot-reload
    payload = get_leaderboard_payload()
    broadcast_event("admin_config_change", payload)
    
    # Set parent login in session to bypass welcome wizard immediately!
    session["parent_auth"] = True
    
    return jsonify({"success": True})

# -------------------------------------------------------------
# CREW MEMBER CHILD PROFILE ACTIONS APIs
# -------------------------------------------------------------
@app.route('/api/admin/children/add', methods=['POST'])
def admin_add_child():
    if not require_parent():
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    data = request.json or {}
    name = data.get("name")
    age = int(data.get("age", 6))
    theme = data.get("theme", "dinosaur")
    font = data.get("font", "fredoka")
    
    if not name:
        return jsonify({"success": False, "message": "Name is required"}), 400
        
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("BEGIN IMMEDIATE")
    try:
        cursor.execute("""
            INSERT INTO children (name, age, theme, points, bankable_balance, lifetime_xp, level, current_level, status, font)
            VALUES (?, ?, ?, ?, 0, 0, 0, 1, 1, 'active', ?)
        """, (name, age, theme, font))
        child_id = cursor.lastrowid
        
        # Programmatically seed customized baseline chores based on age bracket
        config = get_seed_chores_config()
        tier = "toddler" if age <= 4 else ("young" if age <= 8 else ("youth" if age <= 12 else "teen"))
        tier_chores = config.get(tier, [])
        for tc in tier_chores:
            cursor.execute("""
                INSERT INTO chores (name, points, frequency, assigned_child_id, time_block, active_days, image_path)
                VALUES (?, ?, 'daily', ?, ?, 'all', ?)
            """, (tc["name"], int(tc["points"]), child_id, tc.get("time_block", "morning"), tc.get("image_path")))
        
        conn.commit()
    except sqlite3.IntegrityError:
        conn.rollback()
        return jsonify({"success": False, "message": "Child name already exists"}), 400
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        conn.close()
    
    payload = get_leaderboard_payload()
    broadcast_event("admin_config_change", payload)
    return jsonify({"success": True, "child_id": child_id})

@app.route('/api/admin/children/update', methods=['POST'])
def admin_update_child():
    if not require_parent():
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    data = request.json or {}
    child_id = data.get("child_id")
    name = data.get("name")
    age = int(data.get("age", 6))
    theme = data.get("theme", "dinosaur")
    font = data.get("font", "fredoka")
    points = int(data.get("points", 0))
    keys = int(data.get("keys", 0))
    avatar_path = data.get("avatar_path", "")
    profile_photo_path = data.get("profile_photo_path", "")
    
    if not child_id:
        return jsonify({"success": False, "message": "Child ID is required"}), 400
    if not name or not str(name).strip():
        return jsonify({"success": False, "message": "Name is required and cannot be empty"}), 400
        
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("BEGIN IMMEDIATE")
    try:
        # Check if name is taken by another child
        dup = cursor.execute("SELECT * FROM children WHERE name = ? AND id != ?", (name, child_id)).fetchone()
        if dup:
            conn.rollback()
            return jsonify({"success": False, "message": "Name is already in use"}), 400
            
        cursor.execute("""
            UPDATE children 
            SET name = ?, age = ?, theme = ?, font = ?, points = ?, bankable_balance = ?, vault_keys_available = ?, avatar_path = ?, profile_photo_path = ?
            WHERE id = ?
        """, (name, age, theme, font, points, points, keys, avatar_path, profile_photo_path, child_id))
        
        conn.commit()
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        conn.close()
    
    payload = get_leaderboard_payload()
    broadcast_event("admin_config_change", payload)
    return jsonify({"success": True})

@app.route('/api/admin/children/pause', methods=['POST'])
def admin_pause_child():
    if not require_parent():
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    data = request.json or {}
    child_id = data.get("child_id")
    
    conn = get_db()
    conn.execute("UPDATE children SET status = 'paused' WHERE id = ?", (child_id,))
    conn.commit()
    conn.close()
    
    payload = get_leaderboard_payload()
    broadcast_event("admin_config_change", payload)
    return jsonify({"success": True})

@app.route('/api/admin/children/resume', methods=['POST'])
def admin_resume_child():
    if not require_parent():
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    data = request.json or {}
    child_id = data.get("child_id")
    
    conn = get_db()
    conn.execute("UPDATE children SET status = 'active' WHERE id = ?", (child_id,))
    conn.commit()
    conn.close()
    
    payload = get_leaderboard_payload()
    broadcast_event("admin_config_change", payload)
    return jsonify({"success": True})

@app.route('/api/admin/habit-reminders', methods=['GET'])
def api_admin_get_habit_reminders():
    if not require_parent():
        return jsonify({"success": False, "message": "Unauthorized"}), 403
        
    conn = get_db()
    rows = conn.execute("""
        SELECT hr.*, c.name as child_name 
        FROM habit_reminders hr
        JOIN children c ON hr.child_id = c.id
        ORDER BY hr.created_at DESC
    """).fetchall()
    conn.close()
    
    reminders = [dict(r) for r in rows]
    return jsonify({"success": True, "reminders": reminders})

@app.route('/api/admin/habit-reminders', methods=['POST'])
def api_admin_issue_habit_reminder():
    if not require_parent():
        return jsonify({"success": False, "message": "Unauthorized"}), 403

    if request.content_type and request.content_type.startswith("multipart/form-data"):
        data = request.form
    else:
        data = request.json or {}

    child_id = data.get("child_id")
    note = data.get("note", "").strip()
    deduction_points = int(data.get("deduction_points", 5))
    
    if not child_id:
        return jsonify({"success": False, "message": "Child ID is required"}), 400
    if not note:
        return jsonify({"success": False, "message": "Note/reason is required"}), 400

    image_paths = []
    if request.files:
        files = request.files.getlist("images")
        if len(files) > 4:
            return jsonify({"success": False, "message": "Maximum 4 images allowed per reminder"}), 400

        import uuid
        from werkzeug.utils import secure_filename

        upload_dir = os.path.join("static", "habit_reminder_images")
        os.makedirs(upload_dir, exist_ok=True)
        for file in files:
            if not file or file.filename == "":
                continue
            filename = f"habit_{uuid.uuid4().hex}_{secure_filename(file.filename)}"
            file_path = os.path.join(upload_dir, filename)
            file.save(file_path)
            image_paths.append(f"habit_reminder_images/{filename}")
        
    import datetime
    created_at = datetime.datetime.now().isoformat()
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("BEGIN IMMEDIATE")
    try:
        # Insert habit reminder card
        cursor.execute("""
            INSERT INTO habit_reminders (child_id, photo_path, note, deduction_points, refunded_points, status, created_at)
            VALUES (?, ?, ?, ?, 0, 'active', ?)
        """, (child_id, json.dumps(image_paths) if image_paths else None, note, deduction_points, created_at))
        
        # Deduct points from child (points and bankable_balance clamped at 0)
        cursor.execute("""
            UPDATE children 
            SET points = MAX(0, points - ?), bankable_balance = MAX(0, bankable_balance - ?)
            WHERE id = ?
        """, (deduction_points, deduction_points, child_id))
        
        conn.commit()
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        conn.close()
        
    payload = get_leaderboard_payload()
    broadcast_event("admin_config_change", payload)
    broadcast_event("chore_update", {})
    return jsonify({"success": True})

@app.route('/api/admin/habit-reminders/refund', methods=['POST'])
def api_admin_refund_habit_reminder():
    if not require_parent():
        return jsonify({"success": False, "message": "Unauthorized"}), 403
        
    data = request.json or {}
    reminder_id = data.get("reminder_id")
    
    if not reminder_id:
        return jsonify({"success": False, "message": "Reminder ID is required"}), 400
        
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("BEGIN IMMEDIATE")
    try:
        # Fetch the active reminder details
        reminder = cursor.execute("SELECT * FROM habit_reminders WHERE id = ? AND status = 'active'", (reminder_id,)).fetchone()
        if not reminder:
            conn.rollback()
            return jsonify({"success": False, "message": "Active habit reminder not found"}), 404
            
        child_id = reminder["child_id"]
        deduction_points = reminder["deduction_points"]
        
        # Update the status to refunded and record the refunded points amount
        cursor.execute("""
            UPDATE habit_reminders 
            SET status = 'refunded', refunded_points = ?
            WHERE id = ?
        """, (deduction_points, reminder_id))
        
        # Credit the points back to the child
        cursor.execute("""
            UPDATE children 
            SET points = points + ?, bankable_balance = bankable_balance + ?
            WHERE id = ?
        """, (deduction_points, deduction_points, child_id))
        
        conn.commit()
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        conn.close()
        
    payload = get_leaderboard_payload()
    broadcast_event("admin_config_change", payload)
    broadcast_event("chore_update", {})
    return jsonify({"success": True})

@app.route('/api/admin/children/delete', methods=['POST'])
def admin_delete_child():
    if not require_parent():
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    data = request.json or {}
    child_id = data.get("child_id")
    deleted_at_str = datetime.datetime.now().isoformat()
    
    conn = get_db()
    conn.execute("UPDATE children SET status = 'pending_delete', deleted_at = ? WHERE id = ?", (deleted_at_str, child_id))
    conn.commit()
    conn.close()
    
    payload = get_leaderboard_payload()
    broadcast_event("admin_config_change", payload)
    return jsonify({"success": True})

@app.route('/api/admin/children/restore', methods=['POST'])
def admin_restore_child():
    if not require_parent():
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    data = request.json or {}
    child_id = data.get("child_id")
    
    conn = get_db()
    conn.execute("UPDATE children SET status = 'active', deleted_at = NULL WHERE id = ?", (child_id,))
    conn.commit()
    conn.close()
    
    payload = get_leaderboard_payload()
    broadcast_event("admin_config_change", payload)
    return jsonify({"success": True})

@app.route('/api/admin/children/fulfill-asset', methods=['POST'])
def api_admin_fulfill_asset():
    if not require_parent():
        return jsonify({"success": False, "message": "Unauthorized"}), 403
        
    data = request.json or {}
    child_id = data.get("child_id")
    asset = data.get("asset")
    
    if not child_id or not asset:
        return jsonify({"success": False, "message": "Missing child_id or asset"}), 400
        
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("BEGIN IMMEDIATE")
    try:
        child = cursor.execute("SELECT name, unlocked_assets FROM children WHERE id = ?", (child_id,)).fetchone()
        if not child:
            conn.rollback()
            return jsonify({"success": False, "message": "Child profile not found"}), 404
            
        unlocked_list = json.loads(child["unlocked_assets"] or "[]")
        if asset in unlocked_list:
            unlocked_list.remove(asset)
        else:
            conn.rollback()
            return jsonify({"success": False, "message": "Reward asset not found in child's unlocked vault list"}), 404
            
        unlocked_json = json.dumps(unlocked_list)
        cursor.execute("UPDATE children SET unlocked_assets = ? WHERE id = ?", (unlocked_json, child_id))
        conn.commit()
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        conn.close()
        
    # Broadcast configuration payload updates to instantly clear checkboxes and items across all kiosk screens
    payload = get_leaderboard_payload()
    broadcast_event("admin_config_change", payload)
    broadcast_event("chore_update", {"leaderboard": payload})
    return jsonify({"success": True})

@app.route('/api/admin/children/upload-photo', methods=['POST'])
def admin_upload_child_photo():
    if not require_parent():
        return jsonify({"success": False, "message": "Unauthorized"}), 403
        
    child_id = request.form.get("child_id")
    upload_type = request.form.get("type", "profile")  # 'profile' or 'avatar'
    
    if not child_id:
        return jsonify({"success": False, "message": "Child ID is required"}), 400
        
    if 'photo' not in request.files:
        return jsonify({"success": False, "message": "No photo file provided"}), 400
        
    file = request.files['photo']
    if file.filename == '':
        return jsonify({"success": False, "message": "No file selected"}), 400
        
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ['.jpg', '.jpeg', '.png', '.gif', '.webp'] or not (file.content_type and file.content_type.startswith('image/')):
        return jsonify({"success": False, "message": "Invalid format. Supported: JPG, PNG, WEBP, GIF"}), 400
        
    upload_folder = os.path.join("static", "media", "child_photos")
    os.makedirs(upload_folder, exist_ok=True)
    
    filename = f"child_{child_id}_{upload_type}{ext}"
    filepath = os.path.join(upload_folder, filename)
    file.save(filepath)
    
    photo_url = f"/media/child_photos/{filename}"
    conn = get_db()
    if upload_type == "avatar":
        conn.execute("UPDATE children SET avatar_path = ? WHERE id = ?", (photo_url, child_id))
    else:
        conn.execute("UPDATE children SET profile_photo_path = ? WHERE id = ?", (photo_url, child_id))
    conn.commit()
    conn.close()
    
    payload = get_leaderboard_payload()
    broadcast_event("admin_config_change", payload)
    return jsonify({"success": True, f"{upload_type}_path": photo_url})

def run_photo_sync_async(source="static/media/manual_uploads"):
    """Executes the heavy photo re-indexing script cleanly in a disconnected thread context"""
    try:
        import sys
        import subprocess
        python_exe = sys.executable
        script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sync_photos.py")
        subprocess.run([python_exe, script_path, "--source", source], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        payload = get_leaderboard_payload()
        broadcast_event("admin_config_change", payload)
        print(f"[+] Background photo engine indexing completed successfully for source: {source}")
    except Exception as err:
        print(f"[-] Asynchronous photo sync failure check: {err}")

@app.route('/api/admin/photos/upload', methods=['POST'])
def admin_upload_photos():
    if is_system_initialized() and not require_parent():
        return jsonify({"success": False, "message": "Unauthorized"}), 403
        
    files = request.files.getlist('photos[]') or request.files.getlist('photos')
    if not files:
        return jsonify({"success": False, "message": "No photo files provided"}), 400
        
    upload_folder = os.path.join("static", "media", "manual_uploads")
    os.makedirs(upload_folder, exist_ok=True)
    
    saved_count = 0
    allowed_extensions = {'.png', '.jpg', '.jpeg', '.webp', '.gif'}
    
    for file in files:
        if file.filename == '':
            continue
        ext = os.path.splitext(file.filename)[1].lower()
        if ext in allowed_extensions and file.content_type and file.content_type.startswith('image/'):
            from werkzeug.utils import secure_filename
            filename = secure_filename(file.filename)
            base_name, ext_part = os.path.splitext(filename)
            counter = 1
            unique_filename = filename
            while os.path.exists(os.path.join(upload_folder, unique_filename)):
                unique_filename = f"{base_name}_{counter}{ext_part}"
                counter += 1
                
            filepath = os.path.join(upload_folder, unique_filename)
            file.save(filepath)
            saved_count += 1
            
    if saved_count == 0:
        return jsonify({"success": False, "message": "No valid images were uploaded"}), 400
        
    threading.Thread(target=run_photo_sync_async, args=("static/media/manual_uploads",), daemon=True).start()
    
    return jsonify({"success": True, "message": f"Successfully uploaded {saved_count} photos to manual directory."})

@app.route('/api/admin/photos/delete', methods=['POST'])
def admin_delete_photo():
    if not require_parent():
        return jsonify({"success": False, "message": "Unauthorized"}), 403
        
    data = request.json
    if not data or 'src' not in data:
        return jsonify({"success": False, "message": "Missing 'src' parameter"}), 400
        
    src = data['src']
    
    # Clean the src path to prevent directory traversal
    if ".." in src or src.startswith("/") or src.startswith("\\"):
        return jsonify({"success": False, "message": "Invalid photo path"}), 400
        
    # Check if manual or google photo
    actual_filepath = None
    is_google = False
    
    if src.startswith("photos/"):
        is_google = True
        actual_filepath = os.path.join(os.path.dirname(os.path.abspath(__file__)), src)
    elif src.startswith("media/manual_uploads/"):
        actual_filepath = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", src)
    else:
        return jsonify({"success": False, "message": "Unknown photo category"}), 400
        
    # Check if file exists and delete it
    if os.path.exists(actual_filepath):
        try:
            os.remove(actual_filepath)
        except Exception as e:
            return jsonify({"success": False, "message": f"Error deleting file from disk: {str(e)}"}), 500
            
    # If Google Photo, record it in the blacklist so it's not downloaded again
    if is_google:
        filename = os.path.basename(actual_filepath)
        blacklist_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "deleted_photos.json")
        blacklist = []
        if os.path.exists(blacklist_path):
            try:
                with open(blacklist_path, "r", encoding="utf-8") as f:
                    blacklist = json.load(f)
                    if not isinstance(blacklist, list):
                        blacklist = []
            except Exception:
                blacklist = []
                
        if filename not in blacklist:
            blacklist.append(filename)
            try:
                with open(blacklist_path, "w", encoding="utf-8") as f:
                    json.dump(blacklist, f, indent=4)
            except Exception as e:
                return jsonify({"success": False, "message": f"Error updating blacklist: {str(e)}"}), 500

    # Trigger photo registry reindexing asynchronously
    source = "photos" if is_google else "static/media/manual_uploads"
    threading.Thread(target=run_photo_sync_async, args=(source,), daemon=True).start()
    
    return jsonify({"success": True, "message": "Photo deleted successfully."})

# -------------------------------------------------------------
# CORE NETWORK INFRASTRUCTURE & TELEMETRY
# -------------------------------------------------------------
# Helper to dynamically retrieve active local LAN IP address
def get_local_ip():
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip

# Helper to dynamically retrieve host physical hardware MAC address
def get_mac_address():
    import uuid
    try:
        mac_num = uuid.getnode()
        mac_hex = f"{mac_num:012x}"
        mac_str = ":".join(mac_hex[i:i+2] for i in range(0, 11, 2)).upper()
        return mac_str
    except Exception:
        return "00:00:00:00:00:00"

@app.route('/api/admin/network/status', methods=['GET'])
def api_admin_network_status():
    if not require_parent():
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    try:
        ip = get_local_ip()
        mac = get_mac_address()
        return jsonify({
            "success": True,
            "ip_address": ip,
            "mac_address": mac
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/admin/system/update-check', methods=['GET'])
def api_admin_system_update_check():
    if not require_parent():
        return jsonify({"success": False, "message": "Unauthorized"}), 403

    repo_api_url = "https://api.github.com/repos/senyogmx-droid/Family-Command-Center/releases/latest"
    current_version = APP_VERSION       # Keep this in sync with your code

    import urllib.request
    import urllib.error
    import json

    try:
        req = urllib.request.Request(
            repo_api_url,
            headers={'User-Agent': f'FamilyCommandCenter/{APP_VERSION[1:]}'}
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode('utf-8'))
            latest_version = data.get("tag_name", "").strip()
            release_notes = data.get("body", "No release notes provided.")
            download_url = data.get("html_url", repo_api_url)

            # Compare versions
            update_available = latest_version > current_version

            return jsonify({
                "success": True,
                "update_available": update_available,
                "current_version": current_version,
                "latest_version": latest_version,
                "changelog": release_notes[:500],   # first 500 chars
                "url": download_url
            })
    except urllib.error.URLError as e:
        # GitHub API is unreachable—fall back gracefully
        return jsonify({
            "success": True,
            "update_available": False,
            "current_version": current_version,
            "latest_version": current_version,
            "changelog": "Could not connect to GitHub. Please check your internet connection.",
            "url": "https://github.com/senyogmx-droid/Family-Command-Center"
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/admin/spotlight', methods=['POST'])
def admin_add_spotlight():
    if not require_parent():
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    data = request.json or {}
    child_id = data.get("child_id")
    note = data.get("note")
    points = int(data.get("points", 10))
    giver = data.get("giver", "Parent")
    
    if not child_id or not note:
        return jsonify({"success": False, "message": "Child ID and note are required"}), 400
        
    conn = get_db()
    cursor = conn.cursor()
    
    created_at = datetime.datetime.now().isoformat()
    cursor.execute("""
        INSERT INTO parent_spotlights (child_id, note, bonus_points, giver_name, created_at, status)
        VALUES (?, ?, ?, ?, ?, 'pending_popup')
    """, (child_id, note, points, giver, created_at))
    
    cursor.execute("""
        UPDATE children 
        SET points = points + ?, bankable_balance = bankable_balance + ?, lifetime_xp = lifetime_xp + ? 
        WHERE id = ?
    """, (points, points, points, child_id))
    
    conn.commit()
    conn.close()
    
    payload = get_leaderboard_payload()
    broadcast_event("chore_update", {"leaderboard": payload})
    return jsonify({"success": True})

# -------------------------------------------------------------
# TREASURE VAULT CHEST EXCHANGES APIs
# -------------------------------------------------------------
@app.route('/api/children/vault/unlock', methods=['POST'])
def api_children_vault_unlock():
    data = request.json or {}
    child_id = data.get("child_id")
    tier = data.get("tier") or data.get("chest_type") or data.get("chestType") # bronze, silver, gold
    
    if not child_id or not tier:
        return jsonify({"success": False, "message": "Missing arguments"}), 400
        
    cost_map = {"bronze": 1, "silver": 2, "gold": 3}
    cost = cost_map.get(tier.lower(), 99)
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("BEGIN IMMEDIATE")
    try:
        child = cursor.execute("SELECT * FROM children WHERE id = ?", (child_id,)).fetchone()
        
        if not child:
            conn.rollback()
            return jsonify({"success": False, "message": "Child profile not found"}), 404
            
        keys_avail = child["vault_keys_available"]
        if keys_avail < cost:
            conn.rollback()
            return jsonify({"success": False, "message": f"Insufficient Vault Keys! Requires {cost} keys."}), 400
            
        # Pick reward
        if tier.lower() == "bronze":
            reward = random.choice(["🔥 Fire Trail", "✨ Sparkle Dust", "🚀 Comet Speed Boost", "🍕 Victory Pizza", "🐱 Neko Companion"])
        elif tier.lower() == "silver":
            reward = random.choice(["⏰ 15-Min Bedtime Extension", "🎮 30-Min Extra Screen Time", "🧹 Skip Chore Coupon", "🌌 Cosmic Custom UI Theme"])
        else:
            reward = random.choice(["👑 Rare Gold Card Profile Frame", "🍔 Select Dinner of Choice", "🎬 Pick Family Movie Night", "🍦 Double Scoop Ice Cream Treat"])
            
        # Deduct key and add unlocked asset
        new_keys = keys_avail - cost
        unlocked_list = json.loads(child["unlocked_assets"] or "[]")
        unlocked_list.append(reward)
        unlocked_json = json.dumps(unlocked_list)
        
        cursor.execute("UPDATE children SET vault_keys_available = ?, unlocked_assets = ? WHERE id = ?", (new_keys, unlocked_json, child_id))
        conn.commit()
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        conn.close()
    
    payload = get_leaderboard_payload()
    broadcast_event("chore_update", {"leaderboard": payload})
    return jsonify({"success": True, "reward": reward, "keys": new_keys, "unlocked_assets": unlocked_list})

@app.route('/api/chores/submit-enrichment', methods=['POST'])
def api_submit_enrichment():
    chore_id = request.form.get("chore_id")
    child_id = request.form.get("child_id")
    notes = request.form.get("notes", "")
    
    if not chore_id or not child_id:
        return jsonify({"success": False, "message": "Missing chore_id or child_id"}), 400
        
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("BEGIN IMMEDIATE")
    try:
        chore = cursor.execute("SELECT name, points FROM chores WHERE id = ?", (chore_id,)).fetchone()
        child = cursor.execute("SELECT name FROM children WHERE id = ?", (child_id,)).fetchone()
        
        if not chore or not child:
            conn.rollback()
            return jsonify({"success": False, "message": "Chore or child not found"}), 404
            
        child_name = child["name"]
        chore_name = chore["name"]
        
        # Save audio files if uploaded
        audio_urls = [None, None, None]
        audio_folder = os.path.join("static", "media", "submissions", "audio")
        os.makedirs(audio_folder, exist_ok=True)
        
        for i in range(3):
            field_name = f"audio_{i+1}"
            if field_name in request.files:
                file = request.files[field_name]
                if file and file.filename != '':
                    # Validate audio MIME type to ensure only valid audio format uploads are permitted
                    if not (file.content_type and (file.content_type.startswith('audio/') or file.filename.endswith(('.wav', '.mp3', '.m4a', '.ogg')))):
                        conn.rollback()
                        return jsonify({"success": False, "message": "Invalid audio file type."}), 400
                    from werkzeug.utils import secure_filename
                    filename = secure_filename(f"sub_{chore_id}_{child_id}_{i+1}.wav")
                    filepath = os.path.join(audio_folder, filename)
                    file.save(filepath)
                    audio_urls[i] = f"/media/submissions/audio/{filename}"
                    
        # Save photo if uploaded
        photo_url = None
        photo_folder = os.path.join("static", "media", "submissions", "photos")
        os.makedirs(photo_folder, exist_ok=True)
        
        if "photo" in request.files:
            file = request.files["photo"]
            if file and file.filename != '':
                ext = os.path.splitext(file.filename)[1].lower()
                if ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp'] and file.content_type and file.content_type.startswith('image/'):
                    filename = f"sub_{chore_id}_{child_id}{ext}"
                    filepath = os.path.join(photo_folder, filename)
                    file.save(filepath)
                    photo_url = f"/media/submissions/photos/{filename}"
                    
        today_str = datetime.date.today().isoformat()
        
        # Insert pending approval record into chore_submissions
        cursor.execute("""
            INSERT INTO chore_submissions (chore_id, child_id, audio_path_1, audio_path_2, audio_path_3, photo_path, transcript, status, submitted_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'pending_approval', ?)
        """, (chore_id, child_id, audio_urls[0], audio_urls[1], audio_urls[2], photo_url, notes, today_str))
        
        conn.commit()
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        conn.close()
    
    # Trigger background dynamic email alert asynchronously (is_grace_period=False)
    threading.Thread(target=trigger_parent_email_alert, args=(child_name, chore_name, False), daemon=True).start()
    
    # Broadcast hot-reload
    payload = get_leaderboard_payload()
    broadcast_event("chore_update", {"leaderboard": payload})
    
    return jsonify({"success": True})

@app.route('/api/children/status/<name>', methods=['GET'])
def api_child_status(name):
    conn = get_db()
    row = conn.execute("SELECT name, age, theme, font, points, current_level, vault_keys_available FROM children WHERE LOWER(name) = ? AND status = 'active'", (name.lower(),)).fetchone()
    conn.close()
    if not row:
        return jsonify({"success": False, "message": "Child profile profile not found"}), 404
    return jsonify({
        "success": True,
        "name": row["name"],
        "theme": row["theme"],
        "font": row["font"],
        "points": row["points"],
        "level": row["current_level"],
        "keys": row["vault_keys_available"]
    })

@app.route('/api/chores/dismiss-spotlight', methods=['POST'])
def api_dismiss_spotlight():
    data = request.json or {}
    spotlight_id = data.get("id")
    conn = get_db()
    conn.execute("UPDATE system_config SET value = 'dismissed' WHERE key = ?", (f"spotlight_{spotlight_id}",))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route('/api/vault/open', methods=['POST'])
def api_vault_open_alias():
    """Maps legacy frontend open calls directly to the standard unlock controller"""
    return api_children_vault_unlock()

@app.route('/api/admin/chores/review', methods=['GET'])
def api_admin_chores_review():
    if not require_parent():
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    conn = get_db()
    # Fetch entries flagged under yesterday's grace period rules
    pending_items = conn.execute("""
        SELECT s.id, c.name, s.child_id AS assigned_child_id, c.points, ch.name AS child_name, s.submitted_date
        FROM chore_submissions s
        JOIN chores c ON s.chore_id = c.id
        JOIN children ch ON s.child_id = ch.id
        WHERE s.status = 'pending_approval'
    """).fetchall()
    conn.close()
    return jsonify({
        "success": True, 
        "submissions": [dict(row) for row in pending_items]
    })

@app.route('/api/admin/chores/approve-action', methods=['POST'])
def api_admin_approve_action():
    if not require_parent():
        return jsonify({"success": False, "message": "Unauthorized"}), 403
        
    data = request.json or {}
    chore_id = data.get("chore_id")
    action = data.get("action")  # 'approve' or 'reject'
    
    # Calculate yesterday's exact date string to pinpoint the historical row
    import datetime
    yesterday = datetime.date.today() - datetime.timedelta(days=1)
    yesterday_str = yesterday.strftime("%Y-%m-%d")
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("BEGIN IMMEDIATE")
    try:
        # Check if the chore_id is actually a submission_id (from queue)
        submission = cursor.execute("SELECT * FROM chore_submissions WHERE id = ?", (chore_id,)).fetchone()
        if submission:
            actual_chore_id = submission['chore_id']
            assigned_child_id = submission['child_id']
            yesterday_str = submission['submitted_date']
            submission_id = submission['id']
        else:
            actual_chore_id = chore_id
            # Fallback lookup by chore_id and yesterday's date
            submission = cursor.execute("SELECT * FROM chore_submissions WHERE chore_id = ? AND submitted_date = ?", (actual_chore_id, yesterday_str)).fetchone()
            if submission:
                assigned_child_id = submission['child_id']
                submission_id = submission['id']
            else:
                chore_row = cursor.execute("SELECT assigned_child_id FROM chores WHERE id = ?", (actual_chore_id,)).fetchone()
                assigned_child_id = chore_row['assigned_child_id'] if chore_row else None
                submission_id = None
                
        chore = cursor.execute("SELECT points, assigned_child_id FROM chores WHERE id = ?", (actual_chore_id,)).fetchone()
        if not chore:
            conn.rollback()
            return jsonify({"success": False, "message": "Master chore tracking link missing"}), 404
            
        child_id = assigned_child_id or chore['assigned_child_id']
        if not child_id:
            conn.rollback()
            return jsonify({"success": False, "message": "No child associated with this chore completion"}), 400
            
        if action == "approve":
            # 1. Update the historical date-stamped log to 'completed'
            if submission_id:
                cursor.execute("UPDATE chore_submissions SET status = 'completed' WHERE id = ?", (submission_id,))
            else:
                cursor.execute("UPDATE chore_submissions SET status = 'completed' WHERE chore_id = ? AND submitted_date = ?", (actual_chore_id, yesterday_str))
                
            # 2. Insert into history to officially complete it in daily status summaries
            exists = cursor.execute("SELECT 1 FROM chore_history WHERE chore_id = ? AND child_id = ? AND completed_date = ?", (actual_chore_id, child_id, yesterday_str)).fetchone()
            if not exists:
                cursor.execute("INSERT INTO chore_history (chore_id, child_id, completed_date) VALUES (?, ?, ?)", (actual_chore_id, child_id, yesterday_str))
                
            # 3. Award points and progress tokens to the child's profile permanently
            cursor.execute(
                "UPDATE children SET points = points + ?, bankable_balance = bankable_balance + ?, lifetime_xp = lifetime_xp + ? WHERE id = ?", 
                (chore['points'], chore['points'], chore['points'], child_id)
            )
            
            # 4. Check level progression dynamically
            child_row = cursor.execute("SELECT name, lifetime_xp, level, vault_keys_available FROM children WHERE id = ?", (child_id,)).fetchone()
            if child_row:
                new_level = (child_row["lifetime_xp"] // 100) + 1
                if new_level > child_row["level"]:
                    new_keys = child_row["vault_keys_available"] + (new_level - child_row["level"])
                    cursor.execute("UPDATE children SET level = ?, current_level = ?, vault_keys_available = ? WHERE id = ?", (new_level, new_level, new_keys, child_id))
                    broadcast_event("level_up", {
                        "child_id": child_id,
                        "name": child_row["name"],
                        "level": new_level
                    })
        elif action == "revision":
            # 1. Get the parent feedback from the request
            feedback = data.get("feedback", "").strip()
            if not feedback:
                conn.rollback()
                return jsonify({"success": False, "message": "Revision feedback is required"}), 400
    
            # 2. Update submission status to 'needs_revision' and store the feedback
            if submission_id:
                cursor.execute("UPDATE chore_submissions SET status = 'needs_revision', parent_feedback = ? WHERE id = ?", (feedback, submission_id))
            else:
                cursor.execute("UPDATE chore_submissions SET status = 'needs_revision', parent_feedback = ? WHERE chore_id = ? AND submitted_date = ?", (feedback, actual_chore_id, yesterday_str))
            # 3. Remove any existing history entry (so points are never awarded)
            cursor.execute("DELETE FROM chore_history WHERE chore_id = ? AND child_id = ? AND completed_date = ?", (actual_chore_id, child_id, yesterday_str))
    
        else:  # reject / deny
            # 1. Update status to 'rejected' so the child's screen knows it was denied
            if submission_id:
                cursor.execute("UPDATE chore_submissions SET status = 'rejected' WHERE id = ?", (submission_id,))
            else:
                cursor.execute("UPDATE chore_submissions SET status = 'rejected' WHERE chore_id = ? AND submitted_date = ?", (actual_chore_id, yesterday_str))
                
            # 2. Remove history log to revert to uncompleted status
            cursor.execute("DELETE FROM chore_history WHERE chore_id = ? AND child_id = ? AND completed_date = ?", (actual_chore_id, child_id, yesterday_str))
            # (Points are safely untouched because they were never permanently committed during pending status)
    
        conn.commit()
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        conn.close()
    
    # Broadcast configuration payload updates to instantly clear checkboxes on all kiosk screens
    broadcast_event("admin_config_change", get_leaderboard_payload())
    return jsonify({"success": True})

# -------------------------------------------------------------
# MULTI-SCREEN BASE ROUTE HANDLERS
# -------------------------------------------------------------
@app.route('/')
@app.route('/index')
def route_dashboard():
    if not is_system_initialized():
        return redirect('/welcome')
    return send_from_directory(app.static_folder, "index.html")

@app.route('/admin')
def route_admin():
    if not is_system_initialized():
        return redirect('/welcome')
    return send_from_directory(app.static_folder, "admin.html")

@app.route('/performance')
def route_performance():
    if not is_system_initialized():
        return redirect('/welcome')
    return send_from_directory(app.static_folder, "performance.html")

@app.route('/choresum')
def route_choresum():
    if not is_system_initialized():
        return redirect('/welcome')
    return send_from_directory(app.static_folder, "choresum.html")

@app.route('/choresum.html')
def route_choresum_html():
    return redirect('/choresum')

@app.route('/weekly')
def route_weekly():
    return redirect('/choresum')

@app.route('/weekly.html')
def route_weekly_html():
    return redirect('/weekly')

@app.route('/choresum/<name>')
def route_choresum_child(name):
    conn = get_db()
    child = conn.execute("SELECT name FROM children WHERE LOWER(name) = ? AND status = 'active'", (name.lower(),)).fetchone()
    conn.close()
    if child:
        return send_from_directory(app.static_folder, "child.html")
    return "Profile not found", 404

# Optional: redirect old routes
@app.route('/child')
def route_child_old():
    return redirect('/choresum')

@app.route('/child/<name>')
def route_child_legacy_old(name):
    return redirect(f'/choresum/{name}')

@app.route('/welcome')
def route_welcome():
    if is_system_initialized() and not require_parent():
        return redirect('/')
    return send_from_directory(app.static_folder, "welcome.html")

@app.route('/<name>')
def route_child_direct(name):
    conn = get_db()
    child = conn.execute("SELECT name FROM children WHERE LOWER(name) = ? AND status = 'active'", (name.lower(),)).fetchone()
    conn.close()
    if child:
        return send_from_directory(app.static_folder, "child.html")
    # Redirect static asset files cleanly
    static_file_path = os.path.join(app.static_folder, name)
    if os.path.exists(static_file_path) and os.path.isfile(static_file_path):
        return send_from_directory(app.static_folder, name)
    return "Profile not found", 404

@app.route('/download/apk')
def download_apk():
    apk_dir = os.path.join(app.static_folder, "apps")
    apk_filename = "FamilyDashboard.apk"
    if not os.path.exists(os.path.join(apk_dir, apk_filename)):
        # Make a mock empty file if it doesn't exist for direct endpoints
        os.makedirs(apk_dir, exist_ok=True)
        with open(os.path.join(apk_dir, apk_filename), "wb") as f:
            f.write(b"mock_apk_content")
    return send_from_directory(apk_dir, apk_filename, as_attachment=True)

@app.route('/photos/<path:filename>')
def serve_photos(filename):
    return send_from_directory(os.path.abspath("photos"), filename)

@app.route('/<path:path>')
def route_static(path):
    return send_from_directory(app.static_folder, path)

# -------------------------------------------------------------
# INTEGRATIONS — Weather & Solar Credential Endpoints
# -------------------------------------------------------------
@app.route('/api/admin/weather-config', methods=['POST'])
def api_admin_weather_config():
    if not require_parent():
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    data = request.json or {}
    loc_name = data.get("weather_location_name", "").strip()
    lat = data.get("weather_latitude")
    lon = data.get("weather_longitude")

    if not loc_name or lat is None or lon is None:
        return jsonify({"success": False, "message": "Location name, latitude, and longitude are required"}), 400

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO system_config (key, value) VALUES ('weather_location_name', ?)", (loc_name,))
    cursor.execute("INSERT OR REPLACE INTO system_config (key, value) VALUES ('weather_latitude', ?)", (str(lat),))
    cursor.execute("INSERT OR REPLACE INTO system_config (key, value) VALUES ('weather_longitude', ?)", (str(lon),))
    conn.commit()
    conn.close()

    # Broadcast update so dashboard refreshes weather widget
    broadcast_event("admin_config_change", get_leaderboard_payload())
    return jsonify({"success": True})


@app.route('/api/admin/solar-credentials', methods=['POST'])
def api_admin_solar_credentials():
    if not require_parent():
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    data = request.json or {}
    username = data.get("enphase_username", "")
    password = data.get("enphase_password", "")
    system_name = data.get("enphase_system_name", "")
    serial_num = data.get("enphase_serial_num", "")

    conn = get_db()
    cursor = conn.cursor()
    if username:
        cursor.execute("INSERT OR REPLACE INTO system_config (key, value) VALUES ('enphase_username', ?)", (username,))
    if password:
        enc_pw = encrypt_val(password)
        cursor.execute("INSERT OR REPLACE INTO system_config (key, value) VALUES ('enphase_password', ?)", (enc_pw,))
    if system_name:
        cursor.execute("INSERT OR REPLACE INTO system_config (key, value) VALUES ('enphase_system_name', ?)", (system_name,))
    if serial_num:
        cursor.execute("INSERT OR REPLACE INTO system_config (key, value) VALUES ('enphase_serial_num', ?)", (serial_num,))
    conn.commit()
    conn.close()

    broadcast_event("admin_config_change", get_leaderboard_payload())
    return jsonify({"success": True})

@app.route('/api/children/badges/<int:child_id>', methods=['GET'])
def get_child_badges(child_id):
    conn = get_db()
    cursor = conn.cursor()
    
    badges = []
    
    # 1. Level-up badges (from children table)
    child = cursor.execute("SELECT name, level, lifetime_xp, unlocked_assets FROM children WHERE id = ?", (child_id,)).fetchone()
    if child:
        for lvl in range(1, child["level"] + 1):
            badges.append({
                "type": "level",
                "title": f"Level {lvl} Achieved!",
                "icon": "⬆️",
                "date": None,  # we don't store exact date per level, but could approximate
                "description": f"Reached Level {lvl} by earning {lvl*100} XP!"
            })
    
    # 2. Perfect week streaks
    # Count weeks where all 7 days had at least one chore completion
    # This requires some analysis of chore_history. Simplified version:
    cursor.execute("""
        SELECT DATE(completed_date) as date, COUNT(*) as chores
        FROM chore_history
        WHERE child_id = ?
        GROUP BY completed_date
        HAVING chores > 0
    """, (child_id,))
    dates = [row["date"] for row in cursor.fetchall()]
    # Calculate consecutive days (simplified – you can expand)
    # For brevity, I'll add a static example; you can implement actual streak logic.
    
    # 3. Spotlight badges
    spotlights = cursor.execute("""
        SELECT note, bonus_points, created_at FROM parent_spotlights
        WHERE child_id = ?
    """, (child_id,)).fetchall()
    for s in spotlights:
        badges.append({
            "type": "spotlight",
            "title": "Parent’s Spotlight",
            "icon": "⭐",
            "date": s["created_at"][:10] if s["created_at"] else None,
            "description": f"\"{s['note']}\" (+{s['bonus_points']} XP)"
        })
    
    # 4. Vault chest unlocks (from unlocked_assets)
    if child and child["unlocked_assets"]:
        import json
        try:
            assets = json.loads(child["unlocked_assets"])
            for asset in assets:
                badges.append({
                    "type": "vault",
                    "title": asset,
                    "icon": "🎁",
                    "date": None,
                    "description": "Unlocked from the Treasure Vault!"
                })
        except Exception:
            pass
    
    conn.close()
    return jsonify({"success": True, "badges": badges})


@app.route('/api/admin/rewards', methods=['GET'])
def admin_get_rewards():
    if not require_parent():
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    conn = get_db()
    rows = conn.execute("SELECT * FROM rewards ORDER BY points_cost ASC").fetchall()
    conn.close()
    return jsonify({"success": True, "rewards": [dict(r) for r in rows]})

@app.route('/api/admin/rewards', methods=['POST'])
def admin_add_reward():
    if not require_parent():
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    data = request.json
    name = data.get("name", "").strip()
    description = data.get("description", "").strip()
    points_cost = data.get("points_cost")
    child_id = data.get("child_id")  # may be None or "null"
    if child_id == "null" or child_id == "":
        child_id = None
    else:
        try:
            child_id = int(child_id)
        except:
            child_id = None
    
    if not name or not points_cost or points_cost < 1:
        return jsonify({"success": False, "message": "Name and valid points cost required"}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO rewards (name, description, points_cost, child_id, created_at) VALUES (?, ?, ?, ?, ?)",
        (name, description, points_cost, child_id, datetime.datetime.now().isoformat())
    )
    reward_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return jsonify({"success": True, "reward_id": reward_id})

@app.route('/api/admin/rewards/<int:reward_id>', methods=['DELETE'])
def admin_delete_reward(reward_id):
    if not require_parent():
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    conn = get_db()
    conn.execute("DELETE FROM rewards WHERE id = ?", (reward_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route('/api/admin/rewards/<int:reward_id>/upload-image', methods=['POST'])
def upload_reward_image(reward_id):
    if not require_parent():
        return jsonify({"error": "Unauthorized"}), 403
    if 'image' not in request.files:
        return jsonify({"error": "No file"}), 400
    file = request.files['image']
    if file.filename == '':
        return jsonify({"error": "Empty filename"}), 400
    
    import os
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ['.jpg', '.jpeg', '.png', '.gif', '.webp'] or not (file.content_type and file.content_type.startswith('image/')):
        return jsonify({"error": "Invalid format. Supported: JPG, PNG, WEBP, GIF"}), 400
        
    import uuid
    from werkzeug.utils import secure_filename
    filename = f"reward_{reward_id}_{uuid.uuid4().hex}_{secure_filename(file.filename)}"
    upload_dir = os.path.join('static', 'chore_images')
    os.makedirs(upload_dir, exist_ok=True)
    path = os.path.join(upload_dir, filename)
    web_path = f"chore_images/{filename}"
    file.save(path)
    conn = get_db()
    conn.execute("UPDATE rewards SET image_path = ? WHERE id = ?", (web_path, reward_id))
    conn.commit()
    conn.close()
    return jsonify({"success": True, "image_path": web_path})

@app.route('/api/admin/rewards/<int:reward_id>/remove-image', methods=['DELETE'])
def remove_reward_image(reward_id):
    if not require_parent():
        return jsonify({"error": "Unauthorized"}), 403
    conn = get_db()
    conn.execute("UPDATE rewards SET image_path = NULL WHERE id = ?", (reward_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route('/api/admin/seed-chores/upload-image', methods=['POST'])
def upload_seed_chore_image():
    if not require_parent():
        return jsonify({"error": "Unauthorized"}), 403
    if 'image' not in request.files:
        return jsonify({"error": "No file"}), 400
    file = request.files['image']
    if file.filename == '':
        return jsonify({"error": "Empty filename"}), 400
    
    import os
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ['.jpg', '.jpeg', '.png', '.gif', '.webp'] or not (file.content_type and file.content_type.startswith('image/')):
        return jsonify({"error": "Invalid format. Supported: JPG, PNG, WEBP, GIF"}), 400
        
    import uuid
    from werkzeug.utils import secure_filename
    filename = f"seed_{uuid.uuid4().hex}_{secure_filename(file.filename)}"
    upload_dir = os.path.join('static', 'chore_images')
    os.makedirs(upload_dir, exist_ok=True)
    path = os.path.join(upload_dir, filename)
    web_path = f"chore_images/{filename}"
    file.save(path)
    return jsonify({"success": True, "image_path": web_path})

@app.route('/api/rewards', methods=['GET'])
def get_child_rewards():
    # Requires child_id query param
    child_id = request.args.get("child_id", type=int)
    if not child_id:
        return jsonify({"success": False, "message": "Child ID required"}), 400
    
    conn = get_db()
    # Get child's current points
    child = conn.execute("SELECT bankable_balance FROM children WHERE id = ?", (child_id,)).fetchone()
    if not child:
        conn.close()
        return jsonify({"success": False, "message": "Child not found"}), 404
    
    # Fetch rewards: either for this specific child OR for everyone (child_id IS NULL)
    rows = conn.execute("""
        SELECT id, name, description, points_cost, image_path
        FROM rewards
        WHERE active = 1 AND (child_id IS NULL OR child_id = ?)
        ORDER BY points_cost ASC
    """, (child_id,)).fetchall()
    conn.close()
    
    return jsonify({
        "success": True,
        "rewards": [dict(r) for r in rows],
        "current_points": child["bankable_balance"]
    })

@app.route('/api/rewards/redeem', methods=['POST'])
def redeem_reward():
    data = request.json
    child_id = data.get("child_id")
    reward_id = data.get("reward_id")
    
    if not child_id or not reward_id:
        return jsonify({"success": False, "message": "Missing child_id or reward_id"}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("BEGIN IMMEDIATE")
    try:
        # Get child and reward
        child = cursor.execute("SELECT name, bankable_balance, unlocked_assets FROM children WHERE id = ?", (child_id,)).fetchone()
        reward = cursor.execute("SELECT name, points_cost FROM rewards WHERE id = ? AND active = 1", (reward_id,)).fetchone()
        
        if not child or not reward:
            conn.rollback()
            return jsonify({"success": False, "message": "Child or reward not found"}), 404
        
        if child["bankable_balance"] < reward["points_cost"]:
            conn.rollback()
            return jsonify({"success": False, "message": f"Need {reward['points_cost']} points, you have {child['bankable_balance']}"}), 400
        
        # Deduct points
        new_balance = child["bankable_balance"] - reward["points_cost"]
        cursor.execute("UPDATE children SET bankable_balance = ? WHERE id = ?", (new_balance, child_id))
        
        # Add to unlocked_assets
        assets = json.loads(child["unlocked_assets"]) if child["unlocked_assets"] else []
        redeemed_text = f"Redeemed: {reward['name']} (cost {reward['points_cost']} pts)"
        assets.append(redeemed_text)
        cursor.execute("UPDATE children SET unlocked_assets = ? WHERE id = ?", (json.dumps(assets), child_id))
        
        conn.commit()
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        conn.close()
    
    # Broadcast update so dashboard reflects new points
    broadcast_event("chore_update", {"leaderboard": get_leaderboard_payload()})
    
    return jsonify({"success": True, "new_balance": new_balance})


@app.route('/api/child/weekly_progress/<int:child_id>')
def get_weekly_progress(child_id):
    conn = get_db()
    cursor = conn.cursor()
    today = datetime.date.today()
    # Week starts on Sunday
    start_of_week = today - datetime.timedelta(days=(today.weekday() + 1) % 7)
    end_of_week = start_of_week + datetime.timedelta(days=6)
    
    total = cursor.execute("""
        SELECT COUNT(*) FROM chores c
        WHERE c.assigned_child_id = ? OR c.assigned_child_id IS NULL
    """, (child_id,)).fetchone()[0]
    
    completed = cursor.execute("""
        SELECT COUNT(*) FROM chore_history
        WHERE child_id = ? AND completed_date BETWEEN ? AND ?
    """, (child_id, start_of_week.isoformat(), end_of_week.isoformat())).fetchone()[0]
    
    percentage = (completed / total * 100) if total > 0 else 0
    week_key = f"weekly_reward_{child_id}_{start_of_week.isoformat()}"
    claimed = cursor.execute("SELECT value FROM system_config WHERE key = ?", (week_key,)).fetchone()
    conn.close()
    
    return jsonify({
        "percentage": round(percentage),
        "reward_available": percentage >= 80 and not claimed,
        "reward_claimed": claimed is not None
    })

@app.route('/api/child/claim_weekly_reward/<int:child_id>', methods=['POST'])
def claim_weekly_reward(child_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("BEGIN IMMEDIATE")
    try:
        today = datetime.date.today()
        start_of_week = today - datetime.timedelta(days=(today.weekday() + 1) % 7)
        week_key = f"weekly_reward_{child_id}_{start_of_week.isoformat()}"
        
        claimed = cursor.execute("SELECT value FROM system_config WHERE key = ?", (week_key,)).fetchone()
        if claimed:
            conn.rollback()
            return jsonify({"success": False, "message": "Already claimed this week"}), 400
        
        reward = get_random_reward()  # assumes you have this function from reward pool
        child = cursor.execute("SELECT unlocked_assets FROM children WHERE id = ?", (child_id,)).fetchone()
        assets = json.loads(child["unlocked_assets"]) if child["unlocked_assets"] else []
        assets.append(f"Weekly Mystery: {reward}")
        cursor.execute("UPDATE children SET unlocked_assets = ? WHERE id = ?", (json.dumps(assets), child_id))
        cursor.execute("INSERT INTO system_config (key, value) VALUES (?, 'claimed')", (week_key,))
        conn.commit()
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        conn.close()
    
    broadcast_event("chore_update", {"leaderboard": get_leaderboard_payload()})
    return jsonify({"success": True, "reward": reward})


@app.route('/api/admin/google-photos-config', methods=['POST'])
def api_admin_google_photos_config():
    if not require_parent():
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    data = request.json or {}
    url = data.get("google_photos_url", "").strip()
    conn = get_db()
    conn.execute("INSERT OR REPLACE INTO system_config (key, value) VALUES ('google_photos_url', ?)", (url,))
    conn.commit()
    conn.close()
    broadcast_event("admin_config_change", get_leaderboard_payload())
    return jsonify({"success": True})


@app.route('/api/admin/calendar-config', methods=['POST'])
def api_admin_calendar_config():
    """Save Google Calendar iCal URL to database."""
    if not require_parent():
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    data = request.get_json()
    ical_url = data.get('ical_feed_url', '').strip()
    conn = get_db()
    conn.execute("INSERT OR REPLACE INTO system_config (key, value) VALUES ('ical_feed_url', ?)", (ical_url,))
    conn.commit()
    conn.close()
    return jsonify({"status": "ok", "message": "Calendar URL saved"})


@app.route('/api/admin/google-photos/sync', methods=['POST'])
def api_admin_google_photos_sync():
    if not require_parent():
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    data = request.json or {}
    album_url = data.get("album_url", "").strip()
    
    # Fallback: if no album_url in request body, read from saved database config
    if not album_url:
        try:
            conn = get_db()
            row = conn.execute("SELECT value FROM system_config WHERE key = 'google_photos_url'").fetchone()
            conn.close()
            if row and row[0]:
                album_url = row[0].strip()
        except Exception:
            pass
    
    if not album_url:
        return jsonify({"success": False, "message": "No Google Photos album URL configured. Please save one in the Integrations tab first."}), 400
    
    def run_sync():
        import subprocess
        import sys
        script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sync_google_photos.py")
        log_path = get_active_log_dir() / "sync_photos.log"
        try:
            with open(log_path, "a", encoding="utf-8") as lf:
                lf.write(f"\n--- MANUAL PHOTOS SYNC START: {datetime.datetime.now().isoformat()} ---\n")
                lf.flush()
                subprocess.run([sys.executable, script_path, album_url], stdout=lf, stderr=lf, check=True, timeout=300)
            print(f"[+] Google Photos sync completed for: {album_url}")
        except Exception as e:
            print(f"[-] Google Photos sync failed: {e}")
            try:
                with open(log_path, "a", encoding="utf-8") as lf:
                    lf.write(f"[ERROR] Manual sync failed: {e}\n")
            except Exception:
                pass
    
    threading.Thread(target=run_sync, daemon=True).start()
    return jsonify({"success": True, "message": "Google Photos sync started in background. The slideshow will refresh within 1-2 minutes."})


@app.route('/api/admin/calendar/sync', methods=['POST'])
def api_admin_calendar_sync():
    """Force-trigger a background calendar sync from the saved iCal URL."""
    if not require_parent():
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    
    # Read the saved iCal URL from DB (optionally allow override in request body)
    data = request.json or {}
    ical_url = data.get("ical_feed_url", "").strip()
    if not ical_url:
        try:
            conn = get_db()
            row = conn.execute("SELECT value FROM system_config WHERE key = 'ical_feed_url'").fetchone()
            conn.close()
            if row and row[0]:
                ical_url = row[0].strip()
        except Exception:
            pass
    
    if not ical_url:
        return jsonify({"success": False, "message": "No iCal URL configured. Please save one in the Integrations → Google Calendar section first."}), 400
    
    def run_calendar_sync():
        import subprocess
        import sys
        script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sync_calendar.py")
        log_path = get_active_log_dir() / "sync_calendar.log"
        try:
            with open(log_path, "a", encoding="utf-8") as lf:
                lf.write(f"\n--- MANUAL CALENDAR SYNC START: {datetime.datetime.now().isoformat()} ---\n")
                lf.flush()
                subprocess.run([sys.executable, script_path, ical_url], stdout=lf, stderr=lf, check=True, timeout=60)
            print(f"[+] Calendar sync completed for: {ical_url}")
        except Exception as e:
            print(f"[-] Calendar sync failed: {e}")
            try:
                with open(log_path, "a", encoding="utf-8") as lf:
                    lf.write(f"[ERROR] Manual sync failed: {e}\n")
            except Exception:
                pass
    
    threading.Thread(target=run_calendar_sync, daemon=True).start()
    return jsonify({"success": True, "message": "Calendar sync started in background. Events will refresh within 30 seconds."})


@app.route('/api/admin/timezone', methods=['POST'])
def api_admin_timezone():
    if not require_parent():
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    data = request.json or {}
    tz = data.get("timezone", "").strip()
    if not tz:
        return jsonify({"success": False, "message": "Timezone required"}), 400
    conn = get_db()
    conn.execute("INSERT OR REPLACE INTO system_config (key, value) VALUES ('timezone', ?)", (tz,))
    conn.commit()
    conn.close()
    broadcast_event("admin_config_change", get_leaderboard_payload())
    return jsonify({"success": True})

@app.route('/api/admin/quote-settings', methods=['POST'])
def api_admin_quote_settings():
    if not require_parent():
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    data = request.json or {}
    refresh = data.get("quote_refresh", "daily")
    category = data.get("quote_category", "general")
    try:
        conn = get_db()
        conn.execute("INSERT OR REPLACE INTO system_config (key, value) VALUES (?, ?)", ("quote_refresh", refresh))
        conn.execute("INSERT OR REPLACE INTO system_config (key, value) VALUES (?, ?)", ("quote_category", category))
        conn.commit()
        conn.close()
        broadcast_event("admin_config_change", get_leaderboard_payload())
        return jsonify({"success": True})
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/admin/email-config', methods=['GET', 'POST'])
def api_admin_email_config():
    if not require_parent():
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    
    conn = get_db()
    cursor = conn.cursor()
    
    if request.method == 'POST':
        data = request.json or {}
        config_map = {
            'smtp_server': data.get('smtp_server'),
            'smtp_port': data.get('smtp_port'),
            'smtp_username': data.get('smtp_username'),
            'smtp_to_email': data.get('smtp_to_email')
        }
        for key, value in config_map.items():
            if value is not None:
                cursor.execute("INSERT OR REPLACE INTO system_config (key, value) VALUES (?, ?)", (key, str(value)))
        
        password = data.get('smtp_password')
        if password and password != '••••••••':
            enc_pw = encrypt_val(password)
            cursor.execute("INSERT OR REPLACE INTO system_config (key, value) VALUES ('smtp_password', ?)", (enc_pw,))
        
        conn.commit()
        conn.close()
        broadcast_event("admin_config_change", get_leaderboard_payload())
        return jsonify({"success": True})
    
    # GET request
    rows = cursor.execute("SELECT key, value FROM system_config WHERE key LIKE 'smtp_%'").fetchall()
    db_config = {r["key"]: r["value"] for r in rows}
    conn.close()
    
    return jsonify({
        "smtp_server": db_config.get("smtp_server", ""), "smtp_port": db_config.get("smtp_port", "587"),
        "smtp_username": db_config.get("smtp_username", ""), "smtp_password": "••••••••" if db_config.get("smtp_password") else "",
        "smtp_to_email": db_config.get("smtp_to_email", ""),
    })

@app.route('/api/admin/send-test-email', methods=['POST'])
def api_admin_send_test_email():
    if not require_parent():
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    conn = get_db()
    rows = conn.execute("SELECT key, value FROM system_config WHERE key LIKE 'smtp_%'").fetchall()
    config = {r['key']: r['value'] for r in rows}
    conn.close()

    to_email = config.get('smtp_to_email')
    username = config.get('smtp_username')
    password = decrypt_val(config.get('smtp_password', ''))
    server_host = config.get('smtp_server', 'localhost')
    server_port = int(config.get('smtp_port', 587))

    if not to_email or not username or not password or not server_host:
        return jsonify({"success": False, "message": "SMTP settings are incomplete. Please configure them in the Email Setup tab."}), 400

    try:
        import smtplib
        from email.mime.text import MIMEText
        subject = f"Test Email: Family Command Center {APP_VERSION}"
        body = "🎉 Success! Your Family Command Center SMTP email configuration is fully working!"
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = username
        msg['To'] = to_email

        with smtplib.SMTP(server_host, server_port) as server:
            server.starttls()
            server.login(username, password)
            server.send_message(msg)
        return jsonify({"success": True, "message": f"Test email successfully sent to {to_email}!"})
    except Exception as e:
        return jsonify({"success": False, "message": f"SMTP test failed: {str(e)}"}), 500

@app.route('/api/admin/solar/refresh-token', methods=['POST'])
def api_admin_solar_refresh_token():
    if not require_parent():
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    
    def run_fetch():
        import subprocess
        import sys
        script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fetch_enphase_token.py")
        log_path = get_active_log_dir() / "fetch_token.log"
        try:
            with open(log_path, "a", encoding="utf-8") as lf:
                lf.write(f"\n--- MANUAL TOKEN FETCH START: {datetime.datetime.now().isoformat()} ---\n")
                lf.flush()
                subprocess.run([sys.executable, script_path], stdout=lf, stderr=lf, check=True, timeout=300)
            print("[+] Solar token fetch completed successfully.")
        except Exception as e:
            print(f"[-] Solar token fetch failed: {e}")
            try:
                with open(log_path, "a", encoding="utf-8") as lf:
                    lf.write(f"[ERROR] Manual token fetch failed: {e}\n")
            except Exception:
                pass
    
    threading.Thread(target=run_fetch, daemon=True).start()
    return jsonify({"success": True, "message": "Solar token refresh started in background."})

@app.route('/api/admin/backup-database', methods=['POST'])
def api_admin_backup_database():
    if not require_parent():
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    try:
        import shutil
        import datetime
        backup_dir = os.path.abspath("data/backups")
        os.makedirs(backup_dir, exist_ok=True)
        
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(backup_dir, f"database_backup_{timestamp}.db")
        
        shutil.copy2(DB_FILE, backup_path)
        return jsonify({"success": True, "message": f"Database backup successfully saved to data/backups/database_backup_{timestamp}.db!"})
    except Exception as e:
        return jsonify({"success": False, "message": f"Database backup failed: {str(e)}"}), 500

@app.route('/favicon.ico')
def favicon():
    return send_from_directory('static', 'favicon.ico', mimetype='image/vnd.microsoft.icon')


@app.route('/api/version')
def api_version():
    return jsonify({"version": APP_VERSION})


@app.route('/api/health')
def health_check():
    """Health check endpoint: returns database status, last sync times, etc."""
    import os
    import datetime
    from pathlib import Path

    health = {
        "status": "healthy",
        "version": APP_VERSION,
        "timestamp": datetime.datetime.now().isoformat(),
        "database": {"connected": False},
        "sync_times": {},
        "solar_enabled": False,
        "warnings": []
    }

    # 1. Database check
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM children")
        health["database"]["children_count"] = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM chores")
        health["database"]["chores_count"] = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM chore_history")
        health["database"]["chore_history_count"] = cursor.fetchone()[0]
        health["database"]["connected"] = True
        conn.close()
    except Exception as e:
        health["database"]["error"] = str(e)
        health["status"] = "degraded"

    # 2. Sync times from log files (dynamic lookup across standard directories)
    log_dir = get_active_log_dir()

    if log_dir and log_dir.exists():
        sync_files = {
            "calendar": "sync_calendar.log",
            "solar": "sync_solar.log",
            "google_photos": "sync_photos.log",
            "enphase_token": "fetch_token.log"
        }
        for key, filename in sync_files.items():
            log_path = log_dir / filename
            if log_path.exists():
                mtime = os.path.getmtime(log_path)
                health["sync_times"][key] = {
                    "last_run": datetime.datetime.fromtimestamp(mtime).isoformat(),
                    "seconds_ago": int(datetime.datetime.now().timestamp() - mtime)
                }
            else:
                health["sync_times"][key] = None
    else:
        for key in ["calendar", "solar", "google_photos", "enphase_token"]:
            health["sync_times"][key] = None

    # 3. Solar enabled status
    try:
        conn = get_db()
        row = conn.execute("SELECT value FROM system_config WHERE key='solar_enabled'").fetchone()
        health["solar_enabled"] = row and row[0].lower() == 'true'
        conn.close()
    except Exception:
        pass

    # 4. Check for stale syncs (optional warnings)
    thresholds = {
        "calendar": 14400,      # 4 hours
        "solar": 3600,          # 1 hour
        "google_photos": 28800, # 8 hours
        "enphase_token": 86400  # 24 hours
    }
    for key, stale_sec in thresholds.items():
        info = health["sync_times"].get(key)
        if info and info.get("seconds_ago", 0) > stale_sec:
            health["warnings"].append(f"{key} last run {info['seconds_ago']//3600}h ago")
            health["status"] = "degraded"

    return jsonify(health)


@app.route('/api/admin/logs/list', methods=['GET'])
def api_logs_list():
    if not require_parent():
        return jsonify({"error": "Unauthorized"}), 403
    try:
        files = [f for f in os.listdir(LOG_DIR) if f.endswith('.log')]
        return jsonify({"success": True, "files": files})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/admin/logs/view', methods=['GET'])
def api_logs_view():
    if not require_parent():
        return jsonify({"error": "Unauthorized"}), 403
    filename = request.args.get('file', 'server.log')
    lines = request.args.get('lines', 1000, type=int)
    filepath = os.path.join(LOG_DIR, filename)
    if not os.path.exists(filepath):
        return jsonify({"error": "Log file not found"}), 404
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            all_lines = f.readlines()
            last_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines
        return jsonify({"success": True, "content": ''.join(last_lines), "total_lines": len(all_lines)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/admin/logs/download', methods=['GET'])
def api_logs_download():
    from flask import abort, send_file
    if not require_parent():
        return jsonify({"error": "Unauthorized"}), 403
    filename = request.args.get('file', 'server.log')
    filepath = os.path.join(LOG_DIR, filename)
    if not os.path.exists(filepath):
        abort(404)
    return send_file(filepath, as_attachment=True, download_name=filename)

@app.route('/api/admin/logs/clear', methods=['POST'])
def api_logs_clear():
    if not require_parent():
        return jsonify({"error": "Unauthorized"}), 403
    data = request.json
    filename = data.get('file', 'server.log')
    filepath = os.path.join(LOG_DIR, filename)
    if not os.path.exists(filepath):
        return jsonify({"error": "Log file not found"}), 404
    try:
        open(filepath, 'w').close()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    import argparse
    import sys
    
    parser = argparse.ArgumentParser(description="Family Command Center")
    parser.add_argument('--task', choices=['sync_calendar', 'sync_solar', 'sync_photos', 'sync_google_photos', 'fetch_token', 'web'], default='web', help="Task to run")
    args = parser.parse_args()
    
    init_db()
    
    if args.task == 'web':
        local_ip = get_local_ip()
        
        # Look for automated mkcert cert.pem or existing localhost.pem certificates
        cert_options = [('cert.pem', 'key.pem'), ('localhost.pem', 'localhost-key.pem')]
        cert_file = None
        key_file = None
        
        for c_file, k_file in cert_options:
            if os.path.exists(c_file) and os.path.exists(k_file):
                cert_file = c_file
                key_file = k_file
                break
                
        if cert_file and key_file:
            print(f"[*] Family Command Center {APP_VERSION} Blueprint Engine booting on secure port 8080 (HTTPS)...")
            print(f"[*] Local IP Address: https://{local_ip}:8080")
            app.run(
                host="0.0.0.0",
                port=8080,
                ssl_context=(cert_file, key_file),
                debug=False,
                threaded=True
            )
        else:
            print(f"[*] Family Command Center {APP_VERSION} Blueprint Engine booting on port 8080 (HTTP)...")
            print(f"[*] Local IP Address: http://{local_ip}:8080")
            print(f"[!] NOTE: To enable secure HTTPS (required for voice/mic features), run: .\\setup_https.ps1 (Windows) or sudo bash setup_https.sh (Mac/Linux)")
            app.run(host="0.0.0.0", port=8080, debug=False)
    else:
        # Load configuration directly from the local SQLite database
        # This removes the need for an external config.json while preserving your UI settings!
        conn = get_db()
        try:
            rows = conn.execute("SELECT * FROM system_config").fetchall()
            db_config = {r["key"]: r["value"] for r in rows}
        except Exception:
            db_config = {}
        finally:
            conn.close()
            
        def run_task_safely(task_name, script_name, log_name, arg=None):
            import sys
            import os
            import datetime
            import importlib
            import subprocess
            
            log_dir = get_active_log_dir()
            log_path = log_dir / log_name
            
            try:
                with open(log_path, "a", encoding="utf-8") as lf:
                    lf.write(f"\n--- SCHEDULED {task_name.upper()} START: {datetime.datetime.now().isoformat()} ---\n")
                    lf.flush()
            except Exception:
                pass

            if getattr(sys, 'frozen', False):
                # Frozen binary context: run in-process to avoid missing python interpreter issues
                if arg:
                    sys.argv = [sys.argv[0], arg]
                try:
                    module_name = script_name.replace(".py", "")
                    module = importlib.import_module(module_name)
                    
                    with open(log_path, "a", encoding="utf-8") as lf:
                        old_stdout = sys.stdout
                        old_stderr = sys.stderr
                        sys.stdout = lf
                        sys.stderr = lf
                        try:
                            if task_name == "sync_calendar" and hasattr(module, 'main'):
                                module.main()
                            elif task_name == "sync_solar" and hasattr(module, 'fetch_local_solar_data'):
                                module.fetch_local_solar_data()
                            elif task_name == "sync_photos" and hasattr(module, 'main'):
                                module.main()
                            elif task_name == "sync_google_photos" and hasattr(module, 'sync_album'):
                                module.sync_album(arg)
                            elif task_name == "fetch_token" and hasattr(module, 'harvest_token'):
                                module.harvest_token()
                            else:
                                if hasattr(module, 'main'):
                                    module.main()
                        finally:
                            sys.stdout = old_stdout
                            sys.stderr = old_stderr
                    print(f"[+] {task_name} completed successfully (in-process).")
                except Exception as e:
                    print(f"[-] {task_name} failed (in-process): {e}")
                    try:
                        with open(log_path, "a", encoding="utf-8") as lf:
                            lf.write(f"[ERROR] In-process execution failed: {e}\n")
                    except Exception:
                        pass
            else:
                # Source code context: run via safe subprocess execution
                script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), script_name)
                cmd = [sys.executable, script_path]
                if arg:
                    cmd.append(arg)
                try:
                    with open(log_path, "a", encoding="utf-8") as lf:
                        subprocess.run(cmd, stdout=lf, stderr=lf, check=True, timeout=300)
                    print(f"[+] {task_name} completed successfully.")
                except Exception as e:
                    print(f"[-] {task_name} failed: {e}")

        if args.task == 'sync_calendar':
            ical_url = db_config.get("ical_feed_url")
            if ical_url:
                run_task_safely("sync_calendar", "sync_calendar.py", "sync_calendar.log", ical_url)
            else:
                print("[-] Calendar sync skipped: No iCal URL configured.")
            
        elif args.task == 'sync_solar':
            if db_config.get("solar_enabled") == "true":
                run_task_safely("sync_solar", "sync_solar.py", "sync_solar.log")
            else:
                print("[-] Solar sync skipped: Solar not enabled.")
                
        elif args.task == 'sync_photos':
            run_task_safely("sync_photos", "sync_photos.py", "sync_photos.log")

        elif args.task == 'sync_google_photos':
            album_url = db_config.get("google_photos_url")
            if album_url:
                run_task_safely("sync_google_photos", "sync_google_photos.py", "sync_photos.log", album_url)
            else:
                print("[-] Google Photos sync skipped: No Google Photos album URL configured.")
                
        elif args.task == 'fetch_token':
            run_task_safely("fetch_token", "fetch_enphase_token.py", "fetch_token.log")
