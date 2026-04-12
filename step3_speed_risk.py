"""
step3_speed_risk.py
====================
STEP 3 — Speed Optimization + Risk Analysis + Travel Time Estimation.

SPEED PIPELINE (4 sub-steps)
-----------------------------
  3a. Base speed     ← turn_type × surface_factor
  3b. Forward pass   ← can't accelerate faster than MAX_ACCEL_KMH_PER_M
  3c. Backward pass  ← must brake before upcoming slow corners
  3d. Travel time    ← time = distance / speed, cumulative elapsed time

SPEED SMOOTHING ALGORITHM
--------------------------
Same as IEEE paper (Eq. 4 & Eq. 7):

  Forward pass (acceleration limit):
    v_fwd[i] = min( v_raw[i],  v_fwd[i-1] + MAX_ACCEL × Δs )

  Backward pass (deceleration limit):
    v_bwd[i] = min( v_fwd[i],  v_bwd[i+1] + MAX_DECEL × Δs )

  Final speed = v_bwd

This ensures:
  - Rider starts braking BEFORE reaching a corner
  - No sudden speed jumps in either direction
  - Physically realistic speed transitions

RISK CLASSIFICATION
--------------------
  HIGH   : very_sharp_curve / u_turn  OR
           recommended speed ≤ 20 km/h  OR
           cluster of ≥3 sharp turns within 200m  OR
           speed drops > 20 km/h suddenly

  MEDIUM : sharp_curve / intersection  OR
           recommended speed ≤ 35 km/h  OR
           mild_curve

  LOW    : straight road, speed > 35 km/h

TRAVEL TIME
-----------
  segment_time_s = dist_to_next_m / (recommended_speed_kmh / 3.6)
  elapsed_time_s = cumulative sum of segment_time_s
  elapsed_time_min = elapsed_time_s / 60
"""

import numpy as np
from config import (SPEED_RULES, SURFACE_FACTOR,
                     MAX_ACCEL_KMH_PER_M, MAX_DECEL_KMH_PER_M,
                     RISK_HIGH_SPEED_KMPH, RISK_MEDIUM_SPEED_KMPH,
                     SHARP_CLUSTER_WINDOW_M, SHARP_CLUSTER_MIN_COUNT)


# ─────────────────────────────────────────────────────────────────────────────
# 3a — BASE SPEED
# ─────────────────────────────────────────────────────────────────────────────

def _assign_base_speed(segments: list) -> list:
    """
    Assign starting speed from SPEED_RULES[turn_type] × surface_factor.
    """
    for s in segments:
        base = SPEED_RULES.get(s["turn_type"], SPEED_RULES["straight"])
        sf   = SURFACE_FACTOR.get(s.get("surface", "unknown"), 0.85)
        s["raw_speed_kmh"] = round(base * sf, 2)
    return segments


# ─────────────────────────────────────────────────────────────────────────────
# 3b & 3c — FORWARD + BACKWARD SMOOTHING PASS
# ─────────────────────────────────────────────────────────────────────────────

def _smooth_speeds(segments: list) -> list:
    """
    Apply forward (acceleration) and backward (deceleration) passes.
    Ensures physically smooth speed profile with no sudden jumps.
    """
    n   = len(segments)
    raw = np.array([s["raw_speed_kmh"]  for s in segments], dtype=float)
    ds  = np.array([s["dist_to_next_m"] for s in segments], dtype=float)
    ds  = np.maximum(ds, 0.1)    # avoid division-by-zero

    # Forward pass  (Paper Eq. 4 adapted for speed in km/h)
    v_fwd = raw.copy()
    for i in range(1, n):
        v_fwd[i] = min(v_fwd[i], v_fwd[i-1] + MAX_ACCEL_KMH_PER_M * ds[i])

    # Backward pass  (Paper Eq. 7 adapted)
    v_bwd = v_fwd.copy()
    for i in range(n - 2, -1, -1):
        v_bwd[i] = min(v_bwd[i], v_bwd[i+1] + MAX_DECEL_KMH_PER_M * ds[i])

    for i, s in enumerate(segments):
        s["recommended_speed_kmh"] = round(float(v_bwd[i]), 2)

    return segments


# ─────────────────────────────────────────────────────────────────────────────
# 3d — TRAVEL TIME
# ─────────────────────────────────────────────────────────────────────────────

def _compute_travel_time(segments: list) -> list:
    """
    Compute per-segment travel time and cumulative elapsed time.

    segment_time_s   = distance / speed  (m / (km/h ÷ 3.6) = seconds)
    elapsed_time_s   = sum of all segment_time_s up to this point
    elapsed_time_min = elapsed_time_s / 60
    """
    elapsed = 0.0
    for s in segments:
        spd_ms = max(s["recommended_speed_kmh"] / 3.6, 0.1)   # avoid ÷0
        dt     = s["dist_to_next_m"] / spd_ms
        s["segment_time_s"]  = round(dt,        3)
        s["elapsed_time_s"]  = round(elapsed,   2)
        s["elapsed_time_min"]= round(elapsed / 60.0, 3)
        elapsed += dt
    return segments


# ─────────────────────────────────────────────────────────────────────────────
# 3e — RISK LEVEL ASSIGNMENT
# ─────────────────────────────────────────────────────────────────────────────

def _assign_risk(segments: list) -> list:
    """
    Assign 'low', 'medium', or 'high' risk to every point.

    Rules applied in priority order (highest priority first):
      1. very_sharp_curve / u_turn  → HIGH
      2. speed ≤ RISK_HIGH_SPEED    → HIGH
      3. sharp_curve / intersection → MEDIUM
      4. mild_curve                 → MEDIUM
      5. speed ≤ RISK_MEDIUM_SPEED  → MEDIUM
      6. everything else            → LOW

    Post-processing:
      - Clusters of ≥N sharp turns within WINDOW_M → all HIGH
      - Sudden speed drops > 20 km/h               → both points HIGH
    """
    n   = len(segments)
    spd = np.array([s["recommended_speed_kmh"] for s in segments])

    # ── Base risk ─────────────────────────────────────────────────────────
    for s in segments:
        t = s["turn_type"];  v = s["recommended_speed_kmh"]
        if   t in ("very_sharp_curve", "u_turn")  : risk = "high"
        elif v <= RISK_HIGH_SPEED_KMPH              : risk = "high"
        elif t in ("sharp_curve", "intersection")  : risk = "medium"
        elif t == "mild_curve"                      : risk = "medium"
        elif v <= RISK_MEDIUM_SPEED_KMPH            : risk = "medium"
        else                                        : risk = "low"
        s["risk_level"] = risk

    # ── Sharp-turn cluster detection ──────────────────────────────────────
    sharp   = {"sharp_curve", "very_sharp_curve", "u_turn"}
    cum_d   = np.array([s["cumulative_dist_m"] for s in segments])

    for i in range(n):
        if segments[i]["turn_type"] not in sharp:
            continue
        count = 0
        j_end = i
        for j in range(i, min(i + 60, n)):
            if cum_d[j] - cum_d[i] > SHARP_CLUSTER_WINDOW_M:
                break
            if segments[j]["turn_type"] in sharp:
                count += 1
            j_end = j
        if count >= SHARP_CLUSTER_MIN_COUNT:
            for j in range(i, j_end + 1):
                segments[j]["risk_level"] = "high"

    # ── Sudden speed-drop detection ───────────────────────────────────────
    for i in range(1, n):
        if spd[i-1] - spd[i] > 20:
            segments[i]["risk_level"]   = "high"
            segments[i-1]["risk_level"] = "high"

    # ── Print statistics ──────────────────────────────────────────────────
    rc    = {"low":0, "medium":0, "high":0}
    for s in segments:
        rc[s["risk_level"]] += 1
    total = len(segments)

    print(f"\n{'='*62}")
    print(f"  STEP 3 — SPEED & RISK ANALYSIS")
    print(f"{'='*62}")
    all_spd = [s["recommended_speed_kmh"] for s in segments]
    print(f"  Speed min       : {min(all_spd):.1f} km/h")
    print(f"  Speed max       : {max(all_spd):.1f} km/h")
    print(f"  Speed avg       : {sum(all_spd)/len(all_spd):.1f} km/h")
    print(f"  Est. ride time  : {segments[-1]['elapsed_time_min']:.2f} min"
          f"  (at recommended speeds)")
    print(f"\n  Risk breakdown:")
    for r in ("low","medium","high"):
        pct = 100 * rc[r] // total
        bar = "█" * min(40, max(1, rc[r] * 40 // total))
        clr = {"low":"✓","medium":"⚠","high":"✗"}[r]
        print(f"    {clr} {r.upper():<8} : {rc[r]:>5}  ({pct:>2}%)  {bar}")

    return segments


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

def run_speed_risk(segments: list) -> list:
    """Run all 4 speed/risk sub-steps in order."""
    segments = _assign_base_speed(segments)
    segments = _smooth_speeds(segments)
    segments = _compute_travel_time(segments)
    segments = _assign_risk(segments)
    return segments
