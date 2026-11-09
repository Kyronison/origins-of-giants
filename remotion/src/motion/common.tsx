import React from "react";
import { AbsoluteFill, Audio, Easing, Img, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig } from "remotion";

/** Моушен-шортсы (06.10, выбор владельца после лаборатории): общие помощники. Всё время в кадре привязано к словам диктора (words.json), а не к таймеру. */
export type Word = { w: string; s: number; e: number };
export type LabProps = { words: Word[]; duration: number; voiceDur: number; musicDur: number };
/** Спека моушен-шортса: собирает orchestrator/stages/motion_shorts.py. data — данные шаблона. */
export type MotionProps<D = any> = LabProps & { music: boolean; title: string; data: D };

const norm = (t: string) => t.toLowerCase().replace(/[^a-z0-9]/g, "");

/** Секунда начала фразы диктора; after — искать после этой секунды. Нет фразы — ошибка рендера, а не тихий сдвиг. */
export const cue = (words: Word[], phrase: string, after = 0, end = false): number => {
  const p = phrase.split(/\s+/).map(norm).filter(Boolean);
  const tok = words.map((w) => norm(w.w));
  for (let i = 0; i + p.length <= tok.length; i++) {
    if (words[i].s < after) continue;
    if (p.every((x, k) => tok[i + k] === x)) return end ? words[i + p.length - 1].e : words[i].s;
  }
  throw new Error(`cue not found: "${phrase}"`);
};

export const ease = (t: number, a: number, b: number, from = 0, to = 1, e = Easing.inOut(Easing.cubic)) =>
  interpolate(t, [a, b], [from, to], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: e });

export const useT = () => { const f = useCurrentFrame(); const { fps } = useVideoConfig(); return { f, fps, t: f / fps }; };

export const pop = (t: number, at: number, fps: number, cfg = { damping: 12, stiffness: 180, mass: 0.7 }) =>
  t < at ? 0 : spring({ frame: Math.round((t - at) * fps), fps, config: cfg });

/** Голос + музыка: музыка тише под речью, плавные края. */
export const Sound: React.FC<{ p: LabProps & { music?: boolean }; music?: number }> = ({ p, music = 0.11 }) => {
  const { fps } = useVideoConfig(); const total = Math.ceil(p.duration * fps);
  return (<>
    <Audio src={staticFile("voice.mp3")} />
    {p.music !== false && <Audio src={staticFile("music.mp3")} volume={(fr) => music * interpolate(fr, [0, 20, total - 40, total], [0, 1, 1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" })} />}
  </>);
};

/** Субтитры: группы до maxWords слов, разрыв на знаках препинания; активное слово подсвечено. */
export type CapStyle = { top: number; font: string; size: number; color: string; dim: string; active: string; activeBg?: string; upper?: boolean;
  weight?: number; shadow?: string; box?: React.CSSProperties; maxWords?: number; letterSpacing?: number };
export const groups = (words: Word[], maxWords: number, until: number) => {
  const out: Word[][] = []; let cur: Word[] = [];
  for (const w of words) {
    if (w.s >= until) break;
    cur.push(w);
    if (cur.length >= maxWords || /[.,!?;:]$/.test(w.w)) { out.push(cur); cur = []; }
  }
  if (cur.length) out.push(cur);
  return out;
};
export const Captions: React.FC<{ words: Word[]; until: number; st: CapStyle }> = ({ words, until, st }) => {
  const { t, fps } = useT();
  const gs = groups(words, st.maxWords ?? 3, until);
  const k = gs.findIndex((g, i) => t >= g[0].s - 0.05 && (i + 1 >= gs.length || t < gs[i + 1][0].s - 0.05));
  if (k < 0 || t >= until) return null;
  const g = gs[k];
  if (t > g[g.length - 1].e + 0.7) return null;
  const s = pop(t, g[0].s - 0.05, fps, { damping: 14, stiffness: 300, mass: 0.5 });
  return (
    <div style={{ position: "absolute", left: 70, right: 150, top: st.top, display: "flex", justifyContent: "center", flexWrap: "wrap", gap: "4px 18px",
      transform: `translateY(${(1 - s) * 18}px)`, opacity: s, ...st.box }}>
      {g.map((w, i) => {
        const on = t >= w.s - 0.03 && t < w.e + 0.08; const done = t >= w.e;
        return <span key={i} style={{ fontFamily: st.font, fontSize: st.size, fontWeight: st.weight ?? 700, lineHeight: 1.12, letterSpacing: st.letterSpacing,
          textTransform: st.upper ? "uppercase" : undefined, color: on ? st.active : done ? st.color : st.dim, textShadow: st.shadow,
          background: on && st.activeBg ? st.activeBg : undefined, padding: st.activeBg ? "0 10px" : undefined, borderRadius: 8 }}>{w.w.replace(/[“”"]/g, "")}</span>;
      })}
    </div>
  );
};

/** Концовка: превью полного ролика и строка канала. Стиль — от формата. */
export const EndCard: React.FC<{ at: number; title: string; bg: string; fg: string; accent: string; font: string; mono: string; frame?: string }> = ({ at, title, bg, fg, accent, font, mono, frame = "#fff" }) => {
  const { t, fps } = useT();
  if (t < at) return null;
  const a = ease(t, at, at + 0.4); const s = pop(t, at + 0.1, fps, { damping: 13, stiffness: 140, mass: 0.9 });
  return (
    <AbsoluteFill style={{ background: bg, opacity: a }}>
      <div style={{ position: "absolute", top: 330, left: 0, right: 0, textAlign: "center", fontFamily: mono, fontSize: 34, letterSpacing: 8, color: accent }}>THE FULL STORY</div>
      <div style={{ position: "absolute", left: 80, top: 420, width: 920, height: 518, border: `10px solid ${frame}`, boxShadow: "0 30px 80px rgba(0,0,0,.5)",
        transform: `scale(${0.8 + 0.2 * s}) rotate(${-1.5 * s}deg)`, overflow: "hidden" }}>
        <Img src={staticFile("thumb.jpg")} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
      </div>
      <div style={{ position: "absolute", left: 80, right: 80, top: 1000, textAlign: "center", fontFamily: font, fontSize: 52, lineHeight: 1.15, color: fg, opacity: ease(t, at + 0.3, at + 0.8) }}>{title}</div>
      <div style={{ position: "absolute", left: 80, right: 80, top: 1190, textAlign: "center", fontFamily: mono, fontSize: 32, letterSpacing: 3, color: accent, opacity: ease(t, at + 0.5, at + 1) }}>ORIGINS OF GIANTS · ON OUR CHANNEL</div>
    </AbsoluteFill>
  );
};

/** Мелкая подпись источника/фото в нижней безопасной зоне над интерфейсом Shorts. */
export const Credit: React.FC<{ text: string; color: string; font: string; show: number; top?: number }> = ({ text, color, font, show, top = 1430 }) =>
  <div style={{ position: "absolute", left: 70, right: 150, top, fontFamily: font, fontSize: 21, color, opacity: show, lineHeight: 1.35 }}>{text}</div>;

/** Сцены по якорям: k-я сцена идёт от своего якоря до якоря следующей. */
export const sceneAt = (starts: number[], t: number) => { let k = -1; starts.forEach((s, i) => { if (t >= s) k = i; }); return k; };
