"""plan_search：检索规划 Agent。

大模型决定除原文之外还要检索哪些写法（含义相近、显著部分、繁体或谐音等），系统按计划在商标库里试查，
把每条写法的命中数交回模型，模型可以再调整一轮（最多 PLAN_ROUNDS 轮）。最终的写法并入召回：
候选池会加上这些写法检出的商标，并由“义近”通道标注来源（见 app/nodes/recall.py）。
每一轮的计划、理由和试查结果都写进执行记录，页面上可见。没有大模型时跳过，只检索原文。
"""
from __future__ import annotations

import re
import time

from app import llm
from app.library import get_library
from app.state import AgentState
from app.tools import phonetic

PLAN_ROUNDS = 2
MAX_QUERIES = 6
HAN = re.compile(r"[一-鿿]")


def _clean(queries, original: str) -> list[dict]:
    out, seen = [], {phonetic.normalize(original)}
    for q in queries or []:
        if not isinstance(q, dict):
            continue
        text = phonetic.normalize(str(q.get("text") or ""))
        if not text or not HAN.search(text) or len(text) > 12 or text in seen:
            continue
        seen.add(text)
        out.append({"text": text, "why": str(q.get("why") or "")[:60]})
    return out[:MAX_QUERIES]


def _probe(queries: list[dict], classes, scope: str) -> list[dict]:
    """试查：每条写法在检索类别内完全相同或包含它的商标有多少件。"""
    from app.tools import search

    lib = get_library()
    out = []
    for q in queries:
        if lib.available() and scope in ("real", "all"):
            cands = lib.candidates(q["text"], classes)
        else:
            cands = search.pool(classes, scope)
        n = sum(1 for c in cands if c["norm_text"] == q["text"] or (len(q["text"]) >= 2 and q["text"] in c["norm_text"]))
        out.append({**q, "hits": n})
    return out


def plan_search(s: AgentState) -> dict:
    t0 = time.time()
    trace, plan, probe_text = [], [], "（第一轮，尚未试查）"
    base = {"query_mark": s["query_mark"], "distinctive": s.get("distinctive") or s["query_mark"],
            "query_meaning": s.get("query_meaning") or "未提供",
            "goods": "、".join(g.name for g in s.get("goods", []))}
    notes = []
    for rnd in range(1, PLAN_ROUNDS + 1):
        out = llm.chat_json("p0_plan", {**base, "probe": probe_text}, refresh=bool(s.get("fresh")))
        if out is None:
            if rnd == 1:
                why = llm.describe_error()
                notes.append(f"检索规划未使用大模型（{why}），只检索原文")
            break
        plan = _probe(_clean(out.get("queries"), s["query_mark"]), s.get("classes", []), s.get("data_scope", "all"))
        trace.append({"node": "plan_search", "round": rnd,
                      "queries": [f"{q['text']}（{q['why']}，命中 {q['hits']}）" for q in plan]})
        if out.get("done") or not plan:
            break
        probe_text = "；".join(f"“{q['text']}”命中 {q['hits']} 件" for q in plan)
    dt = round(time.time() - t0, 3)
    return {"search_variants": plan, "degraded_notes": notes, "timings": {"plan_search": dt},
            "trace": trace or [{"node": "plan_search", "round": 0, "queries": []}]}
