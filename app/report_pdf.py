"""PDF 报告：标准版（与 Word 报告同样完整）和简洁版（1–2 页摘要），都由 render.build_report 的同一份数据生成。

排版规范与 Word 报告一致：正文宋体，标题黑体，标题黑色；风险等级着色（高红、中蓝、低绿、待核实紫）；
每页有系统水印（app/assets/report-watermark.png）和页眉系统名。字体嵌入并子集化，换电脑打开效果不变。

字体查找顺序：环境变量 TM_PDF_FONT_BODY / TM_PDF_FONT_HEAD（可写“路径#序号”指定字体集合中的一款），
macOS 系统宋体 / 黑体，Linux 的 Noto CJK（Docker 镜像里安装 fonts-noto-cjk）。
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from fpdf import FPDF, FontFace
from fpdf.enums import WrapMode

from app import db

logging.getLogger("fontTools").setLevel(logging.ERROR)     # 子集化时对排版表的提示，不影响中文显示

WATERMARK_IMG = Path(__file__).resolve().parent / "assets" / "report-watermark.png"
SYSTEM_NAME = "商标近似评估智能体"
RISK_RGB = {"高风险": (192, 31, 31), "中风险": (31, 78, 154), "低风险": (47, 122, 82), "待核实": (91, 79, 196)}
INK, MUTED, BRASS, LINE = (20, 20, 20), (102, 112, 133), (176, 141, 87), (214, 208, 196)
HEAD_FILL = (243, 240, 233)

# 字体集合中简体中文常规体的序号：macOS 宋体集合第 6 款为 Songti SC Regular、黑体集合第 1 款为 Heiti SC Medium；
# Noto CJK 的 .ttc 依次为 日、韩、简、繁、港
BODY_FONTS = ["/System/Library/Fonts/Supplemental/Songti.ttc#6",
              "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc#2",
              "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc#2"]
HEAD_FONTS = ["/System/Library/Fonts/STHeiti Medium.ttc#1",
              "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc#2",
              "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc#2"]


def _find(env: str, candidates: list[str]) -> tuple[str, int] | None:
    for spec in ([os.environ[env]] if os.environ.get(env) else []) + candidates:
        path, _, idx = spec.partition("#")
        if Path(path).is_file():
            return path, int(idx or 0)
    return None


def risk_rgb(label: str) -> tuple[int, int, int]:
    return next((v for k, v in RISK_RGB.items() if label.startswith(k)), INK)


class ReportPDF(FPDF):
    def __init__(self, title: str, variant: str):
        super().__init__(format="A4")
        self.variant = variant
        self.title_text = title
        self.set_margins(18, 20, 18)
        self.set_auto_page_break(True, margin=18)
        body, head = _find("TM_PDF_FONT_BODY", BODY_FONTS), _find("TM_PDF_FONT_HEAD", HEAD_FONTS)
        body, head = body or head, head or body
        if not body:
            raise RuntimeError("找不到中文字体：请安装 fonts-noto-cjk，或设置 TM_PDF_FONT_BODY / TM_PDF_FONT_HEAD")
        self.add_font("body", "", body[0], collection_font_number=body[1])
        self.add_font("head", "", head[0], collection_font_number=head[1])
        self.set_title(title)
        self.set_creator(SYSTEM_NAME)

    # ---------- 每页：水印、页眉、页脚 ----------
    def header(self):
        if WATERMARK_IMG.exists():                       # 先画水印，正文压在上面
            w = 150
            self.image(str(WATERMARK_IMG), x=(self.w - w) / 2, y=(self.h - w * 0.75) / 2, w=w)
        self.set_font("body", size=8)
        self.set_text_color(*BRASS)
        self.set_xy(self.l_margin, 10)
        tag = "简洁版" if self.variant == "concise" else "标准版"
        self.cell(0, 4, f"{SYSTEM_NAME} · 商标近似风险筛查报告（{tag}）", align="R")
        self.set_draw_color(*LINE)
        self.line(self.l_margin, 15, self.w - self.r_margin, 15)
        self.set_xy(self.l_margin, 20)
        self.set_text_color(*INK)

    def footer(self):
        self.set_y(-12)
        self.set_font("body", size=8)
        self.set_text_color(*MUTED)
        self.cell(0, 4, f"第 {self.page_no()} 页 / 共 {{nb}} 页", align="C")

    # ---------- 排版小工具 ----------
    def heading(self, text: str, level: int = 1):
        size = {0: 18, 1: 14, 2: 12}[level]
        if level and self.get_y() > self.h - 45:          # 标题不要孤零零落在页底
            self.add_page()
        self.ln({0: 0, 1: 5, 2: 3}[level])
        self.set_font("head", size=size)
        self.set_text_color(*INK)
        self.multi_cell(0, size * 0.55, text, wrapmode=WrapMode.CHAR, new_x="LMARGIN", new_y="NEXT")
        self.ln(1.5 if level else 3)

    def para(self, text: str, size: float = 10.5, color=INK, font: str = "body", gap: float = 1.5):
        self.set_font(font, size=size)
        self.set_text_color(*color)
        self.multi_cell(0, size * 0.55, text, wrapmode=WrapMode.CHAR, new_x="LMARGIN", new_y="NEXT")
        self.ln(gap)
        self.set_text_color(*INK)

    def segments(self, parts: list[tuple[str, str, tuple]], size: float = 10.5, gap: float = 1.5):
        """一段里混排几种字体 / 颜色：parts = [(文字, "body"|"head", 颜色), ...]。"""
        h = size * 0.55
        for text, font, color in parts:
            self.set_font(font, size=size)
            self.set_text_color(*color)
            self.write(h, text, wrapmode=WrapMode.CHAR)
        self.ln(h + gap)
        self.set_text_color(*INK)

    def kv(self, label: str, value: str, size: float = 10.5):
        self.segments([(f"{label}：", "head", INK), (str(value), "body", INK)], size=size, gap=1)

    def warn(self, text: str):
        self.para(text, size=10, color=(192, 31, 31), font="head")

    def grid(self, headers: list[str], rows: list[list[str]], widths: tuple, risk_col: int | None = None,
             size: float = 9):
        self.set_font("body", size=size)
        self.set_draw_color(*LINE)
        head_style = FontFace(family="head", fill_color=HEAD_FILL, color=INK)
        with self.table(col_widths=widths, headings_style=head_style, line_height=size * 0.55,
                        text_align="LEFT", wrapmode=WrapMode.CHAR, padding=1.2) as t:
            row = t.row()
            for h in headers:
                row.cell(h)
            for r in rows:
                row = t.row()
                for i, v in enumerate(r):
                    style = FontFace(family="head", color=risk_rgb(v)) if i == risk_col else None
                    row.cell(str(v), style=style)
        self.ln(2)


# ---------- 两种版本共用的部分 ----------
def _basic(pdf: ReportPDF, report: dict, concise: bool):
    goods = "、".join(f"{g['name']}（{g['code'] or '未对应区分表，待核实'}）" for g in report["goods"])
    cov = report["coverage"]["real"]
    data = (f"国家知识产权局商标开放数据，第 {cov['classes']} 类共 {cov['count']:,} 件，增量截至 {cov['date']}"
            if cov.get("source") == "open" else f"真实记录 {cov['count']} 条")
    rows = [("待查商标", report["query_mark"])]
    if not concise:
        rows.append(("商标含义", report["meaning"] or "未提供"))
    rows += [("指定商品或服务", goods), ("检索类别", "、".join(f"第 {c} 类" for c in report["classes"])),
             ("评估日期", report["eval_date"]), ("（模拟）申请日", report["our_app_date"]),
             ("适用法律版本", report["law_version"]), ("数据范围", data)]
    if not concise:
        rows += [("候选", f"共 {report.get('n_groups', 0)} 个名称组、{report.get('n_marks', 0)} 件注册"),
                 ("报告生成时间", report["generated_at"])]
    for k, v in rows:
        pdf.kv(k, v)


def _warnings(pdf: ReportPDF, report: dict):
    if report["flagged"]:
        pdf.warn("【引用校验未通过，需人工处理】以下结论经两次重写仍未通过校验，不得直接使用。")
        for e in report["errors"]:
            pdf.warn(f"· {e}")
    if report["degraded"]:
        pdf.warn("【降级输出】部分内容未使用大模型：" + "；".join(report["degraded_notes"]))
    if miss := db.uncovered_note(report["classes"], report.get("coverage"),
                                 [g["name"] for g in report["goods"] if not g.get("code")]):
        pdf.warn(f"【检索范围】{miss}")


def _distribution(pdf: ReportPDF, report: dict):
    parts = [("风险分布：", "head", INK)]
    for i, (key, label) in enumerate((("high", "高风险"), ("medium", "中风险"), ("needs_check", "待核实"), ("low", "低风险"))):
        parts.append((("　" if i else "") + f"{label} {len(report[key])} 组", "head", risk_rgb(label)))
    pdf.segments(parts, gap=2)


def short_cite(citation: str) -> str:
    """简洁版用的短引用：“《中华人民共和国商标法》（2019年修正）第三十条” → “商标法第三十条”，
    “《商标审查审理指南》（2021年发布）5.2“释义”” → “审查指南 5.2”。法律版本已在基本信息里写明。"""
    import re

    c = re.sub(r"《中华人民共和国商标法实施条例》（[^）]*）", "实施条例", citation)
    c = re.sub(r"《中华人民共和国商标法》（[^）]*）", "商标法", c)
    c = re.sub(r"《商标审查审理指南》（[^）]*）", "审查指南 ", c)
    return re.sub(r"[“\"].*?[”\"]", "", c).strip()


def _cites(claims: list[dict], limit: int = 2) -> str:
    seen = list(dict.fromkeys(short_cite(b["citation"]) for c in claims for b in c["basis"]))
    return "；".join(seen[:limit]) + ("等" if len(seen) > limit else "") if seen else "—"


def _reason(it: dict, limit: int = 90) -> str:
    text = it.get("explanation") or next((c["conclusion"] for c in it["claims"] if c["type"] != "data_gap"), "")
    first = text.split("。")[0]
    first = first if len(first) <= limit else first[:limit] + "…"
    return first + ("。" if first and not first.endswith("…") else "")


# ---------- 简洁版 ----------
def _concise(pdf: ReportPDF, report: dict):
    pdf.heading(report["title"] + "（简洁版）", 0)
    _warnings(pdf, report)
    _basic(pdf, report, concise=True)
    pdf.heading("结论", 1)
    _distribution(pdf, report)
    if report["overall"]:
        pdf.para(report["overall"]["conclusion"])
    items = [(it, key) for key in ("high", "medium", "needs_check") for it in report[key]]
    pdf.heading("需要关注的在先商标", 1)
    if items:
        rows = [[it["text"] + (f"（同名 {it['count']} 件）" if it["count"] > 1 else ""), it["risk_label"],
                 _reason(it), _cites(it["claims"])] for it, _ in items]
        pdf.grid(["在先商标", "风险", "主要理由", "关键依据"], rows, widths=(24, 10, 46, 30), risk_col=1)
    else:
        pdf.para("没有高风险、中风险或待核实的在先商标。")
    if report["low"]:
        names = "、".join(i["text"] for i in report["low"][:12]) + ("等" if len(report["low"]) > 12 else "")
        pdf.segments([("低风险 ", "head", risk_rgb("低风险")), (f"{len(report['low'])} 组：{names}", "body", INK)])
    pdf.para("完整的事实、各件注册明细、参考判例和依据原文见标准版报告。", size=9, color=MUTED)
    pdf.ln(2)
    pdf.para(report["disclaimer"], size=8.5, color=MUTED)


# ---------- 标准版（与 Word 报告内容一致） ----------
def _standard(pdf: ReportPDF, report: dict):
    pdf.heading(report["title"], 0)
    _warnings(pdf, report)
    pdf.heading("一、基本信息", 1)
    _basic(pdf, report, concise=False)
    if report.get("search_variants"):
        pdf.para("检索规划（大模型）：除原文外还检索了 " + "；".join(
            f"“{q['text']}”（{q['why']}，命中 {q.get('hits', 0)} 件）" for q in report["search_variants"]), size=9.5)

    def claim(c: dict):
        pdf.para(c["conclusion"])
        if c["facts"]:
            pdf.para("事实：" + " ".join(f"（{i}）{t}" for i, t in enumerate(c["facts"], 1)), size=9, color=MUTED)
        if c["basis"]:
            pdf.para("依据：" + "；".join(b["citation"] for b in c["basis"]), size=9, color=(29, 51, 82))

    pdf.heading("二、总结论", 1)
    _distribution(pdf, report)
    if report["overall"]:
        claim(report["overall"])

    def items(title: str, group: list[dict]):
        pdf.heading(title, 1)
        if not group:
            pdf.para("无。")
            return
        for it in group:
            tag = "【示例数据】" if it["is_simulated"] else ""
            count = f"，同名注册 {it['count']} 件" if it["count"] > 1 else f"（{it['mark_id']}）"
            pdf.ln(2)
            pdf.segments([(f"{tag}{it['text']}{count} — ", "head", INK), (it["risk_label"], "head", risk_rgb(it["risk_label"]))],
                         size=12, gap=2)
            who = "大模型判定" if it["decided_by"] == "llm" else "规则引擎（未经大模型判定）"
            pdf.para(f"标识相似程度：{it['mark_sim']}（{who}；规则参考：{it['rule_mark_sim']}）。"
                     + ("模型判断与规则不一致，建议人工复核。" if it["disagree"] else ""), size=9.5)
            for g in it["guardrails"]:
                pdf.para(g, size=9.5)
            for c in it["claims"]:
                claim(c)
            pdf.para(("说明（大模型）：" if it["explanation_source"] == "llm" else "说明（规则生成）：") + it["explanation"],
                     size=9.5)
            if it["flag_review"]:
                pdf.warn("大模型建议人工复核该等级。")
            pdf.grid(["编号", "风险", "在先状态", "商品关系", "申请日", "原始记录"],
                     [[m["mark_id"], m["risk_label"], m["prior"], m["goods_rel"], m["app_date"], m["source_ref"] or "—"]
                      for m in it["marks"]], widths=(18, 9, 22, 22, 13, 26), risk_col=1, size=8)
            pc = it.get("pattern_cases")
            if pc and (pc["similar"] or pc["dissimilar"] or pc["note"]):
                pdf.para(f"同类情形参考判例（{pc['pattern']}，仅供参考，不作为依据）", size=9.5, font="head")
                for c in pc["similar"] + pc["dissimilar"]:
                    pdf.para(f"· 官方认定{c['label']}：“{c['applicant']}”与“{c['cited']}”"
                             + (f"——{c['excerpt']}" if c["excerpt"] else "")
                             + f"（{c['case_id']}，{c['decision_date']}）", size=9)
                if pc["note"]:
                    pdf.para(pc["note"] + "。", size=9, color=MUTED)
            for h in it["hints"]:
                pdf.para(f"提示（历史交叉检索，不参与定级）：{h}", size=9, color=MUTED)

    items("三、高风险候选", report["high"])
    items("四、中风险候选", report["medium"])
    items("五、待核实候选（缺数据，不等于低风险）", report["needs_check"])
    if report.get("scenario") == "rejection_review":
        items("六、低风险的引证商标", report["low"])
        if report.get("missing_citations"):
            pdf.warn("以下引证商标在库内找不到，未比对：" + "、".join(report["missing_citations"]))
    else:
        pdf.heading("六、低风险候选", 1)
        if report["low"]:
            pdf.grid(["商标", "件数", "编号", "说明"],
                     [[i["text"], str(i["count"]),
                       "、".join(m["mark_id"] for m in i["marks"][:6]) + ("等" if i["count"] > 6 else ""),
                       i["explanation"]] for i in report["low"]], widths=(18, 7, 30, 55), size=8)
        else:
            pdf.para("无。")

    pdf.heading("附录一、用户剔除的候选", 1)
    if report["exclusions"]:
        for e in report["exclusions"]:
            pdf.segments([(f"{e['text']}（{e['mark_id']}），原风险等级：", "body", INK),
                          (e["risk_label"], "head", risk_rgb(e["risk_label"])),
                          (f"，剔除时间：{e['at']}" + (f"，说明：{e['note']}" if e["note"] else ""), "body", INK)])
    else:
        pdf.para("无。")
    pdf.heading("附录二、依据原文与来源", 1)
    for b in report["basis_appendix"]:
        pdf.para(b["citation"] + ("（RAG 检索补充）" if b.get("from_rag") else ""), size=10.5, font="head")
        pdf.para(b["text"], size=9.5)
        pdf.para(f"依据 ID：{b['id']}；施行：{b['effective_from']} 至 {b['effective_to']}；来源：{b['source']}"
                 + (f"；版本对应：{b['version_note']}" if b["version_note"] else ""), size=8.5, color=MUTED)
    if not report["basis_appendix"]:
        pdf.para("本报告未引用依据。")
    pdf.heading("声明", 1)
    pdf.para(report["disclaimer"], size=9.5)


def export_pdf(report: dict, path, variant: str = "standard") -> None:
    """variant：standard（标准版）或 concise（简洁版）。"""
    pdf = ReportPDF(report["title"], variant)
    pdf.add_page()
    (_concise if variant == "concise" else _standard)(pdf, report)
    pdf.output(str(path))
