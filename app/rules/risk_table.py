"""第六节的两张规则表。风险等级只由这里得出，大模型不改。"""
from __future__ import annotations

from app.rules.prior_status import GRADED, NEEDS_CHECK
from app.state import GoodsRel, Hit, Level, Prior, Risk

# 第一步：每类命中对“标识相似程度”的贡献
# 依据：《商标审查审理指南》5.5.1 各项；用指南官方例子和决定书调参集校准（eval/run_eval.py）
KIND_LEVEL: dict[str, Level] = {
    "exact": "high",            # 完全相同
    "contains_weak": "high",    # 包含，且多出部分仅为通用名称 / 描述性 / 弱显著文字（5.5.1.12–14）
    "contains_major": "high",   # 完整包含对方，且被包含部分占比较大（5.5.1.16）
    "glyph_single": "high",     # 仅一字形近替换（5.5.1.5）
    "edit_one": "high",         # 三字以上仅一字不同或仅多一字，首字相同（5.5.1.7）
    "redup": "high",            # 叠字 / 叠词（5.5.1.3）
    "pinyin_tone": "medium",    # 带声调拼音相同：读音相同还需字形近似才判高（5.5.1.4，反例“好歌 / 好哥”）
    "contains": "medium",       # 包含，但被包含部分占比小
    "shared_head": "high",      # 共有显著部分且是两商标的开头（字头相同），各自另有文字（5.5.1.15）。
                                # 2026-11-19 调参集：此类 31 对官方全部认定近似、0 对不近似；字头是呼叫和认读的主要部分
    "shared_part": "medium",    # 共有显著部分但不在两商标开头（共尾、居中），各自另有文字（5.5.1.15）；
                                # 调参集 34 对中 8 对官方认定不近似（如“外星森林 / 元气森林”“燊海徐记 / 徐记海鲜”）
    "pinyin_plain": "medium",   # 无声调拼音相同
    "pinyin_edit": "medium",    # 音节编辑距离小
    "glyph_edit": "medium",     # 仅个别字不同但首字不同（5.5.1.7 但书）
    "meaning": "medium",        # 义近（5.5.1.6）
    "transpose": "high",        # 整个商标仅相邻两字顺序互换（5.5.1.2，如“坤星 / 星坤”）；调参集 9 对全部认定近似。
                                # 但书（含义区别明显的不判近似）由大模型结合含义判断
    "transpose_extra": "medium",  # 互换的两字之外另有附加文字（5.5.1.2 但书例“亚美航空 / 美亚医疗”），最多到中
    "pinyin_fuzzy": "low",      # 仅模糊音
}
GLYPH_KINDS = {"glyph_single", "edit_one", "glyph_edit"}
_RANK = {"high": 2, "medium": 1, "low": 0}

LEVEL_LABEL = {"high": "高", "medium": "中", "low": "低"}
RISK_LABEL = {"high": "高风险", "medium": "中风险", "low": "低风险", "needs_check": "待核实"}


def mark_similarity(hits: list[Hit]) -> Level:
    kinds = {h.kind for h in hits}
    if "pinyin_tone" in kinds and kinds & GLYPH_KINDS:
        return "high"                                   # 读音相同且字形近似（5.5.1.4）
    best: Level = "low"
    for h in hits:
        lv = KIND_LEVEL.get(h.kind, "low")
        if _RANK[lv] > _RANK[best]:
            best = lv
    return best


def risk_level(prior: Prior, goods_rel: GoodsRel, mark_sim: Level) -> tuple[Risk, int]:
    """第二步：自上而下匹配，第一条命中即为结果。返回 (风险, 命中的规则行号)。"""
    notable = mark_sim in ("high", "medium")
    if prior in ("invalid", "not_prior"):
        return "low", 1                      # 不构成在先障碍
    if goods_rel == "dissimilar":
        return "low", 2                      # 商品不类似，不论状态都不构成冲突；未考虑驰名商标跨类保护
    if prior in NEEDS_CHECK:
        return "needs_check", 3              # 在先状态待核实：弱命中也保留待核实，不回落到低风险
    if prior in GRADED:
        if goods_rel == "pending" and notable:
            return "needs_check", 4          # 商品关系缺数据
        if goods_rel in ("same", "similar", "linked"):
            if mark_sim == "high":
                return "high", 5
            if mark_sim == "medium":
                return "medium", 6
    return "low", 7
