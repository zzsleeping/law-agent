# 未经实际构建测试（开发机没有 Docker），首次部署时请先在服务器上构建验证。
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    FASTEMBED_CACHE_PATH=/app/data/models

WORKDIR /app

# 国内服务器可在构建时指定镜像：docker build --build-arg PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple .
ARG PIP_INDEX_URL=https://pypi.org/simple
COPY requirements.txt .
RUN pip install -i "$PIP_INDEX_URL" -r requirements.txt

COPY app ./app
COPY ui ./ui
COPY prompts ./prompts
COPY scripts ./scripts
COPY eval ./eval
COPY .streamlit ./.streamlit
# data/ 中的小文件（法条、区分表、字形数据、仿真与决定书记录）随镜像发布；
# 大文件（tm.db、chroma、open_index.sqlite、模型）通过卷挂载，见 docker-compose.yml
COPY data ./data

EXPOSE 8501
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')" || exit 1

CMD ["streamlit", "run", "ui/streamlit_app.py", "--server.port=8501", "--server.address=0.0.0.0", \
     "--server.headless=true", "--browser.gatherUsageStats=false"]
