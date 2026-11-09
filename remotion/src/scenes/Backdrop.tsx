import { AbsoluteFill, Img, interpolate, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { T } from "../theme";

/** Сгенерированная картинка на весь кадр с медленным наездом и виньеткой; инфографика — на бумажной карточке слева
 *  (узкие сцены: вертикальная раскладка 860px; графики и сравнения: card-раскладка 1300px). */
export const Backdrop: React.FC<{ image: string; children: React.ReactNode; wide?: boolean }> = ({ image, children, wide }) => {
  const f = useCurrentFrame(); const { durationInFrames, fps } = useVideoConfig();
  const zoom = interpolate(f, [0, Math.max(1, durationInFrames)], [1, 1.07]);
  const enter = interpolate(f, [fps * 0.25, fps * 0.6], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  return (
    <AbsoluteFill style={{ background: T.ink }}>
      <Img src={staticFile(image)} style={{ width: "100%", height: "100%", objectFit: "cover", transform: `scale(${zoom})` }} />
      <Vignette />
      <div style={{ position: "absolute", inset: 0, background: "linear-gradient(90deg, rgba(22,25,31,0.45) 0%, rgba(22,25,31,0) 55%)" }} />
      <div style={{
        position: "absolute", left: T.pad, top: T.pad * 1.2, bottom: T.pad * 2.4, width: wide ? 1300 : 860,
        background: T.paper, opacity: enter, transform: `translateY(${(1 - enter) * 16}px)`,
        boxShadow: "0 30px 80px rgba(0,0,0,0.35)",
      }}>
        {children}
      </div>
    </AbsoluteFill>
  );
};

/** Одна виньетка на все картинки — часть «единого видеоряда». */
export const Vignette: React.FC = () => (
  <div style={{ position: "absolute", inset: 0, background: "radial-gradient(ellipse at center, rgba(0,0,0,0) 55%, rgba(0,0,0,0.35) 100%)" }} />
);
