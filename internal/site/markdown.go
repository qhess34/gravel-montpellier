package site

import (
	"html"
	"html/template"
	"regexp"
	"strings"
)

// Markdown convertit un sous-ensemble volontairement simple de markdown en HTML :
// titres (#, ##, ###), listes à puces (- item), gras (**mot**), italique (*mot*),
// liens ([texte](url)) et paragraphes séparés par une ligne vide.
//
// Ce n'est pas un moteur markdown complet : il couvre ce dont on a besoin
// pour décrire une sortie gravel sans dépendance externe.
func Markdown(src string) template.HTML {
	src = strings.ReplaceAll(src, "\r\n", "\n")
	blocks := splitBlocks(src)

	var out strings.Builder
	for _, block := range blocks {
		lines := strings.Split(block, "\n")

		switch {
		case isHeading(lines):
			level, text := parseHeading(lines[0])
			out.WriteString("<h" + level + ">" + inline(text) + "</h" + level + ">\n")

		case isList(lines):
			out.WriteString("<ul>\n")
			for _, l := range lines {
				item := strings.TrimSpace(strings.TrimPrefix(strings.TrimSpace(l), "-"))
				out.WriteString("  <li>" + inline(item) + "</li>\n")
			}
			out.WriteString("</ul>\n")

		default:
			var rendered []string
			for _, l := range lines {
				if strings.TrimSpace(l) == "" {
					continue
				}
				rendered = append(rendered, inline(l))
			}
			out.WriteString("<p>" + strings.Join(rendered, "<br>\n") + "</p>\n")
		}
	}

	return template.HTML(out.String())
}

func splitBlocks(src string) []string {
	raw := strings.Split(src, "\n\n")
	var blocks []string
	for _, b := range raw {
		b = strings.Trim(b, "\n")
		if strings.TrimSpace(b) == "" {
			continue
		}
		blocks = append(blocks, b)
	}
	return blocks
}

func isHeading(lines []string) bool {
	return len(lines) == 1 && headingRe.MatchString(lines[0])
}

var headingRe = regexp.MustCompile(`^(#{1,3})\s+(.*)$`)

func parseHeading(line string) (level string, text string) {
	m := headingRe.FindStringSubmatch(line)
	if m == nil {
		return "3", line
	}
	return string(rune('0' + len(m[1]))), m[2]
}

func isList(lines []string) bool {
	for _, l := range lines {
		if !strings.HasPrefix(strings.TrimSpace(l), "- ") {
			return false
		}
	}
	return true
}

var (
	boldRe  = regexp.MustCompile(`\*\*(.+?)\*\*`)
	italRe  = regexp.MustCompile(`\*(.+?)\*`)
	linkRe  = regexp.MustCompile(`\[(.+?)\]\((.+?)\)`)
)

// inline échappe le texte puis applique les transformations markdown en ligne.
func inline(text string) string {
	escaped := html.EscapeString(text)
	escaped = linkRe.ReplaceAllString(escaped, `<a href="$2" target="_blank" rel="noopener">$1</a>`)
	escaped = boldRe.ReplaceAllString(escaped, `<strong>$1</strong>`)
	escaped = italRe.ReplaceAllString(escaped, `<em>$1</em>`)
	return escaped
}
