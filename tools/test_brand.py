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
