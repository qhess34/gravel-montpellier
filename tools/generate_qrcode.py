#!/usr/bin/env python3
"""
Génère un visuel « QR code » aux couleurs de Cyclo Explore, à partager sur
Instagram ou à imprimer (flyer, autocollant au départ d'une sortie…) :

  - photo de la sortie, emblème et nom du site, pastille de difficulté ;
  - titre en Fraunces, chiffres clés (distance, D+, durée) ;
  - QR code stylé (modules arrondis vert forêt, repères d'angle terracotta,
    emblème du logo au centre — correction d'erreur maximale « H », pour
    rester lisible malgré le logo) ;
  - invitation à scanner et adresse de la fiche en pied de page.

Deux façons de l'utiliser :

  1. Avec un dossier de sortie : URL, titre, distance, D+, durée, difficulté
     et photo sont lus dans les fichiers de la sortie (rien à ressaisir) :
         python3 tools/generate_qrcode.py rides/clapiers-corconne
     -> rides/clapiers-corconne/qrcode.jpg

  2. Avec une URL quelconque (usage d'origine du script), les textes étant
     passés en options :
         python3 tools/generate_qrcode.py https://montpellier.cycloexplore.fr \\
             --title "Toutes nos sorties" --photos rides/clapiers-corconne/photos -o accueil.jpg

Options utiles :
    --format carre|affiche     1080×1080 (défaut) ou 1080×1350
    --plain                    exporte seulement le QR code stylé (PNG
                               transparent, 1200 px) pour l'impression
    --utm                      ajoute ?utm_source=qrcode&utm_medium=print
                               pour mesurer les visites dans les statistiques
    --title/--distance/--dplus/--photo/--photos/--logo/--font/-o
                               remplacent les valeurs lues dans la sortie

Dépend de Pillow et segno :
    pip install -r tools/requirements.txt
"""

import argparse
import os
import random
import sys
from pathlib import Path

try:
    import segno
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    sys.exit("Ce script a besoin de Pillow et segno : pip install -r tools/requirements.txt")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import brand as B  # noqa: E402

PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
FOOTER_H = 90
MARGIN = 64


# ============================================================
# QR CODE STYLÉ
# ============================================================

def styled_qr(data, size, quiet=3, logo=True, background=None, scale=4):
    """QR code aux couleurs du site, en image RGBA carrée de size px.

    Modules arrondis vert forêt, repères d'angle terracotta (anneau) + vert
    forêt (centre), emblème du logo au centre sur un disque blanc. La zone
    de silence (quiet modules) est blanche ; background=None la rend
    transparente autour du QR (utile pour l'impression).
    """
    qr = segno.make(data, error="h", boost_error=False)
    matrix = [list(row) for row in qr.matrix]
    n = len(matrix)
    total = n + 2 * quiet
    S = size * scale
    m = S / total  # taille d'un module en px (sur-échantillonné)

    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pad_px = 0  # zone de silence entièrement claire : meilleure lecture
    d.rounded_rectangle((pad_px, pad_px, S - pad_px, S - pad_px), radius=m * 2.2,
                        fill=(*(background or B.WHITE), 255))

    def cell(r, c):
        return quiet * m + c * m, quiet * m + r * m

    finders = [(0, 0), (0, n - 7), (n - 7, 0)]

    def in_finder(r, c):
        return any(fr <= r < fr + 7 and fc <= c < fc + 7 for fr, fc in finders)

    # Zone réservée à l'emblème (disque au centre, ~22 % du côté)
    center = quiet * m + n * m / 2
    logo_r = n * m * 0.11 if logo else 0

    def in_logo(r, c):
        if not logo:
            return False
        x, y = cell(r, c)
        cx, cy = x + m / 2, y + m / 2
        return (cx - center) ** 2 + (cy - center) ** 2 <= (logo_r + m * 0.9) ** 2

    inset = 0  # modules jointifs : un espace entre modules empêche certains lecteurs de décoder
    for r in range(n):
        for c in range(n):
            if not matrix[r][c] or in_finder(r, c) or in_logo(r, c):
                continue
            x, y = cell(r, c)
            d.rounded_rectangle((x + inset, y + inset, x + m - inset, y + m - inset),
                                radius=m * 0.3, fill=(*B.FOREST, 255))

    # Repères d'angle : coins seulement légèrement arrondis — trop ronds, ils
    # ne sont plus reconnus par les lecteurs (vérifié avec OpenCV).
    for fr, fc in finders:
        x, y = cell(fr, fc)
        d.rounded_rectangle((x, y, x + 7 * m, y + 7 * m), radius=m * 0.8, fill=(*B.TERRACOTTA, 255))
        d.rounded_rectangle((x + m, y + m, x + 6 * m, y + 6 * m), radius=m * 0.5, fill=(*(background or B.WHITE), 255))
        d.rounded_rectangle((x + 2 * m, y + 2 * m, x + 5 * m, y + 5 * m), radius=m * 0.4, fill=(*B.FOREST, 255))

    if logo:
        d.ellipse((center - logo_r - m * 0.5, center - logo_r - m * 0.5, center + logo_r + m * 0.5, center + logo_r + m * 0.5),
                  fill=(*(background or B.WHITE), 255))
        mark = B.logo_mark(int(logo_r * 2 * 0.92))
        img.alpha_composite(mark, (int(center - mark.width / 2), int(center - mark.height / 2)))

    return img.resize((size, size), Image.Resampling.LANCZOS)


def verify(img, expected):
    """Vérifie, si OpenCV est installé, que le QR code se décode bien (deux
    lecteurs, plusieurs tailles). Renvoie True/False, ou None sans OpenCV."""
    try:
        import cv2
        import numpy as np
    except ImportError:
        return None
    base = Image.new("RGBA", img.size, (*B.CREAM, 255))
    base.alpha_composite(img.convert("RGBA"))
    arr = np.array(base.convert("RGB"))[:, :, ::-1].copy()
    readers = [cv2.QRCodeDetector()]
    if hasattr(cv2, "QRCodeDetectorAruco"):
        readers.append(cv2.QRCodeDetectorAruco())
    for scale in (1.0, 0.5, 0.3):
        x = cv2.resize(arr, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        if not any(r.detectAndDecode(x)[0] == expected for r in readers):
            return False
    return True


# ============================================================
# PHOTOS (comportement d'origine conservé)
# ============================================================

def find_photos(directory):
    directory = Path(directory)
    if not directory.is_dir():
        raise FileNotFoundError(f"Dossier photos introuvable : {directory}")
    return sorted(p for p in directory.iterdir() if p.is_file() and p.suffix.lower() in PHOTO_EXTENSIONS)


def select_photo(photo=None, photos_dir=None, default=None):
    if photo:
        if not Path(photo).exists():
            raise FileNotFoundError(f"Photo introuvable : {photo}")
        return str(photo)
    if photos_dir:
        photos = find_photos(photos_dir)
        if photos:
            chosen = random.choice(photos)
            print(f"Photo sélectionnée : {chosen}")
            return str(chosen)
        print(f"Aucune photo trouvée dans {photos_dir}")
    return default


# ============================================================
# MISE EN PAGE
# ============================================================

def title_font_override(path, size):
    return ImageFont.truetype(str(path), size)


def render(info, fmt, qr_url, custom_logo=None, custom_font=None):
    W, H = (1080, 1080) if fmt == "carre" else (1080, 1350)
    photo_h = 450 if fmt == "carre" else 480
    canvas = Image.new("RGBA", (W, H), (*B.CREAM, 255))
    d = ImageDraw.Draw(canvas)

    # --- Photo + en-tête -----------------------------------------------------
    if info["photo"]:
        photo = B.cover(B.open_photo(info["photo"]), W, photo_h + 50, focus_y=0.55).convert("RGBA")
    else:
        photo = B.vertical_gradient(W, photo_h + 50, (*B.OLIVE, 255), (*B.FOREST, 255))
    canvas.alpha_composite(photo, (0, 0))
    canvas.alpha_composite(B.vertical_gradient(W, 240, (*B.INK, 120), (*B.INK, 0)), (0, 0))

    if custom_logo:
        logo = Image.open(custom_logo).convert("RGBA")
        logo.thumbnail((360, 120), Image.Resampling.LANCZOS)
        B.shadow(canvas, (40, 40, 40 + logo.width + 36, 40 + logo.height + 24), radius=24, blur=12, offset=(0, 5), alpha=60)
        ImageDraw.Draw(canvas).rounded_rectangle((40, 40, 40 + logo.width + 36, 40 + logo.height + 24), radius=24, fill=(*B.PAPER, 240))
        canvas.alpha_composite(logo, (58, 52))
    else:
        B.brand_lockup(canvas, (40, 40), mark=56)
    d = ImageDraw.Draw(canvas)

    if info["difficulty"]:
        color = B.DIFFICULTY_COLORS.get(B.difficulty_key(info["difficulty"]), B.INK_SOFT)
        f = B.font("sans", 26, 700)
        tw = d.textlength(info["difficulty"], font=f)
        x = W - 40 - tw - 44
        B.shadow(canvas, (x, 50, W - 40, 100), radius=25, blur=10, offset=(0, 4), alpha=70)
        d = ImageDraw.Draw(canvas)
        B.pill(d, (x, 50), info["difficulty"], f, color, B.WHITE, pad=(22, 10))

    poly, fill = B.mountain_edge(W, 42, photo_h + 2, (*B.CREAM, 255))
    d.polygon(poly, fill=fill)
    d.rectangle((0, photo_h, W, H), fill=(*B.CREAM, 255))

    footer_y = H - FOOTER_H
    title_font = (lambda size: title_font_override(custom_font, size)) if custom_font else None

    def fit(text, width, lines, sizes):
        if not title_font:
            return B.fit_title(d, text, width, lines, sizes)
        for s in sizes:
            fnt = title_font(s)
            wrapped = B.wrap(d, text, fnt, width)
            if len(wrapped) <= lines:
                return fnt, wrapped
        fnt = title_font(sizes[-1])
        return fnt, B.wrap(d, text, fnt, width)[:lines]

    stats = " · ".join(x for x in (info["distance"], info["dplus"], info["duration"]) if x)
    cta = "Scannez pour retrouver la trace GPX, la carte, les photos et les vues 360°."

    if fmt == "carre":
        # QR à gauche, textes à droite
        card = 470
        qx, qy = MARGIN, photo_h - 50
        B.shadow(canvas, (qx, qy, qx + card, qy + card), radius=34, blur=22, offset=(0, 12), alpha=85)
        canvas.alpha_composite(styled_qr(qr_url, card), (qx, qy))
        d = ImageDraw.Draw(canvas)

        tx = qx + card + 40
        tw = W - MARGIN - tx
        fnt, lines = fit(info["title"] or "Cyclo Explore", tw, 4, (48, 44, 40, 36, 32))
        asc, desc = fnt.getmetrics()
        lh = int((asc + desc) * 1.02)
        sf, cf = B.font("sans", 25, 600), B.font("sans", 22, 400)
        stat_lines = B.wrap(d, stats, sf, tw) if stats else []
        cta_lines = B.wrap(d, cta, cf, tw)
        block_h = 36 + len(lines) * lh + (len(stat_lines) * 36 + 8 if stat_lines else 0) + 10 + len(cta_lines) * 31
        # colonne de texte centrée verticalement face au QR (sous la photo)
        y = max(photo_h + 24, qy + (card - block_h) / 2 + 20)
        B.draw_text(d, (tx, y), "SORTIE VÉLO & GRAVEL", B.font("sans", 20, 600), B.OLIVE, tracking=2.2)
        y += 36
        for line in lines:
            d.text((tx, y), line, font=fnt, fill=B.INK)
            y += lh
        if stat_lines:
            y += 8
            for line in stat_lines:
                d.text((tx, y), line, font=sf, fill=B.TERRACOTTA_DARK)
                y += 36
        y += 10
        for line in cta_lines:
            d.text((tx, y), line, font=cf, fill=B.INK_SOFT)
            y += 31
    else:
        # Affiche : titre centré, QR centré, invitation dessous
        y = photo_h + 24
        B.draw_text(d, (W / 2, y), "SORTIE VÉLO & GRAVEL", B.font("sans", 21, 600), B.OLIVE, anchor="mt", tracking=2.4)
        y += 38
        fnt, lines = fit(info["title"] or "Cyclo Explore", W - 2 * MARGIN, 2, (60, 54, 48, 42, 38))
        asc, desc = fnt.getmetrics()
        for line in lines:
            d.text((W / 2, y), line, font=fnt, fill=B.INK, anchor="mt")
            y += int((asc + desc) * 1.02)
        if stats:
            y += 6
            d.text((W / 2, y), stats, font=B.font("sans", 28, 600), fill=B.TERRACOTTA_DARK, anchor="mt")
            y += 44
        card = min(420, footer_y - y - 110)
        qx, qy = (W - card) // 2, y + 18
        B.shadow(canvas, (qx, qy, qx + card, qy + card), radius=34, blur=22, offset=(0, 12), alpha=85)
        canvas.alpha_composite(styled_qr(qr_url, card), (qx, qy))
        d = ImageDraw.Draw(canvas)
        d.text((W / 2, qy + card + 26), cta, font=B.font("sans", 23, 500), fill=B.INK_SOFT, anchor="mt")

    # --- Pied de page --------------------------------------------------------
    d.rectangle((0, footer_y, W, H), fill=(*B.FOREST, 255))
    canvas.alpha_composite(B.logo_mark(50, color=B.WHITE), (MARGIN - 4, footer_y + (FOOTER_H - 50) // 2))
    d = ImageDraw.Draw(canvas)
    url_text = B.display_url(info["display_url"])
    uf = B.font("sans", 26, 600)
    while d.textlength(url_text, font=uf) > W - 2 * MARGIN - 70 - 150 and uf.size > 16:
        uf = B.font("sans", uf.size - 1, 600)
    d.text((MARGIN + 60, footer_y + FOOTER_H / 2), url_text, font=uf, fill=B.WHITE, anchor="lm")
    B.draw_text(d, (W - MARGIN, footer_y + FOOTER_H / 2), "SCANNEZ-MOI", B.font("sans", 19, 700), B.SAND,
                anchor="rm", tracking=2.2)
    return canvas


# ============================================================
# CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="QR code aux couleurs de Cyclo Explore (sortie ou URL).")
    parser.add_argument("target", help="Dossier d'une sortie (ex: rides/clapiers-corconne) ou URL à encoder")
    parser.add_argument("--title", help="Titre (défaut : celui de la sortie)")
    parser.add_argument("--distance", help="Distance, ex: « 86 km » (défaut : celle de la sortie)")
    parser.add_argument("--dplus", help="D+, ex: « 1250 m » (défaut : celui de la sortie)")
    parser.add_argument("--photo", help="Photo précise")
    parser.add_argument("--photos", help="Dossier de photos (une est tirée au hasard)")
    parser.add_argument("--logo", help="Logo à utiliser à la place de l'emblème Cyclo Explore")
    parser.add_argument("--font", help="Police TTF/OTF des titres (défaut : Fraunces, fournie)")
    parser.add_argument("--format", choices=("carre", "affiche"), default="carre", help="carre (1080×1080, défaut) ou affiche (1080×1350)")
    parser.add_argument("--plain", action="store_true", help="Exporter seulement le QR code stylé (PNG transparent 1200 px)")
    parser.add_argument("--utm", action="store_true", help="Ajouter ?utm_source=qrcode&utm_medium=print à l'URL encodée")
    parser.add_argument("--site-url", default=B.DEFAULT_SITE_URL, help="URL publique du site (mode dossier de sortie)")
    parser.add_argument("-o", "--output", help="Fichier de sortie (défaut : qrcode.jpg dans le dossier de la sortie, ou cyclo_explore_qrcode.jpg)")
    args = parser.parse_args()

    if args.photo and args.photos:
        parser.error("--photo et --photos ne peuvent pas être utilisés simultanément.")

    info = {"title": "", "distance": "", "dplus": "", "duration": "", "difficulty": "", "photo": None}
    if os.path.isdir(args.target):
        try:
            ride = B.load_ride(args.target, args.site_url)
        except FileNotFoundError as e:
            sys.exit(f"✗ {e}")
        url = ride["url"]
        info.update(
            title=ride["title"],
            distance=f"{B.fmt_int(ride['distance_km'])} km" if ride["distance_km"] else "",
            dplus=f"{B.fmt_int(ride['elevation_m'])} m D+" if ride["elevation_m"] else "",
            duration=ride["duration"],
            difficulty=ride["difficulty"],
            photo=ride["photos"][0] if ride["photos"] else None,
        )
        default_out = os.path.join(args.target, "qrcode.png" if args.plain else "qrcode.jpg")
    elif args.target.startswith(("http://", "https://")):
        url = args.target
        default_out = "cyclo_explore_qrcode.png" if args.plain else "cyclo_explore_qrcode.jpg"
    else:
        sys.exit(f"✗ {args.target} n'est ni un dossier de sortie ni une URL (http/https)")

    if args.title is not None:
        info["title"] = args.title
    if args.distance is not None:
        info["distance"] = args.distance
    if args.dplus is not None:
        info["dplus"] = args.dplus if "D+" in args.dplus or not args.dplus else f"{args.dplus} D+"
    try:
        info["photo"] = select_photo(args.photo, args.photos, info["photo"])
    except FileNotFoundError as e:
        sys.exit(f"✗ {e}")
    for path, label in ((args.logo, "Logo"), (args.font, "Police")):
        if path and not os.path.exists(path):
            sys.exit(f"✗ {label} introuvable : {path}")

    qr_url = url
    if args.utm:
        qr_url += ("&" if "?" in url else "?") + "utm_source=qrcode&utm_medium=print"
    info["display_url"] = url
    out = args.output or default_out

    check = verify(styled_qr(qr_url, 600), qr_url)
    if check is False:
        print("⚠ le QR code stylé n'a pas pu être relu à toutes les tailles : testez-le au téléphone avant impression")

    if args.plain:
        styled_qr(qr_url, 1200, background=B.WHITE).save(out, "PNG", optimize=True)
        print(f"✓ QR code : {out} (1200×1200) → {qr_url}")
        if check:
            print("  Relecture vérifiée (OpenCV)")
        return

    image = render(info, args.format, qr_url, args.logo, args.font)
    if out.lower().endswith(".png"):
        image.save(out, "PNG", optimize=True)
    else:
        image.convert("RGB").save(out, "JPEG", quality=94, optimize=True, progressive=True)
    print(f"✓ Visuel QR code : {out} ({image.width}×{image.height})")
    print(f"  URL encodée : {qr_url}" + ("  (relecture vérifiée)" if check else ""))
    if info["photo"]:
        print(f"  Photo : {info['photo']}")


if __name__ == "__main__":
    main()
