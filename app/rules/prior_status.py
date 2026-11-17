"""在先状态判断：比较双方日期，再按状态文字或公告日期推断对方能否构成在先障碍。

日期只用于风险筛查，法律状态须单独核实。分档（2026-11-18 与用户确认）：

参与评级（等级由标识和商品关系决定）：
- registered  有注册公告、记录专用期未满：“有注册记录，按日期推定在期内”
- prelim      仅见初审公告：“初审公告，可能构成在先障碍”（第三十条涵盖已注册和初步审定的商标）
- earlier_app 对方日期早于我方、申请 18 个月内、库内未见公告：“可能在先申请，审查状态待核实”
- valid       状态文字明确为已注册 / 初审公告的记录（决定书等来源）

待核实（不折算为低风险）：
- same_day     同日申请：“同日申请，使用先后待核实”（第三十一条）
- pending_long 申请超过 18 个月仍未见公告：“有申请记录，库内未见初审或注册公告，审查结果待核实”
- expired      记录专用期已满：“期满记录，续展或注销待核实”（有六个月宽展期，失效日期不明）
- lapsed_recent 已核实失效但可能仍在一年隔离期内（按适用法律版本，见下）
- unknown      其他缺数据情形

不构成在先：not_prior（对方日期晚于我方）、invalid（已核实失效且不适用隔离期，或从未取得注册）

一年隔离期按适用法律版本：
- 2019 年修正《商标法》第五十条：被撤销、宣告无效或期满不再续展的，自撤销、宣告无效或注销之日起一年内；
  因连续三年不使用被撤销的除外（指南 18.3）。
- 2026 年修订《商标法》第四十九条：只针对注册人主动申请注销，自注销公告之日起一年内；
  已核实的撤销、无效或期满未续展不适用。只有“已注销”字样、原因或日期不清的，保留待核实。
18 个月是本项目的筛查阈值，不是法定期限。跨新旧法案件的适用版本还要看过渡规则，这里按 law 参数判断。
"""
from __future__ import annotations

from datetime import date

from app.state import MarkRecord, Prior

REGISTERED = {"已注册", "初审公告", "注册公告"}
PENDING = {"申请中", "实质审查", "等待实质审查", "驳回复审中"}
NEVER_REGISTERED = {"已驳回", "申请驳回", "不予受理", "已撤回"}
LAPSED = {"已无效", "已撤销", "已注销", "期满未续展", "无效"}
PENDING_MONTHS = 18

GRADED = {"valid", "registered", "prelim", "earlier_app"}
NEEDS_CHECK = {"same_day", "pending_long", "expired", "lapsed_recent", "unknown"}

LABEL = {
    "registered": "有注册记录，按日期推定在期内",
    "prelim": "初审公告，可能构成在先障碍",
    "valid": "有效的在先注册或初审公告商标",
    "earlier_app": "可能在先申请，审查状态待核实",
    "same_day": "同日申请，使用先后待核实",
    "pending_long": "有申请记录，库内未见初审或注册公告，审查结果待核实",
    "expired": "期满记录，续展或注销待核实",
    "lapsed_recent": "已失效，可能仍在一年隔离期内（待核实）",
    "unknown": "在先状态未知（待核实）",
    "not_prior": "申请日晚于我方，不构成在先",
    "invalid": "已失效或未取得注册，不构成在先障碍",
}
STATUS_NOTE = "日期仅用于风险筛查，法律状态须另行核实"


def _months_before(d: date, months: int) -> date:
    y, m = divmod(d.month - 1 - months, 12)
    year, month = d.year + y, m + 1
    day = min(d.day, [31, 29 if year % 4 == 0 and (year % 100 or year % 400 == 0) else 28,
                      31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1])
    return date(year, month, day)


def _lapsed(rec: MarkRecord, eval_date: date, law: str, snap: str) -> tuple[Prior, str]:
    reason = rec.invalid_reason or ""
    shown = f"状态为“{rec.status}”（{reason or '原因不明'}）"
    if law == "TML2026":
        voluntary = "申请注销" in reason or "主动注销" in reason
        if voluntary:
            if rec.invalid_date is None:
                return "lapsed_recent", f"{shown}，注销公告日期缺失，无法判断是否仍在一年隔离期内（2026 年修订版关于主动注销后一年隔离的规定）{snap}"
            if (eval_date - rec.invalid_date).days <= 365:
                return "lapsed_recent", (f"{shown}，{rec.invalid_date} 注销公告，至评估日未满一年，"
                                         f"处于一年隔离期（2026 年修订版关于主动注销后一年隔离的规定）{snap}")
            return "invalid", f"{shown}，{rec.invalid_date} 注销公告，已满一年{snap}"
        if reason and rec.invalid_date and rec.status != "已注销":
            return "invalid", f"{shown}，{rec.invalid_date} 生效，不适用 2026 年修订版关于主动注销后一年隔离的规定{snap}"
        return "lapsed_recent", f"{shown}，原因或日期不清，待核实是否属于主动注销{snap}"
    if "三年不使用" in reason:
        return "invalid", f"因连续三年不使用被撤销，不适用一年隔离期（指南 18.3）{snap}"
    if rec.invalid_date is None:
        return "lapsed_recent", f"{shown}，失效日期缺失，无法判断是否已满一年（2019 年修正版一年隔离规定）{snap}"
    if (eval_date - rec.invalid_date).days <= 365:
        return "lapsed_recent", (f"{shown}，{rec.invalid_date} 失效，至评估日未满一年，"
                                 f"可能仍被引证（2019 年修正版一年隔离规定）{snap}")
    return "invalid", f"{shown}，{rec.invalid_date} 失效，已满一年{snap}"


def prior_status(rec: MarkRecord, our_date: date | None, eval_date: date,
                 law: str = "TML2019") -> tuple[Prior, str]:
    """返回 (在先状态, 推断依据)。law 为适用的法律版本：TML2019 或 TML2026。"""
    snap = f"（数据截至 {rec.snapshot_date}）" if rec.snapshot_date else ""
    if rec.status in NEVER_REGISTERED:
        return "invalid", f"状态为“{rec.status}”，未取得注册{snap}"
    if rec.status in LAPSED:
        return _lapsed(rec, eval_date, law, snap)

    their = rec.priority_date or rec.app_date
    kind = "优先权日" if rec.priority_date else "申请日"
    if their is None:
        return "unknown", f"对方申请日缺失{snap}"
    if our_date is None:
        return "unknown", "我方申请日未填写，无法比较先后"
    if their > our_date:
        return "not_prior", f"对方{kind} {their} 晚于我方申请日 {our_date}"
    if their == our_date:
        return "same_day", f"对方{kind} {their} 与我方申请日相同，按同日申请规则以使用先后确定，需核实使用证据"
    earlier = f"对方{kind} {their} 早于我方申请日 {our_date}"

    # 状态文字明确的记录（决定书、仿真数据）
    if rec.status in REGISTERED:
        return "valid", f"状态为“{rec.status}”，{earlier}{snap}"
    if rec.status in PENDING:
        return "earlier_app", f"状态为“{rec.status}”，{earlier}，审查状态待核实{snap}"
    if rec.status:
        return "unknown", f"无法识别的状态“{rec.status}”，{earlier}{snap}"

    # 只有公告日期的记录（商标数据开放）：按日期推定
    if rec.reg_date:
        if rec.term_end is None:
            return "unknown", f"有注册日 {rec.reg_date}，但无专用期记录，{earlier}。{STATUS_NOTE}{snap}"
        if rec.term_end >= eval_date:
            return "registered", (f"注册日 {rec.reg_date}，专用期至 {rec.term_end}，按日期推定在期内；{earlier}。"
                                  f"{STATUS_NOTE}{snap}")
        return "expired", (f"注册日 {rec.reg_date}，记录专用期至 {rec.term_end} 已满，续展或注销待核实"
                           f"（届满后有六个月宽展期）；{earlier}{snap}")
    if rec.prelim_date:
        return "prelim", f"{rec.prelim_date} 初审公告，未见注册公告；{earlier}。{STATUS_NOTE}{snap}"
    if rec.app_date and rec.app_date >= _months_before(eval_date, PENDING_MONTHS):
        return "earlier_app", (f"申请日 {rec.app_date}，申请不足 {PENDING_MONTHS} 个月，库内未见初审或注册公告；"
                               f"{earlier}，审查状态待核实{snap}")
    if rec.app_date:
        return "pending_long", (f"申请日 {rec.app_date}，已超过 {PENDING_MONTHS} 个月，库内未见初审或注册公告，"
                                f"审查结果待核实；{earlier}{snap}")
    return "unknown", f"无申请或公告日期{snap}"
