"""商品关系判断：same / similar / linked / pending / dissimilar。

判断顺序（落到具体商品项，群号只作线索）：
1. 任一方未对应到区分表商品项 → pending
2. 编号相同 → same
3. 群组注释“各部分之间不类似”，且两项在同一群的不同部分 → dissimilar
4. 群组注释明确类似 → 跨群为 linked，同群为 similar
5. 开放式列举的注释（如“……等含果汁的饮料”）中未列明的同群项目 → pending
6. 群组注释“各自然段间互不类似”，库里没有自然段划分 → pending
7. 同一类似群（含跨群保护商品的多群归属）→ similar
8. 其余 → dissimilar
注释规则由 app/rules/goods_notes.py 从区分表原文解析，逐条核对表见 data/goods/notes_rules_review.md。
"""
from __future__ import annotations

from functools import lru_cache

from app import db
from app.state import GoodsItem, GoodsRel

ORDER: list[GoodsRel] = ["same", "similar", "linked", "pending", "dissimilar"]
LABEL = {"same": "同一种商品", "similar": "类似商品（同一类似群）", "linked": "类似商品（区分表注释关联）",
         "pending": "待核实", "dissimilar": "不类似"}


@lru_cache(maxsize=2)
def _tables(db_path: str) -> dict:
    with db.connect() as c:
        items: dict[str, dict] = {}
        for r in c.execute("SELECT code, name, nice_class, grp, part FROM goods_items"):
            it = items.setdefault(r["code"], {"code": r["code"], "name": r["name"], "nice_class": r["nice_class"],
                                              "grps": set(), "parts": {}})
            it["grps"].add(r["grp"])
            if r["part"]:
                it["parts"][r["grp"]] = r["part"]
        notes = {r["note_id"]: dict(r) for r in c.execute("SELECT * FROM goods_notes")}
        members: dict[str, dict[str, set]] = {}
        for r in c.execute("SELECT * FROM goods_note_members"):
            members.setdefault(r["note_id"], {"a": set(), "b": set()})[r["side"]].add(r["code"])
    group_codes: dict[str, set] = {}
    for code, it in items.items():
        for g in it["grps"]:
            group_codes.setdefault(g, set()).add(code)
    by_name = {}
    for code, it in items.items():
        by_name.setdefault((it["nice_class"], _clean(it["name"])), code)
    with db.connect() as c:                     # 同号异名的其他名称也能对应到编号
        for r in c.execute("SELECT code, name, nice_class FROM goods_items"):
            by_name.setdefault((r["nice_class"], _clean(r["name"])), r["code"])
    return {"items": items, "notes": notes, "members": members, "group_codes": group_codes, "by_name": by_name}


def _clean(name: str) -> str:
    """商品名称规范化：去星号、空白，半角括号转全角。"""
    return (name or "").replace("*", "").replace("(", "（").replace(")", "）").replace(" ", "").replace("\u3000", "").strip()


def map_goods_name(nice_class: int, name: str) -> str | None:
    """把商品名称原文对应到第十三版区分表的商品项编号；对应不上返回 None。"""
    return tables()["by_name"].get((nice_class, _clean(name)))


def tables() -> dict:
    from app.config import settings

    return _tables(str(settings.db_path))


def _grp(it: dict) -> str:
    return "/".join(sorted(it["grps"]))


def _group_relation(known: dict, other: GoodsItem) -> tuple[GoodsRel, str]:
    """对方商品对应不上规范名称、但有类似群号时，按群号判断。"""
    t = tables()
    g = other.group
    head = f"“{known['name']}”（{_grp(known)}）与“{other.name}”（{g}，未对应到第十三版规范名称，按群号判断）"
    notes, members = t["notes"], t["members"]
    if g in known["grps"]:
        rule = next((n for n in notes.values() if n["grp"] == g and n["rel_type"] in ("明确不类似", "段间待核实")), None)
        if rule:
            return "pending", f"{head}：{g} 群注释 {rule['note_id']} 规定群内各部分或各自然段之间不类似，对方所属部分不明，需核实"
        return "similar", f"{head}：同属 {g} 类似群"
    codes_g = t["group_codes"].get(g, set())
    partial = None
    for note_id, m in members.items():
        n = notes[note_id]
        if n["rel_type"] != "明确类似":
            continue
        for side, other_side in (("a", "b"), ("b", "a")):
            if known["code"] in m[side]:
                if codes_g and codes_g <= m[other_side]:
                    return "linked", f"{head}：区分表注释 {note_id} 与 {g} 全群类似（第 {n['page']} 页）"
                if codes_g & m[other_side]:
                    partial = note_id
    if partial:
        return "pending", f"{head}：区分表注释 {partial} 只列明 {g} 群的部分商品，对方商品是否在列需核实"
    if not codes_g:
        return "pending", f"{head}：{g} 群不在本库收录的类别内，需核实"
    return "dissimilar", f"{head}：不同群，区分表无关联注释"


def item_relation(a: GoodsItem, b: GoodsItem) -> tuple[GoodsRel, str]:
    t = tables()
    ia, ib = t["items"].get(a.code or ""), t["items"].get(b.code or "")
    if ia is not None and ib is None and b.group:
        return _group_relation(ia, b)
    if ib is not None and ia is None and a.group:
        return _group_relation(ib, a)
    if ia is None or ib is None:
        missing = a.name if ia is None else b.name
        return "pending", f"“{missing}”未对应到区分表商品项，需人工综合功能、用途、消费对象、销售渠道判断"
    if a.code == b.code:
        return "same", f"均为“{ib['name']}”（{b.code}）"
    pair = f"“{ia['name']}”（{_grp(ia)}）与“{ib['name']}”（{_grp(ib)}）"
    shared = ia["grps"] & ib["grps"]
    notes, members = t["notes"], t["members"]

    # 3. 同群不同部分，且该群注明各部分之间不类似
    for g in shared:
        pa, pb = ia["parts"].get(g), ib["parts"].get(g)
        if pa and pb and pa != pb:
            rule = next((n for n in notes.values() if n["grp"] == g and n["rel_type"] == "明确不类似"), None)
            if rule:
                return "dissimilar", f"{pair}：{g} 第{pa}部分与第{pb}部分，区分表注释 {rule['note_id']} 明确各部分之间不类似（第 {rule['page']} 页）"

    # 4. 注释明确类似
    for note_id, m in members.items():
        n = notes[note_id]
        if n["rel_type"] != "明确类似":
            continue
        if (a.code in m["a"] and b.code in m["b"]) or (a.code in m["b"] and b.code in m["a"]):
            rel: GoodsRel = "similar" if shared else "linked"
            return rel, f"{pair}：区分表注释 {note_id} 明确类似（第 {n['page']} 页）"

    # 5. 开放式列举：一方在列举的另一侧，另一方在开放侧所在群但未列明
    for note_id, m in members.items():
        n = notes[note_id]
        if n["rel_type"] != "明确类似" or not n["open_side"]:
            continue
        s, other = n["open_side"], "b" if n["open_side"] == "a" else "a"
        for x, y in ((ia, ib), (ib, ia)):
            if x["code"] in m[other] and n["open_grp"] in y["grps"] and y["code"] not in m[s]:
                return "pending", (f"{pair}：区分表注释 {note_id} 为开放式列举（“等……”），"
                                   f"“{y['name']}”未列明，需核实是否符合限定")

    # 6. 各自然段间互不类似，但库里没有自然段划分
    for note_id, m in members.items():
        n = notes[note_id]
        if n["rel_type"] == "段间待核实" and a.code in m["a"] and b.code in m["a"]:
            return "pending", f"{pair}：区分表注释 {note_id} 规定各自然段间互不类似，本库未划分自然段，需核实"

    if shared:
        return "similar", f"{pair}同属 {'/'.join(sorted(shared))} 类似群"
    return "dissimilar", f"{pair}不同群，区分表无关联注释"


@lru_cache(maxsize=500_000)
def _cached_relation(db_path: str, a: tuple, b: tuple) -> tuple[GoodsRel, str]:
    """按 (编号, 名称, 群号) 缓存两两比较结果；同一批商品反复出现时不再遍历注释规则。"""
    mk = lambda x: GoodsItem(code=x[0], name=x[1], group=x[2], nice_class=x[3])  # noqa: E731
    return item_relation(mk(a), mk(b))


def goods_relation(ours: list[GoodsItem], theirs: list[GoodsItem]) -> tuple[GoodsRel, str]:
    """多个商品项两两比较，取最强的一档；遇到“相同”立即返回。"""
    from app.config import settings

    if not ours or not theirs:
        return "pending", "缺少商品项信息"
    key = lambda g: (g.code, g.name, g.group, g.nice_class)  # noqa: E731
    best: tuple[GoodsRel, str] | None = None
    for a in {key(g): g for g in ours}:
        for b in {key(g): g for g in theirs}:
            rel, why = _cached_relation(str(settings.db_path), a, b)
            if best is None or ORDER.index(rel) < ORDER.index(best[0]):
                best = (rel, why)
                if rel == "same":
                    return best
    return best


def history_hints(items: list[GoodsItem]) -> list[str]:
    """历史交叉检索注释：只作提示，不参与定级。"""
    t = tables()
    codes = {i.code for i in items if i.code}
    out = []
    for note_id, n in t["notes"].items():
        if n["rel_type"] != "历史交叉检索":
            continue
        if codes & t["members"].get(note_id, {}).get("a", set()):
            msg = f"{note_id}（第 {n['page']} 页）：{n['comment']}"
            if msg not in out:
                out.append(msg)
    return out


def linked_classes(items: list[GoodsItem]) -> set[int]:
    """召回的类别范围：商品项所在类别 + 区分表注释明确类似的另一侧所在类别。"""
    t = tables()
    classes = {i.nice_class for i in items if i.nice_class}
    codes = {i.code for i in items if i.code}
    for note_id, m in t["members"].items():
        if t["notes"][note_id]["rel_type"] != "明确类似":
            continue
        for side, other in (("a", "b"), ("b", "a")):
            if codes & m[side]:
                classes |= {t["items"][c]["nice_class"] for c in m[other] if c in t["items"]}
    return classes
