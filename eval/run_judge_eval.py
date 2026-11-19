"""对照评测：判断“标识是否近似”，比较三种方式与官方结论的一致程度。

1. 规则：规则引擎的标识相似程度（与 eval/run_eval.py 相同）
2. 大模型（无判例）：产品里的判定提示词，不给判例
3. 大模型 + 同类判例：再给同一比对情形的官方判例（app/tools/cases.py 的 for_pair，与报告里展示的相同）
为避免看到答案：排除该文书本身，以及两边文字完全相同的商标对；判例库只用调参集一侧（冻结测试集的文书不在库里）。
需要配置真实大模型。用法：
    python eval/run_judge_eval.py            # 指南例子 + 调参集
    python eval/run_judge_eval.py --frozen   # 冻结测试集（只出汇总）
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "eval"))

import run_eval  # noqa: E402
from app import llm  # noqa: E402
from app.rules.risk_table import LEVEL_LABEL, mark_similarity  # noqa: E402
from app.tools import cases as case_lib  # noqa: E402
from app.tools.search import compare  # noqa: E402


ERRORS: Counter = Counter()


def ask(r: dict, use_cases: bool) -> str | None:
    hits = compare(r["query"], r["cited"])
    rule = mark_similarity(hits) if hits else "low"
    evidence = "\n".join(f"- {h.evidence}" for h in hits) or "- 文字类通道没有命中"
    pc = case_lib.for_pair(r["query"], r["cited"], exclude_docs={r["doc_no"]} if r.get("doc_no") else None)
    r.setdefault("pattern", pc["pattern"])
    r["n_cases"] = len(pc["similar"]) + len(pc["dissimilar"])
    out = llm.chat_json("p2_judge", {
        "scenario": "申请前筛查", "eval_date": "2026-11-19", "query_mark": r["query"], "query_meaning": "未提供",
        "goods": "（评测只判断标识是否近似，不涉及商品和在先状态）", "mark_text": r["cited"], "evidence": evidence,
        "rule_mark_sim": LEVEL_LABEL[rule], "marks": "（评测只判断标识，无需逐件给出风险，marks 可为空）",
        "cases": case_lib.prompt_text(pc) if use_cases else "（无）",
    })
    if not out:
        ERRORS[(llm.last_error or "未知")[:80]] += 1
    return out.get("mark_sim") if out and out.get("mark_sim") in ("high", "medium", "low") else None


def score(rows: list[dict], key: str) -> dict:
    judged = [r for r in rows if r.get(key)]
    out = {"n": len(judged), "未返回": len(rows) - len(judged)}
    pos = [r for r in judged if r["label"] == "近似"]
    neg = [r for r in judged if r["label"] == "不近似"]
    out["召回率"] = round(sum(r[key] in ("high", "medium") for r in pos) / len(pos), 3) if pos else None
    out["近似判高"] = round(sum(r[key] == "high" for r in pos) / len(pos), 3) if pos else None
    out["反例判对"] = round(sum(r[key] == "low" for r in neg) / len(neg), 3) if neg else None
    out["反例判高"] = round(sum(r[key] == "high" for r in neg) / len(neg), 3) if neg else None
    # 二分类一致率：官方近似 ↔ 判高或中；官方不近似 ↔ 判低
    ok = sum((r[key] in ("high", "medium")) == (r["label"] == "近似") for r in judged)
    out["一致率"] = round(ok / len(judged), 3) if judged else None
    return out


def run(name: str, rows: list[dict], details: bool) -> dict:
    for r in rows:
        hits = compare(r["query"], r["cited"])
        r["rule"] = mark_similarity(hits) if hits else "low"
    with ThreadPoolExecutor(max_workers=5) as pool:
        no_cases = list(pool.map(lambda r: ask(r, False), rows))
        with_cases = list(pool.map(lambda r: ask(r, True), rows))
    for r, a, b in zip(rows, no_cases, with_cases):
        r["llm"], r["llm_cases"] = a, b
    res = {k: score(rows, k) for k in ("rule", "llm", "llm_cases")}
    with_any = [r for r in rows if r["n_cases"]]
    res["有判例的子集"] = {k: score(with_any, k) for k in ("llm", "llm_cases")}
    print(f"\n=== {name}（{len(rows)} 对：近似 {sum(r['label'] == '近似' for r in rows)}、不近似 {sum(r['label'] == '不近似' for r in rows)}）===")
    label = {"rule": "规则", "llm": "大模型（无判例）", "llm_cases": "大模型 + 同类判例"}
    for k, s in [(k, v) for k, v in res.items() if k in label]:
        print(f"  {label[k]:<12} 一致率 {s['一致率']}　召回率 {s['召回率']}　近似判高 {s['近似判高']}　"
              f"反例判对 {s['反例判对']}　反例判高 {s['反例判高']}　（未返回 {s['未返回']}）")
    sub = res["有判例的子集"]
    print(f"  其中给出了判例的 {len(with_any)} 对：无判例 一致率 {sub['llm']['一致率']}，有判例 一致率 {sub['llm_cases']['一致率']}"
          f"（反例判对 {sub['llm']['反例判对']} → {sub['llm_cases']['反例判对']}）")
    if details:
        for r in rows:
            a, b = r["llm"], r["llm_cases"]
            if a and b and ((a in ("high", "medium")) != (b in ("high", "medium"))):
                fixed = (b in ("high", "medium")) == (r["label"] == "近似")
                print(f"   {'改对' if fixed else '改错'}：{r['query']} / {r['cited']}  官方 {r['label']}  情形 {r['pattern']}"
                      f"  规则 {r['rule']}  无判例 {a}  有判例 {b}")
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--frozen", action="store_true")
    ap.add_argument("--json")
    args = ap.parse_args()
    if not llm.available():
        print("需要配置真实大模型（.env 的 LLM_API_KEY、LLM_MODEL）")
        return 1
    from app.config import settings
    settings.llm_timeout, settings.llm_retries = 60.0, 2   # 评测不赶时间；API 慢时 20 秒会成批超时
    out = {}
    if args.frozen:
        out["frozen"] = run("冻结测试集", run_eval.load("frozen"), details=False)
    else:
        out["guide"] = run("指南官方例子", run_eval.load("guide"), details=True)
        out["tune"] = run("调参集", run_eval.load("tune"), details=True)
    if ERRORS:
        print("调用失败：", dict(ERRORS))
    if args.json:
        Path(args.json).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
