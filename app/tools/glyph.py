"""字形工具：形近字判断、加权编辑距离、字序颠倒与叠字判断。

形近字有两个来源：
1. 汉字部件拆分（CJKVI IDS，data/glyph/ids.txt，GPL-2.0-or-later）：把字递归拆到最小部件后比较，
   只差单笔画部件，或只有一对外形相近的部件（data/glyph/component_pairs.csv）不同，判为形近；
2. 手工字表（data/glyph_pairs.csv）：补充无法拆分的单部件字，如 己/已/巳、未/末。
"""
from __future__ import annotations

import csv
import re
from functools import lru_cache

from app.config import settings

IDC = re.compile(r"[\u2FF0-\u2FFF\u31EF]")
PLACEHOLDER = re.compile(r"[\u2460-\u24FF？?]")        # 圈号部件、问号：拆分数据里的未知部件
SMALL = set("丶一丨丿乀乙乚亅㇇𠃌㇏乛⺀")                     # 单笔画部件
SMALL_COST = 0.3
PAIR_COST = 0.3
GLYPH_IDS_MAX = 0.6


@lru_cache(maxsize=2)
def _pairs(path: str) -> frozenset:
    out = set()
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            a, b = (row.get("char_a") or row.get("comp_a") or "").strip(), (row.get("char_b") or row.get("comp_b") or "").strip()
            if a and b and a != b:
                out.add(frozenset((a, b)))
    return frozenset(out)


@lru_cache(maxsize=2)
def _ids(path: str) -> dict[str, str]:
    """字 -> IDS。优先取标注 [G]（中国大陆字形）或未标注地区的写法。"""
    out: dict[str, str] = {}
    try:
        lines = open(path, encoding="utf-8").read().splitlines()
    except FileNotFoundError:
        return out
    for line in lines:
        if line.startswith(("#", ";")):
            continue
        cols = line.split("\t")
        if len(cols) < 3:
            continue
        char, forms = cols[1], cols[2:]
        pick = next((f for f in forms if "[" not in f or "G" in f[f.index("["):]), forms[0])
        out[char] = re.sub(r"\[.*?\]", "", pick).strip()
    return out


def _ids_map() -> dict[str, str]:
    return _ids(str(settings.data_dir / "glyph" / "ids.txt"))


@lru_cache(maxsize=20000)
def leaves(ch: str, depth: int = 0) -> tuple[str, ...]:
    """把一个字递归拆成最小部件序列（按书写位置顺序，去掉结构符）。拆不动的字自身就是部件。"""
    ids = _ids_map().get(ch)
    if depth > 8 or not ids or ids == ch:
        return (ch,)
    out: list[str] = []
    for c in ids:
        if IDC.match(c) or c.isspace():
            continue
        if PLACEHOLDER.match(c):
            out.append("?")
        else:
            out.extend(leaves(c, depth + 1))
    return tuple(out) or (ch,)


def _manual(a: str, b: str) -> bool:
    return frozenset((a, b)) in _pairs(str(settings.data_dir / "glyph_pairs.csv"))


def _component_pair(a: str, b: str) -> bool:
    return frozenset((a, b)) in _pairs(str(settings.data_dir / "glyph" / "component_pairs.csv"))


def ids_distance(a: str, b: str) -> float:
    """两个字最小部件序列的加权编辑距离：增删单笔画部件、替换相近部件代价低，其余代价 1。"""
    la, lb = leaves(a), leaves(b)
    if "?" in la or "?" in lb:
        return 9.0
    n, m = len(la), len(lb)
    d = [[0.0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        d[i][0] = d[i - 1][0] + (SMALL_COST if la[i - 1] in SMALL else 1.0)
    for j in range(1, m + 1):
        d[0][j] = d[0][j - 1] + (SMALL_COST if lb[j - 1] in SMALL else 1.0)
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            x, y = la[i - 1], lb[j - 1]
            sub = 0.0 if x == y else (PAIR_COST if _component_pair(x, y) or _manual(x, y) else 1.0)
            d[i][j] = min(d[i - 1][j] + (SMALL_COST if x in SMALL else 1.0),
                          d[i][j - 1] + (SMALL_COST if y in SMALL else 1.0),
                          d[i - 1][j - 1] + sub)
    return d[n][m]


@lru_cache(maxsize=50000)
def is_glyph_pair(a: str, b: str) -> bool:
    if a == b:
        return False
    if _manual(a, b):
        return True
    la, lb = leaves(a), leaves(b)
    if max(len(la), len(lb)) < 2:          # 两个都拆不动，只能靠手工字表
        return False
    return ids_distance(a, b) <= GLYPH_IDS_MAX


def glyph_reason(a: str, b: str) -> str:
    if _manual(a, b):
        return "手工字表"
    return f"部件拆分：{''.join(leaves(a))} / {''.join(leaves(b))}"


def weighted_distance(a: str, b: str) -> tuple[float, list[tuple[str, str, bool]]]:
    """返回 (加权编辑距离, 差异列表)。差异项为 (a 侧字, b 侧字, 是否形近)；增删时一侧为空串。

    形近替换代价 settings.glyph_sub_cost，普通替换、增、删代价 1。
    """
    cost = settings.glyph_sub_cost
    n, m = len(a), len(b)
    d = [[0.0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        d[i][0] = float(i)
    for j in range(1, m + 1):
        d[0][j] = float(j)
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            if a[i - 1] == b[j - 1]:
                sub = 0.0
            else:
                sub = cost if is_glyph_pair(a[i - 1], b[j - 1]) else 1.0
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + sub)
    diffs: list[tuple[str, str, bool]] = []
    i, j = n, m
    while i > 0 or j > 0:
        if i > 0 and j > 0:
            same = a[i - 1] == b[j - 1]
            glyph = (not same) and is_glyph_pair(a[i - 1], b[j - 1])
            sub = 0.0 if same else (cost if glyph else 1.0)
            if abs(d[i][j] - (d[i - 1][j - 1] + sub)) < 1e-9:
                if not same:
                    diffs.append((a[i - 1], b[j - 1], glyph))
                i, j = i - 1, j - 1
                continue
        if i > 0 and abs(d[i][j] - (d[i - 1][j] + 1)) < 1e-9:
            diffs.append((a[i - 1], "", False))
            i -= 1
        else:
            diffs.append(("", b[j - 1], False))
            j -= 1
    diffs.reverse()
    return d[n][m], diffs


def is_adjacent_swap(a: str, b: str) -> tuple[str, str] | None:
    """b 是否由 a 交换一对相邻字得到；是则返回被交换的两个字。"""
    if len(a) != len(b) or a == b:
        return None
    diff = [i for i in range(len(a)) if a[i] != b[i]]
    if len(diff) == 2 and diff[1] == diff[0] + 1:
        i, j = diff
        if a[i] == b[j] and a[j] == b[i]:
            return a[i], a[j]
    return None


def reduplication(a: str, b: str) -> str | None:
    """一方是否由另一方整体重叠而成（星/星星、哈罗/哈罗哈罗）；是则返回被重叠的单元。"""
    short, long_ = (a, b) if len(a) < len(b) else (b, a)
    if short and len(long_) > len(short) and len(long_) % len(short) == 0:
        if short * (len(long_) // len(short)) == long_:
            return short
    return None


def swapped_part(a: str, b: str) -> tuple[str, str] | None:
    """一方中的两个相邻字，在另一方中以相反顺序出现（坤星文具 / 星坤、云燕 / 燕云轩）。

    被互换的两字至少占较短商标的一半；两字相同（如“星星”）不算。返回 (一方的写法, 另一方的写法)。
    """
    for x, y in ((a, b), (b, a)):
        for i in range(len(x) - 1):
            pair = x[i:i + 2]
            rev = pair[::-1]
            if pair[0] != pair[1] and rev in y and pair not in y and 2 >= 0.5 * min(len(a), len(b)):
                return pair, rev
    return None
