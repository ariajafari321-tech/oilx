"""Load config.toml into one flat object, with defaults matching the shipped file."""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class Config:
    raw_dir: Path
    out_dir: Path
    start: str
    backtest_start: str
    seasonal_years: int
    spot_glitch_abs: float
    spot_glitch_fut: float
    eia_release_bdays: int
    cot_release_bdays: int
    active: list[str]
    z_scale: float
    cot_dead_zone: float
    inv_glut_dampen: float
    mom_inv_conditioning: bool
    vol_target: float
    vol_lookback_days: int
    max_leverage: float
    kill_drawdown: float
    kill_flat_days: int
    kill_halflife_days: int
    spread_slippage_bps: float
    holding_bps_per_day: float
    train_years: int
    refit_months: int
    min_weight: float
    block_days: int
    n_boot: int
    kalshi: dict = field(default_factory=dict)
    equities: dict = field(default_factory=dict)
    news: dict = field(default_factory=dict)
    root: Path = field(default_factory=Path)


def load(path: str | Path = "config.toml") -> Config:
    path = Path(path)
    root = path.parent.resolve()
    raw = tomllib.loads(path.read_text())
    d, p, lg, s, r, c, w, e = (raw.get(k, {}) for k in
                               ("data", "panel", "lags", "signals", "risk", "costs", "walkforward", "eval"))
    return Config(
        raw_dir=root / d.get("raw_dir", "data/raw"),
        out_dir=root / d.get("out_dir", "data/out"),
        start=p.get("start", "1990-01-01"),
        backtest_start=p.get("backtest_start", "2007-01-03"),
        seasonal_years=int(p.get("seasonal_years", 5)),
        spot_glitch_abs=float(p.get("spot_glitch_abs", 0.12)),
        spot_glitch_fut=float(p.get("spot_glitch_fut", 0.04)),
        eia_release_bdays=int(lg.get("eia_release_bdays", 4)),
        cot_release_bdays=int(lg.get("cot_release_bdays", 4)),
        active=list(s.get("active", ["mom", "crack", "inv_level", "inv_surprise", "cot"])),
        z_scale=float(s.get("z_scale", 1.5)),
        cot_dead_zone=float(s.get("cot_dead_zone", 1.0)),
        inv_glut_dampen=float(s.get("inv_glut_dampen", 0.5)),
        mom_inv_conditioning=bool(s.get("mom_inv_conditioning", True)),
        vol_target=float(r.get("vol_target", 0.10)),
        vol_lookback_days=int(r.get("vol_lookback_days", 20)),
        max_leverage=float(r.get("max_leverage", 1.5)),
        kill_drawdown=float(r.get("kill_drawdown", 0.15)),
        kill_flat_days=int(r.get("kill_flat_days", 10)),
        kill_halflife_days=int(r.get("kill_halflife_days", 10)),
        spread_slippage_bps=float(c.get("spread_slippage_bps", 2.0)),
        holding_bps_per_day=float(c.get("holding_bps_per_day", 0.5)),
        train_years=int(w.get("train_years", 5)),
        refit_months=int(w.get("refit_months", 12)),
        min_weight=float(w.get("min_weight", 0.10)),
        block_days=int(e.get("block_days", 10)),
        n_boot=int(e.get("n_boot", 500)),
        kalshi=dict(raw.get("kalshi", {})),
        equities=dict(raw.get("equities", {})),
        news=dict(raw.get("news", {})),
        root=root,
    )
