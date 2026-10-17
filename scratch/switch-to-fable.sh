#!/usr/bin/env bash
set -euo pipefail

echo "======================================================================"
echo " Переключение на модель DavidAU Fable Cold Fusion 27B на Tesla V100..."
echo "======================================================================"

echo "[1/3] Остановка других LLM серверов на V100..."
docker stop qwen38-llama-server bonsai2-llama-server 2>/dev/null || true
sleep 2

echo "[2/3] Запуск fable-llama-server..."
cd /root/model/fable_cold_fusion
docker compose --env-file .env -f docker-compose.fable.yml up -d

echo "[3/3] Ожидание инициализации модели на порту 8083..."
i=0
while [ $i -lt 60 ]; do
    if curl -s -f http://127.0.0.1:8083/health >/dev/null 2>&1; then
        echo ""
        echo "[OK] Fable Cold Fusion успешно запущена и готова к работе!"
        echo "Прямой эндпоинт: http://192.168.50.101:8083/v1"
        echo "Через OmniRoute: http://192.168.50.101:20128/v1 (модель: fable/fable-cold-fusion-27b)"
        docker ps --filter name=fable-llama-server
        exit 0
    fi
    echo -n "."
    sleep 2
    i=$((i + 1))
done

echo ""
echo "[!] Сервер еще загружается в VRAM. Проверьте логи: docker logs -f fable-llama-server"
