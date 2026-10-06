package site

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"
)

// slopeFileName : fichier généré par tools/slope_colors.py dans le dossier
// de chaque sortie (trace découpée en tronçons colorisés selon la pente).
const slopeFileName = "slope.geojson"

// SlopeClass est une entrée de la légende des pentes (définie dans
// tools/slope_colors.py, recopiée dans le GeoJSON généré).
type SlopeClass struct {
	Key   string `json:"key"`
	Label string `json:"label"`
	Color string `json:"color"`
}

type slopeGeoJSON struct {
	SourceGPX    string       `json:"source_gpx"`
	SourceSHA256 string       `json:"source_sha256"`
	Legend       []SlopeClass `json:"legend"`
	Features     []struct {
		Properties struct {
			Class string `json:"class"`
		} `json:"properties"`
	} `json:"features"`
}

// loadSlopeData vérifie que rides/<slug>/slope.geojson existe et correspond
// bien au GPX actuel de la sortie (empreinte SHA-256 enregistrée par le
// script). Renvoie la légende limitée aux classes réellement présentes sur
// la trace.
//
// Un fichier absent, illisible ou obsolète n'est pas bloquant : la fiche
// affiche alors la trace GPX d'origine en couleur uniforme, et un
// avertissement indique la commande à lancer.
func loadSlopeData(slug, rideDir, gpxPath string) (legend []SlopeClass, ok bool) {
	path := filepath.Join(rideDir, slopeFileName)
	raw, err := os.ReadFile(path)
	if err != nil {
		if os.IsNotExist(err) {
			fmt.Fprintf(os.Stderr, "⚠ %s : %s absent — trace affichée sans colorisation des pentes (lancez : python3 tools/slope_colors.py)\n", slug, slopeFileName)
		} else {
			fmt.Fprintf(os.Stderr, "⚠ %s : lecture de %s impossible (%v)\n", slug, slopeFileName, err)
		}
		return nil, false
	}

	var data slopeGeoJSON
	if err := json.Unmarshal(raw, &data); err != nil || len(data.Features) == 0 {
		fmt.Fprintf(os.Stderr, "⚠ %s : %s invalide — relancez : python3 tools/slope_colors.py %s\n", slug, slopeFileName, rideDir)
		return nil, false
	}

	sum, err := fileSHA256(gpxPath)
	if err != nil {
		return nil, false
	}
	if data.SourceSHA256 != sum {
		fmt.Fprintf(os.Stderr, "⚠ %s : %s obsolète (le GPX a changé depuis sa génération) — trace affichée sans colorisation ; relancez : python3 tools/slope_colors.py %s\n", slug, slopeFileName, rideDir)
		return nil, false
	}

	present := map[string]bool{}
	for _, f := range data.Features {
		present[f.Properties.Class] = true
	}
	for _, c := range data.Legend {
		if present[c.Key] {
			legend = append(legend, c)
		}
	}
	return legend, true
}

func fileSHA256(path string) (string, error) {
	f, err := os.Open(path)
	if err != nil {
		return "", err
	}
	defer f.Close()
	h := sha256.New()
	if _, err := io.Copy(h, f); err != nil {
		return "", err
	}
	return hex.EncodeToString(h.Sum(nil)), nil
}
