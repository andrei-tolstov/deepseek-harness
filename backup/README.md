# Настройка резервного копирования на Google Диск (rclone)

Данный сервис автоматически упаковывает данные `OmniRoute` (настройки, ключи API, маршруты), `DeepSeek Harness` (сессии, конфиги) и рабочей директории в `.tar.gz` архивы и выгружает их на Google Диск по расписанию через `rclone`.

---

## Способы настройки подключения к Google Диску

### Способ 1: Быстрая интерактивная настройка через терминал (Рекомендуется)

Запустите интерактивный конфигуратор `rclone` внутри контейнера:

```bash
docker compose run --rm backup rclone config
```

Шаги мастера настройки:
1. Введите `n` (New remote).
2. Имя remote: введите `gdrive` (или то, что указано в `RCLONE_REMOTE` в `.env`).
3. Тип хранилища: найдите и введите `drive` (Google Drive).
4. `client_id` и `client_secret`: можно оставить пустыми (нажать Enter) или указать собственные Client ID из Google Cloud Console (для более высокой скорости и отсутствия лимитов).
5. `scope`: выберите `1` (Full access: `drive`).
6. `service_account_file`: оставьте пустым (Enter), если настраиваете через аккаунт Google.
7. `Edit advanced config?`: выберите `n`.
8. `Use web browser to automatically authenticate with Google?`:
   - Если настраиваете на локальной машине с браузером: `y`. Откроется окно браузера для авторизации.
   - Если настраиваете на удаленном сервере: выберите `n`, запустите команду авторизации на локальном ПК (`rclone authorize "drive" ...`) и вставьте полученный токен.
9. `Configure this as a Shared Drive (Team Drive)?`: `n` (или `y`, если общий диск).
10. Подтвердите сохранение конфигурации `y` и затем `q` для выхода.

Конфигурационный файл автоматически сохранится в `./backup/rclone.conf`!

---

### Способ 2: Использование Google Service Account (Для удаленных серверов)

Если сервер не имеет браузера, удобнее всего использовать сервисный аккаунт:
1. В [Google Cloud Console](https://console.cloud.google.com/) создайте проект и включите **Google Drive API**.
2. В разделе **IAM & Admin -> Service Accounts** создайте сервисный аккаунт, создайте JSON-ключ и скачайте его.
3. Переименуйте файл в `service_account.json` и положите в папку `./backup/service_account.json`.
4. Создайте папку на Google Диске для бэкапов и выдайте сервисному аккаунту (email вида `...@...iam.gserviceaccount.com`) права **Редактор** на эту папку.
5. Создайте файл `./backup/rclone.conf`:

```ini
[gdrive]
type = drive
scope = drive
service_account_file = /config/rclone/service_account.json
```

---

## Проверка работы

Проверьте подключение к Google Диску:
```bash
docker compose run --rm backup rclone lsd gdrive:
```

Сделать резервную копию вручную прямо сейчас:
```bash
docker compose exec backup /app/backup.sh now
```
или (если контейнер не запущен):
```bash
docker compose run --rm backup now
```

Посмотреть список созданных бэкапов на Google Диске:
```bash
docker compose run --rm backup list
```

---

## Восстановление из бэкапа

1. Скачайте нужный архив с Google Диска:
```bash
docker compose run --rm backup rclone copy gdrive:backups/deepseek-stack/backup_XXXXXXXX_XXXXXX.tar.gz /tmp/
```
2. Распакуйте архив в директорию данных (предварительно остановив сервисы `docker compose stop deepseek-harness omniroute`):
```bash
docker compose run --rm -v omniroute-data:/data/omniroute -v dsh-home:/data/dsh-home backup tar -xzf /tmp/backup_XXXXXXXX_XXXXXX.tar.gz -C /data
```
3. Запустите сервисы обратно:
```bash
docker compose start
```
