import { AbsoluteFill } from "remotion";
import { loadFont as loadGrotesk } from "@remotion/google-fonts/SpaceGrotesk";
import { loadFont as loadAnton } from "@remotion/google-fonts/Anton";

/** Второй канал (испанский) — направление «Neón», выбор владельца 22.09: глубокий синий, электрический жёлтый, гротеск.
 *  Отдельная система от английского канала (там тёмная сцена с лампой, бумага и антиква).
 *  Avatar 800×800 (круг), Banner 2560×1440 (текст в безопасной зоне 1546×423 по центру), Watermark 150×150 (прозрачный). */
const gk = loadGrotesk("normal", { weights: ["500", "700"], subsets: ["latin"] });
const an = loadAnton("normal", { weights: ["400"], subsets: ["latin"] });
export const N = { navy: "#0B1B33", ink: "#071224", yellow: "#FFD500", white: "#FFFFFF", mist: "#9FB0C8", grid: "rgba(255,255,255,.045)", sans: gk.fontFamily, display: an.fontFamily };
export type BrandES = { name: string; tagline: string; word?: string };

const Grid: React.FC = () => (
  <AbsoluteFill style={{ backgroundImage: `linear-gradient(${N.grid} 1px, transparent 1px), linear-gradient(90deg, ${N.grid} 1px, transparent 1px)`, backgroundSize: "80px 80px" }} />
);

/** Аватар: жёлтый круг, чёрно-синяя «G» с засечкой-подчёркиванием — читается в 32 px в комментариях. */
export const AvatarES: React.FC<BrandES> = ({ word = "G" }) => (
  <AbsoluteFill style={{ background: N.yellow, alignItems: "center", justifyContent: "center" }}>
    <div style={{ fontFamily: N.sans, fontWeight: 700, fontSize: 470, lineHeight: 1, color: N.navy, letterSpacing: -20, marginTop: -30 }}>{word}</div>
    <div style={{ position: "absolute", bottom: 150, width: 200, height: 26, background: N.navy }} />
  </AbsoluteFill>
);

/** Шапка: синее поле, жёлтая полоса сверху, название в безопасной зоне, справа знак «$ → $$$». */
export const BannerES: React.FC<BrandES> = ({ name, tagline }) => {
  const [a, b] = name.includes(" de ") ? [name.split(" de ")[0] + " de", name.split(" de ").slice(1).join(" de ")] : [name, ""];
  return (
    <AbsoluteFill style={{ background: N.navy }}>
      <Grid />
      <div style={{ position: "absolute", left: 0, right: 0, top: 0, height: 22, background: N.yellow }} />
      {/* безопасная зона 1546×423: x 507–2053, y 508–931 */}
      <div style={{ position: "absolute", left: 540, top: 528, width: 1000 }}>
        <div style={{ fontFamily: N.sans, fontWeight: 700, fontSize: 150, lineHeight: 0.95, letterSpacing: -6, color: N.white }}>{a}</div>
        <div style={{ fontFamily: N.sans, fontWeight: 700, fontSize: 150, lineHeight: 0.95, letterSpacing: -6, color: N.yellow }}>{b}</div>
        <div style={{ fontFamily: N.sans, fontWeight: 500, fontSize: 40, color: N.mist, marginTop: 28 }}>{tagline}</div>
      </div>
      <div style={{ position: "absolute", left: 1660, top: 604, width: 380, height: 230, border: `6px solid ${N.yellow}`, borderRadius: 18, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 10 }}>
        <div style={{ fontFamily: N.display, fontSize: 96, lineHeight: 1, color: N.yellow, letterSpacing: 2 }}>$ → $$$</div>
        <div style={{ fontFamily: N.sans, fontWeight: 500, fontSize: 26, color: N.mist, letterSpacing: 4 }}>CADA DÍA · 19:00 CDMX</div>
      </div>
    </AbsoluteFill>
  );
};

/** Водяной знак поверх видео: жёлтый квадрат с «G», без фона. */
export const WatermarkES: React.FC<BrandES> = ({ word = "G" }) => (
  <AbsoluteFill style={{ alignItems: "center", justifyContent: "center" }}>
    <div style={{ width: 120, height: 120, borderRadius: 22, background: N.yellow, display: "flex", alignItems: "center", justifyContent: "center", opacity: 0.9 }}>
      <div style={{ fontFamily: N.sans, fontWeight: 700, fontSize: 84, color: N.navy, lineHeight: 1, marginTop: -6 }}>{word}</div>
    </div>
  </AbsoluteFill>
);
