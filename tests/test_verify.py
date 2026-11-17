"""check_claims 的每种错误，含两轮评审复现过的用例。"""
from datetime import date

from app.nodes.verify import check_claims
from app.state import Assessment, Claim, Fact

EV = date(2026, 11, 10)
ALLOWED = ["TML2019-30", "GUIDE2021-5.2"]


def assess(mark_id, risk):
    return Assessment(mark_id=mark_id, text=mark_id, mark_sim="high", goods_rel="same", prior="valid", risk=risk)


FACTS = {
    "F-SCOPE": Fact(fact_id="F-SCOPE", mark_id=None, kind="scope", text="范围"),
    "F-A-hit": Fact(fact_id="F-A-hit", mark_id="A", kind="hit", text="拼音相同"),
    "F-B-hit": Fact(fact_id="F-B-hit", mark_id="B", kind="hit", text="完全相同"),
    "F-C-gap": Fact(fact_id="F-C-gap", mark_id="C", kind="data_gap", text="状态未知"),
}


def risk(mark_id="A", **kw):
    base = dict(mark_id=mark_id, claim_type="risk", conclusion="构成近似。", fact_ids=[f"F-{mark_id}-hit"],
                basis_ids=["TML2019-30"], source="llm")
    base.update(kw)
    return Claim(**base)


def overall(**kw):
    base = dict(mark_id=None, claim_type="overall", conclusion="存在障碍。", fact_ids=["F-SCOPE"],
                basis_ids=["TML2019-30"], source="llm")
    base.update(kw)
    return Claim(**base)


def gap(**kw):
    base = dict(mark_id="C", claim_type="data_gap", conclusion="缺状态。", fact_ids=["F-C-gap"], source="code")
    base.update(kw)
    return Claim(**base)


def check(claims, selected):
    return check_claims(claims, ALLOWED, EV, selected, FACTS)


def test_valid_passes():
    sel = [assess("A", "high"), assess("B", "medium"), assess("C", "needs_check")]
    assert check([risk("A"), risk("B"), gap(), overall()], sel) == []


def test_reviewer_case_excluded_high_candidate_passes():
    """评审用例 9：剔除高风险候选 B 后，只为保留的 A 写结论，应通过。"""
    assert check([risk("A"), overall()], [assess("A", "high")]) == []


def test_reviewer_case_high_claim_without_basis_fails():
    """评审用例 10：无依据的 high 风险结论必须报错。"""
    errs = check([risk("A", basis_ids=[]), overall()], [assess("A", "high")])
    assert any("缺少依据" in e for e in errs)


def test_claim_for_excluded_candidate():
    assert any("不在已确认候选中" in e for e in check([risk("A"), risk("B"), overall()], [assess("A", "high")]))


def test_data_gap_must_be_code():
    errs = check([gap(source="llm"), overall(basis_ids=[])], [assess("C", "needs_check")])
    assert any("不得由模型生成" in e for e in errs)


def test_fact_errors():
    sel = [assess("A", "high")]
    assert any("没有引用事实" in e for e in check([risk("A", fact_ids=[]), overall()], sel))
    assert any("事实不存在" in e for e in check([risk("A", fact_ids=["F-NOPE"]), overall()], sel))
    assert any("不属于 A" in e for e in check([risk("A", fact_ids=["F-B-hit"]), overall()], sel))
    # 总结论不得引用已剔除候选的事实
    assert any("已剔除" in e for e in check([risk("A"), overall(fact_ids=["F-B-hit"])], sel))


def test_basis_errors():
    sel = [assess("A", "high")]
    assert any("依据不存在" in e for e in check([risk("A", basis_ids=["TML2019-999"]), overall()], sel))
    assert any("不在本次允许清单内" in e for e in check([risk("A", basis_ids=["TML2019-57"]), overall()], sel))
    # 版本不适用：评估日 2027 年却引用旧法
    errs = check_claims([risk("A"), overall()], ALLOWED, date(2027, 3, 1), sel, FACTS)
    assert any("版本不适用" in e for e in errs)


def test_article_number_in_conclusion():
    errs = check([risk("A", conclusion="违反商标法第三十条。"), overall()], [assess("A", "high")])
    assert any("自行写了条号" in e for e in errs)
    assert any("自行写了条号" in e for e in check([risk("A", conclusion="依据第30条。"), overall()], [assess("A", "high")]))


def test_coverage():
    assert any("缺少风险结论：A" in e for e in check([overall()], [assess("A", "high")]))
    assert any("缺少数据缺口说明：C" in e for e in check([overall(basis_ids=[])], [assess("C", "needs_check")]))
    assert any("缺少总结论" in e for e in check([risk("A")], [assess("A", "high")]))
    assert any("只能有一条" in e for e in check([risk("A"), overall(), overall()], [assess("A", "high")]))


def test_no_risky_candidates_overall_needs_no_basis():
    """没有近似商标、只有低风险或全部剔除时，总结论由代码生成、不要求依据。"""
    ov = overall(basis_ids=[], source="code")
    assert check([ov], []) == []
    assert check([ov], [assess("A", "low")]) == []
    assert check([gap(), ov], [assess("C", "needs_check")]) == []
    # 但只要有高 / 中风险候选，总结论就必须有依据
    assert any("缺少依据" in e for e in check([risk("A"), ov], [assess("A", "high")]))



def test_group_claims():
    """同名多件注册：一条风险结论覆盖整组，可以引用组内其他件的事实；被剔除的那件不能引用。"""
    g = lambda m, risk: Assessment(mark_id=m, text="茗悦", group="茗悦", mark_sim="high", goods_rel="same",  # noqa: E731
                                   prior="valid", risk=risk)
    facts = {**FACTS,
             "F-G1-hit": Fact(fact_id="F-G1-hit", mark_id="G1", kind="hit", text="完全相同", group="茗悦"),
             "F-G2-hit": Fact(fact_id="F-G2-hit", mark_id="G2", kind="hit", text="完全相同", group="茗悦"),
             "F-G3-gap": Fact(fact_id="F-G3-gap", mark_id="G3", kind="data_gap", text="状态待核实", group="茗悦")}
    sel = [g("G1", "high"), g("G2", "high"), g("G3", "needs_check")]
    claims = [Claim(mark_id="G1", claim_type="risk", conclusion="近似。", fact_ids=["F-G1-hit", "F-G2-hit"],
                    basis_ids=["TML2019-30"]),
              Claim(mark_id="G3", claim_type="data_gap", conclusion="缺。", fact_ids=["F-G3-gap"], source="code"),
              overall()]
    assert check_claims(claims, ALLOWED, EV, sel, facts) == []                     # 整组一条即可
    errs = check_claims(claims[1:], ALLOWED, EV, sel, facts)
    assert any("缺少风险结论：茗悦（同名 3 件）" in e for e in errs)
    errs = check_claims(claims, ALLOWED, EV, sel[:1] + sel[2:], facts)              # 用户剔除了 G2
    assert any("F-G2-hit 属于已剔除的候选" in e for e in errs)
