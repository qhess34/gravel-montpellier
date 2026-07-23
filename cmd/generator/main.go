// Commande generator : construit le site statique "Gravel Montpellier"
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
	outDir := flag.String("out", "public", "dossier de sortie du site généré")
	title := flag.String("title", "Gravel Montpellier", "titre du site")
	flag.Parse()

	err := site.Build(site.Options{
		RidesDir:   *ridesDir,
		FooterPath: *footer,
		OutDir:     *outDir,
		SiteTitle:  *title,
	})
	if err != nil {
		fmt.Fprintln(os.Stderr, "Erreur :", err)
		os.Exit(1)
	}

	fmt.Println("✓ Site généré dans", *outDir)
}
