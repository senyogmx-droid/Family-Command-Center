/* -------------------------------------------------------------
 * ENGINE ENGINE - FAMILY COMMAND CENTER
 * Robust V6 Slideshow, Open-Meteo Tracker, & Calendar Grid
 * ------------------------------------------------------------- */

document.addEventListener('DOMContentLoaded', () => {
    // Initialize Dashboard Modules
    initClock();
    initSolarSim();
    initSlideshow();
    initWeather();
    initCalendar();
    initJokeWidget();
    initLeaderboard();
    initKioskRotator();
});

/* =============================================================
 * MODULE 1: CENTERED CLOCK TICKER
 * ============================================================= */
function initClock() {
    const clockDigits = document.getElementById('clock-digits');
    const clockPeriod = document.getElementById('clock-period');

    function updateClock() {
        const now = new Date();
        let hours = now.getHours();
        const minutes = String(now.getMinutes()).padStart(2, '0');
        const ampm = hours >= 12 ? 'PM' : 'AM';

        hours = hours % 12;
        hours = hours ? hours : 12; // 0 becomes 12

        if (clockDigits) clockDigits.textContent = `${hours}:${minutes}`;
        if (clockPeriod) clockPeriod.textContent = ampm;
    }

    updateClock();
    setInterval(updateClock, 1000); // Ticks every second
}

/* =============================================================
 * MODULE 2: ENPHASE SOLAR PRODUCTION
 * ============================================================= */
function initSolarSim() {
    const solarCurrent = document.getElementById('solar-current');
    const solarToday = document.getElementById('solar-today');
    const homeCurrent = document.getElementById('home-current');
    const homeToday = document.getElementById('home-today');
    const netCurrent = document.getElementById('net-current');
    const netToday = document.getElementById('net-today');
    const netCard = document.getElementById('solar-card-net');

    async function fetchSolarMetrics() {
        try {
            // FIXED: Added a timestamp (?t=...) to force the browser to bypass its cache and grab fresh data
            const response = await fetch('/api/solar?t=' + Date.now());
            if (response.ok) {
                const data = await response.json();
                
                // Bind Solar Production
                if (solarCurrent) solarCurrent.textContent = data.current_power;
                if (solarToday) solarToday.textContent = data.produced_today;
                
                // Bind Home Consumption
                if (homeCurrent) homeCurrent.textContent = data.current_consumption;
                if (homeToday) homeToday.textContent = data.consumed_today;
                
                // Bind Net Grid Exchange
                if (netCurrent) netCurrent.textContent = data.net_power;
                if (netToday) netToday.textContent = data.net_today;
                
                // Dynamic class formatting based on grid direction (import vs export)
                if (netCurrent && data.net_power) {
                    const netVal = parseFloat(data.net_power);
                    if (netVal >= 0) {
                        // Exporting to grid - Cyan glow!
                        netCurrent.className = 'sub-value highlight-cyan';
                        if (netToday) netToday.className = 'sub-value highlight-cyan';
                        if (netCard) {
                            netCard.classList.remove('status-importing');
                            netCard.classList.add('status-exporting');
                        }
                    } else {
                        // Importing from grid - Crimson warning glow!
                        netCurrent.className = 'sub-value highlight-crimson';
                        if (netToday) netToday.className = 'sub-value highlight-crimson';
                        if (netCard) {
                            netCard.classList.remove('status-exporting');
                            netCard.classList.add('status-importing');
                        }
                    }
                }
            }
        } catch (e) {
            console.error("Could not fetch local solar.json data:", e);
        }
    }

    // Run it immediately on page boot
    fetchSolarMetrics();
    
    // FIXED: Placed inside the main block so the browser can loop it safely every 5 seconds
    setInterval(fetchSolarMetrics, 5000); 
}

/* =============================================================
 * MODULE 3: V6 DOUBLE-BUFFER SLIDESHOW ENGINE
 * ============================================================= */
function initSlideshow() {
    const container = document.querySelector('.slideshow-container');
    if (!container) return;

    // Create exactly two permanent HTML buffer tracks to keep GPU memory flat
    const trackA = document.createElement('div');
    const trackB = document.createElement('div');

    trackA.className = 'slideshow-track active';
    trackB.className = 'slideshow-track';

    container.appendChild(trackA);
    container.appendChild(trackB);

    // Initialize images inside tracks (flat DOM tree for zero leak)
    [trackA, trackB].forEach(track => {
        // Background blur is shared at the track level
        const bg = document.createElement('img');
        bg.className = 'slide-bg-blur';
        track.appendChild(bg);

        // Single Image View
        const singleView = document.createElement('div');
        singleView.className = 'slide-single-view';
        const fg = document.createElement('img');
        fg.className = 'slide-fg-contain';
        singleView.appendChild(fg);
        track.appendChild(singleView);

        // Collage View
        const collageView = document.createElement('div');
        collageView.className = 'slide-collage-view';
        for (let i = 0; i < 4; i++) {
            const imgWrapper = document.createElement('div');
            imgWrapper.className = `collage-img-wrapper wrapper-${i}`;
            
            // Background blur for Zero-Crop
            const bgBlur = document.createElement('img');
            bgBlur.className = 'collage-img-bg-blur';
            imgWrapper.appendChild(bgBlur);

            // Foreground contained image
            const img = document.createElement('img');
            img.className = 'collage-img';
            imgWrapper.appendChild(img);
            
            collageView.appendChild(imgWrapper);
        }
        track.appendChild(collageView);
    });

    let photos = [];
    let shuffledPhotos = [];
    let activeTrack = trackA;
    const slideDuration = 10000; // 10 seconds per slide

    // In-memory cache for photo aspect ratios and orientations
    const photoMetadata = {};

    // Fallback photos in case photos.json is missing or empty
    const fallbackPhotos = [
        'https://images.unsplash.com/photo-1506744038136-46273834b3fb?auto=format&fit=crop&w=1200&q=80',
        'https://images.unsplash.com/photo-1470071459604-3b5ec3a7fe05?auto=format&fit=crop&w=1200&q=80',
        'https://images.unsplash.com/photo-1441974231531-c6227db76b6e?auto=format&fit=crop&w=1200&q=80',
        'https://images.unsplash.com/photo-1513836279014-a89f7a76ae86?auto=format&fit=crop&w=1200&q=80'
    ];

    function shuffleArray(array) {
        const arr = [...array];
        for (let i = arr.length - 1; i > 0; i--) {
            const j = Math.floor(Math.random() * (i + 1));
            [arr[i], arr[j]] = [arr[j], arr[i]];
        }
        return arr;
    }

    async function loadPhotosList() {
        try {
            const response = await fetch('/api/photos');
            if (response.ok) {
                const list = await response.json();
                if (Array.isArray(list) && list.length > 0) {
                    photos = list;
                    return;
                }
            }
        } catch (e) {
            console.warn("Could not load photos.json, using fallback feeds.", e);
        }
        photos = fallbackPhotos;
    }

    // Dynamic photo analyzer that fetches width/height and caches results
    function analyzePhoto(src) {
        if (photoMetadata[src]) return Promise.resolve(photoMetadata[src]);
        return new Promise((resolve) => {
            const img = new Image();
            img.onload = () => {
                const ratio = img.naturalWidth / img.naturalHeight;
                let orientation = 'square';
                if (ratio > 1.25) {
                    orientation = 'landscape';
                } else if (ratio < 0.8) {
                    orientation = 'portrait';
                }
                const meta = { src, ratio, orientation };
                photoMetadata[src] = meta;
                resolve(meta);
            };
            img.onerror = () => {
                // Mark as broken to filter out completely from candidates
                const meta = { src, ratio: 1.0, orientation: 'broken' };
                photoMetadata[src] = meta;
                resolve(meta);
            };
            img.src = src;
        });
    }

    function preloadImage(imgElement, src) {
        return new Promise((resolve) => {
            imgElement.onload = resolve;
            imgElement.onerror = resolve; // resolve anyway to avoid getting stuck
            imgElement.src = src;
        });
    }

    function transitionToNext() {
        if (photos.length === 0) return;

        // Refill queue if running low
        if (shuffledPhotos.length < 15) {
            const newDeck = shuffleArray(photos);
            shuffledPhotos = shuffledPhotos.concat(newDeck);
        }

        const inactiveTrack = activeTrack === trackA ? trackB : trackA;
        const bgImg = inactiveTrack.querySelector('.slide-bg-blur');
        const singleView = inactiveTrack.querySelector('.slide-single-view');
        const collageView = inactiveTrack.querySelector('.slide-collage-view');

        // Grab up to 15 candidates to analyze and match
        const candidateUrls = shuffledPhotos.slice(0, 15);
        const candidateAnalysisPromises = candidateUrls.map(url => analyzePhoto(url));

        Promise.all(candidateAnalysisPromises).then((analyzedCandidates) => {
            // Filter out any broken images completely!
            const validCandidates = analyzedCandidates.filter(c => c.orientation !== 'broken');

            // Measure actual container dimensions
            const containerWidth = container.clientWidth || 880;
            const containerHeight = container.clientHeight || 1080;
            const containerRatio = containerWidth / containerHeight;

            // Define the 5 collage layouts with target aspect ratios for their slots
            const layoutsConfig = [
                {
                    name: 'layout-landscape-stack',
                    count: 2,
                    cellRatios: [containerRatio * 2, containerRatio * 2],
                    nameClass: 'layout-landscape-stack'
                },
                {
                    name: 'layout-duo-2',
                    count: 2,
                    cellRatios: [containerRatio / 2, containerRatio / 2],
                    nameClass: 'layout-duo-2'
                },
                {
                    name: 'layout-grid-4',
                    count: 4,
                    cellRatios: [containerRatio, containerRatio, containerRatio, containerRatio],
                    nameClass: 'layout-grid-4'
                },
                {
                    name: 'layout-split-3',
                    count: 3,
                    cellRatios: [containerRatio * 1.15 / 2, containerRatio * 0.85, containerRatio * 0.85],
                    nameClass: 'layout-split-3'
                },
                {
                    name: 'layout-polaroids',
                    count: 4,
                    cellRatios: [containerRatio * 0.94, containerRatio * 0.94, containerRatio * 0.94, containerRatio * 0.94],
                    nameClass: 'layout-polaroids'
                }
            ];

            // Matching function: pairs photos to layout cells based on aspect ratios
            function findMatchingPhotosForLayout(layout, candidates) {
                const matched = [];
                const tempCandidates = [...candidates];
                
                for (let i = 0; i < layout.cellRatios.length; i++) {
                    const targetRatio = layout.cellRatios[i];
                    let bestMatchIndex = -1;
                    let bestScore = -1;
                    
                    for (let j = 0; j < tempCandidates.length; j++) {
                        const photo = tempCandidates[j];
                        // Aspect ratio similarity score (1 = perfect match, 0 = completely different)
                        const score = 1 - Math.abs(photo.ratio - targetRatio) / Math.max(photo.ratio, targetRatio);
                        
                        // Minimum score of 0.72 allows about 28% deviation in aspect ratio
                        if (score > 0.72 && score > bestScore) {
                            bestScore = score;
                            bestMatchIndex = j;
                        }
                    }
                    
                    if (bestMatchIndex !== -1) {
                        matched.push(tempCandidates[bestMatchIndex]);
                        tempCandidates.splice(bestMatchIndex, 1);
                    } else {
                        return null; // Layout cannot be satisfied with valid matches
                    }
                }
                return matched;
            }

            // Find all collage layouts that can be satisfied by current candidates
            const satisfiedLayouts = [];
            layoutsConfig.forEach(layout => {
                const matchedPhotos = findMatchingPhotosForLayout(layout, validCandidates);
                if (matchedPhotos) {
                    satisfiedLayouts.push({
                        config: layout,
                        photos: matchedPhotos
                    });
                }
            });

            // Decide layout: 40% chance of collage if any satisfied, else 60% single view fallback
            const isCollage = satisfiedLayouts.length > 0 && Math.random() < 0.4;
            const preloadPromises = [];
            let selectedPhotos = [];

            if (isCollage) {
                singleView.style.display = 'none';
                collageView.style.display = 'grid';

                const layout = satisfiedLayouts[Math.floor(Math.random() * satisfiedLayouts.length)];
                selectedPhotos = layout.photos.map(p => p.src);

                collageView.className = `slide-collage-view ${layout.config.nameClass}`;
                
                // Background blur is set to the first photo
                preloadPromises.push(preloadImage(bgImg, selectedPhotos[0]));

                const imgWrappers = collageView.querySelectorAll('.collage-img-wrapper');
                for (let i = 0; i < 4; i++) {
                    const wrapper = imgWrappers[i];
                    const bgBlur = wrapper.querySelector('.collage-img-bg-blur');
                    const img = wrapper.querySelector('.collage-img');

                    if (i < selectedPhotos.length) {
                        wrapper.style.display = 'block';

                        // Polaroid layouts have random rotates and offsets
                        if (layout.config.name === 'layout-polaroids') {
                            const rot = (Math.random() * 8 - 4).toFixed(1); // -4deg to 4deg
                            const shiftX = (Math.random() * 12 - 6).toFixed(1); // -6px to 6px
                            const shiftY = (Math.random() * 12 - 6).toFixed(1); // -6px to 6px
                            wrapper.style.transform = `rotate(${rot}deg) translate(${shiftX}px, ${shiftY}px)`;
                            if (bgBlur) bgBlur.style.display = 'none'; // Polaroids don't need blur
                        } else {
                            wrapper.style.transform = '';
                            if (bgBlur) bgBlur.style.display = 'block';
                        }

                        preloadPromises.push(preloadImage(img, selectedPhotos[i]));
                        if (bgBlur && layout.config.name !== 'layout-polaroids') {
                            preloadPromises.push(preloadImage(bgBlur, selectedPhotos[i]));
                        }
                    } else {
                        wrapper.style.display = 'none';
                        img.removeAttribute('src');
                        if (bgBlur) bgBlur.removeAttribute('src');
                    }
                }
            } else {
                // Single View Mode: Select the very first valid photo
                singleView.style.display = 'block';
                collageView.style.display = 'none';

                const firstValidCandidate = validCandidates.length > 0 ? validCandidates[0] : null;
                const photoSrc = firstValidCandidate ? firstValidCandidate.src : shuffledPhotos[0];
                selectedPhotos = [photoSrc];

                const fgImg = singleView.querySelector('.slide-fg-contain');
                preloadPromises.push(preloadImage(fgImg, photoSrc));
                preloadPromises.push(preloadImage(bgImg, photoSrc));
            }

            // Remove selected photos from queue so they aren't repeated
            selectedPhotos.forEach(src => {
                const idx = shuffledPhotos.indexOf(src);
                if (idx !== -1) {
                    shuffledPhotos.splice(idx, 1);
                }
            });

            // Complete transition once preloading is finished
            Promise.all(preloadPromises).then(() => {
                activeTrack.classList.remove('active');
                inactiveTrack.classList.add('active');
                activeTrack = inactiveTrack;
            });
        });
    }

    // Load first image immediately
    loadPhotosList().then(() => {
        if (photos.length > 0) {
            shuffledPhotos = shuffleArray(photos);
            const firstPhoto = shuffledPhotos[0];
            shuffledPhotos.splice(0, 1);

            const bgA = trackA.querySelector('.slide-bg-blur');
            const fgA = trackA.querySelector('.slide-fg-contain');

            trackA.querySelector('.slide-single-view').style.display = 'block';
            trackA.querySelector('.slide-collage-view').style.display = 'none';

            bgA.src = firstPhoto;
            fgA.src = firstPhoto;
        }

        // Start sliding loop
        setInterval(transitionToNext, slideDuration);
    });
}

/* =============================================================
 * MODULE 4: ANIMATED WEATHER TRACKER (OPEN-METEO)
 * ============================================================= */
async function initWeather() {
    const tempMain = document.getElementById('weather-temp-main');
    const highlowMain = document.getElementById('weather-highlow-main');
    const condMain = document.getElementById('weather-cond-main');
    const animIcon = document.getElementById('weather-anim-icon');
    const forecastBox = document.getElementById('weather-forecast-box');

    const lat = 38.4232;
    const lon = -77.4080;
    const apiUrl = `https://api.open-meteo.com/v1/forecast?latitude=${lat}&longitude=${lon}&current=temperature_2m,weather_code&daily=weather_code,temperature_2m_max,temperature_2m_min&temperature_unit=fahrenheit&timezone=America%2FNew_York`;

    const weatherCodes = {
        0: { desc: "Clear Sky", emoji: "☀️", anim: "sun" },
        1: { desc: "Mainly Clear", emoji: "🌤️", anim: "partly-cloudy" },
        2: { desc: "Partly Cloudy", emoji: "⛅", anim: "partly-cloudy" },
        3: { desc: "Overcast", emoji: "☁️", anim: "cloudy" },
        45: { desc: "Foggy", emoji: "🌫️", anim: "cloudy" },
        48: { desc: "Rime Fog", emoji: "🌫️", anim: "cloudy" },
        51: { desc: "Light Drizzle", emoji: "🌧️", anim: "rainy" },
        53: { desc: "Moderate Drizzle", emoji: "🌧️", anim: "rainy" },
        55: { desc: "Dense Drizzle", emoji: "🌧️", anim: "rainy" },
        61: { desc: "Slight Rain", emoji: "🌧️", anim: "rainy" },
        63: { desc: "Moderate Rain", emoji: "🌧️", anim: "rainy" },
        65: { desc: "Heavy Rain", emoji: "🌧️", anim: "rainy" },
        71: { desc: "Slight Snow", emoji: "❄️", anim: "snowy" },
        73: { desc: "Moderate Snow", emoji: "❄️", anim: "snowy" },
        75: { desc: "Heavy Snow", emoji: "❄️", anim: "snowy" },
        77: { desc: "Snow Grains", emoji: "❄️", anim: "snowy" },
        80: { desc: "Slight Showers", emoji: "🌧️", anim: "rainy" },
        81: { desc: "Moderate Showers", emoji: "🌧️", anim: "rainy" },
        82: { desc: "Violent Showers", emoji: "🌧️", anim: "rainy" },
        85: { desc: "Slight Snow Showers", emoji: "❄️", anim: "snowy" },
        86: { desc: "Heavy Snow Showers", emoji: "❄️", anim: "snowy" },
        95: { desc: "Thunderstorm", emoji: "⛈️", anim: "thunderstorm" },
        96: { desc: "Thunderstorm with Hail", emoji: "⛈️", anim: "thunderstorm" },
        99: { desc: "Thunderstorm with Heavy Hail", emoji: "⛈️", anim: "thunderstorm" }
    };

    function getWeatherAnimSVG(type) {
        switch (type) {
            case 'sun':
                return `
                <div class="weather-3d-wrapper">
                    <svg class="weather-layer layer-sun-rays" viewBox="0 0 100 100">
                        <g class="svg-sun-rays">
                            <line x1="50" y1="18" x2="50" y2="6"/>
                            <line x1="50" y1="82" x2="50" y2="94"/>
                            <line x1="18" y1="50" x2="6" y2="50"/>
                            <line x1="82" y1="50" x2="94" y2="50"/>
                            <line x1="27" y1="27" x2="18" y2="18"/>
                            <line x1="73" y1="73" x2="82" y2="82"/>
                            <line x1="27" y1="73" x2="18" y2="82"/>
                            <line x1="73" y1="27" x2="82" y2="18"/>
                        </g>
                    </svg>
                    <svg class="weather-layer layer-sun" viewBox="0 0 100 100">
                        <circle class="svg-sun" cx="50" cy="50" r="18"/>
                    </svg>
                </div>`;
            case 'partly-cloudy':
                return `
                <div class="weather-3d-wrapper">
                    <svg class="weather-layer layer-cloud-back" viewBox="0 0 100 100">
                        <path class="svg-cloud-back" d="M32 62h32a13 13 0 0 0 0-26h-2a16 16 0 0 0-30 7a11 11 0 0 0 0 19z"/>
                    </svg>
                    <svg class="weather-layer layer-sun" viewBox="0 0 100 100">
                        <circle class="svg-sun" cx="36" cy="36" r="14"/>
                    </svg>
                    <svg class="weather-layer layer-cloud-front" viewBox="0 0 100 100">
                        <path class="svg-cloud" d="M26 68h34a13 13 0 0 0 0-26h-2a16 16 0 0 0-30 7a11 11 0 0 0-2 19z"/>
                    </svg>
                </div>`;
            case 'rainy':
                return `
                <div class="weather-3d-wrapper">
                    <svg class="weather-layer layer-cloud-front" viewBox="0 0 100 100">
                        <path class="svg-cloud" d="M26 56h34a13 13 0 0 0 0-26h-2a16 16 0 0 0-30 7a11 11 0 0 0-2 19z"/>
                    </svg>
                    <svg class="weather-layer layer-rain" viewBox="0 0 100 100">
                        <g class="svg-rain-drops">
                            <line x1="32" y1="64" x2="30" y2="76"/>
                            <line x1="43" y1="64" x2="41" y2="76"/>
                            <line x1="54" y1="64" x2="52" y2="76"/>
                        </g>
                    </svg>
                </div>`;
            case 'thunderstorm':
                return `
                <div class="weather-3d-wrapper">
                    <svg class="weather-layer layer-cloud-front" viewBox="0 0 100 100">
                        <path class="svg-cloud" d="M26 52h34a13 13 0 0 0 0-26h-2a16 16 0 0 0-30 7a11 11 0 0 0-2 19z"/>
                    </svg>
                    <svg class="weather-layer layer-lightning" viewBox="0 0 100 100">
                        <polygon class="svg-lightning" points="43,54 36,68 42,68 37,80 49,66 43,66"/>
                    </svg>
                </div>`;
            case 'snowy':
                return `
                <div class="weather-3d-wrapper">
                    <svg class="weather-layer layer-cloud-front" viewBox="0 0 100 100">
                        <path class="svg-cloud" d="M26 56h34a13 13 0 0 0 0-26h-2a16 16 0 0 0-30 7a11 11 0 0 0-2 19z"/>
                    </svg>
                    <svg class="weather-layer layer-snow" viewBox="0 0 100 100">
                        <circle cx="32" cy="66" r="2.5" fill="#e2e8f0"/>
                        <circle cx="43" cy="68" r="2" fill="#fff"/>
                        <circle cx="54" cy="66" r="2.5" fill="#e2e8f0"/>
                    </svg>
                </div>`;
            case 'cloudy':
            default:
                return `
                <div class="weather-3d-wrapper">
                    <svg class="weather-layer layer-cloud-back" viewBox="0 0 100 100">
                        <path class="svg-cloud-back" d="M34 60h32a13 13 0 0 0 0-26h-2a16 16 0 0 0-30 7a11 11 0 0 0 0 19z"/>
                    </svg>
                    <svg class="weather-layer layer-cloud-front" viewBox="0 0 100 100">
                        <path class="svg-cloud" d="M26 66h34a13 13 0 0 0 0-26h-2a16 16 0 0 0-30 7a11 11 0 0 0-2 19z"/>
                    </svg>
                </div>`;
        }
    }

    async function fetchWeather() {
        try {
            const res = await fetch(apiUrl);
            if (!res.ok) throw new Error("Weather service offline");
            const data = await res.json();

            // Render Current Conditions
            const currTemp = Math.round(data.current.temperature_2m);
            const currCode = data.current.weather_code;
            const todayHigh = Math.round(data.daily.temperature_2m_max[0]);
            const todayLow = Math.round(data.daily.temperature_2m_min[0]);

            const info = weatherCodes[currCode] || { desc: "Clear", emoji: "☀️", anim: "sun" };

            if (tempMain) tempMain.textContent = `${currTemp}°F`;
            if (highlowMain) highlowMain.innerHTML = `▲ ${todayHigh}°F &nbsp;&nbsp; ▼ ${todayLow}°F`;
            if (condMain) condMain.textContent = info.desc;

            // Render SVG Animation
            if (animIcon) animIcon.innerHTML = getWeatherAnimSVG(info.anim);

            // Render 3-Day Forecast
            if (forecastBox) {
                forecastBox.innerHTML = "";
                const days = ["Today", "Tomorrow", "Next Day"];
                
                for (let i = 0; i < 3; i++) {
                    const dayCode = data.daily.weather_code[i];
                    const dayHigh = Math.round(data.daily.temperature_2m_max[i]);
                    const dayLow = Math.round(data.daily.temperature_2m_min[i]);
                    const dayInfo = weatherCodes[dayCode] || { desc: "Clear", emoji: "☀️" };
                    
                    const forecastCard = document.createElement('div');
                    forecastCard.className = "forecast-day-card";
                    forecastCard.innerHTML = `
                        <span class="forecast-day-name">${days[i]}</span>
                        <span class="forecast-emoji">${dayInfo.emoji}</span>
                        <span class="forecast-temp-range">
                            <span class="forecast-high">${dayHigh}°</span>
                            <span class="forecast-low">${dayLow}°</span>
                        </span>
                    `;
                    forecastBox.appendChild(forecastCard);
                }
            }
        } catch (e) {
            console.error("Open-Meteo systems sync error:", e);
            if (condMain) condMain.textContent = "Weather sync error";
        }
    }

    fetchWeather();
    setInterval(fetchWeather, 900000); // Syncs every 15 minutes
}

/* =============================================================
 * MODULE 5: GOOGLE CALENDAR TIMELINE WIDGET
 * ============================================================= */
async function initCalendar() {
    const calendarGrid = document.getElementById('calendar-grid');
    const calendarDetails = document.getElementById('calendar-details');
    if (!calendarGrid || !calendarDetails) return;

    let calendarEvents = [];
    const today = new Date();
    
    // Calculate calendar grid dates (rolling 2-week timeline) starting at midnight local time
    const calendarStartDate = new Date(today.getFullYear(), today.getMonth(), today.getDate());
    calendarStartDate.setDate(calendarStartDate.getDate() - calendarStartDate.getDay()); // Start on Sunday

    async function loadCalendar() {
        try {
            const res = await fetch('/api/calendar');
            if (res.ok) {
                calendarEvents = await res.json();
            }
        } catch (e) {
            console.error("Could not load calendar.json feed", e);
        }

        renderCalendarGrid();
    }

    function renderCalendarGrid() {
        calendarGrid.innerHTML = "";
        
        // Render 14 grid slots (2 weeks)
        for (let i = 0; i < 14; i++) {
            const cellDate = new Date(calendarStartDate);
            cellDate.setDate(calendarStartDate.getDate() + i);

            const isToday = cellDate.toDateString() === today.toDateString();
            
            // Format dateStr in local timezone instead of ISO/UTC string to prevent timezone offset shifts
            const year = cellDate.getFullYear();
            const month = String(cellDate.getMonth() + 1).padStart(2, '0');
            const day = String(cellDate.getDate()).padStart(2, '0');
            const dateStr = `${year}-${month}-${day}`;

            // Filter events happening on this specific date
            const daysEvents = calendarEvents.filter(event => {
                const eventDate = event.start.split('T')[0];
                return eventDate === dateStr;
            });

            // Create cell element
            const cell = document.createElement('div');
            cell.className = `calendar-day ${isToday ? 'today' : ''}`;
            cell.dataset.date = dateStr;

            cell.innerHTML = `
                <span class="calendar-day-num">${cellDate.getDate()}</span>
                <div class="calendar-event-indicator"></div>
            `;

            // Append dots for events (max 3 dots for visuals)
            const indicator = cell.querySelector('.calendar-event-indicator');
            const dotCount = Math.min(daysEvents.length, 3);
            for (let d = 0; d < dotCount; d++) {
                const dot = document.createElement('span');
                dot.className = 'calendar-dot';
                indicator.appendChild(dot);
            }

            // Click listener
            cell.addEventListener('click', () => {
                document.querySelectorAll('.calendar-day').forEach(c => c.classList.remove('selected'));
                cell.classList.add('selected');
                showDayDetails(cellDate, daysEvents);
            });

            calendarGrid.appendChild(cell);

            // Auto-select Today on initial load
            if (isToday) {
                cell.classList.add('selected');
                showDayDetails(cellDate, daysEvents);
            }
        }
    }

    function showDayDetails(date, events) {
        const dateStrOptions = { weekday: 'long', month: 'short', day: 'numeric' };
        const headerText = date.toLocaleDateString('en-US', dateStrOptions);
        
        calendarDetails.innerHTML = `
            <div class="detail-day-header">${headerText}</div>
        `;

        if (events.length === 0) {
            calendarDetails.innerHTML += `<p class="select-prompt">No family events scheduled.</p>`;
            return;
        }

        // Sort events by starting hour
        events.sort((a, b) => new Date(a.start) - new Date(b.start));

        events.forEach(event => {
            const startHour = new Date(event.start);
            const endHour = new Date(event.end);
            
            // Format hours
            const formatTime = (d) => {
                let h = d.getHours();
                const m = String(d.getMinutes()).padStart(2, '0');
                const am = h >= 12 ? 'PM' : 'AM';
                h = h % 12 || 12;
                return `${h}:${m} ${am}`;
            };

            const timeRange = formatTime(startHour) + " - " + formatTime(endHour);
            const locationStr = event.location ? `<div class="detail-event-loc"><i class="fa-solid fa-location-dot"></i> ${event.location}</div>` : '';

            const card = document.createElement('div');
            card.className = "detail-event-card";
            card.innerHTML = `
                <div class="detail-event-time">${timeRange}</div>
                <div class="detail-event-title">${event.summary}</div>
                ${locationStr}
            `;
            calendarDetails.appendChild(card);
        });
    }

    loadCalendar();
    setInterval(loadCalendar, 300000); // Check calendar.json updates every 5 minutes
}

/* =============================================================
 * MODULE 6: DAILY JOKE / SMILE WIDGET
 * ============================================================= */
function initJokeWidget() {
    const jokeText = document.getElementById('joke-text');
    if (!jokeText) return;

    const fallbackJokes = [
        "Why do birds fly south for the winter? Because it's too far to walk!",
        "What do you call a factory that makes okay products? A satisfactory.",
        "What do you call a sleeping bull? A bulldozer.",
        "Why did the gym close down? It just didn't work out!",
        "Why did the scarecrow win an award? Because he was outstanding in his field!"
    ];

    async function fetchDailyJoke() {
        try {
            const response = await fetch('https://icanhazdadjoke.com/', {
                headers: { 'Accept': 'application/json' }
            });
            if (response.ok) {
                const data = await response.json();
                jokeText.textContent = data.joke;
                return;
            }
        } catch (e) {
            console.warn("Public Dad Joke API rate limited or offline. Reverting to offline bank.", e);
        }
        
        // Return random joke from fallback list
        const randIdx = Math.floor(Math.random() * fallbackJokes.length);
        jokeText.textContent = fallbackJokes[randIdx];
    }

    fetchDailyJoke();
    // Rotate jokes every 12 hours
    setInterval(fetchDailyJoke, 43200000);
}

/* =============================================================
 * MODULE 7: FAMILY LEADERBOARD & STAR OF THE DAY WIDGETS
 * ============================================================= */
function initLeaderboard() {
    const listBody = document.getElementById('leaderboard-list-body');
    const starName = document.getElementById('star-of-day-name');
    if (!listBody || !starName) return;

    const themeEmojis = {
        "dinosaur": "🦕",
        "gamer": "🎮",
        "princess": "👑",
        "mecha": "🤖"
    };

    async function fetchLeaderboard() {
        try {
            const res = await fetch('/api/leaderboard');
            if (res.ok) {
                const data = await res.json();
                updateLeaderboardUI(data);
            }
        } catch (e) {
            console.error("Could not fetch leaderboard:", e);
        }
    }

    function updateLeaderboardUI(data) {
        // Render dynamic rows
        listBody.innerHTML = "";
        data.leaderboard.forEach(child => {
            let avatarHTML = '';
            if (child.name.toLowerCase() === 'noelle') {
                avatarHTML = `<img src="assets/avatars/noelle-princess.png" style="width: 28px; height: 28px; border-radius: 50%; object-fit: cover; border: 1.5px solid #a855f7; box-shadow: 0 0 6px rgba(168, 85, 247, 0.45); flex-shrink: 0;" alt="Noelle">`;
            } else {
                const emoji = themeEmojis[child.theme ? child.theme.toLowerCase() : ''] || "👤";
                avatarHTML = `<span>${emoji}</span>`;
            }
            const row = document.createElement('div');
            row.className = "leaderboard-row";
            row.innerHTML = `
                <a href="/child/${child.name.toLowerCase()}" class="child-link-glow" style="text-decoration: none;">
                    <span class="child-name" style="cursor: pointer; transition: all 0.2s ease; display: inline-flex; align-items: center; gap: 8px;">${avatarHTML} ${child.name}</span>
                </a>
                <span class="child-points">${child.points} pts</span>
            `;
            listBody.appendChild(row);
        });

        // Render Star of the Day
        if (data.star_of_the_day) {
            starName.textContent = data.star_of_the_day;
        }

        // Apply seasonal theme override if present
        if (data.seasonal) {
            applySeasonalThemes(data.seasonal);
        }
    }

    function applySeasonalThemes(seasonal) {
        const root = document.documentElement;
        if (seasonal.accent_blue) {
            root.style.setProperty('--accent-blue', seasonal.accent_blue);
        }
        if (seasonal.body_tint) {
            root.style.setProperty('--body-tint', seasonal.body_tint);
        }
    }

    // Fetch initial leaderboard state on boot
    fetchLeaderboard();

    // Setup Real-time SSE pipelines
    const evtSource = new EventSource("/api/events");
    
    // Heartbeat/connected message to apply seasonal themes instantly
    evtSource.onmessage = function(event) {
        try {
            const evData = JSON.parse(event.data);
            if (evData.type === 'connected' && evData.seasonal) {
                applySeasonalThemes(evData.seasonal);
            }
        } catch (e) {
            console.error("SSE parsed error:", e);
        }
    };

    evtSource.addEventListener("chore_update", (e) => {
        try {
            const evData = JSON.parse(e.data);
            if (evData.leaderboard) {
                updateLeaderboardUI(evData.leaderboard);
            } else {
                fetchLeaderboard();
            }
        } catch (err) {
            fetchLeaderboard();
        }
    });

    evtSource.addEventListener("admin_config_change", (e) => {
        try {
            const evData = JSON.parse(e.data);
            if (evData.leaderboard) {
                updateLeaderboardUI(evData);
            } else {
                fetchLeaderboard();
            }
        } catch (err) {
            fetchLeaderboard();
        }
    });
}

/* =============================================================
 * MODULE 8: AUTOMATED KIOSK INACTIVITY ROTATOR (index.html -> /child)
 * ============================================================= */
function initKioskRotator() {
    const rotationTime = 90000; // 90 seconds of inactivity before rotating
    let rotatorTimeout = setTimeout(rotateToChildPage, rotationTime);

    function rotateToChildPage() {
        console.log("[Kiosk] Rotating to child chore summary page...");
        window.location.href = '/child';
    }

    function resetRotatorTimer() {
        clearTimeout(rotatorTimeout);
        rotatorTimeout = setTimeout(rotateToChildPage, rotationTime);
    }

    // Capture standard user interactions
    const events = ['mousedown', 'mousemove', 'keypress', 'scroll', 'touchstart'];
    events.forEach(name => {
        document.addEventListener(name, resetRotatorTimer, { passive: true });
    });
}