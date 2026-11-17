"""向量模型封装。

bge：本地 bge-small-zh-v1.5（fastembed / onnx，首次使用会下载约 100 MB）。
hash：字符 n-gram 哈希向量，不需要下载；只用于单元测试和模型下载失败时应急，语义效果差。
建库和查询必须用同一种后端，后端名记录在数据库 meta 表中。
"""
from __future__ import annotations

import hashlib
import math
import os
from functools import lru_cache

from app.config import settings


class HashEmbedder:
    name = "hash"
    dim = 256

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for t in texts:
            v = [0.0] * self.dim
            grams = list(t) + [t[i:i + 2] for i in range(len(t) - 1)]
            for g in grams:
                h = int(hashlib.md5(g.encode("utf-8")).hexdigest(), 16)
                v[h % self.dim] += 1.0 if len(g) == 1 else 1.5
            n = math.sqrt(sum(x * x for x in v)) or 1.0
            out.append([x / n for x in v])
        return out


class BgeEmbedder:
    name = "bge"

    def __init__(self) -> None:
        from fastembed import TextEmbedding

        cache = os.getenv("FASTEMBED_CACHE_PATH", str(settings.data_dir / "models"))
        self._model = TextEmbedding(model_name=settings.embed_model, cache_dir=cache)

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [v.tolist() for v in self._model.embed(texts)]


@lru_cache(maxsize=4)
def get_embedder(backend: str | None = None):
    backend = backend or settings.embed_backend
    if backend == "hash":
        return HashEmbedder()
    return BgeEmbedder()
