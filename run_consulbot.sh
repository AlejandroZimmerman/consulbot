#!/bin/bash
# Una corrida por ventana de 12h (00-12 / 12-00). Si falla, se reintenta en el próximo disparo.

BOT_DIR="/Users/ale/consulbot"
UV="/Users/ale/.local/bin/uv"
TIMESTAMP_FILE="$BOT_DIR/.last_run"
LOCK_DIR="$BOT_DIR/.run_lock"
LOG_FILE="$BOT_DIR/consulbot.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_FILE"
}

HOUR_STR=$(date +%H)
HOUR=$((10#$HOUR_STR))

if [ "$HOUR" -lt 12 ]; then
    WINDOW="00"
else
    WINDOW="12"
fi

WINDOW_KEY="$(date +%Y-%m-%d)_${WINDOW}"

if [ -f "$TIMESTAMP_FILE" ] && [ "$(cat "$TIMESTAMP_FILE")" = "$WINDOW_KEY" ]; then
    exit 0
fi

# mkdir es atómico — evita corridas superpuestas si cron dispara dos veces.
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    log "Corrida omitida: ya hay una instancia en curso"
    exit 0
fi

cleanup() {
    rmdir "$LOCK_DIR" 2>/dev/null || true
}
trap cleanup EXIT

if [ -f "$TIMESTAMP_FILE" ] && [ "$(cat "$TIMESTAMP_FILE")" = "$WINDOW_KEY" ]; then
    exit 0
fi

log "Iniciando consulbot (ventana: $WINDOW_KEY)"
cd "$BOT_DIR"
"$UV" run python bot.py
EXIT_CODE=$?

if [ "$EXIT_CODE" -eq 0 ]; then
    echo "$WINDOW_KEY" > "$TIMESTAMP_FILE"
    log "consulbot finalizado OK"
else
    log "consulbot finalizado con error (exit=$EXIT_CODE). Se reintentara en el proximo disparo."
fi

exit "$EXIT_CODE"
