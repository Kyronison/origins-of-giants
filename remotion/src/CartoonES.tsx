import { AbsoluteFill, Audio, Img, Sequence, interpolate, staticFile, useCurrentFrame } from "remotion";

/** Испанский канал (владелец 13.10): как у Built On You — только рисунок во весь кадр с лёгким движением, резкая смена каждые ~4 с,
 *  без логотипа, плашек, карточек глав и цифр; голос, музыка по желанию. Собирается orchestrator/stages/es_cartoon.py. */
export type CartoonShot = { start: number; end: number; image: string; move?: "in" | "out" | "left" | "right" };
export type CartoonSpec = { duration: number; voice: string; shots: CartoonShot[]; music?: string; musicVolume?: number };

const PAPER = "#F4F1EA";

const Shot: React.FC<{ s: CartoonShot; frames: number }> = ({ s, frames }) => {
  const f = useCurrentFrame();
  const p = interpolate(f, [0, Math.max(1, frames)], [0, 1], { extrapolateRight: "clamp" });
  const m = s.move ?? "in";
  const scale = m === "out" ? 1.12 - 0.08 * p : m === "in" ? 1.03 + 0.09 * p : 1.08;
  const x = m === "left" ? 2.5 - 5 * p : m === "right" ? -2.5 + 5 * p : 0;
  return (
    <AbsoluteFill style={{ background: PAPER, overflow: "hidden" }}>
      <Img src={staticFile(s.image)} style={{ width: "100%", height: "100%", objectFit: "cover", transform: `scale(${scale}) translateX(${x}%)` }} />
    </AbsoluteFill>
  );
};

export const CartoonES: React.FC<{ spec: CartoonSpec; fps?: number }> = ({ spec }) => {
  const fps = 30;
  return (
    <AbsoluteFill style={{ background: PAPER }}>
      <Audio src={staticFile(spec.voice)} />
      {spec.music && <Audio src={staticFile(spec.music)} volume={spec.musicVolume ?? 0.05} loop />}
      {spec.shots.map((s, i) => {
        const from = Math.round(s.start * fps);
        const dur = Math.max(1, Math.round(s.end * fps) - from);
        return <Sequence key={i} from={from} durationInFrames={dur}><Shot s={s} frames={dur} /></Sequence>;
      })}
    </AbsoluteFill>
  );
};
