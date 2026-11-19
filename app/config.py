"""集中配置：路径、可调参数、大模型与向量模型设置。

路径可用环境变量覆盖（测试时指向临时目录）。
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except Exception:  # dotenv 未安装时不影响运行
    pass

ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Settings:
    data_dir: Path = field(default_factory=lambda: Path(os.getenv("TM_DATA_DIR", ROOT / "data")))
    db_path: Path = field(default_factory=lambda: Path(os.getenv("TM_DB_PATH", ROOT / "data" / "tm.db")))
    chroma_dir: Path = field(default_factory=lambda: Path(os.getenv("TM_CHROMA_DIR", ROOT / "data" / "chroma")))
    # 正式商标库后端（app/library.py）：sqlite（开放数据 SQLite + 检索索引）/ none（只用本地记录）
    library_backend: str = field(default_factory=lambda: os.getenv("TM_LIBRARY", "sqlite"))
    # 商标开放数据（只读原库，放在项目外）与本项目生成的检索索引
    open_db_path: str = field(default_factory=lambda: os.getenv("TM_OPEN_DB", ""))
    open_index_path: Path = field(default_factory=lambda: Path(os.getenv("TM_OPEN_INDEX", ROOT / "data" / "open_index.sqlite")))
    # 测试专用：额外导入的仿真记录（产品中为空）
    fixture_marks: Path | None = None
    output_dir: Path = field(default_factory=lambda: Path(os.getenv("TM_OUTPUT_DIR", ROOT / "outputs")))
    prompts_dir: Path = ROOT / "prompts"

    # 大模型（OpenAI 兼容接口）
    llm_base_url: str = field(default_factory=lambda: os.getenv("LLM_BASE_URL", "https://api.deepseek.com"))
    llm_api_key: str = field(default_factory=lambda: os.getenv("LLM_API_KEY", ""))
    llm_model: str = field(default_factory=lambda: os.getenv("LLM_MODEL", ""))
    llm_timeout: float = field(default_factory=lambda: float(os.getenv("LLM_TIMEOUT", "20")))
    llm_retries: int = 1
    # 每次评估最多为多少个名称组调用大模型（解释、风险结论各自计数）；其余用代码模板，控制时延和费用
    llm_max_groups: int = field(default_factory=lambda: int(os.getenv("LLM_MAX_GROUPS", "10")))
    # 报告里的参考判例是否包含冻结测试集一侧的文书。开发和评测期间保持 false（技术侧不看冻结集内容），部署时改为 true
    cases_include_frozen: bool = field(default_factory=lambda: os.getenv("CASES_INCLUDE_FROZEN", "false").lower() == "true")

    # 向量模型：bge（本地 bge-small-zh-v1.5）或 hash（无需下载，仅测试/应急）
    embed_backend: str = field(default_factory=lambda: os.getenv("EMBED_BACKEND", "bge"))
    embed_model: str = "BAAI/bge-small-zh-v1.5"

    # 第五节的待调参数（只在调参集上调）
    glyph_sub_cost: float = 0.3      # 形近替换代价
    glyph_threshold: float = 1.0     # 加权编辑距离上限（三字及以上才允许一个普通替换）
    meaning_threshold: float = 0.62  # 释义余弦相似度下限
    contains_major_ratio: float = 0.4  # 完整包含且被包含部分占较长商标的比例达到此值，判高
    shared_part_ratio: float = 0.4     # 共有部分至少占较短商标的比例，才作为“共用显著部分”召回
    rrf_k: int = 60
    channel_weights: dict = field(default_factory=lambda: {
        "exact": 1.0, "contains": 1.0, "glyph": 1.0, "pinyin": 1.0,
        "transpose": 1.0, "redup": 1.0, "pinyin_fuzzy": 0.5, "meaning": 0.5,
    })
    top_k_per_channel: int = 5000    # 每路召回在归组前保留的件数；1000 时大家族的“共用部分”命中被提前截掉（调参集 24 件官方引证因此丢失），排序交给 merge
    # 同一标识相似等级内的名称组排序打分（eval/rank_bench.py 在调参集上调）：
    # 共有文字占我方的比例、占对方的比例、该名称在检索类别内的注册件数（品牌规模，对数，50 件封顶）。
    # 2026-11-19 调参集：不加形状分 Recall@10 29.2%；只用件数 42.3%；三项合用 43.8%，权重在较大范围内结果不变
    rank_weights: dict = field(default_factory=lambda: {"cover_q": 1.0, "cover_t": 0.5, "size": 2.0})
    judge_with_cases: bool = False   # 判定提示词是否附同一比对情形的官方判例（以 eval/run_judge_eval.py 对照结果决定）
    top_n_assess: int = 15           # 完全同名之外送评的名称组数（每组带出该名称在检索类别内的全部注册）
    max_rewrites: int = 2


settings = Settings()
