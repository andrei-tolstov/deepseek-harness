#!/usr/bin/env bash
set -euo pipefail

# Enable Persistence Mode to keep settings stable
/usr/bin/nvidia-smi -pm 1 > /dev/null 2>&1 || true

# Maximum graphics clock supported by this Tesla V100 32GB (1380 MHz)
MAX_GRAPHICS_CLOCK=1380

set_day_mode() {
    local target_pl=160
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Setting Tesla V100 to Day Mode (${target_pl}W, locked clock ${MAX_GRAPHICS_CLOCK} MHz)..."
    /usr/bin/nvidia-smi -pl "${target_pl}"
    /usr/bin/nvidia-smi -lgc "${MAX_GRAPHICS_CLOCK}"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Day mode active: PL=${target_pl}W, Clocks locked at ${MAX_GRAPHICS_CLOCK} MHz."
}

set_night_mode() {
    local target_pl=100
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Setting Tesla V100 to Night Mode (${target_pl}W, auto DVFS clocks)..."
    /usr/bin/nvidia-smi -rgc > /dev/null 2>&1 || true
    /usr/bin/nvidia-smi -pl "${target_pl}"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Night mode active: PL=${target_pl}W, Clocks reset to auto."
}

MODE="${1:-auto}"

case "$MODE" in
    day)
        set_day_mode
        ;;
    night)
        set_night_mode
        ;;
    auto)
        CURRENT_HOUR=$(date +%H | sed 's/^0*//')
        CURRENT_HOUR="${CURRENT_HOUR:-0}"
        if [ "$CURRENT_HOUR" -ge 23 ] || [ "$CURRENT_HOUR" -lt 9 ]; then
            set_night_mode
        else
            set_day_mode
        fi
        ;;
    status)
        /usr/bin/nvidia-smi --query-gpu=power.limit,power.draw,temperature.gpu,clocks.current.graphics,clocks.max.graphics,clocks.current.memory --format=csv
        ;;
    *)
        echo "Usage: $0 {day|night|auto|status}"
        exit 1
        ;;
esac
