#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_DIR="$ROOT_DIR/data"
BACKUP_DIR="$DATA_DIR/backups"
LOG_DIR="$ROOT_DIR/logs"
LOG_FILE="$LOG_DIR/scrape_loop.log"

INTERVAL_MINUTES="${INTERVAL_MINUTES:-60}"
ONCE=false

if [[ "${1:-}" == "--once" ]]; then
  ONCE=true
fi

mkdir -p "$BACKUP_DIR" "$LOG_DIR"

# Resolve Python: prefer venv, fall back to system python3
if [[ -f "$ROOT_DIR/.venv/bin/python" ]]; then
  PYTHON="$ROOT_DIR/.venv/bin/python"
elif command -v python3 &>/dev/null; then
  PYTHON="python3"
else
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] ERROR: no se encontró Python. Instala el entorno virtual." | tee -a "$LOG_FILE"
  exit 1
fi

# Platforms to scrape — override via env var (space-separated), default to all three
IFS=' ' read -r -a PLATFORM_ARGS <<< "${PLATFORMS:-rappi uber_eats didi_food}"

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Iniciando scrape_loop.sh" | tee -a "$LOG_FILE"
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Python: $PYTHON" | tee -a "$LOG_FILE"
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Plataformas: ${PLATFORM_ARGS[*]}" | tee -a "$LOG_FILE"
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Intervalo: ${INTERVAL_MINUTES} min" | tee -a "$LOG_FILE"

run_cycle() {
  local ts csv_backup_path
  ts="$(date -u +%Y%m%dT%H%M%SZ)"

  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Ejecutando scraping..." | tee -a "$LOG_FILE"

  if (cd "$ROOT_DIR" && "$PYTHON" -m scraper.runner --append --platforms "${PLATFORM_ARGS[@]}") >> "$LOG_FILE" 2>&1; then
    csv_backup_path="$BACKUP_DIR/competitive_data_${ts}.csv"

    if [[ -f "$DATA_DIR/competitive_data.csv" ]]; then
      cp "$DATA_DIR/competitive_data.csv" "$csv_backup_path"
      echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Snapshot guardado: $csv_backup_path" | tee -a "$LOG_FILE"
    else
      echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] WARNING: No existe competitive_data.csv para respaldar" | tee -a "$LOG_FILE"
    fi

    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Ciclo completado correctamente" | tee -a "$LOG_FILE"
  else
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] ERROR: El scraping falló. Revisa $LOG_FILE" | tee -a "$LOG_FILE"
  fi
}

if [[ "$ONCE" == "true" ]]; then
  run_cycle
  exit 0
fi

while true; do
  run_cycle
  sleep "$((INTERVAL_MINUTES * 60))"
done
