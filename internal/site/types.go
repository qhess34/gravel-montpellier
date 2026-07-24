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

	Body template.HTML // description au format HTML (convertie depuis markdown)

	HasGPX    bool
	GPXPoints []GPXPoint
	GPXFile   string // chemin relatif du fichier gpx copié dans la sortie (ex: gpx/track.gpx)

	StartPoint GPXPoint // premier point de la trace (départ)
	EndPoint   GPXPoint // dernier point de la trace (arrivée)
	IsLoop     bool     // true si départ et arrivée sont au même endroit (à ~50 m près)

	ElevationProfileSVG template.HTML // profil altimétrique, rendu en SVG
	HasElevationProfile bool

	Photos []string // chemins relatifs des photos copiées (ex: photos/1.jpg)

	Points       []Point // POI, photos géolocalisées et points panoramax (points.md)
	HasPanoramax bool    // true si au moins un Point de type panoramax
	Supplies     []Point // points d'eau et boulangeries (icon water/food), triés par PK croissant

	OutDir string // nom du dossier de sortie, ex: rides/<slug>/
}

// Site regroupe tout ce qui est nécessaire pour générer les pages.
type Site struct {
	Title  string
	Footer template.HTML
	Rides  []*Ride
}
