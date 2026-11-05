# Стек: AnyJev (Laya System 1) + llama-swap + Резервное копирование на Google Диск

Готовый к запуску стек в Docker Compose для локального инференса LLM, генерации изображений и принятия решений:
1. **llama-swap** — динамический супервизор и роутер переключения моделей на GPU (разделение 32GB VRAM NVIDIA Tesla V100 между LLM `coder390`, `fable`, `qwen38` и диффузионными генераторами изображений `qwen-image`, `fluxed-up`, `juggernaut-xl`).
2. **AnyJev (Laya System 1 Decision Studio)** — сверхбыстрый движок типизированного инференса решений (choice, score, noul) на базе модели `Tacit-4B-Q4_K_M.gguf` + `llama-server` с L0-дебиасингом. Задержка ~120–240 мс на GPU (GTX 1060 3GB). Предоставляет REST API (`/v1/systemone`), Laya-совместимый эндпоинт (`/ask`), классификатор тулсетов (`/v1/chat/completions`) и нативный MCP сервер (`:8787`).
3. **Google Drive Backup** — автоматизированная служба резервного копирования на базе `rclone` и `crond`, архивирующая директории DSH (`/root/harness/dsh`) и синхронизирующая штатные zip-архивы Hermes Agent (`/root/hermes_backup/hermes-backup-*.zip`) на Google Диск с автоматической ротацией.
4. **VS Code Web (code-server)** — полнофункциональный редактор Visual Studio Code в браузере с доступом к директориям `workspace`, DSH и Hermes Agent, встроенным терминалом и правами UID 1000.

---

## Архитектура системы

```
                               ┌───────────────────────────────────────────────┐
                               │                 Docker Network                │
                               │                (deepseek-net)                 │
                               │                                               │
    Клиенты (Hermes / LAN)     │  ┌──────────────────┐                         │
          │                    │  │    llama-swap    │──────► coder390 (:8084) │
          ├───────────────────►│  │  (:8090 -> :8080)│──────► fable    (:8083) │
          │  OpenAI /v1 API    │  │                  │──────► qwen38   (:8081) │
          │  Image Generations │  │                  │──────► qwen-img (:8088) │
          │                    │  │                  │──────► flux     (:8085) │
          │                    │  └──────────────────┘──────► sdxl     (:8086) │
          │                    │                                               │
          │                    │  ┌──────────────────┐                         │
          └───────────────────►│  │ anyjev / laya    │                         │
             System 1 Decision │  │  (:8080, :8787)  │ (Tacit-4B Decisions)    │
             & MCP Tools       │  └──────────────────┘                         │
                               │           │                                   │
      Хост-система             │           │ Тома данных (read-only)           │
      /root/hermes_backup ─────┼──►┌──────────────────┐                       │
      /root/harness/dsh   ─────┼──►│  Backup Service  │──────► Google Диск     │
                               │   │ (rclone + cron)  │      (зашифровано/gzip)│
                               │   └──────────────────┘                       │
                               └───────────────────────────────────────────────┘
```

---

## Быстрый старт

### 1. Подготовка конфигурации

Клонируйте проект и проверьте конфигурационный файл `.env`:
```bash
# Файл .env подготовлен со значениями по умолчанию
cp .env.example .env
nano .env
```

### 2. Настройка подключения к Google Диску (rclone)

Для настройки связи с Google Диском выполните интерактивный мастер:
```bash
docker compose run --rm backup rclone config
```
- Выберите `n` (New remote) -> имя `gdrive` -> тип хранилища `drive` -> подтвердите авторизацию через браузер.
- Конфигурация сохранится в `./backup/rclone.conf`.

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
| **llama-swap Web UI & API** | [http://127.0.0.1:8090](http://127.0.0.1:8090) (`/ui`, `/v1`) | Динамический роутер и супервизор переключения моделей на GPU |
| **AnyJev (Laya Studio & REST)** | [http://127.0.0.1:8080](http://127.0.0.1:8080) | Классификатор System 1 (`/v1/systemone`, `/ask`, `/v1/chat/completions`) |
| **AnyJev MCP Server** | [http://127.0.0.1:8787](http://127.0.0.1:8787) (`/sse`) | MCP интерфейс принятия решений для агентов (Hermes, Claude, Cursor) |
| **VS Code Web (code-server)** | [http://127.0.0.1:8443](http://127.0.0.1:8443) | Редактор кода в браузере с доступом к `workspace`, DSH и Hermes |

---

## Использование llama-swap (динамическое переключение GPU моделей)

[llama-swap](https://github.com/mostlygeek/llama-swap) интегрирован в docker-стек для разделения 32GB VRAM NVIDIA Tesla V100 между текстовыми LLM и диффузионными моделями генерации изображений:
- `coder390` (`coder390-llama-server`, порт 8084) — **основная текстовая модель** (Qwen3.8 27B Coder390 EfficientThink, NInfer V2 MTP + Vision, `ttl: 0`, всегда в горячей памяти).
- `fable` (`fable-llama-server`, порт 8083) — DavidAU Qwen3.8 27B Fable Cold Fusion (`ttl: 1200s` / 20 минут).
- `qwen38` (`qwen38-llama-server`, порт 8081) — HauhauCS Qwen3.8 27B Aggressive MTP (`ttl: 1200s` / 20 минут).
- `qwen-image` (`qwen-image-sd-server`, порт 8088) — **Qwen-Image-2.1-Turbo Uncensored** (`ttl: 5s`, Denoiser Q8_0 + Uncensored LLM Q8_0 + Projector F16 + VAE, 8 шагов Turbo, сэмплер Euler с калиброванным sigma-расписанием, ~16.9 ГБ VRAM).
- `fluxed-up` (`fluxed-up-sd-server`, порт 8085) — генерация изображений FLUX.1 Dev Fluxed Up (`ttl: 5s`, ~22.7 ГБ VRAM в Q8_0/Q4_0 с FlashAttention).
- `juggernaut-xl` (`juggernaut-sd-server`, порт 8086) — генерация изображений Juggernaut XL v9+ (`ttl: 5s`, ~10.9 ГБ VRAM в FP16).

### Принцип работы:
1. При поступлении запроса от Hermes Agent или других клиентов:
   - `llama-swap` останавливает активный контейнер (`docker stop -t 5`).
   - Запускает запрашиваемый контейнер (`docker start -a`) и ожидает прохождения healthcheck.
   - Проксирует запросы на соответствующий порт модели (включая эндпоинт генерации картинок `POST /v1/images/generations`).
2. **Агентный цикл генерации и проверки изображений (`ttl: 5s` + `watchdog 5s`):**
   - Для диффузионных моделей установлен `ttl: 5s`. Сразу после завершения генерации VRAM освобождается.
   - Сторожевой демон (`watchdog`) проверяет состояние VRAM каждые 5 секунд и автоматически возвращает основную модель `coder390` в память, чтобы она могла мгновенно проанализировать полученный результат через встроенный Vision-проектор.
3. **Эндпоинты:**
   - **Web UI & Playground:** `http://127.0.0.1:8090/ui`
   - **OpenAI API (Chat & Image Generations):** `http://127.0.0.1:8090/v1`
   - **Интеграция с Hermes Agent:** прямое подключение в `~/.hermes/config.yaml`:
     ```yaml
     image_gen:
       provider: openai
       model: qwen-image
       openai:
         provider: llama-swap
         model: qwen-image
         base_url: http://192.168.50.38:8090/v1
         api_key: dummy
     ```

---

## Использование AnyJev / Laya (быстрый классификатор / System 1)

AnyJev запускается на базе модели `Tacit-4B-Q4_K_M.gguf` и легковесного C++ бэкенда `llama-server`. Работает с Level 0 (L0) дебиасингом логитов априорного распределения и обеспечивает латентность решений ~120-180 мс на GPU (GTX 1060 3GB).

### Эндпоинты AnyJev:
- **System 1 Decision API:** `POST http://127.0.0.1:8080/v1/systemone`
- **Laya Compatibility API:** `POST http://127.0.0.1:8080/ask`
- **Hermes Token Router Classifier:** `POST http://127.0.0.1:8080/v1/chat/completions`
- **MCP Server:** `http://127.0.0.1:8787/sse`
- **Healthcheck:** `GET http://127.0.0.1:8080/health`
- **Внутри сети Docker:** сервис доступен по именам `http://anyjev:8080` и `http://laya:8080`.

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

---

## Безопасность

- По умолчанию порты могут быть привязаны к `127.0.0.1` (`HOST_BIND_IP` в `.env`) для локального доступа, либо к `0.0.0.0` для доступа внутри защищенной локальной сети.
