"""生成 Word 报告用的系统水印图片：app/assets/report-watermark.png。

水印 = 系统印章标识（圆角方印 + 两个交叠的字框，与 ui/assets/logo-mark.svg 同一造型）+ 系统名称，斜向 30°，
墨蓝色、约 11% 不透明度、透明底。图片提交进仓库，导出报告时不依赖服务器上的中文字体。

用法：python scripts/make_watermark.py   （需要 Pillow 和一种中文字体，默认用 macOS 的宋体）
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "app" / "assets" / "report-watermark.png"
FONTS = ["/System/Library/Fonts/Supplemental/Songti.ttc", "/System/Library/Fonts/STHeiti Medium.ttc",
         "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc"]
INK = (15, 28, 46)
ALPHA = 28                      # 0–255，约 11%：明显可见又不妨碍阅读


def font(size: int) -> ImageFont.FreeTypeFont:
    for f in FONTS:
        if Path(f).exists():
            return ImageFont.truetype(f, size)
    sys.exit("找不到中文字体，请在 FONTS 里加一个本机字体路径")


def main() -> int:
    title, sub = "商标近似评估智能体", "TRADEMARK SIMILARITY · SCREENING REPORT"
    f1, f2 = font(132), font(46)
    s, x0, y0 = 300, 60, 110
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    text_w = max(probe.textbbox((0, 0), title, font=f1)[2], probe.textbbox((0, 0), sub, font=f2)[2])
    w, h = x0 + s + 70 + text_w + 60, 520            # 按实际文字宽度定画布，避免截字
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c = INK + (ALPHA,)
    # 印章：圆角方印 + 两个交叠字框（左上描边、右下实心）
    d.rounded_rectangle([x0, y0, x0 + s, y0 + s], radius=46, outline=c, width=20)
    d.rounded_rectangle([x0 + 62, y0 + 70, x0 + 172, y0 + 180], radius=10, outline=c, width=16)
    d.rounded_rectangle([x0 + 128, y0 + 128, x0 + 238, y0 + 238], radius=10, fill=c)
    # 系统名称与英文副题
    d.text((x0 + s + 70, y0 + 40), title, font=f1, fill=c)
    d.text((x0 + s + 76, y0 + 210), sub, font=f2, fill=c)
    img = img.rotate(30, expand=True, resample=Image.BICUBIC)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    img.save(OUT, optimize=True)
    print(f"{OUT.relative_to(ROOT)}  {img.size[0]}×{img.size[1]}  {OUT.stat().st_size // 1024} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
