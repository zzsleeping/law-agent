# 部署说明（准备中）

目标：把系统部署到一台 Linux 服务器。本文记录已做的准备和尚未解决的问题。
Dockerfile 和 docker-compose.yml 已写好，但开发机没有 Docker，**还没有实际构建测试过**。

## 已做的准备

| 事项 | 做法 |
| --- | --- |
| 配置 | 全部走环境变量（`.env.example` 列出全部变量），代码里没有本机路径 |
| 依赖 | `requirements.txt` 固定到开发机上的版本（Python 3.12） |
| 商标库可替换 | `app/library.py` 定义后端接口；现在是 SQLite，换 Elasticsearch / PostgreSQL 时新增一个实现即可 |
| 大文件不进镜像 | 开放数据原库、检索索引、向量模型、运行时小库都通过卷挂载 |
| 不依赖大库的测试 | `tests/test_open_source.py` 自建小样本库验证开放数据流程，服务器上可直接 `pytest` |

## 需要上传到服务器的数据

| 文件 | 大小 | 来源 |
| --- | --- | --- |
| `cnipa_29_30_32_43.sqlite3` | 约 10 GB | Codex 用官方压缩包整理的原库 |
| `open_index.sqlite` | 约 4.7 GB | 本项目 `scripts/build_open_index.py` 生成，也可以在服务器上重建（约 6 分钟） |

两个文件放到 `deploy/open/`，用 `rsync -P` 上传（可断点续传）。官方原始压缩包约 30 GB，建议单独存档，不必上传。

## 部署步骤（待验证）

```bash
cp .env.example .env              # 填 LLM_API_KEY、LLM_MODEL
mkdir -p deploy/open deploy/runtime deploy/models deploy/outputs
# 上传两个数据文件到 deploy/open/
docker compose build              # 国内服务器加 --build-arg PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple
docker compose run --rm app python scripts/build_db.py   # 建本地小库；首次下载向量模型（可设 HF_ENDPOINT 镜像）
docker compose up -d
docker compose run --rm app pytest -q
```

## 服务器配置建议

- 磁盘：至少 40 GB 可用（数据约 15 GB，镜像与模型约 3 GB，留余量）
- 内存：4 GB 起，8 GB 更稳妥（SQLite 只读查询内存占用小，主要是向量模型和 Streamlit）
- 网络：需要能访问大模型接口；首次建库要下载向量模型

## 尚未解决

1. **原库的构建流程只能在 Mac 上跑**：Codex 的 `build_catalog.py` 用 macOS 的 `xattr` 读取压缩包的下载来源，用本机 conda 的库编译 C++。
   服务器上直接使用上传的原库即可；以后要在服务器上更新增量数据，需要改写成跨平台的导入脚本。
2. **任务状态只存在内存里**：LangGraph 用的是 `MemorySaver`，重启或多进程部署会丢失进行中的任务，需换成 SQLite 或 PostgreSQL 检查点。
3. **页面没有登录**：Streamlit 默认任何能访问端口的人都能用，公网部署前要加访问控制（反向代理加密码，或只在内网开放）。
4. **单进程**：Streamlit 适合演示；多人同时使用或要给其他程序调用，需补方案中的 FastAPI 接口。
5. **数据更新**：开放数据按月增量发布，目前没有自动更新流程。
6. **冷启动慢**：索引（约 4.8 GB）和原库（约 10 GB）刚放到机器上、还没进系统缓存时，前几次查询要从磁盘随机读，
   开发机上实测第一次规则阶段要 30 秒到两分多钟，缓存热了以后约 1 秒。部署后应先预热（例如启动时顺序读一遍索引文件，
   或用几个常见商标跑一次查询），并尽量用 SSD。
