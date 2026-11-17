"""页面样式与 HTML 小组件。只负责外观，不含业务逻辑。"""
from html import escape as esc

RISK_CLASS = {"high": "high", "medium": "med", "needs_check": "check", "low": "low"}

CSS = """
<style>
:root{
  --ink:#1c2733; --muted:#6c7784; --faint:#9aa3ad; --line:#e3dfd5; --paper:#f6f4ee; --card:#ffffff;
  --accent:#1f4e5f; --accent-soft:#e4eef0;
  --high:#b5372f; --high-bg:#fbeceb; --med:#b0741a; --med-bg:#fbf2df;
  --check:#5a53a3; --check-bg:#eeedf8; --low:#3d7a5a; --low-bg:#e8f3ec;
  --serif:"Songti SC","Noto Serif SC","Source Han Serif SC","STSong",serif;
  --sans:"PingFang SC","Hiragino Sans GB","Microsoft YaHei","Noto Sans SC",system-ui,sans-serif;
  --mono:"SF Mono","JetBrains Mono",Menlo,Consolas,monospace;
}
html, body, .stApp, .stApp p, .stApp li, .stApp label, .stApp input, .stApp button{font-family:var(--sans);}
.stApp{background:var(--paper); color:var(--ink);}
.block-container{max-width:1120px; padding-top:2.2rem; padding-bottom:5rem;}
header[data-testid="stHeader"]{background:transparent;}
#MainMenu, footer, [data-testid="stDecoration"]{display:none;}
h1,h2,h3{font-family:var(--serif) !important; color:var(--ink); letter-spacing:.01em;}
[data-testid="stSidebar"]{background:#efece4; border-right:1px solid var(--line);}
[data-testid="stSidebar"] .block-container{padding-top:1.5rem;}

/* 抬头 */
.hero{margin:0 0 1.4rem 0;}
.hero .eyebrow{font-family:var(--mono); font-size:.72rem; letter-spacing:.18em; color:var(--accent); text-transform:uppercase;}
.hero h1{font-size:2.1rem; line-height:1.25; margin:.35rem 0 .3rem 0; padding:0; font-weight:700;}
.hero .sub{color:var(--muted); font-size:.95rem;}

/* 步骤条 */
.steps{display:flex; gap:0; margin:0 0 1.8rem 0; border:1px solid var(--line); border-radius:12px; background:var(--card); overflow:hidden;}
.step{flex:1; display:flex; align-items:center; gap:.6rem; padding:.75rem 1rem; border-right:1px solid var(--line); color:var(--faint); min-width:0;}
.step:last-child{border-right:none;}
.step .n{flex:none; width:1.55rem; height:1.55rem; border-radius:50%; border:1.5px solid currentColor; display:flex; align-items:center; justify-content:center; font-family:var(--mono); font-size:.78rem;}
.step .t{font-size:.9rem; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;}
.step.done{color:var(--accent);}
.step.done .n{background:var(--accent); border-color:var(--accent); color:#fff;}
.step.now{color:var(--ink); background:var(--accent-soft); font-weight:600;}
.step.now .n{border-color:var(--accent); color:var(--accent);}

/* 卡片容器（st.container(border=True)） */
[data-testid="stVerticalBlockBorderWrapper"]{background:var(--card); border-color:var(--line) !important; border-radius:14px !important; box-shadow:0 1px 2px rgba(28,39,51,.04);}
[data-testid="stForm"]{background:var(--card); border:1px solid var(--line); border-radius:14px; padding:1.4rem 1.5rem 1.2rem; box-shadow:0 1px 2px rgba(28,39,51,.04);}
[data-testid="stExpander"] details{border-color:var(--line); border-radius:10px; background:var(--card);}
.stButton button, .stDownloadButton button, [data-testid="stFormSubmitButton"] button{border-radius:10px; font-weight:600; padding:.5rem 1.2rem;}

/* 小标题 */
.sec{display:flex; align-items:baseline; gap:.7rem; margin:1.6rem 0 .7rem 0;}
.sec h2{font-size:1.25rem; margin:0; padding:0;}
.sec .hint{color:var(--muted); font-size:.85rem;}
.lead{color:var(--muted); font-size:.9rem; margin:-.2rem 0 .9rem 0; line-height:1.65;}

/* 徽标与标签 */
.badge{display:inline-flex; align-items:center; gap:.35rem; padding:.16rem .6rem; border-radius:999px; font-size:.78rem; font-weight:600; white-space:nowrap;}
.badge::before{content:""; width:.42rem; height:.42rem; border-radius:50%; background:currentColor;}
.badge.high{color:var(--high); background:var(--high-bg);} .badge.med{color:var(--med); background:var(--med-bg);}
.badge.check{color:var(--check); background:var(--check-bg);} .badge.low{color:var(--low); background:var(--low-bg);}
.chip{display:inline-block; padding:.1rem .5rem; border:1px solid var(--line); border-radius:6px; font-size:.75rem; color:var(--muted); background:#faf9f5; margin-right:.3rem;}
.tag{display:inline-block; padding:.08rem .45rem; border-radius:5px; font-size:.7rem; color:var(--muted); background:#efece4;}
.tag.warn{color:var(--high); background:var(--high-bg);}
.tag.tpl{color:var(--med); background:var(--med-bg);}
.id{font-family:var(--mono); font-size:.76rem; color:var(--faint);}

/* 概览数字 */
.kpis{display:grid; grid-template-columns:repeat(auto-fit,minmax(130px,1fr)); gap:.7rem; margin:.3rem 0 1.1rem 0;}
.kpi{background:var(--card); border:1px solid var(--line); border-radius:12px; padding:.8rem 1rem; border-top:3px solid var(--line);}
.kpi .v{font-family:var(--serif); font-size:1.9rem; font-weight:700; line-height:1.1;}
.kpi .k{font-size:.8rem; color:var(--muted); margin-top:.2rem;}
.kpi .s{font-family:var(--mono); font-size:.7rem; color:var(--faint); margin-top:.15rem;}
.kpi.high{border-top-color:var(--high);} .kpi.high .v{color:var(--high);}
.kpi.med{border-top-color:var(--med);} .kpi.med .v{color:var(--med);}
.kpi.check{border-top-color:var(--check);} .kpi.check .v{color:var(--check);}
.kpi.low{border-top-color:var(--low);} .kpi.low .v{color:var(--low);}
.kpi.accent{border-top-color:var(--accent);}

/* 候选卡片 */
.cand-head{display:flex; flex-wrap:wrap; align-items:center; gap:.55rem; margin-bottom:.35rem;}
.cand-head .mark{font-family:var(--serif); font-size:1.3rem; font-weight:700;}
.cand-ev{font-size:.9rem; line-height:1.65; margin:.25rem 0;}
.cand-meta{font-size:.8rem; color:var(--muted); line-height:1.7;}
.cand-meta b{color:var(--ink); font-weight:600;}
.rank{font-family:var(--mono); font-size:.8rem; color:var(--faint); padding-top:.45rem; text-align:right;}

/* 信息条 */
.note{border-radius:10px; padding:.65rem .9rem; font-size:.86rem; line-height:1.6; margin:.2rem 0 .8rem 0; border:1px solid;}
.note.warn{background:var(--med-bg); border-color:#ecd9ae; color:#7a5310;}
.note.err{background:var(--high-bg); border-color:#eec3bf; color:#8c2a24;}
.note.info{background:var(--accent-soft); border-color:#c9dde1; color:#1f4e5f;}
.kv{display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:.2rem 1.4rem; font-size:.88rem; margin:.2rem 0;}
.kv div span{color:var(--muted); margin-right:.5rem;}

/* 结论卡片 */
.claim{border-left:3px solid var(--line); padding:.15rem 0 .15rem .9rem; margin:.5rem 0 .6rem 0;}
.claim.high{border-left-color:var(--high);} .claim.med{border-left-color:var(--med);}
.claim.check{border-left-color:var(--check);} .claim.overall{border-left-color:var(--accent);}
.claim .txt{font-size:.95rem; line-height:1.8;}
.claim.overall .txt{font-family:var(--serif); font-size:1.05rem;}
.facts{margin:.4rem 0 0 0; padding:0; list-style:none; font-size:.8rem; color:var(--muted); line-height:1.7;}
.stApp .facts li{font-size:.8rem !important; color:var(--muted); margin:0; padding:0;}
.stApp .claim .txt{font-size:.95rem;}
.facts li::before{content:"事实　"; color:var(--faint); font-size:.72rem;}
.cites{margin-top:.45rem; font-size:.8rem; color:var(--accent); line-height:1.8;}
.cites span{display:inline-block; margin-right:.9rem;}
.cites span::before{content:"§ "; color:var(--faint);}
.side-h{font-family:var(--mono); font-size:.7rem; letter-spacing:.14em; color:var(--muted); text-transform:uppercase; margin:1.1rem 0 .4rem 0;}
.side-row{display:flex; justify-content:space-between; font-size:.86rem; padding:.28rem 0; border-bottom:1px dashed var(--line);}
.side-row b{font-family:var(--mono); font-weight:600;}
.side-cap{font-size:.76rem; color:var(--muted); line-height:1.6; margin-top:.4rem;}
</style>
"""

STEPS = ["填写商标与商品", "确认商品项", "确认候选", "风险报告"]


def hero() -> str:
    return ('<div class="hero"><div class="eyebrow">Trademark Similarity · 申请前筛查</div>'
            '<h1>商标近似评估智能体</h1>'
            '<div class="sub">限定类别内的中文文字商标。风险等级由规则表给出，大模型只负责解释和措辞，每条结论都能追溯到事实和带版本的依据。</div></div>')


def steps(current: int) -> str:
    out = []
    for i, name in enumerate(STEPS):
        cls = "done" if i < current else ("now" if i == current else "")
        mark = "✓" if i < current else str(i + 1)
        out.append(f'<div class="step {cls}"><span class="n">{mark}</span><span class="t">{name}</span></div>')
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
    return f'<div class="note {kind}">{text}</div>'


def kv(pairs: list[tuple[str, str]]) -> str:
    return '<div class="kv">' + "".join(f"<div><span>{esc(k)}</span>{esc(str(v))}</div>" for k, v in pairs) + "</div>"


def claim(text: str, facts: list[str], cites: list[str], cls: str, template: bool = False) -> str:
    tpl = ' <span class="tag tpl">模板生成</span>' if template else ""
    f = ('<ul class="facts">' + "".join(f"<li>{esc(x)}</li>" for x in facts) + "</ul>") if facts else ""
    c = ('<div class="cites">' + "".join(f"<span>{esc(x)}</span>" for x in cites) + "</div>") if cites else ""
    return f'<div class="claim {cls}"><div class="txt">{esc(text)}{tpl}</div>{f}{c}</div>'
