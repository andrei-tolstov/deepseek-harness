---
name: laya-distill
description: Автоматическая дистилляция, сравнительная оценка решений и генерация обучающих датасетов для Laya System 1 на основе сессий Hermes Agent и экспертных суждений (ModernBERT: choice, noul, score / RLCD).
---

# Навык: Дистилляция и дообучение Laya на сессиях Hermes Agent (`laya-distill`)

Этот навык автоматизирует сбор данных диалогов Hermes Agent, траекторный экспертный надзор (Teacher Agent), сравнительный аудит решений Laya System 1 (ModernBERT) и генерацию калиброванных датасетов для дообучения модели под реальные сценарии плагинов `hermes-jev`, `hermes-token-router` и `hermes-handoff`.

---

## 1. Архитектура и поддерживаемые плагины

Движок **Laya** выполняет функции «Системы 1» (быстрый дискретный инференс за ~90–140 мс), разгружая основную LLM от рутинных сервисных развилок:

```
                      ┌──────────────────────────────────────────────┐
                      │                 Hermes Agent                 │
                      └───────┬──────────────────────────────┬───────┘
                              │                              │
                 (1) Native System 1 Protocol     (2) OpenAI Chat Completions
                http://laya:8080/v1/systemone    http://laya:8787/v1/chat/completions
                              │                              │
                              ▼                              ▼
                     ┌─────────────────┐           ┌────────────────────┐
                     │   hermes-jev    │           │ hermes-token-router│
                     │  (hermes-handoff│           │  (sidecar bridge)  │
                     │   через jevkit) │           └────────────────────┘
                     └────────┬────────┘                     │
                              │                              │
                              ▼                              ▼
                     ┌──────────────────────────────────────────┐
                     │          Laya Decision Engine            │
                     │    (ModernBERT multi-head classifier)    │
                     └──────────────────────────────────────────┘
```

### Решаемые задачи плагинов:
1. **`hermes-token-router`**:
   - `requires_tools` (`noul`): предварительный гейт, определяющий, нужны ли тулы вообще. Отключение тулов на чистом диалоге экономит тысячи токенов контекста.
   - `toolset_decision` / `category` (`choice`): сужение передаваемых тулсетов (`terminal`, `filesystem`, `web_and_search`, `system`, `schedule`).
2. **`hermes-jev`**:
   - `difficulty` (`score`, уровни 1..5): оценка сложности для модельного роутинга (`/jev routing`).
   - `kind` (`choice`): определение характера работы (`conversational`, `tool_task`, `code_craft`, `deep_reasoning`).
   - `costly_mistake` (`noul`): оценка риска деструктивных действий (удаление файлов, остановка сервисов, форматирование).
   - `needs_skill` (`noul`): определение необходимости подключения специализированного навыка (`/jev skills`).
3. **`hermes-handoff`**:
   - `t{i}` (`choice`: `keep`, `summarize`, `drop`): разметка ценности реплик диалога для передачи контекста между сессиями.

---

## 2. Спецификация форматов обучающих данных (ModernBERT Heads)

Входные данные валидируются утилитой `laya-evals validate` и обязаны содержать строгие типы:
- **`choice`**: строковый ключ из `criteria`.
- **`noul`**: булево значение `true` или `false`.
- **`score`**: строковый уровень из списка уровней `criteria`.

### Пример записи датасета (`data/laya_distill_train.jsonl`):

```json
{
  "state": "Найди в проекте все упоминания функции query_laya_systemone и покажи их",
  "questions": {
    "requires_tools": {
      "type": "noul",
      "instructions": "Determine whether fulfilling this user request requires executing external tools (files, terminal, web, schedule) or if a direct conversational response is appropriate.",
      "criteria": {
        "true": "Executing shell, reading or writing files, web queries, interacting with system or background tools",
        "false": "Pure conversational reply, greeting, general reasoning or explanation without tool execution"
      }
    },
    "tool_decision": {
      "type": "choice",
      "instructions": "Determine whether external tools or terminal execution are required to fulfill the user request, or if direct conversational response is appropriate.",
      "criteria": {
        "direct_chat": "Conversational reply, reasoning, code explanation without tool execution",
        "execute_tools": "Executing shell, reading or writing files, web queries, or interacting with tools"
      }
    },
    "category": {
      "type": "choice",
      "instructions": "Select the primary category of tool required for this task.",
      "criteria": {
        "filesystem": "File operations: reading, writing, editing, listing or patching files",
        "terminal_execution": "Running bash, terminal, shell commands, scripts and process execution",
        "web_and_search": "Web browsing, fetching remote URLs, downloading pages and online searches",
        "schedule": "Timers, background alarms, daily or cron schedules and reminders",
        "system": "System utilities, git repositories, workspace configuration and status"
      }
    },
    "difficulty": {
      "type": "score",
      "instructions": "How demanding is it to complete this turn well?",
      "criteria": ["trivial", "simple", "moderate", "demanding", "extreme"]
    },
    "costly_mistake": {
      "type": "noul",
      "instructions": "A wrong or sloppy answer or destructive command here would be costly or hard to undo.",
      "criteria": {
        "true": "System alteration, destructive commands, file modifications, git push, deployment",
        "false": "Read-only inspection, search, conversational answer, explanation"
      }
    }
  },
  "expected": {
    "requires_tools": true,
    "tool_decision": "execute_tools",
    "category": "filesystem",
    "difficulty": "simple",
    "costly_mistake": false
  },
  "tags": [
    "session:20261016_...",
    "decision:execute_tools",
    "diff:simple"
  ],
  "metadata": {
    "session_id": "...",
    "turn_id": 42,
    "teacher": {
      "requires_tools": true,
      "tool_decision": "execute_tools",
      "category": "filesystem",
      "difficulty": "simple",
      "costly_mistake": false,
      "confidence": 1.0
    },
    "laya": {
      "requires_tools": true,
      "tool_decision": "execute_tools",
      "category": "filesystem",
      "difficulty": "simple",
      "costly_mistake": false,
      "confidence": 0.94
    },
    "match": true,
    "hard_negative": false
  }
}
```

---

## 3. Инструменты и скрипты навыка

Все исполняемые скрипты расположены непосредственно внутри директории навыка:
- **[scripts/laya_distill.py](file:///c:/Users/andrei/projects/deepseek-harness/.agents/skills/laya-distill/scripts/laya_distill.py)**:
  - Извлечение траекторий диалогов из `state.db` и решений из `jev-decisions.jsonl`.
  - Вынесение экспертного суждения (Teacher Agent Judgment) по фактическим вызовам тулов.
  - Live-запрос в `POST /v1/systemone` для сравнительного анализа и расчета расхождений.
  - Расчет метрики калибровки Brier Score для голов вероятности.
  - Формирование датасетов `train.jsonl`, `eval.jsonl` и аналитического отчета `report.json`.
- **[scripts/deploy_laya.py](file:///c:/Users/andrei/projects/deepseek-harness/.agents/skills/laya-distill/scripts/deploy_laya.py)**:
  - Удаленная валидация датасета через `laya-evals validate`.
  - Пробный прогон размерностей батчей через `laya-train --dry-run`.
  - Запуск fine-tuning с целевой функцией RLCD на GPU Tesla V100.
  - Бесшовная горячая перезагрузка C++ движка через `/tmp/laya_restart_requested`.
  - Верификация работоспособности через `jev doctor` и healthchecks.
- **[references/questions_schema.json](file:///c:/Users/andrei/projects/deepseek-harness/.agents/skills/laya-distill/references/questions_schema.json)**:
  - Эталонный словарь спецификаций вопросов для ModernBERT.

---

## 4. Пошаговый рабочий процесс

### Шаг 1. Дистилляция сессий и генерация датасета

Запуск со скачиванием актуальной базы `state.db` с удаленного хоста:

```powershell
python .agents/skills/laya-distill/scripts/laya_distill.py `
  --fetch-remote `
  --ssh-host root@192.168.50.101 `
  --ssh-key "C:\Users\andrei\.gemini\id_ed25519_user_root" `
  --laya-url http://192.168.50.101:8080 `
  --out-train data/laya_distill_train.jsonl `
  --out-eval data/laya_distill_eval.jsonl `
  --out-report data/laya_distill_report.json
```

Скрипт выведет статистику совпадений решений Laya с экспертным прогнозом и Brier score для вероятности `requires_tools`.

### Шаг 2. Загрузка датасета на сервер

```powershell
scp -i "C:\Users\andrei\.gemini\id_ed25519_user_root" `
  data/laya_distill_train.jsonl `
  root@192.168.50.101:/root/deepseek-harness/data/laya_distill_train.jsonl

scp -i "C:\Users\andrei\.gemini\id_ed25519_user_root" `
  data/laya_distill_eval.jsonl `
  root@192.168.50.101:/root/deepseek-harness/data/laya_distill_eval.jsonl
```

### Шаг 3. Валидация схемы и пробный прогон (Dry-Run)

Используйте `deploy_laya.py` для автоматической проверки:

```powershell
# Валидация совместимости со схемой токенизатора ModernBERT:
python .agents/skills/laya-distill/scripts/deploy_laya.py validate

# Проверка размерностей тензоров и батчей без загрузки весов на GPU:
python .agents/skills/laya-distill/scripts/deploy_laya.py dry-run
```

### Шаг 4. Дообучение модели (Fine-Tuning RLCD)

Запуск оптимизации голов решений:

```powershell
python .agents/skills/laya-distill/scripts/deploy_laya.py train `
  --epochs 4 `
  --micro-batch 8 `
  --grad-accum 8 `
  --loss rlcd `
  --device cuda
```

### Шаг 5. Горячая перезагрузка и сквозная верификация

После сохранения чекпоинта отправьте сигнал горячей перезагрузки весов движка Laya и проверьте статус:

```powershell
# Горячая перезагрузка C++ движка без остановки инфраструктуры:
python .agents/skills/laya-distill/scripts/deploy_laya.py reload

# Проверка самодиагностики jev doctor:
python .agents/skills/laya-distill/scripts/deploy_laya.py doctor
```

Или выполните полный конвейер одной командой:
```powershell
python .agents/skills/laya-distill/scripts/deploy_laya.py pipeline
```

---

## 5. Практические рекомендации по качеству данных

1. **Аугментация порядка вариантов (`--shuffle-options`)**:
   - Всегда оставляйте включенным перемешивание вариантов для вопросов типа `choice`, чтобы исключить заучивание позиционного приоритета первого элемента.
2. **Hard Negative Mining**:
   - Строки с тегом `priority:hard_negative` отражают ситуации, где текущая Laya ошиблась или высказала сомнение (`confidence < 0.65`). При подготовке больших выборок такие примеры рекомендуется дублировать (oversampling), повышая чувствительность модели к редким тулам.
3. **Защита от ложных `no_tools` в роутере**:
   - Вопрос `requires_tools` калибруется на минимизацию False Negative (пропуск вызова терминала/файлов недопустим, лучше вернуть `true` с меньшей уверенностью, чем потерять функционал).
