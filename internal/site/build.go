package site

import (
	"fmt"
	"html/template"
	"io"
	"io/fs"
	"net/url"
	"os"
	"path/filepath"
	"strings"
)

// Options contrôle la génération du site.
type Options struct {
	RidesDir   string // dossier contenant un sous-dossier par sortie
	FooterPath string // fichier markdown pour le pied de page
	LegalPath  string // fichier markdown pour la page "Mentions légales"
	OutDir     string // dossier de sortie (site statique généré)
	SiteTitle  string
	SiteURL    string // URL publique du site (ex: https://user.github.io/repo), sans / final
	// nécessaire pour générer des liens de partage et un aperçu d'image
	// valides (Facebook/WhatsApp/etc. exigent des URLs absolues) ; si
	// vide, les boutons de partage et les balises Open Graph sont omis.
}

type pageData struct {
	PageTitle string
	Root      string
	Footer    template.HTML
	Legal     template.HTML
	Rides     []*Ride
	Ride      *Ride
	AllTags   []string

	MetaURL         string // URL absolue de la page (canonical / og:url)
	MetaImage       string // URL absolue de l'image d'aperçu (og:image)
	MetaDescription string // court résumé (meta description / og:description)
	StructuredDataJSON template.JS // JSON-LD (schema.org), si baseURL configuré

	ShareFacebook string
	ShareWhatsApp string
	ShareTwitter  string
	ShareEmail    string
}

// Build génère l'intégralité du site statique dans opts.OutDir.
func Build(opts Options) error {
	// On vide le contenu du dossier de sortie sans supprimer le dossier
	// lui-même : s'il est monté dans un conteneur déjà démarré (ex.
	// `docker compose up serve`), un RemoveAll+MkdirAll casserait le bind
	// mount et nginx se mettrait à répondre 403 (dossier "fantôme" vide).
	if err := cleanDir(opts.OutDir); err != nil {
		return fmt.Errorf("nettoyage du dossier de sortie : %w", err)
	}

	footerHTML, err := loadMarkdownFile(opts.FooterPath)
	if err != nil {
		return fmt.Errorf("footer : %w", err)
	}

	legalHTML, err := loadMarkdownFile(opts.LegalPath)
	if err != nil {
		return fmt.Errorf("mentions légales : %w", err)
	}

	rides, err := LoadRides(opts.RidesDir)
	if err != nil {
		return fmt.Errorf("lecture des sorties : %w", err)
	}
	fmt.Printf("→ %d sortie(s) trouvée(s)\n", len(rides))

	baseURL := strings.TrimRight(opts.SiteURL, "/")
	if baseURL == "" {
		fmt.Println("⚠ -site-url non renseigné : boutons de partage et aperçu d'image (Open Graph) non générés — voir le README")
	}

	if err := copyStatic(opts.OutDir); err != nil {
		return fmt.Errorf("copie des assets statiques : %w", err)
	}

	if err := writeCNAME(opts.OutDir, baseURL); err != nil {
		return fmt.Errorf("écriture du fichier CNAME : %w", err)
	}

	indexTmpl, err := template.ParseFS(TemplatesFS, "templates/base.html", "templates/index.html")
	if err != nil {
		return fmt.Errorf("parsing template index : %w", err)
	}
	rideTmpl, err := template.ParseFS(TemplatesFS, "templates/base.html", "templates/ride.html")
	if err != nil {
		return fmt.Errorf("parsing template ride : %w", err)
	}
	legalTmpl, err := template.ParseFS(TemplatesFS, "templates/base.html", "templates/legal.html")
	if err != nil {
		return fmt.Errorf("parsing template légal : %w", err)
	}

	// Page d'accueil
	indexData := pageData{
		PageTitle: opts.SiteTitle,
		Root:      "",
		Footer:    footerHTML,
		Rides:     rides,
		AllTags:   collectTags(rides),
	}
	if baseURL != "" {
		indexData.MetaURL = baseURL + "/"
		indexData.MetaDescription = "Sorties gravel autour de Montpellier : traces GPX, photos et itinéraires."
		indexData.StructuredDataJSON = websiteStructuredDataJSON(opts.SiteTitle, baseURL+"/")
	}
	if err := renderToFile(indexTmpl, filepath.Join(opts.OutDir, "index.html"), indexData); err != nil {
		return fmt.Errorf("génération index.html : %w", err)
	}

	// Page "Mentions légales"
	legalData := pageData{
		PageTitle: "Mentions légales",
		Root:      "",
		Footer:    footerHTML,
		Legal:     legalHTML,
	}
	if baseURL != "" {
		legalData.MetaURL = baseURL + "/mentions-legales.html"
		legalData.MetaDescription = "Mentions légales de " + opts.SiteTitle + "."
	}
	if err := renderToFile(legalTmpl, filepath.Join(opts.OutDir, "mentions-legales.html"), legalData); err != nil {
		return fmt.Errorf("génération mentions-legales.html : %w", err)
	}

	// Une page + assets par sortie
	for _, ride := range rides {
		outRideDir := filepath.Join(opts.OutDir, "rides", ride.Slug)
		if err := os.MkdirAll(outRideDir, 0o755); err != nil {
			return err
		}

		if ride.HasGPX {
			// on retrouve le fichier gpx d'origine (findFirstGPX l'a déjà validé lors du chargement)
			origDir := filepath.Join(opts.RidesDir, ride.Slug)
			srcGPX, _ := findFirstGPX(origDir)
			dstGPX := filepath.Join(outRideDir, "gpx", filepath.Base(ride.GPXFile))
			if err := os.MkdirAll(filepath.Dir(dstGPX), 0o755); err != nil {
				return err
			}
			if err := copyFile(srcGPX, dstGPX); err != nil {
				return fmt.Errorf("copie gpx (%s) : %w", ride.Slug, err)
			}
		}

		if len(ride.Photos) > 0 {
			dstPhotosDir := filepath.Join(outRideDir, "photos")
			if err := os.MkdirAll(dstPhotosDir, 0o755); err != nil {
				return err
			}
			for _, rel := range ride.Photos {
				name := filepath.Base(rel)
				src := filepath.Join(opts.RidesDir, ride.Slug, "photos", name)
				dst := filepath.Join(dstPhotosDir, name)
				if err := copyFile(src, dst); err != nil {
					return fmt.Errorf("copie photo (%s/%s) : %w", ride.Slug, name, err)
				}
			}
		}

		pd := pageData{
			PageTitle: ride.Title,
			Root:      "../../",
			Footer:    footerHTML,
			Ride:      ride,
		}
		if baseURL != "" {
			pageURL := baseURL + "/rides/" + ride.Slug + "/"
			pd.MetaURL = pageURL
			pd.MetaDescription = shareDescription(ride)
			if len(ride.Photos) > 0 {
				pd.MetaImage = baseURL + "/rides/" + ride.Slug + "/" + ride.Photos[0]
			}
			pd.ShareFacebook = "https://www.facebook.com/sharer/sharer.php?u=" + escapeURLComponent(pageURL)
			pd.ShareWhatsApp = "https://wa.me/?text=" + escapeURLComponent(ride.Title+" "+pageURL)
			pd.ShareTwitter = "https://twitter.com/intent/tweet?url=" + escapeURLComponent(pageURL) + "&text=" + escapeURLComponent(ride.Title)
			pd.ShareEmail = "mailto:?subject=" + escapeURLComponent(ride.Title) + "&body=" + escapeURLComponent(ride.Title+"\n\n"+pageURL)
			pd.StructuredDataJSON = rideStructuredDataJSON(ride, pageURL, pd.MetaImage, pd.MetaDescription, baseURL+"/", opts.SiteTitle)
		}

		if err := renderToFile(rideTmpl, filepath.Join(outRideDir, "index.html"), pd); err != nil {
			return fmt.Errorf("génération page sortie (%s) : %w", ride.Slug, err)
		}

		fmt.Printf("  ✓ %s (%s)\n", ride.Title, ride.Slug)
	}

	if err := writeRobotsTxt(opts.OutDir, baseURL); err != nil {
		return fmt.Errorf("écriture de robots.txt : %w", err)
	}
	if err := writeSitemap(opts.OutDir, baseURL, rides); err != nil {
		return fmt.Errorf("écriture de sitemap.xml : %w", err)
	}
	if baseURL == "" {
		fmt.Println("⚠ sitemap.xml non généré (nécessite -site-url) — robots.txt généré sans référence au sitemap")
	}

	return nil
}

// cleanDir vide le contenu de dir (le crée s'il n'existe pas encore) sans
// supprimer dir lui-même, afin de ne pas casser un éventuel bind mount
// Docker déjà en place sur ce chemin.
func cleanDir(dir string) error {
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return err
	}
	entries, err := os.ReadDir(dir)
	if err != nil {
		return err
	}
	for _, e := range entries {
		if err := os.RemoveAll(filepath.Join(dir, e.Name())); err != nil {
			return err
		}
	}
	return nil
}

// shareDescription construit un court résumé texte (sans HTML) utilisé
// comme description de partage et meta description.
func shareDescription(ride *Ride) string {
	var parts []string
	if ride.DistanceKm > 0 {
		parts = append(parts, fmt.Sprintf("%.0f km", ride.DistanceKm))
	}
	if ride.ElevationM > 0 {
		parts = append(parts, fmt.Sprintf("+%d m D+", ride.ElevationM))
	}
	if ride.Difficulty != "" {
		parts = append(parts, ride.Difficulty)
	}
	if len(parts) == 0 {
		return "Sortie gravel autour de Montpellier."
	}
	return "Sortie gravel — " + strings.Join(parts, " · ")
}

// escapeURLComponent encode une valeur pour l'insérer dans une query string,
// en utilisant %20 plutôt que + pour les espaces (plus largement compatible,
// notamment avec les liens mailto:).
func escapeURLComponent(s string) string {
	return strings.ReplaceAll(url.QueryEscape(s), "+", "%20")
}

// writeCNAME écrit un fichier CNAME à la racine du site quand baseURL
// pointe vers un domaine personnalisé (pas un sous-domaine *.github.io) :
// GitHub Pages en a besoin pour servir le site sur ce domaine. Sans
// domaine personnalisé, ne fait rien.
func writeCNAME(outDir, baseURL string) error {
	if baseURL == "" {
		return nil
	}
	u, err := url.Parse(baseURL)
	if err != nil || u.Host == "" {
		return nil
	}
	if strings.HasSuffix(u.Host, ".github.io") {
		return nil // domaine github.io par défaut : pas de CNAME nécessaire
	}
	return os.WriteFile(filepath.Join(outDir, "CNAME"), []byte(u.Host+"\n"), 0o644)
}

func loadMarkdownFile(path string) (template.HTML, error) {
	if path == "" {
		return "", nil
	}
	data, err := os.ReadFile(path)
	if err != nil {
		if os.IsNotExist(err) {
			return "", nil
		}
		return "", err
	}
	return Markdown(string(data)), nil
}

func renderToFile(tmpl *template.Template, outPath string, data pageData) error {
	if err := os.MkdirAll(filepath.Dir(outPath), 0o755); err != nil {
		return err
	}
	f, err := os.Create(outPath)
	if err != nil {
		return err
	}
	defer f.Close()
	return tmpl.ExecuteTemplate(f, "base", data)
}

func copyStatic(outDir string) error {
	return fs.WalkDir(StaticFS, "static", func(path string, d fs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if d.IsDir() {
			return nil
		}
		data, err := StaticFS.ReadFile(path)
		if err != nil {
			return err
		}
		dst := filepath.Join(outDir, path) // path commence déjà par "static/"
		if err := os.MkdirAll(filepath.Dir(dst), 0o755); err != nil {
			return err
		}
		return os.WriteFile(dst, data, 0o644)
	})
}

func copyFile(src, dst string) error {
	in, err := os.Open(src)
	if err != nil {
		return err
	}
	defer in.Close()

	out, err := os.Create(dst)
	if err != nil {
		return err
	}
	defer out.Close()

	_, err = io.Copy(out, in)
	return err
}
