"""商品项映射：把用户的商品描述对应到区分表规范商品项。"""
from __future__ import annotations

import re

from app import db
from app.embed import get_embedder
from app.state import GoodsItem


def all_items() -> list[dict]:
    with db.connect() as c:
        return [dict(r) for r in c.execute(
            "SELECT code, name, nice_class, grp FROM goods_items ORDER BY nice_class, grp, code")]


def split_desc(desc: str) -> list[str]:
    return [p for p in (x.strip() for x in re.split(r"[、，,；;\n/]+", desc or "")) if p]


def _clean(name: str) -> str:
    return name.replace("*", "").strip()


def search_items(part: str, k: int = 5) -> list[dict]:
    """向量检索区分表商品项，返回 [{code, name, nice_class, grp, sim}]。"""
    col = db.collection("goods_items")
    n = col.count()
    if n == 0:
        return []
    emb = get_embedder(db.get_meta("embed_backend"))
    res = col.query(query_embeddings=emb.embed([part]), n_results=min(k, n))
    return [{**meta, "sim": round(1.0 - dist, 3)} for meta, dist in zip(res["metadatas"][0], res["distances"][0])]


def to_item(meta: dict, mapping: str = "pending") -> GoodsItem:
    return GoodsItem(name=meta["name"], code=meta["code"], nice_class=meta["nice_class"],
                     group=meta["grp"], mapping=mapping)


def map_goods(desc: str) -> tuple[list[GoodsItem], dict[str, list[dict]]]:
    """返回 (建议商品项, 每段描述的候选)。

    名称与规范名称完全一致的直接采用；否则取向量检索第一名作为建议，
    一律标 pending，等用户在页面上确认。
    """
    exact = {}
    for it in all_items():
        exact.setdefault(_clean(it["name"]), it)
        exact.setdefault(_clean(it["name"]).split("（")[0], it)
    proposal: list[GoodsItem] = []
    candidates: dict[str, list[dict]] = {}
    for part in split_desc(desc):
        cands = search_items(part)
        candidates[part] = cands
        if part in exact:
            proposal.append(to_item(exact[part], "confirmed"))
        elif cands:
            proposal.append(to_item(cands[0], "pending"))
        else:
            proposal.append(GoodsItem(name=part, mapping="pending"))
    seen, out = set(), []
    for p in proposal:
        key = (p.code, p.name)
        if key not in seen:
            seen.add(key)
            out.append(p)
    return out, candidates
