"""RAG 的两处用途：写结论时的补充依据（限定范围、按情形检索）与报告页的法律问答。"""
from datetime import date

from app import llm, qa
from app.runner import items_by_code, run_pre_filing
from app.tools import rag
from tests.conftest import good_llm
from tests.test_e2e import EV, TEA


def test_basis_retrieval_scoped_and_situational():
    q = "申请注册的商标，注册商标被注销、期满不再续展，一年内对相同或者近似的商标注册申请不予核准"
    rows = rag.retrieve_basis(q, date(2026, 11, 18))
    laws = [r["id"] for r in rows if r["kind"] == "law"]
    assert "TML2019-50" in laws
    assert set(laws) <= set(rag.SCOPED_LAW_IDS)          # 驰名、优先权等条文不进入补充依据
    new = [r["id"] for r in rag.retrieve_basis(q, date(2027, 3, 1)) if r["kind"] == "law"]
    assert "TML2026-49" in new


def _report():
    llm.set_backend(good_llm)
    return run_pre_filing("茗悦", goods=items_by_code(TEA), eval_date=EV)["report"]


def test_qa_renders_citations_and_drops_unknown_ids():
    rep = _report()
    seen = {}

    def fake(prompt_name, variables):
        if prompt_name != "p4_qa":
            return good_llm(prompt_name, variables)
        seen.update(variables)
        real = __import__("re").search(r"\[(TML[^\]]+)\]", variables["materials"]).group(1)
        return {"answer": f"驳回后可以申请复审 [{real}]，期限见〔{real}〕。另见 [TML2019-999]。", "basis_ids": [real], "insufficient": False}

    llm.set_backend(fake)
    out = qa.answer("如果申请被驳回，可以怎么办？期限是多久？", rep)
    assert out["llm"] and out["sources"]
    assert "〔《中华人民共和国商标法》" in out["answer"] and "[TML" not in out["answer"]
    assert any("TML2019-999" in w for w in out["warnings"])
    assert "茗悦" in seen["report"]                       # 报告事实交给了模型
    assert out["steps"][0]["step"] == "改写检索语句" and "注销之日起一年" in out["steps"][0]["detail"]


def test_qa_rewrite_finds_formal_article_and_searches_again():
    """改写后的法条用语能检索到口语问题检索不到的条文；材料不足时按模型给的语句再检索一轮。"""
    rep = _report()
    calls = []

    def fake(prompt_name, variables):
        if prompt_name != "p4_qa":
            return good_llm(prompt_name, variables)
        calls.append(variables["materials"])
        if len(calls) == 1:
            return {"answer": "资料不足。", "basis_ids": [], "insufficient": True,
                    "search_more": ["商标注册人申请注销其注册商标的，应当向商标局提交商标注销申请书"]}
        return {"answer": "一年内不予核准 [TML2019-50]。", "basis_ids": ["TML2019-50"], "insufficient": False}

    llm.set_backend(fake)
    out = qa.answer("在先商标已经注销，多久以后我才能注册？", rep)
    assert "[TML2019-50]" in calls[0]                    # 改写语句检索到了第五十条
    assert len(calls) == 2 and any(s["step"] == "补充检索" for s in out["steps"])
    assert [s["id"] for s in out["sources"]] == ["TML2019-50"]


def test_qa_flags_self_written_article():
    rep = _report()

    def fake(prompt_name, variables):
        if prompt_name != "p4_qa":
            return good_llm(prompt_name, variables)
        return {"answer": "根据商标法第三十条应当驳回。", "basis_ids": [], "insufficient": False}

    llm.set_backend(fake)
    out = qa.answer("为什么会被驳回？", rep)
    assert any("自行写的条号" in w for w in out["warnings"])


def test_qa_without_llm_returns_retrieved_articles():
    rep = _report()
    llm.set_backend(None)
    out = qa.answer("在先商标已经注销，多久以后我才能注册？", rep)
    assert not out["llm"] and out["sources"]


def _other_group(rep):
    return next(g for k in ("high", "medium", "needs_check", "low") for g in rep[k] if g["text"] != rep["query_mark"])


def test_history_keeps_all_resolved_questions_but_only_recent_answers():
    hist = [{"question": f"问题{i}", "resolved": f"补全{i}", "answer": f"回答{i}"} for i in range(6)]
    text = qa._history_text(hist)
    assert "补全0" in text and "回答0" not in text          # 早期轮次只留补全后的问题
    assert all(f"回答{i}" in text for i in (3, 4, 5))
    assert qa._history_text([]) == "无"


def test_find_candidates_by_name_and_id():
    rep = _report()
    g = _other_group(rep)
    found, _ = qa.find_candidates(f"“{g['text']}”为什么是{g['risk_label']}？", rep)
    assert g in found
    found, _ = qa.find_candidates(f"{g['marks'][0]['mark_id']} 是哪天申请的？", rep)
    assert g in found
    same = [x for k in ("high", "medium", "needs_check", "low") for x in rep[k] if x["text"] == rep["query_mark"]]
    found, _ = qa.find_candidates(f"为什么{rep['query_mark']}有风险？", rep)
    assert not any(x in found for x in same)               # 只提待查商标时不当作提到同名在先商标


def test_followup_pronoun_resolved_and_candidate_details_in_context():
    """第一轮问到某件在先商标，后面用“它”追问：改写把指代换成名称，回答时带上这一组的完整事实。"""
    rep = _report()
    g = _other_group(rep)
    seen = []

    def fake(prompt_name, variables):
        if prompt_name == "p4_qa_query":
            q = variables["question"].replace("它", f"“{g['text']}”")
            return {"question": q, "queries": [q]}
        if prompt_name == "p4_qa":
            seen.append(variables)
            return {"answer": "见报告事实。", "basis_ids": [], "insufficient": False}
        return good_llm(prompt_name, variables)

    llm.set_backend(fake)
    hist = []
    for q in [f"“{g['text']}”的风险从哪里来？", "驳回后多久可以复审？", "费用多少？", "期限怎么算？", "它是哪天申请的？"]:
        hist.append({"question": q, **qa.answer(q, rep, hist)})
    last = seen[-1]
    assert g["text"] in hist[-1]["resolved"]
    assert g["marks"][0]["mark_id"] in last["lookup"] and g["marks"][0]["app_date"] in last["lookup"]
    assert any(s["step"] == "查候选" for s in hist[-1]["steps"])
    assert f"“{g['text']}”的风险从哪里来" in last["history"]    # 第 1 轮已超出最近 3 轮，仍保留问题


def test_same_name_prior_mark_matched_only_when_explicit():
    rep = _report()
    same = [x for k in ("high", "medium", "needs_check", "low") for x in rep[k] if x["text"] == rep["query_mark"]]
    if not same:
        return
    found, _ = qa.find_candidates(f"报告中的在先商标“{rep['query_mark']}”是哪天申请的？", rep)
    assert same[0] in found
