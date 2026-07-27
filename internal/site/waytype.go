package site

import (
	"encoding/json"
	"fmt"
	"math"
	"net/http"
	"net/url"
	"strings"
	"time"
)

// WayType catégorise le type de voie emprunté par un tronçon de la trace.
type WayType string

const (
	WayCycleway  WayType = "cycleway"   // piste cyclable
	WayMajorRoad WayType = "major_road" // grande route
	WayMinorRoad WayType = "minor_road" // petite route
	WayTrack     WayType = "track"      // piste agricole/forestière
	WayPath      WayType = "path"       // sentier
	WayUnknown   WayType = "unknown"    // pas de correspondance OSM à proximité
)

// classifyHighway déduit une WayType à partir de la valeur du tag highway=*.
func classifyHighway(highway string) WayType {
	switch highway {
	case "cycleway":
		return WayCycleway
	case "motorway", "motorway_link", "trunk", "trunk_link", "primary", "primary_link", "secondary", "secondary_link":
		return WayMajorRoad
	case "tertiary", "tertiary_link", "unclassified", "residential", "living_street", "service", "road":
		return WayMinorRoad
	case "track":
		return WayTrack
	case "path", "footway", "bridleway", "steps", "pedestrian":
		return WayPath
	default:
		return WayUnknown
	}
}

// SurfaceCategory regroupe les WayType en deux grandes familles pour les
// statistiques de revêtement : revêtu (route, piste cyclable) et non
// revêtu (chemin agricole/forestier, sentier).
type SurfaceCategory string

const (
	SurfacePaved   SurfaceCategory = "paved"
	SurfaceUnpaved SurfaceCategory = "unpaved"
	SurfaceUnknown SurfaceCategory = "unknown"
)

func surfaceCategory(t WayType) SurfaceCategory {
	switch t {
	case WayCycleway, WayMajorRoad, WayMinorRoad:
		return SurfacePaved
	case WayTrack, WayPath:
		return SurfaceUnpaved
	default:
		return SurfaceUnknown
	}
}

const overpassInterpreterURL = "https://overpass-api.de/api/interpreter"

// overpassMinInterval / lastOverpassCall : limite les appels à l'API
// Overpass à 1 par seconde environ sur l'ensemble du build (LoadRides
// traite les sorties séquentiellement, donc une simple variable de paquet
// suffit — pas d'accès concurrent).
const overpassMinInterval = 1200 * time.Millisecond

var lastOverpassCall time.Time

func waitForOverpass() {
	if !lastOverpassCall.IsZero() {
		if elapsed := time.Since(lastOverpassCall); elapsed < overpassMinInterval {
			time.Sleep(overpassMinInterval - elapsed)
		}
	}
	lastOverpassCall = time.Now()
}

type waySegmentGeom struct {
	Type   WayType
	Points []GPXPoint
}

// fetchWaySegments interroge Overpass pour récupérer, avec leur géométrie
// complète, les voies (highway=*) situées à moins de radiusM de la trace
// échantillonnée dans buffer.
func fetchWaySegments(buffer []GPXPoint, radiusM int) ([]waySegmentGeom, error) {
	waitForOverpass()

	var coords strings.Builder
	for i, p := range buffer {
		if i > 0 {
			coords.WriteByte(',')
		}
		fmt.Fprintf(&coords, "%.6f,%.6f", p.Lat, p.Lon)
	}
	query := fmt.Sprintf(`[out:json][timeout:60];way(around:%d,%s)[highway];out geom;`, radiusM, coords.String())

	form := url.Values{"data": {query}}
	req, err := http.NewRequest("POST", overpassInterpreterURL, strings.NewReader(form.Encode()))
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	req.Header.Set("User-Agent", "gravel-montpellier-generator/1.0 (build-time, voir README)")

	client := &http.Client{Timeout: 60 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("réponse %s de l'API Overpass", resp.Status)
	}

	var parsed struct {
		Elements []struct {
			Type     string            `json:"type"`
			Tags     map[string]string `json:"tags"`
			Geometry []struct {
				Lat float64 `json:"lat"`
				Lon float64 `json:"lon"`
			} `json:"geometry"`
		} `json:"elements"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&parsed); err != nil {
		return nil, fmt.Errorf("réponse Overpass illisible : %w", err)
	}

	var ways []waySegmentGeom
	for _, el := range parsed.Elements {
		if el.Type != "way" || len(el.Geometry) < 2 {
			continue
		}
		t := classifyHighway(el.Tags["highway"])
		if t == WayUnknown {
			continue // inutile de s'appuyer dessus pour l'appariement
		}
		pts := make([]GPXPoint, len(el.Geometry))
		for i, g := range el.Geometry {
			pts[i] = GPXPoint{Lat: g.Lat, Lon: g.Lon}
		}
		ways = append(ways, waySegmentGeom{Type: t, Points: pts})
	}
	return ways, nil
}

// wayMatchThresholdM : au-delà de cette distance (m) à la voie OSM la plus
// proche, un point de trace est considéré de type inconnu plutôt que d'être
// rattaché à une voie trop éloignée.
const wayMatchThresholdM = 25.0

// classifyTrackPoints renvoie, pour chaque point de track, le WayType de la
// voie la plus proche parmi ways (approximation plane, suffisante à cette
// échelle : quelques dizaines de mètres).
func classifyTrackPoints(track []GPXPoint, ways []waySegmentGeom) []WayType {
	if len(track) == 0 {
		return nil
	}
	refLat := track[len(track)/2].Lat
	const metersPerDegLat = 111320.0
	cosLat := math.Cos(refLat * math.Pi / 180)

	toXY := func(p GPXPoint) (float64, float64) {
		return p.Lon * metersPerDegLat * cosLat, p.Lat * metersPerDegLat
	}

	type xySeg struct {
		typ            WayType
		ax, ay, bx, by float64
	}
	var segs []xySeg
	for _, w := range ways {
		for i := 1; i < len(w.Points); i++ {
			ax, ay := toXY(w.Points[i-1])
			bx, by := toXY(w.Points[i])
			segs = append(segs, xySeg{w.Type, ax, ay, bx, by})
		}
	}

	types := make([]WayType, len(track))
	for i, p := range track {
		px, py := toXY(p)
		best := WayUnknown
		bestDist := wayMatchThresholdM
		for _, s := range segs {
			d := pointSegDistM(px, py, s.ax, s.ay, s.bx, s.by)
			if d < bestDist {
				bestDist = d
				best = s.typ
			}
		}
		types[i] = best
	}
	return types
}

func pointSegDistM(px, py, ax, ay, bx, by float64) float64 {
	dx, dy := bx-ax, by-ay
	if dx == 0 && dy == 0 {
		return math.Hypot(px-ax, py-ay)
	}
	t := ((px-ax)*dx + (py-ay)*dy) / (dx*dx + dy*dy)
	if t < 0 {
		t = 0
	} else if t > 1 {
		t = 1
	}
	cx, cy := ax+t*dx, ay+t*dy
	return math.Hypot(px-cx, py-cy)
}

// surfaceDistances calcule la distance (km) parcourue dans chaque catégorie
// de revêtement, à partir d'une trace et du WayType associé à chacun de ses
// points (types[i] qualifie le tronçon menant de track[i-1] à track[i]).
func surfaceDistances(track []GPXPoint, types []WayType) (paved, unpaved, unknown float64) {
	for i := 1; i < len(track); i++ {
		d := PointDistanceKm(track[i-1], track[i])
		switch surfaceCategory(types[i]) {
		case SurfacePaved:
			paved += d
		case SurfaceUnpaved:
			unpaved += d
		default:
			unknown += d
		}
	}
	return
}
