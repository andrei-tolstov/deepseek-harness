#!/bin/bash
set -e

CONFIG_FILE="${LLAMA_SWAP_CONFIG:-/app/config.yaml}"
LISTEN_ADDR="${LLAMA_SWAP_LISTEN:-0.0.0.0:8080}"
FALLBACK_MODEL="${PRIMARY_MODEL:-coder390}"
WATCHDOG_INTERVAL="${WATCHDOG_INTERVAL:-5}"

echo "======================================================================"
echo " [llama-swap] Запуск супервизора и роутера моделей на порту $LISTEN_ADDR"
echo " [llama-swap] Основная модель по умолчанию: $FALLBACK_MODEL"
echo "======================================================================"

# Запуск llama-swap
/usr/local/bin/llama-swap \
    -config "$CONFIG_FILE" \
    -watch-config \
    -listen "$LISTEN_ADDR" &
LS_PID=$!

# Функция корректного завершения
cleanup() {
    echo "[llama-swap] Остановка процессов..."
    kill "$WATCHDOG_PID" 2>/dev/null || true
    kill -TERM "$LS_PID" 2>/dev/null || true
    wait "$LS_PID" 2>/dev/null || true
    exit 0
}
trap cleanup SIGTERM SIGINT

# Фоновый watchdog: если ни одна модель не активна, автоматически подгружаем основную модель (coder390)
(
    # Даем время llama-swap на запуск и биндинг порта
    sleep 4
    while kill -0 "$LS_PID" 2>/dev/null; do
        sleep "$WATCHDOG_INTERVAL"
        
        # Получаем список запущенных моделей из локального API
        RUNNING_JSON=$(curl -s --max-time 5 http://127.0.0.1:8080/running 2>/dev/null || echo '{"running":[]}')
        
        # Проверяем, пуст ли массив running
        IS_EMPTY=$(echo "$RUNNING_JSON" | jq -r '.running | length' 2>/dev/null || echo "0")
        
        if [ "$IS_EMPTY" = "0" ]; then
            echo "[watchdog] Активных моделей в VRAM нет. Переключение на основную модель ($FALLBACK_MODEL)..."
            curl -s --max-time 5 "http://127.0.0.1:8080/upstream/${FALLBACK_MODEL}/health" >/dev/null 2>&1 || true
        fi
    done
) &
WATCHDOG_PID=$!

# Ожидание завершения основного процесса llama-swap
wait "$LS_PID"
kill "$WATCHDOG_PID" 2>/dev/null || true
