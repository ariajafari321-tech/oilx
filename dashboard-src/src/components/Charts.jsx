import React, { useEffect, useMemo, useRef, useState } from "react";
import { Area, AreaChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Cell } from "./Shell.jsx";
import { cents, signed } from "../lib.js";

const AXIS = { fill: "#71717a", fontSize: 11, fontFamily: '"Geist Mono Variable", ui-monospace, monospace' };
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const day = (iso) => { const [y, m, d] = String(iso).split("-"); return MONTHS[+m - 1] + " " + +d; };

function Tip({ active, payload, fmt, title }) {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload;
  return (
    <div className="rounded-md border border-line bg-ink-800/95 px-2.5 py-1.5 shadow-xl backdrop-blur">
      <div className="text-[11px] text-zinc-500">{title(p)}</div>
      <div className="num text-[13px] text-zinc-100">{fmt(p.value)}</div>
    </div>
  );
}

function Series({ data, color, id, fmt, title, height = 240, yWidth = 52, refY, refLabel, xFmt }) {
  return (
    <div style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 8, right: 0, bottom: 0, left: 0 }}>
          <defs>
            <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity={0.22} />
              <stop offset="100%" stopColor={color} stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="#1c1c20" vertical={false} />
          <XAxis dataKey="t" tick={AXIS} tickLine={false} axisLine={false} minTickGap={48} tickFormatter={xFmt} />
          <YAxis orientation="right" width={yWidth} tick={AXIS} tickLine={false} axisLine={false} domain={["auto", "auto"]} tickFormatter={fmt} />
          <Tooltip content={<Tip fmt={fmt} title={title} />} cursor={{ stroke: "#3f3f46", strokeDasharray: "3 4" }} />
          {refY != null && <ReferenceLine y={refY} stroke={color} strokeDasharray="2 5" strokeOpacity={0.7}
            label={{ value: refLabel, position: "insideTopLeft", fill: "#a1a1aa", fontSize: 11 }} ifOverflow="extendDomain" />}
          <Area type="monotone" dataKey="value" stroke={color} strokeWidth={1.75} fill={`url(#${id})`} dot={false}
            activeDot={{ r: 3.5, fill: color, stroke: "#09090b", strokeWidth: 2 }} animationDuration={700} animationEasing="ease-out" />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

const Empty = ({ children, h = 240 }) => (
  <div className="grid place-items-center rounded-lg border border-dashed border-line text-center text-[13px] text-zinc-500" style={{ height: h }}>
    <p className="max-w-[34ch] px-4">{children}</p>
  </div>
);

/* ---------- WTI front-month ---------- */
const RANGES = [["3M", 63], ["6M", 126], ["1Y", 9999]];
export function PriceChart({ S, className, delay }) {
  const [range, setRange] = useState("6M");
  const all = S.price_series || [];
  const n = RANGES.find((r) => r[0] === range)[1];
  const data = useMemo(() => all.slice(-n).map((p) => ({ t: p.time, value: p.value })), [all, n]);
  const close = all.length ? all[all.length - 1].value : null, first = data.length ? data[0].value : null;
  const stale = S.raw_asof && (Date.now() - Date.parse(S.raw_asof)) / 864e5 > 5;
  const last = S.cl_live ?? close;   // the freshest price the bot has seen
  const chg = last != null && first ? (last / first - 1) * 100 : null;
  return (
    <Cell className={className} delay={delay} title="WTI front-month futures"
      aside={<div className="seg" role="tablist" aria-label="Chart range">{RANGES.map(([r]) => (
        <button key={r} type="button" role="tab" aria-selected={range === r} onClick={() => setRange(r)}>{r}</button>))}</div>}>
      <div className="mb-3 flex flex-wrap items-baseline gap-x-4 gap-y-1">
        <span className="num text-[28px] font-medium leading-none text-zinc-50">{last == null ? "–" : "$" + last.toFixed(2)}</span>
        {chg != null && <span className={"num text-[13px] " + (chg >= 0 ? "text-bull" : "text-bear")}>{signed(chg, 1)}% over {range}</span>}
        <span className="text-[12px] text-zinc-500">{S.cl_live ? "price at the latest cycle" : "last daily close"}</span>
      </div>
      {data.length > 1
        ? <Series data={data} color="#c9a25e" id="g-wti" height={330} fmt={(v) => "$" + Number(v).toFixed(0)} title={(p) => day(p.t)} xFmt={day}
            refY={stale && S.cl_live ? S.cl_live : null} refLabel={S.cl_live ? "latest cycle $" + S.cl_live.toFixed(2) : ""} />
        : <Empty h={330}>The price history appears after the first data refresh.</Empty>}
      {stale && <p className="mt-2 text-[12px] text-warn">The daily history stops at {day(S.raw_asof)} (close ${close.toFixed(2)}). The dashed line is the price the latest cycle saw.</p>}
    </Cell>
  );
}

/* ---------- 3-2-1 crack spread ---------- */
export function CrackPanel({ S, className, delay }) {
  const all = S.crack_series || [];
  const data = useMemo(() => all.map((p) => ({ t: p.time, value: p.value })), [all]);
  if (data.length < 2) return <Cell className={className} delay={delay} title="Refining margin"><Empty h={200}>Appears after the first data refresh.</Empty></Cell>;
  const vals = data.map((d) => d.value), last = vals[vals.length - 1], lo = Math.min(...vals), hi = Math.max(...vals);
  const pct = hi > lo ? (last - lo) / (hi - lo) : 0.5;
  const rank = Math.round((vals.filter((v) => v <= last).length / vals.length) * 100);
  return (
    <Cell className={className} delay={delay} title="Refining margin" aside={<span className="text-[11.5px] text-zinc-500">3-2-1 crack spread</span>}>
      <div className="flex items-baseline gap-2">
        <span className="num text-[28px] font-medium leading-none text-zinc-50">${last.toFixed(2)}</span>
        <span className="text-[12px] text-zinc-500">per barrel</span>
      </div>
      <div className="mt-4" role="img" aria-label={`Current margin sits at the ${rank}th percentile of the past year, between $${lo.toFixed(0)} and $${hi.toFixed(0)}`}>
        <div className="relative h-1.5 rounded-full bg-gradient-to-r from-zinc-800 via-crude-dim to-crude">
          <span className="absolute top-1/2 h-3.5 w-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-ink-900 bg-zinc-50 transition-[left] duration-700 ease-spring" style={{ left: pct * 100 + "%" }} />
        </div>
        <div className="num mt-1.5 flex justify-between text-[11px] text-zinc-500">
          <span>${lo.toFixed(0)} low</span><span className="text-zinc-300">{rank}th percentile of the year</span><span>${hi.toFixed(0)} high</span>
        </div>
      </div>
      <div className="mt-3"><Series data={data} color="#c9a25e" id="g-crack" height={128} yWidth={40} fmt={(v) => "$" + Number(v).toFixed(0)} title={(p) => day(p.t)} xFmt={day} /></div>
      <p className="mt-2 text-[12px] leading-relaxed text-zinc-500">What a refinery earns turning three barrels of crude into two of gasoline and one of diesel. Fat margins pull more crude through the system.</p>
    </Cell>
  );
}

/* ---------- account equity curve ---------- */
export function EquityCurve({ S, className, delay }) {
  const data = useMemo(() => {
    const seen = new Set(), out = [];
    for (const r of S.balance_history || []) {
      const t = Date.parse(r.ts);
      if (!t || seen.has(t) || r.balance == null) continue;
      seen.add(t); out.push({ t, value: Number(r.balance) });
    }
    return out.sort((a, b) => a.t - b.t);
  }, [S.balance_history]);
  const stamp = (t) => { const d = new Date(t); return MONTHS[d.getMonth()] + " " + d.getDate(); };
  if (data.length < 2) return <Cell className={className} delay={delay} title="Account equity"><Empty h={200}>The equity curve builds as the bot records its balance each cycle.</Empty></Cell>;
  const last = data[data.length - 1].value, first = data[0].value, d = last - first;
  return (
    <Cell className={className} delay={delay} title="Account equity" aside={<span className="text-[11.5px] text-zinc-500">Kalshi demo</span>}>
      <div className="flex flex-wrap items-baseline gap-x-3">
        <span className="num text-[28px] font-medium leading-none text-zinc-50">${last.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
        <span className={"num text-[12.5px] " + (d > 0 ? "text-bull" : d < 0 ? "text-bear" : "text-zinc-500")}>{signed(d)} since {stamp(data[0].t)}</span>
      </div>
      <div className="mt-4"><Series data={data} color="#4fae87" id="g-eq" height={176} yWidth={56} fmt={(v) => "$" + Math.round(v).toLocaleString("en-US")}
        title={(p) => new Date(p.t).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric" })} xFmt={stamp} /></div>
      <p className="mt-2 text-[12px] leading-relaxed text-zinc-500">Recorded every cycle, {data.length} readings. Steps that aren't trades are top-ups to the practice account.</p>
    </Cell>
  );
}

/* ---------- model vs market ---------- */
function useWidth() {
  const ref = useRef(null);
  const [w, setW] = useState(0);
  useEffect(() => {
    if (!ref.current) return;
    const ro = new ResizeObserver(([e]) => setW(Math.round(e.contentRect.width)));
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);
  return [ref, w];
}

export function StripChart({ S, className, delay }) {
  const sv = S.strip;
  const [ref, W] = useWidth();
  const [hover, setHover] = useState(null);
  const rows = useMemo(() => (sv?.rows || []).filter((r) => r.ask < 1 || r.bid > 0), [sv]);
  const H = 268, m = { l: 38, r: 52, t: 12, b: 26 };
  const ok = rows.length >= 3;
  const k0 = ok ? rows[0].k : 0, k1 = ok ? rows[rows.length - 1].k : 1;
  const x = (k) => m.l + ((k - k0) / (k1 - k0 || 1)) * (W - m.l - m.r), y = (p) => m.t + (1 - p) * (H - m.t - m.b);
  const inZone = ok ? rows.filter((r) => Math.abs(r.z) <= sv.wing_z) : [];
  const half = ok ? (rows[1].k - rows[0].k) / 2 : 0;
  const worst = inZone.length ? Math.max(...inZone.map((r) => Math.abs(r.fair - (r.bid + r.ask) / 2))) : null;
  const step = Math.max(1, Math.ceil(rows.length / Math.max(1, W / 68)));
  const onMove = (e) => {
    const bx = e.currentTarget.getBoundingClientRect(), px = e.clientX - bx.left;
    let best = rows[0];
    for (const r of rows) if (Math.abs(x(r.k) - px) < Math.abs(x(best.k) - px)) best = r;
    setHover({ r: best, y: e.clientY - bx.top });
  };
  const hr = hover?.r;
  return (
    <Cell className={className} delay={delay} title="Model vs market"
      aside={ok && <span className="num text-[11.5px] text-zinc-500">settles in {sv.t_hours < 48 ? Math.round(sv.t_hours) + "h" : Math.round(sv.t_hours / 24) + "d"}</span>}>
      <div className="mb-2 flex flex-wrap gap-x-4 gap-y-1 text-[12px] text-zinc-400">
        <span className="inline-flex items-center gap-1.5"><i className="h-0.5 w-3.5 rounded bg-crude" />Model fair value</span>
        <span className="inline-flex items-center gap-1.5"><i className="h-2 w-2 rounded-full bg-zinc-200" />Market, bid to ask</span>
        <span className="inline-flex items-center gap-1.5"><i className="h-2.5 w-3.5 rounded-sm bg-crude/15" />Where the model is trusted</span>
      </div>
      <div ref={ref} className="relative" style={{ height: H }}>
        {!ok ? <Empty h={H}>Fills in after the next cycle reads a full strip of WTI markets.</Empty> : W > 0 && (
          <svg width={W} height={H} role="img" aria-label="Model fair value against market prices by strike" onMouseMove={onMove} onMouseLeave={() => setHover(null)}>
            {inZone.length > 0 && <rect x={x(inZone[0].k - half)} y={m.t} width={x(inZone[inZone.length - 1].k + half) - x(inZone[0].k - half)} height={H - m.t - m.b} rx="6" fill="#c9a25e" opacity=".09" />}
            {[0, 0.25, 0.5, 0.75, 1].map((p) => (
              <g key={p}><line x1={m.l} x2={W - m.r} y1={y(p)} y2={y(p)} stroke="#1c1c20" />
                <text x={m.l - 8} y={y(p) + 4} textAnchor="end" style={AXIS}>{p * 100}%</text></g>))}
            {rows.map((r, i) => i % step === 0 && <text key={r.k} x={x(r.k)} y={H - 6} textAnchor="middle" style={AXIS}>${r.k.toFixed(r.k % 1 ? 2 : 0)}</text>)}
            {sv.fwd >= k0 && sv.fwd <= k1 && (<g>
              <line x1={x(sv.fwd)} x2={x(sv.fwd)} y1={m.t} y2={H - m.b} stroke="#52525b" strokeDasharray="3 4" />
              <text x={x(sv.fwd) + 6} y={m.t + 11} style={{ ...AXIS, fill: "#a1a1aa" }}>WTI ${sv.fwd.toFixed(2)}</text></g>)}
            {rows.map((r) => <line key={"b" + r.k} x1={x(r.k)} x2={x(r.k)} y1={y(r.bid)} y2={y(r.ask)} stroke="#a1a1aa" strokeWidth="2" opacity=".4" />)}
            <path d={rows.map((r, i) => (i ? "L" : "M") + x(r.k).toFixed(1) + " " + y(r.fair).toFixed(1)).join("")} fill="none" stroke="#c9a25e" strokeWidth="2" strokeLinejoin="round" />
            {rows.map((r) => <circle key={"c" + r.k} cx={x(r.k)} cy={y((r.bid + r.ask) / 2)} r={W < 520 ? 2.6 : 3.5} fill="#e4e4e7" stroke="#0c0c0f" strokeWidth="1.5" />)}
            {hr && <line x1={x(hr.k)} x2={x(hr.k)} y1={m.t} y2={H - m.b} stroke="#71717a" />}
          </svg>)}
        {ok && hr && (
          <div className="pointer-events-none absolute z-10 whitespace-nowrap rounded-md border border-line bg-ink-800/95 px-2.5 py-2 text-[12px] leading-relaxed shadow-xl backdrop-blur"
            style={{ left: x(hr.k) + 14 + 190 > W ? undefined : x(hr.k) + 14, right: x(hr.k) + 14 + 190 > W ? W - x(hr.k) + 14 : undefined, top: Math.max(4, Math.min(H - 110, hover.y - 30)) }}>
            <div className="font-medium text-zinc-100">WTI above ${hr.k.toFixed(2)}</div>
            <div className="num text-zinc-400">market {cents(hr.bid)} / {cents(hr.ask)}</div>
            <div className="num text-crude">model {(hr.fair * 100).toFixed(1)}¢</div>
            <div className="num text-zinc-400">gap {signed((hr.fair - (hr.bid + hr.ask) / 2) * 100, 1)}¢{Math.abs(hr.z) > sv.wing_z ? ", outside the zone" : ""}</div>
          </div>)}
      </div>
      {ok && <p className="mt-2 text-[12px] leading-relaxed text-zinc-500">
        The chance WTI settles above each price: the market's against the model's.
        {worst != null && <> Inside the shaded zone they agree within <span className="num text-zinc-300">{(worst * 100).toFixed(1)}¢</span>, and that is the only place the bot quotes.</>}
      </p>}
    </Cell>
  );
}

/* ---------- micro sparkline ---------- */
export function Spark({ values, w = 64, h = 20 }) {
  if (!values || values.length < 2) return <svg width={w} height={h} aria-hidden="true"><line x1="2" x2={w - 2} y1={h / 2} y2={h / 2} stroke="#3f3f46" strokeDasharray="2 3" /></svg>;
  const lo = Math.min(...values), hi = Math.max(...values), span = hi - lo || 1;
  const pts = values.map((v, i) => [2 + (i / (values.length - 1)) * (w - 4), 2 + (1 - (v - lo) / span) * (h - 4)]);
  const up = values[values.length - 1] >= values[0], c = up ? "#4fae87" : "#d2625a";
  return (
    <svg width={w} height={h} aria-hidden="true">
      <path d={pts.map((p, i) => (i ? "L" : "M") + p[0].toFixed(1) + " " + p[1].toFixed(1)).join("")} fill="none" stroke={c} strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={pts[pts.length - 1][0]} cy={pts[pts.length - 1][1]} r="2" fill={c} />
    </svg>
  );
}
