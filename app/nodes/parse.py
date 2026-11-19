"""parse：要素解析 + 商品项映射（P1）。模型失败时只用向量检索的建议。"""
from __future__ import annotations

import time

from app import llm
from app.state import AgentState
from app.tools import goods as goods_tool


def parse(s: AgentState) -> dict:
    t0 = time.time()
    proposal, candidates = goods_tool.map_goods(s.get("goods_desc", ""))
    out: dict = {"distinctive": "", "query_meaning": s.get("query_meaning", "") or ""}
    data = llm.chat_json("p1_parse", {
        "query_mark": s["query_mark"], "goods_desc": s.get("goods_desc", ""),
        "candidates": {part: [{"code": c["code"], "name": c["name"], "class": c["nice_class"]} for c in cs]
                       for part, cs in candidates.items()},
    }, refresh=bool(s.get("fresh")))
    notes = []
    if data is None:
        notes.append(f"要素解析未使用大模型（{llm.describe_error()}）：商品项仅为向量检索建议，请人工确认"
                     + ("；未生成商标释义，义近召回将跳过" if not out["query_meaning"] else ""))
    else:
        out["distinctive"] = str(data.get("distinctive") or "")
        if not out["query_meaning"]:
            out["query_meaning"] = str(data.get("meaning") or "")
        picked = []
        for g in data.get("goods") or []:
            part, code = g.get("part"), g.get("code")
            match = next((c for c in candidates.get(part, []) if c["code"] == code), None)  # 只能从候选中选
            if match:
                picked.append(goods_tool.to_item(match, "confirmed"))
            elif part:
                picked.append(goods_tool.GoodsItem(name=part, mapping="pending"))
        covered = {g.get("part") for g in data.get("goods") or []}
        for part in candidates:                       # 用户写了、模型没选的商品（多为选录类别之外的）也要保留，标待核实
            if part not in covered:
                picked.append(goods_tool.GoodsItem(name=part, mapping="pending"))
        if picked:
            seen: set = set()
            proposal = [g for g in picked if not ((g.code, g.name) in seen or seen.add((g.code, g.name)))]
    out.update({
        "goods": proposal,
        "degraded": data is None,
        "degraded_notes": notes,
        "timings": {"parse": round(time.time() - t0, 3)},
        "trace": [{"node": "parse", "llm": data is not None, "goods": [g.name for g in proposal]}],
    })
    return out
