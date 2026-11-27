"""用仓库中真实论文图的尺寸检查裁剪方向、取证分工与二分类输出。"""

import json
import unittest
from pathlib import Path

from science_image.paper import PAPER_ROLES, paper_tiles
from science_image.pipeline import run
from science_image.views import ImageViews

ROOT = Path(__file__).resolve().parents[1]


class PaperTests(unittest.TestCase):
    def test_long_strip_covers_source_with_overlap(self):
        for width, height in [(1559, 134), (134, 1559), (574, 349), (10800, 3600)]:
            boxes = [v[0] for v in paper_tiles(width, height).values()]
            self.assertEqual(boxes[0][:2], (0, 0))
            self.assertEqual(boxes[-1][2:], (width, height))
            for x1, y1, x2, y2 in boxes:
                self.assertTrue(0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height)
            self.assertGreater(boxes[0][2], boxes[1][0])
            self.assertGreater(boxes[0][3], boxes[1][1])

    def test_paper_roles_and_forced_choice(self):
        captured = []
        class Model:
            model, backend = "fixture", "test"

            def ask(self, system, prompt, images):
                captured.append((system, prompt, len(images)))
                replies = ([{"checked": "已检查相应位置", "observations": []}] * 4 +
                           [{"reviews": []}, {"label": "uncertain", "evidence_ids": [], "explanation": "证据不足"},
                            {"label": "real", "explanation": "只反映相对倾向"}])
                return json.dumps(replies[len(captured)-1])
        p = ROOT / "real/experiment figure/2308.14409_fig4.png"
        report = run(ImageViews(p, profile="paper"), Model(), binary=True)
        self.assertEqual(list(report["inspections"]), list(PAPER_ROLES))
        self.assertEqual(report["calls"], 7)
        self.assertEqual(report["verdict"]["label"], "uncertain")
        self.assertEqual(report["binary_comparison"]["basis"], "forced_after_abstention")
        self.assertTrue(all(n == 2 for _, _, n in captured[:4]))
        self.assertFalse(any(p.name in system + prompt or "experiment figure/" in system + prompt
                             for system, prompt, _ in captured))

    def test_paper_profile_skips_texture_matching(self):
        p = ROOT / "real/overview/2409.16586_fig5.png"
        views = ImageViews(p, profile="paper")
        self.assertNotIn("PAIR", views.boxes)
        self.assertIn("Z4", views.boxes)
        self.assertEqual(views.info["profile"], "paper")
