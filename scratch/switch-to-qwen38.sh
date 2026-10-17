#!/usr/bin/env bash
set -euo pipefail

echo "======================================================================"
echo " Переключение на модель Qwen 3.8 HauhauCS на Tesla V100..."
echo "======================================================================"

echo "[1/3] Остановка fable-llama-server и bonsai2..."
docker stop fable-llama-server bonsai2-llama-server 2>/dev/null || true
sleep 2

echo "[2/3] Запуск qwen38-llama-server..."
cd /root/model/qwen3.8
docker compose up -d

echo "[3/3] Ожидание готовности Qwen 3.8 на порту 8081..."
i=0
while [ $i -lt 60 ]; do
    if curl -s -f http://127.0.0.1:8081/health >/dev/null 2>&1; then
        echo ""
        echo "[OK] Qwen 3.8 успешно запущена и готова к работе!"
        docker ps --filter name=qwen38-llama-server
        exit 0
    fi
    echo -n "."
    sleep 2
    i=$((i + 1))
done

echo ""
echo "[!] Сервер еще загружается. Проверьте логи: docker logs -f qwen38-llama-server"
