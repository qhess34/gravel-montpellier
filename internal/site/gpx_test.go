package site

import (
	"math"
	"testing"
)

// line renvoie une trace rectiligne vers l'est, à la latitude de
// Montpellier, avec un point tous les stepKm kilomètres.
func line(fromKm, toKm, stepKm float64) []GPXPoint {
	const lat = 43.6
	kmPerDegLon := 6371.0 * math.Pi / 180 * math.Cos(lat*math.Pi/180)
	var pts []GPXPoint
	if fromKm <= toKm {
		for k := fromKm; k <= toKm+1e-9; k += stepKm {
			pts = append(pts, GPXPoint{Lat: lat, Lon: 3.8 + k/kmPerDegLon})
		}
	} else {
		for k := fromKm; k >= toKm-1e-9; k -= stepKm {
			pts = append(pts, GPXPoint{Lat: lat, Lon: 3.8 + k/kmPerDegLon})
		}
	}
	return pts
}

func TestNearestKmProjectsBetweenPoints(t *testing.T) {
	track := line(0, 10, 2) // points tous les 2 km
	target := line(3, 3, 1)[0]
	target.Lat += 0.0001 // ~11 m au nord de la trace
	km, dist := NearestKm(track, target)
	if math.Abs(km-3) > 0.01 {
		t.Errorf("PK = %.3f km, attendu 3 km (projection sur le segment)", km)
	}
	if math.Abs(dist-0.0111) > 0.002 {
		t.Errorf("écart = %.4f km, attendu ~0,011 km", dist)
	}
}

func TestNearestPassagesOutAndBack(t *testing.T) {
	// aller de 0 à 10 km puis retour : le km 3 est longé deux fois,
	// à l'aller (PK 3) et au retour (PK 17)
	track := append(line(0, 10, 0.5), line(9.5, 0, 0.5)...)
	target := line(3, 3, 1)[0]
	target.Lat -= 0.0002
	kms, dist := NearestPassagesKm(track, target)
	if len(kms) != 2 || math.Abs(kms[0]-3) > 0.05 || math.Abs(kms[1]-17) > 0.05 {
		t.Fatalf("passages = %v, attendu [3 17]", kms)
	}
	if dist > 0.03 {
		t.Errorf("écart = %.3f km", dist)
	}
	if km, _ := NearestKm(track, target); km != kms[0] {
		t.Errorf("NearestKm = %.2f, attendu le premier passage %.2f", km, kms[0])
	}
}

func TestNearestPassagesLoopStartFinish(t *testing.T) {
	// boucle : départ et arrivée au même endroit, le point est au départ
	loop := append(line(0, 5, 0.5), line(5, 5, 1)[0])
	back := line(5, 0, 0.5)
	for i := range back {
		back[i].Lat += 0.02 // retour par une autre route (~2 km au nord)…
	}
	track := append(loop, back...)
	track = append(track, track[0]) // …qui rejoint le départ
	kms, _ := NearestPassagesKm(track, track[0])
	if len(kms) != 2 || kms[0] != 0 {
		t.Errorf("passages = %v, attendu le départ (0) et l'arrivée", kms)
	}
}

func TestNearestPassagesSingleWiggle(t *testing.T) {
	// un seul passage, même si la trace zigzague autour du point
	track := line(0, 4, 0.05)
	for i := range track {
		if i%2 == 1 {
			track[i].Lat += 0.0003 // zigzag de ~30 m
		}
	}
	kms, _ := NearestPassagesKm(track, line(2, 2, 1)[0])
	if len(kms) != 1 {
		t.Errorf("passages = %v, attendu un seul", kms)
	}
}

func TestNearestKmDistinctPassagesPicksClosest(t *testing.T) {
	// deux branches écartées de ~500 m : le point est clairement sur la seconde
	first := line(0, 5, 0.5)
	second := line(5, 0, 0.5)
	for i := range second {
		second[i].Lat += 0.0045 // ~500 m au nord
	}
	track := append(first, second...)
	target := second[4] // km 3 de la seconde branche (PK ~ 5 + 0,5 + 2)
	km, dist := NearestKm(track, target)
	if dist > 0.01 || km < 5 {
		t.Errorf("PK = %.2f km (écart %.3f km), attendu sur la seconde branche", km, dist)
	}
}

func TestNearestKmEdgeCases(t *testing.T) {
	if _, d := NearestKm(nil, GPXPoint{}); d != -1 {
		t.Errorf("trace vide : écart %v, attendu -1", d)
	}
	p := GPXPoint{Lat: 43.6, Lon: 3.8}
	if km, d := NearestKm([]GPXPoint{p}, p); km != 0 || d != 0 {
		t.Errorf("trace d'un point : km=%v écart=%v", km, d)
	}
}
