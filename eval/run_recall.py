"""召回评测（方案第十二节 Recall@10）：在正式商标库里查决定书的申请商标，
看官方认定近似的引证商标是否进入展示顺序，以及所在名称组是否排进前 10 组（按名称组统计，2026-11-18 确认）。
另报两个参考数：被召回的比例（任一通道命中），以及按件统计的前 10。

- 只用开放数据（data_scope=real），需要正式商标库可用
- 申请商标本身也在库里，计算名次时去掉它
- 申请商标的商品名称对应不上区分表编号的文书跳过
用法：
    python eval/run_recall.py            # 调参集，列出没进前 10 的引证
    python eval/run_recall.py --frozen   # 冻结测试集，只出汇总
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import llm  # noqa: E402
from app.graph import build_graph  # noqa: E402
from app.library import get_library  # noqa: E402
from app.rules.goods_relation import map_goods_name  # noqa: E402
from app.runner import items_by_code, run_pre_filing  # noqa: E402


def docs_for(split: str) -> list[dict]:
    apps = {json.loads(x)["app_no"] for x in (ROOT / "eval" / f"{split}_pairs.jsonl").read_text(encoding="utf-8").splitlines() if x}
    out = []
    for f in sorted((ROOT / "collected" / "decisions").glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        if d["applicant_mark"].get("app_no") in apps:
            out.append(d)
    return out


def applicant_codes(am: dict) -> list[str]:
    """申请商标的商品：优先取开放数据里该申请号的商品（有群号）；名称对不上编号时，取该群的全部编号来确定检索范围。"""
    from app.rules.goods_relation import tables
    from app.tools import open_source

    t = tables()
    codes: set[str] = set()
    rows = open_source._conn("source").execute(
        "SELECT nice_class, similar_group, item_name FROM goods WHERE mark_id=?", (str(am.get("app_no")),)).fetchall()
    for r in rows:
        c = map_goods_name(r["nice_class"], r["item_name"])
        codes |= {c} if c else set(t["group_codes"].get(r["similar_group"], set()))
    if not codes:
        codes = {c for g in am.get("goods") or [] if isinstance(g.get("nice_class"), int)
                 for c in [map_goods_name(g["nice_class"], g["name"])] if c}
    return sorted(codes)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--frozen", action="store_true")
    args = ap.parse_args()
    if not get_library().available():
        print("正式商标库不可用（检查 TM_OPEN_DB 与 data/open_index.sqlite）")
        return 1
    llm.set_backend(lambda *a: None)                    # 只测召回，不调用模型
    graph = build_graph()
    split = "frozen" if args.frozen else "tune"
    total = in_order = top10 = top10_marks = skipped = recalled = 0
    times, misses = [], []
    for d in docs_for(split):
        am = d["applicant_mark"]
        codes = applicant_codes(am)
        targets = [c for c in d["cited_marks"] if c.get("mark_similar") == "近似" and c.get("reg_no")]
        if not codes or not targets:
            skipped += 1
            continue
        t = time.time()
        v = run_pre_filing(am["text"], goods=items_by_code(codes), eval_date=date.fromisoformat(d["decision_date"]),
                           data_scope="real", graph=graph)
        times.append(time.time() - t)
        own = str(am.get("app_no"))
        order = [m for m in v["display_order"] if m.rpartition("/")[0] != own]
        ids = [m.rpartition("/")[0] for m in order]
        group_rank = {}
        for gi, g in enumerate([g for g in v["display_groups"] if any(m.rpartition("/")[0] != own for m in g["marks"])]):
            for m in g["marks"]:
                group_rank.setdefault(m.rpartition("/")[0], gi)
        recalled_ids = {h.mark_id.rpartition("/")[0] for f in ("hits_exact", "hits_glyph", "hits_pinyin", "hits_variant")
                        for h in v.get(f, [])}
        for c in targets:
            total += 1
            reg = str(c["reg_no"])
            recalled += reg in recalled_ids
            if reg in ids:
                in_order += 1
                top10_marks += ids.index(reg) < 10
                if group_rank.get(reg, 99) < 10:
                    top10 += 1
                    continue
            misses.append((am["text"], c.get("text"), reg, (group_rank[reg] + 1) if reg in group_rank else None))
    print(f"[{'冻结测试集' if args.frozen else '调参集'}] 官方认定近似的引证 {total} 件：被召回 {recalled}（{recalled / max(total, 1):.0%}），"
          f"进入展示顺序 {in_order}（{in_order / max(total, 1):.0%}），所在名称组排进前 10 组 {top10}（Recall@10 = {top10 / max(total, 1):.0%}）；"
          f"参考：按件统计的前 10 为 {top10_marks / max(total, 1):.0%}；"
          f"跳过文书 {skipped} 份；单次耗时中位 {sorted(times)[len(times) // 2] if times else 0:.1f} 秒")
    if not args.frozen:
        for q, t, reg, rank in misses:
            print(f"   未进前 10 组：{q} / {t}（{reg}）组名次 {rank or '未进入展示'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
