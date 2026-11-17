"""建库入口。

用法：
    python scripts/build_db.py            # 用配置的向量模型（默认本地 bge-small-zh-v1.5）
    python scripts/build_db.py --hash     # 不下载模型，用哈希向量（语义效果差，仅应急）
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.ingest import build  # noqa: E402

if __name__ == "__main__":
    build(embed_backend="hash" if "--hash" in sys.argv else None)
