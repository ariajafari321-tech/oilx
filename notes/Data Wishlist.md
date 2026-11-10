---
tags: [oilx, data, wishlist]
---
# Data Wishlist

What each item unlocks, in priority order. Items marked **(me)** Claude fetches from free
sources; everything else is an Aria-at-a-terminal or Aria-download job, whenever
convenient. Drop files in `data/incoming/` and say so in chat.

## Tier 1 - Bloomberg exports (free via Baruch; the real unlocks)
1. **WTI curve history**: `CL1 Comdty` ... `CL6 Comdty`, field `PX_LAST`, daily,
   2005-01-01 to today (`=BDH(...)` in Excel, one column per ticker). Optional extra
   fields: `PX_VOLUME`, `OPEN_INT`.
   *Unlocks: real carry signal, momentum-x-curve double-sort backtest, contract-maturity
   selection. The single biggest upgrade in the project.*
2. **WTI options volatility**: export the `CL1 Comdty OVDV` screen (current surface),
   plus BDH history if the fields cooperate: 30-day ATM implied vol and the 25-delta
   risk reversal.
   *Unlocks: skew-corrected Kalshi fair value (fixes the known ~4-5c left-tail blind
   spot found 2026-10-15).*
3. **Brent curve**: `CO1 Comdty` ... `CO3 Comdty`, PX_LAST daily, 2005+.
   *Unlocks: the Brent-WTI convergence study with term structure (is the war premium in
   the front or the whole curve).*
4. **Tanker freight**: `BDTI Index` and `BCTI Index` (Baltic dirty/clean tanker),
   daily history.
   *Unlocks: freight-rate input, the early tell on the Hormuz premium easing.*
5. **EIA survey consensus** (if findable): Bloomberg's economist survey for the weekly
   DOE/EIA crude inventory change (ECO/ECOS screens; the median forecast series).
   *Unlocks: TRUE inventory surprise (actual minus consensus) instead of actual minus
   seasonal. Even recording the median manually each Tuesday going forward is valuable.*
6. Optional: product curves `XB1/XB2 Comdty` (RBOB), `HO1/HO2 Comdty`.
   *Unlocks: forward crack spreads, not just spot cracks.*

## Tier 2 - free downloads (Aria, 5 minutes each)
7. **Baker Hughes US rig count** workbook (bakerhughes.com -> rig count -> North America
   download). *Unlocks: supply-response signal, slow but orthogonal.*
8. Any broker/desk primers on oil she gets from networking (Goldman/MS commodity
   research PDFs etc.). *Unlocks: desk-flavored context for notes and interviews.*

## Tier 2b - free, Claude's job **(me)**
- EIA weekly demand ("product supplied"), refinery runs/utilization, imports/exports,
  SPR stocks - same dnav source as the stocks series.
- CFTC *disaggregated* COT (managed money split) via the same public API.
- Forward daily collection of the live CL curve from Yahoo (no backfill, but it accrues).

## Tier 3 - papers (library / SSRN / NBER)
- Kilian, "Not All Oil Price Shocks Are Alike" (AER 2009) - demand vs supply shock
  decomposition; the 2026 regime detector.
- Szymanowska, de Roon, Nijman, van den Goorbergh, "An Anatomy of Commodity Futures
  Risk Premia" (JF 2014) - pairs with the curve data.
- Kang, Rouwenhorst, Tang, "A Tale of Two Premiums" (JF 2020) - rebuilds the COT signal
  around hedging pressure and horizons.
- Erb, Harvey, "The Strategic and Tactical Value of Commodity Futures" (FAJ 2006).
- Baumeister, Kilian, "Forty Years of Oil Price Fluctuations" (JEP 2016).
- Hamilton, "Causes and Consequences of the Oil Shock of 2007-08" (Brookings 2009).
- Book, for interviews as much as the model: Morgan Downey, *Oil 101* - the standard
  desk recommendation for how the physical market actually works.

## Known-paid / do not buy
- Intraday CL data around EIA releases (would locate exactly where the surprise edge
  lives; Databento offers free starter credits - worth a look before paying anyone).
- CME DataMine settlement archive (Bloomberg covers the need for free).
- Vintage (as-first-printed) EIA numbers; revisions are small, lowest priority.

Rule for all of it: new data enters through the walk-forward discipline in
[[Evaluation and Honesty Checks]] - tested changes, never midnight tweaks.
