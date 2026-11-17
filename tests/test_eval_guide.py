"""回归测试：指南官方例子上的表现不能退步（数字来自 eval/run_eval.py）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "eval"))
import run_eval  # noqa: E402


def test_guide_examples_not_worse():
    rows = run_eval.judge(run_eval.load("guide"))
    s = run_eval.summary(rows)
    assert s["召回率"] == 1.0                    # 12 对官方近似例子全部召回
    assert s["高风险命中率"] >= 0.9
    by = {(r["query"], r["cited"]): r for r in rows}
    assert by[("好歌", "好哥")]["level"] != "high"          # 仅读音相同不判高（5.5.1.4 反例）
    assert by[("亚美航空", "美亚医疗")]["level"] is None
    assert by[("球王", "球")]["level"] is None
