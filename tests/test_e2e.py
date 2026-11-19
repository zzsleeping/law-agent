"""端到端：完整流程、剔除候选、模型超时降级、无命中、版本切换、校验失败标红。"""
from datetime import date
from pathlib import Path

from app import llm
from app.runner import items_by_code, run_pre_filing
from tests.conftest import bad_llm, good_llm, timeout_llm

EV = date(2026, 11, 10)
TEA = ["300187", "C290069"]          # 茶饮料、奶茶（以奶为主）


def by_text(v):
    """{(文字, 状态/商品摘要)} 不唯一，这里按 mark_id 索引并附文字，便于断言。"""
    return {a.mark_id: a for a in v["assessments"]}


def risks(v, text):
    return sorted(a.risk for a in v["assessments"] if a.text == text)


def test_full_flow_with_llm():
    llm.set_backend(good_llm)
    v = run_pre_filing("茗悦", goods=items_by_code(TEA), eval_date=EV, query_meaning="品茶的愉悦")
    assert v["classes"] == [29, 30, 32]
    # 展示顺序：完全同名置顶
    order_text = [v["records"][m].text for m in v["display_order"]]
    n_exact = order_text.count("茗悦")
    assert n_exact == 5 and order_text[:n_exact] == ["茗悦"] * n_exact
    # 规则表结果
    assert risks(v, "茗悦") == ["high", "low", "low", "needs_check", "needs_check"]
    assert risks(v, "茗悦茶饮") == ["high"]            # 包含 + 弱显著文字
    assert risks(v, "茗悦时光") == ["high"]            # 完整包含且占比大（指南 5.5.1.16）
    assert risks(v, "明月") == ["medium"]              # 仅读音相同、字形不近，最多到中（指南 5.5.1.4）
    assert risks(v, "名悦") == ["medium"]              # 申请在先，仅读音相同
    assert risks(v, "茗约") == ["medium"]
    assert risks(v, "茗悦轩") == ["needs_check"]       # 状态未知
    assert risks(v, "悦茗") == ["high"]                # 整个商标仅相邻两字互换（指南 5.5.1.2；调参集此类全部认定近似）
    assert risks(v, "民悦") == ["low"]                 # 仅模糊音
    assert "餐厅" not in "".join(g.name for m in v["display_order"] for g in v["records"][m].goods)
    # 每个候选都能回溯到原始记录
    assert all(v["records"][m].source_ref and v["records"][m].snapshot_date for m in v["display_order"])
    # 校验通过，报告导出
    assert v["citation_errors"] == [] and v.get("retry_count", 0) == 0
    rep = v["report"]
    assert not rep["flagged"] and Path(v["report_path"]).exists()
    import zipfile                                     # Word 报告每页有系统水印：页眉系统名 + 衬于文字下方的水印图
    with zipfile.ZipFile(v["report_path"]) as z:
        header = "".join(z.read(n).decode("utf-8") for n in z.namelist() if n.startswith("word/header"))
        assert "商标近似评估智能体" in header and 'behindDoc="1"' in header and "SystemWatermark" in header
        assert any(n.startswith("word/media/") for n in z.namelist())
    assert rep["law_version"] == "《中华人民共和国商标法》（2019年修正）"
    high = {i["text"]: i for i in rep["high"]}
    medium = {i["text"]: i for i in rep["medium"]}
    assert any(b["id"] == "TML2019-30" for c in high["茗悦茶饮"]["claims"] for b in c["basis"])
    assert any(b["id"] == "TML2019-31" for c in medium["名悦"]["claims"] for b in c["basis"])   # 申请在先引第三十一条
    # 风险结论由模型写，数据缺口说明由代码写；同名组里两种可能并存（茗悦：1 件高风险 + 2 件待核实）
    assert all(c["source"] == "llm" for i in rep["high"] for c in i["claims"] if c["type"] == "risk")
    assert all(c["source"] == "code" for g in rep.values() if isinstance(g, list)
               for i in g if isinstance(i, dict) and "claims" in i for c in i["claims"] if c["type"] == "data_gap")
    assert all(c["type"] == "data_gap" for i in rep["needs_check"] for c in i["claims"])
    assert all(i["explanation_source"] == "llm" for i in rep["high"])
    mingyue = high["茗悦"]
    assert mingyue["count"] == 5 and sum(c["type"] == "risk" for c in mingyue["claims"]) == 1   # 同名 5 件，一条风险结论
    assert {m["risk"] for m in mingyue["marks"]} == {"high", "needs_check", "low"}
    assert "rule_stage" in v["timings"] and v["timings"]["rule_stage"] < 30


def test_exclude_high_candidate():
    """异常路径 1：用户剔除一个高风险候选，报告按确认结果生成，校验通过，附录列出。"""
    llm.set_backend(good_llm)
    dropped = {}

    def keep(values):
        a = next(a for a in values["assessments"] if a.risk == "high" and a.text == "茗悦茶饮")
        dropped["id"] = a.mark_id
        return [m for m in values["display_order"] if m != a.mark_id]

    v = run_pre_filing("茗悦", goods=items_by_code(TEA), eval_date=EV, keep=keep)
    assert v["citation_errors"] == [] and not v["report"]["flagged"]
    assert dropped["id"] not in {c.mark_id for c in v["claims"]}
    ex = v["report"]["exclusions"]
    assert [e["mark_id"] for e in ex] == [dropped["id"]] and ex[0]["risk_label"] == "高风险" and ex[0]["at"]
    assert "茗悦茶饮" not in [i["text"] for i in v["report"]["high"]]


def test_model_timeout_degrades():
    """异常路径 2：模型超时，风险列表照常出现，解释和报告走降级路径并标注。"""
    llm.set_backend(timeout_llm)
    v = run_pre_filing("茗悦", goods=items_by_code(TEA), eval_date=EV)
    assert risks(v, "茗悦茶饮") == ["high"]                   # 规则结果不受影响
    assert v["degraded"] and len(v["degraded_notes"]) >= 2
    assert all(a.explanation and a.explanation_source == "code" for a in v["assessments"])
    assert v["citation_errors"] == [] and not v["report"]["flagged"]     # 模板结论带依据，校验通过
    assert all(c.source == "code" for c in v["claims"])
    assert v["report"]["degraded"] and Path(v["report_path"]).exists()


def test_no_llm_configured_still_works():
    v = run_pre_filing("茗悦", goods_desc="茶饮料、奶茶", eval_date=EV)       # 走向量映射的建议商品项
    assert v["degraded"] and v["citation_errors"] == []
    assert {g.code for g in v["goods"]} >= {"300187"}


def test_no_hits():
    """没有近似商标时校验不应失败。"""
    v = run_pre_filing("霁川", goods=items_by_code(TEA), eval_date=EV)
    assert v["display_order"] == [] and v["citation_errors"] == []
    assert [c.claim_type for c in v["claims"]] == ["overall"] and v["claims"][0].basis_ids == []


def test_exclude_everything():
    v = run_pre_filing("茗悦", goods=items_by_code(TEA), eval_date=EV, keep=lambda values: [])
    assert v["citation_errors"] == [] and len(v["report"]["exclusions"]) == len(v["display_order"])


def test_transposition_counterexample():
    """字序改变后含义不同的商标：能被召回，规则参考为高（官方实践中整体互换多认定近似，如“蜜蜂 / 蜂蜜”）；
    含义区别明显的但书情形交给大模型结合含义判断（测试里的假模型照抄规则）。"""
    v = run_pre_filing("海星", goods=items_by_code(["320010"]), eval_date=EV)
    a = next(a for a in v["assessments"] if a.text == "星海")
    assert "transpose" in a.channels and a.rule_mark_sim == "high"


def test_app_date_changes_prior():
    v = run_pre_filing("茗悦", goods=items_by_code(TEA), eval_date=EV, our_app_date=date(2026, 10, 1))
    a = next(a for a in v["assessments"] if a.text == "铭月")
    assert a.prior == "not_prior" and a.risk == "low"
    v = run_pre_filing("茗悦", goods=items_by_code(TEA), eval_date=EV)
    assert next(a for a in v["assessments"] if a.text == "铭月").risk == "medium"


def test_law_version_switch():
    """评估日期切到 2027 年，依据自动换成新法条号。"""
    llm.set_backend(good_llm)
    v = run_pre_filing("茗悦", goods=items_by_code(TEA), eval_date=date(2027, 3, 1))
    assert v["citation_errors"] == []
    ids = {b for c in v["claims"] for b in c.basis_ids}
    assert "TML2026-20" in ids and not any(i.startswith("TML2019") for i in ids)
    assert v["report"]["law_version"] == "《中华人民共和国商标法》（2026年修订）"
    cites = [b["citation"] for b in v["report"]["basis_appendix"]]
    assert "《中华人民共和国商标法》（2026年修订）第二十条" in cites


def test_verify_failure_is_flagged_after_two_rewrites():
    llm.set_backend(bad_llm)
    v = run_pre_filing("茗悦", goods=items_by_code(TEA), eval_date=EV)
    assert v["retry_count"] == 3                       # 首次 + 2 次重写均失败
    assert v["report"]["flagged"] and v["report"]["errors"]
    assert sum(1 for t in v["trace"] if t["node"] == "compose") == 3
    assert v["trace"][-1]["node"] == "flag_output"


def test_glyph_and_long_marks():
    v = run_pre_filing("沐茶", goods=items_by_code(TEA), eval_date=EV)
    assert risks(v, "沐荼") == ["high"] and risks(v, "沭茶") == ["high"]
    v = run_pre_filing("云雾知春", goods=items_by_code(["C300147"]), eval_date=EV)
    assert risks(v, "云雾之春") == ["high"] and risks(v, "云雾迎春") == ["high"]    # 四字仅一字不同、首字相同


def test_restaurant_class():
    v = run_pre_filing("南柠", goods=items_by_code(["430024"]), eval_date=EV)
    assert v["classes"] == [43]
    assert risks(v, "南柠咖啡") == ["high"] and risks(v, "蓝柠") == ["low"]
    assert risks(v, "楠柠") in (["medium"], ["high"])   # 同音；字形是否近似取决于形近判断



def test_llm_call_cap():
    """只为前若干个名称组调用大模型，其余用模板；超出部分不算降级失败。"""
    from app.config import settings

    calls = []

    def counting(name, variables):
        calls.append(name)
        return good_llm(name, variables)

    llm.set_backend(counting)
    old = settings.llm_max_groups
    settings.llm_max_groups = 2
    try:
        v = run_pre_filing("茗悦", goods=items_by_code(TEA), eval_date=EV)
    finally:
        settings.llm_max_groups = old
    assert calls.count("p2_judge") == 2                         # 判定只调 2 次
    assert calls.count("p3_compose") == 3                       # 2 组风险结论 + 1 次总结论
    assert v["citation_errors"] == []
    assert any("只为前 2 个名称组" in n for n in v["degraded_notes"])
    assert sum(1 for c in v["claims"] if c.claim_type == "risk" and c.source == "code") >= 1



def test_llm_decides_with_guardrails():
    """大模型定风险：可以推翻规则的参考判断（并被标出），但不能违反护栏。"""
    from app.config import settings

    def contrarian(name, variables):
        if name != "p2_judge":
            return good_llm(name, variables)
        # 对每组都唱反调：规则判高的说低，其余都说高
        flip = {"high": "low", "medium": "high", "low": "high", "needs_check": "high"}
        return {"mark_sim": "high" if variables["rule_mark_sim_code"] != "high" else "low",
                "reason": "（假模型）与规则相反。", "disagree": True,
                "marks": [{"mark_id": m["mark_id"], "risk": flip[m["rule_risk"]]} for m in variables["marks_json"]]}

    llm.set_backend(contrarian)
    old = settings.llm_max_groups
    settings.llm_max_groups = 50
    try:
        v = run_pre_filing("茗悦", goods=items_by_code(TEA), eval_date=EV)
    finally:
        settings.llm_max_groups = old
    by = {a.mark_id: a for a in v["assessments"]}
    exact_same = next(a for a in v["assessments"] if a.text == "茗悦" and a.rule_risk == "high")
    assert exact_same.risk == "high" and "护栏修正" in exact_same.guardrail        # 同名同商品在先：不能判低
    lapsed = next(a for a in v["assessments"] if a.text == "茗悦" and a.prior == "invalid")
    assert lapsed.risk == "low"                                                     # 不构成在先：不能判高
    check = next(a for a in v["assessments"] if a.text == "茗悦轩")
    assert check.risk == "needs_check"                                              # 状态待核实：不能判高
    mingyue = next(a for a in v["assessments"] if a.text == "明月")
    assert mingyue.decided_by == "llm" and mingyue.rule_risk == "medium" and mingyue.risk == "high"
    assert mingyue.disagree and mingyue.flag_review                                 # 推翻规则判断时标出
    assert v["citation_errors"] == []
    judge_facts = [f for f in v["facts"].values() if f.fact_id.endswith("-judge")]
    assert judge_facts and all(f.text.startswith("大模型判定") for f in judge_facts)


def test_judge_falls_back_to_rules_without_llm():
    v = run_pre_filing("茗悦", goods=items_by_code(TEA), eval_date=EV)
    assert all(a.decided_by == "rule" and a.risk == a.rule_risk for a in v["assessments"])
    assert any("未能由大模型判定" in n for n in v["degraded_notes"])


def test_search_planning_agent():
    """检索规划：模型给出的写法被试查、写进执行记录，检出的商标在义近通道标注来源。"""
    rounds = []

    def planner(name, variables):
        if name == "p0_plan":
            rounds.append(variables["probe"])
            return {"queries": [{"text": "悦茗", "why": "字序调换"}, {"text": "茗悦", "why": "与原文相同，应被丢弃"},
                                {"text": "ABC", "why": "非中文，应被丢弃"}], "done": len(rounds) >= 2}
        return good_llm(name, variables)

    llm.set_backend(planner)
    v = run_pre_filing("茗悦", goods=items_by_code(TEA), eval_date=EV)
    assert [x["text"] for x in v["search_variants"]] == ["悦茗"] and v["search_variants"][0]["hits"] >= 1
    assert len(rounds) == 2 and "命中" in rounds[1]                      # 第二轮看到了试查结果
    steps = [t for t in v["trace"] if t["node"] == "plan_search"]
    assert len(steps) == 2 and "悦茗" in steps[0]["queries"][0]
    yue = next(a for a in v["assessments"] if a.text == "悦茗")
    assert "meaning" in yue.channels
    assert any("检索规划" in h.evidence for h in v["hits_by_mark"][yue.mark_id])


def test_search_planning_skipped_without_llm():
    v = run_pre_filing("茗悦", goods=items_by_code(TEA), eval_date=EV)
    assert v["search_variants"] == [] and any("检索规划未使用大模型" in n for n in v["degraded_notes"])



def test_rag_basis_retrieval():
    """写结论时用 RAG 检索补充依据：按评估日期过滤版本，补充的依据进入允许清单并标注来源，校验照常通过。"""
    from datetime import date as d
    from app.tools import rag

    old = [r["id"] for r in rag.retrieve_basis("同一种商品上已经注册的商标相同或者近似，驳回申请", d(2026, 11, 18))]
    new = [r["id"] for r in rag.retrieve_basis("同一种商品上已经注册的商标相同或者近似，驳回申请", d(2027, 3, 1))]
    assert old and not any(i.startswith("TML2026") for i in old)
    assert new and not any(i.startswith("TML2019") for i in new)
    llm.set_backend(good_llm)
    v = run_pre_filing("茗悦", goods=items_by_code(TEA), eval_date=EV)
    rag_ids = [b for b, src in v.get("basis_sources", {}).items() if src == "rag"]
    assert rag_ids and set(rag_ids) <= set(v["allowed_basis"])
    assert v["citation_errors"] == []
    assert any(t.get("rag_basis") for t in v["trace"] if t["node"] == "compose")
