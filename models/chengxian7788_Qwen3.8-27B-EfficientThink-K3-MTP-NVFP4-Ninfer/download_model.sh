#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="${1:-${MODEL_DIR:-${SCRIPT_DIR}}}"

mkdir -p "$TARGET_DIR"
cd "$TARGET_DIR"

MODELSCOPE_REPO="chengxian7788/Qwen3.8-27B-EfficientThink-K3-MTP-NVFP4-Ninfer"
MODEL_FILENAME="qwen3_8_27b_nvfp4_EfficientThink_K3.ninfer"
CONVERSION_FILENAME="qwen3_8_27b_nvfp4_EfficientThink_K3.ninfer.conversion.json"

MS_BASE_URL="https://www.modelscope.cn/models/${MODELSCOPE_REPO}/resolve/master"
MODEL_URL="${MS_BASE_URL}/${MODEL_FILENAME}"
CONVERSION_URL="${MS_BASE_URL}/${CONVERSION_FILENAME}"

EXPECTED_SIZE="24812201456"
EXPECTED_SHA256="6846dd19dc02d52ca45b52855266ac586ed726d5d0b7c18467ca4f485fbdc8b6"

echo "======================================================================"
echo " Загрузка Qwen3.8-27B EfficientThink-K3-MTP-NVFP4 (nvfp4-mixed)"
echo " Репозиторий   : $MODELSCOPE_REPO"
echo " Файл модели   : $MODEL_FILENAME (~23.11 GiB / 24.81 GB)"
echo " Целевая папка : $TARGET_DIR"
echo "======================================================================"

check_file_size() {
    local file="$1"
    local exp_size="$2"
    if [ ! -f "$file" ]; then
        return 1
    fi
    local size
    size="$(stat -c %s "$file" 2>/dev/null || stat -f %z "$file" 2>/dev/null || echo 0)"
    if [ "$size" = "$exp_size" ]; then
        return 0
    else
        return 1
    fi
}

check_sha256() {
    local file="$1"
    local exp_hash="$2"
    if [ ! -f "$file" ]; then
        return 1
    fi
    echo "[*] Проверка SHA256 контрольной суммы для $file..."
    local actual_hash
    actual_hash="$(sha256sum "$file" | awk '{print $1}')"
    if [ "$actual_hash" = "$exp_hash" ]; then
        echo "[OK] SHA256 совпадает: $actual_hash"
        return 0
    else
        echo "[!] ОШИБКА: SHA256 не совпадает (получено $actual_hash, ожидалось $exp_hash)"
        return 1
    fi
}

# 1. Скачивание метаданных конвертации
if [ ! -f "$CONVERSION_FILENAME" ]; then
    echo "[*] Загрузка метаданных конвертации $CONVERSION_FILENAME..."
    curl -fsSL --retry 3 -o "$CONVERSION_FILENAME" "$CONVERSION_URL" || true
fi

# 2. Проверка и скачивание основного файла модели
if check_file_size "$MODEL_FILENAME" "$EXPECTED_SIZE"; then
    echo "[OK] Файл $MODEL_FILENAME уже присутствует и полностью совпадает по байтам ($EXPECTED_SIZE байт)."
else
    echo "[*] Запуск процедуры загрузки модели $MODEL_FILENAME..."

    # Попытка 1: aria2c в 16 потоков с докачкой
    if command -v aria2c >/dev/null 2>&1; then
        echo "[1/2] Загрузка через aria2c (16 потоков)..."
        aria2c \
            --file-allocation=none \
            --continue=true \
            --max-connection-per-server=16 \
            --split=16 \
            --min-split-size=10M \
            --summary-interval=15 \
            --out="$MODEL_FILENAME" \
            "$MODEL_URL" || true
    fi

    # Попытка 2: curl с возобновлением загрузки
    if ! check_file_size "$MODEL_FILENAME" "$EXPECTED_SIZE"; then
        echo "[2/2] Докачка через curl (флаг -C -)..."
        curl -fL -C - --progress-bar --retry 5 -o "$MODEL_FILENAME" "$MODEL_URL"
    fi

    # Валидация размера
    if ! check_file_size "$MODEL_FILENAME" "$EXPECTED_SIZE"; then
        CURRENT_SIZE="$(stat -c %s "$MODEL_FILENAME" 2>/dev/null || echo 0)"
        echo "[!] ОШИБКА: Размер $MODEL_FILENAME ($CURRENT_SIZE байт) не совпадает с ожидаемым ($EXPECTED_SIZE байт)!"
        exit 1
    fi
fi

# 3. Проверка целостности SHA256
if [ -f "${MODEL_FILENAME}.sha256_verified" ]; then
    echo "[OK] Контрольная сумма SHA256 уже была успешно проверена ранее."
else
    if check_sha256 "$MODEL_FILENAME" "$EXPECTED_SHA256"; then
        touch "${MODEL_FILENAME}.sha256_verified"
    else
        exit 1
    fi
fi

# 4. Обновление канонического симлинка
ln -sfn "$MODEL_FILENAME" "model_v100.ninfer"
echo "[OK] Символическая ссылка создана: $TARGET_DIR/model_v100.ninfer -> $MODEL_FILENAME"

echo "======================================================================"
echo " Загрузка и проверка успешно завершены!"
echo "======================================================================"
