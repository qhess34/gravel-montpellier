package site

import (
	"fmt"
	"html"
	"html/template"
	"math"
	"strings"
)

type profilePoint struct {
	Km  float64
	Ele float64
}

// buildElevationProfile ré-échantillonne la trace complète en au plus
// maxPoints points pour le tracé du profil, en conservant la distance
// cumulée réelle (calculée sur la trace complète, pas sur les points
// ré-échantillonnés) pour chaque point retenu.
func buildElevationProfile(track []GPXPoint, maxPoints int) []profilePoint {
	if len(track) == 0 {
		return nil
	}

	cum := make([]float64, len(track))
	for i := 1; i < len(track); i++ {
		cum[i] = cum[i-1] + PointDistanceKm(track[i-1], track[i])
	}

	if len(track) <= maxPoints || maxPoints < 2 {
		profile := make([]profilePoint, len(track))
		for i, p := range track {
			profile[i] = profilePoint{Km: cum[i], Ele: p.Ele}
		}
		return profile
	}

	stride := float64(len(track)-1) / float64(maxPoints-1)
	profile := make([]profilePoint, 0, maxPoints)
	for i := 0; i < maxPoints; i++ {
		idx := int(math.Round(float64(i) * stride))
		if idx >= len(track) {
			idx = len(track) - 1
		}
		profile = append(profile, profilePoint{Km: cum[idx], Ele: track[idx].Ele})
	}
	return profile
}

const (
	profileWidth  = 800.0
	profileHeight = 220.0
	profilePadL   = 42.0
	profilePadR   = 16.0
	profilePadTop = 16.0
	profilePadBot = 26.0
)

// renderElevationProfileSVG construit le profil altimétrique en SVG pur
// (aucun JavaScript ni dépendance externe), avec des repères pour les
// points d'eau et boulangeries situés sur le parcours (survol = info-bulle
// native via <title>).
func renderElevationProfileSVG(profile []profilePoint, supplies []Point) template.HTML {
	if len(profile) < 2 {
		return ""
	}

	totalKm := profile[len(profile)-1].Km
	if totalKm <= 0 {
		return ""
	}

	minEle, maxEle := profile[0].Ele, profile[0].Ele
	for _, p := range profile {
		if p.Ele < minEle {
			minEle = p.Ele
		}
		if p.Ele > maxEle {
			maxEle = p.Ele
		}
	}
	eleRange := maxEle - minEle
	if eleRange < 10 {
		eleRange = 10 // évite un graphe illisible si le profil est quasi plat
	}
	minEle -= eleRange * 0.08
	maxEle += eleRange * 0.08
	eleRange = maxEle - minEle

	chartW := profileWidth - profilePadL - profilePadR
	chartH := profileHeight - profilePadTop - profilePadBot

	x := func(km float64) float64 { return profilePadL + (km/totalKm)*chartW }
	y := func(ele float64) float64 { return profilePadTop + chartH - ((ele-minEle)/eleRange)*chartH }
	yBase := y(minEle)

	var pts strings.Builder
	for i, p := range profile {
		if i > 0 {
			pts.WriteByte(' ')
		}
		fmt.Fprintf(&pts, "%.1f,%.1f", x(p.Km), y(p.Ele))
	}
	pointsStr := pts.String()

	linePath := "M" + pointsStr
	areaPath := fmt.Sprintf("M%.1f,%.1f L%s L%.1f,%.1f Z", x(0), yBase, pointsStr, x(totalKm), yBase)

	var b strings.Builder
	fmt.Fprintf(&b, `<svg class="elevation-profile" viewBox="0 0 %.0f %.0f" preserveAspectRatio="none" role="img" aria-label="Profil altimétrique">`, profileWidth, profileHeight)

	fmt.Fprintf(&b, `<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" class="elevation-axis"/>`, profilePadL, yBase, profileWidth-profilePadR, yBase)
	fmt.Fprintf(&b, `<text x="4" y="%.1f" class="elevation-label">%.0f m</text>`, y(maxEle)+4, maxEle)
	fmt.Fprintf(&b, `<text x="4" y="%.1f" class="elevation-label">%.0f m</text>`, yBase+4, minEle)

	fmt.Fprintf(&b, `<path d="%s" class="elevation-area"/>`, areaPath)
	fmt.Fprintf(&b, `<path d="%s" class="elevation-line" fill="none"/>`, linePath)

	step := niceKmStep(totalKm)
	lastLabelKm := -step
	for km := 0.0; km <= totalKm+0.001; km += step {
		fmt.Fprintf(&b, `<text x="%.1f" y="%.1f" class="elevation-label elevation-label--km">%.0f</text>`, x(km), profileHeight-4, km)
		lastLabelKm = km
	}
	if totalKm-lastLabelKm > step*0.3 {
		fmt.Fprintf(&b, `<text x="%.1f" y="%.1f" class="elevation-label elevation-label--km elevation-label--end">%.0f</text>`, x(totalKm), profileHeight-4, totalKm)
	}

	for _, s := range supplies {
		cx := x(s.KmMark)
		cy := y(elevationAt(profile, s.KmMark))
		label := html.EscapeString(s.Label)
		fmt.Fprintf(&b, `<circle cx="%.1f" cy="%.1f" r="4.5" class="elevation-marker elevation-marker--%s"><title>%s (PK %.0f)</title></circle>`,
			cx, cy, s.Icon, label, s.KmMark)
	}

	b.WriteString(`</svg>`)
	return template.HTML(b.String())
}

// elevationAt renvoie l'altitude interpolée du profil à un kilométrage donné.
func elevationAt(profile []profilePoint, km float64) float64 {
	if len(profile) == 0 {
		return 0
	}
	if km <= profile[0].Km {
		return profile[0].Ele
	}
	for i := 1; i < len(profile); i++ {
		if profile[i].Km >= km {
			prev, cur := profile[i-1], profile[i]
			if cur.Km == prev.Km {
				return cur.Ele
			}
			t := (km - prev.Km) / (cur.Km - prev.Km)
			return prev.Ele + t*(cur.Ele-prev.Ele)
		}
	}
	return profile[len(profile)-1].Ele
}

// niceKmStep choisit un pas de graduation "rond" adapté à la longueur totale.
func niceKmStep(totalKm float64) float64 {
	switch {
	case totalKm <= 10:
		return 2
	case totalKm <= 25:
		return 5
	case totalKm <= 60:
		return 10
	case totalKm <= 120:
		return 20
	default:
		return 50
	}
}
