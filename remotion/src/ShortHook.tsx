import { AbsoluteFill, Audio, Easing, Img, Loop, OffthreadVideo, Sequence, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { loadFont as loadAnton } from "@remotion/google-fonts/Anton";
import { D, Tag } from "./dossier";
import { ScoreAudio } from "./Main";
import type { Score } from "./theme";
import { ShortStory } from "./ShortStory";
import type { StoryPanel } from "./ShortStory";
import grain0 from "./film/grain_0.png";
import grain1 from "./film/grain_1.png";
import grain2 from "./film/grain_2.png";
import grain3 from "./film/grain_3.png";

/** Shorts «новость → полное видео» (владелец 17.09). Вертикаль 1080×1920, темп — кадр каждые 1–2.5 с:
 *  каждый кадр входит «ударом» (наезд 1.16 → 1 за 7 кадров) и дальше двигается; субтитры по 1–3 слова крупным Anton,
 *  ключевые слова и числа — на оксбладовой плашке; числа отдельно выбиваются бумажным ярлыком сверху; кадры прошлого («then») —
 *  сепия, зерно и штамп года (контраст «сейчас / тогда»); в конце всплывает превью полного видео со стрелкой к ссылке «связанное видео».
 *  Безопасные зоны Shorts: низ ~22 % (название, канал, ссылка), справа ~140 px (кнопки), верх ~8 % — текст туда не ставим. */
const anton = loadAnton("normal", { weights: ["400"], subsets: ["latin"] });
const TILES = [grain0, grain1, grain2, grain3];

export type HookShot = {
  start: number; end: number; image?: string | null; src?: string | null; kind: "now" | "then"; aspect?: number | null;
  focus_xy?: [number, number] | null; year?: number | null; move?: string; clip_seconds?: number | null; credit?: string | null;
};
export type HookWord = { w: string; s: number; e: number; hot?: boolean };
export type HookSpec = {
  style?: "calm-story-v1"; story_panels?: StoryPanel[];
  duration: number; voice: string; music?: { src: string; volume: number; offset?: number } | null;
  shots: HookShot[]; captions: { start: number; end: number; words: HookWord[] }[];
  flashes: { start: number; end: number; value: string; label?: string | null }[];
  end: { start: number; thumb?: string | null; line1: string; line2: string; play?: "mr" | "br" }; channel: string;
  score?: Score | null;   // партитура (stages/sound.py): вместо одного трека
};

const OUTLINE = [[4, 0], [-4, 0], [0, 4], [0, -4], [3, 3], [-3, 3], [3, -3], [-3, -3]].map(([x, y]) => `${x}px ${y}px 0 #0d0a08`).join(", ") + ", 0 10px 24px rgba(0,0,0,.55)";

const Shot: React.FC<{ shot: HookShot; len: number; prevKind?: string }> = ({ shot, len, prevKind }) => {
  const f = useCurrentFrame(); const { fps } = useVideoConfig();
  const p = Math.min(1, f / Math.max(1, len));
  const punch = interpolate(f, [0, 7], [0.16, 0], { extrapolateRight: "clamp", easing: Easing.out(Easing.cubic) });
  const then = shot.kind === "then";
  const rewind = then && prevKind !== "then" ? interpolate(f, [0, 12], [0.4, 0], { extrapolateRight: "clamp", easing: Easing.out(Easing.quad) }) : 0;
  const m = shot.move ?? "in";
  const base = m === "out" ? 1.14 - 0.1 * p : m === "detail" ? 1.3 + 0.12 * p : 1.04 + 0.09 * p;
  const tx = m === "left" ? 4 - 8 * p : m === "right" ? -4 + 8 * p : 0;
  const [fx, fy] = shot.focus_xy ?? [0.5, 0.45];
  const scale = base + punch + rewind;
  const grade = then ? `sepia(${0.5 - 0.2 * (1 - Math.min(1, f / 12))}) saturate(0.55) contrast(1.1) brightness(0.93)` : "contrast(1.07) saturate(1.1)";
  const boxed = then && !shot.src && (shot.aspect ?? 1) > 1.15;   // горизонтальный архивный снимок — отпечаток на размытой подложке
  const media = (style: React.CSSProperties) => {
    if (shot.src) {
      const v = <OffthreadVideo src={staticFile(shot.src)} muted style={style} />;
      const clip = shot.clip_seconds ? Math.floor(shot.clip_seconds * fps) : 0;
      return clip && clip < len ? <Loop durationInFrames={clip}>{v}</Loop> : v;
    }
    return <Img src={staticFile(shot.image!)} style={style} />;
  };
  const cover: React.CSSProperties = { position: "absolute", width: "100%", height: "100%", objectFit: "cover", objectPosition: `${fx * 100}% ${fy * 100}%`,
    transform: `translateX(${tx}%) scale(${scale})`, transformOrigin: `${fx * 100}% ${fy * 100}%`, filter: grade };
  if (!boxed) return <AbsoluteFill style={{ background: D.dark, overflow: "hidden" }}>{media(cover)}</AbsoluteFill>;
  // отпечаток крупно (ширина 1010, по высоте до 1000) на подложке из того же снимка — без пустого серого поля и шума (владелец: «не шум»)
  const asp = shot.aspect ?? 1.5; const bw = Math.min(1010, Math.round(1000 * asp)), bh = Math.round(bw / asp);
  return (
    <AbsoluteFill style={{ background: D.dark, overflow: "hidden" }}>
      {media({ ...cover, transform: `scale(${1.5 + punch})`, filter: `${grade} blur(22px) brightness(0.72)` })}
      <div style={{ position: "absolute", left: (1080 - bw) / 2 - 14, top: 700 - bh / 2, width: bw, height: bh, border: `14px solid ${D.photo}`,
        boxShadow: "0 30px 70px rgba(0,0,0,.55)", overflow: "hidden", transform: `rotate(${-1.5 + p}deg) scale(${1 + punch * 0.6 + rewind * 0.5})` }}>
        {media({ ...cover, transform: `scale(${1.02 + 0.06 * p})` })}
      </div>
    </AbsoluteFill>
  );
};

const Grain: React.FC<{ opacity: number }> = ({ opacity }) => {
  const f = useCurrentFrame();
  if (opacity <= 0) return null;
  return <Img src={TILES[Math.floor(f / 2) % TILES.length]} style={{ position: "absolute", inset: 0, width: "100%", height: "100%", objectFit: "cover", mixBlendMode: "overlay", opacity }} />;
};

const Captions: React.FC<{ caps: HookSpec["captions"] }> = ({ caps }) => {
  const f = useCurrentFrame(); const { fps } = useVideoConfig(); const t = f / fps;
  const c = caps.find((x) => t >= x.start && t < x.end);
  if (!c) return null;
  const pop = spring({ frame: Math.round((t - c.start) * fps), fps, config: { damping: 11, stiffness: 260, mass: 0.6 } });
  return (
    <div style={{ position: "absolute", left: 60, right: 150, top: 1060, display: "flex", flexWrap: "wrap", justifyContent: "center", alignItems: "center",
      gap: "6px 22px", transform: `scale(${0.82 + 0.18 * pop})`, transformOrigin: "50% 50%" }}>
      {c.words.map((w, k) => {
        const on = t >= w.s - 0.04;
        const txt = w.w.replace(/[“”"]/g, "");
        return w.hot ? (
          <span key={k} style={{ fontFamily: anton.fontFamily, fontSize: 118, lineHeight: 1.08, textTransform: "uppercase", color: D.cream, background: D.ox,
            padding: "0 18px 4px", transform: "rotate(-2deg)", boxShadow: "0 12px 30px rgba(0,0,0,.45)", opacity: on ? 1 : 0.55 }}>{txt}</span>
        ) : (
          <span key={k} style={{ fontFamily: anton.fontFamily, fontSize: 112, lineHeight: 1.08, textTransform: "uppercase", color: on ? "#FFFFFF" : "rgba(255,255,255,.62)", textShadow: OUTLINE }}>{txt}</span>
        );
      })}
    </div>
  );
};

const Flash: React.FC<{ value: string; label?: string | null; len: number }> = ({ value, label, len }) => {
  const f = useCurrentFrame(); const { fps } = useVideoConfig();
  const s = spring({ frame: f, fps, config: { damping: 10, stiffness: 230, mass: 0.7 } });
  const out = interpolate(f, [len - 5, len], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const shake = f < 8 ? Math.sin(f * 2.4) * (8 - f) * 0.9 : 0;
  return (
    <div style={{ position: "absolute", left: 0, right: 0, top: 300, display: "flex", justifyContent: "center", opacity: out }}>
      <div style={{ transform: `translateX(${shake}px) scale(${0.35 + 0.65 * s}) rotate(-3deg)` }}>
        <Tag style={{ padding: "18px 44px 22px", textAlign: "center" }}>
          <div style={{ fontFamily: D.serif, fontWeight: 700, fontSize: 170, lineHeight: 1, color: D.brown }}>{value}</div>
          {label && <div style={{ fontFamily: D.mono, fontWeight: 700, fontSize: 38, letterSpacing: 3, color: D.ox, textTransform: "uppercase", marginTop: 8 }}>{label}</div>}
        </Tag>
      </div>
    </div>
  );
};

const YearStamp: React.FC<{ year: number }> = ({ year }) => {
  const f = useCurrentFrame(); const { fps } = useVideoConfig();
  const s = spring({ frame: f - 3, fps, config: { damping: 9, stiffness: 200 } });
  return (
    <div style={{ position: "absolute", left: 70, top: 250, transform: `scale(${s}) rotate(-6deg)`, transformOrigin: "0 0" }}>
      <Tag><div style={{ fontFamily: D.mono, fontWeight: 700, fontSize: 64, letterSpacing: 4, color: D.ox }}>{year}</div></Tag>
    </div>
  );
};

const EndCard: React.FC<{ end: HookSpec["end"] }> = ({ end }) => {
  const f = useCurrentFrame(); const { fps } = useVideoConfig();
  const dim = interpolate(f, [0, 8], [0, 0.74], { extrapolateRight: "clamp" });
  const s = spring({ frame: f - 3, fps, config: { damping: 11, stiffness: 150, mass: 0.9 } });
  const rot = interpolate(s, [0, 1], [-9, -2]);
  const tag = spring({ frame: f - 12, fps, config: { damping: 10, stiffness: 220 } });
  const line = spring({ frame: f - 18, fps, config: { damping: 12, stiffness: 200 } });
  const bob = Math.sin((f / fps) * 7) * 14;
  return (
    <AbsoluteFill>
      <AbsoluteFill style={{ background: `rgba(18,13,10,${dim})` }} />
      <div style={{ position: "absolute", left: 0, right: 0, top: 330, display: "flex", justifyContent: "center", transform: `scale(${tag}) rotate(-3deg)` }}>
        <Tag><div style={{ fontFamily: D.mono, fontWeight: 700, fontSize: 52, letterSpacing: 6, color: D.ox, textTransform: "uppercase" }}>{end.line1}</div></Tag>
      </div>
      {end.thumb && (
        <div style={{ position: "absolute", left: 60, top: 500, width: 960, height: 540, border: `16px solid ${D.photo}`, boxShadow: "0 40px 90px rgba(0,0,0,.6)",
          transform: `scale(${0.35 + 0.65 * s}) rotate(${rot}deg)`, opacity: Math.min(1, s * 1.4), overflow: "hidden" }}>
          <Img src={staticFile(end.thumb)} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
          <div style={{ position: "absolute", ...(end.play === "br" ? { right: 26, bottom: 26 } : { left: "50%", marginLeft: -60, bottom: 24 }), width: 120, height: 120, borderRadius: 60,   /* play: снизу по центру — справа посередине кнопка закрывала большую цифру обложки ($294B, Google 20.09), по центру закрывала лица, в нижнем углу — подпись-крючок ref2 */
            background: "rgba(122,46,31,.92)", display: "flex", alignItems: "center", justifyContent: "center", transform: `scale(${1 + 0.06 * Math.sin((f / fps) * 6)})` }}>
            <div style={{ width: 0, height: 0, borderTop: "27px solid transparent", borderBottom: "27px solid transparent", borderLeft: `45px solid ${D.cream}`, marginLeft: 11 }} />
          </div>
        </div>
      )}
      <div style={{ position: "absolute", left: 60, right: 60, top: 1130, textAlign: "center", fontFamily: anton.fontFamily, fontSize: 104, lineHeight: 1.05,
        color: "#FFFFFF", textTransform: "uppercase", textShadow: OUTLINE, opacity: line, transform: `translateY(${(1 - line) * 40}px)` }}>{end.line2}</div>
      {/* подписка: за 28 дней шортсы дали 1 900 просмотров и 0 подписчиков — просьбы подписаться в кадре не было (Studio, 20.09) */}
      <div style={{ position: "absolute", left: 0, right: 0, top: 1286, display: "flex", justifyContent: "center", opacity: line,
        transform: `scale(${0.8 + 0.2 * line})` }}>
        <div style={{ display: "flex", alignItems: "center", gap: 22, background: "#E3262B", borderRadius: 96, padding: "20px 46px 24px",
          boxShadow: "0 18px 44px rgba(0,0,0,.55)" }}>
          <svg width={54} height={54} viewBox="0 0 24 24" fill="#FFFFFF"><path d="M12 22a2.4 2.4 0 0 0 2.4-2.4H9.6A2.4 2.4 0 0 0 12 22zm7.2-5.6v-5.2c0-3.3-1.8-6-4.8-6.7v-.7a2.4 2.4 0 1 0-4.8 0v.7c-3 .7-4.8 3.4-4.8 6.7v5.2L2.4 18.2v1.2h19.2v-1.2l-2.4-1.8z" /></svg>
          <div style={{ fontFamily: anton.fontFamily, fontSize: 76, lineHeight: 1, color: "#FFFFFF", textTransform: "uppercase", letterSpacing: 2 }}>Subscribe</div>
        </div>
      </div>
      <svg width={260} height={300} viewBox="0 0 260 300" style={{ position: "absolute", left: 90, top: 1420 + bob, opacity: line }}>
        <path d="M200 20 C 180 140, 120 200, 50 250" stroke={D.cream} strokeWidth={16} fill="none" strokeLinecap="round" />
        <path d="M30 200 L 45 262 L 108 250" stroke={D.cream} strokeWidth={16} fill="none" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </AbsoluteFill>
  );
};

const LegacyShortHook: React.FC<{ spec: HookSpec }> = ({ spec }) => {
  const { fps } = useVideoConfig(); const f = useCurrentFrame(); const t = f / fps;
  const endF = Math.round(spec.end.start * fps), total = Math.ceil(spec.duration * fps);
  const cur = spec.shots.find((s) => t >= s.start && t < s.end);
  const blur = interpolate(f, [endF, endF + 10], [0, 16], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const vol = spec.music?.volume ?? 0;
  return (
    <AbsoluteFill style={{ background: D.dark }}>
      <Audio src={staticFile(spec.voice)} />
      {spec.score ? <ScoreAudio score={spec.score} /> : spec.music && (
        <Audio src={staticFile(spec.music.src)} startFrom={Math.round((spec.music.offset ?? 0) * fps)}
          volume={(fr) => vol * interpolate(fr, [0, 6, total - fps, total], [0, 1, 1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" })} />
      )}
      <AbsoluteFill style={{ filter: blur ? `blur(${blur}px)` : undefined }}>
        {spec.shots.map((s, k) => {
          const from = Math.round(s.start * fps), len = Math.max(1, Math.round(s.end * fps) - from);
          return (
            <Sequence key={k} from={from} durationInFrames={len}>
              <Shot shot={s} len={len} prevKind={spec.shots[k - 1]?.kind} />
              {s.kind === "then" && spec.shots[k - 1]?.kind !== "then" && s.year && s.year < 2000 && <YearStamp year={s.year} />}
            </Sequence>
          );
        })}
        <Grain opacity={cur?.kind === "then" ? 0.22 : 0.08} />
        {/* виньетка — лицо и текст читаются на любом кадре */}
        <AbsoluteFill style={{ background: "radial-gradient(ellipse at 50% 45%, rgba(0,0,0,0) 45%, rgba(0,0,0,.55) 100%)" }} />
        <AbsoluteFill style={{ background: "linear-gradient(180deg, rgba(0,0,0,0) 45%, rgba(0,0,0,.35) 62%, rgba(0,0,0,0) 80%)" }} />
      </AbsoluteFill>
      {f < endF && <Captions caps={spec.captions} />}
      {spec.flashes.map((x, k) => {
        const from = Math.round(x.start * fps), len = Math.max(6, Math.round(x.end * fps) - from);
        return from < endF ? <Sequence key={k} from={from} durationInFrames={Math.min(len, endF - from)}><Flash value={x.value} label={x.label} len={Math.min(len, endF - from)} /></Sequence> : null;
      })}
      {f < fps * 2.2 && (
        <div style={{ position: "absolute", left: 60, top: 150, opacity: interpolate(f, [fps * 1.8, fps * 2.2], [1, 0], { extrapolateLeft: "clamp" }) }}>
          <Tag rotate={-2}><div style={{ fontFamily: D.mono, fontWeight: 700, fontSize: 30, letterSpacing: 3, color: D.brown, textTransform: "uppercase" }}>{spec.channel}</div></Tag>
        </div>
      )}
      <Sequence from={endF}><EndCard end={spec.end} /></Sequence>
    </AbsoluteFill>
  );
};

// Existing delivered specifications retain their appearance; new generation opts in.
export const ShortHook: React.FC<{ spec: HookSpec }> = ({ spec }) =>
  spec.style === "calm-story-v1" ? <ShortStory spec={spec} /> : <LegacyShortHook spec={spec} />;
