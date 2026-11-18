"""对照评测：判断“标识是否近似”，比较三种方式与官方结论的一致程度。

1. 规则：规则引擎的标识相似程度（与 eval/run_eval.py 相同）
2. 大模型（无 RAG）：同一提示词，不给指南条目和判例
3. 大模型 + RAG：给检索到的指南条目和判例
为避免看到答案：评测决定书的商标对时，排除该文书本身的判例；评测指南例子时，排除该例子所在的指南条目。
需要配置真实大模型。用法：
    python eval/run_judge_eval.py            # 指南例子 + 调参集
    python eval/run_judge_eval.py --frozen   # 冻结测试集（只出汇总）
"""
from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "eval"))

import run_eval  # noqa: E402
from app import llm  # noqa: E402
from app.rules.risk_table import LEVEL_LABEL, mark_similarity  # noqa: E402
from app.tools import rag  # noqa: E402
from app.tools.search import compare  # noqa: E402


def ask(r: dict, use_rag: bool) -> str | None:
    hits = compare(r["query"], r["cited"])
    rule = mark_similarity(hits) if hits else "low"
    evidence = "\n".join(f"- {h.evidence}" for h in hits) or "- 文字类通道没有命中"
    q = f"待查商标“{r['query']}”与在先商标“{r['cited']}”：" + evidence.replace("\n", "；")
    guides = rag.retrieve_guides(q, 4, exclude={r.get("source")} if r.get("source") else None) if use_rag else []
    cases = rag.retrieve_cases(q, 4, exclude={r.get("doc_no")} if r.get("doc_no") else None) if use_rag else []
    out = llm.chat_json("p2_judge", {
        "scenario": "申请前筛查", "eval_date": "2026-11-18", "query_mark": r["query"], "query_meaning": "未提供",
        "goods": "（评测只判断标识是否近似，不涉及商品和在先状态）", "mark_text": r["cited"], "evidence": evidence,
        "rule_mark_sim": LEVEL_LABEL[rule], "marks": "（评测只判断标识，无需逐件给出风险，marks 可为空）",
        "guides": "\n".join(f"[{g['id']}] {g['text'][:300]}" for g in guides) or "（无）",
        "cases": "\n".join(f"[{c['case_id']}] {c['text'][:200]}" for c in cases) or "（无）",
    })
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
        no_rag = list(pool.map(lambda r: ask(r, False), rows))
        with_rag = list(pool.map(lambda r: ask(r, True), rows))
    for r, a, b in zip(rows, no_rag, with_rag):
        r["llm"], r["llm_rag"] = a, b
    res = {k: score(rows, k) for k in ("rule", "llm", "llm_rag")}
    print(f"\n=== {name}（{len(rows)} 对：近似 {sum(r['label'] == '近似' for r in rows)}、不近似 {sum(r['label'] == '不近似' for r in rows)}）===")
    label = {"rule": "规则", "llm": "大模型（无 RAG）", "llm_rag": "大模型 + RAG"}
    for k, s in res.items():
        print(f"  {label[k]:<12} 一致率 {s['一致率']}　召回率 {s['召回率']}　近似判高 {s['近似判高']}　"
              f"反例判对 {s['反例判对']}　反例判高 {s['反例判高']}　（未返回 {s['未返回']}）")
    if details:
        for r in rows:
            if r["llm_rag"] and (r["llm_rag"] in ("high", "medium")) != (r["label"] == "近似"):
                print(f"   不一致：{r['query']} / {r['cited']}  官方 {r['label']}  规则 {r['rule']}  模型 {r['llm']}  模型+RAG {r['llm_rag']}")
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--frozen", action="store_true")
    ap.add_argument("--json")
    args = ap.parse_args()
    if not llm.available():
        print("需要配置真实大模型（.env 的 LLM_API_KEY、LLM_MODEL）")
        return 1
    out = {}
    if args.frozen:
        out["frozen"] = run("冻结测试集", run_eval.load("frozen"), details=False)
    else:
        out["guide"] = run("指南官方例子", run_eval.load("guide"), details=True)
        out["tune"] = run("调参集", run_eval.load("tune"), details=True)
    if args.json:
        Path(args.json).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
