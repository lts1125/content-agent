FROM python:3.11-slim

ARG REQUIREMENTS_FILE=requirements-docker.txt
ARG PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
ARG USE_CHINA_APT_MIRROR=true

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    GRADIO_SERVER_NAME=0.0.0.0 \
    GRADIO_SERVER_PORT=7861

WORKDIR /app

# 国内服务器默认换阿里云 apt 源；海外服务器可通过 USE_CHINA_APT_MIRROR=false 关闭。
RUN if [ "$USE_CHINA_APT_MIRROR" = "true" ]; then \
        sed -i 's|http://deb.debian.org/debian|http://mirrors.aliyun.com/debian|g' /etc/apt/sources.list.d/debian.sources && \
        sed -i 's|http://deb.debian.org/debian-security|http://mirrors.aliyun.com/debian-security|g' /etc/apt/sources.list.d/debian.sources; \
    fi \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
       build-essential \
       curl \
       git \
       libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-docker.txt ./
RUN pip install --no-cache-dir -i ${PIP_INDEX_URL} -r ${REQUIREMENTS_FILE}

COPY . .

EXPOSE 7861

CMD ["python", "chat_ui.py"]
