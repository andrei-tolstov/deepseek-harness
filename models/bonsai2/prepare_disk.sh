#!/usr/bin/env bash
# ==============================================================================
# Скрипт подготовки диска на временной ВМ Yandex Cloud (Debian 12)
# для последующего подключения к целевой GPU ВМ с NVIDIA Tesla V100 32GB
#
# Готовит систему, Docker CE, NVIDIA Container Toolkit, собирает
# образ PrismML-Eng/llama.cpp (CUDA sm_70), скачивает
# Ternary-Bonsai-2-27B-Uncensored-Heretic-PQ2_0.gguf и mmproj-BF16.gguf,
# настраивает автозапуск на контекст 262 144 токенов с эталонным FP16 KV-кэшем.
# ==============================================================================

set -euo pipefail

export DEBIAN_FRONTEND=noninteractive

echo "======================================================================"
echo " [1/7] Обновление операционной системы (Debian 12)..."
echo "======================================================================"
if [ -f /etc/apt/sources.list ]; then
    sed -i 's/main$/main contrib non-free non-free-firmware/g' /etc/apt/sources.list
fi
apt-get update -y
apt-get -y -o Dpkg::Options::="--force-confdef" -o Dpkg::Options::="--force-confold" upgrade

echo "======================================================================"
echo " [2/7] Установка системных утилит, Docker CE и NVIDIA Container Toolkit..."
echo "======================================================================"
apt-get install -y --no-install-recommends \
    apt-transport-https ca-certificates curl gnupg lsb-release wget jq aria2 openssh-client autossh \
    git cmake ninja-build build-essential libcurl4-openssl-dev ufw

# Установка официального Docker CE для Debian
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  tee /etc/apt/sources.list.d/docker.list > /dev/null

apt-get update -y
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
systemctl enable --now docker

# Настройка NVIDIA Container Toolkit (для распознавания V100 после переноса диска)
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | gpg --batch --yes --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
    sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
    tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
apt-get update -y
apt-get install -y nvidia-container-toolkit
nvidia-ctk runtime configure --runtime=docker || true
systemctl restart docker

echo "======================================================================"
echo " [3/7] Системный тюнинг под Tesla V100 (Swap и Memlock)..."
echo "======================================================================"
if [ ! -f /swapfile ]; then
    fallocate -l 4G /swapfile 2>/dev/null || dd if=/dev/zero of=/swapfile bs=1M count=4096
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile || true
    echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

# Memlock unlimited
grep -q '\* soft memlock unlimited' /etc/security/limits.conf || echo "* soft memlock unlimited" >> /etc/security/limits.conf
grep -q '\* hard memlock unlimited' /etc/security/limits.conf || echo "* hard memlock unlimited" >> /etc/security/limits.conf

# ------------------------------------------------------------------------------
# Сетевая безопасность: установка UFW и блокировка всех входящих портов кроме 22.
# Порт инференса 8082 слушает только 127.0.0.1 и пробрасывается через SSH-туннель.
# ------------------------------------------------------------------------------
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp comment "SSH access only"
ufw --force enable

echo "======================================================================"
echo " [4/7] Подготовка директории и сборка Docker-образа PrismML llama.cpp..."
echo "======================================================================"
MODEL_DIR="/root/model/bonsai2"
mkdir -p "$MODEL_DIR"
cd "$MODEL_DIR"

cat <<'EOF' > "${MODEL_DIR}/Dockerfile"
FROM nvidia/cuda:12.4.1-devel-ubuntu22.04 AS builder

ARG CUDA_ARCHITECTURES="70"
ENV DEBIAN_FRONTEND=noninteractive
ENV LIBRARY_PATH="/usr/local/cuda/lib64/stubs:${LIBRARY_PATH}"
ENV LD_LIBRARY_PATH="/usr/local/cuda/lib64/stubs:${LD_LIBRARY_PATH}"

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    cmake \
    ninja-build \
    build-essential \
    ca-certificates \
    libcurl4-openssl-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src
RUN git clone --depth 1 -b prism https://github.com/PrismML-Eng/llama.cpp.git llama.cpp

WORKDIR /src/llama.cpp
RUN cmake -B build -G Ninja \
    -DGGML_CUDA=ON \
    -DCMAKE_CUDA_ARCHITECTURES="${CUDA_ARCHITECTURES}" \
    -DGGML_CUDA_FA_ALL=ON \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_EXE_LINKER_FLAGS="-L/usr/local/cuda/lib64/stubs -lcuda" \
    -DCMAKE_SHARED_LINKER_FLAGS="-L/usr/local/cuda/lib64/stubs -lcuda" \
    && cmake --build build --target llama-server -j$(nproc)

FROM nvidia/cuda:12.4.1-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    libgomp1 \
    libcurl4 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=builder /src/llama.cpp/build/bin/ /app/

ENV LD_LIBRARY_PATH="/app:${LD_LIBRARY_PATH}"
ENV PATH="/app:${PATH}"
EXPOSE 8080

ENTRYPOINT ["/app/llama-server"]
EOF

echo "Сборка Docker-образа prismml-llama:v100..."
docker build -t prismml-llama:v100 --build-arg CUDA_ARCHITECTURES="70" .

echo "======================================================================"
echo " [5/7] Загрузка модели Ternary-Bonsai-2-27B и проектора mmproj..."
echo "======================================================================"
BASE_URL="https://huggingface.co/OS-Software/Ternary-Bonsai-2-27B-Uncensored-Heretic-GGUF/resolve/main"
MODEL_FILE="Ternary-Bonsai-2-27B-Uncensored-Heretic-PQ2_0.gguf"
MMPROJ_FILE="mmproj-BF16.gguf"

download_file_helper() {
    local target="$1"
    if [ -f "$target" ] && [ -s "$target" ] && [ ! -f "${target}.aria2" ]; then
        echo "[OK] Файл $target уже скачан, пропускаем."
    else
        echo "Скачивание $target через aria2c..."
        aria2c \
            --file-allocation=none \
            --continue=true \
            --max-connection-per-server=16 \
            --split=16 \
            --min-split-size=10M \
            --summary-interval=15 \
            --out="$target" \
            "${BASE_URL}/${target}" || {
                curl -L -C - --progress-bar -o "$target" "${BASE_URL}/${target}"
            }
    fi
}

download_file_helper "$MODEL_FILE"
download_file_helper "$MMPROJ_FILE"

echo "======================================================================"
echo " [6/7] Конфигурация Docker Compose под Tesla V100 32GB..."
echo "======================================================================"
cat <<'EOF' > "${MODEL_DIR}/docker-compose.yml"
services:
  bonsai2-llama:
    image: prismml-llama:v100
    container_name: bonsai2-llama-server
    restart: unless-stopped
    ipc: host
    ports:
      - "127.0.0.1:8082:8080"
    environment:
      - LD_LIBRARY_PATH=/app
      - TZ=Europe/Moscow
      - BONSAI_MODEL_FILE=Ternary-Bonsai-2-27B-Uncensored-Heretic-PQ2_0.gguf
      - BONSAI_MMPROJ_FILE=mmproj-BF16.gguf
      - BONSAI_NO_MMPROJ_OFFLOAD=true
      - BONSAI_CPU_THREADS=16
      - BONSAI_API_KEY=${BONSAI_API_KEY:-}
      - BONSAI_ALIAS=bonsai2-27b,bonsai2,default
      - BONSAI_CTX_SIZE=262144
      - BONSAI_BATCH_SIZE=2048
      - BONSAI_UBATCH_SIZE=512
      - BONSAI_CACHE_K=f16
      - BONSAI_CACHE_V=f16
      - BONSAI_TEMP=1.0
      - BONSAI_TOP_P=0.95
      - BONSAI_TOP_K=20
      - BONSAI_MIN_P=0.05
      - BONSAI_REASONING_EFFORT=medium
    volumes:
      - /root/model/bonsai2:/models:ro
    entrypoint:
      - /bin/sh
      - -c
      - |
        set -e
        SERVER_BIN=$$(which /app/llama-server || which llama-server || find / -name llama-server -executable | head -n 1)
        API_KEY_ARG=""
        [ -n "$$BONSAI_API_KEY" ] && API_KEY_ARG="--api-key $$BONSAI_API_KEY"

        MMPROJ_ARG=""
        if [ -f "/models/mmproj-BF16.gguf" ]; then
          echo "Подключение mmproj (выгрузка в RAM): /models/mmproj-BF16.gguf"
          MMPROJ_ARG="--mmproj /models/mmproj-BF16.gguf --no-mmproj-offload --threads 16"
        fi

        exec $$SERVER_BIN --host 0.0.0.0 --port 8080 \
          -m /models/Ternary-Bonsai-2-27B-Uncensored-Heretic-PQ2_0.gguf \
          $$MMPROJ_ARG \
          -c 262144 \
          --flash-attn on \
          -ctk f16 -ctv f16 \
          -b 2048 -ub 512 \
          -ngl 999 \
          --load-mode auto \
          --slots 1 \
          --jinja \
          --reasoning on --reasoning-effort medium \
          --temp 1.0 --top-p 0.95 --top-k 20 --min-p 0.05 \
          --alias bonsai2-27b,bonsai2,default $$API_KEY_ARG
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
    healthcheck:
      test: ["CMD-SHELL", "curl -f http://localhost:8080/health || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s
EOF

echo "======================================================================"
echo " [7/7] Настройка службы systemd (автозапуск при переносе диска)..."
echo "======================================================================"
cat <<EOF > /etc/systemd/system/bonsai-inference.service
[Unit]
Description=Ternary-Bonsai-2 PrismML Llama.cpp GPU Inference (Tesla V100 32GB)
After=network.target docker.service
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=${MODEL_DIR}
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable bonsai-inference.service

cp /tmp/tunnel_to_gpu.sh ${MODEL_DIR}/ 2>/dev/null || true
cp /tmp/setup_gpu_node.sh ${MODEL_DIR}/ 2>/dev/null || true

echo "======================================================================"
echo " ПОДГОТОВКА ДИСКА ПОД TERNARY-BONSAI-2 УСПЕШНО ЗАВЕРШЕНА!"
echo " Содержимое ${MODEL_DIR}:"
echo "======================================================================"
ls -lh "${MODEL_DIR}"
df -h /
sync
