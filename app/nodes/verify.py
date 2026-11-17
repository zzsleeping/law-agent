"""verify：引用校验（方案第七节）。只校验结构，条文是否支持结论由人工抽检。"""
from __future__ import annotations

import re
from datetime import date

from app.nodes.assess import SCOPE_FACT
from app.state import AgentState, Assessment, Claim, Fact
from app.tools.basis import get_basis, is_applicable

ARTICLE = re.compile(r"第\s*[一二三四五六七八九十百零〇\d]+\s*条")


def check_claims(claims: list[Claim], allowed: list[str], eval_date: date,
                 selected: list[Assessment], facts: dict[str, Fact], scenario: str = "pre_filing") -> list[str]:
    errors = []
    kept = {a.mark_id for a in selected}
    group = {a.mark_id: (a.group or a.mark_id) for a in selected}
    has_risky = any(a.risk in ("high", "medium") for a in selected)
    for i, c in enumerate(claims, 1):
        tag = f"第 {i} 条结论"
        # 1. 结论必须属于用户保留的候选
        if c.claim_type != "overall" and c.mark_id not in kept:
            errors.append(f"{tag}：{c.mark_id} 不在已确认候选中")
            continue
        # 2. 数据缺口结论只能由代码生成
        if c.claim_type == "data_gap" and c.source != "code":
            errors.append(f"{tag}：数据缺口结论不得由模型生成")
        # 3. 事实必须存在，且属于该结论的候选；总结论只能引用全局事实或保留候选的事实
        if not c.fact_ids:
            errors.append(f"{tag}：没有引用事实")
        for fid in c.fact_ids:
            f = facts.get(fid)
            if f is None:
                errors.append(f"{tag}：事实不存在 {fid}")
            elif c.mark_id and f.mark_id != c.mark_id and (f.group or f.mark_id) != group.get(c.mark_id):
                errors.append(f"{tag}：事实 {fid} 不属于 {c.mark_id} 或其同名组")
            elif f.mark_id and f.mark_id not in kept and f.kind != "group":
                errors.append(f"{tag}：事实 {fid} 属于已剔除的候选")
            elif c.claim_type == "overall" and fid != SCOPE_FACT and f.mark_id not in kept:
                errors.append(f"{tag}：事实 {fid} 属于已剔除的候选")
        # 4. 是否必引由代码按类型决定：risk 必引；overall 在有高 / 中风险候选时必引；data_gap 不引
        required = c.claim_type == "risk" or (c.claim_type == "overall" and has_risky)
        if required and not c.basis_ids:
            errors.append(f"{tag}：缺少依据")
        for bid in c.basis_ids:
            b = get_basis(bid)
            if b is None:
                errors.append(f"{tag}：依据不存在 {bid}")
            elif bid not in allowed:
                errors.append(f"{tag}：{bid} 不在本次允许清单内")
            elif not is_applicable(b, eval_date):
                errors.append(f"{tag}：{bid} 版本不适用")
        # 5. 结论文本不得自写条号，条号只由 render 渲染
        if ARTICLE.search(c.conclusion):
            errors.append(f"{tag}：结论中自行写了条号")
    # 6. 覆盖：逐个名称组核对是否有对应类型的结论（同名多件注册共用一条）
    claim_types: dict[str, set] = {}
    for c in claims:
        if c.mark_id in group:
            claim_types.setdefault(group[c.mark_id], set()).add(c.claim_type)
    for g, members in {grp: [a for a in selected if group[a.mark_id] == grp] for grp in set(group.values())}.items():
        types = claim_types.get(g, set())
        label = members[0].mark_id if len(members) == 1 else f"{members[0].text}（同名 {len(members)} 件）"
        need_risk = ("high", "medium", "low") if scenario == "rejection_review" else ("high", "medium")
        if any(a.risk in need_risk for a in members) and "risk" not in types:
            errors.append(f"缺少风险结论：{label}")
        if any(a.risk == "needs_check" for a in members) and "data_gap" not in types:
            errors.append(f"缺少数据缺口说明：{label}")
    n_overall = sum(1 for c in claims if c.claim_type == "overall")
    if n_overall == 0:
        errors.append("缺少总结论")
    elif n_overall > 1:
        errors.append("总结论只能有一条")
    return errors


def verify(s: AgentState) -> dict:
    errors = check_claims(s.get("claims", []), s.get("allowed_basis", []), s["eval_date"],
                          s.get("selected", []), s.get("facts", {}), s.get("scenario", "pre_filing"))
    return {"citation_errors": errors,
            "retry_count": s.get("retry_count", 0) + (1 if errors else 0),
            "trace": [{"node": "verify", "errors": len(errors), "detail": errors[:5]}]}
