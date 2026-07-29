// Commande generator : construit le site statique "Cyclo Explore"
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
	title := flag.String("title", "Cyclo Explore", "titre du site")
	siteURL := flag.String("site-url", "https://montpellier.cycloexplore.fr", "URL publique du site — nécessaire pour les boutons de partage et l'aperçu d'image")
	umamiID := flag.String("umami-id", "9e97164b-65cd-4fef-82f2-f08b105783d3", "identifiant de site Umami (statistiques) — vide pour désactiver")
	flag.Parse()

	err := site.Build(site.Options{
		RidesDir:   *ridesDir,
		FooterPath: *footer,
		LegalPath:  *legal,
		OutDir:     *outDir,
		SiteTitle:  *title,
		SiteURL:    *siteURL,
		UmamiID:    *umamiID,
	})
	if err != nil {
		fmt.Fprintln(os.Stderr, "Erreur :", err)
		os.Exit(1)
	}

	fmt.Println("✓ Site généré dans", *outDir)
}
