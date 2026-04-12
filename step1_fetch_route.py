"""
step1_fetch_route.py
=====================
STEP 1 — Fetch a real road-based route from a FREE routing API.

APIS TRIED (in order)
---------------------
1. OpenRouteService (ORS)   — needs free key, best detail
2. OSRM public demo         — no key needed, works immediately
3. Demo fallback            — offline, cubic-spline synthetic route

WHAT THIS MODULE RETURNS
------------------------
A route dictionary with:
  coordinates      : list of (lat, lon)  — the actual road path
  distance_m       : total route distance in metres
  duration_s       : estimated travel time in seconds  (from API)
  distance_txt     : human-readable, e.g. "4.2 km"
  duration_txt     : human-readable, e.g. "12 min 35 sec"
  steps            : turn-by-turn instruction list
  road_names       : list of road names along the route
  surface_per_point: dict  {index: surface_name}
  source           : which API provided the data

WAYPOINTS SUPPORT (NEW)
-----------------------
  fetch_route() now accepts an optional `waypoints` list of (lat, lon) tuples.
  These are INTERMEDIATE stops between origin and destination.
  Both ORS and OSRM APIs support multiple waypoints in a single request.
  ORS free tier supports up to 50 waypoints per request.

  Example usage in main.py (already handled automatically):
    fetch_route(origin, destination, api_key,
                waypoints=[(lat1, lon1), (lat2, lon2)])

NOTE ON COORDINATE ORDER
------------------------
  ORS API  : uses [longitude, latitude] order
  OSRM API : uses lon,lat in URL
  Our code : always converts to (latitude, longitude) tuples
"""

import math
import json
import time
import os
import requests
import numpy as np
from scipy.interpolate import CubicSpline

from config import (ORS_API_KEY, ORS_PROFILE, MAX_GAP_METRES,
                     ORS_SURFACE_MAP, OUTPUT_DIR)


# ─────────────────────────────────────────────────────────────────────────────
# UTILITY FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────

def haversine(p1: tuple, p2: tuple) -> float:
    """
    Great-circle distance in metres between two (lat, lon) points.
    Used for: segment lengths, total distance, densification gaps.
    """
    R    = 6_371_000
    la1  = math.radians(p1[0]);  lo1 = math.radians(p1[1])
    la2  = math.radians(p2[0]);  lo2 = math.radians(p2[1])
    dlat = la2 - la1;             dlon = lo2 - lo1
    a    = math.sin(dlat/2)**2 + math.cos(la1)*math.cos(la2)*math.sin(dlon/2)**2
    return R * 2 * math.asin(math.sqrt(a))


def densify_coordinates(coords: list, max_gap_m: float = MAX_GAP_METRES) -> list:
    """
    Insert linearly interpolated points wherever gap > max_gap_m metres.

    WHY: APIs often return sparse points on highways (50–200 m gaps).
    Curve detection needs ≤10 m spacing to detect short corners.

    Method: simple linear interpolation in lat/lon space.
    Accurate for distances < 20 km (error < 1 mm).
    """
    if len(coords) < 2:
        return coords

    out = [coords[0]]
    for i in range(len(coords) - 1):
        p1 = coords[i];   p2 = coords[i + 1]
        d  = haversine(p1, p2)
        if d > max_gap_m:
            n = int(math.ceil(d / max_gap_m))
            for k in range(1, n):
                f = k / n
                out.append((p1[0] + f * (p2[0] - p1[0]),
                             p1[1] + f * (p2[1] - p1[1])))
        out.append(p2)

    return out


def decode_polyline(encoded: str) -> list:
    """
    Decode a Google-format encoded polyline string to (lat, lon) list.
    Used by OSRM and some ORS responses.

    Google encodes coordinate deltas as 5-bit ASCII chunks.
    """
    coords = [];  index = 0;  lat = 0;  lng = 0;  n = len(encoded)
    while index < n:
        result = 0;  shift = 0
        while True:
            b = ord(encoded[index]) - 63;  index += 1
            result |= (b & 0x1F) << shift;  shift += 5
            if b < 0x20: break
        dlat = ~(result >> 1) if (result & 1) else (result >> 1);  lat += dlat
        result = 0;  shift = 0
        while True:
            b = ord(encoded[index]) - 63;  index += 1
            result |= (b & 0x1F) << shift;  shift += 5
            if b < 0x20: break
        dlng = ~(result >> 1) if (result & 1) else (result >> 1);  lng += dlng
        coords.append((lat / 1e5, lng / 1e5))
    return coords


# ─────────────────────────────────────────────────────────────────────────────
# API 1 — OpenRouteService  (MODIFIED: accepts waypoints list)
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_ors(origin: tuple, destination: tuple,
               api_key: str, profile: str,
               waypoints: list = None) -> dict:
    """
    Fetch route from ORS with optional intermediate waypoints.
    POST https://api.openrouteservice.org/v2/directions/{profile}/geojson

    Parameters
    ----------
    origin      : (lat, lon) start point
    destination : (lat, lon) end point
    api_key     : ORS API key
    profile     : routing profile, e.g. "driving-car"
    waypoints   : list of (lat, lon) intermediate stops (optional)
                  ORS free tier supports up to 50 coordinates total.

    ORS expects coordinates as [longitude, latitude] — we convert here.
    """
    url = f"https://api.openrouteservice.org/v2/directions/{profile}/geojson"

    headers = {
        "Authorization" : api_key,
        "Content-Type"  : "application/json",
        "Accept"        : "application/json",
    }

    # Build full coordinate list: origin → waypoints → destination
    # ORS requires [lon, lat] order for each point
    all_points  = [origin] + (waypoints or []) + [destination]
    ors_coords  = [[pt[1], pt[0]] for pt in all_points]

    body = {
        "coordinates"        : ors_coords,
        "instructions"       : True,
        "instructions_format": "text",
        "elevation"          : False,
        "extra_info"         : ["surface", "roadaccessrestrictions"],
        "geometry_simplify"  : False,
        "preference"         : "recommended",
        "units"              : "m",
        "language"           : "en",
    }

    wpt_count = len(ors_coords)
    print(f"    [ORS] POST {url}  ({wpt_count} coordinates incl. {wpt_count-2} waypoints)")
    resp = requests.post(url, headers=headers, json=body, timeout=20)

    if resp.status_code == 401:
        raise ValueError("ORS key invalid. Check config.py → ORS_API_KEY")
    if resp.status_code == 429:
        raise ValueError("ORS rate limit hit (40/min or 2000/day). Wait and retry.")
    resp.raise_for_status()

    data    = resp.json()
    feature = data["features"][0]
    props   = feature["properties"]
    geom    = feature["geometry"]
    summary = props["summary"]

    # GeoJSON: [[lon, lat], ...] → convert to (lat, lon)
    coords = [(pt[1], pt[0]) for pt in geom["coordinates"]]

    # Steps
    steps      = []
    road_names = []
    for seg in props.get("segments", []):
        for step in seg.get("steps", []):
            name = step.get("name", "")
            steps.append({
                "instruction" : step.get("instruction", ""),
                "name"        : name,
                "distance_m"  : step.get("distance", 0),
                "duration_s"  : step.get("duration", 0),
                "way_points"  : step.get("way_points", []),
            })
            if name and name not in ("-", "") and name not in road_names:
                road_names.append(name)

    # Surface info
    surf_map = {}
    for entry in props.get("extras", {}).get("surface", {}).get("values", []):
        s_idx, e_idx, code = entry
        name = ORS_SURFACE_MAP.get(code, "unknown")
        for i in range(s_idx, min(e_idx + 1, len(coords))):
            surf_map[i] = name

    # Waypoint indices (start of each navigation step)
    wp_idx = set()
    for step in steps:
        wp = step.get("way_points", [])
        if wp:
            wp_idx.add(wp[0])

    d_m = summary.get("distance", 0)
    t_s = summary.get("duration", 0)

    return {
        "coordinates"      : coords,
        "distance_m"       : d_m,
        "duration_s"       : t_s,
        "distance_txt"     : f"{d_m/1000:.2f} km",
        "duration_txt"     : f"{int(t_s//60)} min {int(t_s%60)} sec",
        "steps"            : steps,
        "road_names"       : road_names,
        "surface_per_point": surf_map,
        "waypoint_indices" : wp_idx,
        "source"           : "OpenRouteService",
        "profile"          : profile,
    }


# ─────────────────────────────────────────────────────────────────────────────
# API 2 — OSRM  (MODIFIED: accepts waypoints list)
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_osrm(origin: tuple, destination: tuple,
                waypoints: list = None) -> dict:
    """
    Fetch route from OSRM public demo server with optional waypoints.
    GET http://router.project-osrm.org/route/v1/driving/{coords}

    Parameters
    ----------
    origin      : (lat, lon) start point
    destination : (lat, lon) end point
    waypoints   : list of (lat, lon) intermediate stops (optional)

    NOTE: OSRM uses longitude,latitude order in URL, separated by semicolons.
    Returns encoded polyline geometry.
    """
    # Build semicolon-separated lon,lat string for OSRM URL
    all_points  = [origin] + (waypoints or []) + [destination]
    coords_str  = ";".join(f"{p[1]},{p[0]}" for p in all_points)

    url = (
        f"http://router.project-osrm.org/route/v1/driving/{coords_str}"
        f"?overview=full&geometries=polyline&steps=true&annotations=false"
    )

    wpt_count = len(all_points)
    print(f"    [OSRM] GET ...  ({wpt_count} coordinates incl. {wpt_count-2} waypoints)")
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    if data.get("code") != "Ok":
        raise ValueError(f"OSRM: {data.get('code')} — {data.get('message','')}")

    route    = data["routes"][0]
    geometry = route["geometry"]
    coords   = decode_polyline(geometry) if isinstance(geometry, str) \
               else [(pt[1], pt[0]) for pt in geometry.get("coordinates", [])]

    steps      = []
    road_names = []
    wp_idx     = set()
    for leg in route.get("legs", []):
        for step in leg.get("steps", []):
            name = step.get("name", "")
            m    = step.get("maneuver", {})
            steps.append({
                "instruction" : f"{m.get('type','')} {m.get('modifier','')}".strip(),
                "name"        : name,
                "distance_m"  : step.get("distance", 0),
                "duration_s"  : step.get("duration", 0),
                "way_points"  : [],
            })
            if name and name not in road_names:
                road_names.append(name)

    d_m = route.get("distance", 0)
    t_s = route.get("duration", 0)

    return {
        "coordinates"      : coords,
        "distance_m"       : d_m,
        "duration_s"       : t_s,
        "distance_txt"     : f"{d_m/1000:.2f} km",
        "duration_txt"     : f"{int(t_s//60)} min {int(t_s%60)} sec",
        "steps"            : steps,
        "road_names"       : road_names,
        "surface_per_point": {},
        "waypoint_indices" : wp_idx,
        "source"           : "OSRM",
        "profile"          : "driving",
    }


# ─────────────────────────────────────────────────────────────────────────────
# FALLBACK — Synthetic demo route (works offline)
# ─────────────────────────────────────────────────────────────────────────────

def _demo_route(origin: tuple, destination: tuple,
                waypoints: list = None) -> dict:
    """
    High-quality synthetic road route for offline / no-key use.

    If waypoints are provided, the spline passes through them in order.
    NOT a straight line — uses cubic spline through organic waypoints
    + inserts 2 sharp corners to simulate real road turns.
    """
    print("    [DEMO] Generating synthetic road route...")
    la0, lo0 = origin
    la1, lo1 = destination
    total_d = haversine(origin, destination)

    np.random.seed(abs(int(la0 * 1000 + lo0 * 100)) % 9999)

    # If user provided waypoints, use them as the spline control points
    if waypoints and len(waypoints) > 0:
        wpts = [origin] + list(waypoints) + [destination]
    else:
        # Build 5 organic waypoints between origin and destination
        dlat = la1 - la0;  dlon = lo1 - lo0
        perp_la = -dlon;  perp_lo = dlat
        pm = math.sqrt(perp_la**2 + perp_lo**2) + 1e-9
        perp_la /= pm;    perp_lo /= pm
        wpts = [origin]
        for k in range(1, 5):
            frac   = k / 5
            offset = (0.0025 * math.sin(frac * math.pi * 3)
                      + 0.0008 * float(np.random.randn()))
            wpts.append((la0 + frac*dlat + offset*perp_la,
                         lo0 + frac*dlon + offset*perp_lo))
        wpts.append(destination)

    # Spline through all waypoints
    t  = np.linspace(0, 1, len(wpts))
    tt = np.linspace(0, 1, max(300, int(total_d / MAX_GAP_METRES)))
    cs_la = CubicSpline(t, [w[0] for w in wpts])
    cs_lo = CubicSpline(t, [w[1] for w in wpts])
    coords = [(float(cs_la(ti)), float(cs_lo(ti))) for ti in tt]

    # Add 2 realistic sharp corners if no user waypoints provided
    if not waypoints:
        for frac_pos in [0.28, 0.63]:
            idx = int(frac_pos * len(coords))
            if 3 < idx < len(coords) - 3:
                p  = coords[idx];   pp = coords[idx-1]
                dlt = p[0]-pp[0];   dlg = p[1]-pp[1]
                coords.insert(idx, (p[0] + (-dlg)*5, p[1] + ( dlt)*5))

    dense  = densify_coordinates(coords, MAX_GAP_METRES)
    d_m    = sum(haversine(dense[i], dense[i+1]) for i in range(len(dense)-1))
    t_s    = d_m / (40 / 3.6)

    # Surface: asphalt on main stretch, gravel at ends
    n      = len(dense)
    surf   = {}
    for i in range(n):
        surf[i] = "asphalt" if 10 < i < n-10 else "compacted_gravel"

    steps_demo = [
        {"instruction":"Head towards destination","name":"Main Road",
         "distance_m":d_m*0.35,"duration_s":t_s*0.35,"way_points":[0]},
        {"instruction":"Turn right","name":"Junction Road",
         "distance_m":d_m*0.30,"duration_s":t_s*0.30,"way_points":[int(n*0.35)]},
        {"instruction":"Continue straight","name":"Destination Road",
         "distance_m":d_m*0.35,"duration_s":t_s*0.35,"way_points":[int(n*0.65)]},
    ]

    return {
        "coordinates"      : dense,
        "distance_m"       : d_m,
        "duration_s"       : t_s,
        "distance_txt"     : f"{d_m/1000:.2f} km",
        "duration_txt"     : f"{int(t_s//60)} min {int(t_s%60)} sec",
        "steps"            : steps_demo,
        "road_names"       : ["Main Road","Junction Road","Destination Road"],
        "surface_per_point": surf,
        "waypoint_indices" : {0, int(n*0.35), int(n*0.65)},
        "source"           : "Demo (offline)",
        "profile"          : "driving-car",
    }


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC ENTRY POINT  (MODIFIED: accepts waypoints)
# ─────────────────────────────────────────────────────────────────────────────

def fetch_route(origin: tuple, destination: tuple,
                api_key: str = None,
                waypoints: list = None) -> dict:
    """
    Fetch a real road route. Tries ORS → OSRM → demo in that order.

    Parameters
    ----------
    origin      : (lat, lon) of start
    destination : (lat, lon) of end
    api_key     : ORS key (defaults to config.ORS_API_KEY)
    waypoints   : optional list of (lat, lon) intermediate stops.
                  These are passed directly to the routing API so the
                  returned path follows the actual road through each stop.
                  In main.py, these come from "one-stop", "second-stop", etc.

    Returns
    -------
    route dict (see module docstring for field list)
    """
    key = api_key or ORS_API_KEY
    wpt_n = len(waypoints) if waypoints else 0

    print(f"\n{'='*62}")
    print(f"  STEP 1 — ROUTE FETCH")
    print(f"  Origin      : {origin[0]:.6f}, {origin[1]:.6f}")
    if waypoints:
        for i, w in enumerate(waypoints, 1):
            print(f"  Waypoint {i:<3}: {w[0]:.6f}, {w[1]:.6f}")
    print(f"  Destination : {destination[0]:.6f}, {destination[1]:.6f}")
    print(f"  Total stops : {wpt_n + 2}  ({wpt_n} intermediate)")
    print(f"{'='*62}")

    route = None

    # ── Try ORS first if key is available ─────────────────────────────────
    if key and key not in ("", "YOUR_KEY_HERE"):
        try:
            print("  Trying OpenRouteService...")
            route = _fetch_ors(origin, destination, key, ORS_PROFILE,
                               waypoints=waypoints)
            print(f"  ✓ ORS success — {len(route['coordinates'])} raw points")
        except Exception as e:
            print(f"  ✗ ORS failed: {e}")

    # ── Try OSRM if ORS failed or no key ──────────────────────────────────
    if route is None:
        try:
            print("  Trying OSRM (no key needed)...")
            route = _fetch_osrm(origin, destination,
                                waypoints=waypoints)
            print(f"  ✓ OSRM success — {len(route['coordinates'])} raw points")
        except Exception as e:
            print(f"  ✗ OSRM failed: {e}")

    # ── Demo fallback ──────────────────────────────────────────────────────
    if route is None:
        print("  All APIs failed — using offline demo route")
        print("  (Run on a machine with internet + ORS key for real roads)")
        route = _demo_route(origin, destination, waypoints=waypoints)

    # ── Densify ───────────────────────────────────────────────────────────
    n_raw = len(route["coordinates"])
    route["coordinates"] = densify_coordinates(
        route["coordinates"], MAX_GAP_METRES)
    n_dense = len(route["coordinates"])
    print(f"\n  Source      : {route['source']}")
    print(f"  Distance    : {route['distance_txt']}")
    print(f"  Duration    : {route['duration_txt']}  (from API)")
    print(f"  Points      : {n_raw} raw → {n_dense} dense (max gap {MAX_GAP_METRES}m)")

    # ── Add metadata ──────────────────────────────────────────────────────
    route["origin"]      = origin
    route["destination"] = destination
    route["waypoints"]   = waypoints or []   # store for reference

    # ── Save raw route JSON ───────────────────────────────────────────────
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    save = {k: (list(v) if isinstance(v, set) else v)
            for k, v in route.items()
            if k not in ("surface_per_point", "waypoint_indices")}
    save["surface_per_point"] = {str(k): v
                                  for k, v in route["surface_per_point"].items()}
    save["waypoint_indices"]  = list(route["waypoint_indices"])

    out_path = os.path.join(OUTPUT_DIR, "raw_route.json")
    with open(out_path, "w") as f:
        json.dump(save, f, indent=2)
    print(f"  Raw route   → {out_path}")

    return route
