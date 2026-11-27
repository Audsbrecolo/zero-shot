> 此页的有丝分裂显微图属于早期验证。运行其命令时添加 `--profile microscopy`。当前论文插图的验证范围及结果见[论文插图说明](paper-figures.md)。

# 怎样验证程序和检测效果

## 运行验证

单图入口可用仓库中的公开显微图复现。代码测试用本机 HTTP 服务模拟模型回复，可以重复验证读取、裁剪坐标、证据编号、复核、格式重试、弃判与计分逻辑。实际推理使用 Qwen3-VL-8B-Instruct 的 Q4_K_M 量化权重及 F16 视觉投影，通过 llama.cpp b8219 的多图接口调用。两份权重的 SHA-256 已与固定版本 b93a7ee7 的发布记录核对。Transformers 4.57.6 的本地适配器还使用官方处理器和缩小的随机初始化 Qwen3-VL 网络在 CPU 上完成了单图、双图编码和生成接口检查；学校 CUDA 环境的 8B 原始权重推理需要在相应 GPU 上验证。

```bash
python -m pip install -r requirements-image.txt
python -m unittest discover -s tests -p test_science_image.py
python detect.py examples/science/mitosis.tif --backend api --out results/mitosis.json
python detect.py examples/science/mitosis.tif --backend api --mode direct --out results/mitosis-direct.json
```

读报告时先看 `inspections` 中每个角色实际观察到了什么，再对照 `candidates` 和 `reviews`。当报告写“证据不足”时，检查是哪个现象看不清，或者哪条观察同时符合多种来源。

## 用自己的数据计分

先准备真实来源已核实的原图和已知生成器的 AI 图。文件路径与标签仅供评测脚本读取。检测程序给模型发送像素和固定任务文字，不发送原始文件名、数据集目录或标签。根据研究任务，分别记录整图生成、局部 AI 编辑和常规后处理。正式测试前固定模型、量化方式、提示词和代码版本。校验时确保同一篇文章、原图的变体和衍生图不跨开发集与测试集。

建一个 UTF-8 编码的 `labels.csv`，每张测试图一行。下面是格式示例，路径要换成自己的真实文件。相对路径以 CSV 所在目录为起点。每张图可以先跑两份报告，给五角色与单次看图分别准备一份清单。

```csv
image,label,report,source
images/a.tif,real,results/a.json,SEM仪器
images/b.png,ai_generated,results/b.json,生成器名称
```

```bash
python score_images.py labels.csv
```

| 输出 | 计算方式 |
| --- | --- |
| `n` 和 `uncertain` | 进入统计的图片数和证据不足的数量。请为清单中每张图准备报告；缺图、缺报告或哈希不符会报错。 |
| `coverage` | 明确判为真实或 AI 的张数除以总张数。 |
| `accuracy_all` | 判断正确的张数除以总张数。证据不足仍计入分母。 |
| `accuracy_decided` | 判断正确的张数除以给出明确判断的张数；全部弃判时为 null。 |
| `ai_recall_all`、`real_recall_all` | 各类被正确识别的张数除以该类总张数；该类没有样本时为 null。 |
| `by_source` | 按 CSV 的来源列分别计算，以便单独检查某台仪器或某个生成器。 |

比较五角色与单次看图时使用完全相同的图片、模型、后端和评分规则。以真实采集图的误判、未见生成器的召回率和弃判率检验泛化。单个成功案例可以说明怎样读报告，统计显著性需要在独立且有足够样本量的测试集上评估。
