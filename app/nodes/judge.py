"""judge：大模型判定（Agent 的核心判断）。

每个名称组调用一次模型：交给它文字比对证据、组内各件注册的商品关系与在先状态、规则引擎的参考判断；
模型判断标识是否近似，并给出每件注册的风险等级。
不使用 RAG：2026-11-18 在调参集上对照，大模型不看指南与判例时与官方结论的一致率 0.889，加 RAG 后降到 0.824
（按字面检索到的判例多与比对情形无关）。RAG 改用于写结论时检索法条（见 app/nodes/compose.py）。
之后经过规则护栏（app/rules/guardrails.py）；模型与规则不一致的标出来供人工复核。

超出调用上限（LLM_MAX_GROUPS）或模型失败的组沿用规则引擎的结果，并注明。
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

from app import llm
from app.config import settings
from app.rules import goods_relation as gr
from app.rules import groups
from app.rules import guardrails
from app.rules import prior_status as ps
from app.rules.risk_table import LEVEL_LABEL, RISK_LABEL, risk_level
from app.state import AgentState, Assessment, Fact
from app.tools import basis

LEVELS = ("high", "medium", "low")
RISKS = ("high", "medium", "low", "needs_check")
MAX_MARKS_IN_PROMPT = 12


def _context(s: AgentState, members: list[Assessment]) -> dict:
    rep = groups.representative(members)
    facts = s["facts"]
    evidence = "\n".join(dict.fromkeys(f"- {facts[f].text}" for a in members for f in a.fact_ids
                                       if facts[f].kind == "hit")) or "- 文字类通道没有命中（由检索规划的变体或义近找到）"
    marks = "\n".join(
        f"- {a.mark_id}：{facts[f'F-{a.mark_id}-goods'].text} {facts[f'F-{a.mark_id}-prior'].text}"
        f"（规则参考风险：{RISK_LABEL[a.rule_risk or a.risk]}）" for a in members[:MAX_MARKS_IN_PROMPT])
    return {
        "rep": rep,
        "vars": {
            "scenario": "驳回复审逐项比对" if s.get("scenario") == "rejection_review" else "申请前筛查",
            "eval_date": str(s["eval_date"]), "query_mark": s["query_mark"],
            "query_meaning": s.get("query_meaning") or "未提供",
            "goods": "、".join(g.name for g in s.get("goods", [])),
            "mark_text": rep.text, "evidence": evidence,
            "rule_mark_sim": LEVEL_LABEL[rep.rule_mark_sim or rep.mark_sim],
            "marks": marks,
            "marks_json": [{"mark_id": a.mark_id, "rule_risk": a.rule_risk or a.risk} for a in members],
            "rule_mark_sim_code": rep.rule_mark_sim or rep.mark_sim,
        },
    }


def _apply(s: AgentState, members: list[Assessment], ctx: dict, out: dict) -> tuple[list[Assessment], Fact, int]:
    """把模型结果落到组内各件注册上，经过护栏。返回 (更新后的评估, 判定事实, 护栏修正次数)。"""
    sim = out.get("mark_sim") if out.get("mark_sim") in LEVELS else (ctx["rep"].rule_mark_sim or ctx["rep"].mark_sim)
    by_id = {m.get("mark_id"): m.get("risk") for m in out.get("marks") or [] if isinstance(m, dict)}
    reason = str(out.get("reason") or "")
    rep = ctx["rep"]
    fid = f"F-{rep.mark_id}-judge"
    fact = Fact(fact_id=fid, mark_id=rep.mark_id, kind="hit", group=rep.group,
                text=f"大模型判定：标识相似程度{LEVEL_LABEL[sim]}。{reason}")
    fixed = 0
    updated = []
    for a in members:
        proposed = by_id.get(a.mark_id)
        if proposed not in RISKS:
            proposed, _ = risk_level(a.prior, a.goods_rel, sim)       # 模型没逐件给出时，按它的近似判断组合
        exact = any(s["facts"][f].text == "文字完全相同" for f in a.fact_ids if f in s["facts"])
        final, note = guardrails.apply(proposed, sim, a.prior, a.goods_rel, exact)
        fixed += bool(note)
        rule = a.rule_risk or a.risk
        updated.append(a.model_copy(update={
            "mark_sim": sim, "risk": final, "decided_by": "llm", "guardrail": note,
            "disagree": bool(out.get("disagree")) or final != rule,
            "flag_review": bool(out.get("disagree")) or final != rule,
            "explanation": reason if a.mark_id == rep.mark_id else a.explanation,
            "explanation_source": "llm" if a.mark_id == rep.mark_id else a.explanation_source,
            "fact_ids": a.fact_ids + ([fid] if fid not in a.fact_ids else []),
        }))
    return updated, fact, fixed


def judge(s: AgentState) -> dict:
    t0 = time.time()
    assessments = s.get("assessments", [])
    grouped = groups.by_group(assessments)
    # 所有件都被事实锁定为低风险（不构成在先或商品不类似）的组，不必请模型判断
    worth = [g for g, ms in grouped.items()
             if not all(a.prior in ("not_prior", "invalid") or a.goods_rel == "dissimilar" for a in ms)]
    todo, capped = worth[: settings.llm_max_groups], worth[settings.llm_max_groups:]
    contexts = {g: _context(s, grouped[g]) for g in todo}
    results: dict[str, dict | None] = {}
    if todo and llm.available():
        with ThreadPoolExecutor(max_workers=min(5, len(todo))) as pool:
            results = dict(zip(todo, pool.map(lambda g: llm.chat_json("p2_judge", contexts[g]["vars"]), todo)))
    facts = dict(s.get("facts", {}))
    new: dict[str, Assessment] = {}
    fixed = disagree = failed = 0
    for g in todo:
        out = results.get(g)
        if not out:
            failed += 1
            continue
        updated, fact, n_fixed = _apply(s, grouped[g], contexts[g], out)
        facts[fact.fact_id] = fact
        fixed += n_fixed
        disagree += sum(1 for a in updated if a.disagree)
        new.update({a.mark_id: a for a in updated})
    final = [new.get(a.mark_id, a) for a in assessments]

    # 风险变了，依据要跟着重算：高 / 中风险（驳回复审时低风险也要）按映射表给出建议依据
    review = s.get("scenario") == "rejection_review"
    allowed = list(s.get("allowed_basis", []))
    out_list = []
    for a in final:
        need = a.risk in ("high", "medium") or (review and a.risk == "low")
        kinds = [h.kind for h in s.get("hits_by_mark", {}).get(a.mark_id, [])]
        prior = a.prior if a.prior in ps.GRADED else "valid"
        ids = basis.basis_for(s["scenario"], s["eval_date"], prior, kinds) if need else []
        allowed += [i for i in ids if i not in allowed]
        out_list.append(a.model_copy(update={"basis_ids": ids}))

    notes = []
    if capped:
        notes.append(f"为控制时延和费用，只为前 {len(todo)} 个名称组调用大模型判定，其余 {len(capped)} 组沿用规则引擎的结果")
    if failed or (todo and not llm.available()):
        why = llm.last_error if llm.available() else "未配置 LLM_API_KEY 或 LLM_MODEL"
        notes.append(f"{failed or len(todo)} 个名称组未能由大模型判定（{why}），沿用规则引擎的结果")
    dt = round(time.time() - t0, 3)
    return {"assessments": out_list, "facts": facts, "allowed_basis": allowed,
            "degraded": bool(failed) or bool(todo and not llm.available()), "degraded_notes": notes,
            "timings": {"judge": dt},
            "trace": [{"node": "judge", "judged": len(todo) - failed if llm.available() else 0, "capped": len(capped),
                       "guardrail_fixed": fixed, "disagree": disagree, "seconds": dt}]}
