package site

import (
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
)

// PointType distingue les trois natures de point affichables sur la carte.
type PointType string

const (
	PointPOI       PointType = "poi"       // ravitaillement, danger, point de vue...
	PointPhoto     PointType = "photo"     // photo géolocalisée du dossier photos/
	PointPanoramax PointType = "panoramax" // vue 360° via Panoramax
)

// Point représente un marqueur affiché sur la carte de la sortie.
type Point struct {
	Type  PointType
	Lat   float64
	Lon   float64
	Label string
	Note  string // poi uniquement
	Icon  string // poi uniquement : water, food, danger, viewpoint, generic (défaut)

	PhotoRel string // photo uniquement : chemin relatif copié, ex "photos/xxx.jpg"
	Caption  string // photo uniquement

	Picture  string // panoramax uniquement : identifiant de la photo
	Sequence string // panoramax uniquement : identifiant de séquence (optionnel)
	Endpoint string // panoramax uniquement : URL de l'API (optionnel)
}

const defaultPanoramaxEndpoint = "https://api.panoramax.xyz/api"

// LoadPoints lit le fichier points.md optionnel d'une sortie et renvoie la
// liste des points à afficher sur la carte. validPhotos permet de vérifier
// que les photos référencées par un point de type "photo" existent bien
// dans le dossier photos/ de la sortie (clé = nom de fichier).
func LoadPoints(dir string, validPhotos map[string]bool) ([]Point, error) {
	data, err := os.ReadFile(filepath.Join(dir, "points.md"))
	if err != nil {
		if os.IsNotExist(err) {
			return nil, nil
		}
		return nil, err
	}

	var points []Point
	for i, block := range splitPointBlocks(string(data)) {
		fields := parseKeyValues(block)
		if len(fields) == 0 {
			continue
		}
		p, err := buildPoint(fields, validPhotos)
		if err != nil {
			return nil, fmt.Errorf("point #%d de points.md : %w", i+1, err)
		}
		points = append(points, p)
	}
	return points, nil
}

// splitPointBlocks découpe le fichier en blocs séparés par une ligne "---",
// où qu'elle apparaisse (début, fin, entre deux blocs, avec ou sans lignes
// vides autour).
func splitPointBlocks(content string) []string {
	content = strings.ReplaceAll(content, "\r\n", "\n")

	var blocks []string
	var current []string
	flush := func() {
		block := strings.Join(current, "\n")
		if strings.TrimSpace(block) != "" {
			blocks = append(blocks, block)
		}
		current = nil
	}

	for _, line := range strings.Split(content, "\n") {
		if strings.TrimSpace(line) == "---" {
			flush()
			continue
		}
		current = append(current, line)
	}
	flush()

	return blocks
}

// parseKeyValues lit un bloc "clé: valeur" (une paire par ligne).
func parseKeyValues(block string) map[string]string {
	fields := map[string]string{}
	for _, line := range strings.Split(block, "\n") {
		line = strings.TrimSpace(line)
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		key, value, ok := strings.Cut(line, ":")
		if !ok {
			continue
		}
		key = strings.TrimSpace(key)
		value = strings.TrimSpace(value)
		value = strings.Trim(value, `"'`)
		fields[key] = value
	}
	return fields
}

func buildPoint(fields map[string]string, validPhotos map[string]bool) (Point, error) {
	t := PointType(strings.ToLower(strings.TrimSpace(fields["type"])))
	if t == "" {
		return Point{}, fmt.Errorf("champ 'type' manquant (poi, photo ou panoramax)")
	}

	if fields["lat"] == "" || fields["lon"] == "" {
		return Point{}, fmt.Errorf("champs 'lat' et 'lon' requis")
	}
	lat, err := strconv.ParseFloat(fields["lat"], 64)
	if err != nil {
		return Point{}, fmt.Errorf("lat invalide : %w", err)
	}
	lon, err := strconv.ParseFloat(fields["lon"], 64)
	if err != nil {
		return Point{}, fmt.Errorf("lon invalide : %w", err)
	}

	p := Point{
		Type:  t,
		Lat:   lat,
		Lon:   lon,
		Label: fields["label"],
		Note:  fields["note"],
		Icon:  firstNonEmpty(fields["icon"], "generic"),
	}

	switch t {
	case PointPOI:
		if p.Label == "" {
			return Point{}, fmt.Errorf("un point de type 'poi' nécessite un champ 'label'")
		}

	case PointPhoto:
		photo := fields["photo"]
		if photo == "" {
			return Point{}, fmt.Errorf("un point de type 'photo' nécessite un champ 'photo' (nom du fichier dans photos/)")
		}
		if validPhotos != nil && !validPhotos[photo] {
			return Point{}, fmt.Errorf("photo %q introuvable dans le dossier photos/", photo)
		}
		p.PhotoRel = "photos/" + photo
		p.Caption = fields["caption"]

	case PointPanoramax:
		picture := fields["picture"]
		if picture == "" {
			return Point{}, fmt.Errorf("un point de type 'panoramax' nécessite un champ 'picture' (identifiant de la photo Panoramax)")
		}
		p.Picture = picture
		p.Sequence = fields["sequence"]
		p.Endpoint = firstNonEmpty(fields["endpoint"], defaultPanoramaxEndpoint)
		if p.Label == "" {
			p.Label = "Vue 360°"
		}

	default:
		return Point{}, fmt.Errorf("type de point inconnu %q (attendu : poi, photo ou panoramax)", t)
	}

	return p, nil
}
