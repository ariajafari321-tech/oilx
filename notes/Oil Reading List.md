---
tags: [oilx, reading, papers]
---
# Oil Reading List

Papers that would directly upgrade oilx, in priority order - each with what it changes in
the code. All are on SSRN/NBER or free; Bloomberg's terminal (BBLS <GO> / RES) has most,
and a Baruch library login covers the journals.

## Tier 1 — changes the models
1. **Gorton, Hayashi & Rouwenhorst, "The Fundamentals of Commodity Futures Returns"**
   (Review of Finance, 2013). *The* inventory-to-futures-basis paper: the formal version
   of why `inv_level` proxies carry. Upgrade: calibrate the inventory→expected-return
   mapping instead of a plain z-score.
2. **Szymanowska, de Roon, Nijman & van den Goorbergh, "An Anatomy of Commodity Futures
   Risk Premia"** (JF 2014). Splits spot premia from term premia. Upgrade: when a paid
   curve arrives, separate "price goes up" from "roll earns" in the backtest.
3. **Fuertes, Miffre & Rallis, "Tactical allocation in commodity futures markets:
   Combining momentum and term structure signals"** (JBF 2010). The momentum×curve
   double-sort already referenced in the desk note. Upgrade: condition `mom`'s weight on
   the curve - the "curves may carry more momentum" idea, with evidence.
4. **Moskowitz, Ooi & Pedersen, "Time Series Momentum"** (JFE 2012). The canonical
   vol-scaled trend construction `mom` imitates. Upgrade: their exact spec + the
   12-month horizon decay table.
5. **Kilian, "Not All Oil Price Shocks Are Alike"** (AER 2009). Demand vs supply shock
   decomposition. Upgrade: the regime layer - crack-led rallies (demand) should read
   differently from supply shocks like 2026; right now `crack` can't tell them apart.

## Tier 2 — changes the evaluation
6. **Erb & Harvey, "The Strategic and Tactical Value of Commodity Futures"** (FAJ 2006).
   Why commodity "returns" claims so often mislead (roll, rebalancing). Good hygiene.
7. **Kang, Rouwenhorst & Tang, "A Tale of Two Premiums: The Role of Hedgers and
   Speculators in Commodity Futures Markets"** (JF 2020). COT positioning as *liquidity
   provision*: upgrade `cot` from crowding-fade to the hedging-pressure framing, and the
   horizon at which each works.
8. **Singleton, "Investor Flows and the 2008 Boom/Bust in Oil Prices"** (Mgmt Sci 2014).
   The flows-vs-fundamentals fight; context for why positioning signals are contested.
9. **Baumeister & Kilian, "Forty Years of Oil Price Fluctuations"** (JEP 2016). The
   honest survey of how hard oil forecasting is - calibrates ambition.
10. **Hamilton, "Causes and Consequences of the Oil Shock of 2007-08"** (Brookings 2009).
    Event-study craft for the 2026 shock note.

## Also useful
- CME's **"Introduction to Crack Spreads"** and WTI/MCL contract specs (free, cmegroup.com)
  - the microstructure facts the futures expression relies on.
- EIA's **"This Week in Petroleum"** archive - how the agency itself narrates the
  Wednesday number `inv_surprise` trades.
- **Bürgi, Deng & Whelan** (prediction-market maker/taker returns) - already load-bearing
  in pmx; the bridge paper between the two projects.

Related: [[Signals]], [[Kalshi Oil Markets]], [[Evaluation and Honesty Checks]]
