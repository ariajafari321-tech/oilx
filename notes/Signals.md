---
tags: [oilx, signals]
---
# Signals

Each signal maps the daily panel to a score in [-1, +1] (`oilx/signals.py`), built only
from data available that day. Scores are tanh-squashed z-scores, so no single wild print
can take an outsized position. Economics first, construction second, failure mode third.

## mom — trend
- **Economics:** oil supply and demand adjust slowly (wells and refineries take years),
  so shocks get absorbed over months; prices drift rather than jump to the new truth.
- **Construction:** vol-scaled 63-day return plus 252-day return skipping the latest
  month (the standard "12-1" to dodge short-term reversal), averaged, squashed.
- **Dies when:** choppy, range-bound regimes; V-shaped reversals (it is always late).

## crack — the refiner's margin
- **Economics:** the 3-2-1 crack spread = (2 × gasoline + 1 × diesel − 3 × crude)/3 per
  barrel, the market price of refining. Fat margins → refiners maximize runs → crude
  demand pull. It is also a nowcast of *product* demand that crude hasn't priced yet.
- **Construction:** 252-day z-score of the crack level, squashed.
- **Dies when:** the margin is driven by refining *capacity* shocks rather than demand
  (an outage raises the crack while crude demand falls — see [[The 2026 Oil Shock]]).

## inv_level — scarcity vs the season
- **Economics:** inventories are the market's shock absorber. Stocks far below the
  seasonal norm mean little buffer, so prompt prices carry a scarcity premium — the same
  economics that puts the futures curve in backwardation (Gorton–Rouwenhorst's
  inventory–futures-basis link). With no free futures-curve history, the inventory level
  is the honest proxy for carry.
- **Construction:** level minus the same-week-of-year mean over the trailing 5 years
  (current year excluded), scaled by the seasonal spread; long when below.
- **Dies when:** structural shifts (shale build-out, SPR releases) move the "normal"
  level faster than a 5-year window can learn it. Standalone it *lost* money in this
  backtest (−0.08 Sharpe) and the walk-forward floors it at 10% weight — kept because the
  economics is sound and the floor is cheap insurance, and reported because hiding a
  losing leg is how backtests lie.

## inv_surprise — the Wednesday event
- **Economics:** the weekly change vs its seasonal expectation is news; a surprise draw
  is bullish. Documented event drift, and the reason desks watch 10:30am Wednesday.
- **Construction:** (actual Δ − seasonal mean Δ) / trailing surprise spread, available
  only from the release date (+1 safety day), decaying by half each week of staleness.
- **Dies when:** the surprise is already priced in the first minutes (the drift part is
  the claim, and it is the weakest link); or when SPR operations pollute the number.

## cot — positioning crowding
- **Economics:** the CFTC's Commitments of Traders report says how net-long speculators
  are. At multi-year extremes the marginal buyer is already in; flows mean-revert.
- **Construction:** net non-commercial position as a share of open interest, z-scored
  against 3 years, dead zone inside |z| ≤ 1, faded beyond it.
- **Dies when:** "crowded" keeps being right in a one-way regime (2007, 1H 2026); the
  dead zone and the walk-forward floor limit the bleed.

## What's deliberately *not* here
- **News sentiment** — available live via Alpha Vantage, but with no deep history it
  can't be backtested honestly, so it is display-only in `oilx now`.
- **Real curve carry** — needs CL contract-level history (paid). `data.next_cl_contracts`
  reads the live front-vs-second spread for the dashboard; the backtest uses inv_level
  as the economic stand-in.
- **The options-implied fair value model from pmx** — now built against Kalshi's WTI
  markets, as its own scanner rather than a backtested signal: see [[Kalshi Oil Markets]].

Related: [[Thesis in Plain English]], [[Evaluation and Honesty Checks]]
