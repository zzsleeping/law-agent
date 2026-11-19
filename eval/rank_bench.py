"""召回排序调参台（只用调参集）：缓存候选池，之后每次只重跑文字召回规则和 merge 的名称组排序，几秒出结果。

完整流程（run_recall.py）要跑评估、读商品档案，63 份文书要一个多小时；排序只依赖召回命中，
所以这里只调用 app/tools/search.py 的四路文字召回和 app/nodes/merge.py 的 group_order，改了代码直接重跑本脚本即可。
不含义近通道（需要释义向量，且命中很少）；结果与完整流程的 Recall@10 口径相同（按名称组、去掉申请商标本身）。

用法：
    python eval/rank_bench.py            # 第一次会建缓存（几分钟），之后直接评测
    python eval/rank_bench.py --rebuild  # 候选生成改了以后重建缓存
    python eval/rank_bench.py --misses   # 列出没进前 10 组的引证
"""
from __future__ import annotations

import argparse
import pickle
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "eval"))

import run_recall as rr  # noqa: E402

from app.config import settings  # noqa: E402
from app.nodes import merge as mg  # noqa: E402
from app.rules.goods_relation import linked_classes  # noqa: E402
from app.rules.risk_table import mark_similarity  # noqa: E402
from app.runner import items_by_code  # noqa: E402
from app.tools import phonetic, search  # noqa: E402

CACHE = ROOT / "eval" / ".rank_cache.pkl"
CHANNELS = (search.recall_exact, search.recall_glyph, search.recall_pinyin, search.recall_variant)


def build_cache() -> list[dict]:
    rows = []
    for d in rr.docs_for("tune"):
        am = d["applicant_mark"]
        codes = rr.applicant_codes(am)
        targets = [str(c["reg_no"]) for c in d["cited_marks"] if c.get("mark_similar") == "近似" and c.get("reg_no")]
        if not codes or not targets:
            continue
        classes = sorted(linked_classes(items_by_code(codes)))
        q = phonetic.normalize(am["text"])
        t = time.time()
        pool = search.candidate_pool(am["text"], classes, "real", tuple(search.query_segments(am["text"])))
        rows.append({"doc": d["doc_no"], "text": am["text"], "q": q, "own": str(am.get("app_no")),
                     "classes": classes, "targets": targets, "pool": pool,
                     "cited": {str(c["reg_no"]): c.get("text") for c in d["cited_marks"] if c.get("reg_no")}})
        print(f"  {len(rows):>3} {am['text']}  候选 {len(pool)}  {time.time() - t:.1f}s", flush=True)
    CACHE.write_bytes(pickle.dumps(rows))
    return rows


def rank_doc(row: dict) -> tuple[list[str], dict]:
    pool = row["pool"]
    group = {c["mark_id"]: c.get("group") or c["norm_text"] for c in pool}
    hits = []
    for fn in CHANNELS:
        hits += [h.model_copy(update={"group": group.get(h.mark_id, "")})
                 for h in search.recall_with_segments(fn, row["text"], row["classes"], "real", pool)]
    order, groups = mg.group_order(hits, row["text"])
    own = row["own"]
    order = [g for g in order if any(h.mark_id.rpartition("/")[0] != own for h in groups[g])]
    return order, groups


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rebuild", action="store_true")
    ap.add_argument("--misses", action="store_true")
    a = ap.parse_args()
    rows = build_cache() if a.rebuild or not CACHE.exists() else pickle.loads(CACHE.read_bytes())
    old = settings.top_n_assess
    settings.top_n_assess = 100000                       # 看完整排序；前 10 / 前 15 由下面统计
    buckets, misses, docs_any, t0 = Counter(), [], 0, time.time()
    try:
        for row in rows:
            order, groups = rank_doc(row)
            rank = {}
            for gi, g in enumerate(order):
                for h in groups[g]:
                    rank.setdefault(h.mark_id.rpartition("/")[0], (gi, g, mark_similarity(groups[g])))
            hit_any = False
            for reg in row["targets"]:
                r = rank.get(reg)
                gi = r[0] if r else None
                b = ("未召回" if gi is None else "前10" if gi < 10 else "11-15" if gi < 15
                     else "16-30" if gi < 30 else "31-100" if gi < 100 else ">100")
                buckets[b] += 1
                hit_any |= gi is not None and gi < 10
                if gi is None or gi >= 10:
                    misses.append((row["text"], row["cited"].get(reg), gi, r[2] if r else "", len(order)))
            docs_any += hit_any
    finally:
        settings.top_n_assess = old
    total = sum(buckets.values())
    print(f"调参集引证 {total} 件，文书 {len(rows)} 份，{time.time() - t0:.0f} 秒")
    for b in ("前10", "11-15", "16-30", "31-100", ">100", "未召回"):
        print(f"  {b:<6}{buckets[b]:>5}  {buckets[b] / total:.0%}")
    print(f"Recall@10 = {buckets['前10'] / total:.1%}；前 15 组 = {(buckets['前10'] + buckets['11-15']) / total:.1%}；"
          f"至少一件进前 10 的文书 {docs_any}/{len(rows)}")
    if a.misses:
        for q, t, gi, lv, n in sorted(misses, key=lambda m: (m[2] is None, m[2] or 0)):
            print(f"   {q} / {t}  名次 {gi + 1 if gi is not None else '—'}  {lv}  共 {n} 组")
    return 0


if __name__ == "__main__":
    sys.exit(main())
