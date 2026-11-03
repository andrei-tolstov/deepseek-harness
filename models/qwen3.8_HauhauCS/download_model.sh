#!/usr/bin/env bash
# ==============================================================================
# Скрипт скачивания модели HauhauCS Qwen3.8-27B-Uncensored-Aggressive,
# мультимодального проектора mmproj (MTP отключен)
#
# Репозиторий: HauhauCS/Qwen3.8-27B-Uncensored-HauhauCS-Aggressive-MTP-GGUF
# Оптимизировано для NVIDIA Tesla V100 32GB (Volta, sm_70, Debian 12)
#
# Компоненты:
#   1. Модель: Qwen3.8-27B-Uncensored-HauhauCS-Aggressive-Q6_K_P.gguf (25.92 GB / 24.14 GiB)
#      - Профиль Perfect (K_P): повышенная точность весов при 7.59 BPW.
#   2. Vision mmproj: mmproj-Qwen3.8-27B-Uncensored-HauhauCS-Aggressive-BF16.gguf (931 MB)
#      - Мультимодальность с принудительной выгрузкой в RAM хоста (--no-mmproj-offload).
#   3. (Опционально) FastMTP сайдкар: Qwen3.8-27B-Uncensored-HauhauCS-Aggressive-FastMTP-32K.gguf (903 MB)
#      - По умолчанию отключен (DOWNLOAD_FASTMTP=false).
# ==============================================================================

set -euo pipefail

TARGET_DIR="${1:-${MODEL_DIR:-/root/model/qwen3.8}}"
mkdir -p "$TARGET_DIR"
cd "$TARGET_DIR"

BASE_URL="https://huggingface.co/HauhauCS/Qwen3.8-27B-Uncensored-HauhauCS-Aggressive-MTP-GGUF/resolve/main"

MODEL_FILE="${MODEL_FILE:-Qwen3.8-27B-Uncensored-HauhauCS-Aggressive-Q4_K_P.gguf}"
MMPROJ_FILE="${MMPROJ_FILE:-mmproj-Qwen3.8-27B-Uncensored-HauhauCS-Aggressive-BF16.gguf}"
FASTMTP_FILE="${FASTMTP_FILE:-Qwen3.8-27B-Uncensored-HauhauCS-Aggressive-FastMTP-32K.gguf}"
PATCH_FILE="${PATCH_FILE:-HauhauCS-FastMTP-llama.cpp.patch}"

DOWNLOAD_MMPROJ="${DOWNLOAD_MMPROJ:-true}"
DOWNLOAD_FASTMTP="${DOWNLOAD_FASTMTP:-false}"
DOWNLOAD_PATCH="${DOWNLOAD_PATCH:-false}"

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
echo " Старт загрузки компонентов HauhauCS Qwen3.8-27B в: $TARGET_DIR"
echo " Языковая модель (Q5_K_P) : $MODEL_FILE"
if [ "$DOWNLOAD_FASTMTP" = "true" ]; then
    echo " FastMTP Sidecar (32K)   : $FASTMTP_FILE"
fi
if [ "$DOWNLOAD_MMPROJ" = "true" ]; then
    echo " Vision-проектор (mmproj): $MMPROJ_FILE (запуск в CPU RAM)"
fi
if [ "$DOWNLOAD_PATCH" = "true" ]; then
    echo " Runtime FastMTP patch   : $PATCH_FILE"
fi
echo "======================================================================"

download_file "$MODEL_FILE"

if [ "$DOWNLOAD_FASTMTP" = "true" ]; then
    download_file "$FASTMTP_FILE"
fi

if [ "$DOWNLOAD_MMPROJ" = "true" ]; then
    download_file "$MMPROJ_FILE"
fi

if [ "$DOWNLOAD_PATCH" = "true" ]; then
    download_file "$PATCH_FILE"
fi

echo "======================================================================"
echo " Загрузка завершена! Содержимое $TARGET_DIR:"
echo "======================================================================"
ls -lh "$TARGET_DIR"
