## 📥 Download

Go to the **Releases** section (right sidebar) and download `FamilyCommandCenter-windows.exe`.  
Double‑click the file, then open your browser to `http://localhost:8080`.

# Family-Command-Center
# 🏠 Family Command Center

A complete, self‑hosted household management dashboard – chore tracking, rewards, calendar, solar telemetry, weather, and more. Designed to run on a home server (or any Windows PC) and be viewed on any device in your home network.

## ✨ Key Features

### 👨‍👩‍👧‍👦 For Parents
- **Chore manager** – assign tasks, set points, choose time blocks (morning/afternoon/evening).
- **Audit queue** – approve or request revisions for completed chores (with photo/audio proof).
- **Reward store** – create custom point‑based rewards (e.g., “30 min extra screen time”).
- **Habit reminders** – issue point deductions and refund them when behaviour improves.
- **Spotlight bonus** – send spontaneous points with a celebratory pop‑up.
- **Calendar** – add/edit events with time, colour‑coded categories (sport, school, doctor, family).
- **Photo slideshow** – upload your own photos or sync a Google Photos shared album.
- **Live solar telemetry** – Enphase gateway integration (or show an inspirational quote).
- **Weather station** – automatically fetches current conditions and forecast.
- **Timezone & quote settings** – customise the quote shown when solar is off.

### 🧒 For Kids
- Personalised theme (Dinosaur, Gamer, Princess, Mecha, Fortnite, Roblox, Teen Dark).
- Interactive avatar with text‑to‑speech encouragement.
- Daily chore checklist (morning/afternoon/evening).
- **Reward store** – redeem points for rewards created by parents.
- **Badge collection** – view earned badges (level‑ups, spotlights, vault unlocks).
- **Weekly mystery reward** – reach 80% weekly completion to claim a random reward.
- Points history chart (weekly/monthly).

## 🚀 Getting Started

### 1. Download the executable
- Go to the **Releases** section of this repository.
- Download `FamilyCommandCenter-windows.exe`.

### 2. Run the application
- Double‑click the `.exe` file.  
  *A console window will open (this is normal).*  
- The server will start on `http://localhost:8080`.

### 3. Open the dashboard
- In your web browser (Chrome, Edge, Firefox, etc.), go to:  
  **`http://localhost:8080`**
- You will be greeted by the **Welcome Wizard** – this is a one‑time setup to create your parent account and add your children.

### 4. Log in as a parent (after setup)
- Use the credentials you created during the wizard.  
  *Default password before setup is `admin` (username `parent`).*

### 5. Access the child dashboards
- From the main screen, click **“Go to Child Dashboard”** or visit `http://localhost:8080/child`.

## 🖥️ System Requirements

- **Windows 10 or 11** (64‑bit).
- No Python or other dependencies required – the executable is self‑contained.
- The application runs on your local computer; other devices on the same home network can connect using your computer’s IP address (e.g., `http://192.168.1.100:8080`).

## 🔒 Default Admin Access (first time)

When you first run the application, you must complete the setup wizard:

1. **Parent credentials** – choose a username and password (this will be your admin login).
2. **Add children** – enter names, ages, and choose themes.
3. **Optional** – configure weather (auto‑detect or manual), solar (if you have Enphase), and Google Photos link.

After setup, the parent panel is available at `http://localhost:8080/admin`.

## 📁 Data Storage

All data is stored locally in the same folder as the executable:
- `database.db` – children, points, chore history, rewards, etc.
- `calendar.json` – family events.
- `photos.json` – slideshow registry.
- `static/media/` – uploaded photos and child avatars.

You can safely back up these files.

## ❓ Troubleshooting

- **Port 8080 already in use** – change the port by editing `server.py` (if you have the source) or stop the other application using the port.
- **Firewall warning** – allow the application to accept incoming connections if you want other devices on your network to see the dashboard.
- **Nothing shows in the slideshow** – upload your own photos via the Admin panel → Photo Upload tab, or configure a Google Photos shared album.

## 📜 License

This software is proprietary – see the `LICENSE.txt` file included with the download. You are granted a non‑exclusive, non‑transferable license to use the software for personal, non‑commercial purposes within a single household.

## 🙏 Acknowledgements

Built with Flask, SQLite, Open‑Meteo, and pure HTML/CSS/JS.

---

**Enjoy keeping your family organised and motivated!**  
If you encounter any issues, please open an issue on this repository.
