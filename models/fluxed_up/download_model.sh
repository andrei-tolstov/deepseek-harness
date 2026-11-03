#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="${1:-${MODEL_DIR:-${SCRIPT_DIR}}}"

mkdir -p "$TARGET_DIR"
cd "$TARGET_DIR"

echo "======================================================================"
echo " Загрузка компонентов модели FLUX Fluxed Up (GGUF Q8_0)"
echo " Целевая папка : $TARGET_DIR"
echo "======================================================================"

download_file() {
    local url="$1"
    local filename="$2"
    local desc="$3"

    echo "----------------------------------------------------------------------"
    echo "[*] Проверка: $desc ($filename)"
    if [ -f "$filename" ] && [ -s "$filename" ]; then
        echo "[OK] Файл $filename уже существует ($(du -h "$filename" | awk '{print $1}'))."
        return 0
    fi

    echo "[*] Загрузка $filename..."
    if command -v aria2c >/dev/null 2>&1; then
        aria2c \
            --file-allocation=none \
            --continue=true \
            --max-connection-per-server=16 \
            --split=16 \
            --min-split-size=10M \
            --summary-interval=15 \
            --out="$filename" \
            "$url" || true
    fi

    if [ ! -f "$filename" ] || [ ! -s "$filename" ]; then
        curl -L -C - --progress-bar -o "$filename" "$url"
    fi

    if [ -f "$filename" ] && [ -s "$filename" ]; then
        echo "[OK] Успешно загружен: $filename ($(du -h "$filename" | awk '{print $1}'))."
    else
        echo "ОШИБКА: Не удалось загрузить $filename!"
        exit 1
    fi
}

# 1. Основной трансформер FLUX Fluxed Up в формате Q8_0 (~12.7 ГБ)
DIT_URL="https://huggingface.co/Goncalo2005aa/fluxedu_4.1_nsfw_Q8.gguf/resolve/main/fluxedUpFluxNSFW_41Q80Gguf.gguf"
download_file "$DIT_URL" "fluxed_up_q8_0.gguf" "Трансформер FLUX Fluxed Up (Q8_0)"
ln -sf "fluxed_up_q8_0.gguf" "fluxed_up.gguf"

# 2. Текстовый энкодер CLIP-L (ViT-L/14)
CLIP_URL="https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/clip_l.safetensors"
download_file "$CLIP_URL" "clip_l.safetensors" "Текстовый энкодер CLIP-L"

# 3. Текстовый энкодер T5-XXL (Q8_0 квантование для экономии VRAM)
T5_URL="https://huggingface.co/city96/t5-v1_1-xxl-encoder-gguf/resolve/main/t5-v1_1-xxl-encoder-Q8_0.gguf"
download_file "$T5_URL" "t5xxl_q8_0.gguf" "Текстовый энкодер T5-XXL Q8_0"

# 4. Flux VAE (Autoencoder)
VAE_URL="https://huggingface.co/camenduru/FLUX.1-dev/resolve/main/ae.safetensors"
download_file "$VAE_URL" "ae.safetensors" "Flux VAE (Autoencoder)"

echo "======================================================================"
echo "[OK] Все компоненты FLUX Fluxed Up успешно подготовлены!"
echo "======================================================================"
