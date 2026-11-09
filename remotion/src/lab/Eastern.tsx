import React from "react";
import { AbsoluteFill, Img, staticFile } from "remotion";
import { loadFont as loadElite } from "@remotion/google-fonts/SpecialElite";
import { loadFont as loadPlayfair } from "@remotion/google-fonts/PlayfairDisplay";
import { Captions, Credit, EndCard, LabProps, Sound, cue, ease, pop, useT } from "./common";

/** Формат 3 «Досье-гонка»: бумага, машинка, архивные фото; самолёт против поезда Нью-Йорк → Атланта и часы, которые продают время. */
const elite = loadElite("normal", { weights: ["400"], subsets: ["latin"] });
const play = loadPlayfair("normal", { weights: ["700", "900"], subsets: ["latin"] });
const C = { paper: "#EFE6D2", paper2: "#E4D8BF", ink: "#2B2118", ox: "#9A2E1C", muted: "#7C6A55", night: "#16233A", beacon: "#FFD36B" };
const E = elite.fontFamily, P = play.fontFamily;

const typed = (text: string, t: number, at: number, cps = 22) => text.slice(0, Math.max(0, Math.floor((t - at) * cps)));

const Plane: React.FC<{ color: string }> = ({ color }) => (
  <svg width={92} height={60} viewBox="0 0 92 60"><g fill={color}>
    <rect x={8} y={26} width={70} height={9} rx={4} /><rect x={36} y={6} width={10} height={48} rx={2} /><rect x={30} y={4} width={22} height={6} rx={2} />
    <rect x={30} y={50} width={22} height={6} rx={2} /><rect x={4} y={18} width={6} height={24} rx={2} /><circle cx={82} cy={30} r={6} />
  </g></svg>
);
const Train: React.FC<{ color: string }> = ({ color }) => (
  <svg width={110} height={60} viewBox="0 0 110 60"><g fill={color}>
    <rect x={10} y={18} width={62} height={26} rx={3} /><rect x={58} y={6} width={22} height={38} rx={2} /><rect x={20} y={8} width={10} height={12} />
    <path d="M80 30h18l8 14H80z" /><circle cx={24} cy={50} r={7} /><circle cx={48} cy={50} r={7} /><circle cx={72} cy={50} r={7} />
  </g></svg>
);
const Clock: React.FC<{ hours: number; size: number; color: string }> = ({ hours, size, color }) => (
  <svg width={size} height={size} viewBox="-60 -60 120 120">
    <circle r={56} fill={C.paper} stroke={color} strokeWidth={5} />
    {Array.from({ length: 12 }, (_, k) => <rect key={k} x={-1.5} y={-52} width={3} height={k % 3 ? 6 : 11} fill={color} transform={`rotate(${k * 30})`} />)}
    <rect x={-2.5} y={-30} width={5} height={34} rx={2} fill={color} transform={`rotate(${hours * 30})`} />
    <rect x={-1.5} y={-46} width={3} height={50} rx={1.5} fill={C.ox} transform={`rotate(${hours * 360})`} />
    <circle r={5} fill={C.ox} />
  </svg>
);

export const Eastern: React.FC<LabProps> = (p) => {
  const { t, fps } = useT(); const W = p.words;
  const c = {
    letter: cue(W, "A letter"), train: cue(W, "By train"), day: cue(W, "day", 6, true), plane: cue(W, "By a small"), night: cue(W, "flying at night"),
    lighted: cue(W, "newly lighted"), seven: cue(W, "about seven"), hours: cue(W, "hours", 12, true), three: cue(W, "Roughly three"), gap: cue(W, "That gap"),
    company: cue(W, "The company that"), seats: cue(W, "seats"), comfort: cue(W, "comfort"), time: cue(W, "time", 25), sixty: cue(W, "Sixty-three"), ran: cue(W, "ran out"),
    end: cue(W, "Watch the full"),
  };
  const X0 = 150, X1 = 880;                         // Нью-Йорк → Атланта на полосе
  const trainP = t < c.plane ? ease(t, c.train, c.day + 0.3, 0, 1, (x) => x) : 1;
  const trainH = trainP * 21;
  const planeP = ease(t, c.plane + 0.4, c.hours, 0, 1, (x) => x);
  const planeH = planeP * 7;
  const clockH = t < c.plane ? trainH : planeH;
  const nightA = ease(t, c.night - 0.3, c.night + 0.4) * (1 - ease(t, c.three, c.three + 0.6));
  const raceOn = t >= c.letter - 0.3 && t < c.company;
  const raceA = ease(t, c.letter - 0.3, c.letter + 0.3) * (1 - ease(t, c.company - 0.5, c.company));
  const barsA = ease(t, c.three - 0.1, c.three + 0.5);
  const listOn = t >= c.company - 0.2 && t < c.sixty;
  const finalOn = t >= c.sixty - 0.2;
  const photo = t < c.plane ? "airmail.jpg" : "mailwing.jpg";
  const photoCredit = t < c.plane ? "U.S. airmail loading, c. 1925 · USPS" : "Pitcairn Mailwing, museum collection · Wikimedia Commons, CC0";
  const photoA = 1 * (1 - ease(t, c.company - 0.5, c.company));
  const photoSwap = pop(t, c.plane, fps, { damping: 12, stiffness: 140, mass: 0.8 });

  return (
    <AbsoluteFill style={{ background: C.paper, color: C.ink, overflow: "hidden",
      backgroundImage: `radial-gradient(ellipse at 50% 40%, rgba(255,255,255,.35), rgba(0,0,0,.12) 90%), repeating-linear-gradient(0deg, transparent 0 41px, rgba(122,46,31,.06) 42px)` }}>
      <Sound p={p} music={0.1} />
      {/* старая почтовая карта 1928 года фоном */}
      <Img src={staticFile("routes1928.jpg")} style={{ position: "absolute", left: -120, top: 360, width: 1320, opacity: 0.09 * (1 - ease(t, c.company - 0.5, c.company)), mixBlendMode: "multiply" }} />
      <div style={{ position: "absolute", left: 70, top: 158, fontFamily: E, fontSize: 30, letterSpacing: 4, color: C.ox }}>EASTERN AIR LINES · FILE No. 1</div>
      {t < c.company && <div style={{ position: "absolute", left: 66, top: 200, fontFamily: P, fontWeight: 900, fontSize: 112, lineHeight: 1 }}>May 1, 1928</div>}
      {/* архивное фото */}
      {t < c.company && <div style={{ position: "absolute", left: 120, top: 350, width: 840, opacity: photoA,
        transform: `rotate(${t < c.plane ? -2.2 : 1.8 - 4 * (1 - photoSwap)}deg) scale(${0.96 + 0.04 * photoSwap})` }}>
        <div style={{ background: "#FBF7EE", padding: 16, boxShadow: "0 24px 60px rgba(43,33,24,.35)" }}>
          <Img src={staticFile(photo)} style={{ width: "100%", height: 420, objectFit: "cover", display: "block", filter: "sepia(.35) contrast(1.05)" }} />
        </div>
      </div>}
      {/* гонка */}
      {raceOn && <div style={{ position: "absolute", left: 0, right: 0, top: 830, height: 380, opacity: raceA }}>
        <div style={{ position: "absolute", inset: "0 40px", borderRadius: 18, background: C.night, opacity: nightA }} />
        <div style={{ position: "absolute", left: X0 - 90, top: 14, fontFamily: E, fontSize: 30, color: nightA > 0.5 ? C.paper : C.ink }}>NEW YORK</div>
        <div style={{ position: "absolute", left: X1 - 120, top: 14, fontFamily: E, fontSize: 30, color: nightA > 0.5 ? C.paper : C.ink }}>ATLANTA</div>
        {/* полоса поезда */}
        <div style={{ position: "absolute", left: X0, width: X1 - X0, top: 100, borderTop: `4px dashed ${C.muted}` }} />
        <div style={{ position: "absolute", left: X0 - 55 + trainP * (X1 - X0), top: 56, opacity: ease(t, c.train - 0.2, c.train + 0.2) }}><Train color={nightA > 0.5 ? C.paper : C.ink} /></div>
        {t >= c.train && <div style={{ position: "absolute", left: X1 - 70, top: 118, fontFamily: E, fontSize: 28, color: nightA > 0.5 ? C.paper : C.ox, opacity: trainP >= 1 ? 1 : 0 }}>~21h</div>}
        {/* полоса самолёта с огнями авиатрассы */}
        <div style={{ position: "absolute", left: X0, width: X1 - X0, top: 195, borderTop: `4px solid ${nightA > 0.5 ? "#3B4C6E" : C.muted}`, opacity: ease(t, c.plane - 0.2, c.plane + 0.2) }} />
        {Array.from({ length: 9 }, (_, k) => {
          const at = c.lighted + k * 0.09; const on = t >= at;
          return <div key={k} style={{ position: "absolute", left: X0 + 20 + k * ((X1 - X0 - 40) / 8) - 9, top: 186, width: 18, height: 18, borderRadius: 9,
            background: on ? C.beacon : "#555", boxShadow: on ? `0 0 ${18 + 10 * Math.sin(t * 9 + k)}px ${C.beacon}` : undefined, opacity: nightA }} />;
        })}
        {t >= c.plane - 0.2 && <div style={{ position: "absolute", left: X0 - 46 + planeP * (X1 - X0), top: 165 - Math.sin(planeP * Math.PI) * 30 }}><Plane color={nightA > 0.5 ? C.paper : C.ink} /></div>}
        {t >= c.seven && <div style={{ position: "absolute", left: X1 - 150, top: 236, transform: `rotate(-8deg) scale(${pop(t, c.hours - 0.2, fps)})`, border: `5px solid ${C.ox}`,
          color: C.ox, background: C.paper, fontFamily: E, fontSize: 40, padding: "4px 18px" }}>≈ 7 HRS</div>}
        {/* часы */}
        <div style={{ position: "absolute", left: 470, top: 240, opacity: ease(t, c.train - 0.2, c.train + 0.3) * (1 - barsA) }}><Clock hours={clockH} size={130} color={C.ink} /></div>
        {/* итог: столбики */}
        {barsA > 0 && <div style={{ position: "absolute", left: 80, right: 80, top: 0, bottom: 0, background: C.paper, opacity: barsA, padding: "40px 30px" }}>
          {[["AIR MAIL", 7, C.ox], ["RAIL", 21, C.muted]].map(([label, h, col], k) => (
            <div key={k} style={{ marginBottom: 46 }}>
              <div style={{ fontFamily: E, fontSize: 34, marginBottom: 10 }}>{label as string} · ~{h as number} HOURS</div>
              <div style={{ height: 54, width: `${(h as number) / 21 * 100 * ease(t, c.three + k * 0.25, c.three + 0.9 + k * 0.25)}%`, background: col as string }} />
            </div>))}
          {t >= c.gap && <div style={{ fontFamily: P, fontWeight: 900, fontSize: 60, color: C.ox, transform: `scale(${pop(t, c.gap, fps)})`, transformOrigin: "0 50%" }}>The gap = the product.</div>}
        </div>}
      </div>}
      {raceOn && t < c.company - 0.3 && <Credit text={photoCredit} color={C.muted} font={E} show={photoA} top={805} />}
      {/* не места и не комфорт — время */}
      {listOn && <div style={{ position: "absolute", left: 90, right: 120, top: 330, opacity: ease(t, c.company - 0.2, c.company + 0.3) * (1 - ease(t, c.sixty - 0.4, c.sixty)) }}>
        <div style={{ fontFamily: E, fontSize: 36, color: C.muted, marginBottom: 40 }}>{typed("WHAT EASTERN SOLD:", t, c.company)}</div>
        {[["SEATS", c.seats], ["COMFORT", c.comfort], ["TIME", c.time]].map(([w, at], k) => {
          const s = pop(t, (at as number) - 0.35, fps); const strike = k < 2 ? ease(t, (at as number) + 0.1, (at as number) + 0.45) : 0;
          const circle = k === 2 ? ease(t, (at as number) + 0.1, (at as number) + 0.8) : 0;
          return <div key={k} style={{ position: "relative", height: 210, opacity: s, transform: `translateY(${(1 - s) * 30}px)` }}>
            <span style={{ fontFamily: P, fontWeight: 900, fontSize: k === 2 ? 190 : 150, color: k === 2 ? C.ox : C.ink, opacity: k < 2 ? 1 - 0.45 * strike : 1 }}>{w as string}</span>
            {k < 2 && <div style={{ position: "absolute", left: -10, top: 100, height: 14, width: `${strike * (k === 0 ? 520 : 800)}px`, background: C.ox, transform: "rotate(-3deg)" }} />}
            {k === 2 && <svg width={640} height={260} style={{ position: "absolute", left: -50, top: -30 }}>
              <ellipse cx={310} cy={130} rx={290} ry={105} fill="none" stroke={C.ox} strokeWidth={9} strokeDasharray={1300} strokeDashoffset={1300 * (1 - circle)} transform="rotate(-4 310 130)" />
            </svg>}
          </div>;
        })}
      </div>}
      {/* 63 года спустя */}
      {finalOn && t < c.end && <AbsoluteFill style={{ opacity: ease(t, c.sixty - 0.2, c.sixty + 0.4) }}>
        <div style={{ position: "absolute", left: 66, top: 210, fontFamily: P, fontWeight: 900, fontSize: 130, lineHeight: 1 }}>1928 <span style={{ color: C.ox }}>→</span> 1991</div>
        <div style={{ position: "absolute", left: 110, top: 420, width: 860, transform: `rotate(-1.5deg)` }}>
          <div style={{ background: "#FBF7EE", padding: 16, boxShadow: "0 24px 60px rgba(43,33,24,.35)" }}>
            <Img src={staticFile("a300.jpg")} style={{ width: "100%", display: "block", filter: `grayscale(${ease(t, c.ran, c.ran + 1.2)}) sepia(.2)` }} />
          </div>
          <div style={{ marginTop: 18, fontFamily: E, fontSize: 21, color: C.muted }}>Eastern Airbus A300, 1984 · Andrew Thomas / Wikimedia Commons, CC BY-SA 2.0</div>
        </div>
        <div style={{ position: "absolute", left: 300, top: 640, transform: `rotate(-10deg) scale(${2 - pop(t, c.ran + 0.2, fps)})`, opacity: t > c.ran ? 1 : 0, border: `8px solid ${C.ox}`,
          color: C.ox, fontFamily: E, fontSize: 52, padding: "8px 26px", background: "rgba(239,230,210,.9)", whiteSpace: "nowrap" }}>LAST FLIGHT · JAN 18, 1991</div>
        <div style={{ position: "absolute", right: 150, top: 960 }}><Clock hours={7 + Math.min(t - c.sixty, 1.2) * 4} size={170} color={C.ink} /></div>
      </AbsoluteFill>}
      <Captions words={W} until={c.end} st={{ top: 1262, font: E, size: 54, weight: 400, color: C.ink, dim: "rgba(43,33,24,.45)", active: C.ox, maxWords: 4 }} />
      <EndCard at={c.end} title="What Happened to Eastern Air Lines? Trump Bought the Shuttle" bg={C.paper} fg={C.ink} accent={C.ox} font={P} mono={E} frame="#FBF7EE" />
    </AbsoluteFill>
  );
};
