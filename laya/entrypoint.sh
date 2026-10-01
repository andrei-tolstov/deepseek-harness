#!/bin/bash
set -e

MODEL_PATH="${MODEL_PATH:-/models/laya_multilingual_f16.gguf}"
MODEL_URL="${MODEL_URL:-https://huggingface.co/mys/laya-multilingual-GGUF/resolve/main/laya_multilingual_f16.gguf}"
PORT="${PORT:-8080}"
DEVICE="${DEVICE:-auto}"
EXTRA_FLAGS="${EXTRA_FLAGS:---cuda-graph}"

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
echo " [Laya] Запуск сервера System 1 Decision Studio:"
echo "        Модель : $MODEL_PATH"
echo "        Порт   : $PORT"
echo "        Устройство: $DEVICE"
echo "        Флаги  : $EXTRA_FLAGS"
echo "======================================================================"

exec /usr/local/bin/laya serve "$MODEL_PATH" --port "$PORT" --device "$DEVICE" $EXTRA_FLAGS
