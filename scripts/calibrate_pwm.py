import time
import subprocess
import os

NCT_DIR = '/sys/class/hwmon/hwmon1'
PWM_PATH = f'{NCT_DIR}/pwm2'
ENABLE_PATH = f'{NCT_DIR}/pwm2_enable'

def set_pwm(val):
    with open(ENABLE_PATH, 'w') as f:
        f.write('1')
    with open(PWM_PATH, 'w') as f:
        f.write(str(val))

def get_gpu():
    out = subprocess.check_output(['nvidia-smi', '--query-gpu=temperature.gpu,temperature.memory,power.draw', '--format=csv,noheader,nounits']).decode().strip()
    parts = [p.strip() for p in out.split(',')]
    return int(parts[0]), int(parts[1]), float(parts[2])

print("Stopping service during calibration...")
os.system("systemctl stop v100-fancontrol.service")

# Test progression downwards: 60, 50, 40, 30, 20
test_levels = [60, 50, 40, 30, 20]

for pwm_val in test_levels:
    set_pwm(pwm_val)
    pct = int(pwm_val * 100 / 255)
    print(f"\n--- Testing PWM={pwm_val} ({pct}%) for 45 seconds ---", flush=True)
    for i in range(9):
        time.sleep(5)
        t_gpu, t_mem, pwr = get_gpu()
        print(f"[{i*5+5}s] PWM={pwm_val} ({pct}%) -> GPU: {t_gpu}°C, HBM: {t_mem}°C, Power: {pwr}W", flush=True)
    # Check if temperature is rapidly climbing
    t_gpu, _, _ = get_gpu()
    if t_gpu >= 48:
        print(f"Warning: GPU reached {t_gpu}°C at PWM={pwm_val}, stopping descent.", flush=True)
        break

# Restore safe cooling after test
set_pwm(80)
print("\nCalibration test completed. Restored PWM=80.", flush=True)
