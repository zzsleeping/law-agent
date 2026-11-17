"""拼音工具：带声调、无声调、模糊音归一三种键，以及音节编辑距离。"""
from __future__ import annotations

import re

from pypinyin import Style, lazy_pinyin


HAN = re.compile(r"[\u4e00-\u9fff]")

try:  # 繁简转换（opencc-python-reimplemented）；没装时跳过，不影响其他比对
    from opencc import OpenCC

    _t2s = OpenCC("t2s").convert
except Exception:  # pragma: no cover
    _t2s = None


def to_simplified(text: str) -> str:
    return _t2s(text) if _t2s and text else (text or "")


def normalize(text: str) -> str:
    """比较用的规范文字：去掉“及图”和空白、统一大小写、繁体转简体；含汉字时只保留汉字（本系统只比对中文文字部分）。"""
    t = re.sub(r"\s+", "", to_simplified((text or "").replace("及图", ""))).casefold()
    han = "".join(HAN.findall(t))
    return han or t


def syllables(text: str, tone: bool = False) -> list[str]:
    style = Style.TONE3 if tone else Style.NORMAL
    return lazy_pinyin(normalize(text), style=style, neutral_tone_with_five=tone)


def fuzzy_syllable(s: str) -> str:
    """模糊音归一：zh/z、ch/c、sh/s、n/l、ang/an、eng/en、ing/in。"""
    if s[:2] in ("zh", "ch", "sh"):
        s = s[0] + s[2:]
    if s.startswith("n") and len(s) > 1:
        s = "l" + s[1:]
    if s[-3:] in ("ang", "eng", "ing"):
        s = s[:-1]
    return s


def keys(text: str) -> dict[str, str]:
    plain = syllables(text)
    return {
        "pinyin_tone": " ".join(syllables(text, tone=True)),
        "pinyin": " ".join(plain),
        "pinyin_fuzzy": " ".join(fuzzy_syllable(s) for s in plain),
    }


def edit_distance(a: list[str], b: list[str]) -> int:
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1]
