# syntax=docker/dockerfile:1
ARG BASE_BUILDER=nvidia/cuda:12.4.1-devel-ubuntu22.04
ARG BASE_RUNNER=nvidia/cuda:12.4.1-runtime-ubuntu22.04

# -----------------------------------------------------------------------------
# Этап 1: Сборка laya из форка https://github.com/andrei-tolstov/ggmlc
# -----------------------------------------------------------------------------
FROM ${BASE_BUILDER} AS builder

ARG REPO_URL=https://github.com/andrei-tolstov/ggmlc.git
ARG REPO_BRANCH=main
ARG CUDA_ARCHITECTURES="61;70;75;80;86;89"

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    cmake \
    ninja-build \
    build-essential \
    ca-certificates \
    curl \
    python3 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src
RUN git clone --depth 1 --branch ${REPO_BRANCH} ${REPO_URL} /src

WORKDIR /src/build
RUN cmake .. -G Ninja \
    -DCMAKE_BUILD_TYPE=Release \
    -DGGMLC_ENABLE_CUDA=ON \
    -DCMAKE_CUDA_ARCHITECTURES="${CUDA_ARCHITECTURES}" \
    -DCMAKE_CUDA_RUNTIME_LIBRARY=Static \
    -DGGMLC_BUILD_EXAMPLES=ON

RUN ninja laya ggmlc-run

# -----------------------------------------------------------------------------
# Этап 2: Финальный образ выполнения (автоматический fallback на CPU при отсутствии GPU)
# -----------------------------------------------------------------------------
FROM ${BASE_RUNNER} AS runner

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    libgomp1 \
    python3 \
    python3-pip \
    && rm -rf /var/lib/apt/lists/* \
    && pip3 install --no-cache-dir "mcp>=1.2" httpx starlette uvicorn


# Копируем скомпилированные бинарники
COPY --from=builder /src/build/examples/laya/laya /usr/local/bin/laya
COPY --from=builder /src/build/runtime/ggmlc-run /usr/local/bin/ggmlc-run

# Копируем сервер MCP и скрипт запуска
COPY mcp_server.py /app/mcp_server.py
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

WORKDIR /app
EXPOSE 8080 8787

ENTRYPOINT ["/app/entrypoint.sh"]

