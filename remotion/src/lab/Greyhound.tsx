import React from "react";
import { AbsoluteFill, Img, staticFile } from "remotion";
import { loadFont as loadInter } from "@remotion/google-fonts/InterTight";
import { loadFont as loadMono } from "@remotion/google-fonts/JetBrainsMono";
import { Captions, Credit, EndCard, LabProps, Sound, cue, ease, pop, useT } from "./common";

/** Формат 1 «Квадраты денег»: кинетическая инфографика, 1 квадрат = $1 млн. 78 синих (автобусная компания) против 540 янтарных (вокзалы). */
const inter = loadInter("normal", { weights: ["500", "700", "800"], subsets: ["latin"] });
const mono = loadMono("normal", { weights: ["500", "700"], subsets: ["latin"] });
const C = { bg: "#08121F", bg2: "#0F2238", blue: "#3D7BFF", amber: "#FFB020", red: "#FF4B3E", fg: "#F4F7FB", dim: "rgba(244,247,251,.5)" };
const F = inter.fontFamily, M = mono.fontFamily;

const COLS = 24, CELL = 28, PITCH = 33, GX = (1080 - (COLS * PITCH - (PITCH - CELL))) / 2, GY = 430;

const Counter: React.FC<{ value: number; color: string; size?: number }> = ({ value, color, size = 170 }) =>
  <span style={{ fontFamily: F, fontWeight: 800, fontSize: size, color, letterSpacing: -4, fontVariantNumeric: "tabular-nums" }}>${Math.round(value)}M</span>;

const Building: React.FC<{ size: number; color: string }> = ({ size, color }) => (
  <svg width={size} height={size} viewBox="0 0 100 100">
    <rect x={8} y={44} width={84} height={46} rx={3} fill="none" stroke={color} strokeWidth={6} />
    <rect x={56} y={12} width={18} height={34} fill={color} />
    <path d="M18 58H48M18 72H48" stroke={color} strokeWidth={5} />
    <rect x={60} y={62} width={22} height={28} fill={color} />
  </svg>
);

export const Greyhound: React.FC<LabProps> = (p) => {
  const { t, fps } = useT(); const W = p.words;
  const c = {
    seventy: cue(W, "seventy-eight"), dollars: cue(W, "dollars", 0, true), buses: cue(W, "buses"), brand: cue(W, "brand"), routes: cue(W, "routes"),
    all: cue(W, "All of it"), but: cue(W, "But one thing"), stations: cue(W, "The stations"), owner: cue(W, "The owner kept"), sold: cue(W, "sold them off"),
    thirty: cue(W, "Thirty"), brought: cue(W, "brought in"), m400: cue(W, "million dollars", 18, true), last: cue(W, "The last batch"), added: cue(W, "added another"),
    m140: cue(W, "forty million", 20, true), thats: cue(W, "That's roughly"), almost: cue(W, "Almost"), seven: cue(W, "seven times"), what: cue(W, "what the bus"),
    worth: cue(W, "The stations were"), end: cue(W, "Watch the full"),
  };
  // Сцена A: фото автобуса и счётчик $78M
  const aOut = ease(t, c.all, c.all + 0.6);
  const n78 = ease(t, c.seventy, c.dollars, 0, 78);
  // Сцена B: открытка вокзала и штамп
  const card = pop(t, c.stations - 0.35, fps, { damping: 11, stiffness: 120, mass: 0.9 });
  const stamp = pop(t, c.stations + 0.25, fps, { damping: 9, stiffness: 260, mass: 0.6 });
  const cardOut = ease(t, c.owner + 0.9, c.owner + 1.5);
  // Сцена C: 30 вокзалов один за другим
  const bIn = (k: number) => pop(t, c.sold + k * ((c.thirty - c.sold) / 30), fps, { damping: 12, stiffness: 240, mass: 0.5 });
  const bOut = ease(t, c.brought - 0.3, c.brought + 0.3);
  // Сцена D: янтарная сетка
  const filled = t < c.last ? ease(t, c.brought, c.m400, 0, 400, (x) => x) : 400 + ease(t, c.added, c.m140, 0, 140, (x) => x);
  const amberVal = t < c.brought ? 0 : t < c.added ? filled : filled;
  const blueCells = ease(t, c.almost, c.seven + 0.4, 0, 78, (x) => x);
  const gridOn = t >= c.brought - 0.2 && t < c.end;
  const gridDim = ease(t, c.worth - 0.2, c.worth + 0.3, 1, 0.08);
  const head = t < c.thirty ? null : t < c.thats ? "SOLD OFF, ONE BY ONE" : t < c.almost ? "THE BUILDINGS" : t < c.worth ? "BUILDINGS vs. BUS COMPANY" : null;
  const ratio = pop(t, c.seven, fps, { damping: 9, stiffness: 200, mass: 0.7 });
  const finale = ease(t, c.worth - 0.1, c.worth + 0.4);

  return (
    <AbsoluteFill style={{ background: `radial-gradient(ellipse at 50% 30%, ${C.bg2} 0%, ${C.bg} 70%)`, color: C.fg }}>
      <Sound p={p} />
      {/* A — автобус и $78M */}
      {t < c.all + 0.7 && <AbsoluteFill style={{ opacity: 1 - aOut }}>
        <div style={{ position: "absolute", left: 70, right: 70, top: 220, height: 560, overflow: "hidden", borderRadius: 24 }}>
          <Img src={staticFile("bus.jpg")} style={{ width: "100%", height: "100%", objectFit: "cover", transform: `scale(${1.05 + 0.05 * t / 6})` }} />
          <div style={{ position: "absolute", inset: 0, background: "linear-gradient(180deg, rgba(8,18,31,0) 40%, rgba(8,18,31,.85) 100%)" }} />
        </div>
        <div style={{ position: "absolute", left: 70, top: 168, fontFamily: M, fontSize: 28, letterSpacing: 4, color: C.blue }}>GREYHOUND · SOLD IN 2021</div>
        <div style={{ position: "absolute", left: 0, right: 0, top: 640, textAlign: "center", opacity: ease(t, c.seventy - 0.15, c.seventy + 0.1), transform: `scale(${0.9 + 0.1 * pop(t, c.seventy, fps)})` }}>
          <Counter value={n78} color={C.fg} size={210} />
        </div>
        <div style={{ position: "absolute", left: 0, right: 0, top: 900, display: "flex", justifyContent: "center", gap: 22 }}>
          {[["BUSES", c.buses], ["BRAND", c.brand], ["ROUTES", c.routes]].map(([label, at], k) => {
            const s = pop(t, at as number, fps);
            return <div key={k} style={{ fontFamily: M, fontWeight: 700, fontSize: 40, padding: "14px 28px", border: `3px solid ${C.blue}`, borderRadius: 60, color: C.fg,
              background: "rgba(61,123,255,.18)", transform: `scale(${s}) translateY(${(1 - s) * 30}px)`, opacity: s }}>{label as string}</div>;
          })}
        </div>
        <Credit text="Greyhound bus, 2017 · Tdorante10 / Wikimedia Commons, CC BY-SA 4.0" color={C.dim} font={M} show={1} />
      </AbsoluteFill>}
      {/* A→B — синий блок 78 квадратов */}
      {t >= c.all && t < c.stations && (() => {
        const shrink = ease(t, c.but, c.but + 0.8);
        return <div style={{ position: "absolute", left: 540, top: 600, transform: `translate(-50%,-50%) scale(${1 - 0.3 * shrink}) translateY(${-330 * shrink}px)`, opacity: 1 - ease(t, c.stations - 0.5, c.stations - 0.1) }}>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(13, 48px)", gap: 8 }}>
            {Array.from({ length: 78 }, (_, k) => { const s = pop(t, c.all + k * 0.012, fps, { damping: 13, stiffness: 300, mass: 0.4 });
              return <div key={k} style={{ width: 48, height: 48, borderRadius: 6, background: C.blue, transform: `scale(${s})` }} />; })}
          </div>
          <div style={{ marginTop: 26, textAlign: "center", fontFamily: M, fontSize: 30, color: C.dim }}>1 SQUARE = $1 MILLION</div>
        </div>;
      })()}
      {/* B — открытка вокзала, штамп */}
      {t >= c.stations - 0.4 && t < c.owner + 1.6 && <div style={{ position: "absolute", left: 90, top: 330, width: 900,
        transform: `translateY(${(1 - card) * -700 - cardOut * 900}px) rotate(${-3 + card * 1.5}deg)`, opacity: 1 - cardOut }}>
        <div style={{ background: "#fff", padding: 18, boxShadow: "0 40px 90px rgba(0,0,0,.6)" }}>
          <Img src={staticFile("terminal_chi.jpg")} style={{ width: "100%", display: "block" }} />
        </div>
        <div style={{ position: "absolute", left: 120, top: 210, transform: `rotate(-12deg) scale(${2.2 - 1.2 * stamp})`, opacity: stamp, border: `10px solid ${C.red}`, color: C.red,
          fontFamily: F, fontWeight: 800, fontSize: 74, padding: "6px 30px", letterSpacing: 2, whiteSpace: "nowrap", background: "rgba(255,255,255,.08)" }}>NOT IN THE DEAL</div>
        <div style={{ marginTop: 30, fontFamily: M, fontSize: 21, color: C.dim }}>Greyhound terminal, Chicago · 1953 postcard · public domain</div>
      </div>}
      {/* C — 30 вокзалов */}
      {t >= c.sold && t < c.brought + 0.4 && <div style={{ position: "absolute", left: 0, right: 0, top: 470, display: "flex", justifyContent: "center", opacity: 1 - bOut }}>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(6, 128px)", gap: 18 }}>
          {Array.from({ length: 30 }, (_, k) => { const s = bIn(k);
            return <div key={k} style={{ transform: `scale(${s}) translateY(${(1 - s) * -40}px)`, opacity: s }}><Building size={128} color={C.amber} /></div>; })}
        </div>
      </div>}
      {/* D–F — янтарная сетка, затем синие 78 */}
      {gridOn && <div style={{ position: "absolute", left: GX, top: GY, opacity: gridDim }}>
        {Array.from({ length: 540 }, (_, k) => {
          if (k >= filled) return null;
          const x = (k % COLS) * PITCH, y = Math.floor(k / COLS) * PITCH;
          const born = k < 400 ? c.brought + (k / 400) * (c.m400 - c.brought) : c.added + ((k - 400) / 140) * (c.m140 - c.added);
          const s = Math.min(1, Math.max(0, (t - born) / 0.18));
          const blue = k < blueCells;
          return <div key={k} style={{ position: "absolute", left: x, top: y, width: CELL, height: CELL, borderRadius: 4,
            background: blue ? C.blue : C.amber, transform: `scale(${s})`, boxShadow: blue ? `0 0 18px ${C.blue}` : undefined }} />;
        })}
      </div>}
      {/* Заголовки и счётчики */}
      {head && <div style={{ position: "absolute", left: 70, top: 168, fontFamily: M, fontSize: 28, letterSpacing: 4, color: C.amber }}>{head}</div>}
      {t >= c.brought - 0.2 && t < c.worth && <div style={{ position: "absolute", left: 66, top: 214, lineHeight: 1 }}>
        <Counter value={amberVal} color={C.amber} size={150} />
        {t >= c.almost && <span style={{ marginLeft: 26, fontFamily: F, fontWeight: 800, fontSize: 70, color: C.blue, opacity: ease(t, c.almost, c.almost + 0.4) }}>vs $78M</span>}
      </div>}
      {t >= c.seven && t < c.worth && <div style={{ position: "absolute", right: 150, top: 760, transform: `scale(${ratio}) rotate(-6deg)`, fontFamily: F, fontWeight: 800,
        fontSize: 220, color: C.fg, textShadow: "0 20px 60px rgba(0,0,0,.7)" }}>×6.9</div>}
      {t >= c.almost && t < c.worth && <div style={{ position: "absolute", left: GX, top: GY - 50, fontFamily: M, fontSize: 26, color: C.blue, opacity: ease(t, c.almost + 0.3, c.almost + 0.8) }}>■ BUS COMPANY</div>}
      {t >= c.brought && t < c.worth && <Credit text="$78M: operating company, debt- and cash-free value (2021). $400M: ~30 property deals before the sale; $140M: final sale, net (2022). Measured differently — see the full video." color={C.dim} font={M} show={ease(t, c.brought, c.brought + 0.5)} top={1405} />}
      {/* G — вывод */}
      {t >= c.worth - 0.1 && <div style={{ position: "absolute", left: 80, right: 120, top: 560, opacity: finale, transform: `translateY(${(1 - finale) * 40}px)` }}>
        <div style={{ fontFamily: F, fontWeight: 800, fontSize: 112, lineHeight: 1.02, letterSpacing: -3 }}>
          The <span style={{ color: C.amber }}>stations</span> were worth more than the <span style={{ color: C.blue }}>buses.</span>
        </div>
      </div>}
      <Captions words={W} until={c.end} st={{ top: 1250, font: F, size: 62, weight: 800, color: C.fg, dim: C.dim, active: C.amber, maxWords: 3,
        shadow: "0 4px 18px rgba(0,0,0,.8)" }} />
      <EndCard at={c.end} title="What Happened to Greyhound? The Stations Were Worth More" bg={C.bg} fg={C.fg} accent={C.amber} font={F} mono={M} />
    </AbsoluteFill>
  );
};
