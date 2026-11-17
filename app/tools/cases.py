"""典型案例检索：从案例库（data/cases.json，来自公开的驳回复审决定书）找与本次评估相关的案例。

案例只用于参考，不作为依据，也不参与风险定级。相关性按文字判断：
待查商标或某个候选组的名称，与案例中的申请商标或引证商标共有至少两个汉字、且占较短一方的一半以上。
冻结测试集的文书不在案例库里（见 scripts/import_decisions.py）。
"""
from __future__ import annotations

import json
from functools import lru_cache

from app.config import settings
from app.tools import phonetic
from app.tools.search import longest_common


@lru_cache(maxsize=2)
def _load(path: str) -> tuple[dict, ...]:
    try:
        with open(path, encoding="utf-8") as f:
            return tuple(json.load(f))
    except FileNotFoundError:
        return ()


def _close(a: str, b: str) -> bool:
    if not a or not b:
        return False
    common = longest_common(a, b)
    return len(common) >= 2 and len(common) >= 0.5 * min(len(a), len(b))


def related(query: str, names: list[str], limit: int = 3) -> list[dict]:
    """返回最多 limit 个相关案例，每个附上“为什么相关”。"""
    q = phonetic.normalize(query)
    targets = [q] + [phonetic.normalize(n) for n in names if n]
    out = []
    for case in _load(str(settings.data_dir / "cases.json")):
        texts = [phonetic.normalize(case["applicant_mark"])] + [phonetic.normalize(c.get("text") or "")
                                                                for c in case.get("cited", [])]
        reason = next((f"“{t}”与案例中的“{x}”文字相近" for t in targets for x in texts if _close(t, x)), None)
        if not reason:
            continue
        cited = [c for c in case.get("cited", []) if c.get("mark_similar") in ("近似", "不近似")]
        out.append({
            "case_id": case["case_id"], "decision_date": case["decision_date"], "doc_type": case["doc_type"],
            "applicant_mark": case["applicant_mark"], "outcome": case["outcome"], "source_url": case["source_url"],
            "reason": reason,
            "findings": [f"“{c['text']}”：{c['mark_similar']}" + (f"（{c['excerpt']}）" if c.get("excerpt") else "")
                         for c in cited[:4]],
        })
        if len(out) >= limit:
            break
    return out
