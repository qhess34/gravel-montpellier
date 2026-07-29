#!/usr/bin/env python3
"""
Cherche des points d'intérêt utiles en gravel (points d'eau, boulangeries,
campings, bars, restaurants, réparateurs de vélo) proches d'une trace GPX
via les données OpenStreetMap (API Overpass), les propose un par un de
manière interactive (nom, distance à la trace, PK), et génère les blocs à
ajouter dans points.md pour ceux que vous validez.

Ne dépend que de la bibliothèque standard Python (3.8+) : rien à installer.
Nécessite un accès réseau (interroge https://overpass-api.de).

Usage :
    python3 tools/find_supplies.py rides/tour-du-pic-saint-loup
    python3 tools/find_supplies.py rides/tour-du-pic-saint-loup --radius 200 --only water,bakery
    python3 tools/find_supplies.py chemin/vers/trace.gpx --out chemin/vers/points.md
    python3 tools/find_supplies.py rides/tour-du-pic-saint-loup --dry-run

Types disponibles (--only, séparés par des virgules, défaut : tous) :
    water        points d'eau (fontaines, robinets, sources potables...)
    bakery       boulangeries
    grocery      magasins alimentaires (supérettes, supermarchés, primeurs)
    camping      campings et aires de camping-car
    bar          bars et pubs
    restaurant   restaurants
    bike_repair  magasins de vélo et bornes de réparation en libre-service

À chaque point proposé, répondez :
    o (oui)      ajoute le point tel quel
    n (non)      ignore le point
    e (éditer)   modifie le label et/ou la note avant de l'ajouter
    q (quitter)  arrête la sélection ici (garde ce qui a déjà été validé)
"""

import argparse
import json
import math
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"
NOMINATIM_MIN_INTERVAL = 1.1  # secondes entre deux appels (politique d'usage Nominatim : 1 req/s max)
EARTH_RADIUS_KM = 6371.0
USER_AGENT = "gravel-montpellier-find-supplies/1.0 (script interactif local)"

ALL_KINDS = ["water", "bakery", "grocery", "camping", "bar", "restaurant", "bike_repair"]

# Icône à utiliser dans points.md (doit correspondre aux classes CSS gm-marker--*).
KIND_ICON = {
    "water": "water",
    "bakery": "food",
    "grocery": "grocery",
    "camping": "camping",
    "bar": "bar",
    "restaurant": "restaurant",
    "bike_repair": "bike-repair",
}
KIND_LABEL_FR = {
    "water": "point d'eau",
    "bakery": "boulangerie",
    "grocery": "magasin alimentaire",
    "camping": "camping",
    "bar": "bar",
    "restaurant": "restaurant",
    "bike_repair": "réparateur de vélo",
}
KIND_DEFAULT_NAME = {
    "water": "Point d'eau",
    "bakery": "Boulangerie",
    "grocery": "Magasin alimentaire",
    "camping": "Camping",
    "bar": "Bar",
    "restaurant": "Restaurant",
    "bike_repair": "Réparateur de vélo",
}


# --- Géométrie -------------------------------------------------------------

def haversine_km(a, b):
    lat1, lon1 = math.radians(a[0]), math.radians(a[1])
    lat2, lon2 = math.radians(b[0]), math.radians(b[1])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return EARTH_RADIUS_KM * 2 * math.atan2(math.sqrt(h), math.sqrt(1 - h))


def resample(points, max_points):
    """Échantillonne `points` pour n'en garder qu'au plus `max_points`,
    répartis régulièrement (garde toujours le premier et le dernier)."""
    if len(points) <= max_points:
        return points
    stride = (len(points) - 1) / (max_points - 1)
    out, i = [], 0.0
    while len(out) < max_points:
        idx = min(int(round(i)), len(points) - 1)
        out.append(points[idx])
        i += stride
    return out


def nearest_km(track, target):
    """Renvoie (km cumulés depuis le départ, distance à la trace en km)
    pour le point de `track` le plus proche de `target`."""
    best_idx, best_dist = 0, haversine_km(track[0], target)
    for i in range(1, len(track)):
        d = haversine_km(track[i], target)
        if d < best_dist:
            best_dist, best_idx = d, i
    cum = 0.0
    for i in range(1, best_idx + 1):
        cum += haversine_km(track[i - 1], track[i])
    return cum, best_dist


# --- GPX ---------------------------------------------------------------

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


# --- points.md existant (détection des doublons) --------------------------

DUPLICATE_THRESHOLD_M = 20  # en dessous de cette distance, on considère que c'est le même point


def parse_points_md_coords(path):
    """Renvoie les coordonnées (lat, lon) de tous les points déjà présents
    dans points.md, s'il existe (même format de blocs que le générateur Go :
    des sections séparées par une ligne '---', en 'clé: valeur')."""
    if not os.path.exists(path):
        return []

    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    blocks, current = [], []
    for line in content.replace("\r\n", "\n").split("\n"):
        if line.strip() == "---":
            blocks.append(current)
            current = []
        else:
            current.append(line)
    blocks.append(current)

    coords = []
    for block in blocks:
        fields = {}
        for line in block:
            line = line.strip()
            if not line or line.startswith("#") or ":" not in line:
                continue
            key, _, value = line.partition(":")
            fields[key.strip()] = value.strip().strip("\"'")
        lat, lon = fields.get("lat"), fields.get("lon")
        if lat and lon:
            try:
                coords.append((float(lat), float(lon)))
            except ValueError:
                pass
    return coords


def is_duplicate(lat, lon, existing_coords):
    return any(haversine_km((lat, lon), (elat, elon)) * 1000 <= DUPLICATE_THRESHOLD_M for elat, elon in existing_coords)


# --- Overpass ------------------------------------------------------------

def build_query(buffer_points, radius_m, kinds):
    coords = ",".join(f"{lat:.6f},{lon:.6f}" for lat, lon in buffer_points)
    around = f"around:{radius_m},{coords}"
    clauses = []

    if "water" in kinds:
        # amenity=drinking_water / water_point couvrent la majorité des cas,
        # mais pas mal de points d'eau (fontaines de village, robinets,
        # sources, puits) sont tagués différemment sur OSM.
        clauses += [
            f'  node({around})[amenity=drinking_water];',
            f'  node({around})[amenity=water_point];',
            f'  node({around})[man_made=water_tap];',
            f'  node({around})[amenity=fountain][drinking_water=yes];',
            f'  node({around})[natural=spring][drinking_water=yes];',
            f'  node({around})[man_made=water_well][drinking_water=yes];',
        ]
    if "bakery" in kinds:
        clauses += [
            f'  node({around})[shop=bakery];',
            f'  node({around})[amenity=bakery];',
        ]
    if "grocery" in kinds:
        clauses += [
            f'  node({around})[shop=supermarket];',
            f'  node({around})[shop=convenience];',
            f'  node({around})[shop=grocery];',
            f'  node({around})[shop=greengrocer];',
        ]
    if "camping" in kinds:
        # les campings sont souvent cartographiés comme une zone (way) plutôt
        # qu'un simple point : nwr + "out center" gère les deux cas.
        clauses += [
            f'  nwr({around})[tourism=camp_site];',
            f'  nwr({around})[tourism=caravan_site];',
        ]
    if "bar" in kinds:
        clauses += [
            f'  node({around})[amenity=bar];',
            f'  node({around})[amenity=pub];',
        ]
    if "restaurant" in kinds:
        clauses.append(f'  node({around})[amenity=restaurant];')
    if "bike_repair" in kinds:
        clauses += [
            f'  node({around})[shop=bicycle];',
            f'  node({around})[amenity=bicycle_repair_station];',
        ]

    body = "\n".join(clauses)
    return f"[out:json][timeout:60];\n(\n{body}\n);\nout center;"


def query_overpass(query):
    data = urllib.parse.urlencode({"data": query}).encode("utf-8")
    req = urllib.request.Request(OVERPASS_URL, data=data, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=90) as resp:
        return json.load(resp)


# --- Géocodage inverse (nom de commune) ------------------------------------

def reverse_city(lat, lon):
    """Renvoie le nom de la commune/village au plus proche de (lat, lon) via
    Nominatim, ou None en cas d'échec (pas d'accès réseau, pas de résultat...).
    """
    params = {"format": "jsonv2", "lat": f"{lat:.6f}", "lon": f"{lon:.6f}", "zoom": "14", "addressdetails": "1"}
    url = NOMINATIM_URL + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.load(resp)
    except Exception:
        return None
    addr = data.get("address", {})
    return addr.get("city") or addr.get("town") or addr.get("village") or addr.get("municipality") or addr.get("hamlet")


def add_cities(candidates):
    """Renseigne candidates[i]['city'] pour chaque candidat, en respectant la
    limite d'1 requête/seconde imposée par l'usage policy de Nominatim."""
    if not candidates:
        return
    print(f"Recherche des communes pour {len(candidates)} point(s)...")
    last_call = 0.0
    for c in candidates:
        wait = NOMINATIM_MIN_INTERVAL - (time.time() - last_call)
        if wait > 0:
            time.sleep(wait)
        c["city"] = reverse_city(c["lat"], c["lon"])
        last_call = time.time()


def classify(tags):
    if tags.get("amenity") in ("drinking_water", "water_point"):
        return "water"
    if tags.get("man_made") == "water_tap":
        return "water"
    if tags.get("drinking_water") == "yes" and (
        tags.get("amenity") == "fountain"
        or tags.get("natural") == "spring"
        or tags.get("man_made") == "water_well"
    ):
        return "water"
    if tags.get("shop") == "bakery" or tags.get("amenity") == "bakery":
        return "bakery"
    if tags.get("shop") in ("supermarket", "convenience", "grocery", "greengrocer"):
        return "grocery"
    if tags.get("tourism") in ("camp_site", "caravan_site"):
        return "camping"
    if tags.get("amenity") in ("bar", "pub"):
        return "bar"
    if tags.get("amenity") == "restaurant":
        return "restaurant"
    if tags.get("shop") == "bicycle" or tags.get("amenity") == "bicycle_repair_station":
        return "bike_repair"
    return None


def default_label(tags, kind, city=None):
    name = tags.get("name") or KIND_DEFAULT_NAME.get(kind, kind)
    return f"{city} — {name}" if city else name


def default_note(tags):
    bits = []
    if tags.get("opening_hours"):
        bits.append(f"Horaires : {tags['opening_hours']}")
    if tags.get("operator"):
        bits.append(f"Exploité par {tags['operator']}")
    return " · ".join(bits)


# --- Sélection interactive ------------------------------------------------

def prompt_selection(candidates):
    selected = []
    print(f"\n{len(candidates)} point(s) trouvé(s) près de la trace.\n")

    for c in candidates:
        label = default_label(c["tags"], c["kind"], c.get("city"))
        note = default_note(c["tags"])
        kind_label = KIND_LABEL_FR.get(c["kind"], c["kind"])
        icon = KIND_ICON.get(c["kind"], "generic")

        print(f"— {label} ({kind_label})")
        print(f"  PK {c['km']:.1f} km · à {c['dist_m']:.0f} m de la trace")
        if note:
            print(f"  {note}")

        while True:
            try:
                choice = input("  Ajouter ? [O]ui / [n]on / [e]diter / [q]uitter : ").strip().lower()
            except EOFError:
                choice = "q"
            if choice in ("", "o", "oui", "y", "yes"):
                selected.append({"icon": icon, "lat": c["lat"], "lon": c["lon"], "label": label, "note": note})
                break
            if choice in ("n", "non", "no"):
                break
            if choice in ("e", "editer", "éditer", "edit"):
                new_label = input(f"  Label [{label}] : ").strip() or label
                new_note = input(f"  Note [{note}] : ").strip() or note
                selected.append({"icon": icon, "lat": c["lat"], "lon": c["lon"], "label": new_label, "note": new_note})
                break
            if choice in ("q", "quitter"):
                return selected
            print("  Réponse non reconnue.")
        print()

    return selected


# --- Génération des blocs points.md ---------------------------------------

def format_block(p):
    lines = [
        "type: poi",
        f"icon: {p['icon']}",
        f"lat: {p['lat']:.6f}",
        f"lon: {p['lon']:.6f}",
        f"label: {p['label']}",
    ]
    if p["note"]:
        lines.append(f"note: {p['note']}")
    return "\n".join(lines)


def format_all(selected):
    return "\n\n---\n\n".join(format_block(p) for p in selected)


def append_to_points_md(path, block_text):
    existing = ""
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            existing = f.read()
    prefix = "\n\n---\n\n" if existing.strip() else ""
    with open(path, "a", encoding="utf-8") as f:
        f.write(prefix + block_text + "\n")


# --- Programme principal --------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Cherche des points d'intérêt (eau, boulangeries, campings, bars, "
                    "restaurants, réparateurs de vélo) proches d'une trace GPX "
                    "(OpenStreetMap/Overpass) et prépare des blocs à ajouter dans points.md.",
    )
    parser.add_argument("ride", help="Dossier de la sortie (ex: rides/tour-du-pic-saint-loup) ou chemin direct vers un .gpx")
    parser.add_argument("--radius", type=int, default=150, help="Rayon de recherche autour de la trace, en mètres (défaut : 150)")
    parser.add_argument(
        "--only",
        help=f"Types à chercher, séparés par des virgules, parmi : {', '.join(ALL_KINDS)} (défaut : tous)",
    )
    parser.add_argument("--out", help="Fichier points.md cible (défaut : points.md à côté du .gpx)")
    parser.add_argument("--include-existing", action="store_true", help="Proposer aussi les points déjà présents dans points.md (par défaut, ils sont ignorés silencieusement)")
    parser.add_argument("--dry-run", action="store_true", help="N'écrit rien sur disque, affiche seulement le résultat")
    args = parser.parse_args()

    if args.only:
        requested = [k.strip() for k in args.only.split(",") if k.strip()]
        unknown = [k for k in requested if k not in ALL_KINDS]
        if unknown:
            sys.exit(f"Type(s) inconnu(s) : {', '.join(unknown)} — attendu parmi : {', '.join(ALL_KINDS)}")
        kinds = set(requested)
    else:
        kinds = set(ALL_KINDS)

    if os.path.isdir(args.ride):
        gpx_path = find_gpx_in_dir(args.ride)
        if not gpx_path:
            sys.exit(f"Aucun fichier .gpx trouvé dans {args.ride}")
        out_path = args.out or os.path.join(args.ride, "points.md")
    else:
        gpx_path = args.ride
        out_path = args.out or os.path.join(os.path.dirname(gpx_path) or ".", "points.md")

    print(f"Lecture de {gpx_path}...")
    try:
        track = load_gpx(gpx_path)
    except (ET.ParseError, OSError) as e:
        sys.exit(f"Impossible de lire la trace GPX : {e}")
    if len(track) < 2:
        sys.exit("Trace GPX vide ou illisible.")

    buffer_points = resample(track, 150)
    query = build_query(buffer_points, args.radius, kinds)

    print(f"Recherche sur OpenStreetMap (rayon {args.radius} m, types : {', '.join(sorted(kinds))})...")
    try:
        result = query_overpass(query)
    except (urllib.error.URLError, TimeoutError) as e:
        sys.exit(f"Impossible de contacter l'API Overpass : {e}")

    candidates = {}
    for el in result.get("elements", []):
        el_type = el.get("type")
        if el_type == "node":
            lat, lon = el.get("lat"), el.get("lon")
        else:
            center = el.get("center") or {}
            lat, lon = center.get("lat"), center.get("lon")
        if lat is None or lon is None:
            continue

        tags = el.get("tags", {})
        kind = classify(tags)
        if not kind:
            continue
        km, dist_km = nearest_km(track, (lat, lon))
        candidates[el["id"]] = {
            "kind": kind,
            "lat": lat,
            "lon": lon,
            "tags": tags,
            "km": km,
            "dist_m": dist_km * 1000,
        }

    if not candidates:
        print("Aucun point trouvé dans le rayon indiqué. Essayez d'augmenter --radius.")
        return

    skipped_duplicates = 0
    if not args.include_existing:
        existing_coords = parse_points_md_coords(out_path)
        if existing_coords:
            kept = {}
            for cid, c in candidates.items():
                if is_duplicate(c["lat"], c["lon"], existing_coords):
                    skipped_duplicates += 1
                else:
                    kept[cid] = c
            candidates = kept

    if not candidates:
        if skipped_duplicates:
            print(f"Les {skipped_duplicates} point(s) trouvé(s) sont déjà présents dans {out_path} (relancez avec --include-existing pour les revoir).")
        else:
            print("Aucun point trouvé dans le rayon indiqué. Essayez d'augmenter --radius.")
        return

    if skipped_duplicates:
        print(f"({skipped_duplicates} point(s) déjà présent(s) dans {out_path}, non proposés à nouveau — voir --include-existing)")

    candidate_list = list(candidates.values())
    add_cities(candidate_list)
    ordered = sorted(candidate_list, key=lambda c: c["km"])

    try:
        selected = prompt_selection(ordered)
    except KeyboardInterrupt:
        print("\nInterrompu — rien n'a été écrit.")
        return

    if not selected:
        print("Aucun point sélectionné.")
        return

    block_text = format_all(selected)
    print("\n--- Blocs à ajouter dans points.md ---\n")
    print(block_text)
    print()

    if args.dry_run:
        return

    try:
        answer = input(f"Ajouter ces {len(selected)} point(s) à {out_path} ? [O/n] : ").strip().lower()
    except EOFError:
        answer = "n"

    if answer in ("", "o", "oui", "y", "yes"):
        append_to_points_md(out_path, block_text)
        print(f"✓ Ajouté à {out_path}")
    else:
        print("Rien n'a été écrit — copiez le texte ci-dessus si besoin.")


if __name__ == "__main__":
    main()
