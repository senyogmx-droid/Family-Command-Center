import os
import json
import sqlite3
import hashlib
import datetime
import queue
import math
import random
from flask import Flask, jsonify, request, Response, send_from_directory, session, redirect, url_for

app = Flask(__name__, static_folder="static", static_url_path="")
app.secret_key = "family_command_center_v2_secret_key"

# Disable caching for static/dynamic files to prevent dashboard/kiosk cache issues
@app.after_request
def add_header(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

DB_FILE = "database.db"
XOR_KEY = "EnphaseDashboardSecretKey123"
APP_VERSION = "v3.5.4"

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

def encrypt_val(plain_text, key=XOR_KEY):
    if not plain_text:
        return ""
    # Symmetric XOR cipher
    key_len = len(key)
    xor_bytes = bytearray(ord(plain_text[i]) ^ ord(key[i % key_len]) for i in range(len(plain_text)))
    import base64
    return base64.b64encode(xor_bytes).decode('utf-8')

def decrypt_val(cipher_text, key=XOR_KEY):
    if not cipher_text:
        return ""
    import base64
    try:
        xor_bytes = base64.b64decode(cipher_text.encode('utf-8'))
        key_len = len(key)
        plain_bytes = bytearray(xor_bytes[i] ^ ord(key[i % key_len]) for i in range(len(xor_bytes)))
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

    # 9. Point-based Rewards Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS rewards (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        description TEXT,
        points_cost INTEGER NOT NULL,
        child_id INTEGER,  -- NULL = available to all children, otherwise specific child
        active INTEGER DEFAULT 1,
        created_at TEXT
    )""")
    
    # Seeding parent user if none exist
    cursor.execute("SELECT COUNT(*) FROM users")
    if cursor.fetchone()[0] == 0:
        default_hash = hashlib.sha256("admin".encode('utf-8')).hexdigest()
        cursor.execute("INSERT INTO users (username, password_hash) VALUES ('parent', ?)", (default_hash,))
        
    # --- SELF-HEALING DATABASE MIGRATIONS (V2 to V3.5.3) ---
    try:
        # 1. Audit and patch 'users' table (Parent/Admin configurations only)
        cursor.execute("PRAGMA table_info(users)")
        users_cols = [row[1] for row in cursor.fetchall()]
        users_migrations = [
            ("main_page_privacy", "INTEGER DEFAULT 0")
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

        # 2.8 Audit and patch 'rewards' table
        cursor.execute("PRAGMA table_info(rewards)")
        rewards_cols = [row[1] for row in cursor.fetchall()]
        if rewards_cols:
            if "description" not in rewards_cols:
                cursor.execute("ALTER TABLE rewards ADD COLUMN description TEXT")
            if "active" not in rewards_cols:
                cursor.execute("ALTER TABLE rewards ADD COLUMN active INTEGER DEFAULT 1")
            
        # 3. Seed default system configs if missing
        cursor.execute("SELECT COUNT(*) FROM system_config WHERE key = 'photo_source_mode'")
        if cursor.fetchone()[0] == 0:
            cursor.execute("INSERT INTO system_config (key, value) VALUES ('photo_source_mode', 'default')")
                
    except Exception as e:
        print(f"[!] Migration Error: {e}")
        
    conn.commit()
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

# -------------------------------------------------------------
# AUTHENTICATION ROUTING
# -------------------------------------------------------------
@app.route('/api/auth/login', methods=['POST'])
def api_login():
    data = request.json or {}
    password = data.get("password", "")
    pw_hash = hashlib.sha256(password.encode('utf-8')).hexdigest()
    
    conn = get_db()
    user = conn.execute("SELECT * FROM users").fetchone()
    conn.close()
    
    if user and user["password_hash"] == pw_hash:
        session["parent_auth"] = True
        return jsonify({"success": True})
    return jsonify({"success": False, "message": "Invalid password"}), 401

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
    
    chore = cursor.execute("SELECT * FROM chores WHERE id = ?", (chore_id,)).fetchone()
    child = cursor.execute("SELECT * FROM children WHERE id = ?", (child_id,)).fetchone()
    
    if not chore or not child:
        conn.close()
        return jsonify({"success": False, "message": "Chore or child not found"}), 404
        
    is_teen = child["age"] >= 13
    if is_teen and chore["is_enrichment"] == 0 and date_context != "yesterday":
        # Teenager chores require review (except enrichments that might have separate submit)
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
            conn.close()
            return jsonify({"success": False, "message": "Chore already completed yesterday."}), 400
            
        # Check if already submitted in submissions (excluding rejected)
        sub_record = cursor.execute(
            "SELECT * FROM chore_submissions WHERE chore_id = ? AND child_id = ? AND submitted_date = ? AND status != 'rejected'",
            (chore_id, child_id, target_date_str)
        ).fetchone()
        if sub_record:
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

    conn.close()
    
    # Leaderboard broadcast
    leaderboard_payload = get_leaderboard_payload()
    broadcast_event("chore_update", {
        "chore_id": chore_id,
        "completed": completed,
        "leaderboard": leaderboard_payload
    })
    
    return jsonify({"success": True, "completed": completed, "leaderboard": leaderboard_payload})

# Helper to load leaderboard metrics
def get_leaderboard_payload():
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
# YESTERDAY GRACE PERIOD CHORE SUBMISSION API
# -------------------------------------------------------------
import smtplib
from email.mime.text import MIMEText
import threading

def trigger_parent_email_alert(child_name, chore_name, is_grace_period=True):
    """Fires an asynchronous email notification to the parent if system config is setup"""
    conn = None
    try:
        # Check database system_config table for email activation toggles
        conn = get_db()
        enabled = conn.execute("SELECT value FROM system_config WHERE key = 'email_alerts_enabled'").fetchone()
        parent_email = conn.execute("SELECT value FROM system_config WHERE key = 'parent_notification_email'").fetchone()
        conn.close()
        conn = None
        
        if not enabled or enabled[0] != 'true' or not parent_email:
            return # Silent exit if email notifications are not configured
            
        if is_grace_period:
            body = f"⏳ Grace Period Notification: {child_name} has submitted a late completion request for yesterday's chore: '{chore_name}'. Please review this request on your Admin Panel Dashboard."
            subject = f"⏳ Pending Late Chore Action - {child_name}"
        else:
            body = f"🔔 Verification Approval Needed: {child_name} has submitted a task verification request for: '{chore_name}'. Please review the photo/audio/notes submission on your Admin Panel Dashboard."
            subject = f"🔔 Task Verification Pending - {child_name}"
            
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = "dashboard@familycommand.local"
        msg['To'] = parent_email[0]
        
        # Connect to local or specified SMTP relay pipeline
        with smtplib.SMTP('localhost', 1025) as server:  # Adapts to your active mail relay port
            server.send_message(msg)
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
    data = request.json or {}
    new_password = data.get("new_password", "")
    if not new_password or len(new_password.strip()) < 4:
        return jsonify({"success": False, "message": "Password must be >= 4 chars"}), 400
        
    pw_hash = hashlib.sha256(new_password.encode('utf-8')).hexdigest()
    conn = get_db()
    conn.execute("UPDATE users SET password_hash = ?", (pw_hash,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route('/api/admin/chores', methods=['POST'])
def admin_add_chore():
    if not require_parent():
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    data = request.json or {}
    name = data.get("name")
    points = data.get("points")
    frequency = data.get("frequency", "daily")
    assigned_child_id = data.get("assigned_child_id")
    time_block = data.get("time_block", "morning")
    is_enrichment = data.get("is_enrichment", 0)
    validation_type = data.get("validation_type", "simple")
    active_days = data.get("active_days", "all")
    
    if not name or not points:
        return jsonify({"success": False, "message": "Name and points are required"}), 400
        
    conn = get_db()
    conn.execute("""
        INSERT INTO chores (name, points, frequency, assigned_child_id, time_block, is_enrichment, validation_type, active_days)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (name, int(points), frequency, assigned_child_id, time_block, int(is_enrichment), validation_type, active_days))
    conn.commit()
    conn.close()
    
    broadcast_event("admin_config_change", {})
    return jsonify({"success": True})

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
    solar_file = 'solar.json'
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
        "smtp_from_email": db_config.get("smtp_from_email", ""),
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
    smtp_from_email = data.get("smtp_from_email", "")
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
        parent_hash = hashlib.sha256(parent_password.encode('utf-8')).hexdigest()
    else:
        parent_hash = hashlib.sha256("admin".encode('utf-8')).hexdigest()
    cursor.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", (parent_username, parent_hash))
        
    # 2. Update system configs
    cursor.execute("INSERT OR REPLACE INTO system_config (key, value) VALUES ('admin_configured', 'true')")
    cursor.execute("INSERT OR REPLACE INTO system_config (key, value) VALUES ('smtp_server', ?)", (smtp_server,))
    cursor.execute("INSERT OR REPLACE INTO system_config (key, value) VALUES ('smtp_port', ?)", (smtp_port,))
    cursor.execute("INSERT OR REPLACE INTO system_config (key, value) VALUES ('smtp_username', ?)", (smtp_username,))
    
    # Sentinel preservation checks
    if smtp_password and smtp_password != "••••••••":
        enc_smtp = encrypt_val(smtp_password)
        cursor.execute("INSERT OR REPLACE INTO system_config (key, value) VALUES ('smtp_password', ?)", (enc_smtp,))
        
    cursor.execute("INSERT OR REPLACE INTO system_config (key, value) VALUES ('smtp_from_email', ?)", (smtp_from_email,))
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
                    INSERT INTO chores (name, points, frequency, assigned_child_id, time_block, active_days)
                    VALUES (?, ?, 'daily', ?, ?, 'all')
                """, (tc["name"], int(tc["points"]), child_id, tc.get("time_block", "morning")))
            
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
                INSERT INTO chores (name, points, frequency, assigned_child_id, time_block, active_days)
                VALUES (?, ?, 'daily', ?, ?, 'all')
            """, (tc["name"], int(tc["points"]), child_id, tc.get("time_block", "morning")))
        
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({"success": False, "message": "Child name already exists"}), 400
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
    try:
        cursor = conn.cursor()
        
        # Check if name is taken by another child
        dup = cursor.execute("SELECT * FROM children WHERE name = ? AND id != ?", (name, child_id)).fetchone()
        if dup:
            return jsonify({"success": False, "message": "Name is already in use"}), 400
            
        cursor.execute("""
            UPDATE children 
            SET name = ?, age = ?, theme = ?, font = ?, points = ?, bankable_balance = ?, vault_keys_available = ?, avatar_path = ?, profile_photo_path = ?
            WHERE id = ?
        """, (name, age, theme, font, points, points, keys, avatar_path, profile_photo_path, child_id))
        
        conn.commit()
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
        
    data = request.json or {}
    child_id = data.get("child_id")
    note = data.get("note", "").strip()
    deduction_points = int(data.get("deduction_points", 5))
    
    if not child_id:
        return jsonify({"success": False, "message": "Child ID is required"}), 400
    if not note:
        return jsonify({"success": False, "message": "Note/reason is required"}), 400
        
    import datetime
    created_at = datetime.datetime.now().isoformat()
    
    conn = get_db()
    try:
        cursor = conn.cursor()
        
        # Insert habit reminder card
        cursor.execute("""
            INSERT INTO habit_reminders (child_id, note, deduction_points, refunded_points, status, created_at)
            VALUES (?, ?, ?, 0, 'active', ?)
        """, (child_id, note, deduction_points, created_at))
        
        # Deduct points from child (points and bankable_balance clamped at 0)
        cursor.execute("""
            UPDATE children 
            SET points = MAX(0, points - ?), bankable_balance = MAX(0, bankable_balance - ?)
            WHERE id = ?
        """, (deduction_points, deduction_points, child_id))
        
        conn.commit()
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
    try:
        cursor = conn.cursor()
        
        # Fetch the active reminder details
        reminder = cursor.execute("SELECT * FROM habit_reminders WHERE id = ? AND status = 'active'", (reminder_id,)).fetchone()
        if not reminder:
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
    try:
        child = cursor.execute("SELECT name, unlocked_assets FROM children WHERE id = ?", (child_id,)).fetchone()
        if not child:
            return jsonify({"success": False, "message": "Child profile not found"}), 404
            
        unlocked_list = json.loads(child["unlocked_assets"] or "[]")
        if asset in unlocked_list:
            unlocked_list.remove(asset)
        else:
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
    if ext not in ['.jpg', '.jpeg', '.png', '.gif', '.webp']:
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
        if ext in allowed_extensions:
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
    tier = data.get("tier") # bronze, silver, gold
    
    if not child_id or not tier:
        return jsonify({"success": False, "message": "Missing arguments"}), 400
        
    cost_map = {"bronze": 1, "silver": 2, "gold": 3}
    cost = cost_map.get(tier.lower(), 99)
    
    conn = get_db()
    cursor = conn.cursor()
    child = cursor.execute("SELECT * FROM children WHERE id = ?", (child_id,)).fetchone()
    
    if not child:
        conn.close()
        return jsonify({"success": False, "message": "Child profile not found"}), 404
        
    keys_avail = child["vault_keys_available"]
    if keys_avail < cost:
        conn.close()
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
    
    chore = cursor.execute("SELECT name, points FROM chores WHERE id = ?", (chore_id,)).fetchone()
    child = cursor.execute("SELECT name FROM children WHERE id = ?", (child_id,)).fetchone()
    
    if not chore or not child:
        conn.close()
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
            if ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']:
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
    data = request.json or {}
    # Extract structural tier attributes to translate key mismatches smoothly
    chest_type = data.get("chestType") or data.get("tier", "bronze")
    return redirect(url_for('api_children_vault_unlock'), code=307)

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
        conn.close()
        return jsonify({"success": False, "message": "Master chore tracking link missing"}), 404
        
    child_id = assigned_child_id or chore['assigned_child_id']
    if not child_id:
        conn.close()
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
            conn.close()
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
    conn.close()
    
    # Broadcast configuration payload updates to instantly clear checkboxes on all kiosk screens
    broadcast_event("admin_config_change", get_leaderboard_payload())
    return jsonify({"success": True})

# -------------------------------------------------------------
# MULTI-SCREEN BASE ROUTE HANDLERS
# -------------------------------------------------------------
@app.route('/')
def route_dashboard():
    if not is_system_initialized():
        return redirect('/welcome')
    return send_from_directory("static", "index.html")

@app.route('/admin')
def route_admin():
    if not is_system_initialized():
        return redirect('/welcome')
    return send_from_directory("static", "admin.html")

@app.route('/performance')
def route_performance():
    if not is_system_initialized():
        return redirect('/welcome')
    return send_from_directory("static", "performance.html")

@app.route('/child')
def route_child():
    if not is_system_initialized():
        return redirect('/welcome')
    return send_from_directory("static", "chores_summary.html")

@app.route('/welcome')
def route_welcome():
    if is_system_initialized() and not require_parent():
        return redirect('/')
    return send_from_directory("templates", "welcome.html")

@app.route('/child/<name>')
def route_child_legacy(name):
    conn = get_db()
    child = conn.execute("SELECT name FROM children WHERE LOWER(name) = ? AND status = 'active'", (name.lower(),)).fetchone()
    conn.close()
    if child:
        return send_from_directory("static", "child.html")
    return "Profile not found", 404

@app.route('/<name>')
def route_child_direct(name):
    conn = get_db()
    child = conn.execute("SELECT name FROM children WHERE LOWER(name) = ? AND status = 'active'", (name.lower(),)).fetchone()
    conn.close()
    if child:
        return send_from_directory("static", "child.html")
    # Redirect static asset files cleanly
    static_file_path = os.path.join("static", name)
    if os.path.exists(static_file_path) and os.path.isfile(static_file_path):
        return send_from_directory("static", name)
    return "Profile not found", 404

@app.route('/download/apk')
def download_apk():
    apk_dir = os.path.join("static", "apps")
    apk_filename = "FamilyDashboard.apk"
    if not os.path.exists(os.path.join(apk_dir, apk_filename)):
        # Make a mock empty file if it doesn't exist for direct endpoints
        os.makedirs(apk_dir, exist_ok=True)
        with open(os.path.join(apk_dir, apk_filename), "wb") as f:
            f.write(b"mock_apk_content")
    return send_from_directory(apk_dir, apk_filename, as_attachment=True)

@app.route('/photos/<path:filename>')
def serve_photos(filename):
    return send_from_directory("photos", filename)

@app.route('/<path:path>')
def route_static(path):
    return send_from_directory("static", path)

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
    conn.execute(
        "INSERT INTO rewards (name, description, points_cost, child_id, created_at) VALUES (?, ?, ?, ?, ?)",
        (name, description, points_cost, child_id, datetime.datetime.now().isoformat())
    )
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route('/api/admin/rewards/<int:reward_id>', methods=['DELETE'])
def admin_delete_reward(reward_id):
    if not require_parent():
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    conn = get_db()
    conn.execute("DELETE FROM rewards WHERE id = ?", (reward_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

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
        SELECT id, name, description, points_cost
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
    
    # Get child and reward
    child = cursor.execute("SELECT name, bankable_balance, unlocked_assets FROM children WHERE id = ?", (child_id,)).fetchone()
    reward = cursor.execute("SELECT name, points_cost FROM rewards WHERE id = ? AND active = 1", (reward_id,)).fetchone()
    
    if not child or not reward:
        conn.close()
        return jsonify({"success": False, "message": "Child or reward not found"}), 404
    
    if child["bankable_balance"] < reward["points_cost"]:
        conn.close()
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
    today = datetime.date.today()
    start_of_week = today - datetime.timedelta(days=(today.weekday() + 1) % 7)
    week_key = f"weekly_reward_{child_id}_{start_of_week.isoformat()}"
    
    claimed = cursor.execute("SELECT value FROM system_config WHERE key = ?", (week_key,)).fetchone()
    if claimed:
        conn.close()
        return jsonify({"success": False, "message": "Already claimed this week"}), 400
    
    reward = get_random_reward()  # assumes you have this function from reward pool
    child = cursor.execute("SELECT unlocked_assets FROM children WHERE id = ?", (child_id,)).fetchone()
    assets = json.loads(child["unlocked_assets"]) if child["unlocked_assets"] else []
    assets.append(f"Weekly Mystery: {reward}")
    cursor.execute("UPDATE children SET unlocked_assets = ? WHERE id = ?", (json.dumps(assets), child_id))
    cursor.execute("INSERT INTO system_config (key, value) VALUES (?, 'claimed')", (week_key,))
    conn.commit()
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

@app.route('/api/admin/google-photos/sync', methods=['POST'])
def api_admin_google_photos_sync():
    if not require_parent():
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    data = request.json or {}
    album_url = data.get("album_url", "").strip()
    if not album_url:
        return jsonify({"success": False, "message": "Album URL required"}), 400
    
    def run_sync():
        import subprocess
        import sys
        script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sync_google_photos.py")
        try:
            subprocess.run([sys.executable, script_path, album_url], check=True, timeout=300)
            print(f"[+] Google Photos sync completed for: {album_url}")
        except Exception as e:
            print(f"[-] Google Photos sync failed: {e}")
    
    threading.Thread(target=run_sync, daemon=True).start()
    return jsonify({"success": True, "message": "Sync started in background."})


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


@app.route('/favicon.ico')
def favicon():
    return send_from_directory('static', 'favicon.ico', mimetype='image/vnd.microsoft.icon')


@app.route('/api/version')
def api_version():
    return jsonify({"version": APP_VERSION})


if __name__ == '__main__':
    init_db()
    print(f"[*] Family Command Center {APP_VERSION} Blueprint Engine booting on port 8080...")
    app.run(host="0.0.0.0", port=8080, debug=False)
