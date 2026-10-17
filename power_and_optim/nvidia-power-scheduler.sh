#!/usr/bin/env bash
set -euo pipefail

# Maximum and minimum graphics clock supported by Tesla V100 32GB
MAX_GRAPHICS_CLOCK=1380
MIN_GRAPHICS_CLOCK=495

# Find all Tesla V100 GPUs by name (returns UUIDs)
get_target_gpus() {
    local gpus
    gpus=$(/usr/bin/nvidia-smi --query-gpu=uuid,name --format=csv,noheader 2>/dev/null | grep -i 'Tesla.*V100' | cut -d',' -f1 | tr -d ' ' || true)
    if [ -n "$gpus" ]; then
        echo "$gpus"
    else
        # Fallback: if no Tesla V100 found by name, try finding GPU with max power limit >= 200W
        /usr/bin/nvidia-smi --query-gpu=uuid,power.max_limit --format=csv,noheader,nounits 2>/dev/null | awk -F',' '$2 >= 200 {gsub(/^[ \t]+|[ \t]+$/, "", $1); print $1}' || true
    fi
}

# Ensure persistence mode is enabled
enable_persistence() {
    local target_gpus
    target_gpus=$(get_target_gpus)
    if [ -n "$target_gpus" ]; then
        for gpu in $target_gpus; do
            /usr/bin/nvidia-smi -i "$gpu" -pm 1 > /dev/null 2>&1 || true
        done
    else
        /usr/bin/nvidia-smi -pm 1 > /dev/null 2>&1 || true
    fi
}

set_day_mode() {
    local target_pl=200
    local target_gpus
    target_gpus=$(get_target_gpus)

    if [ -z "$target_gpus" ]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: No Tesla V100 GPUs found to apply Day Mode!" >&2
        exit 1
    fi

    enable_persistence

    for gpu in $target_gpus; do
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Setting Tesla V100 ($gpu) to Day Mode (${target_pl}W, locked clock ${MAX_GRAPHICS_CLOCK} MHz)..."
        /usr/bin/nvidia-smi -i "$gpu" -pl "${target_pl}"
        /usr/bin/nvidia-smi -i "$gpu" -lgc "${MAX_GRAPHICS_CLOCK}"
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Day mode active on $gpu: PL=${target_pl}W, Clocks locked at ${MAX_GRAPHICS_CLOCK} MHz."
    done
}

set_night_mode() {
    local target_pl=100
    local target_gpus
    target_gpus=$(get_target_gpus)

    if [ -z "$target_gpus" ]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: No Tesla V100 GPUs found to apply Night Mode!" >&2
        exit 1
    fi

    enable_persistence

    for gpu in $target_gpus; do
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Setting Tesla V100 ($gpu) to Night Mode (${target_pl}W, clock ${MIN_GRAPHICS_CLOCK} MHz)..."
        /usr/bin/nvidia-smi -i "$gpu" -lgc "${MIN_GRAPHICS_CLOCK}"
        /usr/bin/nvidia-smi -i "$gpu" -pl "${target_pl}"
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Night mode active on $gpu: PL=${target_pl}W, Clocks set to ${MIN_GRAPHICS_CLOCK} MHz."
    done
}

reset_mode() {
    local target_gpus
    target_gpus=$(get_target_gpus)

    if [ -z "$target_gpus" ]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: No Tesla V100 GPUs found to reset!" >&2
        exit 1
    fi

    for gpu in $target_gpus; do
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Resetting Tesla V100 ($gpu) to factory defaults (250W, auto clocks)..."
        /usr/bin/nvidia-smi -i "$gpu" -rgc
        /usr/bin/nvidia-smi -i "$gpu" -pl 250
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Reset complete on $gpu: PL=250W, Auto DVFS."
    done
}

MODE="${1:-auto}"

case "$MODE" in
    day)
        set_day_mode
        ;;
    night)
        set_night_mode
        ;;
    reset)
        reset_mode
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
        echo "=== NVIDIA GPUs Status ==="
        /usr/bin/nvidia-smi --query-gpu=index,name,uuid,power.limit,power.draw,temperature.gpu,clocks.current.graphics,clocks.max.graphics,clocks.current.memory --format=csv
        ;;
    *)
        echo "Usage: $0 {day|night|auto|reset|status}"
        exit 1
        ;;
esac
