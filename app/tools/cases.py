"""参考判例：按比对情形检索（2026-11-19 起替代按文字检索）。

对每个要展示的名称组，先判断“待查商标—在先商标”属于哪种比对情形（app/rules/patterns.py），
再从案例库（data/cases.json，来自公开的评审文书）里找同一情形的官方认定，近似、不近似各取几件，
让用户看到官方在同一种情形下怎么区分。

- 判例只供参考，不作为依据，不参与风险定级；
- 冻结测试集一侧的文书默认不展示（settings.cases_include_frozen），评测期间技术侧不看冻结集内容；
- 排序：认定理由写得具体的优先，与本组文字结构接近的优先（共用部分的比例、位置、字数差），同一份文书只取一件。
"""
from __future__ import annotations

import json
from functools import lru_cache

from app.config import settings
from app.rules import patterns

# 认定理由的具体程度：写到含义、显著性等实质原因的最有参考价值；只写比较了哪些方面的次之；只有结论的最低
# “在文字构成、呼叫、含义等方面相近”“尚可区分”这类套话不算实质原因
SUBSTANTIVE = ("臆造", "固有", "固定含义", "显著性", "通用", "描述", "知名", "显著部分", "显著识别", "主要识别",
               "整体含义", "含义不同", "含义上", "含义区", "常用")
ASPECTS = ("呼叫", "外观", "文字构成", "字形", "读音", "视觉", "构图", "含义", "字序")


def _path() -> str:
    return str(settings.data_dir / "cases.json")


@lru_cache(maxsize=2)
def _load(path: str) -> tuple[dict, ...]:
    try:
        with open(path, encoding="utf-8") as f:
            return tuple(json.load(f))
    except FileNotFoundError:
        return ()


@lru_cache(maxsize=4)
def _pairs(path: str, include_frozen: bool) -> tuple[dict, ...]:
    """把案例库展开成商标对，并标上比对情形。"""
    out = []
    for case in _load(path):
        if case.get("split", "tune") != "tune" and not include_frozen:
            continue
        q = patterns.clean(case["applicant_mark"])
        for c in case.get("cited", []):
            t = patterns.clean(c.get("text") or "")
            if c.get("mark_similar") not in ("近似", "不近似") or not q or not t:
                continue
            out.append({"case_id": case["case_id"], "doc_type": case.get("doc_type", ""),
                        "decision_date": case.get("decision_date", ""), "source_url": case.get("source_url", ""),
                        "applicant": case["applicant_mark"], "cited": c.get("text"), "q": q, "c": t,
                        "label": c["mark_similar"], "excerpt": c.get("excerpt") or "",
                        "pattern": patterns.classify(q, t)})
    return tuple(out)


def reason_level(excerpt: str) -> int:
    """2 = 写了实质原因；1 = 写了比较的方面；0 = 只有结论。"""
    if any(w in excerpt for w in SUBSTANTIVE):
        return 2
    return 1 if any(w in excerpt for w in ASPECTS) else 0


def _shape(q: str, c: str) -> tuple[float, str, int]:
    """文字结构：(共用部分占较长一方的比例, 共用部分在在先商标中的位置, 两边字数差)。"""
    from app.tools.search import longest_common

    common = longest_common(q, c)
    if not common:
        return 0.0, "", len(c) - len(q)
    pos = "head" if c.startswith(common) else "tail" if c.endswith(common) else "mid"
    return len(common) / max(len(q), len(c)), pos, len(c) - len(q)


def _score(p: dict, q: str, c: str) -> float:
    """与本组文字结构越接近、认定理由越具体，分越高。"""
    r1, pos1, d1 = _shape(q, c)
    r2, pos2, d2 = _shape(p["q"], p["c"])
    return 1.5 * reason_level(p["excerpt"]) - 3 * abs(r1 - r2) - (1.0 if pos1 != pos2 else 0) - 0.3 * abs(d1 - d2)


def for_pair(query: str, cited: str, k: int = 2, exclude_docs: set | None = None) -> dict:
    """与“待查商标 query—在先商标 cited”同一比对情形的判例：{pattern, similar, dissimilar, note}。"""
    q, c = patterns.clean(query), patterns.clean(cited)
    pat = patterns.classify(q, c)
    out = {"pattern": pat, "similar": [], "dissimilar": [], "note": ""}
    if pat == "完全相同":
        out["note"] = "文字完全相同，一般直接认定为相同商标，不列参考判例"
        return out
    if pat not in patterns.USEFUL:
        out["note"] = "两商标不共用汉字，不检索同类判例"
        return out
    pool = [p for p in _pairs(_path(), settings.cases_include_frozen)
            if p["pattern"] == pat and p["case_id"] not in (exclude_docs or set())
            and not (p["q"] == q and p["c"] == c)]
    for label, key in (("近似", "similar"), ("不近似", "dissimilar")):
        seen = set()
        for p in sorted((p for p in pool if p["label"] == label), key=lambda p: -_score(p, q, c)):
            if p["case_id"] in seen:
                continue
            seen.add(p["case_id"])
            out[key].append({k2: p[k2] for k2 in ("case_id", "doc_type", "decision_date", "source_url",
                                                   "applicant", "cited", "label", "excerpt")})
            if len(out[key]) >= k:
                break
    missing = [lab for lab, key in (("近似", "similar"), ("不近似", "dissimilar")) if not out[key]]
    if missing:
        out["note"] = f"案例库中暂无同类情形（{pat}）的{'、'.join(missing)}判例"
    return out


def prompt_text(pc: dict | None) -> str:
    """把 for_pair 的结果写成判定提示词里的一段文字。"""
    if not pc or not (pc.get("similar") or pc.get("dissimilar")):
        return "（无）"
    lines = [f"比对情形：{pc['pattern']}"]
    for c in pc.get("similar", []) + pc.get("dissimilar", []):
        lines.append(f"- 官方认定{c['label']}：“{c['applicant']}” / “{c['cited']}”——{c['excerpt'] or '原文未述理由'}")
    return "\n".join(lines)


def coverage() -> dict:
    """各情形的判例数，供页面和统计使用：{情形: {"近似": n, "不近似": n}}。"""
    res: dict = {}
    for p in _pairs(_path(), settings.cases_include_frozen):
        res.setdefault(p["pattern"], {"近似": 0, "不近似": 0})[p["label"]] += 1
    return res
