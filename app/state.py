"""AgentState 与 Pydantic 模型（方案第三节，含已确认的修订）。"""
from __future__ import annotations

import operator
from datetime import date, datetime
from typing import Annotated, Literal, TypedDict

from pydantic import BaseModel

Scenario = Literal["pre_filing", "rejection_review"]
Channel = Literal[
    "exact", "contains", "glyph", "pinyin", "pinyin_fuzzy", "meaning",
    "transpose", "redup", "user_cited",
]
# 每条命中的细分类型，决定它对“标识相似程度”的贡献（app/rules/risk_table.py）
HitKind = Literal[
    "exact", "contains_weak", "contains_major", "contains", "shared_part", "glyph_single", "edit_one", "glyph_edit",
    "pinyin_tone", "pinyin_plain", "pinyin_edit", "pinyin_fuzzy",
    "meaning", "transpose", "redup",
]
Level = Literal["high", "medium", "low"]
GoodsRel = Literal["same", "similar", "linked", "pending", "dissimilar"]
# lapsed_recent：已失效但未满一年或失效日期不明，可能仍被引证（指南 18.3）
Prior = Literal["valid", "registered", "prelim", "earlier_app", "same_day", "pending_long", "expired",
                "lapsed_recent", "unknown", "not_prior", "invalid"]   # 含义见 app/rules/prior_status.py
Risk = Literal["high", "medium", "low", "needs_check"]


class GoodsItem(BaseModel):
    """落到具体商品项；群号只作线索。code 为空表示未能对应到区分表。"""
    name: str
    code: str | None = None
    nice_class: int | None = None
    group: str | None = None
    mapping: Literal["confirmed", "pending"] = "pending"


class MarkRecord(BaseModel):
    mark_id: str
    text: str
    meaning: str = ""
    owner: str = ""
    app_date: date | None = None
    priority_date: date | None = None
    reg_date: date | None = None
    prelim_date: date | None = None       # 初审公告日期
    term_end: date | None = None          # 记录的专用期截止日
    status: str | None = None             # 状态文字（决定书等来源才有；开放数据为空，按日期推定）
    invalid_date: date | None = None      # 失效日期（撤销、无效、注销、期满）
    invalid_reason: str | None = None     # 失效原因
    goods: list[GoodsItem] = []
    snapshot_date: date | None = None
    source: str = ""
    source_ref: str | None = None
    is_simulated: bool = False


class Hit(BaseModel):
    """某一路召回的一条命中。score 只在本路内排序用，不跨路比较。"""
    mark_id: str
    channel: Channel
    kind: HitKind
    rank: int = 0
    score: float = 0.0
    evidence: str = ""
    group: str = ""                  # 所属名称组（商标的整体规范化名称）；同名的多件注册归为一组


class Fact(BaseModel):
    """由代码生成、可被结论引用的事实；模型不能新增。"""
    fact_id: str
    mark_id: str | None          # 全局事实（检索范围等）为 None
    kind: Literal["hit", "goods", "prior", "data_gap", "scope", "group"]
    text: str
    group: str = ""                  # 所属名称组；同组各件的事实可以互相引用


class Assessment(BaseModel):
    mark_id: str
    text: str
    group: str = ""                  # 名称组；为空时视为单独一组（组名 = 编号）
    mark_sim: Level
    goods_rel: GoodsRel
    prior: Prior
    risk: Risk                       # 规则表得出，模型不改
    channels: list[str] = []
    fact_ids: list[str] = []
    basis_ids: list[str] = []        # 代码按映射表给出的建议依据（降级时直接使用）
    hints: list[str] = []            # 不参与定级的提示（历史交叉检索等）
    explanation: str = ""
    explanation_source: Literal["llm", "code"] = "code"
    flag_review: bool = False
    # 大模型判定（2026-11-18 起由大模型定风险，规则作参考和护栏）
    rule_risk: str = ""              # 规则引擎的参考等级
    rule_mark_sim: str = ""
    decided_by: Literal["llm", "rule"] = "rule"   # rule：未经模型判定（超出调用上限或模型失败）
    guardrail: str = ""              # 护栏修正说明，空表示模型判断未被修正
    disagree: bool = False           # 模型与规则判断不一致


ClaimType = Literal["risk", "data_gap", "overall"]


class Claim(BaseModel):
    mark_id: str | None              # overall 结论为 None
    claim_type: ClaimType
    conclusion: str
    fact_ids: list[str] = []
    basis_ids: list[str] = []
    source: Literal["llm", "code"] = "llm"


class Exclusion(BaseModel):
    mark_id: str
    text: str = ""
    risk: str
    at: datetime
    note: str = ""


def merge_dict(a: dict | None, b: dict | None) -> dict:
    return {**(a or {}), **(b or {})}


def either(a: bool | None, b: bool | None) -> bool:
    return bool(a) or bool(b)


class AgentState(TypedDict, total=False):
    scenario: Scenario
    eval_date: date                  # 评估日：决定适用的法规版本
    our_app_date: date               # 我方（模拟）申请日：决定在先关系
    our_priority_date: date | None
    data_scope: Literal["all", "real", "simulated"]
    fresh: bool                      # 用户点了“重新评估”：大模型调用不读缓存（app/cache.py）
    query_mark: str
    search_variants: list[dict]      # 检索规划 Agent 决定的额外写法：text、why、hits
    user_citations: list[str]        # 驳回复审：驳回通知中的引证商标编号（申请号 / 注册号）
    missing_citations: list[str]     # 驳回复审：库内找不到的引证编号
    query_meaning: str               # 可由用户填写；否则由 P1 生成
    distinctive: str
    goods_desc: str
    goods: list[GoodsItem]
    classes: list[int]               # 召回的类别范围
    t_goods_confirmed: float
    hits_exact: list[Hit]            # 各路独立字段，并行写入不冲突
    hits_glyph: list[Hit]
    hits_pinyin: list[Hit]
    hits_meaning: list[Hit]
    hits_variant: list[Hit]
    display_order: list[str]         # 唯一的展示顺序（按名称组排列，组内各件相邻）
    display_groups: list[dict]       # 名称组：group、marks、level、channels、exact
    recalled_total: int
    records: dict[str, MarkRecord]
    hits_by_mark: dict[str, list[Hit]]
    facts: dict[str, Fact]
    assessments: list[Assessment]
    selected: list[Assessment]
    exclusions: list[Exclusion]
    allowed_basis: list[str]
    basis_sources: dict[str, str]    # 依据来源：rag 表示由 RAG 检索补充（其余来自映射表）
    claims: list[Claim]
    citation_errors: list[str]
    retry_count: int
    report: dict
    report_path: str
    degraded: Annotated[bool, either]
    degraded_notes: Annotated[list[str], operator.add]
    timings: Annotated[dict[str, float], merge_dict]
    trace: Annotated[list[dict], operator.add]
