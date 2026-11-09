import { continueRender, delayRender, staticFile } from "remotion";

/** Шрифты — локальные файлы из папки выпуска (public/fonts, кладёт space_ep.build): 24.10 браузер рендера остался без сети,
 *  и загрузка Google Fonts роняла рендер. Sora, Inter, JetBrains Mono — переменные woff2 (OFL). */
const FONT_FILES: [string, string][] = [["SpaceSora", "fonts/sora.woff2"], ["SpaceInter", "fonts/inter.woff2"], ["SpaceMono", "fonts/jbmono.woff2"]];
if (typeof document !== "undefined") {
  const h = delayRender("space fonts");
  Promise.all(FONT_FILES.map(([family, file]) =>
    new FontFace(family, `url(${staticFile(file)})`, { weight: "100 900" }).load().then((f) => { (document as any).fonts.add(f); })))
    .then(() => continueRender(h))
    .catch((e) => { console.error("font load failed", e); continueRender(h); });
}

/** Космический канал (23.10.2026): тёмное небо, тонкие светлые линии, один янтарный акцент для главного числа.
 *  Все размеры и расстояния приходят из Python (orchestrator/stages/space_physics.py) уже посчитанными. */
export const S = {
  W: 1920, H: 1080, fps: 30,
  bg: "#060A14", bg2: "#0C1426", grid: "rgba(140,170,230,0.07)",
  text: "#EAF0FF", dim: "#8D99B8", faint: "#4A5675",
  amber: "#FFB547", cyan: "#6FD3FF", red: "#FF5A4F", green: "#5BE39B", violet: "#B69CFF",
  display: "SpaceSora, sans-serif", body: "SpaceInter, sans-serif", mono: "SpaceMono, monospace",
  fade: 0.4,
};

/** Метка достоверности в углу кадра: установленное знание отделено от оценок и гипотез. */
export const TAGS: Record<string, { text: string; color: string }> = {
  established: { text: "ESTABLISHED", color: S.green },
  estimate: { text: "ESTIMATE · UNCERTAIN", color: S.amber },
  hypothesis: { text: "HYPOTHESIS · DEBATED", color: S.violet },
  calc: { text: "OUR CALCULATION", color: S.cyan },
  thought: { text: "THOUGHT EXPERIMENT", color: S.cyan },
  illustration: { text: "ILLUSTRATION", color: S.dim },
};

export type Shot = {
  id: string; type: string; start: number; end: number; data: any;
  tag?: string | null; source?: string | null; kicker?: string | null;
};
export type SpaceSpec = {
  duration: number; voice?: string | null; music?: { src: string; volume: number } | null;
  shots: Shot[]; title?: string; channel?: string;
};

export const clamp = (x: number, a = 0, b = 1) => Math.max(a, Math.min(b, x));
export const ease = (x: number) => { const t = clamp(x); return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2; };
export const easeOut = (x: number) => 1 - Math.pow(1 - clamp(x), 3);
export const seg = (t: number, a: number, b: number) => clamp((t - a) / Math.max(1e-6, b - a));
export const lerp = (a: number, b: number, t: number) => a + (b - a) * t;

/** Детерминированный генератор для звёздного фона. */
export const rng = (seed: number) => () => { seed = (seed * 1664525 + 1013904223) % 4294967296; return seed / 4294967296; };

/** «1,420» → 1420; «1.3 million» → 1.3e6. Для счётчика в Stat. */
export const parseNum = (s: string): number | null => {
  const m = /^([\d,]*\.?\d+)\s*(million|billion)?$/i.exec(s.trim());
  if (!m) return null;
  const v = parseFloat(m[1].replace(/,/g, ""));
  return m[2] ? v * (m[2].toLowerCase() === "million" ? 1e6 : 1e9) : v;
};
/** Форматирует промежуточное значение счётчика так же, как итоговая строка (запятые, знаки после точки, слово). */
export const fmtLike = (target: string, v: number): string => {
  const m = /^([\d,]*\.?\d+)\s*(million|billion)?$/i.exec(target.trim());
  if (!m) return target;
  const word = m[2] ? " " + m[2] : "";
  const base = m[2] ? v / (m[2].toLowerCase() === "million" ? 1e6 : 1e9) : v;
  const dec = (m[1].split(".")[1] || "").length;
  const comma = m[1].includes(",");
  const s = base.toLocaleString("en-US", { minimumFractionDigits: dec, maximumFractionDigits: dec, useGrouping: comma });
  return s + word;
};
