"""校验脚本本身的测试：合格样例应通过，常见错误应被拦下。样例内容均为虚构。"""
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load(tmp: Path):
    spec = importlib.util.spec_from_file_location("validate_collected", ROOT / "scripts" / "validate_collected.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.COLLECTED = tmp
    return mod


def good_doc(no: str, cited_text: str = "茗月", similar: str = "近似") -> dict:
    return {
        "doc_type": "驳回复审决定书", "doc_no": no, "decision_date": "2024-05-20", "authority": "国家知识产权局",
        "source_url": "https://example.invalid/doc", "retrieved_at": "2026-11-16",
        "applicant_mark": {"text": "茗悦", "app_no": "70000001", "app_date": "2023-01-10", "priority_date": None,
                           "owner": "某某茶饮有限公司",
                           "goods": [{"name": "茶饮料", "nice_class": 30, "group": "3002"}]},
        "cited_marks": [{"text": cited_text, "reg_no": "10000001", "app_date": "2018-03-02", "status": "已注册",
                         "owner": "某某食品有限公司",
                         "goods": [{"name": "茶饮料", "nice_class": 30, "group": "3002"}],
                         "mark_similar": similar, "goods_similar": "类似", "reasoning_excerpt": "二者呼叫相近。"}],
        "outcome": "驳回" if similar == "近似" else "初步审定", "outcome_scope": None, "notes": None,
    }


def write(tmp: Path, docs: list[dict]) -> None:
    d = tmp / "decisions"
    d.mkdir(parents=True, exist_ok=True)
    for doc in docs:
        (d / f"{doc['doc_no']}.json").write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    (d / "REPORT.md").write_text("报告", encoding="utf-8")


def run(tmp: Path):
    mod = load(tmp)
    r = mod.Report()
    mod.check_decisions(r)
    return r


def test_good_decisions_pass(tmp_path):
    write(tmp_path, [good_doc("A-1"), good_doc("A-2", "星海", "不近似")])
    r = run(tmp_path)
    assert r.errors == []
    assert any("样本偏少" in w for w in r.warnings)


def test_common_mistakes_are_caught(tmp_path):
    bad = good_doc("B-1")
    bad["decision_date"] = "2024/05/20"
    bad["applicant_mark"]["goods"][0]["group"] = "3202"            # 群组与类别不符
    bad["cited_marks"][0]["mark_similar"] = "高度近似"              # 不在枚举内
    bad["cited_marks"][0]["owner"] = "张三"                          # 自然人姓名
    bad["cited_marks"][0]["reasoning_excerpt"] = "字" * 120
    del bad["source_url"]
    dup = good_doc("B-1")                                            # 文书编号重复
    write(tmp_path, [bad])
    (tmp_path / "decisions" / "B-1-copy.json").write_text(json.dumps(dup, ensure_ascii=False), encoding="utf-8")
    r = run(tmp_path)
    text = "\n".join(r.errors)
    for key in ("decision_date 不是", "group 3202 与类别 30 不一致", "mark_similar 只能是", "超过 100 字",
                "source_url 缺失", "文书编号与"):
        assert key in text, key
    assert any("像自然人姓名" in w for w in r.warnings)


def test_outcome_consistency_warning(tmp_path):
    doc = good_doc("C-1")
    doc["cited_marks"][0]["mark_similar"] = "不近似"                 # 驳回但没有近似引证
    write(tmp_path, [doc])
    r = run(tmp_path)
    assert any("结果为驳回" in w for w in r.warnings)


def test_missing_goods_preserves_sourced_findings(tmp_path):
    doc = good_doc("D-1")
    citation = doc["cited_marks"][0]
    citation.update(goods=None, notes="官文明确认定近似，原文和详情页未列商品名称。")
    write(tmp_path, [doc])
    assert run(tmp_path).errors == []

    doc["applicant_mark"]["goods"] = None
    doc["notes"] = "决定书给出申请商标编号，未逐项列出商品。"
    write(tmp_path, [doc])
    assert run(tmp_path).errors == []

    for change in ({"goods": []}, {"notes": None}):
        write(tmp_path, [{**doc, "cited_marks": [{**citation, **change}]}])
        assert any("goods 必须是非空数组" in error for error in run(tmp_path).errors)

    citation.pop("goods")
    write(tmp_path, [doc])
    assert any("goods 必须是非空数组" in error for error in run(tmp_path).errors)


def test_references_without_verified_chinese_text_are_kept_as_context(tmp_path, capsys):
    doc = good_doc("E-1")
    chinese = doc["cited_marks"][0]
    numeric = {**chinese, "reg_no": "10000002", "text": "1828", "notes": "图样仅含数字。"}
    unknown = {**chinese, "reg_no": "10000003", "text": None, "notes": "决定书仅载编号。"}
    doc["cited_marks"] = [chinese, numeric, unknown]
    write(tmp_path, [doc])
    assert run(tmp_path).errors == []
    output = capsys.readouterr().out
    assert "引证商标 3 个：近似 1" in output
    assert "2 件引证无已核实的中文文字" in output

    doc["cited_marks"] = [numeric, unknown]
    write(tmp_path, [doc])
    assert any("没有可核实的中文文字引证商标" in err for err in run(tmp_path).errors)



def test_outcomes_by_doc_type(tmp_path):
    """无效宣告、不予注册复审有各自的结果取值；跨类型的取值报错。"""
    inv = good_doc("F-1")
    inv.update(doc_type="无效宣告请求裁定书", outcome="宣告无效")
    keep = good_doc("F-2", "星海", "不近似")
    keep.update(doc_type="无效宣告请求裁定书", outcome="维持注册")
    opp = good_doc("F-3")
    opp.update(doc_type="不予注册复审决定书", outcome="部分不予注册", outcome_scope="茶饮料不予注册")
    write(tmp_path, [inv, keep, opp])
    assert run(tmp_path).errors == []
    bad = good_doc("F-4")
    bad.update(doc_type="无效宣告请求裁定书", outcome="驳回")
    write(tmp_path, [bad])
    assert any("无效宣告请求裁定书 的 outcome 只能是" in e for e in run(tmp_path).errors)
