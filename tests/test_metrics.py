"""检查有弃判时总准确率和已判样本准确率的分母。"""

import unittest

from core.metrics import binary_metrics


class MetricsTests(unittest.TestCase):
    def test_strict_counts_invalid_model_output(self):
        metrics = binary_metrics([("fake", "fake"), ("real", None)])
        self.assertEqual(metrics["rows"], 2)
        self.assertEqual(metrics["invalid"], 1)
        self.assertEqual(metrics["strict"]["accuracy"], 0.5)
        self.assertEqual(metrics["valid_only"]["accuracy"], 1.0)
