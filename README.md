# 🌌 Family Command Center & Chore Gamification Engine (v3.7.1 Release)

Welcome to the precompiled standalone release of the **Family Command Center**, a visually stunning, multi-device smart home kiosk and gamified household productivity engine.

This repository contains the standalone executables for Windows and Linux. The source code is hosted privately.

---

## 💡 What is the Family Command Center?

The **Family Command Center** is a local smart-home kiosk and productivity hub that turns household chore management into a gamified, interactive experience. Built to run on a local home server, it acts as the central hub for the household, connecting family members through custom interactive portals:

* **🖥️ Main Family Kiosk**: A shared wall-mounted display showing a beautiful double-buffered photo slideshow, real-time Enphase solar home energy metrics, local weather forecasts, calendar schedules, and a live points leaderboard.
* **🦖 Kids' Quest Portal**: A gamified checklist where kids track their chores, earn spendable points, gain XP to level up, review their points on custom graphs, and interact with gaze-tracking theme avatars (Arcade Gamer, Prehistoric Dino, Princess, and Cyber-Mecha).
* **🛡️ Parent Audit & Control Cockpit**: A secure control room for parents to review children's audio/photo chore submissions, log violations (with a penalty-refund slider), and award spontaneous spotlights that trigger real-time screen-wide alerts.

---

## 🚀 How to Launch the Application

Select the instructions for your operating system below to start the standalone, precompiled Family Command Center server.

### 🏁 For Windows Users
1. Download **`FamilyCommandCenter.exe`** from the `V3/dist/` directory.
2. Double-click **`FamilyCommandCenter.exe`** to boot the server. A console window will pop up showing the initialization logs and active network URLs.
3. Keep the console window open while using the application.
4. *(Optional)* To configure the server to automatically run in the background on startup, download **`setup_scheduler.bat`** from the `V3/dist/` directory, right-click it, and click **Run as Administrator**.

### 🐧 For Linux Users
1. Download the **`FamilyCommandCenter`** binary from the `V3/dist/` directory.
2. Open a terminal in the folder containing the binary and grant it executable permissions:
   ```bash
   chmod +x FamilyCommandCenter
   ```
3. Run the binary directly:
   ```bash
   ./FamilyCommandCenter
   ```
4. *(Optional)* To configure the server to run in the background on system startup using `cron`, download **`setup_scheduler.sh`** from the `V3/dist/` directory and execute it:
   ```bash
   bash setup_scheduler.sh
   ```

---

## 🔗 Connect to the Command Center
Once launched, the server will default to **HTTPS** (if local certificates are generated) or fall back to **HTTP**:

#### 🔒 Option A: Secure HTTPS (Default & Recommended)
Use these secure URLs so microphone and camera permissions work seamlessly throughout the home:
* **Main Kiosk screen**: [https://localhost:8080/](https://localhost:8080/)
* **Kids' Portal**: [https://localhost:8080/choresum](https://localhost:8080/choresum)
* **Parent Cockpit**: [https://localhost:8080/admin](https://localhost:8080/admin) (Default secure passcode: `admin`)

#### 🔓 Option B: Standard HTTP (Backup / Certificates Not Setup Yet)
* **Main Kiosk screen**: [http://localhost:8080/](http://localhost:8080/)
* **Kids' Portal**: [http://localhost:8080/choresum](http://localhost:8080/choresum)
* **Parent Cockpit**: [http://localhost:8080/admin](http://localhost:8080/admin)