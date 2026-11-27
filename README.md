# 论文插图的零样本 AI 生成检测

给一张论文中的实验结果图、示意图或方法总览图，检查它更接近研究者常规绘制的图还是 AI 生成的插图。输入可以是折线图、柱状图、网络架构图，也可以是多面板结果对照。程序输出中文解释并保留逐条证据。论文里画了 AI 模型、展示 AI 输出或写有 “Generated Motion”，只说明论文展示了什么；需另行判断整张插图的制作来源。

这个分支有 21 张标为真实的 PNG。文件夹名、论文编号、原文件名和真假标签均不会进入模型提示。

| 样本目录 | 数量 | 例子 |
| --- | ---: | --- |
| [real/experiment figure](real/experiment%20figure/) | 10 | 双横轴折线图、柱状图、方法结果对照、遥感原图和掩膜 |
| [real/illustration](real/illustration/) | 5 | 编码器与解码器连接图、训练流程图、模块示意图 |
| [real/overview](real/overview/) | 6 | 框架总览、搜索空间、表格与网络结构组合图 |

这 21 张原图的 Git 文件哈希均与 SciFigDetect 的公开示例一致。每张对应一张 Nano Banana 生成图和两张 GPT 生成图，可以在相同论文主题下比较真假。[21 组原图与生成图对应表](examples/science/paper-pairs.csv)

## 先在学校 GPU 容器跑一张

用 Python 3.10 或更高版本、带 CUDA 的 PyTorch 和配套 torchvision。请在终端执行。先克隆这个分支；下载了项目 ZIP 时，解压后直接进入含 `detect.py` 的目录，从检查 CUDA 的命令开始。

```bash
git clone --branch scitifical_image --single-branch https://github.com/Audsbrecolo/zero-shot.git
cd zero-shot
python -c "import torch, torchvision; print('CUDA 可用', torch.cuda.is_available())"
python -m pip install -r requirements-image-local.txt
python detect.py "real/experiment figure/2308.14409_fig4.png" --out results/line-chart.json
```

检测其他单张图片时只改路径。含空格的路径放进双引号。默认模型为 Qwen3-VL-8B-Instruct，首次运行会下载权重。如果学校服务器已存好权重，使用 `--model /实际的模型目录`。

```bash
python detect.py "real/illustration/2411.15231_fig5.png" --out results/encoder.json
python detect.py "real/overview/2409.16586_fig5.png" --binary --out results/overview.json
```

如果已有兼容 OpenAI 接口且支持多图与 JSON 的视觉模型服务，可以直接连接。该命令会将预览和局部图送到指定服务。默认地址是本机。

```bash
python -m pip install -r requirements-image.txt
python detect.py "real/experiment figure/2308.14409_fig4.png" --backend api --base-url http://127.0.0.1:8000/v1 --out results/line-chart.json
```

[在 Linux CPU 上启动 Qwen 量化服务的完整命令](docs/image-runtime.md)给出了权重、视觉投影和服务启动方法。旧的原始显微图模式用 `--profile microscopy` 运行。

## 一张图是怎样判的

四个取证角色分别检查数据与视觉编码、流程与连接关系、文字与符号、面板与对应关系。它们各看全图和不同位置的放大图。四个角色共用一个模型。随后同一模型回看图片复核每条证据，裁决角色引用保留的证据给出结果。通常每图调用六次，输出格式异常时允许重试。

- `verdict` 是有证据约束的判断，可以是 `real`、`ai_generated` 或 `uncertain`。最后一项表示仅凭当前图像证据无法区分来源。
- `--binary` 适合做必须二选一的实验。若原裁决为证据不足，再加一次比较，将倾向写入 `binary_comparison`。保留原裁决以便统计弃判率。二选一结果不带经过校准的概率。
- `--mode direct` 是只给同一模型看一次全图的对照。可以用它与五角色方案在相同图片上比较。
- 用编辑器打开 JSON。`inspections` 写每个角色检查了什么，`candidates` 给出区域和替代解释，`reviews` 解释哪些观察得以保留。`image.boxes_xyxy` 可定位回原图。

[从入口开始读代码](docs/paper-figures.md) · [测试记录与评测方法](docs/science-image-validation.md) · [原 WeVisForensics 视频项目](README-WeVisForensics.md)

## 当前实测效果

三类论文插图都已用 Qwen3-VL-8B 的量化权重完成单图推理。三张原图和一张同题 GPT 生成图的主裁决均为“证据不足”；强制二选一均判为常规制图，因此漏检了生成图。当前结果适合用于检查取证流程，尚未证明能够可靠地区分来源。[四份报告与复现命令](docs/paper-figures.md#端到端单图实测)
