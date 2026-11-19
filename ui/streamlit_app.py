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

from app import cache, db, llm  # noqa: E402
from app.config import settings  # noqa: E402
from app.graph import build_graph  # noqa: E402
from app.rules import goods_relation as gr  # noqa: E402
from app.rules import prior_status as ps  # noqa: E402
from app.rules.risk_table import LEVEL_LABEL, RISK_LABEL  # noqa: E402
from app.tools import basis  # noqa: E402
from app.tools import goods as goods_tool  # noqa: E402
from ui import style  # noqa: E402

st.set_page_config(page_title="商标近似评估智能体", page_icon="§", layout="wide")
st.markdown(style.css(), unsafe_allow_html=True)

CHANNEL_LABEL = {"exact": "完全相同", "contains": "包含", "glyph": "字形", "pinyin": "读音",
                 "pinyin_fuzzy": "模糊音", "meaning": "含义", "transpose": "字序颠倒", "redup": "叠字"}
RECALL_LABEL = {"recall_exact": "精确文字", "recall_glyph": "字形", "recall_pinyin": "读音",
                "recall_variant": "字序与叠字", "recall_meaning": "含义"}
NODE_LABEL = {"parse": "要素解析", "confirm_goods": "确认商品项", "plan_search": "检索规划（大模型）",
              **RECALL_LABEL, "merge": "按名称归组排序", "load_citations": "载入引证",
              "assess": "规则引擎（事实与参考等级）", "judge": "大模型判定（规则护栏）", "explain": "模型解释", "confirm_candidates": "确认候选",
              "compose": "生成结论（RAG 检索法条）", "verify": "引用校验", "render": "渲染报告", "flag_output": "标红输出"}
RISK_ORDER = ["high", "medium", "needs_check", "low"]


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
    if n == "plan_search":
        if not t.get("queries"):
            return "未使用大模型，只检索原文"
        return f"第 {t.get('round')} 轮：" + "；".join(t["queries"])
    if n == "judge":
        return (f"判定 {t.get('judged', 0)} 组（上限外 {t.get('capped', 0)} 组沿用规则）；"
                f"护栏修正 {t.get('guardrail_fixed', 0)} 件；与规则不一致 {t.get('disagree', 0)} 件 · {t.get('seconds', 0)} 秒")
    if n == "load_citations":
        return f"找到 {t.get('found', 0)} 个引证，缺失 {t.get('missing', 0)} 个"
    if n == "explain":
        return f"模型解释 {t.get('llm_ok', 0)} 条，降级 {t.get('fallback', 0)} 条 · {t.get('seconds', 0)} 秒"
    if n == "confirm_candidates":
        return f"保留 {t.get('kept', 0)} 个，剔除 {t.get('excluded', 0)} 个"
    if n == "compose":
        return (f"{t.get('claims', 0)} 条结论；RAG 检索补充依据 {t.get('rag_basis', 0)} 条 · {t.get('seconds', 0)} 秒"
                + ("" if t.get("llm") else " · 模板生成"))
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
STAGE_INDEX = {"input": 0, "cached": 0, "goods": 1, "candidates": 2, "report": 3}


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
    if llm.unavailable_reason(v.get("degraded_notes", [])):         # 大模型整体不可用：醒目说明，由规则兜底
        html(style.empty("degraded", "大模型暂时不可用，本次结论由规则引擎给出；原因见下方提示。"))
    if v.get("classes") and (miss := db.uncovered_note(v["classes"], pending=[g.name for g in v.get("goods", []) if not g.code])):
        html(style.note(f"<b>检索范围</b>　{esc(miss)}", "warn"))
    for n in v.get("degraded_notes", []):
        if n.startswith("为控制时延"):
            html(style.note(esc(n), "info"))
        else:
            html(style.note(f"<b>降级</b>　{esc(n)}", "warn"))


def restart() -> None:
    for k in list(ss.keys()):
        del ss[k]
    st.rerun()


def start(payload: dict, fresh: bool = False) -> None:
    """开始一次新的评估。fresh=True 为“重新评估”：大模型调用不读缓存。"""
    global cfg
    ss.tid = uuid.uuid4().hex[:12]
    cfg = {"configurable": {"thread_id": ss.tid}}
    ss.pop("cached", None)
    stream({**payload, "fresh": fresh})
    ss.stage = "goods"
    st.rerun()


def open_cached(k: str) -> None:
    """打开缓存里的报告（第一层缓存）。

    Word 文件按缓存的报告内容重新导出，这样水印、版式等导出格式的改进对历史报告同样生效；
    重新导出失败时才用当时存下的文件。
    """
    from app.nodes.render import write_pdfs

    r = cache.report_get(k)
    if r is None:
        st.error("这份报告已无法读取（系统升级后旧缓存失效），请重新评估。")
        return
    p = r["payload"]
    stem = Path(__file__).resolve().parent.parent / "outputs" / f"cached_{k[:12]}"
    stem.parent.mkdir(exist_ok=True)
    try:
        path, concise = write_pdfs(p["report"], stem)
    except Exception:                            # 重新导出失败时用当时存下的标准版文件
        path, concise = stem.with_name(stem.name + ".pdf"), None
        path.write_bytes(r["docx"])
    ss.cached = {**p, "report_path": str(path), "report_path_concise": str(concise) if concise else "",
                 "cached_at": r["created"]}
    ss.payload = p.get("payload") or ss.get("payload")
    ss.stage = "report"
    st.rerun()


def save_report(v: dict, keep: list[str]) -> None:
    """报告生成后存入第一层缓存；降级或引用校验未通过的报告不存，避免把不稳定的结果当成定论复用。"""
    rep = v.get("report") or {}
    if not ss.get("payload") or rep.get("flagged") or rep.get("degraded"):
        return
    full = {**ss.payload, "goods": [(g.code, g.name) for g in v.get("goods", [])], "keep": sorted(keep)}
    payload = {"report": rep, "timings": v.get("timings", {}), "trace": v.get("trace", []),
               "retry_count": v.get("retry_count", 0), "payload": ss.payload,
               "prefix_key": cache.key(ss.payload, cache.versions()),
               "goods_names": [g.name for g in v.get("goods", [])]}
    try:
        docx = Path(v["report_path"]).read_bytes()
        cache.report_put(cache.report_key(full), ss.payload["scenario"], ss.payload["query_mark"],
                         rep.get("title", ""), payload, docx)
    except Exception as e:                       # 缓存失败不影响本次报告
        st.caption(f"报告未能存入缓存：{e}")


# ---------------- 侧边栏 ----------------
with st.sidebar:
    html(style.brand())
    cov = db.coverage()
    if cov["real"].get("source") == "open":
        html(f'<div class="side-h">{style.icon("ic-database")}商标库</div>'
             f'<div class="side-row"><span>开放数据（真实）</span><b>{cov["real"]["count"]:,}</b></div>'
             f'<div class="side-row"><span>覆盖类别</span><b>{esc(cov["real"]["classes"])}</b></div>'
             f'<div class="side-row"><span>增量截至</span><b>{cov["real"]["date"]}</b></div>'
             '<div class="side-cap">数据来自国家知识产权局商标开放数据。在先状态由公告日期推定，'
             '法律状态须另行核实。</div>')
    else:
        html('<div class="side-h">数据覆盖范围</div>'
             f'<div class="side-row"><span>本地真实记录</span><b>{cov["real"]["count"]}</b></div>'
             '<div class="side-cap">未接入正式商标库（TM_OPEN_DB 或检索索引缺失），只能检索决定书导入的少量记录。</div>')
    html(f'<div class="side-h">{style.icon("ic-model")}智能体</div>'
         + f'<div class="side-row"><span>大模型</span><b>{esc(settings.llm_model) if llm.available() else "未配置"}</b></div>'
         '<div class="side-row"><span>负责</span><b>判定近似 · 写结论</b></div>'
         '<div class="side-row"><span>兜底</span><b>规则护栏</b></div>'
         f'<div class="side-h">{style.icon("ic-scale")}法律依据</div>'
         '<div class="side-row"><span>商标法</span><b>按评估日期选版本</b></div>'
         '<div class="side-row"><span>审查审理指南</span><b>2021 年版</b></div>'
         '<div class="side-row"><span>参考判例</span><b>国知局评审文书</b></div>')
    if not llm.available():
        html('<div class="side-cap">未配置 .env 中的 LLM_API_KEY / LLM_MODEL，解释和结论将由代码生成。</div>')
    recent = cache.report_recent(8)
    if recent:
        html(f'<div class="side-h">{style.icon("ic-history")}最近的报告</div>')
        for r in recent:
            label = f"{r['query']} · {'复审' if r['scenario'] == 'rejection_review' else '筛查'} · {r['created'][5:16].replace('T', ' ')}"
            if st.button(label, key=f"recent_{r['key']}", use_container_width=True):
                open_cached(r["key"])
    st.write("")
    if st.button("重新开始", use_container_width=True):
        restart()

if ss.stage in ("input", "cached"):
    _real = cov["real"]
    html(style.hero(facts=[("ic-database", f"{_real['count'] / 10000:,.0f} 万件", "国知局开放数据")
                           if _real.get("source") == "open" else ("ic-database", str(_real["count"]), "本地记录"),
                           ("ic-model", "大模型", "逐组判定 · 规则护栏"),
                           ("ic-scale", "带版本", "商标法与审查指南依据")]))
else:
    html(style.hero(compact=True))
html(style.steps(STAGE_INDEX[ss.stage]))

# ---------------- ① 输入 ----------------
if ss.stage == "input":
    left, right = st.columns([3, 2], gap="large")
    with right:
        html(style.how_it_works([
            ("多路召回", "精确文字、包含、字形、读音、字序与叠字、含义六路检索在先商标，按名称归组排序。"),
            ("逐组判定", "大模型结合指南判断标识是否近似、注册风险多大；规则护栏校正越界结论。"),
            ("可追溯的报告", "每条结论附事实与带施行期间的法条、指南依据，并附同类情形的官方判例。"),
        ], "检索范围限定在开放数据覆盖的第 29、30、32、43 类；在先状态由公告日期推定，法律状态须另行核实。"))
    with left:
        mode = st.segmented_control("场景", ["pre_filing", "rejection_review"], default="pre_filing",
                                    format_func={"pre_filing": "申请前筛查", "rejection_review": "驳回复审逐项比对"}.get,
                                    label_visibility="collapsed") or "pre_filing"
        review = mode == "rejection_review"
        if review:
            html('<div class="lead">录入驳回通知中的引证商标编号，系统逐件比对标识、商品和在先状态，给出每件的比对结论。'
                 '不做复审理由或论证。</div>')
        else:
            html('<div class="lead">填写拟申请的商标文字和要用在哪些商品或服务上，系统检索在先商标并评估注册风险。</div>')
        with st.form("input", border=False):
            c1, c2 = st.columns(2)
            mark = c1.text_input("商标文字（必填）" if not review else "申请商标文字（必填）", key="in_mark", placeholder="例如：茗悦")
            desc = c2.text_input("商品或服务（必填）" if not review else "指定商品或服务（必填）", key="in_desc",
                                 placeholder="用顿号或逗号分隔，例如：茶饮料、奶茶")
            citations = ""
            if review:
                citations = st.text_area("引证商标编号（必填，每行一个，或用逗号分隔）", placeholder="例如：\n19266072\n20266296")
            else:
                meaning = st.text_input("商标含义（可选）", placeholder="不填则由大模型生成；用于义近召回")
            c3, c4, c5 = st.columns(3)
            eval_date = c3.date_input("评估日期（默认今天）", value=date.today(), help="决定适用的法律版本。切到 2027 年可以看到新法条号。")
            app_date = c4.date_input("实际申请日（必填）" if review else "预计申请日（可选）", value=None,
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
                payload = {"scenario": mode, "query_mark": mark.strip(), "goods_desc": desc.strip(),
                           "eval_date": eval_date, "our_app_date": app_date or eval_date, "data_scope": scope}
                if review:
                    payload.update(user_citations=cites, our_priority_date=prio_date)
                else:
                    payload["query_meaning"] = meaning.strip()
                ss.payload = payload
                ss.cache_hits = cache.report_find(payload)
                if ss.cache_hits:                    # 同样的输入评估过：先让用户选择复用还是重新评估
                    ss.stage = "cached"
                    st.rerun()
                start(payload)

# ---------------- ①' 同样的查询评估过 ----------------
elif ss.stage == "cached":
    p = ss.payload
    html(style.section(f"“{p['query_mark']}”评估过", "输入、商标数据、提示词和模型版本都与上次相同"))
    html('<div class="lead">可以直接查看上次的报告；也可以重新评估（重新调用大模型，结论可能与上次略有不同）。'
         '想换商品项时选“按新的商品项评估”，没有变化的在先商标会复用上次的判定。</div>')
    for h in ss.cache_hits:
        with st.container(border=True):
            c1, c2 = st.columns([3, 1.3])
            c1.markdown(f"**{esc(h['title'])}**　生成于 {h['created'].replace('T', ' ')}<br>"
                        f"<span class='side-cap'>商品项：{esc('、'.join(h['goods']) or '—')}</span>", unsafe_allow_html=True)
            if c2.button("查看报告", key=f"open_{h['key']}", type="primary", use_container_width=True):
                open_cached(h["key"])
    c1, c2 = st.columns(2)
    if c1.button("按新的商品项评估", use_container_width=True):
        start(p)
    if c2.button("重新评估", use_container_width=True, help="不复用缓存，重新调用大模型"):
        start(p, fresh=True)

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
        extra = st.text_input("选录之外的商品（可选）", value="、".join(g.name for g in proposal if not g.code),
                              placeholder="逗号分隔",
                              help="会标为“待核实”。与它相关的候选不会被判为低风险。")
        html('<div class="side-cap">检索类别由这里选中的商品项决定：它们所在的类别，加上区分表注释关联到的类别。</div>')
        if miss := db.uncovered_note({options[c]["nice_class"] for c in chosen}, pending=goods_tool.split_desc(extra)):
            html(style.note(f"<b>检索范围</b>　{esc(miss)}", "warn"))
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
    if v.get("search_variants"):
        html(style.note("<b>检索规划（大模型）</b>　除原文外还检索了：" + "；".join(
            f"“{esc(q['text'])}”（{esc(q['why'])}，命中 {q.get('hits', 0)} 件）" for q in v["search_variants"]), "info"))
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
    html(f'<div class="lead">检索与规则初评耗时 <b>{tm.get("rule_stage", "—")} 秒</b>；'
         f'大模型逐组判定耗时 <b>{tm.get("judge", "—")} 秒</b>。</div>')

    from app.rules import groups as grp

    groups_ = [(g["group"], [assessments[m] for m in g["marks"] if m in assessments]) for g in v.get("display_groups", [])]
    gcounts = {r: sum(1 for _, ms in groups_ if ms and grp.group_risk(ms) == r) for r in RISK_ORDER}
    html(style.section("确认候选", f"{len(groups_)} 个名称组、{len(order)} 件注册；完全同名置顶，其余按标识相似程度排序"))
    html(style.kpis([(gcounts[r], RISK_LABEL[r], "名称组（取组内最高）", style.RISK_CLASS[r]) for r in RISK_ORDER]))
    if not order:
        html(style.empty("none", "检索范围内没有召回任何候选，可以直接生成报告。"))
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
        with st.container(border=True, key=f"cand_{style.RISK_CLASS[grp.group_risk(members)]}_{n}"):
            c0, c1, c2 = st.columns([0.45, 8, 1.2])
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
                + ('<span class="tag llm">大模型判定</span>' if rep_a.decided_by == "llm" else '<span class="tag">规则判定</span>')
                + (f'<span class="tag warn">与规则不一致（规则：{RISK_LABEL.get(rep_a.rule_risk, "")}）</span>'
                   if any(a.disagree for a in members) else "")
                + ('<span class="tag warn">护栏修正</span>' if any(a.guardrail for a in members) else "") + "</div>"
                f'<div>{chips}</div><div class="cand-ev">{esc(evidence)}</div>'
                f'<div class="cand-meta">{esc(mix)}</div>', unsafe_allow_html=True)
            c2.toggle("保留", value=True, key=f"keep_g_{g}")
            with c1.expander("判定理由、参考依据与各件注册"):
                st.markdown(("**大模型判定理由**　" if rep_a.explanation_source == "llm" else "**规则生成的理由**　")
                            + rep_a.explanation)
                for a in members:
                    if a.guardrail:
                        st.caption(f"{a.mark_id}　{a.guardrail}")
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
        save_report(values(), keep)
        ss.stage = "report"
        st.rerun()

# ---------------- ⑤ 报告 ----------------
elif ss.stage == "report":
    html(style.report_watermark())
    v = ss.get("cached") or values()
    rep = v["report"]
    if ss.get("cached"):
        cc = st.columns([3, 1.3])
        cc[0].markdown(style.note(f"<b>复用缓存</b>　这是 {esc(v['cached_at'].replace('T', ' '))} 的评估结果；"
                                  "输入、商标数据、提示词和模型版本都与当时相同。", "info"), unsafe_allow_html=True)
        if ss.get("payload") and cc[1].button("重新评估", use_container_width=True, help="不复用缓存，重新调用大模型"):
            start(ss.payload, fresh=True)
    def claim_block(c: dict, cls: str) -> None:
        html(style.claim(c["conclusion"], c["facts"], [b["citation"] for b in c["basis"]], cls,
                         template=c["source"] == "code" and c["type"] != "data_gap"))

    with st.container(border=True, key="doc"):
        top = st.columns([3, 1.3])
        top[0].markdown(style.doc_head(rep["title"], f"生成于 {rep['generated_at']}"), unsafe_allow_html=True)
        if v.get("report_path_concise") and Path(v["report_path_concise"]).exists():
            top[1].download_button("下载简洁版 PDF", Path(v["report_path_concise"]).read_bytes(),
                                   file_name=f"商标筛查报告_{rep['query_mark']}_简洁版.pdf", mime="application/pdf",
                                   type="primary", use_container_width=True, help="1–2 页：结论、需要关注的在先商标及主要理由")
        top[1].download_button("下载标准版 PDF", Path(v["report_path"]).read_bytes(),
                               file_name=f"商标筛查报告_{rep['query_mark']}_标准版.pdf", mime="application/pdf",
                               use_container_width=True, help="完整报告：事实、各件注册、参考判例、依据原文")
        if rep["flagged"]:
            html(style.note("<b>引用校验未通过</b>（已重写 2 次）。以下结论需人工处理，不得直接使用：<br>"
                            + "<br>".join(f"· {esc(e)}" for e in rep["errors"]), "err"))
        if rep["degraded"]:
            if llm.unavailable_reason(rep["degraded_notes"]):
                html(style.empty("degraded", "大模型暂时不可用，本报告的结论由规则引擎给出。"))
            html(style.note("<b>降级输出</b>　" + esc("；".join(rep["degraded_notes"])), "warn"))
        if miss := db.uncovered_note(rep["classes"], rep.get("coverage"), [g["name"] for g in rep["goods"] if not g.get("code")]):
            html(style.note(f"<b>检索范围</b>　{esc(miss)}", "warn"))
        html(style.kv([("评估日期", rep["eval_date"]), ("申请日", rep["our_app_date"]), ("适用法律", rep["law_version"]),
                       ("检索类别", "第 " + "、".join(map(str, rep["classes"])) + " 类"),
                       ("商品项", "、".join(g["name"] for g in rep["goods"]))]))
        html(style.kpis([(len(rep[k]), RISK_LABEL[k], "名称组", style.RISK_CLASS[k]) for k in RISK_ORDER]
                        + [(len(rep["exclusions"]), "用户剔除", "件", "")]))
        html('<div class="label-h">总结论</div>')
        if rep["overall"]:
            claim_block(rep["overall"], "overall")

    def pattern_cases(pc: dict | None) -> None:
        """同类情形的参考判例：官方在同一种比对情形下判近似和判不近似的例子。"""
        if not pc or not (pc["similar"] or pc["dissimilar"] or pc["note"]):
            return
        n = len(pc["similar"]) + len(pc["dissimilar"])
        if not n:                                 # 没有可列的判例时只给一行说明，不放空的折叠框
            st.caption(f"同类情形参考判例：{pc['note']}。")
            return
        with st.expander(f"同类情形参考判例：{pc['pattern']}（{n} 件，仅供参考）"):
            for title, items in (("官方认定近似", pc["similar"]), ("官方认定不近似", pc["dissimilar"])):
                if not items:
                    continue
                st.markdown(f"**{title}**")
                for c in items:
                    st.markdown(f"“{esc(c['applicant'])}” 与 “{esc(c['cited'])}”"
                                + (f"　—　{esc(c['excerpt'])}" if c["excerpt"] else ""))
                    st.caption(f"[{c['case_id']}]({c['source_url']}) · {c['doc_type']} · {c['decision_date']}")
            if pc["note"]:
                st.caption(pc["note"] + "。")
            st.caption("判例只用来看官方在同类情形下如何区分，不作为依据，也不影响本报告的风险等级。")


    titles = {"high": "高风险候选", "medium": "中风险候选", "needs_check": "待核实候选"}
    hints = {"needs_check": "缺数据，不等于低风险"}
    for key in ("high", "medium", "needs_check"):
        if not rep[key]:
            continue
        html(style.section(titles[key], hints.get(key, f"{len(rep[key])} 个名称组")))
        for i, it in enumerate(rep[key]):
            with st.container(border=True, key=f"cand_{style.RISK_CLASS[key]}_r{i}"):
                html(f'<div class="cand-head"><span class="mark">{esc(it["text"])}</span>{style.badge(key, it["risk_label"])}'
                     + (f'<span class="tag">同名 {it["count"]} 件</span>' if it["count"] > 1
                        else f'<span class="id">{esc(it["mark_id"])}</span>')
                     + ('<span class="tag">示例数据</span>' if it["is_simulated"] else "")
                     + ('<span class="tag llm">大模型判定</span>' if it["decided_by"] == "llm" else '<span class="tag">规则判定</span>')
                     + (f'<span class="tag warn">与规则不一致（规则：{esc(it["rule_risk_label"])}）</span>' if it["disagree"] else "")
                     + "</div>")
                for gnote in it["guardrails"]:
                    st.caption(gnote)
                for c in it["claims"]:
                    claim_block(c, "check" if c["type"] == "data_gap" else style.RISK_CLASS[key])
                if it["explanation"]:
                    st.caption(("模型解释：" if it["explanation_source"] == "llm" else "规则生成的理由：") + it["explanation"])
                with st.expander(f"各件注册（{it['count']}）"):
                    st.dataframe(pd.DataFrame([{"编号": m["mark_id"], "风险": m["risk_label"], "在先状态": m["prior"],
                                                "商品关系": m["goods_rel"], "申请日": m["app_date"],
                                                "原始记录": m["source_ref"]} for m in it["marks"]]),
                                 hide_index=True, use_container_width=True)
                pattern_cases(it.get("pattern_cases"))

    if rep["low"]:
        html(style.section("低风险候选", f"{len(rep['low'])} 个"))
        st.dataframe(pd.DataFrame([{"商标": i["text"], "件数": i["count"],
                                    "编号": "、".join(m["mark_id"] for m in i["marks"][:6]) + ("等" if i["count"] > 6 else ""),
                                    "说明": i["explanation"]} for i in rep["low"]]),
                     hide_index=True, use_container_width=True)
    # ---- 法律问答（RAG）：只提供信息，不改变上面的风险结论 ----
    html(style.section("法律问答", "检索法条与审查指南回答追问，每个法律判断附出处；不改变风险结论"))
    with st.container(border=True):
        ss.setdefault("qa", [])
        first = next((it["text"] for k in ("high", "medium") for it in rep[k]), None)
        samples = ([f"为什么“{first}”会有风险？"] if first else []) + \
                  ["如果申请被驳回，可以怎么办？期限是多久？", "在先商标已经注销，多久以后我才能注册？"]
        def _pick() -> None:                      # 点选示例问题后清空选择，便于再次点选
            ss.qa_pending, ss.qa_pill = ss.qa_pill, None
        st.pills("示例问题", samples, key="qa_pill", on_change=_pick, label_visibility="collapsed")
        picked = ss.pop("qa_pending", None)
        with st.form("qa_form", clear_on_submit=True, border=False):
            fc = st.columns([5, 1.2])
            typed = fc[0].text_input("问题", placeholder="例如：同一天申请的近似商标怎么处理？", label_visibility="collapsed")
            sent = fc[1].form_submit_button("提问", type="primary", use_container_width=True)
        question = picked or (typed if sent and typed.strip() else None)
        if question:
            from app import qa
            with st.spinner("检索条文并生成回答…"):
                ss.qa.append({"question": question, **qa.answer(question, rep, ss.qa)})
        for item in reversed(ss.qa):
            st.markdown(f"**问：{item['question']}**")
            if item.get("resolved") and item["resolved"] != item["question"]:
                st.caption(f"理解为：{item['resolved']}")
            st.markdown(item["answer"])
            for w in item["warnings"]:
                st.caption(f"⚠ {w}")
            st.caption("　→　".join(f"{x['step']}：{x['detail']}" for x in item.get("steps", [])))
            if item["sources"]:
                with st.expander(f"引用的条文（{len(item['sources'])}）"):
                    for src in item["sources"]:
                        st.markdown(f"**{src['citation']}**")
                        st.caption(src["text"])
            st.divider()
        if ss.qa:
            st.caption("回答由大模型根据检索到的条文生成，仅供参考，不构成法律意见。")

    html(style.section("附录", "用户剔除的候选、依据原文、执行过程"))
    with st.expander(f"用户剔除的候选（{len(rep['exclusions'])}）", expanded=bool(rep["exclusions"])):
        if rep["exclusions"]:
            st.dataframe(pd.DataFrame([{"商标": e["text"], "编号": e["mark_id"], "原风险等级": e["risk_label"],
                                        "剔除时间": e["at"]} for e in rep["exclusions"]]),
                         hide_index=True, use_container_width=True)
        else:
            st.caption("没有剔除任何候选。")
    with st.expander(f"依据原文与来源（{len(rep['basis_appendix'])}）"):
        for b in rep["basis_appendix"]:
            st.markdown(f"**{b['citation']}**" + ("　`RAG 检索补充`" if b.get("from_rag") else ""))
            st.write(b["text"])
            st.caption(f"依据 ID {b['id']} · 施行 {b['effective_from']} 至 {b['effective_to']} · 来源：{b['source']}"
                       + (f"\n\n版本对应：{b['version_note']}" if b["version_note"] else ""))
            st.divider()
    with st.expander("执行过程与耗时"):
        t = v.get("timings", {})
        html(style.kv([("检索与规则初评", f"{t.get('rule_stage', '—')} 秒"), ("大模型判定", f"{t.get('judge', '—')} 秒"),
                       ("生成结论", f"{t.get('compose', '—')} 秒"), ("重写次数", v.get("retry_count", 0))]))
        st.dataframe(pd.DataFrame([{"节点": NODE_LABEL.get(x["node"], x["node"]),
                                    "结果": trace_text(x)}
                                   for x in v.get("trace", [])]), hide_index=True, use_container_width=True)
    html(f'<div class="side-cap" style="margin-top:1.2rem">{esc(rep["disclaimer"])}</div>')
    st.write("")
    if st.button("评估另一个商标"):
        restart()
