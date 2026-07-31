#!/usr/bin/env python3
"""
Génère une image au format Instagram (portrait 1080x1350) pour une sortie :
photo de fond, silhouette de la trace GPX, infos clés (titre, distance,
dénivelé, difficulté) et logo Cyclo Explore.

Le fichier généré (instagram.jpg, à la racine du dossier de la sortie) est
automatiquement repris par le générateur : s'il existe, un bouton "Instagram"
apparaît dans le bloc de partage de la page de la sortie.

Dépend de Pillow :
    pip install Pillow
    (si erreur "externally-managed-environment" : pip install Pillow --break-system-packages)

Usage :
    python3 tools/make_instagram_image.py rides/tour-du-pic-saint-loup
    python3 tools/make_instagram_image.py rides/tour-du-pic-saint-loup --photo photos/sommet.jpg
    python3 tools/make_instagram_image.py rides/tour-du-pic-saint-loup --out apercu.jpg
"""

import argparse
import math
import os
import sys
import xml.etree.ElementTree as ET

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    sys.exit(
        "Ce script a besoin de Pillow : pip install Pillow\n"
        "(si erreur \"externally-managed-environment\" : pip install Pillow --break-system-packages)"
    )

CANVAS_W, CANVAS_H = 1080, 1350
EARTH_RADIUS_KM = 6371.0

CREAM = (247, 242, 234)
TERRACOTTA = (184, 86, 47)
INK = (43, 38, 32)
WHITE = (255, 255, 255)

FONT_BOLD_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "C:\\Windows\\Fonts\\arialbd.ttf",
]
FONT_REGULAR_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/Library/Fonts/Arial.ttf",
    "C:\\Windows\\Fonts\\arial.ttf",
]


def load_font(candidates, size):
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    # Repli : police par défaut de Pillow (scalable depuis Pillow 10.1+).
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


# --- Contenu de la sortie ---------------------------------------------

def parse_frontmatter(path):
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    lines = content.replace("\r\n", "\n").split("\n")
    if not lines or lines[0].strip() != "---":
        return {}
    fields = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" not in line or line.strip().startswith("#"):
            continue
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip().strip("\"'")
    return fields


def haversine_km(a, b):
    lat1, lon1 = math.radians(a[0]), math.radians(a[1])
    lat2, lon2 = math.radians(b[0]), math.radians(b[1])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return EARTH_RADIUS_KM * 2 * math.atan2(math.sqrt(h), math.sqrt(1 - h))


def load_gpx(path):
    tree = ET.parse(path)
    root = tree.getroot()
    pts = []
    for pt in root.findall(".//{*}trkpt"):
        lat, lon = float(pt.get("lat")), float(pt.get("lon"))
        ele_el = pt.find("{*}ele")
        ele = float(ele_el.text) if ele_el is not None and ele_el.text else None
        pts.append((lat, lon, ele))
    if not pts:
        for pt in root.findall(".//{*}rtept"):
            pts.append((float(pt.get("lat")), float(pt.get("lon")), None))
    return pts


def track_stats(track):
    distance = 0.0
    for i in range(1, len(track)):
        distance += haversine_km(track[i - 1][:2], track[i][:2])
    gain = 0.0
    for i in range(1, len(track)):
        e0, e1 = track[i - 1][2], track[i][2]
        if e0 is not None and e1 is not None and e1 > e0:
            gain += e1 - e0
    return distance, gain


def find_gpx(ride_dir):
    for name in sorted(os.listdir(ride_dir)):
        if name.lower().endswith(".gpx"):
            return os.path.join(ride_dir, name)
    return None


def find_first_photo(ride_dir):
    photos_dir = os.path.join(ride_dir, "photos")
    if not os.path.isdir(photos_dir):
        return None
    exts = (".jpg", ".jpeg", ".png", ".webp")
    for name in sorted(os.listdir(photos_dir)):
        if name.lower().endswith(exts):
            return os.path.join(photos_dir, name)
    return None


# --- Rendu image ------------------------------------------------------

def cover_resize(im, target_w, target_h):
    src_w, src_h = im.size
    src_ratio = src_w / src_h
    target_ratio = target_w / target_h
    if src_ratio > target_ratio:
        new_h = target_h
        new_w = max(1, int(round(new_h * src_ratio)))
    else:
        new_w = target_w
        new_h = max(1, int(round(new_w / src_ratio)))
    im = im.resize((new_w, new_h), Image.Resampling.LANCZOS)
    left = (new_w - target_w) // 2
    top = (new_h - target_h) // 2
    return im.crop((left, top, left + target_w, top + target_h))


def bottom_gradient(w, h, start_frac=0.32, max_alpha=215):
    col = Image.new("L", (1, h), 0)
    for y in range(h):
        frac = y / h
        a = 0 if frac < start_frac else int(max_alpha * (frac - start_frac) / (1 - start_frac))
        col.putpixel((0, y), a)
    alpha = col.resize((w, h))
    overlay = Image.new("RGBA", (w, h), (*INK, 0))
    overlay.putalpha(alpha)
    return overlay


def load_logo_with_transparency(path, size):
    logo = Image.open(path).convert("RGBA")
    logo = logo.resize((size, size), Image.Resampling.LANCZOS)
    gray = logo.convert("L")
    # Le fond du logo est blanc : on le rend transparent par seuillage simple
    # (suffisant pour un logo en aplats de couleur comme celui-ci).
    mask = gray.point(lambda p: 0 if p > 248 else 255)
    logo.putalpha(mask)
    return logo


def wrap_text(draw, text, font, max_width):
    words = text.split()
    if not words:
        return []
    lines, cur = [], words[0]
    for word in words[1:]:
        trial = cur + " " + word
        box = draw.textbbox((0, 0), trial, font=font)
        if box[2] - box[0] <= max_width:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    lines.append(cur)
    return lines


def draw_shadowed_text(draw, pos, text, font, fill):
    x, y = pos
    draw.text((x + 2, y + 2), text, font=font, fill=(0, 0, 0, 140))
    draw.text((x, y), text, font=font, fill=fill)


def draw_track_badge(draw, track, box, color):
    x0, y0, size = box
    if len(track) < 2:
        return
    lats = [p[0] for p in track]
    lons = [p[1] for p in track]
    min_lat, max_lat = min(lats), max(lats)
    min_lon, max_lon = min(lons), max(lons)
    lat_span = max(max_lat - min_lat, 1e-9)
    lon_span = max(max_lon - min_lon, 1e-9)

    ref_lat = (min_lat + max_lat) / 2
    lon_span_m = lon_span * math.cos(math.radians(ref_lat))
    ratio = (lon_span_m / lat_span) if lat_span else 1.0

    pad = size * 0.16
    inner = size - 2 * pad
    if ratio > 1:
        draw_w, draw_h = inner, inner / ratio
    else:
        draw_w, draw_h = inner * ratio, inner

    ox = x0 + (size - draw_w) / 2
    oy = y0 + (size - draw_h) / 2

    pts = []
    for lat, lon, _ in track:
        x = ox + (lon - min_lon) / lon_span * draw_w
        y = oy + (max_lat - lat) / lat_span * draw_h
        pts.append((x, y))

    draw.line(pts, fill=color, width=7, joint="curve")
    draw.ellipse([pts[0][0] - 6, pts[0][1] - 6, pts[0][0] + 6, pts[0][1] + 6], fill=color)
    draw.ellipse([pts[-1][0] - 6, pts[-1][1] - 6, pts[-1][0] + 6, pts[-1][1] + 6], fill=color)


# --- Programme principal --------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Génère une image Instagram pour une sortie.")
    parser.add_argument("ride", help="Dossier de la sortie (ex: rides/tour-du-pic-saint-loup)")
    parser.add_argument("--photo", help="Photo à utiliser (chemin relatif au dossier de la sortie, ou absolu). Défaut : la première de photos/")
    parser.add_argument("--out", help="Fichier de sortie (défaut : instagram.jpg dans le dossier de la sortie)")
    parser.add_argument("--logo", default=os.path.join(os.path.dirname(__file__), "..", "internal", "site", "static", "logo.png"), help="Chemin du logo à incruster")
    args = parser.parse_args()

    ride_dir = args.ride
    if not os.path.isdir(ride_dir):
        sys.exit(f"{ride_dir} n'est pas un dossier de sortie")

    desc_path = os.path.join(ride_dir, "description.md")
    if not os.path.exists(desc_path):
        sys.exit(f"{desc_path} introuvable")
    fields = parse_frontmatter(desc_path)
    title = fields.get("title") or os.path.basename(os.path.normpath(ride_dir))
    difficulty = fields.get("difficulty", "")
    departure = fields.get("departure", "")

    distance_km = float(fields["distance_km"]) if fields.get("distance_km") else None
    elevation_m = float(fields["elevation_m"]) if fields.get("elevation_m") else None

    track = None
    gpx_path = find_gpx(ride_dir)
    if gpx_path:
        try:
            track = load_gpx(gpx_path)
        except (ET.ParseError, OSError) as e:
            print(f"⚠ trace GPX illisible ({e}), ignorée")
            track = None
    if track and len(track) >= 2:
        auto_distance, auto_gain = track_stats(track)
        if distance_km is None:
            distance_km = auto_distance
        if elevation_m is None:
            elevation_m = auto_gain

    photo_path = None
    if args.photo:
        photo_path = args.photo if os.path.isabs(args.photo) else os.path.join(ride_dir, args.photo)
        if not os.path.exists(photo_path):
            sys.exit(f"Photo introuvable : {photo_path}")
    else:
        photo_path = find_first_photo(ride_dir)

    out_path = args.out or os.path.join(ride_dir, "instagram.jpg")

    # --- Fond : photo (cover) ou dégradé de secours ---
    if photo_path:
        photo = Image.open(photo_path)
        try:
            from PIL import ImageOps
            photo = ImageOps.exif_transpose(photo)
        except Exception:
            pass
        canvas = cover_resize(photo.convert("RGB"), CANVAS_W, CANVAS_H).convert("RGBA")
    else:
        canvas = Image.new("RGBA", (CANVAS_W, CANVAS_H), CREAM)
        grad = Image.new("L", (1, CANVAS_H), 0)
        for y in range(CANVAS_H):
            grad.putpixel((0, y), int(255 * (y / CANVAS_H) * 0.5))
        overlay = Image.new("RGBA", (CANVAS_W, CANVAS_H), (*TERRACOTTA, 0))
        overlay.putalpha(grad.resize((CANVAS_W, CANVAS_H)))
        canvas = Image.alpha_composite(canvas, overlay)

    canvas = Image.alpha_composite(canvas, bottom_gradient(CANVAS_W, CANVAS_H))
    draw = ImageDraw.Draw(canvas)

    # --- Logo (haut gauche) ---
    logo_size = 130
    try:
        logo = load_logo_with_transparency(args.logo, logo_size)
        canvas.alpha_composite(logo, (48, 48))
    except (FileNotFoundError, OSError):
        print(f"⚠ logo introuvable ({args.logo}), ignoré")

    # --- Badge trace (haut droite) ---
    if track and len(track) >= 2:
        badge_size = 260
        bx, by = CANVAS_W - badge_size - 48, 48
        draw.rounded_rectangle([bx, by, bx + badge_size, by + badge_size], radius=24, fill=(255, 255, 255, 235))
        draw_track_badge(draw, track, (bx, by, badge_size), TERRACOTTA)

    # --- Texte (bas) ---
    font_title = load_font(FONT_BOLD_CANDIDATES, 64)
    font_stats = load_font(FONT_BOLD_CANDIDATES, 38)
    font_brand = load_font(FONT_REGULAR_CANDIDATES, 30)

    text_max_w = CANVAS_W - 2 * 56
    title_lines = wrap_text(draw, title, font_title, text_max_w)[:3]

    stats_parts = []
    if distance_km:
        stats_parts.append(f"{distance_km:.0f} km")
    if elevation_m:
        stats_parts.append(f"+{elevation_m:.0f} m D+")
    if difficulty:
        stats_parts.append(difficulty)
    stats_line = "  ·  ".join(stats_parts)

    y = CANVAS_H - 72
    if departure:
        box = draw.textbbox((0, 0), departure, font=font_brand)
        y -= (box[3] - box[1])
        draw_shadowed_text(draw, (56, y), departure, font_brand, (247, 242, 234, 230))
        y -= 14
    if stats_line:
        box = draw.textbbox((0, 0), stats_line, font=font_stats)
        y -= (box[3] - box[1])
        draw_shadowed_text(draw, (56, y), stats_line, font_stats, (247, 242, 234, 255))
        y -= 18

    for line in reversed(title_lines):
        box = draw.textbbox((0, 0), line, font=font_title)
        y -= (box[3] - box[1]) + 6
        draw_shadowed_text(draw, (56, y), line, font_title, WHITE)

    canvas.convert("RGB").save(out_path, "JPEG", quality=90)
    print(f"✓ Image générée : {out_path} ({CANVAS_W}x{CANVAS_H})")


if __name__ == "__main__":
    main()
