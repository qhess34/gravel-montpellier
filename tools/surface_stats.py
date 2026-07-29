#!/usr/bin/env python3
"""
Estime la part de route/piste cyclable (revêtu) et de chemin/sentier (non
revêtu) d'une sortie, en comparant sa trace GPX aux données OpenStreetMap
(API Overpass), et met à jour description.md avec le résultat
(surface_paved_km / surface_unpaved_km) — lu automatiquement par le
générateur pour afficher la barre de revêtement sur la page de la sortie,
sans appel réseau au moment du build.

Ne dépend que de la bibliothèque standard Python (3.8+) : rien à installer.
Nécessite un accès réseau (interroge https://overpass-api.de).

Usage :
    python3 tools/surface_stats.py rides/tour-du-pic-saint-loup
    python3 tools/surface_stats.py rides/tour-du-pic-saint-loup --radius 30
    python3 tools/surface_stats.py rides/tour-du-pic-saint-loup --dry-run
"""

import argparse
import json
import math
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
EARTH_RADIUS_KM = 6371.0
USER_AGENT = "gravel-montpellier-surface-stats/1.0 (script interactif local)"

MATCH_THRESHOLD_M = 25  # au-delà, un point de trace est considéré "indéterminé"

PAVED_HIGHWAYS = {
    "cycleway",
    "motorway", "motorway_link", "trunk", "trunk_link",
    "primary", "primary_link", "secondary", "secondary_link",
    "tertiary", "tertiary_link", "unclassified", "residential",
    "living_street", "service", "road", "footway", "pedestrian",
}
UNPAVED_HIGHWAYS = {"track", "path", "bridleway", "steps"}


# --- Géométrie -------------------------------------------------------------

def haversine_km(a, b):
    lat1, lon1 = math.radians(a[0]), math.radians(a[1])
    lat2, lon2 = math.radians(b[0]), math.radians(b[1])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return EARTH_RADIUS_KM * 2 * math.atan2(math.sqrt(h), math.sqrt(1 - h))


def resample(points, max_points):
    if len(points) <= max_points:
        return points
    stride = (len(points) - 1) / (max_points - 1)
    out, i = [], 0.0
    while len(out) < max_points:
        idx = min(int(round(i)), len(points) - 1)
        out.append(points[idx])
        i += stride
    return out


def to_local_xy(lat, lon, ref_lat):
    meters_per_deg_lat = 111320.0
    y = lat * meters_per_deg_lat
    x = lon * meters_per_deg_lat * math.cos(math.radians(ref_lat))
    return x, y


def point_seg_dist(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    cx, cy = ax + t * dx, ay + t * dy
    return math.hypot(px - cx, py - cy)


# --- GPX --------------------------------------------------------------

def load_gpx(path):
    tree = ET.parse(path)
    root = tree.getroot()
    points = [(float(pt.get("lat")), float(pt.get("lon"))) for pt in root.findall(".//{*}trkpt")]
    if not points:
        points = [(float(pt.get("lat")), float(pt.get("lon"))) for pt in root.findall(".//{*}rtept")]
    return points


def find_gpx_in_dir(directory):
    for name in sorted(os.listdir(directory)):
        if name.lower().endswith(".gpx"):
            return os.path.join(directory, name)
    return None


# --- Overpass ------------------------------------------------------------

def classify_highway(highway):
    if highway in PAVED_HIGHWAYS:
        return "paved"
    if highway in UNPAVED_HIGHWAYS:
        return "unpaved"
    return None


def fetch_ways(buffer_points, radius_m):
    coords = ",".join(f"{lat:.6f},{lon:.6f}" for lat, lon in buffer_points)
    query = f"[out:json][timeout:60];way(around:{radius_m},{coords})[highway];out geom;"
    data = urllib.parse.urlencode({"data": query}).encode("utf-8")
    req = urllib.request.Request(OVERPASS_URL, data=data, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=90) as resp:
        parsed = json.load(resp)

    ways = []
    for el in parsed.get("elements", []):
        if el.get("type") != "way":
            continue
        geometry = el.get("geometry")
        if not geometry or len(geometry) < 2:
            continue
        category = classify_highway(el.get("tags", {}).get("highway", ""))
        if category is None:
            continue
        ways.append((category, [(pt["lat"], pt["lon"]) for pt in geometry]))
    return ways


# --- Classification de la trace --------------------------------------------

def classify_track(track, ways, ref_lat):
    segments = []  # (category, ax, ay, bx, by)
    for category, pts in ways:
        xy = [to_local_xy(lat, lon, ref_lat) for lat, lon in pts]
        for i in range(1, len(xy)):
            ax, ay = xy[i - 1]
            bx, by = xy[i]
            segments.append((category, ax, ay, bx, by))

    categories = []
    for lat, lon in track:
        px, py = to_local_xy(lat, lon, ref_lat)
        best_category, best_dist = None, MATCH_THRESHOLD_M
        for category, ax, ay, bx, by in segments:
            d = point_seg_dist(px, py, ax, ay, bx, by)
            if d < best_dist:
                best_dist, best_category = d, category
        categories.append(best_category)
    return categories


def surface_distances(track, categories):
    paved = unpaved = unknown = 0.0
    for i in range(1, len(track)):
        d = haversine_km(track[i - 1], track[i])
        cat = categories[i]
        if cat == "paved":
            paved += d
        elif cat == "unpaved":
            unpaved += d
        else:
            unknown += d
    return paved, unpaved, unknown


# --- Mise à jour de description.md -----------------------------------------

def update_frontmatter(path, updates):
    """Met à jour (ou ajoute) des clés du frontmatter de description.md,
    sans toucher au reste du fichier (autres champs, corps markdown)."""
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    lines = content.replace("\r\n", "\n").split("\n")
    if not lines or lines[0].strip() != "---":
        raise ValueError("le fichier ne commence pas par une ligne '---'")

    close_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            close_idx = i
            break
    if close_idx is None:
        raise ValueError("frontmatter non fermé (ligne '---' de fin manquante)")

    front = lines[1:close_idx]
    remaining = dict(updates)

    new_front = []
    for line in front:
        stripped = line.strip()
        key = None
        if ":" in stripped and not stripped.startswith("#"):
            key = stripped.split(":", 1)[0].strip()
        if key in remaining:
            new_front.append(f"{key}: {remaining.pop(key)}")
        else:
            new_front.append(line)
    for key, value in remaining.items():
        new_front.append(f"{key}: {value}")

    new_content = "\n".join([lines[0]] + new_front + lines[close_idx:])
    if not new_content.endswith("\n"):
        new_content += "\n"

    with open(path, "w", encoding="utf-8") as f:
        f.write(new_content)


# --- Programme principal --------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Estime la part revêtue/non revêtue d'une sortie (OpenStreetMap/Overpass) "
                    "et met à jour description.md en conséquence.",
    )
    parser.add_argument("ride", help="Dossier de la sortie (ex: rides/tour-du-pic-saint-loup)")
    parser.add_argument("--radius", type=int, default=20, help="Rayon de recherche des voies autour de la trace, en mètres (défaut : 20)")
    parser.add_argument("--dry-run", action="store_true", help="N'écrit rien, affiche seulement le résultat")
    args = parser.parse_args()

    if not os.path.isdir(args.ride):
        sys.exit(f"{args.ride} n'est pas un dossier de sortie")

    gpx_path = find_gpx_in_dir(args.ride)
    if not gpx_path:
        sys.exit(f"Aucun fichier .gpx trouvé dans {args.ride}")
    desc_path = os.path.join(args.ride, "description.md")
    if not os.path.exists(desc_path):
        sys.exit(f"{desc_path} introuvable")

    print(f"Lecture de {gpx_path}...")
    try:
        track = load_gpx(gpx_path)
    except (ET.ParseError, OSError) as e:
        sys.exit(f"Impossible de lire la trace GPX : {e}")
    if len(track) < 2:
        sys.exit("Trace GPX vide ou illisible.")

    buffer_points = resample(track, 150)
    stats_track = resample(track, 1000)
    ref_lat = track[len(track) // 2][0]

    print(f"Recherche des voies OpenStreetMap (rayon {args.radius} m)...")
    try:
        ways = fetch_ways(buffer_points, args.radius)
    except (urllib.error.URLError, TimeoutError) as e:
        sys.exit(f"Impossible de contacter l'API Overpass : {e}")

    categories = classify_track(stats_track, ways, ref_lat)
    paved, unpaved, unknown = surface_distances(stats_track, categories)
    total = paved + unpaved + unknown

    if total == 0 or (paved == 0 and unpaved == 0):
        print("Aucune correspondance exploitable trouvée près de la trace — rien à mettre à jour.")
        return

    paved_pct = round(paved / total * 100)
    unpaved_pct = round(unpaved / total * 100)
    print(f"Revêtu      : {paved:.1f} km ({paved_pct} %)")
    print(f"Non revêtu  : {unpaved:.1f} km ({unpaved_pct} %)")
    if unknown > 0:
        print(f"Indéterminé : {unknown:.1f} km ({100 - paved_pct - unpaved_pct} %)")

    if args.dry_run:
        return

    update_frontmatter(desc_path, {
        "surface_paved_km": f"{paved:.1f}",
        "surface_unpaved_km": f"{unpaved:.1f}",
    })
    print(f"✓ {desc_path} mis à jour")


if __name__ == "__main__":
    main()
