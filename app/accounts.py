"""用户账号与积分（本地 SQLite：settings.accounts_path）。

- 密码：PBKDF2-HMAC-SHA256、每个用户独立随机盐、60 万次迭代，只存哈希；比较用 hmac.compare_digest。
- 登录失败 5 次锁定 15 分钟，防止暴力猜密码。
- 积分：只追加的流水账（ledger），每条记下变动、原因和变动后余额；余额就是最新一条的余额。
  扣费在 BEGIN IMMEDIATE 事务里完成，并发提交不会扣成负数。
- VIP：有效期内评估先用 VIP 次数，问答不扣积分（每日上限）；VIP 使用也记一条变动为 0 的流水，便于退款与核对。
- 购买：演示支付（页面明确标注“演示”）与兑换码两种；真实支付以后接入时只需在 purchase() 之前完成收款。
"""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta

from app import pricing
from app.config import settings

ITERATIONS = 600_000
MAX_FAILS, LOCK_MINUTES = 5, 15
USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,20}$")       # 不允许中文（2026-11-19 用户要求）


class AccountError(Exception):
    """可以直接展示给用户的错误。"""


def _now() -> datetime:
    return datetime.now().replace(microsecond=0)


def _conn() -> sqlite3.Connection:
    settings.accounts_path.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(settings.accounts_path, timeout=10, isolation_level=None)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE COLLATE NOCASE,
            pw_hash TEXT NOT NULL, salt TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'user',
            created TEXT NOT NULL, failed INTEGER NOT NULL DEFAULT 0, locked_until TEXT,
            vip_until TEXT, vip_queries_left INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS ledger (
            id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, delta INTEGER NOT NULL, kind TEXT NOT NULL,
            note TEXT, ref TEXT, balance_after INTEGER NOT NULL, created TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS ix_ledger_user ON ledger(user_id, id);
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, product TEXT NOT NULL, amount REAL NOT NULL,
            method TEXT NOT NULL, ref TEXT, created TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS redeem_codes (
            code TEXT PRIMARY KEY, product TEXT NOT NULL, created_by INTEGER, created TEXT NOT NULL,
            used_by INTEGER, used_at TEXT);
        CREATE TABLE IF NOT EXISTS vip_qa (user_id INTEGER NOT NULL, day TEXT NOT NULL, n INTEGER NOT NULL,
            PRIMARY KEY (user_id, day));
        CREATE TABLE IF NOT EXISTS email_codes (email TEXT PRIMARY KEY COLLATE NOCASE, code_hash TEXT NOT NULL,
            expires TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, sent_at TEXT NOT NULL);
    """)
    cols = {r[1] for r in c.execute("PRAGMA table_info(users)")}
    if "email" not in cols:                           # 旧库升级：邮箱（注册时验证）、不限额度（特权测试账号）
        c.execute("ALTER TABLE users ADD COLUMN email TEXT")
    if "unlimited" not in cols:
        c.execute("ALTER TABLE users ADD COLUMN unlimited INTEGER NOT NULL DEFAULT 0")
    c.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_users_email ON users(email COLLATE NOCASE) WHERE email IS NOT NULL")
    return c


@contextmanager
def _tx():
    c = _conn()
    try:
        c.execute("BEGIN IMMEDIATE")
        yield c
        c.execute("COMMIT")
    except Exception:
        c.execute("ROLLBACK")
        raise
    finally:
        c.close()


def _hash(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), ITERATIONS).hex()


def _balance(c, user_id: int) -> int:
    row = c.execute("SELECT balance_after FROM ledger WHERE user_id=? ORDER BY id DESC LIMIT 1", (user_id,)).fetchone()
    return row[0] if row else 0


def _add(c, user_id: int, delta: int, kind: str, note: str = "", ref: str = "") -> int:
    bal = _balance(c, user_id) + delta
    if bal < 0:
        raise AccountError("积分不足")
    cur = c.execute("INSERT INTO ledger (user_id, delta, kind, note, ref, balance_after, created) VALUES (?,?,?,?,?,?,?)",
                    (user_id, delta, kind, note, ref, bal, _now().isoformat()))
    return cur.lastrowid


# ---------- 注册与登录 ----------
def check_password_rule(password: str) -> None:
    if len(password) < 8 or not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        raise AccountError("密码至少 8 位，且同时包含字母和数字")


EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
CODE_TTL_MIN, CODE_RESEND_S, CODE_MAX_TRIES = 10, 60, 5


def register(username: str, password: str, role: str = "user", email: str | None = None,
             unlimited: bool = False, vip_until: str | None = None, enforce_rule: bool = True) -> dict:
    """建账号（内部用）。页面注册走 register_with_email（先验证邮箱）；管理员、特权测试账号由脚本创建。"""
    username = username.strip()
    email = email.strip().lower() if email else None
    if not USERNAME_RE.match(username):
        raise AccountError("用户名为 3–20 位的字母、数字或下划线，不能包含中文")
    if enforce_rule:
        check_password_rule(password)
    salt = secrets.token_hex(16)
    with _tx() as c:
        if c.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone():
            raise AccountError("这个用户名已被注册")
        if email and c.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone():
            raise AccountError("这个邮箱已被注册")
        uid = c.execute("INSERT INTO users (username, pw_hash, salt, role, created, email, unlimited, vip_until, "
                        "vip_queries_left) VALUES (?,?,?,?,?,?,?,?,?)",
                        (username, _hash(password, salt), salt, role, _now().isoformat(), email, int(unlimited),
                         vip_until, 0)).lastrowid
        if role == "user" and pricing.SIGNUP_GIFT and not unlimited:
            _add(c, uid, pricing.SIGNUP_GIFT, "gift", "新用户赠送")
    return get_user(uid)


def _check_registration_key(registration_key: str) -> None:
    if not settings.registration_key:
        raise AccountError("注册暂未开放，请联系管理员")
    if not hmac.compare_digest(registration_key.strip().encode(), settings.registration_key.encode()):
        raise AccountError("注册密钥不正确")


def send_email_code(email: str, *, registration_key: str) -> str | None:
    """给注册邮箱发 6 位验证码。返回 None 表示已发送；本机调试模式（TM_EMAIL_DEV=1）返回验证码本身。"""
    from app import mailer

    _check_registration_key(registration_key)
    email = email.strip().lower()                     # 邮箱统一小写保存和比较
    if not EMAIL_RE.match(email):
        raise AccountError("邮箱格式不正确")
    code = f"{secrets.randbelow(10 ** 6):06d}"
    with _tx() as c:
        if c.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone():
            raise AccountError("这个邮箱已被注册")
        row = c.execute("SELECT sent_at FROM email_codes WHERE email=?", (email,)).fetchone()
        if row and (_now() - datetime.fromisoformat(row["sent_at"])).total_seconds() < CODE_RESEND_S:
            raise AccountError(f"发送太频繁，请 {CODE_RESEND_S} 秒后再试")
        if not mailer.configured() and not mailer.dev_mode():
            raise AccountError("邮件服务尚未配置，暂时无法注册，请联系管理员")
        c.execute("INSERT OR REPLACE INTO email_codes VALUES (?,?,?,0,?)",
                  (email, _hash(code, "11" * 16), (_now() + timedelta(minutes=CODE_TTL_MIN)).isoformat(), _now().isoformat()))
    if mailer.configured():
        try:
            mailer.send(email, "【商标近似评估智能体】注册验证码",
                        f"您的注册验证码是 {code}，{CODE_TTL_MIN} 分钟内有效。如非本人操作，请忽略本邮件。")
        except Exception as e:                            # 发信失败：作废这条验证码，让用户可以立即重发
            with _tx() as c:
                c.execute("DELETE FROM email_codes WHERE email=?", (email,))
            raise AccountError(f"验证码邮件发送失败（{type(e).__name__}），请稍后重试") from e
        return None
    return code                                           # 调试模式：不发信，交给页面显示


def _consume_code(c, email: str, code: str) -> None:
    row = c.execute("SELECT * FROM email_codes WHERE email=?", (email,)).fetchone()
    if row is None:
        raise AccountError("请先获取邮箱验证码")
    if datetime.fromisoformat(row["expires"]) < _now():
        raise AccountError("验证码已过期，请重新获取")
    if row["attempts"] >= CODE_MAX_TRIES:
        raise AccountError("验证码错误次数过多，请重新获取")
    if not hmac.compare_digest(_hash(code.strip(), "11" * 16), row["code_hash"]):
        c.execute("UPDATE email_codes SET attempts=attempts+1 WHERE email=?", (email,))
        raise AccountError("邮箱验证码不正确")
    c.execute("DELETE FROM email_codes WHERE email=?", (email,))


def register_with_email(username: str, email: str, code: str, password: str, *, registration_key: str) -> dict:
    """校验注册密钥和邮箱验证码后建账号。验证码错误次数在单独的事务中提交。"""
    _check_registration_key(registration_key)
    email = email.strip().lower()                     # 邮箱统一小写保存和比较
    if not EMAIL_RE.match(email):
        raise AccountError("邮箱格式不正确")
    if not USERNAME_RE.match(username.strip()):
        raise AccountError("用户名为 3–20 位的字母、数字或下划线，不能包含中文")
    check_password_rule(password)
    error = None
    with _tx() as c:
        try:
            _consume_code(c, email, code)
        except AccountError as e:
            error = str(e)
    if error:
        raise AccountError(error)
    return register(username, password, email=email)


def login(username: str, password: str) -> dict:
    error = None
    with _tx() as c:                                     # 失败计数要先提交，再抛错（在事务里抛错会被回滚）
        u = c.execute("SELECT * FROM users WHERE username=?", (username.strip(),)).fetchone()
        if u is None:
            _hash(password, "00" * 16)                   # 用户不存在时也算一次哈希，不让响应时间泄露用户名是否存在
            error = "用户名或密码错误"
        elif u["locked_until"] and datetime.fromisoformat(u["locked_until"]) > _now():
            error = f"登录失败次数过多，请在 {u['locked_until'][11:16]} 之后再试"
        elif not hmac.compare_digest(_hash(password, u["salt"]), u["pw_hash"]):
            fails = u["failed"] + 1
            lock = (_now() + timedelta(minutes=LOCK_MINUTES)).isoformat() if fails >= MAX_FAILS else None
            c.execute("UPDATE users SET failed=?, locked_until=? WHERE id=?", (0 if lock else fails, lock, u["id"]))
            error = f"登录失败次数过多，账号锁定 {LOCK_MINUTES} 分钟" if lock else "用户名或密码错误"
        else:
            c.execute("UPDATE users SET failed=0, locked_until=NULL WHERE id=?", (u["id"],))
    if error:
        raise AccountError(error)
    return get_user(u["id"])


def change_password(user_id: int, old: str, new: str) -> None:
    check_password_rule(new)
    with _tx() as c:
        u = c.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        if not hmac.compare_digest(_hash(old, u["salt"]), u["pw_hash"]):
            raise AccountError("原密码不正确")
        salt = secrets.token_hex(16)
        c.execute("UPDATE users SET pw_hash=?, salt=? WHERE id=?", (_hash(new, salt), salt, user_id))


def get_user(user_id: int) -> dict:
    c = _conn()
    try:
        u = c.execute("SELECT id, username, role, created, vip_until, vip_queries_left, email, unlimited FROM users "
                      "WHERE id=?", (user_id,)).fetchone()
        if u is None:
            raise AccountError("用户不存在")
        d = dict(u)
        d["balance"] = _balance(c, user_id)
        d["vip_active"] = bool(d["vip_until"]) and datetime.fromisoformat(d["vip_until"]) > _now()
        d["unlimited"] = bool(d["unlimited"])
        return d
    finally:
        c.close()


# ---------- 扣费与退款 ----------
def can_query(user_id: int) -> bool:
    u = get_user(user_id)
    return u["unlimited"] or (u["vip_active"] and u["vip_queries_left"] > 0) or u["balance"] >= pricing.COST_QUERY


def charge_query(user_id: int, ref: str = "") -> dict:
    """开始一次评估时扣费：VIP 有效且有次数时用 VIP 次数，否则扣积分。返回 {charge_id, via, balance}。"""
    with _tx() as c:
        u = c.execute("SELECT vip_until, vip_queries_left, unlimited FROM users WHERE id=?", (user_id,)).fetchone()
        if u["unlimited"]:                                # 特权测试账号：不扣费，只记一条变动为 0 的流水
            cid = _add(c, user_id, 0, "unlimited", f"评估（不限额度）{ref}", ref)
            return {"charge_id": cid, "via": "unlimited", "balance": _balance(c, user_id)}
        if u["vip_until"] and datetime.fromisoformat(u["vip_until"]) > _now() and u["vip_queries_left"] > 0:
            c.execute("UPDATE users SET vip_queries_left=vip_queries_left-1 WHERE id=?", (user_id,))
            cid = _add(c, user_id, 0, "vip_query", f"评估（VIP 次数）{ref}", ref)
            via = "vip"
        else:
            if _balance(c, user_id) < pricing.COST_QUERY:
                raise AccountError(f"积分不足：一次评估需要 {pricing.COST_QUERY} 积分，请先充值")
            cid = _add(c, user_id, -pricing.COST_QUERY, "query", f"评估 {ref}", ref)
            via = "credits"
        return {"charge_id": cid, "via": via, "balance": _balance(c, user_id)}


def charge_qa(user_id: int, ref: str = "") -> dict:
    """一次问答回答成功后扣费：VIP 有效时不扣积分（每日上限），否则扣积分。"""
    day = _now().date().isoformat()
    with _tx() as c:
        u = c.execute("SELECT vip_until, unlimited FROM users WHERE id=?", (user_id,)).fetchone()
        if u["unlimited"]:
            cid = _add(c, user_id, 0, "unlimited", f"问答（不限额度）{ref}", ref)
            return {"charge_id": cid, "via": "unlimited", "balance": _balance(c, user_id)}
        if u["vip_until"] and datetime.fromisoformat(u["vip_until"]) > _now():
            row = c.execute("SELECT n FROM vip_qa WHERE user_id=? AND day=?", (user_id, day)).fetchone()
            n = row[0] if row else 0
            if n < pricing.VIP["qa_daily_cap"]:
                c.execute("INSERT INTO vip_qa VALUES (?,?,1) ON CONFLICT(user_id, day) DO UPDATE SET n=n+1", (user_id, day))
                cid = _add(c, user_id, 0, "vip_qa", f"问答（VIP）{ref}", ref)
                return {"charge_id": cid, "via": "vip", "balance": _balance(c, user_id)}
        if _balance(c, user_id) < pricing.COST_QA:
            raise AccountError(f"积分不足：一次问答需要 {pricing.COST_QA} 积分，请先充值")
        cid = _add(c, user_id, -pricing.COST_QA, "qa", f"问答 {ref}", ref)
        return {"charge_id": cid, "via": "credits", "balance": _balance(c, user_id)}


def can_ask(user_id: int) -> bool:
    u = get_user(user_id)
    return u["unlimited"] or u["vip_active"] or u["balance"] >= pricing.COST_QA


def refund(charge_id: int, reason: str) -> None:
    """退回一次扣费（评估因大模型不可用而降级等）。同一笔只退一次。"""
    with _tx() as c:
        row = c.execute("SELECT * FROM ledger WHERE id=?", (charge_id,)).fetchone()
        if row is None or c.execute("SELECT 1 FROM ledger WHERE kind='refund' AND ref=?", (f"#{charge_id}",)).fetchone():
            return
        if row["kind"] == "vip_query":
            c.execute("UPDATE users SET vip_queries_left=vip_queries_left+1 WHERE id=?", (row["user_id"],))
        _add(c, row["user_id"], -row["delta"], "refund", reason, f"#{charge_id}")


# ---------- 购买、兑换 ----------
def _grant(c, user_id: int, product_id: str, method: str, ref: str = "") -> str:
    p = pricing.PRODUCTS[product_id]
    c.execute("INSERT INTO orders (user_id, product, amount, method, ref, created) VALUES (?,?,?,?,?,?)",
              (user_id, product_id, p["price"], method, ref, _now().isoformat()))
    label = {"demo": "演示支付", "redeem": "兑换码"}.get(method, method)
    if product_id == pricing.VIP["id"]:
        u = c.execute("SELECT vip_until FROM users WHERE id=?", (user_id,)).fetchone()
        start = max(_now(), datetime.fromisoformat(u["vip_until"])) if u["vip_until"] else _now()
        until = start + timedelta(days=p["days"])
        c.execute("UPDATE users SET vip_until=?, vip_queries_left=vip_queries_left+? WHERE id=?",
                  (until.isoformat(), p["queries"], user_id))
        _add(c, user_id, 0, "vip", f"{p['name']}（{label}），有效期至 {until:%Y-%m-%d}", ref)
        return f"已开通{p['name']}，有效期至 {until:%Y-%m-%d}，含 {p['queries']} 次评估"
    _add(c, user_id, p["credits"], "purchase", f"{p['name']}（{label}）", ref)
    return f"已到账 {p['credits']} 积分"


def purchase_demo(user_id: int, product_id: str) -> str:
    """演示支付：不收款，直接到账。页面上必须明确标注“演示”。接入真实支付后应在收款成功回调里调用 _grant。"""
    if product_id not in pricing.PRODUCTS:
        raise AccountError("没有这个套餐")
    with _tx() as c:
        return _grant(c, user_id, product_id, "demo")


def create_codes(product_id: str, n: int, admin_id: int) -> list[str]:
    if product_id not in pricing.PRODUCTS:
        raise AccountError("没有这个套餐")
    codes = ["-".join(secrets.token_hex(2).upper() for _ in range(4)) for _ in range(max(1, min(n, 200)))]
    with _tx() as c:
        c.executemany("INSERT INTO redeem_codes (code, product, created_by, created) VALUES (?,?,?,?)",
                      [(code, product_id, admin_id, _now().isoformat()) for code in codes])
    return codes


def redeem(user_id: int, code: str) -> str:
    code = code.strip().upper()
    with _tx() as c:
        row = c.execute("SELECT * FROM redeem_codes WHERE code=?", (code,)).fetchone()
        if row is None:
            raise AccountError("兑换码不存在")
        if row["used_by"]:
            raise AccountError("兑换码已被使用")
        c.execute("UPDATE redeem_codes SET used_by=?, used_at=? WHERE code=?", (user_id, _now().isoformat(), code))
        return _grant(c, user_id, row["product"], "redeem", code)


# ---------- 查询（页面与管理后台） ----------
def history(user_id: int, limit: int = 50) -> list[dict]:
    c = _conn()
    try:
        return [dict(r) for r in c.execute("SELECT delta, kind, note, balance_after, created FROM ledger "
                                           "WHERE user_id=? ORDER BY id DESC LIMIT ?", (user_id, limit))]
    finally:
        c.close()


def list_users(limit: int = 200) -> list[dict]:
    c = _conn()
    try:
        rows = c.execute("SELECT id FROM users ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    finally:
        c.close()
    return [get_user(r[0]) for r in rows]


def list_codes(limit: int = 200) -> list[dict]:
    c = _conn()
    try:
        return [dict(r) for r in c.execute(
            "SELECT r.code, r.product, r.created, u.username AS used_by, r.used_at FROM redeem_codes r "
            "LEFT JOIN users u ON u.id = r.used_by ORDER BY r.created DESC LIMIT ?", (limit,))]
    finally:
        c.close()


def admin_adjust(user_id: int, delta: int, note: str, admin_id: int) -> int:
    with _tx() as c:
        _add(c, user_id, delta, "admin", note or "管理员调整", f"admin:{admin_id}")
        return _balance(c, user_id)
