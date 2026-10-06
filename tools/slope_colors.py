#!/usr/bin/env python3
"""
Colorise la trace GPX de chaque sortie selon la pente locale, et écrit le
résultat dans rides/<sortie>/slope.geojson — lu tel quel par le site (carte
détaillée de la sortie), sans aucun calcul de pente dans le navigateur.

Ne dépend que de la bibliothèque standard Python (3.8+) : rien à installer,
aucun accès réseau. Les fichiers GPX d'origine ne sont jamais modifiés.

Usage :
    # toutes les sorties de rides/ en une commande
    python3 tools/slope_colors.py

    # une ou plusieurs sorties précises
    python3 tools/slope_colors.py rides/clapiers-corconne rides/clapiers-gardiole

    # vérifier, sans rien écrire, que chaque slope.geojson est à jour
    # (code de sortie 1 sinon — pratique en CI)
    python3 tools/slope_colors.py --check

Méthode (voir aussi la section dédiée du README) :
 1. lecture des points (<trkpt>, à défaut <rtept>) : latitude, longitude,
    altitude ;
 2. altitudes manquantes ou aberrantes interpolées linéairement selon la
    distance ; si moins de MIN_VALID_ELEVATION_RATIO des points ont une
    altitude exploitable, la trace est produite en une seule classe
    « Altitude indisponible » plutôt que d'afficher une fausse précision ;
 3. distance cumulée (haversine) ;
 4. lissage : l'altitude est ré-échantillonnée tous les RESAMPLE_STEP_M
    mètres puis moyennée sur une fenêtre glissante de SMOOTHING_WINDOW_M
    mètres — cela gomme le bruit altimétrique (quelques mètres d'un point à
    l'autre) qui, sur des points espacés de 10–40 m, produirait sinon des
    pentes fantaisistes et une alternance excessive de couleurs ;
 5. découpage en tronçons d'au moins SEGMENT_LENGTH_M mètres, pente
    calculée sur chaque tronçon à partir des altitudes lissées
    (dénivelé / distance horizontale) ;
 6. attribution d'une classe/couleur (SLOPE_CLASSES) à chaque tronçon,
    puis fusion des tronçons consécutifs de même classe (sans changer le
    rendu, en réduisant fortement la taille du fichier) dans la limite de
    MAX_MERGED_LENGTH_M mètres.

Limites : la précision dépend de la source des altitudes. Les traces
Komoot/Strava « planifiées » ont des altitudes issues d'un modèle numérique
de terrain (assez régulières) ; un enregistrement GPS brut est beaucoup plus
bruité. Une pente calculée sur 100 m lissés ne voit pas un mur de 20 m :
c'est une indication de l'effort, pas une mesure topographique.
"""

import argparse
import hashlib
import json
import math
import os
import sys
import xml.etree.ElementTree as ET

# --- Configuration ---------------------------------------------------------
#
# Classes de pente, de la plus descendante à la plus raide. Chaque classe
# couvre [min, max[ en % (None = non borné). Modifiez librement libellés,
# seuils et couleurs, puis relancez le script : le site reprend la légende
# depuis le fichier généré.
SLOPE_CLASSES = [
    # clé,               libellé,                         min,   max,   couleur
    ("descente-forte",   "Descente forte (< −6 %)",       None,  -6.0,  "#1d4ed8"),
    ("descente",         "Descente (−6 à −2 %)",          -6.0,  -2.0,  "#60a5fa"),
    ("plat",             "Plat (−2 à 2 %)",               -2.0,   2.0,  "#94a3b8"),
    ("montee-faible",    "Montée faible (2 à 4 %)",        2.0,   4.0,  "#22c55e"),
    ("montee-moderee",   "Montée modérée (4 à 7 %)",       4.0,   7.0,  "#eab308"),
    ("montee-soutenue",  "Montée soutenue (7 à 10 %)",     7.0,  10.0,  "#f97316"),
    ("montee-forte",     "Montée forte (≥ 10 %)",         10.0,  None,  "#dc2626"),
]

# Classe utilisée quand les altitudes sont absentes ou inexploitables.
UNKNOWN_CLASS = ("inconnue", "Altitude indisponible", None, None, "#8a8178")

SEGMENT_LENGTH_M = 100.0       # longueur minimale d'un tronçon de calcul
SMOOTHING_WINDOW_M = 150.0     # fenêtre du lissage altimétrique (moyenne glissante)
RESAMPLE_STEP_M = 10.0         # pas de ré-échantillonnage avant lissage
MAX_MERGED_LENGTH_M = 1000.0   # longueur max après fusion de tronçons de même classe
MIN_VALID_ELEVATION_RATIO = 0.5  # en dessous : altitude jugée inexploitable
MIN_ELEVATION_M = -450.0       # altitudes hors de [MIN, MAX] considérées invalides
MAX_ELEVATION_M = 9000.0
COORD_DECIMALS = 5             # ~1 m de précision, largement suffisant pour l'affichage

OUTPUT_NAME = "slope.geojson"
FORMAT_VERSION = 1  # à incrémenter si le calcul change : rend les fichiers existants obsolètes
GENERATOR = "tools/slope_colors.py"

EARTH_RADIUS_M = 6371000.0


class SlopeError(Exception):
    """Erreur bloquante pour une sortie (message destiné à l'utilisateur)."""


# --- Lecture du GPX ----------------------------------------------------------

def find_gpx(ride_dir):
    """Premier fichier .gpx (ordre alphabétique) du dossier, comme le site."""
    names = sorted(n for n in os.listdir(ride_dir)
                   if n.lower().endswith(".gpx") and os.path.isfile(os.path.join(ride_dir, n)))
    return os.path.join(ride_dir, names[0]) if names else None


def _local(tag):
    return tag.rsplit("}", 1)[-1]


def parse_elevation(text):
    """Altitude en m, ou None si absente / non numérique / aberrante."""
    if text is None:
        return None
    try:
        v = float(text.strip())
    except ValueError:
        return None
    if math.isnan(v) or math.isinf(v) or not (MIN_ELEVATION_M <= v <= MAX_ELEVATION_M):
        return None
    return v


def read_gpx_points(path):
    """Renvoie [(lat, lon, ele_ou_None), ...] : traces (<trk>), sinon itinéraires (<rte>)."""
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as e:
        raise SlopeError("GPX illisible (%s)" % e)

    def collect(point_tag):
        pts = []
        for el in root.iter():
            if _local(el.tag) != point_tag:
                continue
            try:
                lat = float(el.get("lat"))
                lon = float(el.get("lon"))
            except (TypeError, ValueError):
                continue  # point sans coordonnées valides : ignoré
            ele = None
            for child in el:
                if _local(child.tag) == "ele":
                    ele = parse_elevation(child.text)
                    break
            pts.append((lat, lon, ele))
        return pts

    points = collect("trkpt") or collect("rtept")
    if len(points) < 2:
        raise SlopeError("moins de deux points de trace dans le GPX")
    return points


# --- Géométrie & altitudes ---------------------------------------------------

def haversine_m(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(h)))


def cumulative_distances(points):
    dist = [0.0]
    for (a, b) in zip(points, points[1:]):
        dist.append(dist[-1] + haversine_m(a[0], a[1], b[0], b[1]))
    return dist


def fill_elevations(elevations, dist):
    """Interpole linéairement (selon la distance) les altitudes manquantes.

    Les trous en début/fin de trace prennent l'altitude valide la plus
    proche. Renvoie (altitudes complètes, ratio de points valides), ou
    (None, 0) si aucune altitude n'est exploitable.
    """
    valid = [i for i, e in enumerate(elevations) if e is not None]
    if not valid:
        return None, 0.0
    out = list(elevations)
    for i in range(valid[0]):
        out[i] = elevations[valid[0]]
    for i in range(valid[-1] + 1, len(out)):
        out[i] = elevations[valid[-1]]
    for a, b in zip(valid, valid[1:]):
        span = dist[b] - dist[a]
        for i in range(a + 1, b):
            t = (dist[i] - dist[a]) / span if span > 0 else 0.0
            out[i] = elevations[a] + t * (elevations[b] - elevations[a])
    return out, len(valid) / len(elevations)


def interpolate(xs, ys, x):
    """Interpolation linéaire de y(x) ; xs croissant (non strictement)."""
    lo, hi = 0, len(xs) - 1
    if x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if xs[mid] <= x:
            lo = mid
        else:
            hi = mid
    span = xs[hi] - xs[lo]
    if span <= 0:
        return ys[hi]
    return ys[lo] + (x - xs[lo]) / span * (ys[hi] - ys[lo])


def smooth_elevations(dist, ele, window_m=SMOOTHING_WINDOW_M, step_m=RESAMPLE_STEP_M):
    """Moyenne glissante de l'altitude sur window_m mètres, puis reprojection
    sur les distances d'origine.

    Le ré-échantillonnage à pas constant rend le lissage indépendant de la
    densité des points (variable selon l'outil qui a produit le GPX).
    """
    total = dist[-1]
    if total <= 0 or window_m <= 0:
        return list(ele)
    n = int(total // step_m) + 1
    grid = [min(i * step_m, total) for i in range(n)]
    if grid[-1] < total:
        grid.append(total)
    samples = [interpolate(dist, ele, d) for d in grid]

    half = max(1, int(round(window_m / step_m / 2)))
    prefix = [0.0]
    for v in samples:
        prefix.append(prefix[-1] + v)
    smoothed = []
    last = len(samples) - 1
    for i in range(len(samples)):
        # Fenêtre symétrique, réduite près des extrémités : une fenêtre
        # tronquée d'un seul côté aplatirait artificiellement la pente au
        # départ et à l'arrivée.
        k = min(half, i, last - i)
        smoothed.append((prefix[i + k + 1] - prefix[i - k]) / (2 * k + 1))
    return [interpolate(grid, smoothed, d) for d in dist]


# --- Tronçons & classes --------------------------------------------------------

def classify(slope_pct, classes=SLOPE_CLASSES):
    for cls in classes:
        lo, hi = cls[2], cls[3]
        if (lo is None or slope_pct >= lo) and (hi is None or slope_pct < hi):
            return cls
    return classes[-1]


def split_segments(dist, segment_length_m=SEGMENT_LENGTH_M):
    """Découpe en tronçons [(i_début, i_fin), ...] d'au moins segment_length_m
    mètres (indices de points inclus, chaque tronçon partageant son premier
    point avec la fin du précédent). Un reliquat final trop court est
    rattaché au dernier tronçon.
    """
    segments = []
    start = 0
    for i in range(1, len(dist)):
        if dist[i] - dist[start] >= segment_length_m:
            segments.append([start, i])
            start = i
    if start < len(dist) - 1:
        if segments and dist[-1] - dist[start] < segment_length_m / 2:
            segments[-1][1] = len(dist) - 1
        else:
            segments.append([start, len(dist) - 1])
    if not segments:
        segments.append([0, len(dist) - 1])
    return segments


def build_segments(points, segment_length_m=SEGMENT_LENGTH_M, smoothing_window_m=SMOOTHING_WINDOW_M,
                   classes=SLOPE_CLASSES, max_merged_length_m=MAX_MERGED_LENGTH_M):
    """Calcule les tronçons colorisés d'une trace.

    Renvoie (tronçons, stats) ; chaque tronçon est un dict avec start/end
    (indices), start_m/end_m, ele_start/ele_end (lissées), slope, cls.
    """
    dist = cumulative_distances(points)
    if dist[-1] <= 0:
        raise SlopeError("trace de longueur nulle (tous les points sont confondus)")

    raw_ele = [p[2] for p in points]
    ele, valid_ratio = fill_elevations(raw_ele, dist)
    elevation_ok = ele is not None and valid_ratio >= MIN_VALID_ELEVATION_RATIO
    smoothed = smooth_elevations(dist, ele, smoothing_window_m) if elevation_ok else None

    segments = []
    for a, b in split_segments(dist, segment_length_m):
        length = dist[b] - dist[a]
        if elevation_ok and length > 0:
            slope = (smoothed[b] - smoothed[a]) / length * 100.0
            cls = classify(slope, classes)
            seg = {"start": a, "end": b, "start_m": dist[a], "end_m": dist[b],
                   "ele_start": smoothed[a], "ele_end": smoothed[b], "slope": slope, "cls": cls}
        else:
            seg = {"start": a, "end": b, "start_m": dist[a], "end_m": dist[b],
                   "ele_start": None, "ele_end": None, "slope": None, "cls": UNKNOWN_CLASS}
        segments.append(seg)

    merged = []
    for seg in segments:
        prev = merged[-1] if merged else None
        if (prev is not None and prev["cls"][0] == seg["cls"][0]
                and seg["end_m"] - prev["start_m"] <= max_merged_length_m):
            prev["end"] = seg["end"]
            prev["end_m"] = seg["end_m"]
            prev["ele_end"] = seg["ele_end"]
            length = prev["end_m"] - prev["start_m"]
            if prev["slope"] is not None and length > 0:
                prev["slope"] = (prev["ele_end"] - prev["ele_start"]) / length * 100.0
        else:
            merged.append(dict(seg))

    stats = {
        "distance_km": round(dist[-1] / 1000.0, 2),
        "elevation_valid_ratio": round(valid_ratio, 3),
        "elevation_ok": elevation_ok,
    }
    if elevation_ok:
        gain = sum(max(0.0, b - a) for a, b in zip(smoothed, smoothed[1:]))
        stats["smoothed_gain_m"] = int(round(gain))
        stats["max_slope_pct"] = round(max(s["slope"] for s in segments), 1)
        stats["min_slope_pct"] = round(min(s["slope"] for s in segments), 1)
    return merged, stats


# --- Sortie GeoJSON ------------------------------------------------------------

def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def legend(classes=SLOPE_CLASSES):
    return [{"key": c[0], "label": c[1], "min": c[2], "max": c[3], "color": c[4]} for c in classes]


def params():
    return {
        "segment_length_m": SEGMENT_LENGTH_M,
        "smoothing_window_m": SMOOTHING_WINDOW_M,
        "resample_step_m": RESAMPLE_STEP_M,
        "max_merged_length_m": MAX_MERGED_LENGTH_M,
        "classes": legend(),
    }


def params_fingerprint():
    """Empreinte des paramètres : un changement de seuil rend le fichier obsolète."""
    return hashlib.sha256(json.dumps(params(), sort_keys=True).encode("utf-8")).hexdigest()[:16]


def to_geojson(points, segments, stats, gpx_name, gpx_sha):
    r = lambda v, n: None if v is None else round(v, n)
    features = []
    for seg in segments:
        coords = [[round(p[1], COORD_DECIMALS), round(p[0], COORD_DECIMALS)]
                  for p in points[seg["start"]:seg["end"] + 1]]
        key, label, _, _, color = seg["cls"]
        features.append({
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": coords},
            "properties": {
                "slope_pct": r(seg["slope"], 1),
                "start_km": round(seg["start_m"] / 1000.0, 3),
                "end_km": round(seg["end_m"] / 1000.0, 3),
                "ele_start": r(seg["ele_start"], 1),
                "ele_end": r(seg["ele_end"], 1),
                "class": key,
                "label": label,
                "color": color,
            },
        })
    classes = legend() if stats["elevation_ok"] else legend([UNKNOWN_CLASS])
    return {
        "type": "FeatureCollection",
        # Membres étrangers (autorisés par la RFC 7946) : métadonnées de
        # génération, ignorées par les lecteurs GeoJSON génériques.
        "generator": GENERATOR,
        "format_version": FORMAT_VERSION,
        "source_gpx": gpx_name,
        "source_sha256": gpx_sha,
        "params_fingerprint": params_fingerprint(),
        "params": params(),
        "legend": classes,
        "stats": stats,
        "features": features,
    }


def is_up_to_date(out_path, gpx_sha):
    try:
        with open(out_path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return False
    return (data.get("source_sha256") == gpx_sha
            and data.get("params_fingerprint") == params_fingerprint()
            and data.get("format_version") == FORMAT_VERSION)


def process_ride(ride_dir, check=False, force=False):
    """Traite une sortie. Renvoie 'written', 'up-to-date', 'stale', 'skipped'."""
    gpx = find_gpx(ride_dir)
    if gpx is None:
        return "skipped", "pas de fichier .gpx"
    out_path = os.path.join(ride_dir, OUTPUT_NAME)
    gpx_sha = sha256_of(gpx)

    if not force and is_up_to_date(out_path, gpx_sha):
        return "up-to-date", os.path.basename(gpx)
    if check:
        return "stale", "absent ou obsolète — relancez : python3 tools/slope_colors.py %s" % ride_dir

    points = read_gpx_points(gpx)
    segments, stats = build_segments(points)
    data = to_geojson(points, segments, stats, os.path.basename(gpx), gpx_sha)

    tmp = out_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
        f.write("\n")
    os.replace(tmp, out_path)  # écriture atomique : jamais de fichier à moitié écrit

    detail = "%d tronçons, %.1f km" % (len(segments), stats["distance_km"])
    if stats["elevation_ok"]:
        detail += ", pente %+.1f %% à %+.1f %%" % (stats["min_slope_pct"], stats["max_slope_pct"])
    else:
        detail += ", ⚠ altitudes inexploitables (%.0f %% valides) : trace en gris" % (
            stats["elevation_valid_ratio"] * 100)
    return "written", detail


def ride_dirs_from_args(args):
    if args.rides:
        return args.rides
    if not os.path.isdir(args.rides_dir):
        raise SlopeError("dossier introuvable : %s" % args.rides_dir)
    return [os.path.join(args.rides_dir, n) for n in sorted(os.listdir(args.rides_dir))
            if not n.startswith(".") and os.path.isdir(os.path.join(args.rides_dir, n))]


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Génère rides/<sortie>/slope.geojson (trace colorisée selon la pente).")
    parser.add_argument("rides", nargs="*", help="dossiers de sorties (défaut : toutes celles de --rides-dir)")
    parser.add_argument("--rides-dir", default="rides", help="dossier contenant les sorties (défaut : rides)")
    parser.add_argument("--check", action="store_true",
                        help="n'écrit rien ; code de sortie 1 si un fichier est absent ou obsolète")
    parser.add_argument("--force", action="store_true", help="régénère même si le fichier est à jour")
    args = parser.parse_args(argv)

    try:
        dirs = ride_dirs_from_args(args)
    except SlopeError as e:
        print("✗ %s" % e, file=sys.stderr)
        return 2

    errors = stale = 0
    for d in dirs:
        name = os.path.basename(os.path.normpath(d))
        if not os.path.isdir(d):
            print("✗ %s : dossier introuvable" % d, file=sys.stderr)
            errors += 1
            continue
        try:
            status, detail = process_ride(d, check=args.check, force=args.force)
        except (SlopeError, OSError) as e:
            print("✗ %s : %s" % (name, e), file=sys.stderr)
            errors += 1
            continue
        symbol = {"written": "✓", "up-to-date": "=", "stale": "✗", "skipped": "·"}[status]
        print("%s %s : %s" % (symbol, name, {"up-to-date": "à jour"}.get(status, detail)))
        if status == "stale":
            stale += 1

    if errors or stale:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
