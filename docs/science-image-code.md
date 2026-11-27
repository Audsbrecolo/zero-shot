> 这份说明记录了早期显微图流程。当前默认的论文插图流程请读[逐文件讲解](paper-figures.md)。原显微图实验用 `--profile microscopy`。

# 怎样读懂这套程序

第一次阅读时，在仓库里打开 `detect.py`，找到 `main()`。从这一行一路读到 `run(views, model, ...)`，你就能看到“读哪张图、用哪个模型、从哪里开始分析”。下表的顺序就是一次检测的执行顺序。

| 顺序 | 文件和函数 | 它接收什么，做什么，交给谁 |
| --- | --- | --- |
| 1 | [detect.py](../detect.py) 的 `main` | 读终端命令。必填的是图片路径，`--out` 指定报告位置。先检查图片再加载模型，最后调用 `run`。 |
| 2 | [views.py](../science_image/views.py) 的 `ImageViews` | 读原始字节并计算 SHA-256。校正 EXIF 方向、处理透明背景和高位深灰度，保留原图与最长边不超过 1024 像素的全图预览。 |
| 3 | 同文件的 `thumbnail`、`candidate_boxes` | `thumbnail` 保持比例缩小。另一函数把灰度预览切成不重叠的方块，跳过近乎空白的块，选出灰度标准差最大的 `DETAIL` 和纹理相关性最高的一对 `PAIR`。图像没有足够内容时跳过相应视图。 |
| 4 | 同文件的 `ImageViews.sheet`、`contact_sheet` | 按坐标从原图裁剪，附上区域编号后排成一张图。纹理和重复取证角色可看额外局部图。复核也使用此方法取回每条观察所指的区域。 |
| 5 | [model.py](../science_image/model.py) 的 `LocalModel`、`HttpModel` | 二选一。`LocalModel` 在 GPU 上加载一次模型，用聊天模板把提示与图像编码，解码新生成的回答。`HttpModel` 把同样的图转成 PNG 发到你指定的服务，取回回答。两者都提供 `ask`。 |
| 6 | [prompts.py](../science_image/prompts.py) 的 `ROLES`、`BASE`、`expert_prompt` | `BASE` 给出所有角色共用的任务。字典 `ROLES` 写着四个取证角色各管什么。`expert_prompt` 拼出该角色的提问及规定的 JSON 格式。改“这个角色该看什么”就在这里。 |
| 7 | [pipeline.py](../science_image/pipeline.py) 的 `run`、`ask`、`observation` | `run` 组织整个流程。四个角色先独立看图，不读其他角色的答案。`observation` 校验返回值，程序保存每个角色的检查说明，并为每条候选分配 E1、E2 等编号。内层函数 `ask` 记录次数，格式错误时把具体问题反馈给模型，最多再试一次。如果重试后仅是观察数过多，`first_valid_observation` 按输出顺序采用第一条合格的记录，将选择写入 `format_notes`。 |
| 8 | `prompts.py` 的 `REVIEW` 与 `pipeline.py` 的 `review` | 模型同时看原图、定位裁剪和候选记录，逐条说明能否核实，并独立给出方向。程序检查每个候选都复核了一次。这里实现“证据自净化”。 |
| 9 | `prompts.py` 的 `VERDICT` 与 `pipeline.py` 的 `decision` | 裁决只收到保留证据和全图。程序检查引用 ID；若裁决偏向某一来源，却拿不出方向一致的保留证据，就输出“证据不足”。格式不合法的请求重试后仍失败，会退出并提示错误。 |
| 10 | `detect.py` 的 `save_report` | 将报告先写到同目录的临时文件，完整写好后替换目标，避免中断留下半份 JSON。终端显示简版，文件保留可复查记录。 |
| 11 | [score_images.py](../score_images.py) 的 `score` | 测试完成后读人工准备的标签清单，核对每张图的指纹，分来源统计整体准确率、覆盖率、两类召回率和已判样本准确率。它不参与推理。 |
| 12 | [test_science_image.py](../tests/test_science_image.py) | 用已知位置的图案测试裁剪，用可控回复测试六个步骤、无效引用、格式修正和证据不足。实际模型验证另见运行记录。 |

`pipeline.py` 的小函数 `field` 检查文字字段和允许值，`rows` 检查列表；`pack` 把内存里的证据转成紧凑 JSON。模块 [__init__.py](../science_image/__init__.py) 标记 Python 包的入口。[requirements-image.txt](../requirements-image.txt) 列客户端图像依赖，[requirements-image-local.txt](../requirements-image-local.txt) 加入本地加载模型所需的 Transformers 和 Accelerate。仓库原有的 [core/common.py](../core/common.py) 负责严格解析模型 JSON 并检查重复键，[core/metrics.py](../core/metrics.py) 负责计算指标。

## 这些 Agent 在哪里

| 角色 | 输入与任务 |
| --- | --- |
| 科学形貌 | 看全图中的结构与空间关系。面对 SEM 图时，关注孔壁、颗粒和断面；遇到图表时，改看图表里能观察到的结构。 |
| 局部纹理 | 看全图以及高对比局部，描述边界、纹理是否存在可定位的异常。 |
| 空间重复 | 对照全图和两个相似局部。相似度筛的是候选，模型还要核对两处究竟有哪些细节对应。 |
| 成像与标注 | 根据图类检查比例尺、图例、轴刻度、标注与图像内容的关系。 |
| 来源裁决 | 综合通过复核的证据，给出判断、编号、理由；证据冲突或不足时可以弃判。 |

同一个 `run` 还支持 `--mode direct`，用 `DIRECT` 提示只看一次相同的全图预览，输出一次来源判断。这个对照用来检查整套流程相对单次看图有多少收益；角色分解与额外裁剪的影响在这个对照里合并计算。

例如，角色说“左上区域的几颗颗粒看起来一样”。程序会让复核步骤重新看到左上区域，检查它能否找到这些颗粒，并要求考虑周期结构、后处理等解释。复核后的证据方向可以从 `ai_generated` 变成 `neutral`。裁决能够引用中性证据解释为什么暂时无法判断。

局部匹配对纹理、重复网格或文字很敏感，当前比较同尺度、同方向的粗网格块，可能漏掉旋转、缩放或跨网格边界的重复。多个角色共用同一模型，也可能共享同一种误判。复核提高了输出的可追踪性，检测收益需要有标签的对照实验验证。

## 仓库里其余代码是什么

原仓库包含完整的 WeVisForensics 视频项目。新图片流程复用了 JSON 解析和分类指标。原项目的 `main_agent/` 处理视频主控，`sub_agents/` 处理视频、语音、OCR 等检查，`configs/` 保存配置，`scripts/` 是服务与视频推理脚本，`demo/` 是视频演示，`evaluation/` 是视频评测，`checkpoints/` 指向视频权重说明。需要阅读这些实现时，可从[上游架构说明](architecture.md)开始。
