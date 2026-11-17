"""为国家知识产权局商标开放数据建检索索引（只读原库，索引另存）。

原库：.env 里的 TM_OPEN_DB（Codex 整理的 cnipa_29_30_32_43.sqlite3，约 10 GB，不放进项目）
索引：data/open_index.sqlite（不进 git）

索引内容（只收规范化后含汉字的名称；本系统只比对中文文字部分）：
- names       不重复的规范化名称及三种拼音键
- name_marks  名称 → 商标档案（编号 + 类别），并记录该商标的整体名称（full_id）。
              用分号、斜杠、顿号等连接的多段名称（如“速浪;浪”），每一段和整体各建一条
- grams       名称中的两字片段（找包含、共用显著部分、字序颠倒的候选）
- masks       每个位置替换成“?”的掩码（找仅一字不同、形近替换的候选）
- dels        删去一个字后的串（找仅多一字或少一字的候选）

用法：python scripts/build_open_index.py   （约半小时，可重复运行，会覆盖旧索引）
"""
from __future__ import annotations

import re
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import settings  # noqa: E402
from app.tools import phonetic  # noqa: E402

SPLIT = re.compile(r"[;；/／、|｜]+")
MAX_EDIT_LEN = 12          # 超过这个长度的名称不建掩码和删除键（长名称很少靠一字之差冲突）
BATCH = 200_000


def log(msg: str) -> None:
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def main() -> int:
    src = settings.open_db_path
    if not src or not Path(src).exists():
        print(f"找不到开放数据库：{src!r}。请在 .env 里设置 TM_OPEN_DB。")
        return 1
    out = settings.open_index_path
    tmp = out.with_suffix(".building")
    if tmp.exists():
        tmp.unlink()
    s = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
    o = sqlite3.connect(tmp)
    o.executescript("""
        PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF; PRAGMA temp_store=MEMORY; PRAGMA cache_size=-2000000;
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE names (name_id INTEGER PRIMARY KEY, norm TEXT NOT NULL, n INTEGER NOT NULL,
                            py_tone TEXT, py TEXT, py_fuzzy TEXT);
        CREATE TABLE name_marks (name_id INTEGER NOT NULL, nice_class INTEGER NOT NULL, mark_id TEXT NOT NULL,
                                 full_id INTEGER NOT NULL);
        CREATE TABLE grams (gram TEXT NOT NULL, n INTEGER NOT NULL, name_id INTEGER NOT NULL);
        CREATE TABLE masks (key TEXT NOT NULL, name_id INTEGER NOT NULL);
        CREATE TABLE dels (key TEXT NOT NULL, name_id INTEGER NOT NULL);
    """)

    log("读取不重复名称")
    raw_names = [r[0] for r in s.execute(
        "SELECT DISTINCT mark_name FROM trademarks WHERE mark_name IS NOT NULL AND mark_name GLOB '*[一-鿿]*' "
        "AND instr(mark_name, char(65533)) = 0")]
    log(f"原始名称 {len(raw_names):,} 个，开始规范化和计算拼音")
    norm_id: dict[str, int] = {}
    raw_id: dict[str, tuple[int, list[int]]] = {}   # 原始名称 → (整体名称 id, 各段名称 id)
    rows, grams, masks, dels = [], [], [], []

    def flush() -> None:
        o.executemany("INSERT INTO names VALUES (?,?,?,?,?,?)", rows)
        o.executemany("INSERT INTO grams VALUES (?,?,?)", grams)
        o.executemany("INSERT INTO masks VALUES (?,?)", masks)
        o.executemany("INSERT INTO dels VALUES (?,?)", dels)
        rows.clear(); grams.clear(); masks.clear(); dels.clear()

    def register(norm: str) -> int:
        nid = norm_id.get(norm)
        if nid is None:
            nid = len(norm_id) + 1
            norm_id[norm] = nid
            k = phonetic.keys(norm)
            n = len(norm)
            rows.append((nid, norm, n, k["pinyin_tone"], k["pinyin"], k["pinyin_fuzzy"]))
            grams.extend((g, n, nid) for g in {norm[j:j + 2] for j in range(n - 1)})
            if 2 <= n <= MAX_EDIT_LEN:
                masks.extend((norm[:j] + "?" + norm[j + 1:], nid) for j in range(n))
                dels.extend((d, nid) for d in {norm[:j] + norm[j + 1:] for j in range(n)})
        return nid

    for i, raw in enumerate(raw_names, 1):
        full = phonetic.normalize(raw)
        if not full or not phonetic.HAN.search(full):
            continue
        full_id = register(full)
        parts = {phonetic.normalize(p) for p in SPLIT.split(raw)} - {full}
        part_ids = [register(p) for p in sorted(parts) if p and phonetic.HAN.search(p)]
        raw_id[raw] = (full_id, part_ids)
        if len(rows) >= BATCH:
            flush()
        if i % 1_000_000 == 0:
            log(f"  已处理 {i:,} 个原始名称，不重复规范化名称 {len(norm_id):,}")
    flush()
    log(f"规范化名称 {len(norm_id):,} 个；写入名称 → 商标档案对应")

    batch = []
    total = 0
    for mark_id, cls, name in s.execute("SELECT mark_id, nice_class, mark_name FROM trademarks WHERE mark_name IS NOT NULL"):
        ids = raw_id.get(name)
        if ids:
            full_id, part_ids = ids
            batch.extend((nid, cls, mark_id, full_id) for nid in [full_id, *part_ids])
            if len(batch) >= BATCH:
                o.executemany("INSERT INTO name_marks VALUES (?,?,?,?)", batch)
                total += len(batch)
                batch.clear()
    o.executemany("INSERT INTO name_marks VALUES (?,?,?,?)", batch)
    total += len(batch)
    marks = s.execute("SELECT count(*) FROM trademarks WHERE mark_name IS NOT NULL").fetchone()[0]
    log(f"名称 → 商标档案对应 {total:,} 条；建索引")

    for sql in ("CREATE INDEX ix_names_norm ON names(norm)", "CREATE INDEX ix_names_tone ON names(py_tone)",
                "CREATE INDEX ix_names_py ON names(py)", "CREATE INDEX ix_names_fuzzy ON names(py_fuzzy)",
                "CREATE INDEX ix_nm ON name_marks(name_id, nice_class)", "CREATE INDEX ix_grams ON grams(gram, n)",
                "CREATE INDEX ix_masks ON masks(key)", "CREATE INDEX ix_dels ON dels(key)"):
        o.execute(sql)
        log(f"  {sql.split(' ON ')[0].replace('CREATE INDEX ', '')} 完成")
    latest = s.execute("SELECT max(period) FROM sources WHERE category='incremental_data'").fetchone()[0]
    o.executemany("INSERT INTO meta VALUES (?,?)", [
        ("source_db", str(src)), ("names", str(len(norm_id))), ("marks", str(marks)),
        ("latest_period", str(latest)), ("built_at", time.strftime("%Y-%m-%d"))])
    o.commit()
    o.execute("ANALYZE")
    o.close()
    tmp.replace(out)
    log(f"索引完成 → {out}（{out.stat().st_size / 1e9:.1f} GB）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
