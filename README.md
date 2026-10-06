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
├── points.md            (optionnel, POI / photos / vues 360°)
├── slope.geojson        (généré par tools/slope_colors.py — ne pas éditer)
└── photos/               (optionnel)
    ├── 0.jpg             (la 1re par ordre alphabétique sert de couverture)
    └── single.jpg
```

**Checklist pour ajouter une sortie :**

1. Créer `rides/<slug>/` et y déposer le `.gpx` (export Komoot, Strava…).
2. Écrire `description.md` : frontmatter (`title`, `date`, `difficulty`,
   `departure`, `tags`…), puis un court texte d'introduction — **la
   synthèse** — suivi d'un titre `## Le parcours` et du détail (voir
   ci-dessous).
3. Ajouter les photos dans `photos/` (préfixez la photo de couverture par
   `0` pour qu'elle passe en premier, ex : `0.jpg`).
4. Lancer `python3 tools/new_ride.py rides/<slug>` : il enchaîne POI,
   revêtement, pentes (`slope.geojson`), visuels Instagram et QR code, et
   génère le site pour vérifier la fiche (voir « Tout enchaîner » plus bas).
   Chaque script reste utilisable seul.
5. Relire `description.md`, puis commiter le dossier (dont `slope.geojson`
   et `instagram.jpg`).

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
| `difficulty`  | Facile / Moyenne / Difficile / Très difficile (les variantes « Moyen », « Modéré »… sont regroupées dans le filtre ; la valeur saisie reste affichée telle quelle) |
| `duration`    | Durée estimée, texte libre (ex : `4 h 30`). **Si absent, déduite des tags « 1 jour », « 2 jours »…** (ex : « 2 à 5 jours ») ; sans l'un ni l'autre, aucune durée n'est affichée |
| `color`       | Couleur de la trace sur la carte d'accueil (`#rrggbb`). Optionnel : une couleur stable est attribuée automatiquement |
| `departure`   | Lieu de départ                                                     |
| `tags`        | Liste séparée par des virgules                                     |
| `surface_paved_km` / `surface_unpaved_km` | Km revêtu/non revêtu — généralement pas saisis à la main, voir `tools/surface_stats.py` plus bas |

> Tri : les sorties sont triées de la plus récente à la plus ancienne.
> Les formats `2026-06-15`, `15/06/2026` et `15 juin 2026` sont reconnus.

**Synthèse (accroche) :** le texte situé entre la fin du frontmatter (la
ligne `---` qui le referme) et le titre `## Le parcours` est extrait
automatiquement comme synthèse de la sortie. Elle est affichée dans la
popup de la carte d'accueil, sur le cartouche de la sortie (tronquée
visuellement) et sert de meta description. Sur la fiche, elle apparaît
une seule fois, en chapô, juste avant `## Le parcours`. Sans titre
`## Le parcours`, la synthèse s'arrête au premier titre ; sans aucun
titre, c'est le premier paragraphe.

**Filtres sur l'accueil :** une barre de filtres par **difficulté** et par
**tags** apparaît automatiquement. Les tags sont cumulatifs (une sortie
doit les avoir tous), les difficultés au choix (Facile *ou* Moyenne…).
Les filtres agissent à la fois sur les traces de la carte et sur les
cartouches ; « Toutes les sorties » réinitialise. L'état est mémorisé
dans l'URL (`#tags=...&difficulte=...`), donc partageable. Sur mobile, la
liste des tags est repliée derrière le bouton « Tags ».


### track.gpx

Un seul fichier `.gpx` par dossier de sortie. S'il est présent :
- sa trace (simplifiée) apparaît sur la **carte d'accueil**, avec une couleur propre à la sortie ; cliquer dessus ouvre une popup (photo, synthèse, difficulté, durée, D+, bouton « Voir la sortie ») et amène son cartouche dans la ligne de cartouches sous la carte. Ces cartouches (photo, titre, difficulté, durée, D+, distance, date, synthèse — sans les tags, qui servent au filtre) sont alignés sur une seule ligne qui défile avec les flèches ‹ › (ou au doigt / à la molette) ; survoler un cartouche met sa trace en évidence,
- il est affiché sur une carte (OpenStreetMap + Leaflet) sur la page de la sortie, **colorisé selon la pente** (voir « Colorisation des traces selon la pente »), avec un bouton **« Me localiser »** intégré à la carte à côté du zoom (géolocalisation du navigateur, avec son autorisation) pour voir sa propre position dessus,
- une **estimation du revêtement** (route/piste cyclable vs chemin/sentier) peut être affichée sous forme de barre + pourcentages sous la carte, si `description.md` contient les champs `surface_paved_km`/`surface_unpaved_km` — voir `tools/surface_stats.py` ci-dessous pour les calculer automatiquement,
- un **profil altimétrique** est généré automatiquement (SVG) sous la carte, coloré selon la pente, avec l'icône de chaque POI au bon endroit (cliquer sur une icône centre la carte sur le point et ouvre sa popup) ; survoler la trace ou le profil affiche, sur les deux, la position, le point kilométrique et la pente du tronçon (ex : « PK 12,3 km · ↗ +5,2 % »). La légende des pentes et la barre de revêtement suivent le profil,
- il est proposé au téléchargement (fichier original, non modifié),
- la distance et le dénivelé sont calculés automatiquement si vous ne les
  avez pas renseignés dans `description.md`.

### photos/

Toutes les images (`.jpg`, `.jpeg`, `.png`, `.webp`, `.gif`) placées dans
ce dossier sont présentées dans un **carrousel** en haut de la page de la
sortie : une photo à la fois, défilement automatique en fondu (en boucle),
flèches, points de navigation, clavier (← →) et balayage tactile. Le
défilement s'interrompt dès qu'on interagit et reprend après 10 s
d'inactivité ; un bouton permet de le mettre en pause, et il ne démarre
pas si le système demande de réduire les animations. Cliquer sur une
photo l'ouvre en grand (lightbox). La première photo (ordre alphabétique)
sert de vignette sur l'accueil et dans la popup de la carte — et s'il y a
plusieurs photos, elles défilent au survol du cartouche.

**Miniatures :** au build, une miniature (640 px) de chaque photo est
générée dans `photos/thumbs/` du site publié, pour alléger l'accueil.

**Allègement automatique :** au moment du build, les photos `.jpg`/`.jpeg`
et `.png` dont le plus grand côté dépasse **1024 px** sont réduites à
cette taille (proportions conservées, JPEG ré-encodé en qualité 85) dans
le site généré — vos fichiers d'origine, dans `rides/`, ne sont jamais
modifiés (et restent donc disponibles en pleine résolution pour
`tools/make_instagram_image.py`). L'orientation EXIF des JPEG (photos
prises en portrait au smartphone, par exemple) est corrigée dans les
pixels avant ré-encodage, pour que la photo reste dans le bon sens. Les
photos déjà assez petites sont copiées telles quelles, et les formats
`.webp`/`.gif` aussi (la bibliothèque standard Go ne les gère pas, et
cette fonctionnalité n'utilise volontairement aucune dépendance
externe).

> Effet de bord : le ré-encodage supprime les métadonnées EXIF (dont les
> coordonnées GPS et les infos d'appareil) des photos réduites — un petit
> plus pour la vie privée côté site public. Mais ça ne vaut **pas** pour
> les photos copiées telles quelles (déjà petites, `.webp`, `.gif`), qui
> gardent leurs métadonnées d'origine : à garder en tête si certaines
> photos contiennent un lieu que vous ne souhaitez pas exposer.

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
| `poi`       | `label` (obligatoire), `note`, `icon` (`water`, `food`, `grocery`, `bar`, `restaurant`, `camping`, `bike-repair`, `danger`, `viewpoint`, ou `generic` par défaut) | **obligatoires**, aucune source automatique                                    | Ouvre une popup avec le label et la note              |
| `photo`     | `photo` (obligatoire — nom de fichier présent dans `photos/`), `caption`             | facultatifs : si absents, lus depuis les **EXIF GPS** de la photo (photo ignorée avec avertissement si la photo n'a pas d'EXIF GPS) | Ouvre la photo en grand (lightbox)                     |
| `panoramax` | `picture` (obligatoire — identifiant de la photo sur Panoramax), `sequence` (recommandé), `endpoint` (optionnel, instance publique par défaut) | facultatifs : si absents, **résolus automatiquement via l'API Panoramax** au moment du build (nécessite un accès réseau ; point ignoré avec avertissement si l'API ne répond pas) | Ouvre la vue Panoramax en grand, par-dessus la page (interface web officielle de Panoramax en iframe, comme le userscript [tampermonkey-komoot-panoramax](https://github.com/qhess34/tampermonkey-komoot-panoramax)) ; ✕ ou Échap pour fermer, ↗ pour l'ouvrir dans un nouvel onglet |

> L'identifiant `picture` (et `sequence`) d'une photo Panoramax se
> récupère depuis son visionneur : bouton en haut à gauche de l'image
> → onglet *Résumé* → *Copier l'identifiant*.

**Vues 360° le long des traces.** La plupart des sorties sont visibles en
360° grâce aux photos Panoramax prises le long des traces ; le site le met
en avant : mention dans le bandeau d'accueil, badge « 360° » sur les
cartouches des sorties qui ont des vues sélectionnées dans `points.md`,
encart « Parcours visible en 360° » et bouton « Visite immersive » (vue du
départ) sur la carte de chaque sortie. Cliquer sur la trace **ou sur le
profil altimétrique** affiche un aperçu de la photo la plus proche
(miniature, date de prise de vue, distance) avec un bouton « Voir en
360° ». La recherche est la même que celle du userscript
[tampermonkey-komoot-panoramax](https://github.com/qhess34/tampermonkey-komoot-panoramax) :
photos qui « voient » le point, à moins de 50 m.

Cliquer n'importe où sur la carte d'une sortie propose aussi un bouton
« Voir en 360° » quand une vue panoramax existe à proximité — pas besoin
de viser précisément un marqueur. Il vérifie d'abord vos points
panoramax catalogués dans `points.md` (à moins de 60 m du clic), et à
défaut interroge l'API Panoramax en direct pour trouver n'importe quelle
photo existante à proximité (moins de 50 m), même si vous ne l'avez pas
ajoutée vous-même — pratique pour explorer la couverture Panoramax le
long de tout le parcours plutôt que seulement aux points que vous avez
choisis. Nécessite un accès réseau côté visiteur pour ce second cas.

Chaque type de point (POI par icône, photo, panoramax, départ/arrivée)
a son propre pictogramme sur la carte pour rester reconnaissable en un
coup d'œil. Dès qu'une sortie a au moins deux types de points différents,
une barre de filtre apparaît au-dessus de la carte : cliquer sur un type
le masque à la fois sur la carte et sur le profil altimétrique (et
inversement pour le réafficher) — pratique pour isoler par exemple
seulement les points d'eau sur une longue sortie chargée en POI.

**Liste des points d'intérêt :** pour une sortie avec trace GPX, tout
point `type: poi` (quel que soit son `icon`) est automatiquement projeté
sur la trace pour en déduire son point kilométrique (PK), et listé sous la
description dans l'ordre du parcours : PK, icône, label, type et note.
Cliquer sur un point de la liste centre la carte dessus et ouvre sa popup.
Un point à plus de 3 km de la trace n'a pas de PK : il est listé à part
(« À l'écart du parcours »).

Une sortie sans trace GPX peut quand même afficher une carte si elle
contient des points dans `points.md` — la carte se cadre alors
automatiquement sur ces points.

### Trouver automatiquement des points d'intérêt utiles

`tools/find_supplies.py` interroge OpenStreetMap (API Overpass) le long
de la trace GPX d'une sortie, vous propose un par un les points trouvés
(commune, nom, distance à la trace, PK), et génère les blocs à coller
dans `points.md` pour ceux que vous validez — plus besoin de chercher
les coordonnées à la main. La commune est déterminée par géocodage
inverse (Nominatim) et préfixée au label par défaut (ex :
« Saint-Mathieu-de-Tréviers — Fontaine du village »), modifiable avec `e`
avant validation. Les points déjà présents dans `points.md` (à moins de
20 m d'un point existant) ne sont pas reproposés d'une exécution à
l'autre.

Types recherchés (tous par défaut, filtrables avec `--only`) : points
d'eau (`water`), boulangeries (`bakery`), magasins alimentaires
(`grocery` — supérettes, supermarchés, primeurs), campings (`camping`),
bars (`bar`), restaurants (`restaurant`), réparateurs de vélo
(`bike_repair`).

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

# Un ou plusieurs types précis (séparés par des virgules)
python3 tools/find_supplies.py rides/tour-du-pic-saint-loup --only water,bakery

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

### Visuels de partage : Instagram et QR code

Deux générateurs produisent des visuels aux couleurs du site (fond crème,
vert forêt et terracotta, polices Fraunces et Inter fournies dans
`tools/fonts/`, emblème du logo). Toutes les informations sont lues
dans les fichiers de la sortie (titre, difficulté, durée, distance, D+,
photos, trace, `slope.geojson`) : rien à ressaisir.

Ils dépendent de [Pillow](https://pillow.readthedocs.io/) et
[segno](https://segno.readthedocs.io/) :

```bash
pip install -r tools/requirements.txt
# si erreur "externally-managed-environment" : ajouter --break-system-packages
```

**Instagram** — `tools/make_instagram_image.py` : photo de la sortie,
emblème et nom du site, pastille de difficulté, titre, chiffres clés
(distance, D+, durée), silhouette de la trace et profil altimétrique
colorés selon la pente, adresse de la fiche en pied de page.

```bash
python3 tools/make_instagram_image.py rides/tour-du-pic-saint-loup                 # post 1080×1350 -> instagram.jpg
python3 tools/make_instagram_image.py rides/tour-du-pic-saint-loup --format story   # 1080×1920 -> instagram-story.jpg
python3 tools/make_instagram_image.py rides/tour-du-pic-saint-loup --format carre   # 1080×1080
python3 tools/make_instagram_image.py rides/tour-du-pic-saint-loup --photo photos/sommet.jpg --out apercu.jpg
```

La trace est posée sur un **fond de carte** atténué (Plan IGN par
défaut, sous Licence Ouverte Etalab : réutilisation libre, y compris
commerciale), avec l'attribution de la source imprimée sur l'image. Les
tuiles sont téléchargées à la génération puis gardées en cache
(`~/.cache/cycloexplore/tiles`) ; sans réseau, la trace reste sur fond
uni. Autres fonds : `--fond topo` (OpenTopoMap, licence CC-BY-SA : le
visuel produit hérite de cette licence de partage), `--fond osm`, `--fond velo`, ou
`--fond aucun`.

`instagram.jpg` (format post) est repris automatiquement par le site :
copié avec la fiche, il fait apparaître un bouton **Instagram** dans le
bloc de partage. Sans photo, un dégradé aux couleurs du site la remplace ;
sans `slope.geojson`, la trace est en couleur unie.

**QR code** — `tools/generate_qrcode.py` : visuel avec photo, titre,
chiffres clés et QR code stylé (modules arrondis vert forêt, repères
d'angle terracotta, emblème au centre). Le QR utilise la correction
d'erreur maximale pour rester lisible malgré l'emblème ; si OpenCV est
installé (`pip install opencv-python-headless`), le script vérifie qu'il
se relit bien. Testez-le tout de même avec un téléphone avant une
impression.

```bash
python3 tools/generate_qrcode.py rides/tour-du-pic-saint-loup                     # 1080×1080 -> qrcode.jpg
python3 tools/generate_qrcode.py rides/tour-du-pic-saint-loup --format affiche    # 1080×1350
python3 tools/generate_qrcode.py rides/tour-du-pic-saint-loup --plain             # QR seul, PNG 1200 px (impression)
python3 tools/generate_qrcode.py rides/tour-du-pic-saint-loup --utm               # + ?utm_source=qrcode (statistiques)
# n'importe quelle URL, textes en options (usage d'origine) :
python3 tools/generate_qrcode.py https://montpellier.cycloexplore.fr --title "Toutes nos sorties" --photos rides/clapiers-corconne/photos -o accueil.jpg
```

Les visuels autres que `instagram.jpg` (`instagram-story.jpg`,
`qrcode.jpg`…) sont ignorés par git : régénérez-les quand vous en avez
besoin.

### Tout enchaîner : `tools/new_ride.py`

Pour ajouter une sortie (ou rafraîchir une sortie existante), ce script
lance toutes les étapes dans l'ordre et affiche un récapitulatif :
préparation du dossier (copie du GPX et des photos, `description.md`
pré-rempli), contrôle du contenu (titre, synthèse, « ## Le parcours »,
difficulté, GPX, photos), POI (`find_supplies.py`, interactif), revêtement
(`surface_stats.py`), pentes (`slope_colors.py`), visuels Instagram et QR
code, puis génération du site en local.

```bash
# nouvelle sortie
python3 tools/new_ride.py tour-du-pic --gpx ~/Téléchargements/trace.gpx --photos ~/Photos/pic/

# sortie existante, sans question ni accès réseau
python3 tools/new_ride.py rides/clapiers-corconne --yes --no-network

# seulement certaines étapes, ou en sauter
python3 tools/new_ride.py rides/clapiers-corconne --only pentes,instagram,qrcode
python3 tools/new_ride.py rides/clapiers-corconne --skip poi,surface
```

Une étape impossible (dépendance absente, pas de réseau, Go non installé)
est signalée et sautée sans bloquer les suivantes. Le code de sortie vaut
1 seulement si une étape échoue.

> Partage réel vers Instagram : il n'existe pas de lien web universel
> pour poster directement sur Instagram (contrairement à
> Facebook/WhatsApp/X). Le bouton **Instagram** utilise l'API de partage
> native du navigateur (`navigator.share`) quand elle est disponible —
> essentiellement sur mobile — ce qui ouvre le sélecteur de partage du
> téléphone avec Instagram parmi les options. Sur desktop, ou si cette
> API n'est pas disponible, le bouton télécharge simplement l'image :
> à vous de la partager depuis l'app Instagram.

## Colorisation des traces selon la pente

Sur la page d'une sortie, la trace est colorée selon la **pente locale** :
vert pour le plat (couleur par défaut), du bleu clair au bleu foncé pour
les descentes de plus en plus raides, et du jaune au rouge (jaune,
orangé, orange, rouge) pour les montées de plus en plus raides. Les
mêmes couleurs sont appliquées au **profil altimétrique**. Une légende
est affichée sous le profil, et survoler la trace ou le profil affiche
le point kilométrique et la pente du tronçon. Sur la carte d'accueil, chaque sortie garde au
contraire sa propre couleur.

Les pentes sont **pré-calculées** par `tools/slope_colors.py` (Python 3.8+,
bibliothèque standard uniquement, aucun accès réseau), qui écrit
`rides/<sortie>/slope.geojson` : un GeoJSON de tronçons (`LineString`),
chacun avec `slope_pct`, `start_km`, `end_km`, `ele_start`, `ele_end`,
`class`, `label` et `color`. Le navigateur se contente de l'afficher.

```bash
# (Re)générer toutes les sorties — à relancer après toute modification d'un GPX
python3 tools/slope_colors.py

# Une sortie précise
python3 tools/slope_colors.py rides/clapiers-corconne

# Vérifier que tout est à jour, sans rien écrire (code de sortie 1 sinon)
python3 tools/slope_colors.py --check

# Forcer la régénération (après avoir modifié les seuils, par exemple)
python3 tools/slope_colors.py --force
```

Le script ne touche jamais aux GPX. Il enregistre l'empreinte SHA-256 du
GPX dans le GeoJSON : si le GPX change sans que le script soit relancé, le
générateur Go le détecte, affiche un avertissement, et la fiche montre la
trace d'origine en couleur unie (repli également utilisé si le fichier
est absent ou ne se charge pas, avec un message dans la console du
navigateur). En CI, le script est relancé avant chaque build.

**Réglages** (en tête du script) : `SLOPE_CLASSES` (seuils, libellés,
couleurs), `SEGMENT_LENGTH_M` (100 m), `SMOOTHING_WINDOW_M` (150 m),
`MAX_MERGED_LENGTH_M`, `MIN_VALID_ELEVATION_RATIO`.

**Méthode et limites :** distance cumulée (haversine) ; altitudes
manquantes ou aberrantes interpolées ; altitude ré-échantillonnée tous les
10 m puis lissée par moyenne glissante sur 150 m (le bruit altimétrique
d'un point à l'autre donnerait sinon des pentes fantaisistes) ; pente
calculée sur des tronçons d'au moins 100 m ; tronçons consécutifs de même
classe fusionnés. Si moins de la moitié des points ont une altitude, la
trace est sortie en gris « Altitude indisponible » plutôt qu'avec de
fausses pentes. Les GPX Komoot actuels ont des altitudes issues d'un
modèle de terrain, assez régulières ; un enregistrement GPS brut est plus
bruité. Un mur très court (< 100 m) est lissé : c'est une indication de
l'effort, pas une mesure topographique.

## Fonds de carte et boutons des cartes

Les cartes (accueil et fiches) proposent plusieurs fonds, au choix dans
le menu « Fond de carte » (icône de calques, en haut à droite) ; le choix
est mémorisé d'une page à l'autre dans le navigateur :

| Fond            | Source                                   | Intérêt                                         |
|-----------------|------------------------------------------|-------------------------------------------------|
| Plan            | OpenStreetMap                             | fond général (par défaut)                        |
| Vélo            | CyclOSM                                   | pistes cyclables, revêtements, chemins           |
| Relief          | OpenTopoMap                               | courbes de niveau, ombrage du relief             |
| IGN             | Plan IGN (Géoplateforme, sans clé)        | cartographie française détaillée                 |
| Photo aérienne  | Orthophotos IGN (Géoplateforme, sans clé) | repérer pistes et chemins vus du ciel            |

Les boutons de zoom, « Me localiser » et « Fond de carte » partagent le
même style (pastilles claires, icônes, survol terracotta).

Sur la fiche d'une sortie, le bouton **Plein écran** (sous « Me
localiser ») agrandit la carte à tout l'écran, recadrée sur la trace,
pour la parcourir confortablement ; Échap ou le même bouton en sortent.
Il utilise le mode plein écran du navigateur, et sur les appareils qui ne
le permettent pas pour un élément (iPhone), la carte occupe tout l'écran
de la page. La visionneuse 360° et l'agrandissement des photos restent
accessibles en plein écran.

## En-tête et bandeau d'accueil

L'en-tête (fixe en haut de l'écran) affiche l'emblème du logo
(`internal/site/static/logo-mark.png`, extrait de `logo_withouttext.png`),
le nom et la devise « Sorties vélo · Aventure · Partage », ainsi qu'une
navigation vers la carte et la liste des sorties. Sur l'accueil, un
bandeau reprend en fond la photo de couverture de la sortie la plus
récente, avec le titre du site et les chiffres clés (nombre de sorties,
kilomètres et dénivelé cumulés), calculés automatiquement.

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

## Version en pied de page

Chaque page affiche, tout en bas, une ligne discrète avec la date et
l'heure de génération (UTC) — utile pour vérifier rapidement si un
déploiement a bien pris en compte vos derniers changements :

```
Site généré le 15/08/2026 à 14:32 UTC
```

En CI, le SHA court du commit est ajouté automatiquement à la suite
(`... UTC · a1b2c3d`), via `-version`. En local (`go run`, Docker), cette
option n'est pas renseignée par défaut : seule la date apparaît. Vous
pouvez la préciser vous-même si besoin :

```bash
go run ./cmd/generator -version "test-local"
```

## Statistiques (Umami)

Le script [Umami](https://umami.is/) est inséré sur toutes les pages via
`-umami-id`, déjà réglé par défaut sur l'identifiant du site
(`9e97164b-65cd-4fef-82f2-f08b105783d3`) — rien à faire pour l'activer.

```bash
# Utiliser un autre identifiant
go run ./cmd/generator -umami-id "autre-identifiant"

# Désactiver (aucun script inséré)
go run ./cmd/generator -umami-id ""
```

En CI, surchargeable sans toucher au workflow via une variable de dépôt
**`UMAMI_ID`** (*Settings → Secrets and variables → Actions → Variables*),
selon le même principe que `SITE_URL`.

Les builds locaux (`Dockerfile`, `docker-compose.yml`) désactivent déjà le
tracking (`-umami-id ""`) pour ne pas polluer les statistiques avec des
visites de test — seul le build via la CI (déploiement réel) l'active.

## Référencement (SEO)

Tout est généré automatiquement à partir du contenu des sorties, rien à
saisir en plus :

- **Titres et descriptions** : `<title>` propre à chaque page (« Titre ·
  Cyclo Explore », accueil « Cyclo Explore — Sorties vélo & gravel autour
  de Montpellier ») ; meta description = synthèse de `description.md`
  (~150 caractères).
- **URL canoniques** : `<link rel="canonical">` sur chaque page, et tous
  les liens internes pointent vers la même forme (`/rides/<slug>/`, sans
  `index.html`) pour éviter les doublons.
- **Partage sur les réseaux** (Open Graph / Twitter) : titre, description,
  langue (`fr_FR`), image avec dimensions et texte alternatif — la
  première photo de la sortie, ou pour l'accueil celle de la sortie la plus
  récente —, date de publication et tags (`article:*`).
- **Données structurées** (JSON-LD schema.org) : accueil = Organisation +
  Site web + liste des sorties ; fiche = Article (auteur, éditeur, date,
  mots-clés, jusqu'à 3 photos, point de départ géolocalisé) + fil d'Ariane.
- **sitemap.xml** avec dates (format de date reconnu requis) et photos de
  chaque sortie ; **robots.txt** qui le référence.
- **Page 404** (`404.html`, servie par GitHub Pages) non indexée, avec un
  lien vers les sorties.
- Pages statiques, une seule balise `h1` par page, attribut `lang="fr"`,
  textes alternatifs des photos, images allégées et miniatures.

Après la mise en ligne, déclarez le sitemap
(`https://montpellier.cycloexplore.fr/sitemap.xml`) dans Google Search
Console et Bing Webmaster Tools.

## Partage (Facebook, WhatsApp, X, e-mail) et aperçu d'image

Chaque page de sortie affiche automatiquement des boutons de partage
(Facebook, X, WhatsApp, e-mail, « Copier le lien » avec confirmation, et
« Partager… » via le partage natif du navigateur quand il est disponible,
essentiellement sur mobile) ainsi que le téléchargement du GPX — rien à
faire dans `description.md`. Ça repose sur l'URL publique du
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
dossier `photos/` de la sortie. La description d'aperçu (et la meta
description) est la synthèse de `description.md`, à défaut un court
résumé (distance, dénivelé, difficulté).

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
go run ./cmd/generator -rides ./rides -footer ./content/footer.md -legal ./content/mentions-legales.md -site-url "https://montpellier.cycloexplore.fr" -umami-id "9e97164b-65cd-4fef-82f2-f08b105783d3" -out ./public -title "Cyclo Explore"
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

## Tests

```bash
go vet ./... && go test ./...                          # générateur Go
python3 -m unittest discover -s tools -p "test_*.py"   # script des pentes
```

Les deux sont aussi exécutés par la CI avant chaque déploiement.

## Architecture

- **Générateur Go sans dépendance** : lit `rides/`, calcule les données
  dérivées (synthèse, durée, difficulté normalisée, couleur, PK des POI,
  profil), publie photos + miniatures, GPX d'origine et `slope.geojson`,
  puis rend les gabarits `html/template`. Toutes les pages sont statiques
  et indexables (titres, meta description issue de la synthèse, Open
  Graph, JSON-LD, sitemap).
- **Accueil** : la carte Leaflet reçoit les traces simplifiées (≤ 300
  points) directement intégrées à la page en JSON — aucun GPX téléchargé ;
  les cartouches sont du HTML classique. `script.js` synchronise filtres,
  carte et cartouches.
- **Fiche** : un seul fichier de trace téléchargé (`slope.geojson`, ou le
  GPX en repli). Le profil altimétrique est un SVG généré au build.
- **Couleurs stables** : chaque sortie vise la couleur désignée par un hash
  de son slug dans une palette de 12 couleurs contrastées, et prend la
  suivante libre si elle est prise ; les sorties sont servies de la plus
  ancienne à la plus récente, donc ajouter une sortie ne change pas les
  couleurs existantes. Le champ `color` permet d'imposer une couleur.
- **Bibliothèque externe** (CDN) : Leaflet 1.9.4 uniquement. Le plugin
  leaflet-gpx n'est plus nécessaire (la trace est lue en GeoJSON, ou le
  GPX analysé directement en repli), ni le composant
  `@panoramax/web-viewer` : les vues 360° s'ouvrent dans l'interface web
  officielle de Panoramax, en iframe.

## Structure du projet

```
cmd/generator/        point d'entrée (main.go)
internal/site/         logique du générateur (frontmatter, markdown, gpx, build)
internal/site/meta.go     synthèse, difficulté, durée, dates, couleurs des sorties
internal/site/slope.go    lecture/vérification de slope.geojson
internal/site/homemap.go  données de la carte d'accueil
internal/site/images.go   réduction des photos et miniatures
internal/site/templates/  gabarits HTML (mise en forme, à ne modifier que si besoin)
internal/site/static/     CSS et JavaScript du site
content/footer.md      pied de page, modifiable
content/mentions-legales.md  page mentions légales, modifiable
rides/                  une sortie = un dossier
.github/workflows/     CI de build + déploiement GitHub Pages
Dockerfile              build + service du site via nginx (voir ci-dessus)
docker-compose.yml      boucle de dev : régénération + aperçu local
tools/find_supplies.py  recherche interactive de POI utiles (OSM)
tools/surface_stats.py  estimation du revêtement, écrit dans description.md (OSM)
tools/make_instagram_image.py  visuels Instagram (post, story, carré)
tools/generate_qrcode.py  visuel QR code (et QR seul pour l'impression)
tools/brand.py          charte graphique et lecture des sorties, partagées par les visuels
tools/new_ride.py       enchaîne tous les scripts pour ajouter une sortie
tools/fonts/            polices Fraunces et Inter (licence OFL)
tools/requirements.txt  dépendances Python des visuels (Pillow, segno)
tools/slope_colors.py   colorisation des traces selon la pente (écrit slope.geojson)
```

Vous n'avez normalement besoin de toucher qu'à `rides/`,
`content/footer.md` et `content/mentions-legales.md` — le reste s'occupe
de la mise en forme.
