"""RAG 知识库：法条、审查指南（以及判例）的向量检索。

用途（2026-11-18 调整）：
- 写结论时检索相关法条和指南条目，作为映射表之外的补充依据（retrieve_basis，限定在 BASIS_SCOPE 内）；
- 报告页的法律问答（app/qa.py）检索全部法条和指南。
大模型判定不再使用 RAG（对照评测显示按字面检索到的判例会把模型带偏）；判例库保留，供以后按比对情形检索时使用。

三个集合（建库时由 build_kb 生成，向量模型与商品项映射相同）：
- guide_kb  《商标审查审理指南》条目，每条一段：标题、正文、官方例子；元数据含适用维度
- case_kb   判例：每件“申请商标—引证商标”的官方认定一段；只收调参集一侧的文书（data/cases.json），
            冻结测试集的文书不进库，保证评测公平
- law_kb    法条：每条一段；元数据含施行起止日（YYYYMMDD 整数），检索时按评估日期过滤版本

检索结果只作为参考材料交给模型；模型引用的依据仍要经过引用校验。
"""
from __future__ import annotations

import json
from datetime import date

from app import db
from app.config import settings
from app.embed import get_embedder


def _d2i(v) -> int:
    return int(str(v).replace("-", "")) if v else 99991231


def build_kb(emb) -> dict:
    """建三个知识库集合，返回各自条数。"""
    with db.connect() as c:
        rows = [dict(r) for r in c.execute("SELECT * FROM basis")]
    guides = [r for r in rows if r["basis_id"].startswith("GUIDE")]
    laws = [r for r in rows if not r["basis_id"].startswith("GUIDE")]
    raw_guides = {g["id"]: g for g in json.loads((settings.data_dir / "basis" / "guide_rules.json").read_text(encoding="utf-8"))}

    docs = []
    for g in guides:
        ex = raw_guides.get(g["basis_id"], {}).get("examples") or ""
        docs.append((g["basis_id"], f"{g['title']}\n{g['text']}" + (f"\n例子：{ex}" if ex else ""),
                     {"basis_id": g["basis_id"], "dims": g["dimension"] or "[]"}))
    if docs:
        col = db.collection("guide_kb")
        col.add(ids=[d[0] for d in docs], documents=[d[1] for d in docs],
                embeddings=emb.embed([d[1] for d in docs]), metadatas=[d[2] for d in docs])

    law_docs = [(r["basis_id"], f"{r['doc']}（{r['version']}）{r['article']}：{r['text']}",
                 {"basis_id": r["basis_id"], "from": _d2i(r["effective_from"]), "to": _d2i(r["effective_to"])})
                for r in laws]
    if law_docs:
        col = db.collection("law_kb")
        for i in range(0, len(law_docs), 200):
            part = law_docs[i:i + 200]
            col.add(ids=[d[0] for d in part], documents=[d[1] for d in part],
                    embeddings=emb.embed([d[1] for d in part]), metadatas=[d[2] for d in part])

    case_docs = []
    try:
        cases = json.loads((settings.data_dir / "cases.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        cases = []
    for case in cases:
        if case.get("split", "tune") != "tune":          # 冻结测试集的文书不进 RAG 判例库
            continue
        for j, c in enumerate(case.get("cited", [])):
            if c.get("mark_similar") not in ("近似", "不近似") or not c.get("text"):
                continue
            text = (f"申请商标“{case['applicant_mark']}”与引证商标“{c['text']}”：官方认定{c['mark_similar']}。"
                    + (f"认定：{c['excerpt']}" if c.get("excerpt") else ""))
            case_docs.append((f"{case['case_id']}#{j}", text,
                              {"case_id": case["case_id"], "label": c["mark_similar"],
                               "applicant": case["applicant_mark"], "cited": c["text"],
                               "doc_type": case.get("doc_type", ""), "decision_date": case.get("decision_date", "")}))
    col = db.collection("case_kb")
    for i in range(0, len(case_docs), 200):
        part = case_docs[i:i + 200]
        col.add(ids=[d[0] for d in part], documents=[d[1] for d in part],
                embeddings=emb.embed([d[1] for d in part]), metadatas=[d[2] for d in part])
    return {"guide_kb": len(docs), "law_kb": len(law_docs), "case_kb": len(case_docs)}


def _query(name: str, text: str, k: int, where: dict | None = None) -> list[dict]:
    try:
        col = db.chroma().get_collection(name)
    except Exception:
        return []
    n = col.count()
    if n == 0 or not text.strip():
        return []
    emb = get_embedder(db.get_meta("embed_backend"))
    res = col.query(query_embeddings=emb.embed([text]), n_results=min(k, n), where=where)
    return [{"id": i, "text": doc, "score": round(1 - dist, 3), **meta}
            for i, doc, dist, meta in zip(res["ids"][0], res["documents"][0], res["distances"][0], res["metadatas"][0])]


def retrieve_guides(text: str, k: int = 4, exclude: set | None = None) -> list[dict]:
    """与一对商标的比对情况最相关的指南条目。exclude：评测时排除的条目编号（避免看到答案）。"""
    rows = _query("guide_kb", text, k + len(exclude or ()))
    return [r for r in rows if r["id"] not in (exclude or set())][:k]


def retrieve_cases(text: str, k: int = 4, exclude: set | None = None) -> list[dict]:
    """文字或认定情形相近的判例（调参集一侧）。exclude：评测时排除的文书编号（避免看到答案）。"""
    rows = _query("case_kb", text, k + 6 * len(exclude or ()))
    return [r for r in rows if r["case_id"] not in (exclude or set())][:k]


# 写结论时可补充的法条范围：与注册审查、近似判断、在先状态、驳回复审有关的条文。
# 驰名商标、优先权、代理、侵权、马德里等条文与本系统的结论无关，不进入补充检索（法律问答仍检索全部法条）。
BASIS_SCOPE = {
    "TML2019": [9, 22, 28, 30, 31, 34, 39, 40, 50],
    "TML2026": [20, 32, 34, 35, 37, 39, 44, 48, 49],
    "TMR-2014": [19, 21, 22, 52],
}
SCOPED_LAW_IDS = [f"{v}-{n}" for v, ns in BASIS_SCOPE.items() for n in ns]


def retrieve_law(text: str, eval_date: date, k: int = 3, ids: list[str] | None = None) -> list[dict]:
    """在评估日期适用的法条中检索；ids 给出时只在这些条文里检索。"""
    d = int(eval_date.strftime("%Y%m%d"))
    cond = [{"from": {"$lte": d}}, {"to": {"$gte": d}}] + ([{"basis_id": {"$in": ids}}] if ids else [])
    return _query("law_kb", text, k, where={"$and": cond})


def retrieve_basis(text: str, eval_date: date, k_law: int = 3, k_guide: int = 2) -> list[dict]:
    """写结论时检索相关依据：评估日期适用、且在 BASIS_SCOPE 内的法条，以及已施行的指南条目。
    返回 [{id, kind, score, text}]。"""
    from app.tools import basis as basis_tool

    out = [{"id": r["id"], "kind": "law", "score": r["score"], "text": r["text"]}
           for r in retrieve_law(text, eval_date, k_law, ids=SCOPED_LAW_IDS)]
    for g in retrieve_guides(text, k_guide + 2):
        b = basis_tool.get_basis(g["id"])
        if b and basis_tool.is_applicable(b, eval_date) and len([x for x in out if x["kind"] == "guide"]) < k_guide:
            out.append({"id": g["id"], "kind": "guide", "score": g["score"], "text": g["text"]})
    return out
