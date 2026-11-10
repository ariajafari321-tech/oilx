---
tags: [oilx, kalshi, options]
---
# Kalshi Oil Markets

The bridge between the two projects: pmx's options-implied fair value scanner, pointed at
Kalshi's WTI price markets. A contract like `KXWTI-26OCT1514-T94.49` ("WTI above $94.49
at 2:30pm ET") is a digital option on the CL front-month settle, which is exactly what
pmx priced on BTC/ETH off Deribit's vol surface.

## What Kalshi lists (discovered 2026-10-15, public API)
- **KXWTI** — daily, settles 2:30pm ET (the CL settlement window), 50¢ strikes
- **KXWTIW** (weekly range), **KXWTIMONTHLY** (monthly), **KXWTIH / KXWTI15M** (hourly /
  15-minute — too fast for this model, skipped)
- **KXWTIMAX / KXWTIMIN / KXWHENWTI** — high/low/"when will it hit" = path-dependent;
  excluded, same as pmx excluded "will BTC *hit* X" (they need a barrier model)
- Also KXBRENTW/KXBRENTMON and heating oil — extensions once a Brent vol source exists.

## The model, and what it can't see
`oilx/kalshi.py`: P(settle > K) = N(d2) with σ = **OVX**/100 (Cboe's 30-day oil implied
vol) and F = the live CL front quote. One vol for all strikes — **no skew** — because oil
has no free options chain the way crypto has Deribit. The pmx skew lesson promptly showed
up in live data: on the Nov 3 strip, model and market agreed within 1-4¢ across the whole
curve *except* the deep left tail, where Kalshi priced ~5½% for WTI < $73 in 19 days vs
the flat-vol model's ~1%. That gap is crash-risk skew (put protection bid), not free
money, and a flat-vol model must never sell that tail. The scanner's min-edge and suspect
thresholds keep it out, and the note stands as the recorded reason why.

## The guards (what makes it a bot and not a backtest fantasy)
1. **Stale-underlying guard.** Each strip's own prices imply a forward (where YES crosses
   50¢). If the CL quote disagrees with it by more than half a settlement-horizon sd, the
   whole strip is flagged `stale_underlying` and nothing trades. First live test: fed
   yesterday's close against today's strip → 7 fake "edges" up to 30¢, all flagged. This
   is pmx's "price from the book, never from summary fields," automated.
2. **Suspect guard** (pmx circuit breaker): any edge > 25¢ is labelled too-good, sorted
   last, never traded.
3. **Liquidity, time windows, fees**: OI ≥ 100, 2h–45d to close (flat 30-day vol is wrong
   outside that), Kalshi's actual ceil-to-the-cent fee on every quoted edge.

## Grading and the demo exchange
- Every emitted signal is appended to `data/out/kalshi_signals_log.jsonl`; `kalshi-score`
  fetches settlements and reports realized P&L per contract and **Brier score of the
  model vs Kalshi's own mid**, with distinct settlement times as the honest N — `pmx
  score`, verbatim. The pmx result (Kalshi's crypto prices beat the model, Brier 0.210 vs
  0.243) is the null hypothesis here too.
- `kalshi-demo` places capped limit orders on Kalshi's **demo exchange** for clean
  signals: demo-only by construction (the client refuses any base URL without "demo"),
  credentials from `secrets/` (gitignored), buy-only limit orders, ≤10 contracts each,
  ≤5 orders per run, position cap, flagged signals never trade. Demo fills prove the
  pipeline executes; they say nothing about real liquidity (the demo book is thin and
  separate from production prices).

## First live scan (2026-10-15, demonstration snapshot)
With the correct forward (94.71, the strip's own implied): **zero signals** — the honest
answer, consistent with the pmx finding that liquid Kalshi strips are priced by
professionals running this same model with better inputs. The system's output over time
is the scored log, not any single day's "edge."

Run: `scripts\5_kalshi_scan.bat` (scan + log), `python -m oilx kalshi-score` (grade),
`scripts\6_kalshi_demo.bat` (demo orders, needs secrets). Her network note: campus Wi-Fi
has blocked Kalshi before (see pmx build log 2026-10-06); run from home.

## The three tiers (2026-10-28)
After two weeks of zero trades (believed correct at the time; see the correction below), the system grew two more ways to interact with
the book — each graded separately by `kalshi-score`:

| tier | question it asks | size | threshold |
|---|---|---|---|
| **main** | is the displayed price wrong by more than the fee? | 10 contracts | edge ≥ 5¢ |
| **probe** | are 3–5¢ "edges" real? (calibration spend) | 2 contracts | 3¢ ≤ edge < 5¢ |
| **maker** | at what price would I be happy to be filled? | 5/quote, ≤6 resting | fair − 2¢ |

Maker quotes are passive by construction (capped at ask−1¢, floored at the bid), posted
only on liquid (OI ≥ 500) non-stale strips, cancelled and reposted every cycle, and
counted against the open-contract cap as if they all fill. Makers pay no Kalshi fee, so
a fill at fair−2¢ is +EV *conditional on the model* — the scored log tests exactly that
condition. Brent markets (KXBRENTW/KXBRENTMON) are now scanned too, priced off BZ=F with
OVX as a documented vol proxy and a +2¢ edge penalty for the proxy risk.

## Correction (2026-11-09): the live scanner was blind until this date
Every live "zero signals" before 2026-11-09 was a parsing failure, not a finding: Kalshi
had renamed its quote and open-interest fields and the parser read every market as
empty. The offline result above (Oct 15) stands, because it ran on a hand-built
snapshot. The first real live scan (CL 86.44, OVX 57) showed the model within ~1c of
the market near the money and 2–4c too cheap in both wings, which is why the scanner
now carries a wing guard (`wing_z`) and a schema canary. Details in [[Oilx Build Log]].

Related: [[Options-Implied Fair Value]] (pmx), [[Oilx Build Log]], [[Signals]]
