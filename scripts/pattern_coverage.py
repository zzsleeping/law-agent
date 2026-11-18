"""按比对情形统计 collected/decisions/ 中的商标对，用于检查任务书 05 的配额是否达到。

用法：
    python scripts/pattern_coverage.py                    # 全部文书
    python scripts/pattern_coverage.py --since 2026-11-19 # 只统计 retrieved_at 在该日期及以后的（本批新增）
    python scripts/pattern_coverage.py --list 字序颠倒     # 列出某一情形的商标对

比对情形由系统的文字比对规则自动判断（app/rules/patterns.py，与报告里检索参考判例用的是同一套），与官方结论无关：
完全相同、完整包含、仅一字不同、字序颠倒、叠字、读音相同/相近、字形相近、共用部分、
共用字但未命中（共用汉字但规则没有识别出情形）、无文字命中（不共用汉字，对评测没有区分作用）。
统计口径：只收“近似 / 不近似”；文字去掉“及图”、只保留汉字；同一份文书里两边文字都相同的商标对只算一次。
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.rules.patterns import PATTERNS, clean  # noqa: E402
from app.rules.patterns import classify as pattern  # noqa: E402


def load(since: str | None) -> list[dict]:
    rows, seen = [], set()
    for f in sorted((ROOT / "collected" / "decisions").glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        if since and str(d.get("retrieved_at") or "") < since:
            continue
        q = clean(d["applicant_mark"]["text"])
        for c in d.get("cited_marks") or []:
            t, lab = clean(c.get("text") or ""), c.get("mark_similar")
            if lab not in ("近似", "不近似") or not q or not t or (d["doc_no"], q, t) in seen:
                continue
            seen.add((d["doc_no"], q, t))
            rows.append({"doc_no": d["doc_no"], "query": q, "cited": t, "label": lab,
                         "excerpt": c.get("reasoning_excerpt") or ""})
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", help="只统计 retrieved_at ≥ 该日期（YYYY-MM-DD）的文书")
    ap.add_argument("--list", help="列出某一比对情形的商标对")
    a = ap.parse_args()
    rows = load(a.since)
    for r in rows:
        r["pattern"] = pattern(r["query"], r["cited"])
    if a.list:
        for r in rows:
            if r["pattern"] == a.list:
                print(f"{r['label']}\t{r['query']} / {r['cited']}\t{r['doc_no']}\t{r['excerpt']}")
        return 0
    pairs, docs = Counter(), defaultdict(set)
    for r in rows:
        pairs[(r["pattern"], r["label"])] += 1
        docs[(r["pattern"], r["label"])].add(r["doc_no"])
    print(f"文书 {len({r['doc_no'] for r in rows})} 份，商标对 {len(rows)} 对"
          + (f"（retrieved_at ≥ {a.since}）" if a.since else ""))
    print(f"{'比对情形':<12}{'近似 对数/文书数':>16}{'不近似 对数/文书数':>18}")
    for p in PATTERNS:
        print(f"{p:<12}" + "".join(f"{pairs[(p, lab)]:>10}/{len(docs[(p, lab)]):<6}" for lab in ("近似", "不近似")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
