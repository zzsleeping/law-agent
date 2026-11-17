"""LangGraph 状态图：16 个节点，2 个人工挂起点，2 个条件路由。

申请前筛查（pre_filing）走五路并行召回；驳回复审（rejection_review）跳过召回，
用户录入的引证直接进入评级，不受截断，逐件给出比对结论（不做复审论证提纲）。
"""
from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from app.config import settings
from app.nodes.assess import assess, explain
from app.nodes.compose import compose
from app.nodes.confirm import confirm_candidates, confirm_goods
from app.nodes.merge import merge
from app.nodes.parse import parse
from app.nodes.recall import (load_citations, recall_exact, recall_glyph, recall_meaning, recall_pinyin,
                              recall_variant)
from app.nodes.render import flag_output, render
from app.nodes.verify import verify
from app.state import AgentState

RECALL = ["recall_exact", "recall_glyph", "recall_pinyin", "recall_variant", "recall_meaning"]


def route_after_verify(s: AgentState) -> str:
    if not s.get("citation_errors"):
        return "render"
    return "compose" if s["retry_count"] <= settings.max_rewrites else "flag_output"   # 最多重写 2 次


def build_graph(checkpointer=None):
    g = StateGraph(AgentState)
    for name, fn in {
        "parse": parse,                              # 要素解析 + 商品项映射（P1）
        "confirm_goods": confirm_goods,              # interrupt ① 用户确认商品项
        "recall_exact": recall_exact, "recall_glyph": recall_glyph, "recall_pinyin": recall_pinyin,
        "recall_variant": recall_variant, "recall_meaning": recall_meaning,
        "merge": merge,                              # 排名融合
        "load_citations": load_citations,            # 驳回复审：载入用户录入的引证
        "assess": assess,                            # 规则表定级（不调用模型）
        "explain": explain,                          # 大模型解释（P2）
        "confirm_candidates": confirm_candidates,    # interrupt ② 用户确认候选
        "compose": compose,                          # 结构化结论（P3）
        "verify": verify,
        "render": render,                            # 按版本渲染条号与原文，导出 Word
        "flag_output": flag_output,
    }.items():
        g.add_node(name, fn)

    g.add_edge(START, "parse")
    g.add_edge("parse", "confirm_goods")
    g.add_conditional_edges(                         # 按场景分叉：返回列表即并行扇出
        "confirm_goods",
        lambda s: ["load_citations"] if s.get("scenario") == "rejection_review" else RECALL,
        RECALL + ["load_citations"])
    g.add_edge(RECALL, "merge")                      # 列表形式：等五路全部结束
    g.add_edge("merge", "assess")
    g.add_edge("load_citations", "assess")
    g.add_edge("assess", "explain")
    g.add_edge("explain", "confirm_candidates")
    g.add_edge("confirm_candidates", "compose")
    g.add_edge("compose", "verify")
    g.add_conditional_edges("verify", route_after_verify, ["render", "compose", "flag_output"])
    g.add_edge("render", END)
    g.add_edge("flag_output", END)
    if checkpointer is None:
        # 显式登记状态里用到的自定义类型，检查点才能把它们还原成对象
        from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

        types = ["GoodsItem", "MarkRecord", "Hit", "Fact", "Assessment", "Claim", "Exclusion"]
        checkpointer = MemorySaver(serde=JsonPlusSerializer(
            allowed_msgpack_modules=[("app.state", t) for t in types]))
    return g.compile(checkpointer=checkpointer)
