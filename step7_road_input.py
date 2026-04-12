"""
step7_road_input.py
====================
STEP 7 — Road Type & Condition Input + Friction-Based Safety Enhancement.

WHAT THIS MODULE DOES
---------------------
1. Asks the user (interactively via terminal) two questions:
     a) What type of road is this route?
        Options: tar_road, cc_road, mud_road, highway, gravel_road, dirt_track
     b) What is the road condition right now?
        Options: dry, wet, flooded, icy, snow_covered

2. Looks up the friction coefficient (μ) for that combination from a built-in
   dataset (based on published tyre-road friction research data).

3. Uses friction to compute:
     - Safe stopping distance  = v² / (2 × μ × g)   [metres]
     - Friction speed factor   = sqrt(μ / μ_ref)     [dimensionless multiplier]
       where μ_ref = 0.80 (dry tar road, the reference condition)

4. Applies the friction speed factor to the already-computed
   recommended_speed_kmh for every segment:
     adjusted_speed = recommended_speed_kmh × friction_factor
   This LOWERS the speed on wet/icy/mud roads and DOES NOT change anything
   on a dry tar road (factor = 1.0).

5. Adds new fields to every segment dict:
     road_type          : e.g. "tar_road"
     road_condition     : e.g. "wet"
     friction_mu        : e.g. 0.45
     friction_factor    : e.g. 0.75
     friction_risk      : "low" | "medium" | "high"  (based on μ alone)
     stopping_dist_m    : stopping distance at adjusted speed in metres
     adjusted_speed_kmh : final speed after friction adjustment

6. Re-evaluates risk_level: if friction alone makes the segment high-risk
   (μ < 0.40), the segment is upgraded to "high" regardless of geometry.

FRICTION DATASET
----------------
Source: Compiled from published road safety research:
  - AASHTO Green Book (road design standards)
  - UK DMRB (Design Manual for Roads and Bridges)
  - Indian IRC:SP:84 (road safety manual)
  - Typical published μ ranges for tyre-road pairs

Road type + condition → friction coefficient (μ):

  Road type    | Dry  | Wet  | Flooded | Icy   | Snow
  -------------|------|------|---------|-------|------
  tar_road     | 0.80 | 0.45 | 0.25    | 0.15  | 0.20
  highway      | 0.85 | 0.50 | 0.28    | 0.12  | 0.18
  cc_road      | 0.75 | 0.42 | 0.22    | 0.14  | 0.19
  gravel_road  | 0.55 | 0.35 | 0.18    | 0.12  | 0.15
  mud_road     | 0.40 | 0.20 | 0.10    | 0.08  | 0.10
  dirt_track   | 0.45 | 0.25 | 0.12    | 0.09  | 0.12

FRICTION RISK THRESHOLDS
------------------------
  μ ≥ 0.60  → friction risk = LOW    (safe, normal braking)
  μ ≥ 0.35  → friction risk = MEDIUM (caution, longer stopping)
  μ <  0.35 → friction risk = HIGH   (dangerous, severely reduced grip)

NON-DESTRUCTIVE INTEGRATION
----------------------------
This module does NOT modify any existing fields. It adds NEW fields:
  adjusted_speed_kmh   (new — friction-corrected speed)
  road_type            (new)
  road_condition       (new)
  friction_mu          (new)
  friction_factor      (new)
  friction_risk        (new)
  stopping_dist_m      (new)

The existing recommended_speed_kmh is LEFT INTACT so all existing code
(step4 CSV export, step5 maps, step6 live monitor) continues to work
exactly as before. Only the live monitor and summary report are enhanced
to also show the new adjusted_speed_kmh.

USAGE (called from main.py between step3 and step4)
---------------------------------------------------
  from step7_road_input import ask_road_conditions, apply_friction
  road_type, road_condition = ask_road_conditions()
  segments = apply_friction(segments, road_type, road_condition)
"""

import math


# ─────────────────────────────────────────────────────────────────────────────
# FRICTION DATASET
# μ values from published road safety research (see module docstring)
# ─────────────────────────────────────────────────────────────────────────────

FRICTION_TABLE = {
    #  road_type       : { condition : μ }
    "tar_road"    : {"dry": 0.80, "wet": 0.45, "flooded": 0.25, "icy": 0.15, "snow_covered": 0.20},
    "highway"     : {"dry": 0.85, "wet": 0.50, "flooded": 0.28, "icy": 0.12, "snow_covered": 0.18},
    "cc_road"     : {"dry": 0.75, "wet": 0.42, "flooded": 0.22, "icy": 0.14, "snow_covered": 0.19},
    "gravel_road" : {"dry": 0.55, "wet": 0.35, "flooded": 0.18, "icy": 0.12, "snow_covered": 0.15},
    "mud_road"    : {"dry": 0.40, "wet": 0.20, "flooded": 0.10, "icy": 0.08, "snow_covered": 0.10},
    "dirt_track"  : {"dry": 0.45, "wet": 0.25, "flooded": 0.12, "icy": 0.09, "snow_covered": 0.12},
}

# Reference friction (dry tar road) — factor = 1.0 for this baseline
MU_REFERENCE = 0.80

# Gravitational acceleration (m/s²)
G = 9.81

# Friction risk thresholds
MU_HIGH_RISK   = 0.35   # μ < this → HIGH friction risk
MU_MEDIUM_RISK = 0.60   # μ < this → MEDIUM friction risk

# Human-readable labels for display
ROAD_TYPE_LABELS = {
    "tar_road"   : "Tar Road (Bituminous)",
    "highway"    : "Highway / Expressway",
    "cc_road"    : "CC Road (Concrete Cement)",
    "gravel_road": "Gravel Road",
    "mud_road"   : "Mud Road",
    "dirt_track" : "Dirt Track / Kachcha Road",
}

ROAD_CONDITION_LABELS = {
    "dry"         : "Dry",
    "wet"         : "Wet (rain / recent rain)",
    "flooded"     : "Flooded / Waterlogged",
    "icy"         : "Icy / Frost",
    "snow_covered": "Snow Covered",
}


# ─────────────────────────────────────────────────────────────────────────────
# USER INPUT
# ─────────────────────────────────────────────────────────────────────────────

def ask_road_conditions() -> tuple:
    """
    Ask the user (via terminal) for road type and road condition.

    Returns
    -------
    (road_type, road_condition) — both are string keys matching FRICTION_TABLE.

    Handles:
      - Case-insensitive input
      - Number shortcuts (user can type 1,2,3... instead of full name)
      - Invalid input → loops until valid answer given
      - Non-interactive / piped stdin → returns safe defaults ("tar_road","dry")
    """
    import sys

    # Detect non-interactive (e.g. piped stdin in testing)
    if not sys.stdin.isatty():
        print("  [Step 7] Non-interactive mode → using defaults: tar_road / dry")
        return "tar_road", "dry"

    print(f"\n{'='*62}")
    print(f"  STEP 7 — ROAD TYPE & CONDITION INPUT")
    print(f"{'='*62}")
    print("  This information adjusts speed limits and safety calculations")
    print("  based on road friction coefficients (μ) from published data.")
    print()

    # ── Ask road type ─────────────────────────────────────────────────────
    road_types = list(FRICTION_TABLE.keys())
    print("  ROAD TYPE — What kind of road is this route?")
    for i, k in enumerate(road_types, 1):
        print(f"    {i}. {ROAD_TYPE_LABELS[k]}  [{k}]")
    print()

    road_type = None
    while road_type is None:
        raw = input("  Enter number (1-6) or road type name: ").strip().lower()
        # Number shortcut
        if raw.isdigit() and 1 <= int(raw) <= len(road_types):
            road_type = road_types[int(raw) - 1]
        # Direct name match
        elif raw in FRICTION_TABLE:
            road_type = raw
        # Partial match (user typed "tar" → matches "tar_road")
        else:
            matches = [k for k in road_types if raw in k]
            if len(matches) == 1:
                road_type = matches[0]
            else:
                print(f"  ✗ Invalid. Please enter a number 1–{len(road_types)} or a road type name.")

    print(f"  ✓ Road type selected: {ROAD_TYPE_LABELS[road_type]}")
    print()

    # ── Ask road condition ────────────────────────────────────────────────
    conditions = list(ROAD_CONDITION_LABELS.keys())
    print("  ROAD CONDITION — What is the current road condition?")
    for i, k in enumerate(conditions, 1):
        mu = FRICTION_TABLE[road_type][k]
        print(f"    {i}. {ROAD_CONDITION_LABELS[k]}  [μ = {mu:.2f}]")
    print()

    road_condition = None
    while road_condition is None:
        raw = input("  Enter number (1-5) or condition name: ").strip().lower()
        if raw.isdigit() and 1 <= int(raw) <= len(conditions):
            road_condition = conditions[int(raw) - 1]
        elif raw in ROAD_CONDITION_LABELS:
            road_condition = raw
        else:
            matches = [k for k in conditions if raw in k]
            if len(matches) == 1:
                road_condition = matches[0]
            else:
                print(f"  ✗ Invalid. Please enter a number 1–{len(conditions)} or a condition name.")

    mu = FRICTION_TABLE[road_type][road_condition]
    print(f"  ✓ Condition selected: {ROAD_CONDITION_LABELS[road_condition]}  (μ = {mu:.2f})")
    print()

    return road_type, road_condition


# ─────────────────────────────────────────────────────────────────────────────
# FRICTION CALCULATIONS
# ─────────────────────────────────────────────────────────────────────────────

def get_friction_mu(road_type: str, road_condition: str) -> float:
    """Look up friction coefficient from the dataset."""
    return FRICTION_TABLE.get(road_type, FRICTION_TABLE["tar_road"]) \
                         .get(road_condition, 0.80)


def friction_factor(mu: float) -> float:
    """
    Compute speed correction factor from friction coefficient.

    Based on the relationship between friction and safe cornering speed:
      v_safe ∝ sqrt(μ × r)
    For a constant radius, speed ratio = sqrt(μ / μ_ref).

    A dry tar road (μ=0.80) gives factor=1.0 — no change to speed.
    A wet mud road (μ=0.20) gives factor=0.50 — speed halved.
    """
    return math.sqrt(max(mu, 0.01) / MU_REFERENCE)


def stopping_distance_m(speed_kmh: float, mu: float) -> float:
    """
    Compute stopping distance in metres using kinematic friction formula:
      d = v² / (2 × μ × g)
    where v is in m/s.
    """
    v_ms = speed_kmh / 3.6
    return (v_ms ** 2) / (2 * max(mu, 0.01) * G)


def friction_risk_level(mu: float) -> str:
    """Classify friction risk based on μ value."""
    if   mu < MU_HIGH_RISK  : return "high"
    elif mu < MU_MEDIUM_RISK: return "medium"
    else                    : return "low"


# ─────────────────────────────────────────────────────────────────────────────
# MAIN FUNCTION — annotate segments with friction data
# ─────────────────────────────────────────────────────────────────────────────

def apply_friction(segments: list,
                   road_type: str,
                   road_condition: str) -> list:
    """
    Annotate every segment with road type, condition, friction data,
    adjusted speed, and updated risk level.

    DOES NOT modify existing fields — only adds new ones.
    The existing recommended_speed_kmh is preserved intact.

    New fields added to each segment:
      road_type           : string key, e.g. "tar_road"
      road_condition      : string key, e.g. "wet"
      road_type_label     : human-readable, e.g. "Tar Road (Bituminous)"
      road_condition_label: human-readable, e.g. "Wet (rain / recent rain)"
      friction_mu         : float, e.g. 0.45
      friction_factor     : float, e.g. 0.75
      friction_risk       : "low" | "medium" | "high"
      adjusted_speed_kmh  : recommended_speed_kmh × friction_factor (rounded)
      stopping_dist_m     : stopping distance at adjusted speed (metres)

    Risk level upgrade rule:
      If friction_risk == "high"  AND existing risk_level != "high"
        → risk_level is upgraded to "high"
      If friction_risk == "medium" AND existing risk_level == "low"
        → risk_level is upgraded to "medium"
    """
    mu     = get_friction_mu(road_type, road_condition)
    factor = friction_factor(mu)
    f_risk = friction_risk_level(mu)
    rt_lbl = ROAD_TYPE_LABELS.get(road_type, road_type)
    rc_lbl = ROAD_CONDITION_LABELS.get(road_condition, road_condition)

    print(f"\n{'='*62}")
    print(f"  STEP 7 — FRICTION ANALYSIS")
    print(f"{'='*62}")
    print(f"  Road type       : {rt_lbl}")
    print(f"  Road condition  : {rc_lbl}")
    print(f"  Friction μ      : {mu:.2f}  (reference dry tar = {MU_REFERENCE:.2f})")
    print(f"  Speed factor    : {factor:.4f}  "
          f"({'no change' if abs(factor-1)<0.001 else f'-{(1-factor)*100:.1f}% speed reduction'})")
    print(f"  Friction risk   : {f_risk.upper()}")

    upgraded_high   = 0
    upgraded_medium = 0

    for s in segments:
        base_spd   = s.get("recommended_speed_kmh", 40.0)
        adj_spd    = round(base_spd * factor, 2)
        stop_dist  = stopping_distance_m(adj_spd, mu)

        s["road_type"]            = road_type
        s["road_condition"]       = road_condition
        s["road_type_label"]      = rt_lbl
        s["road_condition_label"] = rc_lbl
        s["friction_mu"]          = round(mu, 4)
        s["friction_factor"]      = round(factor, 4)
        s["friction_risk"]        = f_risk
        s["adjusted_speed_kmh"]   = adj_spd
        s["stopping_dist_m"]      = round(stop_dist, 2)

        # ── Risk level upgrade ─────────────────────────────────────────────
        existing = s.get("risk_level", "low")
        if f_risk == "high" and existing != "high":
            s["risk_level"] = "high"
            upgraded_high  += 1
        elif f_risk == "medium" and existing == "low":
            s["risk_level"] = "medium"
            upgraded_medium += 1

    # ── Print summary ─────────────────────────────────────────────────────
    all_adj = [s["adjusted_speed_kmh"] for s in segments]
    all_stp = [s["stopping_dist_m"]    for s in segments]
    print(f"\n  Adjusted speed  : min {min(all_adj):.1f}  max {max(all_adj):.1f}  "
          f"avg {sum(all_adj)/len(all_adj):.1f} km/h")
    print(f"  Stopping dist   : min {min(all_stp):.1f}  max {max(all_stp):.1f}  "
          f"avg {sum(all_stp)/len(all_stp):.1f} m")
    if upgraded_high or upgraded_medium:
        print(f"\n  Risk upgrades (due to low friction):")
        if upgraded_high  : print(f"    ✗ {upgraded_high} segments upgraded → HIGH")
        if upgraded_medium: print(f"    ⚠ {upgraded_medium} segments upgraded → MEDIUM")
    else:
        print(f"\n  ✓ No risk upgrades needed — friction is adequate.")

    return segments


# ─────────────────────────────────────────────────────────────────────────────
# REPORT HELPER — called from step4_export.py summary
# ─────────────────────────────────────────────────────────────────────────────

def friction_report_lines(segments: list) -> list:
    """
    Return a list of text lines for inclusion in the summary_report.txt.
    Returns empty list if segments have no friction data (step 7 not run).
    """
    if not segments or "friction_mu" not in segments[0]:
        return []

    s0   = segments[0]
    mu   = s0["friction_mu"]
    f    = s0["friction_factor"]
    rt   = s0.get("road_type_label", s0.get("road_type",""))
    rc   = s0.get("road_condition_label", s0.get("road_condition",""))
    fr   = s0["friction_risk"]
    adjs = [s["adjusted_speed_kmh"] for s in segments]
    stps = [s["stopping_dist_m"]    for s in segments]

    return [
        "",
        "  ROAD TYPE & CONDITION (Step 7)",
        "  " + "-"*46,
        f"  Road type       : {rt}",
        f"  Road condition  : {rc}",
        f"  Friction μ      : {mu:.2f}  (dry tar ref = {MU_REFERENCE:.2f})",
        f"  Speed factor    : {f:.4f}",
        f"  Friction risk   : {fr.upper()}",
        f"  Adj. speed min  : {min(adjs):.1f} km/h",
        f"  Adj. speed max  : {max(adjs):.1f} km/h",
        f"  Adj. speed avg  : {sum(adjs)/len(adjs):.1f} km/h",
        f"  Stop dist min   : {min(stps):.1f} m",
        f"  Stop dist max   : {max(stps):.1f} m",
        f"  Stop dist avg   : {sum(stps)/len(stps):.1f} m",
    ]
