FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    curl \
    ca-certificates \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    libxrender1 \
    libxext6 \
    libsm6 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements-server.txt /app/requirements-server.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r /app/requirements-server.txt

COPY server/ /app/server/
COPY hy3d_v2/ /app/hy3d_v2/
COPY tools/ /app/tools/
COPY docker/scripts/docker-entrypoint-api.sh /usr/local/bin/docker-entrypoint-api.sh

RUN mkdir -p /app/server_workspace /app/server_exports /app/model_cache \
    && chmod +x /usr/local/bin/docker-entrypoint-api.sh

EXPOSE 8000

ENTRYPOINT ["docker-entrypoint-api.sh"]
CMD ["uvicorn", "server.hy3d_api.main:app", "--host", "0.0.0.0", "--port", "8000"]

