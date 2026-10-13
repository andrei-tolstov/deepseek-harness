path = '/sys/class/hwmon/hwmon1/pwm3_enable'
for v in [0, 1, 2, 3, 5]:
    try:
        with open(path, 'w') as f:
            f.write(str(v))
        cur = open(path).read().strip()
        print(f"wrote {v} -> read {cur}")
    except Exception as e:
        print(f"wrote {v} -> error {e}")
