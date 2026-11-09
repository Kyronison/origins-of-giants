import { AbsoluteFill, Audio, Sequence, interpolate, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { MusicTrack, Overlay, Pause, Props, Score, T, XFADE_SEC, filmOf, xfadeSecOf } from "./theme";
import { SceneRouter } from "./scenes/SceneRouter";
import { Subtitles } from "./Subtitles";
import { Overlays } from "./Overlays";
import { Film } from "./Film";
import { D, applyTheme } from "./dossier";

export { XFADE_SEC };
/** Музыка глав без пауз (старые видео): старый трек уходит за MUSIC_XF секунд, новый входит под карточкой главы. */
export const MUSIC_XF = 2.5;

/** Слои снизу вверх (§4): контейнер сцен (weave + грейд внутри Film) → титры → зерно/мерцание/царапины/виньетка → водяной знак. */
export const Main: React.FC<Props> = ({ timeline, words }) => {
  const { fps } = useVideoConfig();
  applyTheme(timeline.theme);   // палитра титров и сцен: dossier (англ. канал) или neon (исп.)
  const film = filmOf(timeline.film);
  const scenes = timeline.scenes;
  const pauses = timeline.pauses ?? [];
  return (
    <AbsoluteFill style={{ background: T.paper, fontFamily: T.text, color: T.ink }}>
      {timeline.voice !== false && <Audio src={staticFile(timeline.voice_src ?? "voice.mp3")} />}
      {timeline.score ? <ScoreAudio score={timeline.score} /> : <>
        {timeline.music_tracks?.length
          ? <MusicTracks tracks={timeline.music_tracks} pauses={pauses} />
          : timeline.music && <Music src={staticFile(timeline.music)} volume={timeline.music_volume ?? 0.12} />}
        {timeline.sfx_chapter && timeline.overlays && <ChapterStings overlays={timeline.overlays} src={staticFile(timeline.sfx_chapter)} volume={timeline.sfx_volume} startFrom={timeline.sfx_offset} />}
      </>}
      <Film film={film} scenes={scenes} overlays={timeline.overlays}
        above={timeline.overlays && <Overlays overlays={timeline.overlays} blur={film?.blur ?? true} />}>
        {scenes.map((s, i) => {
          const last = i === scenes.length - 1;
          // сцена держится дольше на наплыв следующей: та проявляется поверх
          const xfNext = last ? 0 : Math.round(xfadeSecOf(scenes[i + 1]) * fps);
          const xf = i === 0 ? 0 : Math.round(xfadeSecOf(s) * fps);
          const mode = i === 0 ? "first" : (s.transition === "cut" || s.transition === "dip" ? s.transition : "xfade");
          return (
            <Sequence key={s.id} from={Math.round(s.start * fps)} durationInFrames={Math.max(1, Math.round((s.end - s.start) * fps) + xfNext)}>
              <FadeIn frames={xf} mode={mode}><SceneRouter scene={s} words={words} /></FadeIn>
            </Sequence>
          );
        })}
      </Film>
      {timeline.subtitles !== false && <Subtitles words={words} scenes={scenes} />}
      <Watermark channel={timeline.channel} />
    </AbsoluteFill>
  );
};

/** Вход сцены (§2.12): xfade — наплыв за frames; cut — без наплыва, 2 кадра gate-dip (brightness 0.85 — вуаль, ощущение склейки хроники);
 *  dip — первый кадр главы: предыдущая сцена держится до `at`, этот стоит с полной непрозрачностью с первого кадра — вуаль карточки
 *  (Chapter) поднимается над ним с pause.at за CHAPTER_LEAD; никакого проявления из чернил (тёмный кадр на срезе главы); first — первая сцена видео. */
export const FadeIn: React.FC<{ frames: number; mode?: "xfade" | "cut" | "dip" | "first"; children: React.ReactNode }> = ({ frames, mode = "xfade", children }) => {
  const f = useCurrentFrame();
  const o = mode === "xfade" && frames ? interpolate(f, [0, frames], [0, 1], { extrapolateRight: "clamp" }) : 1;
  return (
    <AbsoluteFill>
      <AbsoluteFill style={{ opacity: o }}>{children}</AbsoluteFill>
      {mode === "cut" && f < 2 && <AbsoluteFill style={{ background: "#000", opacity: 0.15, pointerEvents: "none" }} />}
    </AbsoluteFill>
  );
};

/** Ambient под голосом: тихо, зациклен, плавно уходит в конце. */
export const Music: React.FC<{ src: string; volume: number }> = ({ src, volume }) => {
  const { durationInFrames, fps } = useVideoConfig();
  return (
    <Audio src={src} loop volume={(f) =>
      volume * interpolate(f, [0, fps * 2, durationInFrames - fps * 4, durationInFrames], [0, 1, 1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" })} />
  );
};

const clamp01 = (x: number) => Math.max(0, Math.min(1, x));
const ramp = (t: number, a: number, b: number) => (b <= a ? (t >= b ? 1 : 0) : clamp01((t - a) / (b - a)));

/** Свой трек на каждую главу. Границы треков = pauses.at (§3.5): старый трек уходит fade-out с `at − 1.0` до `at + 0.5`,
 *  новый стартует прямо на `at` fade-in 0.8 с (прежние «в ноль к at» + старт `at + 0.6` с 1.8 с давали 0.6 с мёртвой тишины под стингером) —
 *  не с начала файла, а с `offset` (Python: первое место, где трек уже звучит в полный уровень); swell под тишиной ×2 (потолок 0.1)
 *  до `at + gap − 0.3`, затем ease к vol за 1.5 с. Последний трек уходит за 2.5 с к концу (не за 4 с — хвост не должен быть тишиной).
 *  Границы без паузы (старые видео) — прежний наплыв MUSIC_XF. */
export const MusicTracks: React.FC<{ tracks: MusicTrack[]; pauses?: Pause[]; offset?: number }> = ({ tracks, pauses = [], offset = 0 }) => {
  const { fps } = useVideoConfig();
  const near = (t: number) => pauses.find((p) => Math.abs(p.at - t) < 0.35);
  return (
    <>
      {tracks.map((t, i) => {
        const first = i === 0, last = i === tracks.length - 1;
        const pIn = first ? undefined : near(t.start), pOut = last ? undefined : near(t.end);
        const from = pIn ? pIn.at : first ? t.start : t.start - MUSIC_XF * 0.4;
        const to = pOut ? pOut.at + 0.5 : last ? t.end : t.end + MUSIC_XF * 0.6;
        const len = Math.round((to - from) * fps);
        if (len <= 0) return null;
        const startFrom = Math.max(0, Math.round((t.offset ?? 0) * fps));
        const swell = Math.min(t.volume * 2, 0.1);
        const vol = (f: number) => {
          const tt = from + f / fps;   // время в шкале таймлайна
          const fin = pIn ? ramp(tt, from, from + 0.8) : ramp(tt, from, from + (first ? 1.5 : MUSIC_XF));
          const fout = pOut ? 1 - ramp(tt, pOut.at - 1.0, pOut.at + 0.5) : 1 - ramp(tt, to - (last ? 2.5 : MUSIC_XF), to);
          let base = t.volume;
          if (pIn) {
            const hold = pIn.at + pIn.gap - 0.3;
            base = tt < hold ? swell : swell + (t.volume - swell) * ramp(tt, hold, hold + 1.5);
          }
          return base * fin * fout;
        };
        return (
          <Sequence key={i} from={Math.round((from - offset) * fps)} durationInFrames={len}>
            <Audio src={staticFile(t.src)} loop startFrom={startFrom} volume={vol} />
          </Sequence>
        );
      })}
    </>
  );
};

/** Партитура (Score): музыка × кривая громкости, эффекты, живой звук архива. Кривая линейно интерполируется между точками (шаг dt). */
export const ScoreAudio: React.FC<{ score: Score }> = ({ score }) => {
  const { fps } = useVideoConfig();
  const { dt, v } = score.curve;
  const g = (t: number) => {
    if (!v.length) return 1;
    const x = Math.max(0, t / dt), k = Math.min(v.length - 1, Math.floor(x)), k2 = Math.min(v.length - 1, k + 1);
    return v[k] + (v[k2] - v[k]) * (x - k);
  };
  return (
    <>
      {score.music.map((m, i) => {
        const len = Math.max(1, Math.round((m.end - m.start) * fps));
        const fi = Math.round((m.fade_in ?? 0) * fps), fo = Math.round((m.fade_out ?? 0) * fps);
        const ramp = (f: number) => Math.min(fi ? Math.min(1, f / fi) : 1, fo ? Math.min(1, (len - f) / fo) : 1);   // кроссфейд соседних частей
        return (
          <Sequence key={`m${i}`} from={Math.round(m.start * fps)} durationInFrames={len}>
            <Audio src={staticFile(m.src)} startFrom={Math.round((m.offset ?? 0) * fps)} volume={(f) => Math.max(0, m.gain * g(m.start + f / fps) * ramp(f))} />
          </Sequence>
        );
      })}
      {score.sfx.map((x, i) => (
        <Sequence key={`s${i}`} from={Math.round(x.at * fps)} durationInFrames={Math.max(1, Math.round((x.dur ?? 4) * fps))}>
          <Audio src={staticFile(x.src)} volume={x.volume} />
        </Sequence>
      ))}
      {score.live.map((x, i) => {
        const len = Math.max(1, Math.round(x.dur * fps));
        return (
          <Sequence key={`l${i}`} from={Math.round(x.at * fps)} durationInFrames={len}>
            <Audio src={staticFile(x.src)} volume={(f) => x.volume * interpolate(f, [0, 3, len - 5, len], [0, 1, 1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" })} />
          </Sequence>
        );
      })}
    </>
  );
};

/** Короткий музыкальный акцент на карточке главы: с pause — на `at + 0.2`, громкость `volume` (Python: sfx_volume — стингер на
 *  SFX_BELOW_DB ниже диктора; 0.45 в тишине пиковал на 10 dB громче голоса), с `startFrom` (sfx_offset: тихое вступление пропущено —
 *  атака в первые 0.3 с, а не через 2 с после карточки); без pause — как раньше. */
export const ChapterStings: React.FC<{ overlays: Overlay[]; src: string; offset?: number; volume?: number | null; startFrom?: number | null }> =
  ({ overlays, src, offset = 0, volume, startFrom }) => {
  const { fps } = useVideoConfig();
  const sf = Math.max(0, Math.round((startFrom ?? 0) * fps));
  return (
    <>
      {overlays.filter((o) => o.type === "chapter").map((o, i) => {
        const at = o.pause ? o.pause.at + 0.2 : o.start;
        const v = o.pause ? (volume ?? 0.15) : 0.6;
        return (
          <Sequence key={i} from={Math.round((at - offset) * fps)} durationInFrames={Math.round(fps * 4)}>
            <Audio src={src} startFrom={o.pause ? sf : 0} volume={(f) => v * interpolate(f, [0, fps * 3, fps * 4], [1, 1, 0], { extrapolateRight: "clamp" })} />
          </Sequence>
        );
      })}
    </>
  );
};

const Watermark: React.FC<{ channel: string }> = ({ channel }) => (
  <div style={{ position: "absolute", top: T.pad * 0.5, left: T.pad, fontFamily: D.serif, fontSize: 26, color: D.muted, textShadow: "0 1px 4px rgba(0,0,0,.5)" }}>
    {channel}
  </div>
);
