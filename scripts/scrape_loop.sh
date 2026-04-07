#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_DIR="$ROOT_DIR/data"
BACKUP_DIR="$DATA_DIR/backups"
LOG_DIR="$ROOT_DIR/logs"
LOG_FILE="$LOG_DIR/scrape_loop.log"

INTERVAL_MINUTES="${INTERVAL_MINUTES:-60}"
PLATFORMS="${PLATFORMS:-rappi uber_eats didi_food}"
ONCE=false

if [[ "${1:-}" == "--once" ]]; then
  ONCE=true
fi

mkdir -p "$BACKUP_DIR" "$LOG_DIR"

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Iniciando scrape_loop.sh" | tee -a "$LOG_FILE"
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Plataformas: $PLATFORMS" | tee -a "$LOG_FILE"
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Intervalo: ${INTERVAL_MINUTES} min" | tee -a "$LOG_FILE"

read -r -a PLATFORM_ARGS <<< "$PLATFORMS"

run_cycle() {
  local ts csv_backup_path
  ts="$(date -u +%Y%m%dT%H%M%SZ)"

  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Ejecutando scraping..." | tee -a "$LOG_FILE"

  if (cd "$ROOT_DIR" && python -m scraper.runner --append --platforms "${PLATFORM_ARGS[@]}") >> "$LOG_FILE" 2>&1; then
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
