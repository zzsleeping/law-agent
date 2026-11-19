"""SQLite 与 Chroma 的访问入口，以及表结构（方案第八节）。"""
from __future__ import annotations

import sqlite3
from datetime import date

from app.config import settings
from app.state import GoodsItem, MarkRecord

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);

CREATE TABLE IF NOT EXISTS marks (
  mark_id        TEXT PRIMARY KEY,   -- 注册号 / 申请号；仿真数据以 SIM- 开头
  text           TEXT NOT NULL,
  norm_text      TEXT NOT NULL,      -- 去空格、统一大小写后的文字
  pinyin_tone    TEXT,
  pinyin         TEXT,
  pinyin_fuzzy   TEXT,
  meaning        TEXT,
  owner          TEXT,
  app_date       DATE,
  priority_date  DATE,
  reg_date       DATE,
  prelim_date    DATE,               -- 初审公告日
  term_end       DATE,               -- 记录的专用期截止日
  status         TEXT,               -- 状态文字；开放数据为空，按日期推定
  invalid_date   DATE,               -- 失效日期，可空
  invalid_reason TEXT,               -- 失效原因，可空
  snapshot_date  DATE NOT NULL,
  source         TEXT NOT NULL,
  source_ref     TEXT,
  is_simulated   INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_marks_norm ON marks(norm_text);
CREATE INDEX IF NOT EXISTS idx_marks_py ON marks(pinyin);
CREATE INDEX IF NOT EXISTS idx_marks_pyf ON marks(pinyin_fuzzy);

CREATE TABLE IF NOT EXISTS mark_goods (
  mark_id    TEXT REFERENCES marks(mark_id),
  item_name  TEXT,                   -- 核定商品原文
  item_code  TEXT,                   -- 区分表商品项编号，对不上则为空
  nice_class INTEGER,
  grp        TEXT
);
CREATE INDEX IF NOT EXISTS idx_mg_mark ON mark_goods(mark_id);
CREATE INDEX IF NOT EXISTS idx_mg_class ON mark_goods(nice_class);

CREATE TABLE IF NOT EXISTS basis (
  basis_id       TEXT PRIMARY KEY,
  doc            TEXT,
  version        TEXT,
  article        TEXT,
  title          TEXT,
  effective_from DATE,
  effective_to   DATE,
  text           TEXT,
  source         TEXT,
  dimension      TEXT                -- 指南条目的适用维度（JSON 数组），法条为空
);

CREATE TABLE IF NOT EXISTS article_map (
  old_id TEXT, new_id TEXT, changed TEXT, note TEXT
);

CREATE TABLE IF NOT EXISTS goods_items (   -- 同号异名、跨群重复列出都存在，主键为 编号 + 名称 + 群组
  code TEXT, name TEXT, nice_class INTEGER, grp TEXT, part TEXT, page TEXT,
  PRIMARY KEY (code, name, grp)
);

CREATE TABLE IF NOT EXISTS goods_notes (     -- 由群组注释原文解析而来（app/rules/goods_notes.py）
  note_id TEXT PRIMARY KEY, grp TEXT, rel_type TEXT, side_a TEXT, side_b TEXT,
  comment TEXT, page TEXT, open_side TEXT, open_grp TEXT, parts TEXT
);

CREATE TABLE IF NOT EXISTS goods_note_members (
  note_id TEXT, side TEXT, code TEXT
);
"""


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row
    return conn


def get_meta(key: str, default: str | None = None) -> str | None:
    with connect() as c:
        row = c.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def _d(v) -> date | None:
    return date.fromisoformat(v) if v else None


def scope_sql(data_scope: str | None) -> str:
    if data_scope == "real":
        return " AND m.is_simulated = 0"
    if data_scope == "simulated":
        return " AND m.is_simulated = 1"
    return ""


def load_records(mark_ids: list[str]) -> dict[str, MarkRecord]:
    from app.library import get_library

    lib_ids = [m for m in mark_ids if "/" in m]          # 正式库的编号写成“编号/类别”
    local = _load_local([m for m in mark_ids if "/" not in m])
    return {**local, **(get_library().load_records(lib_ids) if lib_ids else {})}


def _load_local(mark_ids: list[str]) -> dict[str, MarkRecord]:
    if not mark_ids:
        return {}
    qs = ",".join("?" * len(mark_ids))
    with connect() as c:
        rows = c.execute(f"SELECT * FROM marks WHERE mark_id IN ({qs})", mark_ids).fetchall()
        goods = c.execute(f"SELECT * FROM mark_goods WHERE mark_id IN ({qs})", mark_ids).fetchall()
    by_mark: dict[str, list[GoodsItem]] = {}
    for g in goods:
        by_mark.setdefault(g["mark_id"], []).append(GoodsItem(
            name=g["item_name"], code=g["item_code"], nice_class=g["nice_class"], group=g["grp"],
            mapping="confirmed" if g["item_code"] else "pending"))
    out = {}
    for r in rows:
        out[r["mark_id"]] = MarkRecord(
            mark_id=r["mark_id"], text=r["text"], meaning=r["meaning"] or "", owner=r["owner"] or "",
            app_date=_d(r["app_date"]), priority_date=_d(r["priority_date"]), reg_date=_d(r["reg_date"]),
            prelim_date=_d(r["prelim_date"]), term_end=_d(r["term_end"]),
            status=r["status"], invalid_date=_d(r["invalid_date"]), invalid_reason=r["invalid_reason"],
            goods=by_mark.get(r["mark_id"], []), snapshot_date=_d(r["snapshot_date"]),
            source=r["source"], source_ref=r["source_ref"], is_simulated=bool(r["is_simulated"]))
    return out


def coverage() -> dict:
    """界面展示的数据覆盖范围：真实 / 仿真条数、类别、数据日期。开放数据可用时，真实部分以开放数据为准。"""
    from app.library import get_library

    out = _coverage_local()
    oc = get_library().coverage() if get_library().available() else {}
    if oc:
        out["real"] = {"count": oc["count"], "date": oc["date"], "classes": oc["classes"], "source": "open"}
    return out


def uncovered_classes(classes, cov: dict | None = None) -> list[int]:
    """检索类别中不在正式商标库（开放数据）覆盖范围内的类别；未接入开放数据时返回空（另有提示）。"""
    cov = cov or coverage()
    real = cov.get("real", {})
    if real.get("source") != "open" or not real.get("classes"):
        return []
    have = {int(x) for x in str(real["classes"]).replace("，", ",").split(",") if x.strip().isdigit()}
    return sorted({int(c) for c in classes} - have)


def uncovered_note(classes, cov: dict | None = None, pending: list[str] | tuple = ()) -> str:
    """检索范围提示：检索类别超出正式商标库，或有商品没对应到区分表选录（多半属于其他类别）。都没有时返回空串。"""
    cov = cov or coverage()
    real = cov.get("real", {})
    if real.get("source") != "open":
        return ""
    have = "、".join(x.strip() for x in str(real.get("classes", "")).split(",") if x.strip())
    parts = []
    if miss := uncovered_classes(classes, cov):
        parts.append(f"第 {'、'.join(map(str, miss))} 类不在正式商标库范围内（开放数据只覆盖第 {have} 类），这些类别检索不到在先商标")
    if pending := [p for p in pending if p]:
        parts.append(f"“{'、'.join(pending)}”没有对应到区分表选录（第 {have} 类），如属于其他类别，正式商标库检索不到相关在先商标")
    return ("；".join(parts) + "。结果不代表没有冲突，请另行检索。") if parts else ""


def _coverage_local() -> dict:
    with connect() as c:
        rows = c.execute(
            "SELECT is_simulated, COUNT(*) n, MAX(snapshot_date) d FROM marks GROUP BY is_simulated").fetchall()
        classes = c.execute(
            "SELECT m.is_simulated s, GROUP_CONCAT(DISTINCT g.nice_class) cls FROM marks m "
            "JOIN mark_goods g USING(mark_id) GROUP BY m.is_simulated").fetchall()
    cls = {r["s"]: r["cls"] for r in classes}
    out = {"real": {"count": 0, "date": None, "classes": ""},
           "simulated": {"count": 0, "date": None, "classes": ""}}
    for r in rows:
        k = "simulated" if r["is_simulated"] else "real"
        out[k] = {"count": r["n"], "date": r["d"], "classes": cls.get(r["is_simulated"], "")}
    return out


_chroma_client = None


def chroma():
    global _chroma_client
    if _chroma_client is None or getattr(_chroma_client, "_tm_path", None) != str(settings.chroma_dir):
        import chromadb

        _chroma_client = chromadb.PersistentClient(path=str(settings.chroma_dir))
        _chroma_client._tm_path = str(settings.chroma_dir)
    return _chroma_client


def collection(name: str):
    return chroma().get_or_create_collection(name, metadata={"hnsw:space": "cosine"})
