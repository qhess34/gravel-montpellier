package site

import (
	"encoding/xml"
	"math"
	"os"
)

type gpxFile struct {
	XMLName xml.Name `xml:"gpx"`
	Tracks  []gpxTrk `xml:"trk"`
	Routes  []gpxRte `xml:"rte"`
}

type gpxTrk struct {
	Segments []gpxSeg `xml:"trkseg"`
}

type gpxSeg struct {
	Points []gpxPt `xml:"trkpt"`
}

type gpxRte struct {
	Points []gpxPt `xml:"rtept"`
}

type gpxPt struct {
	Lat float64 `xml:"lat,attr"`
	Lon float64 `xml:"lon,attr"`
	Ele float64 `xml:"ele"`
}

// LoadGPX lit un fichier .gpx et renvoie la liste ordonnée des points.
// Il accepte aussi bien des traces (<trk>) que des itinéraires (<rte>).
func LoadGPX(path string) ([]GPXPoint, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}

	var g gpxFile
	if err := xml.Unmarshal(data, &g); err != nil {
		return nil, err
	}

	var points []GPXPoint
	for _, trk := range g.Tracks {
		for _, seg := range trk.Segments {
			for _, p := range seg.Points {
				points = append(points, GPXPoint{Lat: p.Lat, Lon: p.Lon, Ele: p.Ele})
			}
		}
	}
	if len(points) == 0 {
		for _, rte := range g.Routes {
			for _, p := range rte.Points {
				points = append(points, GPXPoint{Lat: p.Lat, Lon: p.Lon, Ele: p.Ele})
			}
		}
	}

	return points, nil
}

// DistanceKm calcule la distance totale (km) parcourue le long des points,
// via la formule de haversine entre points consécutifs.
func DistanceKm(points []GPXPoint) float64 {
	total := 0.0
	for i := 1; i < len(points); i++ {
		total += PointDistanceKm(points[i-1], points[i])
	}
	return total
}

// PointDistanceKm calcule la distance (km) entre deux points isolés,
// via la formule de haversine.
func PointDistanceKm(a, b GPXPoint) float64 {
	const earthRadiusKm = 6371.0

	lat1, lon1 := degToRad(a.Lat), degToRad(a.Lon)
	lat2, lon2 := degToRad(b.Lat), degToRad(b.Lon)

	dLat := lat2 - lat1
	dLon := lon2 - lon1

	h := math.Sin(dLat/2)*math.Sin(dLat/2) +
		math.Cos(lat1)*math.Cos(lat2)*math.Sin(dLon/2)*math.Sin(dLon/2)
	c := 2 * math.Atan2(math.Sqrt(h), math.Sqrt(1-h))

	return earthRadiusKm * c
}

// passToleranceKm : un passage de la trace compte s'il approche le point
// à moins de cette distance de plus que le passage le plus proche.
const passToleranceKm = 0.05

// minPassageGapKm : deux passages séparés de moins de cette distance le long
// de la trace sont confondus (zigzags GPS, lacets serrés).
const minPassageGapKm = 0.5

// NearestKm renvoie le "point kilométrique" de target sur track (premier
// passage, voir NearestPassagesKm) et l'écart (km) entre target et la trace.
func NearestKm(track []GPXPoint, target GPXPoint) (km float64, distanceToTrack float64) {
	kms, dist := NearestPassagesKm(track, target)
	if len(kms) == 0 {
		return 0, dist
	}
	return kms[0], dist
}

// NearestPassagesKm renvoie les points kilométriques (km depuis le départ,
// croissants) de chaque passage de la trace près de target, et l'écart (km)
// entre target et la trace — utile pour ignorer un point trop éloigné du
// parcours. Écart -1 si la trace est vide.
//
// target est projeté sur chaque segment de la trace (et pas seulement sur
// ses points), ce qui donne un PK précis même entre deux points espacés.
// Une trace peut passer plusieurs fois près d'un point : aller-retour,
// départ et arrivée au même endroit, tronçon emprunté deux fois. Chaque
// suite de segments dont l'écart reste à moins de passToleranceKm du plus
// petit écart forme un passage ; on en retient la position la plus proche.
func NearestPassagesKm(track []GPXPoint, target GPXPoint) (kms []float64, distanceToTrack float64) {
	if len(track) == 0 {
		return nil, -1
	}
	if len(track) == 1 {
		return []float64{0}, PointDistanceKm(track[0], target)
	}

	// Projection locale équirectangulaire centrée sur target (km) : assez
	// précise aux distances qui comptent ici (quelques kilomètres).
	const earthRadiusKm = 6371.0
	cosLat := math.Cos(degToRad(target.Lat))
	xy := func(p GPXPoint) (float64, float64) {
		return degToRad(p.Lon-target.Lon) * cosLat * earthRadiusKm, degToRad(p.Lat-target.Lat) * earthRadiusKm
	}

	n := len(track) - 1
	dists := make([]float64, n)  // écart de target à chaque segment
	alongs := make([]float64, n) // PK de la projection sur chaque segment
	cum, minDist := 0.0, math.Inf(1)
	for i := 1; i <= n; i++ {
		ax, ay := xy(track[i-1])
		bx, by := xy(track[i])
		dx, dy := bx-ax, by-ay
		t := 0.0
		if l2 := dx*dx + dy*dy; l2 > 0 {
			t = math.Max(0, math.Min(1, -(ax*dx+ay*dy)/l2))
		}
		segKm := PointDistanceKm(track[i-1], track[i])
		dists[i-1] = math.Hypot(ax+t*dx, ay+t*dy)
		alongs[i-1] = cum + t*segKm
		cum += segKm
		minDist = math.Min(minDist, dists[i-1])
	}

	// Passages : suites de segments sous le seuil ; pour chacun, la
	// position la plus proche.
	limit := minDist + passToleranceKm
	best := -1
	flush := func() {
		if best < 0 {
			return
		}
		if k := len(kms); k > 0 && alongs[best]-kms[k-1] < minPassageGapKm {
			best = -1 // trop près du passage précédent : le même passage
			return
		}
		kms = append(kms, alongs[best])
		best = -1
	}
	for i := 0; i < n; i++ {
		if dists[i] > limit {
			flush()
			continue
		}
		if best < 0 || dists[i] < dists[best] {
			best = i
		}
	}
	flush()
	return kms, minDist
}

// ElevationGainM additionne les montées positives entre points consécutifs (mètres).
func ElevationGainM(points []GPXPoint) int {
	gain := 0.0
	for i := 1; i < len(points); i++ {
		d := points[i].Ele - points[i-1].Ele
		if d > 0 {
			gain += d
		}
	}
	return int(math.Round(gain))
}

func degToRad(deg float64) float64 {
	return deg * math.Pi / 180
}

// SimplifyForMap réduit le nombre de points pour l'affichage carte (fichier plus léger côté navigateur)
// en gardant au maximum `max` points répartis régulièrement le long de la trace.
func SimplifyForMap(points []GPXPoint, max int) []GPXPoint {
	if max <= 0 || len(points) <= max {
		return points
	}
	stride := float64(len(points)) / float64(max)
	simplified := make([]GPXPoint, 0, max)
	for f := 0.0; int(f) < len(points); f += stride {
		simplified = append(simplified, points[int(f)])
	}
	// on s'assure de toujours garder le tout dernier point
	last := points[len(points)-1]
	if len(simplified) == 0 || simplified[len(simplified)-1] != last {
		simplified = append(simplified, last)
	}
	return simplified
}
