package site

import (
	"fmt"
	"hash/fnv"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"time"
)

// --- Synthèse de la description ----------------------------------------------

// summaryHeadingRe repère le titre qui clôt la synthèse dans description.md.
var summaryHeadingRe = regexp.MustCompile(`(?mi)^##[ \t]+Le parcours[ \t]*$`)

var anyHeadingRe = regexp.MustCompile(`(?m)^#{1,6}[ \t]+\S`)

// splitSummary sépare le corps de description.md (après le frontmatter,
// donc après le premier séparateur « --- » qui le referme) en :
//   - summary : le texte d'introduction, jusqu'au titre « ## Le parcours »
//     exclu ;
//   - rest : la suite, à partir de ce titre inclus.
//
// Sans titre « ## Le parcours », la synthèse s'arrête au premier titre
// markdown ; sans aucun titre, c'est le premier paragraphe. Les lignes
// « --- » éventuelles (délimiteurs) ne font jamais partie de la synthèse.
func splitSummary(body string) (summary, rest string) {
	body = strings.ReplaceAll(body, "\r\n", "\n")

	cut := -1
	if loc := summaryHeadingRe.FindStringIndex(body); loc != nil {
		cut = loc[0]
	} else if loc := anyHeadingRe.FindStringIndex(body); loc != nil && strings.TrimSpace(body[:loc[0]]) != "" {
		cut = loc[0]
	}
	if cut >= 0 {
		summary, rest = body[:cut], body[cut:]
	} else {
		trimmed := strings.TrimLeft(body, "\n")
		if i := strings.Index(trimmed, "\n\n"); i >= 0 && !anyHeadingRe.MatchString(trimmed[:i]) {
			summary, rest = trimmed[:i], trimmed[i:]
		} else {
			rest = body
		}
	}

	var lines []string
	for _, l := range strings.Split(summary, "\n") {
		if strings.TrimSpace(l) == "---" {
			continue
		}
		lines = append(lines, l)
	}
	return strings.TrimSpace(strings.Join(lines, "\n")), strings.TrimSpace(rest)
}

var (
	plainLinkRe   = regexp.MustCompile(`\[(.+?)\]\((.+?)\)`)
	plainBoldRe   = regexp.MustCompile(`\*\*(.+?)\*\*`)
	plainItalicRe = regexp.MustCompile(`\*(.+?)\*`)
	plainSpacesRe = regexp.MustCompile(`\s+`)
)

// markdownToPlainText retire la syntaxe markdown (liens, emphases, titres,
// puces) pour obtenir un texte brut sur une ligne — utilisé dans les
// cartouches, les popups de la carte et la meta description.
func markdownToPlainText(md string) string {
	var parts []string
	for _, l := range strings.Split(md, "\n") {
		l = strings.TrimSpace(l)
		l = strings.TrimLeft(l, "#")
		l = strings.TrimPrefix(strings.TrimSpace(l), "- ")
		parts = append(parts, l)
	}
	s := strings.Join(parts, " ")
	s = plainLinkRe.ReplaceAllString(s, "$1")
	s = plainBoldRe.ReplaceAllString(s, "$1")
	s = plainItalicRe.ReplaceAllString(s, "$1")
	return strings.TrimSpace(plainSpacesRe.ReplaceAllString(s, " "))
}

// truncateText coupe s à environ max caractères, sur une frontière de mot,
// en ajoutant « … ».
func truncateText(s string, max int) string {
	r := []rune(s)
	if len(r) <= max {
		return s
	}
	cut := string(r[:max])
	if i := strings.LastIndex(cut, " "); i > max/2 {
		cut = cut[:i]
	}
	return strings.TrimRight(cut, " ,;:.—-") + "…"
}

// --- Difficulté -----------------------------------------------------------------

// DifficultyOption est une valeur du filtre par difficulté de l'accueil.
type DifficultyOption struct {
	Key   string
	Label string
	Level int
}

// difficultyLevels : niveaux reconnus, du plus facile au plus dur. Les
// variantes d'écriture d'un même niveau (« Moyen », « Moyenne »…) sont
// regroupées dans le filtre sans modifier la valeur saisie, qui reste
// affichée telle quelle sur les cartouches et la fiche.
var difficultyLevels = []struct {
	opt     DifficultyOption
	aliases []string
}{
	{DifficultyOption{"facile", "Facile", 1}, []string{"facile", "tres facile", "debutant"}},
	{DifficultyOption{"moyenne", "Moyenne", 2}, []string{"moyen", "moyenne", "modere", "moderee", "intermediaire"}},
	{DifficultyOption{"difficile", "Difficile", 3}, []string{"difficile", "dur", "sportif", "sportive"}},
	{DifficultyOption{"tres-difficile", "Très difficile", 4}, []string{"tres difficile", "expert", "extreme"}},
}

var accentReplacer = strings.NewReplacer(
	"à", "a", "â", "a", "ä", "a", "é", "e", "è", "e", "ê", "e", "ë", "e",
	"î", "i", "ï", "i", "ô", "o", "ö", "o", "ù", "u", "û", "u", "ü", "u", "ç", "c",
)

func normalizeWord(s string) string {
	s = accentReplacer.Replace(strings.ToLower(strings.TrimSpace(s)))
	return strings.Join(strings.FieldsFunc(s, func(r rune) bool {
		return !(r >= 'a' && r <= 'z' || r >= '0' && r <= '9')
	}), " ")
}

// normalizeDifficulty associe une difficulté saisie librement à un niveau
// connu. Une valeur inconnue reste utilisable dans le filtre (clé dérivée
// de son texte, niveau 0 : triée après les niveaux connus).
func normalizeDifficulty(raw string) (DifficultyOption, bool) {
	n := normalizeWord(raw)
	if n == "" {
		return DifficultyOption{}, false
	}
	for _, lvl := range difficultyLevels {
		for _, a := range lvl.aliases {
			if n == a {
				return lvl.opt, true
			}
		}
	}
	return DifficultyOption{Key: strings.ReplaceAll(n, " ", "-"), Label: strings.TrimSpace(raw)}, true
}

// collectDifficulties renvoie les difficultés présentes parmi les sorties,
// de la plus facile à la plus difficile.
func collectDifficulties(rides []*Ride) []DifficultyOption {
	seen := map[string]bool{}
	var out []DifficultyOption
	for _, r := range rides {
		opt, ok := normalizeDifficulty(r.Difficulty)
		if ok && !seen[opt.Key] {
			seen[opt.Key] = true
			out = append(out, opt)
		}
	}
	sort.SliceStable(out, func(i, j int) bool {
		li, lj := out[i].Level, out[j].Level
		if li == 0 {
			li = 99
		}
		if lj == 0 {
			lj = 99
		}
		if li != lj {
			return li < lj
		}
		return out[i].Label < out[j].Label
	})
	return out
}

// --- Durée -------------------------------------------------------------------------

var dayTagRe = regexp.MustCompile(`^(\d+)\s*jours?$`)

// rideDuration renvoie la durée affichée d'une sortie :
//   - le champ « duration » du frontmatter s'il est renseigné (texte libre,
//     ex : « 4 h 30 ») ;
//   - sinon, la durée déduite des tags « 1 jour », « 2 jours »… déjà
//     utilisés sur le site (« 1 jour », « 2 à 5 jours ») ;
//   - sinon, rien : aucune durée n'est inventée.
func rideDuration(field string, tags []string) string {
	if d := strings.TrimSpace(field); d != "" {
		return d
	}
	var days []int
	for _, t := range tags {
		if m := dayTagRe.FindStringSubmatch(normalizeWord(t)); m != nil {
			if n, err := strconv.Atoi(m[1]); err == nil && n > 0 {
				days = append(days, n)
			}
		}
	}
	if len(days) == 0 {
		return ""
	}
	sort.Ints(days)
	lo, hi := days[0], days[len(days)-1]
	unit := func(n int) string {
		if n > 1 {
			return "jours"
		}
		return "jour"
	}
	if lo == hi {
		return fmt.Sprintf("%d %s", lo, unit(lo))
	}
	return fmt.Sprintf("%d à %d %s", lo, hi, unit(hi))
}

// --- Date ----------------------------------------------------------------------------

var frenchMonths = map[string]time.Month{
	"janvier": 1, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
	"juillet": 7, "aout": 8, "septembre": 9, "octobre": 10, "novembre": 11, "decembre": 12,
}

var frenchDateRe = regexp.MustCompile(`^(\d{1,2})(?:er)? ([a-z]+) (\d{4})$`)

// dateSortKey convertit la date saisie (« 2026-06-15 », « 15/06/2026 »,
// « 15 juin 2026 ») en clé AAAA-MM-JJ, triable et utilisable comme date
// structurée. Une date non reconnue est renvoyée telle quelle.
func dateSortKey(raw string) string {
	raw = strings.TrimSpace(raw)
	for _, layout := range []string{"2006-01-02", "02/01/2006", "2/1/2006", "02-01-2006", "02.01.2006"} {
		if t, err := time.Parse(layout, raw); err == nil {
			return t.Format("2006-01-02")
		}
	}
	if m := frenchDateRe.FindStringSubmatch(normalizeWord(raw)); m != nil {
		if month, ok := frenchMonths[m[2]]; ok {
			day, _ := strconv.Atoi(m[1])
			year, _ := strconv.Atoi(m[3])
			return time.Date(year, month, day, 0, 0, 0, 0, time.UTC).Format("2006-01-02")
		}
	}
	return raw
}

// --- Couleur des traces sur la carte d'accueil -----------------------------------------

// ridePalette : couleurs bien distinctes entre elles et lisibles sur le fond
// OpenStreetMap (les traces sont en plus soulignées d'un liseré blanc).
var ridePalette = []string{
	"#e6194b", // rouge
	"#3cb44b", // vert
	"#4363d8", // bleu
	"#f58231", // orange
	"#911eb4", // violet
	"#0b9db0", // turquoise
	"#e01ec8", // magenta
	"#9a6324", // brun
	"#800000", // bordeaux
	"#000075", // marine
	"#469990", // sarcelle
	"#808000", // olive
}

var hexColorRe = regexp.MustCompile(`^#[0-9a-fA-F]{6}$`)

// assignColors attribue à chaque sortie une couleur de ridePalette, stable
// d'une génération à l'autre :
//   - le champ « color » du frontmatter (#rrggbb), s'il est renseigné, est
//     prioritaire ;
//   - sinon chaque sortie vise la couleur désignée par un hash de son slug,
//     et prend la suivante libre si elle est déjà prise. Les sorties sont
//     servies de la plus ancienne à la plus récente : ajouter une nouvelle
//     sortie ne change donc pas la couleur des précédentes.
//
// Au-delà de len(ridePalette) sorties, les couleurs sont réutilisées.
func assignColors(rides []*Ride) {
	order := make([]*Ride, len(rides))
	copy(order, rides)
	sort.SliceStable(order, func(i, j int) bool {
		if order[i].SortKey != order[j].SortKey {
			return order[i].SortKey < order[j].SortKey
		}
		return order[i].Slug < order[j].Slug
	})

	taken := map[string]bool{}
	for _, r := range order {
		if hexColorRe.MatchString(r.Color) {
			taken[strings.ToLower(r.Color)] = true
		}
	}
	for _, r := range order {
		if hexColorRe.MatchString(r.Color) {
			continue
		}
		h := fnv.New32a()
		h.Write([]byte(r.Slug))
		start := int(h.Sum32() % uint32(len(ridePalette)))
		r.Color = ridePalette[start]
		for k := 0; k < len(ridePalette); k++ {
			c := ridePalette[(start+k)%len(ridePalette)]
			if !taken[c] {
				r.Color = c
				break
			}
		}
		taken[r.Color] = true
	}
}
