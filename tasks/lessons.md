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
## Llama.cpp Dynamic Libraries & Runtime
- **LD_LIBRARY_PATH в контейнерах llama-server**: При сборке бинарников llama.cpp с динамической линковкой (компоненты `libllama-server-impl.so`, `libggml-cuda.so`, `libllama.so`, `libmtmd.so`) они располагаются рядом с бинарником (например, в `/app`). Динамический компоновщик Linux по умолчанию не проверяет `/app`.
- **Правило**: Всегда указывать `ENV LD_LIBRARY_PATH="/app:${LD_LIBRARY_PATH:-}"` в Dockerfile и пробрасывать `LD_LIBRARY_PATH=/app` в docker-compose.
- **Флаг `--slots` в llama-server**: Является переключателем отображения эндпоинта слотов (boolean flag), а не числовым параметром. Число слотов задается через `-np` / `--parallel <N>`.

## UFW & Cloud Node Isolation
- **Политика закрытого периметра хоста**: При требовании полной изоляции портов кроме SSH на Debian 12 настраивается `ufw default deny incoming`, `ufw default allow outgoing`, `ufw allow 22/tcp comment "SSH access only"`, `ufw --force enable`. Доступ к сервисам инференса (порт 8082) пробрасывается исключительно через клиентский SSH-туннель.

## Huananzhi X79 & Fan Control
- **Разъемы SFAN vs CPU_FAN**: На материнских платах Huananzhi X79 разъемы `SFAN` (SYS_FAN) часто не имеют рабочего ШИМ от мультиконтроллера Nuvoton NCT6779D (или 4-й контакт не разведен / прижат к земле). Серверный 4-pin вентилятор в таком разъеме останавливается или работает неуправляемо.
- **Правило**: Использовать для регулируемых вентиляторов разъем `CPU_FAN` (канал `pwm2`), где ШИМ полноценно поддерживается. Для управления программно переводить канал в ручной режим (`echo 1 > pwm2_enable`), писать значение 0-255 в `pwm2` и организовывать демоны с контролем как GPU, так и CPU.
- **Инвертированная логика серверных вентиляторов**: Промышленные и серверные вентиляторы (Delta/San Ace) нередко используют fail-safe инверсию ШИМ: 255 = минимальные тихие обороты, а 0 = 100% максимальный обдув. Кривую в скрипте необходимо выстраивать в обратном направлении (меньше значение ШИМ при росте температуры).

## OmniRoute & OpenAI-Compatible Connections
- **Ошибка "No base URL configured for OpenAI compatible provider"**: В шлюзе OmniRoute при проверке состояния подключения (`CredentialHealth` / `/api/providers/test`) базовый URL извлекается не только из таблицы узла `provider_nodes.base_url`, но и проверяется непосредственно внутри JSON-поля `provider_connections.provider_specific_data` по ключу `baseUrl`.
- **Правило**: При программном создании или настройке соединений `openai-compatible` обязательно прописывать в `provider_specific_data` валидный JSON: `{"baseUrl": "http://<host>:<port>/v1", "autoSync": true, "autoFetchModels": true}`.
- **Согласование размера контекста (128K vs 256K) между llama.cpp, OmniRoute и DSH**:
  `llama-server` возвращает контекст модели в проприетарном поле `meta: { n_ctx: 262144 }`. OmniRoute при импорте моделей из `/v1/models` ищет поля стандарта OpenAI (`context_length`, `max_input_tokens`, `inputTokenLimit`). Не найдя их, OmniRoute сохраняет модель в `syncedAvailableModels` без лимита и при выдаче каталога `/v1/models` клиентам применяет дефолтный fallback `128000` (128K). DSH при синхронизации провайдера фиксирует это значение в `cordis.patch.yml` (`contextWindow: 128000`), и счётчик токенов в UI отображает `~... / 128K`.
- **Правило**: Для локальных моделей с большим контекстом (например, Bonsai 2 с 256K):
  1. В `syncedAvailableModels` OmniRoute сохранять `inputTokenLimit` и `contextWindow`.
  2. Добавлять запись в `model_context_overrides` со статусом `source = 'manual'`, чтобы защитить значение от автоматического сброса.
  3. В профиле DSH (`cordis.patch.yml`) под соответствующим провайдером (`omniroute` или `self`) явно указывать `contextWindow: 262144`.

## DeepSeek Harness (DSH) Web Auth & Multimodality
- **Сброс сессий и бесконечный "Reconnecting." после перезапуска DSH**:
  В пакете `@deepseek-ai/dsh-client-connection` аутентификация в веб-интерфейсе привязана к одноразовому `launchToken`, который генерируется заново в оперативной памяти (`PROCESS_LAUNCH_TOKENS`) при каждом перезапуске Node-процесса. Старые куки браузера `dsh-auth-...` становятся недействительными (возвращают `401 Unauthorized` на `/api` и WebSocket). Если вкладка была открыта, клиент входит в цикл бесконечного переподключения.
- **Правило**: После любого перезапуска контейнера `deepseek-harness` для возобновления работы необходимо открыть URL с новым токеном (`http://<ip>:3080/?token=<launchToken>`), который устанавливает актуальную сессионную куку.
- **Ошибка HTTP 405 в плагине dsh-better-sidebar (зависимость webRuntime)**:
  Плагин `dsh-better-sidebar` декларирует `inject: ['webServer', 'sessions', 'webRuntime', 'tools']` и в `fence` обращается к `ctx.webRuntime.trustedHosts`. В стандартной сборке DSH сервис `webRuntime` не зарегистрирован в Cordis (список `trustedHosts` хранится в сервисе `connection` пакета `@deepseek-ai/dsh-client-connection`). Из-за этого Cordis оставляет бэкенд плагина в состоянии `pending (waiting for service: webRuntime)`, и маршруты `/sidebar/api` не регистрируются на веб-сервере. При этом фронтенд-модуль плагина загружается в браузер и шлет запросы `POST /sidebar/api/fs.tree` и `POST /sidebar/api/git.status`. Запросы проваливаются в SPA-fallback статического сервера, который отклоняет все `POST`-запросы ошибкой `HTTP 405 Method Not Allowed` (в интерфейсе отображается красным `HTTP 405` под файлами и `Failed to load` в Git).
- **Правило**:
  Для корректной работы `dsh-better-sidebar` регистрировать в `@deepseek-ai/dsh-client-connection` сервис `webRuntime`:
  ```javascript
  var WebRuntimeService = class extends Service {
      connection;
      constructor(ctx, connection) {
          super(ctx, "webRuntime");
          this.connection = connection;
      }
      get trustedHosts() {
          return this.connection.trustedHosts;
      }
  };
  new WebRuntimeService(ctx, connection);
  ```
  Это удовлетворяет инъекцию Cordis, активирует все эндпоинты `/sidebar/*` и корректно передает доверенные хосты в `isTrustedApiRequest`. Дополнительно в коде плагина делать fallback: `ctx.webRuntime?.trustedHosts ?? ctx.connection?.trustedHosts ?? []`.
- **Поддержка изображений (Vision) в сторонних провайдерах DSH**:
  В `@deepseek-ai/dsh-llm-pi-ai` для пользовательских провайдеров (`omniroute`, `self`, openai-compatible) по умолчанию выставлено `DEFAULT_INPUT = ["text"]`. Если в `cordis.patch.yml` секция модели не содержит явного списка `input`, DSH устанавливает `model.inputModalities = ["text"]`. При попытке отправить картинку `dsh-api-session-controller` выбрасывает исключение `MODEL_DOES_NOT_SUPPORT_IMAGES`.
- **Правило**: Для любой мультимодальной модели в `cordis.patch.yml` обязательно явно декларировать:
  ```yaml
  input:
    - text
    - image
  ```
  А в OmniRoute — удостовериться, что в `/v1/models` присутствуют `"capabilities": { "vision": true }` и `"input_modalities": ["text", "image"]`.

- **Zero-Auth патч для DSH**:
  Для полного устранения требований токенов авторизации в локальной сети:
  1. В `BrowserAuth` (`dsh-client-connection`) методы `authorizeIndex` и `isAuthenticated` возвращают `true`, а `authenticatedUrl` возвращает базовый URL без query-токена.
  2. В `docker-compose.yml` патч монтируется поверх `/usr/local/lib/node_modules/@deepseek-ai/dsh/node_modules/@deepseek-ai/dsh-client-connection/lib/index.js:ro`.
  3. В healthcheck контейнера проверка статуса должна принимать `200` (так как корень теперь сразу возвращает `200 OK`).
  4. Для корректной работы плагина `@deepseek-ai/dsh-hmr` Chokidar требует права на чтение всех файлов в директории профиля; любые файлы root вызывают EACCES и вечную блокировку.

- **Chokidar, EACCES и блокировка Cordis loader.await() при активном HMR**:
  Плагин `@deepseek-ai/dsh-hmr` использует `chokidar` для наблюдения за изменениями `cordis.patch.yml` и `package.json` в домашней директории профиля (`/home/node/.dsh/profiles/web`). Если в этой директории оказываются файлы, недоступные пользователю `node` (например, файлы бэкапа `*.bak`, созданные пользователем `root` с правами `0600`), `chokidar` при сканировании каталога выбрасывает ошибку `EACCES: permission denied`. В `dsh-hmr` это приводит к реджекту промиса готовности вотчера и зависанию HMR-сервиса в состоянии `fiber.state = 1 (LOADING)` с вечной инерцией `fiber.inertia`. Из-за этого `loader.await()` никогда не завершается, `appReady.commit()` не вызывается, а маршрут WebSocket `/api/remote.mux` не регистрируется в веб-сервере (приводя к ошибкам `socket hang up` / `curl: (52) Empty reply from server` и бесконечному `Reconnecting.` в UI с сообщением `No sessions yet`).
- **Правило**:
  1. В `workspace-init` (`docker-compose.yml`) всегда обеспечивать автоматическую смену владельца для всех томов: `chown -R 1000:1000 /dsh`.
  2. Не создавать внутри смонтированных томов файлы от пользователя `root` с правами `0600`. Бэкапы всегда сохранять вне каталогов томов (например, в `/root/backup_...`).
  3. Для быстрой диагностики: проверить `find /var/lib/docker/volumes/deepseek_dsh_home/_data -user root` и тест WebSocket через `curl -i -N -H 'Connection: Upgrade' -H 'Upgrade: websocket' -H 'Sec-WebSocket-Key: ...' -H 'Sec-WebSocket-Version: 13' http://127.0.0.1:3080/api/remote.mux`.
  4. Для диагностики состояния загрузки плагинов и промисов `loader.await()` использовать инспекцию fiber через Node CDP WebSocket (порт 9229 через `kill -SIGUSR1 <pid>`).

- **OmniRoute SSE Stream Readiness таймаут при длинном контексте (PI_AI_ERROR)**:
  В шлюзе OmniRoute по умолчанию действует жесткий таймаут ожидания первого полезного (не-ping) SSE события: `STREAM_READINESS_MAX_TIMEOUT_MS = 180000` (180 секунд = 3 минуты) и `STREAM_READINESS_TIMEOUT_MS = 80000` (80 секунд). При работе с моделями большого контекста (например, Bonsai 2 с контекстом до 262K токенов) на локальных GPU (Tesla V100), если промпт содержит большой объем истории диалога (например, ~100K токенов), фаза prompt processing (prefill) занимает более 3 минут (~190–220 с). На 180-й секунде OmniRoute принудительно обрывает апстрим-соединение с ошибкой `Stream produced no non-ping SSE event within 180000ms (max=180000ms)`, отменяя задачу в `llama-server`. В DSH это отображается как ошибка шага `PI_AI_ERROR`. Так как prefill не завершается, KV-кэш не сохраняется, и при каждом повторе задача снова начинает пересчитываться с нуля и сбрасывается.
- **Правило**:
  1. Для инсталляций с локальными моделями или длинным контекстом всегда переопределять в окружении OmniRoute (`docker-compose.yml` и `.env`):
     ```env
     REQUEST_TIMEOUT_MS=1200000
     FETCH_TIMEOUT_MS=1200000
     STREAM_IDLE_TIMEOUT_MS=1200000
     STREAM_ACTIVE_TIMEOUT_MS=1800000
     STREAM_READINESS_TIMEOUT_MS=1200000
     STREAM_READINESS_MAX_TIMEOUT_MS=1200000
     ```
  2. В `llama-server` для ускорения prefill на картах уровня Tesla V100 увеличивать микробатч `--ubatch` (например, `-b 4096 -ub 1024` вместо дефолтных `512`), что ускоряет обработку длинных входных промптов на 30–50% без риска переполнения VRAM.

## Windows PowerShell to Linux File Transfer & CRLF
- **CRLF (`\r\n`) в скриптах bash и systemd unit**: При передаче файлов из Windows PowerShell через `Get-Content ... -Raw | ssh ... "cat > ..."` файлы сохраняются с символами возврата каретки Windows (`\r`). Это приводит к ошибке bash `$'\r': command not found` и завершению скрипта со статусом `127`.
- **Правило**: При передаче shell-скриптов и systemd-юнитов из Windows всегда выполнять нормализацию переводов строк на стороне Linux: `sed -i 's/\r$//' <file>` или удалять `\r` перед записью.

## DSH 0.2.x Plugin Compatibility (Cordis settingsScope & ctx.settings.register)
- **Несовместимость API настроек в плагинах, созданных для DSH 0.1.x**:
  1. В бэкенде: в DSH 0.2.x сервис `settings` представлен классом `SettingsForms` без метода `.register()`. Вызов `ctx.settings.register(...)` выбрасывает `TypeError: ctx.settings.register is not a function`.
  2. Во фронтенде: в веб-клиенте сервис `settingsScope` был удален/объединен. Если плагин объявляет `inject: [..., "settingsScope"]`, клиентский Cordis блокирует активацию плагина с ошибкой `web boot: 1 entry did not activate ... pending (waiting for service: settingsScope)`.
  3. В пространстве имен настроек UI (`SettingsForms.describe()`): DSH 0.2.x фильтрует все схемы через `volatileForm(schema)`. Если в схеме плагина (`Config`) ни корневой объект, ни его поля не имеют метаданных `meta.volatile: true`, `volatileForm(schema)` возвращает `undefined` и запись плагина полностью исключается из списка `namespaces` дескриптора настроек. В веб-клиенте это приводит к ошибке: `The Messenger Host plugin has not registered its settings namespace`.
- **Правило**:
  1. Для плагинов DSH 0.1.x в бэкенде проверять `typeof ctx.settings?.register === 'function'`, при отсутствии использовать `readConfig` с разыменованием `Volatile` ссылок.
  2. В `client.js` удалять `"settingsScope"` из массива `inject` и использовать прямую область видимости настроек (`createDirectSettingsScope(api)`).
  3. Добавлять `Config.meta = { ...Config.meta, volatile: true };` к корневой схеме `Config` плагина, чтобы `SettingsForms` регистрировал его namespace, и вызывать `ctx.settings.configure({ auto: false })`, если плагин рендерит собственный интерфейс в настройках.

## Context Compaction & Pressure Budget в DSH 0.2.x
- **Ложное раннее срабатывание сжатия контекста (~22-27% вместо 80%)**:
  Алгоритм расчета порога сжатия `resolveCompactSpec` в `@deepseek-ai/dsh-compaction-basic` вычисляет:
  `messageBudgetTokens = contextWindow - reservedCompletionTokens`
  `pressureBudgetTokens = messageBudgetTokens - policy.headroomTokens`
  `thresholdTokens = min(contextWindow * policy.thresholdRatio, pressureBudgetTokens)`
  В коде пакета `headroomTokens` по умолчанию зашит на уровне `65536`. При дефолтном `maxTokens: 65536` моделей из окна 180 000 токенов суммарно вычитается `131 072` токена. В результате `pressureBudgetTokens` составляет всего `48 928` токенов (27.18%), и сжатие срабатывает задолго до заполнения контекста.
- **Изоляция пресетов (@deepseek-ai/dsh-web-app)**:
  В веб-сборке DSH хостовый `compaction-basic` отключен (`disabled: true`), а рабочий движок монтируется внутри поддерева каждого пресета (`preset-cordis`, `preset-standard`) через `new PresetTree(scope).update(plugins)`. Из-за отсутствия явного блока `config` у `compaction-basic` внутри пресетов он всегда инициализируется с дефолтными значениями `{}`.
- **Правило**:
  1. Для моделей с контекстом 180K выставлять реалистичный `maxTokens: 8192` в `cordis.patch.yml`.
  2. Патчить `@deepseek-ai/dsh-compaction-basic` (`dsh-patches/compaction-basic-index.js`), заменяя дефолт `headroomTokens` с 65536 на 8192 и добавляя поддержку переменных окружения `DSH_COMPACTION_HEADROOM_TOKENS` (8192), `DSH_COMPACTION_THRESHOLD_RATIO` (0.8) и `DSH_COMPACTION_RETAIN_RATIO` (0.15).
  3. Пробрасывать патч через volume в `docker-compose.yml` аналогично другим патчам DSH:
     `- ./dsh-patches/compaction-basic-index.js:/usr/local/lib/node_modules/@deepseek-ai/dsh/node_modules/@deepseek-ai/dsh-compaction-basic/lib/index.js:ro`.
  4. Это обеспечивает честный порог сжатия `thresholdTokens = 144000` (ровно 80.00% от 180K) для всех пресетов без необходимости дублирования списков плагинов пресетов.
- **Взаимодействие высокого maxTokens (32K) и thresholdRatio (0.95)**:
  Если для модели с окном 180K токенов установлен лимит вывода `maxTokens: 32768`, алгоритм `resolveCompactSpec` физически не может допустить накопление промпта до 95% ($180\,000 \times 0.95 = 171\,000$ токенов), так как сумма промпта и зарезервированного ответа $171\,000 + 32\,768 = 203\,768$ токенов вызовет краш `CONTEXT_WINDOW_EXCEEDED` в бэкенде инференса (`llama-server`).
  Алгоритм безопасности DSH берет `thresholdTokens = Math.min(contextWindow * thresholdRatio, pressureBudgetTokens)`.
  При `headroomTokens: 4096` реальный порог сжатия автоматически отсекается значением `pressureBudgetTokens = (180000 - 32768) - 4096 = 143136` токенов (~79.52%).

## Multi-GPU Setups (Tesla + GeForce), nvidia-smi Targeting & Docker Device Isolation
- **Смещение индексов GPU и падение `nvidia-smi` без `-i`**:
  При установке дополнительного GPU (например, GeForce GTX 1060 рядом с серверной Tesla V100) новый адаптер в верхнем PCIe-слоте становится `GPU 0`, а Tesla V100 смещается на `GPU 1`.
  Команды `nvidia-smi -pl <Watts>` и `nvidia-smi -lgc <Clocks>` без явного флага `-i <UUID/Index>` применяются по очереди ко всем GPU. Потребительский адаптер не поддерживает серверные лимиты (например, 200W при диапазоне GTX 1060 60–140W) или не поддерживает `lock-gpu-clocks` (`-lgc`). Утилита `nvidia-smi` завершается с ошибкой `exit code 2`, и в скриптах с `set -e` выполнение немедленно прерывается — настройки до Tesla V100 не применяются вовсе, а systemd-юниты переходят в `failed`.
- **Сбой CUDA Forward Compatibility в Docker при `count: all`**:
  Если в `docker-compose.yml` указано `count: all` (или `count: -1`), Docker пробрасывает все видеокарты. Библиотека прямой совместимости CUDA (`cuda-compat`) внутри контейнера `llama-server` пытается инициализироваться на GPU 0 (GeForce Pascal) и аварийно завершается: `failed to initialize CUDA: forward compatibility was attempted on non supported HW`, после чего `llama-server` сбрасывает слои на CPU (`warning: no usable GPU found`).
- **Правило**:
  1. **Явный таргетинг по UUID**: В скриптах управления питанием и частотами (`nvidia-power-scheduler.sh`) находить целевые карты по имени или UUID (`nvidia-smi --query-gpu=uuid,name ...`) и выполнять команды строго с ключом `-i "$gpu"`.
  2. **Изоляция GPU в Docker**: В `docker-compose.yml` сервисов инференса не использовать `count: all` — всегда явно указывать `device_ids: ['GPU-733ae7cc-c1bf-3352-42d5-ba2762470325']`.
  3. **Таргетинг датчиков в Fan Control**: В скриптах управления охлаждением (`v100-fancontrol.py`) запрашивать температуру конкретно для Tesla V100 (`--query-gpu=name,temperature.gpu`), чтобы нагрев или простой второго GPU не влиял на кривую ШИМ серверного охлаждения.

## Compaction Failure на моделях с мышлением (Qwen/DeepSeek): "Compaction could not produce a useful summary"
- **Симптом**: В UI при ручном (`/compact`) или автоматическом сжатии появляется ошибка `compact · Compaction could not produce a useful summary. The attempt is recorded in the session log.`
- **Первопричина**:
  1. **Лимит maxTokens суммирования**: В DSH 0.2.x движок `compaction-basic` внутри веб-пресетов инициализируется с `{}`. В коде пакета `maxTokens` суммирования брался как `config.maxTokens ?? headroomTokens` (4096 токенов).
  2. **Thinking Mode в Jinja**: Модели класса Qwen 3.8 / DeepSeek при работе через `llama-server --jinja` по умолчанию запускают этап рассуждений (`<think>`).
  3. **Сжигание бюджета токенов на `<think>`**: При суммировании длинного контекста (50K+ токенов) цепочка рассуждений съедает все 4096 токенов до того, как модель завершает генерацию требуемых Markdown-секций. Инференс завершается со статусом `finish_reason: length`.
  4. **Fail-Closed логика DSH**: В `finishError` DSH статус `finish.kind === "max-tokens"` считается фатальной ошибкой: `summarization truncated at the token cap (incomplete checkpoint)`. DSH бракует чекпоинт и фиксирует ошибку в логе сессии.
  5. **Отсутствие метаданных compat**: Библиотека `@earendil-works/pi-ai` отправляет `chat_template_kwargs: { enable_thinking: false }` только при наличии у модели `compat: { thinkingFormat: "qwen-chat-template" }` и `reasoningEfforts`. Без этой конфигурации текстовые инструкции в промпте ("Do NOT think") моделью в Jinja игнорируются.
- **Правило**:
  1. В `cordis.patch.yml` для всех моделей с рассуждениями явно декларировать:
     ```yaml
     reasoningEfforts:
       off: null
       low: low
       medium: medium
       high: high
       xhigh: xhigh
     compat:
       thinkingFormat: qwen-chat-template
       supportsReasoningEffort: true
     ```
  2. В патче `@deepseek-ai/dsh-compaction-basic` (`dsh-patches/compaction-basic-index.js`):
     - Наследовать корневую конфигурацию `cordis.patch.yml` (`rootCompactionConfig`) для экземпляров движка, создаваемых внутри поддеревьев пресетов DSH с `{}`.
     - Использовать `maxTokens` из конфига или откатываться к `headroomTokens` (без необходимости отдельных переменных окружения).
     - Выводить `reasoningEffort` в `compaction-basic` конфиг и передавать `config.reasoningEffort ?? "off"` в `summarizeWithLlm`.
  3. В `cordis.patch.yml` в блоке `compaction-basic` явно задавать:
     ```yaml
     headroomTokens: 32768
     thresholdRatio: 0.95
     retainRatio: 0.15
     maxTokens: 32768
     reasoningEffort: "off"
     ```

## Hermes Agent Docker Deployment & OmniRoute Routing
- **Порты OmniRoute внутри Docker-сети (`20128` vs `20129`)**:
  В шлюзе OmniRoute (на базе Next.js standalone) основной процесс веб-сервера и все эндпоинты OpenAI-совместимого API (`/v1/chat/completions`, `/v1/models`) слушают на порту `PORT` (20128). Порт `20129` (`API_PORT`) используется как внутренний локальный воркер сжатия/петли (`127.0.0.1:20129`) и не принимает внешние соединения из сети Docker.
  - **Правило**: При настройке контейнеров-клиентов (DSH, Hermes Agent) в Docker-сети `deepseek-net` всегда указывать `baseURL: http://omniroute:20128/v1`.
- **Привязка адресов API Server в Hermes Agent (`API_SERVER_HOST`)**:
  Встроенный сервер API шлюза Hermes (`gateway run`) по умолчанию привязывается только к loopback (`127.0.0.1:8642`). При пробросе портов Docker пакеты с хоста приходят на интерфейс контейнера `eth0` и отклоняются.
  - **Правило**: В `docker-compose.yml` всегда явно задавать `API_SERVER_HOST=0.0.0.0`.
- **Политика безопасности веб-дашборда Hermes (Auth Gate на `0.0.0.0`)**:
  В официальном образе `nousresearch/hermes-agent` привязка дашборда к `0.0.0.0:9119` без настроенного провайдера аутентификации принудительно блокируется механизмом безопасности (защита от неавторизованного доступа).
  - **Правило**: Для активации дашборда в контейнере обязательно передавать базовые учетные данные:
    `HERMES_DASHBOARD_BASIC_AUTH_USERNAME=admin` и `HERMES_DASHBOARD_BASIC_AUTH_PASSWORD=...`.
- **Права доступа к тому данных `/opt/data` и совместное использование с VS Code (EACCES)**:
  В официальном образе `nousresearch/hermes-agent` процесс по умолчанию запускается под пользователем `uid=10000(hermes) gid=10000(hermes)`. При совместном монтировании тома в `code-server` (`deepseek-vscode`), работающий под пользователем `coder` (`uid=1000`), попытка редактирования файлов (например, `SOUL.md`) завершается ошибкой `EACCES: permission denied`.
  - **Правило**: Передавать в сервис `hermes-agent` переменные окружения `HERMES_UID=1000` и `HERMES_GID=1000`, а в `workspace-init` обеспечивать `chown -R 1000:1000 /hermes`. При запуске s6-overlay автоматически переназначает пользователя `hermes` внутри контейнера на UID `1000:1000`, устраняя конфликт прав с редактором VS Code и хостом.
- **Конфликт Telegram Bot API (`getUpdates Conflict`) при переносе токена**:
  Если старый контейнер (DSH) не был явно остановлен командой `docker stop`, он продолжает удерживать длинный опрос `getUpdates`. Новый сервис (`hermes-agent`) при запуске завершается ошибкой `Conflict: terminated by other getUpdates request; make sure that only one bot instance is running`.
  - **Правило**: При миграции бота перед запуском нового агента всегда явно останавливать предыдущий контейнер (`docker stop deepseek-harness`).
- **Сломанные ссылки `depends_on` в docker-compose при комментировании сервисов**:
  При комментировании описания сервиса (например, `deepseek-harness`) в `docker-compose.yml`, любые другие сервисы (например, `backup`), имеющие его в списке `depends_on`, блокируют выполнение любых команд compose ошибкой `service "backup" depends on undefined service "deepseek-harness"`.
  - **Правило**: При временном отключении сервиса синхронно комментировать ссылки на него в блоках `depends_on` зависимых контейнеров.

## Hermes Jev Skills & Local Laya System 1 Integration
- **Строгая валидация HTTP Loopback в Jev (`_custom_typesafe_endpoint`)**:
  В модуле `jevkit/client.py` метод `_custom_typesafe_endpoint` проверяет безопасность URL: для схемы `http://` разрешены только числовые loopback-адреса (`127.0.0.1`, `::1`). В среде Docker контейнеры обращаются к соседним сервисам по именам хостов сети (`http://laya:8080`), что вызывает исключение `JevError("invalid_endpoint")`.
  - **Правило**: В `_custom_typesafe_endpoint` расширять список разрешенных хостов: `parsed.hostname in ("127.0.0.1", "::1", "localhost", "laya", "deepseek-laya")`.
- **Согласование каталога моделей с Laya C++ Engine (`TYPESAFE_MODEL`)**:
  По умолчанию клиент Jev отправляет идентификатор модели `jev-latest`. Движок Laya при получении неизвестного имени пытается сопоставить его с языковыми семействами и возвращает `HTTP 400 Bad Request: no GGUF catalogued for family 'english'`. Для работы с загруженной моделью Laya System 1 требуется передавать `laya-multilingual`.
## Laya Decision Distillation & ModernBERT Decision Heads
- **Строгая схема валидации датасета в `laya-evals` и `laya-train`**:
  В Laya Dataset (`laya.evals.Dataset` и `laya.train.items_from_rows`) каждая строка обучающего JSONL обязана содержать ключи `state`, `questions` и `expected` (или `gold`). Поле `expected` должно быть объектом `{ <question_id>: <target_value> }`, где для вопросов типа `choice` передается строковый ключ выбранного варианта из `criteria`, для `noul` — boolean `true`/`false`, а для `score` — числовой уровень рубрики или ключ.
  - **Правило**: При генерации обучающих данных всегда валидировать сформированные файлы через `/root/.unsloth/studio/unsloth_studio/bin/laya-evals validate <file.jsonl>` и делать тестовый батч-прогон через `laya-train --dry-run`.
- **Консольный вывод Unicode на Windows в скриптах Python**:
  При печати русскоязычных сообщений в стандартный вывод Windows PowerShell кодировка по умолчанию может быть `cp1252` или `cp866`, что вызывает `UnicodeEncodeError: 'charmap' codec can't encode characters`.
  - **Правило**: В скриптах CLI всегда добавлять явную реконфигурацию потоков:
    ```python
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ```

## Hermes Gateway Platform Breakers & Port Conflicts
- **Фатальный статус платформ в Hermes Gateway (`api_server_port_in_use`)**:
  Если платформа в Hermes Gateway при старте натыкается на конфликт порта (например, старый Docker-контейнер занимает 8642), шлюз переводит платформу в состояние `fatal` и сохраняет его в `gateway_state.json`. Этот предохранитель (circuit breaker) не сбрасывается автоматически простым рестартом, чтобы предотвратить бесконечные утечки дескрипторов.
  - **Правило**: После освобождения порта остановить шлюз (`systemctl --user stop hermes-gateway`), сбросить состояние (`rm -f /root/.hermes/gateway_state.json`) или возобновить платформу командой `/platform resume <name>`, затем запустить сервис заново.

## Windows PowerShell Quote Interpolation in SSH
- **Парсинг скобок и кавычек в PowerShell при вызове SSH**:
  При передаче встроенных скриптов через `ssh ... "cat << 'EOF' ... (Text) ... EOF"` в PowerShell строки со скобками внутри двойных кавычек интерпретируются PowerShell как вызов субкоманды/cmdlet (например, `The term 'DeepSeek' is not recognized`).
  - **Правило**: Использовать `scp` для передачи структурированных конфигурационных файлов или экранировать кавычки через Here-String / Base64.

## Qwen Jinja Chat Template & Multi-Step Tool Loops ("No user query found in messages")
- **Исключение Jinja в llama-server при агентных и tool-вызовах**:
  В нативном `tokenizer.chat_template` моделей Qwen (Qwen 2.5 / Qwen 3.8 / HauhauCS) встроена строгая проверка наличия не-tool пользовательского сообщения:
  ```jinja
  {%- if ns.multi_step_tool %}
      {{- raise_exception('No user query found in messages.') }}
  {%- endif %}
  ```
  В агентных сценариях (Hermes Agent, DeepSeek Harness, Roo, Cline, OmniRoute), когда после вызова инструмента возвращаются сообщения с ролью `tool`, либо при фоновых задачах / сжатии контекста, в списке сообщений может отсутствовать завершающий или предшествующий пользовательский запрос. Встроенный Jinja-движок `llama-server` выбрасывает исключение `Error: Jinja Exception: No user query found in messages.`, сервер возвращает `HTTP 500 server_error`, а шлюзы (OmniRoute) фиксируют сбой учетной записи/модели (`Preserving last upstream error after credential exhaustion`). Дополнительно `{{- raise_exception('System message must be at the beginning.') }}` блокирует запросы со вставками системных инструкций в середину контекста.
- **Правило**:
  1. Извлекать или переопределять шаблон модели в файл `chat_template.jinja`.
  2. Удалять жесткую проверку `{%- if ns.multi_step_tool %} raise_exception(...) {% endif %}`, чтобы разрешить выполнение запросов с `[system, assistant, tool]` без обязательного `user`-запроса.
  3. В проверке `message.role == "system"` поддерживать также `developer` (`message.role in ("system", "developer")`), а при `not loop.first` рендерить сообщение в разметку `<|im_start|>system\n...<|im_end|>\n` вместо вызова `raise_exception`.
  4. В `docker-compose` монтировать шаблон и передавать в `llama-server` флаг `--chat-template-file /path/to/chat_template.jinja`.
- **Поддержка значений reasoning_effort ('high' vs 'xhigh') в шаблоне Jinja**:
  В кастомных шаблонах Qwen/HauhauCS валидация `reasoning_effort` по умолчанию жестко ограничивает значения списком `('xhigh', 'medium', 'low')`. При передаче стандартного для OpenAI API значения `high` Jinja выбрасывает исключение `Unexpected reasoning effort high`.
  - **Правило**: В `chat_template.jinja` явно поддерживать оба варианта: `resolved_reasoning_effort in ('xhigh', 'high')`.

## OmniRoute Routing Combos & API Key Catalog Scope
- **Отображение комбо-роутеров в каталоге `/v1/models`**:
  По умолчанию в таблице `api_keys` поле `catalog_scope` имеет значение `'models'`, из-за чего эндпоинт `/v1/models` возвращает только провайдерные модели и скрывает маршрутизирующие комбо (`combos`).
  - **Правило**: Для ключей API, используемых клиентами с выпадающими списками моделей (DSH, OpenWebUI, Cursor), устанавливать `catalog_scope = 'all'` и добавлять имя комбо как в `allowed_models`, так и в `allowed_combos`.

