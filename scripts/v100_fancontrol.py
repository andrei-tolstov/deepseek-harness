#!/usr/bin/env python3
"""
Tesla V100 Automatic Fan Controller for Huananzhi X79 (Inverted PWM Mode)
Controls server fan on CPU_FAN (pwm2) and SFAN3 (pwm3) based purely on GPU temperature.
Inverted logic: 255 is lowest speed (quietest), 0 is 100% full speed (maximum airflow).
Calibrated for idle target temperature of ~40°C.
"""

import os
import glob
import time
import signal
import subprocess
import sys

def get_hwmon_dir(name_pattern):
    for d in glob.glob('/sys/class/hwmon/hwmon*'):
        try:
            with open(os.path.join(d, 'name')) as f:
                if name_pattern in f.read().lower():
                    return d
        except Exception:
            pass
    return None

NCT_DIR = get_hwmon_dir('nct')

if not NCT_DIR:
    sys.stderr.write("ERROR: NCT6779 hwmon device not found!\n")
    sys.exit(1)

# Control channels: pwm2 (CPU_FAN header) and pwm3 (SFAN3)
CHANNELS = [2, 3]

def set_channel_pwm(channel, value):
    try:
        val = max(0, min(255, int(value)))
        en_path = os.path.join(NCT_DIR, f'pwm{channel}_enable')
        pwm_path = os.path.join(NCT_DIR, f'pwm{channel}')
        with open(en_path, 'w') as f:
            f.write('1')
        with open(pwm_path, 'w') as f:
            f.write(str(val))
    except Exception as e:
        sys.stderr.write(f"Failed to set pwm{channel}: {e}\n")

def set_all_pwm(value):
    for ch in CHANNELS:
        set_channel_pwm(ch, value)

def get_gpu_temp():
    try:
        cmd = ['nvidia-smi', '--query-gpu=temperature.gpu', '--format=csv,noheader,nounits']
        res = subprocess.check_output(cmd, timeout=3).decode().strip()
        temps = [int(line.strip()) for line in res.splitlines() if line.strip().isdigit()]
        if temps:
            return max(temps)
    except Exception:
        pass
    return None

def calc_inverted_pwm(temp):
    """
    Inverted PWM curve calibrated for ~40°C idle target:
    PWM 255 = ~0% fan speed (slowest/quietest, idle reaches 56°C)
    PWM 160-170 = ~35% fan speed (stabilizes ~41-43°C)
    PWM 145-150 = ~42% fan speed (stabilizes ~39-41°C) - TARGET IDLE
    PWM 120 = ~53% fan speed (stabilizes ~36-38°C)
    PWM 80  = ~69% fan speed (active inference load)
    PWM 40  = ~84% fan speed (heavy load)
    PWM 0   = 100% full speed (emergency/fail-safe)
    """
    if temp <= 38:
        return 170   # Very quiet mode, allows warming towards 40°C
    elif temp <= 42:
        return 150   # Optimal quiet idle baseline (~40°C)
    elif temp <= 48:
        return 125   # Light load cooling
    elif temp <= 58:
        return 90    # Moderate inference cooling
    elif temp <= 68:
        return 50    # High load cooling
    elif temp <= 74:
        return 20    # Near-maximum cooling
    else:
        return 0     # 100% full speed (emergency over 74°C)

def cleanup(signum, frame):
    sys.stdout.write("Exiting fancontrol daemon: reverting to BIOS automatic / safe mode...\n")
    try:
        # Revert pwm2 to BIOS SmartFan (enable=5) or full speed (0)
        with open(os.path.join(NCT_DIR, 'pwm2_enable'), 'w') as f:
            f.write('5')
    except Exception:
        set_all_pwm(0)
    sys.exit(0)

signal.signal(signal.SIGTERM, cleanup)
signal.signal(signal.SIGINT, cleanup)

def main():
    print(f"Starting Tesla V100 inverted fan controller on {NCT_DIR} (channels {CHANNELS})", flush=True)
    # Start at calibrated baseline
    current_pwm = 150
    set_all_pwm(current_pwm)
    fail_count = 0
    iteration = 0

    while True:
        gpu_t = get_gpu_temp()

        if gpu_t is None:
            fail_count += 1
            if fail_count >= 3:
                # Emergency full speed in inverted logic is 0
                set_all_pwm(0)
                current_pwm = 0
                print("WARNING: Failed to read GPU temperature! Forcing 100% fan speed (PWM=0).", flush=True)
        else:
            fail_count = 0
            target_pwm = calc_inverted_pwm(gpu_t)

            # Apply change if target differs
            if abs(target_pwm - current_pwm) >= 10 or (target_pwm == 0 and current_pwm != 0):
                set_all_pwm(target_pwm)
                current_pwm = target_pwm
                # Inverted duty cycle percentage: (255 - PWM) / 255 * 100
                duty_pct = int((255 - target_pwm) * 100 / 255)
                print(f"GPU Temp: {gpu_t}°C -> Set Inverted PWM: {target_pwm}/255 (Fan Speed: ~{duty_pct}%)", flush=True)

        iteration += 1
        # Heartbeat every 30s
        if iteration % 10 == 0:
            duty_pct = int((255 - current_pwm) * 100 / 255)
            print(f"[Heartbeat] GPU Temp: {gpu_t}°C | PWM: {current_pwm}/255 (~{duty_pct}% speed)", flush=True)

        time.sleep(3)

if __name__ == '__main__':
    main()
