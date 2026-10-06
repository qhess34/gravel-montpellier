package site

import (
	"encoding/json"
	"fmt"
	"html"
	"html/template"
	"math"
	"strings"
)

type profilePoint struct {
	Km  float64
	Ele float64
	Lat float64
	Lon float64
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

	build := func(idx int) profilePoint {
		p := track[idx]
		return profilePoint{Km: cum[idx], Ele: p.Ele, Lat: p.Lat, Lon: p.Lon}
	}

	if len(track) <= maxPoints || maxPoints < 2 {
		profile := make([]profilePoint, len(track))
		for i := range track {
			profile[i] = build(i)
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
		profile = append(profile, build(idx))
	}
	return profile
}

const (
	profileWidth  = 800.0
	profileHeight = 170.0
	profilePadL   = 42.0
	profilePadR   = 16.0
	profilePadTop = 16.0
	profilePadBot = 26.0
)

// renderElevationProfileSVG construit le profil altimétrique en SVG pur,
// coloré tronçon par tronçon selon la pente (mêmes couleurs que la carte)
// quand slope.geojson est disponible, avec des repères pour les points d'eau/boulangeries (survol = info-bulle
// native via <title>). Les dimensions et échelles du graphique sont
// exposées en attributs data-* pour que le JS (survol synchronisé avec la
// carte) puisse les réutiliser sans les dupliquer.
func renderElevationProfileSVG(profile []profilePoint, pois []Point, segments []slopeSegment) template.HTML {
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
	// Le SVG est enveloppé dans un conteneur qui porte aussi, en HTML, les
	// icônes cliquables des POI et l'info-bulle de survol : positionnés en %
	// par-dessus le graphique, ils gardent leur taille quelle que soit la
	// largeur d'écran (contrairement à des éléments dessinés dans le SVG).
	b.WriteString(`<div class="elevation-chart">`)
	fmt.Fprintf(&b, `<svg class="elevation-profile" viewBox="0 0 %.0f %.0f" preserveAspectRatio="none" role="img" aria-label="Profil altimétrique, survolez pour repérer la position sur la carte"`, profileWidth, profileHeight)
	fmt.Fprintf(&b, ` data-width="%.0f" data-height="%.0f" data-pad-l="%.0f" data-pad-r="%.0f" data-pad-top="%.0f" data-pad-bot="%.0f" data-min-ele="%.2f" data-max-ele="%.2f">`,
		profileWidth, profileHeight, profilePadL, profilePadR, profilePadTop, profilePadBot, minEle, maxEle)

	fmt.Fprintf(&b, `<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" class="elevation-axis"/>`, profilePadL, yBase, profileWidth-profilePadR, yBase)
	fmt.Fprintf(&b, `<text x="4" y="%.1f" class="elevation-label">%.0f m</text>`, y(maxEle)+4, maxEle)
	fmt.Fprintf(&b, `<text x="4" y="%.1f" class="elevation-label">%.0f m</text>`, yBase+4, minEle)

	if len(segments) > 0 {
		writeSlopeProfile(&b, profile, segments, totalKm, x, y, yBase)
	} else {
		fmt.Fprintf(&b, `<path d="%s" class="elevation-area"/>`, areaPath)
		fmt.Fprintf(&b, `<path d="%s" class="elevation-line" fill="none"/>`, linePath)
	}

	step := niceKmStep(totalKm)
	lastLabelKm := -step
	for km := 0.0; km <= totalKm+0.001; km += step {
		fmt.Fprintf(&b, `<text x="%.1f" y="%.1f" class="elevation-label elevation-label--km">%.0f</text>`, x(km), profileHeight-4, km)
		lastLabelKm = km
	}
	if totalKm-lastLabelKm > step*0.3 {
		fmt.Fprintf(&b, `<text x="%.1f" y="%.1f" class="elevation-label elevation-label--km elevation-label--end">%.0f</text>`, x(totalKm), profileHeight-4, totalKm)
	}

	// Ligne + point de survol, positionnés dynamiquement par script.js
	// (gmInitProfileHover) ; masqués tant qu'aucun survol n'a eu lieu.
	fmt.Fprintf(&b, `<line class="elevation-hover-line" y1="%.1f" y2="%.1f" style="display:none"/>`, profilePadTop, profileHeight-profilePadBot)
	b.WriteString(`<circle class="elevation-hover-dot" r="5" style="display:none"/>`)
	b.WriteString(`</svg>`)

	// POI : icône cliquable (centre la carte sur le point et ouvre sa popup).
	for _, s := range pois {
		label := html.EscapeString(fmt.Sprintf("%s — PK %s km", s.Label, formatKmFR(s.KmMark)))
		icon := html.EscapeString(s.Icon)
		fmt.Fprintf(&b, `<button type="button" class="elevation-poi poi-icon poi-icon--%s elevation-marker--%s" data-poi-id="%d" style="left:%.2f%%;top:%.2f%%" title="%s" aria-label="%s"></button>`,
			icon, icon, s.ID, x(s.KmMark)/profileWidth*100, y(elevationAt(profile, s.KmMark))/profileHeight*100, label, label)
	}
	b.WriteString(`<div class="elevation-tooltip" aria-hidden="true" hidden></div>`)
	b.WriteString(`</div>`)
	return template.HTML(b.String())
}

// writeSlopeProfile dessine le profil tronçon par tronçon : une aire
// translucide et une ligne de la couleur de pente de chaque tronçon.
func writeSlopeProfile(b *strings.Builder, profile []profilePoint, segments []slopeSegment, totalKm float64,
	x, y func(float64) float64, yBase float64) {
	for _, seg := range segments {
		start := math.Max(0, seg.StartKm)
		end := math.Min(totalKm, seg.EndKm)
		if end <= start {
			continue
		}
		var pts strings.Builder
		add := func(km float64) {
			if pts.Len() > 0 {
				pts.WriteByte(' ')
			}
			fmt.Fprintf(&pts, "%.1f,%.1f", x(km), y(elevationAt(profile, km)))
		}
		add(start)
		for _, p := range profile {
			if p.Km > start && p.Km < end {
				add(p.Km)
			}
		}
		add(end)
		line := pts.String()
		fmt.Fprintf(b, `<path d="M%.1f,%.1f L%s L%.1f,%.1f Z" class="elevation-seg-area" fill="%s"/>`,
			x(start), yBase, line, x(end), yBase, seg.Color)
		fmt.Fprintf(b, `<path d="M%s" class="elevation-seg-line" stroke="%s" fill="none"/>`, line, seg.Color)
	}
}

// formatKmFR formate un kilométrage avec une décimale et une virgule.
func formatKmFR(km float64) string {
	return strings.Replace(fmt.Sprintf("%.1f", km), ".", ",", 1)
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

type profileDataPoint struct {
	Km  float64 `json:"km"`
	Ele float64 `json:"ele"`
	Lat float64 `json:"lat"`
	Lon float64 `json:"lon"`
}

// elevationProfileDataJSON sérialise le profil (km, altitude, position) en
// JSON, pour que script.js puisse synchroniser le survol du graphique avec
// un marqueur sur la carte (et inversement).
func elevationProfileDataJSON(profile []profilePoint) template.JS {
	data := make([]profileDataPoint, len(profile))
	for i, p := range profile {
		data[i] = profileDataPoint{
			Km:  math.Round(p.Km*100) / 100,
			Ele: math.Round(p.Ele),
			Lat: math.Round(p.Lat*1e6) / 1e6,
			Lon: math.Round(p.Lon*1e6) / 1e6,
		}
	}
	b, err := json.Marshal(data)
	if err != nil {
		return "[]"
	}
	return template.JS(b)
}
