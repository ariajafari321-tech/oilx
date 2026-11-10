---
tags: [oilx, ops]
---
# Cloud Mode: running the bot off the laptop

Added 2026-11-09. Three straight EIA Wednesdays were lost to the machine the bot lived
on: asleep, then a flaky campus connection, then a campus network that hard-resets every
connection to Kalshi. The fix is not a better retry loop. It is to stop depending on the
laptop and its network at all.

## What runs where
The bot runs on GitHub Actions (free hosted runners) on a schedule:

| workflow | when | what |
|---|---|---|
| `oilx cycle` | hourly through the New York day, lighter overnight and weekends | scan, trade, equity desk |
| `oilx EIA burst` | Wednesdays, 10:27–11:37 New York | scan + trade every 2 minutes around the inventory report |
| `oilx refresh data` | weekdays after the close | re-download EIA / CFTC / futures data so the signals never go stale |
| `oilx control` | by hand ("Run workflow") | stop (kill switch), resume, or flatten |

State lives on a `bot-state` branch as one rolling commit: the bot's logs under `out/`,
plus `index.html` + `state.json`, which is the dashboard. Turning on GitHub Pages for
that branch gives a dashboard URL that works from a phone.

The demo API credentials are stored as two GitHub Actions secrets
(`KALSHI_DEMO_KEY_ID`, `KALSHI_DEMO_PRIVATE_KEY`); the code reads them from the
environment and still refuses any non-demo exchange URL.

## Decisions
- **Polling, not a server.** A scheduled job that wakes, works and exits has no uptime
  to manage. The dashboard is a static file regenerated each run.
- **One codebase, two homes.** `web.build_state()` feeds both the local control room
  (`python -m oilx serve`, live controls) and the cloud snapshot (`oilx export-state`,
  read-only). The same `dashboard.html` detects which one it is talking to.
- **Never run both.** The laptop task and the cloud schedule would cancel each other's
  resting quotes. Once the cloud bot is live, turn the laptop one off
  (`scripts\9_autotrade_off.bat`).
- **Quote-source fallbacks are labelled.** If the live CL or OVX quote is unreachable
  from the runner, the scan falls back to the strip's own implied forward and the last
  recorded vol, and says so in `health.json`. A fallback that hides itself is how the
  month-long blind spot happened.

## One-time setup
See the README section "Run it in the cloud".

Related: [[Oilx Build Log]], [[Kalshi Oil Markets]]
