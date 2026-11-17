"""从决定书和指南官方例子生成评测用的商标对。

产出（都在 eval/ 下）：
- guide_pairs.jsonl   指南 5.5.1 节的中文官方例子，调参用（已公开看过，不能用来报告指标）
- tune_pairs.jsonl    决定书商标对，调参集，可以随便看
- frozen_pairs.jsonl  决定书商标对，冻结测试集，只用来报告指标，不看内容、不据此调参

划分规则：按申请商标（一份文书）整体划分，同一份文书的商标对不会同时出现在两边；
含“不近似”标签的文书和其余文书分别按申请号哈希排序后交替分配，保证两边都有反例。
只收“近似 / 不近似”，“未认定”不收。文字清洗：去掉“及图”，只保留汉字。

用法：python scripts/build_eval_sets.py
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "collected" / "decisions"
OUT = ROOT / "eval"
HAN = re.compile(r"[一-鿿]")

# 《商标审查审理指南》5.5.1 节给出结论的中文例子（条目见 data/basis/guide_rules.json 的 examples 字段）
GUIDE = [
    ("坤星文具", "星坤", "近似", "GUIDE2021-5.5.1.2"), ("亚美航空", "美亚医疗", "不近似", "GUIDE2021-5.5.1.2"),
    ("星星", "星", "近似", "GUIDE2021-5.5.1.3"), ("哈罗哈罗", "哈罗", "近似", "GUIDE2021-5.5.1.3"),
    ("蕙特曼", "惠特曼", "近似", "GUIDE2021-5.5.1.4"), ("好歌", "好哥", "不近似", "GUIDE2021-5.5.1.4"),
    ("玫瑰花", "玫瑰", "近似", "GUIDE2021-5.5.1.6"), ("心之必达", "心至必达", "近似", "GUIDE2021-5.5.1.7"),
    ("北欧风情", "北美风情", "不近似", "GUIDE2021-5.5.1.7"), ("乐曼啤酒", "乐曼", "近似", "GUIDE2021-5.5.1.12"),
    ("老龙潭山泉", "老龙潭", "近似", "GUIDE2021-5.5.1.12"), ("汇源一桶", "汇源", "近似", "GUIDE2021-5.5.1.12"),
    ("云趣店", "云趣", "近似", "GUIDE2021-5.5.1.13"), ("大洋房", "大洋", "不近似", "GUIDE2021-5.5.1.13"),
    ("新吉澳", "吉澳", "近似", "GUIDE2021-5.5.1.14"), ("球王", "球", "不近似", "GUIDE2021-5.5.1.14"),
    ("华为海思", "华为", "近似", "GUIDE2021-5.5.1.16"),
]


def clean(text: str) -> str:
    return "".join(HAN.findall((text or "").replace("及图", "")))


def composite(text: str) -> bool:
    """是否组合商标：带图形、外文、数字或多段文字。"""
    t = text or ""
    return "及图" in t or bool(re.search(r"[A-Za-z0-9]", t)) or bool(re.search(r"\s", t.strip()))


def key(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


def write(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def main() -> int:
    OUT.mkdir(exist_ok=True)
    write(OUT / "guide_pairs.jsonl", [
        {"id": f"guide-{i:02d}", "query": q, "cited": c, "label": lab, "source": src, "composite": False}
        for i, (q, c, lab, src) in enumerate(GUIDE, 1)])

    docs = []
    for f in sorted(SRC.glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        am = d["applicant_mark"]
        pairs = []
        for c in d["cited_marks"]:
            if c.get("mark_similar") not in ("近似", "不近似"):
                continue
            q, t = clean(am["text"]), clean(c.get("text") or "")
            if not q or not t:
                continue
            pairs.append({
                "query": q, "cited": t, "label": c["mark_similar"], "goods_similar": c.get("goods_similar"),
                "query_raw": am["text"], "cited_raw": c.get("text"),
                "composite": composite(am["text"]) or composite(c.get("text") or ""),
                "doc_no": d["doc_no"], "app_no": am.get("app_no"), "cited_reg_no": c.get("reg_no"),
                "source_url": d["source_url"], "excerpt": c.get("reasoning_excerpt"),
            })
        if pairs:
            docs.append((am.get("app_no") or d["doc_no"], pairs))

    # 同一文书内按清洗后的商标对去重；同一对标签冲突的整对丢弃
    dropped_conflict = 0
    for i, (app, pairs) in enumerate(docs):
        seen: dict[tuple, dict] = {}
        conflict = set()
        for p in pairs:
            k = (p["query"], p["cited"])
            if k in seen and seen[k]["label"] != p["label"]:
                conflict.add(k)
            seen.setdefault(k, p)
        dropped_conflict += len(conflict)
        docs[i] = (app, [p for k, p in seen.items() if k not in conflict])

    with_neg = sorted((d for d in docs if any(p["label"] == "不近似" for p in d[1])), key=lambda d: key(d[0]))
    others = sorted((d for d in docs if d not in with_neg), key=lambda d: key(d[0]))
    tune, frozen = [], []
    for group in (with_neg, others):
        for j, (app, pairs) in enumerate(group):
            (tune if j % 2 == 0 else frozen).extend(pairs)
    for name, rows in (("tune", tune), ("frozen", frozen)):
        for n, r in enumerate(rows, 1):
            r["id"] = f"{name}-{n:03d}"
        write(OUT / f"{name}_pairs.jsonl", rows)

    def stat(rows):
        c = Counter(r["label"] for r in rows)
        return (f"{len(rows)} 对（近似 {c['近似']}、不近似 {c['不近似']}；纯中文 {sum(1 for r in rows if not r['composite'])} 对），"
                f"来自 {len({r['app_no'] for r in rows})} 个申请商标")
    print(f"指南例子：{len(GUIDE)} 对")
    print(f"调参集：{stat(tune)}")
    print(f"冻结测试集：{stat(frozen)}")
    print(f"同一对标签冲突而丢弃：{dropped_conflict} 对")
    return 0


if __name__ == "__main__":
    sys.exit(main())
