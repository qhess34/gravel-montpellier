package site

import (
	"encoding/json"
	"fmt"
	"html/template"
	"os"
	"path/filepath"
	"regexp"
	"strings"
)

var isoDateRe = regexp.MustCompile(`^\d{4}-\d{2}-\d{2}$`)

// isISODate signale une date au format AAAA-MM-JJ, seule forme assez fiable
// pour être publiée comme date structurée (datePublished, lastmod...).
func isISODate(s string) bool {
	return isoDateRe.MatchString(s)
}

// --- Sitemap & robots.txt ---------------------------------------------

// writeSitemap génère sitemap.xml (accueil, mentions légales, chaque
// sortie). Nécessite une URL absolue de site ; ne fait rien si baseURL
// est vide (un sitemap sans URLs absolues n'a pas de sens).
func writeSitemap(outDir, baseURL string, rides []*Ride) error {
	if baseURL == "" {
		return nil
	}

	var b strings.Builder
	b.WriteString(`<?xml version="1.0" encoding="UTF-8"?>` + "\n")
	b.WriteString(`<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">` + "\n")

	writeURL := func(loc, lastmod string) {
		b.WriteString("  <url>\n")
		fmt.Fprintf(&b, "    <loc>%s</loc>\n", strings.ReplaceAll(loc, "&", "&amp;"))
		if lastmod != "" {
			fmt.Fprintf(&b, "    <lastmod>%s</lastmod>\n", lastmod)
		}
		b.WriteString("  </url>\n")
	}

	writeURL(baseURL+"/", "")
	writeURL(baseURL+"/mentions-legales.html", "")
	for _, r := range rides {
		lastmod := ""
		if isISODate(r.SortKey) {
			lastmod = r.SortKey
		}
		writeURL(baseURL+"/rides/"+r.Slug+"/", lastmod)
	}

	b.WriteString(`</urlset>` + "\n")
	return os.WriteFile(filepath.Join(outDir, "sitemap.xml"), []byte(b.String()), 0o644)
}

// writeRobotsTxt génère robots.txt, en autorisant l'exploration complète
// du site et en pointant vers le sitemap si une URL de site est connue.
func writeRobotsTxt(outDir, baseURL string) error {
	var b strings.Builder
	b.WriteString("User-agent: *\nAllow: /\n")
	if baseURL != "" {
		fmt.Fprintf(&b, "\nSitemap: %s/sitemap.xml\n", baseURL)
	}
	return os.WriteFile(filepath.Join(outDir, "robots.txt"), []byte(b.String()), 0o644)
}

// --- Données structurées JSON-LD (schema.org) -------------------------

type ldArticle struct {
	Type          string   `json:"@type"`
	Headline      string   `json:"headline"`
	Description   string   `json:"description,omitempty"`
	Image         []string `json:"image,omitempty"`
	URL           string   `json:"url"`
	DatePublished string   `json:"datePublished,omitempty"`
}

type ldListItem struct {
	Type     string `json:"@type"`
	Position int    `json:"position"`
	Name     string `json:"name"`
	Item     string `json:"item"`
}

type ldBreadcrumbList struct {
	Type            string       `json:"@type"`
	ItemListElement []ldListItem `json:"itemListElement"`
}

type ldGraph struct {
	Context string        `json:"@context"`
	Graph   []interface{} `json:"@graph"`
}

type ldWebSite struct {
	Context string `json:"@context"`
	Type    string `json:"@type"`
	Name    string `json:"name"`
	URL     string `json:"url"`
}

// rideStructuredDataJSON construit le JSON-LD (Article + fil d'Ariane)
// d'une page de sortie. pageURL/imageURL/description sont déjà calculés
// côté appelant (mêmes valeurs que les balises Open Graph) pour éviter de
// dupliquer cette logique.
func rideStructuredDataJSON(ride *Ride, pageURL, imageURL, description, homeURL, siteTitle string) template.JS {
	article := ldArticle{
		Type:        "Article",
		Headline:    ride.Title,
		Description: description,
		URL:         pageURL,
	}
	if imageURL != "" {
		article.Image = []string{imageURL}
	}
	if isISODate(ride.SortKey) {
		article.DatePublished = ride.SortKey
	}

	breadcrumb := ldBreadcrumbList{
		Type: "BreadcrumbList",
		ItemListElement: []ldListItem{
			{Type: "ListItem", Position: 1, Name: siteTitle, Item: homeURL},
			{Type: "ListItem", Position: 2, Name: ride.Title, Item: pageURL},
		},
	}

	graph := ldGraph{
		Context: "https://schema.org",
		Graph:   []interface{}{article, breadcrumb},
	}

	b, err := json.Marshal(graph)
	if err != nil {
		return ""
	}
	return template.JS(b)
}

// websiteStructuredDataJSON construit le JSON-LD (WebSite) de la page d'accueil.
func websiteStructuredDataJSON(siteTitle, homeURL string) template.JS {
	site := ldWebSite{Context: "https://schema.org", Type: "WebSite", Name: siteTitle, URL: homeURL}
	b, err := json.Marshal(site)
	if err != nil {
		return ""
	}
	return template.JS(b)
}
