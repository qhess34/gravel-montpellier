package site

import (
	"image"
	"image/color"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestSplitSummary(t *testing.T) {
	body := "Intro **forte** avec un [lien](https://x.fr).\n\nDeuxième paragraphe.\n\n## Le parcours\n\nDétail.\n\n## Autre\n\nFin."
	summary, rest := splitSummary(body)
	if summary != "Intro **forte** avec un [lien](https://x.fr).\n\nDeuxième paragraphe." {
		t.Errorf("synthèse inattendue : %q", summary)
	}
	if !strings.HasPrefix(rest, "## Le parcours") || !strings.Contains(rest, "## Autre") {
		t.Errorf("suite inattendue : %q", rest)
	}
	if got := markdownToPlainText(summary); got != "Intro forte avec un lien. Deuxième paragraphe." {
		t.Errorf("texte brut inattendu : %q", got)
	}
}

func TestSplitSummaryFallbacks(t *testing.T) {
	// Pas de « ## Le parcours » : jusqu'au premier titre.
	s, r := splitSummary("Intro.\n\n## Itinéraire\n\nSuite.")
	if s != "Intro." || !strings.HasPrefix(r, "## Itinéraire") {
		t.Errorf("repli titre : %q / %q", s, r)
	}
	// Aucun titre : premier paragraphe.
	s, r = splitSummary("Premier.\n\nSecond.")
	if s != "Premier." || r != "Second." {
		t.Errorf("repli paragraphe : %q / %q", s, r)
	}
	// Délimiteur --- et titre en tête : pas de synthèse fantôme.
	s, _ = splitSummary("---\nIntro.\n---\n## Le parcours\nX")
	if s != "Intro." {
		t.Errorf("délimiteurs non retirés : %q", s)
	}
	s, r = splitSummary("## Le parcours\n\nTexte.")
	if s != "" || !strings.HasPrefix(r, "## Le parcours") {
		t.Errorf("titre en tête : %q / %q", s, r)
	}
}

func TestNormalizeDifficulty(t *testing.T) {
	cases := map[string]string{"Moyen": "moyenne", "Moyenne": "moyenne", "facile": "facile", "Difficile": "difficile", "Très difficile": "tres-difficile", "Engagé": "engage"}
	for in, want := range cases {
		got, ok := normalizeDifficulty(in)
		if !ok || got.Key != want {
			t.Errorf("%q -> %q, attendu %q", in, got.Key, want)
		}
	}
	if _, ok := normalizeDifficulty(" "); ok {
		t.Error("difficulté vide acceptée")
	}
}

func TestRideDuration(t *testing.T) {
	if d := rideDuration("4 h 30", []string{"1 jour"}); d != "4 h 30" {
		t.Errorf("champ duration ignoré : %q", d)
	}
	if d := rideDuration("", []string{"vue mer", "1 jour"}); d != "1 jour" {
		t.Errorf("1 jour : %q", d)
	}
	if d := rideDuration("", []string{"5 jours", "2 jours", "3 jours"}); d != "2 à 5 jours" {
		t.Errorf("plage : %q", d)
	}
	if d := rideDuration("", []string{"gravel"}); d != "" {
		t.Errorf("durée inventée : %q", d)
	}
}

func TestDateSortKey(t *testing.T) {
	cases := map[string]string{"26/09/2026": "2026-09-26", "2026-06-15": "2026-06-15", "15 juin 2026": "2026-06-15", "1er août 2026": "2026-08-01", "bientôt": "bientôt"}
	for in, want := range cases {
		if got := dateSortKey(in); got != want {
			t.Errorf("%q -> %q, attendu %q", in, got, want)
		}
	}
}

func TestAssignColorsStableAndDistinct(t *testing.T) {
	mk := func(slug, date string) *Ride { return &Ride{Slug: slug, SortKey: date} }
	rides := []*Ride{mk("a", "2026-01-01"), mk("b", "2026-02-01"), mk("c", "2026-03-01"), mk("d", "2026-04-01")}
	assignColors(rides)
	before := map[string]string{}
	seen := map[string]bool{}
	for _, r := range rides {
		if seen[r.Color] {
			t.Fatalf("couleur en double : %s", r.Color)
		}
		seen[r.Color] = true
		before[r.Slug] = r.Color
	}

	// Une nouvelle sortie, plus récente, ne change pas les couleurs existantes.
	again := []*Ride{mk("a", "2026-01-01"), mk("b", "2026-02-01"), mk("c", "2026-03-01"), mk("d", "2026-04-01"), mk("e", "2026-05-01")}
	assignColors(again)
	for _, r := range again[:4] {
		if r.Color != before[r.Slug] {
			t.Errorf("%s : couleur changée %s -> %s", r.Slug, before[r.Slug], r.Color)
		}
	}

	// Couleur imposée par le frontmatter.
	forced := []*Ride{{Slug: "x", Color: "#123456"}, mk("y", "")}
	assignColors(forced)
	if forced[0].Color != "#123456" || forced[1].Color == "#123456" {
		t.Errorf("couleur imposée mal gérée : %v %v", forced[0].Color, forced[1].Color)
	}
}

func TestResizeAndOrientation(t *testing.T) {
	src := image.NewRGBA(image.Rect(0, 0, 400, 200))
	src.Set(0, 0, color.RGBA{255, 0, 0, 255})
	small := resizeToFit(src, 100)
	if small.Bounds().Dx() != 100 || small.Bounds().Dy() != 50 {
		t.Fatalf("taille réduite inattendue : %v", small.Bounds())
	}
	rot := applyOrientation(small, 6) // rotation 90° horaire
	if rot.Bounds().Dx() != 50 || rot.Bounds().Dy() != 100 {
		t.Fatalf("rotation : %v", rot.Bounds())
	}
	if thumbRel("photos/a.jpg") != "photos/thumbs/a.jpg" {
		t.Error("chemin de miniature inattendu")
	}
}

func TestLoadSlopeDataDetectsStaleFile(t *testing.T) {
	dir := t.TempDir()
	gpx := filepath.Join(dir, "t.gpx")
	os.WriteFile(gpx, []byte("<gpx/>"), 0o644)
	sum, _ := fileSHA256(gpx)
	geo := `{"type":"FeatureCollection","source_sha256":"` + sum + `","legend":[{"key":"plat","label":"Plat","color":"#999"},{"key":"montee-forte","label":"Forte","color":"#f00"}],"features":[{"type":"Feature","properties":{"class":"plat"},"geometry":null}]}`
	os.WriteFile(filepath.Join(dir, slopeFileName), []byte(geo), 0o644)

	legend, _, ok := loadSlopeData("t", dir, gpx)
	if !ok || len(legend) != 1 || legend[0].Key != "plat" {
		t.Fatalf("fichier à jour non reconnu : %v %v", ok, legend)
	}
	os.WriteFile(gpx, []byte("<gpx>modifié</gpx>"), 0o644)
	if _, _, ok := loadSlopeData("t", dir, gpx); ok {
		t.Error("fichier obsolète accepté")
	}
	os.Remove(filepath.Join(dir, slopeFileName))
	if _, _, ok := loadSlopeData("t", dir, gpx); ok {
		t.Error("fichier absent accepté")
	}
}

func TestSlopeProfileUsesSegmentColors(t *testing.T) {
	profile := []profilePoint{{Km: 0, Ele: 10}, {Km: 1, Ele: 50}, {Km: 2, Ele: 20}}
	svg := string(renderElevationProfileSVG(profile, nil, []slopeSegment{{StartKm: 0, EndKm: 1, Color: "#dc2626"}, {StartKm: 1, EndKm: 2, Color: "#2563eb"}}))
	if !strings.Contains(svg, `stroke="#dc2626"`) || !strings.Contains(svg, `stroke="#2563eb"`) {
		t.Errorf("couleurs de pente absentes du profil : %s", svg)
	}
	plain := string(renderElevationProfileSVG(profile, nil, nil))
	if !strings.Contains(plain, "elevation-line") || strings.Contains(plain, "elevation-seg") {
		t.Error("profil sans pente : rendu uniforme attendu")
	}
}

func TestLoadRidesFromRepository(t *testing.T) {
	rides, err := LoadRides(filepath.Join("..", "..", "rides"))
	if err != nil {
		t.Fatal(err)
	}
	if len(rides) == 0 {
		t.Skip("aucune sortie")
	}
	for _, r := range rides {
		if r.SummaryText == "" {
			t.Errorf("%s : synthèse vide", r.Slug)
		}
		if strings.Contains(string(r.Body), "---") {
			t.Errorf("%s : délimiteur dans la description", r.Slug)
		}
		if r.Color == "" {
			t.Errorf("%s : pas de couleur", r.Slug)
		}
		for i := 1; i < len(r.RoutePOIs); i++ {
			if r.RoutePOIs[i].KmMark < r.RoutePOIs[i-1].KmMark {
				t.Errorf("%s : POI non triés", r.Slug)
			}
		}
	}
	for i := 1; i < len(rides); i++ {
		if rides[i].SortKey > rides[i-1].SortKey {
			t.Errorf("tri par date incorrect : %s avant %s", rides[i-1].SortKey, rides[i].SortKey)
		}
	}
}
