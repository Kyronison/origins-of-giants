import { AbsoluteFill, Audio, Sequence, staticFile, useVideoConfig } from "remotion";
import { FadeIn, Music, XFADE_SEC } from "./Main";
import { Props, T } from "./theme";
import { SceneRouter } from "./scenes/SceneRouter";
import { Subtitles } from "./Subtitles";
import { Overlays } from "./Overlays";

/** Вертикальная версия: те же сцены, вырезанный сегмент, крупные субтитры по центру. */
export const Short: React.FC<Props> = ({ timeline, words, segment }) => {
  const { fps } = useVideoConfig();
  const seg = segment ?? { start: 0, end: 10 };
  const scenes = timeline.scenes.filter((s) => s.end > seg.start && s.start < seg.end);
  const xf = Math.round(XFADE_SEC * fps);
  return (
    <AbsoluteFill style={{ background: T.paper, fontFamily: T.text, color: T.ink }}>
      {timeline.voice !== false && (
        <Audio src={staticFile("voice.mp3")} startFrom={Math.round(seg.start * fps)} endAt={Math.round(seg.end * fps)} />
      )}
      {timeline.music && <Music src={staticFile(timeline.music)} volume={(timeline.music_volume ?? 0.12) * 0.8} />}
      <div style={{ position: "absolute", top: 0, left: 0, right: 0, height: "58%" }}>
        {scenes.map((s) => (
          <Sequence key={s.id} from={Math.round((s.start - seg.start) * fps)}
            durationInFrames={Math.max(1, Math.round((Math.min(s.end, seg.end) - Math.max(s.start, seg.start)) * fps) + xf)}>
            <FadeIn frames={s.start > seg.start ? xf : 0}><SceneRouter scene={s} vertical /></FadeIn>
          </Sequence>
        ))}
      </div>
      {timeline.overlays && <Overlays overlays={timeline.overlays.filter((o) => o.end > seg.start && o.start < seg.end)} offset={seg.start} vertical />}
      {timeline.subtitles !== false && <Subtitles words={words} scenes={timeline.scenes} offset={seg.start} vertical />}
      <div style={{ position: "absolute", bottom: 72, width: "100%", textAlign: "center", fontFamily: T.display, fontSize: 34, color: T.slate }}>
        {timeline.channel}
      </div>
    </AbsoluteFill>
  );
};
