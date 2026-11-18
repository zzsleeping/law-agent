"""规则护栏：大模型给出的风险等级必须满足的硬性约束（2026-11-18 与用户确认：大模型定，规则护栏）。

大模型是判定者；以下情形由事实决定，模型不能推翻，违反时按护栏修正并记录：
1. 对方不构成在先（申请日晚于我方，或已核实失效且不适用隔离期）→ 低风险
2. 商品明确不类似 → 低风险（未考虑驰名商标跨类保护）
3. 在先状态待核实（同日申请、期满记录、未见公告等）→ 待核实，不能折算为低风险，也不能凭推测定为高
4. 商品关系待核实，且模型认为标识近似 → 待核实
5. 文字完全相同、商品相同或类似、对方构成在先 → 高风险
其余情形以模型的判断为准。
"""
from __future__ import annotations

from app.rules.prior_status import GRADED, NEEDS_CHECK

RELATED = ("same", "similar", "linked")


def apply(llm_risk: str, llm_mark_sim: str, prior: str, goods_rel: str, exact: bool) -> tuple[str, str]:
    """返回 (最终风险, 护栏说明)。说明为空表示模型判断未被修正。"""
    def fix(target: str, why: str) -> tuple[str, str]:
        return (target, "" if target == llm_risk else f"护栏修正：{why}，由“{llm_risk}”改为“{target}”")

    if prior in ("not_prior", "invalid"):
        return fix("low", "对方不构成在先障碍")
    if goods_rel == "dissimilar":
        return fix("low", "商品不类似")
    if prior in NEEDS_CHECK:
        return fix("needs_check", "在先状态待核实")
    if goods_rel == "pending" and llm_mark_sim in ("high", "medium"):
        return fix("needs_check", "商品关系待核实")
    if exact and goods_rel in RELATED and prior in GRADED:
        return fix("high", "文字完全相同、商品相同或类似且构成在先")
    return llm_risk, ""
