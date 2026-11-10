---
tags: [oilx, index]
---
# oilx: the Oil Lab strategy

> [!info] What this is
> A **paper-only** WTI crude strategy that reads five public, scheduled data sources,
> combines them into one view, and spends most of its engineering on **not blowing up**:
> volatility targeting, a leverage cap, a drawdown kill switch, and release-lag hygiene.
> It reuses the pmx culture (this folder's other project): synthetic-world tests,
> both-tails honesty checks, and a build log of decisions.

## One-paragraph summary
Every week the US government publishes how much crude is in storage (the **EIA**, the
Energy Information Administration, on Wednesdays) and how speculators are positioned (the
**CFTC**, the futures regulator, on Fridays); every day the futures market publishes the
**crack spread** (what a refiner earns turning 3 barrels of crude into 2 of gasoline and
1 of diesel). oilx turns those plus trend and inventory scarcity into five scores in
[-1, +1], averages them with weights it could have known at the time, and sizes one
long/short WTI position to a 10% volatility budget. Backtested 2007→2026 with costs:
net Sharpe 0.30 ± 0.23 vs −0.09 for buy-and-hold, and the result beats ~90% of a
scrambled-returns luck distribution. *Suggestive, not proven* — and the write-up says so.

## Reading order
1. [[Thesis in Plain English]] — the elevator version
2. [[Signals]] — the five signals, one honest sentence each
3. [[Risk Layer]] — vol targeting, kill switch, costs
4. [[Evaluation and Honesty Checks]] — walk-forward, bootstrap null, both tails
5. [[Data Pipelines]] — where every number comes from, and the release-lag rule
6. [[The 2026 Oil Shock]] — why the recent data looks wild
7. [[Oilx Build Log]] — decisions and alternatives, pmx-style
8. [[Interview Talking Points]] — how to present this in S&T recruiting

## How to run
`scripts\1_setup.bat` → `scripts\2_fetch.bat` → `scripts\3_backtest.bat`; the tearsheet
opens from `data\out\tearsheet.html`. `python -m oilx now` prints today's scores.
