"""依据库查询：带版本的依据 ID、按评估日期判断适用、按映射表给出允许引用的清单。"""
from __future__ import annotations

from datetime import date
from functools import lru_cache

import yaml

from app import db
from app.config import settings

# 命中类型 -> 依据映射表中的维度
KIND_DIM = {
    "exact": "exact", "contains_weak": "contains", "contains_major": "contains", "contains": "contains",
    "shared_part": "shared", "glyph_single": "shape", "edit_one": "shape", "glyph_edit": "shape",
    "pinyin_tone": "sound", "pinyin_plain": "sound", "pinyin_edit": "sound", "pinyin_fuzzy": "sound",
    "meaning": "meaning", "transpose": "transpose", "redup": "redup",
}


@lru_cache(maxsize=2)
def _all(db_path: str) -> dict[str, dict]:
    out = {}
    with db.connect() as c:
        for r in c.execute("SELECT * FROM basis"):
            b = dict(r)
            b["id"] = b.pop("basis_id")
            b["effective_from"] = date.fromisoformat(b["effective_from"])
            b["effective_to"] = date.fromisoformat(b["effective_to"]) if b["effective_to"] else None
            out[b["id"]] = b
    return out


@lru_cache(maxsize=2)
def _map(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_basis(basis_id: str) -> dict | None:
    """返回 {id, doc, version, article, title, effective_from, effective_to, text, source}；不存在返回 None。"""
    return _all(str(settings.db_path)).get(basis_id)


def is_applicable(b: dict, eval_date: date) -> bool:
    return b["effective_from"] <= eval_date <= (b["effective_to"] or date.max)


def _applicable(ids: list[str], eval_date: date) -> list[str]:
    out = []
    for i in ids:
        b = get_basis(i)
        if b and is_applicable(b, eval_date) and i not in out:
            out.append(i)
    return out


def basis_for(scenario: str, eval_date: date, prior: str, kinds: list[str]) -> list[str]:
    """单个候选的建议依据：法条按在先状态选，指南按命中维度选，再按评估日期筛版本。"""
    m = _map(str(settings.data_dir / "basis" / "basis_map.yaml"))
    prior = "valid" if prior in ("registered", "prelim") else prior
    ids = list(m["law"].get(scenario, {}).get(prior, []))
    ids += m["guide"].get("always", [])
    for dim in dict.fromkeys(KIND_DIM[k] for k in kinds if k in KIND_DIM):
        ids += m["guide"].get(dim, [])
    return _applicable(ids, eval_date)


def allowed_basis(scenario: str, eval_date: date, pairs: list[tuple[str, list[str]]]) -> list[str]:
    """本次评估允许引用的依据清单。pairs 为每个候选的 (在先状态, 命中类型列表)。"""
    out: list[str] = []
    for prior, kinds in pairs:
        for i in basis_for(scenario, eval_date, prior, kinds):
            if i not in out:
                out.append(i)
    return out


def citation(basis_id: str) -> str:
    """正式写法。条号只在这里渲染，结论文本里不允许自写。"""
    b = get_basis(basis_id)
    if b is None:
        return basis_id
    if basis_id.startswith("GUIDE"):
        title = b["title"] if len(b["title"]) <= 40 else b["title"][:40] + "……"
        return f"《{b['doc']}》（{b['version']}）{b['article']}“{title}”"
    return f"《{b['doc']}》（{b['version']}）{b['article']}"


def version_note(basis_id: str) -> str:
    """新旧条文对应说明（来自 article_map），没有则为空串。"""
    with db.connect() as c:
        rows = c.execute("SELECT * FROM article_map WHERE old_id=? OR new_id=?", (basis_id, basis_id)).fetchall()
    notes = []
    for r in rows:
        other = r["new_id"] if r["old_id"] == basis_id else r["old_id"]
        which = "新法" if r["old_id"] == basis_id else "旧法"
        notes.append(f"对应{which}{citation(other)}（实质变化：{r['changed']}）。{r['note']}")
    return " ".join(notes)


def law_version_label(eval_date: date) -> str:
    for i, b in _all(str(settings.db_path)).items():
        if i.startswith("TML") and i.endswith("-1") and is_applicable(b, eval_date):
            return f"《{b['doc']}》（{b['version']}）"
    return "未找到适用版本"


def applicable_law(eval_date: date) -> str:
    """评估日期适用的《商标法》版本：TML2019 或 TML2026（按依据库里第一条的施行期间判断）。"""
    for version in ("TML2026", "TML2019"):
        b = get_basis(f"{version}-1")
        if b and is_applicable(b, eval_date):
            return version
    return "TML2019"
