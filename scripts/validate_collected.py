"""校验 collected/ 下 Codex 收集的资料，导入正式库之前必须通过。

用法：
    python scripts/validate_collected.py            # 校验全部存在的产出
    python scripts/validate_collected.py decisions  # 只校验某一项（decisions / goods / glyph）

退出码：有错误为 1，只有警告或全部通过为 0。
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COLLECTED = Path(os.getenv("TM_COLLECTED_DIR", ROOT / "collected"))
CHINESE = re.compile(r"[一-鿿]")
CODE = re.compile(r"^C?\d{6}$")
GROUP = re.compile(r"^\d{4}$")


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def err(self, where: str, msg: str) -> None:
        self.errors.append(f"{where}：{msg}")

    def warn(self, where: str, msg: str) -> None:
        self.warnings.append(f"{where}：{msg}")


def _date(r: Report, where: str, value, field: str, required: bool) -> date | None:
    if value is None:
        if required:
            r.err(where, f"{field} 缺失")
        return None
    try:
        d = date.fromisoformat(str(value))
    except ValueError:
        r.err(where, f"{field} 不是 YYYY-MM-DD：{value!r}")
        return None
    if d > date.today():
        r.err(where, f"{field} 晚于今天：{d}")
    return d


def _goods(r: Report, where: str, mark: dict, notes) -> None:
    goods = mark.get("goods")
    if "goods" in mark and goods is None and str(notes or "").strip():
        return
    if not isinstance(goods, list) or not goods:
        r.err(where, "goods 必须是非空数组，未查到时可填 null 并在 notes 里说明")
        return
    for i, g in enumerate(goods, 1):
        w = f"{where}.goods[{i}]"
        if not str(g.get("name") or "").strip():
            r.err(w, "name 为空")
        cls = g.get("nice_class")
        if not isinstance(cls, int) or not 1 <= cls <= 45:
            r.err(w, f"nice_class 必须是 1–45 的整数：{cls!r}")
        grp = g.get("group")
        if grp is not None and not GROUP.match(str(grp)):
            r.err(w, f"group 必须是四位数字或 null：{grp!r}")
        elif grp is not None and isinstance(cls, int) and not str(grp).startswith(f"{cls:02d}"):
            r.err(w, f"group {grp} 与类别 {cls} 不一致")


def _owner(r: Report, where: str, owner) -> None:
    if owner in (None, "", "自然人"):
        return
    # 粗略识别疑似自然人姓名：2–4 个汉字且不含组织机构用字
    org = ("公司", "厂", "店", "社", "中心", "集团", "合作", "协会", "研究", "大学", "学院", "所", "部", "局", "行", "馆", "坊", "园")
    if re.fullmatch(r"[一-鿿]{2,4}", owner) and not any(k in owner for k in org):
        r.warn(where, f"owner“{owner}”像自然人姓名，应写“自然人”")


def check_decisions(r: Report) -> None:
    d = COLLECTED / "decisions"
    files = sorted(d.glob("*.json"))
    if not files:
        r.warn("decisions", "没有找到任何 JSON 文件")
        return
    seen_docs: dict[str, str] = {}
    outcomes = {"近似": 0, "不近似": 0, "未认定": 0}
    classes: dict[int, int] = {}
    references_without_chinese_text = 0
    for f in files:
        where = f.name
        try:
            doc = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            r.err(where, f"不是合法 JSON：{e}")
            continue
        for k in ("doc_type", "doc_no", "authority", "source_url", "applicant_mark", "cited_marks", "outcome"):
            if doc.get(k) in (None, "", []):
                r.err(where, f"{k} 缺失")
        no = str(doc.get("doc_no") or "")
        if no in seen_docs:
            r.err(where, f"文书编号与 {seen_docs[no]} 重复")
        seen_docs[no] = where
        if doc.get("source_url") and not str(doc["source_url"]).startswith(("http://", "https://")):
            r.err(where, "source_url 不是网址")
        dec = _date(r, where, doc.get("decision_date"), "decision_date", True)
        _date(r, where, doc.get("retrieved_at"), "retrieved_at", True)
        if doc.get("outcome") not in ("驳回", "部分驳回", "初步审定"):
            r.err(where, f"outcome 只能是 驳回 / 部分驳回 / 初步审定：{doc.get('outcome')!r}")
        if doc.get("outcome") == "部分驳回" and not doc.get("outcome_scope"):
            r.err(where, "部分驳回时 outcome_scope 不能为空")

        am = doc.get("applicant_mark") or {}
        w = f"{where}.applicant_mark"
        if not CHINESE.search(str(am.get("text") or "")):
            r.err(w, f"text 不含中文：{am.get('text')!r}")
        if not am.get("app_no"):
            r.err(w, "app_no 缺失")
        our = _date(r, w, am.get("app_date"), "app_date", False)
        if our is None:
            r.warn(w, "app_date 为空，无法判断在先关系")
        _owner(r, w, am.get("owner"))
        _goods(r, w, am, doc.get("notes"))
        for g in am.get("goods") or []:
            if isinstance(g.get("nice_class"), int):
                classes[g["nice_class"]] = classes.get(g["nice_class"], 0) + 1

        cited = doc.get("cited_marks") or []
        if not isinstance(cited, list) or not cited:
            continue
        if not any(CHINESE.search(str(c.get("text") or "")) for c in cited):
            r.err(where, "没有可核实的中文文字引证商标")
        any_similar = False
        for i, c in enumerate(cited, 1):
            w = f"{where}.cited_marks[{i}]"
            mark_text = c.get("text")
            has_chinese_text = isinstance(mark_text, str) and CHINESE.search(mark_text) is not None
            if not has_chinese_text:
                references_without_chinese_text += 1
                if (
                    "text" not in c
                    or (mark_text is not None and not (isinstance(mark_text, str) and mark_text.strip()))
                    or not str(c.get("notes") or "").strip()
                ):
                    r.err(w, "无已核实中文文字的引证须保留 text 值（未知时填 null），并在 notes 说明来源")
            if not c.get("reg_no"):
                r.err(w, "reg_no 缺失")
            their = _date(r, w, c.get("app_date"), "app_date", False)
            if their and our and their > our and not c.get("notes") and not doc.get("notes"):
                r.warn(w, f"引证商标申请日 {their} 晚于申请商标 {our}，请在 notes 里说明（例如优先权）")
            if dec and their and their > dec:
                r.err(w, f"引证商标申请日 {their} 晚于决定日期 {dec}")
            _owner(r, w, c.get("owner"))
            _goods(r, w, c, c.get("notes"))
            ms, gs = c.get("mark_similar"), c.get("goods_similar")
            if ms not in ("近似", "不近似", "未认定"):
                r.err(w, f"mark_similar 只能是 近似 / 不近似 / 未认定：{ms!r}")
            elif has_chinese_text:
                outcomes[ms] += 1
            if gs not in ("相同", "类似", "不类似", "未认定"):
                r.err(w, f"goods_similar 只能是 相同 / 类似 / 不类似 / 未认定：{gs!r}")
            ex = str(c.get("reasoning_excerpt") or "")
            if not ex:
                r.warn(w, "reasoning_excerpt 为空")
            elif len(ex) > 100:
                r.err(w, f"reasoning_excerpt 超过 100 字（{len(ex)} 字）")
            if c.get("text") and c.get("text") == am.get("text") and ms == "不近似":
                r.warn(w, "两商标文字相同却记为不近似，请核对原文")
            any_similar = any_similar or (ms == "近似" and gs in ("相同", "类似"))
        if doc.get("outcome") == "驳回" and not any_similar:
            r.warn(where, "结果为驳回，但没有任何引证商标同时被认定标识近似且商品相同或类似，请核对")
        if doc.get("outcome") == "初步审定" and any_similar:
            r.warn(where, "结果为初步审定，但有引证商标被认定近似且商品类似（可能已失效，请在 notes 说明）")

    total = sum(outcomes.values()) + references_without_chinese_text
    print(f"决定书 {len(files)} 份，引证商标 {total} 个：近似 {outcomes['近似']}、不近似 {outcomes['不近似']}、"
          f"未认定 {outcomes['未认定']}；申请商标类别分布 {dict(sorted(classes.items()))}")
    if references_without_chinese_text:
        print(f"{references_without_chinese_text} 件引证无已核实的中文文字，仅留档，不计入标识标签统计。")
    if len(files) < 30:
        r.warn("decisions", f"只有 {len(files)} 份，目标 30–50 份")
    judged = outcomes["近似"] + outcomes["不近似"]
    if judged and not 0.3 <= outcomes["近似"] / judged <= 0.7:
        r.warn("decisions", f"近似占比 {outcomes['近似'] / judged:.0%}，目标大致各占一半")
    if not (d / "REPORT.md").exists():
        r.err("decisions", "缺少 REPORT.md")


def check_goods(r: Report) -> None:
    path = COLLECTED / "goods" / "goods_items_full.xlsx"
    if not path.exists():
        r.warn("goods", "没有找到 goods_items_full.xlsx")
        return
    import openpyxl

    wb = openpyxl.load_workbook(path, data_only=True)
    for sheet in ("商品项库", "群组注释"):
        if sheet not in wb.sheetnames:
            r.err("goods", f"缺少工作表“{sheet}”")
    if r.errors:
        return
    rows = list(wb["商品项库"].iter_rows(values_only=True))
    header = [str(h or "").strip() for h in rows[0]]
    need = ["商品项编号", "规范名称", "类别", "群组", "部分", "页码"]
    if header[:6] != need:
        r.err("goods.商品项库", f"表头应为 {need}，实际为 {header[:6]}")
        return
    seen = set()
    per_class: dict[int, int] = {}
    groups = set()
    for n, row in enumerate(rows[1:], 2):
        if not any(row):
            continue
        code, name, cls, grp = str(row[0] or "").strip(), str(row[1] or "").strip(), row[2], str(row[3] or "").strip()
        w = f"goods.商品项库 第 {n} 行"
        if not CODE.match(code):
            r.err(w, f"商品项编号格式不对：{code!r}")
        if not name:
            r.err(w, "规范名称为空")
        if cls not in (29, 30, 32, 43):
            r.err(w, f"类别不在 29/30/32/43：{cls!r}")
        if not GROUP.match(grp) or (isinstance(cls, int) and not grp.startswith(f"{cls:02d}")):
            r.err(w, f"群组与类别不符：{grp!r}")
        if (code, name) in seen:
            r.err(w, f"编号 + 名称重复：{code} {name}")
        seen.add((code, name))
        if row[5] in (None, ""):
            r.warn(w, "页码为空")
        if isinstance(cls, int):
            per_class[cls] = per_class.get(cls, 0) + 1
        groups.add(grp)
    notes = list(wb["群组注释"].iter_rows(values_only=True))
    note_groups = {str(x[0] or "").strip() for x in notes[1:] if x and x[0]}
    for g in sorted(note_groups - groups):
        r.warn("goods.群组注释", f"注释所属群组 {g} 在商品项库里没有出现")
    for cls in (29, 30, 32, 43):
        if not per_class.get(cls):
            r.err("goods", f"第 {cls} 类没有任何商品项")

    # 与现有选录对比：现有编号应当都能在全表里找到
    old = ROOT / "data" / "goods" / "goods_items.xlsx"
    if old.exists():
        ow = openpyxl.load_workbook(old, data_only=True)
        old_items = {(str(x[0]), str(x[1])) for x in list(ow["商品项库"].iter_rows(values_only=True))[1:] if x[0]}
        missing = sorted(old_items - seen)
        if missing:
            r.warn("goods", f"现有选录中有 {len(missing)} 项不在全表里（可能是版本更名），前 5 项：{missing[:5]}")
    print(f"商品项 {len(seen)} 项，各类别 {dict(sorted(per_class.items()))}，类似群 {len(groups)} 个，"
          f"注释 {len(notes) - 1} 条")
    if not (COLLECTED / "goods" / "REPORT.md").exists():
        r.err("goods", "缺少 REPORT.md")


def check_glyph(r: Report) -> None:
    d = COLLECTED / "glyph"
    if not d.exists():
        r.warn("glyph", "没有找到 collected/glyph/")
        return
    if not (d / "REPORT.md").exists():
        r.err("glyph", "缺少 REPORT.md")
    else:
        text = (d / "REPORT.md").read_text(encoding="utf-8")
        for ch in "沐沭茶荼己":
            if ch not in text:
                r.err("glyph.REPORT.md", f"没有给出示例字“{ch}”的原始数据")
        if "许可" not in text and "License" not in text and "license" not in text:
            r.err("glyph.REPORT.md", "没有写许可协议")
    data_files = [p for p in d.iterdir() if p.is_file() and p.name != "REPORT.md"]
    if not any(re.search(r"licen[cs]e|copying", p.name, re.I) for p in data_files):
        r.warn("glyph", "没有找到许可文件（LICENSE / COPYING）；若许可不允许分发，请在 REPORT.md 说明")
    print(f"字形数据目录下有 {len(data_files)} 个文件")


CHECKS = {"decisions": check_decisions, "goods": check_goods, "glyph": check_glyph}


def main(argv: list[str]) -> int:
    which = argv or list(CHECKS)
    r = Report()
    for name in which:
        if name not in CHECKS:
            print(f"未知的校验项：{name}，可选 {list(CHECKS)}")
            return 1
        CHECKS[name](r)
    for w in r.warnings:
        print(f"[警告] {w}")
    for e in r.errors:
        print(f"[错误] {e}")
    print(f"\n错误 {len(r.errors)} 个，警告 {len(r.warnings)} 个。" + ("通过。" if not r.errors else "未通过。"))
    return 1 if r.errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
