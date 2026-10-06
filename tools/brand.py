"""
Charte graphique et lecture des sorties, partagées par les générateurs
d'images (tools/make_instagram_image.py, tools/generate_qrcode.py).

Reprend la charte du site (internal/site/static/style.css) : fond crème,
encre brune, terracotta pour l'action, vert olive et vert forêt du logo,
polices Fraunces (titres) et Inter (texte), emblème du logo
(internal/site/static/logo-mark.png), couleurs de pente de
tools/slope_colors.py (lues dans slope.geojson).

Dépend de Pillow (pip install Pillow).
"""

import io
import json
import math
import os
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(TOOLS_DIR)
FONTS_DIR = os.path.join(TOOLS_DIR, "fonts")
STATIC_DIR = os.path.join(REPO_DIR, "internal", "site", "static")
LOGO_MARK = os.path.join(STATIC_DIR, "logo-mark.png")
DEFAULT_SITE_URL = "https://montpellier.cycloexplore.fr"

# --- Couleurs (style.css + logo) -------------------------------------------

CREAM = (247, 242, 234)        # --cream : fond du site
PAPER = (255, 253, 249)        # --paper : cartes
SAND = (233, 220, 200)         # ancien fond d'en-tête
LINE = (230, 221, 206)         # --line : bordures
INK = (43, 38, 32)             # --ink : texte
INK_SOFT = (107, 96, 83)       # --ink-soft
TERRACOTTA = (184, 86, 47)     # --terracotta : boutons, accents
TERRACOTTA_DARK = (147, 65, 31)
OLIVE = (107, 122, 79)         # --olive : devise du logo
FOREST = (47, 58, 44)          # vert sombre du logo
PANO = (107, 63, 160)          # violet des vues 360° Panoramax
WHITE = (255, 255, 255)

DIFFICULTY_COLORS = {
    "facile": (63, 143, 79),
    "moyenne": (201, 138, 31),
    "difficile": (196, 70, 43),
    "tres-difficile": (122, 31, 31),
}

TAGLINE = "SORTIES VÉLO · AVENTURE · PARTAGE"


def hex_to_rgb(value):
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


# --- Polices ------------------------------------------------------------------

_FALLBACK_SERIF = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Georgia Bold.ttf",
    "C:\\Windows\\Fonts\\georgiab.ttf",
]
_FALLBACK_SANS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "C:\\Windows\\Fonts\\arial.ttf",
]
_font_cache = {}


def font(kind, size, weight=400):
    """Police de la charte : kind = "serif" (Fraunces, titres) ou "sans"
    (Inter, texte). Les polices variables fournies dans tools/fonts sont
    réglées sur la graisse demandée ; à défaut, repli sur une police système."""
    key = (kind, size, weight)
    if key in _font_cache:
        return _font_cache[key]
    path = os.path.join(FONTS_DIR, "Fraunces.ttf" if kind == "serif" else "Inter.ttf")
    f = None
    if os.path.exists(path):
        try:
            f = ImageFont.truetype(path, size)
            axes = []
            for axis in f.get_variation_axes():
                name = axis["name"].decode() if isinstance(axis["name"], bytes) else axis["name"]
                name = name.lower()
                if name == "weight":
                    axes.append(max(axis["minimum"], min(axis["maximum"], weight)))
                elif name.startswith("optical"):
                    axes.append(max(axis["minimum"], min(axis["maximum"], size)))
                elif name == "softness":
                    axes.append(0)
                elif name == "wonky":
                    axes.append(0)
                else:
                    axes.append(axis["default"])
            f.set_variation_by_axes(axes)
        except (OSError, ValueError):
            f = None
    if f is None:
        for candidate in (_FALLBACK_SERIF if kind == "serif" else _FALLBACK_SANS):
            if os.path.exists(candidate):
                f = ImageFont.truetype(candidate, size)
                break
    if f is None:
        f = ImageFont.load_default(size=size)
    _font_cache[key] = f
    return f


def text_size(draw, text, fnt):
    box = draw.textbbox((0, 0), text, font=fnt)
    return box[2] - box[0], box[3] - box[1], box


def draw_text(draw, xy, text, fnt, fill, anchor="la", tracking=0):
    """Texte avec interlettrage optionnel (tracking en px), comme les
    petites capitales espacées du site."""
    if not tracking:
        draw.text(xy, text, font=fnt, fill=fill, anchor=anchor)
        return draw.textlength(text, font=fnt)
    x, y = xy
    total = sum(draw.textlength(c, font=fnt) for c in text) + tracking * (len(text) - 1)
    if anchor[0] == "m":
        x -= total / 2
    elif anchor[0] == "r":
        x -= total
    # Ancre verticale commune à toutes les lettres (« t » = haut de chaque
    # glyphe : un « É » serait décalé) -> ascendante de la police.
    v = "a" if anchor[1] == "t" else anchor[1]
    for c in text:
        draw.text((x, y), c, font=fnt, fill=fill, anchor="l" + v)
        x += draw.textlength(c, font=fnt) + tracking
    return total


def wrap(draw, text, fnt, max_width):
    words = text.split()
    lines, cur = [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if draw.textlength(trial, font=fnt) <= max_width or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def fit_title(draw, text, max_width, max_lines, sizes, weight=700):
    """Plus grande taille de Fraunces pour laquelle le titre tient en
    max_lines lignes de max_width px."""
    for size in sizes:
        fnt = font("serif", size, weight)
        lines = wrap(draw, text, fnt, max_width)
        if len(lines) <= max_lines:
            return fnt, lines
    fnt = font("serif", sizes[-1], weight)
    lines = wrap(draw, text, fnt, max_width)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        while lines[-1] and draw.textlength(lines[-1] + "…", font=fnt) > max_width:
            lines[-1] = lines[-1].rsplit(" ", 1)[0] if " " in lines[-1] else lines[-1][:-1]
        lines[-1] += "…"
    return fnt, lines


# --- Lecture d'une sortie -----------------------------------------------------

def parse_description(path):
    """Frontmatter (dict) et corps markdown de description.md."""
    with open(path, encoding="utf-8") as f:
        content = f.read().replace("\r\n", "\n")
    lines = content.split("\n")
    fields, body_start = {}, 0
    if lines and lines[0].strip() == "---":
        for i, line in enumerate(lines[1:], start=1):
            if line.strip() == "---":
                body_start = i + 1
                break
            if ":" in line and not line.strip().startswith("#"):
                k, _, v = line.partition(":")
                fields[k.strip()] = v.strip().strip("\"'")
    return fields, "\n".join(lines[body_start:])


def summary_text(body):
    """Synthèse : texte avant « ## Le parcours » (comme le site), en texte brut."""
    m = re.search(r"(?mi)^##[ \t]+Le parcours[ \t]*$", body)
    part = body[:m.start()] if m else body.strip().split("\n\n")[0]
    part = "\n".join(l for l in part.split("\n") if l.strip() != "---")
    part = re.sub(r"\[(.+?)\]\((.+?)\)", r"\1", part)
    part = re.sub(r"\*\*(.+?)\*\*", r"\1", part)
    part = re.sub(r"\*(.+?)\*", r"\1", part)
    part = re.sub(r"(?m)^#+\s*", "", part)
    return re.sub(r"\s+", " ", part).strip()


_DIFF_ALIASES = {
    "facile": "facile", "tres facile": "facile", "debutant": "facile",
    "moyen": "moyenne", "moyenne": "moyenne", "modere": "moyenne", "moderee": "moyenne", "intermediaire": "moyenne",
    "difficile": "difficile", "dur": "difficile", "sportif": "difficile", "sportive": "difficile",
    "tres difficile": "tres-difficile", "expert": "tres-difficile", "extreme": "tres-difficile",
}


def _normalize(s):
    s = s.lower().strip()
    for a, b in (("àâä", "a"), ("éèêë", "e"), ("îï", "i"), ("ôö", "o"), ("ùûü", "u"), ("ç", "c")):
        for c in a:
            s = s.replace(c, b)
    return " ".join(re.findall(r"[a-z0-9]+", s))


def difficulty_key(raw):
    return _DIFF_ALIASES.get(_normalize(raw or ""), "")


def duration_text(field, tags):
    """Même règle que le site : champ « duration », sinon tags « N jour(s) »."""
    if field and field.strip():
        return field.strip()
    days = sorted(int(m.group(1)) for t in tags for m in [re.match(r"^(\d+)\s*jours?$", _normalize(t))] if m)
    if not days:
        return ""
    lo, hi = days[0], days[-1]
    unit = lambda n: "jours" if n > 1 else "jour"
    return f"{lo} {unit(lo)}" if lo == hi else f"{lo} à {hi} {unit(hi)}"


def haversine_m(a, b):
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp, dl = p2 - p1, math.radians(b[1] - a[1])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371000 * math.asin(min(1.0, math.sqrt(h)))


def load_track(path):
    """[(lat, lon, ele|None, km_cumulé)] depuis un GPX (trace, sinon itinéraire)."""
    root = ET.parse(path).getroot()
    pts = root.findall(".//{*}trkpt") or root.findall(".//{*}rtept")
    out, km = [], 0.0
    for el in pts:
        try:
            lat, lon = float(el.get("lat")), float(el.get("lon"))
        except (TypeError, ValueError):
            continue
        ele_el = el.find("{*}ele")
        try:
            ele = float(ele_el.text) if ele_el is not None and ele_el.text else None
        except ValueError:
            ele = None
        if out:
            km += haversine_m(out[-1], (lat, lon)) / 1000
        out.append((lat, lon, ele, km))
    return out


def load_slope(ride_dir):
    """Tronçons colorés de slope.geojson : [{coords:[(lat,lon)], color, start_km, end_km}]."""
    path = os.path.join(ride_dir, "slope.geojson")
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return []
    segs = []
    for feat in data.get("features", []):
        p = feat.get("properties", {})
        coords = (feat.get("geometry") or {}).get("coordinates") or []
        if len(coords) < 2 or not p.get("color"):
            continue
        segs.append({
            "coords": [(c[1], c[0]) for c in coords],
            "color": hex_to_rgb(p["color"]),
            "start_km": p.get("start_km", 0.0),
            "end_km": p.get("end_km", 0.0),
        })
    return segs


def photos_of(ride_dir):
    d = os.path.join(ride_dir, "photos")
    if not os.path.isdir(d):
        return []
    exts = (".jpg", ".jpeg", ".png", ".webp")
    return [os.path.join(d, n) for n in sorted(os.listdir(d)) if n.lower().endswith(exts)]


def load_ride(ride_dir, site_url=DEFAULT_SITE_URL):
    """Toutes les informations utiles d'une sortie, depuis les fichiers du
    dossier (aucune donnée inventée : un champ absent reste vide)."""
    ride_dir = os.path.normpath(ride_dir)
    desc = os.path.join(ride_dir, "description.md")
    if not os.path.exists(desc):
        raise FileNotFoundError(f"{desc} introuvable")
    fields, body = parse_description(desc)
    slug = os.path.basename(ride_dir)
    tags = [t.strip() for t in fields.get("tags", "").split(",") if t.strip()]

    gpx = next((os.path.join(ride_dir, n) for n in sorted(os.listdir(ride_dir)) if n.lower().endswith(".gpx")), None)
    track = []
    if gpx:
        try:
            track = load_track(gpx)
        except (ET.ParseError, OSError) as e:
            print(f"⚠ trace GPX illisible ({e}), ignorée")

    distance = float(fields["distance_km"]) if fields.get("distance_km") else (track[-1][3] if track else None)
    elevation = float(fields["elevation_m"]) if fields.get("elevation_m") else None
    if elevation is None and track:
        gain = 0.0
        for a, b in zip(track, track[1:]):
            if a[2] is not None and b[2] is not None and b[2] > a[2]:
                gain += b[2] - a[2]
        elevation = gain

    return {
        "dir": ride_dir,
        "slug": slug,
        "title": fields.get("title") or slug,
        "difficulty": fields.get("difficulty", ""),
        "difficulty_key": difficulty_key(fields.get("difficulty", "")),
        "departure": fields.get("departure", ""),
        "date": fields.get("date", ""),
        "tags": tags,
        "duration": duration_text(fields.get("duration", ""), tags),
        "distance_km": distance,
        "elevation_m": elevation,
        "summary": summary_text(body),
        "photos": photos_of(ride_dir),
        "track": track,
        "slope": load_slope(ride_dir),
        "url": site_url.rstrip("/") + "/rides/" + slug + "/",
    }


def fmt_int(n):
    """5371 -> « 5 371 » (espace fine insécable, comme sur le site)."""
    return f"{int(round(n)):,}".replace(",", "\u202f")


# --- Dessin ---------------------------------------------------------------------

def open_photo(path):
    im = Image.open(path)
    im = ImageOps.exif_transpose(im)
    return im.convert("RGB")


def cover(im, w, h, focus_y=0.5):
    """Recadre im pour remplir w×h sans déformation."""
    r = max(w / im.width, h / im.height)
    im = im.resize((max(w, round(im.width * r)), max(h, round(im.height * r))), Image.Resampling.LANCZOS)
    left = (im.width - w) // 2
    top = int((im.height - h) * focus_y)
    return im.crop((left, top, left + w, top + h))


def vertical_gradient(w, h, top_rgba, bottom_rgba):
    grad = Image.new("RGBA", (1, h))
    for y in range(h):
        t = y / max(1, h - 1)
        grad.putpixel((0, y), tuple(round(a + (b - a) * t) for a, b in zip(top_rgba, bottom_rgba)))
    return grad.resize((w, h))


def shadow(canvas, box, radius, blur=18, offset=(0, 10), alpha=60):
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    x1, y1, x2, y2 = box
    ImageDraw.Draw(layer).rounded_rectangle(
        (x1 + offset[0], y1 + offset[1], x2 + offset[0], y2 + offset[1]), radius=radius, fill=(*INK, alpha))
    canvas.alpha_composite(layer.filter(ImageFilter.GaussianBlur(blur)))


def mountain_edge(w, height, y_base, fill):
    """Polygone « ligne de relief » du site (bas du bandeau d'accueil)."""
    pts = [(0, 1.0), (0, 0.6), (0.08, 0.3), (0.16, 0.55), (0.27, 0.1), (0.38, 0.5), (0.47, 0.35),
           (0.58, 0.7), (0.70, 0.2), (0.81, 0.55), (0.90, 0.35), (1.0, 0.6), (1.0, 1.0)]
    return [(x * w, y_base - height + y * height) for x, y in pts], fill


def logo_mark(size, color=None):
    """Emblème du logo (cercle, montagnes, vélo, chemin), éventuellement
    recoloré d'une teinte unie (ex. blanc sur photo)."""
    im = Image.open(LOGO_MARK).convert("RGBA").resize((size, size), Image.Resampling.LANCZOS)
    if color:
        solid = Image.new("RGBA", im.size, (*color, 255))
        solid.putalpha(im.getchannel("A"))
        return solid
    return im


def brand_lockup(canvas, xy, mark=56, on_photo=True):
    """Emblème + « Cyclo Explore » + devise, dans une pastille claire posée
    sur la photo (comme l'en-tête du site). Renvoie la boîte occupée."""
    x, y = xy
    d = ImageDraw.Draw(canvas)
    name_f = font("serif", round(mark * 0.6), 700)
    tag_f = font("sans", max(11, round(mark * 0.2)), 600)
    name_w = d.textlength("Cyclo Explore", font=name_f)
    tag_w = sum(d.textlength(c, font=tag_f) for c in TAGLINE) + 1.6 * (len(TAGLINE) - 1)
    pad = round(mark * 0.22)
    w = pad + mark + round(mark * 0.25) + max(name_w, tag_w) + pad * 2
    h = mark + pad * 2
    box = (x, y, x + w, y + h)
    if on_photo:
        shadow(canvas, box, radius=h // 2, blur=14, offset=(0, 6), alpha=70)
        d.rounded_rectangle(box, radius=h // 2, fill=(*PAPER, 240))
    canvas.alpha_composite(logo_mark(mark), (x + pad, y + pad))
    tx = x + pad + mark + round(mark * 0.25)
    d.text((tx, y + pad + mark * 0.48), "Cyclo Explore", font=name_f, fill=FOREST, anchor="ls")
    draw_text(d, (tx, y + pad + mark * 0.8), TAGLINE, tag_f, OLIVE, anchor="ls", tracking=1.6)
    return box


def pill(draw, xy, text, fnt, fill, color, pad=(18, 9)):
    x, y = xy
    w = draw.textlength(text, font=fnt)
    asc, desc = fnt.getmetrics()
    h = asc + desc + pad[1] * 2
    draw.rounded_rectangle((x, y, x + w + pad[0] * 2, y + h), radius=h / 2, fill=fill)
    draw.text((x + pad[0], y + h / 2), text, font=fnt, fill=color, anchor="lm")
    return x + w + pad[0] * 2, y + h


def _projector(points, box, pad_frac=0.08):
    """Projection équirectangulaire (corrigée de la latitude) dans box."""
    x0, y0, x1, y1 = box
    lats = [p[0] for p in points]
    lons = [p[1] for p in points]
    min_lat, max_lat, min_lon, max_lon = min(lats), max(lats), min(lons), max(lons)
    k = math.cos(math.radians((min_lat + max_lat) / 2))
    span_x = max((max_lon - min_lon) * k, 1e-9)
    span_y = max(max_lat - min_lat, 1e-9)
    bw, bh = (x1 - x0) * (1 - 2 * pad_frac), (y1 - y0) * (1 - 2 * pad_frac)
    s = min(bw / span_x, bh / span_y)
    ox = x0 + (x1 - x0 - span_x * s) / 2
    oy = y0 + (y1 - y0 - span_y * s) / 2
    return lambda lat, lon: (ox + (lon - min_lon) * k * s, oy + (max_lat - lat) * s)


# --- Fond de carte (tuiles) --------------------------------------------------

# Fonds utilisables sous la trace des visuels. Tous gratuits et sans clé ;
# l'attribution est imprimée sur l'image (obligatoire).
TILE_PROVIDERS = {
    "ign": dict(
        url="https://data.geopf.fr/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0"
            "&LAYER=GEOGRAPHICALGRIDSYSTEMS.PLANIGNV2&STYLE=normal&TILEMATRIXSET=PM"
            "&FORMAT=image/png&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}",
        attribution="© IGN – Géoplateforme", max_zoom=18),
    "osm": dict(url="https://tile.openstreetmap.org/{z}/{x}/{y}.png",
                attribution="© OpenStreetMap", max_zoom=18),
    "topo": dict(url="https://a.tile.opentopomap.org/{z}/{x}/{y}.png",
                 attribution="© OpenStreetMap · OpenTopoMap (CC-BY-SA)", max_zoom=16),
    "velo": dict(url="https://a.tile-cyclosm.openstreetmap.fr/cyclosm/{z}/{x}/{y}.png",
                 attribution="© OpenStreetMap · CyclOSM", max_zoom=18),
}
TILE_CACHE = os.path.join(os.path.expanduser("~"), ".cache", "cycloexplore", "tiles")
USER_AGENT = "CycloExplore-visuels/1.0 (+https://montpellier.cycloexplore.fr)"


def _merc(lat, lon):
    """Coordonnées Web Mercator en pixels au zoom 0 (monde de 256 px)."""
    lat = max(-85.05112878, min(85.05112878, lat))
    x = (lon + 180.0) / 360.0 * 256.0
    y = (1 - math.log(math.tan(math.radians(lat)) + 1 / math.cos(math.radians(lat))) / math.pi) / 2 * 256.0
    return x, y


def fetch_tile(provider, z, x, y, timeout=8):
    """Une tuile (image RVB), depuis le cache local ou téléchargée."""
    prov = TILE_PROVIDERS[provider]
    path = os.path.join(TILE_CACHE, provider, str(z), str(x), f"{y}.img")
    if os.path.exists(path):
        return Image.open(path).convert("RGB")
    req = urllib.request.Request(prov["url"].format(z=z, x=x, y=y), headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
    img = Image.open(io.BytesIO(data)).convert("RGB")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)
    return img


def basemap(points, size, provider, pad_frac=0.1, fetch=None):
    """Fond de carte de taille size=(W, H) cadré sur points, en projection
    Web Mercator, et la fonction qui projette (lat, lon) sur ce fond.

    Le zoom est choisi pour que la trace remplisse le cadre ; les tuiles du
    zoom entier immédiatement supérieur sont assemblées puis réduites (plus
    net). Renvoie (None, None) si une tuile ne peut pas être obtenue (pas de
    réseau…) : l'appelant garde alors un fond uni.
    """
    fetch = fetch or fetch_tile
    W, H = size
    xs, ys = zip(*(_merc(lat, lon) for lat, lon in points))
    span_x, span_y = max(max(xs) - min(xs), 1e-9), max(max(ys) - min(ys), 1e-9)
    zf = math.log2(min(W * (1 - 2 * pad_frac) / span_x, H * (1 - 2 * pad_frac) / span_y))
    zi = max(0, min(TILE_PROVIDERS[provider]["max_zoom"], math.ceil(zf)))
    zf = min(zf, zi)
    k = 2 ** (zf - zi)  # facteur de réduction des tuiles (≤ 1)
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2

    # Zone à couvrir, en pixels du zoom entier zi
    left = cx * 2 ** zi - W / (2 * k)
    top = cy * 2 ** zi - H / (2 * k)
    right, bottom = left + W / k, top + H / k
    tx0, ty0 = int(left // 256), int(top // 256)
    tx1, ty1 = int(right // 256), int(bottom // 256)
    n = 2 ** zi
    mosaic = Image.new("RGB", ((tx1 - tx0 + 1) * 256, (ty1 - ty0 + 1) * 256), CREAM)
    try:
        for tx in range(tx0, tx1 + 1):
            for ty in range(ty0, ty1 + 1):
                if 0 <= ty < n:
                    mosaic.paste(fetch(provider, zi, tx % n, ty), ((tx - tx0) * 256, (ty - ty0) * 256))
    except Exception as e:  # réseau, HTTP, image illisible : on renonce au fond
        print(f"⚠ fond de carte « {provider} » indisponible ({e}) : trace sur fond uni")
        return None, None
    ox, oy = left - tx0 * 256, top - ty0 * 256
    crop = mosaic.crop((round(ox), round(oy), round(ox + W / k), round(oy + H / k)))
    image = crop.resize((W, H), Image.Resampling.LANCZOS)

    def project(lat, lon):
        x, y = _merc(lat, lon)
        return (x - cx) * 2 ** zf + W / 2, (y - cy) * 2 ** zf + H / 2

    return image, project


def soften(image, amount=0.32, tint=CREAM):
    """Atténue un fond de carte (désaturé et éclairci vers le crème du site)
    pour que la trace colorée ressorte."""
    gray = ImageOps.grayscale(image).convert("RGB")
    muted = Image.blend(image, gray, 0.45)
    return Image.blend(muted, Image.new("RGB", image.size, tint), amount)


def draw_route(canvas, box, ride, width=8, casing=(255, 255, 255), fallback=TERRACOTTA, scale=3,
               provider=None, radius=0, fetch=None):
    """Silhouette de la trace, colorée selon la pente (slope.geojson) si
    disponible, sinon d'une couleur unie. Dessinée en sur-échantillonnage
    pour des courbes lisses.

    Avec provider (« ign », « osm », « topo », « velo »), la trace est posée
    sur un fond de carte atténué, recadré dans box (coins arrondis de rayon
    radius) avec l'attribution du fond. Renvoie True si la trace est
    dessinée ; ride["basemap_ok"] indique si le fond a pu être utilisé."""
    pts = [(p[0], p[1]) for p in ride["track"]] or [c for s in ride["slope"] for c in s["coords"]]
    if len(pts) < 2:
        return False
    x0, y0, x1, y1 = box
    W, H = (x1 - x0) * scale, (y1 - y0) * scale
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    proj = None
    ride["basemap_ok"] = False
    if provider:
        image, proj = basemap(pts, (W, H), provider, fetch=fetch)
        if image is not None:
            layer.paste(soften(image).convert("RGBA"), (0, 0))
            ride["basemap_ok"] = True
    if proj is None:
        proj = _projector(pts, (0, 0, W, H))
    d = ImageDraw.Draw(layer)
    w = width * scale
    if casing:
        d.line([proj(*p) for p in pts], fill=(*casing, 255), width=w + 6 * scale, joint="curve")
    if ride["slope"]:
        for s in ride["slope"]:
            d.line([proj(*c) for c in s["coords"]], fill=(*s["color"], 255), width=w, joint="curve")
    else:
        d.line([proj(*p) for p in pts], fill=(*fallback, 255), width=w, joint="curve")
    for p, col in ((pts[0], (63, 143, 79)), (pts[-1], INK)):
        cx, cy = proj(*p)
        r = w * 0.9
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(*col, 255), outline=(255, 255, 255, 255), width=2 * scale)

    if ride["basemap_ok"]:
        text = TILE_PROVIDERS[provider]["attribution"]
        f = font("sans", 11 * scale, 500)
        tw = d.textlength(text, font=f)
        pad = 5 * scale
        d.rounded_rectangle((W - tw - 3 * pad, H - 22 * scale, W - pad, H - pad), radius=6 * scale, fill=(255, 255, 255, 200))
        d.text((W - 2 * pad, H - 13.5 * scale), text, font=f, fill=(*INK_SOFT, 255), anchor="rm")

    out = layer.resize((x1 - x0, y1 - y0), Image.Resampling.LANCZOS)
    if radius:
        mask = Image.new("L", out.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, out.width - 1, out.height - 1), radius=radius, fill=255)
        out.putalpha(Image.composite(out.getchannel("A"), Image.new("L", out.size, 0), mask))
    canvas.alpha_composite(out, (x0, y0))
    return True


def draw_profile(canvas, box, ride, label_font=None, label_color=INK_SOFT, scale=2, background=CREAM):
    """Profil altimétrique : aire + ligne, colorées tronçon par tronçon selon
    la pente (mêmes couleurs que le site), altitudes mini/maxi en légende."""
    pts = [(p[3], p[2]) for p in ride["track"] if p[2] is not None]
    if len(pts) < 2:
        return False
    x0, y0, x1, y1 = box
    W, H = (x1 - x0) * scale, (y1 - y0) * scale
    total = pts[-1][0] or 1
    emin, emax = min(e for _, e in pts), max(e for _, e in pts)
    rng = max(emax - emin, 20)
    X = lambda km: km / total * W
    Y = lambda e: H - (e - emin) / rng * H * 0.9 - H * 0.04
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)

    step = max(1, len(pts) // 600)
    sample = pts[::step] + [pts[-1]]
    segs = ride["slope"] or [{"start_km": 0, "end_km": total, "color": TERRACOTTA}]

    def color_at(km):
        for s in segs:
            if s["start_km"] <= km <= s["end_km"]:
                return s["color"]
        return segs[-1]["color"]

    # Aire : un trapèze par intervalle, en couleur opaque adoucie vers le
    # fond (pas de transparence : aucun raccord visible entre tronçons).
    for (k0, e0), (k1, e1) in zip(sample, sample[1:]):
        c = color_at((k0 + k1) / 2)
        soft = tuple(round(a * 0.3 + b * 0.7) for a, b in zip(c, background))
        d.polygon([(X(k0), H), (X(k0), Y(e0)), (X(k1) + 1, Y(e1)), (X(k1) + 1, H)], fill=(*soft, 255))
    # Ligne : couleur franche, par tronçon continu de même couleur.
    run, run_color = [], None
    for (k0, e0), (k1, e1) in zip(sample, sample[1:]):
        c = color_at((k0 + k1) / 2)
        if c != run_color and run:
            d.line(run, fill=(*run_color, 255), width=3 * scale, joint="curve")
            run = [run[-1]]
        if not run:
            run = [(X(k0), Y(e0))]
        run.append((X(k1), Y(e1)))
        run_color = c
    if len(run) > 1:
        d.line(run, fill=(*run_color, 255), width=3 * scale, joint="curve")
    canvas.alpha_composite(layer.resize((x1 - x0, y1 - y0), Image.Resampling.LANCZOS), (x0, y0))

    if label_font:
        dd = ImageDraw.Draw(canvas)
        dd.text((x0, y0 - 6), f"{fmt_int(emax)} m", font=label_font, fill=label_color, anchor="ld")
        dd.text((x1, y0 - 6), f"{fmt_int(total)} km", font=label_font, fill=label_color, anchor="rd")
    return True


def display_url(url):
    for prefix in ("https://", "http://"):
        if url.startswith(prefix):
            url = url[len(prefix):]
    return url.rstrip("/")


def today_iso():
    return date.today().isoformat()
