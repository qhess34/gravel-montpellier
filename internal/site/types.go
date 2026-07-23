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

	Photos []string // chemins relatifs des photos copiées (ex: photos/1.jpg)

	OutDir string // nom du dossier de sortie, ex: rides/<slug>/
}

// Site regroupe tout ce qui est nécessaire pour générer les pages.
type Site struct {
	Title  string
	Footer template.HTML
	Rides  []*Ride
}
