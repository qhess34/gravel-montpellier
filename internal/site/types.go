package site

import "html/template"

// GPXPoint représente un point de la trace GPS.
type GPXPoint struct {
	Lat float64
	Lon float64
	Ele float64
}

// Ride représente une sortie gravel, construite à partir du contenu
// du dossier rides/<slug>/.
type Ride struct {
	Slug       string
	Title      string
	DateRaw    string // date brute lisible, ex: "15 juin 2026"
	SortKey    string // clé de tri (AAAA-MM-JJ), déduite de la date si possible
	DistanceKm float64
	ElevationM int
	Difficulty string
	Departure  string
	Tags       []string
	TagsAttr   string // tags en minuscules, séparés par des virgules, pour le filtre côté client

	DifficultyKey   string // difficulté normalisée (facile, moyenne...), pour le filtre et la pastille de couleur
	DifficultyLevel int    // 1 (facile) à 4 (très difficile), 0 si inconnue
	Duration        string // durée : champ « duration » ou déduite des tags « N jour(s) » ; vide si inconnue
	Color           string // couleur de la trace sur la carte d'accueil (stable, voir assignColors)

	Summary     template.HTML // synthèse : début de description.md jusqu'à « ## Le parcours » (HTML)
	SummaryText string        // même synthèse en texte brut (cartouches, popups, meta description)
	Body        template.HTML // suite de la description (à partir de « ## Le parcours »), au format HTML

	HasGPX    bool
	GPXPoints []GPXPoint
	GPXFile   string // chemin relatif du fichier gpx copié dans la sortie (ex: gpx/track.gpx)

	StartPoint GPXPoint // premier point de la trace (départ)
	EndPoint   GPXPoint // dernier point de la trace (arrivée)
	IsLoop     bool     // true si départ et arrivée sont au même endroit (à ~50 m près)

	SurfacePavedKm    float64 // km estimés sur route/piste cyclable (revêtu)
	SurfaceUnpavedKm  float64 // km estimés sur chemin/sentier (non revêtu)
	SurfaceUnknownKm  float64 // km sans correspondance OSM fiable à proximité
	SurfacePavedPct   int
	SurfaceUnpavedPct int
	SurfaceUnknownPct int
	HasSurfaceStats   bool // true si la classification a produit un résultat exploitable

	ElevationProfileSVG      template.HTML // profil altimétrique, rendu en SVG
	ElevationProfileDataJSON template.JS   // [{km,ele,lat,lon}, ...] pour la synchro survol carte/profil
	HasElevationProfile      bool

	Photos      []string // chemins relatifs des photos copiées (ex: photos/1.jpg)
	PhotoThumbs []string // miniatures correspondantes (ex: photos/thumbs/1.jpg), même ordre que Photos

	HasSlope    bool         // true si slope.geojson (tools/slope_colors.py) existe et correspond au GPX
	SlopeFile   string       // chemin relatif du GeoJSON publié (ex: slope.geojson)
	SlopeLegend []SlopeClass // classes de pente présentes sur la trace, pour la légende
	SlopeJSON   template.JS  // tronçons [{s,e,c,p,l}] : pente affichée au survol du profil et de la carte

	Points       []Point // POI, photos géolocalisées et points panoramax (points.md)
	HasPanoramax bool    // true si au moins un Point de type panoramax
	RoutePOIs    []Point // POI de type "poi" situés sur le parcours (tous types), triés par PK croissant
	OffRoutePOIs []Point // POI de type "poi" trop loin de la trace pour avoir un PK

	POIKinds     []POIKind // types de points présents sur cette sortie, pour le filtre carte/profil
	HasPOIFilter bool      // true si au moins deux types différents sont présents

	HasInstagramImage bool // true si rides/<slug>/instagram.jpg existe (généré par tools/make_instagram_image.py)

	OutDir string // nom du dossier de sortie, ex: rides/<slug>/
}

// POIKind décrit un type de point pour la barre de filtre (icône + libellé).
type POIKind struct {
	Icon  string
	Label string
}

// Site regroupe tout ce qui est nécessaire pour générer les pages.
type Site struct {
	Title  string
	Footer template.HTML
	Rides  []*Ride
}
