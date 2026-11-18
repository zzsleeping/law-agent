"""建库：把 data/ 下的原始文件导入 SQLite 和 Chroma。

入口：scripts/build_db.py。测试中直接调用 build()。
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from datetime import date

import openpyxl

from app import db
from app.config import settings
from app.embed import get_embedder
from app.rules import goods_notes
from app.tools import phonetic

GUIDE_DOC = "商标审查审理指南"
GUIDE_VERSION = "2021年发布"
GUIDE_EFFECTIVE = "2022-01-01"
GUIDE_SOURCE = "国家知识产权局第462号公告"


def _load_basis(conn) -> int:
    base = settings.data_dir / "basis"
    rows = []
    for b in json.loads((base / "basis.json").read_text(encoding="utf-8")):
        rows.append((b["id"], b["doc"], b["version"], b["article"], "", b["effective_from"],
                     b["effective_to"], b["text"], b["source"], ""))
    for g in json.loads((base / "guide_rules.json").read_text(encoding="utf-8")):
        number = g["id"].split("-", 1)[1]
        rows.append((g["id"], GUIDE_DOC, GUIDE_VERSION, number, g["title"], GUIDE_EFFECTIVE, None,
                     g["text"], GUIDE_SOURCE, json.dumps(g.get("dimension", []), ensure_ascii=False)))
    conn.executemany("INSERT INTO basis VALUES (?,?,?,?,?,?,?,?,?,?)", rows)
    wb = openpyxl.load_workbook(base / "article_map.xlsx", data_only=True)
    maps = [r[:4] for r in list(wb.worksheets[0].iter_rows(values_only=True))[1:] if r[0]]
    conn.executemany("INSERT INTO article_map VALUES (?,?,?,?)", maps)
    return len(rows)


def _load_goods(conn) -> list[dict]:
    """导入区分表商品项（含跨群重复列出的项目）和群组注释，注释解析成规则。"""
    base = settings.data_dir / "goods"
    wb = openpyxl.load_workbook(base / "goods_items.xlsx", data_only=True)
    items = []
    for r in list(wb["商品项库"].iter_rows(values_only=True))[1:]:
        if not r[0]:
            continue
        items.append({"code": str(r[0]).strip(), "name": str(r[1]).strip(), "nice_class": int(r[2]),
                      "grp": str(r[3]).strip(), "part": (str(r[4]).strip() if r[4] else None),
                      "page": str(r[5] or "")})
    cross = base / "cross_group_items.json"
    if cross.exists():
        for c in json.loads(cross.read_text(encoding="utf-8")):
            items.append({"code": c["code"], "name": c["name"], "nice_class": int(c["nice_class"]),
                          "grp": c["group"], "part": c.get("part"), "page": str(c.get("page") or "")})
    conn.executemany("INSERT INTO goods_items VALUES (:code,:name,:nice_class,:grp,:part,:page)", items)

    index = goods_notes.ItemIndex(items)
    notes = [r for r in list(wb["群组注释"].iter_rows(values_only=True))[1:] if r[0]]
    review = ["# 群组注释转换核对表", "",
              "由 `scripts/build_db.py` 自动生成，不要手工修改。每条注释原文、解析出的规则、"
              "规则两侧在商品项库中对应到的商品项数量。“库外”表示该群不在本库收录的类别内。", ""]
    for grp, seq, text, page in ((str(r[0]), str(r[1]), str(r[2]), str(r[3] or "")) for r in notes):
        review.append(f"## {grp} {seq}（第 {page} 页）")
        review.append(f"> {text}")
        review.append("")
        for rule in goods_notes.parse_note(grp, seq, text):
            side_desc, open_side, open_grp = ["", ""], None, None
            for i, side in enumerate(rule.sides):
                key = "ab"[i]
                desc = []
                for sd in side:
                    codes, missing = index.resolve(sd)
                    conn.executemany("INSERT INTO goods_note_members VALUES (?,?,?)",
                                     [(rule.note_id, key, c) for c in sorted(codes)])
                    tag = f"{len(codes)} 项" if index.known(sd.group) else "库外"
                    desc.append(sd.describe() + f"（{tag}）" + (f"，未对应：{'、'.join(missing)}" if missing else ""))
                    if sd.open_ended:
                        open_side, open_grp = key, sd.group
                side_desc[i] = "；".join(desc)
            parts = ""
            if rule.rel_type == "明确不类似":
                parts = ",".join(sorted({it["part"] for it in index.by_group.get(grp, []) if it.get("part")}))
            conn.execute("INSERT INTO goods_notes VALUES (?,?,?,?,?,?,?,?,?,?)",
                         (rule.note_id, grp, rule.rel_type, side_desc[0], side_desc[1], text, page,
                          open_side, open_grp, parts))
            line = f"- **{rule.rel_type}**（{rule.note_id}）"
            if side_desc[0]:
                line += f"：{side_desc[0]}"
            if side_desc[1]:
                line += f" ↔ {side_desc[1]}"
            if parts:
                line += f"：{grp} 的 {parts} 各部分之间"
            if open_side:
                line += "。开放式列举，未列明的项目判待核实"
            review.append(line)
        review.append("")
    (base / "notes_rules_review.md").write_text("\n".join(review), encoding="utf-8")
    return items


def _load_marks(conn, items: list[dict]) -> list[dict]:
    by_code = {}
    for i in items:
        by_code.setdefault(i["code"], i)
    marks = []
    sources = [(p, 0) for p in sorted((settings.data_dir / "raw" / "real").glob("*.json"))]
    if settings.fixture_marks:                                   # 仅测试使用
        sources.append((Path(settings.fixture_marks), 1))
    for path, simulated in sources:
        for m in json.loads(path.read_text(encoding="utf-8")):
            m["is_simulated"] = simulated                        # 以来源为准
            marks.append(m)
    for m in marks:
        k = phonetic.keys(m["text"])
        conn.execute(
            "INSERT INTO marks VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (m["mark_id"], m["text"], phonetic.normalize(m["text"]), k["pinyin_tone"], k["pinyin"],
             k["pinyin_fuzzy"], m.get("meaning"), m.get("owner"), m.get("app_date"), m.get("priority_date"),
             m.get("reg_date"), m.get("prelim_date"), m.get("term_end"), m.get("status"), m.get("invalid_date"), m.get("invalid_reason"),
             m.get("snapshot_date") or date.today().isoformat(), m.get("source") or "未注明",
             m.get("source_ref"), m["is_simulated"]))
        for g in m.get("goods", []):
            lib = by_code.get(g.get("code") or "")
            conn.execute("INSERT INTO mark_goods VALUES (?,?,?,?,?)",
                         (m["mark_id"], g["name"], lib["code"] if lib else None,
                          lib["nice_class"] if lib else g.get("nice_class"),
                          lib["grp"] if lib else g.get("grp")))
    return marks


def clean_name(name: str) -> str:
    return name.replace("*", "").strip()


def build(embed_backend: str | None = None, verbose: bool = True) -> dict:
    backend = embed_backend or settings.embed_backend
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    if settings.db_path.exists():
        settings.db_path.unlink()
    if settings.chroma_dir.exists():
        shutil.rmtree(settings.chroma_dir)
    db._chroma_client = None

    conn = db.connect()
    conn.executescript(db.SCHEMA)
    n_basis = _load_basis(conn)
    items = _load_goods(conn)
    marks = _load_marks(conn, items)
    conn.execute("INSERT INTO meta VALUES ('embed_backend', ?)", (backend,))
    conn.execute("INSERT INTO meta VALUES ('built_at', ?)", (date.today().isoformat(),))
    conn.commit()
    conn.close()

    emb = get_embedder(backend)
    goods_col = db.collection("goods_items")
    names = [clean_name(i["name"]) for i in items]
    goods_col.add(
        ids=[f"{i['code']}|{i['name']}|{i['grp']}" for i in items],
        embeddings=emb.embed(names), documents=names,
        metadatas=[{"code": i["code"], "name": i["name"], "nice_class": i["nice_class"], "grp": i["grp"]}
                   for i in items])
    with_meaning = [m for m in marks if m.get("meaning")]
    if with_meaning:
        db.collection("marks_meaning").add(
            ids=[m["mark_id"] for m in with_meaning],
            embeddings=emb.embed([m["meaning"] for m in with_meaning]),
            documents=[m["meaning"] for m in with_meaning],
            metadatas=[{"is_simulated": m["is_simulated"]} for m in with_meaning])
    from app.tools import rag
    kb = rag.build_kb(emb)                   # RAG 知识库：指南、判例、法条

    stats = {"basis": n_basis, "goods_items": len(items), "marks": len(marks), **kb,
             "marks_real": sum(1 for m in marks if not m["is_simulated"]),
             "marks_simulated": sum(1 for m in marks if m["is_simulated"]), "embed_backend": backend}
    if verbose:
        print("建库完成：", stats)
    return stats
