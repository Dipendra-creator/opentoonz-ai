"""Tests for the .tnz model: stream format, keyframe math and round trips.

Run:  ai/.venv/Scripts/python -m unittest discover -s ai/tests
"""

import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from otai.tnz.model import INCH, Curve, Scene  # noqa: E402
from otai.tnz.stream import format_value, parse  # noqa: E402


class StreamTests(unittest.TestCase):
    def test_quoting_matches_tostream(self):
        self.assertEqual(format_value('Riya_mouth'), 'Riya_mouth')
        self.assertEqual(format_value('two words'), '"two words"')
        self.assertEqual(format_value('a"b\\c'), '"a\\"b\\\\c"')
        self.assertEqual(format_value(''), '""')
        self.assertEqual(format_value(3), '3')

    def test_parse_persist_refs(self):
        root = parse("<a><level id='1'>name <info dpix=\"120\"/><path>\"$scenefolder/x..png\"</path></level>"
                     "<cell>0 2 <level id='1'/> 1 1</cell></a>")
        a = root.find('a')
        lv = a.find('level')
        self.assertFalse(lv.self_closing)
        self.assertEqual(lv.tokens()[0], 'name')
        self.assertEqual(lv.find('path').text(), '$scenefolder/x..png')
        ref = a.find('cell').find('level')
        self.assertTrue(ref.self_closing)
        self.assertEqual(a.find('cell').tokens(), ['0', '2', '1', '1'])


class CurveTests(unittest.TestCase):
    def test_linear_and_hold(self):
        c = Curve(0)
        c.set_key(0, 0)
        c.set_key(10, 10)
        self.assertAlmostEqual(c.value(5), 5)
        self.assertEqual(c.value(-3), 0)
        self.assertEqual(c.value(30), 10)

    def test_step_on_twos(self):
        c = Curve(0)
        c.set_key(0, 0, step=2)
        c.set_key(10, 10)
        self.assertEqual(c.value(1), 0)
        self.assertEqual(c.value(3), c.value(2))

    def test_constant(self):
        c = Curve(0)
        c.set_key(0, 1, 'constant')
        c.set_key(5, 2)
        self.assertEqual(c.value(4.9), 1)
        self.assertEqual(c.value(5), 2)

    def test_ease_is_symmetric_and_bounded(self):
        c = Curve(0)
        c.set_key(0, 0, 'ease', ease_out=5)
        c.set_key(20, 1, 'linear', ease_in=5)
        self.assertAlmostEqual(c.value(10), 0.5, places=6)
        self.assertLess(c.value(2), 2 / 20)  # slower than linear at the start


class SceneRoundTrip(unittest.TestCase):
    def test_save_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = Scene(res=(1280, 720), fps=24)
            s.add_level('hero arm', '$scenefolder/assets/hero..png', 240)
            peg = s.new_pegbar('hero')
            peg.curve('x').set_key(0, -2, 'ease', ease_out=4)
            peg.curve('x').set_key(24, 2, 'linear', ease_in=4)
            idx, col = s.add_column('arm', parent=peg.id)
            col.set_cells(0, 'hero arm', [1, 1, 2, 3, 4, 5, 5, 5])
            obj = s.column_object(idx)
            obj.set_pivot(0.5, 1.0)
            obj.curve('rot').set_key(0, 0, step=2)
            obj.curve('rot').set_key(8, 45)
            path = s.save(Path(tmp) / 'scene.tnz')
            r = Scene.load(path)
            self.assertEqual(r.camera.res, (1280, 720))
            self.assertEqual(r.columns[0].cells, s.columns[0].cells)
            self.assertEqual(r.column_object(0).parent, peg.id)
            for f in (0, 3, 7, 12, 24):
                np.testing.assert_allclose(r.placement('Col1', f), s.placement('Col1', f), atol=1e-6)
            self.assertEqual(r.warnings, [])

    def test_pivot_keeps_rest_position(self):
        s = Scene()
        obj = s.object('Col1')
        before = obj.local_affine(0) @ np.array([1.0, 1.0, 1.0])
        obj.set_pivot(2, 3)
        after = obj.local_affine(0) @ np.array([1.0, 1.0, 1.0])
        np.testing.assert_allclose(before, after)
        obj.curve('rot').default = 90
        pivot = obj.local_affine(0) @ np.array([2 * INCH, 3 * INCH, 1.0])
        np.testing.assert_allclose(pivot[:2], [2 * INCH, 3 * INCH], atol=1e-6)


if __name__ == '__main__':
    unittest.main()
