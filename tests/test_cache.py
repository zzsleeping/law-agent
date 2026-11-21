"""两层缓存（app/cache.py）：大模型调用缓存与整份报告缓存。用假客户端，不访问网络。"""
from types import SimpleNamespace

import pytest

from app import cache, llm
from app.config import settings


@pytest.fixture
def fake_api(tmp_path, monkeypatch):
    """真实调用路径（不注入假模型），把 OpenAI 客户端换成计数的假客户端。"""
    monkeypatch.setattr(settings, "cache_path", tmp_path / "cache.sqlite")
    monkeypatch.setattr(settings, "cache_enabled", True)
    monkeypatch.setattr(settings, "llm_api_key", "test")
    monkeypatch.setattr(settings, "llm_model", "fake-model")
    llm.set_backend(None)
    calls = []

    def create(**kw):
        calls.append(kw)
        content = '{"mark_sim": "%s", "reason": "第 %d 次"}' % (["high", "low"][len(calls) % 2], len(calls))
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    monkeypatch.setattr(llm, "_client", lambda *a: client)
    return calls


VARS = {"scenario": "申请前筛查", "eval_date": "2026-11-19", "query_mark": "茗悦", "query_meaning": "未提供",
        "goods": "茶饮料", "mark_text": "茗悦泉", "evidence": "- 对方商标完整包含我方商标", "rule_mark_sim": "高",
        "marks": "- X/30：商品相同 在先有效", "cases": "（无）"}


def test_same_prompt_reuses_first_answer(fake_api):
    a = llm.chat_json("p2_judge", VARS)
    b = llm.chat_json("p2_judge", VARS)
    assert a == b and len(fake_api) == 1                 # 第二次不调用，结论不会翻转


def test_changed_facts_call_again(fake_api):
    llm.chat_json("p2_judge", VARS)
    llm.chat_json("p2_judge", {**VARS, "marks": "- X/30：商品类似 在先有效"})
    assert len(fake_api) == 2


def test_ignored_variable_does_not_change_key(fake_api):
    llm.chat_json("p2_judge", VARS, cache_ignore=("eval_date",))
    llm.chat_json("p2_judge", {**VARS, "eval_date": "2026-11-20"}, cache_ignore=("eval_date",))
    assert len(fake_api) == 1                            # 第二天再查，在先状态等事实没变，复用判定


def test_refresh_bypasses_and_overwrites(fake_api):
    first = llm.chat_json("p2_judge", VARS)
    fresh = llm.chat_json("p2_judge", VARS, refresh=True)
    assert len(fake_api) == 2 and fresh != first
    assert llm.chat_json("p2_judge", VARS) == fresh      # 重新评估的结果成为新的缓存


def test_disabled_cache_always_calls(fake_api, monkeypatch):
    monkeypatch.setattr(settings, "cache_enabled", False)
    llm.chat_json("p2_judge", VARS)
    llm.chat_json("p2_judge", VARS)
    assert len(fake_api) == 2


def test_injected_backend_skips_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "cache_path", tmp_path / "cache.sqlite")
    llm.set_backend(lambda name, v: {"mark_sim": "high"})
    try:
        llm.chat_json("p2_judge", VARS)
    finally:
        llm.set_backend(None)
    assert not (tmp_path / "cache.sqlite").exists()


def test_report_roundtrip_and_find(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "cache_path", tmp_path / "cache.sqlite")
    monkeypatch.setattr(settings, "cache_enabled", True)
    inputs = {"scenario": "pre_filing", "query_mark": "茗悦", "goods_desc": "茶饮料"}
    payload = {"report": {"title": "报告"}, "prefix_key": cache.key(inputs, cache.versions()), "goods_names": ["茶饮料"]}
    k = cache.report_key({**inputs, "goods": [("300001", "茶饮料")], "keep": ["A/30"]})
    cache.report_put(k, "pre_filing", "茗悦", "报告", payload, b"docx", user_id=7)
    got = cache.report_get(k, 7)
    assert got["payload"]["report"]["title"] == "报告" and got["docx"] == b"docx"
    assert [h["key"] for h in cache.report_find(inputs, 7)] == [k]
    assert cache.report_find({**inputs, "query_mark": "茗悦泉"}, 7) == []
    assert cache.report_recent(user_id=7)[0]["query"] == "茗悦"


def test_reports_are_private_per_user(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "cache_path", tmp_path / "cache.sqlite")
    monkeypatch.setattr(settings, "cache_enabled", True)
    inputs = {"scenario": "pre_filing", "query_mark": "茗悦", "goods_desc": "茶饮料"}
    payload = {"report": {"title": "报告"}, "prefix_key": cache.key(inputs, cache.versions())}
    k1, k2 = cache.report_key(inputs, 1), cache.report_key(inputs, 2)
    assert k1 != k2                                                     # 同样输入、不同用户各存一份
    cache.report_put(k1, "pre_filing", "茗悦", "报告", payload, b"x", user_id=1)
    assert cache.report_get(k1, 1) is not None and cache.report_get(k1, 2) is None
    assert cache.report_find(inputs, 1) and cache.report_find(inputs, 2) == []
    assert cache.report_recent(user_id=1) and cache.report_recent(user_id=2) == []


@pytest.mark.parametrize("warning", ["degraded", "flagged"])
def test_history_keeps_reports_with_warnings_without_replacing_reusable_report(tmp_path, monkeypatch, warning):
    monkeypatch.setattr(settings, "cache_path", tmp_path / "cache.sqlite")
    monkeypatch.setattr(settings, "cache_enabled", True)
    inputs = {"scenario": "pre_filing", "query_mark": "茗悦", "goods_desc": "茶饮料"}
    confirmed = {"goods": [("300001", "茶饮料")], "keep": ["A/30"]}
    valid = {"report": {"title": "常规报告"}}
    limited = {"report": {"title": "带提示的报告", warning: True}}

    cache.report_save(inputs, confirmed, valid, b"standard", user_id=7, run_id="first")
    cache.report_save(inputs, confirmed, limited, b"limited", user_id=7, run_id="second")

    reports = {r["title"]: r["key"] for r in cache.report_recent(user_id=7)}
    assert set(reports) == {"常规报告", "带提示的报告"}
    saved = cache.report_get(reports["带提示的报告"], 7)
    assert saved["payload"] == limited and saved["docx"] == b"limited"
    assert cache.report_get(reports["带提示的报告"], 8) is None
    assert [r["key"] for r in cache.report_find(inputs, 7)] == [reports["常规报告"]]


def test_history_stays_available_when_reuse_is_disabled(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "cache_path", tmp_path / "cache.sqlite")
    monkeypatch.setattr(settings, "cache_enabled", False)
    inputs = {"scenario": "pre_filing", "query_mark": "茗悦"}
    payload = {"report": {"title": "评估报告"}}

    cache.report_save(inputs, {}, payload, b"pdf", user_id=7, run_id="one")

    [row] = cache.report_recent(user_id=7)
    assert cache.report_get(row["key"], 7)["payload"] == payload
    assert cache.report_find(inputs, 7) == []
    monkeypatch.setattr(settings, "cache_enabled", True)
    assert cache.report_find(inputs, 7) == []
