"""标识近似评测：用官方结论检验系统的“标识相似程度”判断。

只评标识，不评商品和在先状态（决定书大多缺商品明细和申请日）；也不含义近通道（决定书没有释义）。

用法：
    python eval/run_eval.py                 # 指南例子 + 调参集，并列出判错的商标对
    python eval/run_eval.py --frozen        # 冻结测试集，只输出汇总数字，不列具体商标对
    python eval/run_eval.py --json out.json # 另存结果

判定口径：
- 官方“近似”：系统判“高”记为一致；判“中”记为偏轻；判“低”或没召回记为漏判
- 官方“不近似”：系统判“低”或没召回记为一致；判“中”记为偏重；判“高”记为误判
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.rules.risk_table import mark_similarity  # noqa: E402
from app.tools.search import compare  # noqa: E402

OUTCOME = {
    ("近似", "high"): "一致", ("近似", "medium"): "偏轻", ("近似", "low"): "漏判", ("近似", None): "漏判",
    ("不近似", None): "一致", ("不近似", "low"): "一致", ("不近似", "medium"): "偏重", ("不近似", "high"): "误判",
}


def load(name: str) -> list[dict]:
    path = ROOT / "eval" / f"{name}_pairs.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def judge(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        hits = compare(r["query"], r["cited"])
        level = mark_similarity(hits) if hits else None
        out.append({**r, "level": level, "kinds": sorted({h.kind for h in hits}),
                    "outcome": OUTCOME[(r["label"], level)]})
    return out


def summary(rows: list[dict]) -> dict:
    res = {}
    for label in ("近似", "不近似"):
        sub = [r for r in rows if r["label"] == label]
        c = Counter(r["outcome"] for r in sub)
        res[label] = {"n": len(sub), **{k: c.get(k, 0) for k in ("一致", "偏轻", "漏判", "偏重", "误判")}}
    pos, neg = res["近似"], res["不近似"]
    res["召回率"] = round((pos["一致"] + pos["偏轻"]) / pos["n"], 3) if pos["n"] else None      # 近似对被判中或高
    res["高风险命中率"] = round(pos["一致"] / pos["n"], 3) if pos["n"] else None               # 近似对被判高
    res["反例正确率"] = round(neg["一致"] / neg["n"], 3) if neg["n"] else None                 # 不近似对判低或不召回
    res["反例误判高"] = round(neg["误判"] / neg["n"], 3) if neg["n"] else None
    return res


def show(name: str, rows: list[dict], details: bool) -> dict:
    groups = {"全部": rows, "纯中文": [r for r in rows if not r.get("composite")]}
    result = {}
    print(f"\n=== {name} ===")
    for gname, sub in groups.items():
        s = summary(sub)
        result[gname] = s
        p, n = s["近似"], s["不近似"]
        print(f"[{gname}] 近似 {p['n']} 对：判高 {p['一致']}、判中 {p['偏轻']}、漏判 {p['漏判']}｜"
              f"不近似 {n['n']} 对：判低或未召回 {n['一致']}、判中 {n['偏重']}、判高 {n['误判']}")
        print(f"         召回率 {s['召回率']}　高风险命中率 {s['高风险命中率']}　"
              f"反例正确率 {s['反例正确率']}　反例误判高 {s['反例误判高']}")
    if details:
        bad = [r for r in rows if r["outcome"] != "一致"]
        if bad:
            print("  不一致的商标对：")
        for r in bad:
            print(f"   {r['outcome']:<2} {r['query']} / {r['cited']}  官方:{r['label']}  系统:{r['level'] or '未召回'} {r['kinds']}")
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--frozen", action="store_true", help="评冻结测试集（只出汇总）")
    ap.add_argument("--json", help="结果另存为 JSON")
    args = ap.parse_args()
    out = {}
    if args.frozen:
        out["frozen"] = show("冻结测试集", judge(load("frozen")), details=False)
    else:
        out["guide"] = show("指南官方例子", judge(load("guide")), details=True)
        out["tune"] = show("调参集（决定书）", judge(load("tune")), details=True)
    if args.json:
        Path(args.json).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
