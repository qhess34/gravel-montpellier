# Guide du développeur

Ce document s'adresse à qui veut **reprendre ou faire évoluer le code** du
site Cyclo Explore. Le [README](../README.md) reste la référence pour
*utiliser* le site, c'est-à-dire ajouter une sortie, renseigner `points.md`
ou lancer les scripts. Ici, on explique comment le code est organisé, par
où passent les données et où intervenir pour chaque type de changement.
La [section 11](#11-référence-détaillée-du-code) détaille les méthodes et
les calculs fonction par fonction.

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

---

## 11. Référence détaillée du code

Cette section décrit les méthodes et la logique fonction par fonction,
pour comprendre *comment* le site calcule ce qu'il affiche. Les noms
renvoient au code. En cas de doute, le commentaire au-dessus de chaque
fonction fait foi.

### 11.1 Lecture d'une sortie (`rides.go`)

`LoadRides(ridesDir)` :
- parcourt les sous-dossiers, en ignorant ceux qui commencent par `.` ;
- ignore avec un avertissement un dossier sans `description.md` ;
- appelle `loadOneRide` pour chaque sortie ;
- trie les sorties par `SortKey` décroissant (plus récentes en premier),
  puis par slug ;
- appelle enfin `assignColors`.

`loadOneRide(slug, dir, descPath)` construit un `Ride` dans cet ordre.

1. **En-tête** : `ParseFrontMatter` exige que le fichier commence par
   `---`. Il lit des paires `clé: valeur` jusqu'au `---` suivant et ignore
   en silence les lignes sans `:`. Le titre vaut le slug par défaut.
2. **Texte** : `splitSummary` coupe le corps en synthèse et description
   (voir 11.2). Les deux sont convertis par `Markdown`. La synthèse existe
   aussi en texte brut (`SummaryText`, via `markdownToPlainText`) pour les
   cartouches, les popups et la meta description.
3. **Chiffres** : `distance_km` et `elevation_m` de l'en-tête **priment**
   sur les valeurs calculées depuis le GPX. Celles-ci ne servent que si le
   champ est absent ou vaut 0.
4. **Revêtement** : `surface_paved_km` et `surface_unpaved_km` sont lus
   tels quels (écrits par `tools/surface_stats.py`). Les pourcentages sont
   arrondis de façon à ce que leur somme fasse exactement 100.
5. **Tags** : la liste séparée par des virgules est gardée telle quelle
   pour l'affichage. Une copie en minuscules (`TagsAttr`) sert au filtre
   de l'accueil, qui compare via l'attribut `data-tags`.
6. **Durée** : `rideDuration` (voir 11.2).
7. **GPX** :
   - le premier `.gpx` du dossier, par ordre alphabétique (`findFirstGPX`) ;
   - `ride.GPXPoints` est une version réduite à 800 points
     (`SimplifyForMap`) ;
   - la trace complète (`trackPoints`) sert aux calculs : distance, D+,
     PK et profil ;
   - `IsLoop` vaut vrai si le départ et l'arrivée sont à moins de 50 m.
8. **Pentes** : `loadSlopeData` (voir 11.4). Les tronçons sont aussi
   sérialisés en `SlopeJSON` pour le survol du profil.
9. **Photos** : tous les fichiers image de `photos/`, triés par nom. La
   **première photo** sert de couverture : vignette de l'accueil, image
   Open Graph et photo par défaut du visuel Instagram.
10. **Points** : `LoadPoints` lit `points.md` (voir 11.3). Ensuite, toute
    photo JPEG **non citée** dans `points.md` et dont les EXIF contiennent
    une position GPS devient automatiquement un point « photo ».
11. **PK** : pour chaque point, `NearestKm` cherche le **sommet de la trace
    le plus proche**, en distance à vol d'oiseau, sans projection sur le
    segment. Il renvoie la distance cumulée jusqu'à ce sommet et l'écart
    au point. Si l'écart est de 3 km au plus (`maxPointToTrackKm`), le
    point reçoit un PK (`HasKmMark`). Les POI avec PK vont dans
    `RoutePOIs`, triés par PK ; les autres vont dans `OffRoutePOIs`.
    Limite connue : sur une trace qui repasse au même endroit (aller-retour,
    boucle en 8), le PK retenu est celui du premier passage le plus proche.
12. **Profil** : `buildElevationProfile(track, 1000)` puis
    `renderElevationProfileSVG` (voir 11.5).

### 11.2 Métadonnées (`meta.go`)

- **`splitSummary`** cherche, sans tenir compte de la casse, un titre
  `## Le parcours`. La synthèse est tout ce qui précède. À défaut, elle
  s'arrête au premier titre Markdown précédé de texte. Sans aucun titre,
  c'est le premier paragraphe. Les lignes `---` sont retirées de la
  synthèse.
- **`normalizeDifficulty`** : minuscules, accents retirés, ponctuation
  remplacée par des espaces, puis comparaison à une liste d'alias. Par
  exemple « Modéré » donne `moyenne` et « Sportif » donne `difficile`.
  Chaque niveau a un ordre (`Level` 1 à 4) pour trier les boutons du
  filtre. Une valeur inconnue reste acceptée telle quelle, avec une clé
  dérivée du texte et rangée en fin de filtre.
- **`rideDuration`** :
  - le champ `duration` prime ;
  - sinon les tags de la forme « N jour(s) » sont extraits ;
  - un seul nombre donne « 2 jours » ; plusieurs donnent une plage
    (« 2 à 5 jours »).

  La même règle existe dans `tools/brand.py` (`duration_text`).
- **`dateSortKey`** :
  - formats acceptés : `AAAA-MM-JJ`, `JJ/MM/AAAA`, `J/M/AAAA`,
    `JJ-MM-AAAA`, `JJ.MM.AAAA` et les dates en toutes lettres
    (« 1er juin 2026 », accents facultatifs) ;
  - la date est normalisée en `AAAA-MM-JJ` pour le tri ;
  - un format non reconnu est gardé tel quel et trié comme du texte ;
  - seule une date ISO est publiée comme date structurée (`isISODate`).
- **`assignColors`** donne une couleur stable par sortie :
  1. les sorties sont traitées de la **plus ancienne à la plus récente** ;
  2. les couleurs imposées par le champ `color` (format `#rrggbb`) sont
     réservées d'abord ;
  3. pour chaque autre sortie, un hash FNV-32a du slug désigne une case de
     `ridePalette` (12 couleurs). Si elle est prise, on prend la suivante
     libre ; si toutes sont prises, la couleur du hash est réutilisée.

  Une sortie ajoutée plus tard ne peut donc pas « voler » la couleur d'une
  sortie existante.
- **`truncateText`** coupe sur une frontière de mot et ajoute « … ». Il
  sert aux résumés des popups (200 caractères) et à la meta description.

### 11.3 Points de carte (`points.go`, `exif.go`, `panoramax.go`)

- **`splitPointBlocks`** découpe `points.md` sur chaque ligne `---`.
  **`parseKeyValues`** lit les paires `clé: valeur` et retire les
  guillemets autour des valeurs. Une ligne commençant par `#` est un
  **commentaire** : c'est ainsi qu'on désactive un point sans le
  supprimer.
- **`buildPoint`** valide chaque bloc selon son `type` :
  - `poi` exige `lat`, `lon` et `label`. L'icône vaut `generic` par défaut ;
  - `photo` exige un `photo` présent dans `photos/`. Sans coordonnées, la
    position est lue dans les EXIF ; à défaut, le point est ignoré avec un
    avertissement (`errSkipPoint`) ;
  - `panoramax` exige `picture`. Sans coordonnées, elles sont demandées à
    l'API (`FetchPanoramaxLocation` : `GET <endpoint>/search?ids=<id>`) ; en
    cas d'échec, le point est ignoré.

  Toute autre erreur (type inconnu, champ obligatoire manquant, nombre
  invalide) **fait échouer le build**, avec le numéro du bloc.
- **`collectPOIKinds`** construit les boutons du filtre par type, dans
  l'ordre de `poiKindOrder`. Une icône hors liste garde son nom brut comme
  libellé. Le filtre n'est affiché que s'il y a au moins deux types.
- **`exif.go`** est un lecteur EXIF minimal :
  - il parcourt les segments JPEG jusqu'au bloc `APP1/Exif` ;
  - il lit l'en-tête TIFF, en petit ou grand boutisme ;
  - il suit le pointeur vers le sous-répertoire GPS ;
  - il convertit les rationnels degrés/minutes/secondes en degrés
    décimaux, avec le signe donné par les références N/S et E/O.

  `PhotoOrientation` lit le tag 0x0112. Chaque lecture renvoie `ok=false`
  au moindre décalage hors limites, sans paniquer.

### 11.4 Pentes : du GPX à `slope.geojson` (`tools/slope_colors.py`, `slope.go`)

Calcul côté Python, dans `build_segments` :
1. **Lecture des points** : `<trkpt>` ou, à défaut, `<rtept>`, avec leur
   altitude.
2. **Altitudes manquantes** (`fill_elevations`) : une altitude absente ou
   hors de [−450 m, 9000 m] est interpolée linéairement selon la distance.
   Si moins de 50 % des points ont une altitude valide, toute la trace
   passe en classe « Altitude indisponible ».
3. **Lissage** (`smooth_elevations`) : l'altitude est ré-échantillonnée
   tous les 10 m, puis on calcule une moyenne glissante sur 150 m. Près du
   départ et de l'arrivée, la fenêtre reste symétrique mais se réduit,
   pour ne pas aplatir artificiellement la pente. Le résultat est ramené
   aux points d'origine par interpolation.
4. **Découpage** (`split_segments`) : tronçons d'au moins 100 m qui se
   partagent leurs points d'extrémité. Un reliquat final de moins de 50 m
   est rattaché au dernier tronçon.
5. **Pente d'un tronçon** : (altitude lissée de fin − de début) ÷ longueur
   horizontale × 100. La classe est donnée par `classify` : chaque classe
   couvre un intervalle `[min, max[` de `SLOPE_CLASSES`.
6. **Fusion** : les tronçons consécutifs de même classe sont regroupés, sur
   1000 m au plus, et la pente est recalculée sur l'ensemble. Le rendu est
   identique mais le fichier bien plus léger.
7. **Écriture** : une `Feature` `LineString` par tronçon, avec dans ses
   propriétés `slope_pct`, `start_km`, `end_km`, `class`, `label` et
   `color`. À la racine du fichier : `source_sha256` (empreinte du GPX),
   `params_fingerprint` (empreinte des réglages), `format_version`,
   `legend` et `stats`.

**Fraîcheur du fichier.**
- Le script (`is_up_to_date`) considère le fichier à jour si trois
  éléments sont inchangés : l'empreinte du GPX, celle des réglages et
  `FORMAT_VERSION`. Changer un seuil ou une couleur rend donc tous les
  fichiers « obsolètes » pour `--check`.
- Le générateur Go (`loadSlopeData`) ne vérifie que l'**empreinte du
  GPX**. Un fichier périmé est ignoré : la trace s'affiche en couleur
  unie, avec un avertissement.
- La CI régénère toujours les pentes avant le build, donc le site publié
  est juste même si le dépôt contient des fichiers périmés.

Côté Go, la légende affichée sous le profil ne garde que les classes
**présentes** sur la trace. Les tronçons (`slopeSegment` : `s`, `e`, `c`,
`p`, `l`) servent à colorer le profil et à afficher la pente au survol.

### 11.5 Profil altimétrique (`profile.go`)

- **`buildElevationProfile`** :
  - calcule la distance cumulée sur la **trace complète** ;
  - si la trace dépasse 1000 points, en garde 1000 répartis à pas
    régulier (par indice) ;
  - chaque point garde son kilométrage réel, ce qui évite un profil
    « compressé ».
- **`renderElevationProfileSVG`** dessine un SVG de 800 × 170 unités, en
  `viewBox` pour qu'il s'adapte à la largeur :
  - **axe des altitudes** : du minimum au maximum, avec au moins 10 m
    d'écart pour qu'une trace plate reste lisible ;
  - **graduations en km** : leur pas est choisi par `niceKmStep` ;
  - **remplissage** : avec les pentes, chaque tronçon est une aire et une
    ligne à sa couleur (`writeSlopeProfile`) ; sinon, une aire unie ;
  - **icônes de POI** : ce sont des éléments **HTML** positionnés en %
    par-dessus le SVG, pas des éléments SVG, pour garder leur taille quel
    que soit l'écran ;
  - **échelles** : marges, dimensions et altitudes min/max sont exposées
    en attributs `data-*`, que le JS relit pour convertir une position de
    souris en kilomètre.
- **`elevationProfileDataJSON`** donne au JS la liste `[{km, ele, lat,
  lon}]` qui relie le profil à la carte.

### 11.6 Photos (`images.go`)

`publishPhoto` ne décode l'original qu'une fois :

| Cas | Photo publiée | Miniature (`photos/thumbs/`) |
|---|---|---|
| JPEG/PNG de plus de 1024 px | réduite à 1024 px, orientation EXIF appliquée, JPEG qualité 85 (PNG sans perte) | 640 px, JPEG qualité 78 |
| JPEG déjà petit mais pivoté (orientation ≠ 1) | ré-encodé, avec la rotation appliquée aux pixels | 640 px |
| déjà petit, orientation normale | copie identique | 640 px |
| WebP, GIF (non décodables en Go standard) | copie | copie de l'original |

`resizeToFit` fait une réduction par moyenne de zone, sans bibliothèque
externe. Le ré-encodage retire les EXIF, d'où la nécessité d'appliquer la
rotation aux pixels (`applyOrientation`). Les originaux de `rides/` ne
sont jamais modifiés.

### 11.7 Pages, chemins et SEO (`build.go`, `seo.go`, `homemap.go`)

- **Chemins relatifs** :
  - chaque page reçoit `Root` (`""` pour l'accueil, `"../../"` pour une
    fiche) et tous les liens internes sont relatifs ;
  - le site fonctionne donc ouvert depuis un sous-dossier ou servi par
    `python3 -m http.server` ;
  - seules les URL absolues de partage et de SEO utilisent `-site-url` ;
  - si `-site-url` est vide, le générateur ne produit ni partage, ni Open
    Graph, ni sitemap, ni JSON-LD.
- **Fichiers d'une fiche** dans `public/rides/<slug>/` : `index.html`, le
  GPX d'origine dans `gpx/`, les photos et miniatures, `slope.geojson` et
  `instagram.jpg` s'ils existent.
- **Carte d'accueil** (`homeMapJSON`) :
  - pour chaque sortie avec GPX : titre, couleur, URL, vignette, résumé de
    200 caractères au plus, difficulté, durée, D+, distance ;
  - la trace est réduite à 300 points, à 5 décimales (environ 1 m) ;
  - le tout est intégré dans la page, sans requête supplémentaire.
- **Données structurées** (`seo.go`) :
  - **accueil** : un graphe JSON-LD `Organization` + `WebSite` +
    `ItemList` des sorties ;
  - **fiche** : `Article` (avec lieu de départ `Place`/`GeoCoordinates`,
    image et date si elle est au format ISO) + `BreadcrumbList` ;
  - **sitemap** : liste l'accueil, les mentions légales et chaque fiche
    avec ses photos (extension image de Google).
- **Markdown** (`markdown.go`) : le texte est d'abord échappé
  (`html.EscapeString`), puis les liens, le gras et l'italique sont
  transformés par expressions régulières. Les liens s'ouvrent dans un
  nouvel onglet (`rel="noopener"`). Leur URL n'est pas filtrée : le
  contenu étant écrit par le propriétaire du site, c'est acceptable. Il
  faudrait la filtrer (refuser `javascript:`) si des contributeurs
  extérieurs écrivaient les descriptions.

### 11.8 JavaScript : logiques principales (`script.js`)

**Survol profil ↔ carte** (`gmInitProfileHover`) :
- **Du profil vers la carte** : la position de la souris (ou du doigt) est
  convertie en km grâce aux attributs `data-*` du SVG. On prend le point
  de profil au km le plus proche (`nearestByKm`, recherche linéaire), puis
  on place :
  - la ligne et le point de repère sur le profil ;
  - un marqueur cercle avec info-bulle sur la carte ;
  - l'info-bulle HTML du profil.
- **De la carte vers le profil** : la trace émet des événements
  personnalisés `gm:track-hover` et `gm:track-hover-end`
  (`gmLoadRideTrack`, fonction `attachHover`). Le profil cherche alors le
  point le plus proche en latitude/longitude (distance euclidienne en
  degrés, suffisante à cette échelle).
- **Texte affiché** : « PK 12,3 km · ↗ +5,2 % · 245 m ». La pente est
  celle du tronçon de `slope.geojson` qui contient ce km. La flèche est
  ↗ au-dessus de +2 %, ↘ en dessous de −2 %, → entre les deux.
- **Clic sur le profil** : recentre la carte sur le point et lance la
  recherche 360°.

**Recherche 360° au clic** (`gmHandleTrackClick`) :
1. Si un point Panoramax de `points.md` est à moins de **60 m** du clic,
   il est pris en priorité. Sa miniature et sa date sont chargées ensuite
   (`gmPanoramaxPreview`).
2. Sinon, une popup « recherche… » s'ouvre et l'API Panoramax est
   interrogée (`gmFindNearestPanoramax`) :
   - `search?place_position=lon,lat&place_fov_tolerance=180&place_distance=0-50`
     renvoie les photos qui « voient » le point, quelle que soit leur
     orientation, dans un rayon de 50 m ;
   - si l'instance ne gère pas cette recherche, on se replie sur une
     recherche par rectangle (`bbox`) ;
   - parmi les résultats, la photo la plus proche est retenue.
3. Un compteur (`gmTrackClickSeq`) ignore les réponses d'un clic
   précédent ou d'une popup déjà fermée, ce qui évite les popups qui se
   mélangent.
4. La visionneuse (`gmOpenPanoramax`) est une iframe de l'interface web
   officielle (`/?focus=pic&pic=<id>`), dans une fenêtre modale.

**Chargement de la trace** (`gmLoadRideTrack`) :
- la fiche charge `slope.geojson` : un liseré sombre semi-transparent,
  puis les tronçons colorés par-dessus ;
- en cas d'échec (fichier absent, erreur HTTP, JSON vide), elle charge le
  GPX, l'analyse avec `DOMParser` et l'affiche en couleur unie ;
- si le GPX échoue aussi, un message s'affiche sous la carte ;
- dans tous les cas, `fit()` mémorise l'emprise dans `map.gmTrackBounds`,
  réutilisée par le plein écran.

**Carte d'accueil** (`initHomeMap` et le gestionnaire `DOMContentLoaded`
qui suit) :
- **Traces** : chaque trace est doublée d'une **ligne invisible et
  large**, qui sert de cible au clic et au survol (plus facile à atteindre
  au doigt qu'un trait de 4 px). Le zoom à la molette n'est actif qu'après
  un clic sur la carte, pour ne pas zoomer en faisant défiler la page.
- **Filtres** :
  - les **tags sont cumulatifs** : une sortie doit les avoir tous ;
  - les **difficultés sont alternatives** : une sortie doit en avoir une ;
  - le filtre masque les cartouches et les traces, puis recadre la carte
    sur les traces visibles (`setVisible`, `fitVisible`) ;
  - l'état est écrit dans l'URL (`#tags=…&difficulte=…`), donc
    partageable et conservé au rechargement.
- **Synchronisation** : survoler un cartouche met sa trace en évidence ;
  cliquer une trace ouvre sa popup et fait défiler le **rail de
  cartouches** horizontalement jusqu'à la sortie, sans faire défiler la
  page. Les flèches du rail défilent du nombre entier de cartouches visibles
  à l'écran et se masquent aux extrémités.

**Autres composants** :
- **Carrousel** (`initCarousel`) :
  - fondu automatique en boucle, avec préchargement de la photo suivante ;
  - pause dès une interaction (flèches, points, clavier ← →, balayage
    tactile), reprise après un délai ;
  - arrêt quand l'onglet est masqué (`visibilitychange`) ;
  - désactivé si l'utilisateur a demandé moins d'animations
    (`prefers-reduced-motion`).
- **Me localiser** (`gmInitLocateMe`) : une seule lecture
  (`getCurrentPosition`, pas de suivi continu), qui place un marqueur à
  la position.
- **Partage Instagram** : utilise la Web Share API avec le fichier
  `instagram.jpg` quand le navigateur le permet. Sinon, le lien
  télécharge simplement l'image.
- **Fonds de carte** (`gmInitBasemaps`) : un seul calque de tuiles actif à
  la fois. La clé choisie est gardée dans `localStorage` (`gm-basemap`) et
  recopiée dans l'attribut `data-basemap` du conteneur, ce qui permet
  d'ajuster le style par fond en CSS.
- **Plein écran** (`gmInitFullscreen`) : utilise `requestFullscreen` si
  possible, sinon la classe `gm-map-fullscreen` (`position: fixed`) avec
  blocage du défilement de la page. À chaque changement, `invalidateSize`
  recalcule la taille ; à l'entrée, la carte est recadrée sur
  `gmTrackBounds`.

### 11.9 Scripts réseau (`find_supplies.py`, `surface_stats.py`)

Les deux scripts suivent le même schéma :
1. lire le GPX et le ré-échantillonner en environ 150 points, qui servent
   de « tampon » ;
2. envoyer **une seule** requête Overpass `around:<rayon>,<points>` ;
3. traiter le résultat localement.

- **`find_supplies.py`** :
  - interroge plusieurs tags OSM par type de POI. Par exemple, l'eau
    regroupe `amenity=drinking_water`, `water_point`,
    `man_made=water_tap`, et les fontaines, sources et puits marqués
    `drinking_water=yes`. Les campings sont cherchés aussi comme zones
    (`nwr` + `out center`) ;
  - `classify` ramène les tags à un type ; `KIND_ICON` le convertit en
    icône du site ;
  - ignore les points à moins de 20 m d'un point déjà présent dans
    `points.md` ;
  - demande la commune à Nominatim (1 requête par seconde au plus) pour
    nommer les points sans nom ;
  - propose la sélection en interactif, puis ajoute les blocs à la fin de
    `points.md`.
- **`surface_stats.py`** :
  - récupère les voies (`way[highway]`, avec géométrie) à 20 m de la
    trace ;
  - projette tout en coordonnées locales (mètres, projection
    équirectangulaire centrée sur la latitude du point central de la
    trace) ;
  - affecte à chacun des 1000 points ré-échantillonnés la catégorie de la
    voie la plus proche à moins de 25 m. Au-delà, le point est
    « indéterminé » ;
  - additionne les distances par catégorie.

  La classification repose **uniquement sur `highway=*`**, pas sur
  `surface=*` : `track` et `path` sont comptés non revêtus, `cycleway`
  et les routes revêtus, et `footway` aussi revêtu. C'est une estimation
  à garder en tête. Le résultat est écrit dans l'en-tête de
  `description.md` (`update_frontmatter`).

### 11.10 Visuels (`brand.py`, `make_instagram_image.py`, `generate_qrcode.py`)

- **Rendu sur-échantillonné** : traces, profil et QR sont dessinés 2 à 4
  fois plus grands, puis réduits en LANCZOS, pour des courbes lisses
  (Pillow n'a pas d'anticrénelage sur les lignes).
- **Fond de carte** (`basemap`) :
  - convertit la trace en Web Mercator (`_merc`, pixels au zoom 0) ;
  - calcule le zoom fractionnaire `zf` qui fait remplir le cadre à la
    trace, avec 10 % de marge ;
  - télécharge les tuiles du zoom entier **supérieur** `zi`, plafonné au
    zoom maximal du fournisseur ;
  - assemble une mosaïque, la découpe, puis la réduit du facteur
    `2^(zf−zi)`, ce qui donne une image plus nette qu'un agrandissement ;
  - renvoie avec l'image une fonction `project(lat, lon)` qui place la
    trace exactement sur le fond. Un test vérifie l'alignement à moins de
    2 px ;
  - au moindre échec réseau, renvoie `(None, None)` et l'appelant garde un
    fond uni.
- **Mise en forme** :
  - `fit_title` essaie des tailles de titre décroissantes jusqu'à tenir en
    N lignes ;
  - `draw_text` gère l'espacement des lettres ;
  - la police variable est réglée sur la graisse demandée (axe `wght`).
- **QR code** (`styled_qr`) :
  - correction d'erreur maximale (`error="h"`), ce qui permet de recouvrir
    le centre par le logo ;
  - modules jointifs aux coins arrondis, repères d'angle peu arrondis,
    zone de silence entièrement claire : ces réglages ont été ajustés
    jusqu'à ce que le code se décode bien ;
  - `verify()` relit le QR avec OpenCV (si installé), à plusieurs tailles.
- **`new_ride.py`** :
  - enchaîne les étapes `dossier`, `controle`, `poi`, `surface`,
    `pentes`, `instagram`, `qrcode` et `site` ;
  - une étape peut être sautée (`SkipStep` : outil absent, pas de réseau)
    sans arrêter les suivantes ;
  - le code de sortie vaut 1 si au moins une étape a échoué ;
  - les étapes réseau (`poi`, `surface`) sont désactivées par
    `--no-network`.
