# 🌌 Family Command Center & Chore Gamification Engine (v2.4 Blueprint)

Welcome to the **Family Command Center**, a visually stunning, multi-device smart home kiosk and gamified household productivity engine. Built to run on a local home server (such as a Raspberry Pi, mini PC, or local computer), it acts as the centralized nervous system for your family—bringing calendar schedules, live home energy telemetry, weather forecast systems, parent-audited children's task lists, and high-performance interactive characters into a unified, delightful experience.

---

## 🎨 System Core Philosophy
Modern smart home screens are often cold, generic, or passive. The **Family Command Center** turns household management into an engaging, responsive, and delightful gamified experience:
* **For Parents**: Simplifies chore tracking with zero-friction automated workflows, a robust audit player for children's verification submissions, penalty/refund adjusters, and real-time custom spot reinforcement.
* **For Kids**: Turns daily checklists into interactive quests. Children earn spendable points, gain **Lifetime XP** to reach higher Levels, watch their custom reactive avatars respond to their gestures, and review their accomplishments on beautiful animated graphs.

---

## 🚀 Key Feature Directory

### 1. 🖥️ The Main Family Kiosk (`index.html`)
The default "wall-mounted kiosk screen" acts as the family's shared information hub:
* **Double-Buffered V6 Slideshow Engine**: Features a GPU-optimized, memory-flat slideshow. It automatically scans custom photos, groups them into beautiful crop-free collages (Landscape Stacks, Duo Portraits, Split-3, Grid-4, or Polaroids), and generates soft blurred background drop-shadow backdrops.
* **3-Column Enphase Solar Telemetry Flow**: Houses real-time home energy metrics, dynamically color-cycling between Solar production (Green), Home draw (Orange), and Net Grid flow (Cyan for grid exporting / Crimson for grid importing).
* **Family Schedule Timeline**: A rolling 2-week calendar grid showing family appointments, colored indicators, and high-contrast timezone-corrected detail panels.
* **Open-Meteo Weather Tracker**: Leverages 3D vector-animated SVGs displaying local weather physics (spinning sun rays, bouncing clouds, rapid rain falling keyframes).
* **Live Leaderboard & Star of the Day**: Displays a dynamic points ranking that updates in real-time when chores are completed.

### 2. 🦖 Gamified Kids' Portal (`child.html`)
A personalized checklist dashboard tailored to each child (Axel, Cayden, Noelle) supporting custom interactive skins:
* **Personalized Themes**: 
  * **Axel (Dinosaur 🦕)**: Playful prehistoric terrain with centering headers.
  * **Cayden (Gamer 🎮)**: Flashing retro-arcade pixel elements.
  * **Noelle (Black Barbie Princess 👑)**: Elegant Satisfy cursive headers, Comfortaa rounded body layouts, soft glowing royal-purple/lavender gradients, and a beautiful custom-styled Black Princess avatar.
  * **Cyber-Mecha (🤖)**: High-tech reactor icons, hazard safety stripes, and cyber-cyan layouts.
* **Gaze-Tracking Avatars**: Highly detailed theme characters that interactively shift their eyes and head depending on which chores card or chart the child hovers over.
* **Automatic Yesterday Chore Auditing**: Clicking yesterday's incomplete items automatically packages a parent review request with zero manual typing, locking the checkmark with an active spinning circular loader during transmission.
* **Voice Accomplishments Feedback (TTS)**: Leverages custom speech profiles per child, congratulating kids when tasks are checked off.
* **Animated Graph Accomplishments**: Displays custom-themed bar charts of weekly, monthly, and yearly points history. Hovering over columns plays micro-scale physics, displaying floating theme emojis and points badges.

### 3. 🛡️ Parent Administration Portal (`admin.html`)
A secure administrative control center accessible via a custom passcode lock:
* **Evidence Audit player**: A media player enabling parents to review chore verification files (including multi-clip audio files and photos) before deciding to **Approve** (credits points and levels up the child), **Deny**, or **Request Revision** (flashes an amber feedback card directly on the child's screen).
* **Corrective Habit Penalty Launcher**: Parents can log rule violations, upload warning photos, write a note, and deduct points. Includes an **interactive partial-refund slider (0% to 100%)** allowing parents to instantly refund deducted points when the child corrects their behavior.
* **Spontaneous Spotlight Launcher**: Parents can award spontaneous surprise points (+2 to +5) using custom titles (e.g. *Mom*, *Dad*, *Grandma*). Submitting broadcasts an SSE alert that instantly interrupts the child's screen with high-contrast glowing banners and animated sparkles.
* **Calendar Insertion Portal**: Quick-add event sidebar that writes events directly to the shared local schedule JSON cache.

### 4. ⚙️ Automation & Backend Engine (`server.py`)
* **Real-time Server-Sent Events (SSE)**: Broadcasts state changes instantly. Whenever a chore is completed, a level is achieved, or a config changes, all screens throughout the house refresh in real-time.
* **Multi-Directional Email Alert Engine**: Runs a background daemon thread that sends automated HTML email alerts to parents (when chores require review) and to kids (notifying them of parental audit results).
* **Storage Pruning Sweeper**: Reviews media storage folders every 24 hours, automatically compressing files older than 90 days, and deleting physical media older than 180 days while keeping database transaction ledgers intact.

---

## 📁 System Architecture & Directory Layout

```text
Family dashboard project/
│
├── server.py                 # Core Python Flask server (DB models, SSE events, SMTP mailing)
├── database.db               # SQLite database (Users, Profiles, History, Configs)
│
├── sync_calendar.py          # iCal Google Calendar synchronization utility
├── sync_google_photos.py     # Shared Google Photos album synchronization utility
├── sync_solar.py             # Local Enphase Gateway Envoy parser
│
├── calendar.json             # Cached rolling calendar events
├── photos.json               # Cached slideshow image URLs
├── solar.json                # Cached home solar gateway readings
│
├── static/                   # Kiosk Web assets
│   ├── index.html            # Main Family Kiosk Dashboard
│   ├── child.html            # Interactive Child gamified checklists page
│   ├── chores_summary.html   # Glassmorphic 3-column kid checklist entry portal
│   ├── admin.html            # Parent admin portal & review player
│   ├── app.js                # Core JS (V6 Slideshow, Weather, SSE listeners, Solar flow)
│   ├── style.css             # Main stylesheet (Glassmorphic cards, 3D weather, energy grid)
│   ├── themes.css            # Kids' theme skins (Dinosaur, Gamer, Princess, Mecha, standard)
│   └── media/                # Storage folder for uploaded child audio and photo evidence
│
├── .venv/                    # Python virtual environment (Self-contained execution stack)
└── README.md                 # This system guide
```

---

## 🚀 How to Launch the Application

### 1. Python Environment Setup
The server runs securely in a self-contained local virtual environment. Start by aligning all required libraries:
```powershell
# 1. Activate the virtual environment
.venv\Scripts\activate

# 2. Run the server using the local virtual environment environment
.venv\Scripts\python.exe server.py
```

### 2. Connect to the Command Center
Once launched, the server runs on standard local HTTP port **`8080`**:
* **Main Kiosk screen**: [http://localhost:8080/](http://localhost:8080/)
* **Kids' Portal Portal**: [http://192.168.1.107:8080/static/chores_summary.html](http://192.168.1.107:8080/static/chores_summary.html)
* **Parent Cockpit**: [http://localhost:8080/admin](http://localhost:8080/admin) (Default secure passcode: `admin`)

---

## 🔒 Security & Data Integrity
* **Hashed Credentials**: Administrative login profiles utilize standard SHA-256 password hashing.
* **Local Isolation**: All children's point tallies, uploaded review files, and history records remain hosted entirely on your local machine—zero cloud dependency.
* **Non-Destructive Database Migrations**: The database engine performs self-check scans on start, seamlessly creating tables and appending schemas without ever touching or resetting your active points historical database ledger.