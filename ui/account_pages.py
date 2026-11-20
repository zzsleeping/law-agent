"""登录 / 注册、积分与充值、管理后台三个页面。业务逻辑在 app/accounts.py，这里只负责界面。"""
from __future__ import annotations

from html import escape as esc

import pandas as pd
import streamlit as st

from app import accounts, captcha, pricing
from app.accounts import AccountError
from ui import style

KIND_LABEL = {"gift": "赠送", "purchase": "购买", "query": "评估", "qa": "问答", "refund": "退款", "unlimited": "不限额度",
              "vip": "VIP", "vip_query": "评估（VIP）", "vip_qa": "问答（VIP）", "admin": "管理员调整"}


def _captcha(slot: str) -> str:
    """显示一张图形验证码和输入框，返回用户输入。slot 区分登录 / 注册各自的验证码。"""
    key = f"cap_{slot}"
    if key not in st.session_state:
        st.session_state[key] = captcha.new()
    c1, c2 = st.columns([1.3, 1])
    answer = c1.text_input("图形验证码", key=f"cap_in_{slot}", placeholder="输入右侧字符，不分大小写")
    c2.image(st.session_state[key]["png"], use_container_width=True)
    return answer


def _retry(slot: str, error: str | None = None, note: str | None = None) -> None:
    """窗口不关闭的所有结果（出错、已发送验证码）都换一张验证码并立即重画窗口，让图片与答案一致。
    提示信息存进会话，重画后显示。"""
    st.session_state[f"cap_{slot}"] = captcha.new()
    if error:
        st.session_state.auth_err = error
    if note:
        st.session_state.reg_note = note
    st.rerun(scope="fragment")


def _captcha_ok(slot: str, answer: str) -> None:
    """校验图形验证码；不通过时换图并提示。通过后也作废这一张（同一张不能用两次）。"""
    if not captcha.check(st.session_state.get(f"cap_{slot}"), answer):
        _retry(slot, "图形验证码不正确或已过期，请重新输入")
    st.session_state[f"cap_{slot}"] = captcha.new()


def _login_form() -> None:
    with st.form("login", border=False):
        name = st.text_input("用户名", placeholder="字母、数字或下划线")
        pw = st.text_input("密码", type="password")
        ans = _captcha("login")
        if st.form_submit_button("登录", type="primary", use_container_width=True):
            _captcha_ok("login", ans)
            try:
                user = accounts.login(name, pw)
            except AccountError as e:
                _retry("login", str(e))
            st.session_state.user = user
            st.rerun()
    if st.button("看不清，换一张", key="cap_refresh_login"):
        _retry("login")


def _register_form() -> None:
    with st.form("register", border=False):
        name = st.text_input("用户名", placeholder="3–20 位字母、数字或下划线，不能包含中文")
        email = st.text_input("邮箱", placeholder="用于接收验证码")
        c1, c2 = st.columns([1.3, 1], vertical_alignment="bottom")
        code = c1.text_input("邮箱验证码", placeholder="6 位数字")
        send = c2.form_submit_button("获取验证码", use_container_width=True)
        pw = st.text_input("密码", type="password", placeholder="至少 8 位，含字母和数字")
        pw2 = st.text_input("确认密码", type="password")
        ans = _captcha("reg")
        submit = st.form_submit_button(f"注册（送 {pricing.SIGNUP_GIFT} 积分）", type="primary", use_container_width=True)
        if send:                                         # 发验证码也要先过图形验证码，防止被拿来批量发信
            _captcha_ok("reg", ans)
            try:
                dev_code = accounts.send_email_code(email)
            except AccountError as e:
                _retry("reg", str(e))
            _retry("reg", note=(f"本机调试模式（未配置邮件服务）：验证码是 {dev_code}" if dev_code
                                else f"验证码已发送到 {email.strip()}，{accounts.CODE_TTL_MIN} 分钟内有效"))
        if submit:
            _captcha_ok("reg", ans)
            if pw != pw2:
                _retry("reg", "两次输入的密码不一致")
            try:
                user = accounts.register_with_email(name, email, code, pw)
            except AccountError as e:
                _retry("reg", str(e))
            st.session_state.user = user
            st.session_state.flash = f"注册成功，已赠送 {pricing.SIGNUP_GIFT} 积分，可以完整评估一次。"
            st.session_state.pop("reg_note", None)
            st.rerun()
    if note := st.session_state.get("reg_note"):
        st.info(note)
    if st.button("看不清，换一张", key="cap_refresh_reg"):
        _retry("reg")


@st.dialog("登录 / 注册", width="small")
def auth_dialog(mode: str = "login") -> None:
    """页面中的小窗口：登录或注册。登录成功后关闭窗口并刷新页面。"""
    pick = st.segmented_control("方式", ["login", "register"], default=mode, label_visibility="collapsed",
                                format_func={"login": "登录", "register": "注册新账号"}.get, key="auth_mode")
    if err := st.session_state.pop("auth_err", None):
        st.error(err)
    if (pick or mode) == "register":
        _register_form()
    else:
        _login_form()


def landing_page(cov: dict) -> None:
    """未登录时的首页：一屏主视觉，顶栏登录 / 注册、中间一个主按钮，不滚动。所有功能都要登录后使用。"""
    real = cov.get("real", {})
    st.markdown(style.landing_css(), unsafe_allow_html=True)
    st.markdown(style.landing_kv([
        (f"{real.get('count', 0) / 10000:,.0f} 万件" if real.get("source") == "open" else "本地数据", "国知局商标开放数据"),
        ("4 大类", "食品、饮料、餐饮与住宿"),
        ("可追溯", "每条结论附法条与审查指南依据"),
    ]), unsafe_allow_html=True)
    with st.container(key="kv_top"):
        c1, c2 = st.columns(2)
        if c1.button("登录", key="top_login"):
            auth_dialog("login")
        if c2.button("注册", type="primary", key="top_reg"):
            auth_dialog("register")
    with st.container(key="kv_cta"):
        if st.button("立即评估　→", key="cta_start"):
            auth_dialog("register")


def account_page(user: dict) -> None:
    html = lambda s: st.markdown(s, unsafe_allow_html=True)  # noqa: E731
    u = accounts.get_user(user["id"])
    if u["unlimited"]:
        html(style.kpis([("不限", "积分余额", "特权测试账号：评估与问答不扣积分", "accent"),
                         ("VIP", "VIP", f"有效期至 {u['vip_until'][:10]}", "low")]))
    else:
        vip = (f"有效期至 {u['vip_until'][:10]}，剩余 {u['vip_queries_left']} 次评估" if u["vip_active"] else "未开通")
        html(style.kpis([(u["balance"], "积分余额", f"约可评估 {u['balance'] // pricing.COST_QUERY} 次", "accent"),
                         ("VIP" if u["vip_active"] else "—", "月度 VIP", vip, "low" if u["vip_active"] else "")]))

    html(style.note("<b>演示支付</b>　当前为比赛演示环境，未接入真实支付：点击“演示支付”会直接到账，不会扣款。"
                    "正式上线时接入微信 / 支付宝。", "info"))
    cols = st.columns(len(pricing.PACKAGES) + 1, gap="medium")
    for col, p in zip(cols, pricing.PACKAGES + [pricing.VIP]):
        vip = p["id"] == pricing.VIP["id"]
        if vip:
            unit = f'{p["days"]} 天'
            perks = [f'{p["queries"]} 次评估', f'问答免费（每天 {p["qa_daily_cap"]} 次）', "续费天数、次数累加"]
        else:
            unit = f'{p["credits"]} 积分'
            n = p["credits"] // pricing.COST_QUERY
            perks = [f"约 {n} 次评估", f"多送 {p['bonus']}%" if p.get("bonus") else "按原价计", "积分长期有效"]
        with col, st.container(border=True, key=f"prod_{p['id']}"):
            html(f'<div class="plan{" vip" if vip else ""}"><div class="nm">{esc(p["name"])}'
                 + ('<span class="tag-vip">推荐</span>' if vip else "") + '</div>'
                 f'<div class="pr"><small>¥</small>{p["price"]:g}</div><div class="unit">{esc(unit)}</div>'
                 '<ul>' + "".join(f"<li>{esc(x)}</li>" for x in perks) + '</ul></div>')
            if st.button("开通 VIP（演示支付）" if vip else "购买（演示支付）", key=f"buy_{p['id']}",
                         use_container_width=True, type="primary" if vip else "secondary"):
                st.session_state.flash = accounts.purchase_demo(u["id"], p["id"])
                st.rerun()

    with st.form("redeem", border=True):
        c1, c2 = st.columns([3, 1])
        code = c1.text_input("兑换码", placeholder="XXXX-XXXX-XXXX-XXXX", label_visibility="collapsed")
        if c2.form_submit_button("兑换", use_container_width=True):
            try:
                st.session_state.flash = accounts.redeem(u["id"], code)
                st.rerun()
            except AccountError as e:
                st.error(str(e))

    html(style.section("积分明细", "最近 50 条"))
    rows = accounts.history(u["id"])
    if rows:
        st.dataframe(pd.DataFrame([{"时间": r["created"].replace("T", " "), "类型": KIND_LABEL.get(r["kind"], r["kind"]),
                                    "变动": (f"+{r['delta']}" if r["delta"] > 0 else str(r["delta"])) if r["delta"] else "—",
                                    "余额": r["balance_after"], "说明": r["note"]} for r in rows]),
                     hide_index=True, use_container_width=True)

    with st.expander("修改密码"), st.form("pw", border=False):
        old = st.text_input("原密码", type="password")
        new = st.text_input("新密码（至少 8 位，含字母和数字）", type="password")
        if st.form_submit_button("修改"):
            try:
                accounts.change_password(u["id"], old, new)
                st.success("密码已修改")
            except AccountError as e:
                st.error(str(e))


def admin_page(user: dict) -> None:
    html = lambda s: st.markdown(s, unsafe_allow_html=True)  # noqa: E731
    if user.get("role") != "admin":
        st.error("没有权限")
        return
    users = accounts.list_users()
    st.dataframe(pd.DataFrame([{"ID": x["id"], "用户名": x["username"], "角色": x["role"],
                                "积分": "不限" if x["unlimited"] else str(x["balance"]), "邮箱": x.get("email") or "—",
                                "VIP": f"至 {x['vip_until'][:10]}（剩 {x['vip_queries_left']} 次）" if x["vip_active"] else "—",
                                "注册时间": x["created"].replace("T", " ")} for x in users]),
                 hide_index=True, use_container_width=True)
    c1, c2 = st.columns(2)
    with c1, st.form("adjust", border=True):
        st.markdown("**调整积分**")
        who = st.selectbox("用户", [x["username"] for x in users if x["role"] == "user"] or ["（暂无用户）"])
        delta = st.number_input("变动（负数为扣减）", value=0, step=10)
        note = st.text_input("说明", placeholder="例如：活动补偿")
        if st.form_submit_button("确认调整"):
            target = next((x for x in users if x["username"] == who), None)
            if target and delta:
                try:
                    bal = accounts.admin_adjust(target["id"], int(delta), note, user["id"])
                    st.success(f"已调整，{who} 当前余额 {bal} 积分")
                except AccountError as e:
                    st.error(str(e))
    with c2, st.form("codes", border=True):
        st.markdown("**生成兑换码**")
        prod = st.selectbox("套餐", list(pricing.PRODUCTS), format_func=lambda k: f"{pricing.PRODUCTS[k]['name']}（¥{pricing.PRODUCTS[k]['price']:g}）")
        n = st.number_input("数量", min_value=1, max_value=200, value=5)
        if st.form_submit_button("生成"):
            codes = accounts.create_codes(prod, int(n), user["id"])
            st.code("\n".join(codes))
    codes = accounts.list_codes()
    if codes:
        with st.expander(f"兑换码记录（{len(codes)}）"):
            st.dataframe(pd.DataFrame([{"兑换码": c["code"], "套餐": pricing.PRODUCTS.get(c["product"], {}).get("name", c["product"]),
                                        "生成时间": c["created"].replace("T", " "), "使用者": c["used_by"] or "—",
                                        "使用时间": (c["used_at"] or "—").replace("T", " ")} for c in codes]),
                         hide_index=True, use_container_width=True)
