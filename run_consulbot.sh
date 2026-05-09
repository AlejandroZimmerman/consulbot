#!/bin/bash
# Wrapper que garantiza una corrida por ventana horaria (00-12 y 12-00).
# Si una corrida falla o queda trunca, vuelve a intentarse en el siguiente disparo.

BOT_DIR="/Users/ale/consulbot"
UV="/Users/ale/.local/bin/uv"
TIMESTAMP_FILE="$BOT_DIR/.last_run"
LOCK_DIR="$BOT_DIR/.run_lock"
LOG_FILE="$BOT_DIR/consulbot.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_FILE"
}

# Determinar ventana actual: "00" (medianoche) o "12" (mediodía)
HOUR_STR=$(date +%H)
HOUR=$((10#$HOUR_STR))

if [ "$HOUR" -lt 12 ]; then
    WINDOW="00"
else
    WINDOW="12"
fi

WINDOW_KEY="$(date +%Y-%m-%d)_${WINDOW}"

# Si ya corrió en esta ventana, salir sin hacer nada
if [ -f "$TIMESTAMP_FILE" ] && [ "$(cat "$TIMESTAMP_FILE")" = "$WINDOW_KEY" ]; then
    exit 0
fi

# Evitar ejecuciones superpuestas.
# mkdir es atómico en POSIX: si ya existe, hay otra corrida en curso.
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    log "Corrida omitida: ya hay una instancia en curso"
    exit 0
fi

cleanup() {
    rmdir "$LOCK_DIR" 2>/dev/null || true
}
trap cleanup EXIT

# Re-chequear la marca después de tomar lock para evitar carreras.
if [ -f "$TIMESTAMP_FILE" ] && [ "$(cat "$TIMESTAMP_FILE")" = "$WINDOW_KEY" ]; then
    exit 0
fi

# Ejecutar el bot
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
