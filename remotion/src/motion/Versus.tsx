import React from "react";
import { AbsoluteFill, Img, staticFile } from "remotion";
import { loadFont as loadArchivo } from "@remotion/google-fonts/ArchivoBlack";
import { loadFont as loadInter } from "@remotion/google-fonts/Inter";
import { loadFont as loadMono } from "@remotion/google-fonts/SpaceMono";
import { Captions, Credit, EndCard, MotionProps, Sound, cue, ease, pop, useT } from "./common";

/** Шаблон «Против» (образец In-N-Out 06.10): две компании рядом — сетка 100 единиц с долей, затем столбики, затем решение со штампами. */
const archivo = loadArchivo("normal", { weights: ["400"], subsets: ["latin"] });
const inter = loadInter("normal", { weights: ["600", "800"], subsets: ["latin"] });
const mono = loadMono("normal", { weights: ["400", "700"], subsets: ["latin"] });
const C = { bg: "#F6F2EA", ink: "#151515", red: "#D6202A", gold: "#E3A21A", dim: "rgba(21,21,21,.5)" };
const A = archivo.fontFamily, I = inter.fontFamily, M = mono.fontFamily;

type Side = { name: string; on: number; cue: string; endCue?: string; allCue?: string; prefix?: string };
export type VersusData = {
  kicker: string; question: string; questionCue: string; left: Side; right: Side; legendOn: string; legendOff: string; icon?: "store" | "unit";
  bars?: { head: string; cue: string; unitNote: string; left: { value: number; text: string; cue: string }; right: { value: number; text: string; cue: string } };
  final?: { cue: string; photo: string; credit: string; questions: { text: string; cue: string }[]; answer: string; answerCue: string; closing?: string; closingCue?: string };
};

const Store: React.FC<{ fill: string; outline?: boolean; unit?: boolean }> = ({ fill, outline, unit }) => unit
  ? <svg width={36} height={36} viewBox="0 0 36 36"><circle cx={18} cy={18} r={14} fill={outline ? "none" : fill} stroke={fill} strokeWidth={4} /></svg>
  : <svg width={36} height={36} viewBox="0 0 36 36">
    <path d="M3 13 L7 4 H29 L33 13 Z" fill={fill} />
    <rect x={5} y={15} width={26} height={18} fill={outline ? "none" : fill} stroke={fill} strokeWidth={3} />
    <rect x={14} y={22} width={8} height={11} fill={outline ? fill : C.bg} />
  </svg>;

export const Versus: React.FC<MotionProps<VersusData>> = (p) => {
  const { t, fps } = useT(); const W = p.words; const D = p.data;
  const end = cue(W, "Watch the full");
  const q = cue(W, D.questionCue);
  const barsT = D.bars ? cue(W, D.bars.cue) : 1e9; const finT = D.final ? cue(W, D.final.cue) : 1e9;
  const gridsA = ease(t, 0, 0.4) * (1 - ease(t, Math.min(barsT, finT), Math.min(barsT, finT) + 0.5));
  const sideState = (s: Side) => { const a = cue(W, s.cue), b = s.endCue ? cue(W, s.endCue, a, true) : a + 1.5, all = s.allCue ? cue(W, s.allCue, a - 0.01) : 1e9;
    return { a, b, all, marked: (k: number) => k < s.on && t >= a + 0.2 + (k / Math.max(1, s.on)) * (b - a), lit: (k: number) => k >= s.on && t >= all + ((k - s.on) / 100) * 1.4 }; };
  const L = sideState(D.left), Rt = sideState(D.right);
  const head = t < Math.min(barsT, finT) ? D.question : t < finT ? D.bars?.head ?? "" : "";
  const headAt = t < Math.min(barsT, finT) ? q : barsT;
  const barsA = D.bars ? ease(t, barsT + 0.3, barsT + 0.8) * (1 - ease(t, finT - 0.4, finT)) : 0;
  const finalA = D.final ? ease(t, finT - 0.3, finT + 0.3) : 0;
  const unit = D.icon === "unit";

  return (
    <AbsoluteFill style={{ background: C.bg, color: C.ink, overflow: "hidden" }}>
      <Sound p={p} music={0.1} />
      {t < finT - 0.3 && <div style={{ position: "absolute", left: 70, top: 158, fontFamily: M, fontWeight: 700, fontSize: 26, letterSpacing: 3, color: C.red }}>{D.kicker}</div>}
      {head && <div style={{ position: "absolute", left: 66, right: 140, top: 200, fontFamily: A, fontSize: head.length > 26 ? 64 : 88, lineHeight: 1.02 }}>
        {head.split(" ").map((w, k) => { const s = pop(t, headAt + k * 0.12, fps); return <span key={k} style={{ display: "inline-block", marginRight: 22, opacity: s, transform: `translateY(${(1 - s) * 30}px)` }}>{w}</span>; })}
      </div>}
      {gridsA > 0 && <AbsoluteFill style={{ opacity: gridsA }}>
        {[[D.left, 70, L, C.gold], [D.right, 570, Rt, C.red]].map(([side, x, st, col], j) => {
          const S = side as Side, ST = st as typeof L;
          return <React.Fragment key={j}>
            <div style={{ position: "absolute", left: x as number, top: 410, fontFamily: A, fontSize: S.name.length > 12 ? 34 : 44, color: j ? C.red : C.ink, opacity: 0.35 + 0.65 * ease(t, ST.a - 0.6, ST.a) }}>{S.name}</div>
            <div style={{ position: "absolute", left: x as number, top: 480, width: 440, display: "grid", gridTemplateColumns: "repeat(10, 36px)", gap: 8 }}>
              {Array.from({ length: 100 }, (_, k) => { const s = Math.min(1, Math.max(0, (t - 0.2 - j * 0.2 - k * 0.012) / 0.2)); const m = ST.marked(k); const lit = ST.lit(k);
                return <div key={k} style={{ transform: `scale(${s})` }}><Store unit={unit} fill={m ? (col as string) : lit ? (col as string) : C.ink} outline={m} /></div>; })}
            </div>
            <div style={{ position: "absolute", left: x as number, top: 935, fontFamily: A, fontSize: 120, color: col as string, opacity: ease(t, ST.a, ST.a + 0.3), transform: `scale(${S.on === 0 ? pop(t, ST.a, fps) : 1})`, transformOrigin: "0 50%" }}>
              {S.prefix ?? ""}{Math.round(S.on === 0 || S.prefix ? S.on : ease(t, ST.a, ST.b, 0, S.on, (v) => v))}<span style={{ fontSize: 60 }}>/100</span></div>
          </React.Fragment>;
        })}
        <div style={{ position: "absolute", left: 70, right: 140, top: 1090, display: "flex", gap: 40, fontFamily: M, fontSize: 25, opacity: ease(t, L.a, L.a + 0.4) }}>
          <span style={{ display: "flex", alignItems: "center", gap: 10 }}><Store unit={unit} fill={C.gold} outline /> {D.legendOn}</span>
          <span style={{ display: "flex", alignItems: "center", gap: 10 }}><Store unit={unit} fill={C.ink} /> {D.legendOff}</span>
        </div>
      </AbsoluteFill>}
      {D.bars && barsA > 0 && <AbsoluteFill style={{ opacity: barsA }}>
        {[[D.left.name, D.bars.left, C.gold, 150], [D.right.name, D.bars.right, C.red, 600]].map(([label, b, col, x], k) => {
          const B = b as { value: number; text: string; cue: string }; const mx = Math.max(D.bars!.left.value, D.bars!.right.value);
          const h = ease(t, cue(W, B.cue, barsT) - 0.3, cue(W, B.cue, barsT) + 0.8) * B.value / mx * 640;
          return <div key={k} style={{ position: "absolute", left: x as number, width: 330, top: 1150 - h, height: h, background: col as string }}>
            <div style={{ position: "absolute", top: -96, left: 0, fontFamily: A, fontSize: 76, color: col as string, opacity: h > 20 ? 1 : 0, whiteSpace: "nowrap" }}>{B.text}</div>
            <div style={{ position: "absolute", bottom: -46, left: 0, fontFamily: M, fontWeight: 700, fontSize: 24, color: C.ink }}>{label as string}</div>
          </div>;
        })}
        <Credit text={D.bars.unitNote} color={C.dim} font={M} show={1} top={1405} />
      </AbsoluteFill>}
      {D.final && finalA > 0 && t < end && <AbsoluteFill style={{ opacity: finalA }}>
        <Img src={staticFile(D.final.photo)} style={{ position: "absolute", left: 70, top: 200, width: 940, height: 600, objectFit: "cover", objectPosition: "50% 22%", filter: "grayscale(1) contrast(1.05)", transform: `scale(${1 + 0.03 * (t - finT)})` }} />
        <div style={{ position: "absolute", left: 70, top: 818, fontFamily: M, fontSize: 21, color: C.dim }}>{D.final.credit}</div>
        {D.final.questions.map((qq, k) => { const s = pop(t, cue(W, qq.cue, finT - 0.01) - 0.2, fps); const no = pop(t, cue(W, D.final!.answerCue, finT - 0.01) + k * 0.25, fps, { damping: 9, stiffness: 260, mass: 0.6 });
          return <div key={k} style={{ position: "absolute", left: 70, top: 880 + k * 120, opacity: s, display: "flex", alignItems: "center", gap: 30 }}>
            <span style={{ fontFamily: A, fontSize: qq.text.length > 18 ? 56 : 70 }}>{qq.text}</span>
            <span style={{ fontFamily: A, fontSize: 64, color: C.red, border: `7px solid ${C.red}`, padding: "0 18px", transform: `rotate(-8deg) scale(${2 - no})`, opacity: no }}>{D.final!.answer}</span>
          </div>; })}
        {D.final.closing && D.final.closingCue && t >= cue(W, D.final.closingCue, finT - 0.01) && <div style={{ position: "absolute", left: 70, top: 1120, fontFamily: A, fontSize: 84, color: C.red,
          transform: `scale(${pop(t, cue(W, D.final.closingCue, finT - 0.01), fps)})`, transformOrigin: "0 50%" }}>{D.final.closing}</div>}
      </AbsoluteFill>}
      <Captions words={W} until={end} st={{ top: 1265, font: I, size: 56, weight: 800, color: C.ink, dim: "rgba(21,21,21,.4)", active: "#fff", activeBg: C.red, maxWords: 3 }} />
      <EndCard at={end} title={p.title} bg={C.bg} fg={C.ink} accent={C.red} font={A} mono={M} />
    </AbsoluteFill>
  );
};
