"""计费参数（2026-11-19 与用户确认，后续可调）。

定价依据：实测一次完整评估约 23 次大模型调用、输入 3.8 万 / 输出 2.2 万 token，按 deepseek-flash 高峰价
（输入 0.30 美元、输出 1.20 美元 / 百万 token）约 0.28 元；一次法律问答约 0.025 元。按成本的 5 倍定价并取整：
评估 15 积分（1.5 元，约 5.4 倍），问答 1 积分（0.1 元，约 4 倍，略有优惠）。
"""
from __future__ import annotations

CREDIT_CNY = 0.1            # 1 积分 = 0.1 元
COST_QUERY = 15             # 一次评估（申请前筛查或驳回复审比对）
COST_QA = 1                 # 一次法律问答
SIGNUP_GIFT = 20            # 新用户赠送：够完整评估一次，外加几次问答

PACKAGES = [
    {"id": "p100", "name": "体验包", "price": 9.9, "credits": 100, "bonus": 0, "note": "约 6 次评估"},
    {"id": "p330", "name": "标准包", "price": 29.9, "credits": 330, "bonus": 10, "note": "多送 10%，约 22 次评估"},
    {"id": "p1200", "name": "专业包", "price": 99.0, "credits": 1200, "bonus": 20, "note": "多送 20%，约 80 次评估"},
]
VIP = {"id": "vip30", "name": "月度 VIP", "price": 99.0, "days": 30, "queries": 100, "qa_daily_cap": 50,
       "note": "30 天内 100 次评估；法律问答不扣积分（每天最多 50 次）"}

PRODUCTS = {p["id"]: p for p in PACKAGES} | {VIP["id"]: VIP}
