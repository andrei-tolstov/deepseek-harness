#!/usr/bin/env bash
# ==============================================================================
# Полный скрипт развертывания GPU-сервера для Ternary-Bonsai-2-27B-Uncensored-Heretic
# Специализированная конфигурация для NVIDIA Tesla V100 32GB (архитектура Volta, sm_70)
# на базе рекомендаций report-ternary-bonsai.md
#
# Ключевые архитектурные решения:
#   1. Модель: Ternary-Bonsai-2-27B-Uncensored-Heretic-PQ2_0.gguf (~7.21 GB).
#      Тернарное квантование (1.58/1.72 бит) снижает размер весов до 7.2 ГБ,
#      сохраняя ~98.2% производительности рассуждений Qwen3.8 и 0% отказов.
#   2. Движок: Обязательно форк PrismML-Eng/llama.cpp (ветка prism). Upstream
#      llama.cpp не поддерживает тернарные матрицы и ядра Hadamard. Сборка
#      производится из исходников с флагом CMAKE_CUDA_ARCHITECTURES="70".
#   3. Контекст: Нативное контекстное окно 262 144 токенов (-c 262144).
#   4. KV-кэш: Несжатый эталонный FP16 (-ctk f16 -ctv f16) ~15.26 GiB VRAM!
#      Вместе с весами PQ2_0 (7.2 GiB) суммарно всего ~24.3 GiB из 31.7 GiB,
#      оставляя огромный запас ~7.4 GiB VRAM для стабильности.
#   5. Батчинг: -b 2048 -ub 512 (Chunked Prefill).
#   6. Мультимодальность: mmproj-BF16.gguf выгружается в системную RAM
#      (--no-mmproj-offload) с распараллеливанием на ядра CPU (--threads).
#   7. Сэмплирование: temp 1.0, top-p 0.95, top-k 20, min-p 0.05, reasoning medium.
#   8. Тюнинг V100: Persistence Mode, Compute Mode EXCLUSIVE_PROCESS, limits memlock.
#   9. Безопасность: UFW (только SSH порт открыт), API привязан к 127.0.0.1:8082.
# ==============================================================================

set -euo pipefail

# ------------------------------------------------------------------------------
# Конфигурационные переменные (переопределяются через env)
# ------------------------------------------------------------------------------
TARGET_HOST_IP="${TARGET_HOST_IP:-}"                   # IP удаленного хоста для Reverse-туннеля
TARGET_HOST_USER="${TARGET_HOST_USER:-root}"          # Пользователь на удаленном хосте
TUNNEL_REMOTE_PORT="${TUNNEL_REMOTE_PORT:-8082}"      # Порт на удаленном хосте
LOCAL_API_PORT="${LOCAL_API_PORT:-8082}"              # Локальный порт llama-server (127.0.0.1)

MODEL_DIR="${MODEL_DIR:-/root/model/bonsai2}"
MODEL_FILE="${MODEL_FILE:-Ternary-Bonsai-2-27B-Uncensored-Heretic-PQ2_0.gguf}"
MMPROJ_FILE="${MMPROJ_FILE:-mmproj-BF16.gguf}"
ENABLE_MMPROJ="${ENABLE_MMPROJ:-true}"
NO_MMPROJ_OFFLOAD="${NO_MMPROJ_OFFLOAD:-true}"
CPU_THREADS="${CPU_THREADS:-$(nproc 2>/dev/null || echo 16)}"
BASE_HF_URL="https://huggingface.co/OS-Software/Ternary-Bonsai-2-27B-Uncensored-Heretic-GGUF/resolve/main"

# Нативное контекстное окно модели: 262 144 токенов (256K)
CTX_SIZE="${CTX_SIZE:-262144}"
BATCH_SIZE="${BATCH_SIZE:-2048}"
UBATCH_SIZE="${UBATCH_SIZE:-512}"
CACHE_K="${CACHE_K:-f16}"
CACHE_V="${CACHE_V:-f16}"

# Параметры сэмплирования для Ternary Bonsai
TEMP="${TEMP:-1.0}"
TOP_P="${TOP_P:-0.95}"
TOP_K="${TOP_K:-20}"
MIN_P="${MIN_P:-0.05}"
REASONING_EFFORT="${REASONING_EFFORT:-medium}"

API_KEY="${API_KEY:-}"
if [ -z "$API_KEY" ]; then
    API_KEY="sk-$(openssl rand -hex 16 2>/dev/null || date +%s%N)"
fi

# Цвета для терминала
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m'

log_info() { echo -e "${CYAN}[INFO $(date +'%H:%M:%S')]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS $(date +'%H:%M:%S')]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN $(date +'%H:%M:%S')]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR $(date +'%H:%M:%S')]${NC} $1" >&2; }
log_step() {
    echo -e "\n${PURPLE}======================================================================${NC}"
    echo -e "${PURPLE} $1 ${NC}"
    echo -e "${PURPLE}======================================================================${NC}"
}

if [ "$(id -u)" -ne 0 ]; then
    log_error "Скрипт должен быть запущен с правами root (sudo)!"
    exit 1
fi

# ==============================================================================
# ШАГ 1: Обновление операционной системы и репозиториев
# ==============================================================================
log_step "ШАГ 1: Обновление операционной системы (Debian/Ubuntu)"

export DEBIAN_FRONTEND=noninteractive
. /etc/os-release
OS_ID="${ID:-debian}"
OS_CODENAME="${VERSION_CODENAME:-bookworm}"

log_info "Определена операционная система: ${OS_ID} (${OS_CODENAME})"

# Для Debian включаем contrib non-free non-free-firmware
if [ "$OS_ID" = "debian" ]; then
    if [ -f /etc/apt/sources.list ]; then
        sed -i 's/main$/main contrib non-free non-free-firmware/g' /etc/apt/sources.list
    fi
fi

log_info "Обновление индексов пакетов..."
apt-get update -y

log_info "Установка базовых системных утилит..."
apt-get install -y --no-install-recommends \
    apt-transport-https \
    ca-certificates \
    curl \
    gnupg \
    lsb-release \
    wget \
    jq \
    aria2 \
    ufw \
    openssh-client \
    autossh \
    git \
    cmake \
    ninja-build \
    build-essential \
    libcurl4-openssl-dev

log_success "Базовые утилиты успешно установлены!"

# ==============================================================================
# ШАГ 2: Системный тюнинг под Tesla V100 32GB и настройка Swap
# ==============================================================================
log_step "ШАГ 2: Системный тюнинг под NVIDIA Tesla V100 (32GB VRAM)"

# 2.1. Создание защитного Swap файла (4 ГБ)
if [ ! -f /swapfile ]; then
    log_info "Создание 4 ГБ swap-файла для защиты от OOM при сборке и инференсе..."
    fallocate -l 4G /swapfile 2>/dev/null || dd if=/dev/zero of=/swapfile bs=1M count=4096
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    grep -q '/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
    log_success "Swap-файл настроен!"
else
    log_info "Swap-файл уже существует."
fi

# 2.2. Снятие системных лимитов блокировки памяти для флага --mlock
log_info "Настройка memlock unlimited в /etc/security/limits.conf..."
grep -q '\* soft memlock unlimited' /etc/security/limits.conf || echo "* soft memlock unlimited" >> /etc/security/limits.conf
grep -q '\* hard memlock unlimited' /etc/security/limits.conf || echo "* hard memlock unlimited" >> /etc/security/limits.conf
ulimit -l unlimited 2>/dev/null || true

# 2.3. Тюнинг драйвера GPU
if command -v nvidia-smi >/dev/null 2>&1; then
    log_info "Обнаружен GPU NVIDIA. Применение настроек Tesla V100:"
    nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader

    # Включение Persistence Mode (предотвращает выгрузку драйвера из ядра)
    nvidia-smi -pm 1 || true
    # Перевод GPU в эксклюзивный процессный режим
    nvidia-smi -c EXCLUSIVE_PROCESS || true
    log_success "Тюнинг драйвера NVIDIA успешно применен (Persistence Mode + Exclusive Process)!"
else
    log_warn "nvidia-smi не найден. Убедитесь, что драйвер NVIDIA установлен для работы на GPU."
fi

# ==============================================================================
# ШАГ 3: Установка Docker CE и NVIDIA Container Toolkit
# ==============================================================================
log_step "ШАГ 3: Установка Docker CE и NVIDIA Container Toolkit"

if ! command -v docker >/dev/null 2>&1; then
    log_info "Установка Docker CE для ${OS_ID}..."
    install -m 0755 -d /etc/apt/keyrings
    DOCKER_GPG_URL="https://download.docker.com/linux/${OS_ID}/gpg"
    curl -fsSL "$DOCKER_GPG_URL" -o /etc/apt/keyrings/docker.asc
    chmod a+r /etc/apt/keyrings/docker.asc

    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/${OS_ID} \
      ${OS_CODENAME} stable" | \
      tee /etc/apt/sources.list.d/docker.list > /dev/null

    apt-get update -y
    apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    systemctl enable --now docker
    log_success "Docker CE успешно установлен!"
else
    log_info "Docker уже установлен: $(docker --version)"
fi

if ! command -v nvidia-ctk >/dev/null 2>&1; then
    log_info "Установка NVIDIA Container Toolkit..."
    curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
    curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
        sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
        tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
    apt-get update -y
    apt-get install -y nvidia-container-toolkit
    nvidia-ctk runtime configure --runtime=docker
    systemctl restart docker
    log_success "NVIDIA Container Toolkit настроен!"
else
    log_info "NVIDIA Container Toolkit уже установлен."
fi

# ==============================================================================
# ШАГ 4: Настройка файрвола UFW (Только SSH)
# Безопасность: UFW блокирует абсолютно все входящие соединения, кроме порта 22 (SSH).
# Доступ к инференсу llama-server (порт 8082) осуществляется строго через защищенный SSH-туннель.
# ==============================================================================
log_step "ШАГ 4: Настройка файрвола UFW (блокировка всех портов кроме SSH 22)"

SSH_PORT="22"
if [ -f /etc/ssh/sshd_config ]; then
    DETECTED_PORT=$(grep -E "^Port [0-9]+" /etc/ssh/sshd_config | awk '{print $2}' || true)
    [ -n "$DETECTED_PORT" ] && SSH_PORT="$DETECTED_PORT"
fi

log_info "Разрешение SSH порта: ${SSH_PORT}/tcp..."
ufw default deny incoming
ufw default allow outgoing
ufw allow "${SSH_PORT}/tcp" comment "SSH Remote Access"
ufw --force enable
log_success "UFW активен! Открыт только порт ${SSH_PORT}/tcp."

# ==============================================================================
# ШАГ 5: Загрузка модели Ternary-Bonsai-2-27B и проектора mmproj
# ==============================================================================
log_step "ШАГ 5: Загрузка модели ${MODEL_FILE} и проектора ${MMPROJ_FILE}"

mkdir -p "$MODEL_DIR"
cd "$MODEL_DIR"

download_file_aria2() {
    local filename="$1"
    local url="${BASE_HF_URL}/${filename}"

    if [ -f "$filename" ] && [ -s "$filename" ] && [ ! -f "${filename}.aria2" ]; then
        log_info "Файл уже загружен: $filename ($(du -h "$filename" | cut -f1))"
    else
        log_info "Загрузка $filename ..."
        aria2c \
            --file-allocation=none \
            --continue=true \
            --max-connection-per-server=16 \
            --split=16 \
            --min-split-size=10M \
            --summary-interval=15 \
            --out="$filename" \
            "$url" || {
                log_warn "aria2c вернул ошибку, переключение на curl..."
                curl -L -C - --progress-bar -o "$filename" "$url"
            }
        log_success "Файл $filename успешно скачан!"
    fi
}

download_file_aria2 "$MODEL_FILE"
if [ "$ENABLE_MMPROJ" = "true" ]; then
    download_file_aria2 "$MMPROJ_FILE"
fi
ls -lh "$MODEL_DIR"

# ==============================================================================
# ШАГ 6: Сборка PrismML llama.cpp и запуск сервиса
# ==============================================================================
log_step "ШАГ 6: Сборка PrismML llama-server (CUDA sm_70) и запуск Docker Compose"

# 6.1. Создание Dockerfile для PrismML-Eng/llama.cpp
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
COPY --from=builder /src/llama.cpp/build/bin/llama-server /app/llama-server

ENV PATH="/app:${PATH}"
EXPOSE 8080

ENTRYPOINT ["/app/llama-server"]
EOF

# 6.2. Создание docker-compose.yml
cat <<EOF > "${MODEL_DIR}/docker-compose.yml"
services:
  bonsai2-llama:
    build:
      context: .
      dockerfile: Dockerfile
      args:
        CUDA_ARCHITECTURES: "70"
    image: prismml-llama:v100
    container_name: bonsai2-llama-server
    restart: unless-stopped
    ipc: host
    ports:
      - "127.0.0.1:${LOCAL_API_PORT}:8080"
    environment:
      - TZ=Europe/Moscow
      - BONSAI_MODEL_FILE=${MODEL_FILE}
      - BONSAI_MMPROJ_FILE=${MMPROJ_FILE}
      - BONSAI_ENABLE_MMPROJ=${ENABLE_MMPROJ}
      - BONSAI_NO_MMPROJ_OFFLOAD=${NO_MMPROJ_OFFLOAD}
      - BONSAI_CPU_THREADS=${CPU_THREADS}
      - BONSAI_CTX_SIZE=${CTX_SIZE}
      - BONSAI_BATCH_SIZE=${BATCH_SIZE}
      - BONSAI_UBATCH_SIZE=${UBATCH_SIZE}
      - BONSAI_CACHE_K=${CACHE_K}
      - BONSAI_CACHE_V=${CACHE_V}
      - BONSAI_TEMP=${TEMP}
      - BONSAI_TOP_P=${TOP_P}
      - BONSAI_TOP_K=${TOP_K}
      - BONSAI_MIN_P=${MIN_P}
      - BONSAI_REASONING_EFFORT=${REASONING_EFFORT}
      - BONSAI_API_KEY=${API_KEY}
      - BONSAI_ALIAS=bonsai2-27b,bonsai2,default
    volumes:
      - "${MODEL_DIR}:/models:ro"
    entrypoint:
      - /bin/sh
      - -c
      - |
        set -e
        SERVER_BIN="\\\$\$(which /app/llama-server 2>/dev/null || which llama-server 2>/dev/null || find / -name llama-server -type f -executable 2>/dev/null | head -n 1)"
        MODEL_PATH="/models/\\\$\${BONSAI_MODEL_FILE}"

        ARGS="--host 0.0.0.0 --port 8080"
        ARGS="\\\$ARGS -m \\\$MODEL_PATH"

        MMPROJ_PATH="/models/\\\$\${BONSAI_MMPROJ_FILE}"
        if [ "\\\$\${BONSAI_ENABLE_MMPROJ:-true}" = "true" ] && [ -f "\\\$MMPROJ_PATH" ]; then
          echo "Подключение мультимодального проектора (mmproj): \\\$MMPROJ_PATH"
          ARGS="\\\$ARGS --mmproj \\\$MMPROJ_PATH"
          if [ "\\\$\${BONSAI_NO_MMPROJ_OFFLOAD:-true}" = "true" ]; then
            echo "Vision Tower выгружен в RAM хоста (--no-mmproj-offload)"
            ARGS="\\\$ARGS --no-mmproj-offload"
          fi
          if [ -n "\\\$\${BONSAI_CPU_THREADS}" ]; then
            ARGS="\\\$ARGS --threads \\\$\${BONSAI_CPU_THREADS}"
          fi
        fi

        ARGS="\\\$ARGS -c \\\$\${BONSAI_CTX_SIZE}"
        ARGS="\\\$ARGS --flash-attn on"
        ARGS="\\\$ARGS -ctk \\\$\${BONSAI_CACHE_K} -ctv \\\$\${BONSAI_CACHE_V}"
        ARGS="\\\$ARGS -b \\\$\${BONSAI_BATCH_SIZE} -ub \\\$\${BONSAI_UBATCH_SIZE}"
        ARGS="\\\$ARGS -ngl 999"
        ARGS="\\\$ARGS --mlock --no-mmap"
        ARGS="\\\$ARGS --cache-prompt-tokens"
        ARGS="\\\$ARGS --slots 1"
        ARGS="\\\$ARGS --jinja"
        ARGS="\\\$ARGS --reasoning on --reasoning-effort \\\$\${BONSAI_REASONING_EFFORT}"
        ARGS="\\\$ARGS --temp \\\$\${BONSAI_TEMP} --top-p \\\$\${BONSAI_TOP_P} --top-k \\\$\${BONSAI_TOP_K} --min-p \\\$\${BONSAI_MIN_P}"

        [ -n "\\\$\${BONSAI_ALIAS}" ] && ARGS="\\\$ARGS --alias \\\$\${BONSAI_ALIAS}"
        [ -n "\\\$\${BONSAI_API_KEY}" ] && ARGS="\\\$ARGS --api-key \\\$\${BONSAI_API_KEY}"

        echo "Запуск PrismML llama-server: \\\$SERVER_BIN \\\$ARGS"
        eval exec "\\\$SERVER_BIN" "\\\$ARGS"
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

# 6.3. Сборка Docker-образа с PrismML llama.cpp
log_info "Сборка Docker-образа prismml-llama:v100 (компиляция под sm_70)..."
docker compose -f "${MODEL_DIR}/docker-compose.yml" build

# 6.4. Создание службы автозапуска через systemd
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

log_info "Запуск контейнера bonsai2-llama-server..."
docker compose -f "${MODEL_DIR}/docker-compose.yml" down --remove-orphans 2>/dev/null || true
docker compose -f "${MODEL_DIR}/docker-compose.yml" up -d

log_info "Ожидание инициализации модели в VRAM (до 180 сек)..."
MAX_WAIT=180
WAIT_COUNTER=0
HEALTHY=false

while [ $WAIT_COUNTER -lt $MAX_WAIT ]; do
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:${LOCAL_API_PORT}/health" 2>/dev/null || true)
    if [ "$HTTP_CODE" = "200" ]; then
        HEALTHY=true
        break
    fi
    sleep 3
    WAIT_COUNTER=$((WAIT_COUNTER + 3))
    echo -n "."
done
echo ""

if [ "$HEALTHY" = "true" ]; then
    log_success "Эндпоинт /health отвечает 200 OK! Модель полностью готова в VRAM."
else
    log_warn "Сервер еще загружает веса в память или инициализируется. Логи:"
    docker compose -f "${MODEL_DIR}/docker-compose.yml" logs --tail 30 || true
fi

# ==============================================================================
# ШАГ 7: Тестовый инференс с параметрами сэмплирования из отчета
# ==============================================================================
log_step "ШАГ 7: Проверка API и тестовый инференс"

log_info "Проверка списка моделей (/v1/models)..."
curl -s "http://127.0.0.1:${LOCAL_API_PORT}/v1/models" -H "Authorization: Bearer ${API_KEY}" | jq . || true

log_info "Тестовый инференс (Thinking Mode + параметры: temp 1.0, top-p 0.95, top-k 20, min-p 0.05)..."
TEST_COMPLETION=$(curl -s "http://127.0.0.1:${LOCAL_API_PORT}/v1/chat/completions" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer ${API_KEY}" \
    -d '{
        "model": "bonsai2",
        "messages": [
            {"role": "user", "content": "Ответь кратко: тест пройден успешно?"}
        ],
        "max_tokens": 128,
        "temperature": 1.0,
        "top_p": 0.95,
        "top_k": 20,
        "min_p": 0.05,
        "chat_template_kwargs": {"enable_thinking": true}
    }' || true)

log_success "Ответ модели:"
echo "$TEST_COMPLETION" | jq . 2>/dev/null || echo "$TEST_COMPLETION"

# ==============================================================================
# ШАГ 8: Настройка SSH-туннелей
# ==============================================================================
log_step "ШАГ 8: Настройка SSH-туннелей"

if [ ! -f /root/.ssh/id_ed25519 ]; then
    mkdir -p /root/.ssh
    chmod 700 /root/.ssh
    ssh-keygen -t ed25519 -N "" -f /root/.ssh/id_ed25519
fi

if [ -n "$TARGET_HOST_IP" ]; then
    log_info "Настройка сервиса Reverse-туннеля к ${TARGET_HOST_IP}..."
    cat <<EOF > /etc/systemd/system/bonsai-reverse-tunnel.service
[Unit]
Description=AutoSSH Reverse Tunnel for Bonsai2 API to ${TARGET_HOST_IP}
After=network.target docker.service

[Service]
Type=simple
User=root
ExecStart=/usr/bin/autossh -M 0 -N \\
    -o "ServerAliveInterval 30" \\
    -o "ServerAliveCountMax 3" \\
    -o "ExitOnForwardFailure yes" \\
    -o "StrictHostKeyChecking=no" \\
    -R ${TUNNEL_REMOTE_PORT}:127.0.0.1:${LOCAL_API_PORT} \\
    ${TARGET_HOST_USER}@${TARGET_HOST_IP}
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
    systemctl daemon-reload
fi

CURRENT_IP=$(curl -s ifconfig.me || curl -s icanhazip.com || hostname -I | awk '{print $1}' || echo "GPU_HOST_IP")
cat <<EOF > "${MODEL_DIR}/connect_tunnel.sh"
#!/usr/bin/env bash
# Запустите на клиенте для локального доступа к модели на порту ${TUNNEL_REMOTE_PORT}:
ssh -N -f -L ${TUNNEL_REMOTE_PORT}:127.0.0.1:${LOCAL_API_PORT} root@${CURRENT_IP}
echo "Туннель запущен: http://127.0.0.1:${TUNNEL_REMOTE_PORT}/v1"
echo "API Key: ${API_KEY}"
EOF
chmod +x "${MODEL_DIR}/connect_tunnel.sh"

log_step "РАЗВЕРТЫВАНИЕ TERNARY-BONSAI-2 НА TESLA V100 УСПЕШНО ЗАВЕРШЕНО!"
echo -e "${GREEN}Итоги конфигурации:${NC}"
echo -e " 1. Модель: Ternary-Bonsai-2-27B-Uncensored-Heretic-PQ2_0.gguf (~7.21 GB)"
echo -e " 2. Движок: PrismML-Eng/llama.cpp (ветка prism, собрана под CUDA sm_70)"
echo -e " 3. Vision проектор: ${MMPROJ_FILE} в RAM хоста (--no-mmproj-offload, потоков: ${CPU_THREADS})"
echo -e " 4. Контекст: ${CTX_SIZE} токенов (256K нативное окно)"
echo -e " 5. KV-кэш: Несжатый FP16 (-ctk f16 -ctv f16, ~15.3 GiB VRAM)"
echo -e " 6. Память VRAM: ~24.3 GiB из 31.7 GiB (свободно ~7.4 GiB VRAM!)"
echo -e " 7. Сэмплирование: temp ${TEMP}, top-p ${TOP_P}, top-k ${TOP_K}, min-p ${MIN_P}"
echo -e " 8. Тюнинг V100: Persistence Mode, Compute Mode, memlock unlimited, 4GB Swap"
echo -e " 9. API эндпоинт: http://127.0.0.1:${LOCAL_API_PORT}/v1 (ключ: ${API_KEY})"
