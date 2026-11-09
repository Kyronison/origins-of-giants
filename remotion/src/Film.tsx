import { createContext, useContext, useMemo } from "react";
import { AbsoluteFill, Img, useCurrentFrame, useVideoConfig } from "remotion";
import { Film as FilmCfg, Overlay, Scene, slotsOf, xfadeSecOf } from "./theme";
import { hash32, hashN, mulberry32, rangeOf } from "./noise";
import grain0 from "./film/grain_0.png";
import grain1 from "./film/grain_1.png";
import grain2 from "./film/grain_2.png";
import grain3 from "./film/grain_3.png";
import frameMask from "./film/frame_mask.png";

/** «Старая плёнка» (docs/scene-grammar.md §4, переделано 15.09 по замечанию владельца: нужен не шум, а плёнка).
 *  Что даёт ощущение плёнки, в порядке важности: выцветший грейд с тёплым тоном и приподнятыми тенями (на самом медиа),
 *  мерцание проектора, дрожание кадра, тёмное неровное «окно» гейта, редкие царапины/волоски/пыль, засветки раз в полминуты,
 *  и только потом тонкое зерно. Всё детерминировано по кадру (noise.ts). Титры и плашки остаются чистыми (напечатаны поверх).
 *  Слои снизу вверх: контейнер сцен (weave + грейд на <img>/<video> через FilmContext) → выцветание → титры → зерно → мерцание →
 *  царапины/пыль → засветка → окно гейта → виньетка. */
const TILES = [grain0, grain1, grain2, grain3];
const W = 1920, H = 1080;
/** Общий грейд медиа: контраст ниже, цвет выцвел, тёплый тон. Эпоха уточняется в Slot.gradeOf. */
export const GRADE = "contrast(0.9) saturate(0.62) sepia(0.3) brightness(1.03)";

export type FilmCtx = { weave: string; grade: string };
export const FilmContext = createContext<FilmCtx>({ weave: "", grade: "" });
export const useFilm = () => useContext(FilmContext);

/** Как плёнка ложится на сцену: сила эффектов, «бумажность» (0 — медиа, 1 — бумажная композиция), амплитуда weave. */
export type Look = { mul: number; paper: number; weave: number };
const NONE: Look = { mul: 0, paper: 1, weave: 0 };

export const lookOf = (s?: Scene | null): Look => {
  if (!s) return NONE;
  const slots = slotsOf(s); const k = slots[0]?.kind;
  const hasMedia = slots.some((x) => x.src || x.image);
  const lowRes = !!slots[0]?.src && !!slots[0]?.src_px && slots[0].src_px![1] < 720;
  switch (s.type) {
    case "map": case "timeline": case "chart": case "object": case "quote":
    case "bar_chart": case "line_chart": case "compare": case "stat": return { mul: 0.3, paper: 1, weave: 0 };
    case "title": case "outro": return { mul: 0, paper: 1, weave: 0 };
    case "people": return { mul: 0.85, paper: 0, weave: 0.7 };
    case "split": return { mul: 0.9, paper: 0, weave: s.data?.mode === "vs" ? 1.6 : 0.8 };
    default:   // broll, montage и неизвестные типы
      if (!hasMedia) return { mul: 0.3, paper: 1, weave: 0 };
      if (k === "archive") return { mul: lowRes ? 0.85 : 1, paper: 0, weave: 1 };
      return { mul: 0.85, paper: 0, weave: 0.8 };   // сгенерированные и сток — тоже «плёнка»: единый видеоряд
  }
};
const CHAPTER: Look = { mul: 0.7, paper: 0, weave: 1 };
const mix = (a: Look, b: Look, w: number): Look => ({ mul: a.mul + (b.mul - a.mul) * w, paper: a.paper + (b.paper - a.paper) * w, weave: a.weave + (b.weave - a.weave) * w });
const clamp01 = (x: number) => Math.max(0, Math.min(1, x));

/** Текущий look по кадру: сцена под кадром, смешанная через наплыв с предыдущей; карточка главы с паузой — свой look. */
const useLook = (scenes: Scene[], overlays: Overlay[] | undefined, offset: number) => {
  const f = useCurrentFrame(); const { fps } = useVideoConfig();
  const t = f / fps + offset;
  const chapter = overlays?.find((o) => o.type === "chapter" && t >= (o.pause && o.pause.at < o.start ? o.pause.at : o.start) && t < o.end);
  const flash = overlays?.some((o) => o.type === "flash" && t >= o.start && t < o.end);
  let cur = -1;
  for (let i = 0; i < scenes.length; i++) if (scenes[i].start <= t) cur = i;
  let look = cur < 0 ? NONE : lookOf(scenes[cur]);
  if (cur > 0) {
    const xf = xfadeSecOf(scenes[cur]);
    const w = xf > 0 ? clamp01((t - scenes[cur].start) / xf) : 1;
    look = mix(lookOf(scenes[cur - 1]), look, w);
  }
  if (chapter) {
    const c0 = chapter.pause && chapter.pause.at < chapter.start ? chapter.pause.at : chapter.start;
    const w = Math.min(clamp01((t - c0) / Math.max(0.3, chapter.start - c0)), clamp01((chapter.end - t) / 0.6));
    look = mix(look, CHAPTER, w);
  }
  return { look, chapter: !!chapter, flash: !!flash, t };
};

export const Film: React.FC<{
  film: Required<FilmCfg> | null; scenes: Scene[]; overlays?: Overlay[]; offset?: number;
  above?: React.ReactNode;      // титры — между выцветанием и зерном
  scratches?: boolean;          // Short: без царапин
  children: React.ReactNode;
}> = ({ film, scenes, overlays, offset = 0, above, scratches = true, children }) => {
  const { look, chapter, flash, t } = useLook(scenes, overlays ?? [], offset);
  const { fps } = useVideoConfig();
  const S = film?.strength ?? 0;
  const amt = S * look.mul;
  const fr = Math.round(t * fps);   // абсолютный кадр (Short: с учётом offset)
  // дрожание кадра в гейте: медленное плавание + мелкий джиттер + раз в ~15 с «скачок» на 2 кадра
  const wv = film?.weave ? look.weave : 0;
  const jump = wv > 0 && hash32(Math.floor(t / 15) * 17 + 3) < 0.6 && (t % 15) < 2 / fps ? 5 : 0;
  const dx = wv * (0.9 * Math.sin(2 * Math.PI * t / 0.7) + 0.5 * Math.sin(2 * Math.PI * t / 2.3 + 1.3) + 0.4 * (hash32(fr * 3 + 1) - 0.5));
  const dy = wv * (0.8 * Math.sin(2 * Math.PI * t / 1.1) + 0.5 * (hash32(fr * 5 + 2) - 0.5)) + jump;
  const rot = wv * 0.04 * Math.sin(2 * Math.PI * t / 3.1);
  const sc = 1 + 0.008 * Math.min(1, wv);
  const weave = wv > 0 ? `translate(${dx.toFixed(3)}px, ${dy.toFixed(3)}px) rotate(${rot.toFixed(4)}deg) scale(${sc})` : "";
  const grade = film?.grade ? GRADE + (film.soft ? " blur(0.35px)" : "") : "";
  const ctx = useMemo<FilmCtx>(() => ({ weave, grade }), [weave, grade]);
  if (!film) return <>{children}{above}</>;
  return (
    <>
      <FilmContext.Provider value={ctx}><AbsoluteFill>{children}</AbsoluteFill></FilmContext.Provider>
      {film.fade && amt > 0.01 && <Fade amount={amt * (1 - 0.7 * look.paper)} />}
      {above}
      {film.grain && amt > 0.01 && <Grain frame={fr} opacity={0.17 * amt * clamp01(film.grain_strength)} />}
      {film.flicker && amt > 0.01 && <Flicker frame={fr} t={t} amount={amt * (1 - 0.7 * look.paper)} />}
      {film.scratches && scratches && !chapter && !flash && amt > 0.05 && <Scratches frame={fr} paper={look.paper} strength={Math.min(1, amt)} />}
      {film.vignette && <Gate paper={look.paper} strength={S} />}
      {film.vignette && <Vignette paper={look.paper} strength={S} archive={look.mul > 0.9} />}
    </>
  );
};

/** Выцветание отпечатка: молочно-тёплая вуаль приподнимает тени и глушит контраст (CSS-фильтр «lift» не умеет). */
const Fade: React.FC<{ amount: number }> = ({ amount }) => (
  <AbsoluteFill style={{ background: "rgb(236,222,190)", opacity: 0.11 * amount, pointerEvents: "none" }} />
);

/** Зерно: тайл по кадру, сдвиг по хешу — узор не повторяется; растянут до 896 px (зерно ≈ 3 px, переживает кодек). Тонкое. */
const GRAIN_PX = 896;
const Grain: React.FC<{ frame: number; opacity: number }> = ({ frame, opacity }) => {
  const ox = Math.floor(hashN(frame, 1) * GRAIN_PX), oy = Math.floor(hashN(frame, 2) * GRAIN_PX);
  return (
    <AbsoluteFill style={{ backgroundImage: `url(${TILES[((frame % 4) + 4) % 4]})`, backgroundSize: `${GRAIN_PX}px ${GRAIN_PX}px`, backgroundRepeat: "repeat",
      backgroundPosition: `${ox}px ${oy}px`, mixBlendMode: "overlay", opacity, pointerEvents: "none" }} />
  );
};

/** Мерцание: только мягкое дыхание яркости (±2 %). Вспышки и провалы проектора убраны по замечанию владельца (16.09) — рябило. */
const Flicker: React.FC<{ frame: number; t: number; amount: number }> = ({ frame, t, amount }) => {
  const n = 0.5 + 0.3 * Math.sin(2 * Math.PI * t / 0.53) + 0.2 * Math.sin(2 * Math.PI * t / 1.9) + 0.3 * (hash32(frame) - 0.5);
  const dark = Math.max(0, Math.min(0.045, 0.03 * amount * n));
  return dark > 0.002 ? <AbsoluteFill style={{ background: "#000", opacity: dark, pointerEvents: "none" }} /> : null;
};

/** Царапины, волоски и пыль. Царапина живёт 6–30 кадров и плывёт; волосок — изогнутая линия на 3–8 кадров; пыль — крапины.
 *  Все кадры жизни объекта рисуют его одинаково (seed по стартовому кадру). */
const Scratches: React.FC<{ frame: number; paper: number; strength: number }> = ({ frame, paper, strength }) => {
  const onPaper = paper > 0.5;
  const light = onPaper ? "rgba(22,25,31,.12)" : "rgba(255,250,235,.16)";
  const els: React.ReactNode[] = [];
  for (let s = frame - 30; s <= frame; s++) {
    if (hash32(s * 7 + 1) < 0.02) {   // царапина
      const r = mulberry32(s * 7 + 2);
      const life = 6 + Math.floor(r() * 25);
      if (frame < s + life) {
        const x0 = r() * W, w = rangeOf(r(), 0.8, 2.2), a = r() * 0.35, b = rangeOf(r(), 0.55, 1), drift = (r() - 0.5) * 1.4, wob = r() * 6;
        const x = x0 + drift * (frame - s) + wob * Math.sin((frame - s) * 0.9);
        const id = `sc${s}`;
        els.push(
          <g key={id}>
            <defs>
              <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
                <stop offset={0} stopColor={light} stopOpacity={0} />
                <stop offset={a} stopColor={light} stopOpacity={1} />
                <stop offset={b} stopColor={light} stopOpacity={1} />
                <stop offset={1} stopColor={light} stopOpacity={0} />
              </linearGradient>
            </defs>
            <rect x={x} y={0} width={w} height={H} fill={`url(#${id})`} />
          </g>,
        );
      }
    }
    if (s > frame - 8 && hash32(s * 11 + 4) < 0.006) {   // волосок
      const r = mulberry32(s * 11 + 5);
      const life = 3 + Math.floor(r() * 6);
      if (frame < s + life) {
        const x = r() * W, y = r() * H, len = rangeOf(r(), 40, 140), ang = r() * Math.PI, bend = rangeOf(r(), -40, 40);
        const x1 = x + Math.cos(ang) * len, y1 = y + Math.sin(ang) * len, cx = (x + x1) / 2 - Math.sin(ang) * bend, cy = (y + y1) / 2 + Math.cos(ang) * bend;
        els.push(<path key={`h${s}`} d={`M${x} ${y} Q${cx} ${cy} ${x1} ${y1}`} stroke={onPaper ? "rgba(22,25,31,.35)" : "rgba(10,8,6,.55)"} strokeWidth={1.4} fill="none" />);
      }
    }
  }
  if (hash32(frame * 13 + 5) < 0.12) {   // пыль: крапины на один кадр
    const r = mulberry32(frame * 13 + 6);
    const n = 2 + Math.floor(r() * 4);
    for (let i = 0; i < n; i++) {
      const dark = r() < 0.6;
      els.push(<circle key={`d${i}`} cx={r() * W} cy={r() * H} r={rangeOf(r(), 0.8, 2.6)} fill={dark ? "rgba(10,8,6,.5)" : "rgba(255,250,235,.4)"} />);
    }
  }
  if (!els.length) return null;
  return (
    <svg width={W} height={H} style={{ position: "absolute", inset: 0, opacity: strength, pointerEvents: "none" }}>{els}</svg>
  );
};

/** Засветка (выключена по замечанию владельца 16.09: читалась как вспышка; оставлена на случай film.leaks в будущем). */
const Leak: React.FC<{ t: number; strength: number }> = ({ t, strength }) => {
  const cycle = 30, k = Math.floor(t / cycle);
  const r = mulberry32(k * 101 + 9);
  const start = k * cycle + r() * (cycle - 3) + 1.5, dur = 1.6;
  const p = (t - start) / dur;
  if (p < 0 || p > 1) return null;
  const env = Math.sin(Math.PI * p);
  const side = Math.floor(r() * 4);   // 0 слева, 1 справа, 2 сверху, 3 снизу
  const warm = r() < 0.7;
  const c1 = warm ? "rgba(255,150,60,.95)" : "rgba(255,70,110,.85)", c2 = warm ? "rgba(255,90,30,.5)" : "rgba(255,140,60,.45)";
  const ang = side === 0 ? 90 : side === 1 ? 270 : side === 2 ? 180 : 0;
  const shift = (p - 0.5) * 30;   // проплывает
  return (
    <AbsoluteFill style={{ opacity: 0.28 * strength * env, mixBlendMode: "screen", pointerEvents: "none",
      transform: side < 2 ? `translateX(${(side === 0 ? 1 : -1) * shift}%)` : `translateY(${(side === 2 ? 1 : -1) * shift}%)`,
      background: `linear-gradient(${ang}deg, ${c1} 0%, ${c2} 22%, rgba(255,120,40,0) 48%)` }} />
  );
};

/** Окно гейта: статичная PNG-маска с тёмными скруглёнными неровными краями (make_film.py); на бумаге — слабее. */
const Gate: React.FC<{ paper: number; strength: number }> = ({ paper, strength }) => (
  <Img src={frameMask} style={{ position: "absolute", inset: 0, width: "100%", height: "100%", opacity: strength * (1 - 0.6 * paper), pointerEvents: "none" }} />
);

/** Виньетка: на медиа тёмная (архив сильнее), на бумаге — тёплая слабая. Смешивается по «бумажности». */
const Vignette: React.FC<{ paper: number; strength: number; archive: boolean }> = ({ paper, strength, archive }) => (
  <>
    {paper < 0.99 && (
      <AbsoluteFill style={{ opacity: (1 - paper) * strength, pointerEvents: "none",
        background: `radial-gradient(ellipse at center, rgba(0,0,0,0) 45%, rgba(0,0,0,${archive ? 0.5 : 0.45}) 100%)` }} />
    )}
    {paper > 0.01 && (
      <AbsoluteFill style={{ opacity: paper * strength, pointerEvents: "none",
        background: "radial-gradient(ellipse at center, rgba(60,40,20,0) 55%, rgba(60,40,20,.2) 100%)" }} />
    )}
  </>
);
