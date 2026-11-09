import { useState } from "react";
import { AbsoluteFill, Img, Loop, OffthreadVideo, interpolate, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { Slot as SlotT, T } from "../theme";
import { useFilm } from "../Film";
import { D } from "../dossier";

/** Общий медиа-слот (§2.2): Img / OffthreadVideo (+Loop), boxed contain на размытой подложке из себя же для узкого архива,
 *  матте-рамка 6 px, грейд по kind/year, Ken Burns к focus_xy, дрейф архивного фото, onError → бумажная плашка с подписью.
 *  w/h — размер контейнера в px (нужен для расчёта бокса под contain); сам компонент заполняет родителя (AbsoluteFill). */
export type Fit = "auto" | "cover" | "contain";

export const yearOf = (s?: string | null): number | null => {
  const m = s?.match(/\b(1[6-9]\d\d|20\d\d)\b/);
  return m ? Number(m[1]) : null;
};

/** Грейд по источнику и эпохе. С плёнкой (film=true) общий выцветший грейд уже стоит (Film.GRADE), здесь — только эпоха:
 *  до 1960 — почти монохром, цветная хроника 70–80-х — чуть холоднее. Без плёнки (news/anatomy) — прежние лёгкие грейды. */
export const gradeOf = (s: SlotT, film = false): string => {
  const y = s.kind === "archive" ? (s.year ?? yearOf(s.caption)) : null;
  if (film) {
    if (y && y < 1960) return "grayscale(0.85) contrast(1.04)";
    if (y && y >= 1970 && y < 1990) return "hue-rotate(-6deg) contrast(1.02)";
    if (s.kind === "stock" || (s.src && s.kind !== "image" && s.kind !== "archive")) return "brightness(0.92) hue-rotate(-6deg)";
    return "none";
  }
  if (s.kind === "archive") {
    if (y && y < 1960) return "contrast(1.05) sepia(0.08) saturate(0.55)";
    if (y && y >= 1970 && y < 1990) return "contrast(1.05) sepia(0.08) saturate(0.9) hue-rotate(-4deg)";
    return "contrast(1.05) sepia(0.08) saturate(0.9)";
  }
  // сток приводим к палитре сгенерированных кадров
  if (s.kind === "stock" || (s.src && s.kind !== "image")) return "saturate(0.72) contrast(1.06) brightness(0.88) sepia(0.12) hue-rotate(-8deg)";
  return "none";
};

/** Ken Burns по motion: возвращает [scale от, scale до, pan % за сцену]. Видео — только 1.00→1.04.
 *  «static» у картинки — лёгкий наезд 1.00→1.05: неподвижная картинка 10 с — «слайд», статика только у видео. */
export const kenBurns = (motion: string | undefined, video: boolean): [number, number, number] => {
  const m = (motion ?? "slow push in").toLowerCase();
  if (video) return [1, 1.04, 0];
  if (m.includes("detail")) return [1, 1.28, 0];
  if (m.includes("hard")) return [1, 1.18, 0];
  if (m.includes("pull")) return [1.08, 1, 0];
  if (m.includes("pan left")) return [1.08, 1.08, -3];
  if (m.includes("pan right")) return [1.08, 1.08, 3];
  if (m.includes("static")) return [1, 1.05, 0];
  return [1, 1.07, 0];
};

export const Slot: React.FC<{
  slot: SlotT; motion?: string; fit?: Fit; w?: number; h?: number;
  matte?: boolean;              // тёмная рамка 6 px вокруг бокса (фото на столе)
  push?: [number, number];      // переопределить наезд (People: 1→1.05)
  drift?: boolean;              // дрейф архивного фото 0.5 px/с
  vignette?: boolean;
  children?: React.ReactNode;   // содержимое поверх медиа (подписи)
}> = ({ slot, motion, fit = "auto", w = 1920, h = 1080, matte = true, push, drift = true, vignette = true, children }) => {
  const [err, setErr] = useState(false);
  const film = useFilm();   // weave и общий грейд плёнки ложатся на медиа здесь (см. Film.tsx)
  const f = useCurrentFrame(); const { fps, durationInFrames } = useVideoConfig();
  const video = !!slot.src;
  const has = (video || !!slot.image) && !err;
  const p = interpolate(f, [0, Math.max(1, durationInFrames)], [0, 1]);
  const ease = p * p * (3 - 2 * p);
  const [s0, s1, pan] = push ? [push[0], push[1], 0] : kenBurns(motion, video);
  const scale = s0 + (s1 - s0) * ease;
  const tx = pan < 0 ? pan * p : pan > 0 ? pan * p - pan : 0;
  const [fx, fy] = slot.focus_xy ?? [0.5, 0.5];
  const archive = slot.kind === "archive";
  const dx = drift && archive && !video ? (f / fps) * 0.5 : 0;
  const aspect = slot.aspect ?? (video ? 1.78 : 1.5);
  const boxed = has && (fit === "contain" || (fit === "auto" && archive && aspect < 1.5));
  // бокс под contain: вписываем исходник в контейнер с полем, рамка снаружи
  const m = matte ? 0.84 : 0.94;   // отпечаток в рамке — с полем тёмного стола: рамка не уходит под маску кадра и водяной знак
  const mW = w * m, mH = h * m;
  const [bw, bh] = aspect >= mW / mH ? [mW, mW / aspect] : [mH * aspect, mH];
  const media = (style: React.CSSProperties) => {
    if (video) {
      const v = <OffthreadVideo src={staticFile(slot.src!)} muted style={style} onError={() => setErr(true)}
        delayRenderRetries={3} delayRenderTimeoutInMilliseconds={60000} />;   // сеть/прокси могут моргнуть — повторяем
      const clip = slot.clip_seconds ? Math.max(1, Math.floor(slot.clip_seconds * fps)) : 0;
      return clip && clip < durationInFrames ? <Loop durationInFrames={clip}>{v}</Loop> : v;
    }
    return <Img src={staticFile(slot.image!)} style={style} onError={() => setErr(true)} />;
  };
  const grade = gradeOf(slot, !!film.grade);
  const style: React.CSSProperties = {
    width: "100%", height: "100%", objectFit: "cover", filter: film.grade ? (grade === "none" ? film.grade : `${film.grade} ${grade}`) : grade,
    transform: `${film.weave} translateX(calc(${tx}% + ${dx.toFixed(2)}px)) scale(${scale})`, transformOrigin: `${fx * 100}% ${fy * 100}%`,
  };
  const bg: React.CSSProperties = { width: "100%", height: "100%", objectFit: "cover", transform: `${film.weave} scale(1.25)`, filter: "blur(28px) brightness(0.45) saturate(0.7)" };
  return (
    <AbsoluteFill style={{ background: D.dark, overflow: "hidden" }}>
      {!has && <Plate caption={slot.caption} />}
      {has && boxed && <AbsoluteFill>{media(bg)}</AbsoluteFill>}
      {has && boxed && (
        <div style={{ position: "absolute", left: (w - bw) / 2, top: (h - bh) / 2, width: bw, height: bh, overflow: "hidden",
          boxSizing: "content-box", border: matte ? `12px solid ${D.photo}` : "none", marginLeft: matte ? -12 : 0, marginTop: matte ? -12 : 0,   // узкое архивное фото — отпечаток в белой рамке (досье)
          boxShadow: "0 18px 50px rgba(0,0,0,.35)" }}>
          {media(style)}
        </div>
      )}
      {has && !boxed && media(style)}
      {has && vignette && <div style={{ position: "absolute", inset: 0, background: "radial-gradient(ellipse at center, rgba(0,0,0,0) 60%, rgba(0,0,0,0.22) 100%)" }} />}
      {children}
    </AbsoluteFill>
  );
};

/** Пустой слот (нет медиа или файл не загрузился): бумажная плашка с подписью на ink-фоне — чёрного кадра не бывает. */
export const Plate: React.FC<{ caption?: string | null }> = ({ caption }) => (
  <AbsoluteFill style={{ background: D.dark, alignItems: "center", justifyContent: "center" }}>
    <div style={{ background: D.cream, color: D.brown, padding: "26px 40px 28px", fontFamily: D.serif, fontSize: 40, fontWeight: 400, maxWidth: 1100,
      textAlign: "center", boxShadow: "0 20px 60px rgba(0,0,0,.45)" }}>
      {caption || "—"}
      <div style={{ height: 3, width: 120, background: D.ox, margin: "16px auto 0" }} />
    </div>
  </AbsoluteFill>
);
