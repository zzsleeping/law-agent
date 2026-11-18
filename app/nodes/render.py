"""render / flag_output：把结构化结论渲染成报告，按版本渲染条号与原文，导出 Word。"""
from __future__ import annotations

from datetime import datetime

from langchain_core.runnables import RunnableConfig

from app import db
from app.config import settings
from app.rules import goods_relation as gr
from app.rules import groups as grp
from app.rules import prior_status as ps
from app.rules.risk_table import LEVEL_LABEL, RISK_LABEL
from app.state import AgentState
from app.tools import basis
from app.tools import cases as case_lib

DISCLAIMER = ("本报告由程序按规则表和结构化校验生成，仅供申请前筛查参考，不构成法律意见。"
              "未考虑驰名商标跨类保护、图形要素和实际使用情况。在先状态由公告日期推定，法律状态须另行核实。")


def build_report(s: AgentState, flagged: bool) -> dict:
    records = s.get("records", {})
    facts = s.get("facts", {})
    claims = s.get("claims", [])

    def claim_view(c) -> dict:
        return {"type": c.claim_type, "conclusion": c.conclusion, "source": c.source,
                "facts": [facts[f].text for f in c.fact_ids if f in facts],
                "basis": [{"id": b, "citation": basis.citation(b)} for b in c.basis_ids]}

    def item_view(a) -> dict:
        r = records[a.mark_id]
        return {
            "mark_id": a.mark_id, "text": a.text, "risk": a.risk, "risk_label": RISK_LABEL[a.risk],
            "mark_sim": LEVEL_LABEL[a.mark_sim], "goods_rel": gr.LABEL[a.goods_rel], "prior": ps.LABEL[a.prior],
            "channels": a.channels, "explanation": a.explanation, "explanation_source": a.explanation_source,
            "flag_review": a.flag_review, "hints": a.hints,
            "owner": r.owner, "status": r.status or ps.LABEL[a.prior], "app_date": str(r.app_date or "未知"),
            "goods": "、".join(g.name for g in r.goods),
            "source": r.source, "source_ref": r.source_ref, "snapshot_date": str(r.snapshot_date),
            "is_simulated": r.is_simulated,
            "decided_by": a.decided_by, "rule_risk_label": RISK_LABEL.get(a.rule_risk, ""), "guardrail": a.guardrail,
            "disagree": a.disagree,
            "claims": [claim_view(c) for c in claims if c.mark_id == a.mark_id],
        }

    selected = s.get("selected", [])

    def group_view(members) -> dict:
        """名称组：同名的多件注册。风险取组内最高，解释取代表件。"""
        rep = grp.representative(members)
        ids = {a.mark_id for a in members}
        r = records[rep.mark_id]
        return {
            "group": grp.group_of(rep), "mark_id": rep.mark_id, "text": r.text or rep.text,
            "count": len(members), "risk": rep.risk, "risk_label": RISK_LABEL[rep.risk],
            "mark_sim": LEVEL_LABEL[rep.mark_sim], "channels": rep.channels,
            "explanation": rep.explanation, "explanation_source": rep.explanation_source,
            "flag_review": rep.flag_review, "hints": rep.hints, "is_simulated": r.is_simulated,
            "decided_by": rep.decided_by, "rule_risk_label": RISK_LABEL.get(rep.rule_risk, ""),
            "rule_mark_sim": LEVEL_LABEL.get(rep.rule_mark_sim, ""), "disagree": any(a.disagree for a in members),
            "guardrails": [f"{a.mark_id}：{a.guardrail}" for a in members if a.guardrail],
            "claims": [claim_view(c) for c in claims if c.mark_id in ids],
            "marks": [item_view(a) for a in sorted(members, key=lambda a: grp.RISK_ORDER[a.risk])],
        }

    group_views = [group_view(ms) for ms in grp.by_group(selected).values()]
    # 同类情形的参考判例：高 / 中风险组（驳回复审时全部引证），最多 llm_max_groups 组
    review = s.get("scenario") == "rejection_review"
    want = {g["group"] for g in group_views if review or g["risk"] in ("high", "medium")}
    want = set(list(dict.fromkeys(g["group"] for g in group_views if g["group"] in want))[: settings.llm_max_groups])
    for g in group_views:
        g["pattern_cases"] = case_lib.for_pair(s["query_mark"], g["text"]) if g["group"] in want else None
    used = list(dict.fromkeys(b for c in claims for b in c.basis_ids))
    appendix = []
    for bid in used:
        b = basis.get_basis(bid)
        if b:
            appendix.append({"id": bid, "citation": basis.citation(bid), "text": b["text"], "source": b["source"],
                             "effective_from": str(b["effective_from"]),
                             "effective_to": str(b["effective_to"] or "现行有效"),
                             "version_note": basis.version_note(bid),
                             "from_rag": s.get("basis_sources", {}).get(bid) == "rag"})
    overall = next((claim_view(c) for c in claims if c.claim_type == "overall"), None)
    return {
        "title": (f"驳回复审逐项比对报告：{s['query_mark']}" if s.get("scenario") == "rejection_review"
                  else f"商标近似风险筛查报告：{s['query_mark']}"),
        "scenario": s.get("scenario", "pre_filing"),
        "missing_citations": s.get("missing_citations", []),
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "query_mark": s["query_mark"], "distinctive": s.get("distinctive", ""),
        "meaning": s.get("query_meaning", ""),
        "goods": [g.model_dump() for g in s.get("goods", [])],
        "classes": s.get("classes", []),
        "eval_date": str(s["eval_date"]), "our_app_date": str(s.get("our_app_date") or ""),
        "our_priority_date": str(s.get("our_priority_date") or ""),
        "law_version": basis.law_version_label(s["eval_date"]),
        "data_scope": s.get("data_scope", "all"), "coverage": db.coverage(),
        "flagged": flagged, "errors": s.get("citation_errors", []) if flagged else [],
        "degraded": bool(s.get("degraded")), "degraded_notes": s.get("degraded_notes", []),
        "overall": overall,
        # 按名称组列出；组的风险取组内最高
        "high": [g for g in group_views if g["risk"] == "high"],
        "medium": [g for g in group_views if g["risk"] == "medium"],
        "needs_check": [g for g in group_views if g["risk"] == "needs_check"],
        "low": [g for g in group_views if g["risk"] == "low"],
        "n_marks": len(selected), "n_groups": len(group_views),
        "exclusions": [{"mark_id": e.mark_id, "text": e.text, "risk_label": RISK_LABEL.get(e.risk, e.risk),
                        "at": e.at.strftime("%Y-%m-%d %H:%M:%S"), "note": e.note} for e in s.get("exclusions", [])],
        "basis_appendix": appendix,
        "timings": s.get("timings", {}),
        "search_variants": s.get("search_variants", []),
        "agent_steps": [t for t in s.get("trace", []) if t.get("node") in ("plan_search", "judge")],
        "disclaimer": DISCLAIMER,
    }


def export_docx(report: dict, path) -> None:
    from docx import Document
    from docx.shared import Pt, RGBColor

    doc = Document()
    doc.styles["Normal"].font.size = Pt(10.5)
    doc.add_heading(report["title"], level=0)

    def red(text: str) -> None:
        run = doc.add_paragraph().add_run(text)
        run.bold = True
        run.font.color.rgb = RGBColor(0xC0, 0x00, 0x00)

    if report["flagged"]:
        red("【引用校验未通过，需人工处理】以下结论经两次重写仍未通过校验，不得直接使用。")
        for e in report["errors"]:
            red(f"· {e}")
    if report["degraded"]:
        red("【降级输出】部分内容未使用大模型：" + "；".join(report["degraded_notes"]))

    doc.add_heading("一、基本信息", level=1)
    goods = "、".join(f"{g['name']}（{g['code'] or '未对应区分表，待核实'}）" for g in report["goods"])
    cov = report["coverage"]
    for k, v in [
        ("待查商标", report["query_mark"]), ("商标含义", report["meaning"] or "未提供"),
        ("指定商品或服务", goods), ("检索类别", "、".join(f"第 {c} 类" for c in report["classes"])),
        ("评估日期", report["eval_date"]), ("（模拟）申请日", report["our_app_date"]),
        ("适用法律版本", report["law_version"]),
        ("数据范围", (f"国家知识产权局商标开放数据，第 {cov['real']['classes']} 类共 {cov['real']['count']:,} 件，"
                      f"增量截至 {cov['real']['date']}" if cov["real"].get("source") == "open"
                      else f"真实记录 {cov['real']['count']} 条（数据日期 {cov['real']['date'] or '—'}）")
                  + (f"；测试用仿真记录 {cov['simulated']['count']} 条" if cov["simulated"]["count"] else "")),
        ("候选", f"共 {report.get('n_groups', 0)} 个名称组、{report.get('n_marks', 0)} 件注册"),
        ("报告生成时间", report["generated_at"]),
    ]:
        p = doc.add_paragraph()
        p.add_run(f"{k}：").bold = True
        p.add_run(str(v))

    def add_claim(c: dict) -> None:
        doc.add_paragraph(c["conclusion"])
        if c["facts"]:
            doc.add_paragraph("事实：" + " ".join(f"（{i}）{t}" for i, t in enumerate(c["facts"], 1)))
        if c["basis"]:
            doc.add_paragraph("依据：" + "；".join(b["citation"] for b in c["basis"]))

    if report.get("search_variants"):
        doc.add_paragraph("检索规划（大模型）：除原文外还检索了 " + "；".join(
            f"“{q['text']}”（{q['why']}，命中 {q.get('hits', 0)} 件）" for q in report["search_variants"]))

    doc.add_heading("二、总结论", level=1)
    if report["overall"]:
        add_claim(report["overall"])

    def marks_table(marks: list[dict]) -> None:
        t = doc.add_table(rows=1, cols=6)
        t.style = "Table Grid"
        for cell, h in zip(t.rows[0].cells, ["编号", "风险", "在先状态（推断依据见事实）", "商品关系", "申请日", "原始记录"]):
            cell.text = h
        for m in marks:
            row = t.add_row().cells
            for cell, v in zip(row, [m["mark_id"], m["risk_label"], m["prior"], m["goods_rel"], m["app_date"],
                                     m["source_ref"] or "—"]):
                cell.text = str(v)

    def add_cases(pc: dict | None) -> None:
        """同类情形的参考判例（仅供参考，不作为依据）。"""
        if not pc or not (pc["similar"] or pc["dissimilar"] or pc["note"]):
            return
        doc.add_paragraph().add_run(f"同类情形参考判例（{pc['pattern']}，仅供参考，不作为依据）").bold = True
        for c in pc["similar"] + pc["dissimilar"]:
            doc.add_paragraph(f"· 官方认定{c['label']}：“{c['applicant']}”与“{c['cited']}”"
                              + (f"——{c['excerpt']}" if c["excerpt"] else "")
                              + f"（{c['case_id']}，{c['decision_date']}，{c['source_url']}）")
        if pc["note"]:
            doc.add_paragraph(pc["note"] + "。")

    def add_items(title: str, items: list[dict], with_claims: bool = True) -> None:
        doc.add_heading(title, level=1)
        if not items:
            doc.add_paragraph("无。")
            return
        for it in items:
            tag = "【示例数据】" if it["is_simulated"] else ""
            count = f"，同名注册 {it['count']} 件" if it["count"] > 1 else f"（{it['mark_id']}）"
            doc.add_heading(f"{tag}{it['text']}{count} — {it['risk_label']}", level=2)
            who = "大模型判定" if it["decided_by"] == "llm" else "规则引擎（未经大模型判定）"
            doc.add_paragraph(f"标识相似程度：{it['mark_sim']}（{who}；规则参考：{it['rule_mark_sim']}）。"
                              + ("模型判断与规则不一致，建议人工复核。" if it["disagree"] else ""))
            for gnote in it["guardrails"]:
                doc.add_paragraph(gnote)
            if with_claims:
                for c in it["claims"]:
                    add_claim(c)
            doc.add_paragraph(("说明（大模型）：" if it["explanation_source"] == "llm" else "说明（规则生成）：")
                              + it["explanation"])
            if it["flag_review"]:
                red("大模型建议人工复核该等级。")
            marks_table(it["marks"])
            add_cases(it.get("pattern_cases"))
            for h in it["hints"]:
                doc.add_paragraph(f"提示（历史交叉检索，不参与定级）：{h}")

    add_items("三、高风险候选", report["high"])
    add_items("四、中风险候选", report["medium"])
    add_items("五、待核实候选（缺数据，不等于低风险）", report["needs_check"])
    if report.get("scenario") == "rejection_review":
        add_items("六、低风险的引证商标", report["low"])
        if report.get("missing_citations"):
            red("以下引证商标在库内找不到，未比对：" + "、".join(report["missing_citations"]))
    elif report["low"]:
        doc.add_heading("六、低风险候选", level=1)
        t = doc.add_table(rows=1, cols=4)
        t.style = "Table Grid"
        for cell, h in zip(t.rows[0].cells, ["商标", "件数", "编号", "说明"]):
            cell.text = h
        for it in report["low"]:
            row = t.add_row().cells
            row[0].text, row[1].text = it["text"], str(it["count"])
            row[2].text = "、".join(m["mark_id"] for m in it["marks"][:6]) + ("等" if it["count"] > 6 else "")
            row[3].text = it["explanation"]
    else:
        doc.add_heading("六、低风险候选", level=1)
        doc.add_paragraph("无。")

    doc.add_heading("附录一、用户剔除的候选", level=1)
    if report["exclusions"]:
        for e in report["exclusions"]:
            doc.add_paragraph(f"{e['text']}（{e['mark_id']}），原风险等级：{e['risk_label']}，剔除时间：{e['at']}"
                              + (f"，说明：{e['note']}" if e["note"] else ""))
    else:
        doc.add_paragraph("无。")

    doc.add_heading("附录二、依据原文与来源", level=1)
    for b in report["basis_appendix"]:
        doc.add_heading(b["citation"] + ("（RAG 检索补充）" if b.get("from_rag") else ""), level=2)
        doc.add_paragraph(b["text"])
        doc.add_paragraph(f"依据 ID：{b['id']}；施行：{b['effective_from']} 至 {b['effective_to']}；来源：{b['source']}")
        if b["version_note"]:
            doc.add_paragraph(f"版本对应：{b['version_note']}")
    if not report["basis_appendix"]:
        doc.add_paragraph("本报告未引用依据。")

    doc.add_heading("声明", level=1)
    doc.add_paragraph(report["disclaimer"])
    doc.save(str(path))


def _finish(s: AgentState, config: RunnableConfig, flagged: bool, node: str) -> dict:
    report = build_report(s, flagged)
    tid = (config or {}).get("configurable", {}).get("thread_id", "report")
    settings.output_dir.mkdir(parents=True, exist_ok=True)
    path = settings.output_dir / f"{tid}.docx"
    export_docx(report, path)
    return {"report": report, "report_path": str(path),
            "trace": [{"node": node, "flagged": flagged, "path": str(path)}]}


def render(s: AgentState, config: RunnableConfig) -> dict:
    return _finish(s, config, False, "render")


def flag_output(s: AgentState, config: RunnableConfig) -> dict:
    """重写两次仍未通过校验：标红输出，提示人工处理。"""
    return _finish(s, config, True, "flag_output")
