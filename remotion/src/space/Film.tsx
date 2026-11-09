import React from "react";
import { AbsoluteFill, Audio, Sequence, staticFile, useCurrentFrame } from "remotion";
import { S, TAGS, Shot, SpaceSpec, seg } from "./theme";
import { Sky, SVG_SCENES, PhotoLayer } from "./scenes";

/** Один кадр раскадровки: фон, сцена, метка достоверности, источник, название главы. Входит наплывом S.fade секунд. */
const ShotView: React.FC<{ shot: Shot; first: boolean }> = ({ shot, first }) => {
  const f = useCurrentFrame();
  const t = f / S.fps, dur = shot.end - shot.start;
  const Scene = SVG_SCENES[shot.type];
  const photo = shot.type === "photo";
  const o = first ? 1 : seg(t, 0, S.fade);
  const tag = shot.tag ? TAGS[shot.tag] : null;
  return (
    <AbsoluteFill style={{ opacity: o }}>
      {photo ? <PhotoLayer t={t} dur={dur} data={shot.data} /> : (
        <svg width={S.W} height={S.H} viewBox={`0 0 ${S.W} ${S.H}`} style={{ position: "absolute", inset: 0 }}>
          <Sky grid={shot.type === "compare" || shot.type === "bars" || shot.type === "measure"} />
          {Scene ? <Scene t={t} dur={dur} data={shot.data} /> : <text x={100} y={100} fill="red" fontSize={40}>unknown scene {shot.type}</text>}
        </svg>
      )}
      {shot.kicker && (
        <div style={{ position: "absolute", left: 96, top: 54, fontFamily: S.mono, fontWeight: 700, fontSize: 24, letterSpacing: 4,
          color: S.dim, textTransform: "uppercase", textShadow: photo ? "0 1px 10px rgba(0,0,0,0.9)" : undefined }}>{shot.kicker}</div>
      )}
      {tag && (
        <div style={{ position: "absolute", right: 96, bottom: 54, display: "flex", alignItems: "center", gap: 12, fontFamily: S.mono, fontWeight: 700,
          fontSize: 24, letterSpacing: 3, color: tag.color, opacity: seg(t, 0.3, 0.8), textShadow: "0 1px 10px rgba(0,0,0,0.9)" }}>
          <span style={{ width: 12, height: 12, borderRadius: 6, background: tag.color, display: "inline-block" }} />{tag.text}
        </div>
      )}
      {shot.source && (
        <div style={{ position: "absolute", left: 96, bottom: 56, maxWidth: 1200, fontFamily: S.body, fontWeight: 500, fontSize: 22,
          color: S.dim, opacity: seg(t, 0.4, 0.9), textShadow: "0 1px 10px rgba(0,0,0,0.9)" }}>{shot.source}</div>
      )}
    </AbsoluteFill>
  );
};

/** Лист просмотра: кадр N = сцена N на 80% её длины (space_ep.sheet). */
export const SpaceSheet: React.FC<{ spec: SpaceSpec }> = ({ spec }) => {
  const f = useCurrentFrame();
  const s = spec.shots[Math.min(f, spec.shots.length - 1)];
  const dur = s.end - s.start;
  const local = Math.max(0, Math.min(dur - 0.2, dur * 0.8));
  return (
    <AbsoluteFill style={{ background: S.bg }}>
      <Sequence from={-Math.round(local * S.fps) + f} layout="none">
        <ShotView shot={s} first />
      </Sequence>
    </AbsoluteFill>
  );
};

export const SpaceFilm: React.FC<{ spec: SpaceSpec }> = ({ spec }) => {
  const fadeF = Math.round(S.fade * S.fps);
  return (
    <AbsoluteFill style={{ background: S.bg }}>
      {spec.shots.map((s, i) => {
        const from = Math.round(s.start * S.fps);
        const to = Math.round(s.end * S.fps) + (i + 1 < spec.shots.length ? fadeF : 0);
        return (
          <Sequence key={s.id} from={from} durationInFrames={Math.max(1, to - from)} layout="none">
            <ShotView shot={s} first={i === 0} />
          </Sequence>
        );
      })}
      {spec.voice && <Audio src={staticFile(spec.voice)} />}
      {spec.music && <Audio src={staticFile(spec.music.src)} volume={spec.music.volume} loop />}
    </AbsoluteFill>
  );
};
