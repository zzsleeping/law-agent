"""创建管理员账号（管理后台：查看用户、调整积分、生成兑换码）。

用法：python scripts/create_admin.py 用户名
密码交互输入（不回显、不进命令历史）；也可以用环境变量 ADMIN_PASSWORD 传入，便于部署脚本。
管理员不赠送积分；需要试用评估时可在管理后台给自己调整积分。
"""
from __future__ import annotations

import getpass
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import accounts  # noqa: E402
from app.accounts import AccountError  # noqa: E402


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 1
    pw = os.environ.get("ADMIN_PASSWORD") or getpass.getpass("管理员密码（至少 8 位，含字母和数字）：")
    if not os.environ.get("ADMIN_PASSWORD") and pw != getpass.getpass("再次输入："):
        print("两次输入不一致")
        return 1
    try:
        u = accounts.register(sys.argv[1], pw, role="admin")
    except AccountError as e:
        print(f"创建失败：{e}")
        return 1
    print(f"已创建管理员 {u['username']}（ID {u['id']}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
