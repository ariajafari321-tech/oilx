"""Data layer: load the cached CSVs, and refresh them from the free sources.

Sources (all public, no API keys):
- EIA weekly petroleum data: the dnav "LeafHandler" history pages (full weekly history).
- CFTC Commitments of Traders: the public Socrata API at publicreporting.cftc.gov.
- Prices: Yahoo's chart API (CL/RB/HO front-month continuations, USO, XOP, ^OVX, ^IRX).
- WTI / Brent spot: Alpha Vantage csv (already seeded; refresh needs a free AV key, or
  keep using the seeded file - spot is only used for cross-checks and pre-2005 history).

Design rule carried over from pmx: fetchers never silently change the cache. `oilx fetch`
writes fresh files next to the old ones only after basic sanity checks pass.
"""
from __future__ import annotations

import io
import json
import logging
import re
import time as _time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

log = logging.getLogger("oilx.data")

UA = {"User-Agent": "oilx/0.1 (student research; read-only)"}

EIA_SERIES = {
    "eia_crude_stocks_weekly.csv": ("WCESTUS1", "crude_stocks_kbbl"),
    "eia_cushing_stocks_weekly.csv": ("W_EPC0_SAX_YCUOK_MBBL", "cushing_stocks_kbbl"),
    "eia_gasoline_stocks_weekly.csv": ("WGTSTUS1", "gasoline_stocks_kbbl"),
    "eia_product_supplied_weekly.csv": ("WRPUPUS2", "product_supplied_kbd"),
    "eia_refinery_util_weekly.csv": ("WPULEUS3", "refinery_util_pct"),
    "eia_spr_stocks_weekly.csv": ("WCSSTUS1", "spr_stocks_kbbl"),
}
YAHOO_SERIES = {
    "cl_front_daily.csv": ("CL=F", "cl_close", False),
    "rbob_front_daily.csv": ("RB=F", "rbob_close_usd_gal", False),
    "heatoil_front_daily.csv": ("HO=F", "ho_close_usd_gal", False),
    "uso_adj_daily.csv": ("USO", "uso_adjclose", True),
    "xop_adj_daily.csv": ("XOP", "xop_adjclose", True),
    "ovx_daily.csv": ("^OVX", "ovx", False),
    "irx_daily.csv": ("^IRX", "tbill13w_yield_pct", False),
}
COT_FILE = "cftc_cot_wti_weekly.csv"
COT_CODES = ("067651", "067411")  # NYMEX WTI: legacy "light sweet" + the newer listing


# ---------------------------------------------------------------- loading

def load_csv(raw_dir: Path, name: str) -> pd.DataFrame:
    df = pd.read_csv(raw_dir / name)
    if "timestamp" in df.columns:  # Alpha Vantage csv header
        df = df.rename(columns={"timestamp": "date"})
    df["date"] = pd.to_datetime(df["date"])
    for c in df.columns:
        if c not in ("date", "code"):
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)


def load_all(raw_dir: Path) -> dict[str, pd.DataFrame]:
    out = {}
    for name in list(EIA_SERIES) + list(YAHOO_SERIES) + [COT_FILE, "wti_spot_daily.csv", "brent_spot_daily.csv"]:
        p = raw_dir / name
        if p.exists():
            out[name] = load_csv(raw_dir, name)
        else:
            log.warning("missing %s (run `oilx fetch`, or reseed)", name)
    # Alpha Vantage spot files use timestamp,value with '.' for missing days.
    for name, col in (("wti_spot_daily.csv", "wti_spot"), ("brent_spot_daily.csv", "brent_spot")):
        if name in out:
            df = out[name]
            df.columns = ["date", col]
            out[name] = df.dropna().reset_index(drop=True)
    return out


# ---------------------------------------------------------------- fetchers (run on a normal network)

def fetch_eia(sid: str) -> pd.DataFrame:
    """Parse the full weekly history off the EIA dnav history page for one series."""
    url = f"https://www.eia.gov/dnav/pet/hist/LeafHandler.ashx?n=PET&s={sid}&f=W"
    html = requests.get(url, headers=UA, timeout=60).text
    rows = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
        cells = [re.sub(r"<[^>]+>|&nbsp;?|,", "", c).strip()
                 for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
        if not cells:
            continue
        m = re.match(r"^(\d{4})-[A-Z][a-z]{2}$", cells[0])
        if not m:
            continue
        year = m.group(1)
        for i in range(1, len(cells) - 1, 2):
            d = re.match(r"^(\d{2})/(\d{2})$", cells[i] or "")
            v = cells[i + 1]
            if d and re.match(r"^-?\d+(\.\d+)?$", v or ""):
                rows.append((f"{year}-{d.group(1)}-{d.group(2)}", float(v)))
    df = pd.DataFrame(rows, columns=["date", "value"])
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values("date").reset_index(drop=True)


def fetch_cot() -> pd.DataFrame:
    """Weekly legacy-format COT for NYMEX WTI (both contract codes), via Socrata."""
    base = "https://publicreporting.cftc.gov/resource/6dca-aqww.json"
    frames = []
    for code in COT_CODES:
        params = {
            "$select": ("report_date_as_yyyy_mm_dd,noncomm_positions_long_all,"
                        "noncomm_positions_short_all,comm_positions_long_all,"
                        "comm_positions_short_all,open_interest_all"),
            "$where": f"cftc_contract_market_code='{code}'",
            "$order": "report_date_as_yyyy_mm_dd",
            "$limit": 5000,
        }
        rows = requests.get(base, params=params, headers=UA, timeout=60).json()
        df = pd.DataFrame(rows)
        if df.empty:
            continue
        df["code"] = code
        frames.append(df)
        _time.sleep(0.5)
    df = pd.concat(frames, ignore_index=True)
    df = df.rename(columns={
        "report_date_as_yyyy_mm_dd": "date",
        "noncomm_positions_long_all": "noncomm_long", "noncomm_positions_short_all": "noncomm_short",
        "comm_positions_long_all": "comm_long", "comm_positions_short_all": "comm_short",
        "open_interest_all": "oi"})
    df["date"] = pd.to_datetime(df["date"].str[:10])
    for c in ("noncomm_long", "noncomm_short", "comm_long", "comm_short", "oi"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df[["date", "code", "noncomm_long", "noncomm_short", "comm_long", "comm_short", "oi"]] \
        .sort_values(["date", "code"]).reset_index(drop=True)


def fetch_yahoo(symbol: str, start: str = "2005-01-01", adjusted: bool = False) -> pd.DataFrame:
    p1 = int(pd.Timestamp(start, tz="UTC").timestamp())
    p2 = int(_time.time()) + 86400
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{requests.utils.quote(symbol)}"
    j = requests.get(url, params={"period1": p1, "period2": p2, "interval": "1d"},
                     headers=UA, timeout=60).json()
    res = j["chart"]["result"][0]
    ts = res.get("timestamp", [])
    close = res["indicators"]["quote"][0]["close"]
    if adjusted and res["indicators"].get("adjclose"):
        close = res["indicators"]["adjclose"][0]["adjclose"]
    rows = [(datetime.fromtimestamp(t, tz=timezone.utc).date().isoformat(), c)
            for t, c in zip(ts, close) if c is not None]
    df = pd.DataFrame(rows, columns=["date", "value"])
    df["date"] = pd.to_datetime(df["date"])
    return df


def refresh(raw_dir: Path) -> list[str]:
    """Refresh every cache file in place. Returns the list of files written."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for name, (sid, col) in EIA_SERIES.items():
        df = fetch_eia(sid)
        if len(df) < 500:
            log.warning("EIA %s came back short (%d rows); keeping the old file", sid, len(df))
            continue
        df.columns = ["date", col]
        df.to_csv(raw_dir / name, index=False)
        written.append(name)
    cot = fetch_cot()
    if len(cot) > 500:
        cot.to_csv(raw_dir / COT_FILE, index=False)
        written.append(COT_FILE)
    for name, (sym, col, adj) in YAHOO_SERIES.items():
        try:
            df = fetch_yahoo(sym, adjusted=adj)
        except Exception as e:  # yahoo hiccups; keep the old file
            log.warning("yahoo %s failed: %s", sym, e)
            continue
        if len(df) < 500:
            log.warning("yahoo %s came back short (%d rows); keeping the old file", sym, len(df))
            continue
        df.columns = ["date", col]
        df.to_csv(raw_dir / name, index=False)
        written.append(name)
    try:
        written += fetch_gdelt(raw_dir)
    except Exception as e:  # GDELT throttles hard and unpredictably; never block the rest
        log.warning("gdelt fetch failed (%s); keeping any old files", e)
    return written


# ---------------------------------------------------------------- GDELT news archive

GDELT_DOC = "https://api.gdeltproject.org/api/v2/doc/doc"


def fetch_gdelt(raw_dir: Path, start_year: int = 2017) -> list[str]:
    """Daily average article tone + raw article volume for crude-oil news, 2017->now,
    from GDELT's DOC API - the free headline archive that lets the live news tilt be
    BACKTESTED instead of trusted. The API rate-limits aggressively and unpredictably
    (429s for whole evenings), so: gentle pacing, chunked spans, one long retry, and on
    persistent 429 we keep whatever old files exist and try again next refresh."""
    import time as _t
    frames: dict[str, list[pd.DataFrame]] = {"tone": [], "vol": []}
    this_year = datetime.now().year
    spans = [(y, min(y + 1, this_year)) for y in range(start_year, this_year + 1, 2)]
    for mode, key in (("timelinetone", "tone"), ("timelinevolraw", "vol")):
        for y0, y1 in spans:
            params = {"query": '"crude oil"', "mode": mode, "format": "csv",
                      "STARTDATETIME": f"{y0}0101000000", "ENDDATETIME": f"{y1}1231235959"}
            txt = None
            for attempt in range(2):
                r = requests.get(GDELT_DOC, params=params, timeout=40,
                                 headers={"User-Agent": "oilx/0.1 (student research)"})
                if r.status_code == 200 and len(r.text) > 100 and "," in r.text:
                    txt = r.text
                    break
                _t.sleep(75 if attempt == 0 else 0)  # one long backoff, then give up
            if txt is None:
                raise RuntimeError(f"GDELT {mode} {y0}-{y1} still rate-limited")
            df = pd.read_csv(io.StringIO(txt))
            frames[key].append(df)
            _t.sleep(8)  # stay far under their 1-per-5s line
    written = []
    for key, name, col in (("tone", "gdelt_tone_crude.csv", "tone"),
                           ("vol", "gdelt_vol_crude.csv", "volume")):
        df = pd.concat(frames[key], ignore_index=True)
        # DOC csv columns are like (Date, Series, Value); keep date + value, dedupe
        df = df.iloc[:, [0, -1]]
        df.columns = ["date", col]
        df["date"] = pd.to_datetime(df["date"]).dt.date
        df = df.drop_duplicates("date").sort_values("date")
        if len(df) < 300:
            log.warning("gdelt %s came back short (%d rows); keeping the old file", key, len(df))
            continue
        df.to_csv(raw_dir / name, index=False)
        written.append(name)
    return written


# ---------------------------------------------------------------- live extras (not backtested)

MONTH_CODES = "FGHJKMNQUVXZ"


def next_cl_contracts(now: datetime | None = None, n: int = 3) -> list[str]:
    """Yahoo tickers for the next n CL contracts, e.g. CLZ26.NYM - used by `oilx now`
    to read the real front-vs-second carry, which has no free history to backtest."""
    now = now or datetime.now(timezone.utc)
    out = []
    y, m = now.year, now.month
    for k in range(1, n + 1):
        mm = m + k
        yy = y + (mm - 1) // 12
        mm = (mm - 1) % 12 + 1
        out.append(f"CL{MONTH_CODES[mm - 1]}{yy % 100:02d}.NYM")
    return out
