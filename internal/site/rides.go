package site

import (
	"fmt"
	"math"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
)

var imageExts = map[string]bool{
	".jpg": true, ".jpeg": true, ".png": true, ".webp": true, ".gif": true,
}

// maxPointToTrackKm : au-delà de cette distance (km) entre un point et la
// trace la plus proche, on considère qu'il n'est pas "sur le parcours" et
// on ne lui attribue pas de point kilométrique.
const maxPointToTrackKm = 3.0

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
	if len(ride.Tags) > 0 {
		normalized := make([]string, len(ride.Tags))
		for i, t := range ride.Tags {
			normalized[i] = strings.ToLower(t)
		}
		ride.TagsAttr = strings.Join(normalized, ",")
	}

	// Trace GPX : on prend le premier fichier .gpx trouvé dans le dossier.
	var trackPoints []GPXPoint
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
			trackPoints = points

			if ride.DistanceKm == 0 {
				ride.DistanceKm = DistanceKm(points)
			}
			if ride.ElevationM == 0 {
				ride.ElevationM = ElevationGainM(points)
			}

			ride.StartPoint = points[0]
			ride.EndPoint = points[len(points)-1]
			ride.IsLoop = PointDistanceKm(ride.StartPoint, ride.EndPoint) < 0.05 // < 50 m : boucle

			// Statistiques de revêtement (route/piste cyclable vs chemin/sentier),
			// par comparaison de la trace aux voies OSM alentour. Purement
			// informatif : n'affecte jamais le rendu de la trace elle-même.
			buffer := SimplifyForMap(points, 150)
			statsTrack := SimplifyForMap(points, 1000)
			ways, err := fetchWaySegments(buffer, 20)
			if err != nil {
				fmt.Fprintf(os.Stderr, "⚠ %s : statistiques de revêtement indisponibles (%v)\n", slug, err)
			} else {
				types := classifyTrackPoints(statsTrack, ways)
				paved, unpaved, unknown := surfaceDistances(statsTrack, types)
				if total := paved + unpaved + unknown; total > 0 {
					ride.SurfacePavedKm = paved
					ride.SurfaceUnpavedKm = unpaved
					ride.SurfaceUnknownKm = unknown
					ride.SurfacePavedPct = int(math.Round(paved / total * 100))
					ride.SurfaceUnpavedPct = int(math.Round(unpaved / total * 100))
					ride.SurfaceUnknownPct = 100 - ride.SurfacePavedPct - ride.SurfaceUnpavedPct
					ride.HasSurfaceStats = paved > 0 || unpaved > 0
				}
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

	// Photos géolocalisées automatiquement : toute photo du dossier photos/
	// pas déjà référencée manuellement dans points.md, et dont les données
	// EXIF contiennent une position GPS, devient un point sur la carte.
	alreadyReferenced := map[string]bool{}
	for _, p := range points {
		if p.Type == PointPhoto {
			alreadyReferenced[filepath.Base(p.PhotoRel)] = true
		}
	}
	for _, rel := range ride.Photos {
		name := filepath.Base(rel)
		if alreadyReferenced[name] {
			continue
		}
		ext := strings.ToLower(filepath.Ext(name))
		if ext != ".jpg" && ext != ".jpeg" {
			continue // seul le JPEG est pris en charge pour la lecture EXIF
		}
		if lat, lon, ok := PhotoGPS(filepath.Join(photosDir, name)); ok {
			points = append(points, Point{
				Type:     PointPhoto,
				Lat:      lat,
				Lon:      lon,
				PhotoRel: rel,
			})
		}
	}

	// Point kilométrique : pour chaque point assez proche de la trace,
	// on calcule sa position (km depuis le départ) en le projetant sur le
	// point de trace le plus proche.
	if len(trackPoints) > 0 {
		for i := range points {
			km, dist := NearestKm(trackPoints, GPXPoint{Lat: points[i].Lat, Lon: points[i].Lon})
			if dist >= 0 && dist <= maxPointToTrackKm {
				points[i].KmMark = km
				points[i].HasKmMark = true
			}
		}
	}

	ride.Points = points
	for _, p := range points {
		if p.Type == PointPanoramax {
			ride.HasPanoramax = true
		}
		if p.Type == PointPOI && p.HasKmMark && (p.Icon == "water" || p.Icon == "food") {
			ride.Supplies = append(ride.Supplies, p)
		}
	}
	sort.Slice(ride.Supplies, func(i, j int) bool {
		return ride.Supplies[i].KmMark < ride.Supplies[j].KmMark
	})

	if len(trackPoints) > 0 {
		profile := buildElevationProfile(trackPoints, 200)
		if svg := renderElevationProfileSVG(profile, ride.Supplies); svg != "" {
			ride.ElevationProfileSVG = svg
			ride.ElevationProfileDataJSON = elevationProfileDataJSON(profile)
			ride.HasElevationProfile = true
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

// collectTags renvoie la liste triée et dédupliquée (en minuscules) de tous
// les tags présents parmi les sorties, pour la barre de filtre de l'accueil.
func collectTags(rides []*Ride) []string {
	seen := map[string]bool{}
	var tags []string
	for _, r := range rides {
		for _, t := range r.Tags {
			lt := strings.ToLower(t)
			if !seen[lt] {
				seen[lt] = true
				tags = append(tags, lt)
			}
		}
	}
	sort.Strings(tags)
	return tags
}
