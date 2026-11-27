# 从一张论文图开始读代码

可以先打开 [2308.14409_fig4.png](../real/experiment%20figure/2308.14409_fig4.png)。这张图画了两条 PSNR 曲线，底部横轴表示适配间隔，顶部横轴表示 LoRA 参数。两个轴分别对应不同变量，刻度方向不同也可以成立。取证角色要先找准“哪条线读哪个轴”，才有条件讨论数据与标注是否矛盾。

另一个例子是 [2411.15231_fig5.png](../real/illustration/2411.15231_fig5.png)。图中有 Encoder、Decoder、节点和带方向的连线。可以沿一条线追踪两个端点。图上的交叉和省略号都需要结合全图解释。[2409.16586_fig5.png](../real/overview/2409.16586_fig5.png) 把框架与搜索空间并列，图例中的箭头样式是核对两者对应关系的依据。

| 按执行顺序读 | 这一段解决的问题 |
| --- | --- |
| [detect.py](../detect.py) 中的 `main` | 读取单张图片路径和命令行参数，默认选用 `paper`，装载一次模型，调用下方流程，输出中文结果。 |
| [science_image/views.py](../science_image/views.py) 中的 `ImageViews` | 校正方向、处理透明背景、记录文件指纹。保存全图预览和局部视区的像素坐标。论文模式跳过纹理块匹配。 |
| [science_image/paper.py](../science_image/paper.py) 中的 `paper_tiles` | 生成四个略有重叠的局部视区 Z1–Z4。普通图按象限分；横长图沿横向分四块；竖长图沿纵向分。这样超宽公式图不会只剩一条压扁的小字。裁剪是固定视区，可能仍跨越面板边界。 |
| 同一文件的 `PAPER_ROLES` 和 `PAPER_CONTEXT` | 写明每个角色的任务、所看的局部和“来源”的含义。内容不引用测试图的文件名、论文编号或真假标签。修改角色分工主要看这里。 |
| [science_image/model.py](../science_image/model.py) 中的 `LocalModel`、`HttpModel` | 前者在 GPU 加载权重，后者连接已启动的视觉服务。两者都接收文字和像素，返回模型文本。 |
| [science_image/prompts.py](../science_image/prompts.py) | 定义候选、复核、裁决所用的公共提示和输出格式。旧显微图角色也在这里。 |
| [science_image/pipeline.py](../science_image/pipeline.py) 中的 `run` | 依次调用四个取证角色，为观察编号，再让模型对照全图和证据局部复核。裁决只可以引用保留的编号。`field`、`rows`、`observation`、`review`、`decision` 检查每一步返回的内容。`first_valid_observation` 处理模型多报的情况，并留下记录。 |
| 同文件的 `report` | 汇总判断和实际调用次数。启用 `--binary` 后，若主裁决弃判，额外记录一个强制比较结果；已有明确主裁决时直接复用。 |
| [score_images.py](../score_images.py) | 读带来源标签的 CSV，逐张核对文件指纹后计算指标。`--binary` 统计二选一结果。默认把弃判计入总样本，另报明确判断覆盖率。 |
| [tests/test_paper_figures.py](../tests/test_paper_figures.py) 和 [tests/test_science_image.py](../tests/test_science_image.py) | 检查长条图覆盖、标签隔离、二选一与原裁决分别保存、复核编号、错误处理和计分。 |

## 验证范围

该分支的 `real/` 中 21 张 PNG 均已实际解码，并通过论文模式的预览和局部裁剪检查。其中一张柱状图为 10800 × 3600 像素，一张量子电路图为 1559 × 134 像素。目录标签来自仓库，未逐篇核实制图历史。该集合可统计真实类误报和弃判，评估 AI 类召回率需要来源已知的生成插图。

验证单图和离线代码测试可在仓库根目录运行。

```bash
python -m unittest discover -s tests -p 'test_*image.py'
python -m unittest discover -s tests -p 'test_paper_figures.py'
python detect.py "real/experiment figure/2308.14409_fig4.png" --backend api --binary --out results/line-chart.json
```
