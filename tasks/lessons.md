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




