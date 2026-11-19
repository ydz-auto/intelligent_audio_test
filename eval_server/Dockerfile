FROM python:3.11-slim

ARG APT_MIRROR=mirrors.tuna.tsinghua.edu.cn
ENV PYTHONUNBUFFERED=1 \
    PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN for f in /etc/apt/sources.list /etc/apt/sources.list.d/*; do \
        [ -f "$f" ] && sed -i "s|deb.debian.org|${APT_MIRROR}|g" "$f"; \
    done; \
    apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8888

CMD ["python", "app.py", "--host", "0.0.0.0", "--port", "8888"]
