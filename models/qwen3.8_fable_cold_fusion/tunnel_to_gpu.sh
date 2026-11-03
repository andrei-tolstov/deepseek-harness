#!/usr/bin/env bash
# ==============================================================================
# Скрипт поднятия защищенного SSH-туннеля к удаленному GPU-серверу с DavidAU Fable Cold Fusion
#
# Использование:
#   ./tunnel_to_gpu.sh <IP_УДАЛЕННОГО_GPU_СЕРВЕРА> [SSH_KEY_PATH]
#
# Пример:
#   ./tunnel_to_gpu.sh 89.208.100.50 ~/.ssh/id_ed25519
# ==============================================================================

set -euo pipefail

GPU_IP="${1:-}"
KEY_PATH="${2:-~/.ssh/id_ed25519}"
LOCAL_PORT="${LOCAL_PORT:-8083}"
REMOTE_PORT="${REMOTE_PORT:-8080}"
SSH_USER="${SSH_USER:-root}"

if [ -z "$GPU_IP" ]; then
    echo "Использование: $0 <IP_УДАЛЕННОГО_GPU_СЕРВЕРА> [SSH_KEY_PATH]"
    echo "Пример: $0 89.208.100.50"
    exit 1
fi

KEY_OPT=""
if [ -f "$KEY_PATH" ]; then
    KEY_OPT="-i $KEY_PATH"
fi

echo "======================================================================"
echo " Поднятие защищенного SSH-туннеля:"
echo "   Удаленный GPU-сервер : ${SSH_USER}@${GPU_IP}"
echo "   Проброс порта        : localhost:${LOCAL_PORT} -> ${GPU_IP}:localhost:${REMOTE_PORT}"
echo "======================================================================"

if ss -tulpn 2>/dev/null | grep -q ":${LOCAL_PORT} "; then
    echo "[!] Порт ${LOCAL_PORT} уже слушается локально."
else
    if command -v autossh >/dev/null 2>&1; then
        echo "[*] Запуск постоянного туннеля через autossh в фоне..."
        autossh -M 0 -f -N \
            -o "ServerAliveInterval 30" \
            -o "ServerAliveCountMax 3" \
            -o "ExitOnForwardFailure yes" \
            -o "StrictHostKeyChecking=no" \
            $KEY_OPT \
            -L "${LOCAL_PORT}:127.0.0.1:${REMOTE_PORT}" \
            "${SSH_USER}@${GPU_IP}"
    else
        echo "[*] Запуск туннеля через ssh в фоне..."
        ssh -f -N \
            -o "ServerAliveInterval 30" \
            -o "ServerAliveCountMax 3" \
            -o "ExitOnForwardFailure yes" \
            -o "StrictHostKeyChecking=no" \
            $KEY_OPT \
            -L "${LOCAL_PORT}:127.0.0.1:${REMOTE_PORT}" \
            "${SSH_USER}@${GPU_IP}"
    fi
fi

sleep 2

echo "[*] Проверка доступности API модели через туннель..."
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:${LOCAL_PORT}/health" 2>/dev/null || true)

if [ "$HTTP_CODE" = "200" ]; then
    echo "[OK] Туннель активен! API доступно по адресу http://127.0.0.1:${LOCAL_PORT}"
    AUTH_HEADER=()
    [ -n "${API_KEY:-}" ] && AUTH_HEADER=(-H "Authorization: Bearer ${API_KEY}")
    curl -s "http://127.0.0.1:${LOCAL_PORT}/v1/models" "${AUTH_HEADER[@]}"
    echo ""
    echo "======================================================================"
    echo "Пример запроса (Thinking Mode, сжатый TURBO reasoning):"
    echo "curl http://127.0.0.1:${LOCAL_PORT}/v1/chat/completions \\"
    [ -n "${API_KEY:-}" ] && echo "  -H 'Authorization: Bearer ${API_KEY}' \\"
    echo "  -H 'Content-Type: application/json' \\"
    echo "  -d '{\"model\": \"fable\", \"messages\": [{\"role\": \"user\", \"content\": \"Привет!\"}], \"temperature\": 0.85, \"min_p\": 0.05, \"top_p\": 0.95, \"repeat_penalty\": 1.0}'"
    echo "======================================================================"
else
    echo "[?] Эндпоинт /health вернул код: $HTTP_CODE. Возможно, модель еще загружается в VRAM."
fi
