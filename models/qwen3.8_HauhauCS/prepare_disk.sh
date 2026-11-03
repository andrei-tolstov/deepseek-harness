#!/usr/bin/env bash
# ==============================================================================
# Скрипт подготовки диска на временной ВМ Yandex Cloud (Debian 12)
# для последующего подключения к целевой GPU ВМ с NVIDIA Tesla V100 32GB
#
# Готовит систему, Docker CE, NVIDIA Container Toolkit, скачивает
# Huihui-Qwen3.8-27B-abliterated-Q5_K_L.gguf и mmproj-model-bf16.gguf (для CPU RAM)
# и настраивает автозапуск llama.cpp на контекст 262 144 токенов с Q8_0 KV-кэшем
# согласно рекомендациям report.md.
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
    apt-transport-https ca-certificates curl gnupg lsb-release wget jq aria2 ufw openssh-client autossh

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
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
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

grep -q '\* soft memlock unlimited' /etc/security/limits.conf || echo "* soft memlock unlimited" >> /etc/security/limits.conf
grep -q '\* hard memlock unlimited' /etc/security/limits.conf || echo "* hard memlock unlimited" >> /etc/security/limits.conf

# Настройка файрвола UFW
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp comment "SSH access"
ufw --force enable

echo "======================================================================"
echo " [4/7] Предварительная загрузка Docker-образа llama.cpp (CUDA)..."
echo "======================================================================"
docker pull ghcr.io/ggml-org/llama.cpp:server-cuda

echo "======================================================================"
echo " [5/7] Загрузка модели HauhauCS Qwen3.8-27B Q5_K_P, FastMTP и mmproj..."
echo "======================================================================"
MODEL_DIR="/root/model/qwen3.8"
mkdir -p "$MODEL_DIR"
cd "$MODEL_DIR"

BASE_URL="https://huggingface.co/HauhauCS/Qwen3.8-27B-Uncensored-HauhauCS-Aggressive-MTP-GGUF/resolve/main"
MODEL_FILE="Qwen3.8-27B-Uncensored-HauhauCS-Aggressive-Q5_K_P.gguf"
FASTMTP_FILE="Qwen3.8-27B-Uncensored-HauhauCS-Aggressive-FastMTP-32K.gguf"
MMPROJ_FILE="mmproj-Qwen3.8-27B-Uncensored-HauhauCS-Aggressive-BF16.gguf"

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
download_file_helper "$FASTMTP_FILE"
download_file_helper "$MMPROJ_FILE"

echo "======================================================================"
echo " [6/7] Конфигурация Docker Compose под Tesla V100 32GB..."
echo "======================================================================"
cat <<'EOF' > "${MODEL_DIR}/docker-compose.yml"
services:
  qwen38-llama:
    image: ghcr.io/ggml-org/llama.cpp:server-cuda
    container_name: qwen38-llama-server
    restart: unless-stopped
    ipc: host
    ports:
      - "127.0.0.1:8080:8080"
    environment:
      - TZ=Europe/Moscow
      - QWEN_MODEL_FILE=Qwen3.8-27B-Uncensored-HauhauCS-Aggressive-Q5_K_P.gguf
      - QWEN_MMPROJ_FILE=mmproj-Qwen3.8-27B-Uncensored-HauhauCS-Aggressive-BF16.gguf
      - QWEN_FASTMTP_FILE=Qwen3.8-27B-Uncensored-HauhauCS-Aggressive-FastMTP-32K.gguf
      - QWEN_NO_MMPROJ_OFFLOAD=true
      - QWEN_CPU_THREADS=8
      - QWEN_API_KEY=${QWEN_API_KEY:-}
      - QWEN_ALIAS=qwen3.8-27b,qwen3.8,default
      - QWEN_CTX_SIZE=262144
      - QWEN_BATCH_SIZE=2048
      - QWEN_UBATCH_SIZE=512
    volumes:
      - /root/model/qwen3.8:/models:ro
    entrypoint:
      - /bin/sh
      - -c
      - |
        set -e
        SERVER_BIN=$$(which llama-server || which /app/llama-server || find / -name llama-server -executable | head -n 1)
        API_KEY_ARG=""
        [ -n "$$QWEN_API_KEY" ] && API_KEY_ARG="--api-key $$QWEN_API_KEY"

        MMPROJ_ARG=""
        if [ -f "/models/mmproj-Qwen3.8-27B-Uncensored-HauhauCS-Aggressive-BF16.gguf" ]; then
          echo "Подключение mmproj (выгрузка в CPU RAM): mmproj-BF16"
          MMPROJ_ARG="--mmproj /models/mmproj-Qwen3.8-27B-Uncensored-HauhauCS-Aggressive-BF16.gguf --no-mmproj-offload --threads 8"
        fi

        MTP_ARG="--spec-type draft-mtp"
        if [ -f "/models/Qwen3.8-27B-Uncensored-HauhauCS-Aggressive-FastMTP-32K.gguf" ]; then
          echo "Подключение HauhauCS FastMTP 32K сайдкара"
          MTP_ARG="--spec-draft-model /models/Qwen3.8-27B-Uncensored-HauhauCS-Aggressive-FastMTP-32K.gguf --spec-draft-ngl all --spec-type draft-mtp --spec-draft-n-max 3 --spec-draft-p-min 0"
        fi

        exec $$SERVER_BIN --host 0.0.0.0 --port 8080 \
          -m /models/Qwen3.8-27B-Uncensored-HauhauCS-Aggressive-Q5_K_P.gguf \
          $$MMPROJ_ARG \
          $$MTP_ARG \
          -c 262144 \
          --flash-attn on \
          -ctk q8_0 -ctv q8_0 \
          -b 2048 -ub 512 \
          -ngl 999 \
          --jinja \
          --reasoning on --reasoning-effort xhigh --reasoning-format deepseek --reasoning-preserve \
          --temp 1.0 --top-p 0.95 --top-k 20 --min-p 0.0 --repeat-penalty 1.0 --presence-penalty 0.0 \
          --alias qwen3.8-27b,qwen3.8,default $$API_KEY_ARG
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
cat <<EOF > /etc/systemd/system/qwen-inference.service
[Unit]
Description=Huihui-Qwen3.8 Llama.cpp GPU Inference (Tesla V100 32GB)
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
systemctl enable qwen-inference.service

cp /tmp/tunnel_to_gpu.sh ${MODEL_DIR}/ 2>/dev/null || true
cp /tmp/setup_gpu_node.sh ${MODEL_DIR}/ 2>/dev/null || true

echo "======================================================================"
echo " ПОДГОТОВКА ДИСКА ПОД TESLA V100 УСПЕШНО ЗАВЕРШЕНА!"
echo " Содержимое ${MODEL_DIR}:"
echo "======================================================================"
ls -lh "${MODEL_DIR}"
df -h /
sync
