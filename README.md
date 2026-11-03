# Стек: OmniRoute + AnyJev (Laya) + llama-swap + Резервное копирование на Google Диск

Готовый к запуску стек в Docker Compose, объединяющий:
1. **OmniRoute** — шлюз-роутер AI моделей (OpenAI, DeepSeek, Anthropic, OpenRouter, Groq и еще 350+ провайдеров) с автоматическим переключением (fallback), кэшированием, защитой от исчерпания лимитов и экономией токенов.
2. **Redis** — быстрое хранилище квот и состояний rate-limiting для OmniRoute.
3. **AnyJev (Laya System 1 Decision Studio)** — сверхбыстрый движок типизированного инференса решений (choice, score, noul) на базе модели `Tacit-4B-Q4_K_M.gguf` + `llama-server` с L0-дебиасингом. Предоставляет нативный REST API (`/v1/systemone`), Laya-совместимый эндпоинт (`/ask`) и классификатор тулсетов для агентов (`/v1/chat/completions`).
4. **llama-swap** — динамический супервизор и роутер переключения моделей на GPU (разделение 32GB VRAM Tesla V100 между LLM `coder390`, `fable`, `qwen38`, `bonsai2` и генерацией изображений `fluxed-up`, `juggernaut-xl`).
5. **Google Drive Backup** — автоматизированная служба резервного копирования на базе `rclone` и `crond`, которая архивирует конфигурации OmniRoute, директории DSH (`/root/harness/dsh`), а также синхронизирует штатные zip-архивы Hermes Agent (`/root/hermes_backup/hermes-backup-*.zip`) на Google Диск с автоматической ротацией.
6. **VS Code Web (code-server)** — веб-версия редактора Visual Studio Code в браузере с доступом к директориям `workspace`, DSH и Hermes Agent, встроенным терминалом и правами UID 1000.

---

## Архитектура системы

```
                               ┌───────────────────────────────────────────────┐
                               │                 Docker Network                │
                               │                (deepseek-net)                 │
                               │                                               │
    Пользователь               │  ┌──────────────────┐                         │
         │                     │  │   Redis 7        │                         │
         │                     │  │   (Кэш & Rate)   │                         │
         │                     │  └────────▲─────────┘                         │
         │                     │           │ internal                          │
         ▼                     │           ▼                                   │
[OmniRoute Dashboard] ───────►│  ┌──────────────────┐        Провайдеры       │
 http://127.0.0.1:20128       │  │    OmniRoute     │──────► DeepSeek API     │
                              │  │    (AI Router)   │──────► OpenAI, Claude   │
                              │  └────────▲─────────┘──────► OpenRouter, etc. │
                              │           │                                   │
                              │           │ http://omniroute:20128/v1         │
                              │           │ (внутренний адрес для агентов)    │
                              │           │                                   │
                              │           ▼                                   │
                              │  ┌──────────────────┐                         │
                              │  │    llama-swap    │──────► coder390 (:8084) │
                              │  │  (:8090 -> :8080)│──────► fable    (:8083) │
                              │  └────────▲─────────┘──────► flux/sd  (:8085) │
                              │           │                                   │
                              │           ▼                                   │
                              │  ┌──────────────────┐                         │
                              │  │ anyjev / laya    │                         │
                              │  │  (:8080, :8787)  │ (System 1 Decisions)    │
                              │  └──────────────────┘                         │
                              │           │                                   │
     Нативный стек             │           │ Тома данных (read-only)           │
     Harness (Хост)            │           ▼                                   │
     /root/harness/hermes ─────┼──►┌──────────────────┐                       │
     /root/harness/dsh    ─────┼──►│  Backup Service  │──────► Google Диск     │
                               │   │ (rclone + cron)  │      (зашифровано/gzip)│
                               │   └──────────────────┘                       │
                               └───────────────────────────────────────────────┘
```

---

## Быстрый старт

### 1. Подготовка конфигурации

Клонируйте проект и проверьте конфигурационный файл `.env`:
```bash
# Файл .env уже подготовлен с безопасными значениями по умолчанию
notepad .env
```

### 2. Настройка подключения к Google Диску (rclone)

Для настройки связи с Google Диском выполните интерактивный мастер:
```bash
docker compose run --rm backup rclone config
```
- Выберите `n` (New remote) -> имя `gdrive` -> тип хранилища `drive` -> подтвердите авторизацию через браузер.
- Конфигурация сохранится в `./backup/rclone.conf`.
- *Подробнее см. в [backup/README.md](file:///c:/Users/andrei/projects/deepseek-harness/backup/README.md).*

### 3. Сборка и запуск контейнеров

```bash
docker compose up -d --build
```

Проверить статус работы всех сервисов:
```bash
docker compose ps
```

---

## Доступ к сервисам

| Сервис | Адрес | Описание |
| :--- | :--- | :--- |
| **OmniRoute Dashboard** | [http://127.0.0.1:20128](http://127.0.0.1:20128) | Панель управления моделями, ключами и правилами маршрутизации |
| **OmniRoute API** | [http://127.0.0.1:20128](http://127.0.0.1:20128) | OpenAI-совместимый эндпоинт `/v1` |
| **llama-swap Web UI & API** | [http://127.0.0.1:8090](http://127.0.0.1:8090) (`/ui`, `/v1`) | Динамический роутер и супервизор переключения моделей на GPU |
| **VS Code Web (code-server)** | [http://127.0.0.1:8443](http://127.0.0.1:8443) | Полнофункциональный редактор кода в браузере с доступом к `workspace`, DSH и Hermes |
| **AnyJev (Laya Studio)** | [http://127.0.0.1:8080](http://127.0.0.1:8080) | Быстрый классификатор System 1 (`/v1/systemone`, `/ask`, `/v1/chat/completions`) |

---

## Использование AnyJev / Laya (быстрый классификатор / System 1)

AnyJev запускается на базе модели `Tacit-4B-Q4_K_M.gguf` и легковесного C++ бэкенда `llama-server`. Работает с Level 0 (L0) дебиасингом логитов априорного распределения и обеспечивает латентность решений ~120-180 мс на GPU.

### Эндпоинты AnyJev:
- **System 1 Decision API:** `POST http://127.0.0.1:8080/v1/systemone`
- **Laya Compatibility API:** `POST http://127.0.0.1:8080/ask`
- **Hermes Token Router Classifier:** `POST http://127.0.0.1:8080/v1/chat/completions` (или порт `:8787`)
- **Healthcheck:** `GET http://127.0.0.1:8080/health` (возвращает `503 Service Unavailable`, если C++ backend не готов)
- **Внутри сети Docker:** сервис доступен по именам `http://anyjev:8080` и `http://laya:8080`.

---

## Использование llama-swap (динамическое переключение GPU моделей)

[llama-swap](https://github.com/mostlygeek/llama-swap) интегрирован в docker-стек для разделения 32GB VRAM NVIDIA Tesla V100 между текстовыми LLM и диффузионными моделями генерации изображений:
- `coder390` (`coder390-llama-server`, порт 8084) — **основная текстовая модель** (NInfer V2 MTP + Vision, `ttl: 0`, всегда в горячей памяти).
- `fable` (`fable-llama-server`, порт 8083) — `ttl: 1200s` (20 минут).
- `qwen38` (`qwen38-llama-server`, порт 8081) — `ttl: 1200s` (20 минут).
- `bonsai2` (`bonsai2-llama-server`, порт 8082) — `ttl: 1200s` (20 минут).
- `fluxed-up` (`fluxed-up-sd-server`, порт 8085) — генерация изображений FLUX.1 Dev Fluxed Up (`ttl: 5s`, ~22.7 ГБ VRAM в Q8_0/Q4_0 с FlashAttention).
- `juggernaut-xl` (`juggernaut-sd-server`, порт 8086) — генерация изображений Juggernaut XL v9+ (`ttl: 5s`, ~10.9 ГБ VRAM в FP16).

### Принцип работы:
1. При поступлении запроса от OmniRoute, Hermes Agent или других клиентов:
   - `llama-swap` останавливает активный контейнер (`docker stop -t 5`).
   - Запускает запрашиваемый контейнер (`docker start -a`) и ожидает прохождения healthcheck.
   - Проксирует запросы на соответствующий порт модели (включая эндпоинт генерации картинок `POST /v1/images/generations`).
2. **Агентный цикл генерации и проверки изображений (`ttl: 5s` + `watchdog 5s`):**
   - Для диффузионных моделей установлен `ttl: 5s`. Сразу после завершения генерации VRAM освобождается.
   - Сторожевой демон (`watchdog`) проверяет состояние VRAM каждые 5 секунд и автоматически возвращает основную модель `coder390` в память, чтобы она могла мгновенно проанализировать полученный результат через Vision.
3. **Эндпоинты:**
   - **Web UI & Playground:** `http://127.0.0.1:8090/ui`
   - **OpenAI API (Chat & Image Generations):** `http://127.0.0.1:8090/v1`
   - **Внутри сети Docker (для OmniRoute):** `http://llama-swap:8080/v1`
   - **Интеграция с Hermes Agent:** прямое подключение инструмента `image_gen` к `http://192.168.50.38:8090/v1`.

---

## Связка с OmniRoute

Hermes Agent и DeepSeek Harness могут обращаться к моделям через OmniRoute по внутренней сети Docker:
- **Base URL:** `http://omniroute:20128/v1` *(внутренний порт в Docker сети)*
- **API Key:** ваш ключ из OmniRoute (или любое значение, если `REQUIRE_API_KEY=false`).

---

## Управление резервными копиями

Резервное копирование выполняется автоматически по расписанию через cron (по умолчанию каждый день в 15:00 по МСК, параметр `BACKUP_CRON_SCHEDULE`).

### Ручной запуск бэкапа
```bash
docker compose exec backup /app/backup.sh now
```

### Просмотр списка бэкапов на Google Диске
```bash
docker compose run --rm backup list
```

### Восстановление из архива
1. Остановите сервисы:
   ```bash
   docker compose stop omniroute
   ```
2. Скачайте нужный архив с Google Диска в локальную директорию и распакуйте:
   ```bash
   docker compose run --rm -v ./backups:/host_backups backup rclone copy gdrive:backups/deepseek-stack/backup_XXXXXXXX_XXXXXX.tar.gz /host_backups/
   docker compose run --rm -v ./backups:/host_backups -v omniroute-data:/data/omniroute backup tar -xzf /host_backups/backup_XXXXXXXX_XXXXXX.tar.gz -C /data
   ```
3. Запустите сервисы:
   ```bash
   docker compose start
   ```

---

## Безопасность

- По умолчанию все порты привязаны к `127.0.0.1` (`HOST_BIND_IP` в `.env`), предотвращая несанкционированный доступ из локальной сети или интернета к сервисам с доступом к хосту.
- Redis изолирован внутри сети Docker `deepseek-net` и не публикует порты на хост-машину.
