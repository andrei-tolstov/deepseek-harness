#!/bin/bash
# ==============================================================================
# Скрипт подготовки и сборки NInfer v3 для EfficientThink-K3 (nvfp4-mixed)
# Платформа: NVIDIA Tesla V100 32GB (CUDA 12.8, sm_70)
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "======================================================================"
echo " [1/3] Загрузка модели Qwen3.8-27B EfficientThink-K3 с ModelScope..."
echo "======================================================================"
bash ./download_model.sh "$SCRIPT_DIR"

MODEL_FILE="qwen3_8_27b_nvfp4_EfficientThink_K3.ninfer"
if [ ! -f "$SCRIPT_DIR/$MODEL_FILE" ]; then
    echo "ОШИБКА: Файл модели $MODEL_FILE не найден после скачивания!"
    exit 1
fi

ln -sfn "$MODEL_FILE" "$SCRIPT_DIR/model_v100.ninfer"
echo "[OK] Символическая ссылка создана: model_v100.ninfer -> $MODEL_FILE"

echo "======================================================================"
echo " [2/3] Проверка/сборка Docker-образа ninfer-v100:cuda12.8..."
echo "======================================================================"
if docker image inspect ninfer-v100:cuda12.8 >/dev/null 2>&1; then
    echo "[OK] Образ ninfer-v100:cuda12.8 уже собран в локальном реестре Docker."
else
    echo "[*] Сборка образа ninfer-v100:cuda12.8 из Dockerfile.v100..."
    docker build -f Dockerfile.v100 -t ninfer-v100:cuda12.8 .
fi

echo "======================================================================"
echo " [3/3] Готово! Для запуска используйте:"
echo "   docker compose up -d"
echo "   или ./switch-to-efficientthink-k3.sh"
echo "======================================================================"
