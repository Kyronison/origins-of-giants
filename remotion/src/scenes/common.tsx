import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { T } from "../theme";

export const useEnter = (delay = 0) => {
  const f = useCurrentFrame(); const { fps } = useVideoConfig();
  return spring({ frame: f - delay, fps, config: { damping: 200, stiffness: 120 } });
};

/** Единственный «жест» канала: красная линия, которая прочерчивается слева направо. */
export const RedRule: React.FC<{ width?: number; delay?: number }> = ({ width = 220, delay = 8 }) => {
  const s = useEnter(delay);
  return <div style={{ height: 8, width: width * s, background: T.red, marginTop: 24 }} />;
};

/** Три раскладки: полный кадр 1920×1080 (низ — полоса субтитров), вертикальная (Shorts и узкая карточка),
 *  card — широкая карточка 1300px поверх картинки (сравнения и графики). */
export type Layout = { vertical?: boolean; card?: boolean };
export const pick = <A,>(l: Layout, full: A, vertical: A, card: A): A => (l.card ? card : l.vertical ? vertical : full);

export const Frame: React.FC<{ children: React.ReactNode; align?: "left" | "center" } & Layout> = ({ children, vertical, card, align = "left" }) => (
  <div style={{ position: "absolute", inset: 0,
    padding: card ? "48px 56px" : vertical ? "56px 56px 120px" : `${T.pad * 1.4}px ${T.pad}px ${T.pad * 2.4}px`,   // низ — полоса субтитров
    display: "flex", flexDirection: "column", justifyContent: "center", alignItems: align === "center" ? "center" : "flex-start",
    textAlign: align }}>{children}</div>
);

export const Caption: React.FC<{ text?: string } & Layout> = ({ text, vertical, card }) =>
  text ? <div style={{ fontSize: pick({ vertical, card }, 30, 34, 26), color: T.slate, marginTop: card ? 18 : 28, maxWidth: 900, lineHeight: 1.35 }}>{text}</div> : null;

export const fmt = (v: number, unit = "") => {
  const s = Math.abs(v) >= 100 ? v.toFixed(0) : Math.abs(v) >= 10 ? v.toFixed(1) : v.toFixed(2);
  return unit.startsWith("$") ? `$${s}${unit.slice(1)}` : `${s}${unit}`;
};

export const fadeOut = (frame: number, total: number, fps: number) => interpolate(frame, [total - fps * 0.4, total], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
