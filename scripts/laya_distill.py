#!/usr/bin/env python3
"""
scripts/laya_distill.py

Комплексный конвейер дистилляции решений и подготовки обучающих данных для Laya System 1
на основе реальных диалогов и траекторий Hermes Agent (плагины hermes-jev, hermes-token-router, hermes-handoff).

Синхронизировано с .agents/skills/laya-distill/scripts/laya_distill.py
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sqlite3
import subprocess
import sys
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


DEFAULT_QUESTIONS = {
    "requires_tools": {
        "type": "noul",
        "instructions": (
            "Determine whether fulfilling this user request requires executing external tools "
            "(filesystem, terminal, web queries, schedule, git), or if direct conversational response is appropriate."
        ),
        "criteria": {
            "true": "Executing shell, reading or writing files, web queries, interacting with system or background tools",
            "false": "Pure conversational reply, greeting, general reasoning or explanation without tool execution",
        },
    },
    "tool_decision": {
        "type": "choice",
        "instructions": (
            "Determine whether external tools or terminal execution are required to fulfill the user request, "
            "or if direct conversational response is appropriate."
        ),
        "criteria": {
            "direct_chat": "Conversational reply, reasoning, code explanation without tool execution",
            "execute_tools": "Executing shell, reading or writing files, web queries, or interacting with tools",
        },
    },
    "category": {
        "type": "choice",
        "instructions": "Select the primary category of tool required for this task.",
        "criteria": {
            "filesystem": "File operations: reading, writing, editing, listing or patching files",
            "terminal_execution": "Running bash, terminal, shell commands, scripts and process execution",
            "web_and_search": "Web browsing, fetching remote URLs, downloading pages and online searches",
            "schedule": "Timers, background alarms, daily or cron schedules and reminders",
            "system": "System utilities, git repositories, workspace configuration and status",
        },
    },
    "difficulty": {
        "type": "score",
        "instructions": "How demanding is it to complete this turn well?",
        "criteria": [
            "trivial",
            "simple",
            "moderate",
            "demanding",
            "extreme",
        ],
    },
    "costly_mistake": {
        "type": "noul",
        "instructions": "A wrong or sloppy answer or destructive command here would be costly or hard to undo.",
        "criteria": {
            "true": "System alteration, destructive commands, file modifications, git push, deployment",
            "false": "Read-only inspection, search, conversational answer, explanation",
        },
    },
}

TOOL_TO_CATEGORY = {
    "web_search": "web_and_search",
    "web_extract": "web_and_search",
    "web_scrape": "web_and_search",
    "fetch_web_page": "web_and_search",
    "terminal": "terminal_execution",
    "exec": "terminal_execution",
    "bash": "terminal_execution",
    "read_file": "filesystem",
    "write_file": "filesystem",
    "edit_file": "filesystem",
    "patch_file": "filesystem",
    "list_dir": "filesystem",
    "file_search": "filesystem",
    "skill_view": "system",
    "skills_list": "system",
    "tool_search": "system",
    "request_toolset": "system",
    "schedule": "schedule",
    "timer": "schedule",
}

DESTRUCTIVE_KEYWORDS = [
    "rm ", "rm -rf", "delete", "drop ", "truncate", "kill ", "killall",
    "reboot", "shutdown", "chown", "chmod 777", "git reset --hard",
    "git push -f", "docker stop", "docker rm", "docker rmi", "systemctl stop"
]


def query_laya_systemone(
    laya_url: str,
    state: str,
    questions: Dict[str, Any],
    timeout: float = 10.0,
) -> Optional[Dict[str, Any]]:
    """Отправляет запрос в инференс-сервер Laya C++ Engine (POST /v1/systemone)."""
    endpoint = f"{laya_url.rstrip('/')}/v1/systemone"
    payload = {"state": state, "questions": questions}
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        endpoint,
        data=data,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None
    return None


def fetch_remote_file(ssh_host: str, ssh_key: str, remote_path: str, local_dest: str) -> bool:
    """Загружает файл с удаленного сервера по scp."""
    print(f"[*] Скачивание {remote_path} с {ssh_host} -> {local_dest}...")
    os.makedirs(os.path.dirname(os.path.abspath(local_dest)), exist_ok=True)
    cmd = ["scp", "-i", ssh_key, f"{ssh_host}:{remote_path}", local_dest]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"[!] Ошибка scp при скачивании {remote_path}: {res.stderr.strip()}")
        return False
    print(f"[+] Файл {os.path.basename(local_dest)} успешно загружен.")
    return True


def extract_turns_from_sqlite(db_path: str) -> List[Dict[str, Any]]:
    """Извлекает диалоговые пары и траектории вызовов инструментов из SQLite базы данных Hermes."""
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"SQLite файл не найден: {db_path}")

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, session_id, role, content, tool_calls, tool_name, timestamp
        FROM messages
        ORDER BY session_id, id ASC
        """
    )
    rows = cur.fetchall()
    conn.close()

    sessions: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        m = {
            "id": r[0],
            "session_id": r[1],
            "role": r[2],
            "content": r[3] or "",
            "tool_calls": r[4],
            "tool_name": r[5],
            "timestamp": r[6],
        }
        sessions.setdefault(m["session_id"], []).append(m)

    extracted: List[Dict[str, Any]] = []

    for sid, msgs in sessions.items():
        for i, m in enumerate(msgs):
            if m["role"] == "user":
                user_text = m["content"].strip()
                if not user_text:
                    continue

                subsequent_tools = []
                assistant_text = ""
                for next_m in msgs[i + 1:]:
                    if next_m["role"] == "user":
                        break
                    if next_m["role"] == "assistant":
                        if next_m["content"]:
                            assistant_text = next_m["content"].strip()
                        if next_m["tool_calls"]:
                            try:
                                tcs = json.loads(next_m["tool_calls"])
                                for tc in tcs:
                                    fn = tc.get("function", {}).get("name")
                                    if fn:
                                        subsequent_tools.append(fn)
                            except Exception:
                                pass
                    elif next_m["role"] == "tool" and next_m["tool_name"]:
                        subsequent_tools.append(next_m["tool_name"])

                extracted.append({
                    "session_id": sid,
                    "turn_id": m["id"],
                    "user_text": user_text,
                    "assistant_text": assistant_text,
                    "called_tools": subsequent_tools,
                })

    return extracted


def evaluate_teacher_judgment(case: Dict[str, Any]) -> Dict[str, Any]:
    """
    Выносит экспертное суждение эталона (Teacher Agent Judgment)
    на основе фактических вызовов инструментов в траектории и правил.
    """
    user_text = case["user_text"]
    text_lower = user_text.lower()
    called_tools = case["called_tools"]

    # 1. Потребность в инструментах и базовая категория
    if called_tools:
        requires_tools = True
        tool_decision = "execute_tools"
        categories = [TOOL_TO_CATEGORY.get(t, "system") for t in called_tools]
        primary_cat = max(set(categories), key=categories.count)

        # Оценка сложности по глубине траектории
        if len(called_tools) >= 4:
            difficulty = "demanding"
        elif len(called_tools) >= 2:
            difficulty = "moderate"
        else:
            difficulty = "simple"
    else:
        # Без вызова инструментов
        requires_tools = False
        tool_decision = "direct_chat"
        primary_cat = "system"

        chat_greetings = ["привет", "здравствуй", "добрый день", "hello", "hi", "кто ты", "как дела"]
        if any(g in text_lower for g in chat_greetings) and len(user_text) < 50:
            difficulty = "trivial"
        elif len(user_text) > 300 or "explain" in text_lower or "почему" in text_lower or "архитектур" in text_lower:
            difficulty = "moderate"
        else:
            difficulty = "simple"

    # 2. Оценка критичности ошибки (costly_mistake)
    costly = any(dk in text_lower for dk in DESTRUCTIVE_KEYWORDS)
    if "sudo " in text_lower or "format" in text_lower or "wipe" in text_lower:
        costly = True

    return {
        "requires_tools": requires_tools,
        "tool_decision": tool_decision,
        "category": primary_cat,
        "difficulty": difficulty,
        "costly_mistake": costly,
        "confidence": 1.0,
    }


def distill_sessions(
    db_path: str,
    jev_log_path: Optional[str] = None,
    laya_url: Optional[str] = "http://192.168.50.101:8080",
    out_train_path: str = "data/laya_distill_train.jsonl",
    out_eval_path: str = "data/laya_distill_eval.jsonl",
    out_report_path: str = "data/laya_distill_report.json",
    eval_split_ratio: float = 0.2,
) -> Dict[str, Any]:
    """Главный процесс дистилляции, сравнения с Laya и генерации калиброванного датасета."""
    os.makedirs(os.path.dirname(os.path.abspath(out_train_path)), exist_ok=True)
    os.makedirs(os.path.dirname(os.path.abspath(out_report_path)), exist_ok=True)

    print(f"[*] Извлечение пользовательских ходов из {db_path}...")
    cases = extract_turns_from_sqlite(db_path)
    print(f"[+] Извлечено ходов: {len(cases)}")

    if not cases:
        print("[!] Нет доступных ходов для обработки.")
        return {}

    dataset_rows: List[Dict[str, Any]] = []
    comparisons: List[Dict[str, Any]] = []

    matches_count = 0
    tested_count = 0
    brier_scores: List[float] = []
    laya_online = False

    for case in cases:
        state_text = case["user_text"]
        teacher = evaluate_teacher_judgment(case)

        laya_pred = {}
        match = None
        laya_conf = None

        if laya_url:
            laya_resp = query_laya_systemone(laya_url, state_text, DEFAULT_QUESTIONS)
            if laya_resp and "answers" in laya_resp:
                laya_online = True
                tested_count += 1
                ans = laya_resp["answers"]

                pred_req = ans.get("requires_tools", {}).get("noul")
                pred_td = ans.get("tool_decision", {}).get("choice")
                pred_cat = ans.get("category", {}).get("choice")
                pred_diff = ans.get("difficulty", {}).get("score")
                pred_cost = ans.get("costly_mistake", {}).get("noul")

                laya_conf = ans.get("tool_decision", {}).get("confidence", 0.0)

                laya_pred = {
                    "requires_tools": pred_req,
                    "tool_decision": pred_td,
                    "category": pred_cat,
                    "difficulty": pred_diff,
                    "costly_mistake": pred_cost,
                    "confidence": laya_conf,
                }

                # Расчет совпадения
                match_td = (pred_td == teacher["tool_decision"])
                match_cat = (pred_cat == teacher["category"]) if teacher["requires_tools"] else True
                match = match_td and match_cat
                if match:
                    matches_count += 1

                # Расчет Brier Score для вероятности noul requires_tools
                prob = ans.get("requires_tools", {}).get("noul", 0.5)
                actual_num = 1.0 if teacher["requires_tools"] else 0.0
                brier = (prob - actual_num) ** 2
                brier_scores.append(brier)

        # Формирование expected по спецификации Laya (choice: str, noul: bool, score: str)
        expected: Dict[str, Any] = {
            "requires_tools": teacher["requires_tools"],
            "tool_decision": teacher["tool_decision"],
            "difficulty": teacher["difficulty"],
            "costly_mistake": teacher["costly_mistake"],
        }
        if teacher["requires_tools"]:
            expected["category"] = teacher["category"]

        is_hard_negative = (match is False) or (laya_conf is not None and laya_conf < 0.65)

        tags = [
            f"session:{case['session_id']}",
            f"decision:{teacher['tool_decision']}",
            f"diff:{teacher['difficulty']}",
        ]
        if is_hard_negative:
            tags.append("priority:hard_negative")

        row = {
            "state": state_text,
            "questions": DEFAULT_QUESTIONS,
            "expected": expected,
            "tags": tags,
            "metadata": {
                "session_id": case["session_id"],
                "turn_id": case["turn_id"],
                "teacher": teacher,
                "laya": laya_pred,
                "match": match,
                "hard_negative": is_hard_negative,
            },
        }
        dataset_rows.append(row)

        comparisons.append({
            "turn_id": case["turn_id"],
            "state": state_text[:80],
            "teacher": teacher["tool_decision"],
            "laya": laya_pred.get("tool_decision"),
            "confidence": laya_conf,
            "match": match,
            "hard_negative": is_hard_negative,
        })

    # Разбиение на обучающую и валидационную выборку
    split_idx = int(len(dataset_rows) * (1.0 - eval_split_ratio))
    train_rows = dataset_rows[:split_idx] if split_idx > 0 else dataset_rows
    eval_rows = dataset_rows[split_idx:] if split_idx < len(dataset_rows) else []

    with open(out_train_path, "w", encoding="utf-8") as f:
        for r in train_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    if eval_rows:
        with open(out_eval_path, "w", encoding="utf-8") as f:
            for r in eval_rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    avg_brier = (sum(brier_scores) / len(brier_scores)) if brier_scores else None
    accuracy = (matches_count / tested_count) if tested_count > 0 else 0.0

    report = {
        "summary": {
            "total_turns": len(cases),
            "train_items": len(train_rows),
            "eval_items": len(eval_rows),
            "laya_online": laya_online,
            "tested_items": tested_count,
            "laya_matches": matches_count,
            "laya_accuracy": round(accuracy, 4),
            "brier_score_requires_tools": round(avg_brier, 4) if avg_brier is not None else None,
            "hard_negatives_count": sum(1 for c in comparisons if c["hard_negative"]),
        },
        "comparisons": comparisons,
    }

    with open(out_report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"[+] Экспорт завершен:")
    print(f"    - Train JSONL : {out_train_path} ({len(train_rows)} строк)")
    print(f"    - Eval JSONL  : {out_eval_path} ({len(eval_rows)} строк)")
    print(f"    - Отчет       : {out_report_path}")
    if tested_count > 0:
        print(f"    - Точность Laya System 1: {matches_count}/{tested_count} ({accuracy*100:.1f}%)")
        if avg_brier is not None:
            print(f"    - Brier Score (requires_tools): {avg_brier:.4f}")

    return report


def main():
    parser = argparse.ArgumentParser(
        description="Laya Distill: Генерация калиброванных обучающих датасетов для Laya System 1"
    )
    parser.add_argument("--db-path", default="hermes_state.db", help="Путь к SQLite базе state.db")
    parser.add_argument("--jev-log", default=None, help="Путь к jev-decisions.jsonl")
    parser.add_argument("--fetch-remote", action="store_true", help="Автоматически скачать файлы с сервера перед анализом")
    parser.add_argument("--ssh-host", default="root@192.168.50.101", help="SSH хост сервера")
    parser.add_argument("--ssh-key", default=r"C:\Users\andrei\.gemini\id_ed25519_user_root", help="SSH приватный ключ")
    parser.add_argument("--remote-db", default="/root/harness/hermes/state.db", help="Удаленный путь к state.db")
    parser.add_argument("--remote-jev-log", default="/root/harness/hermes/logs/jev-decisions.jsonl", help="Удаленный путь к jev-decisions.jsonl")
    parser.add_argument("--laya-url", default="http://192.168.50.101:8080", help="URL Laya /v1/systemone")
    parser.add_argument("--out-train", default="data/laya_distill_train.jsonl", help="Путь к train jsonl")
    parser.add_argument("--out-eval", default="data/laya_distill_eval.jsonl", help="Путь к eval jsonl")
    parser.add_argument("--out-report", default="data/laya_distill_report.json", help="Путь к отчету json")

    args = parser.parse_args()

    if args.fetch_remote:
        fetch_remote_file(args.ssh_host, args.ssh_key, args.remote_db, args.db_path)
        if args.jev_log:
            fetch_remote_file(args.ssh_host, args.ssh_key, args.remote_jev_log, args.jev_log)

    distill_sessions(
        db_path=args.db_path,
        jev_log_path=args.jev_log,
        laya_url=args.laya_url,
        out_train_path=args.out_train,
        out_eval_path=args.out_eval,
        out_report_path=args.out_report,
    )


if __name__ == "__main__":
    main()
