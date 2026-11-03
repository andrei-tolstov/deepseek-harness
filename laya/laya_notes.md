# Справка по управлению и настройкам плагинов Jev и Laya в DeepSeek Harness

Данный документ описывает архитектуру, параметры конфигурации, управление и диагностику стека быстрых решений **Laya System 1** и интегрированных плагинов в **Hermes Agent** (`hermes-jev`, `hermes-token-router`, `hermes-handoff`).

---

## 1. Архитектура интеграции

В проекте [deepseek-harness](file:///c:/Users/andrei/projects/deepseek-harness) движок **Laya** выполняет роль «Системы 1» (быстрый, бескомпромиссно дешёвый и точный инференс на GPU для принятия дискретных решений), разгружая основную языковую модель (LLM) от рутинных сервисных развилок.

```
                  ┌──────────────────────────────────────────────┐
                  │                 Hermes Agent                 │
                  │  (Gateway / Telegram / Web-интерфейс / CLI)  │
                  └───────┬──────────────────────────────┬───────┘
                          │                              │
             (1) TypeSafe/Jev Protocol        (2) OpenAI Chat Completions
            http://laya:8080/v1/systemone     http://laya:8787/v1/chat/completions
                          │                              │
                          ▼                              ▼
                 ┌─────────────────┐           ┌────────────────────┐
                 │   Laya Engine   │           │    Laya Sidecar    │
                 │   (C++ ggmlc)   │◀──────────│ (FastAPI / MCP 2.x)│
                 │    Port 8080    │           │     Port 8787      │
                 └─────────────────┘           └────────────────────┘
                          │                              │
                          └──────────────┬───────────────┘
                                         ▼
                                  NVIDIA CUDA GPU
                           (laya_multilingual_f16.gguf)
```

### Сервисы и эндпоинты

| Сервис | Порт | Протокол | Назначение |
|---|---|---|---|
| **Laya C++ Engine** | `8080` | `POST /v1/systemone` | Прямой нативный инференс Jev / TypeSafe-совместимых запросов (`choice`, `score`, `noul`). Время отклика: **~90–140 мс**. |
| **Laya Sidecar** | `8787` | `POST /v1/chat/completions` | OpenAI-совместимый классификатор для плагинов, ожидающих стандартные сообщения Chat Completions (`hermes-token-router`). |
| **Laya Sidecar MCP** | `8787` | `POST /mcp` (Streamable HTTP) | MCP-интерфейс для прямого вызова Laya-инструментов из агента. |

---

## 2. Плагин `hermes-jev` (Hermes Jev Skills)

Плагин связывает Hermes Agent с движком решений через протокол System 1. Он делегирует Laya выбор подходящих инструментов, фильтрацию воспоминаний, ранжирование поисковой выдачи, оценку срочности и скрининг веб-данных.

### Переменные окружения

Переменные задаются в [docker-compose.yml](file:///c:/Users/andrei/projects/deepseek-harness/docker-compose.yml) и в файле `/opt/data/.env`:

```bash
# Базовый URL совместимого API System 1 (локальный Laya Engine)
TYPESAFE_BASE_URL=http://laya:8080

# Модель для инференса решений в Laya
TYPESAFE_MODEL=laya-multilingual
```

> **Важно**: Благодаря патчу в `jevkit/client.py`, эндпоинт `http://laya:8080` разрешен во внутренней Docker-сети (валидатор принимает хосты `laya`, `deepseek-laya`, `localhost`, `127.0.0.1`). Внешний API-ключ не требуется.

### Слэш-команды в чате Hermes (Telegram / Web / Terminal)

Управление состоянием плагина осуществляется интерактивно через команду `/jev`:

| Команда | Режимы | Описание |
|---|---|---|
| `/jev` | — | Вывод текущего статуса плагина, активных переключателей и задержки. |
| `/jev routing <mode>` | `off` \| `shadow` \| `on` | Модельный роутинг по сложности вопроса. В режиме `shadow` решения только логируются. |
| `/jev skills <mode>` | `off` \| `on` | Автоматический выбор и подключение релевантных навыков (skills) на каждом ходу. |
| `/jev notice <mode>` | `off` \| `on` | Отображение бейджа с моделью и уверенностью решения (например: `[Jev] hard · coding → fable · 0.92`). |
| `/jev screen <mode>` | `off` \| `shadow` \| `on` | Защита от prompt injection в результатах `web_search`/`web_extract`. |
| `/jev routing on all` | — | Сделать роутинг через Jev настройкой по умолчанию для всех профилей. |

### Инструменты агента (Tools)

Агент получает в системный промпт набор легковесных специализированных инструментов:
- `jev_memory_filter` — фильтрация нерелевантных фрагментов из долговременной памяти агента.
- `jev_compact_select` — разметка реплик диалога (`keep`, `summarize`, `drop`) перед сжатием контекста.
- `jev_choose_action` — выбор следующего действия в GUI или браузере из таблицы кандидатов.
- `jev_search` — оценка достаточности найденных материалов в поисковой выдаче и выбор следующего запроса.
- `jev_decide` / `jev_score` / `jev_route_to` — выполнение кастомных дискретных политик и рубрикаторов.
- `jev_supervise` / `jev_escalate` — оценка прогресса подзадач и передача оператору при тупике.

### Использование CLI-утилиты `jev`

Утилита доступна внутри контейнера по пути `/opt/data/bin/jev`:

```bash
# Проверка доступности Laya и задержки отклика
docker exec -u hermes hermes-agent jev doctor

# Прямой запрос к Laya System 1 через stdin (JSON)
echo '{"state":"Build failed with syntax error","questions":[{"id":"act","type":"choice","instructions":"What to do?","criteria":{"fix":"Fix syntax","ignore":"Ignore"}}]}' | \
docker exec -i -u hermes hermes-agent jev ask

# Сортировка почты / очереди сообщений по важности
docker exec -u hermes hermes-agent jev triage --help
```

---

## 3. Плагин `hermes-token-router` (Роутер инструментов)

Плагин динамически ограничивает набор системных инструментов перед каждым запросом к LLM. Если запрос пользователя простой (например, обычный диалог), агент не тратит контекстное окно на описание десятков инструментов и не совершает ложных вызовов.

### Файл конфигурации

Конфигурация хранится в файле:  
`/opt/data/plugins/hermes-token-router/config.yaml`  
(локальная копия для репозитория: [scratch/hermes-tool-router/config.yaml](file:///c:/Users/andrei/projects/deepseek-harness/scratch/hermes-tool-router/config.yaml)).

```yaml
global:
  enabled: true
  floor_toolsets: []
  deterministic_rules_enabled: true
  confidence_threshold: 0.80
  router_timeout_ms: 2000
  router_hard_timeout_ms: 3000
  fail_open: true                     # При ошибке/таймауте открывает все инструменты
  auto_recover_registered_tools: true
  classifier:
    enabled: true
    provider: custom
    model: laya-multilingual
    base_url: http://laya:8787/v1     # Эндпоинт OpenAI-совместимого sidecar Laya
    api_key_env: null

profiles:
  default:
    enabled: true
    floor_toolsets: []
    deterministic_rules_enabled: true
    confidence_threshold: 0.80
    router_timeout_ms: 2000
    router_hard_timeout_ms: 3000
    fail_open: true
    auto_recover_registered_tools: true
    classifier:
      enabled: true
      provider: custom
      model: laya-multilingual
      base_url: http://laya:8787/v1
      api_key_env: null
```

### Диагностика роутера

Для проверки готовности среды и доступности хуков выполните:

```bash
docker exec -u hermes hermes-agent python3 /opt/data/plugins/hermes-token-router/diagnostics.py
```

Ожидаемый статус: `"compatibility_mode": "late_compatibility"`, `"first_turn_savings_available": true`.

---

## 4. Плагин `hermes-handoff`

Плагин обеспечивает бесшовную передачу контекста и памяти между сессиями диалога.
- Использует алгоритмы сжатия `jevkit/compact.py`.
- Предотвращает потерю критических инструкций и фактов при авто-компактификации диалогов.
- Не требует отдельной конфигурации, автоматически использует настроенный `TYPESAFE_BASE_URL`.

---

## 5. Проверка состояния и диагностика

### 1. Проверка здоровья контейнеров Laya и Hermes

```bash
# Проверка нативного C++ движка Laya
curl -s http://127.0.0.1:8080/health

# Проверка sidecar и OpenAI-эндпоинта
curl -s http://127.0.0.1:8787/health

# Проверка статуса контейнеров Docker
docker ps --filter name=laya --filter name=hermes-agent
```

### 2. Проверка подключенных плагинов в Hermes

```bash
docker exec -u hermes hermes-agent hermes plugins list --plain --no-bundled
```

Корректный вывод:
```text
enabled      user     0.4.1    hermes-handoff
enabled      user     0.23.1   hermes-jev
enabled      git      0.2.0-rc1 hermes-token-router
```

### 3. Проверка самодиагностики `jev doctor`

```bash
docker exec -u hermes hermes-agent jev doctor
```

Корректный вывод (`exit code 0`):
```json
{
  "version": "0.23.1",
  "endpoint_override": {
    "url": "http://laya:8080/v1/systemone",
    "valid": true,
    "bearer": null
  },
  "jev": {
    "reachable": true,
    "latency_ms": 139
  }
}
```

### 4. Просмотр журнала принятых решений

Все решения, принятые Laya в процессе работы агента, фиксируются в JSONL-файле без раскрытия конфиденциального текста:

```bash
# Последние решения агента
docker exec hermes-agent tail -n 20 /opt/data/logs/jev-decisions.jsonl
```

---

## 6. Типичные проблемы и решения

| Проблема | Причина | Решение |
|---|---|---|
| `error: "invalid_endpoint"` в `jev doctor` | Защита от non-loopback HTTP в `client.py` не знает имени docker-хоста. | Убедиться, что в `_custom_typesafe_endpoint` (`jevkit/client.py`) прописаны хосты `laya`, `deepseek-laya`, `localhost`. |
| `HTTP 400 Bad Request: no GGUF catalogued for family 'english'` | Клиент запросил модель по умолчанию `jev-latest`, которой нет в каталоге Laya. | Задать `TYPESAFE_MODEL=laya-multilingual` в окружении контейнера или в `.env`. |
| Роутер тулов возвращает все тулы (`action: full`) | Сработал защитный fallback (`fail_open: true`) из-за таймаута или ошибки парсинга. | Проверить логи sidecar: `docker logs --tail 50 deepseek-laya` и задержку отклика `http://laya:8787/v1/chat/completions`. |
| Плагины не отображаются в `hermes plugins list` | Отсутствует запись в `plugins.enabled` в `config.yaml`. | Проверить блок `plugins.enabled` в `/opt/data/config.yaml` или переустановить через `install.py --enable all`. |

---

## 7. Дообучение и дистилляция Laya (Навык `laya-distill`)

Для адаптации Laya под специфику реальных диалогов и снижения ошибок маршрутизации разработан навык и конвейер дистилляции:

### Стек и инструменты:
- **Скрипт дистилляции**: [`scripts/laya_distill.py`](file:///c:/Users/andrei/projects/deepseek-harness/scripts/laya_distill.py)
- **Спецификация навыка**: [`.agents/skills/laya-distill/SKILL.md`](file:///c:/Users/andrei/projects/deepseek-harness/.agents/skills/laya-distill/SKILL.md)
- **Валидация датасета**: `/root/.unsloth/studio/unsloth_studio/bin/laya-evals validate <dataset.jsonl>`
- **Обучение**: `/root/.unsloth/studio/unsloth_studio/bin/laya-train --data <dataset.jsonl> --base /root/deepseek-harness/finetune-checkpoint --loss rlcd --epochs 4`

### Запуск сбора и сравнительного анализа:
```powershell
python scripts/laya_distill.py --fetch-remote --ssh-host root@192.168.50.101 --laya-url http://192.168.50.101:8080
```
Скрипт автоматически:
1. Выгружает сессии из `state.db`.
2. Выносит экспертное суждение (Teacher Agent Decision) на основе реальных вызовов инструментов.
3. Проводит параллельный аудит через live-инференс Laya (`POST /v1/systemone`).
4. Формирует строгий датасет в формате Laya (`data/laya_distill_train.jsonl`).
5. Генерирует отчет расхождений (`data/laya_distill_report.json`).

