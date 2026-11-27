"""准备模型实际看到的图，并把每个局部视图映射回原图像素坐标。"""

import hashlib
import io
import warnings
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageOps

from .paper import paper_tiles

REGIONS = ("ALL", "TL", "TR", "BL", "BR")


def thumbnail(image, side):
    copy = image.copy()
    copy.thumbnail((side, side), Image.Resampling.LANCZOS)
    return copy


def contact_sheet(items, side=320):
    """给复核用的裁剪拼图加英文编号，标签区与像素区分开。"""
    patches = [(label, thumbnail(image, side)) for label, image in items]
    columns = min(2, len(patches))
    rows = (len(patches) + columns - 1) // columns
    widths = [max(max(140, patch.width) for _, patch in patches[col::columns]) for col in range(columns)]
    heights = [24 + max(patch.height for _, patch in patches[row*columns:(row+1)*columns]) for row in range(rows)]
    sheet = Image.new("RGB", (sum(widths), sum(heights)), "white")
    pen = ImageDraw.Draw(sheet)
    for i, (label, patch) in enumerate(patches):
        x, y = sum(widths[:i % columns]), sum(heights[:i // columns])
        pen.text((x + 4, y + 3), label, fill="black")
        sheet.paste(patch, (x, y + 24))
    return sheet


def candidate_boxes(image):
    """在缩略灰度图上比较不重叠方块，返回局部细节和最佳重复候选。"""
    small = thumbnail(image.convert("L"), 512)
    gray = np.asarray(small, dtype=np.float32)
    w, h = small.size
    step = max(8, min(w, h) // 6)
    boxes, vectors, deviations = [], [], []
    for y in range(0, h - step + 1, step):
        for x in range(0, w - step + 1, step):
            block = gray[y:y + step, x:x + step]
            deviation = float(block.std())
            if deviation < 5:  # 近乎纯色的背景没有足够纹理
                continue
            patch = np.asarray(Image.fromarray(block).resize((16, 16), Image.Resampling.BILINEAR))
            centered = patch.ravel() - patch.mean()
            norm = float(np.linalg.norm(centered))
            if norm < 1:
                continue
            boxes.append((round(x * image.width / w), round(y * image.height / h),
                          round((x + step) * image.width / w), round((y + step) * image.height / h)))
            vectors.append(centered / norm)
            deviations.append(deviation)
    if not boxes:
        return {}, None
    result = {"DETAIL": [boxes[int(np.argmax(deviations))]]}
    if len(boxes) < 2:
        return result, None
    # 点积是归一化互相关，选相似度最大的两个不同方块。
    matrix = np.stack(vectors)
    scores = matrix @ matrix.T
    np.fill_diagonal(scores, -np.inf)
    a, b = np.unravel_index(int(scores.argmax()), scores.shape)
    result["PAIR"] = [boxes[a], boxes[b]]
    return result, round(float(np.clip(scores[a, b], -1, 1)), 3)


class ImageViews:
    def __init__(self, path, side=1024, profile="microscopy"):
        if profile not in ("paper", "microscopy"):
            raise ValueError("未知图像配置。")
        self.profile = profile
        path = Path(path)
        if path.stat().st_size > 256 * 1024**2:
            raise ValueError("单张文件超过 256 MiB，请导出一个代表性视野。")
        raw = path.read_bytes()
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                opened = Image.open(io.BytesIO(raw))
        except (Image.DecompressionBombWarning, Image.DecompressionBombError) as exc:
            raise ValueError("图像尺寸过大，请导出一个代表性视野。") from exc
        with opened:
            if getattr(opened, "n_frames", 1) != 1:
                raise ValueError("输入包含多帧，请先导出要检测的那一帧。")
            if opened.width * opened.height > 40_000_000 or min(opened.size) < 8:
                raise ValueError("图像短边至少为 8 像素，总像素请控制在 4000 万以内。")
            mode = opened.mode
            image = ImageOps.exif_transpose(opened)
            note = "按原始灰度或颜色转换为 RGB，透明背景合成到白色。"
            if mode in ("I", "F") or mode.startswith("I;16"):
                pixels = np.asarray(image, dtype=np.float64)
                if not np.isfinite(pixels).all():
                    raise ValueError("灰度图含非有限值，请先确定显示窗口并导出。")
                low, high = float(pixels.min()), float(pixels.max())
                scaled = (pixels - low) * (255 / (high - low)) if high > low else np.zeros(image.size[::-1])
                image = Image.fromarray(scaled.astype("uint8"))
                note = f"灰度显示窗口 [{low:g}, {high:g}]，线性映射到 8 位。"
            rgba = image.convert("RGBA")
            self.image = Image.new("RGB", image.size, "white")
            self.image.paste(rgba, mask=rgba.getchannel("A"))
        w, h = self.image.size
        self.boxes = {"ALL": [(0, 0, w, h)]}
        for idx, name in enumerate(REGIONS[1:]):
            x, y = idx % 2, idx // 2
            self.boxes[name] = [(w*x//2, h*y//2, w*(x+1)//2, h*(y+1)//2)]
        if profile == "paper":
            extra, score = paper_tiles(w, h), None
        else:
            extra, score = candidate_boxes(self.image)
        self.boxes.update(extra)
        self.overview = thumbnail(self.image, side)
        self.info = {"sha256": hashlib.sha256(raw).hexdigest(), "size": [w, h],
                     "original_mode": mode, "overview_size": list(self.overview.size),
                     "profile": profile, "display": note, "boxes_xyxy": self.boxes, "pair_ncc": score}

    def sheet(self, entries):
        crops = [(f"{label} {region} {i+1}", self.image.crop(box))
                 for label, region in entries for i, box in enumerate(self.boxes[region])]
        size = 448 if self.profile == "paper" else 320
        return contact_sheet(crops, side=size) if crops else None
