#!/usr/bin/env bash
# ==============================================================================
# Скрипт переключения на nerkyor Qwen3.8-Coder390 (NInfer V2) на Tesla V100
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="${1:-${SCRIPT_DIR}}"

echo "======================================================================"
echo " Переключение на модель nerkyor Qwen3.8-Coder390 (NInfer V2) на Tesla V100..."
echo "======================================================================"

echo "[1/3] Остановка других LLM и Diffusion серверов на V100..."
docker stop qwen38-llama-server fable-llama-server bonsai2-llama-server coder390-llama-server fluxed-up-sd-server juggernaut-sd-server 2>/dev/null || true
sleep 2

echo "[2/3] Запуск сервиса coder390-server (ninfer-serve)..."
cd "$TARGET_DIR"
docker compose --env-file .env -f docker-compose.coder390.yml up -d

echo "[3/3] Ожидание инициализации модели на порту 8084..."
i=0
while [ $i -lt 90 ]; do
    if curl -s -f http://127.0.0.1:8084/health >/dev/null 2>&1; then
        echo ""
        echo "[OK] Qwen3.8 Coder390 (NInfer V2) успешно запущена и готова к работе!"
        echo "Прямой эндпоинт: http://192.168.50.38:8084/v1"
        echo "Через OmniRoute: http://192.168.50.38:20128/v1 (модель: coder390/coder390-27b или andrei-router)"
        docker ps --filter name=coder390-llama-server
        exit 0
    fi
    echo -n "."
    sleep 2
    i=$((i + 1))
done

echo ""
echo "[!] Сервер еще загружается в VRAM. Проверьте логи: docker logs -f coder390-llama-server"
