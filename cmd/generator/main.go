// Commande generator : construit le site statique 
// à partir du contenu du dossier rides/ et du fichier content/footer.md.
//
// Usage :
//
//	go run ./cmd/generator
//	go run ./cmd/generator -rides ./rides -footer ./content/footer.md -out ./public
package main

import (
	"flag"
	"fmt"
	"os"

	"gravel-montpellier/internal/site"
)

func main() {
	ridesDir := flag.String("rides", "rides", "dossier contenant un sous-dossier par sortie")
	footer := flag.String("footer", "content/footer.md", "fichier markdown du pied de page")
	legal := flag.String("legal", "content/mentions-legales.md", "fichier markdown de la page Mentions légales")
	outDir := flag.String("out", "public", "dossier de sortie du site généré")
	title := flag.String("title", "CycloExplore Montpellier", "titre du site")
	siteURL := flag.String("site-url", "", "URL publique du site (ex: https://user.github.io/repo) — nécessaire pour les boutons de partage et l'aperçu d'image")
	flag.Parse()

	err := site.Build(site.Options{
		RidesDir:   *ridesDir,
		FooterPath: *footer,
		LegalPath:  *legal,
		OutDir:     *outDir,
		SiteTitle:  *title,
		SiteURL:    *siteURL,
	})
	if err != nil {
		fmt.Fprintln(os.Stderr, "Erreur :", err)
		os.Exit(1)
	}

	fmt.Println("✓ Site généré dans", *outDir)
}
