"""Build one aligned daily panel from the raw files.

Every input gets an **availability date** - the first day the strategy is allowed to see
it - and joins the daily index with `merge_asof` on that date. Weekly EIA data for the
week ending Friday is released the following Wednesday; COT data as of Tuesday is
released Friday. Both lags are set in config and deliberately padded by one business day.
Look-ahead through release lags is the classic way oil backtests fool their authors.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from .config import Config
from . import data as dlib

log = logging.getLogger("oilx.panel")

BBL_PER_GAL = 42.0


def _bday_shift(dates: pd.Series, n: int) -> pd.Series:
    return dates + pd.offsets.BusinessDay(n)


def build(cfg: Config) -> pd.DataFrame:
    raw = dlib.load_all(cfg.raw_dir)

    spot = raw["wti_spot_daily.csv"].rename(columns={"wti_spot": "spot"})
    brent = raw["brent_spot_daily.csv"].rename(columns={"brent_spot": "brent"})
    cl = raw["cl_front_daily.csv"].rename(columns={"cl_close": "cl"})
    rb = raw["rbob_front_daily.csv"].rename(columns={"rbob_close_usd_gal": "rb"})
    ho = raw["heatoil_front_daily.csv"].rename(columns={"ho_close_usd_gal": "ho"})
    ovx = raw.get("ovx_daily.csv", pd.DataFrame(columns=["date", "ovx"]))
    irx = raw.get("irx_daily.csv", pd.DataFrame(columns=["date", "tbill13w_yield_pct"]))

    # ---- daily index: CL trading days, extended back with spot days pre-CL
    start = pd.Timestamp(cfg.start)
    days = pd.Index(sorted(set(cl["date"]) | set(spot.loc[spot["date"] < cl["date"].min(), "date"])))
    days = days[days >= start]
    px = pd.DataFrame(index=days)
    for df, col in ((spot, "spot"), (brent, "brent"), (cl, "cl"), (rb, "rb"), (ho, "ho"),
                    (ovx, "ovx"), (irx, "tbill13w_yield_pct")):
        if not df.empty:
            px[col] = df.set_index("date")[col].reindex(days)

    # ---- clean obvious bad prints in the EIA spot series (cross-checked against CL)
    ret_spot = px["spot"].pct_change()
    ret_cl = px["cl"].pct_change()
    bad = (ret_spot.abs() > cfg.spot_glitch_abs) & (ret_cl.abs() < cfg.spot_glitch_fut) & px["cl"].notna()
    n_bad = int(bad.sum())
    if n_bad:
        log.info("flagged %d suspect spot prints (|spot move|>%.0f%% while CL moved <%.0f%%)",
                 n_bad, cfg.spot_glitch_abs * 100, cfg.spot_glitch_fut * 100)
        px.loc[bad, "spot"] = np.nan
    px["spot"] = px["spot"].ffill(limit=5)

    # ---- the tradable instrument: CL front; spot extends history before CL exists
    px["instr"] = px["cl"].where(px["cl"].notna(), px["spot"])
    px["ret"] = px["instr"].pct_change()
    # daily cash return from the 13-week bill (ACT/252, decimal)
    px["cash_ret"] = (px["tbill13w_yield_pct"].ffill() / 100.0) / 252.0

    # ---- 3-2-1 crack spread, $ per bbl of crude: (2 gasoline + 1 distillate - 3 crude)/3
    px["crack"] = (2 * px["rb"] * BBL_PER_GAL + px["ho"] * BBL_PER_GAL - 3 * px["cl"]) / 3.0
    px["brent_wti"] = px["brent"] - px["spot"]

    # ---- weekly EIA inventories -> surprise + level vs seasonal, lagged to release
    inv = _inventory_features(raw["eia_crude_stocks_weekly.csv"], cfg)
    px = pd.merge_asof(px.reset_index(names="date"), inv, on="date", direction="backward")

    # ---- weekly COT -> speculator crowding z, lagged to release
    cot = _cot_features(raw[dlib.COT_FILE], cfg)
    px = pd.merge_asof(px, cot, on="date", direction="backward")

    return px.set_index("date")


def _inventory_features(stocks: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """Weekly crude stocks -> (surprise z, level z) with release-lagged availability.

    The 'expected' weekly change is the average change in the same week of year over the
    trailing `seasonal_years`, excluding the current year. The surprise is this week's
    change minus that expectation, scaled by the trailing spread of surprises. The level
    feature compares today's level with the seasonal mean level, scaled the same way.
    """
    df = stocks.rename(columns={stocks.columns[1]: "stk"}).copy()
    df["chg"] = df["stk"].diff()
    df["woy"] = df["date"].dt.isocalendar().week.astype(int).clip(upper=52)
    df["year"] = df["date"].dt.year

    exp_chg, exp_lvl, sd_lvl = [], [], []
    by_woy_chg: dict[int, list[tuple[int, float]]] = {}
    by_woy_lvl: dict[int, list[tuple[int, float]]] = {}
    for _, r in df.iterrows():
        w, y = int(r["woy"]), int(r["year"])
        hist_c = [v for (yy, v) in by_woy_chg.get(w, []) if y - cfg.seasonal_years <= yy < y]
        hist_l = [v for (yy, v) in by_woy_lvl.get(w, []) if y - cfg.seasonal_years <= yy < y]
        exp_chg.append(np.mean(hist_c) if len(hist_c) >= 3 else np.nan)
        exp_lvl.append(np.mean(hist_l) if len(hist_l) >= 3 else np.nan)
        sd_lvl.append(np.std(hist_l, ddof=1) if len(hist_l) >= 3 else np.nan)
        if np.isfinite(r["chg"]):
            by_woy_chg.setdefault(w, []).append((y, float(r["chg"])))
        if np.isfinite(r["stk"]):
            by_woy_lvl.setdefault(w, []).append((y, float(r["stk"])))

    df["exp_chg"] = exp_chg
    df["surprise"] = df["chg"] - df["exp_chg"]
    sd_sur = df["surprise"].rolling(104, min_periods=26).std()
    df["inv_surprise_z"] = df["surprise"] / sd_sur
    df["inv_level_z"] = (df["stk"] - pd.Series(exp_lvl)) / pd.Series(sd_lvl)

    out = df[["date", "stk", "chg", "exp_chg", "inv_surprise_z", "inv_level_z"]].copy()
    out["date"] = _bday_shift(out["date"], cfg.eia_release_bdays)  # availability date
    return out.rename(columns={"stk": "inv_stocks", "chg": "inv_chg", "exp_chg": "inv_exp_chg"}) \
        .sort_values("date").reset_index(drop=True)


def _cot_features(cot: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """Managed/speculative crowding: net noncommercial position as a share of open
    interest, z-scored against the trailing three years, lagged to its release date."""
    df = cot.copy()
    # one row per report date: keep the contract with the larger open interest
    df = df.sort_values(["date", "oi"]).groupby("date", as_index=False).last()
    df["net_share"] = (df["noncomm_long"] - df["noncomm_short"]) / df["oi"]
    mean = df["net_share"].rolling(156, min_periods=52).mean()
    sd = df["net_share"].rolling(156, min_periods=52).std()
    df["cot_z"] = (df["net_share"] - mean) / sd
    out = df[["date", "net_share", "cot_z"]].copy()
    out["date"] = _bday_shift(out["date"], cfg.cot_release_bdays)
    return out.sort_values("date").reset_index(drop=True)
