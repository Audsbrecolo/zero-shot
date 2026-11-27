"""从带真实标签的清单核对报告，按图像、类别与生成器统计结果。"""

import argparse
import csv
import hashlib
import json
from pathlib import Path

from core.metrics import binary_metrics
from science_image.prompts import VERDICTS


def score(manifest, binary=False):
    pairs, groups, seen = [], {}, set()
    settings = None
    with manifest.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not {"image", "label", "report", "source"} <= set(reader.fieldnames or []):
            raise ValueError("CSV 必须有 image,label,report,source 四列。")
        for n, row in enumerate(reader, 2):
            label = row["label"]
            if label not in ("real", "ai_generated"):
                raise ValueError(f"第 {n} 行来源标签无效。")
            digest = hashlib.sha256((manifest.parent / row["image"]).read_bytes()).hexdigest()
            if digest in seen:
                raise ValueError(f"第 {n} 行图片重复。")
            seen.add(digest)
            report = json.loads((manifest.parent / row["report"]).read_text(encoding="utf-8"))
            if report["image"]["sha256"] != digest:
                raise ValueError(f"第 {n} 行报告与图片的 SHA-256 不一致。")
            config = {k: report[k] for k in ("model", "backend", "mode")}
            config["profile"] = report.get("profile", "microscopy")
            if settings is not None and config != settings:
                raise ValueError(f"第 {n} 行的模型、后端或运行模式不同，请分开统计。")
            settings = config
            result = report.get("binary_comparison" if binary else "verdict")
            if not isinstance(result, dict):
                raise ValueError(f"第 {n} 行缺少所选模式的预测。")
            answer = result["label"]
            if answer not in VERDICTS:
                raise ValueError(f"第 {n} 行报告标签无效。")
            pair = (label, answer)
            pairs.append(pair)
            groups.setdefault(row["source"].strip() or "unknown", []).append(pair)
    if not pairs:
        raise ValueError("清单没有样本。")

    def summarize(items):
        # 复用原项目指标。其内部把正类命名为 fake，在输出中还原为 ai_generated。
        to_old = {"ai_generated": "fake", "real": "real", "uncertain": None}
        metrics = binary_metrics([(to_old[label], to_old[pred]) for label, pred in items])
        abstained = metrics["invalid"]
        return {"n": len(items), "uncertain": abstained, "coverage": 1 - abstained / len(items),
                "accuracy_all": metrics["strict"]["accuracy"], "accuracy_decided": metrics["valid_only"]["accuracy"],
                "ai_recall_all": metrics["strict"]["fake"]["recall"],
                "real_recall_all": metrics["strict"]["real"]["recall"]}

    return {"settings": settings, "overall": summarize(pairs), "by_source": {k: summarize(v) for k, v in groups.items()}}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--binary", action="store_true", help="统计实验二选一")
    args = parser.parse_args()
    try:
        print(json.dumps(score(args.manifest, binary=args.binary), ensure_ascii=False, indent=2))
    except (ValueError, KeyError, OSError, TypeError) as exc:
        parser.exit(1, f"统计失败：{exc}\n")
