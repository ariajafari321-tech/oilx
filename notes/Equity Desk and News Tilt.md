---
tags: [oilx, research, equities, news]
---
# Equity Desk and News Tilt

Added 2026-10-28. The question a real desk asks is not "long or short crude?" but
"**which instrument carries this view best?**" — the same view is worth different amounts
in different wrappers.

## The universe (17 names + XLE as the yardstick)

| bucket | names | what it expresses | stated priors |
|---|---|---|---|
| upstream | EOG, OXY, DVN, FANG, COP | the crude view at full volume | crude β 0.9–1.3 |
| integrated | XOM, CVX, SHEL | the view at half volume, refining buffer | crude β 0.4–0.5 |
| midstream | EPD, PAA, ET | paid per barrel **moved**, not per dollar of price — the hiding spot | crude β 0.15–0.25, defensive |
| refiner | MPC, VLO, PSX | **long the crack, mildly short crude** (crude is the input cost) | crack β 0.7–1.1, crude β ≤ 0 |
| services | SLB, HAL | the capex cycle — lagged, torquey | crude β 0.7–0.8 |
| ETF | XOP, USO | the basket / the futures roll (USO: never a hold) | — |

Each name carries one-line hand-written strengths and weaknesses, printed with every
pick. The betas are **stated priors, not fitted coefficients** — "how much should this
name move per unit of view" — because fitting them to our daily panel would be a fresh
overfitting surface with ~no independent regimes to fit on.

The classic mistake is encoded as a test: refiners must have `crude_beta <= 0`
(`test_refiners_are_not_oil_exposure`). Marathon **Petroleum** is a crack-spread trade,
not "oil exposure"; Marathon **Oil** no longer exists (absorbed by COP, 2024), and a test
asserts MRO is not in the universe.

## How the pick happens
The desk reads the **same state as the futures book** — combined signal score (crude
view), the crack signal, realized vol, the kill switch — plus the news tilt:

    score = crude_view·crude_β + crack_view·crack_β + tilt·0.5·crude_β + high_vol·0.25·defensive

- Bullish crude → high-beta upstream (OXY tops).
- Wide cracks + soft crude → refiners (VLO/MPC) while high-crude-beta names sink.
- No view (|score| < 0.10) → **no trade**: "a weak view expressed through equities is
  just fees; stay in cash or fee-based midstream."
- Kill switch on → the equity desk goes quiet too. One risk layer, every instrument.
- The bottom-ranked name is reported as the **weakest expression** of the view — not a
  short call.

Every run logs one paper pick with entry quotes; `oilx equity-score` grades picks ≥5 days
old **against XLE, not against zero** — "energy went up" is not stock-picking skill.

## The news tilt (and why it's caged)
Headlines from Google News RSS (free, keyless), scored by a transparent keyword lexicon —
supply cuts / attacks / Hormuz / draws are bullish; output hikes / ceasefire / builds /
demand fear are bearish. Every matched headline is logged with the pattern that matched
it, so the tilt is auditable line by line. Dilution is deliberate: one scary headline
among forty quiet ones is a whisper, not a regime (tilt ≈ matched sum / max(N, 10),
clipped to ±1).

**The cage:** there is no free historical headline archive, so this signal cannot be
backtested honestly. Therefore it is live-only, logged from day one, capped at half the
weight of the crude view, and allowed to influence the **equity ranking only** — it does
not touch the futures book or any Kalshi threshold until its own log earns it a
promotion. The alternative — wiring an untested signal into position sizing because it
feels current — is how fitted stories replace evidence.

Run: `python -m oilx equity-pick` (also part of every hourly cycle; the dashboard's
Equity Desk card shows the pick, the ranked table, and the matched headlines), and
`python -m oilx equity-score` to grade the history.

Related: [[Instrument Menu and Exposure Map]], [[Signals]], [[Oilx Build Log]]
