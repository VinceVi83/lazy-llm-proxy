#!/usr/bin/env bash
set -u

WOL_FLAG="/tmp/wol"
LOG_PATH="#LOG_PATH#/debug.log"
PROJECT_PATH="#PROJECT_PATH#/llm-gateway"

log() {
    printf '%s wol-detect: %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$1" >> "$LOG_PATH"
}

if [[ -e "$WOL_FLAG" ]]; then
    log "WOL found, launching auto-suspend.py"
    rm -f "$WOL_FLAG"
    nohup python3 "$PROJECT_PATH/auto-suspend.py" >> "$LOG_PATH" 2>&1 &
    exit 0
fi

log "No WOL detected, no action"
exit 0

