package site

import (
	"encoding/json"
	"encoding/xml"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestBuildSEO(t *testing.T) {
	out := t.TempDir()
	err := Build(Options{
		RidesDir: filepath.Join("..", "..", "rides"), OutDir: out, SiteTitle: "Cyclo Explore",
		SiteURL: "https://montpellier.cycloexplore.fr",
	})
	if err != nil {
		t.Fatal(err)
	}
	read := func(p string) string {
		b, err := os.ReadFile(filepath.Join(out, p))
		if err != nil {
			t.Fatal(err)
		}
		return string(b)
	}

	// Sitemap : XML valide, avec les photos.
	sitemap := read("sitemap.xml")
	if err := xml.Unmarshal([]byte(sitemap), new(struct{})); err != nil {
		t.Fatalf("sitemap invalide : %v", err)
	}
	if !strings.Contains(sitemap, "<image:loc>") || !strings.Contains(sitemap, "/rides/clapiers-corconne/</loc>") {
		t.Error("sitemap incomplet")
	}

	// Pages : JSON-LD valide, balises essentielles, liens canoniques.
	pages := []string{"index.html", "rides/clapiers-corconne/index.html", "mentions-legales.html"}
	for _, p := range pages {
		h := read(p)
		for _, tag := range []string{`<link rel="canonical"`, `<meta name="description"`, `og:locale`, `<html lang="fr">`} {
			if !strings.Contains(h, tag) {
				t.Errorf("%s : %s absent", p, tag)
			}
		}
		if strings.Contains(h, `/index.html"`) || strings.Contains(h, `href="index.html"`) {
			t.Errorf("%s : lien interne vers index.html (URL non canonique)", p)
		}
		if i := strings.Index(h, `application/ld+json">`); i >= 0 {
			j := strings.Index(h[i:], "</script>")
			var v interface{}
			if err := json.Unmarshal([]byte(h[i+len(`application/ld+json">`):i+j]), &v); err != nil {
				t.Errorf("%s : JSON-LD invalide : %v", p, err)
			}
		}
	}
	ride := read("rides/clapiers-corconne/index.html")
	for _, want := range []string{`og:image:width`, `article:published_time" content="2026-09-26"`, `"@type":"Article"`, `"GeoCoordinates"`, `"BreadcrumbList"`} {
		if !strings.Contains(ride, want) {
			t.Errorf("fiche : %s absent", want)
		}
	}
	home := read("index.html")
	if !strings.Contains(home, `"@type":"ItemList"`) || strings.Contains(home, "<title>Cyclo Explore · Cyclo Explore") {
		t.Error("accueil : ItemList absent ou titre en double")
	}
	if nf := read("404.html"); !strings.Contains(nf, `content="noindex"`) || !strings.Contains(nf, `href="/static/style.css"`) {
		t.Error("404 : noindex ou liens absolus manquants")
	}
}
