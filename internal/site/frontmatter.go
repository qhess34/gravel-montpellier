package site

import (
	"fmt"
	"strings"
)

// ParseFrontMatter sépare un fichier texte en un bloc d'en-tête
// (clé: valeur, délimité par des lignes "---") et le corps restant.
//
// Exemple attendu :
//
//	---
//	title: Tour du Pic Saint-Loup
//	date: 2026-06-15
//	---
//	Le reste du fichier est le corps en markdown.
func ParseFrontMatter(content string) (map[string]string, string, error) {
	content = strings.ReplaceAll(content, "\r\n", "\n")
	lines := strings.Split(content, "\n")

	if len(lines) == 0 || strings.TrimSpace(lines[0]) != "---" {
		return nil, "", fmt.Errorf("le fichier doit commencer par une ligne '---'")
	}

	fields := map[string]string{}
	i := 1
	for ; i < len(lines); i++ {
		line := lines[i]
		if strings.TrimSpace(line) == "---" {
			i++ // on saute la ligne de fermeture
			break
		}
		if strings.TrimSpace(line) == "" {
			continue
		}
		key, value, ok := strings.Cut(line, ":")
		if !ok {
			continue // ligne mal formée, on l'ignore silencieusement
		}
		key = strings.TrimSpace(key)
		value = strings.TrimSpace(value)
		value = strings.Trim(value, `"'`)
		fields[key] = value
	}

	body := ""
	if i < len(lines) {
		body = strings.Join(lines[i:], "\n")
	}
	body = strings.TrimLeft(body, "\n")

	return fields, body, nil
}
