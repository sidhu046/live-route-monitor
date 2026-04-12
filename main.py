"""
main.py — Road Navigation & Speed Optimization System
=======================================================
Complete pipeline: Real Road Extraction → Speed Planning → Safety Analysis
                 + Intermediate Waypoint Routing + Live Speed Monitor.

QUICK START
-----------
  python main.py                    ← runs with demo route (no API key)
  python main.py --key YOUR_KEY     ← uses real ORS road data

TO ADD YOUR API KEY PERMANENTLY:
  Edit config.py → ORS_API_KEY = "your_key_here"
  Get free: https://openrouteservice.org/dev/#/signup

ROUTES INCLUDED
---------------
  Route 1: IIIT RGUKT-Nuzvid SAC Building → Main Gate (with 5 waypoints)
  (Add more in the ROUTES list below)

WHAT'S NEW IN THIS VERSION
--------------------------
  ✓ Intermediate waypoints: "one-stop", "second-stop", etc. in each route
    are now passed to ORS/OSRM so the route follows actual roads through
    each stop. Previously these keys were stored but never used.

  ✓ Step 6: live_monitor.html is generated for every route.
    Open it in Chrome with HTTPS to get real-time GPS speed monitoring
    with turn-aware speed limits and visual warnings.

  ✓ Step 7 (NEW): Road type & condition input with friction analysis.
    After step3, the user is asked:
      a) What type of road is this? (tar, cc, mud, highway, gravel, dirt)
      b) What is the road condition? (dry, wet, flooded, icy, snow)
    The system looks up friction coefficient (μ) from a published dataset,
    computes a speed correction factor sqrt(μ / μ_ref), and applies it to
    every segment's speed. This creates adjusted_speed_kmh which is used
    by live_monitor.html as the warning threshold.
    Risk levels are upgraded automatically for very low-friction conditions.
    All existing fields and outputs remain fully intact.

OUTPUT FILES (per route, in outputs/<route_name>/)
--------------------------------------------------
  route_coordinates.csv      ← basic CSV: latitude, longitude  (MATLAB)
  route_full_analysis.csv    ← enhanced: + speed, risk, curvature
  high_risk_zones.csv        ← only HIGH-risk points
  navigation_data.json       ← full structured data
  summary_report.txt         ← human-readable analysis
  turn_by_turn.txt           ← navigation instructions
  interactive_map.html       ← ★ STATIC map — open in browser ★
  live_monitor.html          ← ★ LIVE GPS monitor — open with HTTPS ★
  plot_dashboard.png         ← 10-panel analysis dashboard
  plot_route_speed.png       ← map coloured by speed
  plot_route_risk.png        ← map coloured by risk
  plot_speed_profile.png     ← speed vs distance
  plot_curvature.png         ← curvature along route
  plot_angle.png             ← turning angles
  plot_time.png              ← speed vs time
  plot_risk_summary.png      ← risk pie + turn bar

HOW TO USE live_monitor.html
-----------------------------
  1. Run: python main.py
  2. Generate a self-signed cert (one time):
       openssl req -x509 -newkey rsa:2048 -keyout key.pem -out cert.pem
         -days 365 -nodes -subj "/CN=localhost"
  3. Serve with HTTPS from the route output folder:
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
  4. Open https://localhost:8443/live_monitor.html in Chrome.
  5. To simulate GPS on desktop: F12 → More tools → Sensors → Location.

CSV FORMAT  (for MATLAB)
-----------------------
The basic CSV matches your MATLAB script format exactly:
  latitude,longitude
  16.5062000,80.6480000
  16.5071234,80.6492345
  ...

Load in MATLAB:
  data = readtable('route_coordinates.csv');
  x    = data.longitude;
  y    = data.latitude;
"""

import os
import sys
import time
import argparse

from config            import ORS_API_KEY, OUTPUT_DIR
from step1_fetch_route import fetch_route
from step2_process_route import process_route
from step3_speed_risk  import run_speed_risk
from step4_export      import run_export
from step5_map         import run_visualise
from step6_live_monitor import generate_live_monitor   # ← NEW
from step7_road_input  import ask_road_conditions, apply_friction  # ← NEW

# ══════════════════════════════════════════════════════════════════════════════
# ▼▼▼  EDIT YOUR ROUTES HERE  ▼▼▼
# ══════════════════════════════════════════════════════════════════════════════

ROUTES = [
    # {
    #     # IIIT RGUKT-Nuzvid Engineering College → Kanaka Durga Temple, Vijayawada
    #     # Distance: ~55 km via NH-16 (real road)
    #     "name"       : "RGUKT_Nuzvid_to_Durga_Temple",
    #     "origin"     : (16.789378382071007, 80.82260459661485),   # IIIT RGUKT-Nuzvid
    #     "one-stop"    : (16.679325983024693, 80.78282207250597),
    #     "destination": (16.51301904298443, 80.60533761978151),   # Kanaka Durga Temple
    # },
    # {
    #     # Vijayawada railway station → Hyderabad Central Bus Stand
    #     # Distance: ~275 km via NH-65 (real road)
    #     "name"       : "Vijayawada_to_Hyderabad",
    #     "origin"     : (16.517989846618992, 80.61959087848665),   # Vijayawada railway station
    #     "destination": (17.39234378992583, 78.46777796745302),   # Hyderabad Central Bus Stand
    # },
    # {
    #     # tirupati → varanasi
    #     # Distance: ~1200 km via NH-44 (real road)
    #     "name"       : "Tirupati_to_Varanasi",
    #     "origin"     : (13.628755, 79.419200),   # Tirupati
    #     "destination": (25.317644, 82.973915),   # Varanasi
    # },
    {
        # IIIT RGUKT-Nuzvid SAC Building → IIIT RGUKT-Nuzvid Main Gate
        # Distance: ~1.5 km via internal roads (real road)
        # All "one-stop" through "fifth-stop" keys are now used as real
        # intermediate waypoints sent to ORS/OSRM. The route will follow
        # the actual road through each of these points in order.
        "name"        : "Workshop_to_MainGate",
        "origin"      : (16.794331747678317, 80.82665473222734),   # SAC Building
        # "one-stop"    : (16.79270375063626, 80.82246526439573),   # Midpoint 1
        # "second-stop" : (16.792485484987328, 80.82276291197819),   # Midpoint 2
        # "third-stop"  : (16.791617555571282, 80.82212471265723),   # Midpoint 3
        "destination" : (16.789401492941533, 80.8226126432419),    # Main Gate
    },
    # {
    #     "name"       : "cheepurupalli_to_srikakulam",
    #     "origin"     : (18.304443275033854, 83.56789380311967), # start coordinates
    #     "one-stop"   : (18.341424577368812, 83.62560153007509),          # optional intermediate stop 1
    #     "destination": (18.294743414476574, 83.89204412698747),          # end coordinates
    # },
    # ── Add your own routes below ─────────────────────────────────────────
    # {
    #     "name"       : "My_Custom_Route",
    #     "origin"     : (lat, lon),          # start coordinates
    #     "one-stop"   : (lat, lon),          # optional intermediate stop 1
    #     "destination": (lat, lon),          # end coordinates
    # },
]

# ▲▲▲  END OF EDIT SECTION  ▲▲▲
# ══════════════════════════════════════════════════════════════════════════════


def _extract_waypoints(cfg: dict) -> list:
    """
    Pull intermediate waypoints from a route config dict in order.

    Recognised keys (in order): one-stop, second-stop, third-stop,
    fourth-stop, fifth-stop.  Add more keys here if you need more stops.

    Returns a list of (lat, lon) tuples, empty list if none defined.
    """
    waypoint_keys = [
        "one-stop", "second-stop", "third-stop",
        "fourth-stop", "fifth-stop",
    ]
    return [cfg[k] for k in waypoint_keys if k in cfg]


def run_one_route(cfg: dict, api_key: str) -> dict:
    """
    Run the complete 6-step pipeline for one origin → destination pair.

    NEW in this version:
      - Extracts intermediate waypoints from cfg and passes them to step 1.
      - Calls step 6 to generate live_monitor.html.

    Returns a results dict with all data for downstream use.
    """
    name    = cfg["name"]
    origin  = cfg["origin"]
    dest    = cfg["destination"]
    out_dir = os.path.join(OUTPUT_DIR, name)
    os.makedirs(out_dir, exist_ok=True)

    # ── Collect intermediate waypoints ────────────────────────────────────
    waypoints = _extract_waypoints(cfg)

    print(f"\n{'#'*64}")
    print(f"  ROUTE: {name}")
    print(f"  From : {origin}")
    if waypoints:
        for i, w in enumerate(waypoints, 1):
            print(f"  Via  : waypoint {i} → {w}")
    print(f"  To   : {dest}")
    print(f"{'#'*64}")
    t0 = time.time()

    # ── Step 1: Fetch real road route (now with waypoints) ────────────────
    route    = fetch_route(origin, dest, api_key, waypoints=waypoints)

    # ── Step 2: Geometry analysis ─────────────────────────────────────────
    segments = process_route(route)

    # ── Step 3: Speed optimization + risk analysis ────────────────────────
    segments = run_speed_risk(segments)

    # ── Step 7: Road type + condition input → friction analysis ──────────
    # road_type and road_condition come from the ROUTES config (if set)
    # or are asked interactively from the user in the terminal.
    road_type      = cfg.get("road_type")       # optional pre-set in ROUTES
    road_condition = cfg.get("road_condition")   # optional pre-set in ROUTES

    if road_type and road_condition:
        # Non-interactive: use values from the ROUTES dict directly
        print(f"\n{'='*62}")
        print(f"  STEP 7 — FRICTION ANALYSIS  (pre-configured)")
        print(f"{'='*62}")
        print(f"  Road type      : {road_type}")
        print(f"  Road condition : {road_condition}")
        segments = apply_friction(segments, road_type, road_condition)
    else:
        # Interactive: ask the user in the terminal
        road_type, road_condition = ask_road_conditions()
        segments = apply_friction(segments, road_type, road_condition)

    # ── Step 4: Export CSV / JSON / reports ───────────────────────────────
    files    = run_export(segments, route, out_dir)

    # ── Step 5: Interactive map + plots ───────────────────────────────────
    vis      = run_visualise(segments, route, out_dir)

    # ── Step 6: Live GPS speed monitor (NEW) ──────────────────────────────
    print(f"\n{'='*62}")
    print(f"  STEP 6 — LIVE SPEED MONITOR")
    print(f"{'='*62}")
    live_html = generate_live_monitor(segments, route, out_dir)

    elapsed  = time.time() - t0

    # ── Print sample output in requested format ────────────────────────────
    print(f"\n  SAMPLE OUTPUT  (latitude, longitude, turn_type, speed, risk)")
    print(f"  {'lat':>13}  {'lon':>13}  {'turn_type':<22}  "
          f"{'speed':>6}  {'risk':<8}  {'angle':>7}  {'dist_m':>7}")
    print(f"  {'-'*90}")
    step_n = max(1, len(segments) // 14)
    for s in segments[::step_n][:14]:
        print(f"  {s['lat']:>13.7f}  {s['lon']:>13.7f}  "
              f"{s['turn_type']:<22}  "
              f"{s.get('recommended_speed_kmh',0):>5.1f}  "
              f"{s.get('risk_level',''):8}  "
              f"{s['turning_angle_deg']:>7.1f}°  "
              f"{s['dist_to_next_m']:>7.1f}m")

    print(f"\n  {'─'*50}")
    print(f"  Done in {elapsed:.1f}s  |  Outputs: {out_dir}")
    print(f"  ★ Static map : {vis['html_map']}")
    print(f"  ★ Live monitor: {live_html}")
    print(f"     (Serve with HTTPS — see README in docstring above)")

    return {
        "name"     : name,
        "route"    : route,
        "segments" : segments,
        "files"    : files,
        "vis"      : vis,
        "live_html": live_html,
        "elapsed"  : elapsed,
    }


def main():
    # ── Parse optional command-line API key ───────────────────────────────
    parser = argparse.ArgumentParser(
        description="Road Navigation & Speed Optimization System")
    parser.add_argument("--key", default="",
                        help="ORS API key (or set in config.py)")
    parser.add_argument("--route", default=None,
                        help="Run only one route by index (0, 1, ...)")
    args = parser.parse_args()

    api_key = args.key or ORS_API_KEY

    print("\n" + "="*64)
    print("  ROAD NAVIGATION & SPEED OPTIMIZATION SYSTEM")
    print("  ORS / OSRM | NumPy | SciPy | Matplotlib | Folium | Leaflet")
    print("="*64)

    if api_key and api_key not in ("", "YOUR_KEY_HERE"):
        print(f"\n  ORS key: SET  → will use real road geometry + waypoints")
    else:
        print(f"\n  ORS key: NOT SET  → demo mode (synthetic route)")
        print("  For real roads:")
        print("  1. Sign up free: https://openrouteservice.org/dev/#/signup")
        print("  2. Set ORS_API_KEY in config.py  or  run: python main.py --key YOUR_KEY")

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Select routes to run
    routes_to_run = ROUTES
    if args.route is not None:
        idx = int(args.route)
        if 0 <= idx < len(ROUTES):
            routes_to_run = [ROUTES[idx]]
        else:
            print(f"  Route index {idx} out of range (0–{len(ROUTES)-1})")
            return

    all_results = []
    for cfg in routes_to_run:
        try:
            result = run_one_route(cfg, api_key)
            all_results.append(result)
        except Exception as e:
            print(f"\n  ERROR on '{cfg['name']}': {e}")
            import traceback; traceback.print_exc()

    # ── Final summary table ───────────────────────────────────────────────
    if len(all_results) > 1:
        print(f"\n{'='*64}")
        print("  ALL ROUTES SUMMARY")
        print(f"{'='*64}")
        print(f"  {'Route':<35} {'Dist':>8} {'Pts':>6} "
              f"{'Avg km/h':>9} {'HIGH':>6} {'Time':>7}")
        print(f"  {'-'*64}")
        for r in all_results:
            segs = r["segments"];  ri = r["route"]
            spds = [s.get("recommended_speed_kmh",0) for s in segs]
            high = sum(1 for s in segs if s.get("risk_level")=="high")
            et   = segs[-1].get("elapsed_time_min",0)
            print(f"  {r['name']:<35} "
                  f"{ri.get('distance_txt',''):>8}  "
                  f"{len(segs):>5}  "
                  f"{sum(spds)/len(spds):>8.1f}  "
                  f"{high:>6}  {et:>6.1f}m")

    print(f"\n  All outputs → {OUTPUT_DIR}")
    print("  ★ Open interactive_map.html for the static risk map")
    print("  ★ Open live_monitor.html (via HTTPS) for real-time GPS speed")
    print("="*64)


if __name__ == "__main__":
    main()
