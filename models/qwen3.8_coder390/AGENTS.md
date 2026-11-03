# DEPLOYMENT RUNBOOK
## Модель: Qwen3.8-27B-Coder390-EfficientThink (NInfer V2 MTP + Vision)
## Целевая платформа: NVIDIA Tesla V100 32 GB (Volta, sm_70)

1. Только CUDA 12.8 для компиляции pod V100 (sm_70).
2. Эталонный пакет: NInfer V2 MTP `W4A4-W8A8` (`Qwen3.8-27B-Coder390-EfficientThink-NVFP4-W4A4-W8A8-MTP-NInferV2.ninfer`).
3. Поддерживается мультимодальный режим Vision (`--vision`, media-cache-mib 512, media-live-mib 1024).
4. Встроенный MTP (--spec mtp --draft-tokens 3 --lm-head-draft).
5. Параметр reasoning_effort: "xhigh", "medium" или "low" (не использовать "high").

## Загрузка модели и сборка

Скрипт загрузки и сборки образа:
```bash
./setup_and_build.sh
```

Активная модель подключается через симлинк:
`model_v100.ninfer -> Qwen3.8-27B-Coder390-EfficientThink-NVFP4-W4A4-W8A8-MTP-NInferV2.ninfer`
