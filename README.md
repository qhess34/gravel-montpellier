# Cyclo Explore — Montpellier

Générateur de site statique en Go qui liste les sorties gravel autour de
Montpellier, publié sur **montpellier.cycloexplore.fr**. La mise en forme
est entièrement automatique : vous n'avez qu'à déposer le contenu de
chaque sortie dans `rides/`, la CI GitHub Actions génère le site et le
publie sur GitHub Pages à chaque `push` sur `main`.

## Ajouter une sortie

Créez un dossier dans `rides/`, avec un nom court sans espace ni accent
(ce sera l'URL de la page), par exemple `rides/tour-du-pic-saint-loup/` :

```
rides/tour-du-pic-saint-loup/
├── description.md      (obligatoire)
├── track.gpx            (optionnel, un seul fichier .gpx par sortie)
└── photos/               (optionnel)
    ├── depart.jpg
    └── single.jpg
```

### description.md

```md
---
title: Tour du Pic Saint-Loup
date: 15 juin 2026
difficulty: Difficile
departure: Montpellier - Place Zeus
tags: calcaire, single, ravitaillement à Saint-Mathieu
---

Le texte de description, en markdown simple : titres avec `#`/`##`,
listes avec `- `, **gras**, *italique* et [liens](https://exemple.fr).
```

Champs du frontmatter (toutes optionnelles sauf `title`) :

| Champ         | Rôle                                                              |
|---------------|--------------------------------------------------------------------|
| `title`       | Titre de la sortie                                                 |
| `date`        | Date affichée (texte libre) et utilisée pour trier les sorties     |
| `distance_km` | Distance en km. **Si absent, calculée automatiquement depuis le GPX** |
| `elevation_m` | Dénivelé positif en m. **Si absent, calculé depuis le GPX**        |
| `difficulty`  | Ex : Facile / Modéré / Difficile                                   |
| `departure`   | Lieu de départ                                                     |
| `tags`        | Liste séparée par des virgules                                     |
| `surface_paved_km` / `surface_unpaved_km` | Km revêtu/non revêtu — généralement pas saisis à la main, voir `tools/surface_stats.py` plus bas |

> Astuce tri : pour un tri chronologique fiable, utilisez un format
> `date: 2026-06-15` (les sorties sont triées par ordre alphabétique
> décroissant de ce champ).

**Filtre par tags sur l'accueil :** dès qu'au moins une sortie a des
`tags`, une barre de filtre apparaît automatiquement sur la page
d'accueil (aucune configuration à faire). Cliquer sur un ou plusieurs
tags affiche uniquement les sorties qui les ont tous (filtrage cumulatif,
pas de rechargement de page) ; « Toutes les sorties » réinitialise. Le
filtre actif est mémorisé dans l'URL (`#tags=...`), donc partageable ou
rechargeable tel quel.

### track.gpx

Un seul fichier `.gpx` par dossier de sortie. S'il est présent :
- il est affiché tel quel sur une carte (OpenStreetMap + Leaflet) sur la page de la sortie,
- une **estimation du revêtement** (route/piste cyclable vs chemin/sentier) peut être affichée sous forme de barre + pourcentages sous la carte, si `description.md` contient les champs `surface_paved_km`/`surface_unpaved_km` — voir `tools/surface_stats.py` ci-dessous pour les calculer automatiquement,
- un **profil altimétrique** est généré automatiquement (SVG, sans JavaScript) sous la carte, avec les points d'eau/boulangeries repérés au bon endroit ; survoler la carte ou le profil affiche le point correspondant sur l'autre (et inversement),
- il est proposé au téléchargement,
- la distance et le dénivelé sont calculés automatiquement si vous ne les
  avez pas renseignés dans `description.md`.

### photos/

Toutes les images (`.jpg`, `.jpeg`, `.png`, `.webp`, `.gif`) placées dans
ce dossier sont listées en galerie sur la page de la sortie. La première
(ordre alphabétique) sert de vignette sur la page d'accueil. Cliquer sur
une photo de la galerie l'ouvre en grand (lightbox).

**Géolocalisation automatique :** si une photo `.jpg`/`.jpeg` contient des
coordonnées GPS dans ses métadonnées EXIF (cas courant pour une photo prise
au smartphone ou avec un appareil GPS activé), un marqueur est
automatiquement ajouté sur la carte — sans rien à faire dans `points.md`.
Une photo recadrée/exportée depuis un réseau social a souvent perdu ses
EXIF ; dans ce cas, ajoutez-la manuellement dans `points.md` (voir
ci-dessous) avec ses coordonnées.

### Départ et arrivée

Si la sortie a une trace GPX, les marqueurs de départ et d'arrivée sont
ajoutés automatiquement sur la carte, à partir du premier et du dernier
point de la trace — rien à configurer. Si départ et arrivée sont au même
endroit (à 50 m près), un seul marqueur « Départ / Arrivée » est affiché.

### points.md — POI, photos géolocalisées et points Panoramax

Fichier optionnel pour ajouter des marqueurs cliquables sur la carte :
un ravitaillement, une photo géolocalisée précise, ou une vue à 360° via
[Panoramax](https://panoramax.fr/). Un bloc par point, séparés par une
ligne `---` :

```
type: poi
icon: food
lat: 43.7950
lon: 3.8300
label: Ravitaillement
note: Point d'eau à Saint-Mathieu-de-Tréviers

---

type: photo
photo: single-technique.jpg
caption: Le passage technique du single

---

type: panoramax
picture: cafb0ec8-51dd-43ac-836c-8cd1f7cb8725
sequence: 11111111-2222-3333-4444-555555555555
label: Vue à 360° depuis le sommet
```

Champs communs : `type` (obligatoire), `label`. `lat`/`lon` sont
**optionnels selon le type** :

| `type`      | Champs spécifiques                                                                 | `lat`/`lon`                                                                 | Comportement au clic                              |
|-------------|--------------------------------------------------------------------------------------|-------------------------------------------------------------------------------|-------------------------------------------------------|
| `poi`       | `label` (obligatoire), `note`, `icon` (`water`, `food`, `danger`, `viewpoint`, ou `generic` par défaut) | **obligatoires**, aucune source automatique                                    | Ouvre une popup avec le label et la note              |
| `photo`     | `photo` (obligatoire — nom de fichier présent dans `photos/`), `caption`             | facultatifs : si absents, lus depuis les **EXIF GPS** de la photo (photo ignorée avec avertissement si la photo n'a pas d'EXIF GPS) | Ouvre la photo en grand (lightbox)                     |
| `panoramax` | `picture` (obligatoire — identifiant de la photo sur Panoramax), `sequence` (recommandé), `endpoint` (optionnel, instance publique par défaut) | facultatifs : si absents, **résolus automatiquement via l'API Panoramax** au moment du build (nécessite un accès réseau ; point ignoré avec avertissement si l'API ne répond pas) | Ouvre la visionneuse Panoramax intégrée en superposition |

> L'identifiant `picture` (et `sequence`) d'une photo Panoramax se
> récupère depuis son visionneur : bouton en haut à gauche de l'image
> → onglet *Résumé* → *Copier l'identifiant*.

Chaque type de point (POI par icône, photo, panoramax, départ/arrivée)
a son propre pictogramme sur la carte pour rester reconnaissable en un
coup d'œil.

**Synthèse ravitaillement :** pour une sortie avec trace GPX, tout point
`type: poi` avec `icon: water` ou `icon: food` est automatiquement
projeté sur la trace pour en déduire son point kilométrique (PK), et
listé dans un encadré « Points d'eau et boulangeries sur le parcours »
sous la description — rien à écrire en plus, ça vient uniquement de ce
que vous avez déjà mis dans `points.md`. Un point à plus de 3 km de la
trace n'est pas considéré comme « sur le parcours » et n'apparaît pas
dans cette synthèse (il reste affiché sur la carte).

Une sortie sans trace GPX peut quand même afficher une carte si elle
contient des points dans `points.md` — la carte se cadre alors
automatiquement sur ces points.

### Trouver automatiquement les points d'eau et boulangeries

`tools/find_supplies.py` interroge OpenStreetMap (API Overpass) le long
de la trace GPX d'une sortie, vous propose un par un les points d'eau et
boulangeries trouvés (commune, nom, distance à la trace, PK), et génère
les blocs à coller dans `points.md` pour ceux que vous validez — plus
besoin de chercher les coordonnées à la main. La commune est déterminée
par géocodage inverse (Nominatim) et préfixée au label par défaut (ex :
« Saint-Mathieu-de-Tréviers — Fontaine du village »), modifiable avec `e`
avant validation. Les points déjà présents dans `points.md` (à moins de
20 m d'un point existant) ne sont pas reproposés d'une exécution à
l'autre.

Ne dépend que de Python 3.8+ (bibliothèque standard uniquement, rien à
installer) ; nécessite un accès réseau.

```bash
python3 tools/find_supplies.py rides/tour-du-pic-saint-loup
```

Pour chaque point trouvé, répondez `o` (ajouter), `n` (ignorer), `e`
(éditer le label/note avant d'ajouter) ou `q` (arrêter la sélection). À
la fin, le script propose d'ajouter directement les points validés à
`points.md` (ou affiche juste le texte à copier avec `--dry-run`).

Options utiles :

```bash
# Rayon de recherche autour de la trace (défaut : 150 m)
python3 tools/find_supplies.py rides/tour-du-pic-saint-loup --radius 250

# Un seul type de point
python3 tools/find_supplies.py rides/tour-du-pic-saint-loup --only water

# Revoir aussi les points déjà présents dans points.md
python3 tools/find_supplies.py rides/tour-du-pic-saint-loup --include-existing

# Afficher le résultat sans rien écrire
python3 tools/find_supplies.py rides/tour-du-pic-saint-loup --dry-run
```

### Estimer le revêtement (route/piste cyclable vs chemin/sentier)

`tools/surface_stats.py` compare la trace GPX d'une sortie aux données
OpenStreetMap (API Overpass) pour estimer la part de route/piste cyclable
(revêtu) et de chemin/sentier (non revêtu), puis écrit le résultat dans
`description.md` (`surface_paved_km` / `surface_unpaved_km`). Le
générateur lit ensuite simplement ces deux champs pour afficher une barre
de revêtement sur la page de la sortie — **aucun appel réseau au moment
du build**, tout se joue quand vous lancez ce script.

```bash
python3 tools/surface_stats.py rides/tour-du-pic-saint-loup
```

Sans trace GPX ou si `description.md` est absent, le script s'arrête
avec un message clair. Options utiles :

```bash
# Rayon de recherche des voies autour de la trace (défaut : 20 m)
python3 tools/surface_stats.py rides/tour-du-pic-saint-loup --radius 30

# Afficher le résultat sans modifier description.md
python3 tools/surface_stats.py rides/tour-du-pic-saint-loup --dry-run
```

Relancer le script écrase simplement les valeurs précédentes (pas de
doublon), par exemple après avoir mis à jour la trace d'une sortie.

## Le footer

Le contenu de `content/footer.md` (markdown simple, pas de frontmatter)
est affiché sur toutes les pages du site. Modifiez ce fichier librement.

## Mentions légales

Le contenu de `content/mentions-legales.md` (markdown simple) est publié
sur une page dédiée (`mentions-legales.html`), reliée par un lien fixe en
bas de chaque page — ce lien est toujours présent, indépendamment de ce
que vous mettez dans `content/footer.md`.

Un fichier de départ est fourni, couvrant l'absence de garantie sur
l'état du terrain, les passages sur des voies privées, et la limitation
de responsabilité de l'auteur. Adaptez-le à votre situation ; ce n'est
pas un avis juridique, faites-le relire par un professionnel si vous
voulez une protection solide.

Chaque page de sortie affiche en plus, automatiquement (ce bandeau n'est
pas éditable par sortie, il vient du gabarit) un court rappel — terrain
qui peut avoir changé, passage éventuel sur propriété privée, pratique
sous sa propre responsabilité — avec un lien vers la page complète.

## Partage (Facebook, WhatsApp, X, e-mail) et aperçu d'image

Chaque page de sortie affiche automatiquement des boutons de partage —
rien à faire dans `description.md`. Ça repose sur l'URL publique du
site, connue via `-site-url` — par défaut déjà réglée sur
`https://montpellier.cycloexplore.fr` (inutile d'y toucher sauf pour
tester ailleurs) :

```bash
go run ./cmd/generator -site-url "https://montpellier.cycloexplore.fr"
```

En CI, cette même valeur est utilisée par défaut ; pour la changer sans
modifier le workflow (test, environnement de staging...), définissez une
variable de dépôt **`SITE_URL`** dans *Settings → Secrets and variables →
Actions → Variables* — elle prend le pas sur la valeur par défaut.

Quand `-site-url` pointe vers un domaine personnalisé (comme ici, pas un
sous-domaine `*.github.io`), un fichier `CNAME` contenant ce domaine est
généré automatiquement dans `public/` — c'est ce dont GitHub Pages a
besoin pour servir le site sur `montpellier.cycloexplore.fr`. Il faut
par ailleurs configurer une fois le DNS (enregistrement CNAME de
`montpellier` vers `<compte>.github.io`) et déclarer le domaine dans
*Settings → Pages* du dépôt.

L'image d'aperçu utilisée est la première photo (ordre alphabétique) du
dossier `photos/` de la sortie ; sans photo, seuls le titre et un court
résumé (distance, dénivelé, difficulté) sont utilisés dans l'aperçu.

## Générer le site localement

```bash
go run ./cmd/generator
```

Le site est généré dans `./public/`. Ouvrez `public/index.html` dans un
navigateur (certains navigateurs bloquent les requêtes `fetch` en
`file://` : pour tester la carte GPX, servez le dossier, par exemple
`python3 -m http.server --directory public`).

Options disponibles :

```bash
go run ./cmd/generator -rides ./rides -footer ./content/footer.md -legal ./content/mentions-legales.md -site-url "https://montpellier.cycloexplore.fr" -out ./public -title "Cyclo Explore"
```

## Générer et prévisualiser avec Docker

Alternative à l'installation de Go en local : tout se passe dans des
conteneurs. Deux façons de faire, du plus simple au plus pratique pour
itérer.

### Option 1 — image tout-en-un

```bash
docker build -t gravel-montpellier .
docker run --rm -p 8080:80 gravel-montpellier
```

Le site est généré pendant le `build` puis servi sur
[http://localhost:8080](http://localhost:8080). Simple, mais il faut
reconstruire l'image (`docker build`) à chaque modification de `rides/`
ou `content/footer.md`.

### Option 2 — avec Docker Compose (recommandée pour itérer)

Deux services : l'un régénère le site à la demande, l'autre le sert en
continu.

```bash
# 1. Servir le site (à laisser tourner dans un terminal)
docker compose up serve
# → http://localhost:8080

# 2. Dans un autre terminal, à chaque modification de rides/ ou du footer :
docker compose run --rm generate
```

Il suffit ensuite de rafraîchir le navigateur après chaque
`docker compose run --rm generate` pour voir vos changements — aucune
reconstruction d'image nécessaire, `go run` télécharge l'image Go une
seule fois puis réutilise le cache.

> **403 côté `serve` ?** Si vous démarrez `serve` avant d'avoir jamais
> lancé `generate`, le dossier `public/` n'existe pas encore côté hôte :
> Docker le crée vide au montage, et nginx renvoie 403 tant qu'il est
> vide (pas d'`index.html`, listing désactivé). Lancez simplement
> `docker compose run --rm generate` une première fois, puis rafraîchissez.

## Mise en place de GitHub Pages (une seule fois)

1. Poussez ce dépôt sur GitHub.
2. Dans **Settings → Pages**, réglez la section *Build and deployment*
   sur **Source: GitHub Actions**.
3. Toujours dans **Settings → Pages**, section *Custom domain*, entrez
   `montpellier.cycloexplore.fr` et validez (GitHub vérifie le DNS).
4. Chez votre fournisseur DNS, ajoutez un enregistrement **CNAME** pour
   `montpellier.cycloexplore.fr` pointant vers `<compte>.github.io`.
5. Poussez sur `main` (ou lancez le workflow manuellement depuis l'onglet
   **Actions**) : le site est construit (avec son fichier `CNAME`, généré
   automatiquement — voir la section partage ci-dessus) puis publié.

Aucun token à configurer : le workflow utilise les permissions
`pages`/`id-token` fournies automatiquement par GitHub Actions.

## Structure du projet

```
cmd/generator/        point d'entrée (main.go)
internal/site/         logique du générateur (frontmatter, markdown, gpx, build)
internal/site/templates/  gabarits HTML (mise en forme, à ne modifier que si besoin)
internal/site/static/     CSS du site
content/footer.md      pied de page, modifiable
content/mentions-legales.md  page mentions légales, modifiable
rides/                  une sortie = un dossier
.github/workflows/     CI de build + déploiement GitHub Pages
Dockerfile              build + service du site via nginx (voir ci-dessus)
docker-compose.yml      boucle de dev : régénération + aperçu local
tools/find_supplies.py  recherche interactive de points d'eau/boulangeries (OSM)
tools/surface_stats.py  estimation du revêtement, écrit dans description.md (OSM)
```

Vous n'avez normalement besoin de toucher qu'à `rides/`,
`content/footer.md` et `content/mentions-legales.md` — le reste s'occupe
de la mise en forme.
