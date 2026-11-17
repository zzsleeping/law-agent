"""规则表每一行、商品关系、在先状态、依据的版本适用。"""
from datetime import date

import pytest

from app.rules.goods_relation import goods_relation, linked_classes
from app.rules.prior_status import prior_status
from app.rules.risk_table import mark_similarity, risk_level
from app.runner import items_by_code
from app.state import GoodsItem, Hit, MarkRecord
from app.tools import basis


@pytest.mark.parametrize("prior,goods,sim,expected,row", [
    ("invalid", "same", "high", "low", 1),
    ("not_prior", "same", "high", "low", 1),
    ("unknown", "dissimilar", "high", "low", 2),          # 商品不类似，状态如何都不构成冲突
    ("valid", "dissimilar", "high", "low", 2),
    ("unknown", "same", "high", "needs_check", 3),
    ("lapsed_recent", "similar", "medium", "needs_check", 3),
    ("unknown", "same", "low", "needs_check", 3),          # 状态待核实的弱命中保留待核实
    ("pending_long", "same", "high", "needs_check", 3),
    ("expired", "similar", "high", "needs_check", 3),
    ("same_day", "same", "medium", "needs_check", 3),
    ("valid", "pending", "medium", "needs_check", 4),
    ("earlier_app", "pending", "low", "low", 7),
    ("valid", "same", "high", "high", 5),
    ("earlier_app", "linked", "high", "high", 5),          # 可能在先申请照常评级
    ("registered", "same", "high", "high", 5),
    ("prelim", "similar", "medium", "medium", 6),
    ("valid", "similar", "medium", "medium", 6),
    ("valid", "same", "low", "low", 7),
])
def test_risk_table_rows(prior, goods, sim, expected, row):
    assert risk_level(prior, goods, sim) == (expected, row)


def test_mark_similarity():
    h = lambda kind: Hit(mark_id="x", channel="pinyin", kind=kind)  # noqa: E731
    assert mark_similarity([h("pinyin_fuzzy")]) == "low"                    # 仅模糊音
    assert mark_similarity([h("transpose")]) == "medium"                    # 字序颠倒单独最多到中
    assert mark_similarity([h("redup")]) == "high"                         # 叠字（指南 5.5.1.3）
    assert mark_similarity([h("pinyin_tone")]) == "medium"                 # 仅读音相同（反例“好歌 / 好哥”）
    assert mark_similarity([h("pinyin_tone"), h("edit_one")]) == "high"    # 读音相同且字形近似
    assert mark_similarity([h("transpose"), h("pinyin_tone")]) == "medium"
    assert mark_similarity([h("shared_part")]) == "medium" and mark_similarity([h("contains_major")]) == "high"
    assert mark_similarity([h("exact")]) == "high" and mark_similarity([]) == "low"


def rel(a, b):
    return goods_relation(items_by_code(a), items_by_code(b))[0]


def test_goods_relation():
    assert rel(["300187"], ["300187"]) == "same"
    assert rel(["300187"], ["300292"]) == "similar"          # 同为 3002 第（二）部分
    assert rel(["300187"], ["300037"]) == "dissimilar"       # R10：3002 第（一）与第（二）部分不类似
    assert rel(["300187"], ["320031"]) == "linked"           # R01：3002 第（二）部分 ↔ 3202 全群
    assert rel(["300149"], ["320031"]) == "linked"           # R03：3001 指定六项 ↔ 3202
    assert rel(["300026"], ["320031"]) == "dissimilar"       # 3001 其他项目不由 R03 扩展
    assert rel(["C290069"], ["300187"]) == "linked"          # R05：2907 第二自然段 ↔ 3002 第（二）部分
    assert rel(["300125"], ["320010"]) == "linked"           # R08 明列的含果汁饮料
    assert rel(["300125"], ["320015"]) == "pending"          # R08 开放式列举，矿泉水未列明
    assert rel(["430024"], ["300026"]) == "dissimilar"       # 咖啡馆 vs 咖啡：区分表无关联
    assert rel(["300187", "300026"], ["300037", "300026"]) == "same"        # 多项取最强
    unmapped = [GoodsItem(name="现制茶饮", nice_class=30)]
    assert goods_relation(items_by_code(["300187"]), unmapped)[0] == "pending"   # 库里查不到不判不类似


def test_linked_classes():
    assert linked_classes(items_by_code(["300187", "C290069"])) == {29, 30, 32}
    assert linked_classes(items_by_code(["430024"])) == {43}


def rec(**kw):
    base = dict(mark_id="T", text="x", status="已注册", app_date=date(2020, 1, 1), snapshot_date=date(2026, 11, 10))
    base.update(kw)
    return MarkRecord(**base)


def test_prior_status():
    ev, ours = date(2026, 11, 10), date(2026, 11, 10)
    assert prior_status(rec(), ours, ev)[0] == "valid"
    assert prior_status(rec(status="初审公告"), ours, ev)[0] == "valid"
    assert prior_status(rec(status="申请中"), ours, ev)[0] == "earlier_app"
    assert prior_status(rec(status="申请中", app_date=date(2026, 11, 5)), date(2026, 10, 1), ev)[0] == "not_prior"
    # 优先权日早于我方申请日则仍在先
    assert prior_status(rec(status="申请中", app_date=date(2026, 11, 5), priority_date=date(2026, 6, 1)),
                        date(2026, 10, 1), ev)[0] == "earlier_app"
    assert prior_status(rec(app_date=date(2026, 11, 10)), ours, ev)[0] == "same_day"       # 同日申请单列
    assert prior_status(rec(status="怪状态"), ours, ev)[0] == "unknown"
    assert prior_status(rec(app_date=None), ours, ev)[0] == "unknown"
    assert prior_status(rec(), None, ev)[0] == "unknown"                     # 我方申请日缺失
    assert prior_status(rec(status="已驳回"), ours, ev)[0] == "invalid"
    lapsed = dict(status="已撤销", invalid_reason="宣告无效")
    assert prior_status(rec(**lapsed, invalid_date=date(2024, 3, 1)), ours, ev)[0] == "invalid"
    assert prior_status(rec(**lapsed, invalid_date=date(2026, 8, 15)), ours, ev)[0] == "lapsed_recent"
    assert prior_status(rec(**lapsed), ours, ev)[0] == "lapsed_recent"       # 失效日期缺失
    assert prior_status(rec(status="已撤销", invalid_reason="连续三年不使用撤销",
                            invalid_date=date(2026, 8, 15)), ours, ev)[0] == "invalid"


def test_prior_status_from_dates():
    """开放数据没有状态文字，按公告日期推定。"""
    ev, ours = date(2026, 11, 18), date(2026, 11, 18)
    d = lambda **kw: rec(status=None, **kw)  # noqa: E731
    p, why = prior_status(d(reg_date=date(2017, 7, 7), term_end=date(2037, 7, 6)), ours, ev)
    assert p == "registered" and "按日期推定在期内" in why and "须另行核实" in why
    assert prior_status(d(reg_date=date(2010, 1, 1), term_end=date(2026, 5, 1)), ours, ev)[0] == "expired"
    assert prior_status(d(reg_date=date(2010, 1, 1)), ours, ev)[0] == "unknown"           # 有注册日无专用期
    assert prior_status(d(prelim_date=date(2026, 9, 1)), ours, ev)[0] == "prelim"
    assert prior_status(d(app_date=date(2026, 1, 5)), ours, ev)[0] == "earlier_app"        # 18 个月内、未见公告
    assert prior_status(d(app_date=date(2025, 5, 18)), ours, ev)[0] == "earlier_app"       # 恰好 18 个月
    assert prior_status(d(app_date=date(2025, 5, 17)), ours, ev)[0] == "pending_long"
    assert prior_status(d(app_date=date(2026, 11, 19)), ours, ev)[0] == "not_prior"        # 晚于我方，无论有无公告
    assert prior_status(d(app_date=date(2026, 11, 19), reg_date=date(2026, 11, 19),
                          term_end=date(2036, 1, 1)), ours, ev)[0] == "not_prior"


def test_prior_status_new_law():
    """2026 年修订版：一年隔离只针对主动申请注销。"""
    ev, ours = date(2027, 3, 1), date(2027, 3, 1)
    vol = dict(status="已注销", invalid_reason="注册人申请注销")
    assert prior_status(rec(**vol, invalid_date=date(2026, 12, 1)), ours, ev, "TML2026")[0] == "lapsed_recent"
    assert prior_status(rec(**vol, invalid_date=date(2025, 12, 1)), ours, ev, "TML2026")[0] == "invalid"
    assert prior_status(rec(**vol), ours, ev, "TML2026")[0] == "lapsed_recent"            # 日期缺失
    wipe = dict(status="已无效", invalid_reason="宣告无效", invalid_date=date(2027, 1, 20))
    assert prior_status(rec(**wipe), ours, ev, "TML2026")[0] == "invalid"                 # 不适用新法隔离期
    assert prior_status(rec(**wipe), ours, ev, "TML2019")[0] == "lapsed_recent"           # 旧法下仍在一年内
    unclear = dict(status="已注销", invalid_reason=None, invalid_date=date(2026, 6, 1))
    assert prior_status(rec(**unclear), ours, ev, "TML2026")[0] == "lapsed_recent"        # 只有“已注销”字样，待核实


def test_basis_version():
    old, new = date(2026, 11, 10), date(2027, 1, 1)
    assert basis.get_basis("TML2019-30")["article"] == "第三十条"
    assert basis.get_basis("NOPE-1") is None
    assert basis.is_applicable(basis.get_basis("TML2019-30"), date(2026, 12, 31))
    assert not basis.is_applicable(basis.get_basis("TML2019-30"), new)
    assert not basis.is_applicable(basis.get_basis("TML2026-20"), old)
    assert not basis.is_applicable(basis.get_basis("GUIDE2021-5.2"), date(2021, 12, 31))   # 2022-01-01 施行
    a = basis.basis_for("pre_filing", old, "valid", ["pinyin_tone"])
    b = basis.basis_for("pre_filing", new, "valid", ["pinyin_tone"])
    assert "TML2019-30" in a and "TML2026-20" not in a and "GUIDE2021-5.5.1.4" in a
    assert "TML2026-20" in b and "TML2019-30" not in b
    assert "TML2019-31" in basis.basis_for("pre_filing", old, "earlier_app", ["exact"])    # 申请在先引第三十一条
    assert basis.citation("TML2019-30") == "《中华人民共和国商标法》（2019年修正）第三十条"
    assert basis.citation("TML2026-20") == "《中华人民共和国商标法》（2026年修订）第二十条"
    assert "TML2026".replace("TML", "") in basis.law_version_label(new)
    assert "第三十条" in basis.version_note("TML2026-20")      # 新旧对应一对多：30 → 20、34
    assert "第三十条" in basis.version_note("TML2026-34")
