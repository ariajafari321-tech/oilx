#!/usr/bin/env bash
# One hosted run of the oilx bot (GitHub Actions). Usage: cloud_cycle.sh <mode>
#   cycle    scan + trade + equity desk            (the hourly job)
#   burst    EIA release mode: every 2 min for 70 min, starting 10:27 New York
#   stop     set the KILL switch, cancel quotes, close positions
#   resume   clear the KILL switch
#   flatten  cancel quotes and close positions, keep trading enabled
#
# State lives on the `bot-state` branch, checked out at ./_state by the workflow:
#   _state/out/        the bot's logs and files (restored into data/out each run)
#   _state/index.html  the dashboard, _state/state.json what it shows
# Nothing here ever touches the laptop or the network it is on.
set -uo pipefail
MODE="${1:-cycle}"
STATE=_state
mkdir -p data/out "$STATE/out" "$STATE/vendor"
cp -r "$STATE/out/." data/out/ 2>/dev/null || true
LOG=data/out/auto_run_log.txt
run() { echo "\$ oilx $*" >>"$LOG"; python -m oilx "$@" >>"$LOG" 2>&1 || echo "(exit $?)" >>"$LOG"; }

{ echo; echo "===== cloud $MODE $(date -u +%FT%TZ) ====="; } >>"$LOG"
case "$MODE" in
  cycle)   run kalshi-scan; run kalshi-demo; run equity-pick ;;
  burst)   run burst --wait-until 10:27 --max-wait 45 --minutes 70 --interval 120; run equity-pick ;;
  stop)    run stop ;;
  resume)  run resume ;;
  flatten) run flatten ;;
  *) echo "unknown mode $MODE" >&2; exit 2 ;;
esac
tail -n 4000 "$LOG" >"$LOG.tmp" && mv "$LOG.tmp" "$LOG"     # keep the log bounded
python -m oilx export-state >>"$LOG" 2>&1 || echo "export-state failed" >>"$LOG"

cp -r data/out/. "$STATE/out/"
cp data/out/state.json "$STATE/state.json" 2>/dev/null || true
cp oilx/dashboard.html "$STATE/index.html"
cp oilx/vendor/*.js "$STATE/vendor/"
touch "$STATE/.nojekyll"
tail -n 25 "$LOG"
