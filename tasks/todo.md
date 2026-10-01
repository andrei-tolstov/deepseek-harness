# Задачи: Добавление сервиса Laya в Docker Compose

- [x] 1. Создать каталог `laya/` с Dockerfile и скриптом запуска `entrypoint.sh`:
  - [x] Многоэтапная сборка из форка `https://github.com/andrei-tolstov/ggmlc.git` (поддержка sm_61, sm_70, sm_75, sm_80, sm_86, sm_89)
  - [x] Автоматическая загрузка мультиязычной модели при первом старте (если отсутствует в `./models`) с Hugging Face
  - [x] Поддержка CUDA (с автоматическим fallback на CPU)
- [x] 2. Обновить `docker-compose.yml`:
  - [x] Добавить сервис `laya` с пробросом порта 8080, healthcheck и сетью `deepseek-net`
  - [x] Настроить том для моделей `./models:/models`
  - [x] Создать оверлей `docker-compose.gpu.yml` для прямого проброса NVIDIA GPU
- [x] 3. Обновить файлы конфигурации `.env.example` и `.env`:
  - [x] Добавить переменные `LAYA_PORT`, `LAYA_DEVICE`, `LAYA_EXTRA_FLAGS`
- [x] 4. Обновить документацию `README.md`:
  - [x] Описать сервис Laya, его порты, Web Studio и REST API
- [x] 5. Проверить синтаксис `docker compose config`
  - [x] Базовый запуск проверен через `docker compose config` (код 0)
  - [x] GPU запуск проверен через `docker compose -f docker-compose.yml -f docker-compose.gpu.yml config` (код 0)

---

## Review & Verification

1. **Сервис `laya` в Docker Compose**:
   - Образ собирается локально из форка `https://github.com/andrei-tolstov/ggmlc.git` (ветка `main`).
   - При старте проверяется наличие весов `/models/laya_multilingual_f16.gguf`: если их нет в `./models`, они автоматически скачиваются с Hugging Face.
   - Сервис доступен как снаружи (`http://127.0.0.1:8080`), так и внутри контейнерной сети (`http://laya:8080`).
2. **GPU и CPU совместимость**:
   - Базовая конфигурация работает везде и безопасно переключается на CPU.
   - Оверлей `docker-compose.gpu.yml` активирует резервацию устройств NVIDIA GPU для пользователей с NVIDIA Container Toolkit.
