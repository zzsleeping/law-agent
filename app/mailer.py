"""发送邮件（注册验证码）。SMTP 参数在 .env 里配置（见 .env.example）：

SMTP_HOST、SMTP_PORT（默认 465）、SMTP_USER、SMTP_PASSWORD（多为邮箱的“授权码”）、SMTP_FROM（默认同 SMTP_USER）、
SMTP_SSL（默认 1：465 端口直接 SSL；设为 0 时用 587 端口 STARTTLS）。

本机调试可设 TM_EMAIL_DEV=1：不发邮件，验证码直接显示在注册窗口里。正式部署不要打开。
"""
from __future__ import annotations

import os
import smtplib
import ssl
from email.mime.text import MIMEText
from email.utils import formataddr


def configured() -> bool:
    return bool(os.getenv("SMTP_HOST") and os.getenv("SMTP_USER") and os.getenv("SMTP_PASSWORD"))


def dev_mode() -> bool:
    return os.getenv("TM_EMAIL_DEV") == "1"


def send(to: str, subject: str, body: str) -> None:
    host, user, pw = os.environ["SMTP_HOST"], os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"]
    port = int(os.getenv("SMTP_PORT", "465"))
    sender = os.getenv("SMTP_FROM", user)
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"], msg["From"], msg["To"] = subject, formataddr(("商标近似评估智能体", sender)), to
    ctx = ssl.create_default_context()
    if os.getenv("SMTP_SSL", "1") == "1":
        with smtplib.SMTP_SSL(host, port, context=ctx, timeout=15) as s:
            s.login(user, pw)
            s.sendmail(sender, [to], msg.as_string())
    else:
        with smtplib.SMTP(host, port, timeout=15) as s:
            s.starttls(context=ctx)
            s.login(user, pw)
            s.sendmail(sender, [to], msg.as_string())
