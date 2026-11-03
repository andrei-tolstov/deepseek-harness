#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="${1:-${MODEL_DIR:-${SCRIPT_DIR}}}"

mkdir -p "$TARGET_DIR"
cd "$TARGET_DIR"

MODEL_FILENAME="Juggernaut-XL_v9_RunDiffusionPhoto_v2.safetensors"
HF_REPO="RunDiffusion/Juggernaut-XL-v9"
HF_URL="https://huggingface.co/${HF_REPO}/resolve/main/${MODEL_FILENAME}"

echo "======================================================================"
echo " Загрузка чекпоинта Juggernaut XL v9+ (SDXL 1.0 Photo v2)"
echo " Файл модели   : $MODEL_FILENAME"
echo " Репозиторий   : $HF_REPO"
echo " Целевая папка : $TARGET_DIR"
echo "======================================================================"

if [ -f "$MODEL_FILENAME" ] && [ -s "$MODEL_FILENAME" ]; then
    echo "[OK] Файл $MODEL_FILENAME уже существует ($(du -h "$MODEL_FILENAME" | awk '{print $1}'))."
else
    echo "[*] Загрузка $MODEL_FILENAME..."
    if command -v aria2c >/dev/null 2>&1; then
        aria2c \
            --file-allocation=none \
            --continue=true \
            --max-connection-per-server=16 \
            --split=16 \
            --min-split-size=10M \
            --summary-interval=15 \
            --out="$MODEL_FILENAME" \
            "$HF_URL" || true
    fi

    if [ ! -f "$MODEL_FILENAME" ] || [ ! -s "$MODEL_FILENAME" ]; then
        curl -L -C - --progress-bar -o "$MODEL_FILENAME" "$HF_URL"
    fi

    if [ -f "$MODEL_FILENAME" ] && [ -s "$MODEL_FILENAME" ]; then
        echo "[OK] Успешно загружен: $MODEL_FILENAME ($(du -h "$MODEL_FILENAME" | awk '{print $1}'))."
    else
        echo "ОШИБКА: Не удалось загрузить $MODEL_FILENAME!"
        exit 1
    fi
fi

# Создание канонического симлинка
ln -sf "$MODEL_FILENAME" "juggernaut_xl.safetensors"
echo "[OK] Симлинк создан: $TARGET_DIR/juggernaut_xl.safetensors -> $MODEL_FILENAME"

# 2. Загрузка исправленного VAE для предотвращения переполнения FP16 (Black Image Bug) на Tesla V100
VAE_FILENAME="sdxl_vae_fp16_fix.safetensors"
VAE_URL="https://huggingface.co/madebyollin/sdxl-vae-fp16-fix/resolve/main/sdxl_vae_fp16_fix.safetensors"

echo "----------------------------------------------------------------------"
echo "[*] Проверка исправленного VAE: $VAE_FILENAME"
if [ -f "$VAE_FILENAME" ] && [ -s "$VAE_FILENAME" ]; then
    echo "[OK] VAE $VAE_FILENAME уже существует ($(du -h "$VAE_FILENAME" | awk '{print $1}'))."
else
    echo "[*] Загрузка $VAE_FILENAME..."
    if command -v aria2c >/dev/null 2>&1; then
        aria2c \
            --file-allocation=none \
            --continue=true \
            --max-connection-per-server=8 \
            --split=8 \
            --out="$VAE_FILENAME" \
            "$VAE_URL" || true
    fi

    if [ ! -f "$VAE_FILENAME" ] || [ ! -s "$VAE_FILENAME" ]; then
        curl -L -C - --progress-bar -o "$VAE_FILENAME" "$VAE_URL"
    fi

    if [ -f "$VAE_FILENAME" ] && [ -s "$VAE_FILENAME" ]; then
        echo "[OK] Успешно загружен VAE: $VAE_FILENAME ($(du -h "$VAE_FILENAME" | awk '{print $1}'))."
    else
        echo "ОШИБКА: Не удалось загрузить $VAE_FILENAME!"
        exit 1
    fi
fi

echo "======================================================================"
