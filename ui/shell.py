"""登录后的页面外框：与首页同一套视觉——深墨蓝顶栏、带网纹的页头、金色主按钮、底部信息条。

顶栏替代原来的侧边栏：标识、导航（新建评估 / 历史报告 / 积分与充值 / 管理后台）、账号信息与退出。
内容区仍是浅色纸面卡片，保证报告和表格好读。
"""
from __future__ import annotations

from html import escape as esc

import streamlit as st

from app import pricing
from ui import style

PAGES = {
    "input": ("NEW ASSESSMENT", "新建评估", "填写拟申请的商标和要用在哪些商品或服务上，检索在先商标并评估注册风险"),
    "cached": ("NEW ASSESSMENT", "这个查询评估过", "可以直接查看上次的报告，也可以重新评估"),
    "goods": ("STEP 2", "确认商品项", "检索类别由选中的商品项决定，选录之外的商品会单独提示"),
    "candidates": ("STEP 3", "确认候选", "查看召回的在先商标和大模型的逐组判定，剔除明显无关的候选"),
    "report": ("REPORT", "风险报告", "风险分布、总结论和每个候选的理由与依据；可下载简洁版或标准版 PDF"),
    "history": ("HISTORY", "历史报告", "你评估过的报告，打开查看不扣积分"),
    "account": ("ACCOUNT", "积分与充值", f"1 积分 = {pricing.CREDIT_CNY:g} 元；评估 {pricing.COST_QUERY} 积分 / 次，"
                                        f"法律问答 {pricing.COST_QA} 积分 / 次"),
    "admin": ("ADMIN", "管理后台", "用户、积分调整与兑换码"),
}
NAV = [("input", "新建评估"), ("history", "历史报告"), ("account", "积分与充值")]
FLOW = {"input", "cached", "goods", "candidates", "report"}


def css() -> str:
    pattern = style.asset_uri("hero-pattern.svg") or ""
    return f"""<style>
[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"], [data-testid="stHeader"]{{display:none !important;}}
.block-container{{padding-top:0 !important;}}
/* 顶栏：固定在页面顶部的整条深色栏（标识、导航、账号），内容区让出高度 */
.block-container{{padding-top:58px !important; padding-bottom:0 !important;}}
.appbar{{position:fixed; top:0; left:0; right:0; height:58px; z-index:990; background:#0b1626;
  border-bottom:1px solid rgba(255,255,255,.08); display:flex; align-items:center; justify-content:space-between;
  padding:0 calc(4vw + 70px) 0 4vw;}}
.appbar .tn-brand{{display:flex; align-items:center; gap:.6rem;}}
.appbar .tn-brand img{{width:1.8rem; height:1.8rem;}}
.appbar .tn-brand b{{font-family:var(--serif); color:#fff; font-size:.98rem; white-space:nowrap;}}
.appbar .tn-user{{display:flex; align-items:center; gap:.5rem; color:#c3ccd8; font-size:.82rem; white-space:nowrap;}}
.tn-chip{{border:1px solid rgba(255,255,255,.2); border-radius:999px; padding:.14rem .7rem; color:#e8edf3; font-size:.78rem;}}
.tn-chip.vip{{border-color:var(--brass); color:var(--brass);}}
.st-key-topnav, .st-key-tn_logout{{position:fixed !important; top:11px; z-index:1000; width:auto !important;}}
.st-key-topnav{{left:50%; transform:translateX(-50%);}}
.st-key-tn_logout{{right:4vw;}}
.st-key-topnav [data-testid="stHorizontalBlock"]{{gap:.2rem; flex-wrap:nowrap;}}
.st-key-topnav [data-testid="stColumn"]{{width:auto !important; flex:0 0 auto !important; min-width:0 !important;}}
.st-key-topnav .stButton button[kind], .st-key-tn_logout .stButton button[kind]{{background:transparent !important; border:none !important;
  box-shadow:none !important; color:#c3ccd8 !important; padding:.38rem .9rem !important; min-height:0; border-radius:8px;
  white-space:nowrap;}}
.st-key-topnav .stButton button[kind] p, .st-key-tn_logout .stButton button[kind] p{{color:#c3ccd8 !important; font-size:.9rem; font-weight:500 !important;}}
.st-key-topnav .stButton button:hover, .st-key-tn_logout .stButton button:hover{{background:rgba(255,255,255,.07) !important;}}
.st-key-topnav .stButton button:hover p, .st-key-tn_logout .stButton button:hover p{{color:#fff !important;}}
.st-key-topnav .stButton button[kind="primary"][kind]{{background:transparent !important; box-shadow:inset 0 -2px 0 var(--brass) !important; border-radius:0;}}
.st-key-topnav .stButton button[kind="primary"][kind] p{{color:#fff !important; font-weight:600 !important;}}
.st-key-tn_logout .stButton button[kind]{{border:1px solid rgba(255,255,255,.2) !important; border-radius:999px;}}
/* 固定定位的顶栏元素不占版面：把它们在文档流里的占位压成 0，页头紧贴顶栏 */
[data-testid="stElementContainer"]:has(.appbar), [data-testid="stVerticalBlock"] > div:has(> .st-key-topnav),
[data-testid="stVerticalBlock"] > div:has(> .st-key-tn_logout),
[data-testid="stElementContainer"]:has([data-testid="stMarkdown"] style):not(:has(.pagehead)){{
  height:0 !important; min-height:0 !important; margin:0 0 -1rem 0 !important; padding:0 !important;}}   /* -1rem 抵消列间距 */
/* 页头 */
.pagehead{{width:100vw; margin-left:calc(50% - 50vw); padding:2.1rem max(1.2rem, calc(50vw - 590px)) 1.5rem;
  margin-bottom:1.6rem; color:#fff;
  background:url("{pattern}") right center / cover no-repeat,
             radial-gradient(800px 300px at 85% 0%, rgba(176,141,87,.25), transparent 65%),
             linear-gradient(160deg, #0f1c2e 0%, #0b1626 100%);}}
.pagehead .eb{{display:flex; align-items:center; gap:.7rem; font-size:.7rem; letter-spacing:.3em; color:var(--brass); font-weight:600;}}
.pagehead .eb::before{{content:""; width:1.8rem; height:1px; background:var(--brass);}}
.pagehead h1{{font-family:var(--serif) !important; font-size:2rem; margin:.5rem 0 .35rem 0; padding:0; color:#fff !important;}}
.pagehead h1 *{{color:#fff !important;}}
.pagehead p{{color:#aeb9c7; font-size:.92rem; margin:0;}}
.pagehead .steps{{margin:1.3rem 0 0 0;}}
.pagehead .step{{background:rgba(255,255,255,.04); border-color:rgba(255,255,255,.12); color:#8794a6;}}
.pagehead .step .n{{background:rgba(255,255,255,.08); color:#aeb9c7;}}
.pagehead .step .t small{{color:#6f7d90;}}
.pagehead .step.done{{color:#c3ccd8;}}
.pagehead .step.done .n{{background:#2a3f5c; color:#fff;}}
.pagehead .step.now{{background:rgba(176,141,87,.12); border-color:var(--brass); color:#fff; box-shadow:none;}}
.pagehead .step.now .n{{background:var(--brass); color:#0b1626;}}
/* 金色主按钮（与首页“立即评估”一致） */
.stButton button[kind="primary"], .stDownloadButton button[kind="primary"], [data-testid="stFormSubmitButton"] button[kind="primary"],
.stButton button[data-testid="stBaseButton-primary"], .stDownloadButton button[data-testid="stBaseButton-primary"],
[data-testid="stFormSubmitButton"] button[data-testid="stBaseButton-primaryFormSubmit"]{{
  background:linear-gradient(135deg, #c9a46a, #b08d57) !important; border:none !important; color:#0b1626 !important;
  box-shadow:0 6px 18px rgba(176,141,87,.28);}}
.stButton button[kind="primary"] p, .stDownloadButton button[kind="primary"] p, [data-testid="stFormSubmitButton"] button[kind="primary"] p{{
  color:#0b1626 !important; font-weight:700;}}
/* 历史报告 */
.hist{{display:flex; flex-direction:column; gap:.15rem;}}
.hist b{{font-family:var(--serif); font-size:1.12rem; color:var(--ink);}}
.hist span{{font-size:.8rem; color:var(--muted);}}
/* 底部信息条 */
.appfoot{{width:100vw; margin-left:calc(50% - 50vw); margin-top:3rem; padding:1.1rem max(1.2rem, calc(50vw - 590px));
  background:#0b1626; color:#8794a6; font-size:.76rem; line-height:1.8;}}
/* 页脚高度固定、贴住窗口底部：内容少时中间留浅色，内容多时页脚跟在内容后面 */
.block-container{{min-height:100vh; box-sizing:border-box; display:flex; flex-direction:column;}}
.block-container > [data-testid="stVerticalBlock"]{{flex:1 0 auto;}}
[data-testid="stElementContainer"]:has(> [data-testid="stMarkdown"] .appfoot){{margin-top:auto !important;}}
[data-testid="stElementContainer"]:has(.appfoot) :is([data-testid="stMarkdown"], [data-testid="stMarkdownContainer"]){{
  margin-bottom:0 !important;}}   /* 文本块自带的负下边距会让页脚超出页面底边 */
.appfoot b{{color:#c3ccd8; font-weight:600;}}
@media (max-width: 1100px){{ .appbar .tn-brand b, .appbar .tn-user .name{{display:none;}} }}
@media (max-width: 760px){{ .appbar .tn-user, .appbar .tn-brand{{display:none;}} .st-key-topnav{{left:auto; right:calc(4vw + 64px); transform:none;}}
  .st-key-topnav .stButton button{{padding:.38rem .5rem !important;}} .pagehead h1{{font-size:1.5rem;}} }}
</style>"""


def topnav(me: dict, stage: str) -> str | None:
    """画顶栏，返回用户点到的目标页（或 "logout"），没点返回 None。
    整条深色栏是一段固定定位的 HTML；导航和退出按钮是 Streamlit 按钮，固定定位叠在栏上。"""
    pages = NAV + ([("admin", "管理后台")] if me.get("role") == "admin" else [])
    current = "input" if stage in FLOW else stage
    bal = "积分不限" if me.get("unlimited") else f"{me['balance']} 积分"
    vip = '<span class="tn-chip vip">VIP</span>' if me.get("vip_active") else ""
    st.markdown(f'<div class="appbar"><div class="tn-brand"><img src="{style.asset_uri("logo-mark-light.svg")}" alt="">'
                f'<b>商标近似评估智能体</b></div><div class="tn-user"><span class="name">{esc(me["username"])}</span>'
                f'<span class="tn-chip">{esc(bal)}</span>{vip}</div></div>', unsafe_allow_html=True)
    clicked = None
    with st.container(key="topnav"):
        for col, (key, label) in zip(st.columns(len(pages)), pages):
            if col.button(label, key=f"nav_{key}", type="primary" if key == current else "secondary"):
                clicked = key
    with st.container(key="tn_logout"):
        if st.button("退出", key="nav_logout"):
            clicked = "logout"
    return clicked


def page_head(stage: str, step: int | None = None, subtitle: str | None = None) -> str:
    eb, title, sub = PAGES.get(stage, ("", "", ""))
    steps = style.steps(step) if step is not None else ""
    return (f'<div class="pagehead"><div class="eb">{esc(eb)}</div><h1>{esc(title)}</h1>'
            f'<p>{esc(subtitle or sub)}</p>{steps}</div>')


def footer(cov: dict, llm_model: str) -> str:
    real = cov.get("real", {})
    data = (f"国家知识产权局商标开放数据 <b>{real.get('count', 0):,}</b> 件（第 {esc(str(real.get('classes', '')))} 类，"
            f"增量截至 {esc(str(real.get('date', '')))}）" if real.get("source") == "open"
            else f"本地记录 {real.get('count', 0)} 条（未接入正式商标库）")
    return (f'<div class="appfoot">数据：{data}　·　大模型：<b>{esc(llm_model or "未配置")}</b> 逐组判定，规则护栏兜底　·　'
            '法律依据按评估日期选用商标法版本，审查审理指南 2021 年版<br>'
            '仅供商标申请前筛查参考，不构成法律意见；在先状态由公告日期推定，法律状态须另行核实。</div>')
