package site

import (
	"fmt"
	"image"
	"image/draw"
	"image/jpeg"
	"image/png"
	"os"
	"path/filepath"
	"strings"
)

// maxPhotoSide : plus grand côté (px) des photos publiées sur le site. Les
// originaux, dans rides/, ne sont jamais modifiés.
const maxPhotoSide = 1024

// maxThumbSide : plus grand côté (px) des miniatures utilisées sur
// l'accueil (cartouches, popups de la carte) et en fond flou du carrousel.
const maxThumbSide = 640

// thumbDir : sous-dossier (relatif au dossier photos/ publié) qui contient
// les miniatures.
const thumbDir = "thumbs"

const jpegQuality = 85

// processPhotoFile publie la photo src vers dst :
//   - JPEG/PNG dont le plus grand côté dépasse maxSide : réduite à maxSide
//     (proportions conservées), orientation EXIF appliquée aux pixels pour
//     les JPEG, ré-encodée (JPEG qualité 85, PNG sans perte) ;
//   - JPEG avec une orientation EXIF non standard : ré-encodé même s'il est
//     déjà petit, sinon la photo s'afficherait couchée une fois les EXIF
//     ignorés par le navigateur ;
//   - autres cas (déjà petite, .webp, .gif) : copiée telle quelle.
func processPhotoFile(src, dst string, maxSide int) error {
	img, format, orientation, err := decodePhoto(src)
	if err != nil {
		return err
	}
	if img == nil {
		return copyFile(src, dst) // format non pris en charge par la bibliothèque standard
	}
	b := img.Bounds()
	if b.Dx() <= maxSide && b.Dy() <= maxSide && orientation == 1 {
		return copyFile(src, dst)
	}
	return encodePhoto(dst, format, applyOrientation(resizeToFit(img, maxSide), orientation))
}

// processThumbFile écrit une miniature de src (plus grand côté maxSide) dans
// dst. Pour un format non décodable (.webp, .gif), la photo est copiée telle
// quelle : la miniature existe toujours, elle n'est simplement pas allégée.
func processThumbFile(src, dst string, maxSide int) error {
	img, format, orientation, err := decodePhoto(src)
	if err != nil {
		return err
	}
	if img == nil {
		return copyFile(src, dst)
	}
	if format == "jpeg" {
		return encodeJPEG(dst, applyOrientation(resizeToFit(img, maxSide), orientation), 78)
	}
	return encodePhoto(dst, format, applyOrientation(resizeToFit(img, maxSide), orientation))
}

// thumbRel renvoie le chemin relatif de la miniature d'une photo
// (ex: "photos/a.jpg" -> "photos/thumbs/a.jpg").
func thumbRel(photoRel string) string {
	return filepath.ToSlash(filepath.Join(filepath.Dir(photoRel), thumbDir, filepath.Base(photoRel)))
}

// decodePhoto décode un JPEG ou un PNG. Renvoie img == nil (sans erreur)
// pour les autres formats.
func decodePhoto(path string) (img image.Image, format string, orientation int, err error) {
	ext := strings.ToLower(filepath.Ext(path))
	if ext != ".jpg" && ext != ".jpeg" && ext != ".png" {
		return nil, "", 1, nil
	}
	f, err := os.Open(path)
	if err != nil {
		return nil, "", 1, err
	}
	defer f.Close()

	if ext == ".png" {
		img, err = png.Decode(f)
		if err != nil {
			return nil, "", 1, fmt.Errorf("décodage PNG : %w", err)
		}
		return img, "png", 1, nil
	}
	img, err = jpeg.Decode(f)
	if err != nil {
		return nil, "", 1, fmt.Errorf("décodage JPEG : %w", err)
	}
	return img, "jpeg", PhotoOrientation(path), nil
}

func encodePhoto(dst, format string, img image.Image) error {
	if format == "png" {
		out, err := os.Create(dst)
		if err != nil {
			return err
		}
		defer out.Close()
		return png.Encode(out, img)
	}
	return encodeJPEG(dst, img, jpegQuality)
}

func encodeJPEG(dst string, img image.Image, quality int) error {
	out, err := os.Create(dst)
	if err != nil {
		return err
	}
	defer out.Close()
	return jpeg.Encode(out, img, &jpeg.Options{Quality: quality})
}

// resizeToFit réduit img pour que son plus grand côté fasse au plus maxSide,
// par moyenne de zone (box filter) : simple, sans dépendance, et sans
// crénelage pour une réduction (c'est le seul cas utile ici). L'image est
// renvoyée telle quelle (convertie en RGBA) si elle est déjà assez petite.
func resizeToFit(img image.Image, maxSide int) *image.RGBA {
	b := img.Bounds()
	src := image.NewRGBA(image.Rect(0, 0, b.Dx(), b.Dy()))
	draw.Draw(src, src.Bounds(), img, b.Min, draw.Src)

	sw, sh := b.Dx(), b.Dy()
	if sw <= maxSide && sh <= maxSide {
		return src
	}
	dw, dh := maxSide, maxSide
	if sw >= sh {
		dh = max(1, int(float64(sh)*float64(maxSide)/float64(sw)+0.5))
	} else {
		dw = max(1, int(float64(sw)*float64(maxSide)/float64(sh)+0.5))
	}

	dst := image.NewRGBA(image.Rect(0, 0, dw, dh))
	for dy := 0; dy < dh; dy++ {
		y0 := dy * sh / dh
		y1 := max(y0+1, (dy+1)*sh/dh)
		for dx := 0; dx < dw; dx++ {
			x0 := dx * sw / dw
			x1 := max(x0+1, (dx+1)*sw/dw)
			var r, g, bl, a, n uint32
			for y := y0; y < y1; y++ {
				row := src.Pix[y*src.Stride+x0*4 : y*src.Stride+x1*4]
				for i := 0; i < len(row); i += 4 {
					r += uint32(row[i])
					g += uint32(row[i+1])
					bl += uint32(row[i+2])
					a += uint32(row[i+3])
					n++
				}
			}
			o := dy*dst.Stride + dx*4
			dst.Pix[o] = uint8(r / n)
			dst.Pix[o+1] = uint8(g / n)
			dst.Pix[o+2] = uint8(bl / n)
			dst.Pix[o+3] = uint8(a / n)
		}
	}
	return dst
}

// applyOrientation applique aux pixels la transformation décrite par le tag
// EXIF Orientation (1 à 8), pour que l'image s'affiche dans le bon sens
// sans dépendre des métadonnées (supprimées au ré-encodage).
func applyOrientation(img *image.RGBA, orientation int) *image.RGBA {
	if orientation < 2 || orientation > 8 {
		return img
	}
	w, h := img.Bounds().Dx(), img.Bounds().Dy()
	dw, dh := w, h
	if orientation >= 5 {
		dw, dh = h, w // rotation de 90° : dimensions échangées
	}
	dst := image.NewRGBA(image.Rect(0, 0, dw, dh))
	for y := 0; y < h; y++ {
		for x := 0; x < w; x++ {
			var nx, ny int
			switch orientation {
			case 2: // miroir horizontal
				nx, ny = w-1-x, y
			case 3: // rotation 180°
				nx, ny = w-1-x, h-1-y
			case 4: // miroir vertical
				nx, ny = x, h-1-y
			case 5: // transposition
				nx, ny = y, x
			case 6: // rotation 90° horaire
				nx, ny = h-1-y, x
			case 7: // transverse
				nx, ny = h-1-y, w-1-x
			case 8: // rotation 90° anti-horaire
				nx, ny = y, w-1-x
			}
			so := y*img.Stride + x*4
			do := ny*dst.Stride + nx*4
			copy(dst.Pix[do:do+4], img.Pix[so:so+4])
		}
	}
	return dst
}
