# oilx: a risk-controlled, multi-signal WTI crude strategy on alternative data

Sibling project to **pmx** (the cross-exchange prediction market monitor in this folder).
Same rules: **paper only, no orders, every claim gets graded, and the honesty checks can
say no.**

## The thesis in one paragraph (plain English)

Oil is unusual among big markets: the real-world facts that move it are published on a
public schedule. Every Wednesday the US government says how much crude is sitting in
storage (the EIA report); every Friday the regulator says how speculators are positioned
(the CFTC report); every day the futures market says how much refiners earn turning crude
into fuel (the crack spread). None of these is secret, but each tends to move prices in a
known direction for a while. oilx reads five such signals, averages them into one view,
and then — the actual point of the project — **keeps the risk constant**: the position is
sized so the book targets 10% annualized volatility, capped at 1.5x, and a 15% drawdown
flattens everything for two weeks. The claim isn't "we predict oil"; it's "small, honest
edges survive only inside a risk budget."

## Signals (one sentence each)

| signal | one sentence |
|---|---|
| `mom` | Oil trends; follow the 3- and 12-month move at constant risk. |
| `crack` | Rising refining margins (3-2-1 crack spread) mean refiners bid harder for crude. |
| `inv_level` | Stocks far below the seasonal norm = a tight market (the same economics as backwardation). |
| `inv_surprise` | The Wednesday event: a bigger-than-seasonal draw is bullish, a surprise build bearish, fading as it goes stale. |
| `cot` | When speculators are crowded at a 3-year extreme, fade it; inside the dead zone, no view. |

Weights are set **walk-forward** (yearly, from trailing 5-year standalone Sharpe, floored
at 10% and never sign-flipped), so the combined book never uses a weight it couldn't have
known at the time.

## Data (all free, no keys)

| file | source | series |
|---|---|---|
| `eia_*_weekly.csv` | EIA dnav history pages | US crude stocks ex-SPR, Cushing, gasoline (1982→) |
| `cftc_cot_wti_weekly.csv` | CFTC public Socrata API | NYMEX WTI legacy COT (1986→) |
| `cl/rbob/heatoil_front_daily.csv` | Yahoo chart API | front-month futures (2005→) |
| `uso/xop_adj_daily.csv` | Yahoo chart API | USO, XOP adjusted (2006→) |
| `ovx_daily.csv`, `irx_daily.csv` | Yahoo chart API | crude VIX, 13-week T-bill |
| `wti/brent_spot_daily.csv` | Alpha Vantage (EIA spot) | daily spot (1986→), cross-checks |

Weekly data joins the daily panel **on its release date plus one safety day** (EIA:
week-ending Friday → available the next Thursday; COT: as-of Tuesday → available the next
Monday). Look-ahead through release lags is the classic oil-backtest bug.

## Quick start

```
scripts\1_setup.bat        # venv outside OneDrive + pip install + pytest (24 tests, offline)
scripts\2_fetch.bat        # refresh all raw files from the free sources
scripts\3_backtest.bat     # panel -> backtest -> data\out\tearsheet.html
python -m oilx now         # today's scores and target position
scripts\5_kalshi_scan.bat  # price Kalshi's WTI markets off the OVX digital model + log signals
python -m oilx kalshi-score  # grade settled signals: P&L + Brier vs Kalshi's own mid
scripts\6_kalshi_demo.bat  # scan, then place capped limit orders on Kalshi's DEMO exchange
                           # (needs demo API key files in secrets\ - see secrets\README.md)
scripts\7_desk_note.bat    # the daily briefing: direction + size, ranked paper expressions
                           # (futures/curve/USO/Kalshi/equities), exposure map
scripts\run_cycle.bat      # ONE unattended scan + demo-order cycle, no pauses, logged to
                           # data\out\auto_run_log.txt (this is what you'd schedule)
python -m oilx equity-pick   # rank the 17-name oil-equity universe off the live signal
                             # state + news tilt; log one paper pick (graded vs XLE)
python -m oilx equity-score  # grade every logged equity pick vs XLE (>= 5 days old)
scripts\12_eia_burst.bat   # EIA release mode: scan+trade every 2 min for 70 min
                           # (11_wake_for_eia.bat schedules this for Wed 10:27am + wake)
```

## Making it fully automatic (deliberately your call, not the bot's)

An autonomous trading loop - even on the demo exchange - should be switched on by the
account owner, not installed by software. If you want one cycle per hour while the PC is
on, open Command Prompt yourself and paste (one line):

```
schtasks /Create /F /SC HOURLY /TN "oilx demo trader" /TR "cmd /c \"\"C:\Users\AriaJ\OneDrive - The City University of New York\Desktop\Oil Lab\oilx\scripts\run_cycle.bat\"\""
```

Check it ran: `data\out\auto_run_log.txt`. Turn it off anytime:
`schtasks /Delete /F /TN "oilx demo trader"`. The per-cycle caps (5 orders, 10 contracts
each, position limit, flagged signals never trade) apply to every scheduled run.

## Kalshi: the pmx bridge

`oilx kalshi-scan` prices Kalshi's WTI strips (daily/weekly/monthly) as digital options:
N(d2) with OVX as the vol and the live CL front as the forward, Kalshi's real fee, and
three guards - a stale-underlying check against each strip's own implied forward, the
25-cent "too good to be real" suspect flag (pmx's circuit breaker), and liquidity/time
windows. Signals are logged and graded after settlement (`kalshi-score`, Brier vs
Kalshi's mid). `kalshi-demo` executes clean signals on the demo exchange only -
structurally: the order client refuses any non-demo URL. Details: `notes/Kalshi Oil
Markets.md`.

## Honest results (2007 → Oct 2026, net of 2bp/turnover + 0.5bp/day)

Net Sharpe **0.30 ± 0.23** at 8.4% realized vol (10% target), max drawdown −17%, versus
buy-and-hold WTI at −0.09 over the same window. The scrambled-returns bootstrap puts the
result above ~90% of luck draws — *suggestive, not proven*. The inverted book loses
(−0.41). 2022–now is slightly negative; that is reported, not tuned away. A backtest that
finds huge free money is a bug report until proven otherwise (see pmx build log).

## Layout

```
oilx/
  config.toml      every number the strategy uses, commented
  oilx/            config.py data.py panel.py signals.py risk.py backtest.py stats.py report.py cli.py
  tests/           12 offline tests incl. planted-signal recovery and no-peek checks
  notes/           Obsidian notes (this folder is already a vault)
  data/raw         seed CSVs      data/out  backtest outputs + tearsheet
```

## Disclaimer

Research and educational use; paper trading only. Nothing here is investment advice.


## Run it in the cloud (no laptop, no campus Wi-Fi)

The bot can run on GitHub's free hosted runners instead of this computer. One-time setup:

1. Create a GitHub account and an empty repository (for example `oilx`).
2. In this folder, rename `cloud-setup\dot-github` to `.github` and move it up one level
   so it sits beside `oilx\` and `scripts\` (these are the workflow files; they ship in
   a plain folder because they are yours to switch on).
3. Put this folder in the repository (GitHub Desktop: *Add local repository* ->
   *Publish*). `secrets/` is git-ignored and never leaves the laptop.
4. In the repository: *Settings -> Secrets and variables -> Actions -> New repository
   secret*, twice:
   - `KALSHI_DEMO_KEY_ID` - the key id (the contents of `secrets/Public Key.txt`)
   - `KALSHI_DEMO_PRIVATE_KEY` - the whole private key file, from `-----BEGIN` to `-----END`
5. *Actions* tab -> enable workflows -> open **oilx cycle** -> *Run workflow* once.
6. *Settings -> Pages* -> deploy from branch `bot-state`, folder `/ (root)`. That URL is
   the dashboard; it works from a phone. (Pages on a private repository needs GitHub
   Pro, which is free for students.)
7. Turn the laptop schedule off (`scripts\9_autotrade_off.bat`) so two bots don't fight.

Controls live in the *Actions* tab: **oilx control** (stop / resume / flatten) and
**oilx cycle** (run now). Details: `notes/Cloud Mode.md`.
