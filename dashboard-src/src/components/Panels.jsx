import React, { useState } from "react";
import { Cell } from "./Shell.jsx";
import { Spark } from "./Charts.jsx";
import { SIG_HINT, SIG_NAME, ago, cents, cents1, isoSec, market, signed } from "../lib.js";

/* ---------- a diverging bar: red left of centre, green right ---------- */
function Diverge({ v, scale = 1 }) {
  const w = Math.min(50, (Math.abs(v) / scale) * 50);
  return (
    <span className="relative block h-1.5 rounded-full bg-zinc-800/80">
      <span className="absolute left-1/2 top-[-3px] h-[calc(100%+6px)] w-px bg-zinc-600" aria-hidden="true" />
      <span className={"absolute top-0 h-full transition-[width] duration-700 ease-spring " + (v >= 0 ? "left-1/2 rounded-r-full bg-bull" : "right-1/2 rounded-l-full bg-bear")} style={{ width: w + "%" }} />
    </span>
  );
}

/* ---------- signal center ---------- */
function Gauge({ value }) {
  // semicircle from -1 (left) to +1 (right); the lit arc grows from the top centre
  const R = 84, cx = 110, cy = 100, v = Math.max(-1, Math.min(1, value || 0));
  const pt = (t) => { const a = Math.PI * (1 - (t + 1) / 2); return [cx + R * Math.cos(a), cy - R * Math.sin(a)]; };
  const arc = (a, b) => { const [x0, y0] = pt(a), [x1, y1] = pt(b); return `M${x0.toFixed(1)} ${y0.toFixed(1)}A${R} ${R} 0 0 1 ${x1.toFixed(1)} ${y1.toFixed(1)}`; };
  const [nx, ny] = pt(v), col = v >= 0 ? "#4fae87" : "#d2625a";
  const lean = Math.abs(v) < 0.1 ? "No real lean" : v > 0 ? "Leaning bullish" : "Leaning bearish";
  return (
    <div className="relative mx-auto w-[220px]" role="img" aria-label={`Combined signal ${signed(v)} on a scale from minus one to plus one: ${lean}`}>
      <svg width="220" height="118" viewBox="0 0 220 118">
        <path d={arc(-1, 1)} fill="none" stroke="#27272a" strokeWidth="10" strokeLinecap="round" />
        {Math.abs(v) > 0.005 && <path d={v >= 0 ? arc(0, v) : arc(v, 0)} fill="none" stroke={col} strokeWidth="10" strokeLinecap="round" />}
        <line x1={cx} y1={cy - R - 9} x2={cx} y2={cy - R + 9} stroke="#52525b" strokeWidth="1.5" />
        <circle cx={nx} cy={ny} r="7" fill="#09090b" stroke={col} strokeWidth="3" style={{ filter: `drop-shadow(0 0 6px ${col})` }} />
      </svg>
      <div className="absolute inset-x-0 top-[60px] text-center">
        <div className="num text-[30px] font-medium leading-none" style={{ color: col }}>{signed(v)}</div>
      </div>
      <div className="num -mt-1 flex justify-between text-[11px] text-zinc-500"><span>−1 bearish</span><span>bullish +1</span></div>
    </div>
  );
}

export function SignalCenter({ S, className, delay }) {
  const s = S.signals;
  if (!s) return <Cell className={className} delay={delay} title="What the signals say about crude">
    <p className="text-[13px] text-zinc-500">{S.signal_error ? "The signals couldn't be computed: " + S.signal_error : "Signals appear after the first data refresh."}</p></Cell>;
  const sc = S.score ?? 0, tp = S.target_pos ?? 0;
  const lean = Math.abs(sc) < 0.1 ? "No real lean" : sc > 0 ? "Leaning bullish" : "Leaning bearish";
  return (
    <Cell className={className} delay={delay} title="What the signals say about crude"
      aside={S.signal_asof && <span className="num text-[11.5px] text-zinc-500">inputs to {S.signal_asof}</span>}>
      <Gauge value={sc} />
      <p className="mt-3 text-center text-[13.5px] text-zinc-300">
        <span className="font-medium text-zinc-50">{lean}.</span>{" "}
        {Math.abs(tp) < 0.005 ? "Too weak to size a position." : <>Sized as <span className="num text-zinc-100">{tp > 0 ? "long" : "short"} {Math.abs(tp).toFixed(2)}×</span> the account at {Math.round((S.inst_vol || 0) * 100)}% volatility.</>}
      </p>
      <ul className="mt-5 space-y-3 border-t border-line-soft pt-4">
        {Object.entries(s).map(([k, v]) => (
          <li key={k} className="grid grid-cols-[minmax(0,1fr)_84px_44px] items-center gap-3 sm:grid-cols-[minmax(0,1fr)_120px_44px]" title={SIG_HINT[k]}>
            <div className="min-w-0">
              <div className="truncate text-[13px] text-zinc-200">{SIG_NAME[k] || k}</div>
              <div className="truncate text-[11.5px] text-zinc-500">{SIG_HINT[k]}</div>
            </div>
            <Diverge v={v} />
            <span className={"num text-right text-[13px] " + (v > 0.02 ? "text-bull" : v < -0.02 ? "text-bear" : "text-zinc-400")}>{signed(v)}</span>
          </li>
        ))}
      </ul>
    </Cell>
  );
}

/* ---------- order book + executions ---------- */
const TAG = {
  Resting: "border-crude-dim bg-crude-wash text-crude-bright", Wanted: "border-line text-zinc-400",
  "Paper fill": "border-transparent bg-bull-wash text-bull", "Quote sent": "border-crude-dim bg-crude-wash text-crude-bright",
  "Order sent": "border-crude-dim bg-crude-wash text-crude-bright",
};
function Tag({ children }) {
  return <span className={"inline-block whitespace-nowrap rounded-full border px-2 py-px text-[11px] font-medium " + (TAG[children] || "border-line text-zinc-400")}>{children}</span>;
}
const TH = ({ children, right, wide }) => <th scope="col" className={"border-b border-line pb-2 text-[11px] font-medium text-zinc-500 " + (right ? "pl-3 text-right" : "pr-3 text-left") + (wide ? " hidden sm:table-cell" : "")}>{children}</th>;

function Book({ S }) {
  const sv = S.strip;
  if (!sv?.rows?.length) return <p className="text-[13px] text-zinc-500">The book appears after the next cycle reads a full strip of WTI markets.</p>;
  const mine = {};
  for (const q of [...(S.maker_quotes || []), ...(S.resting || [])]) { const m = /-T([\d.]+)$/.exec(q.ticker || ""); if (m && /^KXWTI-/.test(q.ticker)) mine[Number(m[1]).toFixed(2)] = q; }
  const rows = sv.rows.filter((r) => Math.abs(r.z) <= 1.6 && (r.bid > 0 || r.ask < 1)).slice().reverse();
  const maxOi = Math.max(1, ...rows.map((r) => r.oi));
  return (
    <div className="max-h-[540px] overflow-auto">
      <table className="w-full border-collapse text-[12.5px]">
        <caption className="sr-only">Kalshi WTI order book near the money, with the model's value for each strike</caption>
        <thead className="sticky top-0 bg-ink-900"><tr><TH>WTI above</TH><TH right>Bid</TH><TH right>Ask</TH><TH right wide>Spread</TH><TH right>Model</TH><TH right>Gap</TH><TH right wide>Open interest</TH><TH right>Our quote</TH></tr></thead>
        <tbody className="num">
          {rows.map((r) => {
            const mid = (r.bid + r.ask) / 2, gap = r.fair - mid, q = mine[r.k.toFixed(2)], inside = Math.abs(r.z) <= sv.wing_z;
            return (
              <tr key={r.k} className={"border-b border-line-soft transition-colors hover:bg-ink-800 " + (inside ? "" : "text-zinc-500")}>
                <td className="py-1.5 pr-3 text-zinc-200">${r.k.toFixed(2)}{inside && <span className="ml-2 inline-block h-1 w-1 rounded-full bg-crude align-middle" title="Inside the zone where the model is trusted" />}</td>
                <td className="py-1.5 pl-3 text-right text-bull">{cents(r.bid)}</td>
                <td className="py-1.5 pl-3 text-right text-bear">{cents(r.ask)}</td>
                <td className="hidden py-1.5 pl-3 text-right text-zinc-400 sm:table-cell">{Math.round((r.ask - r.bid) * 100)}¢</td>
                <td className="py-1.5 pl-3 text-right text-crude">{cents1(r.fair)}</td>
                <td className={"py-1.5 pl-3 text-right " + (Math.abs(gap) < 0.015 ? "text-zinc-500" : "text-zinc-200")}>{signed(gap * 100, 1)}</td>
                <td className="relative hidden py-1.5 pl-3 text-right text-zinc-400 sm:table-cell">
                  <span className="absolute inset-y-1 right-0 rounded-sm bg-zinc-700/35" style={{ width: (r.oi / maxOi) * 72 + "%" }} aria-hidden="true" />
                  <span className="relative">{Math.round(r.oi).toLocaleString()}</span>
                </td>
                <td className="py-1.5 pl-3 text-right">{q ? <span className="text-crude-bright">{q.side} {cents(q.price)}</span> : <span className="text-zinc-700">–</span>}</td>
              </tr>);
          })}
        </tbody>
      </table>
    </div>
  );
}

function Executions({ S }) {
  const rows = [];
  for (const q of S.resting || []) rows.push({ k: "Resting", t: 9e12, tk: q.ticker, side: q.side, px: q.price, fair: q.fair, n: q.count });
  if (!(S.resting || []).length) for (const q of S.maker_quotes || []) rows.push({ k: "Wanted", t: 8e12, tk: q.ticker, side: q.side, px: q.price, fair: q.fair, bid: q.book_bid, ask: q.book_ask });
  for (const f of S.shadow_fills || []) rows.push({ k: "Paper fill", t: isoSec(f.ts), tk: f.ticker, side: f.side, px: f.price, fair: f.model_p, when: f.ts });
  for (const o of S.orders || []) rows.push({ k: o.tier === "maker" ? "Quote sent" : "Order sent", t: isoSec(o.ts), tk: o.ticker, side: o.side, px: o.price, fair: o.price + (o.edge || 0), n: o.count, when: o.ts, ms: o.ms });
  rows.sort((a, b) => b.t - a.t);
  if (!rows.length) return <p className="max-w-[56ch] text-[13px] leading-relaxed text-zinc-500">Nothing yet. Quotes appear when the model finds a price it would be happy to be filled at, and fills appear when the market trades down to one.</p>;
  return (
    <div className="max-h-[540px] overflow-auto">
      <table className="w-full border-collapse text-[12.5px]">
        <caption className="sr-only">Quotes, orders and fills, newest first</caption>
        <thead className="sticky top-0 bg-ink-900"><tr><TH>Status</TH><TH>Market</TH><TH>Side</TH><TH right>Price</TH><TH right>Model</TH><TH right wide>Edge</TH><TH right wide>Book</TH><TH right wide>Speed</TH><TH right>When</TH></tr></thead>
        <tbody>
          {rows.slice(0, 40).map((r, i) => {
            const mk = market(r.tk), edge = r.fair != null ? r.fair - r.px : null;
            return (
              <tr key={i} className="border-b border-line-soft transition-colors hover:bg-ink-800">
                <td className="py-2 pr-3"><Tag>{r.k}</Tag></td>
                <td className="py-2 pr-3 text-zinc-200"><span className="text-zinc-500">{mk.u}</span> {mk.text}<span className="num ml-2 text-[11px] text-zinc-600">{mk.date}</span></td>
                <td className="num py-2 pr-3 text-zinc-300">{r.n ? r.n + " " : ""}{r.side}</td>
                <td className="num py-2 pl-3 text-right text-zinc-100">{cents(r.px)}</td>
                <td className="num py-2 pl-3 text-right text-crude">{r.fair ? cents1(r.fair) : "–"}</td>
                <td className={"num hidden py-2 pl-3 text-right sm:table-cell " + (edge > 0 ? "text-bull" : "text-zinc-500")}>{edge != null ? signed(edge * 100, 1) : "–"}</td>
                <td className="num hidden py-2 pl-3 text-right text-zinc-500 sm:table-cell">{r.bid != null ? cents(r.bid) + "/" + cents(r.ask) : "–"}</td>
                <td className="num hidden py-2 pl-3 text-right text-zinc-500 sm:table-cell">{r.ms != null ? r.ms + " ms" : "–"}</td>
                <td className="num py-2 pl-3 text-right text-zinc-500">{r.when ? ago(isoSec(r.when)) : "now"}</td>
              </tr>);
          })}
        </tbody>
      </table>
    </div>
  );
}

export function OrderPanel({ S, className, delay }) {
  const [tab, setTab] = useState("exec");
  return (
    <Cell className={className} delay={delay} title="Quotes, fills and the order book"
      aside={<div className="seg" role="tablist" aria-label="Order view">
        <button type="button" role="tab" aria-selected={tab === "exec"} onClick={() => setTab("exec")}>Quotes and fills</button>
        <button type="button" role="tab" aria-selected={tab === "book"} onClick={() => setTab("book")}>Order book</button></div>}>
      {tab === "exec" ? <Executions S={S} /> : <Book S={S} />}
    </Cell>
  );
}

/* ---------- equity desk ---------- */
export function EquityDesk({ S, className, delay }) {
  const e = S.equity;
  if (!e) return <Cell className={className} delay={delay} title="Which oil stock carries this view best"><p className="text-[13px] text-zinc-500">The ranking appears after the first cycle that runs the equity desk.</p></Cell>;
  const p = e.pick || {}, top = (e.ranked || []).slice(0, 7), mx = Math.max(0.01, ...top.map((r) => Math.abs(r.score)));
  const hist = S.equity_scores || {}, n = e.news || {}, ms = (n.matches || []).slice(0, 4);
  const anyHist = top.some((r) => (hist[r.ticker] || []).length > 1);
  return (
    <Cell className={className} delay={delay} title="Which oil stock carries this view best" aside={<span className="text-[11.5px] text-zinc-500">paper picks, no orders</span>}>
      {p.action === "long" ? (
        <div className="rounded-lg border border-line bg-ink-950/60 p-4">
          <div className="flex flex-wrap items-baseline gap-x-3">
            <span className="num text-[26px] font-medium leading-none text-zinc-50">{p.ticker}</span>
            <span className="text-[13px] text-zinc-400">{p.name}</span>
            <span className="rounded-full border border-crude-dim bg-crude-wash px-2 py-px text-[11px] font-medium text-crude-bright">{p.bucket}</span>
          </div>
          <dl className="mt-3 grid gap-1.5 text-[12.5px] leading-relaxed">
            <div className="grid grid-cols-[62px_1fr] gap-2"><dt className="text-bull">Strength</dt><dd className="text-zinc-300">{p.strengths}</dd></div>
            <div className="grid grid-cols-[62px_1fr] gap-2"><dt className="text-bear">Weakness</dt><dd className="text-zinc-300">{p.weaknesses}</dd></div>
          </dl>
        </div>
      ) : <p className="text-[13px] leading-relaxed text-zinc-400"><span className="font-medium text-zinc-100">No pick.</span> {p.reason}</p>}

      <table className="mt-4 w-full border-collapse text-[12.5px]">
        <caption className="sr-only">How the top names score for the current view</caption>
        <thead><tr><TH>Ticker</TH><TH wide>Type</TH><TH>Score trend</TH><TH>Fit</TH><TH right>Score</TH></tr></thead>
        <tbody>
          {top.map((r) => (
            <tr key={r.ticker} className="border-b border-line-soft transition-colors hover:bg-ink-800" title={r.why}>
              <td className="num py-1.5 pr-3 font-medium text-zinc-100">{r.ticker}</td>
              <td className="hidden py-1.5 pr-3 text-zinc-500 sm:table-cell">{r.bucket}</td>
              <td className="py-1.5 pr-3"><Spark values={hist[r.ticker]} /></td>
              <td className="w-[28%] py-1.5 pr-3"><Diverge v={r.score} scale={mx} /></td>
              <td className={"num py-1.5 pl-3 text-right " + (r.score > 0 ? "text-bull" : r.score < 0 ? "text-bear" : "text-zinc-400")}>{signed(r.score)}</td>
            </tr>))}
        </tbody>
      </table>
      <p className="mt-2 text-[11.5px] text-zinc-600">{anyHist ? "Trend lines show each name's score over recent cycles." : "Trend lines fill in as the bot logs each name's score every cycle."}</p>

      <h3 className="mt-4 text-[12px] font-medium text-zinc-400">Headlines moving the news tilt <span className={"num " + ((n.tilt || 0) >= 0 ? "text-bull" : "text-bear")}>{signed(n.tilt || 0)}</span></h3>
      {ms.length ? (
        <ul className="mt-2 space-y-1.5 text-[12.5px] leading-snug text-zinc-400">
          {ms.map((m, i) => (
            <li key={i} className="grid grid-cols-[14px_1fr] gap-1.5">
              <span className={m.weight > 0 ? "text-bull" : "text-bear"} aria-hidden="true">{m.weight > 0 ? "▲" : "▼"}</span>
              <span><span className="sr-only">{m.weight > 0 ? "Bullish: " : "Bearish: "}</span>{m.headline}</span>
            </li>))}
        </ul>
      ) : <p className="mt-2 text-[12.5px] text-zinc-500">No headline matched in the last scan ({n.n_headlines || 0} read).</p>}
    </Cell>
  );
}
