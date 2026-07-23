package site

import (
	"fmt"
	"html/template"
	"io"
	"io/fs"
	"os"
	"path/filepath"
)

// Options contrôle la génération du site.
type Options struct {
	RidesDir   string // dossier contenant un sous-dossier par sortie
	FooterPath string // fichier markdown pour le pied de page
	OutDir     string // dossier de sortie (site statique généré)
	SiteTitle  string
}

type pageData struct {
	PageTitle string
	Root      string
	Footer    template.HTML
	Rides     []*Ride
	Ride      *Ride
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

	footerHTML, err := loadFooter(opts.FooterPath)
	if err != nil {
		return fmt.Errorf("footer : %w", err)
	}

	rides, err := LoadRides(opts.RidesDir)
	if err != nil {
		return fmt.Errorf("lecture des sorties : %w", err)
	}
	fmt.Printf("→ %d sortie(s) trouvée(s)\n", len(rides))

	if err := copyStatic(opts.OutDir); err != nil {
		return fmt.Errorf("copie des assets statiques : %w", err)
	}

	indexTmpl, err := template.ParseFS(TemplatesFS, "templates/base.html", "templates/index.html")
	if err != nil {
		return fmt.Errorf("parsing template index : %w", err)
	}
	rideTmpl, err := template.ParseFS(TemplatesFS, "templates/base.html", "templates/ride.html")
	if err != nil {
		return fmt.Errorf("parsing template ride : %w", err)
	}

	// Page d'accueil
	if err := renderToFile(indexTmpl, filepath.Join(opts.OutDir, "index.html"), pageData{
		PageTitle: opts.SiteTitle,
		Root:      "",
		Footer:    footerHTML,
		Rides:     rides,
	}); err != nil {
		return fmt.Errorf("génération index.html : %w", err)
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

		if err := renderToFile(rideTmpl, filepath.Join(outRideDir, "index.html"), pageData{
			PageTitle: ride.Title,
			Root:      "../../",
			Footer:    footerHTML,
			Ride:      ride,
		}); err != nil {
			return fmt.Errorf("génération page sortie (%s) : %w", ride.Slug, err)
		}

		fmt.Printf("  ✓ %s (%s)\n", ride.Title, ride.Slug)
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

func loadFooter(path string) (template.HTML, error) {
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
