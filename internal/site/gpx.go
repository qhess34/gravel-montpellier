package site

import (
	"encoding/xml"
	"math"
	"os"
)

type gpxFile struct {
	XMLName xml.Name  `xml:"gpx"`
	Tracks  []gpxTrk  `xml:"trk"`
	Routes  []gpxRte  `xml:"rte"`
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
	const earthRadiusKm = 6371.0
	total := 0.0
	for i := 1; i < len(points); i++ {
		a, b := points[i-1], points[i]
		lat1, lon1 := degToRad(a.Lat), degToRad(a.Lon)
		lat2, lon2 := degToRad(b.Lat), degToRad(b.Lon)

		dLat := lat2 - lat1
		dLon := lon2 - lon1

		h := math.Sin(dLat/2)*math.Sin(dLat/2) +
			math.Cos(lat1)*math.Cos(lat2)*math.Sin(dLon/2)*math.Sin(dLon/2)
		c := 2 * math.Atan2(math.Sqrt(h), math.Sqrt(1-h))

		total += earthRadiusKm * c
	}
	return total
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
