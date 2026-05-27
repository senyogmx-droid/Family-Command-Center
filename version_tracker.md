# Master Walkthrough & Historical Changelog - Family Command Center

Welcome to the comprehensive master walkthrough for the **Family Command Center**. This document tracks all features, architectural designs, database schemas, and integration pipelines developed from the initial core launch through the latest **v3.5.3 Blueprint** release.

---

## 🎨 Visual Assets & Telemetry Footers

All templates feature a sleek, futuristic version release watermark at their footers to indicate the current active design blueprint:

```html
<!-- Telemetry Release Tag -->
<div class="version-telemetry-tag">
    Family Command Center Kiosk Engine Version v3.5.3 Blueprint
</div>

The watermark inherits custom `'Orbitron'` monospace styling with subtle opacity, blending cleanly into the bottom margins of all active viewports:
* **Main Kiosk Dashboard (`index.html` / `static/index.html`)**
* **Child Personal Checklist (`static/child.html`)**
* **Kids' Chores Summary Grid (`static/chores_summary.html`)**
* **Weekly Performance Honor Roll (`static/performance.html`)**
* **Parent Administration Portal (`static/admin.html`)**
* **Welcome Setup Onboarding Wizard (`templates/welcome.html`)**

Four stunning, high-resolution landscape backgrounds are pre-loaded to fuel the double-buffered slideshow engine:
1. **Mountain Sunset** (Warm crimson tones)
2. **Forest Lake** (Cozy pine gradients)
3. **Misty Canyon** (Sleek slate depths)
4. **Snowy Peaks** (Minimalist frost contours)

---

## 📂 Core Project Files & Directory Structure

Your project code is structured inside the workspace folder `C:\Users\senyo\OneDrive\Documents\VS code writing\Family dashboard project`:

```text
Family Command Center/
│
├── server.py                       # Core Flask Server (routing, API endpoints, SQLite managers)
├── database.db                     # Active SQLite database (users, children, chores, completion history)
├── photos.json                     # Google Photos registry (compiled dynamically by sync_photos.py)
├── calendar.json                   # Persisted Month Calendar events registry
├── sync_google_photos.py           # Playwright download album syncs
├── sync_photos.py                  # Generates active photo registry
├── fetch_enphase_token.py          # Harvester for Envoy local JWT
│
├── static/                         # Dashboard Static Assets
│   ├── index.html                  # Main Kiosk Display Dashboard
│   ├── admin.html                  # Parent Control Cockpit (Glassmorphic 4-Tab deck)
│   ├── child.html                  # Kids Chore Checklist (themeable, gold coin/XP tickers, audio oscillators)
│   ├── chores_summary.html         # Kids Chores Grid with Mobile APK links and carousel triggers
│   ├── performance.html            # Weekly Performance Honor Roll (zero-scroll landscape carousel)
│   ├── style.css                   # Master Styling Sheet (translucent glass borders, neon glowing lights)
│   ├── themes.css                  # Roster specific visual tier stylesheet (7 active themes)
│   ├── media/                      # Child Profile Photo Upload folder
│   └── apps/                       # Custom Android APK deployment folder
│
└── templates/
    └── welcome.html                # Setup Onboarding Wizard (seeding configurations, alert hooks)


💾 Database Architecture (SQLite Schema)
The active SQLite database (database.db) leverages automatic startup migrations inside init_db() in server.py to ensure schema additions apply without losing point values or task history:

users: Manages parent security logins, hashed password signatures, main page privacy toggles, and lifetime scores.

children: Stores crew profiles including name, age, active Visual theme (Dinosaur, Princess, Gamer, Mecha, Roblox, Fortnite, Teen Dark), custom typography font (Fredoka, Orbitron, Outfit), points balances (points, bankable_balance, lifetime_xp), active level, soft-delete controls (status, deleted_at), and custom profile picture relative URLs (avatar_path).

chores: Registry of daily/weekly routines showing names, values, blocks (morning, afternoon, evening), active days checks, validation rules, and child assignments.

chore_history: Records completion histories by matching children IDs and daily ISO date strings.

parent_spotlights: Encapsulates spot encouragements from Mom & Dad, notes, and bonus XP allocations.

system_config: Flexible Key-Value storage containing setup parameters, Enphase solar credentials, google shared links, and SMTP mail hashes.

rewards (v3.5.0): Parent-defined point-based rewards (store items).

habit_reminders & parent_spotlights (v2.3) remain.

---

## 🛸 First-Time Onboarding Wizard (`/welcome`)

* **Setup Gateway**: Middleware inside `server.py` checks database states. If the children profiles roster is empty or `admin_configured` is not `'true'` in `system_config`, all routes redirect to `/welcome`.
* **Multi-Step Setup Form**: Served from `welcome.html`, this glassmorphic wizard handles:
  1. *Step 1*: Parent Password Setup.
  2. *Step 2*: Crew Roster Ingestion (adds children, determining default seed chores based on age-brackets: toddlers, young child, youth, teen).
  3. *Step 3*: iCal calendar integrations and SMTP Gmail App Password alert setup.
  4. *Step 4*: Enphase solar gateway credentials and enabled solar toggles.
* **POST `/api/system/initialize`**: Initializes parameters, securely encrypts credentials via symmetric base64 XOR ciphers, autoseeds default chores, and logs in the parent.

---

## 🚀 Version 2.0 Historical Milestones

Version 2.0 transitioned the Family Command Center from a static screen into a multi-device local web ecosystem:

### 1. Secure SQLite Store & Seasonal Engine
* **Hashed Credentials**: Leveraged secure SHA-256 hashing to store parent dashboard access passwords (`users` table), replacing cleartext storing.
* **Automated Seasonal Colors**: Dynamically calculates the active season based on the system calendar on boot, serving tailormade color parameters (`accent_blue`, `text_glow`, `body_tint` for Deep Spring Green, Summer Sky, pumpkin Autumn, and frosty Winter).

### 2. Smart Collage Aspect Ratio Matching Engine
* Resolves image cropping issues in kiosk slideshow loops by scanning aspect ratios in the background:
  - Categorizes photos into **Landscape** ($>1.25$), **Portrait** ($<0.8$), or **Square** ($0.8$ to $1.25$).
  - Evaluates satisfied grid fits (`layout-landscape-stack`, `layout-duo-2`, `layout-split-3`, `layout-grid-4`, `layout-polaroids`) and dynamically assigns them.
  - Implements a blurred-background single crop-free plate for irregular images.

### 3. Sci-Fi Cyber-Mecha Theme (`.theme-mecha`)
* Added a premium cybernetic skin featuring Cyber Neon Cyan (`#00f0ff`), Warning Amber (`#ffb700`), and Crimson Reactor (`#ff0055`) set on a dark star gradient.
* Floating mech emojis (`🤖`, `⚔️`) hover utilizing neon keyframe shadows. Card headers display high-contrast repeating warning hazard stripes.
* **Princess Crown Optimization**: Adjusted Noelle's animated crowns (`👑` and `✨`) to a refined size, pushing them to the card boundaries to prevent name overlapping.

### 4. Real-Time Household Solar & Energy Telemetry
* Redesigned the Enphase widget into a responsive **3-Column Energy Flow** dashboard (Solar production, Home consumption, and Net Grid exchange).
* **Gauss Model Simulators**: Simulates active home load with Gaussian peak draws (morning spikes at 7:30 AM, dinner cooking peaks at 6:30 PM).
* **Gaussian CDF Calculus**: Integrates daily consumed energy analytically using `math.erf` to guarantee mathematical precision at any minute of the day.
* **Envoy 7.x CT parsing**: Pulls current home draw (`wNow`) and cumulative consumption (`whToday`) from production JSON streams.
* **Reactive Colors**: Green for solar, orange for draw, and net grid cycles between Cyan (grid exporting) and crimson (grid importing).

### 5. Raspberry Pi Autostart & Deployment
* Created autostart instructions launching Chromium in native full-screen kiosk modes:
  ```bash
  @chromium-browser --noerrdialogs --disable-infobars --kiosk http://localhost:8080
  ```
* Written Windows (`deploy_to_pi.bat`) and Unix (`deploy_to_pi.sh`) scripts with rsync exclusion flags to ensure transferring code updates never overrides live database progress or locally cached JSON feeds.

---

## ⚡ Version 2.3 Blueprint Upgrades

The Version 2.3 Blueprint introduces deep gamification, absolute parent feedback review loops, corrective routine audits, and spontaneous spot reinforcements:

### 1. Database Schema Migrations
Upon server execution, `server.py` performs non-destructive schema validation, adding columns and setting up three new SQL tables:
* **`children` Table Extensions**: Adds `bankable_balance`, `lifetime_xp`, and `level` (defaulting level math: Level up every 100 XP).
* **`chores` Table Extensions**: Adds `time_block`, `is_enrichment` (blocks direct checkboxes), and `validation_type`.
* **New Tables**:
  - `chore_submissions`: Stores proof metadata (up to 3 sequential audio clips, text dictation, photo files, auditing status, and parent review comments).
  - `habit_reminders`: Log of active routine penalties, warning photos, point deductions, and refund resolutions.
  - `parent_spotlights`: Spontaneous spotlight alerts featuring givers' names and points bonuses.

### 2. Time-Block Filtration Tabs
Checklists are divided into **🌅 Morning**, **☀️ Afternoon**, and **🌙 Evening** tabs inside the child interface (`child.html`). This structure filters chores contextually, keeping kids focused on relevant tasks.

### 3. Multi-Clip Audio Verification Pipeline
* Enrichment chores require multi-clip verification before points are awarded:
  - Displays a recording canvas with slots for `[Clip 1]`, `[Clip 2]`, and `[Clip 3]`.
  - Captures raw voice recordings using HTML5 MediaRecorder (5 mins max per clip) or falls back to device keyboard dictation textareas.
  - Submits proof directly to `/media` folders for parent verification.

### 4. Parent Pending Reviews Audit Queue
* All audio/photo/text submissions queue up in the Parent Cockpit (`admin.html`).
* Parents can inspect photos, read transcripts, play audio clips sequentially, and select:
  - `🟢 Approve`: Credits XP and balance instantly, and runs level-up evaluations.
  - `🔴 Deny`: Rejects the task and locks the checkmark.
  - `🟡 Request Revision`: Flashes a warning banner (`⚠️ Parent Feedback: Attention Needed!`) at the top of the child's screen, displaying parent correction comments and reopening speech inputs.

### 5. Corrective Action Center & Partial Refunds
* Parents can penalize child violations by posting warning photos, writing reminders, and deducting bankable balance points.
* Once the child corrects the behavior, parents can adjust a **dynamic point slider (0% to 100%)** to issue a partial refund of deducted points instantly.

### 6. Spontaneous Parent's Spotlight Launcher
* Enables parents to issue spot bonuses to children immediately.
* Supports customizable "Giver Names" (Mom, Dad, Grandma, etc.) and points (+2 to +5).
* SSE broadcasts interrupt the child's screen instantly with a glowing glassmorphic card presenting the points award and animated sparkles.

### 7. Google Calendar Quick-Add
* Integrates a sidebar quick-add form in the admin cockpit, enabling parents to write new events directly into the Stafford local calendar JSON pipeline.

### 8. Data Retention Daemon Threads
* To prevent local disk congestion, a daemon thread reviews the `/media` folders every 24 hours:
  - **90 Days**: Mock-compresses media files (bitrates/resolutions).
  - **180 Days**: Permanently deletes physical audio and photo assets (preserving database textual transcripts and point ledgers indefinitely).

### 9. High-Legibility Font & Outline Overhaul
* Replaced highly stylized theme fonts (`'Fredoka One'`, `'Orbitron'`, `'Playfair Display'`) on checklists, buttons, cards, and body elements with highly-legible geometric sans-serif families (`'Outfit'`, `'Inter'`, `-apple-system`, `sans-serif`) across all child views (**Dinosaur, Gamer, Princess, Mecha**).
* Retained unique theme headers and welcome banners in their custom stylized fonts (`'Fredoka One'` for Dinosaur, `'Orbitron'` for Gamer/Mecha, `'Pacifico'` for Princess) to preserve the delightful thematic character.
* Softened and removed the hard-to-read solid black text-shadow outlines on children chores lists and summary items (completely removed for the pastel Princess theme) to optimize legibility and eliminate visual clutter.
* Solved the graphic overlap on Axel's header by centering the `#welcome-title` text and raising its layers (`z-index: 2`), pushing dinosaur graphics safely to the margins (`z-index: 1`).
* Resolved page scroll blockages on **Parent Admin Portal (`admin.html`)**, **Kids' Chores Summary Grid (`chores_summary.html`)**, and **Child Personal Checklist (`child.html`)** by overriding the main kiosk's rigid fullscreen limits (`height: 100vh; overflow: hidden;`) with natural vertical scrolling parameters (`height: auto !important; overflow-y: auto !important;`) on their body elements, making all elements accessible.

### 10. Grouped Chore Registry & Multi-Child Assignment Dashboard
* **Clean UI Grouping**: Instead of displaying separate, duplicate rows for each child assigned to the same chore, identical chores are automatically grouped into a single, clean row in the Parent Admin Panel registry.
* **Smart Assignee Summary**: Consolidates multiple children into a single string. If all children in the household are assigned to the task, it displays `Child: Everyone` in clean cyan styling. If a subset of children is assigned, it lists them as a comma-separated string (e.g. `Child: Axel, Cayden`).
* **Interactive Glassmorphic Multi-Select Pills**: Replaced rigid drop-down selectors with dynamic, animated, checkable pill tags for both Chore Assignments and Parent's Spotlight launchers.
  - Supports a dedicated toggleable `Everyone` pill that automatically selects or deselects all children.
  - State is fully preserved during background Server-Sent Events (SSE) data refreshes, preventing administrative layout shifts.
* **Unified Administrative Actions**:
  - **Group Deletion**: Clicking the delete button triggers parallel `DELETE` requests to delete all corresponding SQLite chore instances in the group, prompt-confirming with the user first.
  - **Group Editing & Parallel SQLite Diffing**: Clicking edit on a grouped chore loads its details into the Chore Manager form, transitions the header and submission button to amber, and automatically selects the pills for all currently assigned children. Saving changes in edit mode executes a parallel SQLite diffing algorithm:
    - Reuses and updates existing IDs for children who remain in the group (completely preserving completion history).
    - Deletes database entries for children removed from the group.
    - Creates new entries for children newly added to the group.

### 11. Animated Points Accomplishments History Tracker
* **Theme-Responsive Visuals**: Implemented a kid-friendly Points History Tracker card at the bottom of the child checklist screen (`static/child.html`).
* **Visual Mechanics**: A dynamic bar graph showing points accumulated over the days of the week, with an adjacent timeframe switcher that transforms the visualization dynamically to show weekly, monthly, or yearly accomplishments.
* **Highly Responsive Layout**: Supports full scaling and layout wrapping on tablets and smartphones down to 320px wide. Monthly dense views are visually optimized with thinner bars and softened alternate labels to prevent overlap.
* **Gradients & Accents**: Chart bars and timeframe switch buttons automatically style themselves with the active child's profile theme colors (Dinosaur, Gamer, Princess, Mecha) by binding CSS variables (`var(--accent-blue)`, `--panel-bg`, etc.).
* **Hover Interactions & Micro-Animations**:
  - Hovering over a bar plays a sleek micro-animation scaling up the column.
  - Floating emojis matching the selected child's theme (Dinosaur `🦕`, Gamer `⚡`, Princess `✨`, Mecha `🤖`, Default `⭐`) pop up above the active bar.
  - Glowing numeric point badges (e.g. `12 pts`) fade in above the emojis.
* **Live Dynamic Backend Integration**:
  - Connects to `/api/chores/history/<child_name>` backend API to fetch real-time points.
  - Aggregates daily completions (`chore_history`), bonus points (`parent_spotlights`), and net corrective deductions (`habit_reminders`) into dynamic time-series.
  - Auto-synchronizes the bar chart in real-time when chores are completed, spots are awarded, or parent config changes are received via Server-Sent Events (SSE).

### 12. Dynamic Y-Axis Scale & Background Gridlines
* **Precision Number System**:
  - Added a responsive, absolute-positioned Y-axis numbering column (`.tracker-y-axis`) directly to the left of the chart container, bounded by a dashed divider.
  - Ticks are dynamically generated at standard intervals of 4 divisions, calculating clean whole-integer labels based on the active timeframe's maximum point values.
  - Ticks are positioned relative to coordinates via absolute `bottom` percentages matching the background gridlines, ensuring perfect horizontal alignment.
  - Shifted labels' color contrast to a highly legible and premium `rgba(255, 255, 255, 0.65)` matching the kid-friendly themes.
  - Centered tick labels vertically on their coordinate gridlines via a mathematically precise `transform: translateY(50%)` adjustment.
* **Layout Isolation & Flex Spacing**:
  - Configured the main bar chart container to a responsive flex layout (`flex: 1; min-width: 0;`), completely eliminating any container overlap or clipping across both desktop and mobile viewports.
  - The dashed gridlines are placed absolutely in the background (`z-index: 1`) behind the bars (`z-index: 2`), ensuring visual clean-cut depth.

### 13. Interactive Context-Aware Avatar Component & Native TTS Speech Synthesis
* **Avatar Container Placement**: Floating side-by-side flex layout next to the main chore cards.
* **Context-Aware Event Listeners**:
  - The avatar shifts its gaze (eyes looking down/right) when the child hovers over chores or the accomplishments chart.
  - Celebrates completed tasks with custom animated animations (twirls for Noelle, jumps for Axel, etc.).
* **Integrated Native Text-to-Speech (TTS) Engine**:
  - Automatically welcomes the child to their dashboard, reading out a time-based greeting and highlighting how many chores remain in the active time block.
  - Dynamically detects and verbally warns the child of parent revision audit feedback (e.g. "Attention is needed! You have an important parent update: 'Brush teeth is missing picture!'").
  - Highlights accomplishments when the child clicks on their daily Points Accomplishments card, providing detailed levels, scores, and completion ratios.
  - Speaks excited celebrations whenever spot bonuses are received, submissions are made, or chores are successfully checked.
  - Standardized custom character speech parameters (`utterance.pitch` and `utterance.rate`) for Noelle (Princess high-pitch), Axel (Dinosaur growl), Cayden (Gamer energy), and Mecha (Robotic monotone).

### 14. Noelle's Theme Customization (Black Barbie Princess & Purple Favorite Color)
* **Custom Typography**: Aggregated Google Fonts `'Satisfy'` (chic script) and `'Comfortaa'` (rounded sans-serif) at the top of `themes.css`.
* **Theme Styling**: Re-designed Noelle's `.theme-princess` body styles to a royal lavender-purple gradient, violet texts, and amethyst accents, replacing the former pink styling.
* **Cocoa Princess Fallback SVG**: Re-engineered her fallback vector SVG to feature a gorgeous Black Barbie princess with cocoa skin, black space buns with gold curly highlights, lavender ribbons, gold crown with purple gems, and a royal purple gown with lavender corsetry.
* **Global Kiosk Sync**: Upgraded Noelle's leaderboard card in `static/chores_summary.html` to match her purple color scheme and custom typography.

### 15. Array-Based Query Bugfix for Avatar Engine
* **The Bug**: The original speech engine in `greetChild` and `highlightAccomplishments` queried `.chore-item-row` and `.chore-checkbox` classes, which are not present in the simplified touch-friendly checklist DOM inside `child.html`. This caused counts to always read `0` or say "Block Complete!".
* **The Solution**: Upgraded `AvatarEngine` to query the global `allChores` state array directly. The avatar now counts active chores and completed tasks mathematically and perfectly under all conditions (e.g. `allChores.filter(c => c.time_block === activeTab && !c.completed_today).length`).

### 16. Noelle's Premium Custom Avatar Portrait Drawing & Natural Little Girl Voice (Phase 24)
* **Custom PNG Portrait Integration**: Extracted the custom hand-drawn character design from the parent uploaded drawing (`media__1779412734821.png`) and saved it as a high-fidelity image at `static/assets/avatars/noelle-princess.png` showing a gorgeous Black girl with adorable puff buns, pink/green bows, diamond tiara, majestic gown, and butterfly wand.
* **Circular Premium Image Framing**:
  - Refactored `initSelectorScreen()` in `child.html` to check for Noelle and load her custom drawing styled as a high-end circular frame profile with a 3px amethyst purple border and glowing shadow effect (`box-shadow: 0 0 15px rgba(168, 85, 247, 0.45)`).
  - Configured `onChildSelected()` to load the premium portrait PNG inside the floating dynamic interactive avatar container, styled with an 18px rounded box, 4.5px solid purple border, and glassmorphic depth shadows.
  - Implemented automatic path safeguards in `triggerReaction()` to preserve `noelle-princess.png` as the image source during reactive animations, bypassing non-existent GIF calls and preventing broken image links, while letting CSS transition classes trigger keyframe celebrations (like elegant spins and bounces) seamlessly.
  - Upgraded the `triggerSpotlightPopup()` parent reward overlay to show the custom portrait in a gorgeous 100px circular glowing avatar container.
  - Upgraded `static/app.js` to render her beautiful PNG portrait in the family dashboard leaderboard rows instead of generic text emojis.
* **Natural Child-Like Speech Synthesis (TTS)**:
  - Upgraded `AvatarEngine.speak()` in `child.html` with a robust native voice selection system that targets sweet, high-quality, friendly little girl voices first (such as Microsoft's child/kid voice `"Ana"` or Google natural/expressive child voices) and falls back gracefully to warm, sweet female voice profiles.
  - Fine-tuned the sound parameter metrics specifically for Noelle: elevated pitch to `1.45` (representing a bright, cute kid frequency) and rate to `0.95` (creating a slower, natural, highly expressive speech flow) to guarantee she sounds like a warm, sweet real little girl instead of a default system robot.
  - Injected an active voice cache preloader into `AvatarEngine.init()` that queries `getVoices()` and registers `onvoiceschanged` so voices are immediately loaded by the browser engine upon load.

---

## 🦄 Version 2.3.1 Past-Day Checklist Recovery & Princess Checkbox Overhaul

Version 2.3.1 resolves core usability challenges around historical chore auditing and high-legibility checkbox systems specifically tailored for light pastel children's themes:

### 1. Retroactive Past-Day Checklist Recovery
* **Time-Traveling Day Selector (`static/child.html`)**:
  - Injected an elegant, theme-responsive `#day-selector-tabs` component directly beneath the header card, allowing children to cycle between **Today** and **Yesterday**.
  - Dynamically updates active stylesheet variables and limits the retrospective window to exactly 1 day backward to preserve routine discipline.
* **Parental Verification Request Modal**:
  - Incomplete chores on the **Yesterday** view cannot be toggled directly. Clicking a yesterday chore triggers a glassmorphic `#yesterday-modal-overlay` prompt.
  - The child can input a clarification note (e.g., "Forgot to check yesterday, done on time!") which submits a formal verification request.
  - Submissions display an amber `⏳ Pending Review` or red `⚠️ Revision Needed` badge, locking standard checkbox clicks to prevent duplicates.
* **Database Isolation and Backdating (`server.py`)**:
  - Refactored server query states in SQLite to match submissions on both `chore_id` and `submitted_date`. This guarantees date-wise isolation, preventing clashes where yesterday's audit entries overwrite today's completions.
  - Seamlessly handles parental approvals via `/api/chores/approve`, backdating the accomplishments record to the actual historical completion day and recalculating charts and balances.

### 2. Noelle's Princess Checkbox High-Visibility Overhaul (`static/themes.css`)
* **The Usability Challenge**: Noelle's premium Princess theme utilizes soft, gorgeous lavender-white backgrounds. The default semi-transparent checklist circles (`rgba(255, 255, 255, 0.25)`) blended completely into the panel card, making it extremely hard to locate where empty checkboxes were.
* **High-Contrast Amethyst Redesign**:
  - Redesigned `body.theme-princess .checkbox-holder` with a thick, solid, premium amethyst border (`3px solid #c084fc !important`).
  - Added a solid, pure white background (`#ffffff !important`) to block the underlying card patterns and make the circle pop out perfectly.
  - Applied a delicate radial drop-shadow (`box-shadow: 0 3px 10px rgba(192, 132, 252, 0.25)`) to create visual depth and premium 3D lift.
* **Interactive Focus States**:
  - Hovering over a touchable chore card on Noelle's page scales the checkbox circle smoothly (`transform: scale(1.05)`) and deepens the border color to royal purple (`#a855f7 !important`) with an energized glow shadow.
  - Upon completion, the circle fills fully with a royal purple background (`#a855f7`) showing a crisp white checkmark (`#ffffff`) for maximum visual clarity.

---

## 🚀 Version 2.3.2 Fully-Automated Past-Day Audits & SMTP Notification Alerts

Version 2.3.2 removes visual friction from retrospective auditing, introduces a robust HTML SMTP Email alert subsystem, and outlines modern secure context specifications for microphone capture on mobile touch devices:

### 1. Zero-Friction Automatic Yesterday Submissions (`static/child.html`)
* **Click-to-Submit Workflow**:
  - Bypassed and eliminated the manual text-note modal for past-day checklist items, fulfilling the user requirement for instant retroactive submissions.
  - Clicking an unchecked chore on the **Yesterday** tab now invokes `submitYesterdayRequestAutomatically(chore)` immediately.
* **Responsive Visual Feedback**:
  - Tapping a yesterday chore instantly locks the card element (`disabled-touchable`) and displays a smooth spinning loader inside the checkbox circle (`<i class="fa-solid fa-spinner fa-spin"></i>`).
  - Packages and POSTs the payload dynamically to the backend SQLite servers with a `[YESTERDAY AUTOMATIC REQUEST]` audit label.
  - Reloads page telemetry immediately, displaying a gorgeous orange **⏳ Pending Review** badge and preventing accidental double clicks.
* **Character Voice Encouragement**:
  - Hooks directly into the customized `AvatarEngine` TTS system, prompting Noelle, Axel, Cayden, or Mecha to verbally confirm the submission to the child (e.g. *"Sent Make Bed to parents for approval!"*).

### 2. Multi-Directional HTML SMTP Email Notification Engine (`server.py`)
* **Core Engine (`send_email_notification`)**:
  - Added a highly flexible python SMTP engine supporting SSL (Port `465`) and TLS (Port `587`) protocols.
  - Safely falls back to an elegant mock console logger when credentials are not yet configured in environment variables or the SQLite `system_config` table, ensuring the main application never crashes.
  - Leverages python `threading.Thread` daemons to broadcast emails completely in the background, eliminating any loading delay for children.
* **Triggered Notifications**:
  - **Parent Action Alerts**: Whenever a child completes an enrichment chore or submits a retroactive task, parents instantly receive a styled HTML email listing the child's name, chore name, exact timestamp/date, and a one-click button link back to the parent dashboard.
  - **Child Status Updates**: Whenever a parent reviews a submission and takes action (Approve, Deny, or Request Revision), an email notification is automatically dispatched notifying them of their new chore review status and displaying custom parent feedback comments.

### 3. Local Secure Contexts & Mobile Microphone Guidelines
* **Secure Context Security Policy**:
  - Web browsers (Chrome, Safari, Firefox, Edge) restrict media device access (microphone and camera) strictly to **Secure Contexts**.
  - Local loopback connections served on `http://localhost` or `http://127.0.0.1` are treated as secure by default, which is why voice recording works on the host machine.
  - Connections from other local network devices (e.g., accessing the server via `http://192.168.1.107:8080` from an iPad, tablet, or phone) are treated as **insecure**, thus blocking microphone access.
* **HTTPS Activation Guide**:
  - To enable microphone support on iPads and tablets over Wi-Fi, the Flask application must be served over HTTPS.
  - This can be easily activated by providing Flask with a self-signed certificate, or running the server with `ssl_context='adhoc'` inside `server.py`.

---

## 📜 Historical Changelogs (v3.0.0+)

### 🦖 Version 3.1.3 — Age-Tier Theme CSS
* Added three new high-end visual themes inside `static/themes.css`:
  - `.theme-fortnite` — Purple/gold combat border gradients, Orbitron monospaced headings, animated trophy emojis.
  - `.theme-roblox` — Red blocky voxel structures, bevel shadow cards, brick-stripe titles.
  - `.theme-teen-dark` — Slate gray minimalism, zero glowing text lines, strike-through lines on completed tasks.
* Unified telemetry watermarks across all core page files.

---

### ⚙️ Version 3.2.0 — Parents Admin Tab Restructure
* Rebuilt parent interface (`admin.html`) from a standard form layout into a beautiful Glassmorphic 4-Tab deck:
  - **Tab 1: Chore Manager**: Form fields supporting Time Block dropdowns and weekly days checks, with a complete chore registry table.
  - **Tab 2: Spotlight & Settings**: Peak-hour speedup switch, Star of Day overrides, encouraging spotlights, Gmail/Enphase credential settings, and danger zone resets.
  - **Tab 3: Month Calendar**: Translucent month grid showing days, matching event indicators, upcoming schedules, and prev/next month navigations.
  - **Tab 4: Child Settings**: Clickable selector row of crew members. Clicking details reveals config forms, Pause switches, soft-delete triggers, and Deleted Recovery grids.

---

### 🪙 Version 3.3.0 — Leveling Progression & Audio Oscillators
* **RPG dual-counter panel (`child.html`)**: Separated kid checklists into spendable balance (Gold Coins 🪙) vs. non-dropping lifetime XP levels (Level Ranger title hooks e.g. Lvl 1 -> Lvl 2).
* **Web Audio Oscillators**: Synthesizes retro arcade positive feedback sounds (ping on checking tasks, major arpeggio sequence trumpets fanfare on final daily completion).
* **Enphase XOR harvesters**: Enabled double-symmetric base64 XOR ciphers inside `server.py` to encrypt SMTP and Enphase credentials at-rest. Masked all passwords as `"••••••••"` in configs APIs.

---

### 🏆 Version 3.4.0 — Weekly Performance Honor Roll Slide
* **Weekly Performance Slide (`performance.html`)**: Zero-scroll landscape slide calculating date boundaries of the previous complete week (Sunday to Saturday).
* **Accolades Badges**: Award streaks dynamically (Streaks, Helper, XP Earner) alongside Parent spotlights bubble quotes.
* **Deck Carousel Rotation**: If children roster size exceeds 3, columns paginate and transition every 15 seconds.
* **Slideshow Loop**: Updated chores summary (`chores_summary.html`) to route inactive screens to `/performance`, which then rotates back to the main homepage `/`.

---

### 📸 Version 3.4.1 — Child Profile Photo Uploads & Layered Visuals
* **AJAX Photo Uploader**: Implemented secure `/api/admin/children/upload-photo` POST route, creating `static/media/child_photos/child_{id}.{ext}` folder stores and updating children database profiles.
* **Uploader Component (`admin.html`)**: Appended camera upload zones under settings cards, immediately displaying high-res previews next to franchise avatars.
* **Premium Layered Headers (`child.html` & `performance.html`)**: Renders custom child circular photos (neon theme-glowing borders) layered with floating franchise badge badges on the bottom-right for instant guest recognition.
* Watermarked all core layout watermarks to `v3.4.1 Blueprint`.

---

### 🏞️ Version 3.4.2 — Codebase Sanitization & 3-Way Photo Source Selector
* **Clean Distributable Assets**: Completely purged all private family images from the default distribution directories and local `photos/` folder. Added 4 unbranded, high-resolution default landscape background assets inside `static/media/landscapes/` (Mountain Sunset, Forest Lake, Misty Canyon, Snowy Peaks) for beautiful fallback screen cycling.
* **3-Way Photo Source Selector**: Updated the onboarding wizard `templates/welcome.html` (Step 4) and SQLite config parameter `photo_source_mode` to offer families three screensaver feeds: Default Landscapes (no configuration), Google Photos Stream (public album harvesting), and Local Storage Manual Uploads.
* **Zero-Dependency Aspect Ratio Scanner (`sync_photos.py`)**: Rebuilt the indexer in pure Python to parse image header bytes (supporting PNG, JPEG, GIF, and WebP formats) and compile structured metadata records directly into `photos.json`, caching ratios and orientations to save kiosk browser CPU load.
* **Frosted-Glass Tab 5 Photo Upload (`admin.html`)**: Added a 5th tab to the parent admin portal featuring an interactive drag-and-drop file uploader zone (dashed neon-cyan border), a FileReader gallery preview queue grid, and a multi-file POST API endpoint `/api/admin/photos/upload` in `server.py` that processes uploads asynchronously inside background daemon threads.
* **Strict Exclusions Safety Guardrails**: Hardened exclusions inside `deploy.ps1`, `deploy_to_pi.sh`, and `deploy_to_linux.bat` to guarantee that transferring codebase updates never deletes a family's manually dropped photos, custom kid avatars, or active SQL entries.
* Watermarked all core layout watermarks to `v3.4.2 Blueprint`.

---

🎁 Version 3.5.0 — Point-Based Reward System (Reward Store)
Database addition: New rewards table to store parent-defined rewards (name, description, points cost, optional child assignment).

Admin Panel – Reward System Tab:

Located inside Chore Manager as a new subtab “Reward System”.

Allows parents to create, edit, and delete point-based rewards.

Rewards can be assigned to “Everyone” or a specific child.

Child Page – Reward Store:

New button “Reward Store” next to Badge Collection.

Modal displays available rewards, points cost, and child’s current bankable balance.

One-click redemption deducts points and adds a “Redeemed: …” entry to unlocked_assets.

Backend endpoints:

GET /api/admin/rewards, POST /api/admin/rewards, DELETE /api/admin/rewards/<id>

GET /api/rewards?child_id=..., POST /api/rewards/redeem

SSE broadcasts update the leaderboard and points display immediately.

✨ Version 3.5.1 — Weekly Mystery Reward & Milestone System
Weekly secret reward (80% weekly chore completion threshold):

Backend tracks weekly percentage (Sunday–Saturday).

Once threshold is reached, a “Claim” button appears in the progress area of child.html.

Clicking claims a random reward from the existing reward pool and adds it to unlocked_assets.

One reward per child per week (prevents double‑claiming).

Milestone backend:

check_and_award_milestones() function in server.py detects 7‑day streaks and 20‑chore weekly completions.

Automatically awards random rewards and broadcasts milestone_unlocked SSE events.

Child page popup: Shows a celebratory modal when a milestone is reached.

Removed the old per‑chore streak panel (crowded UI) – now only the single weekly mystery reward teaser appears in the progress card.

🛡️ Version 3.5.2 — Habit Reminders, Badge Collection, and Revision Flow
Habit Reminders (already present in v2.3, but fully integrated):

Parents can issue corrective action cards with point deductions.

Refund system (partial/complete) with point restoration.

Badge Collection:

Replaced the redundant “Epic Year” chart button with “🏆 Badge Collection”.

Displays all earned badges: level-ups, parent spotlights, vault unlocks, and weekly mystery rewards.

Badges are shown in a horizontal, scrollable grid with newest first.

Parent “Send for Revision” Flow:

Added a “Send for Revision” button in the approval queue.

Parents can enter feedback text; backend updates chore_submissions status to needs_revision and stores feedback.

Child page shows a persistent revision banner until the chore is corrected and resubmitted.

Fixed approval queue UI to support revision action.

🌦️ Version 3.5.3 — Integrations Tab, Solar Quote Replacement, Network UI, Calendar Time & Edit
Integrations Tab in Admin Panel:

Weather Station configuration (location, lat/lon, auto‑detect).

Enphase Solar Gateway settings (enable toggle, credentials).

Timezone selector.

Solar Simulation Removed: /api/solar returns no fake data; solar off shows Inspirational Quote of the Day (deterministic daily).

Network Infrastructure UI: IP/MAC addresses displayed in large, high‑contrast monospaced font.

Calendar Enhancements:

Time fields (start/end) when adding/editing events.

Edit event modal (pen icon in upcoming list).

Color picker replaced radio buttons with vertical descriptive pills (Sport, School, Doctor, Family).

Duplicate header badges removed from child page (old “Lvl 1” and “Points” badges) – only RPG panel remains.

Fireworks canvas added for level‑up celebrations.

Fixed broken spotlight modal HTML.

🔧 Version 3.5.4 — Quote Settings, Centralised Version, Google Photos in Photo Tab, Cleanup
Quote Settings in Integrations Tab:

Refresh frequency (Daily / Hourly / Weekly).

Category (General / Bible / Kids) with curated quote lists.

Quotes update dynamically on main dashboard without restart.

Centralised Version Management:

APP_VERSION constant in server.py; served via /api/version.

All HTML footers fetch version dynamically – change one place, update everywhere.

Google Photos moved to Photo Upload tab (not Integrations), with config and sync button.

Final Code Cleanup:

Deleted all internal planning docs (handoff_next_session.md, project_overview.md, etc.).

Removed deployment scripts containing personal IPs (deploy.ps1, deploy_to_linux.bat, etc.).

Created clean_for_distribution.py to sanitise personal data, empty JSON caches, delete user uploads, and reset database.

All core files now dynamically show v3.5.4 via API.