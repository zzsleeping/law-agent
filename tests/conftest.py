"""测试夹具：用哈希向量在临时目录建库，不访问网络；默认不配置大模型。"""
import importlib.util
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import llm  # noqa: E402
from app.config import settings  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def test_db(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("tm")
    settings.db_path = tmp / "tm.db"
    settings.chroma_dir = tmp / "chroma"
    settings.output_dir = tmp / "outputs"
    settings.embed_backend = "hash"
    settings.open_db_path = ""                 # 默认不用开放数据；test_open_source.py 自建小样本库
    settings.open_index_path = tmp / "no_open_index.sqlite"
    settings.llm_api_key = ""
    settings.meaning_threshold = 0.3          # 哈希向量的相似度分布与 bge 不同
    spec = importlib.util.spec_from_file_location("gen_simulated", ROOT / "tests" / "fixtures" / "gen_simulated.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.main()
    settings.fixture_marks = ROOT / "tests" / "fixtures" / "simulated_marks.json"
    from app.ingest import build

    build(embed_backend="hash", verbose=False)
    yield


@pytest.fixture(autouse=True)
def no_llm():
    llm.set_backend(None)
    yield
    llm.set_backend(None)


def good_llm(prompt_name: str, variables: dict) -> dict:
    """行为正确的假模型：按材料里给出的事实 ID 和建议依据写结论。"""
    if prompt_name == "p1_parse":
        return {"distinctive": variables["query_mark"], "meaning": "", "goods": []}
    if prompt_name == "p2_explain":
        return {"explanation": "（假模型）两商标近似，商品类似。", "flag_review": False}
    claims = []
    for block in re.split(r"\n(?=- mark_id: )", variables["assessments"]):
        m = re.match(r"- mark_id: (\S+)", block)
        if not m:
            continue
        facts = re.findall(r"\[(F-[^\]]+)\]", block)
        basis_ids = [b.strip() for b in re.search(r"建议依据：(.*)", block).group(1).split(",") if b.strip()]
        claims.append({"mark_id": m.group(1), "claim_type": "risk", "conclusion": "（假模型）构成近似商标的可能性较大。",
                       "fact_ids": facts[:2], "basis_ids": basis_ids[:2]})
    first = claims[0]
    claims.append({"mark_id": None, "claim_type": "overall", "conclusion": "（假模型）存在在先障碍。",
                   "fact_ids": ["F-SCOPE"], "basis_ids": first["basis_ids"][:1]})
    # 模型越权写的数据缺口结论应被代码丢弃
    claims.append({"mark_id": first["mark_id"], "claim_type": "data_gap", "conclusion": "多余", "fact_ids": [], "basis_ids": []})
    return {"claims": claims}


def bad_llm(prompt_name: str, variables: dict) -> dict:
    """始终犯错的假模型：不给依据，还自己写条号。"""
    data = good_llm(prompt_name, variables)
    if prompt_name == "p3_compose":
        for c in data["claims"]:
            c["basis_ids"] = []
            c["conclusion"] += "违反商标法第三十条。"
    return data


def timeout_llm(prompt_name: str, variables: dict) -> dict:
    raise TimeoutError("模拟模型超时")
