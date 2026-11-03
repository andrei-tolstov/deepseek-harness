#!/usr/bin/env bash
# ==============================================================================
# Скрипт переключения на Qwen3.8 EfficientThink-K3 на Tesla V100
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="${1:-${SCRIPT_DIR}}"

echo "======================================================================"
echo " Переключение на Qwen3.8 EfficientThink-K3 (nvfp4-mixed) на Tesla V100..."
echo "======================================================================"

echo "[1/3] Остановка других LLM и Diffusion серверов на V100..."
docker stop coder390-llama-server qwen38-llama-server fable-llama-server bonsai2-llama-server efficientthink-k3-llama-server fluxed-up-sd-server juggernaut-sd-server 2>/dev/null || true
sleep 2

echo "[2/3] Запуск сервиса efficientthink-k3-server (ninfer-serve)..."
cd "$TARGET_DIR"
docker compose --env-file .env -f docker-compose.yml up -d

echo "[3/3] Ожидание инициализации модели на порту 8087..."
i=0
while [ $i -lt 90 ]; do
    if curl -s -f http://127.0.0.1:8087/health >/dev/null 2>&1; then
        echo ""
        echo "[OK] Qwen3.8 EfficientThink-K3 успешно запущена и готова к работе!"
        echo "Прямой эндпоинт: http://192.168.50.38:8087/v1"
        echo "Через llama-swap: http://192.168.50.38:8090/v1 (модель: efficientthink-k3 или default)"
        docker ps --filter name=efficientthink-k3-llama-server
        exit 0
    fi
    echo -n "."
    sleep 2
    i=$((i + 1))
done

echo ""
echo "[!] Сервер еще загружается в VRAM. Проверьте логи: docker logs -f efficientthink-k3-llama-server"
