#!/usr/bin/env python3

import argparse
import random
import subprocess
from pathlib import Path

import segno
from PIL import Image, ImageDraw, ImageFont, ImageFilter


# ============================================================
# CHARTE GRAPHIQUE CYCLO EXPLORE
# ============================================================

WIDTH = 1080
HEIGHT = 1080

HEADER_BG = "#E9DCC8"
CONTENT_BG = "#F7F2EA"
TEXT_COLOR = "#2B2620"
WHITE = "#FFFFFF"

HEADER_HEIGHT = 230
FOOTER_HEIGHT = 90

# QR exactement au centre
QR_SIZE = 360
QR_CENTER_X = WIDTH // 2
QR_CENTER_Y = HEIGHT // 2 + 125

# Logo environ 3x plus grand
LOGO_MAX_WIDTH = 900
LOGO_MAX_HEIGHT = 300

FONT_DIRS = [
    Path("/usr/share/fonts"),
    Path("/usr/local/share/fonts"),
    Path.home() / ".fonts",
    Path.home() / ".local/share/fonts",
]

PHOTO_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
}


# ============================================================
# OUTILS
# ============================================================

def hex_to_rgb(value):
    value = value.lstrip("#")
    return tuple(
        int(value[i:i + 2], 16)
        for i in (0, 2, 4)
    )


def find_font_with_fc(pattern):
    try:
        result = subprocess.run(
            ["fc-match", "-f", "%{file}", pattern],
            capture_output=True,
            text=True,
            check=True
        )

        path = result.stdout.strip()

        if path and Path(path).exists():
            return Path(path)

    except Exception:
        pass

    return None


def find_font_file(names):
    names = [name.lower() for name in names]

    for directory in FONT_DIRS:
        if not directory.exists():
            continue

        try:
            for path in directory.rglob("*"):
                if not path.is_file():
                    continue

                if path.suffix.lower() not in {
                    ".ttf",
                    ".otf",
                    ".ttc"
                }:
                    continue

                filename = path.name.lower()

                if any(name in filename for name in names):
                    return path

        except Exception:
            pass

    return None


def resolve_fonts(explicit_font=None):

    # --------------------------------------------------------
    # Police explicitement fournie
    # --------------------------------------------------------

    if explicit_font:
        path = Path(explicit_font)

        if not path.exists():
            raise FileNotFoundError(
                f"Police introuvable : {path}"
            )

        return path, path

    # --------------------------------------------------------
    # Fraunces
    # --------------------------------------------------------

    regular = find_font_with_fc("Fraunces")
    bold = find_font_with_fc(
        "Fraunces:style=Bold"
    )

    if not regular:
        regular = find_font_file([
            "fraunces-regular",
            "fraunces_regular",
            "fraunces"
        ])

    if not bold:
        bold = find_font_file([
            "fraunces-bold",
            "fraunces-semibold",
            "fraunces-medium"
        ])

    if regular:
        print(f"Police : Fraunces ({regular})")
        return regular, bold or regular

    # --------------------------------------------------------
    # Georgia
    # --------------------------------------------------------

    regular = find_font_with_fc("Georgia")
    bold = find_font_with_fc(
        "Georgia:style=Bold"
    )

    if regular:
        print(f"Police : Georgia ({regular})")
        return regular, bold or regular

    # --------------------------------------------------------
    # DejaVu Serif
    # --------------------------------------------------------

    regular = find_font_with_fc("DejaVu Serif")
    bold = find_font_with_fc(
        "DejaVu Serif:style=Bold"
    )

    if regular:
        print(
            "Attention : Fraunces et Georgia "
            "non trouvées, utilisation de DejaVu Serif."
        )
        return regular, bold or regular

    raise RuntimeError(
        "Aucune police compatible trouvée."
    )


def load_font(path, size):
    return ImageFont.truetype(
        str(path),
        size=size
    )


def fit_font(
    draw,
    text,
    font_path,
    max_size,
    max_width,
    min_size=20
):
    for size in range(
        max_size,
        min_size - 1,
        -1
    ):
        font = load_font(
            font_path,
            size
        )

        bbox = draw.textbbox(
            (0, 0),
            text,
            font=font
        )

        width = bbox[2] - bbox[0]

        if width <= max_width:
            return font

    return load_font(
        font_path,
        min_size
    )


# ============================================================
# PHOTOS
# ============================================================

def find_photos(directory):
    """
    Retourne toutes les photos présentes dans un dossier.
    """

    directory = Path(directory)

    if not directory.exists():
        raise FileNotFoundError(
            f"Dossier photos introuvable : {directory}"
        )

    if not directory.is_dir():
        raise NotADirectoryError(
            f"Ce n'est pas un dossier : {directory}"
        )

    photos = [
        p
        for p in directory.iterdir()
        if p.is_file()
        and p.suffix.lower() in PHOTO_EXTENSIONS
    ]

    return sorted(photos)


def select_photo(photo=None, photos_dir=None):

    # Une photo explicitement donnée
    if photo:
        path = Path(photo)

        if not path.exists():
            raise FileNotFoundError(
                f"Photo introuvable : {path}"
            )

        return path

    # Un dossier de photos
    if photos_dir:
        photos = find_photos(
            photos_dir
        )

        if not photos:
            print(
                f"Aucune photo trouvée dans "
                f"{photos_dir}"
            )
            return None

        selected = random.choice(
            photos
        )

        print(
            f"Photo sélectionnée : {selected}"
        )

        return selected

    return None


def crop_to_size(
    image,
    width,
    height
):
    image = image.convert("RGB")

    ratio = max(
        width / image.width,
        height / image.height
    )

    new_width = int(
        image.width * ratio
    )

    new_height = int(
        image.height * ratio
    )

    image = image.resize(
        (new_width, new_height),
        Image.Resampling.LANCZOS
    )

    left = (
        new_width - width
    ) // 2

    top = (
        new_height - height
    ) // 2

    return image.crop(
        (
            left,
            top,
            left + width,
            top + height
        )
    )


def add_background_photo(
    canvas,
    photo_path
):

    if not photo_path:
        return

    photo = Image.open(
        photo_path
    ).convert("RGB")

    photo_height = (
        HEIGHT
        - HEADER_HEIGHT
        - FOOTER_HEIGHT
    )

    photo = crop_to_size(
        photo,
        WIDTH,
        photo_height
    )

    layer = Image.new(
        "RGBA",
        (WIDTH, photo_height),
        (0, 0, 0, 0)
    )

    layer.paste(
        photo,
        (0, 0)
    )

    # Voile crème au lieu d'un voile noir
    overlay = Image.new(
        "RGBA",
        (WIDTH, photo_height),
        (
            *hex_to_rgb(CONTENT_BG),
            80
        )
    )

    layer.alpha_composite(
        overlay
    )

    canvas.alpha_composite(
        layer,
        (0, HEADER_HEIGHT)
    )


# ============================================================
# OMBRE
# ============================================================

def add_shadow(
    base,
    box,
    radius=30,
    offset=(0, 10)
):

    x1, y1, x2, y2 = box

    shadow = Image.new(
        "RGBA",
        base.size,
        (0, 0, 0, 0)
    )

    draw = ImageDraw.Draw(
        shadow
    )

    draw.rounded_rectangle(
        (
            x1 + offset[0],
            y1 + offset[1],
            x2 + offset[0],
            y2 + offset[1]
        ),
        radius=radius,
        fill=(43, 38, 32, 55)
    )

    shadow = shadow.filter(
        ImageFilter.GaussianBlur(15)
    )

    base.alpha_composite(
        shadow
    )


# ============================================================
# LOGO
# ============================================================

def add_logo(
    canvas,
    logo_path,
    font_bold
):

    if logo_path:

        path = Path(logo_path)

        if not path.exists():
            raise FileNotFoundError(
                f"Logo introuvable : {path}"
            )

        original = Image.open(path).convert("RGBA")
 
        alpha = original.getchannel("A")

        logo = Image.new(
            "RGBA",
            original.size,
            (*hex_to_rgb(TEXT_COLOR), 0)
        )

        logo.putalpha(alpha)

        scale = min(
            LOGO_MAX_WIDTH / logo.width,
            LOGO_MAX_HEIGHT / logo.height
        )

        logo = logo.resize(
            (
                int(logo.width * scale),
                int(logo.height * scale)
            ),
            Image.Resampling.LANCZOS
        )

        x = (
            WIDTH - logo.width
        ) // 2

        y = (
            HEADER_HEIGHT - logo.height
        ) // 2

        canvas.alpha_composite(
            logo,
            (x, y)
        )

        return

    # --------------------------------------------------------
    # Fallback si aucun logo n'est fourni
    # --------------------------------------------------------

    draw = ImageDraw.Draw(
        canvas
    )

    font = load_font(
        font_bold,
        150
    )

    text = "CYCLO EXPLORE"

    bbox = draw.textbbox(
        (0, 0),
        text,
        font=font
    )

    text_width = (
        bbox[2] - bbox[0]
    )

    text_height = (
        bbox[3] - bbox[1]
    )

    x = (
        WIDTH - text_width
    ) // 2

    y = (
        HEADER_HEIGHT - text_height
    ) // 2 - bbox[1]

    draw.text(
        (x, y),
        text,
        font=font,
        fill=TEXT_COLOR
    )


# ============================================================
# TITRE
# ============================================================

def add_title(
    canvas,
    title,
    font_bold
):

    if not title:
        return

    draw = ImageDraw.Draw(
        canvas
    )

    font = fit_font(
        draw,
        title,
        font_bold,
        max_size=62,
        max_width=920,
        min_size=30
    )

    bbox = draw.textbbox(
        (0, 0),
        title,
        font=font
    )

    text_width = (
        bbox[2] - bbox[0]
    )

    x = (
        WIDTH - text_width
    ) // 2

    y = HEADER_HEIGHT + 20

    draw.text(
        (x, y),
        title,
        font=font,
        fill=TEXT_COLOR
    )


# ============================================================
# DISTANCE / D+
# ============================================================

def add_metrics(
    canvas,
    distance,
    dplus,
    font_bold
):

    values = []

    if distance:
        values.append(distance)

    if dplus:
        values.append(
            f"D+ {dplus}"
        )

    if not values:
        return

    draw = ImageDraw.Draw(
        canvas
    )

    text = "   •   ".join(
        values
    )

    font = load_font(
        font_bold,
        34
    )

    bbox = draw.textbbox(
        (0, 0),
        text,
        font=font
    )

    text_width = (
        bbox[2] - bbox[0]
    )

    x = (
        WIDTH - text_width
    ) // 2

    y = HEADER_HEIGHT + 85

    draw.text(
        (x, y),
        text,
        font=font,
        fill=TEXT_COLOR
    )


# ============================================================
# QR CODE
# ============================================================

def create_qr(url):

    qr = segno.make(
        url,
        error="h"
    )

    temp = Path(
        "/tmp/cyclo_explore_qr.png"
    )

    qr.save(
        temp,
        kind="png",
        scale=10,
        border=4,
        dark=TEXT_COLOR,
        light=WHITE
    )

    image = Image.open(
        temp
    ).convert("RGBA")

    image = image.resize(
        (QR_SIZE, QR_SIZE),
        Image.Resampling.NEAREST
    )

    return image


def add_qr(
    canvas,
    url
):

    qr = create_qr(
        url
    )

    # QR centré exactement à 540,540
    qr_x = (
        QR_CENTER_X
        - QR_SIZE // 2
    )

    qr_y = (
        QR_CENTER_Y
        - QR_SIZE // 2
    )

    padding = 30

    card = (
        qr_x - padding,
        qr_y - padding,
        qr_x + QR_SIZE + padding,
        qr_y + QR_SIZE + padding
    )

    add_shadow(
        canvas,
        card,
        radius=35,
        offset=(0, 10)
    )

    draw = ImageDraw.Draw(
        canvas
    )

    draw.rounded_rectangle(
        card,
        radius=35,
        fill=WHITE
    )

    canvas.alpha_composite(
        qr,
        (qr_x, qr_y)
    )


# ============================================================
# FOOTER
# ============================================================

def add_footer(
    canvas,
    url,
    font_regular
):

    draw = ImageDraw.Draw(
        canvas
    )

    footer_y = (
        HEIGHT - FOOTER_HEIGHT
    )

    draw.rectangle(
        (
            0,
            footer_y,
            WIDTH,
            footer_y + 3
        ),
        fill=TEXT_COLOR
    )

    display_url = url

    for prefix in (
        "https://",
        "http://"
    ):
        if display_url.startswith(prefix):
            display_url = display_url[
                len(prefix):
            ]

    display_url = display_url.rstrip(
        "/"
    )

    font = fit_font(
        draw,
        display_url,
        font_regular,
        max_size=27,
        max_width=950,
        min_size=18
    )

    bbox = draw.textbbox(
        (0, 0),
        display_url,
        font=font
    )

    text_width = (
        bbox[2] - bbox[0]
    )

    text_height = (
        bbox[3] - bbox[1]
    )

    x = (
        WIDTH - text_width
    ) // 2

    y = (
        footer_y
        + (FOOTER_HEIGHT - text_height)
        // 2
        - bbox[1]
    )

    draw.text(
        (x, y),
        display_url,
        font=font,
        fill=TEXT_COLOR
    )


# ============================================================
# GÉNÉRATION
# ============================================================

def generate(args):

    font_regular, font_bold = resolve_fonts(
        args.font
    )

    # --------------------------------------------------------
    # Photo
    # --------------------------------------------------------

    photo = select_photo(
        photo=args.photo,
        photos_dir=args.photos
    )

    # --------------------------------------------------------
    # Canvas
    # --------------------------------------------------------

    canvas = Image.new(
        "RGBA",
        (WIDTH, HEIGHT),
        CONTENT_BG
    )

    draw = ImageDraw.Draw(
        canvas
    )

    # --------------------------------------------------------
    # Header
    # --------------------------------------------------------

    draw.rectangle(
        (
            0,
            0,
            WIDTH,
            HEADER_HEIGHT
        ),
        fill=HEADER_BG
    )

    # --------------------------------------------------------
    # Photo
    # --------------------------------------------------------

    add_background_photo(
        canvas,
        photo
    )

    # --------------------------------------------------------
    # Logo
    # --------------------------------------------------------

    add_logo(
        canvas,
        args.logo,
        font_bold
    )

    # --------------------------------------------------------
    # Titre
    # --------------------------------------------------------

    add_title(
        canvas,
        args.title,
        font_bold
    )

    # --------------------------------------------------------
    # Distance / D+
    # --------------------------------------------------------

    add_metrics(
        canvas,
        args.distance,
        args.dplus,
        font_bold
    )

    # --------------------------------------------------------
    # QR
    # --------------------------------------------------------

    add_qr(
        canvas,
        args.url
    )

    # --------------------------------------------------------
    # Footer
    # --------------------------------------------------------

    add_footer(
        canvas,
        args.url,
        font_regular
    )

    # --------------------------------------------------------
    # Export
    # --------------------------------------------------------

    output = Path(
        args.output
    )

    # PNG si demandé
    if output.suffix.lower() == ".png":

        canvas.save(
            output,
            "PNG",
            optimize=True
        )

    else:

        canvas.convert("RGB").save(
            output,
            "JPEG",
            quality=95,
            optimize=True
        )

    print()
    print("======================================")
    print(" Publication générée")
    print("======================================")
    print(f"Fichier : {output}")
    print(f"Taille  : {WIDTH}x{HEIGHT}")
    print(f"URL QR  : {args.url}")

    if photo:
        print(f"Photo   : {photo}")

    print()


# ============================================================
# CLI
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description=(
            "Générateur de publications "
            "Instagram Cyclo Explore"
        )
    )

    # URL obligatoire
    parser.add_argument(
        "url",
        help="URL encodée dans le QR code"
    )

    parser.add_argument(
        "--title",
        default="",
        help="Nom du parcours"
    )

    parser.add_argument(
        "--distance",
        default="",
        help="Distance, ex: 86 km"
    )

    parser.add_argument(
        "--dplus",
        default="",
        help="D+, ex: 1250 m"
    )

    # Une seule photo
    parser.add_argument(
        "--photo",
        default=None,
        help="Utiliser une photo précise"
    )

    # OU un dossier de photos
    parser.add_argument(
        "--photos",
        default=None,
        help=(
            "Dossier contenant les photos "
            "du parcours"
        )
    )

    # Logo
    parser.add_argument(
        "--logo",
        default=None,
        help="Logo Cyclo Explore"
    )

    # Police
    parser.add_argument(
        "--font",
        default=None,
        help="Fichier TTF/OTF de police"
    )

    # Sortie : accepte --output ET -o
    parser.add_argument(
        "-o",
        "--output",
        default="cyclo_explore_instagram.jpg",
        help="Fichier de sortie"
    )

    args = parser.parse_args()

    # Vérification
    if args.photo and args.photos:
        parser.error(
            "--photo et --photos ne peuvent "
            "pas être utilisés simultanément."
        )

    generate(args)


if __name__ == "__main__":
    main()
