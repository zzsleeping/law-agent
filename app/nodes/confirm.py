"""两个人工挂起点：确认商品项、确认候选。"""
from __future__ import annotations

import time
from datetime import datetime

from langgraph.types import interrupt

from app.rules.goods_relation import linked_classes
from app.state import AgentState, Exclusion, GoodsItem


def confirm_goods(s: AgentState) -> dict:
    """interrupt ①：前端展示建议商品项并等待。恢复值为商品项列表（dict 或 GoodsItem）。"""
    answer = interrupt({"stage": "goods", "proposal": [g.model_dump() for g in s.get("goods", [])]})
    goods = [g if isinstance(g, GoodsItem) else GoodsItem(**g) for g in answer]
    for g in goods:                      # 用户确认过且能对应到区分表的才算 confirmed
        g.mapping = "confirmed" if g.code else "pending"
    classes = sorted(linked_classes(goods))
    return {"goods": goods, "classes": classes, "t_goods_confirmed": time.time(),
            "trace": [{"node": "confirm_goods", "goods": [g.name for g in goods], "classes": classes}]}


def confirm_candidates(s: AgentState) -> dict:
    """interrupt ②：用户确认保留哪些候选。恢复值为 {"keep": [mark_id], "notes": {mark_id: 说明}} 或 mark_id 列表。"""
    answer = interrupt({"stage": "candidates", "order": s.get("display_order", [])})
    if isinstance(answer, dict):
        keep, notes = set(answer.get("keep", [])), answer.get("notes", {}) or {}
    else:
        keep, notes = set(answer), {}
    selected = [a for a in s["assessments"] if a.mark_id in keep]
    now = datetime.now()
    exclusions = [Exclusion(mark_id=a.mark_id, text=a.text, risk=a.risk, at=now, note=notes.get(a.mark_id, ""))
                  for a in s["assessments"] if a.mark_id not in keep]
    return {"selected": selected, "exclusions": exclusions,      # compose 与 verify 只读 selected
            "trace": [{"node": "confirm_candidates", "kept": len(selected), "excluded": len(exclusions)}]}
