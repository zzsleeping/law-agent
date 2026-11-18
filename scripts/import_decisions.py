"""把 collected/decisions 里的决定书导入正式数据：真实商标记录 + 典型案例库。

产出：
- data/raw/real/decision_marks.json  真实商标记录（申请商标与引证商标），只收有中文文字且有商品信息的
- data/cases.json                    典型案例摘要，只取调参集一侧的文书，冻结测试集的文书不进入系统

不做推断：申请日、状态、商品照录决定书；没有就留空。商品名称与区分表规范名称完全一致的才填编号，
否则编号留空（系统会判“待核实”）。状态采集日用决定日期，因为记录反映的是决定作出时的情况。

用法：python scripts/import_decisions.py   （之后运行 python scripts/build_db.py 重新建库）
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "collected" / "decisions"
HAN = re.compile(r"[一-鿿]")


def goods_index() -> dict[tuple[int, str], str]:
    wb = openpyxl.load_workbook(ROOT / "data" / "goods" / "goods_items.xlsx", data_only=True)
    out = {}
    for r in list(wb["商品项库"].iter_rows(values_only=True))[1:]:
        if r[0]:
            out.setdefault((int(r[2]), str(r[1]).replace("*", "").strip()), str(r[0]))
    return out


def map_goods(goods, index) -> list[dict]:
    out = []
    for g in goods or []:
        name, cls = str(g.get("name") or "").strip(), g.get("nice_class")
        if not name or not isinstance(cls, int):
            continue
        code = index.get((cls, name.replace("*", "").strip()))
        out.append({"name": name, "code": code, "nice_class": cls, "grp": g.get("group")})
    return out


def tune_apps() -> set[str]:
    path = ROOT / "eval" / "tune_pairs.jsonl"
    if not path.exists():
        return set()
    return {json.loads(line)["app_no"] for line in path.read_text(encoding="utf-8").splitlines() if line.strip()}


def main() -> int:
    index = goods_index()
    tune = tune_apps()
    marks: dict[str, dict] = {}
    cases = []
    for f in sorted(SRC.glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        am = d["applicant_mark"]
        ref = f"{d['doc_no']}（{d['source_url']}）"

        def add(mark_id, text, owner, app_date, priority, status, goods):
            if not mark_id or not text or not HAN.search(text):
                return
            g = map_goods(goods, index)
            if not g:
                return
            rec = marks.setdefault(mark_id, {
                "mark_id": mark_id, "text": text, "meaning": None, "owner": owner or "",
                "app_date": app_date, "priority_date": priority, "reg_date": None, "status": status,
                "invalid_date": None, "invalid_reason": None, "snapshot_date": d["decision_date"],
                "source": "商标驳回复审文书（公开全文）", "source_ref": ref, "goods": []})
            known = {(x["name"], x["nice_class"]) for x in rec["goods"]}
            rec["goods"] += [x for x in g if (x["name"], x["nice_class"]) not in known]

        add(am.get("app_no"), am.get("text"), am.get("owner"), am.get("app_date"), am.get("priority_date"),
            None, am.get("goods"))                       # 申请商标的现状决定书里没有，不推断
        for c in d["cited_marks"]:
            add(c.get("reg_no"), c.get("text"), c.get("owner"), c.get("app_date"), None, c.get("status"), c.get("goods"))

        # 全部文书进案例库，用 split 区分调参集 / 冻结测试集；评测和 RAG 判例库只用调参集一侧
        cases.append({
            "case_id": d["doc_no"], "split": "tune" if am.get("app_no") in tune else "frozen",
            "doc_type": d["doc_type"], "decision_date": d["decision_date"],
            "source_url": d["source_url"], "applicant_mark": am["text"], "outcome": d["outcome"],
            "outcome_scope": d.get("outcome_scope"),
            "cited": [{"text": c.get("text"), "reg_no": c.get("reg_no"), "mark_similar": c.get("mark_similar"),
                       "goods_similar": c.get("goods_similar"), "excerpt": c.get("reasoning_excerpt")}
                      for c in d["cited_marks"] if c.get("mark_similar") in ("近似", "不近似")],
        })
    out = ROOT / "data" / "raw" / "real" / "decision_marks.json"
    out.write_text(json.dumps(list(marks.values()), ensure_ascii=False, indent=1), encoding="utf-8")
    (ROOT / "data" / "cases.json").write_text(json.dumps(cases, ensure_ascii=False, indent=1), encoding="utf-8")
    n_goods = sum(len(m["goods"]) for m in marks.values())
    n_code = sum(1 for m in marks.values() for g in m["goods"] if g["code"])
    print(f"真实商标记录 {len(marks)} 条（核定或指定商品 {n_goods} 项，其中 {n_code} 项对应到区分表编号）→ {out}")
    n_tune = sum(1 for c in cases if c["split"] == "tune")
    print(f"典型案例 {len(cases)} 份（调参集 {n_tune}、冻结测试集 {len(cases) - n_tune}）→ data/cases.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
