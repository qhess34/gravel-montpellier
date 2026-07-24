# Gravel Montpellier

Générateur de site statique en Go qui liste les sorties gravel autour de
Montpellier. La mise en forme est entièrement automatique : vous n'avez
qu'à déposer le contenu de chaque sortie dans `rides/`, la CI GitHub
Actions génère le site et le publie sur GitHub Pages à chaque `push` sur
`main`.

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

> Astuce tri : pour un tri chronologique fiable, utilisez un format
> `date: 2026-06-15` (les sorties sont triées par ordre alphabétique
> décroissant de ce champ).

### track.gpx

Un seul fichier `.gpx` par dossier de sortie. S'il est présent :
- il est affiché sur une carte (OpenStreetMap + Leaflet) sur la page de la sortie,
- il est proposé au téléchargement,
- la distance et le dénivelé sont calculés automatiquement si vous ne les
  avez pas renseignés dans `description.md`.

### photos/

Toutes les images (`.jpg`, `.jpeg`, `.png`, `.webp`, `.gif`) placées dans
ce dossier sont listées en galerie sur la page de la sortie. La première
(ordre alphabétique) sert de vignette sur la page d'accueil. Cliquer sur
une photo de la galerie l'ouvre en grand (lightbox).

### points.md — POI, photos géolocalisées et points Panoramax

Fichier optionnel pour ajouter des marqueurs cliquables sur la carte :
un ravitaillement, une photo géolocalisée, ou une vue à 360° via
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
lat: 43.8200
lon: 3.8400
photo: single-technique.jpg
caption: Le passage technique du single

---

type: panoramax
lat: 43.8450
lon: 3.8100
picture: cafb0ec8-51dd-43ac-836c-8cd1f7cb8725
sequence: 11111111-2222-3333-4444-555555555555
label: Vue à 360° depuis le sommet
```

Champs communs à tous les types : `type` (obligatoire), `lat`/`lon`
(obligatoires, coordonnées GPS décimales), `label`.

| `type`      | Champs spécifiques                                                                 | Comportement au clic                              |
|-------------|--------------------------------------------------------------------------------------|-----------------------------------------------------|
| `poi`       | `label` (obligatoire), `note`, `icon` (`water`, `food`, `danger`, `viewpoint`, ou `generic` par défaut) | Ouvre une popup avec le label et la note            |
| `photo`     | `photo` (obligatoire — nom de fichier présent dans `photos/`), `caption`             | Ouvre la photo en grand (lightbox)                   |
| `panoramax` | `picture` (obligatoire — identifiant de la photo sur Panoramax), `sequence` (recommandé), `endpoint` (optionnel, instance publique par défaut) | Ouvre la visionneuse Panoramax intégrée en superposition |

> L'identifiant `picture` (et `sequence`) d'une photo Panoramax se
> récupère depuis son visionneur : bouton en haut à gauche de l'image
> → onglet *Résumé* → *Copier l'identifiant*.

Une sortie sans trace GPX peut quand même afficher une carte si elle
contient des points dans `points.md` — la carte se cadre alors
automatiquement sur ces points.

## Le footer

Le contenu de `content/footer.md` (markdown simple, pas de frontmatter)
est affiché sur toutes les pages du site. Modifiez ce fichier librement.

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
go run ./cmd/generator -rides ./rides -footer ./content/footer.md -out ./public -title "Gravel Montpellier"
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
3. Poussez sur `main` (ou lancez le workflow manuellement depuis l'onglet
   **Actions**) : le site est construit puis publié automatiquement.

Aucun token à configurer : le workflow utilise les permissions
`pages`/`id-token` fournies automatiquement par GitHub Actions.

## Structure du projet

```
cmd/generator/        point d'entrée (main.go)
internal/site/         logique du générateur (frontmatter, markdown, gpx, build)
internal/site/templates/  gabarits HTML (mise en forme, à ne modifier que si besoin)
internal/site/static/     CSS du site
content/footer.md      pied de page, modifiable
rides/                  une sortie = un dossier
.github/workflows/     CI de build + déploiement GitHub Pages
Dockerfile              build + service du site via nginx (voir ci-dessus)
docker-compose.yml      boucle de dev : régénération + aperçu local
```

Vous n'avez normalement besoin de toucher qu'à `rides/` et
`content/footer.md` — le reste s'occupe de la mise en forme.
