# Стек: DeepSeek Harness + OmniRoute + Резервное копирование на Google Диск

Готовый к запуску стек в Docker Compose, объединяющий:
1. **DeepSeek Harness (`dsh`)** — автономная среда выполнения AI-агентов от DeepSeek AI с веб-интерфейсом и встроенным VNC-десктопом для браузерных задач.
2. **OmniRoute** — шлюз-роутер AI моделей (OpenAI, DeepSeek, Anthropic, OpenRouter, Groq и еще 350+ провайдеров) с автоматическим переключением (fallback), кэшированием, защитой от исчерпания лимитов и экономией токенов.
3. **Redis** — быстрое хранилище квот и состояний rate-limiting для OmniRoute.
4. **Google Drive Backup** — автоматизированная служба резервного копирования на базе `rclone` и `crond`, которая архивирует базы данных, ключи провайдеров, сессии агента и выгружает архивы на Google Диск с автоматической ротацией старых копий.

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
                              │           │ http://omniroute:20129/v1         │
                              │           │ (внутренний адрес для агента)     │
        ▼                     │           │                                   │
[DeepSeek Harness Web] ──────►│  ┌────────┴─────────┐                         │
 http://127.0.0.1:3080        │  │ DeepSeek Harness │                         │
 (Desktop: :6080)             │  │   (AI Агент)     │                         │
                              │  └────────┬─────────┘                         │
                              │           │                                   │
                              │           │ Тома данных (read-only)           │
                              │           ▼                                   │
                              │  ┌──────────────────┐                         │
                              │  │  Backup Service  │──────► Google Диск      │
                              │  │ (rclone + cron)  │      (зашифровано/gzip) │
                              │  └──────────────────┘                         │
                              └───────────────────────────────────────────────┘
```

---

## Быстрый старт

### 1. Подготовка конфигурации

Клонируйте проект и проверьте конфигурационный файл `.env`:
```bash
# Файл .env уже подготовлен с безопасными значениями по умолчанию
# При необходимости отредактируйте параметры:
notepad .env
```

### 2. Настройка подключения к Google Диску (rclone)

Для настройки связи с Google Диском выполните интерактивный мастер:
```bash
docker compose run --rm backup rclone config
```
- Выберите `n` (New remote) -> имя `gdrive` -> тип хранилища `drive` -> подтвердите авторизацию через браузер.
- Конфигурация сохранится в `./backup/rclone.conf`.
- *Подробнее о других способах (например, через сервисный аккаунт Google Cloud) см. в [backup/README.md](file:///c:/Users/andrei/projects/deepseek-harness/backup/README.md).*

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
| **OmniRoute API** | [http://127.0.0.1:20129](http://127.0.0.1:20129) | OpenAI-совместимый эндпоинт `/v1` |
| **DeepSeek Harness Web UI** | [http://127.0.0.1:3080](http://127.0.0.1:3080) | Веб-интерфейс автономного AI-агента DeepSeek |
| **DSH Desktop / VNC** | [http://127.0.0.1:6080](http://127.0.0.1:6080) | noVNC-трансляция экрана (для наблюдения за браузером агента) |

> [!TIP]
> **Токен первого входа в DeepSeek Harness:**
> При первом запуске DeepSeek Harness генерирует одноразовый токен авторизации. Получить ссылку с токеном можно командой:
> ```bash
> docker compose logs deepseek-harness | grep "dsh web:"
> ```

---

## Связка DeepSeek Harness с OmniRoute

Главное преимущество совместного запуска — DeepSeek Harness может обращаться к моделям через OmniRoute по внутренней сети Docker без выхода наружу:

1. Откройте панель **OmniRoute** (`http://127.0.0.1:20128`) и добавьте ваши ключи API (DeepSeek, OpenRouter, OpenAI или Anthropic).
2. Настройте нужный маршрут (например, модель `deepseek-chat` или `deepseek-reasoner`).
3. В настройках агента **DeepSeek Harness** (`http://127.0.0.1:3080`) укажите:
   - **Base URL:** `http://omniroute:20129/v1` *(внутренний адрес внутри Docker сети)*
   - **API Key:** ваш ключ из OmniRoute (или любое значение, если `REQUIRE_API_KEY=false`)
   - **Model:** имя модели, настроенной в OmniRoute.

---

## Управление резервными копиями

Резервное копирование выполняется автоматически по расписанию через cron (по умолчанию каждую ночь в 03:00, параметр `BACKUP_CRON_SCHEDULE`).

### Ручной запуск бэкапа
```bash
docker compose exec backup /app/backup.sh now
```

### Просмотр списка бэкапов на Google Диске
```bash
docker compose run --rm backup list
```

### Восстановление из архива
1. Остановите рабочие сервисы:
   ```bash
   docker compose stop deepseek-harness omniroute
   ```
2. Скачайте нужный архив с Google Диска и распакуйте в тома данных:
   ```bash
   docker compose run --rm backup rclone copy gdrive:backups/deepseek-stack/backup_XXXXXXXX_XXXXXX.tar.gz /tmp/
   docker compose run --rm -v omniroute-data:/data/omniroute -v dsh-home:/data/dsh-home backup tar -xzf /tmp/backup_XXXXXXXX_XXXXXX.tar.gz -C /data
   ```
3. Запустите сервисы:
   ```bash
   docker compose start
   ```

---

## Безопасность

- По умолчанию все порты привязаны исключительно к `127.0.0.1` (`HOST_BIND_IP` в `.env`), что предотвращает несанкционированный доступ из локальной сети или интернета к агенту, способному выполнять код на хосте.
- Redis изолирован внутри сети Docker `deepseek-net` и не публикует порты на хост-машину.
- Контейнер агента DeepSeek запускается в режиме с ограниченными привилегиями (`cap_drop: ALL`, `read_only: true`, `no-new-privileges: true`).
