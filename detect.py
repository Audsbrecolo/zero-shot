"""命令行入口。例：python detect.py "real/experiment figure/2308.14409_fig4.png" --out results/chart.json"""

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

from science_image.model import MODEL, HttpModel, LocalModel

LABELS = {"real": "倾向真实来源", "ai_generated": "倾向 AI 生成", "uncertain": "证据不足"}


def save_report(report, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as f:
            temporary = Path(f.name)
            json.dump(report, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description="判断单张科学图片的来源，并给出可复核的证据。")
    parser.add_argument("image", type=Path, help="一张 PNG、JPEG 或单页 TIFF 等图片的路径")
    parser.add_argument("--backend", choices=("local", "api"), default="local", help="默认直接在 GPU 上加载模型")
    parser.add_argument("--mode", choices=("agents", "direct"), default="agents", help="五角色流程或单次看图对照")
    parser.add_argument("--profile", choices=("paper", "microscopy"), default="paper",
                        help="默认识别论文图表、示意图与总览图；显微原图可选 microscopy")
    parser.add_argument("--binary", action="store_true", help="附加实验性真实/AI 二选一；保留原裁决")
    parser.add_argument("--model", default=MODEL, help="模型 ID、本地权重目录，或服务设置的模型别名")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/v1", help="API 服务的 /v1 地址")
    parser.add_argument("--out", type=Path, help="保存完整 JSON 报告的路径")
    args = parser.parse_args()
    try:
        from science_image.pipeline import run
        from science_image.views import ImageViews

        if args.out and args.out.resolve() == args.image.resolve():
            raise ValueError("报告和输入图片需要使用不同路径。")
        views = ImageViews(args.image, profile=args.profile)
        print("正在准备视觉模型…", file=sys.stderr, flush=True)
        model = LocalModel(args.model) if args.backend == "local" else HttpModel(args.model, args.base_url)
        report = run(views, model, lambda stage: print("正在执行：" + stage, file=sys.stderr, flush=True), mode=args.mode, binary=args.binary)
        if args.out:
            save_report(report, args.out)
        verdict = report["verdict"]
        print(f"判断：{LABELS[verdict['label']]}\n依据：{verdict['explanation']}")
        cited = set(verdict["evidence_ids"])
        for e in report["candidates"]:
            if e["id"] in cited:
                print(f"  {e['id']} · {e['location']} · {e['finding']}")
        if args.binary:
            choice = report["binary_comparison"]
            print(f"实验二选一：{LABELS[choice['label']]}。{choice['explanation']}")
        if args.out:
            print(f"完整报告：{args.out}")
        return 0
    except (OSError, ValueError, RuntimeError, ImportError) as exc:
        print(f"检测失败：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
