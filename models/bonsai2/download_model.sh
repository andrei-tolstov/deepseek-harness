#!/usr/bin/env bash
# ==============================================================================
# Скрипт скачивания модели Ternary-Bonsai-2-27B-Uncensored-Heretic (GGUF) и mmproj
# Оптимизировано для NVIDIA Tesla V100 32GB (архитектура Volta, sm_70)
#
# Обоснование выбора:
#   - Модель упакована в тернарный формат PQ2_0 (~7.21 GB) с сохранением
#     исходных блочных масштабов и максимальной стабильностью активаций.
#   - Компактный размер весов позволяет впервые на одиночной 32GB видеокарте
#     развернуть полный нативный контекст 262 144 токенов с эталонным
#     несжатым FP16 KV-кэшем (-ctk f16 -ctv f16, ~15.3 GiB VRAM),
#     оставляя ~7.4 GiB VRAM запаса!
#   - Мультимодальный проектор (mmproj-BF16.gguf, ~931 МБ) обеспечивает
#     нативное зрение и при инференсе выгружается в системную RAM (--no-mmproj-offload).
# ==============================================================================

set -euo pipefail

TARGET_DIR="${1:-${MODEL_DIR:-/root/model/bonsai2}}"
mkdir -p "$TARGET_DIR"
cd "$TARGET_DIR"

BASE_URL="https://huggingface.co/OS-Software/Ternary-Bonsai-2-27B-Uncensored-Heretic-GGUF/resolve/main"

# Целевая модель и мультимодальный проектор
MODEL_FILE="${MODEL_FILE:-Ternary-Bonsai-2-27B-Uncensored-Heretic-PQ2_0.gguf}"
MMPROJ_FILE="${MMPROJ_FILE:-mmproj-BF16.gguf}"
DOWNLOAD_MMPROJ="${DOWNLOAD_MMPROJ:-true}"

download_file() {
    local file="$1"
    local url="${BASE_URL}/${file}"

    if [ -f "$file" ] && [ -s "$file" ] && [ ! -f "${file}.aria2" ]; then
        echo "[OK] Файл $file уже существует ($(du -h "$file" | cut -f1)), пропускаем."
        return 0
    fi

    echo "======================================================================"
    echo " Загрузка $file с Hugging Face..."
    echo " URL: $url"
    echo "======================================================================"

    if command -v aria2c >/dev/null 2>&1; then
        aria2c \
            --file-allocation=none \
            --continue=true \
            --max-connection-per-server=16 \
            --split=16 \
            --min-split-size=10M \
            --summary-interval=15 \
            --out="$file" \
            "$url" || {
                echo "[!] aria2c завершился с ошибкой, переключение на curl..."
                curl -L -C - --progress-bar -o "$file" "$url"
            }
    elif command -v curl >/dev/null 2>&1; then
        curl -L -C - --progress-bar -o "$file" "$url"
    else
        wget -c --show-progress -O "$file" "$url"
    fi

    echo "[OK] Успешно загружен: $file ($(du -h "$file" | cut -f1))"
}

echo "======================================================================"
echo " Старт загрузки компонентов Ternary-Bonsai-2 в директорию: $TARGET_DIR"
echo " Тернарная модель: $MODEL_FILE"
if [ "$DOWNLOAD_MMPROJ" = "true" ]; then
    echo " Vision-проектор : $MMPROJ_FILE (запуск в RAM хоста)"
fi
echo "======================================================================"

download_file "$MODEL_FILE"

if [ "$DOWNLOAD_MMPROJ" = "true" ]; then
    download_file "$MMPROJ_FILE"
fi

echo "======================================================================"
echo " Загрузка завершена! Содержимое $TARGET_DIR:"
echo "======================================================================"
ls -lh "$TARGET_DIR"
