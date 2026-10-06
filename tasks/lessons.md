# Lessons & Patterns

## Web Editors / Line Number Gutters
- **Схлопывание перевода строк в HTML**: Для элементов-контейнеров номеров строк (`div`), чье содержимое заполняется текстом с символами `\n` (`textContent = "1\n2\n..."`), свойство `white-space` по умолчанию равно `normal`. В этом режиме браузер схлопывает `\n` в пробелы и переносит числа по ширине блока (`1 2 3`, `4 5 6`...).
- **Правило**: Всегда указывать `white-space: pre;` (или `pre-line`), `flex-shrink: 0;`, `box-sizing: border-box;`, а также синхронизировать `line-height` и `padding-top` с основным полем ввода (`textarea`).
- **Скролл и UX**: Для контейнера номеров строк желательно пробрасывать событие `wheel` в основной редактор (`editor.scrollTop += e.deltaY`), а ширину колонки рассчитывать с запасом на разрядность общего количества строк (`digits * 8 + 24`).

## VS Code / code-server Workspace Files
- **EROFS на `.code-workspace`**: При открытии рабочей области VS Code автоматически пытается записать метаданные (workspace trust, состояние и настройки Workspace Settings) в сам файл `.code-workspace`. Если файл смонтирован из хоста как `:ro` или в системную директорию (`/etc/...`), это вызывает ошибку `EROFS: read-only file system`.
- **Правило**: Монтировать шаблон с хоста как шаблон, а на старте копировать его (`cp -u`) в домашнюю перезаписываемую директорию пользователя (`/home/coder/project.code-workspace`), принадлежащую пользователю контейнера (`1000:1000`).

## MCP 2.x & Docker Networks
- **DNS Rebinding Protection в MCP SDK 2.x**: В современных версиях `mcp` SDK (2.x) `streamable_http_app` по умолчанию включает валидацию заголовка `Host` (`TransportSecuritySettings`), пропуская только `localhost` и `127.0.0.1`. При обращении по имени сервиса в сети Docker (например, `Host: laya:8787`) сервер возвращает `421 Misdirected Request`.
- **Правило**: Для контейнеризированных MCP-серверов отключать проверку или настраивать `allowed_hosts`: `transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False)`.

## Ubuntu 22.04 Docker & Pip
- **Флаг `--break-system-packages`**: Отсутствует в базовом pip 22.0.2 дистрибутива Ubuntu 22.04 (PEP 668 появился в pip 23+). Передача флага приводит к ошибке `no such option: --break-system-packages`.
- **Правило**: Не передавать `--break-system-packages` на старых версиях pip до 23.0.

## Yandex Cloud GPU Quotas
- **Нулевая квота на GPU по умолчанию**: Создание ВМ с Tesla V100 (`gpu-standard-v2`) возвращает `ResourceExhausted: The limit on maximum number of GPU devices has exceeded` если квота `compute.instanceGpus.count` равна 0.
- **Правило**: Проверять квоты через `yc quota-manager quota-limit list --resource-type resource-manager.cloud --resource-id <cloud_id> --service compute`. Запрашивать увеличение через `yc quota-manager quota-request create --resource-type resource-manager.cloud --resource-id <cloud_id> --desired-limit quota-id=compute.instanceGpus.count,value=1` (базовые лимиты на 1 GPU одобряются автоматически).

## Llama.cpp / Llama-server CLI
- **Флаг Flash Attention**: В актуальных версиях `llama-server` аргумент `--flash-attn` принимает строковое значение (`--flash-attn on|off|auto`). Передача одиночного флага без значения приводит к захвату следующего аргумента (например, `-ctk`) как значения `--flash-attn` и ошибке парсера CLI.
- **Флаги памяти**: Флаги `--mlock`, `--no-mmap` в новых версиях сгруппированы в `--load-mode mlock|mmap|auto`. Кэширование промптов включено по умолчанию.


