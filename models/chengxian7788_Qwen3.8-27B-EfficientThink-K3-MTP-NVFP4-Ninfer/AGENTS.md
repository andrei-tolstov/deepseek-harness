# DEPLOYMENT RUNBOOK
## Модель: chengxian7788/Qwen3.8-27B-EfficientThink-K3-MTP-NVFP4-Ninfer
## Целевая платформа: NVIDIA Tesla V100 32 GB (Volta, sm_70)

1. Движок: NInfer v3 (`liujun-7788/ninfer-v3-v100`, CUDA 12.8, sm_70).
2. Формат артефакта: NInfer v3 `nvfp4-mixed` (`qwen3_8_27b_nvfp4_EfficientThink_K3.ninfer`, 24.81 GB).
   - Внимание: в VRAM загружается 21.0 GiB (веса DFlash2 внутри артефакта пропускаются при использовании `--spec mtp`).
3. Мультимодальность: Vision включен (`--vision --media-cache-mib 512 --media-live-mib 1024`).
4. Спекулятивное декодирование: MTP K=3 (`--spec mtp --draft-tokens 3 --lm-head-draft`).
5. Контекст:
   - Максимум: 235,520 токенов (`--max-context 235520 --kv-capacity 235520`) с запасом ~528 MiB VRAM.
   - Безопасный режим: 215,040 токенов (`--max-context 215040 --kv-capacity auto`) с запасом ~1.20 GiB VRAM.
6. Параметр reasoning_effort: "xhigh", "medium" или "low".
7. Порт по умолчанию: 8087 (внутри контейнера 8080).

## Быстрый запуск
```bash
./setup_and_build.sh
./switch-to-efficientthink-k3.sh
```
