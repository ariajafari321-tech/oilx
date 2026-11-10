---
tags: [oilx, instruments, concept]
---
# Instrument Menu and Exposure Map

What `oilx recommend` chooses between, and why the same bullish-crude view is a different
trade in each wrapper. Plain English first, mechanics after.

## The menu

**1. Futures (CL, or MCL micro = 100 bbl).** The direct expression. You post margin, you
get ~1:1 crude exposure, and every month you *roll* to the next contract. The roll is
where the curve matters: in **backwardation** (near price above far) rolling a long
*earns* the slope; in **contango** it *pays* it. That's why the desk note ranks futures
first only when the curve agrees with the direction - a long in steep contango fights a
headwind every month. The "oil curves carry momentum" idea is exactly this interaction:
trend signals have historically worked better when the term structure leans the same way
(Fuertes-Miffre-Rallis double-sort, in [[Oil Reading List]]). Live curve read:
`oilx recommend` quotes the front two contracts when Yahoo is reachable; the backtest
can't include real curve history until a paid source exists.

**2. USO (futures ETF).** Same exposure in a cash/brokerage account, no margin account
needed. It holds the futures and does the rolling for you - and charges you the contango
cost plus fees. Fine for weeks; expensive for years (USO's long-run chart vs spot crude
is the tuition bill). The 2020 reverse split is the cautionary tale.

**3. Kalshi binaries.** Defined-risk, dated bets on a level ("WTI above X at 2:30pm").
Right wrapper for the *event* views - the Wednesday EIA release - not for the standing
book. Priced by the [[Kalshi Oil Markets]] scanner; demo-exchange execution only.

**4. Equities.** A crude view with a company attached. Rule of thumb: equity beta to
crude of roughly 0.5-1.5x depending on bucket, plus idiosyncratic risk the signal says
nothing about (hedging policy, basin mix, balance sheet, buybacks). Right wrapper when
the view is *months to years* (the equity compounds operating leverage), wrong wrapper
for a two-week signal.

## The exposure buckets (the part people get wrong)

- **E&P "pure plays"** (FANG, DVN, PR, OXY, APA): revenue ≈ barrels × price, so they are
  the closest equity to a crude position. Check the hedge book - a heavily hedged
  producer is a bond with drama.
- **Integrateds** (XOM, CVX): upstream + refining + chemicals. Diluted, steadier; partly
  self-hedged because refining gains when crude (their input) falls.
- **Refiners** (MPC, VLO, PSX): **not a crude bet.** A refiner buys crude and sells
  gasoline/diesel; its margin is the crack spread - oilx's `crack` signal is literally
  their income statement. "Marathon Petroleum as an oil play" is the classic mix-up:
  Marathon *Oil* (MRO), the producer, was absorbed by ConocoPhillips in 2024; the
  surviving Marathon (MPC) is the refiner. In 2026 this mattered enormously: cracks went
  from ~$20 to $60+/bbl while US crude lagged seaborne barrels, so refiners and E&Ps
  told opposite stories ([[The 2026 Oil Shock]]).
- **Services** (SLB, HAL): paid from producers' *capex budgets*, which respond to price
  with a lag of quarters. A derivative of a derivative.
- **Tankers** (FRO, STNG): freight rates, not oil price - they monetize disruption and
  rerouting. The 2026 Hormuz closure regime is their showcase.
- **ETFs**: XOP ≈ diversified E&P beta; XLE ≈ XOM+CVX in a trench coat; USO ≈ futures
  (above). Pick by which bucket you actually want.

## How the desk note uses this
Direction and size come from the risk layer (one view, vol-budgeted). The menu maps that
view to a wrapper by horizon and mechanics: futures for the clean directional view (curve
permitting), USO when it must live in a cash account, Kalshi for the dated event, an E&P
or XOP for the multi-month version. Refiners enter only as a `crack`-signal expression,
never as "oil exposure."

*Paper framework; not investment advice. Company facts drift with M&A - verify before
leaning on any single name.*

Related: [[Thesis in Plain English]], [[Risk Layer]], [[Kalshi Oil Markets]]
