"""Streamlit 页面：申请前筛查。启动：streamlit run ui/streamlit_app.py"""
import re
import sys
import uuid
from datetime import date
from html import escape as esc
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402
from langgraph.types import Command  # noqa: E402

from app import db, llm  # noqa: E402
from app.config import settings  # noqa: E402
from app.graph import build_graph  # noqa: E402
from app.rules import goods_relation as gr  # noqa: E402
from app.rules import prior_status as ps  # noqa: E402
from app.rules.risk_table import LEVEL_LABEL, RISK_LABEL  # noqa: E402
from app.tools import basis  # noqa: E402
from app.tools import goods as goods_tool  # noqa: E402
from ui import style  # noqa: E402

st.set_page_config(page_title="商标近似评估智能体", page_icon="§", layout="wide")
st.markdown(style.CSS, unsafe_allow_html=True)

CHANNEL_LABEL = {"exact": "完全相同", "contains": "包含", "glyph": "字形", "pinyin": "读音",
                 "pinyin_fuzzy": "模糊音", "meaning": "含义", "transpose": "字序颠倒", "redup": "叠字"}
RECALL_LABEL = {"recall_exact": "精确文字", "recall_glyph": "字形", "recall_pinyin": "读音",
                "recall_variant": "字序与叠字", "recall_meaning": "含义"}
NODE_LABEL = {"parse": "要素解析", "confirm_goods": "确认商品项", **RECALL_LABEL, "merge": "排名融合",
              "assess": "规则定级", "explain": "模型解释", "confirm_candidates": "确认候选",
              "compose": "生成结论", "verify": "引用校验", "render": "渲染报告", "flag_output": "标红输出"}
RISK_ORDER = ["high", "medium", "needs_check", "low"]
EXAMPLES = [("茗悦", "茶饮料、奶茶"), ("沐茶", "茶饮料、奶茶"), ("云雾知春", "绿茶"),
            ("海星", "果汁"), ("南柠", "咖啡馆"), ("霁川", "茶饮料")]


def trace_text(t: dict) -> str:
    """把节点的执行记录写成一句中文。"""
    n = t.get("node", "")
    if n in RECALL_LABEL:
        return f"命中 {t.get('hits', 0)} 条 · {t.get('seconds', 0)} 秒"
    if n == "parse":
        return "大模型解析" if t.get("llm") else "未用大模型，仅向量检索建议"
    if n == "confirm_goods":
        return "检索第 " + "、".join(map(str, t.get("classes", []))) + " 类"
    if n == "merge":
        return f"召回 {t.get('recalled', 0)} 个，展示 {t.get('shown', 0)} 个"
    if n == "assess":
        c = t.get("counts", {})
        return (f"高 {c.get('high', 0)} · 中 {c.get('medium', 0)} · 待核实 {c.get('needs_check', 0)} · 低 {c.get('low', 0)}"
                f" · {t.get('rule_stage_seconds', '—')} 秒")
    if n == "explain":
        return f"模型解释 {t.get('llm_ok', 0)} 条，降级 {t.get('fallback', 0)} 条 · {t.get('seconds', 0)} 秒"
    if n == "confirm_candidates":
        return f"保留 {t.get('kept', 0)} 个，剔除 {t.get('excluded', 0)} 个"
    if n == "compose":
        return f"{t.get('claims', 0)} 条结论 · {t.get('seconds', 0)} 秒" + ("" if t.get("llm") else " · 模板生成")
    if n == "verify":
        return "通过" if not t.get("errors") else f"{t['errors']} 个错误：" + "；".join(t.get("detail", [])[:2])
    if n == "render":
        return "已导出 Word"
    if n == "flag_output":
        return "校验未通过，标红输出"
    return ""


def html(s: str) -> None:
    st.markdown(s, unsafe_allow_html=True)


@st.cache_resource
def get_graph():
    return build_graph()


if not settings.db_path.exists():
    st.error("还没有建库。请先运行：python scripts/import_decisions.py && python scripts/build_db.py && python scripts/build_open_index.py")
    st.stop()

graph = get_graph()
ss = st.session_state
ss.setdefault("stage", "input")
cfg = {"configurable": {"thread_id": ss.get("tid", "none")}}
STAGE_INDEX = {"input": 0, "goods": 1, "candidates": 2, "report": 3}


def values() -> dict:
    return graph.get_state(cfg).values


def stream(payload) -> None:
    """执行到下一个挂起点或结束，实时显示每个节点的状态。"""
    with st.status("正在执行……", expanded=True) as status:
        for chunk in graph.stream(payload, cfg, stream_mode="updates"):
            for node, upd in chunk.items():
                if node == "__interrupt__":
                    continue
                extra = trace_text((upd or {}).get("trace", [{"node": node}])[-1])
                st.markdown(f"✓ **{NODE_LABEL.get(node, node)}**" + (f"　{extra}" if extra else ""))
        status.update(label="本阶段完成", state="complete")


def notices(v: dict) -> None:
    for n in v.get("degraded_notes", []):
        if n.startswith("为控制时延"):
            html(style.note(esc(n), "info"))
        else:
            html(style.note(f"<b>降级</b>　{esc(n)}", "warn"))


def restart() -> None:
    for k in list(ss.keys()):
        del ss[k]
    st.rerun()


# ---------------- 侧边栏 ----------------
with st.sidebar:
    cov = db.coverage()
    if cov["real"].get("source") == "open":
        html('<div class="side-h">商标库</div>'
             f'<div class="side-row"><span>开放数据（真实）</span><b>{cov["real"]["count"]:,}</b></div>'
             f'<div class="side-row"><span>覆盖类别</span><b>{esc(cov["real"]["classes"])}</b></div>'
             f'<div class="side-row"><span>增量截至</span><b>{cov["real"]["date"]}</b></div>'
             '<div class="side-cap">数据来自国家知识产权局商标开放数据。在先状态由公告日期推定，'
             '法律状态须另行核实。</div>')
    else:
        html('<div class="side-h">数据覆盖范围</div>'
             f'<div class="side-row"><span>本地真实记录</span><b>{cov["real"]["count"]}</b></div>'
             '<div class="side-cap">未接入正式商标库（TM_OPEN_DB 或检索索引缺失），只能检索决定书导入的少量记录。</div>')
    html('<div class="side-h">模型</div>'
         + (f'<div class="side-row"><span>大模型</span><b>{esc(settings.llm_model)}</b></div>'
            f'<div class="side-row"><span>超时</span><b>{settings.llm_timeout:.0f} 秒</b></div>' if llm.available()
            else '<div class="side-row"><span>大模型</span><b>未配置</b></div>')
         + f'<div class="side-row"><span>向量模型</span><b>{esc(db.get_meta("embed_backend") or "")}</b></div>')
    if not llm.available():
        html('<div class="side-cap">未配置 .env 中的 LLM_API_KEY / LLM_MODEL，解释和结论将由代码生成。</div>')
    st.write("")
    if st.button("重新开始", use_container_width=True):
        restart()

html(style.hero())
html(style.steps(STAGE_INDEX[ss.stage]))

# ---------------- ① 输入 ----------------
if ss.stage == "input":
    mode = st.segmented_control("场景", ["pre_filing", "rejection_review"], default="pre_filing",
                                format_func={"pre_filing": "申请前筛查", "rejection_review": "驳回复审逐项比对"}.get,
                                label_visibility="collapsed") or "pre_filing"
    review = mode == "rejection_review"
    if review:
        html('<div class="lead">录入驳回通知中的引证商标编号，系统逐件比对标识、商品和在先状态，给出每件的比对结论。'
             '不做复审理由或论证。</div>')
    else:
        html('<div class="lead">可以直接点一个示例填入，再点“开始评估”。</div>')
        cols = st.columns(len(EXAMPLES))
        for col, (m, g) in zip(cols, EXAMPLES):
            if col.button(m, key=f"ex_{m}", use_container_width=True, help=f"商品：{g}"):
                ss.in_mark, ss.in_desc = m, g
    with st.form("input", border=False):
        c1, c2 = st.columns(2)
        mark = c1.text_input("商标文字" if not review else "申请商标文字", key="in_mark", placeholder="例如：茗悦")
        desc = c2.text_input("商品或服务" if not review else "指定商品或服务", key="in_desc",
                             placeholder="用顿号或逗号分隔，例如：茶饮料、奶茶")
        citations = ""
        if review:
            citations = st.text_area("引证商标编号（每行一个，或用逗号分隔）", placeholder="例如：\n19266072\n20266296")
        else:
            meaning = st.text_input("商标含义（可选）", placeholder="不填则由大模型生成；用于义近召回")
        c3, c4, c5 = st.columns(3)
        eval_date = c3.date_input("评估日期", value=date.today(), help="决定适用的法律版本。切到 2027 年可以看到新法条号。")
        app_date = c4.date_input("实际申请日（必填）" if review else "预计申请日", value=None,
                                 help="从驳回通知或申请记录里取。" if review else "决定谁在先。留空则与评估日期相同。")
        prio_date = c5.date_input("优先权日（如有）", value=None, help="有优先权的，按优先权日比较先后。") if review else None
        from app.library import get_library
        scope = "real" if get_library().available() else "all"
        go = st.form_submit_button("开始比对" if review else "开始评估", type="primary")
    if go:
        cites = [c for c in re.split(r"[\s,，、;；]+", citations or "") if c]
        if not mark.strip() or not desc.strip():
            st.error("请填写商标文字和商品或服务。")
        elif review and not cites:
            st.error("请录入至少一个引证商标编号。")
        elif review and app_date is None:
            st.error("驳回复审需要填写实际申请日，可以从驳回通知或申请记录里取。")
        else:
            ss.tid = uuid.uuid4().hex[:12]
            cfg = {"configurable": {"thread_id": ss.tid}}
            payload = {"scenario": mode, "query_mark": mark.strip(), "goods_desc": desc.strip(),
                       "eval_date": eval_date, "our_app_date": app_date or eval_date, "data_scope": scope}
            if review:
                payload.update(user_citations=cites, our_priority_date=prio_date)
            else:
                payload["query_meaning"] = meaning.strip()
            stream(payload)
            ss.stage = "goods"
            st.rerun()

# ---------------- ② 确认商品项 ----------------
elif ss.stage == "goods":
    v = values()
    html(style.section(f"“{v['query_mark']}”的商品项", "系统建议，请确认后再检索"))
    notices(v)
    html(style.kv([("显著部分", v.get("distinctive") or "—"), ("评估日期", v["eval_date"]),
                   ("申请日", v.get("our_app_date"))]))
    html(f'<div class="lead" style="margin-top:.3rem">含义：{esc(v.get("query_meaning") or "未提供")}</div>')
    items = goods_tool.all_items()
    label = lambda it: f"{it['code']} · {it['name']}（第 {it['nice_class']} 类 {it['grp']}）"  # noqa: E731
    options = {label(it): it for it in items}
    by_key = {(it["code"], it["name"]): label(it) for it in items}
    proposal = v.get("goods", [])
    default = [by_key[(g.code, g.name)] for g in proposal if (g.code, g.name) in by_key]
    with st.container(border=True):
        chosen = st.multiselect("规范商品项（来自《类似商品和服务区分表》选录）", list(options), default=default)
        extra = st.text_input("选录之外的商品", value="、".join(g.name for g in proposal if not g.code),
                              placeholder="逗号分隔",
                              help="会标为“待核实”。与它相关的候选不会被判为低风险。")
        html('<div class="side-cap">检索类别由这里选中的商品项决定：它们所在的类别，加上区分表注释关联到的类别。</div>')
    if st.button("确认商品项，开始检索", type="primary"):
        goods = [goods_tool.to_item({**options[c]}, "confirmed").model_dump() for c in chosen]
        goods += [{"name": n, "mapping": "pending"} for n in goods_tool.split_desc(extra)]
        if not any(g.get("code") for g in goods):
            st.error("至少选择一个规范商品项，否则无法确定检索类别。")
        else:
            stream(Command(resume=goods))
            ss.stage = "candidates"
            st.rerun()

# ---------------- ③④ 召回过程与确认候选 ----------------
elif ss.stage == "candidates":
    v = values()
    assessments = {a.mark_id: a for a in v.get("assessments", [])}
    order = v.get("display_order", [])
    tm = v.get("timings", {})
    if v.get("scenario") == "rejection_review":
        html(style.section("引证商标", f"录入 {len(v.get('user_citations', []))} 个编号，库内找到 "
                                     f"{len(v.get('display_groups', []))} 个，共 {len(order)} 件档案"))
    else:
        html(style.section("召回过程", f"检索第 {'、'.join(map(str, v.get('classes', [])))} 类 · "
                                       f"共召回 {v.get('recalled_total', 0)} 个，展示 {len(order)} 个"))
    notices(v)
    recall_trace = {t["node"]: t for t in v.get("trace", []) if t["node"] in RECALL_LABEL}
    if v.get("scenario") != "rejection_review":
        html(style.kpis([(recall_trace.get(n, {}).get("hits", 0), name, f"{recall_trace.get(n, {}).get('seconds', 0)} 秒", "accent")
                     for n, name in RECALL_LABEL.items()]))
    html(f'<div class="lead">规则阶段（确认商品项 → 风险列表，不调用模型）耗时 <b>{tm.get("rule_stage", "—")} 秒</b>；'
         f'模型解释耗时 {tm.get("explain", "—")} 秒。</div>')

    from app.rules import groups as grp

    groups_ = [(g["group"], [assessments[m] for m in g["marks"] if m in assessments]) for g in v.get("display_groups", [])]
    gcounts = {r: sum(1 for _, ms in groups_ if ms and grp.group_risk(ms) == r) for r in RISK_ORDER}
    html(style.section("确认候选", f"{len(groups_)} 个名称组、{len(order)} 件注册；完全同名置顶，其余按标识相似程度排序"))
    html(style.kpis([(gcounts[r], RISK_LABEL[r], "名称组（取组内最高）", style.RISK_CLASS[r]) for r in RISK_ORDER]))
    if not order:
        html(style.note("检索范围内没有召回任何候选。可以直接生成报告。", "info"))
    show = st.pills("按风险筛选", RISK_ORDER, selection_mode="multi", default=RISK_ORDER,
                    format_func=RISK_LABEL.get, label_visibility="collapsed") or []
    html('<div class="lead">同名的多件注册归为一组。关掉右侧的“保留”即剔除整组；剔除的候选不会进入结论，但会列入报告附录。</div>')
    for n, (g, members) in enumerate(groups_, 1):
        if not members:
            continue
        rep_a = grp.representative(members)
        if grp.group_risk(members) not in show:
            continue
        r = v["records"][rep_a.mark_id]
        with st.container(border=True):
            c0, c1, c2 = st.columns([0.35, 8, 1.2])
            c0.markdown(f'<div class="rank">{n:02d}</div>', unsafe_allow_html=True)
            chips = "".join(f'<span class="chip">{CHANNEL_LABEL.get(c, c)}</span>' for c in rep_a.channels)
            evidence = "；".join(dict.fromkeys(h.evidence for h in v["hits_by_mark"].get(rep_a.mark_id, [])))
            mix = "　".join(f"{RISK_LABEL[k]} {c}" for k in RISK_ORDER
                           if (c := sum(1 for a in members if a.risk == k)))
            c1.markdown(
                f'<div class="cand-head"><span class="mark">{esc(r.text or rep_a.text)}</span>'
                f'{style.badge(rep_a.risk, RISK_LABEL[rep_a.risk])}'
                + (f'<span class="tag">同名 {len(members)} 件</span>' if len(members) > 1 else f'<span class="id">{esc(rep_a.mark_id)}</span>')
                + ('<span class="tag">示例数据</span>' if r.is_simulated else "")
                + ('<span class="tag warn">模型建议复核</span>' if rep_a.flag_review else "") + "</div>"
                f'<div>{chips}</div><div class="cand-ev">{esc(evidence)}</div>'
                f'<div class="cand-meta">{esc(mix)}</div>', unsafe_allow_html=True)
            c2.toggle("保留", value=True, key=f"keep_g_{g}")
            with c1.expander("解释与各件注册"):
                st.markdown(("**大模型解释**　" if rep_a.explanation_source == "llm" else "**规则生成的理由**　")
                            + rep_a.explanation)
                for a in sorted(members, key=lambda x: grp.RISK_ORDER[x.risk]):
                    ra = v["records"][a.mark_id]
                    html(f'<div class="cand-meta" style="margin-top:.5rem">{style.badge(a.risk, RISK_LABEL[a.risk])}　'
                         f'<b>{esc(a.mark_id)}</b>　<b>商品</b> {esc(gr.LABEL[a.goods_rel])}　<b>在先</b> {esc(ps.LABEL[a.prior])}'
                         f'　<b>申请日</b> {ra.app_date or "未知"}</div>')
                    html('<ul class="facts">' + "".join(f"<li>{esc(v['facts'][f].text)}</li>" for f in a.fact_ids
                                                        if v["facts"][f].kind in ("goods", "prior", "data_gap")) + "</ul>")
                    st.caption(f"原始记录：{ra.source_ref or '—'}；来源：{ra.source}；数据截至 {ra.snapshot_date}")
                for h in rep_a.hints:
                    st.caption(f"提示（历史交叉检索，不参与定级）：{h}")
    st.write("")
    if st.button("确认候选，生成报告", type="primary"):
        keep = [m for g in v.get("display_groups", []) if ss.get(f"keep_g_{g['group']}", True) for m in g["marks"]]
        stream(Command(resume={"keep": keep}))
        ss.stage = "report"
        st.rerun()

# ---------------- ⑤ 报告 ----------------
elif ss.stage == "report":
    v = values()
    rep = v["report"]
    top = st.columns([5, 1.4])
    top[0].markdown(style.section(rep["title"], f"生成于 {rep['generated_at']}"), unsafe_allow_html=True)
    with open(v["report_path"], "rb") as f:
        top[1].download_button("下载 Word 报告", f.read(), file_name=f"商标筛查报告_{rep['query_mark']}.docx",
                               mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                               type="primary", use_container_width=True)
    if rep["flagged"]:
        html(style.note("<b>引用校验未通过</b>（已重写 2 次）。以下结论需人工处理，不得直接使用：<br>"
                        + "<br>".join(f"· {esc(e)}" for e in rep["errors"]), "err"))
    if rep["degraded"]:
        html(style.note("<b>降级输出</b>　" + esc("；".join(rep["degraded_notes"])), "warn"))
    html(style.kv([("评估日期", rep["eval_date"]), ("申请日", rep["our_app_date"]), ("适用法律", rep["law_version"]),
                   ("检索类别", "第 " + "、".join(map(str, rep["classes"])) + " 类"),
                   ("商品项", "、".join(g["name"] for g in rep["goods"]))]))
    html(style.kpis([(len(rep[k]), RISK_LABEL[k], "名称组", style.RISK_CLASS[k]) for k in RISK_ORDER]
                    + [(len(rep["exclusions"]), "用户剔除", "件", "")]))

    def claim_block(c: dict, cls: str) -> None:
        html(style.claim(c["conclusion"], c["facts"], [b["citation"] for b in c["basis"]], cls,
                         template=c["source"] == "code" and c["type"] != "data_gap"))

    with st.container(border=True):
        html('<div class="side-h" style="margin-top:.2rem">总结论</div>')
        if rep["overall"]:
            claim_block(rep["overall"], "overall")

    titles = {"high": "高风险候选", "medium": "中风险候选", "needs_check": "待核实候选"}
    hints = {"needs_check": "缺数据，不等于低风险"}
    for key in ("high", "medium", "needs_check"):
        if not rep[key]:
            continue
        html(style.section(titles[key], hints.get(key, f"{len(rep[key])} 个名称组")))
        for it in rep[key]:
            with st.container(border=True):
                html(f'<div class="cand-head"><span class="mark">{esc(it["text"])}</span>{style.badge(key, it["risk_label"])}'
                     + (f'<span class="tag">同名 {it["count"]} 件</span>' if it["count"] > 1
                        else f'<span class="id">{esc(it["mark_id"])}</span>')
                     + ('<span class="tag">示例数据</span>' if it["is_simulated"] else "")
                     + ('<span class="tag warn">模型建议复核</span>' if it["flag_review"] else "") + "</div>")
                for c in it["claims"]:
                    claim_block(c, "check" if c["type"] == "data_gap" else style.RISK_CLASS[key])
                if it["explanation"]:
                    st.caption(("模型解释：" if it["explanation_source"] == "llm" else "规则生成的理由：") + it["explanation"])
                with st.expander(f"各件注册（{it['count']}）"):
                    st.dataframe(pd.DataFrame([{"编号": m["mark_id"], "风险": m["risk_label"], "在先状态": m["prior"],
                                                "商品关系": m["goods_rel"], "申请日": m["app_date"],
                                                "原始记录": m["source_ref"]} for m in it["marks"]]),
                                 hide_index=True, use_container_width=True)

    if rep["low"]:
        html(style.section("低风险候选", f"{len(rep['low'])} 个"))
        st.dataframe(pd.DataFrame([{"商标": i["text"], "件数": i["count"],
                                    "编号": "、".join(m["mark_id"] for m in i["marks"][:6]) + ("等" if i["count"] > 6 else ""),
                                    "说明": i["explanation"]} for i in rep["low"]]),
                     hide_index=True, use_container_width=True)
    html(style.section("附录", "用户剔除的候选、依据原文、执行过程"))
    with st.expander(f"用户剔除的候选（{len(rep['exclusions'])}）", expanded=bool(rep["exclusions"])):
        if rep["exclusions"]:
            st.dataframe(pd.DataFrame([{"商标": e["text"], "编号": e["mark_id"], "原风险等级": e["risk_label"],
                                        "剔除时间": e["at"]} for e in rep["exclusions"]]),
                         hide_index=True, use_container_width=True)
        else:
            st.caption("没有剔除任何候选。")
    with st.expander(f"相关典型案例（{len(rep.get('cases', []))}，仅供参考，不作为依据）"):
        if not rep.get("cases"):
            st.caption("案例库中没有文字相近的案例。")
        for c in rep.get("cases", []):
            st.markdown(f"**{c['case_id']}**（{c['decision_date']}）　申请商标“{c['applicant_mark']}”，结果：{c['outcome']}")
            st.caption(c["reason"])
            for f in c["findings"]:
                st.write("· " + f)
            st.caption(f"来源：{c['source_url']}")
            st.divider()
    with st.expander(f"依据原文与来源（{len(rep['basis_appendix'])}）"):
        for b in rep["basis_appendix"]:
            st.markdown(f"**{b['citation']}**")
            st.write(b["text"])
            st.caption(f"依据 ID {b['id']} · 施行 {b['effective_from']} 至 {b['effective_to']} · 来源：{b['source']}"
                       + (f"\n\n版本对应：{b['version_note']}" if b["version_note"] else ""))
            st.divider()
    with st.expander("执行过程与耗时"):
        t = v.get("timings", {})
        html(style.kv([("规则阶段", f"{t.get('rule_stage', '—')} 秒"), ("模型解释", f"{t.get('explain', '—')} 秒"),
                       ("生成结论", f"{t.get('compose', '—')} 秒"), ("重写次数", v.get("retry_count", 0))]))
        st.dataframe(pd.DataFrame([{"节点": NODE_LABEL.get(x["node"], x["node"]),
                                    "结果": trace_text(x)}
                                   for x in v.get("trace", [])]), hide_index=True, use_container_width=True)
    html(f'<div class="side-cap" style="margin-top:1.2rem">{esc(rep["disclaimer"])}</div>')
    st.write("")
    if st.button("评估另一个商标"):
        restart()
