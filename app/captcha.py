"""图形验证码：登录、注册、发送邮箱验证码前都要通过，挡住脚本批量尝试。

图片用 Pillow 生成（随机字符、逐字旋转、干扰线与噪点），用 Pillow 自带字体，不依赖系统字体。
答案只在服务端（页面会话）保存哈希，用过一次即作废，有效期 5 分钟。
"""
from __future__ import annotations

import hashlib
import io
import random
import secrets
import time

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"     # 去掉容易混淆的 0/O、1/I/L
TTL = 300


def _hash(answer: str) -> str:
    return hashlib.sha256(answer.strip().upper().encode()).hexdigest()


def new(n: int = 4) -> dict:
    """返回 {"png": 图片字节, "hash": 答案哈希, "at": 生成时间}。不含明文答案。"""
    return new_with_answer(n)[0]


def new_with_answer(n: int = 4) -> tuple[dict, str]:
    """生成验证码并返回明文答案（只给测试用）。"""
    text = "".join(secrets.choice(ALPHABET) for _ in range(n))
    rnd = random.Random(secrets.randbits(64))
    w, h = 40 * n + 20, 56
    img = Image.new("RGB", (w, h), (247, 245, 240))
    d = ImageDraw.Draw(img)
    for _ in range(6):                              # 干扰线
        d.line([(rnd.randint(0, w), rnd.randint(0, h)), (rnd.randint(0, w), rnd.randint(0, h))],
               fill=(rnd.randint(120, 190), rnd.randint(120, 170), rnd.randint(90, 150)), width=rnd.randint(1, 2))
    try:
        font = ImageFont.load_default(size=34)
    except TypeError:                               # 旧版 Pillow 的默认字体不能调大小
        font = ImageFont.load_default()
    for i, ch in enumerate(text):                   # 逐字绘制、旋转
        glyph = Image.new("RGBA", (44, 52), (0, 0, 0, 0))
        ImageDraw.Draw(glyph).text((6, 4), ch, font=font,
                                   fill=(rnd.randint(10, 60), rnd.randint(25, 60), rnd.randint(50, 100)))
        glyph = glyph.rotate(rnd.uniform(-28, 28), resample=Image.BICUBIC, expand=False)
        img.paste(glyph, (10 + i * 40 + rnd.randint(-3, 3), rnd.randint(-2, 6)), glyph)
    for _ in range(140):                            # 噪点
        d.point((rnd.randint(0, w - 1), rnd.randint(0, h - 1)),
                fill=(rnd.randint(60, 200), rnd.randint(60, 200), rnd.randint(60, 200)))
    img = img.filter(ImageFilter.SMOOTH)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return {"png": buf.getvalue(), "hash": _hash(text), "at": time.time()}, text


def check(challenge: dict | None, answer: str) -> bool:
    """校验答案（不区分大小写）。过期或没有验证码返回 False。调用方校验后应立即换一张。"""
    if not challenge or time.time() - challenge["at"] > TTL or not answer:
        return False
    return secrets.compare_digest(challenge["hash"], _hash(answer))
