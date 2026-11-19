"""比对情形：按系统的文字比对规则，把一对商标归入一种情形。

用于按情形检索参考判例（app/tools/cases.py）和统计判例覆盖（scripts/pattern_coverage.py）。
情形只描述两商标文字之间的关系，与官方是否认定近似无关。
"""
from __future__ import annotations

import re
from functools import lru_cache

HAN = re.compile(r"[一-鿿]")
PATTERNS = ["完全相同", "完整包含", "仅一字不同", "字序颠倒", "叠字", "读音相同/相近", "字形相近",
            "共用部分", "共用字但未命中", "无文字命中"]
# 有参考价值的情形：不共用汉字的不检索判例
USEFUL = PATTERNS[:8]


def clean(text: str) -> str:
    """去掉“及图”，只保留汉字（与评测集的清洗一致）。"""
    return "".join(HAN.findall((text or "").replace("及图", "")))


@lru_cache(maxsize=4096)
def classify(query: str, cited: str) -> str:
    from app.tools import phonetic
    from app.tools.search import compare

    q, c = phonetic.normalize(clean(query)), phonetic.normalize(clean(cited))
    if not q or not c:
        return "无文字命中"
    if q == c:
        return "完全相同"
    hits = compare(q, c)
    if not hits:
        return "共用字但未命中" if set(q) & set(c) else "无文字命中"
    kinds = {h.kind for h in hits}
    glyph_ev = " ".join(h.evidence for h in hits if h.kind == "glyph_edit")
    # 按命中类型归类（类型见 app/tools/search.py），优先级从上到下
    # 字序颠倒分两种：整体互换；局部互换且另有附加文字。后者在任意位置找互换的两个字，
    # 容易误报（如“可口纯 / 可口可乐”里的“口可”），只在两商标之间没有别的关系时才采用
    swaps = [h for h in hits if h.kind == "transpose"]
    if any("另有附加文字" not in h.evidence for h in swaps):
        return "字序颠倒"
    if "redup" in kinds:
        return "叠字"
    if any(k.startswith("contains") for k in kinds):
        return "完整包含"
    if swaps and kinds <= {"transpose"}:
        return "字序颠倒"
    if "glyph_single" in kinds or (glyph_ev and not glyph_ev.startswith("仅个别")):   # 差异全是形近字替换
        return "字形相近"
    if kinds & {"edit_one", "glyph_edit"}:
        return "仅一字不同"
    if any(k.startswith("pinyin") for k in kinds):
        return "读音相同/相近"
    return "共用部分"
