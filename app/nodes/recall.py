"""五路并行召回。每路写自己的字段，互不冲突。"""
from __future__ import annotations

import time

from app.config import settings
from app.state import AgentState
from app.tools import phonetic
from app.tools import search


def _run(name: str, field: str, fn, *args) -> dict:
    t0 = time.time()
    hits = fn(*args)
    dt = round(time.time() - t0, 3)
    return {field: hits, "timings": {name: dt},
            "trace": [{"node": name, "hits": len(hits), "seconds": dt}]}


def _variants(s: AgentState) -> tuple:
    """候选生成用的附加检索词：待查商标的各段 + 检索规划 Agent 给出的写法。"""
    return tuple(search.query_segments(s["query_mark"])) + tuple(v["text"] for v in s.get("search_variants", []))


def _pool(s: AgentState) -> list[dict]:
    return search.candidate_pool(s["query_mark"], s["classes"], s.get("data_scope", "all"), _variants(s))


def _text_channel(name: str, field: str, fn, s: AgentState) -> dict:
    def go():
        pool = _pool(s)
        group = {c["mark_id"]: c.get("group") or c["norm_text"] for c in pool}
        hits = search.recall_with_segments(fn, s["query_mark"], s["classes"], s.get("data_scope", "all"), pool)
        return [h.model_copy(update={"group": group.get(h.mark_id, "")}) for h in hits]
    return _run(name, field, go)


def recall_exact(s: AgentState) -> dict:
    return _text_channel("recall_exact", "hits_exact", search.recall_exact, s)


def recall_glyph(s: AgentState) -> dict:
    return _text_channel("recall_glyph", "hits_glyph", search.recall_glyph, s)


def recall_pinyin(s: AgentState) -> dict:
    return _text_channel("recall_pinyin", "hits_pinyin", search.recall_pinyin, s)


def recall_variant(s: AgentState) -> dict:
    return _text_channel("recall_variant", "hits_variant", search.recall_variant, s)


def recall_meaning(s: AgentState) -> dict:
    """义近通道。

    1. 检索规划 Agent 给出的写法：与写法完全相同或包含它的商标，标注“由哪个写法、因什么理由”检出；
    2. 本地小库上的释义向量检索（开放数据有上千万个名称，本机无法逐一编码，只在本地记录上做）。
    """
    from app.library import get_library
    from app.state import Hit

    def go():
        hits: list[Hit] = []
        variants = s.get("search_variants", [])
        if variants:
            pool = _pool(s)
            group = {c["mark_id"]: c.get("group") or c["norm_text"] for c in pool}
            q = phonetic.normalize(s["query_mark"])
            for rank_base, v in enumerate(variants):
                for c in pool:
                    t = c["norm_text"]
                    if t == q:
                        continue
                    if t == v["text"] or (len(v["text"]) >= 2 and v["text"] in t):
                        hits.append(Hit(mark_id=c["mark_id"], channel="meaning", kind="meaning",
                                        score=(2.0 if t == v["text"] else 1.0) - rank_base * 0.01,
                                        evidence=f"检索规划：与写法“{v['text']}”{'相同' if t == v['text'] else '包含该写法'}（{v['why']}）",
                                        group=group.get(c["mark_id"], "")))
        scope = s.get("data_scope", "all")
        if get_library().available():
            scope = "simulated" if scope in ("all", "simulated") else None
        if scope:
            hits += search.recall_meaning(s.get("query_meaning", ""), s["classes"], scope, None, s["query_mark"])
        return search._ranked(hits, settings.top_k_per_channel)
    return _run("recall_meaning", "hits_meaning", go)


def load_citations(s: AgentState) -> dict:
    """驳回复审：按用户录入的引证编号读取商标，逐件比对，不经过召回和截断。

    每件引证单独成组（同一编号在多个类别的档案归为一组），展示顺序即录入顺序。
    库内找不到的编号列入 missing_citations，在报告里提示人工补充。
    """
    from app import db
    from app.library import get_library
    from app.tools import phonetic

    t0 = time.time()
    lib = get_library()
    order, groups_, missing = [], [], []
    for raw in s.get("user_citations", []):
        cid = raw.strip()
        if not cid:
            continue
        ids = lib.find(cid) if lib.available() else []
        if not ids and db.load_records([cid]):
            ids = [cid]                                  # 本地记录（决定书导入）
        if not ids:
            missing.append(cid)
            continue
        new = [i for i in ids if i not in order]
        order += new
        groups_.append((cid, new))
    records = db.load_records(order)
    by_mark, display_groups = {}, []
    for cid, ids in groups_:
        ids = [i for i in ids if i in records]
        for i in ids:
            hits = search.compare(s["query_mark"], records[i].text)
            by_mark[i] = [h.model_copy(update={"mark_id": i, "group": cid, "rank": 1}) for h in hits]
        if ids:
            from app.rules.risk_table import mark_similarity
            display_groups.append({"group": cid, "marks": ids,
                                   "level": mark_similarity([h for i in ids for h in by_mark[i]]),
                                   "channels": sorted({h.channel for i in ids for h in by_mark[i]}),
                                   "exact": any(h.kind == "exact" for i in ids for h in by_mark[i])})
    order = [i for i in order if i in records]
    dt = round(time.time() - t0, 3)
    notes = [f"以下引证商标在库内找不到，需人工补充后再比对：{'、'.join(missing)}"] if missing else []
    return {"display_order": order, "display_groups": display_groups, "hits_by_mark": by_mark,
            "records": records, "recalled_total": len(order), "missing_citations": missing,
            "degraded_notes": notes, "timings": {"load_citations": dt},
            "trace": [{"node": "load_citations", "found": len(display_groups), "missing": len(missing), "seconds": dt}]}
