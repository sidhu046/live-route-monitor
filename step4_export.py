"""
step4_export.py
================
STEP 4 — Export all route data to structured files.

FILES GENERATED
---------------
route_coordinates.csv      — basic CSV: latitude, longitude
                              (exactly as requested in your requirement)

route_full_analysis.csv    — enhanced CSV: lat, lon, turn_type,
                              recommended_speed, risk_level + all metrics

high_risk_zones.csv        — only the HIGH-risk points (quick lookup table)

navigation_data.json       — complete structured JSON

summary_report.txt         — human-readable analysis report

turn_by_turn.txt           — navigation instructions from the API

CSV FORMAT DETAILS
------------------
Basic CSV (for MATLAB compatibility):
  latitude, longitude
  16.506200, 80.648000
  16.507100, 80.649200
  ...

This matches the format your MATLAB scripts expect.
Load in MATLAB with:
  data = readtable('route_coordinates.csv');
  x = data.longitude;
  y = data.latitude;

Enhanced CSV (for analysis):
  point_id, latitude, longitude,
  dist_to_next_m, cumulative_dist_m,
  turning_angle_deg, curvature_1pm, radius_m,
  turn_type, surface,
  raw_speed_kmh, recommended_speed_kmh,
  segment_time_s, elapsed_time_s, elapsed_time_min,
  risk_level
"""

import csv
import json
import os
from config import OUTPUT_DIR


# ─────────────────────────────────────────────────────────────────────────────
# BASIC COORDINATES CSV  (latitude, longitude only)
# ─────────────────────────────────────────────────────────────────────────────

def export_basic_csv(segments: list, path: str = None) -> str:
    """
    Write simple latitude, longitude CSV.
    Compatible with MATLAB readtable() / readmatrix().

    Format:
        latitude,longitude
        16.5062000,80.6480000
        16.5071234,80.6492345
        ...
    """
    if path is None:
        path = os.path.join(OUTPUT_DIR, "route_coordinates.csv")
    os.makedirs(os.path.dirname(path), exist_ok=True)

    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["latitude", "longitude"])
        for s in segments:
            writer.writerow([s["lat"], s["lon"]])

    print(f"  Basic CSV   → {path}  ({len(segments)} rows)")
    return path


# ─────────────────────────────────────────────────────────────────────────────
# ENHANCED CSV  (all analysis columns)
# ─────────────────────────────────────────────────────────────────────────────

def export_enhanced_csv(segments: list, path: str = None) -> str:
    """
    Write full analysis CSV with all computed fields.
    This is the main output for the speed/safety system.
    """
    if path is None:
        path = os.path.join(OUTPUT_DIR, "route_full_analysis.csv")

    # Check whether step7 friction data is present
    has_friction = segments and "friction_mu" in segments[0]

    fields = [
        "point_id", "latitude", "longitude",
        "dist_to_next_m", "cumulative_dist_m",
        "turning_angle_deg", "curvature_1pm", "radius_m",
        "turn_type", "surface",
        "raw_speed_kmh", "recommended_speed_kmh",
        "segment_time_s", "elapsed_time_s", "elapsed_time_min",
        "risk_level",
    ]
    # Append friction columns only when step7 has been run
    if has_friction:
        fields += [
            "road_type", "road_condition",
            "friction_mu", "friction_factor", "friction_risk",
            "adjusted_speed_kmh", "stopping_dist_m",
        ]

    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for s in segments:
            row = {
                "point_id"             : s["point_id"],
                "latitude"             : s["lat"],
                "longitude"            : s["lon"],
                "dist_to_next_m"       : s["dist_to_next_m"],
                "cumulative_dist_m"    : s["cumulative_dist_m"],
                "turning_angle_deg"    : s["turning_angle_deg"],
                "curvature_1pm"        : s["curvature_1pm"],
                "radius_m"             : s["radius_m"],
                "turn_type"            : s["turn_type"],
                "surface"              : s.get("surface", ""),
                "raw_speed_kmh"        : s.get("raw_speed_kmh", ""),
                "recommended_speed_kmh": s.get("recommended_speed_kmh", ""),
                "segment_time_s"       : s.get("segment_time_s", ""),
                "elapsed_time_s"       : s.get("elapsed_time_s", ""),
                "elapsed_time_min"     : s.get("elapsed_time_min", ""),
                "risk_level"           : s.get("risk_level", ""),
            }
            if has_friction:
                row.update({
                    "road_type"         : s.get("road_type", ""),
                    "road_condition"    : s.get("road_condition", ""),
                    "friction_mu"       : s.get("friction_mu", ""),
                    "friction_factor"   : s.get("friction_factor", ""),
                    "friction_risk"     : s.get("friction_risk", ""),
                    "adjusted_speed_kmh": s.get("adjusted_speed_kmh", ""),
                    "stopping_dist_m"   : s.get("stopping_dist_m", ""),
                })
            writer.writerow(row)

    print(f"  Enhanced CSV → {path}")
    return path


# ─────────────────────────────────────────────────────────────────────────────
# HIGH-RISK ZONES CSV
# ─────────────────────────────────────────────────────────────────────────────

def export_high_risk_csv(segments: list, path: str = None) -> str:
    """
    Export only HIGH-risk points — useful for quick lookup and alerting.
    """
    if path is None:
        path = os.path.join(OUTPUT_DIR, "high_risk_zones.csv")

    high_risk = [s for s in segments if s.get("risk_level") == "high"]

    fields = [
        "point_id", "latitude", "longitude",
        "cumulative_dist_m", "turn_type",
        "recommended_speed_kmh", "turning_angle_deg",
        "surface", "risk_level",
    ]

    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for s in high_risk:
            writer.writerow({
                "point_id"             : s["point_id"],
                "latitude"             : s["lat"],
                "longitude"            : s["lon"],
                "cumulative_dist_m"    : s["cumulative_dist_m"],
                "turn_type"            : s["turn_type"],
                "recommended_speed_kmh": s.get("recommended_speed_kmh", ""),
                "turning_angle_deg"    : s["turning_angle_deg"],
                "surface"              : s.get("surface", ""),
                "risk_level"           : "high",
            })

    print(f"  High-risk CSV → {path}  ({len(high_risk)} zones)")
    return path


# ─────────────────────────────────────────────────────────────────────────────
# JSON EXPORT
# ─────────────────────────────────────────────────────────────────────────────

def export_json(segments: list, route: dict, path: str = None) -> str:
    """Export complete structured JSON for programmatic access."""
    if path is None:
        path = os.path.join(OUTPUT_DIR, "navigation_data.json")

    spd  = [s.get("recommended_speed_kmh", 0) for s in segments]
    rc   = {"low": 0, "medium": 0, "high": 0}
    for s in segments:
        rc[s.get("risk_level", "low")] = rc.get(s.get("risk_level","low"),0)+1

    out = {
        "route_info": {
            "source"          : route.get("source", ""),
            "profile"         : route.get("profile", ""),
            "origin"          : route.get("origin"),
            "destination"     : route.get("destination"),
            "waypoints"       : route.get("waypoints", []),
            "distance_txt"    : route.get("distance_txt", ""),
            "distance_m"      : round(route.get("distance_m", 0), 1),
            "api_duration_txt": route.get("duration_txt", ""),
            "est_ride_min"    : round(segments[-1].get("elapsed_time_min",0),2),
            "total_points"    : len(segments),
            "road_names"      : route.get("road_names", []),
        },
        "speed_stats": {
            "min_kmh" : round(min(spd), 1),
            "max_kmh" : round(max(spd), 1),
            "avg_kmh" : round(sum(spd)/len(spd), 1),
        },
        "risk_summary" : rc,
        "segments": [
            {k: v for k, v in s.items() if k not in ("xy_x","xy_y","is_waypoint")}
            for s in segments
        ],
    }

    with open(path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"  JSON        → {path}")
    return path


# ─────────────────────────────────────────────────────────────────────────────
# SUMMARY TEXT REPORT
# ─────────────────────────────────────────────────────────────────────────────

def export_summary(segments: list, route: dict, path: str = None) -> str:
    """Write a human-readable analysis summary."""
    if path is None:
        path = os.path.join(OUTPUT_DIR, "summary_report.txt")

    spd  = [s.get("recommended_speed_kmh", 0) for s in segments]
    rc   = {"low":0,"medium":0,"high":0}
    tc   = {}
    for s in segments:
        rc[s.get("risk_level","low")] = rc.get(s.get("risk_level","low"),0)+1
        tc[s["turn_type"]]            = tc.get(s["turn_type"], 0) + 1
    total     = len(segments)
    high_pts  = [(s["lat"],s["lon"],s.get("recommended_speed_kmh",0),
                   s["turn_type"],s["cumulative_dist_m"])
                  for s in segments if s.get("risk_level")=="high"]
    ride_min  = segments[-1].get("elapsed_time_min", 0)

    waypoints = route.get("waypoints", [])

    L = [
        "="*64,
        "  ROAD NAVIGATION & SPEED OPTIMIZATION — ANALYSIS REPORT",
        "="*64, "",
        "  ROUTE INFORMATION",
        "  " + "-"*46,
        f"  API Source      : {route.get('source','')}",
        f"  Route Profile   : {route.get('profile','')}",
        f"  Origin          : {route.get('origin','')}",
    ]
    for i, w in enumerate(waypoints, 1):
        L.append(f"  Waypoint {i:<3}     : {w}")
    L += [
        f"  Destination     : {route.get('destination','')}",
        f"  Total Stops     : {len(waypoints) + 2}  ({len(waypoints)} intermediate)",
        f"  Total Distance  : {route.get('distance_txt','')}",
        f"  API Duration    : {route.get('duration_txt','')}",
        f"  Est. Ride Time  : {ride_min:.2f} min  (at recommended speeds)",
        f"  Total Points    : {total}",
        "",
        "  SPEED STATISTICS",
        "  " + "-"*46,
        f"  Minimum speed   : {min(spd):.1f} km/h",
        f"  Maximum speed   : {max(spd):.1f} km/h",
        f"  Average speed   : {sum(spd)/len(spd):.1f} km/h",
        "",
        "  ROAD GEOMETRY BREAKDOWN",
        "  " + "-"*46,
    ]
    for t, c in sorted(tc.items(), key=lambda x: -x[1]):
        pct = 100 * c // total
        L.append(f"  {t:<24}: {c:>5}  ({pct:>2}%)")

    L += [
        "",
        "  RISK ANALYSIS",
        "  " + "-"*46,
        f"  LOW    risk     : {rc['low']:>5}  ({100*rc['low']//total:>2}%)",
        f"  MEDIUM risk     : {rc['medium']:>5}  ({100*rc['medium']//total:>2}%)",
        f"  HIGH   risk     : {rc['high']:>5}  ({100*rc['high']//total:>2}%)",
        "",
        "  HIGH-RISK LOCATIONS (first 20)",
        "  " + "-"*46,
        "  #   Latitude     Longitude    Speed  Type                Dist(m)",
    ]
    for k, (lat,lon,spd_v,tt,dist) in enumerate(high_pts[:20], 1):
        L.append(f"  {k:<3} {lat:.7f}  {lon:.7f}  "
                 f"{spd_v:>5.0f}  {tt:<20}  {dist:.0f}")

    if route.get("road_names"):
        L += ["", "  ROADS ALONG ROUTE", "  " + "-"*46]
        for rn in route["road_names"][:20]:
            L.append(f"  • {rn}")

    # ── Friction section (only when step7 has been run) ────────────────────
    try:
        from step7_road_input import friction_report_lines
        L += friction_report_lines(segments)
    except ImportError:
        pass

    L += ["", "="*64]
    text = "\n".join(L)

    print(text)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"\n  Summary TXT → {path}")
    return path


# ─────────────────────────────────────────────────────────────────────────────
# TURN-BY-TURN TEXT
# ─────────────────────────────────────────────────────────────────────────────

def export_turn_by_turn(route: dict, path: str = None) -> str:
    """Write navigation instructions from API steps."""
    if path is None:
        path = os.path.join(OUTPUT_DIR, "turn_by_turn.txt")

    steps = route.get("steps", [])
    L = ["="*64, "  TURN-BY-TURN NAVIGATION", "="*64, ""]

    for k, step in enumerate(steps, 1):
        d = step.get("distance_m", 0)
        t = step.get("duration_s", 0)
        dist_txt = f"{d/1000:.2f} km" if d >= 1000 else f"{d:.0f} m"
        time_txt = f"{int(t//60)} min {int(t%60)} sec" if t >= 60 else f"{t:.0f} sec"
        name     = f"  on {step['name']}" if step.get("name") else ""
        L.append(f"  {k:>3}. {step.get('instruction','')}")
        L.append(f"       Distance: {dist_txt}  |  Time: {time_txt}{name}")
        L.append("")

    with open(path, "w") as f:
        f.write("\n".join(L))
    print(f"  Turn-by-turn → {path}")
    return path


# ─────────────────────────────────────────────────────────────────────────────
# RUNNER
# ─────────────────────────────────────────────────────────────────────────────

def run_export(segments: list, route: dict,
               out_dir: str = None) -> dict:
    """Export all files. Returns dict of {name: file_path}."""
    _dir = out_dir or OUTPUT_DIR
    os.makedirs(_dir, exist_ok=True)

    print(f"\n{'='*62}")
    print(f"  STEP 4 — EXPORT FILES")
    print(f"{'='*62}")

    return {
        "basic_csv"    : export_basic_csv(
                            segments,
                            os.path.join(_dir, "route_coordinates.csv")),
        "enhanced_csv" : export_enhanced_csv(
                            segments,
                            os.path.join(_dir, "route_full_analysis.csv")),
        "high_risk_csv": export_high_risk_csv(
                            segments,
                            os.path.join(_dir, "high_risk_zones.csv")),
        "json"         : export_json(
                            segments, route,
                            os.path.join(_dir, "navigation_data.json")),
        "summary"      : export_summary(
                            segments, route,
                            os.path.join(_dir, "summary_report.txt")),
        "tbt"          : export_turn_by_turn(
                            route,
                            os.path.join(_dir, "turn_by_turn.txt")),
    }
