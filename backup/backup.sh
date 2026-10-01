#!/bin/bash
set -e

# Настройки по умолчанию
RCLONE_REMOTE="${RCLONE_REMOTE:-gdrive}"
RCLONE_DEST_FOLDER="${RCLONE_DEST_FOLDER:-backups/deepseek-stack}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
MIN_BACKUPS_TO_KEEP="${MIN_BACKUPS_TO_KEEP:-3}"
BACKUP_CRON_SCHEDULE="${BACKUP_CRON_SCHEDULE:-0 3 * * *}"
BACKUP_ON_STARTUP="${BACKUP_ON_STARTUP:-false}"
BACKUP_TEMP_DIR="/tmp/backups"

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

perform_backup() {
    log "=== Запуск резервного копирования ==="

    if ! check_rclone_config; then
        log "Ошибка: пропуск бэкапа из-за отсутствия конфигурации rclone."
        return 1
    fi

    mkdir -p "${BACKUP_TEMP_DIR}"
    TIMESTAMP=$(date '+%Y%m%d_%H%M%S')
    ARCHIVE_NAME="backup_${TIMESTAMP}.tar.gz"
    ARCHIVE_PATH="${BACKUP_TEMP_DIR}/${ARCHIVE_NAME}"

    log "Создание архива: ${ARCHIVE_NAME}..."

    # Проверяем наличие данных
    if [ ! -d "/data" ] || [ -z "$(ls -A /data 2>/dev/null)" ]; then
        log "Предупреждение: Директория /data пуста или не существует!"
    fi

    # Архивируем содержимое директории /data
    tar -czf "${ARCHIVE_PATH}" -C /data .

    ARCHIVE_SIZE=$(du -h "${ARCHIVE_PATH}" | cut -f1)
    log "Архив успешно создан. Размер: ${ARCHIVE_SIZE}"

    log "Загрузка архива на Google Диск: ${RCLONE_REMOTE}:${RCLONE_DEST_FOLDER}/${ARCHIVE_NAME}..."
    if rclone copy "${ARCHIVE_PATH}" "${RCLONE_REMOTE}:${RCLONE_DEST_FOLDER}/" --progress; then
        log "Загрузка завершена успешно!"
    else
        log "Ошибка при загрузке архива в Google Диск!"
        rm -f "${ARCHIVE_PATH}"
        return 1
    fi

    # Очистка локального временного файла
    rm -f "${ARCHIVE_PATH}"

    # Удаление старых резервных копий на Google Диске (ротация с защитой минимального числа бэкапов)
    if [ "${RETENTION_DAYS}" -gt 0 ]; then
        log "Проверка резервных копий для ротации (срок хранения: ${RETENTION_DAYS} дн., гарантированный минимум: ${MIN_BACKUPS_TO_KEEP})..."

        # Список всех бэкапов в алфавитном порядке (соответствует хронологическому)
        ALL_BACKUPS=$(rclone lsf "${RCLONE_REMOTE}:${RCLONE_DEST_FOLDER}" --files-only 2>/dev/null | grep -E '^backup_.*\.tar\.gz$' | sort || true)
        
        if [ -z "${ALL_BACKUPS}" ]; then
            TOTAL_BACKUPS=0
        else
            TOTAL_BACKUPS=$(echo "${ALL_BACKUPS}" | grep -c . || true)
        fi

        log "Всего резервных копий на Google Диске: ${TOTAL_BACKUPS}"

        if [ "${TOTAL_BACKUPS}" -le "${MIN_BACKUPS_TO_KEEP}" ]; then
            log "Обнаружено ${TOTAL_BACKUPS} бэкап(ов) (<= ${MIN_BACKUPS_TO_KEEP}). Удаление не производится даже при превышении срока ${RETENTION_DAYS} дн."
        else
            # Ищем бэкапы старше RETENTION_DAYS
            OLD_BACKUPS=$(rclone lsf "${RCLONE_REMOTE}:${RCLONE_DEST_FOLDER}" --files-only --min-age "${RETENTION_DAYS}d" 2>/dev/null | grep -E '^backup_.*\.tar\.gz$' | sort || true)

            if [ -n "${OLD_BACKUPS}" ]; then
                # Лимит на удаление, чтобы осталось как минимум MIN_BACKUPS_TO_KEEP самых свежих копий
                MAX_DELETABLE=$(( TOTAL_BACKUPS - MIN_BACKUPS_TO_KEEP ))
                FILES_TO_DELETE=$(echo "${OLD_BACKUPS}" | head -n "${MAX_DELETABLE}")

                echo "${FILES_TO_DELETE}" | while IFS= read -r file; do
                    if [ -n "${file}" ]; then
                        log "Удаление устаревшей копии: ${file}"
                        rclone deletefile "${RCLONE_REMOTE}:${RCLONE_DEST_FOLDER}/${file}" || true
                    fi
                done
                log "Ротация завершена. На Google Диске сохранено как минимум ${MIN_BACKUPS_TO_KEEP} последних копий."
            else
                log "Устаревших бэкапов (старше ${RETENTION_DAYS} дн.) не найдено."
            fi
        fi
    fi

    log "=== Резервное копирование завершено успешно ==="
}

# Обработка аргументов командной строки
case "$1" in
    now|backup)
        perform_backup
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
