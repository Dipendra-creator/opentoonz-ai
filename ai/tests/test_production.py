"""Smoke test of the production path without network: build a character and
a set, compile a shot to .tnz, reload it and render a frame (~20 s)."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from otai.production.schema import BackgroundSpec, CharacterSpec, Shot  # noqa: E402
from otai.production.studio import Studio  # noqa: E402
from otai.tnz.model import Scene  # noqa: E402
from otai.production.rigging import PART_ORDER  # noqa: E402

import numpy as np  # noqa: E402


class ProductionSmoke(unittest.TestCase):
    def test_shot_compiles_to_loadable_scene(self):
        with tempfile.TemporaryDirectory() as tmp:
            st = Studio(Path(tmp))
            p = st.create('Smoke', resolution='480p', tts_engine='none')
            st.add_character(p.id, CharacterSpec(name='Mei', hair_style='twintails', top='dress'))
            p = st.load(p.id)
            st.add_background(p.id, BackgroundSpec(name='Park', location='park'))
            shot = Shot(background='Park', shot_type='closeup', focus='Mei',
                        characters=[{'name': 'Mei', 'emotion': 'happy'}],
                        beats=[{'kind': 'dialogue', 'character': 'Mei', 'text': 'What a lovely day!',
                                'action': 'wave'},
                               {'kind': 'reaction', 'character': 'Mei', 'emotion': 'surprised'}])
            report = st.add_shots(p.id, [shot])
            self.assertEqual(report['rejected'], {})
            tnz = st.dir(p.id) / 'scenes' / 's001.tnz'
            scene = Scene.load(tnz)
            self.assertEqual(scene.warnings, [])
            self.assertGreater(scene.frame_count, 24)
            self.assertEqual(len(scene.columns), 1 + len(PART_ORDER) + 1)  # background, rig, captions
            # the baked .tnz reproduces the in-memory animation
            mem, _ = st.scene_for(st.load(p.id), st.load(p.id).shots[0])
            for f in (0, 7, 20, scene.frame_count - 1):
                for oid in ('Col2', 'Col12', 'Col21', 'Camera1'):
                    np.testing.assert_allclose(scene.placement(oid, f), mem.placement(oid, f), atol=0.05)
            png = st.preview(p.id, 's001', 0.3)
            self.assertTrue(png.exists())
            bad = Shot(background='Nowhere', characters=[{'name': 'Ghost'}],
                       beats=[{'kind': 'dialogue', 'character': 'Ghost', 'text': 'boo'}])
            self.assertIn('#0', st.add_shots(p.id, [bad])['rejected'])


if __name__ == '__main__':
    unittest.main()
