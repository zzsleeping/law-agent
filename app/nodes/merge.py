"""merge：按名称归组，输出唯一的展示顺序。

真实商标库里同一名称常有多件注册（不同类别、不同申请），逐件排序会让少数名称占满名额，
所以排序以“名称组”为单位：组 = 商标的整体规范化名称。
组的排序依据（2026-11-18 与用户确认）：
1. 标识相似程度（高 > 中 > 低）——只看两个标识像不像，不混入在先状态和商品关系；
2. 命中的通道数；
3. RRF 分数：RRF(g) = Σ w_c / (k + rank_c(g))，rank_c(g) 为该组在通道 c 中的最好名次。
完全同名的组置顶、全部保留（整体名称相同的排在只有某一段相同的前面）；其余取前 top_n_assess 组。每组带出该名称在检索类别内的全部注册。
"""
from __future__ import annotations

from collections import defaultdict

from app import db
from app.config import settings
from app.rules.risk_table import mark_similarity
from app.state import AgentState, Hit
from app.tools import phonetic

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


def group_order(hits: list[Hit], query: str = "") -> tuple[list[str], dict[str, list[Hit]]]:
    hits = _dedupe(hits)
    groups: dict[str, list[Hit]] = defaultdict(list)
    for h in hits:
        groups[h.group or h.mark_id].append(h)
    rrf = rrf_scores(hits)
    level = {g: mark_similarity(hs) for g, hs in groups.items()}
    nchan = {g: len({h.channel for h in hs}) for g, hs in groups.items()}
    exact = {g for g, hs in groups.items() if any(h.kind == "exact" for h in hs)}
    whole = phonetic.normalize(query)
    key = lambda g: (g != whole, -_RANK[level[g]], -nchan[g], -rrf[g], g)  # noqa: E731  整体名称完全相同的组最前
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
