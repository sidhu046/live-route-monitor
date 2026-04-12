"""
step6_live_monitor.py
======================
STEP 6 — Generate a live GPS speed monitor HTML page.

WHAT THIS PRODUCES
------------------
  live_monitor.html   — open in any browser (Chrome recommended)
                        Works on desktop (simulate GPS via DevTools)
                        Works on mobile (uses real GPS chip)

FEATURES
--------
  1. ROUTE DISPLAY      : Shows your pre-computed route on a Leaflet map,
                          coloured by risk level (green/yellow/red).
                          All intermediate waypoints are shown as blue markers.

  2. REAL-TIME SPEED    : Tracks your live GPS position using the browser
                          Geolocation API (watchPosition).
                          Speed is calculated using the haversine formula
                          from successive GPS fixes — NOT random numbers.
                          A 3-sample median filter smooths GPS noise.

  3. SPEED LIMIT LOOKUP : For every GPS position, finds the nearest route
                          segment and reads its recommended_speed_kmh.
                          Limit changes automatically at curves and turns.

  4. WARNING SYSTEM     : Compares actual speed to the current segment limit.
                          - Under limit      → GREEN  "Safe"
                          - 1–9 km/h over   → YELLOW "Slow down!"
                          - 10+ km/h over   → RED    flashing "DANGER"

HOW TO TEST LOCALLY (desktop)
------------------------------
  Step 1: Run the full pipeline:
    python main.py

  Step 2: Serve with HTTPS (Geolocation API requires HTTPS):
    openssl req -x509 -newkey rsa:2048 -keyout key.pem -out cert.pem \\
      -days 365 -nodes -subj "/CN=localhost"

    cd outputs/<route_name>
    python3 -c "
    import ssl, http.server
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain('../../cert.pem', '../../key.pem')
    httpd = http.server.HTTPServer(('localhost', 8443),
            http.server.SimpleHTTPRequestHandler)
    httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
    print('Open: https://localhost:8443/live_monitor.html')
    httpd.serve_forever()
    "

  Step 3: Open https://localhost:8443/live_monitor.html in Chrome.
          Accept the self-signed certificate warning.

  Step 4: Simulate GPS movement in Chrome DevTools:
    F12 → More tools → Sensors → Location
    Change latitude/longitude to move the position.
    The speed widget updates with each change.

HOW TO USE ON MOBILE
---------------------
  1. Copy live_monitor.html to a web server (any free hosting, e.g. GitHub Pages)
     OR open it directly if your mobile browser allows file:// GPS access.
  2. Open on your phone — allow location permission.
  3. Drive / walk along the route — speed updates in real time.

NOTE: GPS accuracy on desktop is ~1000 m (cell tower based).
      On mobile with GPS chip, accuracy is ~5–15 m.
      Use DevTools Sensors for accurate desktop testing.
"""

import os
import json


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

def generate_live_monitor(segments: list, route: dict,
                           save_dir: str) -> str:
    """
    Build live_monitor.html and return its file path.

    Parameters
    ----------
    segments : list of segment dicts from step3 (lat, lon,
               recommended_speed_kmh, risk_level, turn_type, etc.)
    route    : route dict from step1 (distance_txt, source,
               waypoints, origin, destination)
    save_dir : output directory, e.g. outputs/RGUKT_Nuzvid_SAC_to_MainGate

    Returns
    -------
    Path to the generated live_monitor.html file.
    """
    # Build a compact version of the route for embedding in HTML.
    # Only the fields needed by the browser are included to keep file size small.
    has_friction = segments and "friction_mu" in segments[0]
    route_points = []
    for s in segments:
        pt = {
            "lat"  : s["lat"],
            "lon"  : s["lon"],
            "limit": s.get("adjusted_speed_kmh",
                           s.get("recommended_speed_kmh", 40)),  # prefer friction-adjusted
            "limit_orig": s.get("recommended_speed_kmh", 40),    # original geometry limit
            "risk" : s.get("risk_level", "low"),
            "turn" : s.get("turn_type", "straight"),
            "angle": s.get("turning_angle_deg", 180.0),
        }
        if has_friction:
            pt["mu"]       = s.get("friction_mu", 0.80)
            pt["f_risk"]   = s.get("friction_risk", "low")
            pt["stop_m"]   = s.get("stopping_dist_m", 0)
            pt["road_type"]= s.get("road_type_label", s.get("road_type", ""))
            pt["road_cond"]= s.get("road_condition_label", s.get("road_condition", ""))
        route_points.append(pt)

    route_json   = json.dumps(route_points)
    route_name   = route.get("distance_txt", "Route")
    route_src    = route.get("source", "")
    waypoints    = route.get("waypoints", [])
    origin       = route.get("origin", (segments[0]["lat"], segments[0]["lon"]))
    destination  = route.get("destination", (segments[-1]["lat"], segments[-1]["lon"]))

    # Build waypoints JS array for the map
    wpt_js = json.dumps([[w[0], w[1]] for w in waypoints])

    html = _build_html(route_json, route_name, route_src,
                       wpt_js, origin, destination)

    out_path = os.path.join(save_dir, "live_monitor.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"  Live monitor → {out_path}")
    return out_path


# ─────────────────────────────────────────────────────────────────────────────
# HTML BUILDER
# ─────────────────────────────────────────────────────────────────────────────

def _build_html(route_json: str, route_name: str, route_src: str,
                wpt_js: str, origin: tuple, destination: tuple) -> str:
    """Build the complete self-contained HTML string."""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Live Speed Monitor — {route_name}</title>

<!-- Leaflet CSS (free CDN, no API key needed) -->
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>

<style>
/* ── Reset & base ── */
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{
  font-family: system-ui, -apple-system, monospace;
  background: #0d1117;
  color: #e6edf3;
  height: 100vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}}

/* ── Top info bar ── */
#info-bar {{
  background: #161b22;
  padding: 6px 16px;
  border-bottom: 1px solid #30363d;
  font-size: 0.72rem;
  color: #8b949e;
  display: flex;
  gap: 20px;
  flex-wrap: wrap;
  align-items: center;
  flex-shrink: 0;
}}
#info-bar span {{ white-space: nowrap; }}
#gps-status {{ color: #d29922; }}
#gps-status.active {{ color: #3fb950; }}

/* ── Map fills middle space ── */
#map {{ flex: 1; min-height: 0; }}

/* ── Bottom dashboard panel ── */
#dashboard {{
  background: #161b22;
  border-top: 2px solid #30363d;
  padding: 10px 16px;
  display: flex;
  gap: 12px;
  align-items: stretch;
  flex-wrap: wrap;
  flex-shrink: 0;
}}

/* ── Individual metric boxes ── */
.metric {{
  text-align: center;
  min-width: 80px;
  background: #0d1117;
  border: 1px solid #30363d;
  border-radius: 8px;
  padding: 8px 12px;
}}
.metric .value {{
  font-size: 1.9rem;
  font-weight: 700;
  line-height: 1;
  font-variant-numeric: tabular-nums;
}}
.metric .label {{
  font-size: 0.65rem;
  color: #8b949e;
  margin-top: 3px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}}

/* ── Colour-coded speed values ── */
#speed-val {{ color: #58a6ff; }}
#limit-val {{ color: #3fb950; }}
#acc-val   {{ color: #d29922; }}
#turn-val  {{ font-size: 0.85rem; color: #bc8cff; }}
#dist-val  {{ color: #f0883e; font-size: 1.2rem; }}

/* ── Warning/status box ── */
#status-box {{
  flex: 1;
  min-width: 200px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  text-align: center;
  font-weight: 700;
  font-size: 1rem;
  padding: 10px 16px;
  border: 2px solid #30363d;
  background: #21262d;
  color: #8b949e;
  transition: background 0.25s, border-color 0.25s, color 0.25s;
  line-height: 1.4;
}}

/* Warning states */
#status-box.stationary {{
  background: #0d1117;
  border-color: #30363d;
  color: #8b949e;
}}
#status-box.safe {{
  background: #0d2318;
  border-color: #3fb950;
  color: #3fb950;
}}
#status-box.warn {{
  background: #2e1f00;
  border-color: #d29922;
  color: #d29922;
}}
#status-box.danger {{
  background: #2d1117;
  border-color: #f85149;
  color: #f85149;
  animation: danger-flash 0.55s ease-in-out infinite alternate;
}}

@keyframes danger-flash {{
  from {{ opacity: 1;   border-color: #f85149; }}
  to   {{ opacity: 0.5; border-color: #ff8080; }}
}}

/* ── Accuracy bar ── */
#acc-bar-wrap {{
  width: 100%;
  height: 3px;
  background: #21262d;
  border-radius: 2px;
  margin-top: 4px;
  overflow: hidden;
}}
#acc-bar {{
  height: 3px;
  background: #3fb950;
  border-radius: 2px;
  transition: width 0.5s, background 0.5s;
  width: 100%;
}}
</style>
</head>
<body>

<!-- Top status bar -->
<div id="info-bar">
  <span>&#128507; {route_name} &nbsp;|&nbsp; {route_src}</span>
  <span id="gps-status">GPS: waiting for signal…</span>
  <span id="accuracy-info">Accuracy: —</span>
  <span id="segment-info">Nearest segment: —</span>
</div>

<!-- Leaflet map -->
<div id="map"></div>

<!-- Dashboard panel -->
<div id="dashboard">

  <!-- Actual speed -->
  <div class="metric">
    <div class="value" id="speed-val">—</div>
    <div class="label">km/h actual</div>
  </div>

  <!-- Speed limit from route segment -->
  <div class="metric">
    <div class="value" id="limit-val">—</div>
    <div class="label">km/h limit</div>
  </div>

  <!-- GPS accuracy -->
  <div class="metric" style="min-width:100px;">
    <div class="value" id="acc-val">—</div>
    <div class="label">GPS accuracy (m)</div>
    <div id="acc-bar-wrap"><div id="acc-bar"></div></div>
  </div>

  <!-- Turn type on current segment -->
  <div class="metric">
    <div class="value" id="turn-val">—</div>
    <div class="label">segment type</div>
  </div>

  <!-- Distance to destination -->
  <div class="metric">
    <div class="value" id="dist-val">—</div>
    <div class="label">dist to end (m)</div>
  </div>

  <!-- Stopping distance (from friction) -->
  <div class="metric">
    <div class="value" id="stop-val" style="color:#f0883e">—</div>
    <div class="label">stop dist (m)</div>
  </div>

  <!-- Road type & condition panel (shown when friction data exists) -->
  <div class="metric" id="road-panel" style="min-width:160px;text-align:left;display:none">
    <div style="font-size:0.68rem;color:#8b949e;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:4px">Road info</div>
    <div id="road-type-val" style="font-size:0.82rem;font-weight:600;color:#bc8cff">—</div>
    <div id="road-cond-val" style="font-size:0.75rem;color:#8b949e;margin-top:2px">—</div>
    <div id="friction-val"  style="font-size:0.75rem;color:#f0883e;margin-top:2px">μ = —</div>
  </div>

  <!-- Warning / status box -->
  <div id="status-box" class="stationary">
    Waiting for GPS signal…
  </div>

</div>

<!-- Leaflet JS -->
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>

<script>
// ════════════════════════════════════════════════════════════════
// ROUTE DATA  — embedded by Python at generation time
// Each element: {{ lat, lon, limit (km/h), risk, turn, angle }}
// ════════════════════════════════════════════════════════════════
const ROUTE = {route_json};

// Intermediate waypoints [[lat, lon], ...]
const WAYPOINTS = {wpt_js};

// Origin and destination
const ORIGIN      = [{origin[0]}, {origin[1]}];
const DESTINATION = [{destination[0]}, {destination[1]}];

// ════════════════════════════════════════════════════════════════
// MAP SETUP
// ════════════════════════════════════════════════════════════════
const map = L.map('map', {{ zoomControl: true }});

L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
  attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
  maxZoom: 19
}}).addTo(map);

// ── Draw route coloured by risk ──────────────────────────────────
const riskColor = {{
  low    : '#3fb950',
  medium : '#d29922',
  high   : '#f85149'
}};

for (let i = 0; i < ROUTE.length - 1; i++) {{
  L.polyline(
    [[ROUTE[i].lat, ROUTE[i].lon], [ROUTE[i+1].lat, ROUTE[i+1].lon]],
    {{
      color   : riskColor[ROUTE[i].risk] || '#58a6ff',
      weight  : 5,
      opacity : 0.85
    }}
  ).bindPopup(
    '<b>Segment #' + i + '</b><br>' +
    'Limit: ' + ROUTE[i].limit + ' km/h<br>' +
    'Risk: ' + ROUTE[i].risk + '<br>' +
    'Type: ' + ROUTE[i].turn.replace(/_/g,' ')
  ).addTo(map);
}}

// ── Start marker ─────────────────────────────────────────────────
const startIcon = L.divIcon({{
  html: '<div style="width:20px;height:20px;border-radius:50%;' +
        'background:#3fb950;border:3px solid #fff;' +
        'box-shadow:0 0 8px #3fb95088"></div>',
  iconSize:[20,20], iconAnchor:[10,10], className:''
}});
L.marker(ORIGIN, {{icon: startIcon}})
  .bindPopup('<b>START</b><br>' + ORIGIN[0].toFixed(6) + ', ' + ORIGIN[1].toFixed(6))
  .addTo(map);

// ── Intermediate waypoint markers ────────────────────────────────
const wptIcon = L.divIcon({{
  html: '<div style="width:14px;height:14px;background:#58a6ff;' +
        'border:2px solid #fff;transform:rotate(45deg);' +
        'box-shadow:0 0 6px #58a6ff88"></div>',
  iconSize:[14,14], iconAnchor:[7,7], className:''
}});
WAYPOINTS.forEach(function(w, idx) {{
  L.marker(w, {{icon: wptIcon}})
    .bindPopup('<b>Waypoint ' + (idx+1) + '</b><br>' +
               w[0].toFixed(6) + ', ' + w[1].toFixed(6))
    .addTo(map);
}});

// ── End marker ───────────────────────────────────────────────────
const endIcon = L.divIcon({{
  html: '<div style="width:20px;height:20px;border-radius:3px;' +
        'background:#f85149;border:3px solid #fff;' +
        'box-shadow:0 0 8px #f8514988"></div>',
  iconSize:[20,20], iconAnchor:[10,10], className:''
}});
L.marker(DESTINATION, {{icon: endIcon}})
  .bindPopup('<b>END</b><br>' + DESTINATION[0].toFixed(6) + ', ' + DESTINATION[1].toFixed(6))
  .addTo(map);

// Fit map to full route bounds
const allLatLngs = ROUTE.map(p => [p.lat, p.lon]);
map.fitBounds(L.latLngBounds(allLatLngs), {{ padding: [40, 40] }});

// ── Live position marker (animated blue dot) ──────────────────────
const posIcon = L.divIcon({{
  html: '<div style="width:20px;height:20px;border-radius:50%;' +
        'background:#58a6ff;border:3px solid #fff;' +
        'box-shadow:0 0 12px #58a6ffaa;' +
        'animation:pulse 1.5s ease-in-out infinite alternate"></div>' +
        '<style>@keyframes pulse{{' +
        'from{{box-shadow:0 0 6px #58a6ff88}}' +
        'to{{box-shadow:0 0 18px #58a6ffcc}}}}</style>',
  iconSize:[20,20], iconAnchor:[10,10], className:''
}});
const posMarker = L.marker(ORIGIN, {{
  icon: posIcon,
  zIndexOffset: 1000
}}).addTo(map);

// Accuracy circle around live position
const accCircle = L.circle(ORIGIN, {{
  radius: 20,
  color: '#58a6ff',
  fillColor: '#58a6ff',
  fillOpacity: 0.08,
  weight: 1
}}).addTo(map);

// ── Map legend ────────────────────────────────────────────────────
const legend = L.control({{position: 'bottomright'}});
legend.onAdd = function() {{
  const d = L.DomUtil.create('div');
  d.style.cssText = 'background:#161b22;padding:10px 12px;border:1px solid #30363d;' +
                    'border-radius:8px;color:#e6edf3;font-size:11px;font-family:monospace;';
  d.innerHTML = '<b style="color:#58a6ff">Risk colours</b><br>' +
    '<span style="color:#3fb950">━━</span> Low risk<br>' +
    '<span style="color:#d29922">━━</span> Medium risk<br>' +
    '<span style="color:#f85149">━━</span> High risk<br>' +
    '<span style="color:#58a6ff">◆</span> Waypoint<br>' +
    '<span style="color:#58a6ff">●</span> You are here';
  return d;
}};
legend.addTo(map);


// ════════════════════════════════════════════════════════════════
// HAVERSINE DISTANCE  (matches Python step1_fetch_route.py)
// Returns metres between two (lat, lon) points.
// ════════════════════════════════════════════════════════════════
function haversine(lat1, lon1, lat2, lon2) {{
  const R = 6371000;
  const toRad = x => x * Math.PI / 180;
  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  const a = Math.sin(dLat/2) * Math.sin(dLat/2)
          + Math.cos(toRad(lat1)) * Math.cos(toRad(lat2))
          * Math.sin(dLon/2) * Math.sin(dLon/2);
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}}


// ════════════════════════════════════════════════════════════════
// NEAREST SEGMENT LOOKUP
// Returns the index of the closest ROUTE point to (lat, lon).
// Used to get the speed limit and turn type for current position.
// ════════════════════════════════════════════════════════════════
function nearestSegment(lat, lon) {{
  let bestIdx  = 0;
  let bestDist = Infinity;
  for (let i = 0; i < ROUTE.length; i++) {{
    const d = haversine(lat, lon, ROUTE[i].lat, ROUTE[i].lon);
    if (d < bestDist) {{
      bestDist = d;
      bestIdx  = i;
    }}
  }}
  return bestIdx;
}}


// ════════════════════════════════════════════════════════════════
// SPEED CALCULATION STATE
// ════════════════════════════════════════════════════════════════
let prevPos = null;          // {{ lat, lon, ts }} of last GPS fix
let currentSpeedKmh = 0;     // smoothed speed in km/h

// Rolling median buffer (3 samples) — removes GPS spike outliers
const SPEED_BUF    = [];
const SPEED_BUF_N  = 3;

function medianSpeed(raw) {{
  // Sanity gate: ignore physically impossible jumps (GPS glitch)
  if (raw > 200 || raw < 0) return currentSpeedKmh;

  SPEED_BUF.push(raw);
  if (SPEED_BUF.length > SPEED_BUF_N) SPEED_BUF.shift();

  const sorted = [...SPEED_BUF].sort((a, b) => a - b);
  return sorted[Math.floor(sorted.length / 2)];
}}


// ════════════════════════════════════════════════════════════════
// GEOLOCATION CALLBACK — fires on every GPS fix
// This is the core of the real-time speed monitoring system.
// ════════════════════════════════════════════════════════════════
function onPosition(pos) {{
  const lat = pos.coords.latitude;
  const lon = pos.coords.longitude;
  const acc = pos.coords.accuracy;   // GPS accuracy in metres
  const ts  = pos.timestamp;         // milliseconds since epoch

  // ── Update GPS status bar ───────────────────────────────────
  const statusEl = document.getElementById('gps-status');
  statusEl.textContent = 'GPS: active';
  statusEl.className   = 'active';

  document.getElementById('accuracy-info').textContent =
    'Accuracy: ~' + Math.round(acc) + ' m';

  // ── Move live position marker ────────────────────────────────
  posMarker.setLatLng([lat, lon]);
  accCircle.setLatLng([lat, lon]);
  accCircle.setRadius(Math.min(acc, 200));  // cap visual radius

  // ── Pan map to follow position ───────────────────────────────
  map.panTo([lat, lon], {{ animate: true, duration: 0.6 }});

  // ── Speed calculation (haversine + time delta) ───────────────
  if (prevPos !== null) {{
    const distM  = haversine(prevPos.lat, prevPos.lon, lat, lon);
    const dtSec  = (ts - prevPos.ts) / 1000;

    if (dtSec > 0.05) {{  // ignore duplicate timestamps
      const rawKmh    = (distM / dtSec) * 3.6;
      currentSpeedKmh = medianSpeed(rawKmh);
    }}
  }}
  prevPos = {{ lat, lon, ts }};

  // ── Find nearest route segment → get limit & turn type ───────
  const segIdx = nearestSegment(lat, lon);
  const seg    = ROUTE[segIdx];
  const limit  = seg.limit;

  // ── Distance to end of route ─────────────────────────────────
  const distToEnd = haversine(lat, lon, DESTINATION[0], DESTINATION[1]);

  // ── Update accuracy bar (green < 20m, yellow < 50m, red > 50m) ──
  const accBar = document.getElementById('acc-bar');
  const accPct = Math.max(0, Math.min(100, (1 - acc / 200) * 100));
  accBar.style.width = accPct + '%';
  accBar.style.background = acc < 20 ? '#3fb950' : acc < 50 ? '#d29922' : '#f85149';

  // ── Update all dashboard values ───────────────────────────────
  document.getElementById('speed-val').textContent =
    currentSpeedKmh.toFixed(1);
  document.getElementById('limit-val').textContent =
    limit;
  document.getElementById('acc-val').textContent =
    Math.round(acc);
  document.getElementById('turn-val').textContent =
    (seg.turn || '').replace(/_/g, ' ');
  document.getElementById('dist-val').textContent =
    Math.round(distToEnd);
  document.getElementById('segment-info').textContent =
    'Segment #' + segIdx + '  |  ' + seg.turn.replace(/_/g,' ') +
    '  |  angle ' + seg.angle.toFixed(0) + '°';

  // ── Road type / condition / friction info (step7 data) ────────────────
  if (seg.mu !== undefined) {{
    const roadPanel = document.getElementById('road-panel');
    roadPanel.style.display = '';
    document.getElementById('road-type-val').textContent = seg.road_type || '—';
    document.getElementById('road-cond-val').textContent = seg.road_cond || '—';
    document.getElementById('friction-val').textContent  =
      'μ = ' + seg.mu.toFixed(2) + '  |  ' + seg.f_risk.toUpperCase() + ' friction';
    document.getElementById('stop-val').textContent =
      seg.stop_m ? seg.stop_m.toFixed(1) : '—';
  }}

  // ── Warning system ─────────────────────────────────────────
  updateWarning(currentSpeedKmh, limit, seg);
}}


// ════════════════════════════════════════════════════════════════
// WARNING SYSTEM
// Compares actual speed to the nearest segment's speed limit.
// The limit is turn-aware: curves get lower limits automatically
// because step3_speed_risk.py assigned them lower recommended_speed_kmh.
// When step7 friction data is present, adjusted_speed_kmh is used as
// the limit (already friction-corrected by Python) and friction risk
// is also shown in the warning panel.
// ════════════════════════════════════════════════════════════════
function updateWarning(speed, limit, seg) {{
  const box  = document.getElementById('status-box');
  const over = speed - limit;

  // Case 1: Not moving (or very low speed)
  if (speed < 0.5) {{
    box.className   = 'stationary';
    box.innerHTML   = '&#9899; Stationary';
    return;
  }}

  // Build friction suffix for display (only when step7 data present)
  let frictionNote = '';
  if (seg.mu !== undefined && seg.f_risk !== 'low') {{
    const fClr = seg.f_risk === 'high' ? '#f85149' : '#d29922';
    frictionNote = '<br><small style="font-weight:400;font-size:0.7rem;color:' + fClr + '">' +
      '&#9888; ' + seg.f_risk.toUpperCase() + ' friction — μ=' + seg.mu.toFixed(2) +
      ' — stop in ' + (seg.stop_m||0).toFixed(0) + 'm</small>';
  }}

  // Case 2: Under the limit — safe (but warn if friction is bad)
  if (over <= 0) {{
    const turnLabel = seg.turn.replace(/_/g, ' ');
    if (seg.mu !== undefined && seg.f_risk === 'high') {{
      box.className   = 'warn';
      box.innerHTML   = '&#9888; Caution: low grip<br>' +
        '<small style="font-weight:400;font-size:0.75rem">' +
        speed.toFixed(1) + ' km/h &nbsp;|&nbsp; ' + turnLabel + '</small>' + frictionNote;
    }} else {{
      box.className   = 'safe';
      box.innerHTML   = '&#10003; Safe<br><small style="font-weight:400;font-size:0.75rem">' +
                        speed.toFixed(1) + ' km/h &nbsp;|&nbsp; ' + turnLabel + '</small>' + frictionNote;
    }}
    return;
  }}

  // Case 3: Slightly over (1–9 km/h) — yellow warning
  if (over < 10) {{
    box.className   = 'warn';
    box.innerHTML   = '&#9888; Slow down!<br><small style="font-weight:400;font-size:0.75rem">'
                    + '+' + over.toFixed(1) + ' km/h over limit (' + limit + ')</small>' + frictionNote;
    return;
  }}

  // Case 4: Significantly over (10+ km/h) — red flashing danger
  box.className   = 'danger';
  box.innerHTML   = '&#128680; DANGER &#128680;<br><small style="font-weight:400;font-size:0.75rem">'
                  + '+' + over.toFixed(1) + ' km/h OVER LIMIT (' + limit + ' km/h)</small>' + frictionNote;
}}


// ════════════════════════════════════════════════════════════════
// ERROR HANDLER
// ════════════════════════════════════════════════════════════════
function onError(err) {{
  const statusEl = document.getElementById('gps-status');
  statusEl.className = '';

  const messages = {{
    1: 'GPS denied — allow location in browser settings',
    2: 'GPS unavailable — check device settings',
    3: 'GPS timeout — retrying…'
  }};

  statusEl.textContent = 'GPS: ' + (messages[err.code] || err.message);
  document.getElementById('status-box').className = 'stationary';
  document.getElementById('status-box').textContent =
    'No GPS signal\\nCheck browser permissions';
}}


// ════════════════════════════════════════════════════════════════
// START GPS WATCHING
// enableHighAccuracy: true  → uses GPS chip (not cell tower)
// maximumAge: 0             → always fresh fix, never cached
// timeout: 10000            → 10s before error fires
// ════════════════════════════════════════════════════════════════
if ('geolocation' in navigator) {{
  navigator.geolocation.watchPosition(onPosition, onError, {{
    enableHighAccuracy : true,
    maximumAge         : 0,
    timeout            : 10000
  }});
}} else {{
  document.getElementById('gps-status').textContent =
    'Geolocation not supported in this browser';
  document.getElementById('status-box').textContent =
    'Browser does not support GPS';
}}
</script>
</body>
</html>"""
