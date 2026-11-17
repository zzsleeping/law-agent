"""把《类似商品和服务区分表》的群组注释原文解析成机器可用的规则。

只做句式解析，不做法律推断：注释怎么写就怎么转。解析不了的句子标为“说明”，不参与判断，
并在核对表 data/goods/notes_rules_review.md 里列出，供人工检查。

规则类型（rel_type）：
- 明确类似：A 侧与 B 侧的商品类似（跨群或群内）
- 明确不类似：同一类似群的不同部分之间不类似（“本类似群各部分之间商品不类似”）
- 段间待核实：“各自然段间互不类似”，但库里没有自然段划分，同群不同商品判待核实
- 历史交叉检索：与旧版区分表的交叉检索，只作提示
- 跨群保护：同一商品同时列在两个群，已由商品项库的多群归属体现
- 说明：群组删除、商品移出等，不参与判断
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

HISTORY = re.compile(r"第[一二三四五六七八九十]+版及以前版本")
PART = re.compile(r"^第（([一二三四五六七八九十]+)）部分")
PARA = re.compile(r"^第([一二三四五六七八九十]+)自然段")
GROUP_HEAD = re.compile(r"^(\d{4})(.*)$")


@dataclass
class Side:
    group: str
    scope: str                      # whole / part / para / items
    part: str | None = None         # “（二）”或“第二自然段”
    names: list[str] = field(default_factory=list)
    open_ended: bool = False        # 列举后有“等……”
    remark: str = ""                # 无法细分的限定，如“第一自然段商品（人用药除外）”

    def describe(self) -> str:
        if self.scope == "whole":
            body = "全群"
        elif self.scope in ("part", "para"):
            body = (f"第{self.part}部分" if self.scope == "part" else self.part) + (self.remark and f"（{self.remark}）")
        else:
            body = "、".join(self.names) + ("等" if self.open_ended else "")
        return f"{self.group} {body}"


@dataclass
class Rule:
    note_id: str
    group: str
    rel_type: str
    text: str
    sides: list[list[Side]] = field(default_factory=list)   # [A 侧的若干 Side, B 侧的若干 Side]
    parts: list[str] = field(default_factory=list)          # 明确不类似：涉及的部分


def _strip(text: str) -> str:
    return text.strip().rstrip("；;。.").strip()


def _split_names(s: str) -> tuple[list[str], bool]:
    """“A，B，C等含果汁的饮料” → ([A, B, C], True)。"""
    open_ended = False
    if "等" in s:
        head, _, tail = s.rpartition("等")
        if tail and not tail.startswith(("（", ")")):
            s, open_ended = head, True
    names = [n.strip() for n in re.split(r"[，,、]", s) if n.strip()]
    return names, open_ended


def _subject(group: str, s: str) -> Side:
    s = s.strip()
    if s == "本类似群":
        return Side(group, "whole")
    m = PART.match(s)
    if m:
        rest = s[m.end():]
        return Side(group, "part", f"（{m.group(1)}）", remark=rest)
    m = PARA.match(s)
    if m:
        return Side(group, "para", f"第{m.group(1)}自然段")
    names, open_ended = _split_names(s)
    return Side(group, "items", names=names, open_ended=open_ended)


def _targets(s: str) -> list[Side]:
    """“2907第二自然段，3001加奶可可饮料，咖啡饮料，3202” → 三个 Side。"""
    out: list[Side] = []
    for seg in re.split(r"[，,]|和(?=\d{4})", s):
        seg = seg.strip()
        if not seg:
            continue
        m = GROUP_HEAD.match(seg)
        if m:
            grp, rest = m.group(1), m.group(2).strip()
            if not rest:
                out.append(Side(grp, "whole"))
                continue
            pm, am = PART.match(rest), PARA.match(rest)
            if pm:
                out.append(Side(grp, "part", f"（{pm.group(1)}）", remark=rest[pm.end():]))
                continue
            if am:
                out.append(Side(grp, "para", f"第{am.group(1)}自然段", remark=rest[am.end():]))
                continue
            names, open_ended = _split_names(rest)
            out.append(Side(grp, "items", names=names, open_ended=open_ended))
        elif out and out[-1].scope == "items":
            names, open_ended = _split_names(seg)
            out[-1].names += names
            out[-1].open_ended = out[-1].open_ended or open_ended
        else:
            raise ValueError(f"无法归属的片段：{seg}")
    return out


def parse_note(group: str, seq: str, text: str) -> list[Rule]:
    note_id = f"{group}-{seq}"
    t = _strip(text)
    if t.startswith("跨类似群保护商品"):
        return [Rule(note_id, group, "跨群保护", text)]
    if "版时删除" in t or "移入" in t:
        return [Rule(note_id, group, "说明", text)]
    if "各部分之间" in t and "不类似" in t:
        return [Rule(note_id, group, "明确不类似", text)]
    if "各自然段间互不类似" in t:
        scope_text = t.split("为单一")[0]
        return [Rule(note_id, group, "段间待核实", text, sides=[[_subject(group, scope_text)]])]

    rules: list[Rule] = []
    if "与" not in t:
        return [Rule(note_id, group, "说明", text)]
    subject_text, _, rest = t.partition("与")
    subject = _subject(group, subject_text)
    # 现行部分：……类似；历史部分：与第N版及以前版本……交叉检索 / 类似
    current, history = rest, ""
    hm = HISTORY.search(rest)
    if hm:
        current = rest[:hm.start()]
        history = rest[hm.start():]
        current = re.sub(r"[，,]?\s*与?\s*$", "", current)
    if current.endswith("类似") and not current.endswith("不类似"):
        rules.append(Rule(note_id, group, "明确类似", text,
                          sides=[[subject], _targets(current[: -len("类似")])]))
    elif current.strip():
        rules.append(Rule(note_id, group, "说明", text))
    if history:
        rules.append(Rule(f"{note_id}-历史", group, "历史交叉检索", text, sides=[[subject], []]))
    return rules or [Rule(note_id, group, "说明", text)]


def clean_name(name: str) -> str:
    return name.replace("*", "").strip()


class ItemIndex:
    """按群组索引商品项：group -> [(code, name, part)]。"""

    def __init__(self, items: list[dict]) -> None:
        self.by_group: dict[str, list[dict]] = {}
        for it in items:
            self.by_group.setdefault(it["grp"], []).append(it)

    def known(self, group: str) -> bool:
        return group in self.by_group

    def resolve(self, side: Side) -> tuple[set[str], list[str]]:
        """返回 (编号集合, 未能对应的名称)。库里没有该群（区分表其他类别）时返回空集合、无未对应项。"""
        rows = self.by_group.get(side.group)
        if rows is None:
            return set(), []
        if side.scope == "whole":
            return {r["code"] for r in rows}, []
        if side.scope in ("part", "para"):
            got = {r["code"] for r in rows if r.get("part") == side.part}
            return got, ([] if got else [side.describe()])
        codes, missing = set(), []
        for n in side.names:
            hit = {r["code"] for r in rows if clean_name(r["name"]) == clean_name(n)}
            if hit:
                codes |= hit
            else:
                missing.append(n)
        return codes, missing
