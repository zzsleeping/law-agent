"""compose：生成结构化结论（P3）。

- data_gap 结论永远由代码生成；
- risk / overall 结论由大模型生成，失败时用模板，并直接采用代码给出的建议依据；
- 没有高 / 中风险候选时，总结论由代码生成，不要求依据。
只读 selected（用户确认保留的候选）。
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

from app import llm
from app.config import settings
from app.nodes.assess import SCOPE_FACT
from app.rules import groups
from app.rules.risk_table import RISK_LABEL
from app.state import AgentState, Assessment, Claim
from app.tools import basis


def _gap_claims(s: AgentState, selected: list[Assessment]) -> list[Claim]:
    """每个名称组一条数据缺口说明，合并组内全部待核实的注册。"""
    out = []
    for g, members in groups.by_group([a for a in selected if a.risk == "needs_check"]).items():
        gaps = [f for a in members for f in a.fact_ids if s["facts"][f].kind == "data_gap"]
        first = members[0]
        if len(members) == 1:
            head = f"在先商标“{first.text}”（{first.mark_id}）"
            detail = "；".join(s["facts"][f].text for f in gaps)
        else:
            head = f"与“{first.text}”同名的 {len(members)} 件在先注册（{'、'.join(a.mark_id for a in members[:8])}{'等' if len(members) > 8 else ''}）"
            detail = "；".join(dict.fromkeys(s["facts"][f].text.split("：")[0] for f in gaps))
        out.append(Claim(mark_id=first.mark_id, claim_type="data_gap", source="code", fact_ids=gaps, basis_ids=[],
                         conclusion=f"{head}与待查商标标识有相似之处，但数据不足，暂不能评定风险等级。{detail}。"
                                    "补齐后需重新评估，不应视为低风险。"))
    return out


def _counts(selected: list[Assessment]) -> str:
    c = {r: sum(1 for a in selected if a.risk == r) for r in RISK_LABEL}
    return f"高风险 {c['high']} 个、中风险 {c['medium']} 个、待核实 {c['needs_check']} 个、低风险 {c['low']} 个"


REVIEW_TASK = ("逐项比对：为下面列出的每件引证商标各写一条 claim_type 为 \"risk\" 的结论，"
               "写明两商标在文字构成、读音、含义上的相同点和不同点，以及商品关系和在先状态；"
               "风险等级照抄代码给出的结果，不得改变；不写复审理由或论证。不要写总结论。")


def _review(s: AgentState) -> bool:
    return s.get("scenario") == "rejection_review"


def _template_risk(s: AgentState, a: Assessment) -> Claim:
    ev = "；".join(s["facts"][f].text for f in a.fact_ids if s["facts"][f].kind == "hit")
    return Claim(
        mark_id=a.mark_id, claim_type="risk", source="code",
        fact_ids=[f for f in a.fact_ids if s["facts"][f].kind in ("hit", "goods", "prior")],
        basis_ids=a.basis_ids,
        conclusion=(f"待查商标“{s['query_mark']}”与在先商标“{a.text}”（{a.mark_id}）：{ev}。"
                    f"{s['facts'][f'F-{a.mark_id}-goods'].text} {s['facts'][f'F-{a.mark_id}-prior'].text} "
                    f"综合评为{RISK_LABEL[a.risk]}，"
                    + ("构成在先障碍的可能性较小。" if a.risk == "low" else "存在被引证驳回的可能。")))


def _template_overall(s: AgentState, selected: list[Assessment], risky: list[Assessment]) -> Claim:
    if not selected:
        text = (f"本次检索范围内，没有保留任何与“{s['query_mark']}”构成在先障碍的候选商标。"
                "该结论仅限于本次检索的类别和数据范围，不代表全量商标库的检索结果。")
    elif not risky:
        text = (f"本次保留的 {len(selected)} 个候选中（{_counts(selected)}），未发现高风险或中风险的在先商标。"
                "待核实的候选需补齐数据后重新评估；该结论仅限于本次检索的类别和数据范围。")
    else:
        risky = sorted(risky, key=lambda a: a.risk != "high")      # 高风险排在前面，原顺序不变
        names = "、".join(list(dict.fromkeys(f"“{a.text}”" for a in risky))[:5])
        text = (f"本次保留的 {len(selected)} 个候选中（{_counts(selected)}），{names}"
                f"{'等' if len(risky) > 5 else ''}与待查商标“{s['query_mark']}”在同一种或类似商品上"
                "构成相同或近似商标的可能性较大，建议在申请前调整标识或商品范围，或进一步人工评估。")
    basis_ids = []
    for a in risky:
        for b in a.basis_ids:
            if b.startswith("TML") and b not in basis_ids:
                basis_ids.append(b)
    return Claim(mark_id=None, claim_type="overall", source="code", conclusion=text,
                 fact_ids=[SCOPE_FACT], basis_ids=basis_ids)


def _call(s: AgentState, cands: list[Assessment], task: str) -> list[Claim] | None:
    """调用一次 P3。task 为 "risk"（只写这些候选的风险结论）或 "overall"（只写总结论）。失败返回 None。"""
    lines = []
    for a in cands:
        facts = "\n".join(f"    [{f}] {s['facts'][f].text}" for f in a.fact_ids)
        lines.append(f"- mark_id: {a.mark_id}  文字：{a.text}  风险：{RISK_LABEL[a.risk]}\n"
                     f"  可引用的事实：\n{facts}\n  建议依据：{', '.join(a.basis_ids)}")
    wanted = list(dict.fromkeys(b for a in cands for b in a.basis_ids)) if task == "risk" else s.get("allowed_basis", [])
    allowed = []
    for i in wanted:
        b = basis.get_basis(i)
        allowed.append(f"[{i}] {b['title'] + '：' if b['title'] else ''}{b['text'][:600]}")
    data = llm.chat_json("p3_compose", {
        "scenario": "驳回复审逐项比对" if _review(s) else "申请前筛查", "eval_date": str(s["eval_date"]),
        "query": f"{s['query_mark']}；" + "、".join(g.name for g in s.get("goods", [])),
        "task": (REVIEW_TASK if _review(s) else "只为下面列出的候选各写一条 claim_type 为 \"risk\" 的结论，不要写总结论。")
                if task == "risk" else
                "只写一条 claim_type 为 \"overall\" 的总结论（mark_id 填 null），概括全部候选，不要写 risk 结论。",
        "assessments": "\n".join(lines),
        "scope_fact": f"[{SCOPE_FACT}] {s['facts'][SCOPE_FACT].text}",
        "allowed_basis": "\n".join(allowed),
        "errors": "\n".join(s.get("citation_errors") or []) or "无",
    })
    if data is None:
        return None
    ids = {a.mark_id for a in cands}
    out = []
    for c in data.get("claims") or []:
        try:
            # 只收本次任务要的类型；模型自行给出的 data_gap 等一律丢弃
            if c.get("claim_type") != task or (task == "risk" and c.get("mark_id") not in ids):
                continue
            out.append(Claim(mark_id=(c.get("mark_id") or None) if task == "risk" else None, claim_type=task,
                             conclusion=str(c.get("conclusion", "")), fact_ids=list(c.get("fact_ids") or []),
                             basis_ids=list(c.get("basis_ids") or []), source="llm"))   # source 强制为 llm
        except Exception:
            continue
    return out


def _llm_claims(s: AgentState, selected: list[Assessment], risky: list[Assessment]) -> tuple[list[Claim], int]:
    """每个名称组一次调用并发执行（最多 llm_max_groups 组，其余用模板），外加一次总结论调用。
    失败的部分用模板补上。返回 (结论, 失败次数)。"""
    head, tail = risky[: settings.llm_max_groups], risky[settings.llm_max_groups:]
    with ThreadPoolExecutor(max_workers=min(5, len(head) + 1)) as pool:
        overall_job = pool.submit(_call, s, head, "overall")
        per_mark = list(pool.map(lambda a: _call(s, [a], "risk"), head))
        overall = overall_job.result()
    claims, failed = [_template_risk(s, a) for a in tail], 0
    for a, got in zip(head, per_mark):
        if got is None:
            failed += 1
            claims.append(_template_risk(s, a))
        else:
            claims += got
    if overall is None:
        failed += 1
        claims.append(_template_overall(s, selected, risky))
    else:
        claims += overall[:1] if overall else []
    return claims, failed


def compose(s: AgentState) -> dict:
    t0 = time.time()
    selected = s.get("selected", [])
    # 每个高 / 中风险名称组由代表件写一条风险结论；驳回复审逐件比对，低风险的引证也写
    wanted = ("high", "medium", "low") if _review(s) else ("high", "medium")
    risky = [groups.representative(ms) for ms in groups.by_group(
        [a for a in selected if a.risk in wanted]).values()]
    claims = _gap_claims(s, selected)
    notes, degraded, used_llm = [], False, False
    if risky:
        generated, failed = _llm_claims(s, selected, risky)
        if len(risky) > settings.llm_max_groups:
            notes.append(f"为控制时延和费用，只为前 {settings.llm_max_groups} 个名称组调用大模型写结论，"
                         f"其余 {len(risky) - settings.llm_max_groups} 组使用模板")
        used_llm = failed < len(risky) + 1
        if failed:
            degraded = True
            why = llm.last_error if llm.available() else "未配置 LLM_API_KEY 或 LLM_MODEL"
            notes.append(f"{failed} 条结论未使用大模型（{why}），由模板生成")
        claims += generated
    else:
        claims.append(_template_overall(s, selected, risky))
    dt = round(time.time() - t0, 3)
    key = "compose" if not s.get("retry_count") else f"compose_retry{s['retry_count']}"
    return {"claims": claims, "degraded": degraded, "degraded_notes": notes, "timings": {key: dt},
            "trace": [{"node": "compose", "claims": len(claims), "llm": used_llm, "seconds": dt}]}
