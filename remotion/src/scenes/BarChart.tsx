import { spring, useCurrentFrame, useVideoConfig } from "remotion";
import { T } from "../theme";
import { Frame, fmt, Caption, Layout, pick } from "./common";

/** Столбики растут снизу, последняя точка первой серии — красная (это то, о чём речь). */
export const BarChart: React.FC<{ d: any; caption?: string } & Layout> = ({ d, caption, vertical, card }) => {
  const f = useCurrentFrame(); const { fps } = useVideoConfig(); const L = { vertical, card };
  const series = d.series?.[0] ?? { points: [] }; const pts = (series.points ?? []) as { x: string; y: number }[];
  if (!pts.length) return <Frame vertical={vertical} card={card}><div style={{ fontFamily: T.display, fontSize: 56 }}>{d.title ?? ""}</div></Frame>;
  const max = Math.max(...pts.map((p) => p.y)) * 1.15 || 1;
  const W = pick(L, 1700, 960, 1180), H = pick(L, 470, 560, 380), gap = 26;
  const bw = (W - gap * (pts.length - 1)) / pts.length;
  return (
    <Frame vertical={vertical} card={card}>
      <div style={{ fontFamily: T.display, fontSize: pick(L, 56, 48, 44), marginBottom: card ? 20 : 36 }}>{d.title ?? ""}</div>
      <svg width={W} height={H + 70} style={{ overflow: "visible" }}>
        <line x1={0} y1={H} x2={W} y2={H} stroke={T.rule} strokeWidth={2} />
        {pts.map((p, i) => {
          const s = spring({ frame: f - i * 3, fps, config: { damping: 200, stiffness: 90 } });
          const h = (p.y / max) * H * s; const last = i === pts.length - 1;
          return (
            <g key={i}>
              <rect x={i * (bw + gap)} y={H - h} width={bw} height={h} fill={last ? T.red : T.ink} />
              <text x={i * (bw + gap) + bw / 2} y={H - h - 16} textAnchor="middle" fontSize={card ? 26 : 30} fontWeight={600}
                fill={T.ink} opacity={s} fontFamily={T.text}>{fmt(p.y, d.unit)}</text>
              <text x={i * (bw + gap) + bw / 2} y={H + 44} textAnchor="middle" fontSize={card ? 24 : 28} fill={T.slate} fontFamily={T.text}>{p.x}</text>
            </g>
          );
        })}
      </svg>
      <Caption text={caption} vertical={vertical} card={card} />
    </Frame>
  );
};
