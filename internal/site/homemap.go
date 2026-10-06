package site

import (
	"encoding/json"
	"html/template"
	"math"
)

// homeMapMaxPoints : nombre maximal de points par trace sur la carte
// d'accueil. Les traces y sont vues de loin : quelques centaines de points
// suffisent et évitent de télécharger les GPX complets de toutes les sorties.
const homeMapMaxPoints = 300

// homeMapRide : données d'une sortie pour la carte d'accueil (trace + popup).
type homeMapRide struct {
	Slug       string       `json:"slug"`
	Title      string       `json:"title"`
	Color      string       `json:"color"`
	URL        string       `json:"url"`
	Thumb      string       `json:"thumb,omitempty"`
	Summary    string       `json:"summary,omitempty"`
	Difficulty string       `json:"difficulty,omitempty"`
	DiffKey    string       `json:"difficultyKey,omitempty"`
	Duration   string       `json:"duration,omitempty"`
	ElevationM int          `json:"elevation,omitempty"`
	DistanceKm float64      `json:"distance,omitempty"`
	Coords     [][2]float64 `json:"coords"`
}

// homeMapJSON sérialise, pour la carte d'accueil, la trace simplifiée et les
// informations de popup de chaque sortie ayant un GPX. Le JSON est intégré
// directement à la page (pas de requête supplémentaire) ; json.Marshal
// échappe <, > et &, ce qui le rend sûr dans une balise <script>.
func homeMapJSON(rides []*Ride, root string) template.JS {
	out := []homeMapRide{}
	for _, r := range rides {
		if !r.HasGPX || len(r.GPXPoints) < 2 {
			continue
		}
		item := homeMapRide{
			Slug:       r.Slug,
			Title:      r.Title,
			Color:      r.Color,
			URL:        root + "rides/" + r.Slug + "/index.html",
			Summary:    truncateText(r.SummaryText, 200),
			Difficulty: r.Difficulty,
			DiffKey:    r.DifficultyKey,
			Duration:   r.Duration,
			ElevationM: r.ElevationM,
			DistanceKm: math.Round(r.DistanceKm*10) / 10,
		}
		if len(r.PhotoThumbs) > 0 {
			item.Thumb = root + "rides/" + r.Slug + "/" + r.PhotoThumbs[0]
		}
		for _, p := range SimplifyForMap(r.GPXPoints, homeMapMaxPoints) {
			item.Coords = append(item.Coords, [2]float64{round5(p.Lat), round5(p.Lon)})
		}
		out = append(out, item)
	}
	b, err := json.Marshal(out)
	if err != nil {
		return "[]"
	}
	return template.JS(b)
}

func round5(v float64) float64 { return math.Round(v*1e5) / 1e5 }
