"""商标开放数据（国家知识产权局）作为正式商标库：候选生成与记录读取。

两个只读库：
- 索引 data/open_index.sqlite（scripts/build_open_index.py 生成）：名称、拼音键、两字片段、掩码、删除键
- 原库 TM_OPEN_DB：商标档案（日期）、商品服务、优先权

商标编号在系统里写成“编号/类别”，因为同一申请号可以有多个类别。
候选生成只负责“可能相关”的名称，是否近似、近似程度仍由 app/tools/search.py 的召回规则判断。
为保证时延，每类候选都有上限；上限会让极常见的片段漏掉部分候选，这一点在报告的检索范围里说明。
"""
from __future__ import annotations

import sqlite3
import threading
from datetime import date
from functools import lru_cache
from pathlib import Path

from app.config import settings
from app.state import GoodsItem, MarkRecord
from app.tools import phonetic

LIMIT_PINYIN = 400
LIMIT_GRAM = 3000
LIMIT_CONTAINS = 20000
LIMIT_MASK = 2000
LIMIT_NAMES = 15000
_local = threading.local()
_lock = threading.Lock()


def available() -> bool:
    return bool(settings.open_db_path) and Path(settings.open_db_path).exists() and settings.open_index_path.exists()


def _conn(kind: str) -> sqlite3.Connection:
    path = str(settings.open_index_path) if kind == "index" else settings.open_db_path
    key = f"{kind}:{path}"
    conns = getattr(_local, "conns", None)
    if conns is None:
        conns = _local.conns = {}
    if key not in conns:
        c = sqlite3.connect(f"file:{path}?mode=ro", uri=True, check_same_thread=False)
        c.row_factory = sqlite3.Row
        conns[key] = c
    return conns[key]


def meta() -> dict:
    if not available():
        return {}
    return {r["key"]: r["value"] for r in _conn("index").execute("SELECT key, value FROM meta")}


def snapshot_date() -> date | None:
    p = meta().get("latest_period", "")
    try:
        return date(int(p[:4]), int(p[4:6]), int(p[6:8])) if len(p) == 8 else None
    except ValueError:
        return None


def _names(sql: str, params) -> dict[int, sqlite3.Row]:
    return {r["name_id"]: r for r in _conn("index").execute(sql, params)}


def _in(col: str, values: list) -> tuple[str, list]:
    return f"{col} IN ({','.join('?' * len(values))})", list(values)


def candidate_names(q: str) -> dict[int, sqlite3.Row]:
    """可能与待查商标相关的名称（name_id → 行）。"""
    from app.tools.search import is_weak

    ix = _conn("index")
    q = phonetic.normalize(q)
    if not q:
        return {}
    k = phonetic.keys(q)
    n = len(q)
    found: dict[int, sqlite3.Row] = {}
    sel = "SELECT name_id, norm, n, py_tone, py, py_fuzzy FROM names WHERE "

    def take(rows: dict) -> None:
        for nid, r in rows.items():
            if len(found) < LIMIT_NAMES:
                found.setdefault(nid, r)

    # 完全相同、对方是我方的一部分、叠字、仅少一字
    exact = {q, q * 2, q * 3}
    exact |= {q[i:j] for i in range(n) for j in range(i + 2, n + 1)}
    exact |= {q[:j] + q[j + 1:] for j in range(n)} if n >= 3 else set()
    for size in range(1, n + 1):
        if n % size == 0 and q[:size] * (n // size) == q and size < n:
            exact.add(q[:size])
    where, params = _in("norm", sorted(exact))
    take(_names(sel + where, params))
    # 拼音
    for col, val in (("py_tone", k["pinyin_tone"]), ("py", k["pinyin"]), ("py_fuzzy", k["pinyin_fuzzy"])):
        take(_names(sel + f"{col}=? LIMIT {LIMIT_PINYIN}", (val,)))
    # 对方完整包含我方：取最少见的两字片段，再逐个核对
    bigrams = sorted({q[j:j + 2] for j in range(n - 1)})
    if bigrams:
        counts = {g: ix.execute("SELECT count(*) FROM grams WHERE gram=?", (g,)).fetchone()[0] for g in bigrams}
        rare = min(bigrams, key=lambda g: counts[g])
        rows = ix.execute(
            f"SELECT g.name_id, m.norm, m.n, m.py_tone, m.py, m.py_fuzzy FROM grams g JOIN names m USING(name_id) "
            f"WHERE g.gram=? LIMIT {LIMIT_CONTAINS}", (rare,)).fetchall()
        take({r["name_id"]: r for r in rows if q in r["norm"]})
    # 共用显著部分、字序颠倒：每个非弱显著的两字片段及其倒序，短名称优先
    pieces = set(bigrams) | {g[::-1] for g in bigrams if g[0] != g[1]}
    for g in sorted(pieces):
        if is_weak(g):
            continue
        rows = ix.execute(
            f"SELECT g.name_id, m.norm, m.n, m.py_tone, m.py, m.py_fuzzy FROM grams g JOIN names m USING(name_id) "
            f"WHERE g.gram=? ORDER BY g.n LIMIT {LIMIT_GRAM}", (g,)).fetchall()
        take({r["name_id"]: r for r in rows})
    # 仅一字不同（含形近替换）、仅多一字
    if n >= 2:
        for j in range(n):
            key = q[:j] + "?" + q[j + 1:]
            take(_names(sel + f"name_id IN (SELECT name_id FROM masks WHERE key=? LIMIT {LIMIT_MASK})", (key,)))
        take(_names(sel + f"name_id IN (SELECT name_id FROM dels WHERE key=? LIMIT {LIMIT_MASK})", (q,)))
    return found


@lru_cache(maxsize=64)
def _candidates_cached(q: str, classes: tuple[int, ...]) -> tuple[dict, ...]:
    names = candidate_names(q)
    if not names or not classes:
        return ()
    ids = list(names)
    out = []
    cls_where, cls_params = _in("nice_class", list(classes))
    for i in range(0, len(ids), 800):
        chunk = ids[i:i + 800]
        where, params = _in("name_id", chunk)
        rows = _conn("index").execute(
            f"SELECT name_id, nice_class, mark_id, full_id FROM name_marks WHERE {where} AND {cls_where}",
            params + cls_params).fetchall()
        fulls = {r["full_id"] for r in rows} - set(names)
        full_norm = {k: v["norm"] for k, v in names.items()}
        for j in range(0, len(fulls), 800):
            part = list(fulls)[j:j + 800]
            w, p = _in("name_id", part)
            full_norm.update({r["name_id"]: r["norm"] for r in _conn("index").execute(
                f"SELECT name_id, norm FROM names WHERE {w}", p)})
        for r in rows:
            nm = names[r["name_id"]]
            out.append({"mark_id": f"{r['mark_id']}/{r['nice_class']}", "text": nm["norm"], "norm_text": nm["norm"],
                        "pinyin_tone": nm["py_tone"], "pinyin": nm["py"], "pinyin_fuzzy": nm["py_fuzzy"],
                        "meaning": "", "group": full_norm.get(r["full_id"], nm["norm"])})
    return tuple(out)


def candidates(q: str, classes) -> list[dict]:
    """开放数据中、在给定类别内的候选商标（每件商标档案一条）。"""
    if not available():
        return []
    with _lock:                       # 五路召回并行调用时只算一次
        return list(_candidates_cached(phonetic.normalize(q), tuple(sorted(set(classes)))))


def _d(v) -> date | None:
    try:
        return date.fromisoformat(v) if v else None
    except ValueError:
        return None


def load_records(ids: list[str]) -> dict[str, MarkRecord]:
    """按“编号/类别”读取商标档案、商品和优先权。"""
    from app.rules.goods_relation import map_goods_name

    if not ids or not available():
        return {}
    src = _conn("source")
    snap = snapshot_date()
    period = meta().get("latest_period", "")
    sources = {r["source_id"]: r for r in src.execute("SELECT source_id, category, period, official_file FROM sources")}
    out = {}
    for key in ids:
        mark_id, _, cls = key.rpartition("/")
        cls = int(cls)
        t = src.execute("SELECT * FROM trademarks WHERE nice_class=? AND mark_id=?", (cls, mark_id)).fetchone()
        if t is None:
            continue
        goods = []
        for g in src.execute("SELECT similar_group, item_name, item_status FROM goods WHERE nice_class=? AND mark_id=? "
                             "ORDER BY item_sequence", (cls, mark_id)):
            code = map_goods_name(cls, g["item_name"])
            goods.append(GoodsItem(name=g["item_name"], code=code, nice_class=cls, group=g["similar_group"],
                                   mapping="confirmed" if code else "pending"))
        pr = src.execute("SELECT min(priority_date) FROM priorities WHERE nice_class=? AND mark_id=?",
                         (cls, mark_id)).fetchone()[0]
        s = sources.get(t["latest_source_id"])
        origin = f"{'增量' if s and s['category'] == 'incremental_data' else '历史'}数据 {s['period']} {s['official_file']}" if s else ""
        out[key] = MarkRecord(
            mark_id=key, text=t["mark_name"] or "", app_date=_d(t["app_date"]), priority_date=_d(pr),
            reg_date=_d(t["registration_date"]), prelim_date=_d(t["preliminary_date"]), term_end=_d(t["term_end"]),
            status=None, goods=goods, snapshot_date=snap,
            source=f"国家知识产权局商标开放数据（增量截至 {period}）",
            source_ref=f"第 {mark_id} 号第 {cls} 类；原始包：{origin}", is_simulated=False)
    return out


def coverage() -> dict:
    m = meta()
    if not m:
        return {}
    return {"count": int(m.get("marks", 0)), "names": int(m.get("names", 0)),
            "date": str(snapshot_date() or ""), "classes": "29,30,32,43"}


def find(mark_id: str) -> list[str]:
    """按编号找出各类别的档案（“编号/类别”）。"""
    if not available() or not mark_id:
        return []
    rows = _conn("source").execute("SELECT nice_class FROM trademarks WHERE mark_id=? ORDER BY nice_class",
                                   (mark_id.strip(),)).fetchall()
    return [f"{mark_id.strip()}/{r['nice_class']}" for r in rows]
