# Guide du développeur

Ce document s'adresse à qui veut **reprendre ou faire évoluer le code** du
site Cyclo Explore. Le [README](../README.md) reste la référence pour
*utiliser* le site, c'est-à-dire ajouter une sortie, renseigner `points.md`
ou lancer les scripts. Ici, on explique comment le code est organisé, par
où passent les données et où intervenir pour chaque type de changement.

---

## 1. Vue d'ensemble

Le projet est un **générateur de site statique** écrit en Go, auquel
s'ajoutent quelques scripts Python lancés à la main :

```
rides/<slug>/               ← contenu (un dossier par sortie)
  description.md, *.gpx, photos/, points.md
  slope.geojson             ← produit par tools/slope_colors.py
        │
        ▼
go run ./cmd/generator      ← internal/site : lecture, calculs, gabarits
        │
        ▼
public/                     ← site statique (HTML, CSS, JS, photos, GPX)
        │
        ▼
GitHub Actions → GitHub Pages (à chaque push sur main)
```

Principes à respecter :

- **Aucune dépendance Go externe.** Seule la bibliothèque standard est
  utilisée (`html/template`, `encoding/xml`, `image/jpeg`…). `go.mod` ne
  liste aucun module ; garder ce cap simplifie la CI et Docker.
- **Front sans build.** Le site n'a ni bundler ni npm : un seul
  `script.js` en JavaScript « vanilla » et un seul `style.css`, embarqués
  dans le binaire (`go:embed`). La seule bibliothèque externe est
  **Leaflet 1.9.4**, chargée depuis unpkg.
- **Ne jamais inventer de données.** Ce qui n'est pas dans les fichiers
  d'une sortie n'est pas affiché : pas de distance devinée, de POI fictif
  ou de photo de remplacement.
- **Contenu et code séparés.** La personne qui publie les sorties ne
  touche qu'à `rides/` et `content/`. Le reste est du code.
- **Français partout** : interface, messages du générateur, commentaires
  du code et messages de commit.

---

## 2. Démarrer

Prérequis : Go 1.22 ou plus et Python 3.8 ou plus. Pillow et segno ne
servent qu'aux visuels Instagram et QR code.

```bash
# générer le site dans ./public
go run ./cmd/generator

# le servir localement (n'importe quel serveur statique convient)
python3 -m http.server -d public 8080      # → http://localhost:8080

# ou avec Docker (voir le README) :
docker compose up serve      # terminal 1
docker compose run --rm generate   # terminal 2, après chaque modification
```

Options du générateur (`go run ./cmd/generator -h`) : `-rides`,
`-footer`, `-legal`, `-out`, `-title`, `-site-url`, `-umami-id` (une
valeur vide désactive les statistiques) et `-version`.

> **Accès réseau pendant le build.** Le générateur interroge l'API
> Panoramax pour les points 360° dont les coordonnées ne sont pas
> indiquées dans `points.md` (`internal/site/panoramax.go`). Sans réseau,
> ces points sont ignorés avec un avertissement et le build réussit quand
> même.

---

## 3. Arborescence commentée

```
cmd/generator/main.go        point d'entrée : lit les options, appelle site.Build
internal/site/
  build.go                   orchestration : Build() → pages, copie des assets, sitemap
  types.go                   structures centrales : GPXPoint, Ride, POIKind, Site
  rides.go                   LoadRides / loadOneRide : lecture d'un dossier de sortie
  frontmatter.go             en-tête « clé: valeur » de description.md
  markdown.go                mini-moteur Markdown (titres, listes, gras, liens)
  meta.go                    synthèse, difficulté, durée, tri des dates, couleur des traces
  gpx.go                     lecture GPX, distances (haversine), D+, simplification
  points.go                  lecture de points.md (POI, photos, Panoramax), PK des points
  exif.go                    GPS et orientation EXIF des JPEG (lecteur maison)
  images.go                  réduction des photos (1024 px) et miniatures (640 px)
  panoramax.go               coordonnées d'une photo Panoramax via son API
  slope.go                   lecture et contrôle de fraîcheur de slope.geojson
  profile.go                 profil altimétrique en SVG, généré au build
  homemap.go                 JSON des traces simplifiées pour la carte d'accueil
  seo.go                     sitemap.xml, robots.txt, données structurées JSON-LD
  waytype.go                 classification OSM des voies (non appelé, voir § 9)
  assets.go                  go:embed des gabarits et du dossier static/
  templates/                 gabarits html/template (base, index, ride, legal, 404, partials)
  static/                    script.js, style.css, logos
  *_test.go                  tests Go
content/                     footer.md et mentions-legales.md (Markdown)
rides/                       les sorties
tools/                       scripts Python (pentes, POI, revêtement, visuels, new_ride)
.github/workflows/deploy.yml CI : tests, pentes, build, déploiement Pages
Dockerfile, docker-compose.yml
```

---

## 4. Le générateur Go, étape par étape

`site.Build(opts)` (`build.go`) enchaîne les étapes suivantes :

1. **Vider `public/`** sans supprimer le dossier lui-même (`cleanDir`), afin
   de ne pas casser le montage de `docker compose up serve`.
2. **Charger le pied de page et les mentions légales**, convertis avec le
   Markdown maison.
3. **Charger les sorties** (`LoadRides` dans `rides.go`). Pour chaque
   sous-dossier contenant un `description.md` :
   - en-tête (`ParseFrontMatter`), puis synthèse et description
     (`splitSummary` coupe au titre `## Le parcours`) ;
   - premier `.gpx` trouvé : distance, D+, départ et arrivée, trace
     simplifiée ;
   - `photos/` : liste triée, publiée par `publishPhoto` (redimensionnement
     et rotation EXIF) ;
   - `points.md` : `LoadPoints`, puis calcul du PK de chaque point par
     rapport à la trace (`NearestKm`). Au-delà de 3 km de la trace
     (`maxPointToTrackKm`), un point est classé « hors parcours » ;
   - `slope.geojson` : `loadSlopeData` vérifie l'empreinte SHA-256 du GPX.
     Si le fichier est périmé, il est ignoré et la trace est affichée en
     couleur unie ;
   - profil altimétrique : `buildElevationProfile`, puis
     `renderElevationProfileSVG`.

   Les sorties sont ensuite triées par date décroissante, et
   `assignColors` leur attribue une couleur stable (hash du slug dans
   `ridePalette`).
4. **Copier `static/`** et écrire `CNAME` (déduit de `-site-url`).
5. **Rendre les pages** : `mentions-legales.html`,
   `rides/<slug>/index.html`, `index.html` et `404.html`. Chaque page est
   rendue avec `base.html`, la page elle-même et `partials.html`
   (`parsePage`), à partir d'une même structure `pageData`.
6. **Écrire `robots.txt` et `sitemap.xml`** (`seo.go`).

### Gabarits

- `base.html` définit `base` : `<head>`, en-tête, pied de page, Leaflet,
  `script.js`. Chaque page définit `head` (facultatif) et `content`.
- `partials.html` : blocs partagés, par exemple `ride-facts` (les chiffres
  clés d'une sortie).
- Les fonctions disponibles dans les gabarits sont déclarées dans
  `templateFuncs` (`build.go`).
- **Échappement** : `html/template` échappe selon le contexte, y compris à
  l'intérieur des `<script>`. Les données volumineuses passées au JS
  (traces, profil, pentes) sont produites en Go sous forme de
  `template.JS` à partir de `json.Marshal`, ce qui est sûr. N'utilisez
  jamais `template.HTML` ou `template.JS` sur du texte qui n'a pas été
  échappé.

### Ajouter un champ dans `description.md`

1. Ajouter le champ à `Ride` (`types.go`).
2. Le lire dans `loadOneRide` (`rides.go`), à partir de la map `fields`
   renvoyée par `ParseFrontMatter`. `parseFloatField` sert pour les
   nombres.
3. L'afficher dans `ride.html` et/ou `partials.html`.
4. Le documenter dans la section `description.md` du README.
5. Si les visuels doivent l'utiliser, le lire aussi dans
   `tools/brand.py` (`load_ride`).

---

## 5. Le front (`static/script.js`, `static/style.css`)

### JavaScript

Tout le code tient dans une IIFE. Les fonctions appelées depuis les
gabarits sont exposées sous `window.gm*` ; le préfixe `gm` évite les
collisions. Le fichier est organisé en sections marquées
`// --- Titre ---` :

| Section / fonction | Rôle |
|---|---|
| `openModal`, `gmOpenPhoto` | fenêtre modale (photo en grand) |
| `gmOpenPanoramax`, `gmFindNearestPanoramax`, `gmHandleTrackClick` | visionneuse 360° en iframe, recherche de la vue la plus proche d'un clic sur la trace |
| `gmPoiPopup`, `gmIcon` | popups et marqueurs (`L.divIcon` stylé par la classe CSS `gm-marker--<type>`) |
| `gmInitProfileHover` | survol synchronisé entre profil SVG et carte (PK, altitude, pente) |
| `gmInitPOIFilter`, `gmInitPOIList` | filtre par type de POI, liste des POI reliée à la carte |
| `GM_BASEMAPS`, `gmInitBasemaps` | fonds de carte et menu de choix (mémorisé dans `localStorage`) |
| `gmInitFullscreen` | plein écran (API native, repli CSS pour iPhone) |
| `gmInitLocateMe` | bouton « me localiser » |
| `gmLoadRideTrack` | charge `slope.geojson` (ou le GPX en repli) et cadre la carte |
| `initCarousel` | carrousel de photos de la fiche |
| `initHomeMap` et suivants | carte d'accueil, popups, filtres, rail de cartouches |

La fiche (`ride.html`) se termine par un script en ligne qui crée la carte
et appelle ces fonctions dans l'ordre. C'est le meilleur point d'entrée
pour comprendre l'assemblage.

Les données circulent ainsi :
- **Accueil** : les traces simplifiées (300 points au plus) sont
  intégrées à la page en JSON (`homemap.go`). Aucun GPX n'est téléchargé.
- **Fiche** : un seul fichier de trace est chargé (`slope.geojson`, ou le
  GPX en repli). Le profil est déjà en SVG ; ses échelles sont exposées
  en attributs `data-*` pour le JS.

### CSS

- Les couleurs de la charte sont des variables sur `:root` (`--cream`,
  `--ink`, `--terracotta`, `--olive`…, plus `--pano` pour Panoramax).
- **Piège Leaflet** : `leaflet.css` est chargé *après* `style.css` et
  l'emporte à spécificité égale. Les règles qui restylent les contrôles
  Leaflet sont donc préfixées par `body` (`body .leaflet-container
  .leaflet-bar …`).
- Le site est pensé mobile d'abord : vérifier chaque changement à environ
  375 px de large.

---

## 6. Scripts Python (`tools/`)

| Script | Dépendances | Réseau | Rôle |
|---|---|---|---|
| `slope_colors.py` | bibliothèque standard | non | écrit `slope.geojson` (tronçons colorés selon la pente, empreinte du GPX). **Relancé par la CI** avant le build. |
| `find_supplies.py` | bibliothèque standard | Overpass (OSM) | propose des POI utiles près de la trace, en interactif, et les ajoute à `points.md` |
| `surface_stats.py` | bibliothèque standard | Overpass (OSM) | estime les km revêtus et non revêtus, écrit dans `description.md` |
| `brand.py` | Pillow | tuiles de carte | charte partagée par les visuels : couleurs, polices, lecture d'une sortie, profil, trace, fond de carte |
| `make_instagram_image.py` | Pillow | tuiles de carte | visuel Instagram (post, story, carré) |
| `generate_qrcode.py` | Pillow, segno | non | QR code stylé et visuel d'affiche |
| `new_ride.py` | (selon les étapes) | (selon les étapes) | enchaîne tous les scripts pour une nouvelle sortie |

Points d'attention :

- **Les couleurs de pente** sont définies dans `SLOPE_CLASSES`
  (`slope_colors.py`) et recopiées dans chaque `slope.geojson`. Le site
  (Go et JS) les lit dans le fichier ; aucune couleur de pente n'est codée
  côté site. Après un changement de seuils ou de couleurs, relancer
  `python3 tools/slope_colors.py --force`.
- **La charte des visuels** (`brand.py` : `CREAM`, `TERRACOTTA`,
  `DIFFICULTY_COLORS`…) duplique les variables CSS et les couleurs de
  difficulté de `style.css` (`.diff-dot--*`). Si l'une change, mettre
  l'autre à jour.
- **La logique « durée » et « difficulté »** existe en Go (`meta.go`) et
  en Python (`brand.py`), et doit donner le même résultat (voir les tests
  `test_duration_same_rules_as_site`).
- **Les fonds de carte** des visuels (`TILE_PROVIDERS`) et du site
  (`GM_BASEMAPS`) sont gratuits et sans clé, mais soumis aux règles
  d'usage de chaque fournisseur. Toujours afficher l'attribution ; ne
  jamais télécharger de tuiles en masse. Les tuiles des visuels sont
  mises en cache dans `~/.cache/cycloexplore/tiles`.
- Les scripts qui modifient des fichiers de contenu (`find_supplies`,
  `surface_stats`) proposent `--dry-run`. Utilisez-le pour tester.

---

## 7. Tests et vérifications

```bash
go vet ./... && go test ./...                           # générateur Go
python3 -m unittest discover -s tools -p "test_*.py"    # scripts Python
python3 tools/slope_colors.py --check                   # slope.geojson à jour ?
node --check internal/site/static/script.js             # syntaxe JS (si Node est installé)
```

- `meta_test.go` couvre la synthèse, la difficulté, la durée, le tri des
  dates, les couleurs, la réduction des photos, `slope.geojson` et le
  chargement des vraies sorties de `rides/`.
- `seo_test.go` génère le site complet dans un dossier temporaire et
  vérifie les métadonnées (titres, Open Graph, JSON-LD, sitemap).
- `tools/test_*.py` : pentes, charte et visuels. Les tests des visuels sont
  ignorés si Pillow ou segno ne sont pas installés.
- **Pas de tests navigateur dans le dépôt.** Pour une modification du
  front, générer le site et le vérifier à la main dans un navigateur
  (ordinateur et mobile), en particulier :
  - carte d'accueil : filtres, popups, défilement des cartouches ;
  - fiche : carte, profil et survol, POI, plein écran, fonds de carte,
    carrousel, Panoramax.

  Playwright fonctionne bien pour automatiser ces vérifications au
  besoin.

---

## 8. Intégration continue et déploiement

`.github/workflows/deploy.yml` se déclenche **uniquement sur un push sur
`main`** ou à la main (`workflow_dispatch`). Il n'y a **pas de CI sur les
pull requests** : lancez les tests localement avant de proposer une PR.

Étapes : `go vet`, `go test`, tests Python, `slope_colors.py` (régénère les
pentes), génération du site avec les variables de dépôt `SITE_URL` et
`UMAMI_ID`, puis publication sur GitHub Pages. Le SHA court du commit est
affiché en pied de page (`-version`).

Méthode de travail habituelle : une branche par sujet, un commit par
fonctionnalité, une PR vers `main`. Le merge déclenche le déploiement.

---

## 9. Recettes courantes

**Ajouter un type de POI** (par exemple `toilets`) :
1. Ajouter le type à `poiKindOrder` et `poiKindSingular` (`points.go`) :
   libellé du filtre et libellé d'un point isolé.
2. Ajouter le style du marqueur `.gm-marker--toilets` dans `style.css`
   (icône et couleur, sur le modèle des types existants).
3. Si `find_supplies.py` doit le proposer, ajouter la correspondance de
   tags OSM dans ce script.
4. Le documenter dans la table des icônes `points.md` du README.

**Ajouter un fond de carte au site** : ajouter une entrée à `GM_BASEMAPS`
(`script.js`) avec `key`, `label`, `hint`, `swatch` (aperçu CSS dans le
menu), `url` et `opts` (`maxZoom`, `attribution` **obligatoire**). Puis
compléter la table « Fonds de carte » du README. Vérifier la licence et
les règles d'usage du fournisseur.

**Ajouter un fond de carte aux visuels** : ajouter une entrée à
`TILE_PROVIDERS` (`brand.py`) avec `url`, `attribution` et `max_zoom` ;
l'option `--fond` de `make_instagram_image.py` la propose alors
automatiquement.

**Changer les seuils ou couleurs de pente** : modifier `SLOPE_CLASSES`
dans `slope_colors.py`, relancer `--force`, puis mettre à jour les tests
(`test_slope_colors.py`) et la section du README sur la colorisation.

**Modifier la palette des traces** : modifier `ridePalette` (`meta.go`).
Ajouter des couleurs ne change pas celles des sorties existantes tant que
leur couleur cible reste libre. En changer l'ordre ou en retirer, si.

**Ajouter une page** : créer `templates/<page>.html` (blocs `content` et,
si besoin, `head`), la rendre dans `Build` avec `parsePage` puis
`renderToFile`, et l'ajouter à `writeSitemap` si elle doit être indexée.

---

## 10. Pièges et dette connue

- **`waytype.go` n'est pas appelé** par le générateur. Le revêtement est
  calculé hors build par `tools/surface_stats.py`, qui écrit
  `surface_paved_km` et `surface_unpaved_km` dans `description.md`. Ce
  fichier reste comme base si l'on veut un jour déplacer ce calcul dans le
  build ; sinon il peut être supprimé.
- **`public/` est ignoré par git**, mais `public/static/style.css` a été
  commité par le passé. C'est un fichier généré : ne pas le modifier, il
  est écrasé à chaque build. Il peut être retiré avec
  `git rm --cached public/static/style.css`.
- **Markdown maison** (`markdown.go`) : seuls les titres `#` à `###`, les
  listes `-`, le gras, l'italique, les liens et les paragraphes sont pris
  en charge. Tableaux, images et code ne le sont pas. Étendre ce fichier
  plutôt que d'ajouter une dépendance.
- **Lecteur EXIF maison** (`exif.go`) : JPEG uniquement. Les photos
  exportées par les réseaux sociaux perdent souvent leurs coordonnées GPS.
- **Visuels générés non versionnés** : `instagram-*.jpg` et
  `qrcode.*` sont dans `.gitignore`, mais `rides/*/instagram.jpg` est
  versionné (le site affiche un bouton « Instagram » quand il existe). Le
  régénérer après une modification de la sortie.
- **iPhone et plein écran** : Safari iOS n'accepte pas `requestFullscreen`
  sur un `div`. `gmInitFullscreen` bascule alors sur une classe CSS
  (`gm-map-fullscreen`). Les fenêtres modales (photo, Panoramax) sont
  attachées à l'élément plein écran (`gmOverlayHost`), sinon elles
  resteraient invisibles derrière.
- **Leaflet et carte non initialisée** : n'appeler `map.getCenter()` et
  les fonctions voisines qu'après `map._loaded` (la vue est fixée de façon
  asynchrone par `gmLoadRideTrack`).
