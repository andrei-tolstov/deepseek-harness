#!/usr/bin/env python3
"""
Скрипт переключения маршрутов OmniRoute на llama-swap (http://llama-swap:8080/v1)
"""

import os
import shutil
import sqlite3
import json
import datetime
import sys

DB_PATH = sys.argv[1] if len(sys.argv) > 1 else '/var/lib/docker/volumes/deepseek_omniroute_data/_data/storage.sqlite'
LLAMA_SWAP_URL = sys.argv[2] if len(sys.argv) > 2 else 'http://llama-swap:8080/v1'

def main():
    if not os.path.exists(DB_PATH):
        print(f"ОШИБКА: База данных OmniRoute не найдена по пути: {DB_PATH}")
        sys.exit(1)

    # 1. Резервная копия базы данных (сохраняется вне тома docker, чтобы не вызывать EACCES)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = os.environ.get("BACKUP_DIR", "/root/backups")
    os.makedirs(backup_dir, exist_ok=True)
    backup_path = os.path.join(backup_dir, f"omniroute_storage_{timestamp}.sqlite.bak")
    shutil.copy2(DB_PATH, backup_path)
    print(f"[1/4] Резервная копия создана: {backup_path}")

    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    # 2. Обновление существующих provider_nodes
    target_node_prefixes = ['coder390', 'fable', 'qwen38', 'bonsai2']
    print(f"[2/4] Обновление base_url для провайдеров {target_node_prefixes} на {LLAMA_SWAP_URL}...")
    
    cur.execute("SELECT id, name, prefix, base_url FROM provider_nodes")
    nodes = cur.fetchall()
    for node_id, name, prefix, base_url in nodes:
        if any(p in (prefix or '').lower() or p in (name or '').lower() for p in target_node_prefixes):
            cur.execute("UPDATE provider_nodes SET base_url = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (LLAMA_SWAP_URL, node_id))
            print(f"  -> provider_node '{name}' ({node_id}): {base_url} => {LLAMA_SWAP_URL}")

    # 3. Обновление существующих provider_connections
    target_conn_ids = ['conn-coder390', 'conn-fable', 'conn-qwen38', 'conn-bonsai2']
    print(f"[3/4] Обновление baseUrl в provider_connections...")
    
    cur.execute("SELECT id, provider, provider_specific_data FROM provider_connections")
    conns = cur.fetchall()
    for conn_id, provider, psd_str in conns:
        if conn_id in target_conn_ids or any(p in conn_id.lower() for p in target_node_prefixes):
            try:
                psd = json.loads(psd_str) if psd_str else {}
            except Exception:
                psd = {}
            old_base = psd.get('baseUrl', '')
            psd['baseUrl'] = LLAMA_SWAP_URL
            psd['autoSync'] = True
            psd['autoFetchModels'] = True
            new_psd_str = json.dumps(psd)
            cur.execute("UPDATE provider_connections SET provider_specific_data = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (new_psd_str, conn_id))
            print(f"  -> provider_connection '{conn_id}': {old_base} => {LLAMA_SWAP_URL}")

    # 4. Регистрация единого провайдера llama-swap Unified
    unified_node_id = 'openai-compatible-chat-llamaswap'
    cur.execute("SELECT id FROM provider_nodes WHERE id = ?", (unified_node_id,))
    if not cur.fetchone():
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        cur.execute("""
            INSERT INTO provider_nodes (id, type, name, prefix, api_type, base_url, chat_path, models_path, custom_headers_json, created_at, updated_at)
            VALUES (?, 'openai-compatible', 'llama-swap GPU Router', 'llamaswap', 'chat', ?, '/chat/completions', '/models', '{}', ?, ?)
        """, (unified_node_id, LLAMA_SWAP_URL, now, now))
        print(f"[4/4] Добавлен узел provider_nodes: {unified_node_id}")
    else:
        cur.execute("UPDATE provider_nodes SET base_url = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (LLAMA_SWAP_URL, unified_node_id))
        print(f"[4/4] Обновлен узел provider_nodes: {unified_node_id}")

    unified_conn_id = 'conn-llamaswap'
    cur.execute("SELECT id FROM provider_connections WHERE id = ?", (unified_conn_id,))
    psd_unified = json.dumps({"baseUrl": LLAMA_SWAP_URL, "autoSync": True, "autoFetchModels": True})
    if not cur.fetchone():
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        cur.execute("""
            INSERT INTO provider_connections (id, provider, auth_type, name, priority, is_active, test_status, provider_specific_data, created_at, updated_at)
            VALUES (?, ?, 'api-key', 'llamaswap-unified-conn', 10, 1, 'active', ?, ?, ?)
        """, (unified_conn_id, unified_node_id, psd_unified, now, now))
        print(f"  -> Добавлено соединение provider_connections: {unified_conn_id}")
    else:
        cur.execute("UPDATE provider_connections SET provider_specific_data = ?, is_active = 1, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (psd_unified, unified_conn_id))
        print(f"  -> Обновлено соединение provider_connections: {unified_conn_id}")

    con.commit()
    con.close()
    print("\n[OK] Настройки OmniRoute успешно обновлены для работы с llama-swap!")

if __name__ == '__main__':
    main()
