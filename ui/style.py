"""页面样式与 HTML 小组件。只负责外观，不含业务逻辑。

风格：编辑式法律工作台——深墨蓝 + 暖白纸色，衬线标题，细线、留白，印章红只用在品牌标识。
视觉素材（图标、插画、纹样）见 tasks/codex/06-ui-assets.md：先找 ui/assets/，再找 collected/ui_assets/，
都没有时用内置的简单标识，页面照常显示。
"""
from __future__ import annotations

import base64
import re
from functools import lru_cache
from html import escape as esc
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSET_DIRS = [ROOT / "ui" / "assets", ROOT / "collected" / "ui_assets"]
RISK_CLASS = {"high": "high", "medium": "med", "needs_check": "check", "low": "low"}

# 素材缺失时的内置标识：圆角方印 + 两个重叠的字框
_FALLBACK_LOGO = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
                  '<rect x="5" y="5" width="54" height="54" rx="9" fill="none" stroke="#b23a2e" stroke-width="4"/>'
                  '<rect x="15" y="17" width="21" height="21" rx="2" fill="none" stroke="#b23a2e" stroke-width="3.2"/>'
                  '<rect x="28" y="27" width="21" height="21" rx="2" fill="#b23a2e" fill-opacity=".9"/></svg>')


@lru_cache(maxsize=64)
def _read(name: str) -> str | None:
    for d in ASSET_DIRS:
        p = d / name
        if p.is_file():
            return p.read_text(encoding="utf-8")
    return None


def asset_uri(name: str) -> str | None:
    """素材的 data URI（用于 <img> 和 CSS 背景）；没有该素材时返回 None。"""
    svg = _read(name)
    if svg is None and name.startswith("logo-mark"):
        svg = _FALLBACK_LOGO.replace("#b23a2e", "#ffffff") if "light" in name else _FALLBACK_LOGO
    if svg is None:
        return None
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode("utf-8")).decode()


def icon(name: str) -> str:
    """内联线性图标（随文字颜色变色）；没有素材时返回空串。"""
    svg = _read(f"icons/{name}.svg")
    if not svg:
        return ""
    svg = re.sub(r"<\?xml[^>]*>|<!--.*?-->", "", svg, flags=re.S).strip()
    return f'<span class="ico">{svg}</span>'


def logo_file() -> str:
    """侧边栏 st.logo 用的图片（data URI）。"""
    return asset_uri("logo-mark-light.svg")


def _css() -> str:
    pattern = asset_uri("hero-pattern.svg")
    watermark = asset_uri("report-watermark.svg")
    hero_bg = f'url("{pattern}") right center / cover no-repeat, ' if pattern else ""
    doc_bg = f'url("{watermark}") right -40px top -60px / 300px no-repeat, ' if watermark else ""
    return CSS.replace("/*HERO_BG*/", hero_bg).replace("/*DOC_BG*/", doc_bg)


CSS = """
<style>
:root{
  --ink:#0f1c2e; --ink-2:#1d3352; --text:#1f2a37; --muted:#667085; --faint:#98a2b3;
  --paper:#f7f5f0; --card:#ffffff; --line:#e6e1d6; --line-2:#efebe2;
  --brass:#b08d57; --seal:#b23a2e; --accent:#1d3352; --accent-soft:#eef1f6;
  --high:#b42318; --high-bg:#fdf0ee; --med:#b54708; --med-bg:#fdf4e7;
  --check:#5b4fc4; --check-bg:#f1effc; --low:#2f7a52; --low-bg:#ebf5ef;
  --serif:"Songti SC","Noto Serif SC","Source Han Serif SC","STSong","SimSun",serif;
  --sans:"PingFang SC","Hiragino Sans GB","Microsoft YaHei","Noto Sans SC",system-ui,sans-serif;
  --mono:"SF Mono","JetBrains Mono",Menlo,Consolas,monospace;
  --shadow:0 1px 2px rgba(15,28,46,.04), 0 4px 16px rgba(15,28,46,.04);
}
html, body, .stApp, .stApp p, .stApp li, .stApp label, .stApp input, .stApp button, .stApp textarea{font-family:var(--sans);}
.stApp{background:var(--paper); color:var(--text);}
.block-container{max-width:1180px; padding-top:1.6rem; padding-bottom:5rem;}
header[data-testid="stHeader"]{background:transparent;}
#MainMenu, footer, [data-testid="stDecoration"]{display:none;}
h1,h2,h3{font-family:var(--serif) !important; color:var(--ink); letter-spacing:.01em;}
.ico{display:inline-flex; width:1.05em; height:1.05em; vertical-align:-.16em;}
.ico svg{width:100%; height:100%;}

/* ---------- 侧边栏：深墨蓝 ---------- */
[data-testid="stSidebar"]{background:var(--ink); border-right:none;}
[data-testid="stSidebar"] *{color:#c9d1dc;}
[data-testid="stSidebar"] .block-container{padding-top:1rem;}
[data-testid="stSidebarHeader"] img{height:2.1rem !important;}
.brand{display:flex; align-items:center; gap:.7rem; margin:.2rem 0 1.2rem 0;}
.brand img{width:2.4rem; height:2.4rem;}
.brand .n{font-family:var(--serif); font-size:1.08rem; font-weight:700; color:#fff !important; line-height:1.25;}
.brand .s{font-size:.7rem; letter-spacing:.12em; color:var(--brass) !important;}
.side-h{display:flex; align-items:center; gap:.4rem; font-size:.7rem; letter-spacing:.16em; color:var(--brass) !important;
  margin:1.3rem 0 .45rem 0; font-weight:600;}
.side-h *{color:var(--brass) !important;}
.side-row{display:flex; justify-content:space-between; gap:.6rem; font-size:.84rem; padding:.36rem 0;
  border-bottom:1px solid rgba(255,255,255,.07);}
.side-row b{font-family:var(--mono); font-weight:600; color:#fff !important; font-size:.8rem;}
.side-cap{font-size:.75rem; color:#8d99aa !important; line-height:1.65; margin-top:.5rem;}
[data-testid="stSidebar"] .stButton button{background:rgba(255,255,255,.04); border:1px solid rgba(255,255,255,.12);
  color:#dfe5ec !important; font-weight:500; text-align:left; justify-content:flex-start; padding:.45rem .8rem;}
[data-testid="stSidebar"] .stButton button:hover{background:rgba(255,255,255,.09); border-color:var(--brass);}
[data-testid="stSidebar"] .stButton button p{color:#dfe5ec !important; font-size:.82rem;}
.main-only{}

/* ---------- 抬头横幅 ---------- */
.hero{position:relative; border-radius:18px; padding:1.9rem 2.1rem 1.7rem; margin:0 0 1.2rem 0; overflow:hidden;
  background:/*HERO_BG*/radial-gradient(1200px 300px at 85% -20%, rgba(176,141,87,.22), transparent 60%), var(--ink);
  box-shadow:var(--shadow);}
.hero .eyebrow{display:flex; align-items:center; gap:.6rem; font-size:.72rem; letter-spacing:.22em; color:var(--brass);
  font-weight:600;}
.hero .eyebrow::before{content:""; width:1.6rem; height:1px; background:var(--brass);}
.hero h1{font-size:2.15rem; line-height:1.25; margin:.55rem 0 .45rem 0; padding:0; font-weight:700; color:#fff !important;}
.hero .sub{color:#b8c2cf; font-size:.94rem; max-width:44rem; line-height:1.75;}
.hero .hfacts{display:flex; flex-wrap:wrap; gap:.55rem; margin-top:1.15rem; list-style:none; padding:0;}
.hero .fact{display:inline-flex; align-items:center; gap:.45rem; padding:.36rem .8rem; border-radius:999px;
  border:1px solid rgba(255,255,255,.14); background:rgba(255,255,255,.05); color:#e3e8ee; font-size:.8rem;}
.hero .fact b{color:#fff; font-family:var(--mono); font-weight:600;}
.hero .fact .ico{color:var(--brass);}
.hero.compact{padding:1.05rem 1.6rem; border-radius:14px; display:flex; align-items:center; gap:1.2rem;}
.hero.compact h1{font-size:1.3rem; margin:0;}
.hero.compact .eyebrow{font-size:.66rem;}
.hero.compact .eyebrow::before{display:none;}

/* ---------- 步骤条 ---------- */
.steps{display:flex; gap:.5rem; margin:0 0 1.6rem 0;}
.step{flex:1; display:flex; align-items:center; gap:.65rem; padding:.7rem .95rem; min-width:0; border-radius:12px;
  background:var(--card); border:1px solid var(--line); color:var(--faint);}
.step .n{flex:none; width:1.8rem; height:1.8rem; border-radius:50%; display:flex; align-items:center; justify-content:center;
  font-family:var(--mono); font-size:.78rem; background:var(--line-2); color:var(--muted);}
.step .n .ico{width:1rem; height:1rem;}
.step .t{font-size:.88rem; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;}
.step .t small{display:block; font-size:.7rem; color:var(--faint); letter-spacing:.08em;}
.step.done{color:var(--ink-2);}
.step.done .n{background:var(--ink-2); color:#fff;}
.step.now{color:var(--ink); border-color:var(--ink-2); box-shadow:0 0 0 3px var(--accent-soft); font-weight:600;}
.step.now .n{background:var(--seal); color:#fff;}

/* ---------- 卡片、表单、按钮 ---------- */
[data-testid="stVerticalBlockBorderWrapper"]{background:var(--card); border-color:var(--line) !important;
  border-radius:14px !important; box-shadow:var(--shadow);}
[data-testid="stForm"]{background:var(--card); border:1px solid var(--line); border-radius:16px;
  padding:1.5rem 1.6rem 1.3rem; box-shadow:var(--shadow);}
[data-testid="stExpander"] details{border-color:var(--line); border-radius:10px; background:#fcfbf8;}
[data-testid="stExpander"] summary p{font-size:.86rem; color:var(--ink-2);}
.stTextInput input, .stTextArea textarea, .stDateInput input{border-radius:10px !important;}
[data-testid="InputInstructions"]{display:none !important;}   /* 表单输入框里的“Press Enter to submit form”会压住占位文字 */
.stTextInput [data-baseweb="input"], .stDateInput [data-baseweb="input"], .stTextArea [data-baseweb="textarea"]{
  border-radius:10px; border-color:var(--line); background:#fcfbf8;}
.stTextInput label p, .stDateInput label p, .stTextArea label p, .stMultiSelect label p{font-weight:600; color:var(--ink-2); font-size:.86rem;}
.stButton button, .stDownloadButton button, [data-testid="stFormSubmitButton"] button{border-radius:10px; font-weight:600;
  padding:.52rem 1.25rem; border-color:var(--line); transition:all .15s ease;}
.stButton button[kind="primary"], .stDownloadButton button[kind="primary"], [data-testid="stFormSubmitButton"] button[kind="primary"],
.stButton button[data-testid="stBaseButton-primary"], .stDownloadButton button[data-testid="stBaseButton-primary"],
[data-testid="stFormSubmitButton"] button[data-testid="stBaseButton-primaryFormSubmit"]{
  background:var(--ink); border-color:var(--ink); color:#fff;}
.stButton button[kind="primary"]:hover, [data-testid="stFormSubmitButton"] button:hover{background:var(--ink-2); border-color:var(--ink-2);}
.stButton button[kind="secondary"]:hover{border-color:var(--ink-2); color:var(--ink);}


/* ---------- 小标题、说明 ---------- */
.sec{display:flex; align-items:baseline; flex-wrap:wrap; gap:.4rem .8rem; margin:1.9rem 0 .8rem 0; padding-top:.2rem;}
.sec h2{font-size:1.3rem; margin:0; padding:0; display:flex; align-items:center; gap:.55rem;}
.sec h2::before{content:""; width:4px; height:1.05em; border-radius:2px; background:var(--seal);}
.sec .hint{color:var(--muted); font-size:.84rem;}
.lead{color:var(--muted); font-size:.9rem; margin:-.2rem 0 .9rem 0; line-height:1.7;}

/* ---------- 徽标与标签 ---------- */
.badge{display:inline-flex; align-items:center; gap:.35rem; padding:.18rem .65rem; border-radius:999px; font-size:.78rem;
  font-weight:600; white-space:nowrap;}
.badge::before{content:""; width:.42rem; height:.42rem; border-radius:50%; background:currentColor;}
.badge.high{color:var(--high); background:var(--high-bg);} .badge.med{color:var(--med); background:var(--med-bg);}
.badge.check{color:var(--check); background:var(--check-bg);} .badge.low{color:var(--low); background:var(--low-bg);}
.chip{display:inline-flex; align-items:center; gap:.3rem; padding:.12rem .55rem; border:1px solid var(--line);
  border-radius:6px; font-size:.75rem; color:var(--ink-2); background:#fcfbf8; margin:0 .3rem .2rem 0;}
.tag{display:inline-block; padding:.1rem .5rem; border-radius:5px; font-size:.72rem; color:var(--muted); background:var(--line-2);}
.tag.llm{color:var(--ink-2); background:var(--accent-soft);}
.tag.warn{color:var(--high); background:var(--high-bg);}
.tag.tpl{color:var(--med); background:var(--med-bg);}
.id{font-family:var(--mono); font-size:.76rem; color:var(--faint);}

/* ---------- 概览数字 ---------- */
.kpis{display:grid; grid-template-columns:repeat(auto-fit,minmax(140px,1fr)); gap:.75rem; margin:.3rem 0 1.1rem 0;}
.kpi{position:relative; background:var(--card); border:1px solid var(--line); border-radius:14px; padding:.95rem 1.1rem .85rem;
  box-shadow:var(--shadow); overflow:hidden;}
.kpi::before{content:""; position:absolute; left:0; top:0; bottom:0; width:4px; background:var(--line);}
.kpi .v{font-family:var(--serif); font-size:2rem; font-weight:700; line-height:1.05; color:var(--ink);}
.kpi .k{font-size:.82rem; color:var(--text); margin-top:.3rem; font-weight:600;}
.kpi .s{font-size:.72rem; color:var(--faint); margin-top:.15rem;}
.kpi.high::before{background:var(--high);} .kpi.high .v{color:var(--high);}
.kpi.med::before{background:var(--med);} .kpi.med .v{color:var(--med);}
.kpi.check::before{background:var(--check);} .kpi.check .v{color:var(--check);}
.kpi.low::before{background:var(--low);} .kpi.low .v{color:var(--low);}
.kpi.accent::before{background:var(--brass);}

/* ---------- 候选卡片（按风险着色的左边条） ---------- */
[class*="st-key-cand_"]{border-left:4px solid var(--line) !important;}
[class*="st-key-cand_high"]{border-left-color:var(--high) !important;}
[class*="st-key-cand_med"]{border-left-color:var(--med) !important;}
[class*="st-key-cand_check"]{border-left-color:var(--check) !important;}
[class*="st-key-cand_low"]{border-left-color:var(--low) !important;}
.cand-head{display:flex; flex-wrap:wrap; align-items:center; gap:.55rem; margin-bottom:.4rem;}
.cand-head .mark{font-family:var(--serif); font-size:1.35rem; font-weight:700; color:var(--ink);}
.cand-ev{font-size:.9rem; line-height:1.7; margin:.3rem 0; color:var(--text);}
.cand-meta{font-size:.8rem; color:var(--muted); line-height:1.75;}
.cand-meta b{color:var(--ink); font-weight:600;}
.rank{font-family:var(--serif); font-size:1.15rem; color:var(--brass); padding-top:.3rem; text-align:right;}

/* ---------- 信息条 ---------- */
.note{display:flex; gap:.6rem; align-items:flex-start; border-radius:12px; padding:.75rem 1rem; font-size:.86rem;
  line-height:1.65; margin:.2rem 0 .9rem 0; border:1px solid;}
.note.warn{background:var(--med-bg); border-color:#f0d9b5; color:#7a3e06;}
.note.err{background:var(--high-bg); border-color:#f3c7c1; color:#8a1c12;}
.note.info{background:var(--accent-soft); border-color:#d5dce8; color:var(--ink-2);}
.kv{display:grid; grid-template-columns:repeat(auto-fit,minmax(210px,1fr)); gap:.35rem 1.4rem; font-size:.88rem; margin:.4rem 0 .8rem 0;}
.kv div span{color:var(--muted); margin-right:.5rem;}

/* ---------- 输入页右侧说明 ---------- */
.how{background:var(--card); border:1px solid var(--line); border-radius:16px; padding:1.3rem 1.4rem; box-shadow:var(--shadow);}
.how img.illus{width:100%; max-height:220px; object-fit:contain; margin:-.2rem 0 .6rem 0;}
.how h3{font-size:1.02rem; margin:0 0 .7rem 0;}
.how ol{list-style:none; padding:0; margin:0; counter-reset:how;}
.how li{counter-increment:how; position:relative; padding:0 0 .8rem 2.1rem; font-size:.86rem; line-height:1.65; color:var(--text);}
.how li::before{content:counter(how); position:absolute; left:0; top:.05rem; width:1.45rem; height:1.45rem; border-radius:50%;
  border:1px solid var(--brass); color:var(--brass); font-family:var(--serif); font-size:.8rem;
  display:flex; align-items:center; justify-content:center;}
.how li b{color:var(--ink);}
.how .foot{border-top:1px dashed var(--line); padding-top:.7rem; margin-top:.2rem; font-size:.76rem; color:var(--muted); line-height:1.6;}
.empty{text-align:center; padding:1.6rem 1rem; color:var(--muted); font-size:.88rem;}
.empty img{width:200px; max-width:60%; margin-bottom:.6rem;}

/* ---------- 报告：像一份文书 ---------- */
.st-key-doc{background:/*DOC_BG*/var(--card) !important; padding:.6rem .4rem !important;}
.doc-head{border-bottom:1px solid var(--line); padding-bottom:.9rem; margin-bottom:.6rem;}
.doc-head .k{font-size:.7rem; letter-spacing:.2em; color:var(--brass); font-weight:600;}
.doc-head h1{font-size:1.65rem; margin:.35rem 0 .25rem 0; padding:0;}
.doc-head .m{font-size:.8rem; color:var(--muted);}
.claim{border-left:3px solid var(--line); padding:.2rem 0 .2rem 1rem; margin:.55rem 0 .7rem 0;}
.claim.high{border-left-color:var(--high);} .claim.med{border-left-color:var(--med);}
.claim.check{border-left-color:var(--check);} .claim.overall{border-left-color:var(--seal);}
.claim .txt{font-size:.95rem; line-height:1.85;}
.claim.overall .txt{font-family:var(--serif); font-size:1.08rem; color:var(--ink);}
.facts{margin:.45rem 0 0 0; padding:0; list-style:none; font-size:.8rem; color:var(--muted); line-height:1.75;}
.stApp .facts li{font-size:.8rem !important; color:var(--muted); margin:0; padding:0;}
.stApp .claim .txt{font-size:.95rem;}
.facts li::before{content:"事实　"; color:var(--brass); font-size:.72rem;}
.cites{margin-top:.5rem; font-size:.8rem; color:var(--ink-2); line-height:1.8;}
.cites span{display:inline-block; margin-right:.9rem;}
.cites span::before{content:"§ "; color:var(--brass);}
details.more summary{cursor:pointer; font-size:.76rem; color:var(--ink-2); margin:.2rem 0; list-style:none;}
details.more summary::before{content:"▸ "; color:var(--brass);}
details.more[open] summary::before{content:"▾ ";}
.label-h{font-size:.7rem; letter-spacing:.18em; color:var(--brass); font-weight:600; margin:.2rem 0 .3rem 0;}

@media (max-width: 760px){
  .hero{padding:1.3rem 1.2rem;} .hero h1{font-size:1.6rem;}
  .steps{flex-wrap:wrap;} .step{flex:1 1 45%;}
  .step .t small{display:none;}
  .hero .eyebrow::before{display:none;}
}
/* 窗口较窄（含侧边栏展开）时收起输入页右侧说明，表单占满宽度 */
@media (max-width: 1200px){
  [data-testid="stHorizontalBlock"]:has(.how) > [data-testid="stColumn"]:has(.how){display:none !important;}
  [data-testid="stHorizontalBlock"]:has(.how) > [data-testid="stColumn"]{width:100% !important; flex:1 1 100% !important;}
}
</style>
"""

STEPS = [("填写商标与商品", "INPUT", "step-input"), ("确认商品项", "GOODS", "step-goods"),
         ("确认候选", "CANDIDATES", "step-candidates"), ("风险报告", "REPORT", "step-report")]


def css() -> str:
    return _css()


# 网页报告的系统水印：与 Word 报告同一造型（印章标识 + 系统名），斜向、固定在报告页背后
_WATERMARK_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="760" height="520" viewBox="0 0 760 520">'
    '<g transform="rotate(-28 380 260)" fill="none" stroke="#0f1c2e" stroke-opacity=".07">'
    '<rect x="70" y="200" width="120" height="120" rx="18" stroke-width="8"/>'
    '<rect x="95" y="228" width="44" height="44" rx="4" stroke-width="6"/>'
    '<rect x="121" y="251" width="44" height="44" rx="4" fill="#0f1c2e" fill-opacity=".07" stroke="none"/>'
    '<text x="215" y="278" font-size="54" font-weight="700" fill="#0f1c2e" fill-opacity=".07" stroke="none" '
    'font-family="Songti SC, Noto Serif SC, Source Han Serif SC, SimSun, serif">商标近似评估智能体</text>'
    '<text x="218" y="312" font-size="17" letter-spacing="3" fill="#0f1c2e" fill-opacity=".07" stroke="none" '
    'font-family="Georgia, serif">TRADEMARK SIMILARITY · SCREENING REPORT</text></g></svg>')


def report_watermark() -> str:
    uri = "data:image/svg+xml;base64," + base64.b64encode(_WATERMARK_SVG.encode("utf-8")).decode()
    return (f'<style>[data-testid="stMain"]{{background:url("{uri}") center / 620px auto repeat fixed;}}'
            '.st-key-doc{background:rgba(255,255,255,.86) !important;}</style>')


def brand() -> str:
    uri = asset_uri("logo-mark-light.svg")
    return (f'<div class="brand"><img src="{uri}" alt=""><div><div class="n">商标近似评估智能体</div>'
            '<div class="s">TRADEMARK SIMILARITY</div></div></div>')


def hero(compact: bool = False, facts: list[tuple[str, str, str]] | None = None) -> str:
    """facts: (图标名, 数值, 说明)。"""
    if compact:
        return ('<div class="hero compact"><div class="eyebrow">TRADEMARK SIMILARITY</div>'
                '<h1>商标近似评估智能体</h1></div>')
    chips = "".join(f'<li class="fact">{icon(i)}<b>{esc(v)}</b>{esc(t)}</li>' for i, v, t in (facts or []))
    return ('<div class="hero"><div class="eyebrow">TRADEMARK SIMILARITY · 申请前筛查 · 驳回复审比对</div>'
            '<h1>商标近似评估智能体</h1>'
            '<div class="sub">面向限定类别的中文文字商标。多路召回在先商标，大模型逐组判定近似与注册风险，规则护栏兜底；'
            '每条结论都能追溯到事实和带版本的法律依据。</div>'
            + (f'<ul class="hfacts">{chips}</ul>' if chips else "") + '</div>')


def steps(current: int) -> str:
    out = []
    for i, (name, en, ic) in enumerate(STEPS):
        cls = "done" if i < current else ("now" if i == current else "")
        mark = icon(ic) or ("✓" if i < current else str(i + 1))
        out.append(f'<div class="step {cls}"><span class="n">{mark}</span>'
                   f'<span class="t"><small>{en}</small>{name}</span></div>')
    return f'<div class="steps">{"".join(out)}</div>'


def section(title: str, hint: str = "") -> str:
    return f'<div class="sec"><h2>{esc(title)}</h2><span class="hint">{esc(hint)}</span></div>'


def badge(risk: str, label: str) -> str:
    return f'<span class="badge {RISK_CLASS.get(risk, "low")}">{esc(label)}</span>'


def kpis(items: list[tuple[str, str, str, str]]) -> str:
    """items: (数值, 名称, 补充说明, 样式类)。"""
    cells = "".join(f'<div class="kpi {cls}"><div class="v">{esc(str(v))}</div><div class="k">{esc(k)}</div>'
                    + (f'<div class="s">{esc(s)}</div>' if s else "") + "</div>" for v, k, s, cls in items)
    return f'<div class="kpis">{cells}</div>'


def note(text: str, kind: str = "warn") -> str:
    ic = {"warn": "ic-alert", "err": "ic-alert", "info": "ic-info"}.get(kind, "")
    return f'<div class="note {kind}">{icon(ic)}<div>{text}</div></div>'


def kv(pairs: list[tuple[str, str]]) -> str:
    return '<div class="kv">' + "".join(f"<div><span>{esc(k)}</span>{esc(str(v))}</div>" for k, v in pairs) + "</div>"


def how_it_works(points: list[tuple[str, str]], foot: str) -> str:
    illus = asset_uri("illus-compare.svg")
    img = f'<img class="illus" src="{illus}" alt="">' if illus else ""
    items = "".join(f"<li><b>{esc(t)}</b>　{esc(d)}</li>" for t, d in points)
    return f'<div class="how">{img}<h3>系统怎么做</h3><ol>{items}</ol><div class="foot">{esc(foot)}</div></div>'


def empty(kind: str, text: str) -> str:
    uri = asset_uri({"none": "empty-none.svg", "degraded": "empty-degraded.svg"}.get(kind, ""))
    img = f'<img src="{uri}" alt=""><br>' if uri else ""
    return f'<div class="empty">{img}{esc(text)}</div>'


def doc_head(title: str, meta: str) -> str:
    return f'<div class="doc-head"><div class="k">SCREENING REPORT · 商标近似风险筛查</div><h1>{esc(title)}</h1><div class="m">{esc(meta)}</div></div>'


def claim(text: str, facts: list[str], cites: list[str], cls: str, template: bool = False) -> str:
    tpl = ' <span class="tag tpl">模板生成</span>' if template else ""
    lis = [f"<li>{esc(x)}</li>" for x in facts]
    f = ('<ul class="facts">' + "".join(lis[:3]) + "</ul>") if facts else ""
    if len(lis) > 3:                                  # 事实多时折叠，避免整屏都是注册清单
        f += (f'<details class="more"><summary>其余 {len(lis) - 3} 条事实</summary>'
              f'<ul class="facts">{"".join(lis[3:])}</ul></details>')
    c = ('<div class="cites">' + "".join(f"<span>{esc(x)}</span>" for x in cites) + "</div>") if cites else ""
    return f'<div class="claim {cls}"><div class="txt">{esc(text)}{tpl}</div>{f}{c}</div>'
