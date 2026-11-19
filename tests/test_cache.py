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
    cache.report_put(k, "pre_filing", "茗悦", "报告", payload, b"docx")
    got = cache.report_get(k)
    assert got["payload"]["report"]["title"] == "报告" and got["docx"] == b"docx"
    assert [h["key"] for h in cache.report_find(inputs)] == [k]
    assert cache.report_find({**inputs, "query_mark": "茗悦泉"}) == []
    assert cache.report_recent()[0]["query"] == "茗悦"
