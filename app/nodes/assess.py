"""assess：规则表定级（纯代码，不调用模型）；explain：大模型解释（P2），失败则保留代码生成的理由。"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

from app import db, llm
from app.config import settings
from app.rules import goods_relation as gr
from app.rules import groups
from app.rules import prior_status as ps
from app.rules import risk_table as rt
from app.state import AgentState, Assessment, Fact
from app.tools import basis

SCOPE_FACT = "F-SCOPE"


def assess(s: AgentState) -> dict:
    our_date = s.get("our_priority_date") or s.get("our_app_date")
    facts: dict[str, Fact] = {}
    out: list[Assessment] = []
    pairs = []
    hints_goods = gr.history_hints(s.get("goods", []))
    for mark_id in s.get("display_order", []):
        rec = s["records"][mark_id]
        hits = s["hits_by_mark"].get(mark_id, [])
        fact_ids = []

        def add(suffix: str, kind: str, text: str) -> None:
            fid = f"F-{mark_id}-{suffix}"
            facts[fid] = Fact(fact_id=fid, mark_id=mark_id, kind=kind, text=text)
            fact_ids.append(fid)

        for h in hits:
            add(f"hit-{h.kind}", "hit", h.evidence)
        mark_sim = rt.mark_similarity(hits)
        goods_rel, goods_why = gr.goods_relation(s.get("goods", []), rec.goods)
        add("goods", "goods", f"商品关系：{gr.LABEL[goods_rel]}。{goods_why}")
        prior, prior_why = ps.prior_status(rec, our_date, s["eval_date"], basis.applicable_law(s["eval_date"]))
        add("prior", "prior", f"在先状态：{ps.LABEL[prior]}。{prior_why}")
        risk, row = rt.risk_level(prior, goods_rel, mark_sim)
        if risk == "needs_check":
            if prior in ps.NEEDS_CHECK:
                add("gap-prior", "data_gap", f"在先状态待核实（{ps.LABEL[prior]}）：{prior_why}")
            if goods_rel == "pending":
                add("gap-goods", "data_gap", f"商品关系待核实：{goods_why}")
        kinds = [h.kind for h in hits]
        review = s.get("scenario") == "rejection_review"
        needs_basis = risk in ("high", "medium") or (review and risk == "low")   # 复审逐件比对，低风险也要写结论
        basis_ids = basis.basis_for(s["scenario"], s["eval_date"],
                                    prior if prior in ps.GRADED else "valid", kinds) if needs_basis else []
        if needs_basis:
            pairs.append((prior if prior in ps.GRADED else "valid", kinds))
        explanation = (f"{'；'.join(h.evidence for h in hits)}。{goods_why}。{prior_why}。"
                       f"按规则表第 {row} 行评为{rt.RISK_LABEL[risk]}"
                       f"（标识相似程度：{rt.LEVEL_LABEL[mark_sim]}）。")
        if risk == "low" and row == 2:
            explanation += "未考虑驰名商标跨类保护。"
        group = (hits[0].group if hits and hits[0].group else "") or mark_id
        for fid in fact_ids:
            facts[fid] = facts[fid].model_copy(update={"group": group})
        out.append(Assessment(
            mark_id=mark_id, text=rec.text, group=group, mark_sim=mark_sim, goods_rel=goods_rel, prior=prior, risk=risk,
            rule_risk=risk, rule_mark_sim=mark_sim,
            channels=list(dict.fromkeys(h.channel for h in hits)), fact_ids=fact_ids, basis_ids=basis_ids,
            hints=hints_goods, explanation=explanation))

    # 同名多件注册：每组一条“组成”事实，组内各件都可引用
    for gi, (g, members) in enumerate(groups.by_group(out).items(), 1):
        if len(members) < 2:
            continue
        fid = f"F-GRP-{gi}"
        listed = "；".join(f"{a.mark_id}（{rt.RISK_LABEL[a.risk]}，{ps.LABEL[a.prior]}）" for a in members[:12])
        facts[fid] = Fact(fact_id=fid, mark_id=members[0].mark_id, kind="group", group=g,
                          text=f"与“{members[0].text}”同名的注册共 {len(members)} 件：{listed}"
                               + ("等" if len(members) > 12 else ""))
        for a in members:
            a.fact_ids.append(fid)

    cov = db.coverage()
    counts = {r: sum(1 for a in out if a.risk == r) for r in ("high", "medium", "needs_check", "low")}
    real = cov["real"]
    if real.get("source") == "open":
        scope_name = f"国家知识产权局商标开放数据（第 {real['classes']} 类共 {real['count']:,} 件，增量截至 {real['date']}）"
    else:
        scope_name = f"本地真实记录 {real['count']} 条"
    if cov["simulated"]["count"]:
        scope_name += f"，另含测试用仿真记录 {cov['simulated']['count']} 条"
    facts[SCOPE_FACT] = Fact(fact_id=SCOPE_FACT, mark_id=None, kind="scope", text=(
        f"检索范围：第 {'、'.join(str(c) for c in s.get('classes', []))} 类，{scope_name}。"
        f"共召回 {s.get('recalled_total', 0)} 个候选，展示并评级 {len(out)} 个："
        f"高风险 {counts['high']}、中风险 {counts['medium']}、待核实 {counts['needs_check']}、低风险 {counts['low']}。"))

    timings = {}
    if s.get("t_goods_confirmed"):
        timings["rule_stage"] = round(time.time() - s["t_goods_confirmed"], 3)   # 30 秒口径：确认商品项 → 规则风险列表
    return {"assessments": out, "facts": facts,
            "allowed_basis": basis.allowed_basis(s["scenario"], s["eval_date"], pairs),
            "timings": timings,
            "trace": [{"node": "assess", "counts": counts, "rule_stage_seconds": timings.get("rule_stage")}]}


def explain(s: AgentState) -> dict:
    """每个非低风险的名称组只请求一次模型解释（用组内代表件）；并发调用。模型不改等级，只能置 flag_review。"""
    t0 = time.time()
    reps = [groups.representative(ms) for ms in groups.by_group(
        [a for a in s.get("assessments", []) if a.risk != "low"]).values()]
    todo, skipped = reps[: settings.llm_max_groups], reps[settings.llm_max_groups:]   # 按展示顺序，只解释前若干组
    goods = "、".join(g.name for g in s.get("goods", []))

    def one(a: Assessment):
        return llm.chat_json("p2_explain", {
            "query_mark": s["query_mark"], "goods": goods, "mark_text": a.text, "mark_id": a.mark_id,
            "evidence": "\n".join(f"- {s['facts'][f].text}" for f in a.fact_ids if s["facts"][f].kind == "hit"),
            "goods_rel": s["facts"][f"F-{a.mark_id}-goods"].text,
            "prior": s["facts"][f"F-{a.mark_id}-prior"].text,
            "mark_sim": rt.LEVEL_LABEL[a.mark_sim], "risk": rt.RISK_LABEL[a.risk],
            "query_meaning": s.get("query_meaning") or "未提供",
            "mark_meaning": s["records"][a.mark_id].meaning or "未提供",
        }, refresh=bool(s.get("fresh")))

    results = {}
    if todo and llm.available():
        with ThreadPoolExecutor(max_workers=min(5, len(todo))) as pool:
            results = dict(zip((a.mark_id for a in todo), pool.map(one, todo)))
    failed = [a.mark_id for a in todo if not results.get(a.mark_id)]
    updated = []
    for a in s.get("assessments", []):
        r = results.get(a.mark_id)
        if r and r.get("explanation"):
            a = a.model_copy(update={"explanation": str(r["explanation"]), "explanation_source": "llm",
                                     "flag_review": bool(r.get("flag_review"))})
        updated.append(a)
    notes = []
    if skipped:
        notes.append(f"为控制时延和费用，只为前 {len(todo)} 个名称组调用大模型解释，其余 {len(skipped)} 组显示规则生成的理由")
    if failed:
        why = llm.last_error if llm.available() else "未配置 LLM_API_KEY 或 LLM_MODEL"
        notes.append(f"{len(failed)} 个名称组的解释未使用大模型（{why}），显示的是代码生成的理由")
    dt = round(time.time() - t0, 3)
    return {"assessments": updated, "degraded": bool(failed), "degraded_notes": notes,
            "timings": {"explain": dt},
            "trace": [{"node": "explain", "llm_ok": len(todo) - len(failed), "fallback": len(failed),
                       "capped": len(skipped), "seconds": dt}]}
