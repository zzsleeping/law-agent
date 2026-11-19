"""merge：按名称归组，输出唯一的展示顺序。

真实商标库里同一名称常有多件注册（不同类别、不同申请），逐件排序会让少数名称占满名额，
所以排序以“名称组”为单位：组 = 商标的整体规范化名称。
组的排序依据（2026-11-18 与用户确认）：
1. 标识相似程度（高 > 中 > 低）——只看两个标识像不像，不混入在先状态和商品关系。
   例外：只因“字头相同”（shared_head）而判高的组，排序时与其他“共用部分”的组同档比较（显示仍为高）。
   否则大家族里字头相同的组会整体排到前面，把共尾、居中的官方引证挤出前 10（2026-11-19 与用户确认；
   调参集 Recall@10：严格按等级 40.2%，同档比较 46.6%）；
2. 同等级内按“形状分”：共有文字占我方、占对方的比例，该名称的注册件数（品牌规模）
   （真实库里大家族常有几百个同等级的组，只按通道数和 RRF 排时顺序近乎随意，官方引证常被埋掉；
   权重见 settings.rank_weights，用 eval/rank_bench.py 在调参集上调）；
3. 命中的通道数、RRF 分数：RRF(g) = Σ w_c / (k + rank_c(g))，rank_c(g) 为该组在通道 c 中的最好名次。
完全同名的组置顶、全部保留（整体名称相同的排在只有某一段相同的前面）；其余取前 top_n_assess 组。每组带出该名称在检索类别内的全部注册。
"""
from __future__ import annotations

import math
from collections import defaultdict

from app import db
from app.config import settings
from app.rules.risk_table import GLYPH_KINDS, KIND_LEVEL, mark_similarity
from app.state import AgentState, Hit
from app.tools import phonetic
from app.tools.search import longest_common

FIELDS = ["hits_exact", "hits_glyph", "hits_pinyin", "hits_variant", "hits_meaning"]
_RANK = {"high": 2, "medium": 1, "low": 0}


def _dedupe(hits: list[Hit]) -> list[Hit]:
    """同一件商标经多段名称在同一通道多次命中时，只保留名次最好的一条。"""
    best: dict[tuple, Hit] = {}
    for h in hits:
        k = (h.mark_id, h.channel, h.kind)
        if k not in best or h.rank < best[k].rank:
            best[k] = h
    return list(best.values())


def rrf_scores(hits: list[Hit]) -> dict[str, float]:
    """按组计算 RRF；没有组名的命中按编号单独成组。"""
    ranks: dict[str, dict[str, int]] = defaultdict(dict)
    for h in hits:
        g = h.group or h.mark_id
        ranks[g][h.channel] = min(ranks[g].get(h.channel, 10 ** 9), h.rank)
    return {g: sum(settings.channel_weights.get(c, 1.0) / (settings.rrf_k + r) for c, r in cr.items())
            for g, cr in ranks.items()}


def shape_score(g: str, q: str, n_marks: int) -> float:
    """同等级内的排序分，越大越靠前。g 为组名（对方整体规范化名称），q 为我方规范化名称。"""
    if not q or not g:
        return 0.0
    w = settings.rank_weights
    c = len(longest_common(q, g))
    return (w.get("cover_q", 0) * c / len(q) + w.get("cover_t", 0) * c / len(g)
            + w.get("size", 0) * min(1.0, math.log1p(n_marks) / math.log1p(50)))


def ordering_level(hs: list[Hit]) -> str:
    """排序用的等级：只因字头相同而判高的组按中档排序，其余与标识相似程度相同。"""
    lv = mark_similarity(hs)
    if lv == "high" and not any(KIND_LEVEL.get(h.kind) == "high" and h.kind != "shared_head" for h in hs) \
            and not ({h.kind for h in hs} & {"pinyin_tone"} and {h.kind for h in hs} & GLYPH_KINDS):
        return "medium"
    return lv


def group_order(hits: list[Hit], query: str = "") -> tuple[list[str], dict[str, list[Hit]]]:
    hits = _dedupe(hits)
    groups: dict[str, list[Hit]] = defaultdict(list)
    for h in hits:
        groups[h.group or h.mark_id].append(h)
    rrf = rrf_scores(hits)
    level = {g: ordering_level(hs) for g, hs in groups.items()}
    nchan = {g: len({h.channel for h in hs}) for g, hs in groups.items()}
    exact = {g for g, hs in groups.items() if any(h.kind == "exact" for h in hs)}
    whole = phonetic.normalize(query)
    shape = {g: shape_score(g, whole, len({h.mark_id for h in hs})) for g, hs in groups.items()}
    key = lambda g: (g != whole, -_RANK[level[g]], -round(shape[g], 6), -nchan[g], -rrf[g], g)  # noqa: E731  整体名称完全相同的组最前
    order = sorted(exact, key=key) + sorted(set(groups) - exact, key=key)[: settings.top_n_assess]
    return order, groups


def display_order(hits: list[Hit]) -> list[str]:
    order, groups = group_order(hits)
    return [m for g in order for m in sorted({h.mark_id for h in groups[g]})]


def _fill_groups(hits: list[Hit]) -> list[Hit]:
    """义近等通道的命中没有组名时，用本地记录的规范化名称补上。"""
    missing = sorted({h.mark_id for h in hits if not h.group})
    if not missing:
        return hits
    recs = db.load_records(missing)
    names = {m: phonetic.normalize(r.text) for m, r in recs.items()}
    return [h if h.group else h.model_copy(update={"group": names.get(h.mark_id, h.mark_id)}) for h in hits]


def merge(s: AgentState) -> dict:
    hits = _fill_groups([h for f in FIELDS for h in s.get(f, [])])
    order, groups = group_order(hits, s.get("query_mark", ""))
    display = [m for g in order for m in sorted({h.mark_id for h in groups[g]})]
    by_mark: dict[str, list[Hit]] = {m: [] for m in display}
    for h in _dedupe(hits):
        if h.mark_id in by_mark:
            by_mark[h.mark_id].append(h)
    display_groups = [{"group": g, "marks": sorted({h.mark_id for h in groups[g]}),
                       "level": mark_similarity(groups[g]), "channels": sorted({h.channel for h in groups[g]}),
                       "exact": any(h.kind == "exact" for h in groups[g])} for g in order]
    total = len({h.mark_id for h in hits})
    n_groups = len({h.group or h.mark_id for h in hits})
    return {"display_order": display, "display_groups": display_groups, "hits_by_mark": by_mark,
            "records": db.load_records(display), "recalled_total": total,
            "trace": [{"node": "merge", "recalled": total, "groups": n_groups, "shown_groups": len(order),
                       "shown": len(display)}]}
