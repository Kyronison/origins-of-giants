import React from "react";
import { AbsoluteFill, Img, staticFile } from "remotion";
import { loadFont as loadInter } from "@remotion/google-fonts/InterTight";
import { loadFont as loadMono } from "@remotion/google-fonts/JetBrainsMono";
import { Captions, Credit, EndCard, MotionProps, Sound, cue, ease, pop, sceneAt, useT } from "./common";

/** Шаблон «Квадраты денег» (образец Greyhound 06.10, выбор владельца): 1 квадрат = единица суммы.
 *  Сцены идут по якорям-фразам диктора: photo (фото + счётчик + чипы) → block (синий блок A) → stamp (фото со штампом)
 *  → fill (янтарная сетка B по шагам) → compare (первые A клеток сетки синеют, кратность) → statement (вывод). */
const inter = loadInter("normal", { weights: ["500", "700", "800"], subsets: ["latin"] });
const mono = loadMono("normal", { weights: ["500", "700"], subsets: ["latin"] });
const C = { bg: "#08121F", bg2: "#0F2238", a: "#3D7BFF", b: "#FFB020", red: "#FF4B3E", fg: "#F4F7FB", dim: "rgba(244,247,251,.5)" };
const F = inter.fontFamily, M = mono.fontFamily;

type Money = { value: number; prefix?: string; suffix?: string; decimals?: number };
type Scene =
  | { type: "photo"; cue: string; photo: string; credit: string; counter?: Money & { cue: string; endCue: string }; chips?: { text: string; cue: string }[]; kicker?: string }
  | { type: "block"; cue: string; count: number; label?: string }
  | { type: "stamp"; cue: string; photo: string; credit: string; text: string; stampCue: string }
  | { type: "fill"; cue: string; head: string; steps: (Money & { count: number; cue: string; endCue: string })[] }
  | { type: "compare"; cue: string; count: number; label: string; versus: string; ratio?: { text: string; cue: string }; head?: string }
  | { type: "statement"; cue: string; text: string; accentB?: string[]; accentA?: string[] };
export type BlocksData = { kicker: string; unitLabel: string; scenes: Scene[]; footnote?: { text: string; cue: string } };

const fmt = (m: Money, v: number) => (m.suffix ?? "").trim().toUpperCase() === "M" && v >= 1000
  ? `${m.prefix ?? ""}${(v / 1000).toFixed(v >= 10000 ? 0 : 1)}B` : `${m.prefix ?? ""}${v.toFixed(m.decimals ?? (v < 100 && v % 1 ? 1 : 0))}${m.suffix ?? ""}`;
const Big: React.FC<{ text: string; color: string; size?: number }> = ({ text, color, size = 170 }) =>
  <span style={{ fontFamily: F, fontWeight: 800, fontSize: size, color, letterSpacing: -4, fontVariantNumeric: "tabular-nums" }}>{text}</span>;

export const Blocks: React.FC<MotionProps<BlocksData>> = (p) => {
  const { t, fps } = useT(); const W = p.words; const D = p.data;
  const end = cue(W, "Watch the full");
  const starts: number[] = []; D.scenes.forEach((s, i) => starts.push(cue(W, s.cue, i ? starts[i - 1] + 0.01 : 0)));
  const k = sceneAt(starts, t); const sc = k >= 0 ? D.scenes[k] : D.scenes[0];
  const next = (i: number) => (i + 1 < starts.length ? starts[i + 1] : end);
  // сетка B: общая для fill / compare / statement
  const fillIdx = D.scenes.findIndex((s) => s.type === "fill");
  const fill = fillIdx >= 0 ? (D.scenes[fillIdx] as Extract<Scene, { type: "fill" }>) : null;
  const stepT: number[][] = []; if (fill) fill.steps.forEach((s, i) => { const a = cue(W, s.cue, i ? stepT[i - 1][1] - 0.01 : starts[fillIdx]); stepT.push([a, cue(W, s.endCue, a, true)]); });
  const total = fill ? fill.steps[fill.steps.length - 1].count : 0;
  const cols = total > 300 ? 24 : total > 120 ? 18 : 12;
  const pitch = Math.min(Math.floor(900 / cols), Math.floor(760 / Math.ceil(total / cols || 1)));
  const cell = Math.round(pitch * 0.85), gx = (1080 - cols * pitch) / 2, gy = 440;
  const filled = (() => {
    if (!fill || t < stepT[0][0]) return 0; let prev = 0;
    for (let i = 0; i < fill.steps.length; i++) {
      const [a, b] = stepT[i]; if (t < a) return prev;
      if (t < b) return prev + (fill.steps[i].count - prev) * ease(t, a, b, 0, 1, (x) => x);
      prev = fill.steps[i].count;
    }
    return prev;
  })();
  const bornOf = (n: number) => { if (!fill) return 0; let prev = 0;
    for (let i = 0; i < fill.steps.length; i++) { const c = fill.steps[i].count; if (n < c) { const [a, b] = stepT[i]; return a + ((n - prev) / Math.max(1, c - prev)) * (b - a); } prev = c; } return 0; };
  const money = (() => { if (!fill || t < stepT[0][0]) return null; let prevV = 0;
    for (let i = 0; i < fill.steps.length; i++) { const s = fill.steps[i]; const [a, b] = stepT[i];
      if (t < b || i === fill.steps.length - 1) return fmt(s, t < a ? prevV : prevV + (s.value - prevV) * ease(t, a, b, 0, 1, (x) => x)); prevV = s.value; } return null; })();
  const cmpIdx = D.scenes.findIndex((s) => s.type === "compare"); const cmp = cmpIdx >= 0 ? (D.scenes[cmpIdx] as Extract<Scene, { type: "compare" }>) : null;
  const cmpT = cmp ? starts[cmpIdx] : 1e9; const stIdx = D.scenes.findIndex((s) => s.type === "statement"); const stT = stIdx >= 0 ? starts[stIdx] : end;
  const blueCells = cmp ? ease(t, cmpT, cmpT + 1.4, 0, cmp.count, (x) => x) : 0;
  const gridOn = fill && t >= starts[fillIdx] - 0.2 && t < end;
  // сцены фото/штампа/блока после заполнения сетки идут поверх пустого фона: сетка уходит и возвращается к compare/statement (08.10)
  const isOver = (i: number) => i > fillIdx && fillIdx >= 0 && ["photo", "stamp", "block"].includes(D.scenes[i]?.type);
  const nextOver = k + 1 < starts.length && isOver(k + 1) ? starts[k + 1] : null;
  const gridVis = k < 0 ? 1 : isOver(k) ? 0
    : (k > 0 && isOver(k - 1) ? ease(t, starts[k], starts[k] + 0.35) : 1) * (nextOver != null ? 1 - ease(t, nextOver - 0.7, nextOver - 0.4) : 1);
  const head = k >= 0 && (sc.type === "fill" ? sc.head : sc.type === "compare" ? sc.head ?? "" : "");

  return (
    <AbsoluteFill style={{ background: `radial-gradient(ellipse at 50% 30%, ${C.bg2} 0%, ${C.bg} 70%)`, color: C.fg }}>
      <Sound p={p} />
      {gridOn && gridVis > 0.01 && <div style={{ position: "absolute", left: gx, top: gy, opacity: ease(t, stT - 0.2, stT + 0.3, 1, 0.08) * gridVis }}>
        {Array.from({ length: total }, (_, n) => {
          if (n >= filled) return t < stT ? <div key={n} style={{ position: "absolute", left: (n % cols) * pitch, top: Math.floor(n / cols) * pitch, width: cell, height: cell, borderRadius: 4,
            border: "2px solid rgba(255,176,32,.22)", opacity: ease(t, starts[fillIdx] + (n / total) * 0.6, starts[fillIdx] + (n / total) * 0.6 + 0.3) }} /> : null;
          const q = Math.min(1, Math.max(0, (t - bornOf(n)) / 0.18)); const blue = n < blueCells;
          return <div key={n} style={{ position: "absolute", left: (n % cols) * pitch, top: Math.floor(n / cols) * pitch, width: cell, height: cell, borderRadius: 4,
            background: blue ? C.a : C.b, transform: `scale(${q})`, boxShadow: blue ? `0 0 18px ${C.a}` : undefined }} />;
        })}
      </div>}
      {D.scenes.map((s, i) => {
        const a = starts[i], b = next(i); if (t < a - 0.5 || t > b + 0.8) return null;
        const out = ease(t, b, b + 0.6);
        if (s.type === "photo") {
          const c = s.counter; const cs = c ? cue(W, c.cue, a) : 0, ce = c ? cue(W, c.endCue, cs, true) : 0;
          return <AbsoluteFill key={i} style={{ opacity: 1 - out }}>
            <div style={{ position: "absolute", left: 70, right: 70, top: 220, height: 560, overflow: "hidden", borderRadius: 24 }}>
              <Img src={staticFile(s.photo)} style={{ width: "100%", height: "100%", objectFit: "cover", transform: `scale(${1.05 + 0.05 * (t - a) / 6})` }} />
              <div style={{ position: "absolute", inset: 0, background: "linear-gradient(180deg, rgba(8,18,31,0) 40%, rgba(8,18,31,.85) 100%)" }} />
            </div>
            <div style={{ position: "absolute", left: 70, top: 168, fontFamily: M, fontSize: 28, letterSpacing: 4, color: C.a }}>{s.kicker ?? D.kicker}</div>
            {c && <div style={{ position: "absolute", left: 0, right: 0, top: 640, textAlign: "center", opacity: ease(t, cs - 0.15, cs + 0.1), transform: `scale(${0.9 + 0.1 * pop(t, cs, fps)})` }}>
              <Big text={fmt(c, ease(t, cs, ce, 0, c.value))} color={C.fg} size={200} /></div>}
            <div style={{ position: "absolute", left: 60, right: 130, top: 900, display: "flex", justifyContent: "center", flexWrap: "wrap", gap: 18 }}>
              {(s.chips ?? []).map((ch, j) => { const at = cue(W, ch.cue, a); const q = pop(t, at, fps);
                return <div key={j} style={{ fontFamily: M, fontWeight: 700, fontSize: 38, padding: "12px 26px", border: `3px solid ${C.a}`, borderRadius: 60, background: "rgba(61,123,255,.18)",
                  transform: `scale(${q}) translateY(${(1 - q) * 30}px)`, opacity: q }}>{ch.text}</div>; })}
            </div>
            <Credit text={s.credit} color={C.dim} font={M} show={1} />
          </AbsoluteFill>;
        }
        if (s.type === "block") {
          const shrink = ease(t, b, b + 0.8); const colsA = s.count > 120 ? 16 : s.count > 40 ? 13 : Math.max(1, Math.min(8, s.count));
          const sz = Math.min(s.count <= 4 ? 220 : s.count <= 16 ? 96 : 56, Math.floor(820 / colsA) - 8);   // 08.10: 1–4 квадрата — крупно, а не точка на пустом экране
          return <div key={i} style={{ position: "absolute", left: 540, top: 640, transform: `translate(-50%,-50%) scale(${1 - 0.3 * shrink}) translateY(${-330 * shrink}px)`, opacity: 1 - ease(t, b + 0.4, b + 0.9) }}>
            <div style={{ display: "grid", gridTemplateColumns: `repeat(${colsA}, ${sz}px)`, gap: 8 }}>
              {Array.from({ length: s.count }, (_, j) => { const q = pop(t, a + j * Math.min(0.012, 0.9 / s.count), fps, { damping: 13, stiffness: 300, mass: 0.4 });
                return <div key={j} style={{ width: sz, height: sz, borderRadius: 6, background: C.a, transform: `scale(${q})` }} />; })}
            </div>
            <div style={{ marginTop: 26, textAlign: "center", fontFamily: M, fontSize: 30, color: C.dim }}>{s.label ?? D.unitLabel}</div>
          </div>;
        }
        if (s.type === "stamp") {
          const card = pop(t, a - 0.3, fps, { damping: 11, stiffness: 120, mass: 0.9 }); const st = pop(t, cue(W, s.stampCue, a) + 0.2, fps, { damping: 9, stiffness: 260, mass: 0.6 });
          return <div key={i} style={{ position: "absolute", left: 90, top: 330, width: 900, transform: `translateY(${(1 - card) * -700 - out * 900}px) rotate(${-3 + card * 1.5}deg)`, opacity: 1 - out }}>
            <div style={{ background: "#fff", padding: 18, boxShadow: "0 40px 90px rgba(0,0,0,.6)" }}><Img src={staticFile(s.photo)} style={{ width: "100%", maxHeight: 640, objectFit: "cover", display: "block" }} /></div>
            <div style={{ position: "absolute", left: 80, top: 200, transform: `rotate(-12deg) scale(${2.2 - 1.2 * st})`, opacity: st, border: `10px solid ${C.red}`, color: C.red,
              fontFamily: F, fontWeight: 800, fontSize: 74, padding: "6px 30px", whiteSpace: "nowrap", background: "rgba(255,255,255,.08)" }}>{s.text}</div>
            <div style={{ marginTop: 30, fontFamily: M, fontSize: 21, color: C.dim }}>{s.credit}</div>
          </div>;
        }
        if (s.type === "statement") {
          const f = ease(t, a - 0.1, a + 0.4);
          const words = s.text.split(" ");
          const hit = (w: string, list?: string[]) => (list ?? []).some((x) => w.toLowerCase().replace(/[^a-z0-9]/g, "") === x.toLowerCase().replace(/[^a-z0-9]/g, ""));
          return <div key={i} style={{ position: "absolute", left: 80, right: 120, top: 560, opacity: f * (1 - out), transform: `translateY(${(1 - f) * 40}px)`,
            fontFamily: F, fontWeight: 800, fontSize: s.text.length > 60 ? 88 : 112, lineHeight: 1.02, letterSpacing: -3 }}>
            {words.map((w, j) => <span key={j} style={{ color: hit(w, s.accentB) ? C.b : hit(w, s.accentA) ? C.a : C.fg }}>{w} </span>)}
          </div>;
        }
        return null;
      })}
      {head && <div style={{ position: "absolute", left: 70, top: 168, fontFamily: M, fontSize: 28, letterSpacing: 4, color: C.b }}>{head}</div>}
      {money && t < stT && gridVis > 0.01 && <div style={{ position: "absolute", left: 66, top: 214, lineHeight: 1, opacity: gridVis }}>
        <Big text={money} color={C.b} size={150} />
        {cmp && t >= cmpT && <span style={{ marginLeft: 26, fontFamily: F, fontWeight: 800, fontSize: 70, color: C.a, opacity: ease(t, cmpT, cmpT + 0.4) }}>{cmp.versus}</span>}
      </div>}
      {cmp && t >= cmpT && t < stT && gridVis > 0.5 && <div style={{ position: "absolute", left: gx, top: gy - 50, fontFamily: M, fontSize: 26, color: C.a, opacity: ease(t, cmpT + 0.3, cmpT + 0.8) }}>■ {cmp.label}</div>}
      {cmp?.ratio && t >= cue(W, cmp.ratio.cue, cmpT) && t < stT && gridVis > 0.5 && <div style={{ position: "absolute", right: 150, top: 760, transform: `scale(${pop(t, cue(W, cmp.ratio.cue, cmpT), fps, { damping: 9, stiffness: 200, mass: 0.7 })}) rotate(-6deg)`,
        fontFamily: F, fontWeight: 800, fontSize: 220, color: C.fg, textShadow: "0 20px 60px rgba(0,0,0,.7)" }}>{cmp.ratio.text}</div>}
      {gridOn && t < stT && gridVis > 0.5 && <div style={{ position: "absolute", right: 150, top: gy - 50, fontFamily: M, fontSize: 24, color: C.dim }}>{D.unitLabel}</div>}
      {D.footnote && t >= cue(W, D.footnote.cue) && t < stT && <Credit text={D.footnote.text} color={C.dim} font={M} show={ease(t, cue(W, D.footnote.cue), cue(W, D.footnote.cue) + 0.5)} top={1405} />}
      <Captions words={W} until={end} st={{ top: 1250, font: F, size: 62, weight: 800, color: C.fg, dim: C.dim, active: C.b, maxWords: 3, shadow: "0 4px 18px rgba(0,0,0,.8)" }} />
      <EndCard at={end} title={p.title} bg={C.bg} fg={C.fg} accent={C.b} font={F} mono={M} />
    </AbsoluteFill>
  );
};
