"""群组注释解析与完整区分表下的商品关系。"""
from app import db
from app.rules.goods_notes import parse_note
from app.rules.goods_relation import goods_relation, history_hints, linked_classes, tables
from app.state import GoodsItem


def item(name: str, grp: str | None = None) -> GoodsItem:
    sql = "SELECT code, name, nice_class, grp FROM goods_items WHERE name=?" + (" AND grp=?" if grp else "")
    with db.connect() as c:
        r = c.execute(sql, (name, grp) if grp else (name,)).fetchone()
    assert r, name
    return GoodsItem(name=r["name"], code=r["code"], nice_class=r["nice_class"], group=r["grp"], mapping="confirmed")


def rel(a: GoodsItem, b: GoodsItem) -> str:
    return goods_relation([a], [b])[0]


def test_parse_note_shapes():
    r = parse_note("3002", "注2", "第（二）部分与2907第二自然段，3001加奶可可饮料，咖啡饮料，3202类似，"
                                  "与第十版及以前版本3011豆浆，豆汁交叉检索。")
    assert [x.rel_type for x in r] == ["明确类似", "历史交叉检索"]
    a, b = r[0].sides
    assert a[0].scope == "part" and a[0].part == "（二）"
    assert [(s.group, s.scope) for s in b] == [("2907", "para"), ("3001", "items"), ("3202", "whole")]
    assert b[1].names == ["加奶可可饮料", "咖啡饮料"]
    r = parse_note("3202", "注3", "果汁，柠檬水等含果汁的饮料与3013果汁刨冰类似")
    assert r[0].sides[0][0].open_ended and r[0].sides[0][0].names == ["果汁", "柠檬水"]
    assert parse_note("3002", "注1", "本类似群各部分之间商品不类似；")[0].rel_type == "明确不类似"
    assert parse_note("3019", "注", "本类似群为单一商品，各自然段间互不类似。")[0].rel_type == "段间待核实"
    assert parse_note("3202", "注4", "格瓦斯与第九版及以前版本3201克瓦斯淡啤酒（无酒精饮料）类似。")[0].rel_type == "历史交叉检索"
    assert parse_note("3003", "注1", "跨类似群保护商品：糖（3003，3004）；")[0].rel_type == "跨群保护"
    assert parse_note("3011", "注", "本类似群第十一版时豆粉移入3008类似群。")[0].rel_type == "说明"


def test_all_notes_resolved():
    """库内群组的注释，名称都应对应到商品项（核对表里不应有“未对应”）。"""
    t = tables()
    assert len(t["items"]) > 900
    unresolved = [n["note_id"] for n in t["notes"].values() if "未对应" in (n["side_a"] or "") + (n["side_b"] or "")]
    assert unresolved == []
    types = {n["rel_type"] for n in t["notes"].values()}
    assert {"明确类似", "明确不类似", "段间待核实", "历史交叉检索"} <= types


def test_cross_group_items():
    sugar = item("糖*")                                # 跨群保护：3003、3004
    assert tables()["items"][sugar.code]["grps"] == {"3003", "3004"}
    sweets_3004 = item("甜食", "3004")
    assert rel(sugar, sweets_3004) == "similar"        # 经 3004 同群


def test_new_group_notes():
    assert rel(item("方便米饭"), item("方便面")) == "linked"               # 3007 注：与 3009 类似
    soy = item("酱菜（调味品）")
    assert rel(soy, item("酱菜")) == "linked"                               # 3016 注2 ↔ 2905
    g3014 = next(i for i in tables()["items"].values() if "3014" in i["grps"])
    g3016 = next(i for i in tables()["items"].values() if "3016" in i["grps"] and len(i["grps"]) == 1)
    a = GoodsItem(name=g3014["name"], code=g3014["code"], nice_class=30, mapping="confirmed")
    b = GoodsItem(name=g3016["name"], code=g3016["code"], nice_class=30, mapping="confirmed")
    assert rel(a, b) == "linked"                                            # 3014 与 3016 全群类似


def test_paragraph_and_parts():
    t = tables()
    g3019 = [i for i in t["items"].values() if "3019" in i["grps"]]
    a, b = (GoodsItem(name=i["name"], code=i["code"], nice_class=30, mapping="confirmed") for i in g3019[:2])
    assert rel(a, b) == "pending"                                           # 段间互不类似，库里没有自然段
    g4306 = [i for i in t["items"].values() if "4306" in i["grps"]]
    p1 = next(i for i in g4306 if i["parts"].get("4306") == "（一）")
    p2 = next(i for i in g4306 if i["parts"].get("4306") == "（二）")
    x, y = (GoodsItem(name=i["name"], code=i["code"], nice_class=43, mapping="confirmed") for i in (p1, p2))
    assert rel(x, y) == "dissimilar"                                        # 4306 各部分之间不类似


def test_history_hints_and_classes():
    hints = history_hints([item("茶饮料")])
    assert any(h.startswith("3002-注2-历史") for h in hints)
    assert linked_classes([item("茶饮料")]) == {29, 30, 32}
    assert linked_classes([item("餐厅")]) == {43}
