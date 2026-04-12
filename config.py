"""
config.py
=========
Central configuration for the Road Navigation & Speed Optimization System.

HOW TO GET A FREE ORS API KEY (takes 2 minutes)
------------------------------------------------
1. Visit  https://openrouteservice.org/dev/#/signup
2. Register with your email (no credit card)
3. Your key appears on the dashboard instantly
4. Free tier: 2,000 requests/day, 40 requests/min
5. Paste it below as  ORS_API_KEY = "your_key"

ROUTES TO ANALYZE
-----------------
Edit the ROUTES list in main.py with your (lat, lon) coordinates.
How to find coordinates:
  - Open Google Maps
  - Right-click any location
  - Click "What's here?"
  - Coordinates appear at the bottom

SYSTEM FLOW
-----------
  main.py
    └─ step1_fetch_route.py    → ORS/OSRM API → real road coordinates
    └─ step2_process_route.py  → densify, segment, curvature analysis
    └─ step3_speed_risk.py     → speed planning, risk detection, travel time
    └─ step7_road_input.py     → road type + condition input → friction analysis (NEW)
    └─ step4_export.py         → CSV export (basic + enhanced)
    └─ step5_map.py            → Folium HTML map + matplotlib plots
    └─ step6_live_monitor.py   → Live GPS speed monitor HTML page
"""

import os

# ─────────────────────────────────────────────────────────────────────────────
# API KEYS  (free — see instructions above)
# ─────────────────────────────────────────────────────────────────────────────

# OpenRouteService — best road detail, surface info, turn-by-turn
# Get free: https://openrouteservice.org/dev/#/signup
ORS_API_KEY  = "eyJvcmciOiI1YjNjZTM1OTc4NTExMTAwMDFjZjYyNDgiLCJpZCI6IjZjMTk1YzhlNjZkNTQ0OGFhZjk5YmJkYTA5MTI0ZTYwIiwiaCI6Im11cm11cjY0In0="           # ← PASTE YOUR ORS KEY HERE

# ORS route profile: "driving-car" follows all car roads (best for bikes)
ORS_PROFILE  = "driving-car"

# ─────────────────────────────────────────────────────────────────────────────
# PATHS
# ─────────────────────────────────────────────────────────────────────────────

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "outputs")

# ─────────────────────────────────────────────────────────────────────────────
# ROUTE PROCESSING
# ─────────────────────────────────────────────────────────────────────────────

# Maximum gap between consecutive route points (metres)
# Smaller = denser path = better curve detection
# Recommended: 8–15 m  (smaller = larger CSV file)
MAX_GAP_METRES = 10.0

# ─────────────────────────────────────────────────────────────────────────────
# TURN ANGLE THRESHOLDS  (degrees, where 180° = perfectly straight)
# ─────────────────────────────────────────────────────────────────────────────

ANGLE_THRESHOLD = {
    "straight"         : 170,   # angle > 170°  → straight
    "mild_curve"       : 150,   # 150° – 170°  → mild curve
    "sharp_curve"      : 120,   # 120° – 150°  → sharp curve
    "very_sharp_curve" : 90,    # 90°  – 120°  → very sharp
    # below 90° = u_turn
}

# ─────────────────────────────────────────────────────────────────────────────
# SPEED RULES  (km/h) — recommended speed per road segment type
# ─────────────────────────────────────────────────────────────────────────────

SPEED_RULES = {
    "straight"          : 60,
    "mild_curve"        : 40,
    "sharp_curve"       : 25,
    "very_sharp_curve"  : 15,
    "intersection"      : 20,
    "u_turn"            : 10,
}

# Speed smoothing: max change in km/h per metre of road
MAX_ACCEL_KMH_PER_M = 2.5   # acceleration limit
MAX_DECEL_KMH_PER_M = 4.0   # braking limit (harder than accelerating)

# ─────────────────────────────────────────────────────────────────────────────
# RISK THRESHOLDS
# ─────────────────────────────────────────────────────────────────────────────

RISK_HIGH_SPEED_KMPH    = 20    # speed ≤ this → HIGH risk
RISK_MEDIUM_SPEED_KMPH  = 35    # speed ≤ this → MEDIUM risk
SHARP_CLUSTER_WINDOW_M  = 200   # metres to look for sharp-turn clusters
SHARP_CLUSTER_MIN_COUNT = 3     # how many sharp turns → HIGH risk zone

# ─────────────────────────────────────────────────────────────────────────────
# ROAD SURFACE SPEED MODIFIERS
# ─────────────────────────────────────────────────────────────────────────────
# Multiply base speed by this factor depending on road surface

SURFACE_FACTOR = {
    "asphalt"          : 1.00,
    "paved"            : 1.00,
    "concrete"         : 0.95,
    "paving_stones"    : 0.80,
    "cobblestone"      : 0.70,
    "compacted_gravel" : 0.75,
    "gravel"           : 0.65,
    "dirt"             : 0.60,
    "ground"           : 0.60,
    "sand"             : 0.50,
    "grass"            : 0.55,
    "ice"              : 0.35,
    "unknown"          : 0.90,
}

# ─────────────────────────────────────────────────────────────────────────────
# ORS SURFACE CODE → NAME MAP
# ─────────────────────────────────────────────────────────────────────────────

ORS_SURFACE_MAP = {
    0: "unknown",    1: "paved",      2: "unpaved",
    3: "asphalt",    4: "concrete",   5: "cobblestone",
    6: "metal",      7: "wood",       8: "compacted_gravel",
    9: "fine_gravel",10: "gravel",    11: "dirt",
    12: "ground",    13: "ice",       14: "paving_stones",
    15: "sand",      16: "woodchips", 17: "grass",
}

# ─────────────────────────────────────────────────────────────────────────────
# MAP / PLOT COLOURS
# ─────────────────────────────────────────────────────────────────────────────

COLORS = dict(
    bg="#0D1117", panel="#161B22", grid="#21262D",
    text="#E6EDF3", muted="#8B949E", border="#30363D",
    blue="#58A6FF", green="#3FB950", orange="#F0883E",
    red="#F85149", yellow="#D29922", purple="#BC8CFF",
)

# Folium / HTML colours
RISK_COLOR  = {"low": "#3FB950", "medium": "#D29922", "high": "#F85149"}
ROUTE_COLOR = "#58A6FF"

# ─────────────────────────────────────────────────────────────────────────────
# ROAD TYPE & CONDITION (Step 7)  — friction-based safety enhancement
# ─────────────────────────────────────────────────────────────────────────────
# These thresholds are used by step7_road_input.py to classify friction risk.
# They can be tuned here without touching the step7 code.

# Friction coefficient (μ) below which segment risk is upgraded to HIGH
FRICTION_HIGH_RISK_MU   = 0.35

# Friction coefficient (μ) below which segment risk is upgraded to MEDIUM
FRICTION_MEDIUM_RISK_MU = 0.60

# Reference friction: dry tar road (no speed penalty at this μ)
FRICTION_REFERENCE_MU   = 0.80
