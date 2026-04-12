"""
step5_map.py
=============
STEP 5 — Map Visualization & Analysis Plots.

OUTPUTS
-------
interactive_map.html    — Folium map with route, markers, risk colours
                          Open in any browser (Chrome, Firefox, Edge)

plot_dashboard.png      — 8-panel matplotlib analysis dashboard
plot_route_speed.png    — route coloured by speed
plot_route_risk.png     — route coloured by risk level
plot_speed_profile.png  — speed vs distance along route
plot_curvature.png      — curvature along route
plot_angle.png          — turning angles along route
plot_time.png           — speed vs elapsed time
plot_risk_summary.png   — risk pie chart + turn type bar

FOLIUM MAP LAYERS
-----------------
The HTML map includes:
  - OpenStreetMap base tiles (free, no key needed)
  - Route polyline coloured by risk (green/yellow/red)
  - Start marker (green icon)
  - End marker (red icon)
  - Popup on each segment: lat, lon, speed, risk, turn type
  - Legend explaining colour coding
  - Sidebar with turn-by-turn instructions

INSTALLATION NOTE
-----------------
Folium is required for the interactive HTML map:
  pip install folium

If folium is not installed, the system automatically falls back to
a self-contained Leaflet.js HTML file (no Python library needed).
Both produce identical interactive maps in the browser.
"""

import os
import math
import json
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib.collections import LineCollection
from matplotlib.colors import Normalize, BoundaryNorm, ListedColormap
from matplotlib.patches import Patch
import matplotlib.cm as mcm

from config import COLORS as C, RISK_COLOR, ROUTE_COLOR, OUTPUT_DIR


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _style(fig, axes):
    """Apply dark theme."""
    fig.patch.set_facecolor(C["bg"])
    for ax in (axes if hasattr(axes,"__iter__") else [axes]):
        ax.set_facecolor(C["panel"])
        ax.tick_params(colors=C["text"], labelsize=8)
        ax.xaxis.label.set_color(C["text"])
        ax.yaxis.label.set_color(C["text"])
        ax.title.set_color(C["text"])
        ax.grid(True, color=C["grid"], lw=0.4, ls="--", alpha=0.6)
        for sp in ax.spines.values():
            sp.set_edgecolor(C["border"])


def _xy(segs):
    return (np.array([s["xy_x"] for s in segs]),
            np.array([s["xy_y"] for s in segs]))


def _lc(ax, xs, ys, vals, cmap, norm, lw=3):
    pts  = np.c_[xs, ys].reshape(-1, 1, 2)
    segs = np.concatenate([pts[:-1], pts[1:]], axis=1)
    lc   = LineCollection(segs, cmap=cmap, norm=norm, lw=lw, zorder=3)
    lc.set_array(vals)
    ax.add_collection(lc)
    return lc


_RISK_NUM = {"low": 0, "medium": 1, "high": 2}
_RISK_CLR = [RISK_COLOR["low"], RISK_COLOR["medium"], RISK_COLOR["high"]]


# ─────────────────────────────────────────────────────────────────────────────
# FOLIUM INTERACTIVE MAP
# ─────────────────────────────────────────────────────────────────────────────

def build_folium_map(segments: list, route: dict,
                      save_dir: str = OUTPUT_DIR) -> str:
    """
    Build interactive Leaflet map using the folium library.
    Falls back to pure HTML/JS if folium is not installed.
    """
    try:
        import folium
        return _folium_map(segments, route, save_dir)
    except ImportError:
        print("  folium not installed — building pure HTML/JS map instead")
        print("  Install with:  pip install folium")
        return _pure_html_map(segments, route, save_dir)


def _folium_map(segments: list, route: dict,
                 save_dir: str) -> str:
    """Create map using folium library."""
    import folium
    from folium.plugins import MeasureControl

    lats = [s["lat"] for s in segments]
    lons = [s["lon"] for s in segments]
    ctr  = [(min(lats)+max(lats))/2, (min(lons)+max(lons))/2]

    # Base map
    m = folium.Map(location=ctr, zoom_start=14,
                   tiles="OpenStreetMap")

    # ── Route polyline coloured by risk ───────────────────────────────────
    for i in range(len(segments)-1):
        s   = segments[i]
        clr = RISK_COLOR.get(s.get("risk_level","low"), "#58A6FF")
        popup_txt = (
            f"<b>Point #{s['point_id']}</b><br>"
            f"Lat: {s['lat']:.7f}<br>Lon: {s['lon']:.7f}<br>"
            f"Speed: {s.get('recommended_speed_kmh',0):.0f} km/h<br>"
            f"Risk: <b style='color:{clr}'>{s.get('risk_level','').upper()}</b><br>"
            f"Turn: {s['turn_type'].replace('_',' ')}<br>"
            f"Angle: {s['turning_angle_deg']:.1f}°<br>"
            f"Curvature: {s['curvature_1pm']:.5f} 1/m<br>"
            f"Radius: {s['radius_m']:.1f} m<br>"
            f"Surface: {s.get('surface','')}<br>"
            f"Dist from start: {s['cumulative_dist_m']:.0f} m<br>"
            f"Elapsed: {s.get('elapsed_time_min',0):.2f} min"
        )
        folium.PolyLine(
            locations=[[segments[i]["lat"], segments[i]["lon"]],
                        [segments[i+1]["lat"], segments[i+1]["lon"]]],
            color=clr, weight=5, opacity=0.88,
            popup=folium.Popup(popup_txt, max_width=240),
        ).add_to(m)

    # ── Start marker ──────────────────────────────────────────────────────
    org = route.get("origin", (lats[0], lons[0]))
    folium.Marker(
        location=[org[0], org[1]],
        popup=folium.Popup(
            f"<b>START</b><br>Lat: {org[0]:.6f}<br>Lon: {org[1]:.6f}",
            max_width=200),
        icon=folium.Icon(color="green", icon="play", prefix="fa"),
        tooltip="START"
    ).add_to(m)

    # ── Intermediate waypoint markers ─────────────────────────────────────
    waypoints = route.get("waypoints", [])
    for i, wp in enumerate(waypoints, 1):
        folium.Marker(
            location=[wp[0], wp[1]],
            popup=folium.Popup(
                f"<b>WAYPOINT {i}</b><br>Lat: {wp[0]:.6f}<br>Lon: {wp[1]:.6f}",
                max_width=200),
            icon=folium.Icon(color="blue", icon="map-marker", prefix="fa"),
            tooltip=f"WAYPOINT {i}"
        ).add_to(m)

    # ── End marker ────────────────────────────────────────────────────────
    dst = route.get("destination", (lats[-1], lons[-1]))
    folium.Marker(
        location=[dst[0], dst[1]],
        popup=folium.Popup(
            f"<b>END</b><br>Lat: {dst[0]:.6f}<br>Lon: {dst[1]:.6f}",
            max_width=200),
        icon=folium.Icon(color="red", icon="flag", prefix="fa"),
        tooltip="END"
    ).add_to(m)

    # ── High-risk zone circle markers ─────────────────────────────────────
    high_segs = [s for s in segments if s.get("risk_level")=="high"]
    for s in high_segs[::max(1, len(high_segs)//30)]:
        folium.CircleMarker(
            location=[s["lat"], s["lon"]],
            radius=6, color="#F85149", fill=True,
            fill_color="#F85149", fill_opacity=0.7,
            popup=folium.Popup(
                f"<b>⚠ HIGH RISK</b><br>"
                f"{s['turn_type'].replace('_',' ')}<br>"
                f"Speed: {s.get('recommended_speed_kmh',0):.0f} km/h",
                max_width=180)
        ).add_to(m)

    # ── Legend ────────────────────────────────────────────────────────────
    legend_html = """
    <div style='position:fixed;bottom:30px;right:10px;z-index:1000;
                 background:#161B22;padding:12px;border:1px solid #30363D;
                 border-radius:8px;font-family:monospace;font-size:12px;
                 color:#E6EDF3;'>
      <b>Risk Level</b><br>
      <span style='color:#3FB950'>━━</span> Low<br>
      <span style='color:#D29922'>━━</span> Medium<br>
      <span style='color:#F85149'>━━</span> High<br>
      <span style='color:#F85149'>●</span> High-risk point<br>
      <span style='color:#58A6FF'>▲</span> Waypoint
    </div>"""
    m.get_root().html.add_child(folium.Element(legend_html))

    # ── Info panel ────────────────────────────────────────────────────────
    rc = {"low":0,"medium":0,"high":0}
    for s in segments: rc[s.get("risk_level","low")] += 1
    ride_min = segments[-1].get("elapsed_time_min",0)

    info_html = f"""
    <div style='position:fixed;top:10px;left:60px;z-index:1000;
                 background:#161B22;padding:10px 15px;
                 border:1px solid #30363D;border-radius:8px;
                 font-family:monospace;font-size:11px;color:#E6EDF3;'>
      <b style='color:#58A6FF;font-size:13px'>Route Analysis</b><br>
      Source: {route.get('source','')}<br>
      Distance: {route.get('distance_txt','')}<br>
      API Duration: {route.get('duration_txt','')}<br>
      Est. Ride Time: {ride_min:.1f} min<br>
      Waypoints: {len(waypoints)}<br>
      Points: {len(segments)}<br>
      <span style='color:#3FB950'>LOW: {rc['low']}</span> &nbsp;
      <span style='color:#D29922'>MED: {rc['medium']}</span> &nbsp;
      <span style='color:#F85149'>HIGH: {rc['high']}</span>
    </div>"""
    m.get_root().html.add_child(folium.Element(info_html))

    # Measure control
    MeasureControl(position="bottomleft").add_to(m)

    p = os.path.join(save_dir, "interactive_map.html")
    m.save(p)
    print(f"  Folium map  → {p}  (open in browser)")
    return p


def _pure_html_map(segments: list, route: dict,
                    save_dir: str) -> str:
    """
    Build a self-contained Leaflet.js map (no Python libraries needed).
    Identical visual output to the folium version.
    """
    lats  = [s["lat"] for s in segments]
    lons  = [s["lon"] for s in segments]
    ctr_la = sum(lats)/len(lats);  ctr_lo = sum(lons)/len(lons)
    org    = route.get("origin", (lats[0], lons[0]))
    dst    = route.get("destination", (lats[-1], lons[-1]))
    waypoints = route.get("waypoints", [])

    pts_js  = ",\n".join(f"[{s['lat']},{s['lon']}]" for s in segments)
    clrs_js = ",\n".join(f'"{RISK_COLOR.get(s.get("risk_level","low"),"#58A6FF")}"'
                          for s in segments)
    pop_js  = ",\n".join(
        '"#{} ({:.7f},{:.7f})<br>Speed: {:.0f} km/h<br>Risk: {}<br>Turn: {}<br>Angle: {:.1f} deg<br>Dist: {:.0f} m"'
        .format(s["point_id"], s["lat"], s["lon"],
                s.get("recommended_speed_kmh",0),
                s.get("risk_level",""), s["turn_type"],
                s["turning_angle_deg"], s["cumulative_dist_m"])
        for s in segments
    )

    # Build waypoints JS array
    wpt_js = ",\n".join(f"[{w[0]},{w[1]}]" for w in waypoints)

    rc = {"low":0,"medium":0,"high":0}
    for s in segments: rc[s.get("risk_level","low")] += 1
    ride_min = segments[-1].get("elapsed_time_min",0)

    steps_html = "".join(
        f"<div class='stp'><b>{k}.</b> {st.get('instruction','')}"
        f"<span class='sd'>{st.get('distance_m',0):.0f}m"
        f"{' | '+st['name'] if st.get('name') else ''}</span></div>"
        for k,st in enumerate(route.get("steps",[])[:30], 1)
    )

    html = f"""<!DOCTYPE html>
<html><head>
<meta charset="utf-8"/>
<title>Road Route — {route.get('distance_txt','')}</title>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{display:flex;flex-direction:column;height:100vh;
      background:#0D1117;color:#E6EDF3;font-family:monospace;font-size:12px}}
#hdr{{padding:7px 15px;background:#161B22;border-bottom:1px solid #30363D;
       display:flex;gap:12px;flex-wrap:wrap;align-items:center}}
.kpi{{background:#0D1117;border:1px solid #30363D;border-radius:4px;padding:4px 10px}}
.kl{{font-size:10px;color:#8B949E}} .kv{{font-size:13px;font-weight:bold}}
#body{{display:flex;flex:1;overflow:hidden}}
#map{{flex:1}}
#sb{{width:260px;background:#161B22;overflow-y:auto;
      border-left:1px solid #30363D;padding:10px;font-size:11px}}
#sb h3{{color:#58A6FF;margin-bottom:6px}}
.stp{{padding:4px 0;border-bottom:1px solid #21262D;line-height:1.5}}
.sd{{display:block;color:#8B949E;font-size:10px}}
.leg{{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:4px}}
</style></head>
<body>
<div id="hdr">
  <div style="color:#58A6FF;font-weight:bold;font-size:13px">
    Road Navigation  |  {route.get('source','')}
  </div>
  <div class="kpi"><div class="kl">Distance</div><div class="kv">{route.get('distance_txt','')}</div></div>
  <div class="kpi"><div class="kl">API Duration</div><div class="kv">{route.get('duration_txt','')}</div></div>
  <div class="kpi"><div class="kl">Ride Time</div><div class="kv">{ride_min:.1f} min</div></div>
  <div class="kpi"><div class="kl">Waypoints</div><div class="kv">{len(waypoints)}</div></div>
  <div class="kpi"><div class="kl">Points</div><div class="kv">{len(segments)}</div></div>
  <div class="kpi"><div class="kl">LOW</div><div class="kv" style="color:#3FB950">{rc['low']}</div></div>
  <div class="kpi"><div class="kl">MEDIUM</div><div class="kv" style="color:#D29922">{rc['medium']}</div></div>
  <div class="kpi"><div class="kl">HIGH</div><div class="kv" style="color:#F85149">{rc['high']}</div></div>
</div>
<div id="body">
<div id="map"></div>
<div id="sb">
  <h3>TURN-BY-TURN</h3>
  <div style="margin-bottom:8px;font-size:10px;color:#8B949E">
    <span class="leg" style="background:#3FB950"></span>Low &nbsp;
    <span class="leg" style="background:#D29922"></span>Medium &nbsp;
    <span class="leg" style="background:#F85149"></span>High
  </div>
  {steps_html}
</div>
</div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
var map=L.map('map').setView([{ctr_la},{ctr_lo}],14);
L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png',
  {{attribution:'© OpenStreetMap contributors',maxZoom:19}}).addTo(map);

var pts=[{pts_js}];
var clrs=[{clrs_js}];
var pops=[{pop_js}];

// Draw route segments coloured by risk
for(var i=0;i<pts.length-1;i++){{
  L.polyline([pts[i],pts[i+1]],{{color:clrs[i],weight:5,opacity:0.88}})
   .addTo(map).bindPopup(pops[i]);
}}

// Point markers every ~50 points
var step=Math.max(1,Math.floor(pts.length/80));
for(var i=0;i<pts.length;i+=step){{
  L.circleMarker(pts[i],{{radius:4,color:clrs[i],
    fillColor:clrs[i],fillOpacity:0.85,weight:1}})
   .addTo(map).bindPopup(pops[i]);
}}

// Start marker (green)
var greenIcon=L.divIcon({{html:'<div style="background:#3FB950;border:2px solid white;'
  +'border-radius:50%;width:18px;height:18px;"></div>',
  iconSize:[18,18],iconAnchor:[9,9]}});
L.marker([{org[0]},{org[1]}],{{icon:greenIcon}}).addTo(map)
 .bindPopup('<b>START</b><br>Lat:{org[0]:.7f}<br>Lon:{org[1]:.7f}').openPopup();

// Intermediate waypoint markers (blue diamonds)
var wpts=[{wpt_js}];
var blueIcon=L.divIcon({{html:'<div style="background:#58A6FF;border:2px solid white;'
  +'width:14px;height:14px;transform:rotate(45deg);"></div>',
  iconSize:[14,14],iconAnchor:[7,7]}});
for(var w=0;w<wpts.length;w++){{
  L.marker(wpts[w],{{icon:blueIcon}}).addTo(map)
   .bindPopup('<b>WAYPOINT '+(w+1)+'</b><br>Lat:'+wpts[w][0].toFixed(7)+'<br>Lon:'+wpts[w][1].toFixed(7));
}}

// End marker (red)
var redIcon=L.divIcon({{html:'<div style="background:#F85149;border:2px solid white;'
  +'border-radius:3px;width:18px;height:18px;"></div>',
  iconSize:[18,18],iconAnchor:[9,9]}});
L.marker([{dst[0]},{dst[1]}],{{icon:redIcon}}).addTo(map)
 .bindPopup('<b>END</b><br>Lat:{dst[0]:.7f}<br>Lon:{dst[1]:.7f}');

// Legend
var leg=L.control({{position:'bottomright'}});
leg.onAdd=function(){{
  var d=L.DomUtil.create('div');
  d.style.cssText='background:#161B22;padding:10px;border:1px solid #30363D;'
    +'border-radius:6px;color:#E6EDF3;font-family:monospace;font-size:11px;';
  d.innerHTML='<b>Risk Level</b><br>'
    +'<span style="color:#3FB950">━━</span> Low<br>'
    +'<span style="color:#D29922">━━</span> Medium<br>'
    +'<span style="color:#F85149">━━</span> High<br>'
    +'<span style="color:#58A6FF">◆</span> Waypoint';
  return d;
}};
leg.addTo(map);

var poly=L.polyline(pts,{{opacity:0}}).addTo(map);
map.fitBounds(poly.getBounds(),{{padding:[20,20]}});
</script></body></html>"""

    p = os.path.join(save_dir, "interactive_map.html")
    with open(p, "w") as f:
        f.write(html)
    print(f"  HTML map    → {p}  (open in browser)")
    return p


# ─────────────────────────────────────────────────────────────────────────────
# MATPLOTLIB PLOTS
# ─────────────────────────────────────────────────────────────────────────────

def _plot_route_speed(segs, save_dir):
    xs, ys = _xy(segs)
    spd    = np.array([s.get("recommended_speed_kmh",0) for s in segs])
    norm   = Normalize(vmin=spd.min(), vmax=spd.max())
    fig, ax = plt.subplots(figsize=(8,8)); _style(fig, ax)
    lc2 = _lc(ax, xs, ys, spd, mcm.RdYlGn, norm)
    cb  = plt.colorbar(lc2, ax=ax, fraction=0.025, pad=0.02)
    cb.set_label("Speed [km/h]", color=C["text"], fontsize=8)
    cb.ax.tick_params(colors=C["text"], labelsize=7)
    ax.plot(xs[0], ys[0], "*", color=C["green"], ms=14, zorder=6, label="Start")
    ax.plot(xs[-1],ys[-1],"*", color=C["red"],   ms=14, zorder=6, label="End")
    ax.autoscale(); ax.set_aspect("equal")
    ax.set_xlabel("X [m]"); ax.set_ylabel("Y [m]")
    ax.set_title("Route — Coloured by Speed  (Green=Fast, Red=Slow)", fontweight="bold")
    ax.legend(fontsize=8, labelcolor=C["text"], facecolor=C["panel"], edgecolor=C["border"])
    plt.tight_layout()
    p = os.path.join(save_dir, "plot_route_speed.png")
    fig.savefig(p, dpi=150, bbox_inches="tight", facecolor=C["bg"]); plt.close()
    print(f"  Plot saved  → {p}"); return p


def _plot_route_risk(segs, save_dir):
    xs, ys   = _xy(segs)
    risk_val = np.array([_RISK_NUM.get(s.get("risk_level","low"),0) for s in segs])
    cmap_r   = ListedColormap(_RISK_CLR)
    norm_r   = BoundaryNorm([-.5,.5,1.5,2.5], cmap_r.N)
    fig, ax  = plt.subplots(figsize=(8,8)); _style(fig, ax)
    _lc(ax, xs, ys, risk_val, cmap_r, norm_r)
    patches  = [Patch(color=c, label=l) for c,l in
                zip(_RISK_CLR, ["Low Risk","Medium Risk","High Risk"])]
    ax.legend(handles=patches, fontsize=8, labelcolor=C["text"],
              facecolor=C["panel"], edgecolor=C["border"])
    ax.plot(xs[0], ys[0], "*", color="white", ms=12, zorder=5)
    ax.plot(xs[-1],ys[-1],"*", color=C["blue"], ms=12, zorder=5)
    ax.autoscale(); ax.set_aspect("equal")
    ax.set_xlabel("X [m]"); ax.set_ylabel("Y [m]")
    ax.set_title("Route — Coloured by Risk Level", fontweight="bold")
    plt.tight_layout()
    p = os.path.join(save_dir, "plot_route_risk.png")
    fig.savefig(p, dpi=150, bbox_inches="tight", facecolor=C["bg"]); plt.close()
    print(f"  Plot saved  → {p}"); return p


def _plot_speed_profile(segs, save_dir):
    dist = np.array([s["cumulative_dist_m"] for s in segs])
    spd  = np.array([s.get("recommended_speed_kmh",0) for s in segs])
    raw  = np.array([s.get("raw_speed_kmh",0) for s in segs])
    risk = [s.get("risk_level","low") for s in segs]
    fig, ax = plt.subplots(figsize=(13,4)); _style(fig, ax)
    for i in range(len(segs)-1):
        ax.axvspan(dist[i],dist[i+1],
                   color=RISK_COLOR.get(risk[i],"#3FB950"), alpha=0.09)
    ax.plot(dist, raw,  color=C["muted"],  lw=1.0, ls="--", alpha=0.5, label="Raw speed")
    ax.fill_between(dist, spd, alpha=0.18, color=C["blue"])
    ax.plot(dist, spd,  color=C["blue"],   lw=2.0, label="Recommended speed")
    ax.axhline(np.mean(spd), color=C["yellow"], lw=1.2, ls=":",
               label=f"Avg {np.mean(spd):.1f} km/h")
    ax.set_xlabel("Distance [m]"); ax.set_ylabel("Speed [km/h]")
    ax.set_title("Speed Profile Along Route  (background = risk level)", fontweight="bold")
    ax.legend(fontsize=8, labelcolor=C["text"], facecolor=C["panel"], edgecolor=C["border"])
    ax.set_xlim(0, dist[-1])
    plt.tight_layout()
    p = os.path.join(save_dir, "plot_speed_profile.png")
    fig.savefig(p, dpi=150, bbox_inches="tight", facecolor=C["bg"]); plt.close()
    print(f"  Plot saved  → {p}"); return p


def _plot_curvature(segs, save_dir):
    dist = np.array([s["cumulative_dist_m"] for s in segs])
    kap  = np.array([s["curvature_1pm"]     for s in segs])
    fig, ax = plt.subplots(figsize=(13,4)); _style(fig, ax)
    ax.fill_between(dist, kap, alpha=0.2,  color=C["purple"])
    ax.plot(dist, kap, color=C["purple"], lw=1.5)
    if np.any(kap > 1e-6):
        thresh = np.percentile(kap[kap>1e-6], 90)
        ax.fill_between(dist, kap, where=kap>thresh,
                        color=C["red"], alpha=0.45, label=f"Top 10% (κ>{thresh:.4f})")
        ax.legend(fontsize=8, labelcolor=C["text"], facecolor=C["panel"], edgecolor=C["border"])
    ax.set_xlabel("Distance [m]"); ax.set_ylabel("Curvature κ [1/m]")
    ax.set_title("Road Curvature Profile  (high κ = tight turn)", fontweight="bold")
    ax.set_xlim(0, dist[-1])
    plt.tight_layout()
    p = os.path.join(save_dir, "plot_curvature.png")
    fig.savefig(p, dpi=150, bbox_inches="tight", facecolor=C["bg"]); plt.close()
    print(f"  Plot saved  → {p}"); return p


def _plot_angle(segs, save_dir):
    dist = np.array([s["cumulative_dist_m"] for s in segs])
    ang  = np.array([s["turning_angle_deg"] for s in segs])
    fig, ax = plt.subplots(figsize=(13,4)); _style(fig, ax)
    ax.axhspan(  0, 90,  color=C["red"],    alpha=0.07, label="U-turn (<90°)")
    ax.axhspan( 90,120,  color=C["orange"], alpha=0.07, label="Very sharp (90-120°)")
    ax.axhspan(120,150,  color=C["yellow"], alpha=0.07, label="Sharp (120-150°)")
    ax.axhspan(150,170,  color=C["blue"],   alpha=0.07, label="Mild (150-170°)")
    ax.fill_between(dist, ang, 180, where=ang<150, color=C["red"], alpha=0.22)
    ax.plot(dist, ang, color=C["text"], lw=1.0, alpha=0.9)
    ax.axhline(170, color=C["green"], lw=1.0, ls="--", alpha=0.5, label="Straight (>170°)")
    ax.set_ylim(0,185); ax.set_xlim(0, dist[-1])
    ax.set_xlabel("Distance [m]"); ax.set_ylabel("Turning Angle [°]")
    ax.set_title("Turning Angle Profile  (180° = perfectly straight)", fontweight="bold")
    ax.legend(fontsize=7, labelcolor=C["text"], facecolor=C["panel"],
              edgecolor=C["border"], loc="lower right", ncol=2)
    plt.tight_layout()
    p = os.path.join(save_dir, "plot_angle.png")
    fig.savefig(p, dpi=150, bbox_inches="tight", facecolor=C["bg"]); plt.close()
    print(f"  Plot saved  → {p}"); return p


def _plot_time(segs, save_dir):
    t_min = np.array([s.get("elapsed_time_min",0) for s in segs])
    spd   = np.array([s.get("recommended_speed_kmh",0) for s in segs])
    dist  = np.array([s["cumulative_dist_m"] for s in segs])
    fig, (ax1,ax2) = plt.subplots(1,2, figsize=(13,4)); _style(fig,[ax1,ax2])
    ax1.fill_between(t_min, spd, alpha=0.18, color=C["orange"])
    ax1.plot(t_min, spd, color=C["orange"], lw=2.0)
    ax1.set_xlabel("Elapsed Time [min]"); ax1.set_ylabel("Speed [km/h]")
    ax1.set_title("Speed vs Elapsed Time", fontweight="bold")
    c60 = dist / (60/3.6) / 60
    ax2.plot(t_min, dist/1000, color=C["blue"], lw=2.0, label="Recommended speeds")
    ax2.plot(c60,   dist/1000, color=C["muted"],lw=1.2, ls="--",label="Constant 60 km/h")
    ax2.set_xlabel("Time [min]"); ax2.set_ylabel("Distance [km]")
    ax2.set_title("Distance vs Time", fontweight="bold")
    ax2.legend(fontsize=8, labelcolor=C["text"], facecolor=C["panel"], edgecolor=C["border"])
    plt.tight_layout()
    p = os.path.join(save_dir, "plot_time.png")
    fig.savefig(p, dpi=150, bbox_inches="tight", facecolor=C["bg"]); plt.close()
    print(f"  Plot saved  → {p}"); return p


def _plot_risk_summary(segs, save_dir):
    rc = {"low":0,"medium":0,"high":0}
    tc = {}
    for s in segs:
        rc[s.get("risk_level","low")] += 1
        tc[s["turn_type"]] = tc.get(s["turn_type"],0)+1
    fig,(ax1,ax2) = plt.subplots(1,2,figsize=(11,5)); _style(fig,[ax1,ax2])
    ax1.pie([rc["low"],rc["medium"],rc["high"]],
            labels=[f"Low\n({rc['low']})",f"Medium\n({rc['medium']})",
                    f"High\n({rc['high']})"],
            colors=_RISK_CLR, autopct="%1.0f%%", startangle=90,
            textprops={"color":C["text"],"fontsize":9})
    ax1.set_title("Risk Level Distribution", fontweight="bold")
    so = sorted(tc.items(), key=lambda x:-x[1])
    clrs = [C["red"] if "sharp" in n or "u_turn" in n
            else C["yellow"] if "mild" in n or "inter" in n
            else C["green"]
            for n,_ in so]
    ax2.barh([n.replace("_"," ") for n,_ in so],
             [v for _,v in so], color=clrs, alpha=0.85, edgecolor=C["bg"])
    ax2.set_xlabel("Count"); ax2.set_title("Turn Type Breakdown", fontweight="bold")
    plt.tight_layout()
    p = os.path.join(save_dir, "plot_risk_summary.png")
    fig.savefig(p, dpi=150, bbox_inches="tight", facecolor=C["bg"]); plt.close()
    print(f"  Plot saved  → {p}"); return p


# ─────────────────────────────────────────────────────────────────────────────
# MASTER DASHBOARD
# ─────────────────────────────────────────────────────────────────────────────

def build_dashboard(segments: list, route: dict,
                     save_dir: str = OUTPUT_DIR) -> str:
    """8-panel analysis dashboard in one figure."""
    xs,ys  = _xy(segments)
    dist   = np.array([s["cumulative_dist_m"]          for s in segments])
    spd    = np.array([s.get("recommended_speed_kmh",0) for s in segments])
    raw    = np.array([s.get("raw_speed_kmh",0)         for s in segments])
    kap    = np.array([s["curvature_1pm"]               for s in segments])
    ang    = np.array([s["turning_angle_deg"]            for s in segments])
    t_min  = np.array([s.get("elapsed_time_min",0)       for s in segments])
    rval   = np.array([_RISK_NUM.get(s.get("risk_level","low"),0) for s in segments])
    rc     = {"low":0,"medium":0,"high":0}
    for s in segments: rc[s.get("risk_level","low")] += 1
    total  = len(segments)

    fig = plt.figure(figsize=(20,14))
    fig.patch.set_facecolor(C["bg"])
    gs  = gridspec.GridSpec(3,4, figure=fig,
                            hspace=0.45, wspace=0.33,
                            left=0.05, right=0.97,
                            top=0.92, bottom=0.06)

    ax_sm   = fig.add_subplot(gs[0:2,0])
    ax_rm   = fig.add_subplot(gs[0:2,1])
    ax_sp   = fig.add_subplot(gs[0,2])
    ax_cp   = fig.add_subplot(gs[1,2])
    ax_ap   = fig.add_subplot(gs[0,3])
    ax_tp   = fig.add_subplot(gs[1,3])
    ax_pie  = fig.add_subplot(gs[2,0])
    ax_surf = fig.add_subplot(gs[2,1])
    ax_turn = fig.add_subplot(gs[2,2])
    ax_kpi  = fig.add_subplot(gs[2,3])

    _style(fig,[ax_sm,ax_rm,ax_sp,ax_cp,ax_ap,ax_tp,ax_pie,ax_surf,ax_turn,ax_kpi])

    nm_s = Normalize(vmin=spd.min(),vmax=spd.max())
    nm_r = BoundaryNorm([-.5,.5,1.5,2.5],3)
    cmp_r = ListedColormap(_RISK_CLR)

    lc1 = _lc(ax_sm,xs,ys,spd,mcm.RdYlGn,nm_s)
    plt.colorbar(lc1,ax=ax_sm,fraction=0.04,pad=0.02).set_label("km/h",color=C["text"],fontsize=7)
    ax_sm.plot(xs[0],ys[0],"*",color="white",ms=12,zorder=5)
    ax_sm.plot(xs[-1],ys[-1],"*",color=C["blue"],ms=12,zorder=5)
    ax_sm.autoscale(); ax_sm.set_aspect("equal")
    ax_sm.set_title("Speed Map",fontsize=9); ax_sm.set_xlabel("X [m]"); ax_sm.set_ylabel("Y [m]")

    _lc(ax_rm,xs,ys,rval,cmp_r,nm_r)
    patches = [Patch(color=c,label=l) for c,l in zip(_RISK_CLR,["Low","Med","High"])]
    ax_rm.legend(handles=patches,fontsize=7,labelcolor=C["text"],facecolor=C["panel"],edgecolor=C["border"])
    ax_rm.autoscale(); ax_rm.set_aspect("equal")
    ax_rm.set_title("Risk Map",fontsize=9); ax_rm.set_xlabel("X [m]"); ax_rm.set_ylabel("Y [m]")

    for i in range(len(segments)-1):
        ax_sp.axvspan(dist[i],dist[i+1],
            color=RISK_COLOR.get(segments[i].get("risk_level","low"),"#3FB950"),alpha=0.07)
    ax_sp.plot(dist,raw,color=C["muted"],lw=0.8,ls="--",alpha=0.5)
    ax_sp.fill_between(dist,spd,alpha=0.18,color=C["blue"])
    ax_sp.plot(dist,spd,color=C["blue"],lw=1.8)
    ax_sp.set_xlabel("Dist [m]"); ax_sp.set_ylabel("Speed [km/h]")
    ax_sp.set_title("Speed Profile",fontsize=9); ax_sp.set_xlim(0,dist[-1])

    ax_cp.fill_between(dist,kap,alpha=0.18,color=C["purple"])
    ax_cp.plot(dist,kap,color=C["purple"],lw=1.5)
    ax_cp.set_xlabel("Dist [m]"); ax_cp.set_ylabel("κ [1/m]")
    ax_cp.set_title("Curvature",fontsize=9); ax_cp.set_xlim(0,dist[-1])

    ax_ap.fill_between(dist,ang,180,where=ang<150,color=C["red"],alpha=0.25)
    ax_ap.plot(dist,ang,color=C["text"],lw=1.0,alpha=0.85)
    ax_ap.axhline(170,color=C["green"],lw=0.8,ls="--",alpha=0.5)
    ax_ap.set_ylim(0,185); ax_ap.set_xlim(0,dist[-1])
    ax_ap.set_xlabel("Dist [m]"); ax_ap.set_ylabel("Angle [°]")
    ax_ap.set_title("Turning Angle",fontsize=9)

    ax_tp.fill_between(t_min,spd,alpha=0.18,color=C["orange"])
    ax_tp.plot(t_min,spd,color=C["orange"],lw=1.8)
    ax_tp.set_xlabel("Time [min]"); ax_tp.set_ylabel("Speed [km/h]")
    ax_tp.set_title("Speed vs Time",fontsize=9)

    ax_pie.pie([rc["low"],rc["medium"],rc["high"]],
               labels=["Low","Medium","High"],colors=_RISK_CLR,
               autopct="%1.0f%%",startangle=90,
               textprops={"color":C["text"],"fontsize":8})
    ax_pie.set_title("Risk Distribution",fontsize=9,color=C["text"])

    surf_c = {}
    for s in segments: surf_c[s.get("surface","unknown")] = surf_c.get(s.get("surface","unknown"),0)+1
    so2 = sorted(surf_c.items(),key=lambda x:-x[1])
    ax_surf.barh([n for n,_ in so2],[v for _,v in so2],color=C["green"],alpha=0.85,edgecolor=C["bg"])
    ax_surf.set_xlabel("Count"); ax_surf.set_title("Surface Types",fontsize=9)

    tc = {}
    for s in segments: tc[s["turn_type"]]=tc.get(s["turn_type"],0)+1
    so3 = sorted(tc.items(),key=lambda x:-x[1])
    c3  = [C["red"] if "sharp" in n or "u_turn" in n
           else C["yellow"] if "mild" in n or "inter" in n
           else C["green"] for n,_ in so3]
    ax_turn.barh([n.replace("_"," ") for n,_ in so3],[v for _,v in so3],color=c3,alpha=0.85,edgecolor=C["bg"])
    ax_turn.set_xlabel("Count"); ax_turn.set_title("Turn Types",fontsize=9)

    ax_kpi.axis("off")
    org = route.get("origin",""); dst_r = route.get("destination","")
    waypoints = route.get("waypoints", [])
    kpis = [
        ("API Source",   route.get("source","")),
        ("Distance",     route.get("distance_txt","")),
        ("API Duration", route.get("duration_txt","")),
        ("Ride Time",    f"{segments[-1].get('elapsed_time_min',0):.2f} min"),
        ("Waypoints",    str(len(waypoints))),
        ("Points",       str(total)),
        ("Min Speed",    f"{spd.min():.0f} km/h"),
        ("Max Speed",    f"{spd.max():.0f} km/h"),
        ("Avg Speed",    f"{spd.mean():.0f} km/h"),
        ("Risk LOW",     f"{rc['low']} ({100*rc['low']//total}%)"),
        ("Risk MED",     f"{rc['medium']} ({100*rc['medium']//total}%)"),
        ("Risk HIGH",    f"{rc['high']} ({100*rc['high']//total}%)"),
    ]
    for j,(lbl,val) in enumerate(kpis):
        yp = 0.97 - j*0.079
        ax_kpi.text(0.02,yp,f"{lbl}:",transform=ax_kpi.transAxes,
                    fontsize=8,color=C["muted"],va="top")
        col = C["red"] if lbl=="Risk HIGH" and rc["high"]>0 else C["text"]
        ax_kpi.text(0.52,yp,val,transform=ax_kpi.transAxes,
                    fontsize=8,color=col,va="top",fontweight="bold")
    ax_kpi.set_title("KPI Summary",fontsize=9,color=C["text"])

    org_s = f"({org[0]:.4f},{org[1]:.4f})" if org else ""
    dst_s = f"({dst_r[0]:.4f},{dst_r[1]:.4f})" if dst_r else ""
    fig.suptitle(
        f"ROAD NAVIGATION ANALYSIS  |  {org_s} → {dst_s}  |  "
        f"{route.get('distance_txt','')}  |  Source: {route.get('source','')}",
        color=C["text"],fontsize=10,fontweight="bold",y=0.97)

    p = os.path.join(save_dir,"plot_dashboard.png")
    fig.savefig(p,dpi=150,bbox_inches="tight",facecolor=C["bg"]); plt.close()
    print(f"  Dashboard   → {p}")
    return p


# ─────────────────────────────────────────────────────────────────────────────
# RUNNER
# ─────────────────────────────────────────────────────────────────────────────

def run_visualise(segments: list, route: dict,
                   save_dir: str = OUTPUT_DIR) -> dict:
    """Generate all maps and plots."""
    print(f"\n{'='*62}")
    print(f"  STEP 5 — MAP & VISUALISATION")
    print(f"{'='*62}")
    os.makedirs(save_dir, exist_ok=True)

    return {
        "html_map"      : build_folium_map(segments, route, save_dir),
        "route_speed"   : _plot_route_speed(segments, save_dir),
        "route_risk"    : _plot_route_risk(segments, save_dir),
        "speed_profile" : _plot_speed_profile(segments, save_dir),
        "curvature"     : _plot_curvature(segments, save_dir),
        "angle"         : _plot_angle(segments, save_dir),
        "time"          : _plot_time(segments, save_dir),
        "risk_summary"  : _plot_risk_summary(segments, save_dir),
        "dashboard"     : build_dashboard(segments, route, save_dir),
    }
