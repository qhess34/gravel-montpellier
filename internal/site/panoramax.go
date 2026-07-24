package site

import (
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"strings"
	"time"
)

type panoramaxSearchResponse struct {
	Features []struct {
		Geometry struct {
			Coordinates []float64 `json:"coordinates"`
		} `json:"geometry"`
	} `json:"features"`
}

// FetchPanoramaxLocation interroge l'API Panoramax (compatible STAC, via
// l'endpoint /search) pour récupérer les coordonnées GPS d'une photo à
// partir de son seul identifiant, quand elles ne sont pas renseignées
// manuellement dans points.md. Nécessite un accès réseau au moment du
// build (disponible en CI GitHub Actions).
func FetchPanoramaxLocation(endpoint, pictureID string) (lat, lon float64, err error) {
	u, err := url.Parse(strings.TrimRight(endpoint, "/") + "/search")
	if err != nil {
		return 0, 0, err
	}
	q := u.Query()
	q.Set("ids", pictureID)
	q.Set("limit", "1")
	u.RawQuery = q.Encode()

	client := &http.Client{Timeout: 10 * time.Second}
	resp, err := client.Get(u.String())
	if err != nil {
		return 0, 0, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return 0, 0, fmt.Errorf("réponse %s de %s", resp.Status, u.String())
	}

	var parsed panoramaxSearchResponse
	if err := json.NewDecoder(resp.Body).Decode(&parsed); err != nil {
		return 0, 0, fmt.Errorf("réponse illisible : %w", err)
	}
	if len(parsed.Features) == 0 || len(parsed.Features[0].Geometry.Coordinates) < 2 {
		return 0, 0, fmt.Errorf("aucune photo trouvée pour cet identifiant sur %s", endpoint)
	}

	coords := parsed.Features[0].Geometry.Coordinates // GeoJSON : [lon, lat]
	return coords[1], coords[0], nil
}
