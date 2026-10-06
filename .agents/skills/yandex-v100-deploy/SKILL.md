---
name: yandex-v100-deploy
description: >-
  Развертывание и эксплуатация виртуальных машин с GPU NVIDIA Tesla V100 в Yandex Cloud.
  Включает полный двухэтапный сценарий: проверку квот, подготовку кастомного образа диска
  с моделью через сверхдешевую прерываемую ВМ (без GPU), сборку образа, запуск прерываемой
  ВМ gpu-standard-v2 (Tesla V100 32GB), настройку драйверов, инференса llama-server и SSH-туннелирования API.
---

# Развертывание ВМ с NVIDIA Tesla V100 в Yandex Cloud

Данный скил регламентирует полный процесс развертывания ВМ с GPU NVIDIA Tesla V100 (32 ГБ VRAM) с максимальной экономией средств (прерываемый режим `--preemptible`, двухэтапная подготовка диска).

---

## 0. Архитектура и стратегия экономии

1. **Никогда не скачивать модели и не настраивать диск на активной GPU-машине**:
   * Стоимость ВМ с Tesla V100 в разы выше обычной ВМ.
   * Все подготовительные операции (скачивание 20-30 ГБ весов модели, установка Docker, настройка окружения) выполняются на дешевой прерываемой ВМ без GPU (`standard-v3`, 2 vCPU c долей 20%, 4 ГБ RAM).
2. **Создание кастомного образа диска (Custom Image)**:
   * После подготовки диск останавливается и сохраняется в образ Yandex Cloud (`yc compute image create`).
   * Временная ВМ сборщика сразу удаляется.
3. **Запуск боевой GPU-ноды из готового образа**:
   * Машина с Tesla V100 стартует из сохраненного образа и сразу готова к инференсу без траты времени на скачивание.

---

## 1. Проверка и запрос квот на GPU

По умолчанию в Yandex Cloud установлена нулевая квота на GPU устройства (`compute.instanceGpus.count: 0`).

### Проверка текущих квот:
```bash
# Получить ID облака:
CLOUD_ID=$(yc config get cloud-id)

# Проверить лимиты сервиса compute:
yc quota-manager quota-limit list \
  --resource-type resource-manager.cloud \
  --resource-id "$CLOUD_ID" \
  --service compute | grep -A 2 -E "instanceGpus|instanceT4Gpus"
```

### Запрос квоты на 1 GPU Tesla V100:
Если `compute.instanceGpus.count` равен `0`, отправить запрос (запрос на 1 GPU одобряется моментально):
```bash
yc quota-manager quota-request create \
  --resource-type resource-manager.cloud \
  --resource-id "$CLOUD_ID" \
  --desired-limit quota-id=compute.instanceGpus.count,value=1
```

---

## 2. Проверка наличия готового образа

Перед созданием билдера проверить, нет ли уже собранного образа для нужной модели:
```bash
yc compute image list
```
Если образ с семейством/именем модели найден и имеет статус `READY`, **перейти сразу к Разделу 4**.

---

## 3. Этап подготовки образа через дешевую ВМ (без GPU)

### 3.1. Расчет размера SSD диска
Формула минимального диска:
$$\text{Диск} = \text{Размер ОС + Docker (~7 ГБ)} + \text{Swap (4 ГБ)} + \text{Размер файлов модели} + \text{Запас (+5 ГБ)}$$
*Пример для модели 22 ГБ*: $7 + 4 + 22 + 5 = 38$ ГБ $\rightarrow$ берем **43 ГБ `network-ssd`** (чистый остаток доступного места $\approx 5.7$ ГБ).

### 3.2. Создание дешевой прерываемой ВМ-сборщика
```bash
yc compute instance create \
  --name disk-builder \
  --zone ru-central1-a \
  --platform standard-v3 \
  --cores 2 \
  --core-fraction 20 \
  --memory 4 \
  --preemptible \
  --network-interface subnet-name=default-ru-central1-a,nat-ip-version=ipv4,security-group-ids=<SECURITY_GROUP_ID> \
  --create-boot-disk image-folder-id=standard-images,image-family=debian-12,size=<CALCULATED_SIZE>GB,type=network-ssd \
  --metadata ssh-keys="modelgpu:<SSH_PUBLIC_KEY>"
```

### 3.3. Настройка окружения и загрузка модели внутри билдера
Подключиться по SSH к сборщику и выполнить:
1. **Настройка системы и Docker**:
   ```bash
   sudo apt-get update && sudo apt-get install -y curl wget git jq ca-certificates
   curl -fsSL https://get.docker.com | sudo sh
   sudo usermod -aG docker modelgpu
   
   # NVIDIA Container Toolkit (для проброса GPU в контейнеры при будущем старте на V100):
   curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
   curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
     sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
     sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
   sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
   sudo nvidia-ctk runtime configure --runtime=docker
   ```

2. **Создание Swap 4 ГБ и настройка лимитов**:
   ```bash
   sudo fallocate -l 4G /swapfile
   sudo chmod 600 /swapfile
   sudo mkswap /swapfile
   sudo swapon /swapfile
   echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
   echo '* soft memlock unlimited' | sudo tee -a /etc/security/limits.conf
   echo '* hard memlock unlimited' | sudo tee -a /etc/security/limits.conf
   ```

3. **Загрузка модели и подготовка docker-compose**:
   * Скачать веса модели в директорию `/root/model/<model_name>/`.
   * Предзагрузить docker-образ инференса: `sudo docker pull ghcr.io/ggml-org/llama.cpp:server-cuda`.
   * Создать `docker-compose.yml` и службу `systemd` (например, `/etc/systemd/system/inference.service` с `enabled`).
   * Очистить кэши: `sudo apt-get clean && rm -rf /tmp/* ~/.cache`.

4. **Обязательная проверка перед созданием образа**:
   ```bash
   sudo reboot
   ```
   Убедиться, что ВМ поднимается и доступна по SSH после перезагрузки.

### 3.4. Создание кастомного образа и удаление билдера
```bash
# Остановить билдер:
yc compute instance stop disk-builder

# Получить ID загрузочного диска:
DISK_ID=$(yc compute instance get disk-builder --format json | jq -r .boot_disk.disk_id)

# Создать образ диска:
yc compute image create \
  --name "<MODEL_NAME>-v100-ready" \
  --family "<MODEL_FAMILY>" \
  --source-disk-id "$DISK_ID"

# Удалить временную машину сборщика:
yc compute instance delete disk-builder
```

---

## 4. Развертывание боевой ВМ с Tesla V100

### 4.1. Параметры платформы `gpu-standard-v2`
* Архитектура: Intel Cascade Lake with NVIDIA Tesla V100 SXM2 (32 ГБ VRAM).
* Минимальное соотношение на 1 GPU: **8 vCPU, 48 ГБ RAM**.
* Флаг `--preemptible`: обеспечивает скидку ~70–80%.

### 4.2. Команда создания ВМ
```bash
yc compute instance create \
  --name "<MODEL_NAME>-gpu-v100" \
  --zone ru-central1-a \
  --platform gpu-standard-v2 \
  --cores 8 \
  --memory 48 \
  --gpus 1 \
  --preemptible \
  --network-interface subnet-name=default-ru-central1-a,nat-ip-version=ipv4,security-group-ids=<SECURITY_GROUP_ID> \
  --create-boot-disk image-id=<IMAGE_ID>,size=<DISK_SIZE>GB,type=network-ssd \
  --metadata ssh-keys="modelgpu:<SSH_PUBLIC_KEY>"
```

---

## 5. Настройка драйверов NVIDIA и запуск инференса

После запуска ВМ с V100:

1. **Установка драйвера NVIDIA на Debian 12**:
   ```bash
   sudo sed -i 's/main/main contrib non-free non-free-firmware/g' /etc/apt/sources.list
   sudo apt-get update
   sudo DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
     linux-headers-amd64 nvidia-driver nvidia-smi firmware-misc-nonfree
   
   # Перезагрузка для выгрузки nouveau и загрузки модуля nvidia:
   sudo reboot
   ```

2. **Проверка обнаружения Tesla V100**:
   ```bash
   nvidia-smi
   ```
   Должно отобразиться: `Tesla V100-SXM2-32GB` с объемом памяти `32768MiB`.

3. **Особенности параметров `llama-server` для V100 (Volta sm_70)**:
   * **Flash Attention**: Аргумент требует явного значения: `--flash-attn on`. (Одиночный `--flash-attn` без значения приводит к синтаксической ошибке CLI).
   * **Режимы памяти**: Использовать дефолтный mmap или `--load-mode auto`.
   * **Проектор mmproj**: Для мультимодальных моделей (VL) при ограниченной VRAM выгружать Vision Tower в системную RAM хоста: `--no-mmproj-offload --threads 8`.
   * **Квантование KV-кэша**: `-ctk q8_0 -ctv q8_0` снижает потребление контекста в разы при 256k токенов.

---

## 6. Настройка доступа к API через SSH-туннель

Чтобы не открывать порт API наружу в интернет без аутентификации, поднять постоянный SSH-туннель на клиентском сервере (например, `192.168.50.101`):

1. Авторизовать публичный ключ клиента на GPU ВМ:
   ```bash
   echo "<CLIENT_PUBLIC_KEY>" >> ~/.ssh/authorized_keys
   ```

2. Создать службу `systemd` на стороне клиента (`/etc/systemd/system/qwen-tunnel.service`):
   ```ini
   [Unit]
   Description=SSH Tunnel to Remote Qwen3.8 GPU Node (Tesla V100)
   After=network.target

   [Service]
   Type=simple
   User=root
   ExecStart=/usr/bin/ssh -NT -o ServerAliveInterval=15 -o ServerAliveCountMax=3 -o ExitOnForwardFailure=yes -o StrictHostKeyChecking=no -i /root/.ssh/id_ed25519 -L 0.0.0.0:8081:127.0.0.1:8080 modelgpu@<GPU_VM_IP>
   Restart=always
   RestartSec=5

   [Install]
   WantedBy=multi-user.target
   ```

3. Запустить службу:
   ```bash
   systemctl daemon-reload
   systemctl enable --now qwen-tunnel.service
   ```

4. Проверить доступность API:
   ```bash
   curl http://localhost:8081/health
   curl http://localhost:8081/v1/models
   ```
