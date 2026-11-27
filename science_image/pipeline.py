"""四次取证，一次复核，一次裁决。每一阶段都检查上一步的输出。"""

import json
import time

from core.common import try_parse_json_strict
from .paper import PAPER_CONTEXT, PAPER_ROLES
from .prompts import BASE, BINARY, DIRECT, DIRECTIONS, REVIEW, ROLES, VERDICT, VERDICTS, expert_prompt
from .views import REGIONS


def field(item, name, choices=None):
    value = item.get(name) if isinstance(item, dict) else None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} 必须是非空文本。")
    value = value.strip()
    if choices is not None and value not in choices:
        raise ValueError(f"{name} 只能用 {list(choices)}。")
    return value


def rows(data, key):
    if not isinstance(data, dict) or not isinstance(data.get(key), list):
        raise ValueError(f"回复必须是对象，其中 {key} 必须是数组。")
    return data[key]


def observation(data, regions):
    items = rows(data, "observations")
    if len(items) > 1:
        raise ValueError("每个角色至多报告一条观察。")
    checked = field(data, "checked")
    evidence = [{"region": field(e, "region", regions), "location": field(e, "location"),
             "finding": field(e, "finding"), "direction": field(e, "direction", DIRECTIONS),
             "alternative": field(e, "alternative")} for e in items]
    return checked, evidence


def first_valid_observation(data, regions):
    """模型重试后仍多报时，按返回顺序取第一条可校验记录，并在报告中说明。"""
    if not isinstance(data, dict) or not isinstance(data.get("observations"), list):
        return None
    items = data["observations"]
    if len(items) <= 1:
        return None
    for index, item in enumerate(items, 1):
        try:
            result = observation({**data, "observations": [item]}, regions)
        except ValueError:
            continue
        return result, f"模型返回 {len(items)} 条观察，采用第 {index} 条格式合格的记录。"
    return None


def review(data, ids):
    checked = []
    for row in rows(data, "reviews"):
        checked.append({"id": field(row, "id", ids), "status": field(row, "status", ("keep","drop","unsure")),
                        "direction": field(row, "direction", DIRECTIONS), "reason": field(row, "reason")})
    if sorted(r["id"] for r in checked) != sorted(ids):
        raise ValueError(f"必须恰好复核这些 ID 各一次：{ids}。")
    return checked


def decision(data, eligible):
    ids = rows(data, "evidence_ids")
    if any(not isinstance(i, str) or i not in eligible for i in ids) or len(set(ids)) != len(ids):
        raise ValueError(f"evidence_ids 只能引用已保留 ID，各一次：{list(eligible)}。")
    label = field(data, "label", VERDICTS)
    explanation = field(data, "explanation")
    if label != "uncertain" and not any(eligible[i] == label for i in ids):
        return {"label": "uncertain", "evidence_ids": [],
                "explanation": "裁决所引证据缺少与该来源方向一致的复核结果，现有证据不足。"}
    return {"label": label, "evidence_ids": ids, "explanation": explanation}


def run(views, model, progress=lambda message: None, mode="agents", binary=False):
    start = time.monotonic()
    attempts = {}
    candidates = []
    inspections = {}
    format_notes = {}
    paper = views.profile == "paper"
    system = BASE + (PAPER_CONTEXT if paper else "")

    def ask(stage, prompt, images, validate, recover=None):
        """仅在回复格式错误时重试一次；连接失败直接报错，避免生成假报告。"""
        progress(stage)
        feedback = ""
        for attempt in (1, 2):
            attempts[stage] = attempt
            answer = model.ask(system, prompt + feedback, images)
            parsed = None
            try:
                parsed = try_parse_json_strict(answer)
                return validate(parsed)
            except ValueError as exc:
                feedback = f"\n上一次格式检查失败：{exc} 请重新查看图片并完整返回上述格式。"
                if attempt == 2:
                    if recover and parsed is not None:
                        recovered = recover(parsed)
                        if recovered is not None:
                            result, note = recovered
                            format_notes[stage] = note
                            return result
                    raise ValueError(f"{stage} 连续两次回复不符合格式：{exc}") from exc

    def report(verdict, reviews):
        comparison = None
        if binary:
            if verdict["label"] != "uncertain":
                comparison = {"label": verdict["label"], "explanation": verdict["explanation"], "basis": "primary"}
            else:
                retained = {r["id"]: r for r in reviews if r["status"] == "keep"}
                support = [{"finding": e["finding"], "review": retained[e["id"]]["reason"],
                            "alternative": e["alternative"]} for e in candidates if e["id"] in retained]
                def read_choice(obj):
                    return {"label": field(obj, "label", ("real", "ai_generated")),
                            "explanation": field(obj, "explanation"), "basis": "forced_after_abstention"}
                comparison = ask("实验二选一", BINARY + json.dumps(support, ensure_ascii=False), [views.overview], read_choice)
        return {"schema_version": 2, "profile": views.profile, "binary_comparison": comparison, "model": model.model, "backend": model.backend, "mode": mode,
                "image": views.info, "inspections": inspections, "format_notes": format_notes, "candidates": candidates,
                "reviews": reviews, "verdict": verdict, "calls": sum(attempts.values()),
                "attempts": attempts, "seconds": round(time.monotonic() - start, 2)}

    if mode == "direct":
        def read_direct(data):
            return {"label": field(data, "label", VERDICTS), "evidence_ids": [],
                    "explanation": field(data, "explanation")}
        return report(ask("单次直接判断", DIRECT, [views.overview], read_direct), [])
    if mode != "agents":
        raise ValueError("mode 需为 agents 或 direct。")

    roles = PAPER_ROLES if paper else ROLES
    for role, (name, task, extra) in roles.items():
        regions = list(REGIONS)
        images = [views.overview]
        if paper:
            additions = [f"Z{index+1}" for index in extra]
        else:
            additions = [extra] if extra in views.boxes else []
        if additions:
            regions.extend(additions)
            images.append(views.sheet([(role, region) for region in additions]))
        prompt = expert_prompt(role, regions, task)
        if paper:
            prompt += " Z 表示从原图按位置取出的局部，编号只供定位。用能看清的一个具体对象说明。每个数组至多一项。"
        inspections[role], result = ask(
            name, prompt, images, lambda d: observation(d, regions),
            lambda d: first_valid_observation(d, regions)
        )
        for item in result:
            candidates.append({"id": f"E{len(candidates)+1}", "role": role, **item})

    def pack(items):
        return json.dumps(items, ensure_ascii=False, separators=(",", ":"))

    ids = [e["id"] for e in candidates]
    crops = views.sheet([(e["id"], e["region"]) for e in candidates])
    images = [views.overview] + ([crops] if crops is not None else [])
    review_task = REVIEW + "\n候选证据：" + pack(candidates) + "\n本图需逐一复核的 ID：" + pack(ids)
    checked = ask("证据复核", review_task, images, lambda d: review(d, ids))
    by_id = {r["id"]: r for r in checked}
    kept = [{"id": e["id"], "region": e["region"], "location": e["location"], "finding": e["finding"],
             "alternative": e["alternative"], "direction": by_id[e["id"]]["direction"],
             "review_reason": by_id[e["id"]]["reason"]} for e in candidates if by_id[e["id"]]["status"] == "keep"]
    eligible = {e["id"]: e["direction"] for e in kept}
    verdict = ask("来源裁决", VERDICT + "\n可引用证据：" + pack(kept), [views.overview],
                  lambda d: decision(d, eligible))
    return report(verdict, checked)
