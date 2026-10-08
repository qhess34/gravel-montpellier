# AGENTS.md

Instructions pour les assistants IA (Claude Code, Codex, Copilot…) qui
travaillent sur ce dépôt. Le contexte détaillé est dans
[docs/DEVELOPPEMENT.md](docs/DEVELOPPEMENT.md). Lisez la section
concernée avant de modifier une partie que vous ne connaissez pas. Le
[README](README.md) documente l'usage du site (format des sorties,
scripts).

## Le projet en bref

Cyclo Explore est un site statique de sorties gravel et vélo autour de
Montpellier.
- **Générateur** : Go 1.22, bibliothèque standard uniquement
  (`cmd/generator`, `internal/site`). Il lit `rides/<slug>/` et écrit
  `public/`.
- **Front** : `internal/site/static/script.js` (JS vanilla, fonctions
  exposées en `window.gm*`) et `style.css`, embarqués via `go:embed`,
  avec Leaflet 1.9.4 depuis unpkg.
- **Scripts** : `tools/*.py`, lancés à la main ou par la CI.
- **Déploiement** : GitHub Actions vers GitHub Pages, à chaque push sur
  `main` seulement.

## Commandes

```bash
go run ./cmd/generator                                   # génère public/
go vet ./... && go test ./...                            # tests Go
python3 -m unittest discover -s tools -p "test_*.py"     # tests Python
python3 tools/slope_colors.py --check                    # slope.geojson à jour ?
node --check internal/site/static/script.js              # syntaxe JS
python3 -m http.server -d public 8080                    # aperçu local
```

Lancez les tests Go et Python avant chaque commit. **La CI ne tourne pas
sur les PR**, elle ne tourne qu'après le merge sur `main` : un test rouge
casse donc directement le déploiement.

## Règles impératives

1. **Ne jamais inventer de données** : distances, dénivelés, POI,
   coordonnées, horaires, descriptions, photos. Ce qui n'est pas dans les
   fichiers d'une sortie n'est pas affiché. En cas de doute, demandez.
2. **Aucune dépendance Go externe** : `go.mod` doit rester sans `require`.
3. **Aucun outil de build front** : pas de npm, bundler ni framework. Une
   nouvelle bibliothèque front ne s'ajoute qu'avec l'accord explicite du
   propriétaire, depuis un CDN, avec une version épinglée.
4. **Ne pas modifier le contenu des sorties** (`rides/*/description.md`,
   `points.md`, GPX, photos) sauf demande explicite. Les fichiers GPX
   d'origine ne sont jamais modifiés.
5. **Ne pas modifier `public/`** : c'est la sortie du générateur, écrasée
   à chaque build.
6. **Français partout** : interface, messages du générateur, commentaires
   et messages de commit. Gardez le style des commits existants
   (« Zone : ce qui change », par exemple « Cartes : choix du fond de
   carte »).
7. **Un commit par fonctionnalité**, sur une branche dédiée, puis une PR
   vers `main`. Ne poussez jamais directement sur `main`.
8. **Fonds de carte et API externes** : toujours afficher l'attribution
   exigée. Pas de téléchargement en masse de tuiles. Pas de service
   nécessitant une clé sans accord du propriétaire.

## Conventions de code

- **Go** : `gofmt` sur le code que vous écrivez. Quelques fichiers
  existants ne sont pas encore formatés : ne reformatez pas un fichier
  entier dans un commit sans rapport. Commentaires en français au-dessus de chaque fonction,
  expliquant le *pourquoi*. Les données passées au JS sont produites avec
  `json.Marshal` puis typées `template.JS`. N'utilisez jamais
  `template.HTML` ou `template.JS` sur du texte non échappé.
- **JS** : ES5 compatible (`var`, `function`), pas de modules. Préfixez
  toute nouvelle fonction globale par `gm` et exposez-la sur `window`
  seulement si un gabarit l'appelle. Entourez chaque accès à
  `localStorage` d'un `try/catch`.
- **CSS** : utilisez les variables de `:root` (`--cream`, `--ink`,
  `--terracotta`, `--olive`, `--pano`…). Préfixez par `body` les règles
  qui restylent Leaflet, car `leaflet.css` est chargé après `style.css`.
  Mobile d'abord : vérifiez à environ 375 px de large.
- **Python** : bibliothèque standard pour les scripts lancés par la CI
  (`slope_colors.py`). Pillow et segno sont permis pour les visuels
  seulement (`tools/requirements.txt`). Interface et messages en français.

## Logique dupliquée à garder synchronisée

| Sujet | Emplacements |
|---|---|
| Couleurs de la charte | `style.css` (`:root`, `.diff-dot--*`) ↔ `tools/brand.py` |
| Durée et difficulté d'une sortie | `internal/site/meta.go` ↔ `tools/brand.py` (testé par `test_duration_same_rules_as_site`) |
| Classes et couleurs de pente | `tools/slope_colors.py` (`SLOPE_CLASSES`) seulement. Le site les lit dans `slope.geojson` ; relancer `slope_colors.py --force` après un changement |
| Types de POI | `points.go` (`poiKindOrder`, `poiKindSingular`) ↔ `style.css` (`.gm-marker--<type>`) ↔ `tools/find_supplies.py` |
| Fonds de carte | `script.js` (`GM_BASEMAPS`) pour le site, `tools/brand.py` (`TILE_PROVIDERS`) pour les visuels |

Quand vous modifiez un comportement visible, mettez aussi à jour la
section correspondante du README et, si l'architecture change,
`docs/DEVELOPPEMENT.md`.

## Vérifier un changement front

Il n'y a pas de tests navigateur dans le dépôt. Après une modification de
`script.js`, `style.css` ou d'un gabarit :
1. générez le site et servez `public/` ;
2. vérifiez l'accueil et au moins une fiche, sur ordinateur et à la
   largeur d'un mobile (Playwright est utilisable pour automatiser) ;
3. sur l'accueil, contrôlez la carte, les filtres, les popups et le rail
   de cartouches ;
4. sur la fiche, contrôlez la carte, le profil et son survol, les POI, le
   plein écran, les fonds de carte, le carrousel et Panoramax ;
5. ouvrez la console du navigateur : elle ne doit afficher aucune erreur.

## Environnement

- Le build interroge l'API Panoramax pour certains points. Sans réseau,
  ces points sont ignorés avec un avertissement, sans erreur.
- Les serveurs de tuiles et l'API Overpass peuvent être inaccessibles en
  sandbox. Dites-le explicitement si un rendu n'a pas pu être vérifié
  avec de vraies données.

## Pièges connus

Voir la section 10 de `docs/DEVELOPPEMENT.md`. En résumé :
- `waytype.go` n'est pas appelé ;
- `public/static/style.css` est versionné par erreur ;
- le Markdown et le lecteur EXIF sont faits maison et limités ;
- le plein écran sur iPhone passe par un repli CSS ;
- n'appelez `map.getCenter()` qu'après `map._loaded`.
