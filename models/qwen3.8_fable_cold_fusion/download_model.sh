#!/usr/bin/env bash
# ==============================================================================
# Скрипт скачивания модели DavidAU Qwen3.8-27B-TURBO-Fable-Cold-Fusion-735-882,
# встроенного MTP и мультимодального проектора mmproj
#
# Репозиторий: DavidAU/Qwen3.8-27B-TURBO-Fable-Cold-Fusion-735-882-Heretic-Uncensored-NEO-CODER-MAX-MTP-GGUF
# Оптимизировано для NVIDIA Tesla V100 32GB (Volta, sm_70, Debian 12 / Ubuntu)
#
# Компоненты:
#   1. Модель: Qwen3.8-27B-TurboFCFusion-735-882-Here-Uncen-NEO-CODER-MAX-MTP-Q6_K.gguf (~22.38 GiB)
#      - MTP-голова уже интегрирована в квантованный GGUF-файл весов
#      - Оптимальный квант наивысшего качества (6.56 BPW) под 120-140K токенов Q8_0 KV-кэша на 32GB VRAM
#   2. Vision mmproj: mmproj-BF16.gguf (~931 MB)
#      - Мультимодальность с принудительной выгрузкой в RAM хоста (--no-mmproj-offload)
# ==============================================================================

set -euo pipefail

TARGET_DIR="${1:-${MODEL_DIR:-/root/model/fable_cold_fusion}}"
mkdir -p "$TARGET_DIR"
cd "$TARGET_DIR"

BASE_URL="https://huggingface.co/DavidAU/Qwen3.8-27B-TURBO-Fable-Cold-Fusion-735-882-Heretic-Uncensored-NEO-CODER-MAX-MTP-GGUF/resolve/main"

MODEL_FILE="${MODEL_FILE:-Qwen3.8-27B-TurboFCFusion-735-882-Here-Uncen-NEO-CODER-MAX-MTP-Q6_K.gguf}"
MMPROJ_FILE="${MMPROJ_FILE:-mmproj-BF16.gguf}"

DOWNLOAD_MMPROJ="${DOWNLOAD_MMPROJ:-true}"

download_file() {
    local file="$1"
    local url="${BASE_URL}/${file}"

    if [ -f "$file" ] && [ -s "$file" ] && [ ! -f "${file}.aria2" ]; then
        echo "[OK] Файл $file уже существует ($(du -h "$file" 2>/dev/null | cut -f1 || echo 'exists')), пропускаем."
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

    echo "[OK] Успешно загружен: $file"
}

echo "======================================================================"
echo " Старт загрузки DavidAU Fable Cold Fusion 735-882 (MTP Q6_K) в: $TARGET_DIR"
echo " Языковая модель (Q6_K MTP) : $MODEL_FILE"
if [ "$DOWNLOAD_MMPROJ" = "true" ]; then
    echo " Vision-проектор (mmproj)   : $MMPROJ_FILE (запуск в CPU RAM)"
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
