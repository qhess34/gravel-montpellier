#!/usr/bin/env python3
"""
Tests navigateur du site généré (Playwright pour Python, Chromium).

Ils génèrent le site dans un dossier temporaire, le servent en local et
vérifient l'accueil et une fiche : carte, filtres, profil, liste des POI,
fonds de carte, couches (dont les pentes calculées), plein écran, sans
erreur JavaScript.

Aucun appel réseau vers les services de cartes : les tuiles sont simulées
(images unies, et tuiles d'altitude synthétiques pour la couche des
pentes), les API Panoramax et de statistiques sont neutralisées. Seul
Leaflet est chargé depuis unpkg, sauf si LEAFLET_DIR désigne un dossier
local contenant leaflet.js et leaflet.css.

Installation et lancement :
    pip install playwright
    python3 -m playwright install chromium
    python3 -m unittest discover -s tests/e2e -v

Variables d'environnement facultatives :
    CHROMIUM_PATH  exécutable Chromium à utiliser (sinon celui de Playwright)
    LEAFLET_DIR    dossier local de Leaflet 1.9.4 (leaflet.js, leaflet.css)

Ignorés (skip) si Playwright ou Go ne sont pas installés.
"""

import functools
import http.server
import json
import math
import os
import shutil
import struct
import subprocess
import tempfile
import threading
import unittest
import zlib

try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RIDE = "clapiers-corconne"  # sortie de référence : GPX, pentes, POI, photos

TILE_HOSTS = ("tile.openstreetmap.org", "tile-cyclosm", "opentopomap.org", "data.geopf.fr", "waymarkedtrails.org")
TERRAIN_MAX_ZOOM_SERVED = 12  # au-delà : 404, pour tester le repli de la couche des pentes
TERRAIN_SLOPE = 0.20          # pente de la moitié droite des tuiles d'altitude synthétiques
SLOPE_20_COLOR = (245, 158, 11)  # #f59e0b : classe 15–25 % de GM_TERRAIN_SLOPES


def png(width, height, row_bytes):
    """PNG RGB minimal (bibliothèque standard) ; row_bytes(y) -> bytes RGB."""
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + row_bytes(y) for y in range(height))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


BASE_TILE = png(256, 256, lambda y: bytes((236, 232, 220)) * 256)


@functools.lru_cache(maxsize=None)
def terrain_tile(z):
    """Tuile d'altitude Terrarium 512 px : moitié gauche plate, moitié droite
    à TERRAIN_SLOPE (calculée pour la latitude de Montpellier)."""
    m = 40075016.686 * math.cos(math.radians(43.7)) / (512 * 2 ** z)
    row = bytearray()
    for c in range(512):
        e = 1000.0 + (0 if c < 256 else TERRAIN_SLOPE * m * (c - 256)) + 32768
        row += bytes((int(e // 256), int(e % 256), int((e - int(e)) * 256)))
    row = bytes(row)
    return png(512, 512, lambda y: row)


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@unittest.skipUnless(HAS_PLAYWRIGHT, "Playwright non installé (pip install playwright)")
@unittest.skipUnless(shutil.which("go"), "Go non installé")
class SiteTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="cycloexplore-e2e-")
        out = os.path.join(cls.tmp, "public")
        subprocess.run(["go", "run", "./cmd/generator", "-umami-id", "", "-out", out],
                       cwd=REPO, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        handler = functools.partial(_Quiet, directory=out)
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        cls.base = "http://127.0.0.1:%d/" % cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.pw = sync_playwright().start()
        kwargs = {}
        if os.environ.get("CHROMIUM_PATH"):
            kwargs["executable_path"] = os.environ["CHROMIUM_PATH"]
        cls.browser = cls.pw.chromium.launch(**kwargs)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.server.shutdown()
        cls.server.server_close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    # --- outillage -------------------------------------------------------------

    def open(self, path, width=1280, height=800, storage=None):
        """Nouvelle page avec réseau simulé ; renvoie (page, erreurs JS, zooms
        des tuiles d'altitude demandées)."""
        ctx = self.browser.new_context(viewport={"width": width, "height": height})
        self.addCleanup(ctx.close)
        terrain_zooms = []

        def route(r):
            url = r.request.url
            if "tiles.mapterhorn.com/" in url:
                z = int(url.split("tiles.mapterhorn.com/")[1].split("/")[0])
                terrain_zooms.append(z)
                if z > TERRAIN_MAX_ZOOM_SERVED:
                    return r.fulfill(status=404, body="")
                return r.fulfill(body=terrain_tile(z), content_type="image/webp",
                                 headers={"Access-Control-Allow-Origin": "*"})
            if any(h in url for h in TILE_HOSTS):
                return r.fulfill(body=BASE_TILE, content_type="image/png")
            if "panoramax" in url and "/api/" in url:
                return r.fulfill(body='{"features":[]}', content_type="application/json")
            if "unpkg.com/leaflet@" in url and os.environ.get("LEAFLET_DIR"):
                name = url.rsplit("/", 1)[1]
                return r.fulfill(path=os.path.join(os.environ["LEAFLET_DIR"], name),
                                 content_type="text/css" if name.endswith(".css") else "application/javascript")
            if url.startswith(self.base) or "unpkg.com" in url:
                return r.continue_()
            return r.abort()  # statistiques, polices, iframes externes…

        ctx.route("**/*", route)
        if storage:
            ctx.add_init_script("(function(s){for(var k in s)localStorage.setItem(k,s[k]);})(%s)" % json.dumps(storage))
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(self.base + path)
        return page, errors, terrain_zooms

    def open_ride(self, **kw):
        page, errors, zooms = self.open("rides/%s/" % RIDE, **kw)
        page.wait_for_function("document.querySelectorAll('#map path').length > 20")
        page.evaluate("document.getElementById('map').scrollIntoView({block: 'center', behavior: 'instant'})")
        return page, errors, zooms

    # --- accueil -----------------------------------------------------------------

    def test_home_map_cards_and_filters(self):
        page, errors, _ = self.open("")
        page.wait_for_function("document.querySelectorAll('.leaflet-container path').length > 0")
        total = page.locator("[data-slug].ride-card").count()
        self.assertGreater(total, 0)
        diff = page.locator("button[data-difficulty]").first
        if diff.count():
            diff.click()
            visible = page.evaluate("[...document.querySelectorAll('[data-slug].ride-card')].filter(c => !c.hidden).length")
            self.assertLessEqual(visible, total)
            self.assertIn("difficulte=", page.evaluate("location.hash"))
        self.assertEqual(errors, [])

    # --- fiche ---------------------------------------------------------------------

    def test_ride_profile_hover_and_poi_list(self):
        page, errors, _ = self.open_ride()
        svg = page.locator(".elevation-profile")
        box = svg.bounding_box()
        page.mouse.move(box["x"] + box["width"] * 0.5, box["y"] + box["height"] * 0.5)
        tooltip = page.locator(".elevation-tooltip")
        tooltip.wait_for(state="visible")
        self.assertIn("PK", tooltip.inner_text())
        self.assertEqual(page.locator(".gm-hover-marker").count(), 1)  # repère synchronisé sur la carte
        page.mouse.move(0, 0)
        first = page.locator(".poi-item").first
        first.scroll_into_view_if_needed()
        first.click()
        page.locator(".gm-poi-popup").wait_for(state="visible")
        self.assertEqual(errors, [])

    def test_basemap_choice_is_remembered(self):
        page, errors, _ = self.open_ride()
        page.click(".gm-basemap-toggle")
        page.click("[data-basemap=relief]")
        self.assertEqual(page.get_attribute("#map", "data-basemap"), "relief")
        page.reload()
        page.wait_for_function("document.querySelectorAll('#map path').length > 20")
        self.assertEqual(page.get_attribute("#map", "data-basemap"), "relief")
        self.assertEqual(errors, [])

    def test_overlays_and_terrain_slope_layer(self):
        page, errors, zooms = self.open_ride()
        page.click(".gm-basemap-toggle")
        for key in ("ombrage", "pentes", "itineraires"):
            page.click("[data-overlay=%s]" % key)
        self.assertFalse(page.evaluate("document.querySelector('.gm-basemap-list').hidden"))  # menu resté ouvert
        self.assertEqual(page.get_attribute("#map", "data-overlays"), "ombrage pentes itineraires")
        attribution = page.inner_text(".leaflet-control-attribution")
        for name in ("IGN", "Mapterhorn", "Waymarked Trails"):
            self.assertIn(name, attribution)
        page.keyboard.press("Escape")
        # zoom 15 : tuiles d'altitude 14 et 13 absentes (404) -> repli sur 12
        page.evaluate("map.setView([43.75, 3.88], 15, {animate: false})")
        page.wait_for_function("document.querySelectorAll('.gm-overlay-slope canvas.leaflet-tile-loaded').length > 0")
        page.wait_for_timeout(500)
        colors = page.evaluate("""() => {
            const counts = {};
            document.querySelectorAll('.gm-overlay-slope canvas').forEach(t => {
                const d = t.getContext('2d').getImageData(0, 0, t.width, t.height).data;
                for (let i = 3; i < d.length; i += 4 * 61) {
                    const k = d[i] ? d[i-3] + ',' + d[i-2] + ',' + d[i-1] : 'transparent';
                    counts[k] = (counts[k] || 0) + 1;
                }
            });
            return counts;
        }""")
        self.assertIn("transparent", colors)  # moitié plate
        coloured = {k: v for k, v in colors.items() if k != "transparent"}
        self.assertTrue(coloured, colors)
        dominant = max(coloured, key=coloured.get)
        self.assertEqual(tuple(int(x) for x in dominant.split(",")), SLOPE_20_COLOR, colors)
        for z in (14, 13, 12):
            self.assertIn(z, zooms)
        self.assertEqual(errors, [])

    def test_fullscreen(self):
        page, errors, _ = self.open_ride()
        page.click(".gm-fullscreen-btn")
        page.wait_for_function("document.querySelector('.gm-fullscreen-btn').getAttribute('aria-pressed') === 'true'")
        page.wait_for_function("map.getSize().x === innerWidth && map.getSize().y === innerHeight")  # Leaflet redimensionné
        page.click(".gm-fullscreen-btn")
        page.wait_for_function("document.querySelector('.gm-fullscreen-btn').getAttribute('aria-pressed') === 'false'")
        self.assertEqual(errors, [])

    def test_mobile_layer_menu_fits_without_scrolling(self):
        page, errors, _ = self.open_ride(width=375, height=812)
        page.click(".gm-basemap-toggle")
        fit = page.evaluate("""() => {
            const l = document.querySelector('.gm-basemap-list');
            const m = document.getElementById('map').getBoundingClientRect();
            const b = l.getBoundingClientRect();
            return {scroll: l.scrollHeight, client: l.clientHeight, inside: b.left >= m.left && b.bottom <= m.bottom};
        }""")
        self.assertLessEqual(fit["scroll"], fit["client"] + 1, fit)
        self.assertTrue(fit["inside"], fit)
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
