import time
import subprocess

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

# Start from current 56C and test PWM values down to reach ~40C
for target in [180, 160, 140]:
    set_pwm(target)
    print(f"\n--- Testing inverted PWM={target} (quieter mode) for 90 seconds ---", flush=True)
    for i in range(9):
        time.sleep(10)
        tg, tm, pw = get_gpu()
        print(f"[{(i+1)*10}s] PWM={target} -> GPU: {tg}°C, HBM: {tm}°C", flush=True)
