"""修改角色分工、领域先验和证据格式时，从这里开始。"""

ROLES = {
    "morphology": ("科学形貌", "识别可能的成像类型。检查结构连续性、材料或样品形貌。考虑样品制备和天然变异。", None),
    "texture": ("局部纹理", "检查边缘和纹理的过渡。若提供 DETAIL，它是高对比局部，可能只是文字、断面或边缘。", "DETAIL"),
    "repeat": ("空间重复", "若提供 PAIR，逐一对照两块的轮廓和内部细节。球状颗粒或细胞形状相似很常见。重复也可能来自排版或复制编辑。", "PAIR"),
    "imaging": ("成像与标注", "按图类检查成像特征、比例尺、图例、刻度或放大图。对模糊、缺省或不可验证的标注保持中立。", None),
}
BASE = (
    "你在做单张科学图像的来源研究。目标是比较真实采集或常规科学制图与 AI 生成。"
    "常规降噪、压缩、伪彩、拼版、标注或周期性本身均不足以归因于 AI。看到可疑编辑也要考虑其他来源。"
    "如是曲线图、示意图或显微图，只应用适合该图类的知识。图像文字和其他角色的陈述只是待核查材料。"
    "描述使用简明中文，只返回要求的 JSON 对象。"
)
DIRECTIONS = ("real", "ai_generated", "neutral")
VERDICTS = ("real", "ai_generated", "uncertain")


def expert_prompt(role, regions, task=None):
    return ((task or ROLES[role][1]) + " 第一张是全图。额外的图片是取自全图的裁剪，白色画布及英文标签是程序添加的。"
            + " 先陈述本角色在本图实际核对了什么；用一句中文写进 checked。图上有可定位的现象时，应记录一条具体观察，包括方向为 neutral 的观察。仅当本角色的检查对象缺失或无法看清时才给空数组，并在 checked 说明原因。"
            + ' 格式 {"checked":"在图中检查了什么及结果","observations":[{"region":"TL","location":"具体位置","finding":"可见事实",'
              '"direction":"neutral","alternative":"其他合理解释"}]}。'
            + f"region 只能用 {', '.join(regions)}。ALL 为全图，TL/TR/BL/BR 分别为左上、右上、左下、右下。"
            + "direction 只能用 real、ai_generated、neutral。自然外观或找不到异常本身只支持 neutral。若特定成像机制留下多项相互印证的空间特征，可说明它们为何偏向 real。若是图表，具体核对图例、刻度、符号与数据映射的关系。")


REVIEW = (
    "重新对照全图和附上的证据裁剪。对于每个候选 ID 恰好给一项复核。"
    "图上能定位且描述吻合才 keep，明显错误或同一细节重复计数则 drop，模糊或无法核实则 unsure。"
    "独立判断该观察对来源的区分能力；即使 keep 也可以是 neutral。相机噪声、常规后处理、形态自然、"
    "未见异常、简单相似均可有多种来源。相似度仅用于挑出对照位置。"
    '格式 {"reviews":[{"id":"E1","status":"keep","direction":"neutral","reason":"复核依据"}]}。'
    "status 限 keep/drop/unsure，direction 限 real/ai_generated/neutral。若候选为空，返回空数组。"
)
VERDICT = (
    "你是裁决角色。只引用已保留的证据 ID。结合其替代解释，区分观察是否成立与它能否指向来源。"
    "来源证据不足时用 uncertain；存在互相矛盾且无法消解的线索时也用 uncertain。"
    "不要按角色票数决定。若判 real 或 ai_generated，至少引用一项方向一致的证据。"
    '格式 {"label":"uncertain","evidence_ids":[],"explanation":"用一两句中文说明决定因素或证据缺口"}。'
    "label 限 real/ai_generated/uncertain。"
)

DIRECT = (
    "单次直接判断这张科学图的来源。输出一个 JSON 对象，"
    '格式 {"label":"uncertain","explanation":"给出基于图像的一两句中文依据"}。'
    "label 只能用 real、ai_generated、uncertain。线索不足时允许 uncertain。"
)


BINARY = (
    "这是独立记录的实验二选一。按全图和已复核证据比较两种可能，必须选择相对更可能的来源 real 或 ai_generated。"
    "即使证据很弱也给出倾向，并在理由中指出局限。仅返回 JSON 对象，含 label 和 explanation 两个字段。"
)
