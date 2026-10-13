#!/bin/bash
set -e

MODEL_PATH="${MODEL_PATH:-/models/laya_multilingual_f16.gguf}"
MODEL_URL="${MODEL_URL:-https://huggingface.co/mys/laya-multilingual-GGUF/resolve/main/laya_multilingual_f16.gguf}"
PORT="${PORT:-8080}"
MCP_PORT="${MCP_PORT:-8787}"
DEVICE="${DEVICE:-cpu}"
EXTRA_FLAGS="${EXTRA_FLAGS:---threads 8}"

mkdir -p "$(dirname "$MODEL_PATH")"

if [ ! -f "$MODEL_PATH" ]; then
    echo "======================================================================"
    echo " [Laya] Файл модели не найден по пути: $MODEL_PATH"
    echo " [Laya] Начинается автоматическая загрузка с Hugging Face:"
    echo "        $MODEL_URL"
    echo "======================================================================"
    curl -L --progress-bar -o "$MODEL_PATH" "$MODEL_URL"
    echo " [Laya] Загрузка модели завершена успешно!"
fi

echo "======================================================================"
echo " [Laya] Запуск C++ сервера System 1 Decision Studio:"
echo "        Модель    : $MODEL_PATH"
echo "        Порт REST : $PORT"
echo "        Устройство: $DEVICE"
echo "        Флаги     : $EXTRA_FLAGS"
echo "======================================================================"

start_laya() {
    /usr/local/bin/laya serve "$MODEL_PATH" --port "$PORT" --device "$DEVICE" $EXTRA_FLAGS &
    LAYA_PID=$!
    echo "$LAYA_PID" > /tmp/laya.pid
}

start_laya

echo " [Laya] Ожидание готовности C++ инференс-сервера на порту $PORT..."
until curl -s "http://127.0.0.1:$PORT/health" > /dev/null; do
    if ! kill -0 "$LAYA_PID" 2>/dev/null; then
        echo " [Laya] ОШИБКА: C++ сервер laya аварийно завершился!"
        exit 1
    fi
    sleep 1
done
echo " [Laya] C++ инференс-сервер готов!"

echo "======================================================================"
echo " [Laya] Запуск MCP & Sidecar сервера (Streamable HTTP / Tools):"
echo "        Порт MCP  : $MCP_PORT"
echo "======================================================================"

LAYA_ENGINE_URL="http://127.0.0.1:$PORT" MCP_PORT="$MCP_PORT" python3 /app/mcp_server.py &
MCP_PID=$!

cleanup() {
    echo " [Laya] Завершение работы..."
    kill -TERM "$MCP_PID" 2>/dev/null || true
    kill -TERM "$LAYA_PID" 2>/dev/null || true
    wait "$LAYA_PID" 2>/dev/null || true
    wait "$MCP_PID" 2>/dev/null || true
    exit 0
}

trap cleanup SIGINT SIGTERM

while kill -0 "$MCP_PID" 2>/dev/null; do
    if [ -f /tmp/laya_restart_requested ]; then
        echo " [Laya] Обнаружен запрос на перезагрузку весов модели. Перезапуск C++ движка..."
        rm -f /tmp/laya_restart_requested
        kill -TERM "$LAYA_PID" 2>/dev/null || true
        wait "$LAYA_PID" 2>/dev/null || true
        sleep 0.5
        start_laya
    fi
    if ! kill -0 "$LAYA_PID" 2>/dev/null; then
        echo " [Laya] C++ инференс-сервер завершился, перезапуск..."
        sleep 1
        start_laya
    fi
    sleep 0.5
done

cleanup
