"""正式商标库的后端接口。

系统其他部分只通过这里取候选和读记录，不直接接触具体数据库，方便部署时更换存储：
- sqlite：商标开放数据的 SQLite 原库 + 本项目的检索索引（app/tools/open_source.py），当前默认
- none：不用正式库，只用本地记录（测试、离线演示）
以后要换 Elasticsearch、PostgreSQL 等，新增一个实现以下四个方法的类，并在 BACKENDS 里登记即可。
选择方式：环境变量 TM_LIBRARY（sqlite / none）。
"""
from __future__ import annotations

from typing import Protocol

from app.config import settings
from app.state import MarkRecord


class MarkLibrary(Protocol):
    name: str

    def available(self) -> bool:
        """库是否可用（配置齐全、文件存在、服务可连）。"""

    def candidates(self, query: str, classes) -> list[dict]:
        """给定类别内可能相关的商标。每条含 mark_id、text、norm_text、pinyin_tone、pinyin、pinyin_fuzzy、meaning。"""

    def load_records(self, ids: list[str]) -> dict[str, MarkRecord]:
        """按编号读取完整记录（日期、商品、来源）。"""

    def coverage(self) -> dict:
        """数据覆盖范围：count、date、classes。"""

    def find(self, mark_id: str) -> list[str]:
        """按申请号 / 注册号找出该商标在库内各类别的档案编号（“编号/类别”）。"""


class SQLiteOpenLibrary:
    name = "sqlite"

    def available(self) -> bool:
        from app.tools import open_source
        return open_source.available()

    def candidates(self, query: str, classes) -> list[dict]:
        from app.tools import open_source
        return open_source.candidates(query, classes)

    def load_records(self, ids: list[str]) -> dict[str, MarkRecord]:
        from app.tools import open_source
        return open_source.load_records(ids)

    def coverage(self) -> dict:
        from app.tools import open_source
        return open_source.coverage()

    def find(self, mark_id: str) -> list[str]:
        from app.tools import open_source
        return open_source.find(mark_id)


class NoLibrary:
    name = "none"

    def available(self) -> bool:
        return False

    def candidates(self, query: str, classes) -> list[dict]:
        return []

    def load_records(self, ids: list[str]) -> dict[str, MarkRecord]:
        return {}

    def coverage(self) -> dict:
        return {}

    def find(self, mark_id: str) -> list[str]:
        return []


BACKENDS = {"sqlite": SQLiteOpenLibrary, "none": NoLibrary}


def get_library() -> MarkLibrary:
    return BACKENDS.get(settings.library_backend, NoLibrary)()
