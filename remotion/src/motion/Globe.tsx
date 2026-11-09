import React from "react";
import { AbsoluteFill, Easing, Img, interpolate, staticFile } from "remotion";
import { geoDistance, geoGraticule10, geoInterpolate, geoOrthographic, geoPath } from "d3-geo";
import { loadFont as loadBebas } from "@remotion/google-fonts/BebasNeue";
import { loadFont as loadInter } from "@remotion/google-fonts/Inter";
import { loadFont as loadMono } from "@remotion/google-fonts/IBMPlexMono";
import land from "../geo/land50.json";
import { Captions, Credit, EndCard, MotionProps, Sound, cue, ease, pop, useT } from "./common";

/** Шаблон «Глобус» (образец Pan Am 06.10, выбор владельца): схема сети на вращающемся глобусе.
 *  Группы линий появляются (appear) или гаснут (vanish) на фразе диктора; камера летит по якорям; годы и подписи — тоже по якорям. */
const bebas = loadBebas("normal", { weights: ["400"], subsets: ["latin"] });
const inter = loadInter("normal", { weights: ["500", "700", "800"], subsets: ["latin"] });
const mono = loadMono("normal", { weights: ["500", "600"], subsets: ["latin"] });
const C = { bg: "#050C18", ocean: "#0B1C33", land: "#1C3656", coast: "#2F5580", line: "#5CC8FF", gone: "#FF5A4F", fg: "#F2F6FB", dim: "rgba(242,246,251,.55)", gold: "#FFD166" };

export type GlobeData = {
  kicker: string; counterLabel: string; disclaimer: string;
  points: Record<string, [number, number]>;              // код → [долгота, широта]
  lines: [string, string, string][];                     // [от, до, группа]
  groups: Record<string, { mode?: "start" | "appear" | "vanish"; cue?: string; appear?: string; vanish?: string }>;
  camera: { cue: string; lon: number; lat: number; zoom: number }[];   // первая точка — кадр с начала
  headlines: { cue: string; year?: string; text: string }[];
  tags?: { cue: string; text: string; point: string; until?: string }[];
  finale?: { cue: string; photo: string; credit: string };
};
const R = 450, CX = 540, CY = 850;
const graticule = geoGraticule10();

export const Globe: React.FC<MotionProps<GlobeData>> = (p) => {
  const { t, fps } = useT(); const W = p.words; const D = p.data;
  const end = cue(W, "Watch the full");
  // камера: долготы разворачиваются, чтобы глобус крутился кратчайшим путём
  const cams: (GlobeData["camera"][number] & { t: number })[] = []; D.camera.forEach((c, i) => cams.push({ ...c, t: i ? cue(W, c.cue, cams[i - 1].t + 0.01) : 0 }));
  for (let i = 1; i < cams.length; i++) { let d = cams[i].lon - cams[i - 1].lon; while (d > 180) d -= 360; while (d < -180) d += 360; cams[i] = { ...cams[i], lon: cams[i - 1].lon + d }; }
  const cam = (() => {
    let k = 0; while (k < cams.length - 1 && t > cams[k + 1].t) k++;
    if (k >= cams.length - 1) return cams[cams.length - 1];
    const a = cams[k], b = cams[k + 1]; const u = interpolate(t, [b.t - 0.2, b.t + 2.0], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.inOut(Easing.cubic) });
    return { lon: a.lon + (b.lon - a.lon) * u, lat: a.lat + (b.lat - a.lat) * u, zoom: a.zoom + (b.zoom - a.zoom) * u };
  })();
  const proj = geoOrthographic().scale(R * cam.zoom).translate([CX, CY]).rotate([-cam.lon, -cam.lat]).clipAngle(90).precision(0.3);
  const path = geoPath(proj);
  const centre: [number, number] = [((cam.lon % 360) + 540) % 360 - 180, cam.lat];
  const visible = (pt: [number, number]) => geoDistance(pt, centre) < Math.PI / 2 - 0.05;
  // группа: появляется (appear) и/или гаснет (vanish) на фразе диктора; старое поле mode+cue тоже понимается
  const gT = Object.fromEntries(Object.entries(D.groups).map(([g, v]) => {
    const ap = v.appear ? cue(W, v.appear) : v.mode === "appear" && v.cue ? cue(W, v.cue) : null;
    const va = v.vanish ? cue(W, v.vanish, ap ?? 0) : v.mode === "vanish" && v.cue ? cue(W, v.cue) : null;
    return [g, { ap, va }];
  }));
  const lineState = (g: string, k: number) => {
    const { ap, va } = gT[g] ?? { ap: null, va: null }; const s = ap != null ? ap + (k % 4) * 0.12 : 0.15 + k * 0.05;
    const draw = ease(t, s, s + 1.25, 0, 1, Easing.out(Easing.cubic));
    if (va == null) return { draw, flash: 0, fade: 0, gone: false };
    const at = va + (k % 4) * 0.08; const flash = ease(t, at, at + 0.15) * (1 - ease(t, at + 0.15, at + 0.5));
    return { draw, flash, fade: ease(t, at + 0.2, at + 1.6), gone: t >= at };
  };
  const shown = D.lines.filter(([, , g], k) => { const st = lineState(g, k); return st.draw > 0 && st.fade < 1 && !st.gone; }).length;
  const hs: (GlobeData["headlines"][number] & { t: number })[] = []; D.headlines.forEach((h, i) => hs.push({ ...h, t: cue(W, h.cue, i ? hs[i - 1].t + 0.01 : 0) })); const hk = hs.filter((h) => t >= h.t - 0.05).pop();
  const year = hs.filter((h) => h.year && t >= h.t - 0.05).pop();
  const fin = D.finale ? cue(W, D.finale.cue) : 1e9;
  const globeDim = 1 - 0.75 * ease(t, fin, fin + 0.8);
  const stars = Array.from({ length: 70 }, (_, k) => [(k * 397) % 1080, (k * 733) % 1920, ((k * 13) % 10) / 10]);

  return (
    <AbsoluteFill style={{ background: `radial-gradient(circle at 50% 44%, #0E2240 0%, ${C.bg} 62%)`, color: C.fg, overflow: "hidden" }}>
      <Sound p={p} music={0.12} />
      <svg width={1080} height={1920} style={{ position: "absolute" }}>{stars.map(([x, y, o], k) => <circle key={k} cx={x} cy={y} r={1.6} fill="#fff" opacity={0.15 + 0.35 * o} />)}</svg>
      <svg width={1080} height={1920} style={{ position: "absolute", opacity: globeDim }}>
        <defs>
          <radialGradient id="ocean" cx="40%" cy="35%"><stop offset="0%" stopColor="#13304F" /><stop offset="100%" stopColor={C.ocean} /></radialGradient>
          <filter id="glow"><feGaussianBlur stdDeviation="5" result="b" /><feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge></filter>
        </defs>
        <circle cx={CX} cy={CY} r={R * cam.zoom} fill="url(#ocean)" />
        <path d={path(graticule) ?? ""} fill="none" stroke="#24476F" strokeWidth={1} opacity={0.5} />
        <path d={path(land as any) ?? ""} fill={C.land} stroke={C.coast} strokeWidth={1.2} />
        <circle cx={CX} cy={CY} r={R * cam.zoom} fill="none" stroke={C.line} strokeOpacity={0.35} strokeWidth={3} />
        <g filter="url(#glow)">
          {D.lines.map(([a, b, g], k) => {
            const st = lineState(g, k); if (st.fade >= 1 || st.draw <= 0 || !D.points[a] || !D.points[b]) return null;
            const ip = geoInterpolate(D.points[a], D.points[b]); const n = 40;
            const coords = Array.from({ length: Math.max(2, Math.round(n * st.draw) + 1) }, (_, i) => ip(Math.min(st.draw, i / n)));
            const color = st.flash > 0.01 ? "#FFFFFF" : st.gone ? C.gone : C.line;
            const short = geoDistance(D.points[a], D.points[b]) < 0.03;
            return <path key={k} d={path({ type: "LineString", coordinates: coords } as any) ?? ""} fill="none" stroke={color}
              strokeWidth={(short ? 7 : 4.5) + st.flash * 5} strokeLinecap="round" opacity={1 - st.fade} />;
          })}
        </g>
        {Object.entries(D.points).map(([code, pt]) => {
          if (!visible(pt)) return null; const xy = proj(pt); if (!xy) return null;
          const live = D.lines.some(([a, b, g], k) => (a === code || b === code) && (() => { const s = lineState(g, k); return s.draw > 0 && s.fade < 1; })());
          return <circle key={code} cx={xy[0]} cy={xy[1]} r={live ? 7 : 4} fill={live ? "#fff" : "#4A6A8F"} />;
        })}
        {(D.tags ?? []).map((tg, k) => {
          const at = cue(W, tg.cue); const until = tg.until ? cue(W, tg.until, at) : at + 3; const pt = D.points[tg.point];
          if (!pt || t < at || t > until + 0.8 || !visible(pt)) return null; const xy = proj(pt); if (!xy) return null;
          const s = pop(t, at, fps); const out = ease(t, until, until + 0.6);
          const x = Math.min(1080 - 160 - tg.text.length * 13, Math.max(40 + tg.text.length * 13, xy[0]));
          return <g key={k} opacity={s * (1 - out)} transform={`translate(${x} ${xy[1] - 30 * s})`}>
            <rect x={-tg.text.length * 13 - 18} y={-58} width={tg.text.length * 26 + 36} height={52} rx={26} fill={C.gone} />
            <text x={0} y={-22} textAnchor="middle" fill="#fff" fontFamily={inter.fontFamily} fontWeight={800} fontSize={30}>{tg.text}</text>
          </g>;
        })}
      </svg>
      {D.finale && t >= fin && t < end && <div style={{ position: "absolute", left: 90, right: 90, top: 560, opacity: ease(t, fin, fin + 0.8) }}>
        <div style={{ border: "10px solid #fff", boxShadow: "0 40px 90px rgba(0,0,0,.7)", transform: `rotate(-2deg) scale(${1 + 0.02 * (t - fin)})` }}>
          <Img src={staticFile(D.finale.photo)} style={{ width: "100%", display: "block", filter: "grayscale(0.85) brightness(0.8)" }} />
        </div>
        <div style={{ marginTop: 26, fontFamily: mono.fontFamily, fontSize: 21, color: C.dim }}>{D.finale.credit}</div>
      </div>}
      <div style={{ position: "absolute", left: 70, top: 160, fontFamily: mono.fontFamily, fontWeight: 600, fontSize: 28, letterSpacing: 5, color: C.line }}>{D.kicker}</div>
      <div style={{ position: "absolute", right: 150, top: 160, textAlign: "right", fontFamily: mono.fontFamily, fontSize: 22, color: C.dim, letterSpacing: 2 }}>
        {D.counterLabel}<div style={{ fontFamily: bebas.fontFamily, fontSize: 84, color: shown ? C.fg : C.gone, letterSpacing: 2, lineHeight: 1 }}>{shown}</div>
      </div>
      {year && <div key={year.year} style={{ position: "absolute", left: 66, top: 200, fontFamily: bebas.fontFamily, fontSize: (year.year ?? "").length > 4 ? 120 : 170, lineHeight: 1, color: C.fg,
        transform: `translateY(${(1 - pop(t, year.t, fps)) * 40}px)`, opacity: pop(t, year.t, fps) }}>{year.year}</div>}
      {hk && hk.text && <div key={hk.text} style={{ position: "absolute", left: 70, right: 150, top: 380, fontFamily: inter.fontFamily, fontWeight: 800, fontSize: 44, color: hk.text.includes("→") ? C.gold : C.fg,
        transform: `translateX(${(1 - pop(t, hk.t, fps)) * -60}px)`, opacity: pop(t, hk.t, fps) }}>{hk.text}</div>}
      {t < fin && <Credit text={D.disclaimer} color={C.dim} font={mono.fontFamily} show={ease(t, 0.5, 1.2)} top={1420} />}
      <Captions words={W} until={end} st={{ top: 1325, font: inter.fontFamily, size: 60, weight: 800, color: C.fg, dim: C.dim, active: C.line, maxWords: 3, shadow: "0 4px 16px rgba(0,0,0,.9)" }} />
      <EndCard at={end} title={p.title} bg={C.bg} fg={C.fg} accent={C.line} font={inter.fontFamily} mono={mono.fontFamily} />
    </AbsoluteFill>
  );
};
