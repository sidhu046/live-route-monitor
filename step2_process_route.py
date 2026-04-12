"""
step2_process_route.py
=======================
STEP 2 — Route Processing: Geometry Analysis + Feature Extraction.

FOR EVERY POINT IN THE ROUTE THIS COMPUTES
-------------------------------------------
  dist_to_next_m      distance to the next GPS point (metres)
  cumulative_dist_m   total distance from start to this point
  turning_angle_deg   angle at this point (degrees, 180°=straight)
  curvature_1pm       curvature κ = 1/radius  (1/metres)
  radius_m            radius of curvature (metres)
  turn_type           "straight" | "mild_curve" | "sharp_curve" |
                      "very_sharp_curve" | "u_turn" | "intersection"
  surface             road surface from ORS (or "unknown")

CURVATURE FORMULA  (IEEE paper Eq. 8)
--------------------------------------
For three consecutive points P1, P2, P3 (in local Cartesian metres):

  a = |P2 - P3|,  b = |P1 - P3|,  c = |P1 - P2|
  s = (a + b + c) / 2                          ← semi-perimeter
  Area = sqrt( s(s-a)(s-b)(s-c) )              ← Heron's formula
  r = (a × b × c) / (4 × Area)                ← circumcircle radius
  κ = 1 / r                                    ← curvature

TURNING ANGLE FORMULA
----------------------
  A = P2 − P1   (incoming direction)
  B = P3 − P2   (outgoing direction)
  angle = 180° − arccos( dot(A,B) / (|A|×|B|) )
  → 180° = straight road
  → 90°  = right-angle turn
  → 0°   = U-turn
"""

import math
import numpy as np
from config import ANGLE_THRESHOLD, OUTPUT_DIR


# ─────────────────────────────────────────────────────────────────────────────
# LOCAL COORDINATE CONVERSION
# ─────────────────────────────────────────────────────────────────────────────

def latlon_to_xy(coords: list) -> np.ndarray:
    """
    Convert (lat, lon) list → local Cartesian (x, y) metres.
    Equirectangular projection centred on first point.
    Accurate for distances < 100 km.
    """
    R    = 6_371_000
    lat0 = math.radians(coords[0][0])
    out  = []
    for lat, lon in coords:
        x = R * math.radians(lon - coords[0][1]) * math.cos(lat0)
        y = R * math.radians(lat - coords[0][0])
        out.append([x, y])
    return np.array(out)


def haversine(p1, p2):
    R = 6_371_000
    la1,lo1 = math.radians(p1[0]),math.radians(p1[1])
    la2,lo2 = math.radians(p2[0]),math.radians(p2[1])
    a = (math.sin((la2-la1)/2)**2
         + math.cos(la1)*math.cos(la2)*math.sin((lo2-lo1)/2)**2)
    return R * 2 * math.asin(math.sqrt(a))


# ─────────────────────────────────────────────────────────────────────────────
# CURVATURE & ANGLE CALCULATIONS
# ─────────────────────────────────────────────────────────────────────────────

def _circumcircle_radius(p1, p2, p3):
    """
    Circumcircle radius of triangle P1-P2-P3 using Heron's formula.
    Returns (radius_m, curvature_1pm).
    """
    a = np.linalg.norm(p2 - p3)
    b = np.linalg.norm(p1 - p3)
    c = np.linalg.norm(p1 - p2)
    s = (a + b + c) / 2.0
    area_sq = max(0.0, s * (s-a) * (s-b) * (s-c))
    if area_sq < 1e-14 or c < 1e-9:
        return 1e6, 0.0
    area   = math.sqrt(area_sq)
    r      = (a * b * c) / (4.0 * area + 1e-12)
    return r, 1.0 / r


def _turning_angle(p1, p2, p3):
    """
    Interior turning angle at P2 in degrees.
    180° = straight,  90° = right-angle,  0° = U-turn.
    """
    A = p2 - p1;  B = p3 - p2
    mA = np.linalg.norm(A);  mB = np.linalg.norm(B)
    if mA < 1e-9 or mB < 1e-9:
        return 180.0
    cos_val = np.clip(np.dot(A, B) / (mA * mB), -1.0, 1.0)
    return 180.0 - math.degrees(math.acos(cos_val))


# ─────────────────────────────────────────────────────────────────────────────
# TURN CLASSIFICATION
# ─────────────────────────────────────────────────────────────────────────────

def classify_turn(angle_deg: float) -> str:
    """
    Map a turning angle to a road segment type.
    Thresholds are defined in config.py → ANGLE_THRESHOLD.
    """
    t = ANGLE_THRESHOLD
    if   angle_deg >= t["straight"]:          return "straight"
    elif angle_deg >= t["mild_curve"]:         return "mild_curve"
    elif angle_deg >= t["sharp_curve"]:        return "sharp_curve"
    elif angle_deg >= t["very_sharp_curve"]:   return "very_sharp_curve"
    else:                                       return "u_turn"


# ─────────────────────────────────────────────────────────────────────────────
# MAIN PROCESSING FUNCTION
# ─────────────────────────────────────────────────────────────────────────────

def process_route(route: dict) -> list:
    """
    Convert raw route coordinates into a fully-annotated segment list.

    Parameters
    ----------
    route : dict from step1_fetch_route.fetch_route()

    Returns
    -------
    segments : list of dicts, one per GPS point, with fields:
        point_id, lat, lon,
        dist_to_next_m, cumulative_dist_m,
        turning_angle_deg, curvature_1pm, radius_m,
        turn_type, surface,
        is_waypoint,
        xy_x, xy_y   (local Cartesian, for plotting)
    """
    coords  = route["coordinates"]
    surf    = route.get("surface_per_point", {})
    wp_idx  = route.get("waypoint_indices", set())
    n       = len(coords)

    # Convert to local Cartesian for accurate angle/curvature computation
    xy = latlon_to_xy(coords)

    # ── Distance to next point ────────────────────────────────────────────
    dists = np.zeros(n)
    for i in range(n - 1):
        dists[i] = haversine(coords[i], coords[i+1])
    # dists[n-1] = 0 (last point)

    cum_dist = np.concatenate([[0.0], np.cumsum(dists[:-1])])

    # ── Turning angle + curvature at every point ──────────────────────────
    angles = np.full(n, 180.0)
    radii  = np.full(n, 1e6)
    kappas = np.zeros(n)

    for i in range(1, n - 1):
        angles[i]            = _turning_angle(xy[i-1], xy[i], xy[i+1])
        radii[i], kappas[i]  = _circumcircle_radius(xy[i-1], xy[i], xy[i+1])

    # Endpoints copy from nearest interior point
    angles[0] = angles[1];   angles[-1] = angles[-2]
    radii[0]  = radii[1];    radii[-1]  = radii[-2]
    kappas[0] = kappas[1];   kappas[-1] = kappas[-2]

    # ── Build segment list ────────────────────────────────────────────────
    segments = []
    for i in range(n):
        turn_type = classify_turn(float(angles[i]))

        # Upgrade to intersection if it's a step waypoint + has a turn
        if i in wp_idx and angles[i] < ANGLE_THRESHOLD["straight"]:
            turn_type = "intersection"

        segments.append({
            "point_id"          : i,
            "lat"               : round(coords[i][0], 7),
            "lon"               : round(coords[i][1], 7),
            "dist_to_next_m"    : round(float(dists[i]),    3),
            "cumulative_dist_m" : round(float(cum_dist[i]), 2),
            "turning_angle_deg" : round(float(angles[i]),   3),
            "curvature_1pm"     : round(float(kappas[i]),   7),
            "radius_m"          : round(float(min(radii[i], 9999.0)), 2),
            "turn_type"         : turn_type,
            "surface"           : surf.get(i, "unknown"),
            "is_waypoint"       : (i in wp_idx),
            "xy_x"              : round(float(xy[i][0]), 3),
            "xy_y"              : round(float(xy[i][1]), 3),
        })

    # ── Print statistics ──────────────────────────────────────────────────
    type_counts = {}
    for s in segments:
        t = s["turn_type"]
        type_counts[t] = type_counts.get(t, 0) + 1

    print(f"\n{'='*62}")
    print(f"  STEP 2 — GEOMETRY ANALYSIS")
    print(f"{'='*62}")
    print(f"  Total points       : {n}")
    print(f"  Total distance     : {cum_dist[-1]/1000:.4f} km")
    valid_k = kappas[kappas > 1e-6]
    if len(valid_k):
        print(f"  Max curvature      : {np.max(valid_k):.6f} 1/m")
        print(f"  Min corner radius  : {1.0/np.max(valid_k):.2f} m")
    print(f"  Avg turning angle  : {np.mean(angles):.1f}°")
    print(f"\n  Segment breakdown:")
    for t, c in sorted(type_counts.items(), key=lambda x: -x[1]):
        pct = 100 * c // n
        bar = "█" * min(40, max(1, c * 40 // n))
        print(f"    {t:<24}: {c:>5}  ({pct:>2}%)  {bar}")

    return segments
