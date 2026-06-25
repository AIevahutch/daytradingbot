#!/bin/zsh

set -u

PROJECT_DIR="/Users/eva/Documents/Day Trading Bot"
PORT="8501"
HOST="127.0.0.1"
BASE_URL="http://${HOST}:${PORT}/"
HEALTH_URL="http://${HOST}:${PORT}/_stcore/health"
LOG_FILE="${PROJECT_DIR}/logs/dashboard_launcher.log"
WATCHDOG_LOG_FILE="${PROJECT_DIR}/logs/scanner_watchdog.log"
RUNTIME_PY="/Users/eva/.cache/daytradingbot/fastvenv/bin/python"

cd "${PROJECT_DIR}" || exit 1
mkdir -p logs

export STREAMLIT_BROWSER_GATHER_USAGE_STATS=false
export STREAMLIT_SERVER_HEADLESS=true
export STREAMLIT_SERVER_FILE_WATCHER_TYPE=none

open_dashboard() {
  # The timestamp avoids reusing a stale blank browser tab.
  open "${BASE_URL}?launcher=$(date +%s)"
}

dashboard_is_ready() {
  curl -fsS "${HEALTH_URL}" >/dev/null 2>&1
}

start_scanner_if_possible() {
  if [[ "${TRADING_BOT_AUTOSTART_SCANNER:-1}" != "1" ]]; then
    echo "$(date): Scanner autostart disabled." >> "${LOG_FILE}"
    return 0
  fi
  if [[ ! -x "${RUNTIME_PY}" ]]; then
    echo "$(date): Missing scanner Python runtime; scanner not started." >> "${LOG_FILE}"
    return 0
  fi

  "${RUNTIME_PY}" - <<'PY' >> "${LOG_FILE}" 2>&1
from datetime import datetime
from trading_bot.runtime.scanner_process import start_scanner

status = start_scanner()
print(f"{datetime.now().isoformat(timespec='seconds')}: {status.message}; pid={status.pid or '-'}")
PY
}

start_watchdog_if_possible() {
  if [[ "${TRADING_BOT_AUTOSTART_WATCHDOG:-1}" != "1" ]]; then
    echo "$(date): Scanner watchdog autostart disabled." >> "${LOG_FILE}"
    return 0
  fi
  if [[ ! -x "${RUNTIME_PY}" ]]; then
    echo "$(date): Missing scanner Python runtime; watchdog not started." >> "${LOG_FILE}"
    return 0
  fi
  "${RUNTIME_PY}" - <<'PY' >> "${LOG_FILE}" 2>&1
from datetime import datetime
from trading_bot.runtime.scanner_process import start_watchdog

status = start_watchdog()
print(f"{datetime.now().isoformat(timespec='seconds')}: {status.message}; pid={status.pid or '-'}")
PY
}

wait_then_open() {
  for _ in {1..60}; do
    if dashboard_is_ready; then
      open_dashboard
      exit 0
    fi
    sleep 1
  done

  echo "$(date): Dashboard did not become ready after 60 seconds." >> "${LOG_FILE}"
  open_dashboard
  exit 1
}

if [[ ! -x "${RUNTIME_PY}" ]]; then
  RUNTIME_PY=".venv/bin/python"
fi
if [[ ! -x "${RUNTIME_PY}" ]]; then
  echo "$(date): Missing dashboard Python runtime. Run setup before launching." >> "${LOG_FILE}"
  open_dashboard
  exit 1
fi

start_scanner_if_possible
start_watchdog_if_possible

if dashboard_is_ready; then
  open_dashboard
  exit 0
fi

wait_then_open &
exec "${RUNTIME_PY}" -m streamlit run dashboard/app.py \
  --server.port "${PORT}" \
  --server.address "${HOST}" \
  --server.fileWatcherType none \
  >> "${LOG_FILE}" 2>&1
