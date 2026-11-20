"""创建特权测试账号：VIP 长期有效、评估和问答不限额度（不扣积分），不需要邮箱验证。

用法：python scripts/create_privileged.py 用户名
密码交互输入，或用环境变量 TEST_PASSWORD 传入。特权账号不做密码强度检查——
只用于本机演示和测试；正式部署前请删除或改成强密码（管理后台可看到角色为 tester 的账号）。
"""
from __future__ import annotations

import getpass
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import accounts  # noqa: E402
from app.accounts import AccountError  # noqa: E402

VIP_FOREVER = "2099-12-31T23:59:59"


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 1
    pw = os.environ.get("TEST_PASSWORD") or getpass.getpass("密码：")
    try:
        u = accounts.register(sys.argv[1], pw, role="tester", unlimited=True, vip_until=VIP_FOREVER, enforce_rule=False)
    except AccountError as e:
        print(f"创建失败：{e}")
        return 1
    print(f"已创建特权测试账号 {u['username']}（ID {u['id']}）：VIP 至 {u['vip_until'][:10]}，评估与问答不限额度")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
