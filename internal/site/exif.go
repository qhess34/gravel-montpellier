package site

import (
	"bytes"
	"encoding/binary"
	"os"
)

// PhotoGPS tente de lire les coordonnées GPS EXIF d'une photo JPEG.
// Renvoie ok=false si le fichier n'est pas un JPEG, n'a pas de bloc EXIF,
// ou n'a pas de tags GPS (cas fréquent : photo recadrée/exportée par un
// réseau social, qui retire souvent les métadonnées).
func PhotoGPS(path string) (lat, lon float64, ok bool) {
	data, err := os.ReadFile(path)
	if err != nil {
		return 0, 0, false
	}
	return parseJPEGGPS(data)
}

func parseJPEGGPS(data []byte) (lat, lon float64, ok bool) {
	if len(data) < 4 || data[0] != 0xFF || data[1] != 0xD8 {
		return 0, 0, false // pas un JPEG (SOI manquant)
	}

	pos := 2
	for pos+4 <= len(data) {
		if data[pos] != 0xFF {
			pos++
			continue
		}
		marker := data[pos+1]

		// Marqueurs sans segment de longueur associé.
		if marker == 0x01 || (marker >= 0xD0 && marker <= 0xD9) {
			pos += 2
			continue
		}

		segLen := int(binary.BigEndian.Uint16(data[pos+2 : pos+4]))
		segStart := pos + 4
		segEnd := pos + 2 + segLen
		if segLen < 2 || segEnd > len(data) {
			break
		}

		if marker == 0xE1 { // APP1 : c'est ici que vit l'EXIF
			seg := data[segStart:segEnd]
			if bytes.HasPrefix(seg, []byte("Exif\x00\x00")) {
				if lt, ln, found := parseTIFFGPS(seg[6:]); found {
					return lt, ln, true
				}
			}
		}

		if marker == 0xDA { // Start Of Scan : les données image suivent, on arrête
			break
		}

		pos = segEnd
	}

	return 0, 0, false
}

// --- Lecture d'un mini sous-ensemble de la structure TIFF/EXIF ---

type ifdEntry struct {
	tag   uint16
	typ   uint16
	count uint32
	raw   [4]byte // octets bruts du champ valeur/offset, tels que stockés dans le fichier
}

func (e ifdEntry) offset(order binary.ByteOrder) uint32 {
	return order.Uint32(e.raw[:])
}

func parseTIFFGPS(tiff []byte) (lat, lon float64, found bool) {
	if len(tiff) < 8 {
		return 0, 0, false
	}

	var order binary.ByteOrder
	switch string(tiff[0:2]) {
	case "II":
		order = binary.LittleEndian
	case "MM":
		order = binary.BigEndian
	default:
		return 0, 0, false
	}

	ifd0Offset := order.Uint32(tiff[4:8])
	gpsOffset, ok := findIFDTagOffset(tiff, order, ifd0Offset, 0x8825) // GPS Info IFD pointer
	if !ok {
		return 0, 0, false
	}

	return readGPSIFD(tiff, order, gpsOffset)
}

func readIFDEntries(tiff []byte, order binary.ByteOrder, offset uint32) ([]ifdEntry, bool) {
	if int(offset)+2 > len(tiff) {
		return nil, false
	}
	count := int(order.Uint16(tiff[offset : offset+2]))
	base := int(offset) + 2

	entries := make([]ifdEntry, 0, count)
	for i := 0; i < count; i++ {
		start := base + i*12
		if start+12 > len(tiff) {
			return nil, false
		}
		var e ifdEntry
		e.tag = order.Uint16(tiff[start : start+2])
		e.typ = order.Uint16(tiff[start+2 : start+4])
		e.count = order.Uint32(tiff[start+4 : start+8])
		copy(e.raw[:], tiff[start+8:start+12])
		entries = append(entries, e)
	}
	return entries, true
}

func findIFDTagOffset(tiff []byte, order binary.ByteOrder, ifdOffset uint32, wantTag uint16) (uint32, bool) {
	entries, ok := readIFDEntries(tiff, order, ifdOffset)
	if !ok {
		return 0, false
	}
	for _, e := range entries {
		if e.tag == wantTag {
			return e.offset(order), true
		}
	}
	return 0, false
}

func readGPSIFD(tiff []byte, order binary.ByteOrder, offset uint32) (lat, lon float64, found bool) {
	entries, ok := readIFDEntries(tiff, order, offset)
	if !ok {
		return 0, 0, false
	}

	var latRef, lonRef string
	var haveLat, haveLon bool

	for _, e := range entries {
		switch e.tag {
		case 0x0001: // GPSLatitudeRef ("N" ou "S")
			latRef = readASCII(tiff, order, e)
		case 0x0003: // GPSLongitudeRef ("E" ou "W")
			lonRef = readASCII(tiff, order, e)
		case 0x0002: // GPSLatitude (degrés, minutes, secondes)
			if v, ok := readRationalDMS(tiff, order, e); ok {
				lat = v
				haveLat = true
			}
		case 0x0004: // GPSLongitude (degrés, minutes, secondes)
			if v, ok := readRationalDMS(tiff, order, e); ok {
				lon = v
				haveLon = true
			}
		}
	}

	if !haveLat || !haveLon {
		return 0, 0, false
	}
	if latRef == "S" {
		lat = -lat
	}
	if lonRef == "W" {
		lon = -lon
	}
	return lat, lon, true
}

// readASCII lit une valeur de type ASCII (2), en gérant le stockage
// "inline" (≤4 octets) ou déporté via offset.
func readASCII(tiff []byte, order binary.ByteOrder, e ifdEntry) string {
	size := int(e.count)
	var b []byte
	if size <= 4 {
		b = append([]byte(nil), e.raw[:min4(size)]...)
	} else {
		off := int(e.offset(order))
		if off < 0 || off+size > len(tiff) {
			return ""
		}
		b = tiff[off : off+size]
	}
	if i := bytes.IndexByte(b, 0); i >= 0 {
		b = b[:i]
	}
	return string(b)
}

func min4(n int) int {
	if n > 4 {
		return 4
	}
	if n < 0 {
		return 0
	}
	return n
}

// readRationalDMS lit un triplet RATIONAL (type 5, 3 valeurs) représentant
// degrés/minutes/secondes, et renvoie l'équivalent en degrés décimaux.
func readRationalDMS(tiff []byte, order binary.ByteOrder, e ifdEntry) (float64, bool) {
	if e.typ != 5 || e.count < 3 {
		return 0, false
	}
	off := int(e.offset(order))
	need := 3 * 8
	if off < 0 || off+need > len(tiff) {
		return 0, false
	}

	dms := make([]float64, 3)
	for i := 0; i < 3; i++ {
		start := off + i*8
		num := order.Uint32(tiff[start : start+4])
		den := order.Uint32(tiff[start+4 : start+8])
		if den == 0 {
			return 0, false
		}
		dms[i] = float64(num) / float64(den)
	}

	return dms[0] + dms[1]/60 + dms[2]/3600, true
}
