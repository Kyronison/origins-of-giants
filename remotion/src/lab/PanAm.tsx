import React from "react";
import { AbsoluteFill, Easing, Img, interpolate, staticFile } from "remotion";
import { geoDistance, geoGraticule10, geoInterpolate, geoOrthographic, geoPath } from "d3-geo";
import { loadFont as loadBebas } from "@remotion/google-fonts/BebasNeue";
import { loadFont as loadInter } from "@remotion/google-fonts/Inter";
import { loadFont as loadMono } from "@remotion/google-fonts/IBMPlexMono";
import land from "../geo/land50.json";
import { Captions, Credit, EndCard, LabProps, Sound, cue, ease, pop, useT } from "./common";

/** Формат 2 «Глобус»: схема маршрутов Pan Am на вращающемся глобусе; каждая продажа гасит свой участок сети. */
const bebas = loadBebas("normal", { weights: ["400"], subsets: ["latin"] });
const inter = loadInter("normal", { weights: ["500", "700", "800"], subsets: ["latin"] });
const mono = loadMono("normal", { weights: ["500", "600"], subsets: ["latin"] });
const C = { bg: "#050C18", ocean: "#0B1C33", land: "#1C3656", coast: "#2F5580", route: "#5CC8FF", sold: "#FF5A4F", fg: "#F2F6FB", dim: "rgba(242,246,251,.55)", gold: "#FFD166" };

const AP: Record<string, [number, number]> = {
  JFK: [-73.78, 40.64], LGA: [-73.87, 40.78], MIA: [-80.29, 25.79], SFO: [-122.38, 37.62], LAX: [-118.41, 33.94], HNL: [-157.92, 21.32],
  NRT: [140.39, 35.77], PEK: [116.6, 40.08], HKG: [113.92, 22.31], SYD: [151.18, -33.95], AKL: [174.79, -37.01],
  LHR: [-0.45, 51.47], FRA: [8.57, 50.03], CDG: [2.55, 49.01], FCO: [12.25, 41.8], IST: [28.8, 40.98], TXL: [13.29, 52.56], MUC: [11.79, 48.35], HAM: [9.99, 53.63],
  BOS: [-71.0, 42.36], DCA: [-77.04, 38.85], IAD: [-77.46, 38.95], GRU: [-46.47, -23.43], CCS: [-66.99, 10.6], BOG: [-74.15, 4.7], SJU: [-66.0, 18.44],
};
type Group = "pacific" | "germany" | "london" | "atlantic" | "shuttle" | "rest";
const ROUTES: [string, string, Group][] = [
  ["SFO", "HNL", "pacific"], ["LAX", "HNL", "pacific"], ["HNL", "NRT", "pacific"], ["SFO", "NRT", "pacific"], ["NRT", "PEK", "pacific"], ["NRT", "HKG", "pacific"], ["HNL", "SYD", "pacific"], ["HNL", "AKL", "pacific"],
  ["TXL", "FRA", "germany"], ["TXL", "MUC", "germany"], ["TXL", "HAM", "germany"],
  ["JFK", "LHR", "london"], ["IAD", "LHR", "london"], ["MIA", "LHR", "london"], ["SFO", "LHR", "london"],
  ["JFK", "FRA", "atlantic"], ["JFK", "CDG", "atlantic"], ["JFK", "FCO", "atlantic"], ["JFK", "IST", "atlantic"],
  ["LGA", "BOS", "shuttle"], ["LGA", "DCA", "shuttle"],
  ["MIA", "CCS", "rest"], ["MIA", "BOG", "rest"], ["MIA", "SJU", "rest"], ["MIA", "GRU", "rest"],
];
const R = 450, CX = 540, CY = 850;
const graticule = geoGraticule10();

export const PanAm: React.FC<LabProps> = (p) => {
  const { t, fps } = useT(); const W = p.words;
  const c = {
    watch: cue(W, "Watch what"), y85: cue(W, "1985"), cash: cue(W, "needs cash"), united1: cue(W, "United", 9), japan: cue(W, "Japan"), china: cue(W, "China"),
    australia: cue(W, "Australia"), hk: cue(W, "Hong Kong"), gone: cue(W, "Gone"), y90: cue(W, "1990"), germany: cue(W, "inside Germany"), lufthansa: cue(W, "Lufthansa"),
    then: cue(W, "Then London"), united2: cue(W, "United", 20), y91: cue(W, "1991", 20), delta: cue(W, "Delta buys"), atlantic: cue(W, "Atlantic"), shuttle: cue(W, "Shuttle"),
    every: cue(W, "Every sale kept"), and: cue(W, "And every sale"), dec: cue(W, "On December"), stopped: cue(W, "stopped flying"), end: cue(W, "Watch the full"),
  };
  // камера: [секунда, долгота центра, широта центра, зум]
  const keys: [number, number, number, number][] = [
    [0, 15, 38, 1], [c.y85, -100, 30, 1], [c.y85 + 2.4, -200, 12, 1.0], [c.gone + 0.3, -200, 12, 1.0],
    [c.y90 + 1.4, -349, 51, 4.6], [c.then - 0.1, -349, 51, 4.6], [c.then + 1.2, -398, 45, 1.12], [c.every, -402, 38, 1.05], [c.and + 1.5, -430, 8, 1.2], [c.end, -430, 8, 1.2],
  ];
  const cam = (() => {
    let k = 0; while (k < keys.length - 2 && t > keys[k + 1][0]) k++;
    const [t0, a0, b0, z0] = keys[k], [t1, a1, b1, z1] = keys[k + 1];
    const u = interpolate(t, [t0, t1], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.inOut(Easing.cubic) });
    return { lon: a0 + (a1 - a0) * u, lat: b0 + (b1 - b0) * u, z: z0 + (z1 - z0) * u };
  })();
  const proj = geoOrthographic().scale(R * cam.z).translate([CX, CY]).rotate([-cam.lon, -cam.lat]).clipAngle(90).precision(0.3);
  const path = geoPath(proj);
  const visible = (pt: [number, number]) => geoDistance(pt, [((cam.lon % 360) + 540) % 360 - 180, cam.lat]) < Math.PI / 2 - 0.05;

  // когда гаснет каждая группа
  const soldAt: Record<Group, number> = { pacific: c.united1, germany: c.lufthansa, london: c.united2, atlantic: c.atlantic, shuttle: c.shuttle, rest: c.dec + 0.7 };
  const state = (g: Group, k: number) => {
    const at = soldAt[g] + (k % 4) * 0.08;
    const flash = ease(t, at, at + 0.15) * (1 - ease(t, at + 0.15, at + 0.5));
    const fade = ease(t, at + 0.2, at + 1.6);
    return { flash, fade, alive: t < at };
  };
  const draw = (k: number) => ease(t, 0.15 + k * 0.05, 1.4 + k * 0.05, 0, 1, Easing.out(Easing.cubic));
  const left = ROUTES.filter(([, , g], k) => state(g, k).alive).length;

  const year = t < c.y85 ? null : t < c.y90 ? "1985" : t < c.y91 ? "1990" : t < c.dec ? "1991" : "DEC 4, 1991";
  const deal = t >= c.dec ? "PAN AM STOPS FLYING" : t >= c.delta ? "ATLANTIC + SHUTTLE → DELTA" : t >= c.then ? "LONDON HEATHROW → UNITED" : t >= c.germany ? "INSIDE GERMANY → LUFTHANSA"
    : t >= c.united1 - 0.3 && t < c.y90 ? "PACIFIC NETWORK → UNITED" : t >= c.cash ? "PAN AM NEEDS CASH" : null;
  const dealKey = deal ?? "";
  const dealAt = ({ "PAN AM NEEDS CASH": c.cash, "PACIFIC NETWORK → UNITED": c.united1 - 0.3, "INSIDE GERMANY → LUFTHANSA": c.germany, "LONDON HEATHROW → UNITED": c.then,
    "ATLANTIC + SHUTTLE → DELTA": c.delta, "PAN AM STOPS FLYING": c.dec } as Record<string, number>)[dealKey] ?? 0;
  const dealPop = pop(t, dealAt, fps);
  const yearAt = t < c.y90 ? c.y85 : t < c.y91 ? c.y90 : t < c.dec ? c.y91 : c.dec;
  const globeDim = 1 - 0.75 * ease(t, c.dec + 1.6, c.dec + 2.4);
  const cities: [string, [number, number], number][] = [["TOKYO", AP.NRT, c.japan], ["BEIJING", AP.PEK, c.china], ["SYDNEY", AP.SYD, c.australia], ["HONG KONG", AP.HKG, c.hk]];
  const stars = Array.from({ length: 70 }, (_, k) => [(k * 397) % 1080, (k * 733) % 1920, ((k * 13) % 10) / 10]);

  return (
    <AbsoluteFill style={{ background: `radial-gradient(circle at 50% 44%, #0E2240 0%, ${C.bg} 62%)`, color: C.fg, overflow: "hidden" }}>
      <Sound p={p} music={0.12} />
      <svg width={1080} height={1920} style={{ position: "absolute" }}>
        {stars.map(([x, y, o], k) => <circle key={k} cx={x} cy={y} r={1.6} fill="#fff" opacity={0.15 + 0.35 * o} />)}
      </svg>
      <svg width={1080} height={1920} style={{ position: "absolute", opacity: globeDim }}>
        <defs>
          <radialGradient id="ocean" cx="40%" cy="35%"><stop offset="0%" stopColor="#13304F" /><stop offset="100%" stopColor={C.ocean} /></radialGradient>
          <filter id="glow"><feGaussianBlur stdDeviation="5" result="b" /><feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge></filter>
        </defs>
        <circle cx={CX} cy={CY} r={R * cam.z} fill="url(#ocean)" />
        <path d={path(graticule) ?? ""} fill="none" stroke="#24476F" strokeWidth={1} opacity={0.5} />
        <path d={path(land as any) ?? ""} fill={C.land} stroke={C.coast} strokeWidth={1.2} />
        <circle cx={CX} cy={CY} r={R * cam.z} fill="none" stroke="#5CC8FF" strokeOpacity={0.35} strokeWidth={3} />
        <g filter="url(#glow)">
          {ROUTES.map(([a, b, g], k) => {
            const st = state(g, k); if (st.fade >= 1) return null;
            const d = draw(k); const ip = geoInterpolate(AP[a], AP[b]); const n = 40;
            const coords = Array.from({ length: Math.max(2, Math.round(n * d) + 1) }, (_, i) => ip(Math.min(d, i / n)));
            const color = st.flash > 0.01 ? "#FFFFFF" : t >= soldAt[g] ? C.sold : C.route;
            return <path key={k} d={path({ type: "LineString", coordinates: coords } as any) ?? ""} fill="none" stroke={color}
              strokeWidth={(g === "shuttle" ? 7 : 4.5) + st.flash * 5} strokeLinecap="round" opacity={1 - st.fade} />;
          })}
        </g>
        {Object.entries(AP).map(([code, pt]) => {
          if (!visible(pt)) return null; const xy = proj(pt); if (!xy) return null;
          const live = ROUTES.some(([a, b, g], k) => (a === code || b === code) && state(g, k).fade < 1);
          return <circle key={code} cx={xy[0]} cy={xy[1]} r={live ? 7 : 4} fill={live ? "#fff" : "#4A6A8F"} />;
        })}
        {cities.map(([label, pt, at], k) => {
          if (t < at || t > c.gone + 0.8 || !visible(pt)) return null; const xy = proj(pt); if (!xy) return null;
          const s = pop(t, at, fps); const out = ease(t, c.gone, c.gone + 0.6);
          return <g key={k} opacity={s * (1 - out)} transform={`translate(${xy[0]} ${xy[1] - 30 * s})`}>
            <rect x={-label.length * 13 - 18} y={-58} width={label.length * 26 + 36} height={52} rx={26} fill={C.sold} />
            <text x={0} y={-22} textAnchor="middle" fill="#fff" fontFamily={inter.fontFamily} fontWeight={800} fontSize={30}>{label}</text>
          </g>;
        })}
      </svg>
      {/* финал: фото последних лет */}
      {t >= c.dec + 1.6 && t < c.end && <div style={{ position: "absolute", left: 90, right: 90, top: 560, opacity: ease(t, c.dec + 1.6, c.dec + 2.4) }}>
        <div style={{ border: "10px solid #fff", boxShadow: "0 40px 90px rgba(0,0,0,.7)", transform: `rotate(-2deg) scale(${1 + 0.02 * (t - c.dec)})` }}>
          <Img src={staticFile("b747_1990.jpg")} style={{ width: "100%", display: "block", filter: "grayscale(0.85) brightness(0.8)" }} />
        </div>
        <div style={{ marginTop: 26, fontFamily: mono.fontFamily, fontSize: 21, color: C.dim }}>Pan Am Boeing 747, 1990 · Sunil Gupta / Wikimedia Commons, GFDL 1.2</div>
      </div>}
      {/* шапка */}
      <div style={{ position: "absolute", left: 70, top: 160, fontFamily: mono.fontFamily, fontWeight: 600, fontSize: 28, letterSpacing: 5, color: C.route }}>PAN AM · THE NETWORK</div>
      <div style={{ position: "absolute", right: 150, top: 160, textAlign: "right", fontFamily: mono.fontFamily, fontSize: 22, color: C.dim, letterSpacing: 2 }}>
        ROUTES ON THIS MAP<div style={{ fontFamily: bebas.fontFamily, fontSize: 84, color: left ? C.fg : C.sold, letterSpacing: 2, lineHeight: 1 }}>{left}</div>
      </div>
      {year && <div key={year} style={{ position: "absolute", left: 66, top: 200, fontFamily: bebas.fontFamily, fontSize: year.length > 4 ? 120 : 170, lineHeight: 1, color: C.fg,
        transform: `translateY(${(1 - pop(t, yearAt, fps)) * 40}px)`, opacity: pop(t, yearAt, fps) }}>{year}</div>}
      {deal && <div style={{ position: "absolute", left: 70, top: 380, fontFamily: inter.fontFamily, fontWeight: 800, fontSize: 44, color: dealKey.includes("→") || dealKey.includes("STOPS") ? C.gold : C.fg,
        transform: `translateX(${(1 - dealPop) * -60}px)`, opacity: dealPop }}>{deal}</div>}
      {t < c.dec + 1.6 && <Credit text="Schematic: selected Pan Am routes for illustration, not a complete network map." color={C.dim} font={mono.fontFamily} show={ease(t, 0.5, 1.2)} top={1420} />}
      <Captions words={W} until={c.end} st={{ top: 1325, font: inter.fontFamily, size: 60, weight: 800, color: C.fg, dim: C.dim, active: C.route, upper: false, maxWords: 3,
        shadow: "0 4px 16px rgba(0,0,0,.9)" }} />
      <EndCard at={c.end} title="What Happened to Pan Am? It Sold Its Routes to Survive" bg={C.bg} fg={C.fg} accent={C.route} font={inter.fontFamily} mono={mono.fontFamily} />
    </AbsoluteFill>
  );
};
