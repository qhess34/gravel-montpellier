#!/usr/bin/env python3
"""Tests de tools/brand.py et des générateurs d'images (ignorés sans Pillow) :

    python3 -m unittest discover -s tools -p "test_*.py"
"""

import os
import tempfile
import unittest

try:
    import PIL  # noqa: F401
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    import segno  # noqa: F401
    HAS_SEGNO = True
except ImportError:
    HAS_SEGNO = False

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RIDE = os.path.join(REPO, "rides", "clapiers-corconne")


@unittest.skipUnless(HAS_PIL, "Pillow non installé")
class BrandTest(unittest.TestCase):
    def setUp(self):
        import brand
        self.B = brand

    def test_duration_same_rules_as_site(self):
        self.assertEqual(self.B.duration_text("", ["1 jour", "gravel"]), "1 jour")
        self.assertEqual(self.B.duration_text("", ["5 jours", "2 jours"]), "2 à 5 jours")
        self.assertEqual(self.B.duration_text("4 h", ["1 jour"]), "4 h")
        self.assertEqual(self.B.duration_text("", ["gravel"]), "")

    def test_difficulty_and_summary(self):
        self.assertEqual(self.B.difficulty_key("Moyen"), "moyenne")
        self.assertEqual(self.B.difficulty_key("Très difficile"), "tres-difficile")
        body = "Intro **forte** et [lien](https://x.fr).\n\n## Le parcours\n\nSuite."
        self.assertEqual(self.B.summary_text(body), "Intro forte et lien.")

    def test_load_ride_reads_files_without_inventing(self):
        ride = self.B.load_ride(RIDE)
        self.assertEqual(ride["slug"], "clapiers-corconne")
        self.assertTrue(ride["title"])
        self.assertTrue(ride["track"] and ride["slope"] and ride["photos"])
        self.assertTrue(ride["url"].endswith("/rides/clapiers-corconne/"))

    def test_basemap_aligned_with_route(self):
        """Le fond de carte (tuiles Web Mercator) et la trace se superposent."""
        import math
        from PIL import Image, ImageDraw
        ride = self.B.load_ride(RIDE)
        pts = [(p[0], p[1]) for p in ride["track"]]
        target = pts[len(pts) // 2]

        def fake(provider, z, x, y):
            im = Image.new("RGB", (256, 256), (236, 232, 220))
            px, py = self.B._merc(*target)
            lx, ly = px * 2 ** z - x * 256, py * 2 ** z - y * 256
            ImageDraw.Draw(im).ellipse((lx - 6, ly - 6, lx + 6, ly + 6), fill=(255, 0, 255))
            return im

        img, proj = self.B.basemap(pts, (600, 400), "ign", fetch=fake)
        ex, ey = proj(*target)
        hits = [(x, y) for x in range(int(ex) - 30, int(ex) + 30) for y in range(int(ey) - 30, int(ey) + 30)
                if img.getpixel((x, y))[0] > 180 and img.getpixel((x, y))[2] > 180 and img.getpixel((x, y))[1] < 120]
        cx = sum(h[0] for h in hits) / len(hits)
        cy = sum(h[1] for h in hits) / len(hits)
        self.assertLess(math.hypot(cx - ex, cy - ey), 2.0)

    def test_basemap_unavailable_falls_back(self):
        def offline(*args):
            raise OSError("pas de réseau")
        ride = self.B.load_ride(RIDE)
        img, proj = self.B.basemap([(p[0], p[1]) for p in ride["track"]], (300, 300), "osm", fetch=offline)
        self.assertIsNone(img)
        import make_instagram_image as M
        self.assertEqual(M.render(ride, "post", fetch=offline).size, (1080, 1350))
        self.assertFalse(ride["basemap_ok"])

    def test_instagram_formats(self):
        import make_instagram_image as M
        ride = self.B.load_ride(RIDE)
        for fmt, size in (("post", (1080, 1350)), ("story", (1080, 1920)), ("carre", (1080, 1080))):
            self.assertEqual(M.render(ride, fmt).size, size)


@unittest.skipUnless(HAS_PIL and HAS_SEGNO, "Pillow / segno non installés")
class QRCodeTest(unittest.TestCase):
    def test_visuals_and_plain_qr(self):
        import generate_qrcode as G
        import brand as B
        ride = B.load_ride(RIDE)
        info = dict(title=ride["title"], distance="78 km", dplus="798 m D+", duration="1 jour",
                    difficulty="Difficile", photo=ride["photos"][0], display_url=ride["url"])
        self.assertEqual(G.render(info, "carre", ride["url"]).size, (1080, 1080))
        self.assertEqual(G.render(info, "affiche", ride["url"]).size, (1080, 1350))
        qr = G.styled_qr(ride["url"], 600)
        self.assertEqual(qr.size, (600, 600))
        # Relecture du QR stylé si OpenCV est disponible (sinon None : test non bloquant)
        self.assertIn(G.verify(qr, ride["url"]), (True, None))


@unittest.skipUnless(HAS_PIL, "Pillow non installé")
class NewRideTest(unittest.TestCase):
    def test_slug_and_dir_resolution(self):
        import new_ride as N
        self.assertEqual(N.slugify("Tour du Pic Saint-Loup"), "tour-du-pic-saint-loup")
        self.assertTrue(N.resolve_ride_dir("tour").endswith(os.path.join("rides", "tour")))
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(N.resolve_ride_dir(d), d)


if __name__ == "__main__":
    unittest.main()
