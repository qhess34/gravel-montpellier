#!/usr/bin/env python3
"""
Ajoute (ou met à jour) une sortie en enchaînant tous les scripts utiles,
dans le bon ordre, avec un récapitulatif à la fin :

  1. dossier   crée rides/<slug>/, copie le GPX et les photos fournis,
               prépare description.md (frontmatter + plan du texte) s'il
               n'existe pas ;
  2. contrôle  vérifie description.md (titre, synthèse, « ## Le parcours »,
               difficulté), le GPX (points, altitudes) et les photos ;
  3. poi       points d'eau, boulangeries… le long de la trace
               (tools/find_supplies.py — interactif, réseau) ;
  4. surface   part route / chemin (tools/surface_stats.py — réseau) ;
  5. pentes    trace colorisée selon la pente (tools/slope_colors.py) ;
  6. instagram visuels Instagram post + story (tools/make_instagram_image.py) ;
  7. qrcode    visuel QR code (tools/generate_qrcode.py) ;
  8. site      génère le site en local pour vérifier la fiche (go run).

Usage :
    # nouvelle sortie à partir d'un GPX et de photos
    python3 tools/new_ride.py tour-du-pic --gpx ~/Téléchargements/trace.gpx --photos ~/Photos/pic/

    # sortie existante : relancer toutes les étapes
    python3 tools/new_ride.py rides/clapiers-corconne

    # sans question ni accès réseau (POI et revêtement sautés)
    python3 tools/new_ride.py rides/clapiers-corconne --yes --no-network

    # seulement certaines étapes / en sauter
    python3 tools/new_ride.py rides/clapiers-corconne --only pentes,instagram,qrcode
    python3 tools/new_ride.py rides/clapiers-corconne --skip poi,surface

Les étapes 6 et 7 nécessitent Pillow et segno (pip install -r tools/requirements.txt) ;
l'étape 8 nécessite Go. Une étape impossible est signalée et sautée, sans
bloquer les suivantes.
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import date

TOOLS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TOOLS)
STEPS = ["dossier", "controle", "poi", "surface", "pentes", "instagram", "qrcode", "site"]
NETWORK_STEPS = {"poi", "surface"}
PHOTO_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif")
DIFFICULTIES = ["Facile", "Moyenne", "Difficile", "Très difficile"]

GREEN, YELLOW, RED, DIM, BOLD, RESET = ("\033[32m", "\033[33m", "\033[31m", "\033[2m", "\033[1m", "\033[0m") \
    if sys.stdout.isatty() else ("",) * 6


def say(symbol, color, text):
    print(f"{color}{symbol}{RESET} {text}")


def title(n, name, text):
    print(f"\n{BOLD}[{n}/{len(STEPS)}] {name} — {text}{RESET}")


def ask(question, default="", yes=False):
    if yes:
        return default
    suffix = f" [{default}]" if default else ""
    try:
        answer = input(f"  {question}{suffix} : ").strip()
    except EOFError:
        return default
    return answer or default


def run(cmd, interactive=False):
    """Lance une commande (sortie affichée en direct). Renvoie le code retour."""
    print(f"  {DIM}$ {' '.join(cmd)}{RESET}")
    try:
        return subprocess.run(cmd, cwd=REPO, stdin=None if interactive else subprocess.DEVNULL).returncode
    except FileNotFoundError as e:
        print(f"  {e}")
        return 127


def has_module(name):
    try:
        __import__(name)
        return True
    except ImportError:
        return False


def resolve_ride_dir(arg):
    """« slug », « rides/slug » ou chemin absolu -> chemin du dossier."""
    if os.path.isabs(arg) or os.sep in arg.strip(os.sep) or arg.startswith("rides"):
        return os.path.normpath(os.path.join(REPO, arg) if not os.path.isabs(arg) else arg)
    return os.path.join(REPO, "rides", arg)


def slugify(text):
    text = text.lower()
    for a, b in (("àâä", "a"), ("éèêë", "e"), ("îï", "i"), ("ôö", "o"), ("ùûü", "u"), ("ç", "c")):
        for c in a:
            text = text.replace(c, b)
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


# --- 1. Dossier ------------------------------------------------------------------

DESCRIPTION_TEMPLATE = """---
title: {title}
date: {date}
difficulty: {difficulty}
departure: {departure}
tags: {tags}
---

{summary}

## Le parcours

Décrivez ici l'itinéraire, étape par étape : routes et chemins empruntés,
villages traversés, difficultés, points de vue, ravitaillements…
"""

SUMMARY_PLACEHOLDER = "Résumé de la sortie en deux ou trois phrases : c'est ce texte qui apparaît dans la popup de la carte d'accueil, sur le cartouche et dans les aperçus de partage."


def step_folder(ride_dir, args):
    os.makedirs(os.path.join(ride_dir, "photos"), exist_ok=True)
    report = []

    if args.gpx:
        if not os.path.isfile(args.gpx):
            raise RuntimeError(f"GPX introuvable : {args.gpx}")
        existing = [n for n in os.listdir(ride_dir) if n.lower().endswith(".gpx")]
        dst = os.path.join(ride_dir, os.path.basename(args.gpx))
        for n in existing:
            if n != os.path.basename(args.gpx):
                say("⚠", YELLOW, f"un autre GPX est déjà présent ({n}) : le site prend le premier par ordre alphabétique")
        shutil.copy2(args.gpx, dst)
        report.append(f"GPX copié : {os.path.basename(dst)}")

    copied = 0
    for src in args.photos or []:
        files = [os.path.join(src, n) for n in sorted(os.listdir(src))] if os.path.isdir(src) else [src]
        for f in files:
            if os.path.isfile(f) and f.lower().endswith(PHOTO_EXTS):
                shutil.copy2(f, os.path.join(ride_dir, "photos", os.path.basename(f)))
                copied += 1
    if copied:
        report.append(f"{copied} photo(s) copiée(s) dans photos/ (la 1re par ordre alphabétique sert de couverture)")

    desc = os.path.join(ride_dir, "description.md")
    if not os.path.exists(desc):
        print("  Nouvelle sortie : quelques informations pour préparer description.md")
        slug = os.path.basename(ride_dir)
        t = args.title or ask("Titre", slug.replace("-", " ").capitalize(), args.yes)
        diff = args.difficulty or ask("Difficulté (" + " / ".join(DIFFICULTIES) + ")", "Moyenne", args.yes)
        dep = args.departure or ask("Lieu de départ", "", args.yes)
        tags = args.tags or ask("Tags (séparés par des virgules, ex : gravel, 1 jour, vues panoramiques)", "gravel, 1 jour", args.yes)
        d = args.date or ask("Date (AAAA-MM-JJ ou JJ/MM/AAAA)", date.today().isoformat(), args.yes)
        with open(desc, "w", encoding="utf-8") as f:
            f.write(DESCRIPTION_TEMPLATE.format(title=t, date=d, difficulty=diff, departure=dep, tags=tags,
                                                summary=SUMMARY_PLACEHOLDER))
        report.append("description.md créé : complétez la synthèse et « ## Le parcours »")
    for line in report or ["rien à créer : dossier déjà prêt"]:
        say("✓", GREEN, line)
    return "ok"


# --- 2. Contrôle ---------------------------------------------------------------------

def step_check(ride_dir, args):
    sys.path.insert(0, TOOLS)
    import brand  # lecture des sorties partagée avec les générateurs d'images (Pillow requis)
    warnings = 0

    desc = os.path.join(ride_dir, "description.md")
    if not os.path.exists(desc):
        raise RuntimeError("description.md manquant (obligatoire)")
    fields, body = brand.parse_description(desc)
    checks = [
        (bool(fields.get("title")), "titre (title)"),
        (bool(fields.get("date")), "date"),
        (bool(brand.difficulty_key(fields.get("difficulty", ""))), f"difficulté reconnue ({fields.get('difficulty', '—')} ; attendu : " + ", ".join(DIFFICULTIES) + ")"),
        (bool(fields.get("departure")), "lieu de départ (departure)"),
        (bool(fields.get("tags")), "tags"),
        (re.search(r"(?mi)^##[ \t]+Le parcours", body) is not None, "titre « ## Le parcours » (délimite la synthèse)"),
        (SUMMARY_PLACEHOLDER not in body and bool(brand.summary_text(body)), "synthèse rédigée (texte avant « ## Le parcours »)"),
    ]
    for ok, label in checks:
        say("✓" if ok else "⚠", GREEN if ok else YELLOW, label)
        warnings += not ok

    gpx = [n for n in sorted(os.listdir(ride_dir)) if n.lower().endswith(".gpx")]
    if not gpx:
        say("⚠", YELLOW, "aucun GPX : pas de carte, de profil ni de colorisation des pentes")
        warnings += 1
    else:
        track = brand.load_track(os.path.join(ride_dir, gpx[0]))
        with_ele = sum(1 for p in track if p[2] is not None)
        if len(track) < 2:
            say("✗", RED, f"{gpx[0]} : moins de deux points de trace")
            warnings += 1
        else:
            say("✓", GREEN, f"{gpx[0]} : {len(track)} points, {track[-1][3]:.1f} km, altitude sur {with_ele * 100 // len(track)} % des points")
            if with_ele < len(track) / 2:
                say("⚠", YELLOW, "altitudes insuffisantes : pentes et profil seront incomplets")
                warnings += 1
        if len(gpx) > 1:
            say("⚠", YELLOW, f"{len(gpx)} fichiers GPX : seul {gpx[0]} est utilisé")
            warnings += 1

    photos = brand.photos_of(ride_dir)
    say("✓" if photos else "⚠", GREEN if photos else YELLOW,
        f"{len(photos)} photo(s)" + (f", couverture : {os.path.basename(photos[0])}" if photos else " : ajoutez-en dans photos/"))
    warnings += not photos
    return "ok" if not warnings else f"{warnings} point(s) à revoir"


# --- 3 à 8 ------------------------------------------------------------------------------

def step_script(cmd, interactive=False):
    def _run(ride_dir, args):
        code = run([sys.executable, os.path.join(TOOLS, cmd[0])] + [a.replace("{ride}", ride_dir) for a in cmd[1:]],
                   interactive=interactive)
        if code != 0:
            raise RuntimeError(f"{cmd[0]} a échoué (code {code})")
        return "ok"
    return _run


def step_instagram(ride_dir, args):
    for fmt in ("post", "story"):
        code = run([sys.executable, os.path.join(TOOLS, "make_instagram_image.py"), ride_dir, "--format", fmt,
                    "--site-url", args.site_url])
        if code != 0:
            raise RuntimeError("make_instagram_image.py a échoué")
    return "instagram.jpg + instagram-story.jpg"


def step_qrcode(ride_dir, args):
    code = run([sys.executable, os.path.join(TOOLS, "generate_qrcode.py"), ride_dir, "--site-url", args.site_url])
    if code != 0:
        raise RuntimeError("generate_qrcode.py a échoué")
    return "qrcode.jpg"


def step_site(ride_dir, args):
    if not shutil.which("go"):
        raise SkipStep("Go non installé (https://go.dev/dl/) — la CI génèrera le site au push")
    out = args.out or tempfile.mkdtemp(prefix="cycloexplore-")
    code = run(["go", "run", "./cmd/generator", "-out", out, "-umami-id", ""])
    if code != 0:
        raise RuntimeError("la génération du site a échoué")
    page = os.path.join(out, "rides", os.path.basename(ride_dir), "index.html")
    if not os.path.exists(page):
        raise RuntimeError("la fiche n'a pas été générée (description.md présent ?)")
    print(f"  Aperçu : python3 -m http.server --directory {out} 8080  →  http://localhost:8080/rides/{os.path.basename(ride_dir)}/")
    return f"fiche générée dans {out}"


class SkipStep(Exception):
    pass


def main():
    p = argparse.ArgumentParser(description="Ajoute ou met à jour une sortie en lançant tous les scripts nécessaires.",
                                formatter_class=argparse.RawDescriptionHelpFormatter, epilog="Étapes : " + ", ".join(STEPS))
    p.add_argument("ride", help="slug (ex: tour-du-pic) ou dossier (ex: rides/tour-du-pic)")
    p.add_argument("--gpx", help="fichier GPX à copier dans la sortie")
    p.add_argument("--photos", nargs="+", help="photos ou dossiers de photos à copier dans photos/")
    p.add_argument("--title", help="titre (nouvelle sortie)")
    p.add_argument("--date", help="date (nouvelle sortie)")
    p.add_argument("--difficulty", help="difficulté (nouvelle sortie)")
    p.add_argument("--departure", help="lieu de départ (nouvelle sortie)")
    p.add_argument("--tags", help="tags séparés par des virgules (nouvelle sortie)")
    p.add_argument("--only", help="étapes à lancer, séparées par des virgules")
    p.add_argument("--skip", help="étapes à sauter, séparées par des virgules")
    p.add_argument("--yes", "-y", action="store_true", help="aucune question (valeurs par défaut ; saute l'étape poi, interactive)")
    p.add_argument("--no-network", action="store_true", help="saute les étapes qui interrogent OpenStreetMap (poi, surface)")
    p.add_argument("--site-url", default="https://montpellier.cycloexplore.fr", help="URL publique du site")
    p.add_argument("--out", help="dossier de génération du site pour l'étape « site » (défaut : dossier temporaire)")
    args = p.parse_args()

    ride_dir = resolve_ride_dir(args.ride)
    if os.path.basename(ride_dir) != slugify(os.path.basename(ride_dir)):
        sys.exit(f"✗ nom de dossier « {os.path.basename(ride_dir)} » : utilisez un slug sans espace ni accent, ex : {slugify(os.path.basename(ride_dir))}")
    os.chdir(REPO)

    def parse_list(v):
        items = [s.strip() for s in (v or "").split(",") if s.strip()]
        unknown = [s for s in items if s not in STEPS]
        if unknown:
            sys.exit(f"✗ étape(s) inconnue(s) : {', '.join(unknown)} (attendu : {', '.join(STEPS)})")
        return items

    only, skip = parse_list(args.only), set(parse_list(args.skip))
    if args.no_network:
        skip |= NETWORK_STEPS
    if args.yes and "poi" not in only:
        skip.add("poi")
    if not os.path.isdir(ride_dir) and only and "dossier" not in only:
        sys.exit(f"✗ {ride_dir} n'existe pas (lancez sans --only pour le créer)")

    has_pillow, has_segno = has_module("PIL"), has_module("segno")
    actions = {
        "dossier": ("préparation du dossier", step_folder),
        "controle": ("vérification du contenu", step_check),
        "poi": ("points d'intérêt (OpenStreetMap, interactif)", step_script(["find_supplies.py", "{ride}"], interactive=True)),
        "surface": ("revêtement route / chemin (OpenStreetMap)", step_script(["surface_stats.py", "{ride}"])),
        "pentes": ("colorisation des pentes", step_script(["slope_colors.py", "{ride}"])),
        "instagram": ("visuels Instagram", step_instagram),
        "qrcode": ("visuel QR code", step_qrcode),
        "site": ("génération du site", step_site),
    }
    needs = {"controle": has_pillow, "instagram": has_pillow, "qrcode": has_pillow and has_segno}

    print(f"{BOLD}Sortie : {os.path.relpath(ride_dir, REPO)}{RESET}")
    results = []
    failed = False
    for i, name in enumerate(STEPS, 1):
        label, fn = actions[name]
        if (only and name not in only) or name in skip:
            results.append((name, "sautée", DIM))
            continue
        title(i, name, label)
        if name in needs and not needs[name]:
            say("·", YELLOW, "Pillow / segno manquants : pip install -r tools/requirements.txt")
            results.append((name, "sautée (dépendance manquante)", YELLOW))
            continue
        try:
            status = fn(ride_dir, args)
            results.append((name, status, GREEN if status == "ok" or not status.split()[0].isdigit() else YELLOW))
        except SkipStep as e:
            say("·", YELLOW, str(e))
            results.append((name, f"sautée ({e})", YELLOW))
        except (RuntimeError, OSError, ValueError) as e:
            say("✗", RED, str(e))
            results.append((name, f"échec : {e}", RED))
            failed = True
            if name == "dossier":
                break

    print(f"\n{BOLD}Récapitulatif{RESET}")
    for name, status, color in results:
        print(f"  {color}{name:10s}{RESET} {status}")
    rel = os.path.relpath(ride_dir, REPO)
    print(f"\n{BOLD}Ensuite{RESET}\n  relisez {rel}/description.md, puis :\n"
          f"  git add {rel} && git commit -m \"Ajoute la sortie {os.path.basename(ride_dir)}\" && git push")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
