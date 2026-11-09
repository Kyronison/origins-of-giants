import React from "react";
import { Img, staticFile } from "remotion";
import { S, clamp, ease, easeOut, seg, lerp, rng, parseNum, fmtLike } from "./theme";

/** Сцена получает t (секунды от начала кадра), dur и data. Всё рисуется в SVG 1920×1080. */
type P = { t: number; dur: number; data: any };

const W = S.W, H = S.H;

// ---------- общий фон: небо с редкими звёздами и тонкой сеткой ----------
const STARS = (() => { const r = rng(7); return Array.from({ length: 260 }, () => ({ x: r() * W, y: r() * H, s: r() ** 3 * 1.6 + 0.3, o: 0.25 + r() * 0.6 })); })();

export const Sky: React.FC<{ grid?: boolean; dim?: number }> = ({ grid = false, dim = 1 }) => (
  <g>
    <defs>
      <radialGradient id="bgGrad" cx="50%" cy="45%" r="75%">
        <stop offset="0%" stopColor={S.bg2} /><stop offset="100%" stopColor={S.bg} />
      </radialGradient>
    </defs>
    <rect width={W} height={H} fill="url(#bgGrad)" />
    {STARS.map((s, i) => <circle key={i} cx={s.x} cy={s.y} r={s.s} fill="#fff" opacity={s.o * 0.55 * dim} />)}
    {grid && Array.from({ length: 21 }, (_, i) => <line key={"v" + i} x1={i * 96} y1={0} x2={i * 96} y2={H} stroke={S.grid} />)}
    {grid && Array.from({ length: 12 }, (_, i) => <line key={"h" + i} x1={0} y1={i * 96} x2={W} y2={i * 96} stroke={S.grid} />)}
  </g>
);

// ---------- тела: звезда с потемнением к краю, планета, чёрная дыра ----------
let gid = 0;
export const Body: React.FC<{ cx: number; cy: number; r: number; color: string; kind?: string; fuzzy?: boolean }> = ({ cx, cy, r, color, kind = "star", fuzzy }) => {
  const id = React.useMemo(() => "b" + (gid++), []);
  if (r < 0.6) return <circle cx={cx} cy={cy} r={0.9} fill={color} />;
  if (kind === "bh") {
    return (
      <g>
        <defs>
          <radialGradient id={id + "g"} cx="50%" cy="50%" r="50%">
            <stop offset="70%" stopColor="#FFB547" stopOpacity={0} />
            <stop offset="78%" stopColor="#FFB547" stopOpacity={0.55} />
            <stop offset="88%" stopColor="#FF7A2F" stopOpacity={0.18} />
            <stop offset="100%" stopColor="#FF7A2F" stopOpacity={0} />
          </radialGradient>
        </defs>
        <circle cx={cx} cy={cy} r={r * 1.45} fill={`url(#${id}g)`} />
        <circle cx={cx} cy={cy} r={r} fill="#000" stroke="rgba(255,190,110,0.55)" strokeWidth={Math.max(1, r * 0.012)} />
      </g>
    );
  }
  const planet = kind === "planet";
  return (
    <g>
      <defs>
        <radialGradient id={id + "s"} cx="50%" cy="50%" r="50%">
          <stop offset={planet ? "45%" : "55%"} stopColor="#000" stopOpacity={0} />
          <stop offset="100%" stopColor="#000" stopOpacity={planet ? 0.55 : 0.3} />
        </radialGradient>
        <radialGradient id={id} cx="40%" cy="38%" r="45%">
          <stop offset="0%" stopColor="#ffffff" stopOpacity={planet ? 0.28 : 0.55} />
          <stop offset="100%" stopColor="#ffffff" stopOpacity={0} />
        </radialGradient>
        {!planet && (
          <radialGradient id={id + "h"} cx="50%" cy="50%" r="50%">
            <stop offset={fuzzy ? "55%" : "80%"} stopColor={color} stopOpacity={0.45} />
            <stop offset="100%" stopColor={color} stopOpacity={0} />
          </radialGradient>
        )}
      </defs>
      {!planet && <circle cx={cx} cy={cy} r={r * (fuzzy ? 1.35 : 1.12)} fill={`url(#${id}h)`} />}
      <circle cx={cx} cy={cy} r={r} fill={color} />
      <circle cx={cx} cy={cy} r={r} fill={`url(#${id}s)`} />
      <circle cx={cx} cy={cy} r={r} fill={`url(#${id})`} />
    </g>
  );
};

const Label: React.FC<{ x: number; y: number; title: string; sub?: string; anchor?: string; color?: string; size?: number; o?: number }> =
  ({ x, y, title, sub, anchor = "middle", color = S.text, size = 34, o = 1 }) => (
    <g opacity={o}>
      <text x={x} y={y} textAnchor={anchor as any} fill={color} fontFamily={S.display} fontWeight={700} fontSize={size}>{title}</text>
      {sub && <text x={x} y={y + size * 1.05} textAnchor={anchor as any} fill={S.dim} fontFamily={S.body} fontWeight={500} fontSize={size * 0.68}>{sub}</text>}
    </g>
  );

/** Подпись под именем без повтора имени («The Sun / the Sun»). */
const dedupe = (name: string, sub?: string) => {
  if (!sub) return undefined;
  const n = name.toLowerCase().replace(/^the /, ""), s = sub.toLowerCase().replace(/^the /, "");
  if (s === n) return undefined;
  return s.startsWith(n) ? sub.slice(sub.toLowerCase().indexOf(n) + n.length).replace(/^[\s·:,-]+/, "") || undefined : sub;
};

// ---------- Compare: тела в ряд на общей линии, настоящий масштаб, камера отъезжает ----------
export const Compare: React.FC<P> = ({ t, dur, data }) => {
  const bodies: any[] = data.bodies;
  let x = 0; const pos: number[] = [];
  bodies.forEach((b, i) => { const gap = i ? Math.max(b.r, bodies[i - 1].r) * 0.18 : 0; x += (i ? bodies[i - 1].r : 0) + gap + b.r; pos.push(x); });
  const view = (i: number | "all") => {
    if (i === "all" || i === bodies.length) {
      const x0 = pos[0] - bodies[0].r, x1 = pos[pos.length - 1] + bodies[bodies.length - 1].r;
      const rmax = Math.max(...bodies.map((b) => b.r));
      const s = Math.min(0.86 * W / (x1 - x0), 0.62 * H / (2 * rmax));
      return { s, cx: (x0 + x1) / 2, cy: rmax };
    }
    const b = bodies[i]; return { s: 0.5 * H / (2 * b.r), cx: pos[i], cy: b.r };
  };
  const v0 = view(data.from ?? 0), v1 = view(data.to ?? "all");
  const p = ease(seg(t, dur * (data.hold0 ?? 0.12), dur * (data.hold1 ?? 0.82)));
  const s = Math.exp(lerp(Math.log(v0.s), Math.log(v1.s), p));
  const w = Math.abs(1 / v1.s - 1 / v0.s) < 1e-12 ? p : (1 / s - 1 / v0.s) / (1 / v1.s - 1 / v0.s);
  const cx = lerp(v0.cx, v1.cx, w), cy = lerp(v0.cy, v1.cy, w);
  const baseY = H * 0.6 + 0.5 * H * 0.62 - 0; // нижняя линия на экране
  const X = (wx: number) => W / 2 + (wx - cx) * s;
  const Y = (wy: number) => H * 0.52 - (wy - cy) * s;
  const ground = Y(0);
  return (
    <g>
      <line x1={0} y1={ground} x2={W} y2={ground} stroke={S.faint} strokeWidth={2} strokeDasharray="6 10" />
      {bodies.map((b, i) => {
        const r = b.r * s, X0 = X(pos[i]), Y0 = Y(b.r);
        if (X0 + r < -50 || X0 - r > W + 50) return null;
        return <Body key={i} cx={X0} cy={Y0} r={r} color={b.color} kind={b.kind} fuzzy={b.fuzzy} />;
      })}
      {bodies.map((b, i) => {
        const r = b.r * s, X0 = X(pos[i]);
        if (X0 < -200 || X0 > W + 200) return null;
        if (r > 28) {
          const o = clamp((r - 28) / 30);
          return <Label key={"l" + i} x={X0} y={Math.min(ground + 64, H - 60)} title={b.name} sub={dedupe(b.name, b.label)} o={o} size={Math.min(40, 22 + r / 12)} />;
        }
        if (!b.callout) return null;
        const o = clamp((28 - r) / 10);
        const tx = X0 - 120 - (b.callout_dx || 0), ty = ground - 170 - (b.callout_dy || 0);
        return (
          <g key={"c" + i} opacity={o}>
            <circle cx={X0} cy={ground - Math.max(r, 1)} r={14} fill="none" stroke={S.amber} strokeWidth={3} />
            <line x1={X0 - 10} y1={ground - Math.max(r, 1) - 10} x2={tx + 10} y2={ty + 12} stroke={S.amber} strokeWidth={2} />
            <Label x={tx} y={ty} title={b.name} sub={b.callout === true ? "to scale" : dedupe(b.name, b.callout) || "to scale"} anchor="end" size={30} color={S.amber} />
          </g>
        );
      })}
      {data.note && <Label x={W / 2} y={110} title={data.note} size={44} o={seg(t, 0.3, 0.9)} />}
    </g>
  );
};

// ---------- Orbits: Солнечная система сверху; звезда или чёрная дыра на месте Солнца растёт до настоящего размера ----------
export const Orbits: React.FC<P> = ({ t, dur, data }) => {
  const fit = data.fit_au as number;
  const s = 0.44 * H / fit;
  const cx = W / 2, cy = H / 2 + 20;
  const p = ease(seg(t, dur * 0.15, dur * 0.78));
  const r = Math.exp(lerp(Math.log(data.r_from_au), Math.log(data.r_to_au), p)) * s;
  const orbits: any[] = data.orbits;
  const angles = [200, 320, 40, 140, 250, 20, 290, 100];
  return (
    <g>
      {orbits.map((o, i) => (
        <circle key={i} cx={cx} cy={cy} r={o.a * s} fill="none" stroke={o.highlight ? S.cyan : "rgba(170,190,240,0.35)"} strokeWidth={o.highlight ? 2.5 : 1.6} />
      ))}
      {data.belt && <circle cx={cx} cy={cy} r={(data.belt[0] + data.belt[1]) / 2 * s} fill="none" stroke="rgba(170,190,240,0.18)" strokeWidth={(data.belt[1] - data.belt[0]) * s} />}
      <Body cx={cx} cy={cy} r={r} color={data.color} kind={data.kind} fuzzy={data.fuzzy} />
      {orbits.map((o, i) => {
        const a = (angles[i % angles.length] * Math.PI) / 180, R = o.a * s;
        const inside = R < r;
        return (
          <g key={"p" + i}>
            {inside && <circle cx={cx} cy={cy} r={R} fill="none" stroke="rgba(255,255,255,0.55)" strokeWidth={1.5} strokeDasharray="5 7" />}
            <circle cx={cx + R * Math.cos(a)} cy={cy + R * Math.sin(a)} r={7} fill={inside ? "rgba(255,255,255,0.6)" : "#cfd8ff"} />
            <text x={cx + R * Math.cos(a) + 14} y={cy + R * Math.sin(a) - 12} fill={inside ? "rgba(255,255,255,0.8)" : S.dim} fontFamily={S.body} fontWeight={600} fontSize={26}>{o.name}</text>
          </g>
        );
      })}
      <Label x={110} y={150} anchor="start" title={data.title} sub={data.sub} size={46} o={seg(t, 0.2, 0.8)} />
      {data.readout && (
        <text x={110} y={H - 120} fill={S.amber} fontFamily={S.mono} fontWeight={700} fontSize={44} opacity={seg(t, 0.4, 1)}>
          {fmtLike(data.readout, Math.exp(lerp(Math.log(parseNum(data.readout_from || "1") || 1), Math.log(parseNum(data.readout) || 1), p)))} {data.readout_unit}
        </text>
      )}
      <ScaleBar x={W - 420} y={H - 190} px={s * (data.bar_au || 1)} label={data.bar_label || "1 AU = Earth–Sun distance"} />
    </g>
  );
};

const ScaleBar: React.FC<{ x: number; y: number; px: number; label: string }> = ({ x, y, px, label }) => (
  <g>
    <line x1={x} y1={y} x2={x + px} y2={y} stroke={S.text} strokeWidth={3} />
    <line x1={x} y1={y - 10} x2={x} y2={y + 10} stroke={S.text} strokeWidth={3} />
    <line x1={x + px} y1={y - 10} x2={x + px} y2={y + 10} stroke={S.text} strokeWidth={3} />
    <text x={x} y={y + 44} fill={S.dim} fontFamily={S.body} fontWeight={500} fontSize={24}>{label}</text>
  </g>
);

// ---------- Stat: одно число крупно ----------
const Icon: React.FC<{ kind: string; x: number; y: number; t: number }> = ({ kind, x, y, t }) => {
  if (kind === "jet") return (
    <g transform={`translate(${x},${y}) rotate(-12) scale(2.2)`} fill={S.text} opacity={0.9}>
      <path d="M-60,0 L40,-6 Q60,-6 66,0 Q60,6 40,6 L-60,0 Z M-10,-4 L-30,-36 L-18,-36 L18,-5 Z M-10,4 L-30,36 L-18,36 L18,5 Z M-52,-2 L-62,-18 L-55,-18 L-44,-3 Z M-52,2 L-62,18 L-55,18 L-44,3 Z" />
    </g>
  );
  if (kind === "light") return (
    <g transform={`translate(${x},${y})`}>
      {[0, 1, 2].map((i) => <line key={i} x1={-120} y1={(i - 1) * 22} x2={lerp(-120, 120, clamp(t * 1.5 - i * 0.15))} y2={(i - 1) * 22} stroke={S.cyan} strokeWidth={6} strokeLinecap="round" opacity={0.85 - i * 0.2} />)}
    </g>
  );
  if (kind === "clock") return (
    <g transform={`translate(${x},${y})`}>
      <circle r={70} fill="none" stroke={S.text} strokeWidth={6} />
      <line x1={0} y1={0} x2={0} y2={-48} stroke={S.text} strokeWidth={6} strokeLinecap="round" transform={`rotate(${t * 90})`} />
      <line x1={0} y1={0} x2={34} y2={0} stroke={S.amber} strokeWidth={6} strokeLinecap="round" transform={`rotate(${t * 8})`} />
    </g>
  );
  return null;
};

export const Stat: React.FC<P> = ({ t, data }) => {
  const target = String(data.value);
  const n = parseNum(target);
  const k = data.count === false || n === null ? 1 : easeOut(seg(t, 0.15, 1.4));
  const shown = n === null || k >= 1 ? target : fmtLike(target, n * k);
  const o = seg(t, 0, 0.35);
  return (
    <g opacity={o}>
      {data.icon && <Icon kind={data.icon} x={W / 2} y={260} t={t} />}
      {data.pre && <text x={W / 2} y={data.icon ? 420 : 380} textAnchor="middle" fill={S.dim} fontFamily={S.body} fontWeight={500} fontSize={44}>{data.pre}</text>}
      <text x={W / 2} y={data.icon ? 610 : 600} textAnchor="middle" fill={data.color || S.amber} fontFamily={S.display} fontWeight={800} fontSize={data.size || 210}>
        {shown}<tspan fill={S.text} fontSize={(data.size || 210) * 0.42} fontWeight={700} dx={18}>{data.unit || ""}</tspan>
      </text>
      {data.caption && <text x={W / 2} y={data.icon ? 720 : 720} textAnchor="middle" fill={S.text} fontFamily={S.body} fontWeight={500} fontSize={46} opacity={seg(t, 0.4, 0.9)}>{data.caption}</text>}
      {data.sub && <text x={W / 2} y={800} textAnchor="middle" fill={S.dim} fontFamily={S.body} fontWeight={400} fontSize={34} opacity={seg(t, 0.7, 1.2)}>{data.sub}</text>}
    </g>
  );
};

// ---------- Duo: два числа рядом (самолёт и свет) ----------
export const Duo: React.FC<P> = ({ t, data }) => {
  const col = (d: any, x: number, delay: number) => {
    const n = parseNum(String(d.value)); const k = n === null ? 1 : easeOut(seg(t, delay, delay + 1.2));
    return (
      <g opacity={seg(t, delay - 0.2, delay + 0.3)}>
        {d.icon && <Icon kind={d.icon} x={x} y={330} t={t - delay} />}
        <text x={x} y={600} textAnchor="middle" fill={d.color || S.amber} fontFamily={S.display} fontWeight={800} fontSize={150}>
          {n === null || k >= 1 ? d.value : fmtLike(String(d.value), n * k)}<tspan fill={S.text} fontSize={62} dx={12}>{d.unit}</tspan>
        </text>
        <text x={x} y={690} textAnchor="middle" fill={S.text} fontFamily={S.body} fontWeight={500} fontSize={40}>{d.caption}</text>
        {d.sub && <text x={x} y={750} textAnchor="middle" fill={S.dim} fontFamily={S.body} fontSize={32}>{d.sub}</text>}
      </g>
    );
  };
  return (
    <g>
      {data.title && <Label x={W / 2} y={150} title={data.title} size={48} o={seg(t, 0, 0.4)} />}
      <line x1={W / 2} y1={260} x2={W / 2} y2={800} stroke={S.faint} strokeWidth={2} opacity={seg(t, 0.3, 0.8)} />
      {col(data.left, W * 0.27, 0.2)}
      {col(data.right, W * 0.73, data.right_delay ?? 0.9)}
    </g>
  );
};

// ---------- Bars: горизонтальные столбики с усами погрешности и линией предела ----------
export const Bars: React.FC<P> = ({ t, dur, data }) => {
  const items: any[] = data.items; const max = data.max as number;
  const x0 = 520, x1 = W - 200, rowH = Math.min(120, 620 / items.length), y0 = 300;
  const X = (v: number) => x0 + (x1 - x0) * v / max;
  return (
    <g>
      <Label x={110} y={150} anchor="start" title={data.title} sub={data.sub} size={46} o={seg(t, 0, 0.4)} />
      {items.map((it, i) => {
        const delay = 0.3 + i * (data.stagger ?? 0.35);
        const grow = easeOut(seg(t, delay, delay + 0.9));
        const shrink = it.from != null ? ease(seg(t, dur * (it.at ?? 0.45), dur * (it.at ?? 0.45) + 1.6)) : 1;
        const v = it.from != null ? lerp(it.from, it.value, shrink) * grow : it.value * grow;
        const y = y0 + i * rowH;
        const done = grow >= 1 && (it.from == null || shrink >= 1);
        return (
          <g key={i} opacity={seg(t, delay - 0.2, delay + 0.2)}>
            <text x={x0 - 30} y={y + rowH * 0.42} textAnchor="end" fill={S.text} fontFamily={S.display} fontWeight={700} fontSize={34}>{it.label}</text>
            {it.note && <text x={x0 - 30} y={y + rowH * 0.42 + 34} textAnchor="end" fill={S.dim} fontFamily={S.body} fontSize={24}>{it.note}</text>}
            <rect x={x0} y={y + rowH * 0.12} width={Math.max(2, X(v) - x0)} height={rowH * 0.46} rx={6} fill={it.color || S.amber} opacity={it.ghost ? 0.35 : 0.9} />
            {done && it.lo != null && (
              <g stroke={S.text} strokeWidth={3}>
                <line x1={X(it.lo)} y1={y + rowH * 0.35} x2={X(it.hi)} y2={y + rowH * 0.35} />
                <line x1={X(it.lo)} y1={y + rowH * 0.2} x2={X(it.lo)} y2={y + rowH * 0.5} />
                <line x1={X(it.hi)} y1={y + rowH * 0.2} x2={X(it.hi)} y2={y + rowH * 0.5} />
              </g>
            )}
            <text x={X(done && it.hi != null ? Math.max(v, it.hi) : v) + 18} y={y + rowH * 0.45} fill={S.text} fontFamily={S.mono} fontWeight={700} fontSize={32}>
              {Math.round(v).toLocaleString("en-US")}{it.suffix ?? data.suffix ?? ""}
            </text>
          </g>
        );
      })}
      {data.limit && (
        <g opacity={seg(t, dur * 0.4, dur * 0.4 + 0.6)}>
          <line x1={X(data.limit.value)} y1={y0 - 40} x2={X(data.limit.value)} y2={y0 + items.length * rowH} stroke={S.violet} strokeWidth={3} strokeDasharray="10 8" />
          <text x={X(data.limit.value)} y={y0 - 56} textAnchor="middle" fill={S.violet} fontFamily={S.body} fontWeight={600} fontSize={28}>{data.limit.label}</text>
        </g>
      )}
      {data.axis && <text x={x1} y={y0 + items.length * rowH + 50} textAnchor="end" fill={S.dim} fontFamily={S.body} fontSize={26}>{data.axis}</text>}
    </g>
  );
};

// ---------- Measure: угол на небе × расстояние = размер ----------
export const Measure: React.FC<P> = ({ t, dur, data }) => {
  const ox = 230, oy = H / 2 + 40;
  const d0 = 1500, d1 = 1500 * data.ratio;
  const p = ease(seg(t, dur * 0.35, dur * 0.8));
  const d = lerp(d0, d1, p);
  const half = 0.075; // половина угла, рад (условно, для наглядности)
  const R = Math.tan(half) * d;
  const sx = ox + d * 0.0 + Math.min(d, 1500) * 0.0 + (d / 1500) * 1450;
  return (
    <g>
      <g transform={`translate(${ox},${oy})`}>
        <rect x={-90} y={-26} width={110} height={52} rx={8} fill="none" stroke={S.text} strokeWidth={4} />
        <line x1={-60} y1={26} x2={-90} y2={90} stroke={S.text} strokeWidth={4} />
        <line x1={-20} y1={26} x2={10} y2={90} stroke={S.text} strokeWidth={4} />
        <text x={-35} y={140} textAnchor="middle" fill={S.dim} fontFamily={S.body} fontSize={26}>telescope</text>
      </g>
      <line x1={ox + 20} y1={oy} x2={sx} y2={oy - (sx - ox) * Math.tan(half)} stroke={S.cyan} strokeWidth={3} opacity={0.8} />
      <line x1={ox + 20} y1={oy} x2={sx} y2={oy + (sx - ox) * Math.tan(half)} stroke={S.cyan} strokeWidth={3} opacity={0.8} />
      <Body cx={sx} cy={oy} r={(sx - ox) * Math.tan(half)} color="#ff6b3d" fuzzy />
      <line x1={ox + 20} y1={oy + 220} x2={sx} y2={oy + 220} stroke={S.amber} strokeWidth={3} />
      <text x={(ox + sx) / 2} y={oy + 270} textAnchor="middle" fill={S.amber} fontFamily={S.mono} fontWeight={700} fontSize={34}>
        {p < 0.5 ? data.label_from : data.label_to}
      </text>
      <Label x={W / 2} y={140} title={data.title || "Size = angle × distance"} sub={data.sub} size={48} o={seg(t, 0, 0.5)} />
      {data.size_from && (
        <text x={sx} y={oy - R - 40 > 200 ? oy - (sx - ox) * Math.tan(half) - 30 : 230} textAnchor="middle" fill={S.text} fontFamily={S.mono} fontWeight={700} fontSize={36}>
          {fmtLike(data.size_to, lerp(parseNum(data.size_from)!, parseNum(data.size_to)!, p))} {data.size_unit}
        </text>
      )}
    </g>
  );
};

// ---------- SkyMap: созвездие по настоящим координатам ----------
const CONST: Record<string, { c: [number, number]; scale: number; stars: [string, number, number, number][]; lines: [number, number][] }> = {
  orion: { c: [5.6, 0], scale: 50, stars: [["Betelgeuse", 5.919, 7.41, 0.5], ["Rigel", 5.242, -8.2, 0.13], ["Bellatrix", 5.419, 6.35, 1.64], ["Saiph", 5.796, -9.67, 2.06],
    ["Alnitak", 5.679, -1.94, 1.77], ["Alnilam", 5.604, -1.2, 1.69], ["Mintaka", 5.533, -0.3, 2.23], ["Meissa", 5.585, 9.93, 3.33]],
    lines: [[0, 4], [2, 6], [4, 5], [5, 6], [4, 3], [6, 1], [0, 7], [2, 7]] },
  dipper: { c: [12.9, 38], scale: 15, stars: [["Dubhe", 11.062, 61.75, 1.8], ["Merak", 11.031, 56.38, 2.37], ["Phecda", 11.897, 53.69, 2.44], ["Megrez", 12.257, 57.03, 3.31],
    ["Alioth", 12.9, 55.96, 1.77], ["Mizar", 13.399, 54.93, 2.04], ["Alkaid", 13.792, 49.31, 1.86], ["Arcturus", 14.261, 19.18, -0.05]],
    lines: [[0, 1], [1, 2], [2, 3], [3, 0], [3, 4], [4, 5], [5, 6]] },
  scorpius: { c: [16.7, -30], scale: 30, stars: [["Antares", 16.49, -26.43, 1.06], ["Dschubba", 16.006, -22.62, 2.29], ["Acrab", 16.091, -19.8, 2.62], ["Pi Sco", 15.981, -26.11, 2.89],
    ["Sigma Sco", 16.353, -25.59, 2.88], ["Tau Sco", 16.598, -28.22, 2.82], ["Epsilon Sco", 16.836, -34.29, 2.29], ["Mu Sco", 16.864, -38.05, 3.0],
    ["Zeta Sco", 16.91, -42.36, 3.6], ["Eta Sco", 17.203, -43.24, 3.32], ["Theta Sco", 17.622, -43.0, 1.86], ["Iota Sco", 17.793, -40.13, 2.99],
    ["Kappa Sco", 17.708, -39.03, 2.41], ["Shaula", 17.56, -37.1, 1.62]],
    lines: [[2, 1], [1, 3], [1, 4], [4, 0], [0, 5], [5, 6], [6, 7], [7, 8], [8, 9], [9, 10], [10, 11], [11, 12], [12, 13]] },
};

export const SkyMap: React.FC<P> = ({ t, data }) => {
  const c = CONST[data.constellation];
  const [ra0, de0] = c.c;
  const proj = (ra: number, de: number) => {
    const a = ((ra - ra0) * 15 * Math.PI) / 180, d = (de * Math.PI) / 180, d0 = (de0 * Math.PI) / 180;
    const cosc = Math.sin(d0) * Math.sin(d) + Math.cos(d0) * Math.cos(d) * Math.cos(a);
    const x = (Math.cos(d) * Math.sin(a)) / cosc, y = (Math.cos(d0) * Math.sin(d) - Math.sin(d0) * Math.cos(d) * Math.cos(a)) / cosc;
    return [W / 2 - (x * 180 / Math.PI) * c.scale, H / 2 + 30 - (y * 180 / Math.PI) * c.scale];
  };
  const pts = c.stars.map((s) => proj(s[1], s[2]));
  const hl: string[] = data.highlight || [];
  return (
    <g>
      {c.lines.map(([a, b], i) => <line key={i} x1={pts[a][0]} y1={pts[a][1]} x2={pts[b][0]} y2={pts[b][1]} stroke="rgba(140,170,230,0.35)" strokeWidth={2} opacity={seg(t, 0.1 + i * 0.05, 0.6 + i * 0.05)} />)}
      {data.arc && (() => { const [a, b] = data.arc; const p1 = pts[a], p2 = pts[b]; const mx = (p1[0] + p2[0]) / 2 + 120, my = (p1[1] + p2[1]) / 2 - 40;
        return <path d={`M${p1[0]},${p1[1]} Q${mx},${my} ${p2[0]},${p2[1]}`} fill="none" stroke={S.amber} strokeWidth={3} strokeDasharray="10 10" opacity={seg(t, 0.8, 1.6)} />; })()}
      {c.stars.map((s, i) => {
        const r = Math.max(3, 11 - s[3] * 2.4), on = hl.includes(s[0]);
        return (
          <g key={i}>
            {on && <circle cx={pts[i][0]} cy={pts[i][1]} r={r * 3.2 + 6 * Math.sin(t * 3)} fill="none" stroke={S.amber} strokeWidth={3} opacity={seg(t, 0.6, 1)} />}
            <circle cx={pts[i][0]} cy={pts[i][1]} r={r} fill={on ? "#ffd9a8" : "#ffffff"} />
            {on && <text x={pts[i][0] + r * 3.5 + 12} y={pts[i][1] + 12} fill={S.amber} fontFamily={S.display} fontWeight={700} fontSize={38} opacity={seg(t, 0.7, 1.1)}>{s[0]}</text>}
          </g>
        );
      })}
      {data.title && <Label x={110} y={150} anchor="start" title={data.title} sub={data.sub} size={46} o={seg(t, 0, 0.4)} />}
    </g>
  );
};

// ---------- Timeline ----------
export const Timeline: React.FC<P> = ({ t, data }) => {
  const items: any[] = data.items; const x0 = 200, x1 = W - 200, y = H / 2 + 40;
  return (
    <g>
      {data.title && <Label x={110} y={150} anchor="start" title={data.title} size={46} o={seg(t, 0, 0.4)} />}
      <line x1={x0} y1={y} x2={lerp(x0, x1, easeOut(seg(t, 0, 1)))} y2={y} stroke={S.faint} strokeWidth={4} />
      {items.map((it, i) => {
        const x = items.length === 1 ? (x0 + x1) / 2 : lerp(x0 + 80, x1 - 80, i / (items.length - 1));
        const d = 0.4 + i * (data.stagger ?? 0.6); const up = i % 2 === 0;
        return (
          <g key={i} opacity={seg(t, d, d + 0.4)}>
            <circle cx={x} cy={y} r={14} fill={it.color || S.amber} />
            <text x={x} y={up ? y - 50 : y + 80} textAnchor="middle" fill={it.color || S.amber} fontFamily={S.mono} fontWeight={700} fontSize={48}>{it.year}</text>
            {String(it.text).split("\n").map((ln: string, k: number) => (
              <text key={k} x={x} y={(up ? y - 110 - 38 * (String(it.text).split("\n").length - 1) : y + 130) + k * 38} textAnchor="middle" fill={S.text} fontFamily={S.body} fontWeight={500} fontSize={32}>{ln}</text>
            ))}
          </g>
        );
      })}
    </g>
  );
};

// ---------- Known / Open: что установлено, а что нет ----------
export const Known: React.FC<P> = ({ t, data }) => {
  const col = (title: string, items: string[], x: number, color: string, d0: number) => (
    <g>
      <text x={x} y={260} fill={color} fontFamily={S.display} fontWeight={800} fontSize={44} opacity={seg(t, d0, d0 + 0.4)}>{title}</text>
      <line x1={x} y1={285} x2={x + 700} y2={285} stroke={color} strokeWidth={3} opacity={seg(t, d0, d0 + 0.4)} />
      {items.map((s, i) => (
        <g key={i} opacity={seg(t, d0 + 0.4 + i * 0.5, d0 + 0.8 + i * 0.5)}>
          <circle cx={x + 14} cy={355 + i * 110} r={8} fill={color} />
          {s.split("\n").map((ln, k) => <text key={k} x={x + 44} y={367 + i * 110 + k * 42} fill={S.text} fontFamily={S.body} fontWeight={500} fontSize={36}>{ln}</text>)}
        </g>
      ))}
    </g>
  );
  return (
    <g>
      {data.title && <Label x={W / 2} y={140} title={data.title} size={50} o={seg(t, 0, 0.4)} />}
      {col(data.known_title || "ESTABLISHED", data.known, 150, S.green, 0.2)}
      {col(data.open_title || "STILL OPEN", data.open, 1010, S.violet, 0.2 + (data.known.length + 1) * 0.5)}
    </g>
  );
};

// ---------- Card: глава / утверждение крупно ----------
export const Card: React.FC<P> = ({ t, data }) => {
  const lines = String(data.text).split("\n");
  const size = data.size || (data.chapter ? 92 : 78);
  const y0 = H / 2 - ((lines.length - 1) * size * 1.15) / 2 + size * 0.35 + (data.chapter ? 30 : 0);
  return (
    <g>
      {data.chapter && <text x={W / 2} y={y0 - size * 1.3} textAnchor="middle" fill={S.amber} fontFamily={S.mono} fontWeight={700} fontSize={34} letterSpacing={8} opacity={seg(t, 0, 0.4)}>{data.chapter}</text>}
      {lines.map((ln, i) => (
        <text key={i} x={W / 2} y={y0 + i * size * 1.15} textAnchor="middle" fill={data.color || S.text} fontFamily={S.display} fontWeight={800} fontSize={size}
          opacity={seg(t, 0.1 + i * 0.25, 0.5 + i * 0.25)} transform={`translate(0,${(1 - easeOut(seg(t, 0.1 + i * 0.25, 0.7 + i * 0.25))) * 24})`}>{ln}</text>
      ))}
      {data.sub && <text x={W / 2} y={y0 + lines.length * size * 1.15 + 20} textAnchor="middle" fill={S.dim} fontFamily={S.body} fontWeight={500} fontSize={40} opacity={seg(t, 0.8, 1.3)}>{data.sub}</text>}
      {data.chapter && <line x1={W / 2 - 160 * easeOut(seg(t, 0.3, 1))} y1={y0 + lines.length * size * 1.15 + 60} x2={W / 2 + 160 * easeOut(seg(t, 0.3, 1))} y2={y0 + lines.length * size * 1.15 + 60} stroke={S.amber} strokeWidth={4} />}
    </g>
  );
};

// ---------- Tidal: приливное растяжение у малой и у гигантской чёрной дыры ----------
const Figure: React.FC<{ x: number; y: number; sy: number; sx: number; color?: string; o?: number }> = ({ x, y, sy, sx, color = "#E8EEFF", o = 1 }) => (
  <g transform={`translate(${x},${y}) scale(${sx},${sy})`} opacity={o} fill={color}>
    <circle cx={0} cy={-62} r={16} />
    <rect x={-16} y={-44} width={32} height={58} rx={12} />
    <rect x={-15} y={12} width={12} height={46} rx={6} />
    <rect x={3} y={12} width={12} height={46} rx={6} />
  </g>
);

export const Tidal: React.FC<P> = ({ t, dur, data }) => {
  const giant = data.mode === "giant";
  const p = ease(seg(t, 0.4, dur * 0.85));
  const bx = giant ? -2400 : 300, by = H / 2 + 20, br = giant ? 2900 : 70;
  const horizonX = bx + br;
  const fx = giant ? lerp(W - 300, horizonX - 140, p) : lerp(W - 260, horizonX + 420, p);
  const stretch = giant ? 1 : 1 + 2.6 * Math.pow(p, 3);
  const squeeze = 1 / Math.sqrt(stretch);
  const arrow = (x: number, y: number, len: number, dir: number, k: number) => (
    <g key={k} stroke={S.amber} strokeWidth={5} strokeLinecap="round" fill={S.amber}>
      <line x1={x} y1={y} x2={x + dir * len} y2={y} />
      <path d={`M${x + dir * (len + 16)},${y} l${-dir * 18},-12 l0,24 z`} stroke="none" />
    </g>
  );
  const head = giant ? 22 : 22 + 30 * p, feet = giant ? 22 : 22 + 260 * Math.pow(p, 2);
  return (
    <g>
      <Body cx={bx} cy={by} r={br} color="#000" kind="bh" />
      {giant && <text x={horizonX + 20} y={by - 300} fill={S.dim} fontFamily={S.body} fontWeight={600} fontSize={30}>event horizon</text>}
      <g transform={`translate(${fx},${by}) rotate(90) scale(1.35)`}>
        <Figure x={0} y={0} sy={stretch} sx={squeeze} />
      </g>
      {arrow(fx - 110 * stretch, by - 120, feet, -1, 1)}
      {arrow(fx + 110 * stretch, by - 120, head, -1, 2)}
      <text x={fx - 110 * stretch - feet / 2} y={by - 150} textAnchor="middle" fill={S.amber} fontFamily={S.body} fontWeight={600} fontSize={26}>feet</text>
      <text x={fx + 110 * stretch - head / 2} y={by - 150} textAnchor="middle" fill={S.amber} fontFamily={S.body} fontWeight={600} fontSize={26}>head</text>
      <Label x={W / 2} y={140} title={data.title} sub={data.sub} size={48} o={seg(t, 0, 0.5)} />
      {data.readout && <text x={W / 2} y={H - 110} textAnchor="middle" fill={S.amber} fontFamily={S.mono} fontWeight={700} fontSize={42} opacity={seg(t, dur * 0.5, dur * 0.5 + 0.5)}>{data.readout}</text>}
    </g>
  );
};

// ---------- Redshift: взгляд друга — падающий замедляется, краснеет и гаснет ----------
export const Redshift: React.FC<P> = ({ t, dur, data }) => {
  const hx = 520, y = H / 2 + 40;
  const tau = dur / 5;
  const x = hx + 40 + (W - 300 - hx) * Math.exp(-t / tau);
  const k = clamp(1 - (x - hx - 40) / (W - 300 - hx));
  const col = `rgb(${255},${Math.round(lerp(240, 40, k))},${Math.round(lerp(255, 20, k))})`;
  const yours = t * 1.0, seen = tau * (1 - Math.exp(-t / tau));
  const clock = (cx: number, label: string, v: number, c: string) => (
    <g>
      <circle cx={cx} cy={250} r={60} fill="none" stroke={c} strokeWidth={5} />
      <line x1={cx} y1={250} x2={cx} y2={200} stroke={c} strokeWidth={6} strokeLinecap="round" transform={`rotate(${v * 72},${cx},250)`} />
      <text x={cx} y={355} textAnchor="middle" fill={c} fontFamily={S.body} fontWeight={600} fontSize={30}>{label}</text>
    </g>
  );
  return (
    <g>
      <rect x={0} y={0} width={hx} height={H} fill="#000" />
      <line x1={hx} y1={0} x2={hx} y2={H} stroke="rgba(255,190,110,0.6)" strokeWidth={3} />
      <text x={hx - 30} y={H - 80} textAnchor="end" fill={S.dim} fontFamily={S.body} fontWeight={600} fontSize={30}>event horizon</text>
      <g opacity={lerp(1, 0.08, Math.pow(k, 1.5))}>
        <circle cx={x} cy={y} r={26} fill={col} />
        <circle cx={x} cy={y} r={60} fill={col} opacity={0.18} />
      </g>
      {clock(W - 520, data.left || "your watch", yours, S.text)}
      {clock(W - 260, data.right || "what your friend sees", seen, S.amber)}
      {data.title && <Label x={110} y={140} anchor="start" title={data.title} size={44} o={seg(t, 0, 0.5)} />}
    </g>
  );
};

// ---------- Inside: внутри горизонта все пути ведут к центру ----------
export const Inside: React.FC<P> = ({ t, data }) => {
  const cx = W / 2, cy = H / 2 + 40, R = 400;
  const arrows = Array.from({ length: 16 }, (_, i) => (i / 16) * Math.PI * 2);
  const pulse = (t * 0.35) % 1;
  return (
    <g>
      <circle cx={cx} cy={cy} r={R} fill="#000" stroke="rgba(255,190,110,0.6)" strokeWidth={3} />
      {arrows.map((a, i) => {
        const r0 = R * lerp(0.95, 0.25, (pulse + i * 0.37) % 1), r1 = r0 - 60;
        return (
          <g key={i} opacity={seg(t, 0.2 + i * 0.03, 0.6 + i * 0.03)}>
            <line x1={cx + r0 * Math.cos(a)} y1={cy + r0 * Math.sin(a)} x2={cx + r1 * Math.cos(a)} y2={cy + r1 * Math.sin(a)} stroke={S.cyan} strokeWidth={4} strokeLinecap="round" />
            <path d={`M${cx + (r1 - 14) * Math.cos(a)},${cy + (r1 - 14) * Math.sin(a)} L${cx + r1 * Math.cos(a) - 10 * Math.sin(a)},${cy + r1 * Math.sin(a) + 10 * Math.cos(a)} L${cx + r1 * Math.cos(a) + 10 * Math.sin(a)},${cy + r1 * Math.sin(a) - 10 * Math.cos(a)} Z`} fill={S.cyan} />
          </g>
        );
      })}
      <circle cx={cx} cy={cy} r={6} fill={S.violet} />
      <Label x={W / 2} y={140} title={data.title} sub={data.sub} size={46} o={seg(t, 0, 0.5)} />
      {data.center && <text x={cx} y={cy + 60} textAnchor="middle" fill={S.violet} fontFamily={S.body} fontWeight={600} fontSize={30} opacity={seg(t, 1, 1.5)}>{data.center}</text>}
    </g>
  );
};

// ---------- Photo: реальный снимок (NASA/ESA/ESO/EHT) или иллюстрация с медленным наездом ----------
export const Photo: React.FC<P & { html?: boolean }> = () => null;

export const PhotoLayer: React.FC<P> = ({ t, dur, data }) => {
  const z = data.motion === "out" ? lerp(1.12, 1.0, t / dur) : lerp(1.0, 1.12, t / dur);
  const dx = data.motion === "left" ? lerp(30, -30, t / dur) : data.motion === "right" ? lerp(-30, 30, t / dur) : 0;
  const contain = data.fit === "contain";
  return (
    <div style={{ position: "absolute", inset: 0, overflow: "hidden", background: S.bg }}>
      {contain && <Img src={staticFile(data.src)} style={{ position: "absolute", inset: -40, width: W + 80, height: H + 80, objectFit: "cover", filter: "blur(40px) brightness(0.35)" }} />}
      <Img src={staticFile(data.src)} style={{ position: "absolute", inset: 0, width: W, height: H, objectFit: contain ? "contain" : "cover",
        transform: `scale(${z}) translateX(${dx}px)`, transformOrigin: data.focus || "50% 50%" }} />
      {data.caption && (
        <div style={{ position: "absolute", left: 96, bottom: 120, color: S.text, fontFamily: S.display, fontWeight: 700, fontSize: 44,
          textShadow: "0 2px 18px rgba(0,0,0,0.85)", opacity: seg(t, 0.3, 0.8) }}>{data.caption}</div>
      )}
    </div>
  );
};

export const SVG_SCENES: Record<string, React.FC<P>> = {
  compare: Compare, orbits: Orbits, stat: Stat, duo: Duo, bars: Bars, measure: Measure, sky: SkyMap,
  timeline: Timeline, known: Known, card: Card, tidal: Tidal, redshift: Redshift, inside: Inside,
};
