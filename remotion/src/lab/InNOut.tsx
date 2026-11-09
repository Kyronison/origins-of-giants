import React from "react";
import { AbsoluteFill, Img, staticFile } from "remotion";
import { loadFont as loadArchivo } from "@remotion/google-fonts/ArchivoBlack";
import { loadFont as loadInter } from "@remotion/google-fonts/Inter";
import { loadFont as loadMono } from "@remotion/google-fonts/SpaceMono";
import { Captions, Credit, EndCard, LabProps, Sound, cue, ease, pop, useT } from "./common";

/** Формат 4 «Против»: два бренда на одном экране, 100 ресторанов каждого; кто владелец — видно по цвету; потом выручка точки столбиками. */
const archivo = loadArchivo("normal", { weights: ["400"], subsets: ["latin"] });
const inter = loadInter("normal", { weights: ["600", "800"], subsets: ["latin"] });
const mono = loadMono("normal", { weights: ["400", "700"], subsets: ["latin"] });
const C = { bg: "#F6F2EA", ink: "#151515", red: "#D6202A", gold: "#E3A21A", grey: "#C9C2B6", dim: "rgba(21,21,21,.5)" };
const A = archivo.fontFamily, I = inter.fontFamily, M = mono.fontFamily;

const Store: React.FC<{ fill: string; outline?: boolean }> = ({ fill, outline }) => (
  <svg width={36} height={36} viewBox="0 0 36 36">
    <path d="M3 13 L7 4 H29 L33 13 Z" fill={fill} />
    <rect x={5} y={15} width={26} height={18} fill={outline ? "none" : fill} stroke={fill} strokeWidth={3} />
    <rect x={14} y={22} width={8} height={11} fill={outline ? fill : C.bg} />
  </svg>
);

const Grid: React.FC<{ x: number; color: (k: number) => string; outline: (k: number) => boolean; born: (k: number) => number; t: number }> = ({ x, color, outline, born, t }) => (
  <div style={{ position: "absolute", left: x, top: 480, width: 440, display: "grid", gridTemplateColumns: "repeat(10, 36px)", gap: 8 }}>
    {Array.from({ length: 100 }, (_, k) => { const s = Math.min(1, Math.max(0, (t - born(k)) / 0.2));
      return <div key={k} style={{ transform: `scale(${s})` }}><Store fill={color(k)} outline={outline(k)} /></div>; })}
  </div>
);

export const InNOut: React.FC<LabProps> = (p) => {
  const { t, fps } = useT(); const W = p.words;
  const c = {
    two: cue(W, "Two burger"), question: cue(W, "One question"), who: cue(W, "Who actually"), mcd: cue(W, "At McDonald's"), ninety: cue(W, "ninety-five"),
    fr: cue(W, "franchisees"), innout: cue(W, "At In-N-Out"), zero: cue(W, "Zero"), every: cue(W, "Every single"), company: cue(W, "company", 15),
    estimate: cue(W, "And by one"), six: cue(W, "six million"), avg2: cue(W, "An average American"), four: cue(W, "about four"), family: cue(W, "The family could"),
    franchises: cue(W, "sold franchises"), faster: cue(W, "much faster"), chose: cue(W, "It chose"), keep: cue(W, "keep everything"), end: cue(W, "Watch the full"),
  };
  const gridsA = ease(t, c.two, c.two + 0.4) * (1 - ease(t, c.estimate, c.estimate + 0.5));
  const mcdFr = (k: number) => t >= c.ninety + 0.2 + (k / 95) * (c.fr - c.ninety) && k < 95;
  const inCo = t >= c.every;
  const barsA = ease(t, c.estimate + 0.3, c.estimate + 0.8) * (1 - ease(t, c.family - 0.4, c.family));
  const finalA = ease(t, c.family - 0.3, c.family + 0.3);
  const head = t < c.estimate ? "WHO OWNS THE RESTAURANT?" : t < c.family ? "AVERAGE SALES PER U.S. RESTAURANT" : "";
  const headW = head.split(" "); const headAt = t < c.estimate ? c.who : c.estimate;
  const bar = (v: number, at: number) => ease(t, at, at + 1.1) * v;

  return (
    <AbsoluteFill style={{ background: C.bg, color: C.ink, overflow: "hidden" }}>
      <Sound p={p} music={0.1} />
      {t < c.family - 0.3 && <div style={{ position: "absolute", left: 70, top: 158, fontFamily: M, fontWeight: 700, fontSize: 26, letterSpacing: 3, color: C.red }}>
        {t < c.question ? "TWO BURGER CHAINS" : "ONE QUESTION"}
      </div>}
      {head && <div style={{ position: "absolute", left: 66, right: 140, top: 200, fontFamily: A, fontSize: t < c.estimate ? 88 : 64, lineHeight: 1.02 }}>
        {headW.map((w, k) => { const s = pop(t, headAt + k * 0.12, fps); return <span key={k} style={{ display: "inline-block", marginRight: 22, opacity: s, transform: `translateY(${(1 - s) * 30}px)` }}>{w}</span>; })}
      </div>}
      {/* сетки ресторанов */}
      {gridsA > 0 && <AbsoluteFill style={{ opacity: gridsA }}>
        {[["McDONALD'S", 70, c.mcd], ["IN-N-OUT", 570, c.innout]].map(([label, x, at], k) => (
          <div key={k} style={{ position: "absolute", left: x as number, top: 410, fontFamily: A, fontSize: 44, color: k ? C.red : C.ink, opacity: 0.35 + 0.65 * ease(t, (at as number) - 0.2, (at as number) + 0.3) }}>{label as string}</div>))}
        <Grid x={70} t={t} born={(k) => c.two + 0.2 + k * 0.012} color={(k) => (mcdFr(k) ? C.gold : C.ink)} outline={(k) => mcdFr(k)} />
        <Grid x={570} t={t} born={(k) => c.two + 0.4 + k * 0.012} color={(k) => (inCo && t >= c.every + (k / 100) * (c.company - c.every) ? C.red : C.ink)} outline={() => false} />
        <div style={{ position: "absolute", left: 70, top: 935, fontFamily: A, fontSize: 120, color: C.gold, opacity: ease(t, c.ninety, c.ninety + 0.3) }}>
          {Math.round(ease(t, c.ninety, c.fr, 0, 95, (x) => x))}<span style={{ fontSize: 60 }}>/100</span></div>
        <div style={{ position: "absolute", left: 570, top: 935, fontFamily: A, fontSize: 120, color: C.red, transform: `scale(${pop(t, c.zero, fps)})`, transformOrigin: "0 50%" }}>0<span style={{ fontSize: 60 }}>/100</span></div>
        <div style={{ position: "absolute", left: 70, right: 140, top: 1090, display: "flex", gap: 40, fontFamily: M, fontSize: 25, opacity: ease(t, c.ninety, c.ninety + 0.4) }}>
          <span style={{ display: "flex", alignItems: "center", gap: 10 }}><Store fill={C.gold} outline /> FRANCHISEE</span>
          <span style={{ display: "flex", alignItems: "center", gap: 10 }}><Store fill={C.ink} /> COMPANY-OWNED</span>
        </div>
      </AbsoluteFill>}
      {/* выручка точки */}
      {barsA > 0 && <AbsoluteFill style={{ opacity: barsA }}>
        {[["IN-N-OUT", 6.0, "$6.0M", C.red, c.six, 600], ["McDONALD'S (U.S.)", 4.1, "$4.1M", C.ink, c.avg2 + 0.6, 150]].map(([label, v, txt, col, at, x], k) => {
          const h = bar(v as number, (at as number) - 0.3) / 6 * 640;
          return <div key={k} style={{ position: "absolute", left: x as number, width: 330, top: 1150 - h, height: h, background: col as string }}>
            <div style={{ position: "absolute", top: -96, left: 0, fontFamily: A, fontSize: 76, color: col as string, opacity: h > 20 ? 1 : 0 }}>{txt as string}</div>
            <div style={{ position: "absolute", bottom: -46, left: 0, fontFamily: M, fontWeight: 700, fontSize: 24, color: C.ink }}>{label as string}</div>
          </div>;
        })}
        <Credit text="QSR estimates for 2025: average annual sales per restaurant. In-N-Out: 0 franchised; McDonald's: ~95% of restaurants franchised (end of 2025)." color={C.dim} font={M} show={1} top={1405} />
      </AbsoluteFill>}
      {/* решение семьи */}
      {finalA > 0 && t < c.end && <AbsoluteFill style={{ opacity: finalA }}>
        <Img src={staticFile("innout.jpg")} style={{ position: "absolute", left: 70, top: 200, width: 940, height: 600, objectFit: "cover", filter: "grayscale(1) contrast(1.05)",
          transform: `scale(${1 + 0.03 * (t - c.family)})` }} />
        <div style={{ position: "absolute", left: 70, top: 818, fontFamily: M, fontSize: 21, color: C.dim }}>In-N-Out, early years · photo via eatthis.com</div>
        {[["SELL FRANCHISES?", c.franchises], ["GROW FASTER?", c.faster]].map(([q, at], k) => {
          const s = pop(t, (at as number) - 0.2, fps); const no = pop(t, c.chose + k * 0.25, fps, { damping: 9, stiffness: 260, mass: 0.6 });
          return <div key={k} style={{ position: "absolute", left: 70, top: 880 + k * 120, opacity: s, display: "flex", alignItems: "center", gap: 30 }}>
            <span style={{ fontFamily: A, fontSize: 70 }}>{q as string}</span>
            <span style={{ fontFamily: A, fontSize: 64, color: C.red, border: `7px solid ${C.red}`, padding: "0 18px", transform: `rotate(-8deg) scale(${2 - no})`, opacity: no }}>NO</span>
          </div>;
        })}
        {t >= c.keep && <div style={{ position: "absolute", left: 70, top: 1120, fontFamily: A, fontSize: 84, color: C.red, transform: `scale(${pop(t, c.keep, fps)})`, transformOrigin: "0 50%" }}>KEPT EVERYTHING.</div>}
      </AbsoluteFill>}
      <Captions words={W} until={c.end} st={{ top: 1265, font: I, size: 56, weight: 800, color: C.ink, dim: "rgba(21,21,21,.4)", active: "#fff", activeBg: C.red, maxWords: 3 }} />
      <EndCard at={c.end} title="In-N-Out Sells $6M Per Store. No Franchisee Gets a Cut" bg={C.bg} fg={C.ink} accent={C.red} font={A} mono={M} />
    </AbsoluteFill>
  );
};
