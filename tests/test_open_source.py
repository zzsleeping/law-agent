"""开放数据后端：自建与原库结构相同的小样本库，走一遍建索引 → 召回 → 按日期推定状态。样本均为虚构。"""
import importlib.util
import sqlite3
from datetime import date
from pathlib import Path

import pytest

from app import llm
from app.config import settings
from app.runner import items_by_code, run_pre_filing

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = """
CREATE TABLE sources (source_id INTEGER PRIMARY KEY, category TEXT, period TEXT, official_file TEXT,
  local_file TEXT, compressed_bytes INTEGER, basic_rows INTEGER, named_rows INTEGER, goods_rows INTEGER,
  priority_rows INTEGER, malformed_rows INTEGER, repaired_utf8_fields INTEGER);
CREATE TABLE trademarks (mark_id TEXT, nice_class INTEGER, mark_name TEXT, app_date TEXT, mark_type TEXT,
  mark_form TEXT, preliminary_date TEXT, registration_date TEXT, term_start TEXT, term_end TEXT,
  latest_source_id INTEGER, name_source_id INTEGER, PRIMARY KEY(nice_class, mark_id));
CREATE TABLE goods (mark_id TEXT, nice_class INTEGER, similar_group TEXT, item_sequence TEXT, item_name TEXT,
  item_status TEXT, source_id INTEGER);
CREATE TABLE priorities (mark_id TEXT, nice_class INTEGER, priority_number TEXT, priority_type TEXT,
  priority_date TEXT, priority_goods TEXT, priority_country TEXT, source_id INTEGER);
"""
#  编号, 类别, 名称, 申请日, 初审, 注册, 专用期止, 商品[(群, 名称)]
MARKS = [
    ("90000001", 32, "茗悦", "2015-03-01", "2015-12-01", "2016-03-01", "2036-02-28",
     [("3202", "含果汁的非酒精饮料")]),                                  # 旧版写法，对不上规范名称
    ("90000002", 32, "茗悦", "2010-03-01", "2010-12-01", "2011-03-01", "2021-02-28", [("3202", "无酒精饮料")]),
    ("90000003", 30, "茗悦茶饮", "2026-06-01", None, None, None, [("3002", "茶饮料")]),
    ("90000004", 30, "明月", "2019-01-01", "2019-09-01", None, None, [("3002", "茶饮料")]),
    ("90000005", 30, "茗约", "2020-01-01", None, None, None, [("3002", "茶饮料")]),
    ("90000006", 30, "茗悦", "2026-11-18", None, None, None, [("3002", "茶饮料")]),
    ("90000007", 30, "茗悦", "2026-12-01", None, None, None, [("3002", "茶饮料")]),
    ("90000008", 30, "茗悦轩 及图", "2018-01-01", "2018-09-01", "2018-12-01", "2028-11-30",
     [("3002", "含茶的饮料(非规范名)")]),
    ("90000009", 43, "茗悦", "2015-01-01", "2015-09-01", "2015-12-01", "2035-11-30", [("4301", "餐厅")]),
    ("90000010", 30, "速茗;茗悦", "2016-01-01", "2016-09-01", "2016-12-01", "2036-11-30", [("3002", "茶饮料")]),
]


@pytest.fixture(scope="module")
def open_lib(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("open")
    src = tmp / "open.sqlite3"
    con = sqlite3.connect(src)
    con.executescript(SCHEMA)
    con.execute("INSERT INTO sources VALUES (1,'incremental_data','20261113','tmInfo.zip','x',0,0,0,0,0,0,0)")
    for mid, cls, name, app, pre, reg, end, goods in MARKS:
        con.execute("INSERT INTO trademarks VALUES (?,?,?,?,?,?,?,?,?,?,1,1)",
                    (mid, cls, name, app, "P", None, pre, reg, reg, end))
        con.executemany("INSERT INTO goods VALUES (?,?,?,?,?,?,1)",
                        [(mid, cls, g, str(i), n, None) for i, (g, n) in enumerate(goods)])
    con.commit()
    con.close()
    old = settings.open_db_path, settings.open_index_path, settings.library_backend
    settings.open_db_path, settings.open_index_path, settings.library_backend = str(src), tmp / "idx.sqlite", "sqlite"
    spec = importlib.util.spec_from_file_location("build_open_index", ROOT / "scripts" / "build_open_index.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.main() == 0
    from app.tools import open_source
    open_source._candidates_cached.cache_clear()
    yield
    settings.open_db_path, settings.open_index_path, settings.library_backend = old
    open_source._candidates_cached.cache_clear()


def test_open_library_end_to_end(open_lib):
    llm.set_backend(lambda *a: None)
    v = run_pre_filing("茗悦", goods=items_by_code(["300187"]), eval_date=date(2026, 11, 18),
                       data_scope="real")
    by = {a.mark_id: a for a in v["assessments"]}
    rec = v["records"]
    assert v["classes"] == [29, 30, 32]
    assert "90000009/43" not in by                                    # 第 43 类不在检索范围
    assert by["90000001/32"].prior == "registered" and by["90000001/32"].risk == "high"
    assert by["90000001/32"].goods_rel == "linked"      # 名称对不上，按群号：3002（二）与 3202 全群类似
    assert by["90000002/32"].prior == "expired" and by["90000002/32"].risk == "needs_check"
    assert by["90000003/30"].prior == "earlier_app" and by["90000003/30"].risk == "high"  # 可能在先申请照常评级
    assert by["90000004/30"].prior == "prelim"
    assert by["90000005/30"].prior == "pending_long" and by["90000005/30"].risk == "needs_check"
    assert by["90000006/30"].prior == "same_day" and by["90000006/30"].risk == "needs_check"
    assert by["90000007/30"].prior == "not_prior" and by["90000007/30"].risk == "low"
    # 3002 群各部分之间不类似，对方商品对不上规范名称、所属部分不明 → 待核实；带“及图”的名称按中文部分比对
    assert by["90000008/30"].goods_rel == "pending" and by["90000008/30"].risk == "needs_check"
    assert "contains_weak" in str(v["hits_by_mark"]["90000008/30"])
    assert rec["90000001/32"].source.startswith("国家知识产权局商标开放数据")
    assert rec["90000001/32"].snapshot_date == date(2026, 11, 13)
    # 多段名称按段索引：“速茗;茗悦”经“茗悦”一段完全相同召回，分组用整体名称
    assert "exact" in str(v["hits_by_mark"]["90000010/30"])
    groups = {g["group"]: g for g in v["display_groups"]}
    assert "90000010/30" in groups["速茗茗悦"]["marks"]
    # 同名多件注册归为一组，完全同名组置顶
    assert v["display_groups"][0]["group"] == "茗悦" and len(v["display_groups"][0]["marks"]) >= 4
    assert v["citation_errors"] == []



def test_rejection_review(open_lib):
    """驳回复审：录入引证编号，逐件比对；低风险的引证也有结论；库内找不到的列出来。"""
    from tests.conftest import good_llm
    from app.runner import run_review

    llm.set_backend(good_llm)
    v = run_review("茗悦", ["90000001", "90000005", "90000009", "99999999"], items_by_code(["300187"]),
                   app_date=date(2026, 11, 1), eval_date=date(2026, 11, 18))
    by = {a.mark_id: a for a in v["assessments"]}
    assert set(by) == {"90000001/32", "90000005/30", "90000009/43"}          # 第 43 类也比对，不受检索类别限制
    assert by["90000009/43"].risk == "low"                                     # 餐厅与茶饮料不类似
    assert v["missing_citations"] == ["99999999"]
    assert v["citation_errors"] == []
    kinds = {c.mark_id: c.claim_type for c in v["claims"] if c.mark_id}
    assert kinds.get("90000009/43") == "risk"                                  # 低风险的引证也写比对结论
    assert v["report"]["title"].startswith("驳回复审逐项比对报告")
