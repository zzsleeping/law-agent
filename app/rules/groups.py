"""名称组的公共函数：组名、代表件。同名的多件注册归为一组，解释和结论按组生成。"""
from __future__ import annotations

from app.state import Assessment

RISK_ORDER = {"high": 0, "medium": 1, "needs_check": 2, "low": 3}
SIM_ORDER = {"high": 0, "medium": 1, "low": 2}


def group_of(a: Assessment) -> str:
    return a.group or a.mark_id


def by_group(items: list[Assessment]) -> dict[str, list[Assessment]]:
    out: dict[str, list[Assessment]] = {}
    for a in items:
        out.setdefault(group_of(a), []).append(a)
    return out


def representative(items: list[Assessment]) -> Assessment:
    """组内风险最高、标识最相似的一件，代表该组写解释和结论。"""
    return sorted(items, key=lambda a: (RISK_ORDER[a.risk], SIM_ORDER[a.mark_sim], a.mark_id))[0]


def group_risk(items: list[Assessment]) -> str:
    return representative(items).risk
