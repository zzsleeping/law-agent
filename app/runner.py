"""不经过页面跑完整流程的辅助函数，供测试、评估脚本和命令行验收使用。"""
from __future__ import annotations

import uuid
from datetime import date
from typing import Callable

from langgraph.types import Command

from app.graph import build_graph
from app.state import GoodsItem
from app.tools import goods as goods_tool


def items_by_code(codes: list[str]) -> list[GoodsItem]:
    lib = {}
    for it in goods_tool.all_items():
        lib.setdefault(it["code"], it)
    return [goods_tool.to_item(lib[c], "confirmed") for c in codes]


def run_pre_filing(
    query_mark: str,
    goods_desc: str = "",
    goods: list[GoodsItem] | None = None,          # 给定则跳过“采用系统建议”，直接作为用户确认结果
    eval_date: date | None = None,
    our_app_date: date | None = None,
    query_meaning: str = "",
    data_scope: str = "all",
    keep: Callable[[dict], list[str]] | None = None,   # 输入挂起时的状态，返回保留的 mark_id；默认全部保留
    graph=None,
    thread_id: str | None = None,
) -> dict:
    graph = graph or build_graph()
    cfg = {"configurable": {"thread_id": thread_id or uuid.uuid4().hex[:12]}}
    eval_date = eval_date or date.today()
    graph.invoke({
        "scenario": "pre_filing", "query_mark": query_mark, "goods_desc": goods_desc,
        "query_meaning": query_meaning, "eval_date": eval_date,
        "our_app_date": our_app_date or eval_date, "data_scope": data_scope,
    }, cfg)
    proposal = goods if goods is not None else graph.get_state(cfg).values["goods"]
    graph.invoke(Command(resume=[g.model_dump() for g in proposal]), cfg)          # 挂起点 ①
    values = graph.get_state(cfg).values
    kept = keep(values) if keep else list(values["display_order"])
    graph.invoke(Command(resume={"keep": kept}), cfg)                              # 挂起点 ②
    return graph.get_state(cfg).values


def run_review(query_mark: str, citations: list[str], goods: list[GoodsItem], app_date: date,
               eval_date: date | None = None, priority_date: date | None = None, keep=None, graph=None,
               thread_id: str | None = None) -> dict:
    """驳回复审：录入引证编号，逐件比对。app_date 为我方实际申请日（必填）。"""
    graph = graph or build_graph()
    cfg = {"configurable": {"thread_id": thread_id or uuid.uuid4().hex[:12]}}
    eval_date = eval_date or date.today()
    graph.invoke({"scenario": "rejection_review", "query_mark": query_mark, "user_citations": citations,
                  "goods_desc": "、".join(g.name for g in goods), "eval_date": eval_date,
                  "our_app_date": app_date, "our_priority_date": priority_date, "data_scope": "real"}, cfg)
    graph.invoke(Command(resume=[g.model_dump() for g in goods]), cfg)
    values = graph.get_state(cfg).values
    kept = keep(values) if keep else list(values["display_order"])
    graph.invoke(Command(resume={"keep": kept}), cfg)
    return graph.get_state(cfg).values
