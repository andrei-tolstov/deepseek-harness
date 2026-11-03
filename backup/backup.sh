#!/bin/bash
set -e

# Настройки по умолчанию
RCLONE_REMOTE="${RCLONE_REMOTE:-gdrive}"
RCLONE_DEST_FOLDER="${RCLONE_DEST_FOLDER:-backups/deepseek-stack}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
MIN_BACKUPS_TO_KEEP="${MIN_BACKUPS_TO_KEEP:-3}"
BACKUP_CRON_SCHEDULE="${BACKUP_CRON_SCHEDULE:-0 15 * * *}"
BACKUP_ON_STARTUP="${BACKUP_ON_STARTUP:-false}"
BACKUP_TEMP_DIR="/tmp/backups"

# Настройки бэкапа Hermes
HERMES_BACKUP_DIR="${HERMES_BACKUP_DIR:-/hermes_backup}"
HERMES_DEST_FOLDER="${HERMES_DEST_FOLDER:-${RCLONE_DEST_FOLDER}}"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

check_rclone_config() {
    if ! rclone listremotes | grep -q "^${RCLONE_REMOTE}:"; then
        log "ВНИМАНИЕ: Remote '${RCLONE_REMOTE}:' не найден в конфигурации rclone!"
        log "Пожалуйста, настройте подключение к Google Диску:"
        log "1. Запустите: docker compose run --rm backup rclone config"
        log "2. Или добавьте конфигурацию в ./backup/rclone.conf"
        return 1
    fi
    return 0
}

perform_stack_backup() {
    log "--- Создание архива стека (/data: OmniRoute, DSH) ---"

    mkdir -p "${BACKUP_TEMP_DIR}"
    TIMESTAMP=$(date '+%Y%m%d_%H%M%S')
    ARCHIVE_NAME="backup_${TIMESTAMP}.tar.gz"
    ARCHIVE_PATH="${BACKUP_TEMP_DIR}/${ARCHIVE_NAME}"

    # Проверяем наличие данных
    if [ ! -d "/data" ] || [ -z "$(ls -A /data 2>/dev/null)" ]; then
        log "Предупреждение: Директория /data пуста или не существует!"
    fi

    log "Создание архива: ${ARCHIVE_NAME}..."
    tar --warning=no-file-changed -czf "${ARCHIVE_PATH}" -C /data . || [ $? -eq 1 ]

    ARCHIVE_SIZE=$(du -h "${ARCHIVE_PATH}" | cut -f1)
    log "Архив успешно создан. Размер: ${ARCHIVE_SIZE}"

    log "Загрузка архива на Google Диск: ${RCLONE_REMOTE}:${RCLONE_DEST_FOLDER}/${ARCHIVE_NAME}..."
    if rclone copy "${ARCHIVE_PATH}" "${RCLONE_REMOTE}:${RCLONE_DEST_FOLDER}/" --progress; then
        log "Загрузка архива стека завершена успешно!"
    else
        log "Ошибка при загрузке архива в Google Диск!"
        rm -f "${ARCHIVE_PATH}"
        return 1
    fi

    # Очистка локального временного файла
    rm -f "${ARCHIVE_PATH}"

    # Удаление старых резервных копий на Google Диске (ротация с защитой минимального числа бэкапов)
    if [ "${RETENTION_DAYS}" -gt 0 ]; then
        log "Проверка резервных копий стека для ротации (срок: ${RETENTION_DAYS} дн., минимум: ${MIN_BACKUPS_TO_KEEP})..."

        ALL_BACKUPS=$(rclone lsf "${RCLONE_REMOTE}:${RCLONE_DEST_FOLDER}" --files-only 2>/dev/null | grep -E '^backup_.*\.tar\.gz$' | sort || true)

        if [ -z "${ALL_BACKUPS}" ]; then
            TOTAL_BACKUPS=0
        else
            TOTAL_BACKUPS=$(echo "${ALL_BACKUPS}" | grep -c . || true)
        fi

        log "Всего резервных копий стека на Google Диске: ${TOTAL_BACKUPS}"

        if [ "${TOTAL_BACKUPS}" -le "${MIN_BACKUPS_TO_KEEP}" ]; then
            log "Обнаружено ${TOTAL_BACKUPS} бэкап(ов) (<= ${MIN_BACKUPS_TO_KEEP}). Удаление не производится даже при превышении срока ${RETENTION_DAYS} дн."
        else
            OLD_BACKUPS=$(rclone lsf "${RCLONE_REMOTE}:${RCLONE_DEST_FOLDER}" --files-only --min-age "${RETENTION_DAYS}d" 2>/dev/null | grep -E '^backup_.*\.tar\.gz$' | sort || true)

            if [ -n "${OLD_BACKUPS}" ]; then
                MAX_DELETABLE=$(( TOTAL_BACKUPS - MIN_BACKUPS_TO_KEEP ))
                FILES_TO_DELETE=$(echo "${OLD_BACKUPS}" | head -n "${MAX_DELETABLE}")

                echo "${FILES_TO_DELETE}" | while IFS= read -r file; do
                    if [ -n "${file}" ]; then
                        log "Удаление устаревшей копии стека: ${file}"
                        rclone deletefile "${RCLONE_REMOTE}:${RCLONE_DEST_FOLDER}/${file}" || true
                    fi
                done
                log "Ротация бэкапов стека завершена (сохранено как минимум ${MIN_BACKUPS_TO_KEEP} последних копий)."
            else
                log "Устаревших бэкапов стека (старше ${RETENTION_DAYS} дн.) не найдено."
            fi
        fi
    fi

    return 0
}

perform_hermes_backup() {
    log "--- Обработка резервных копий Hermes Agent ---"

    if [ ! -d "${HERMES_BACKUP_DIR}" ]; then
        log "Предупреждение: Директория архивов Hermes '${HERMES_BACKUP_DIR}' не существует!"
    fi

    # Ищем самый свежий архив hermes-backup-*.zip в исходном каталоге
    LATEST_LOCAL=$(ls "${HERMES_BACKUP_DIR}"/hermes-backup-*.zip 2>/dev/null | sort -V | tail -n 1 || true)

    if [ -n "${LATEST_LOCAL}" ] && [ -f "${LATEST_LOCAL}" ]; then
        ARCHIVE_NAME=$(basename "${LATEST_LOCAL}")
        ARCHIVE_SIZE=$(du -h "${LATEST_LOCAL}" | cut -f1)
        log "Найден последний локальный архив Hermes: ${ARCHIVE_NAME} (${ARCHIVE_SIZE})"

        log "Копирование архива Hermes на Google Диск: ${RCLONE_REMOTE}:${HERMES_DEST_FOLDER}/${ARCHIVE_NAME}..."
        if rclone copy "${LATEST_LOCAL}" "${RCLONE_REMOTE}:${HERMES_DEST_FOLDER}/" --progress; then
            log "Архив Hermes успешно скопирован на Google Диск."
        else
            log "Ошибка при копировании архива Hermes на Google Диск!"
            return 1
        fi
    else
        log "Предупреждение: В исходном каталоге '${HERMES_BACKUP_DIR}' отсутствуют архивы hermes-backup-*.zip!"
    fi

    # Ротация на Google Диске:
    # Требование: хранить ровно 1 самый последний архив.
    # Если в исходном каталоге пусто — гарантировать сохранение хотя бы одной копии на Google Диске.
    log "Проверка архивов Hermes на Google Диск для ротации (хранение 1 последней копии)..."
    REMOTE_BACKUPS=$(rclone lsf "${RCLONE_REMOTE}:${HERMES_DEST_FOLDER}" --files-only 2>/dev/null | grep -E '^hermes-backup-.*\.zip$' | sort -V || true)

    if [ -z "${REMOTE_BACKUPS}" ]; then
        TOTAL_REMOTE=0
    else
        TOTAL_REMOTE=$(echo "${REMOTE_BACKUPS}" | grep -c . || true)
    fi

    log "Всего архивов Hermes на Google Диске: ${TOTAL_REMOTE}"

    if [ "${TOTAL_REMOTE}" -le 1 ]; then
        if [ "${TOTAL_REMOTE}" -eq 1 ]; then
            log "На Google Диске сохранена 1 актуальная копия Hermes (${REMOTE_BACKUPS}). Удаление не требуется."
        else
            log "Внимание: На Google Диске нет ни одной копии Hermes!"
        fi
    else
        # На Диске больше 1 копии: оставляем ровно 1 последнюю (tail -n 1), удаляем более старые
        DELETE_COUNT=$(( TOTAL_REMOTE - 1 ))
        FILES_TO_DELETE=$(echo "${REMOTE_BACKUPS}" | head -n "${DELETE_COUNT}")
        LATEST_KEEP=$(echo "${REMOTE_BACKUPS}" | tail -n 1)

        log "Найдено ${TOTAL_REMOTE} копий на Google Диске. Сохраняем свежую копию: ${LATEST_KEEP}"
        echo "${FILES_TO_DELETE}" | while IFS= read -r file; do
            if [ -n "${file}" ]; then
                log "Удаление устаревшей копии Hermes: ${file}"
                rclone deletefile "${RCLONE_REMOTE}:${HERMES_DEST_FOLDER}/${file}" || true
            fi
        done
        log "Ротация завершена: на Google Диске сохранена 1 последняя копия Hermes."
    fi

    return 0
}

perform_backup() {
    log "=== Запуск резервного копирования ==="

    if ! check_rclone_config; then
        log "Ошибка: пропуск бэкапа из-за отсутствия конфигурации rclone."
        return 1
    fi

    local status=0
    perform_stack_backup || status=1
    perform_hermes_backup || status=1

    if [ "${status}" -eq 0 ]; then
        log "=== Резервное копирование завершено успешно ==="
    else
        log "=== Резервное копирование завершено с предупреждениями/ошибками ==="
    fi
    return "${status}"
}

# Обработка аргументов командной строки
case "$1" in
    now|backup)
        perform_backup
        exit $?
        ;;
    hermes)
        check_rclone_config && perform_hermes_backup
        exit $?
        ;;
    stack)
        check_rclone_config && perform_stack_backup
        exit $?
        ;;
    list)
        check_rclone_config && rclone ls "${RCLONE_REMOTE}:${RCLONE_DEST_FOLDER}"
        exit $?
        ;;
    rclone)
        shift
        exec rclone "$@"
        ;;
    *)
        log "Инициализация службы резервного копирования..."
        check_rclone_config || true

        if [ "${BACKUP_ON_STARTUP}" = "true" ]; then
            log "Выполнение бэкапа при запуске контейнера..."
            perform_backup || true
        fi

        log "Настройка планировщика cron: '${BACKUP_CRON_SCHEDULE}'"
        echo "${BACKUP_CRON_SCHEDULE} /app/backup.sh now >> /proc/1/fd/1 2>> /proc/1/fd/2" > /etc/crontabs/root

        log "Запуск crond..."
        exec crond -f -l 2
        ;;
esac
