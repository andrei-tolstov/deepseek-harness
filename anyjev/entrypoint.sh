#!/bin/bash
set -e

MODEL_PATH="${MODEL_PATH:-/models/Tacit-4B-Q4_K_M.gguf}"
LLAMA_PORT="${LLAMA_PORT:-8081}"
PORT="${PORT:-8080}"
MCP_PORT="${MCP_PORT:-8787}"
CTX_SIZE="${CTX_SIZE:-2048}"
N_GPU_LAYERS="${N_GPU_LAYERS:-99}"
THREADS="${THREADS:-4}"
PARALLEL_SLOTS="${PARALLEL_SLOTS:-2}"
CACHE_REUSE="${CACHE_REUSE:-64}"

export CUDA_DEVICE_ORDER=PCI_BUS_ID
export CUDA_VISIBLE_DEVICES=0
export LD_LIBRARY_PATH=/usr/local/lib:${LD_LIBRARY_PATH}

echo "======================================================================"
echo " [AnyJev] Запуск llama-server (C++ GGUF inference backend):"
echo "          Модель         : $MODEL_PATH"
echo "          Внутренний порт: $LLAMA_PORT"
echo "          Контекст (ctx) : $CTX_SIZE"
echo "          GPU слои (ngl) : $N_GPU_LAYERS"
echo "          Слоты (parallel): $PARALLEL_SLOTS"
echo "          Кэш-реюз       : $CACHE_REUSE"
echo "======================================================================"

start_llama() {
    /usr/local/bin/llama-server \
        --model "$MODEL_PATH" \
        --port "$LLAMA_PORT" \
        --host 127.0.0.1 \
        --ctx-size "$CTX_SIZE" \
        --n-gpu-layers "$N_GPU_LAYERS" \
        --threads "$THREADS" \
        --parallel "$PARALLEL_SLOTS" \
        --cache-prompt \
        --cache-reuse "$CACHE_REUSE" \
        &
    LLAMA_PID=$!
    echo "$LLAMA_PID" > /tmp/llama_server.pid
}

start_llama

echo " [AnyJev] Ожидание готовности llama-server на порту $LLAMA_PORT..."
until curl -sf "http://127.0.0.1:$LLAMA_PORT/health" > /dev/null; do
    if ! kill -0 "$LLAMA_PID" 2>/dev/null; then
        echo " [AnyJev] ОШИБКА: llama-server аварийно завершился!"
        exit 1
    fi
    sleep 0.5
done
echo " [AnyJev] llama-server готов к инференсу!"

echo "======================================================================"
echo " [AnyJev] Запуск AnyJev FastBridge сервиса решений:"
echo "          Порт System 1: $PORT (/v1/systemone)"
echo "          Порт Sidecar : $MCP_PORT (/ask, /v1/chat/completions, /health)"
echo "======================================================================"

LLAMA_URL="http://127.0.0.1:$LLAMA_PORT" python3 /app/anyjev_server.py "$PORT" &
PID_8080=$!

LLAMA_URL="http://127.0.0.1:$LLAMA_PORT" python3 /app/anyjev_server.py "$MCP_PORT" &
PID_8787=$!

EXIT_CODE=0
cleanup() {
    echo " [AnyJev] Завершение работы..."
    kill -TERM "$PID_8080" 2>/dev/null || true
    kill -TERM "$PID_8787" 2>/dev/null || true
    kill -TERM "$LLAMA_PID" 2>/dev/null || true
    wait "$LLAMA_PID" 2>/dev/null || true
    wait "$PID_8080" 2>/dev/null || true
    wait "$PID_8787" 2>/dev/null || true
    exit "${EXIT_CODE:-0}"
}

trap "EXIT_CODE=0; cleanup" SIGINT SIGTERM

while kill -0 "$PID_8080" 2>/dev/null && kill -0 "$PID_8787" 2>/dev/null && kill -0 "$LLAMA_PID" 2>/dev/null; do
    sleep 1
done

EXIT_CODE=1
cleanup
