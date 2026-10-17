#!/usr/bin/env python3
"""
.agents/skills/laya-distill/scripts/deploy_laya.py

Автоматизация жизненного цикла дообучения, валидации и деплоя Laya System 1:
1. Валидация схемы обучающего датасета через laya-evals validate
2. Dry-Run проверка размерностей тензоров и батчей через laya-train --dry-run
3. Запуск fine-tuning с целевой функцией RLCD на GPU
4. Горячая перезагрузка C++ движка через /tmp/laya_restart_requested
5. Верификация отклика (jev doctor, healthcheck)
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def run_ssh(host: str, key: str, cmd: str) -> subprocess.CompletedProcess[str]:
    """Выполняет команду на удаленном сервере по SSH."""
    full_cmd = ["ssh", "-i", key, "-o", "StrictHostKeyChecking=no", host, cmd]
    return subprocess.run(full_cmd, capture_output=True, text=True)


def cmd_validate(args: argparse.Namespace) -> bool:
    print(f"[*] Валидация схемы датасета {args.remote_data} через laya-evals...")
    script = f"/root/.unsloth/studio/unsloth_studio/bin/laya-evals validate {args.remote_data}"
    res = run_ssh(args.ssh_host, args.ssh_key, script)
    if res.returncode != 0:
        print(f"[!] Ошибка валидации: {res.stderr or res.stdout}")
        return False
    print(f"[+] Схема датасета валидна!\n{res.stdout.strip()}")
    return True


def cmd_dry_run(args: argparse.Namespace) -> bool:
    print(f"[*] Пробный прогон обучения (Dry-Run) для {args.remote_data}...")
    script = (
        f"/root/.unsloth/studio/unsloth_studio/bin/laya-train "
        f"--data {args.remote_data} "
        f"--base {args.base_checkpoint} "
        f"--dry-run"
    )
    res = run_ssh(args.ssh_host, args.ssh_key, script)
    if res.returncode != 0:
        print(f"[!] Ошибка dry-run: {res.stderr or res.stdout}")
        return False
    print(f"[+] Dry-run успешно завершен:\n{res.stdout.strip()}")
    return True


def cmd_train(args: argparse.Namespace) -> bool:
    print(f"[*] Запуск дообучения модели Laya на GPU ({args.epochs} эпох, loss={args.loss})...")
    eval_flag = f"--eval {args.remote_eval} " if args.remote_eval else ""
    script = (
        f"/root/.unsloth/studio/unsloth_studio/bin/laya-train "
        f"--data {args.remote_data} "
        f"{eval_flag}"
        f"--base {args.base_checkpoint} "
        f"--out {args.output_checkpoint} "
        f"--epochs {args.epochs} "
        f"--micro-batch {args.micro_batch} "
        f"--grad-accum {args.grad_accum} "
        f"--loss {args.loss} "
        f"--shuffle-options "
        f"--device {args.device}"
    )
    res = run_ssh(args.ssh_host, args.ssh_key, script)
    if res.returncode != 0:
        print(f"[!] Ошибка в процессе обучения: {res.stderr or res.stdout}")
        return False
    print(f"[+] Обучение успешно завершено!\n{res.stdout.strip()}")
    return True


def cmd_reload(args: argparse.Namespace) -> bool:
    print("[*] Запрос на горячую перезагрузку весов модели Laya...")
    script = "docker exec deepseek-laya touch /tmp/laya_restart_requested || touch /tmp/laya_restart_requested"
    res = run_ssh(args.ssh_host, args.ssh_key, script)
    if res.returncode != 0:
        print(f"[!] Не удалось отправить сигнал перезагрузки: {res.stderr}")
        return False
    print("[+] Сигнал перезагрузки отправлен. Ожидание 3 секунды...")
    time.sleep(3)
    return True


def cmd_doctor(args: argparse.Namespace) -> bool:
    print("[*] Проверка доступности и задержки Laya System 1...")
    script = (
        "(jev doctor 2>/dev/null || docker exec -u hermes hermes-agent jev doctor 2>/dev/null || true) && "
        "curl -s http://127.0.0.1:8080/health && echo '' && "
        "curl -s http://127.0.0.1:8787/health && echo ''"
    )
    res = run_ssh(args.ssh_host, args.ssh_key, script)
    if res.returncode != 0:
        print(f"[!] Сбой диагностики: {res.stderr or res.stdout}")
        return False
    print(f"[+] Диагностика успешна:\n{res.stdout.strip()}")
    return True


def cmd_pipeline(args: argparse.Namespace) -> bool:
    print("======================================================================")
    print(" [Laya Pipeline] Запуск полного сквозного цикла дообучения и деплоя")
    print("======================================================================")
    if not cmd_validate(args):
        return False
    if not cmd_dry_run(args):
        return False
    if not args.skip_train:
        if not cmd_train(args):
            return False
    if not cmd_reload(args):
        return False
    return cmd_doctor(args)


def main():
    parser = argparse.ArgumentParser(description="Управление обучением и деплоем Laya System 1")
    parser.add_argument("--ssh-host", default="root@192.168.50.101", help="SSH хост сервера")
    parser.add_argument("--ssh-key", default=r"C:\Users\andrei\.gemini\id_ed25519_user_root", help="SSH приватный ключ")
    parser.add_argument("--remote-data", default="/root/deepseek-harness/data/laya_distill_train.jsonl", help="Путь к train jsonl на сервере")
    parser.add_argument("--remote-eval", default="/root/deepseek-harness/data/laya_distill_eval.jsonl", help="Путь к eval jsonl на сервере")
    parser.add_argument("--base-checkpoint", default="/root/deepseek-harness/finetune-checkpoint", help="Базовый чекпоинт")
    parser.add_argument("--output-checkpoint", default="/root/deepseek-harness/finetune-checkpoint-v2", help="Директория сохранения чекпоинта")
    parser.add_argument("--epochs", type=int, default=4, help="Количество эпох")
    parser.add_argument("--micro-batch", type=int, default=8, help="Микробатч")
    parser.add_argument("--grad-accum", type=int, default=8, help="Аккумуляция градиента")
    parser.add_argument("--loss", default="rlcd", choices=["rlcd", "soft-ce"], help="Функция потерь")
    parser.add_argument("--device", default="cuda", help="Устройство обучения")
    parser.add_argument("--skip-train", action="store_true", help="Пропустить обучение, только валидация и перезагрузка")

    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate", help="Валидация схемы обучающих данных")
    sub.add_parser("dry-run", help="Пробный прогон размерностей батчей")
    sub.add_parser("train", help="Запуск fine-tuning на GPU")
    sub.add_parser("reload", help="Горячая перезагрузка весов C++ движка")
    sub.add_parser("doctor", help="Проверка статуса Laya и jev doctor")
    sub.add_parser("pipeline", help="Сквозной цикл (validate -> dry-run -> train -> reload -> doctor)")

    args = parser.parse_args()

    commands = {
        "validate": cmd_validate,
        "dry-run": cmd_dry_run,
        "train": cmd_train,
        "reload": cmd_reload,
        "doctor": cmd_doctor,
        "pipeline": cmd_pipeline,
    }

    success = commands[args.command](args)
    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
