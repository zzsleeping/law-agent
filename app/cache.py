"""两层缓存（本地 SQLite，settings.cache_path）。

第一层：整份报告。键 = 全部用户输入（场景、商标、商品描述、确认的商品项、日期、引证、保留的候选）
        + 数据快照日期 + 提示词与模型版本 + REPORT_VERSION。同样的查询再来时页面提示“复用上次结果”，
        用户可以查看上次报告，也可以重新评估。报告同时存下 Word 文件，刷新页面后也能找回（结果持久化）。
第二层：每次大模型调用。键 = 模型名 + 提示词模板 + 填入的变量（可排除与结论无关的变量，如判定时的评估日期）。
        判定按名称组调用，所以这一层就是“按在先商标组缓存判定”：组的文字证据、商品关系、在先状态都没变，
        就直接复用上次的判定，不同查询之间也一致；解析、检索规划、写结论同理，整条流程因此可复现。
        只缓存成功解析的结果；“重新评估”时跳过读取、用新结果覆盖。

为什么不把旧结果交给模型再判一次：仍可能翻转，错误会被固化，还要再等一次调用（2026-11-19 与用户确认）。
测试注入假模型时不读写缓存；评测脚本关闭缓存，测的是模型本身。
"""
from __future__ import annotations

import hashlib
import json
import pickle
import sqlite3
from datetime import datetime

from app.config import settings

REPORT_VERSION = 1          # 报告内容的生成逻辑有不兼容的改动时加一，旧报告缓存自动失效


def key(*parts) -> str:
    raw = json.dumps(parts, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _conn() -> sqlite3.Connection:
    settings.cache_path.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(settings.cache_path, timeout=10)       # 判定并行调用，每次单独开连接
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("CREATE TABLE IF NOT EXISTS llm (key TEXT PRIMARY KEY, prompt TEXT, model TEXT, created TEXT, response TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS reports (key TEXT PRIMARY KEY, created TEXT, scenario TEXT, query TEXT, "
              "title TEXT, payload BLOB, docx BLOB)")
    return c


def enabled() -> bool:
    return settings.cache_enabled


# ---------- 第二层：大模型调用 ----------
def llm_get(k: str) -> dict | None:
    if not enabled():
        return None
    with _conn() as c:
        row = c.execute("SELECT response FROM llm WHERE key=?", (k,)).fetchone()
    return json.loads(row[0]) if row else None


def llm_put(k: str, prompt: str, data: dict) -> None:
    if not enabled():
        return
    with _conn() as c:
        c.execute("INSERT OR REPLACE INTO llm VALUES (?,?,?,?,?)",
                  (k, prompt, settings.llm_model, datetime.now().isoformat(timespec="seconds"),
                   json.dumps(data, ensure_ascii=False)))


# ---------- 第一层：整份报告 ----------
def versions() -> dict:
    """影响报告内容的版本信息：提示词文件、模型、数据快照、报告生成逻辑。"""
    from app.library import get_library

    prompts = sorted((settings.prompts_dir).glob("*.yaml"))
    lib = get_library()
    return {"report": REPORT_VERSION, "model": settings.llm_model,
            "prompts": key(*[(p.name, p.read_text(encoding="utf-8")) for p in prompts]),
            "data": lib.coverage().get("date", "") if lib.available() else "local",
            "judge_with_cases": settings.judge_with_cases}


def report_key(inputs: dict) -> str:
    return key(inputs, versions())


def report_get(k: str) -> dict | None:
    """返回 {"created", "payload", "docx"}；没有或无法读取（代码改动后反序列化失败）时返回 None。"""
    if not enabled():
        return None
    with _conn() as c:
        row = c.execute("SELECT created, payload, docx FROM reports WHERE key=?", (k,)).fetchone()
    if not row:
        return None
    try:
        return {"created": row[0], "payload": pickle.loads(row[1]), "docx": row[2]}
    except Exception:
        return None


def report_put(k: str, scenario: str, query: str, title: str, payload: dict, docx: bytes) -> None:
    if not enabled():
        return
    with _conn() as c:
        c.execute("INSERT OR REPLACE INTO reports VALUES (?,?,?,?,?,?,?)",
                  (k, datetime.now().isoformat(timespec="seconds"), scenario, query, title,
                   pickle.dumps(payload), docx))


def report_find(prefix_inputs: dict) -> list[dict]:
    """按输入页的信息（不含之后确认的商品项和候选）找以前的报告，供输入页提示“已评估过”。"""
    if not enabled():
        return []
    k = key(prefix_inputs, versions())
    with _conn() as c:
        rows = c.execute("SELECT key, created, title, payload FROM reports ORDER BY created DESC LIMIT 200").fetchall()
    out = []
    for rk, created, title, blob in rows:
        try:
            p = pickle.loads(blob)
        except Exception:
            continue
        if p.get("prefix_key") == k:
            out.append({"key": rk, "created": created, "title": title, "goods": p.get("goods_names", [])})
    return out


def report_recent(limit: int = 10) -> list[dict]:
    if not enabled():
        return []
    with _conn() as c:
        rows = c.execute("SELECT key, created, scenario, query, title FROM reports ORDER BY created DESC LIMIT ?",
                         (limit,)).fetchall()
    return [{"key": r[0], "created": r[1], "scenario": r[2], "query": r[3], "title": r[4]} for r in rows]
