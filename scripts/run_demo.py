"""命令行跑演示集（eval/demo.yaml），不经过页面。商品项采用系统建议，候选全部保留。

用法：python scripts/run_demo.py [demo-1 ...]
"""
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402

from app.graph import build_graph  # noqa: E402
from app.rules.risk_table import RISK_LABEL  # noqa: E402
from app.runner import run_pre_filing  # noqa: E402


def main() -> None:
    cases = yaml.safe_load((ROOT / "eval" / "demo.yaml").read_text(encoding="utf-8"))
    want = set(sys.argv[1:])
    graph = build_graph()
    for c in cases:
        if want and c["id"] not in want:
            continue
        ev = date.fromisoformat(str(c["eval_date"])) if c.get("eval_date") else date.today()
        v = run_pre_filing(c["query"], goods_desc=c["goods"], query_meaning=c.get("meaning", ""),
                           eval_date=ev, graph=graph, thread_id=c["id"])
        rep = v["report"]
        print(f"\n=== {c['id']}  商标“{c['query']}”  商品：{'、'.join(g.name for g in v['goods'])}  "
              f"评估日 {ev}  {rep['law_version']} ===")
        print(f"考察点：{c['shows']}")
        for m in v["display_order"]:
            a = next(a for a in v["assessments"] if a.mark_id == m)
            print(f"  {RISK_LABEL[a.risk]:<4} {a.text:<6} {m}  [{'/'.join(a.channels)}]  "
                  f"商品:{a.goods_rel}  在先:{a.prior}")
        t = v["timings"]
        print(f"  校验错误 {len(v['citation_errors'])} 条；重写 {v.get('retry_count', 0)} 次；"
              f"降级 {'是' if v.get('degraded') else '否'}；规则阶段 {t.get('rule_stage')} 秒；"
              f"解释 {t.get('explain')} 秒；结论 {t.get('compose')} 秒")
        print(f"  总结论：{rep['overall']['conclusion']}")
        print(f"  报告：{v['report_path']}")


if __name__ == "__main__":
    main()
