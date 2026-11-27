"""可离线重复的协议与 CLI 测试。这里的模拟回复只验证程序逻辑。"""

import base64
import hashlib
import io
import json
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np
from PIL import Image

from score_images import score
from science_image.pipeline import decision, first_valid_observation, observation, review, run
from science_image.views import ImageViews

ROOT = Path(__file__).resolve().parents[1]


class ScienceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.path = self.folder / "盲测.png"
        rng = np.random.default_rng(77)
        noise = rng.integers(0, 256, (96, 96), dtype=np.uint8)
        noise[80:96, 80:96] = noise[:16, :16]
        Image.fromarray(noise).save(self.path)

    def cli(self, *args):
        return subprocess.run([sys.executable, str(ROOT / "detect.py"), str(self.path), *map(str, args)],
                              cwd=self.folder, capture_output=True, text=True, timeout=30)

    def test_repeated_patch_maps_back_to_original(self):
        views = ImageViews(self.path)
        self.assertEqual(set(views.boxes["PAIR"]), {(0, 0, 16, 16), (80, 80, 96, 96)})
        self.assertAlmostEqual(views.info["pair_ncc"], 1)
        self.assertEqual(views.info["sha256"], hashlib.sha256(self.path.read_bytes()).hexdigest())

    def test_blank_and_transparent(self):
        Image.new("RGBA", (64, 64), (0, 0, 0, 0)).save(self.path)
        views = ImageViews(self.path)
        self.assertIsNone(views.info["pair_ncc"])
        self.assertEqual(views.overview.getpixel((0, 0)), (255, 255, 255))

    def test_16bit_window(self):
        tiff = self.folder / "window.tif"
        pixels = np.tile(np.arange(16, dtype=np.uint16) + 4000, (16, 1))
        Image.fromarray(pixels).save(tiff)
        v = ImageViews(tiff)
        self.assertEqual(v.overview.convert("L").getextrema(), (0, 255))
        self.assertIn("4015", v.info["display"])

    def test_multiframe_is_rejected(self):
        frame = Image.new("L", (32, 32))
        tiff = self.folder / "stack.tif"
        frame.save(tiff, save_all=True, append_images=[frame])
        with self.assertRaisesRegex(ValueError, "多帧"):
            ImageViews(tiff)

    def test_decision_must_reference_real_kept_ids(self):
        with self.assertRaises(ValueError):
            decision({"label": "real", "evidence_ids": ["E9"], "explanation": "原因"}, {})
        for label in ("ai_generated", "real"):
            d = {"label": label, "evidence_ids": ["E1"], "explanation": "原因"}
            self.assertEqual(decision(d, {"E1": "neutral"})["label"], "uncertain")
            self.assertEqual(decision(d, {"E1": label})["label"], label)

    def test_malformed_fields_and_missing_reviews(self):
        with self.assertRaises(ValueError):
            observation({"observations": [{}]}, ["ALL"])
        with self.assertRaises(ValueError):
            review({"reviews": []}, ["E1"])
        with self.assertRaises(ValueError):
            review({"reviews": [{"id": "E1", "status": "keep", "direction": "neutral",
                                 "reason": "重复编号"}] * 2}, ["E1", "E2"])

    def test_cli_error_preserves_original(self):
        data = self.path.read_bytes()
        self.assertNotEqual(self.cli("--out", self.path).returncode, 0)
        self.assertEqual(self.path.read_bytes(), data)

    def test_cli_real_http_transport_and_retry(self):
        entries = []
        one = {"region": "ALL", "location": "中心", "finding": "纹理中有交界", "direction": "neutral",
               "alternative": "可能来自成像"}
        replies = iter(["format error", {"checked": "核对颗粒交界", "observations": [one]}, *[{"checked": "无法定位", "observations": []} for _ in range(3)],
                        {"reviews": [{"id": "E1", "status": "drop", "direction": "neutral", "reason": "缺少定位"}]},
                        {"label": "uncertain", "evidence_ids": [], "explanation": "证据不足"}])

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                entries.append((self.path, body))
                value = next(replies)
                txt = value if isinstance(value, str) else json.dumps(value)
                self.send_response(200)
                self.end_headers()
                self.wfile.write(json.dumps({"choices": [{"message": {"content": txt}}]}).encode())

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.addCleanup(server.server_close)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.shutdown)
        out = self.folder / "nested/report.json"
        p = self.cli("--backend", "api", "--base-url", f"http://127.0.0.1:{server.server_port}/v1", "--out", out)
        self.assertEqual(p.returncode, 0, p.stderr)
        report = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(report["calls"], 7)
        self.assertEqual(report["reviews"][0]["status"], "drop")
        self.assertNotIn('"E1"', entries[-1][1]["messages"][1]["content"][-1]["text"])
        for url, body in entries:
            self.assertEqual(url, "/v1/chat/completions")
            data = body["messages"][1]["content"][0]["image_url"]["url"].split(",", 1)[1]
            with Image.open(io.BytesIO(base64.b64decode(data))) as image:
                self.assertEqual(image.format, "PNG")
            self.assertNotIn(self.path.name, json.dumps(body, ensure_ascii=False))

    def test_extra_observations_after_retry_are_audited(self):
        good = {"region": "TL", "location": "左上", "finding": "边界", "direction": "neutral", "alternative": "成像"}
        data = {"checked": "检查局部", "observations": [{}, good, good]}
        with self.assertRaises(ValueError):
            observation(data, ["TL"])
        (summary, evidence), note = first_valid_observation(data, ["TL"])
        self.assertEqual((summary, evidence), ("检查局部", [good]))
        self.assertIn("第 2 条", note)
        self.assertIsNone(first_valid_observation({"checked": "无法核对", "observations": [{}, {}]}, ["TL"]))

    def test_direct_baseline_is_one_call(self):
        class DirectModel:
            model, backend = "test", "test"

            def ask(self, system, prompt, images):
                return '{"label":"real","explanation":"可定位的依据"}'

        result = run(ImageViews(self.path), DirectModel(), mode="direct")
        self.assertEqual((result["calls"], result["mode"], result["verdict"]["label"]), (1, "direct", "real"))

    def test_persistent_bad_schema_is_an_error(self):
        class BrokenModel:
            model, backend = "test", "test"

            def ask(self, system, prompt, images):
                return '{}'

        with self.assertRaisesRegex(ValueError, "连续两次"):
            run(ImageViews(self.path), BrokenModel())

    def test_score_counts_abstentions_and_checks_input(self):
        report = self.folder / "result.json"
        digest = hashlib.sha256(self.path.read_bytes()).hexdigest()
        report.write_text(json.dumps({"model": "test", "backend": "api", "mode": "agents", "image": {"sha256": digest}, "verdict": {"label": "uncertain"}}))
        manifest = self.folder / "labels.csv"
        manifest.write_text(f"image,label,report,source\n{self.path.name},real,result.json,microscope\n", encoding="utf8")
        overall = score(manifest)["overall"]
        self.assertEqual((overall["coverage"], overall["accuracy_all"], overall["accuracy_decided"]), (0, 0, None))
        self.path.write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            score(manifest)
