"""召回工具（方案第五节）。

各路只在本路内排序，分数不跨路比较；都不按类似群组过滤，只限定类别范围。
初赛数据量小，直接在内存里扫描候选池；数据量上去后再改成走索引。
"""
from __future__ import annotations

import re
from functools import lru_cache

from app import db
from app.config import settings
from app.embed import get_embedder
from app.state import Hit
from app.tools import glyph, phonetic


def pool(classes: set[int] | list[int], data_scope: str | None = "all") -> list[dict]:
    """类别范围内的全部商标（去重）。"""
    classes = sorted(set(classes))
    if not classes:
        return []
    qs = ",".join("?" * len(classes))
    sql = ("SELECT DISTINCT m.mark_id, m.text, m.norm_text, m.pinyin_tone, m.pinyin, m.pinyin_fuzzy, m.meaning "
           f"FROM marks m JOIN mark_goods g USING(mark_id) WHERE g.nice_class IN ({qs})"
           + db.scope_sql(data_scope) + " ORDER BY m.mark_id")
    with db.connect() as c:
        return [dict(r) for r in c.execute(sql, classes)]


def candidate_pool(query: str, classes, data_scope: str | None = "all", variants: tuple = ()) -> list[dict]:
    """召回用的候选池。

    开放数据可用时，它就是正式的真实商标库：“仅真实”只查开放数据，“仅仿真”只查本地仿真记录，
    “全部”两者都查（本地由决定书导入的真实记录与开放数据重复，此时不再使用）。
    开放数据不可用时退回本地库。
    """
    from app.library import get_library

    lib = get_library()
    if not lib.available():
        return pool(classes, data_scope)
    out: list[dict] = []
    if data_scope in ("all", "simulated"):
        out += pool(classes, "simulated")
    if data_scope in ("all", "real"):
        seen: set[tuple] = set()
        for q in (query, *variants):                     # 原文 + 检索规划 Agent 给出的写法
            for c in lib.candidates(q, classes):
                key = (c["mark_id"], c["norm_text"])     # 多段名称的整体和各段要分别保留
                if key not in seen:
                    seen.add(key)
                    out.append(c)
    return out


SEG_SPLIT = re.compile(r"[\s;；/／、|｜]+")


def query_segments(text: str) -> list[str]:
    """待查商标由空格等分隔的多段中文时，各段单独作为检索词（整体之外）。

    例如“一葉了然 梅及图”整体规范化为“一叶了然梅”，与“一目了然”只能算共用部分；
    拆出“一叶了然”后才能识别为仅一字不同。在先商标一侧建索引时已按段拆分。
    """
    whole = phonetic.normalize(text)
    out = []
    for part in SEG_SPLIT.split((text or "").replace("及图", "")):
        seg = phonetic.normalize(part)
        if len(seg) >= 2 and seg != whole and phonetic.HAN.search(seg) and seg not in out:
            out.append(seg)
    return out


def recall_with_segments(fn, text: str, classes, data_scope: str | None, candidates: list[dict]) -> list[Hit]:
    """对整体和各段分别召回；分段命中的依据前面注明是我方哪一段。"""
    hits = fn(text, classes, data_scope, candidates=candidates)
    for seg in query_segments(text):
        hits += [h.model_copy(update={"evidence": f"我方商标中的“{seg}”：{h.evidence}"})
                 for h in fn(seg, classes, data_scope, candidates=candidates)]
    return hits


def _ranked(hits: list[Hit], top_k: int) -> list[Hit]:
    """按通道分别排序、编号、截断。"""
    out: list[Hit] = []
    by_channel: dict[str, list[Hit]] = {}
    for h in hits:
        by_channel.setdefault(h.channel, []).append(h)
    for channel, hs in by_channel.items():
        hs.sort(key=lambda h: (-h.score, h.mark_id))
        keep = hs if channel == "exact" else hs[:top_k]     # 完全同名不截断
        for i, h in enumerate(keep, 1):
            out.append(h.model_copy(update={"rank": i}))
    return out


@lru_cache(maxsize=2)
def _weak_words(data_dir: str, db_path: str) -> frozenset:
    words = set()
    for line in open(f"{data_dir}/weak_words.txt", encoding="utf-8"):
        line = line.strip()
        if line and not line.startswith("#"):
            words.add(line)
    with db.connect() as c:
        for r in c.execute("SELECT name FROM goods_items"):
            name = r["name"].replace("*", "").split("（")[0].strip()
            if name:
                words.add(name)
    return frozenset(words)


def is_weak(text: str) -> bool:
    """text 能否完全切分成弱显著文字 / 商品通用名称。空串视为是。"""
    words = _weak_words(str(settings.data_dir), str(settings.db_path))
    ok = [True] + [False] * len(text)
    for i in range(1, len(text) + 1):
        ok[i] = any(ok[j] and text[j:i] in words for j in range(max(0, i - 6), i))
    return ok[len(text)]


def recall_exact(text: str, classes, data_scope: str | None = "all", top_k: int | None = None,
                 candidates: list[dict] | None = None) -> list[Hit]:
    """完全相同（channel=exact）与包含 / 被包含（channel=contains）。"""
    q = phonetic.normalize(text)
    hits = []
    for m in (candidates if candidates is not None else pool(classes, data_scope)):
        t = m["norm_text"]
        if t == q:
            hits.append(Hit(mark_id=m["mark_id"], channel="exact", kind="exact", score=2.0,
                            evidence="文字完全相同"))
            continue
        short, long_ = (q, t) if len(q) < len(t) else (t, q)
        if len(short) >= 2 and short in long_:
            i = long_.index(short)
            before, after = long_[:i], long_[i + len(short):]
            rest = before + after
            weak = is_weak(before) and is_weak(after)
            who = "对方商标完整包含我方商标" if short == q else "我方商标完整包含对方商标"
            tail = (f"多出的“{rest}”为通用名称或弱显著文字" if weak
                    else f"多出的“{rest}”不属于弱显著文字表")
            ratio = len(short) / len(long_)
            if weak:
                kind = "contains_weak"
            elif ratio >= settings.contains_major_ratio:
                kind = "contains_major"
                tail += f"，被包含部分占较长商标的 {ratio:.0%}"
            else:
                kind = "contains"
            hits.append(Hit(mark_id=m["mark_id"], channel="contains", kind=kind,
                            score=(1.0 if kind != "contains" else 0.0) + ratio, evidence=f"{who}，{tail}"))
            continue
        common = longest_common(q, t)
        if (len(common) >= 2 and len(common) >= settings.shared_part_ratio * min(len(q), len(t))
                and not is_weak(common)):
            head = q.startswith(common) and t.startswith(common)     # 共有部分是两商标的开头（字头相同）
            hits.append(Hit(mark_id=m["mark_id"], channel="contains", kind="shared_head" if head else "shared_part",
                            score=len(common) / max(len(q), len(t)) + (0.5 if head else 0.0),
                            evidence=(f"两商标开头的“{common}”相同，其余部分不同" if head
                                      else f"两商标共有“{common}”，其余部分不同")))
    return _ranked(hits, top_k or settings.top_k_per_channel)


def longest_common(a: str, b: str) -> str:
    """最长公共子串。"""
    best, end = 0, 0
    prev = [0] * (len(b) + 1)
    for i in range(1, len(a) + 1):
        cur = [0] * (len(b) + 1)
        for j in range(1, len(b) + 1):
            if a[i - 1] == b[j - 1]:
                cur[j] = prev[j - 1] + 1
                if cur[j] > best:
                    best, end = cur[j], i
        prev = cur
    return a[end - best:end]


def recall_glyph(text: str, classes, data_scope: str | None = "all", top_k: int | None = None,
                 candidates: list[dict] | None = None) -> list[Hit]:
    """形近字替换后相同，或加权编辑距离不超过阈值。"""
    q = phonetic.normalize(text)
    hits = []
    for m in (candidates if candidates is not None else pool(classes, data_scope)):
        t = m["norm_text"]
        if t == q or abs(len(t) - len(q)) > 1:
            continue
        dist, diffs = glyph.weighted_distance(q, t)
        glyph_subs = [d for d in diffs if d[2]]
        others = [d for d in diffs if not d[2]]
        if glyph_subs and not others:                       # 全部差异都是形近替换
            kind = "glyph_single" if len(glyph_subs) == 1 else "glyph_edit"
            ev = "、".join(f"“{a}/{b}”形近" for a, b, _ in glyph_subs)
        elif len(diffs) == 1 and q[0] == t[0] and (
                (len(q) == len(t) and len(q) >= 3) or (len(q) != len(t) and min(len(q), len(t)) >= 2)):
            kind = "edit_one"                                # 指南 5.5.1.7：仅个别汉字不同，首字相同
            a, b, g = diffs[0]
            ev = (f"仅一字不同（“{a}/{b}”{'形近' if g else ''}），首字相同" if a and b
                  else f"仅多一字“{a or b}”，首字相同")
        elif dist <= settings.glyph_threshold and min(len(q), len(t)) >= 3:
            kind = "glyph_edit"                              # 三字及以上，仅个别字不同（含首字不同）
            ev = "仅个别字不同：" + "、".join(
                f"“{a or '（无）'}/{b or '（无）'}”" + ("形近" if g else "") for a, b, g in diffs)
        else:
            continue
        hits.append(Hit(mark_id=m["mark_id"], channel="glyph", kind=kind, score=-dist, evidence=ev))
    return _ranked(hits, top_k or settings.top_k_per_channel)


def recall_pinyin(text: str, classes, data_scope: str | None = "all", top_k: int | None = None,
                  candidates: list[dict] | None = None) -> list[Hit]:
    """带声调相同 > 无声调相同 > 音节编辑距离小（channel=pinyin）；仅模糊音归一后相同的为 pinyin_fuzzy。"""
    q = phonetic.normalize(text)
    k = phonetic.keys(q)
    q_syl = k["pinyin"].split()
    hits = []
    for m in (candidates if candidates is not None else pool(classes, data_scope)):
        if m["norm_text"] == q:
            continue
        if m["pinyin_tone"] == k["pinyin_tone"]:
            hits.append(Hit(mark_id=m["mark_id"], channel="pinyin", kind="pinyin_tone", score=3.0,
                            evidence=f"带声调拼音相同（{k['pinyin_tone']}）"))
        elif m["pinyin"] == k["pinyin"]:
            hits.append(Hit(mark_id=m["mark_id"], channel="pinyin", kind="pinyin_plain", score=2.0,
                            evidence=f"无声调拼音相同（{k['pinyin']}），声调不同"))
        elif m["pinyin_fuzzy"] == k["pinyin_fuzzy"]:
            hits.append(Hit(mark_id=m["mark_id"], channel="pinyin_fuzzy", kind="pinyin_fuzzy", score=1.0,
                            evidence=f"仅模糊音归一后相同（{k['pinyin']} / {m['pinyin']}）"))
        else:
            t_syl = m["pinyin"].split()
            if max(len(q_syl), len(t_syl)) >= 3 and phonetic.edit_distance(q_syl, t_syl) <= 1:
                hits.append(Hit(mark_id=m["mark_id"], channel="pinyin", kind="pinyin_edit", score=1.0,
                                evidence=f"读音仅一个音节不同（{k['pinyin']} / {m['pinyin']}）"))
    return _ranked(hits, top_k or settings.top_k_per_channel)


def recall_variant(text: str, classes, data_scope: str | None = "all", top_k: int | None = None,
                   candidates: list[dict] | None = None) -> list[Hit]:
    """字序颠倒（相邻两字互换）与叠字 / 叠词。只标注召回原因，等级仍按规则表。"""
    q = phonetic.normalize(text)
    hits = []
    for m in (candidates if candidates is not None else pool(classes, data_scope)):
        t = m["norm_text"]
        swap = glyph.is_adjacent_swap(q, t)
        if swap:
            hits.append(Hit(mark_id=m["mark_id"], channel="transpose", kind="transpose", score=1.0,
                            evidence=f"汉字构成相同，仅“{swap[0]}”“{swap[1]}”相邻两字顺序互换"))
        elif len(q) != len(t):
            part = glyph.swapped_part(q, t)
            if part:
                hits.append(Hit(mark_id=m["mark_id"], channel="transpose", kind="transpose_extra", score=0.8,
                                evidence=f"“{part[0]}”与“{part[1]}”汉字相同、顺序互换，另有附加文字"))
        unit = glyph.reduplication(q, t)
        if unit:
            hits.append(Hit(mark_id=m["mark_id"], channel="redup", kind="redup", score=1.0,
                            evidence=f"一方由“{unit}”重叠而成"))
    return _ranked(hits, top_k or settings.top_k_per_channel)


def recall_meaning(meaning: str, classes, data_scope: str | None = "all", top_k: int | None = None,
                   exclude_text: str = "") -> list[Hit]:
    """释义向量相似（补充通道）。没有释义时返回空。"""
    if not (meaning or "").strip():
        return []
    col = db.collection("marks_meaning")
    n = col.count()
    if n == 0:
        return []
    emb = get_embedder(db.get_meta("embed_backend"))
    res = col.query(query_embeddings=emb.embed([meaning]), n_results=min(60, n))
    in_pool = {m["mark_id"]: m for m in pool(classes, data_scope)}
    q = phonetic.normalize(exclude_text)
    hits = []
    for mark_id, dist, doc in zip(res["ids"][0], res["distances"][0], res["documents"][0]):
        sim = 1.0 - dist
        m = in_pool.get(mark_id)
        if m is None or sim < settings.meaning_threshold or m["norm_text"] == q:
            continue
        hits.append(Hit(mark_id=mark_id, channel="meaning", kind="meaning", score=sim,
                        evidence=f"含义相近（对方释义：{doc}）"))
    return _ranked(hits, top_k or settings.top_k_per_channel)


def compare(query: str, text: str) -> list[Hit]:
    """两两比较一个待查商标和一个在先商标，返回文字类通道的命中（不含义近通道）。评测用。"""
    rec = {"mark_id": "X", "text": text, "norm_text": phonetic.normalize(text), "meaning": "", **phonetic.keys(text)}
    hits: list[Hit] = []
    for fn in (recall_exact, recall_glyph, recall_pinyin, recall_variant):
        hits += fn(query, set(), candidates=[rec])
    return hits
