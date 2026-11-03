#!/bin/bash
# ==============================================================================
# Скрипт подготовки и сборки NInfer V2 для nerkyor Qwen3.8-27B-Coder390
# Платформа: NVIDIA Tesla V100 32GB (CUDA 12.8, sm_70)
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "======================================================================"
echo " Загрузка эталонной модели NInfer V2 (W4A4-W8A8 MTP + Vision)..."
echo "======================================================================"
bash ./download_model_w4a4_w8a8.sh "$SCRIPT_DIR"

MODEL_FILE="Qwen3.8-27B-Coder390-EfficientThink-NVFP4-W4A4-W8A8-MTP-NInferV2.ninfer"
if [ ! -f "$SCRIPT_DIR/$MODEL_FILE" ]; then
    echo "ОШИБКА: Файл модели $MODEL_FILE не найден после скачивания!"
    exit 1
fi

ln -sfn "$MODEL_FILE" "$SCRIPT_DIR/model_v100.ninfer"
echo "[OK] Символическая ссылка создана: model_v100.ninfer -> $MODEL_FILE"

echo "======================================================================"
echo " Сборка Docker-образа ninfer-v100:cuda12.8..."
echo "======================================================================"
docker build -f Dockerfile.v100 -t ninfer-v100:cuda12.8 .

echo "======================================================================"
echo " Готово! Образ ninfer-v100:cuda12.8 успешно собран."
echo " Для запуска используйте: docker compose up -d"
echo "======================================================================"
