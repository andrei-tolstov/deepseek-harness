#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="${1:-${MODEL_DIR:-${SCRIPT_DIR}}}"

mkdir -p "$TARGET_DIR"
cd "$TARGET_DIR"

echo "======================================================================"
echo " Загрузка компонентов модели Qwen-Image-2.1-Turbo-Uncensored (Q8_0)"
echo " Оптимизировано под NVIDIA Tesla V100 32GB (sm_70)"
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

# 1. Denoiser Qwen-Image-2.1-Turbo в квантовании Q8_0 (~7.07 GiB / 7.59 GB)
DIT_URL="https://huggingface.co/AtomicChat/Qwen-Image-2.1-Turbo-GGUF/resolve/main/Qwen-Image-2.1-Turbo-Q8_0.gguf"
download_file "$DIT_URL" "Qwen-Image-2.1-Turbo-Q8_0.gguf" "Трансформер/Denoiser Qwen-Image-2.1-Turbo (Q8_0)"
ln -sf "Qwen-Image-2.1-Turbo-Q8_0.gguf" "qwen_image_turbo.gguf"

# 2. Нецензурированный текстовый энкодер Qwen3-VL-8B-Instruct (Abliterated) в квантовании Q8_0 (~8.11 GiB / 8.71 GB)
LLM_URL="https://huggingface.co/AtomicChat/Qwen-Image-2.1-Turbo-Uncensored-GGUF/resolve/main/Qwen-Image-2.1-Turbo-Uncensored-Q8_0.gguf"
download_file "$LLM_URL" "Qwen-Image-2.1-Turbo-Uncensored-Q8_0.gguf" "Текстовый энкодер Uncensored LLM (Q8_0)"
ln -sf "Qwen-Image-2.1-Turbo-Uncensored-Q8_0.gguf" "qwen_image_llm_uncensored.gguf"

# 3. Vision Projector (F16 для идеальной совместимости с V100 Volta, ~1.08 GiB / 1.16 GB)
MMPROJ_URL="https://huggingface.co/AtomicChat/Qwen-Image-2.1-Turbo-Uncensored-GGUF/resolve/main/mmproj-Qwen-Image-2.1-Turbo-Uncensored-F16.gguf"
download_file "$MMPROJ_URL" "mmproj-Qwen-Image-2.1-Turbo-Uncensored-F16.gguf" "Vision Projector mmproj (F16)"
ln -sf "mmproj-Qwen-Image-2.1-Turbo-Uncensored-F16.gguf" "qwen_image_mmproj.gguf"

# 4. Qwen-Image-2.1 VAE (~0.63 GiB / 0.68 GB)
VAE_URL="https://huggingface.co/Comfy-Org/Qwen-Image-2.1/resolve/main/vae/qwen_image_2.1_vae_bf16.safetensors"
download_file "$VAE_URL" "qwen_image_2.1_vae_bf16.safetensors" "Qwen-Image-2.1 VAE"

echo "======================================================================"
echo "[OK] Все компоненты Qwen-Image-2.1-Turbo-Uncensored успешно подготовлены!"
echo "======================================================================"
