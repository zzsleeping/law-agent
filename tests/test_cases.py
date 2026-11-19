"""按比对情形检索参考判例。"""
import json

import pytest

from app.config import settings
from app.rules import patterns
from app.tools import cases


def test_classify_patterns():
    assert patterns.classify("茗悦", "茗悦泉") == "完整包含"
    assert patterns.classify("云燕", "燕雲") == "字序颠倒"
    assert patterns.classify("聚丰园", "聚豐園 及图") == "完全相同"
    assert "不列参考判例" in cases.for_pair("聚丰园", "聚豐園")["note"]
    assert patterns.classify("霁川", "雪花") == "无文字命中"
    assert patterns.classify("花言花语", "花言巧语") == "仅一字不同"
    assert patterns.classify("古茗", "古名") == "读音相同/相近"
    assert patterns.classify("喜茶", "嘉茶") == "字形相近"       # 差异只是形近字替换
    assert patterns.classify("可口纯", "可口可乐") == "共用部分"   # “口可”不算字序颠倒
    assert patterns.classify("好太太好生活", "好太太") == "完整包含"
    assert patterns.classify("时尚之夜搜亚", "亚搜") == "字序颠倒"   # 只有局部互换这一种关系


def test_reason_level():
    assert cases.reason_level("“百力士”为臆造词，而“大力士”为固有词汇") == 2
    assert cases.reason_level("在文字构成、呼叫、含义等方面相近") == 1
    assert cases.reason_level("整体尚可区分") == 0


def _case(cid, split, applicant, cited, label, excerpt=""):
    return {"case_id": cid, "split": split, "doc_type": "无效宣告请求裁定书", "decision_date": "2024-01-01",
            "source_url": f"https://example.org/{cid}", "applicant_mark": applicant, "outcome": "",
            "cited": [{"text": cited, "mark_similar": label, "excerpt": excerpt}]}


@pytest.fixture
def lib(tmp_path, monkeypatch):
    data = [
        _case("D1", "tune", "华味", "华味轩", "近似", "未构成近似商标"),
        _case("D2", "tune", "金鼎", "金鼎坊", "近似", "“坊”为常用店铺名称，未形成区别于引证商标的整体含义"),
        _case("D3", "tune", "东升", "东升阁", "不近似", "“东升阁”另有固定含义，整体区别明显，相关公众能够区分"),
        _case("D4", "frozen", "长青", "长青藤", "不近似", "“长青藤”为植物名称，含义已与“长青”明显不同"),
        _case("D5", "tune", "美亚", "亚美", "近似", "字序颠倒，呼叫相近"),
    ]
    (tmp_path / "cases.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(cases, "_path", lambda: str(tmp_path / "cases.json"))
    monkeypatch.setattr(settings, "cases_include_frozen", False)
    cases._load.cache_clear(), cases._pairs.cache_clear()
    yield
    cases._load.cache_clear(), cases._pairs.cache_clear()


def test_same_pattern_both_labels_and_reason_first(lib):
    got = cases.for_pair("茗悦", "茗悦泉")
    assert got["pattern"] == "完整包含"
    assert [c["case_id"] for c in got["similar"]] == ["D2", "D1"]        # 写了理由的排前面
    assert [c["case_id"] for c in got["dissimilar"]] == ["D3"]            # 冻结集一侧默认不展示
    assert all(c["case_id"] != "D5" for c in got["similar"])              # 情形不同的不收


def test_frozen_included_when_enabled(lib, monkeypatch):
    monkeypatch.setattr(settings, "cases_include_frozen", True)
    got = cases.for_pair("茗悦", "茗悦泉")
    assert {c["case_id"] for c in got["dissimilar"]} == {"D3", "D4"}


def test_missing_label_noted_and_unrelated_skipped(lib):
    got = cases.for_pair("云燕", "燕云")
    assert got["similar"] and not got["dissimilar"] and "不近似" in got["note"]
    none = cases.for_pair("霁川", "雪花")
    assert not none["similar"] and "不共用汉字" in none["note"]


def test_report_groups_carry_pattern_cases():
    from app import llm
    from app.runner import items_by_code, run_pre_filing
    from tests.conftest import good_llm
    from tests.test_e2e import EV, TEA

    llm.set_backend(good_llm)
    rep = run_pre_filing("茗悦", goods=items_by_code(TEA), eval_date=EV)["report"]
    risky = rep["high"] + rep["medium"]
    assert risky and all(g["pattern_cases"] is not None for g in risky)
    assert all(g["pattern_cases"] is None for g in rep["low"])
    assert "cases" not in rep
