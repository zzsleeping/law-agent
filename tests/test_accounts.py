"""账号与积分（app/accounts.py）：临时库、降低哈希迭代次数以加快测试。"""
import sqlite3
from datetime import datetime, timedelta

import pytest

from app import accounts, pricing
from app.accounts import AccountError
from app.config import settings


REGISTRATION_KEY = "test-registration-key"


@pytest.fixture(autouse=True)
def tmp_accounts(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "accounts_path", tmp_path / "accounts.sqlite")
    monkeypatch.setattr(accounts, "ITERATIONS", 1000)
    monkeypatch.setattr(settings, "registration_key", REGISTRATION_KEY)


def test_register_gift_and_password_not_stored_in_plain():
    u = accounts.register("alice", "secret123")
    assert u["balance"] == pricing.SIGNUP_GIFT >= pricing.COST_QUERY       # 赠送积分够试用一次评估
    raw = sqlite3.connect(settings.accounts_path).execute("SELECT pw_hash, salt FROM users").fetchone()
    assert "secret123" not in raw[0] and len(raw[1]) == 32
    with pytest.raises(AccountError, match="已被注册"):
        accounts.register("ALICE", "secret123")                               # 用户名不区分大小写
    with pytest.raises(AccountError, match="至少 8 位"):
        accounts.register("bob", "short1")
    with pytest.raises(AccountError, match="用户名"):
        accounts.register("a b", "secret123")
    with pytest.raises(AccountError, match="不能包含中文"):
        accounts.register("张三abc", "secret123")


def test_login_and_lockout():
    accounts.register("alice", "secret123")
    assert accounts.login("alice", "secret123")["username"] == "alice"
    with pytest.raises(AccountError, match="用户名或密码错误"):
        accounts.login("nobody", "secret123")
    for _ in range(accounts.MAX_FAILS - 1):
        with pytest.raises(AccountError, match="用户名或密码错误"):
            accounts.login("alice", "wrong-pass1")
    with pytest.raises(AccountError, match="锁定"):
        accounts.login("alice", "wrong-pass1")
    with pytest.raises(AccountError, match="之后再试"):                       # 锁定期内正确密码也不行
        accounts.login("alice", "secret123")


def test_query_charge_refund_and_insufficient():
    uid = accounts.register("alice", "secret123")["id"]
    c = accounts.charge_query(uid, "茗悦")
    assert c["via"] == "credits" and c["balance"] == pricing.SIGNUP_GIFT - pricing.COST_QUERY
    assert not accounts.can_query(uid)
    with pytest.raises(AccountError, match="积分不足"):
        accounts.charge_query(uid)
    accounts.refund(c["charge_id"], "大模型不可用，退回")
    accounts.refund(c["charge_id"], "重复退款")                               # 同一笔只退一次
    assert accounts.get_user(uid)["balance"] == pricing.SIGNUP_GIFT


def test_qa_charge():
    uid = accounts.register("alice", "secret123")["id"]
    assert accounts.charge_qa(uid)["balance"] == pricing.SIGNUP_GIFT - pricing.COST_QA


def test_demo_purchase_and_vip():
    uid = accounts.register("alice", "secret123")["id"]
    assert "100 积分" in accounts.purchase_demo(uid, "p100")
    assert accounts.get_user(uid)["balance"] == pricing.SIGNUP_GIFT + 100
    msg = accounts.purchase_demo(uid, "vip30")
    u = accounts.get_user(uid)
    assert "月度 VIP" in msg and u["vip_active"] and u["vip_queries_left"] == pricing.VIP["queries"]
    bal = u["balance"]
    c = accounts.charge_query(uid)                                            # VIP 期间评估用次数，不扣积分
    assert c["via"] == "vip" and c["balance"] == bal
    accounts.refund(c["charge_id"], "退回")
    assert accounts.get_user(uid)["vip_queries_left"] == pricing.VIP["queries"]
    assert accounts.charge_qa(uid)["via"] == "vip"                            # VIP 问答不扣积分
    accounts.purchase_demo(uid, "vip30")                                      # 续费：有效期顺延、次数累加
    u2 = accounts.get_user(uid)
    assert u2["vip_queries_left"] == 2 * pricing.VIP["queries"]
    assert datetime.fromisoformat(u2["vip_until"]) - datetime.fromisoformat(u["vip_until"]) >= timedelta(days=29)


def test_vip_qa_daily_cap(monkeypatch):
    monkeypatch.setitem(pricing.VIP, "qa_daily_cap", 2)
    uid = accounts.register("alice", "secret123")["id"]
    accounts.purchase_demo(uid, "vip30")
    assert [accounts.charge_qa(uid)["via"] for _ in range(3)] == ["vip", "vip", "credits"]


def test_redeem_codes_single_use():
    admin = accounts.register("admin1", "secret123", role="admin")["id"]
    uid = accounts.register("alice", "secret123")["id"]
    code = accounts.create_codes("p330", 1, admin)[0]
    assert "330 积分" in accounts.redeem(uid, code.lower())                    # 大小写不敏感
    with pytest.raises(AccountError, match="已被使用"):
        accounts.redeem(uid, code)
    with pytest.raises(AccountError, match="不存在"):
        accounts.redeem(uid, "XXXX-XXXX-XXXX-XXXX")
    assert accounts.list_codes()[0]["used_by"] == "alice"


def test_ledger_history_and_admin_adjust():
    admin = accounts.register("admin1", "secret123", role="admin")["id"]
    uid = accounts.register("alice", "secret123")["id"]
    assert accounts.admin_adjust(uid, 50, "补偿", admin) == pricing.SIGNUP_GIFT + 50
    kinds = [h["kind"] for h in accounts.history(uid)]
    assert kinds == ["admin", "gift"]
    with pytest.raises(AccountError, match="积分不足"):
        accounts.admin_adjust(uid, -1000, "扣成负数", admin)


def test_registration_key_required_for_email_and_account(monkeypatch):
    monkeypatch.setenv("TM_EMAIL_DEV", "1")
    monkeypatch.delenv("SMTP_HOST", raising=False)
    email = "invited@example.com"
    with pytest.raises(AccountError, match="注册密钥不正确"):
        accounts.send_email_code(email, registration_key="密钥错误")
    assert not settings.accounts_path.exists()

    code = accounts.send_email_code(email, registration_key=REGISTRATION_KEY)
    assert code
    with pytest.raises(AccountError, match="注册密钥不正确"):
        accounts.register_with_email("guest", email, code, "secret123", registration_key="")

    monkeypatch.setattr(settings, "registration_key", "")
    with pytest.raises(AccountError, match="注册暂未开放"):
        accounts.send_email_code(email, registration_key=REGISTRATION_KEY)
    with pytest.raises(AccountError, match="注册暂未开放"):
        accounts.register_with_email("guest", email, code, "secret123", registration_key=REGISTRATION_KEY)

    monkeypatch.setattr(settings, "registration_key", REGISTRATION_KEY)
    user = accounts.register_with_email("guest", email, code, "secret123", registration_key=REGISTRATION_KEY)
    assert user["email"] == email


def test_email_code_register_flow(monkeypatch):
    monkeypatch.setenv("TM_EMAIL_DEV", "1")
    monkeypatch.delenv("SMTP_HOST", raising=False)
    code = accounts.send_email_code("a@example.com", registration_key=REGISTRATION_KEY)
    assert code and len(code) == 6
    with pytest.raises(AccountError, match="太频繁"):                        # 60 秒内不能重发
        accounts.send_email_code("a@example.com", registration_key=REGISTRATION_KEY)
    wrong = "000000" if code != "000000" else "111111"
    with pytest.raises(AccountError, match="不正确"):
        accounts.register_with_email("alice", "a@example.com", wrong, "secret123", registration_key=REGISTRATION_KEY)
    u = accounts.register_with_email("alice", "a@example.com", code, "secret123", registration_key=REGISTRATION_KEY)
    assert u["email"] == "a@example.com" and u["balance"] == pricing.SIGNUP_GIFT
    with pytest.raises(AccountError, match="请先获取"):                       # 验证码用过即作废
        accounts.register_with_email("bob", "a@example.com", code, "secret123", registration_key=REGISTRATION_KEY)
    with pytest.raises(AccountError, match="已被注册"):                       # 邮箱不区分大小写
        accounts.send_email_code("A@example.com", registration_key=REGISTRATION_KEY)
    with pytest.raises(AccountError, match="格式"):
        accounts.send_email_code("not-an-email", registration_key=REGISTRATION_KEY)


def test_email_code_wrong_attempts_limited(monkeypatch):
    monkeypatch.setenv("TM_EMAIL_DEV", "1")
    monkeypatch.delenv("SMTP_HOST", raising=False)
    code = accounts.send_email_code("b@example.com", registration_key=REGISTRATION_KEY)
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(accounts.CODE_MAX_TRIES):
        with pytest.raises(AccountError, match="不正确"):
            accounts.register_with_email("bob", "b@example.com", wrong, "secret123", registration_key=REGISTRATION_KEY)
    with pytest.raises(AccountError, match="次数过多"):                       # 错误次数用完后正确的也不行
        accounts.register_with_email("bob", "b@example.com", code, "secret123", registration_key=REGISTRATION_KEY)


def test_email_required_service(monkeypatch):
    monkeypatch.delenv("TM_EMAIL_DEV", raising=False)
    monkeypatch.delenv("SMTP_HOST", raising=False)
    with pytest.raises(AccountError, match="尚未配置"):
        accounts.send_email_code("c@example.com", registration_key=REGISTRATION_KEY)


def test_unlimited_account_never_charged():
    u = accounts.register("zzz_test", "000000", role="tester", unlimited=True, vip_until="2099-12-31T23:59:59",
                          enforce_rule=False)
    assert u["unlimited"] and u["vip_active"] and u["balance"] == 0
    for _ in range(3):
        assert accounts.charge_query(u["id"])["via"] == "unlimited"
        assert accounts.charge_qa(u["id"])["via"] == "unlimited"
    assert accounts.can_query(u["id"]) and accounts.get_user(u["id"])["balance"] == 0
    assert accounts.login("zzz_test", "000000")["unlimited"]


def test_captcha():
    from app import captcha

    ch, answer = captcha.new_with_answer()
    assert captcha.check(ch, answer.lower()) and not captcha.check(ch, "WRONG") and not captcha.check(None, answer)
    assert "answer" not in str(captcha.new().keys()) and set(captcha.new()) == {"png", "hash", "at"}
    ch["at"] -= captcha.TTL + 1
    assert not captcha.check(ch, answer)                                      # 过期作废
