"""拼音三档、加权编辑距离、字序与叠字、RRF 与展示顺序。"""
from app.config import settings
from app.nodes.merge import display_order, rrf_scores
from app.state import Hit
from app.tools import glyph, phonetic, search

C30 = {29, 30, 32}


def kinds(hits, text=None):
    from app import db

    recs = db.load_records([h.mark_id for h in hits])
    return {(recs[h.mark_id].text, h.kind) for h in hits if text is None or recs[h.mark_id].text == text}


def test_pinyin_keys_and_fuzzy():
    k = phonetic.keys("茗悦")
    assert k["pinyin"] == "ming yue" and k["pinyin_tone"] == "ming2 yue4"
    assert phonetic.keys("民悦")["pinyin_fuzzy"] == k["pinyin_fuzzy"]          # ing/in
    assert phonetic.keys("蓝柠")["pinyin_fuzzy"] == phonetic.keys("南柠")["pinyin_fuzzy"]   # n/l
    assert phonetic.fuzzy_syllable("zhang") == "zan" and phonetic.fuzzy_syllable("shi") == "si"
    assert phonetic.edit_distance(["yun", "wu", "zhi", "chun"], ["yun", "wu", "ying", "chun"]) == 1


def test_pinyin_three_tiers():
    hits = search.recall_pinyin("茗悦", C30)
    got = kinds(hits)
    assert ("明月", "pinyin_tone") in got          # 带声调相同
    assert ("茗约", "pinyin_plain") in got         # 无声调相同
    assert ("民悦", "pinyin_fuzzy") in got         # 仅模糊音，单独通道
    fuzzy = [h for h in hits if h.kind == "pinyin_fuzzy"]
    assert all(h.channel == "pinyin_fuzzy" for h in fuzzy)
    tone = [h.rank for h in hits if h.kind == "pinyin_tone"]
    plain = [h.rank for h in hits if h.kind == "pinyin_plain"]
    assert max(tone) < min(plain)                  # 三档依次排列
    assert ("云雾迎春", "pinyin_edit") in kinds(search.recall_pinyin("云雾知春", C30))


def test_weighted_distance():
    d, diffs = glyph.weighted_distance("沐茶", "沐荼")
    assert abs(d - settings.glyph_sub_cost) < 1e-9 and diffs == [("茶", "荼", True)]
    d, diffs = glyph.weighted_distance("云雾知春", "云雾迎春")
    assert d == 1.0 and diffs == [("知", "迎", False)]
    assert glyph.weighted_distance("茗悦", "茗悦茶")[0] == 1.0
    assert glyph.weighted_distance("己已", "已己")[0] < 1.0


def test_glyph_recall():
    got = kinds(search.recall_glyph("沐茶", C30))
    assert ("沐荼", "glyph_single") in got and ("沭茶", "glyph_single") in got
    assert ("云雾迎春", "edit_one") in kinds(search.recall_glyph("云雾知春", C30))       # 首字相同、仅一字不同
    # 两字商标不允许一个普通替换（否则“茗约”这类会全部进来）
    assert not any(t == "茗约" for t, _ in kinds(search.recall_glyph("茗悦", C30)))


def test_exact_and_contains():
    hits = search.recall_exact("茗悦", C30)
    got = kinds(hits)
    assert ("茗悦", "exact") in got
    assert ("茗悦茶饮", "contains_weak") in got    # 多出“茶饮”为弱显著文字
    assert ("茗悦时光", "contains_major") in got   # “时光”不是弱显著文字，但被包含部分占一半
    assert ("南柠咖啡", "contains_weak") in kinds(search.recall_exact("南柠", {43}))
    assert not search.recall_exact("茗悦", {43}, "real")       # 真实库目前为空


def test_transpose_and_redup():
    assert glyph.is_adjacent_swap("坤星", "星坤") == ("坤", "星")
    assert glyph.is_adjacent_swap("云雾知春", "云知雾春") == ("雾", "知")
    assert glyph.is_adjacent_swap("云雾知春", "春雾知云") is None      # 非相邻
    assert glyph.reduplication("星", "星星") == "星"
    assert glyph.reduplication("哈罗哈罗", "哈罗") == "哈罗"
    assert glyph.reduplication("哈罗", "哈罗罗") is None
    got = kinds(search.recall_variant("茗悦", C30))
    assert ("悦茗", "transpose") in got and ("茗悦茗悦", "redup") in got
    assert ("星海", "transpose") in kinds(search.recall_variant("海星", C30))


def test_rrf_and_display_order():
    hits = [
        Hit(mark_id="A", channel="pinyin", kind="pinyin_tone", rank=1),
        Hit(mark_id="A", channel="glyph", kind="glyph_single", rank=1),
        Hit(mark_id="B", channel="pinyin", kind="pinyin_plain", rank=2),
        Hit(mark_id="C", channel="pinyin_fuzzy", kind="pinyin_fuzzy", rank=1),
        Hit(mark_id="X", channel="exact", kind="exact", rank=1),
    ]
    s = rrf_scores(hits)
    k = settings.rrf_k
    assert abs(s["A"] - 2 / (k + 1)) < 1e-12
    assert abs(s["B"] - 1 / (k + 2)) < 1e-12
    assert abs(s["C"] - 0.5 / (k + 1)) < 1e-12            # 模糊音权重 0.5
    assert display_order(hits) == ["X", "A", "B", "C"]     # 完全同名置顶，其余按 RRF
    many = [Hit(mark_id=f"M{i:02d}", channel="pinyin", kind="pinyin_plain", rank=i) for i in range(1, 31)]
    order = display_order(many + [Hit(mark_id="X", channel="exact", kind="exact", rank=1)])
    assert order[0] == "X" and len(order) == 1 + settings.top_n_assess     # 同名不占名额


def test_new_match_kinds():
    def kinds_of(q, t):
        return {h.kind for h in search.compare(q, t)}
    assert search.longest_common("青藏冰泉", "青藏老酸奶") == "青藏"
    assert "shared_part" in kinds_of("温氏冰行", "温氏集团")        # 共有“温氏”，各自另有文字
    assert "shared_part" not in kinds_of("茗悦茶饮", "蜜雪茶饮")    # 共有部分是弱显著文字，不算
    assert "transpose" in kinds_of("坤星文具", "星坤")               # 字序颠倒 + 附加文字
    assert "transpose" in kinds_of("云燕", "燕云轩")
    assert "edit_one" in kinds_of("心之必达", "心至必达")
    assert "edit_one" in kinds_of("云燕", "云之燕")                  # 仅多一字、首字相同
    assert "edit_one" not in kinds_of("茗悦", "茗约")                # 两字商标换一字不算
    assert "edit_one" not in kinds_of("北美风情", "南美风情")        # 首字不同
    assert "contains_major" in kinds_of("华为海思", "华为")
    assert "contains" in kinds_of("蜜雪冰城带上雪王共赴春光", "春光")  # 占比小，只到中


def test_ids_glyph_similarity():
    assert glyph.ids_distance("沐", "沭") <= glyph.GLYPH_IDS_MAX     # 只差一个“丶”
    assert glyph.ids_distance("土", "士") == 0                      # 拆分相同
    assert glyph.ids_distance("香", "杳") <= glyph.GLYPH_IDS_MAX     # 不在手工字表里，靠部件拆分
    assert glyph.is_glyph_pair("香", "杳")
    assert not glyph.is_glyph_pair("茗", "铭")                      # 偏旁不同
    assert not glyph.is_glyph_pair("沐", "汁")
    assert glyph.is_glyph_pair("己", "已")                          # 单部件字，靠手工字表


def test_traditional_normalized():
    assert phonetic.normalize("燕雲樓 及图") == "燕云楼"
    assert "exact" in {h.kind for h in search.compare("聚丰园", "聚豐園")}
    assert "transpose" in {h.kind for h in search.compare("云燕", "燕雲")}
