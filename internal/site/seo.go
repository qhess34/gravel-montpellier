package site

import (
	"encoding/json"
	"encoding/xml"
	"fmt"
	"html/template"
	"image"
	"net/url"
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
// sortie avec ses photos — extension « image » de Google). Nécessite une
// URL absolue de site ; ne fait rien si baseURL est vide (un sitemap sans
// URLs absolues n'a pas de sens).
func writeSitemap(outDir, baseURL string, rides []*Ride) error {
	if baseURL == "" {
		return nil
	}

	var b strings.Builder
	b.WriteString(`<?xml version="1.0" encoding="UTF-8"?>` + "\n")
	b.WriteString(`<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">` + "\n")

	esc := func(s string) string {
		var buf strings.Builder
		xml.EscapeText(&buf, []byte(s))
		return buf.String()
	}
	writeURL := func(loc, lastmod string, images []string) {
		b.WriteString("  <url>\n")
		fmt.Fprintf(&b, "    <loc>%s</loc>\n", esc(loc))
		if lastmod != "" {
			fmt.Fprintf(&b, "    <lastmod>%s</lastmod>\n", lastmod)
		}
		for _, img := range images {
			fmt.Fprintf(&b, "    <image:image><image:loc>%s</image:loc></image:image>\n", esc(img))
		}
		b.WriteString("  </url>\n")
	}

	// L'accueil change dès qu'une sortie est ajoutée : sa date est celle de
	// la sortie la plus récente.
	latest := ""
	for _, r := range rides {
		if isISODate(r.SortKey) && r.SortKey > latest {
			latest = r.SortKey
		}
	}
	writeURL(baseURL+"/", latest, nil)
	writeURL(baseURL+"/mentions-legales.html", "", nil)
	for _, r := range rides {
		lastmod := ""
		if isISODate(r.SortKey) {
			lastmod = r.SortKey
		}
		var images []string
		for _, p := range r.Photos {
			images = append(images, baseURL+"/rides/"+r.Slug+"/"+urlPathEscape(p))
		}
		writeURL(baseURL+"/rides/"+r.Slug+"/", lastmod, images)
	}

	b.WriteString(`</urlset>` + "\n")
	return os.WriteFile(filepath.Join(outDir, "sitemap.xml"), []byte(b.String()), 0o644)
}

// urlPathEscape encode chaque segment d'un chemin relatif (espaces, accents).
func urlPathEscape(p string) string {
	parts := strings.Split(p, "/")
	for i, s := range parts {
		parts[i] = url.PathEscape(s)
	}
	return strings.Join(parts, "/")
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

type ldRef struct {
	ID string `json:"@id"`
}

type ldImage struct {
	Type   string `json:"@type"`
	URL    string `json:"url"`
	Width  int    `json:"width,omitempty"`
	Height int    `json:"height,omitempty"`
}

type ldOrganization struct {
	Type string  `json:"@type"`
	ID   string  `json:"@id"`
	Name string  `json:"name"`
	URL  string  `json:"url"`
	Logo ldImage `json:"logo"`
}

type ldWebSite struct {
	Type        string `json:"@type"`
	ID          string `json:"@id"`
	Name        string `json:"name"`
	Description string `json:"description,omitempty"`
	URL         string `json:"url"`
	InLanguage  string `json:"inLanguage"`
	Publisher   ldRef  `json:"publisher"`
}

type ldGeo struct {
	Type      string  `json:"@type"`
	Latitude  float64 `json:"latitude"`
	Longitude float64 `json:"longitude"`
}

type ldPlace struct {
	Type string `json:"@type"`
	Name string `json:"name,omitempty"`
	Geo  *ldGeo `json:"geo,omitempty"`
}

type ldArticle struct {
	Type             string   `json:"@type"`
	ID               string   `json:"@id"`
	Headline         string   `json:"headline"`
	Description      string   `json:"description,omitempty"`
	Image            []string `json:"image,omitempty"`
	URL              string   `json:"url"`
	MainEntityOfPage string   `json:"mainEntityOfPage"`
	DatePublished    string   `json:"datePublished,omitempty"`
	DateModified     string   `json:"dateModified,omitempty"`
	InLanguage       string   `json:"inLanguage"`
	Keywords         string   `json:"keywords,omitempty"`
	Author           ldRef    `json:"author"`
	Publisher        ldRef    `json:"publisher"`
	IsPartOf         ldRef    `json:"isPartOf"`
	ContentLocation  *ldPlace `json:"contentLocation,omitempty"`
}

type ldListItem struct {
	Type     string `json:"@type"`
	Position int    `json:"position"`
	Name     string `json:"name"`
	Item     string `json:"item,omitempty"`
	URL      string `json:"url,omitempty"`
}

type ldBreadcrumbList struct {
	Type            string       `json:"@type"`
	ItemListElement []ldListItem `json:"itemListElement"`
}

type ldItemList struct {
	Type            string       `json:"@type"`
	Name            string       `json:"name"`
	NumberOfItems   int          `json:"numberOfItems"`
	ItemListElement []ldListItem `json:"itemListElement"`
}

type ldGraph struct {
	Context string        `json:"@context"`
	Graph   []interface{} `json:"@graph"`
}

// siteDescription : description générale du site (accueil, WebSite).
const siteDescription = "Itinéraires gravel et vélo autour de Montpellier : traces GPX, cartes, photos, profils et points d'intérêt de chaque sortie."

func organizationLD(siteTitle, homeURL string) ldOrganization {
	return ldOrganization{
		Type: "Organization", ID: homeURL + "#organization", Name: siteTitle, URL: homeURL,
		Logo: ldImage{Type: "ImageObject", URL: homeURL + "static/logo.png"},
	}
}

func websiteLD(siteTitle, homeURL string) ldWebSite {
	return ldWebSite{
		Type: "WebSite", ID: homeURL + "#website", Name: siteTitle, Description: siteDescription,
		URL: homeURL, InLanguage: "fr-FR", Publisher: ldRef{homeURL + "#organization"},
	}
}

func marshalLD(graph ldGraph) template.JS {
	b, err := json.Marshal(graph)
	if err != nil {
		return ""
	}
	return template.JS(b)
}

// rideStructuredDataJSON construit le JSON-LD d'une page de sortie : Article
// (auteur, éditeur, date, mots-clés, photos, lieu de départ géolocalisé) et
// fil d'Ariane. pageURL/imageURL/description sont déjà calculés côté
// appelant (mêmes valeurs que les balises Open Graph).
func rideStructuredDataJSON(ride *Ride, pageURL, imageURL, description, homeURL, siteTitle string) template.JS {
	org := ldRef{homeURL + "#organization"}
	article := ldArticle{
		Type:             "Article",
		ID:               pageURL + "#article",
		Headline:         ride.Title,
		Description:      description,
		URL:              pageURL,
		MainEntityOfPage: pageURL,
		InLanguage:       "fr-FR",
		Keywords:         strings.Join(append([]string{"gravel", "vélo", "Montpellier"}, ride.Tags...), ", "),
		Author:           org,
		Publisher:        org,
		IsPartOf:         ldRef{homeURL + "#website"},
	}
	if imageURL != "" {
		article.Image = []string{imageURL}
	}
	// Quelques photos supplémentaires (Google en affiche jusqu'à 3 formats).
	for i := 1; i < len(ride.Photos) && len(article.Image) < 3; i++ {
		article.Image = append(article.Image, strings.TrimSuffix(pageURL, "/")+"/"+urlPathEscape(ride.Photos[i]))
	}
	if isISODate(ride.SortKey) {
		article.DatePublished = ride.SortKey
		article.DateModified = ride.SortKey
	}
	if ride.HasGPX || ride.Departure != "" {
		place := &ldPlace{Type: "Place", Name: ride.Departure}
		if ride.HasGPX {
			place.Geo = &ldGeo{Type: "GeoCoordinates", Latitude: round5(ride.StartPoint.Lat), Longitude: round5(ride.StartPoint.Lon)}
		}
		article.ContentLocation = place
	}

	breadcrumb := ldBreadcrumbList{
		Type: "BreadcrumbList",
		ItemListElement: []ldListItem{
			{Type: "ListItem", Position: 1, Name: siteTitle, Item: homeURL},
			{Type: "ListItem", Position: 2, Name: ride.Title, Item: pageURL},
		},
	}
	return marshalLD(ldGraph{Context: "https://schema.org", Graph: []interface{}{article, breadcrumb}})
}

// websiteStructuredDataJSON construit le JSON-LD de la page d'accueil :
// organisation, site, et liste des sorties (ItemList).
func websiteStructuredDataJSON(siteTitle, homeURL string, rides []*Ride) template.JS {
	list := ldItemList{Type: "ItemList", Name: "Sorties gravel autour de Montpellier", NumberOfItems: len(rides)}
	for i, r := range rides {
		list.ItemListElement = append(list.ItemListElement, ldListItem{
			Type: "ListItem", Position: i + 1, Name: r.Title, URL: homeURL + "rides/" + r.Slug + "/",
		})
	}
	graph := []interface{}{organizationLD(siteTitle, homeURL), websiteLD(siteTitle, homeURL)}
	if len(rides) > 0 {
		graph = append(graph, list)
	}
	return marshalLD(ldGraph{Context: "https://schema.org", Graph: graph})
}

// --- Taille des images partagées ---------------------------------------

// imageSize lit les dimensions d'une image publiée (JPEG/PNG), pour
// og:image:width/height ; 0, 0 si illisible ou format non pris en charge.
func imageSize(path string) (int, int) {
	f, err := os.Open(path)
	if err != nil {
		return 0, 0
	}
	defer f.Close()
	cfg, _, err := image.DecodeConfig(f)
	if err != nil {
		return 0, 0
	}
	return cfg.Width, cfg.Height
}
