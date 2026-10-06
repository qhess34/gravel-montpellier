#!/usr/bin/env python3
"""
Génère le visuel Instagram d'une sortie, aux couleurs du site Cyclo Explore :

  - photo de la sortie en grand, avec l'emblème et le nom du site ;
  - pastille de difficulté (même couleur que sur le site) ;
  - titre en Fraunces, chiffres clés (distance, D+, durée) ;
  - silhouette de la trace et profil altimétrique colorés selon la pente
    (mêmes couleurs que la carte du site, lues dans slope.geojson) ;
  - bandeau de pied avec l'adresse de la fiche.

Trois formats : post (1080×1350, défaut), story (1080×1920), carre (1080×1080).

Le fichier généré (instagram.jpg à la racine du dossier de la sortie, pour
le format post) est repris automatiquement par le site : un bouton
« Instagram » apparaît dans le bloc de partage de la fiche.

Toutes les données viennent des fichiers de la sortie (description.md, GPX,
photos/, slope.geojson) : rien à ressaisir. Polices Fraunces et Inter
fournies dans tools/fonts (licence OFL).

Dépend de Pillow :
    pip install -r tools/requirements.txt

Usage :
    python3 tools/make_instagram_image.py rides/clapiers-corconne
    python3 tools/make_instagram_image.py rides/clapiers-corconne --format story
    python3 tools/make_instagram_image.py rides/clapiers-corconne --photo photos/sommet.jpg
    python3 tools/make_instagram_image.py rides/clapiers-corconne --out apercu.jpg
"""

import argparse
import os
import sys

try:
    from PIL import Image, ImageDraw
except ImportError:
    sys.exit("Ce script a besoin de Pillow : pip install -r tools/requirements.txt")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import brand as B  # noqa: E402

FORMATS = {
    # largeur, hauteur, hauteur photo, côté de la carte de trace, tailles de titre, lignes max, synthèse
    "post": dict(w=1080, h=1350, photo=690, route=290, sizes=(58, 54, 50, 46, 42), lines=3, summary=False),
    "story": dict(w=1080, h=1920, photo=1000, route=360, sizes=(76, 68, 60, 54), lines=3, summary=True),
    "carre": dict(w=1080, h=1080, photo=500, route=250, sizes=(52, 48, 44, 40), lines=2, summary=False),
}
MARGIN = 56
FOOTER_H = 84


def stat_blocks(ride):
    blocks = []
    if ride["distance_km"]:
        blocks.append(("DISTANCE", f"{B.fmt_int(ride['distance_km'])} km"))
    if ride["elevation_m"]:
        blocks.append(("DÉNIVELÉ +", f"{B.fmt_int(ride['elevation_m'])} m"))
    if ride["duration"]:
        blocks.append(("DURÉE", ride["duration"]))
    return blocks


def render(ride, fmt, photo_path=None, basemap="ign", fetch=None):
    L = FORMATS[fmt]
    W, H = L["w"], L["h"]
    canvas = Image.new("RGBA", (W, H), (*B.CREAM, 255))
    d = ImageDraw.Draw(canvas)

    # --- Photo + voiles (lisibilité du logo en haut) ------------------------
    photo_h = L["photo"]
    photo_path = photo_path or (ride["photos"][0] if ride["photos"] else None)
    if photo_path:
        photo = B.cover(B.open_photo(photo_path), W, photo_h + 60, focus_y=0.55).convert("RGBA")
    else:
        photo = B.vertical_gradient(W, photo_h + 60, (*B.OLIVE, 255), (*B.FOREST, 255))
    canvas.alpha_composite(photo, (0, 0))
    canvas.alpha_composite(B.vertical_gradient(W, 260, (*B.INK, 120), (*B.INK, 0)), (0, 0))

    B.brand_lockup(canvas, (40, 40), mark=58)

    if ride["difficulty"]:
        color = B.DIFFICULTY_COLORS.get(ride["difficulty_key"], B.INK_SOFT)
        f = B.font("sans", 28, 700)
        tw = d.textlength(ride["difficulty"], font=f)
        x = W - 40 - tw - 44
        B.shadow(canvas, (x, 52, W - 40, 104), radius=26, blur=10, offset=(0, 4), alpha=70)
        d = ImageDraw.Draw(canvas)
        B.pill(d, (x, 52), ride["difficulty"], f, color, B.WHITE, pad=(22, 11))

    # --- Bord « relief » entre la photo et le panneau crème -------------------
    poly, fill = B.mountain_edge(W, 46, photo_h + 2, (*B.CREAM, 255))
    d.polygon(poly, fill=fill)
    d.rectangle((0, photo_h, W, H), fill=(*B.CREAM, 255))

    # --- Carte de la trace, à cheval sur la photo -----------------------------
    R = L["route"]
    rx, ry = W - MARGIN - R, photo_h - int(R * 0.55)
    has_route = bool(ride["track"] or ride["slope"])
    if has_route:
        B.shadow(canvas, (rx, ry, rx + R, ry + R), radius=30, blur=22, offset=(0, 12), alpha=80)
        d = ImageDraw.Draw(canvas)
        d.rounded_rectangle((rx, ry, rx + R, ry + R), radius=30, fill=(*B.PAPER, 255))
        if basemap and basemap != "aucun":
            # trace sur fond de carte, sur toute la carte (coins arrondis)
            B.draw_route(canvas, (rx, ry, rx + R, ry + R), ride, width=6, provider=basemap, radius=30, fetch=fetch)
            if not ride.get("basemap_ok"):  # pas de fond (réseau…) : rendu d'origine
                d = ImageDraw.Draw(canvas)
                d.rounded_rectangle((rx, ry, rx + R, ry + R), radius=30, fill=(*B.PAPER, 255))
                B.draw_route(canvas, (rx + 16, ry + 16, rx + R - 16, ry + R - 16), ride, width=7)
        else:
            B.draw_route(canvas, (rx + 16, ry + 16, rx + R - 16, ry + R - 16), ride, width=7)
        d = ImageDraw.Draw(canvas)

    # --- Titre ------------------------------------------------------------------
    col_w = (W - 2 * MARGIN - R - 36) if has_route else (W - 2 * MARGIN)
    y = photo_h + 26
    B.draw_text(d, (MARGIN, y), "SORTIE VÉLO & GRAVEL · MONTPELLIER", B.font("sans", 21, 600), B.OLIVE, tracking=2.4)
    y += 40
    tf, lines = B.fit_title(d, ride["title"], col_w, L["lines"], L["sizes"])
    asc, desc = tf.getmetrics()
    line_h = int((asc + desc) * 1.02)
    for line in lines:
        d.text((MARGIN, y), line, font=tf, fill=B.INK)
        y += line_h
    if ride["departure"]:
        y += 4
        d.text((MARGIN, y), "Départ : " + ride["departure"], font=B.font("sans", 24, 500), fill=B.INK_SOFT)
        y += 36
    y = max(y, (ry + R) if has_route else y) + 26

    # --- Chiffres clés -----------------------------------------------------------
    blocks = stat_blocks(ride)
    if blocks:
        bw = (W - 2 * MARGIN) / len(blocks)
        vf, cf = B.font("serif", 50, 650), B.font("sans", 19, 700)
        for i, (cap, val) in enumerate(blocks):
            bx = MARGIN + i * bw
            if i:
                d.line((bx, y + 6, bx, y + 86), fill=B.LINE, width=2)
            px = bx + (24 if i else 0)
            B.draw_text(d, (px, y), cap, cf, B.INK_SOFT, tracking=2)
            d.text((px, y + 26), val, font=vf, fill=B.TERRACOTTA_DARK)
        y += 96

    # --- Synthèse (story) -----------------------------------------------------------
    if L["summary"] and ride["summary"]:
        sf = B.font("sans", 31, 400)
        lines = B.wrap(d, ride["summary"], sf, W - 2 * MARGIN)
        if len(lines) > 6:
            lines = lines[:6]
            lines[-1] = lines[-1].rstrip(" ,;:.") + "…"
        y += 6
        for line in lines:
            d.text((MARGIN, y), line, font=sf, fill=B.INK)
            y += 46
        y += 14

    # --- Profil altimétrique coloré selon la pente -----------------------------------
    footer_y = H - FOOTER_H
    prof_top = y + 30
    prof_bottom = footer_y - 24
    if prof_bottom - prof_top >= 50 and ride["track"]:
        B.draw_profile(canvas, (MARGIN, prof_top, W - MARGIN, prof_bottom), ride,
                       label_font=B.font("sans", 20, 600))
        d = ImageDraw.Draw(canvas)

    # --- Pied de page -------------------------------------------------------------------
    d.rectangle((0, footer_y, W, H), fill=(*B.FOREST, 255))
    canvas.alpha_composite(B.logo_mark(48, color=B.WHITE), (MARGIN - 4, footer_y + (FOOTER_H - 48) // 2))
    d = ImageDraw.Draw(canvas)
    d.text((MARGIN + 58, footer_y + FOOTER_H / 2), B.display_url(ride["url"]), font=B.font("sans", 25, 600),
           fill=B.WHITE, anchor="lm")
    B.draw_text(d, (W - MARGIN, footer_y + FOOTER_H / 2), "GPX · CARTE · 360°", B.font("sans", 19, 700), B.SAND,
                anchor="rm", tracking=2)
    return canvas.convert("RGB")


def main():
    parser = argparse.ArgumentParser(description="Génère le visuel Instagram d'une sortie (charte Cyclo Explore).")
    parser.add_argument("ride", help="Dossier de la sortie (ex: rides/clapiers-corconne)")
    parser.add_argument("--format", choices=sorted(FORMATS), default="post",
                        help="post (1080×1350, défaut), story (1080×1920) ou carre (1080×1080)")
    parser.add_argument("--photo", help="Photo à utiliser (chemin relatif au dossier de la sortie, ou absolu). Défaut : la première de photos/")
    parser.add_argument("--out", help="Fichier de sortie (défaut : instagram.jpg, ou instagram-<format>.jpg, dans le dossier de la sortie)")
    parser.add_argument("--site-url", default=B.DEFAULT_SITE_URL, help="URL publique du site (adresse affichée)")
    parser.add_argument("--fond", choices=sorted(B.TILE_PROVIDERS) + ["aucun"], default="ign",
                        help="fond de carte sous la trace : ign (Plan IGN, défaut), osm, topo, velo, ou aucun ; "
                             "tuiles téléchargées puis gardées en cache (~/.cache/cycloexplore/tiles)")
    parser.add_argument("--logo", help=argparse.SUPPRESS)  # ancienne option, l'emblème du site est utilisé
    args = parser.parse_args()

    if not os.path.isdir(args.ride):
        sys.exit(f"✗ {args.ride} n'est pas un dossier de sortie")
    try:
        ride = B.load_ride(args.ride, args.site_url)
    except FileNotFoundError as e:
        sys.exit(f"✗ {e}")

    photo = None
    if args.photo:
        photo = args.photo if os.path.isabs(args.photo) else os.path.join(args.ride, args.photo)
        if not os.path.exists(photo):
            sys.exit(f"✗ Photo introuvable : {photo}")
    if not (photo or ride["photos"]):
        print("⚠ aucune photo : fond aux couleurs du site")
    if not ride["slope"] and ride["track"]:
        print("⚠ slope.geojson absent : trace en couleur unie (python3 tools/slope_colors.py " + args.ride + ")")

    image = render(ride, args.format, photo, basemap=args.fond)
    name = "instagram.jpg" if args.format == "post" else f"instagram-{args.format}.jpg"
    out = args.out or os.path.join(args.ride, name)
    image.save(out, "JPEG", quality=92, optimize=True, progressive=True)
    print(f"✓ Image générée : {out} ({image.width}×{image.height})")


if __name__ == "__main__":
    main()
