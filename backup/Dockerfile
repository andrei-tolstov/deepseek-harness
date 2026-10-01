FROM alpine:3.20

# Установка необходимых утилит: rclone, tar, gzip, bash, tzdata, curl
RUN apk add --no-cache \
    bash \
    rclone \
    tar \
    gzip \
    tzdata \
    curl \
    coreutils

# Рабочая директория
WORKDIR /app

# Копирование скрипта резервного копирования
COPY backup.sh /app/backup.sh
RUN chmod +x /app/backup.sh

ENTRYPOINT ["/app/backup.sh"]
