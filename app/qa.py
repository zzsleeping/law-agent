"""法律问答（RAG）：用户看完报告后追问，模型从法条库、指南库检索相关条文，结合本次报告的事实回答。

Agent 步骤：
1. 改写（P4a）：模型结合之前的问答补全追问，把口语问题改写成法条用语的检索语句（小向量模型对口语检索效果差）；
   补全后的问题保存下来，供后面各轮理解指代；
1b. 查候选：补全后的问题里提到报告中的商标名称或编号时，把这一组的完整事实（各件注册的申请日、商品、在先状态、
   比对证据、判定理由）放进上下文；
2. 检索：评估日期适用的全部法条（不限 BASIS_SCOPE）+ 已施行的指南条目，外加报告里已经引用的依据；
3. 回答（P4）：模型在句末用 [依据 ID] 标出处，不许自写条号；认为材料不足时可以给出新的检索语句，
   再检索一轮后重答（最多 MAX_ROUNDS 轮）；
- 校验：不在检索材料里的 ID 一律删除并提示；自写条号的回答加警告；ID 由代码渲染成正式条号；
- 问答只提供信息，不改变报告的风险结论。
"""
from __future__ import annotations

import re
from datetime import date

from app import llm
from app.tools import basis, rag

ID_RE = re.compile(r"[\[〔【]\s*([A-Z][A-Za-z0-9.\-]*\d)\s*[\]〕】]")   # 模型偶尔用中文括号
SELF_ARTICLE_RE = re.compile(r"第[一二三四五六七八九十百零〇\d]+条")
RISK_KEYS = ("high", "medium", "needs_check", "low")
MAX_GROUPS_IN_CONTEXT = 12
MAX_ROUNDS = 2
FULL_TURNS = 3            # 最近几轮带完整回答；更早的轮次只带补全后的问题
MAX_LOOKUP_GROUPS = 3
MAX_MARKS_PER_GROUP = 8


def _report_context(rep: dict) -> str:
    """把报告压成一段供模型参考的文字：待查商标、商品、总结论、各名称组的风险与理由。"""
    lines = [f"待查商标：{rep['query_mark']}；商品项：{'、'.join(g['name'] for g in rep.get('goods', []))}；"
             f"检索类别：{'、'.join(map(str, rep.get('classes', [])))}；申请日：{rep.get('our_app_date') or '未提供'}"]
    if rep.get("overall"):
        lines.append(f"总结论：{rep['overall']['conclusion']}")
    n = 0
    for key in RISK_KEYS:
        for it in rep.get(key, []):
            if n >= MAX_GROUPS_IN_CONTEXT:
                break
            n += 1
            m = it["marks"][0] if it.get("marks") else {}
            claim = next((c["conclusion"] for c in it.get("claims", [])), "")
            lines.append(f"- 在先商标“{it['text']}”（{it['count']} 件，如 {it['mark_id']}）：{it['risk_label']}；"
                         f"在先状态 {m.get('prior', '—')}；商品关系 {m.get('goods_rel', '—')}。"
                         f"{claim or it.get('explanation', '')}")
    return "\n".join(lines)


def _history_text(history: list[dict], answer_chars: int | None = None) -> str:
    """问答历史：更早的轮次只列补全后的问题（短，保证指代能追溯）；最近 FULL_TURNS 轮带完整回答。"""
    if not history:
        return "无"
    old, recent = history[:-FULL_TURNS], history[-FULL_TURNS:]
    lines = [f"（第 {i + 1} 轮）问：{h.get('resolved') or h['question']}" for i, h in enumerate(old)]
    for i, h in enumerate(recent, start=len(old)):
        ans = h["answer"] if answer_chars is None else h["answer"][:answer_chars]
        lines.append(f"（第 {i + 1} 轮）问：{h['question']}"
                     + (f"（理解为：{h['resolved']}）" if h.get("resolved") and h["resolved"] != h["question"] else "")
                     + f"\n答：{ans}")
    return "\n".join(lines)


def _all_groups(rep: dict) -> list[dict]:
    return [g for k in RISK_KEYS for g in rep.get(k, [])]


def find_candidates(text: str, rep: dict) -> tuple[list[dict], list[dict]]:
    """在文字里找报告中的商标：先按编号，再按名称（长的优先，匹配过的位置不再重复匹配）。
    与待查商标同名的组只有写出编号、或写明“在先商标‘X’”“同名”时才算提到（否则“茗悦”多半指待查商标本身）。
    返回 (命中的名称组, 命中的用户剔除项)。"""
    groups, hit, rest = _all_groups(rep), [], text
    for g in groups:
        if any(m["mark_id"] in text or m["mark_id"].split("/")[0] in text for m in g["marks"]):
            hit.append(g)
    for g in sorted(groups, key=lambda g: -len(g["text"])):
        if g in hit or not g["text"]:
            continue
        if g["text"] == rep["query_mark"]:
            # 与待查商标同名：只有明确说“在先商标‘X’”或“同名”时才算提到
            if f"在先商标“{g['text']}”" in rest or f"同名的“{g['text']}”" in rest or "同名" in rest:
                hit.append(g)
            continue
        if g["text"] in rest:
            hit.append(g)
            rest = rest.replace(g["text"], "　")
    hit_ids = {g["mark_id"] for g in hit}
    excluded = [e for e in rep.get("exclusions", [])
                if e["mark_id"] not in hit_ids and (e["mark_id"] in text or (e["text"] and e["text"] in rest
                                                                             and e["text"] != rep["query_mark"]))]
    return hit[:MAX_LOOKUP_GROUPS], excluded[:MAX_LOOKUP_GROUPS]


def _group_detail(g: dict) -> str:
    """一组的完整事实，供回答细节问题。"""
    lines = [f"【在先商标“{g['text']}”】共 {g['count']} 件，组内最高风险 {g['risk_label']}；标识相似程度 {g['mark_sim']}；"
             f"{'大模型判定' if g.get('decided_by') == 'llm' else '规则判定'}"
             + (f"（规则参考：{g['rule_risk_label']}）" if g.get("disagree") else "")]
    if g.get("explanation"):
        lines.append(f"判定理由：{g['explanation']}")
    for c in g.get("claims", []):
        lines.append(f"结论：{c['conclusion']}")
        lines += [f"  事实：{f}" for f in dict.fromkeys(c["facts"])]
    for gn in g.get("guardrails", []):
        lines.append(f"护栏修正：{gn}")
    for m in g["marks"][:MAX_MARKS_PER_GROUP]:
        lines.append(f"- {m['mark_id']}：{m['risk_label']}；申请日 {m['app_date']}；在先状态 {m['prior']}；"
                     f"商品关系 {m['goods_rel']}；注册人 {m.get('owner') or '未知'}；"
                     f"核定商品 {(m.get('goods') or '未知')[:120]}")
    if g["count"] > MAX_MARKS_PER_GROUP:
        lines.append(f"- 其余 {g['count'] - MAX_MARKS_PER_GROUP} 件略")
    return "\n".join(lines)


def _lookup_text(groups: list[dict], excluded: list[dict]) -> str:
    parts = [_group_detail(g) for g in groups]
    parts += [f"【“{e['text']}”（{e['mark_id']}）】已被用户在确认候选时剔除，报告没有对它作出结论（原风险等级 {e['risk_label']}）。"
              for e in excluded]
    return "\n\n".join(parts) or "无（问题没有提到报告中的具体商标）"


def retrieve(queries: list[str], eval_date: date, extra_ids: list[str] | None = None,
             k_law: int = 4, k_guide: int = 2) -> list[str]:
    """按多条检索语句检索问答材料，返回依据 ID（去重，按语句顺序轮流取，保证每条语句都有结果进入）。"""
    per_query = []
    for q in queries:
        ids = [r["id"] for r in rag.retrieve_law(q, eval_date, k_law)]
        n_guide = 0
        for g in rag.retrieve_guides(q, k_guide + 3):
            b = basis.get_basis(g["id"])
            if b and basis.is_applicable(b, eval_date) and n_guide < k_guide:
                ids.append(g["id"])
                n_guide += 1
        per_query.append(ids)
    out = []
    for row in zip(*[r + [None] * (max(map(len, per_query)) - len(r)) for r in per_query]) if per_query else []:
        out += [i for i in row if i and i not in out]
    for i in extra_ids or []:
        b = basis.get_basis(i)
        if b and basis.is_applicable(b, eval_date) and i not in out:
            out.append(i)
    return out


def _rewrite(question: str, history: list[dict], rep: dict) -> tuple[str, list[str]]:
    """P4a：补全追问并改写成检索语句。失败时直接用原问题检索。"""
    names = list(dict.fromkeys(g["text"] for g in _all_groups(rep) if g["text"]))[:40]
    data = llm.chat_json("p4_qa_query", {
        "history": _history_text(history, answer_chars=200), "question": question,
        "query_mark": rep["query_mark"], "candidates": "、".join(names) or "无"})
    queries = [str(q)[:80] for q in (data or {}).get("queries") or [] if str(q).strip()][:3]
    resolved = str((data or {}).get("question") or question)
    return resolved, [question] + queries


def _render(text: str, allowed: set[str]) -> tuple[str, list[str], list[str]]:
    """把 [ID] 渲染成正式条号；返回 (渲染后的文字, 实际引用的 ID, 被删除的非法 ID)。"""
    used, dropped = [], []

    def sub(m: re.Match) -> str:
        i = m.group(1)
        if i not in allowed:
            dropped.append(i)
            return ""
        if i not in used:
            used.append(i)
        return f"〔{basis.citation(i)}〕"
    return ID_RE.sub(sub, text), used, dropped


def answer(question: str, rep: dict, history: list[dict] | None = None) -> dict:
    """回答一个问题。返回 {answer, sources: [{id, citation, text}], warnings, insufficient, llm, steps, resolved}。
    history：之前各轮的返回值（含 question）；resolved 是补全后的问题，下一轮起用于理解指代。"""
    question = question.strip()
    eval_date = date.fromisoformat(rep["eval_date"])
    history = history or []
    resolved, queries = _rewrite(question, history, rep)
    steps = [{"step": "改写检索语句", "detail": "；".join(queries[1:]) or "未改写（直接用原问题检索）"}]
    found, excluded = find_candidates(question + "\n" + resolved, rep)
    if found or excluded:
        steps.append({"step": "查候选", "detail": "、".join([f"“{g['text']}”" for g in found]
                                                          + [f"“{e['text']}”（已剔除）" for e in excluded])})
    reported = [b["id"] for b in rep.get("basis_appendix", [])]
    ids = retrieve(queries, eval_date, reported[:6])
    steps.append({"step": "检索条文", "detail": f"{len(ids)} 条"})

    def source(i: str) -> dict:
        return {"id": i, "citation": basis.citation(i), "text": basis.get_basis(i)["text"]}

    data = None
    for rnd in range(MAX_ROUNDS):
        materials = [f"[{i}] {basis.citation(i)}：{basis.get_basis(i)['text'][:500]}" for i in ids]
        data = llm.chat_json("p4_qa", {
            "eval_date": rep["eval_date"], "law_version": rep.get("law_version", ""),
            "report": _report_context(rep), "materials": "\n".join(materials),
            "history": _history_text(history), "lookup": _lookup_text(found, excluded),
            "question": question, "resolved": resolved,
        })
        more = [str(q)[:80] for q in (data or {}).get("search_more") or [] if str(q).strip()][:2]
        if not data or not data.get("insufficient") or not more or rnd == MAX_ROUNDS - 1:
            break
        added = [i for i in retrieve(more, eval_date) if i not in ids]
        steps.append({"step": "补充检索", "detail": "；".join(more) + f"（新增 {len(added)} 条）"})
        if not added:
            break
        ids += added

    if not data or not str(data.get("answer", "")).strip():
        why = llm.last_error if llm.available() else "未配置 LLM_API_KEY 或 LLM_MODEL"
        return {"answer": "大模型暂时无法回答（" + why + "）。下面是按问题检索到的相关条文，供自行查阅。",
                "sources": [source(i) for i in ids[:5]], "warnings": [], "insufficient": True, "llm": False,
                "steps": steps, "resolved": resolved}

    raw = str(data["answer"])
    warnings = []
    if SELF_ARTICLE_RE.search(ID_RE.sub("", raw)):
        warnings.append("回答中出现了模型自行写的条号，请以下方列出的依据原文为准")
    text, used, dropped = _render(raw, set(ids))
    used += [i for i in data.get("basis_ids") or [] if i in ids and i not in used]
    if dropped:
        warnings.append(f"已删除不在检索材料中的依据：{'、'.join(dict.fromkeys(dropped))}")
    insufficient = bool(data.get("insufficient"))
    if not used and not insufficient:
        warnings.append("回答没有标注依据，请谨慎参考")
    steps.append({"step": "生成回答", "detail": f"引用 {len(used)} 条" + ("，资料不足" if insufficient else "")})
    return {"answer": text.strip(), "sources": [source(i) for i in used], "warnings": warnings,
            "insufficient": insufficient, "llm": True, "steps": steps, "resolved": resolved}
