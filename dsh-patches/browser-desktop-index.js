import z from '@deepseek-ai/schemastery'
import fs from 'node:fs'
import fsp from 'node:fs/promises'
import path from 'node:path'

export const name = 'browser-desktop'
export const inject = ['tools', 'systemPrompt', 'webServer']

const defaultDesktopPath = '/vnc.html?autoconnect=1&resize=scale&view_only=0&reconnect=1'
const CONFIG_FILE_PATH = '/home/node/.dsh/profiles/web/cordis.patch.yml'

export const Config = z.object({
  cdpBaseUrl: z.string().min(1).default('http://127.0.0.1:9222'),
  desktopPort: z.number().step(1).min(1).max(65535).default(6080),
  desktopPath: z.string().min(1).default(defaultDesktopPath),
  pollIntervalMs: z.number().step(1).min(250).max(10000).default(750)
})

function normalizeBaseUrl(input) {
  const parsed = new URL(input)
  if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
    throw new Error('cdpBaseUrl must use http:// or https://')
  }
  return parsed.toString().replace(/\/$/, '')
}

function normalizeDesktopPath(input) {
  const parsed = new URL(input, 'http://browser-desktop.invalid')
  if (parsed.origin !== 'http://browser-desktop.invalid') {
    throw new Error('desktopPath must be a same-origin absolute path')
  }
  return `${parsed.pathname}${parsed.search}${parsed.hash}`
}

function normalizeUrl(input) {
  const value = input.trim()
  if (value.length === 0) throw new Error('url must be a non-empty string')

  const parsed = new URL(value.includes('://') ? value : `https://${value}`)
  if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
    throw new Error('only http:// and https:// URLs can be opened')
  }
  return parsed.toString()
}

function sendJson(res, status, value) {
  const body = JSON.stringify(value)
  res.writeHead(status, {
    'content-type': 'application/json; charset=utf-8',
    'cache-control': 'no-store',
    'content-length': Buffer.byteLength(body)
  })
  res.end(body)
}

async function readJson(req) {
  let body = ''
  for await (const chunk of req) {
    body += chunk
    if (body.length > 65536) throw new Error('request body is too large')
  }
  if (body.length === 0) throw new Error('request body is required')
  return JSON.parse(body)
}

function isSameOrigin(req) {
  const origin = req.headers.origin
  if (origin === undefined) return true
  try {
    return new URL(origin).host === req.headers.host
  } catch {
    return false
  }
}

function renderConfigEditorHtml(yamlContent) {
  const escapedYaml = yamlContent
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;')

  return `<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>DeepSeek Harness — Configuration File (cordis.patch.yml)</title>
  <style>
    :root {
      --bg: #121316;
      --card-bg: #1a1c20;
      --header-bg: #16181c;
      --border: #2a2d34;
      --border-focus: #4d6bfe;
      --text: #e4e7eb;
      --text-muted: #8b929d;
      --primary: #4d6bfe;
      --primary-hover: #3b5bdb;
      --success: #10a37f;
      --danger: #ef4444;
      --warning: #f59e0b;
      --font-mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      height: 100vh;
      display: flex;
      flex-direction: column;
      overflow: hidden;
    }
    header {
      background: var(--header-bg);
      border-bottom: 1px solid var(--border);
      padding: 12px 20px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      flex-shrink: 0;
    }
    .header-left {
      display: flex;
      align-items: center;
      gap: 12px;
    }
    .logo-badge {
      background: linear-gradient(135deg, #4d6bfe, #8c52ff);
      color: white;
      font-weight: 700;
      font-size: 13px;
      padding: 4px 8px;
      border-radius: 6px;
      letter-spacing: 0.5px;
    }
    h1 {
      font-size: 16px;
      font-weight: 600;
      color: var(--text);
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .path-badge {
      font-family: var(--font-mono);
      font-size: 12px;
      color: var(--text-muted);
      background: var(--card-bg);
      border: 1px solid var(--border);
      padding: 2px 8px;
      border-radius: 4px;
    }
    .status-badge {
      font-size: 12px;
      padding: 3px 10px;
      border-radius: 12px;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      font-weight: 500;
    }
    .status-badge.clean { background: rgba(16, 163, 127, 0.15); color: #2ecc71; border: 1px solid rgba(16, 163, 127, 0.3); }
    .status-badge.dirty { background: rgba(245, 158, 11, 0.15); color: #f59e0b; border: 1px solid rgba(245, 158, 11, 0.3); }
    .status-badge.saving { background: rgba(77, 107, 254, 0.15); color: #4d6bfe; border: 1px solid rgba(77, 107, 254, 0.3); }
    .status-badge.error { background: rgba(239, 68, 68, 0.15); color: #ef4444; border: 1px solid rgba(239, 68, 68, 0.3); }

    .header-actions {
      display: flex;
      align-items: center;
      gap: 8px;
    }
    button, a.btn {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 6px 14px;
      font-size: 13px;
      font-weight: 500;
      border-radius: 6px;
      cursor: pointer;
      text-decoration: none;
      transition: all 0.15s ease;
      border: 1px solid transparent;
      user-select: none;
    }
    .btn-primary {
      background: var(--primary);
      color: white;
    }
    .btn-primary:hover:not(:disabled) {
      background: var(--primary-hover);
    }
    .btn-primary:disabled {
      opacity: 0.5;
      cursor: not-allowed;
    }
    .btn-secondary {
      background: var(--card-bg);
      color: var(--text);
      border-color: var(--border);
    }
    .btn-secondary:hover {
      background: #23262d;
      border-color: #3b3f49;
    }
    .editor-container {
      flex: 1;
      display: flex;
      overflow: hidden;
      position: relative;
      background: var(--card-bg);
    }
    .line-numbers {
      width: 52px;
      padding: 16px 8px 16px 0;
      text-align: right;
      font-family: var(--font-mono);
      font-size: 13px;
      line-height: 20px;
      color: #555b68;
      background: #141518;
      border-right: 1px solid var(--border);
      user-select: none;
      overflow: hidden;
    }
    textarea {
      flex: 1;
      background: transparent;
      color: #e4e7eb;
      font-family: var(--font-mono);
      font-size: 13px;
      line-height: 20px;
      padding: 16px;
      border: none;
      outline: none;
      resize: none;
      white-space: pre;
      word-break: normal;
      overflow-wrap: normal;
      overflow: auto;
      tab-size: 2;
    }
    textarea::selection {
      background: rgba(77, 107, 254, 0.35);
    }
    .footer-bar {
      background: var(--header-bg);
      border-top: 1px solid var(--border);
      padding: 8px 20px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-size: 12px;
      color: var(--text-muted);
    }
    .footer-left { display: flex; gap: 16px; align-items: center; }
    .toast {
      position: fixed;
      bottom: 24px;
      right: 24px;
      background: #1e2025;
      color: white;
      padding: 12px 18px;
      border-radius: 8px;
      border: 1px solid var(--border);
      box-shadow: 0 8px 24px rgba(0,0,0,0.5);
      font-size: 13px;
      display: flex;
      align-items: center;
      gap: 10px;
      opacity: 0;
      transform: translateY(12px);
      transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
      pointer-events: none;
      z-index: 1000;
    }
    .toast.show {
      opacity: 1;
      transform: translateY(0);
    }
    .toast.success { border-color: var(--success); }
    .toast.error { border-color: var(--danger); }
  </style>
</head>
<body>
  <header>
    <div class="header-left">
      <span class="logo-badge">DSH</span>
      <h1>Конфигурация</h1>
      <span class="path-badge">${CONFIG_FILE_PATH}</span>
      <span id="statusBadge" class="status-badge clean">● Сохранено</span>
    </div>
    <div class="header-actions">
      <button id="copyBtn" class="btn-secondary" title="Скопировать YAML в буфер обмена">Скопировать</button>
      <a href="/api/config-document?download=1" class="btn btn-secondary" title="Скачать файл конфигурации">Скачать</a>
      <a href="/api/config-document?raw=1" target="_blank" class="btn btn-secondary" title="Открыть чистый YAML">Raw YAML</a>
      <button id="saveBtn" class="btn-primary" disabled title="Сохранить изменения (Ctrl+S)">Сохранить изменения</button>
    </div>
  </header>

  <div class="editor-container">
    <div id="lineNumbers" class="line-numbers">1</div>
    <textarea id="editor" spellcheck="false">${escapedYaml}</textarea>
  </div>

  <div class="footer-bar">
    <div class="footer-left">
      <span id="cursorPos">Строка 1, Колонка 1</span>
      <span id="lineCount">Всего строк: 1</span>
      <span>Синтаксис: YAML (Cordis Patch)</span>
    </div>
    <div>
      <span>Горячие клавиши: <strong>Ctrl+S</strong> — сохранить, <strong>Tab</strong> — 2 пробела</span>
    </div>
  </div>

  <div id="toast" class="toast"></div>

  <script>
    const editor = document.getElementById('editor');
    const lineNumbers = document.getElementById('lineNumbers');
    const saveBtn = document.getElementById('saveBtn');
    const copyBtn = document.getElementById('copyBtn');
    const statusBadge = document.getElementById('statusBadge');
    const cursorPos = document.getElementById('cursorPos');
    const lineCount = document.getElementById('lineCount');
    const toast = document.getElementById('toast');

    let initialContent = editor.value;
    let isSaving = false;

    function showToast(message, type = 'success') {
      toast.textContent = message;
      toast.className = 'toast show ' + type;
      setTimeout(() => { toast.className = 'toast'; }, 3500);
    }

    function updateLineNumbers() {
      const lines = editor.value.split('\\n');
      const count = lines.length;
      let numbers = '';
      for (let i = 1; i <= count; i++) {
        numbers += i + '\\n';
      }
      lineNumbers.textContent = numbers;
      lineCount.textContent = 'Всего строк: ' + count;
    }

    function updateCursor() {
      const pos = editor.selectionStart;
      const text = editor.value.substring(0, pos);
      const lines = text.split('\\n');
      const currentLine = lines.length;
      const currentCol = lines[lines.length - 1].length + 1;
      cursorPos.textContent = 'Строка ' + currentLine + ', Колонка ' + currentCol;
    }

    function checkDirty() {
      const isDirty = editor.value !== initialContent;
      saveBtn.disabled = !isDirty || isSaving;
      if (isDirty) {
        statusBadge.className = 'status-badge dirty';
        statusBadge.textContent = '● Несохраненные изменения';
      } else {
        statusBadge.className = 'status-badge clean';
        statusBadge.textContent = '● Сохранено';
      }
    }

    editor.addEventListener('input', () => {
      updateLineNumbers();
      checkDirty();
    });

    editor.addEventListener('scroll', () => {
      lineNumbers.scrollTop = editor.scrollTop;
    });

    editor.addEventListener('click', updateCursor);
    editor.addEventListener('keyup', updateCursor);

    // Tab key support (insert 2 spaces)
    editor.addEventListener('keydown', (e) => {
      if (e.key === 'Tab') {
        e.preventDefault();
        const start = editor.selectionStart;
        const end = editor.selectionEnd;
        editor.value = editor.value.substring(0, start) + '  ' + editor.value.substring(end);
        editor.selectionStart = editor.selectionEnd = start + 2;
        updateLineNumbers();
        checkDirty();
        updateCursor();
      } else if ((e.ctrlKey || e.metaKey) && e.key === 's') {
        e.preventDefault();
        if (!saveBtn.disabled) saveContent();
      }
    });

    async function saveContent() {
      if (isSaving) return;
      isSaving = true;
      saveBtn.disabled = true;
      statusBadge.className = 'status-badge saving';
      statusBadge.textContent = '⏳ Сохранение...';

      try {
        const response = await fetch('/api/config-document', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ yaml: editor.value })
        });
        const data = await response.json();
        if (!response.ok || !data.ok) {
          throw new Error(data.error || 'Ошибка при сохранении');
        }
        initialContent = editor.value;
        checkDirty();
        showToast('✓ Конфигурация успешно сохранена!', 'success');
      } catch (err) {
        statusBadge.className = 'status-badge error';
        statusBadge.textContent = '✕ Ошибка сохранения';
        showToast(err.message, 'error');
        saveBtn.disabled = false;
      } finally {
        isSaving = false;
      }
    }

    saveBtn.addEventListener('click', saveContent);

    copyBtn.addEventListener('click', async () => {
      try {
        await navigator.clipboard.writeText(editor.value);
        showToast('✓ Скопировано в буфер обмена');
      } catch {
        editor.select();
        document.execCommand('copy');
        showToast('✓ Скопировано в буфер обмена');
      }
    });

    window.addEventListener('beforeunload', (e) => {
      if (editor.value !== initialContent) {
        e.preventDefault();
        e.returnValue = '';
      }
    });

    updateLineNumbers();
    updateCursor();
  </script>
</body>
</html>`
}

export function apply(ctx, config = {}) {
  // Inject ownsHost: true for browser clients and wire up the "Open configuration file" button
  // so that clicking it opens our rich Web-based YAML viewer/editor in a new browser tab
  ctx.on('webserver/index-inject', (table) => {
    table.push({
      kind: 'global',
      name: '__DSH_TRANSPORT__',
      value: { ownsHost: true }
    })

    table.push({
      kind: 'script',
      placement: 'body',
      text: `
(function() {
  document.addEventListener('click', function(e) {
    var btn = e.target.closest('button');
    if (!btn) return;
    var txt = (btn.textContent || '').trim();
    if (txt === 'Open configuration file' || txt === '打开配置文件') {
      window.open('/api/config-document', '_blank');
    }
  }, true);
})();
      `.trim()
    })
  })

  const cdpBase = normalizeBaseUrl(config.cdpBaseUrl ?? 'http://127.0.0.1:9222')
  const desktop = {
    port: config.desktopPort ?? 6080,
    path: normalizeDesktopPath(config.desktopPath ?? defaultDesktopPath)
  }
  const pollIntervalMs = config.pollIntervalMs ?? 750

  let state = {
    revision: 0,
    url: null,
    openedAt: 0
  }

  async function cdpFetch(path, init, signal) {
    let lastError
    for (let attempt = 0; attempt < 20; attempt += 1) {
      try {
        const response = await fetch(`${cdpBase}${path}`, { ...init, signal })
        if (!response.ok) throw new Error(`Chromium DevTools returned HTTP ${response.status}`)
        return response
      } catch (error) {
        lastError = error
        if (signal?.aborted) throw error
        await new Promise((resolve) => setTimeout(resolve, 250))
      }
    }
    throw lastError
  }

  async function openUrl(input, signal) {
    const url = normalizeUrl(input)
    const response = await cdpFetch(`/json/new?${encodeURIComponent(url)}`, { method: 'PUT' }, signal)
    const target = await response.json()
    await cdpFetch(`/json/activate/${encodeURIComponent(target.id)}`, {}, signal)
    state = {
      revision: state.revision + 1,
      url,
      openedAt: Date.now()
    }
    return { url, status: 'opened' }
  }

  ctx.systemPrompt.section({
    name: 'tool:browser_open',
    order: 115,
    text: 'Use browser_open only when the user asks to open, show, or hand off a URL in the visible browser desktop. It opens the persistent container Chromium and reveals it for human takeover. When Browser Use tools are available, use those tools for page inspection and interaction instead of treating browser_open as an automation tool. Do not investigate or reinstall browser, VNC, noVNC, or websockify.'
  })

  ctx.tools.register({
    name: 'browser_open',
    description: 'Open an HTTP or HTTPS URL in the visible persistent Chromium desktop and reveal it for human takeover. Use Browser Use tools for page inspection and interaction.',
    parameters: {
      type: 'object',
      additionalProperties: false,
      properties: {
        url: {
          type: 'string',
          description: 'The URL to open. A missing scheme defaults to https://.'
        }
      },
      required: ['url']
    },
    output: {
      schema: {
        type: 'object',
        additionalProperties: false,
        properties: {
          url: { type: 'string' },
          status: { type: 'string' }
        },
        required: ['url', 'status']
      },
      render: (_args, value) => [{
        type: 'text',
        text: `Opened ${value.url} in the embedded browser.`
      }]
    },
    async execute(args, exec) {
      if (typeof args?.url !== 'string') throw new Error('url must be a string')
      return openUrl(args.url, exec.signal)
    }
  })

  ctx.effect(() => {
    // ---------------------------------------------------------------------------
    // Route: /api/config-document (View / Edit cordis.patch.yml directly in Web)
    // ---------------------------------------------------------------------------
    const disposeConfigDocument = ctx.webServer.register({
      kind: 'exact',
      path: '/api/config-document',
      async handler(req, res) {
        if (!isSameOrigin(req)) {
          sendJson(res, 403, { error: 'cross-origin requests are not allowed' })
          return
        }

        const url = new URL(req.url, 'http://127.0.0.1:3080')

        if (req.method === 'GET') {
          try {
            let content = ''
            try {
              content = await fsp.readFile(CONFIG_FILE_PATH, 'utf8')
            } catch (err) {
              if (err.code === 'ENOENT') {
                content = '[]\n'
              } else {
                throw err
              }
            }

            if (url.searchParams.get('raw') === '1') {
              res.writeHead(200, {
                'content-type': 'text/plain; charset=utf-8',
                'cache-control': 'no-store'
              })
              res.end(content)
              return
            }

            if (url.searchParams.get('download') === '1') {
              res.writeHead(200, {
                'content-type': 'application/x-yaml; charset=utf-8',
                'content-disposition': 'attachment; filename="cordis.patch.yml"',
                'cache-control': 'no-store'
              })
              res.end(content)
              return
            }

            const html = renderConfigEditorHtml(content)
            res.writeHead(200, {
              'content-type': 'text/html; charset=utf-8',
              'cache-control': 'no-store',
              'content-length': Buffer.byteLength(html)
            })
            res.end(html)
          } catch (error) {
            sendJson(res, 500, {
              ok: false,
              error: error instanceof Error ? error.message : 'failed to read configuration file'
            })
          }
          return
        }

        if (req.method === 'POST') {
          try {
            const body = await readJson(req)
            if (typeof body?.yaml !== 'string') {
              throw new Error('yaml field is required')
            }

            // Create backup if file exists
            if (fs.existsSync(CONFIG_FILE_PATH)) {
              await fsp.copyFile(CONFIG_FILE_PATH, `${CONFIG_FILE_PATH}.bak`)
            }

            // Write new configuration file
            await fsp.writeFile(CONFIG_FILE_PATH, body.yaml, 'utf8')
            sendJson(res, 200, { ok: true, message: 'Configuration saved successfully' })
          } catch (error) {
            sendJson(res, 400, {
              ok: false,
              error: error instanceof Error ? error.message : 'failed to save configuration file'
            })
          }
          return
        }

        res.writeHead(405)
        res.end()
      }
    })

    const disposeState = ctx.webServer.register({
      kind: 'exact',
      path: '/browser-desktop/state',
      handler(req, res) {
        if (req.method !== 'GET' && req.method !== 'HEAD') {
          res.writeHead(405)
          res.end()
          return
        }
        if (req.method === 'HEAD') {
          res.writeHead(200, { 'cache-control': 'no-store' })
          res.end()
          return
        }
        sendJson(res, 200, { ...state, desktop, pollIntervalMs })
      }
    })

    const disposeOpen = ctx.webServer.register({
      kind: 'exact',
      path: '/browser-desktop/open',
      async handler(req, res) {
        if (req.method !== 'POST') {
          res.writeHead(405)
          res.end()
          return
        }
        if (!isSameOrigin(req)) {
          sendJson(res, 403, { error: 'cross-origin requests are not allowed' })
          return
        }
        try {
          const input = await readJson(req)
          if (typeof input?.url !== 'string') throw new Error('url must be a string')
          sendJson(res, 200, await openUrl(input.url))
        } catch (error) {
          sendJson(res, 400, {
            error: error instanceof Error ? error.message : 'unable to open URL'
          })
        }
      }
    })

    return () => {
      disposeConfigDocument()
      disposeOpen()
      disposeState()
    }
  }, 'browser-desktop: HTTP routes')
}
