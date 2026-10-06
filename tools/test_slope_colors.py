#!/usr/bin/env python3
"""Tests de tools/slope_colors.py — lancer avec :

    python3 -m unittest discover -s tools -p "test_*.py"
"""

import json
import os
import shutil
import tempfile
import unittest

import slope_colors as sc

# 1 degré de latitude ≈ 111,2 km : pas de 0,0009° ≈ 100 m.
STEP_DEG = 0.0009


def gpx_text(elevations, step_deg=STEP_DEG):
    pts = []
    for i, e in enumerate(elevations):
        ele = "" if e is None else "<ele>%s</ele>" % e
        pts.append('<trkpt lat="%.6f" lon="3.900000">%s</trkpt>' % (43.6 + i * step_deg, ele))
    return ('<?xml version="1.0"?><gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1">'
            "<trk><trkseg>%s</trkseg></trk></gpx>" % "".join(pts))


class TempRide:
    def __init__(self, elevations, step_deg=STEP_DEG):
        self.dir = tempfile.mkdtemp()
        self.gpx = os.path.join(self.dir, "trace.gpx")
        with open(self.gpx, "w") as f:
            f.write(gpx_text(elevations, step_deg))

    def cleanup(self):
        shutil.rmtree(self.dir)


class ClassifyTest(unittest.TestCase):
    def test_bounds(self):
        self.assertEqual(sc.classify(-10)[0], "descente-forte")
        self.assertEqual(sc.classify(-8)[0], "descente")       # borne basse incluse
        self.assertEqual(sc.classify(-3)[0], "descente-legere")
        self.assertEqual(sc.classify(0)[0], "plat")
        self.assertEqual(sc.classify(2)[0], "montee-faible")
        self.assertEqual(sc.classify(5.5)[0], "montee-moderee")
        self.assertEqual(sc.classify(9.99)[0], "montee-soutenue")
        self.assertEqual(sc.classify(25)[0], "montee-forte")

    def test_descents_never_classified_as_hard_climbs(self):
        for slope in (-30, -12, -8, -4):
            self.assertTrue(sc.classify(slope)[0].startswith("descente"))


class ElevationTest(unittest.TestCase):
    def test_fill_interpolates_by_distance(self):
        ele, ratio = sc.fill_elevations([100, None, None, 130], [0, 100, 200, 300])
        self.assertEqual(ele, [100, 110, 120, 130])
        self.assertEqual(ratio, 0.5)

    def test_fill_edges_and_empty(self):
        ele, _ = sc.fill_elevations([None, 50, None], [0, 10, 20])
        self.assertEqual(ele, [50, 50, 50])
        self.assertEqual(sc.fill_elevations([None, None], [0, 1]), (None, 0.0))

    def test_parse_invalid_elevations(self):
        self.assertIsNone(sc.parse_elevation("abc"))
        self.assertIsNone(sc.parse_elevation("nan"))
        self.assertIsNone(sc.parse_elevation("-9999"))
        self.assertEqual(sc.parse_elevation(" 12.5 "), 12.5)

    def test_smoothing_removes_noise(self):
        dist = [i * 10.0 for i in range(200)]
        noisy = [100 + (5 if i % 2 else -5) for i in range(200)]
        smoothed = sc.smooth_elevations(dist, noisy)
        self.assertLess(max(smoothed[20:-20]) - min(smoothed[20:-20]), 1.0)

    def test_zero_length_segments_do_not_divide_by_zero(self):
        dist = [0.0, 0.0, 0.0]
        self.assertEqual(sc.smooth_elevations(dist, [1, 2, 3]), [1, 2, 3])
        with self.assertRaises(sc.SlopeError):
            sc.build_segments([(43.6, 3.9, 10), (43.6, 3.9, 20)])


class SegmentsTest(unittest.TestCase):
    def test_constant_climb(self):
        # 40 points, +8 m tous les ~100 m : pente ≈ 8 %
        pts = [(43.6 + i * STEP_DEG, 3.9, 100 + 8 * i) for i in range(40)]
        segments, stats = sc.build_segments(pts)
        self.assertEqual({s["cls"][0] for s in segments}, {"montee-soutenue"})
        for s in segments:
            self.assertAlmostEqual(s["slope"], 8.0, delta=0.6)
        self.assertTrue(stats["elevation_ok"])

    def test_segments_are_contiguous(self):
        pts = [(43.6 + i * STEP_DEG / 3, 3.9, 100 + (i % 30)) for i in range(300)]
        segments, _ = sc.build_segments(pts)
        for a, b in zip(segments, segments[1:]):
            self.assertEqual(a["end"], b["start"])
            self.assertAlmostEqual(a["end_m"], b["start_m"])
        self.assertEqual(segments[0]["start"], 0)
        self.assertEqual(segments[-1]["end"], len(pts) - 1)

    def test_missing_elevations_give_unknown_class(self):
        pts = [(43.6 + i * STEP_DEG, 3.9, None if i % 3 else 10) for i in range(30)]
        segments, stats = sc.build_segments(pts)
        self.assertFalse(stats["elevation_ok"])
        self.assertEqual({s["cls"][0] for s in segments}, {"inconnue"})
        self.assertIsNone(segments[0]["slope"])


class ProcessRideTest(unittest.TestCase):
    def test_writes_geojson_without_touching_gpx(self):
        ride = TempRide([100 + 5 * i for i in range(30)] + [250 - 5 * i for i in range(30)])
        try:
            with open(ride.gpx, "rb") as f:
                before = f.read()
            status, _ = sc.process_ride(ride.dir)
            self.assertEqual(status, "written")
            with open(ride.gpx, "rb") as f:
                self.assertEqual(f.read(), before)

            with open(os.path.join(ride.dir, sc.OUTPUT_NAME)) as f:
                data = json.load(f)
            self.assertEqual(data["type"], "FeatureCollection")
            self.assertEqual(data["source_gpx"], "trace.gpx")
            props = data["features"][0]["properties"]
            for key in ("slope_pct", "start_km", "end_km", "color", "ele_start", "ele_end", "class"):
                self.assertIn(key, props)
            classes = {f["properties"]["class"] for f in data["features"]}
            self.assertIn("montee-moderee", classes)
            self.assertTrue(any(c.startswith("descente") for c in classes))

            self.assertEqual(sc.process_ride(ride.dir)[0], "up-to-date")
            self.assertEqual(sc.process_ride(ride.dir, check=True)[0], "up-to-date")

            with open(ride.gpx, "a") as f:
                f.write("\n<!-- trace modifiée -->\n")
            self.assertEqual(sc.process_ride(ride.dir, check=True)[0], "stale")
        finally:
            ride.cleanup()

    def test_ride_without_gpx_is_skipped(self):
        d = tempfile.mkdtemp()
        try:
            self.assertEqual(sc.process_ride(d)[0], "skipped")
        finally:
            shutil.rmtree(d)

    def test_invalid_gpx_reports_error(self):
        d = tempfile.mkdtemp()
        try:
            with open(os.path.join(d, "x.gpx"), "w") as f:
                f.write("<gpx><trk>")
            with self.assertRaises(sc.SlopeError):
                sc.process_ride(d)
            self.assertEqual(sc.main([d]), 1)
        finally:
            shutil.rmtree(d)


if __name__ == "__main__":
    unittest.main()
