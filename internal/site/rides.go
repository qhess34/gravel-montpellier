package site

import (
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
)

var imageExts = map[string]bool{
	".jpg": true, ".jpeg": true, ".png": true, ".webp": true, ".gif": true,
}

// LoadRides parcourt ridesDir (un sous-dossier par sortie) et construit
// la liste des sorties, triée par date décroissante (les plus récentes en premier).
//
// Chaque sortie doit contenir un fichier description.md. Un fichier .gpx et
// un dossier photos/ sont optionnels.
func LoadRides(ridesDir string) ([]*Ride, error) {
	entries, err := os.ReadDir(ridesDir)
	if err != nil {
		if os.IsNotExist(err) {
			return nil, nil
		}
		return nil, err
	}

	var rides []*Ride
	for _, entry := range entries {
		if !entry.IsDir() || strings.HasPrefix(entry.Name(), ".") {
			continue
		}
		slug := entry.Name()
		dir := filepath.Join(ridesDir, slug)

		descPath := filepath.Join(dir, "description.md")
		if _, err := os.Stat(descPath); err != nil {
			fmt.Fprintf(os.Stderr, "⚠ %s : pas de description.md, sortie ignorée\n", slug)
			continue
		}

		ride, err := loadOneRide(slug, dir, descPath)
		if err != nil {
			return nil, fmt.Errorf("sortie %q : %w", slug, err)
		}
		rides = append(rides, ride)
	}

	sort.Slice(rides, func(i, j int) bool {
		return rides[i].SortKey > rides[j].SortKey // plus récent en premier
	})

	return rides, nil
}

func loadOneRide(slug, dir, descPath string) (*Ride, error) {
	raw, err := os.ReadFile(descPath)
	if err != nil {
		return nil, err
	}

	fields, body, err := ParseFrontMatter(string(raw))
	if err != nil {
		return nil, err
	}

	ride := &Ride{
		Slug:       slug,
		Title:      firstNonEmpty(fields["title"], slug),
		DateRaw:    fields["date"],
		SortKey:    fields["date"],
		Difficulty: fields["difficulty"],
		Departure:  fields["departure"],
		Body:       Markdown(body),
	}

	if fields["distance_km"] != "" {
		if v, err := strconv.ParseFloat(fields["distance_km"], 64); err == nil {
			ride.DistanceKm = v
		}
	}
	if fields["elevation_m"] != "" {
		if v, err := strconv.Atoi(fields["elevation_m"]); err == nil {
			ride.ElevationM = v
		}
	}
	if fields["tags"] != "" {
		for _, t := range strings.Split(fields["tags"], ",") {
			t = strings.TrimSpace(t)
			if t != "" {
				ride.Tags = append(ride.Tags, t)
			}
		}
	}

	// Trace GPX : on prend le premier fichier .gpx trouvé dans le dossier.
	gpxPath, err := findFirstGPX(dir)
	if err != nil {
		return nil, err
	}
	if gpxPath != "" {
		points, err := LoadGPX(gpxPath)
		if err != nil {
			return nil, fmt.Errorf("lecture gpx : %w", err)
		}
		if len(points) > 0 {
			ride.HasGPX = true
			ride.GPXPoints = SimplifyForMap(points, 800)
			ride.GPXFile = "gpx/" + filepath.Base(gpxPath)

			if ride.DistanceKm == 0 {
				ride.DistanceKm = DistanceKm(points)
			}
			if ride.ElevationM == 0 {
				ride.ElevationM = ElevationGainM(points)
			}
		}
	}

	// Photos : tout fichier image dans dir/photos/, trié par nom.
	photosDir := filepath.Join(dir, "photos")
	validPhotoNames := map[string]bool{}
	if entries, err := os.ReadDir(photosDir); err == nil {
		var names []string
		for _, e := range entries {
			if e.IsDir() {
				continue
			}
			if imageExts[strings.ToLower(filepath.Ext(e.Name()))] {
				names = append(names, e.Name())
			}
		}
		sort.Strings(names)
		for _, n := range names {
			ride.Photos = append(ride.Photos, "photos/"+n)
			validPhotoNames[n] = true
		}
	}

	// Points de carte (POI, photos géolocalisées, panoramax) : fichier optionnel points.md
	points, err := LoadPoints(dir, validPhotoNames)
	if err != nil {
		return nil, err
	}
	ride.Points = points
	for _, p := range points {
		if p.Type == PointPanoramax {
			ride.HasPanoramax = true
			break
		}
	}

	return ride, nil
}

func findFirstGPX(dir string) (string, error) {
	entries, err := os.ReadDir(dir)
	if err != nil {
		return "", err
	}
	for _, e := range entries {
		if !e.IsDir() && strings.EqualFold(filepath.Ext(e.Name()), ".gpx") {
			return filepath.Join(dir, e.Name()), nil
		}
	}
	return "", nil
}

func firstNonEmpty(values ...string) string {
	for _, v := range values {
		if strings.TrimSpace(v) != "" {
			return v
		}
	}
	return ""
}
