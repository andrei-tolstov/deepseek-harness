#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="${1:-${MODEL_DIR:-${SCRIPT_DIR}}}"

mkdir -p "$TARGET_DIR"
cd "$TARGET_DIR"

HF_REPO="nerkyor/Qwen3.8-27B-Coder390-EfficientThink-Opus5.5-GPT6Astra-Grok4.7-DSV4Pro-K3-SFT-RLOO-NVFP4-NInfer"
MODEL_REL_PATH="NVFP4-NInfer/W4A4-W8A8/Qwen3.8-27B-Coder390-EfficientThink-NVFP4-W4A4-W8A8-MTP-NInferV2.ninfer"
MODEL_FILENAME="$(basename "$MODEL_REL_PATH")"
HF_DIRECT_URL="https://huggingface.co/${HF_REPO}/resolve/main/${MODEL_REL_PATH}"

# Точный размер с Hugging Face (~20.01 GiB / 21.49 GB)
FALLBACK_EXPECTED_SIZE="21490955393"

echo "======================================================================"
echo " Загрузка Qwen3.8-27B Coder390 (NInfer V2 MTP, W4A4-W8A8)"
echo " Репозиторий       : $HF_REPO"
echo " Файл модели       : $MODEL_FILENAME"
echo " Целевая папка     : $TARGET_DIR"
echo "======================================================================"

# Получаем точный размер файла напрямую с Hugging Face через Content-Length
echo "[*] Проверка размера удаленного файла на Hugging Face..."
REMOTE_SIZE=$(curl -sIL "$HF_DIRECT_URL" | grep -i '^content-length:' | tail -n 1 | awk '{print $2}' | tr -d '\r')

if [ -n "$REMOTE_SIZE" ] && [ "$REMOTE_SIZE" -gt 1000000000 ] 2>/dev/null; then
    EXPECTED_SIZE="$REMOTE_SIZE"
    echo "[OK] Размер с сервера HF: $(awk "BEGIN {printf \"%.2f\", $EXPECTED_SIZE/1024/1024/1024}") GiB ($EXPECTED_SIZE байт)"
else
    EXPECTED_SIZE="$FALLBACK_EXPECTED_SIZE"
    echo "[!] Не удалось получить Content-Length по сети, взят эталон: $EXPECTED_SIZE байт"
fi

check_file_validity() {
    local file="$1"
    if [ ! -f "$file" ]; then
        return 1
    fi
    local size
    size="$(stat -c %s "$file" 2>/dev/null || stat -f %z "$file" 2>/dev/null || echo 0)"
    if [ "$size" = "$EXPECTED_SIZE" ]; then
        return 0
    else
        return 1
    fi
}

if check_file_validity "$MODEL_FILENAME"; then
    echo "[OK] Файл $MODEL_FILENAME уже существует и полностью совпадает по байтам."
else
    echo "[*] Файл отсутствует или не докачан. Запуск процедуры загрузки..."

    # 1. Быстрое скачивание через aria2c в 16 потоков с докачкой
    if command -v aria2c >/dev/null 2>&1; then
        echo "[1/3] Попытка через aria2c (16 параллельных соединений)..."
        aria2c \
            --file-allocation=none \
            --continue=true \
            --max-connection-per-server=16 \
            --split=16 \
            --min-split-size=10M \
            --summary-interval=15 \
            --out="$MODEL_FILENAME" \
            "$HF_DIRECT_URL" || true
    fi

    # 2. Fallback через официальный Hugging Face CLI
    if ! check_file_validity "$MODEL_FILENAME"; then
        if command -v hf >/dev/null 2>&1 || command -v huggingface-cli >/dev/null 2>&1; then
            echo "[2/3] Загрузка через huggingface-cli..."
            HF_CMD="$(command -v hf 2>/dev/null || command -v huggingface-cli 2>/dev/null)"
            $HF_CMD download "$HF_REPO" "$MODEL_REL_PATH" --local-dir ./tmp_dl
            if [ -f "./tmp_dl/$MODEL_REL_PATH" ]; then
                mv "./tmp_dl/$MODEL_REL_PATH" "./$MODEL_FILENAME"
                rm -rf ./tmp_dl
            fi
        fi
    fi

    # 3. Fallback через стандартный curl с возобновлением загрузки
    if ! check_file_validity "$MODEL_FILENAME"; then
        echo "[3/3] Докачка через curl (флаг -C -)..."
        curl -L -C - --progress-bar -o "$MODEL_FILENAME" "$HF_DIRECT_URL"
    fi

    # Финальная валидация размера перед созданием ссылки
    echo "======================================================================"
    echo " Проверка целостности..."
    echo "======================================================================"
    CURRENT_SIZE="$(stat -c %s "$MODEL_FILENAME" 2>/dev/null || stat -f %z "$MODEL_FILENAME" 2>/dev/null || echo 0)"
    if [ "$CURRENT_SIZE" != "$EXPECTED_SIZE" ]; then
        echo "ОШИБКА: Размер файла ($CURRENT_SIZE байт) не равен ожидаемому ($EXPECTED_SIZE байт)!"
        exit 1
    fi
    echo "[OK] Размер полностью подтвержден: $CURRENT_SIZE байт."
fi

# Привязка канонического симлинка для Docker Compose
ln -sfn "$MODEL_FILENAME" "model_v100.ninfer"
echo "[OK] Симлинк обновлен: $TARGET_DIR/model_v100.ninfer -> $MODEL_FILENAME"

echo "======================================================================"
echo " Готово к запуску! Выполните:"
echo "   docker compose restart"
echo "======================================================================"
