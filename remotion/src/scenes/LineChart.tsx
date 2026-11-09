import { interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { T } from "../theme";
import { Frame, fmt, Caption, Layout, pick } from "./common";

/** Линии прочерчиваются за 1.2 сек; до трёх серий: чернила, серый, красный. */
export const LineChart: React.FC<{ d: any; caption?: string } & Layout> = ({ d, caption, vertical, card }) => {
  const f = useCurrentFrame(); const { fps } = useVideoConfig(); const L = { vertical, card };
  const series = (d.series ?? []).filter((s: any) => s?.points?.length);
  if (!series.length) return <Frame vertical={vertical} card={card}><div style={{ fontFamily: T.display, fontSize: 56 }}>{d.title ?? ""}</div></Frame>;
  const W = pick(L, 1700, 960, 1180), H = pick(L, 470, 560, 380);
  const all = series.flatMap((s: any) => s.points.map((p: any) => p.y));
  const min = Math.min(0, ...all), max = Math.max(...all) * 1.1 || 1;
  const xs = series[0].points.map((p: any) => p.x);
  const X = (i: number) => (xs.length > 1 ? (i / (xs.length - 1)) * W : W / 2), Y = (v: number) => H - ((v - min) / (max - min)) * H;
  const prog = interpolate(f, [0, fps * 1.2], [0, 1], { extrapolateRight: "clamp" });
  const colors = [T.ink, T.slate, T.red];
  return (
    <Frame vertical={vertical} card={card}>
      <div style={{ fontFamily: T.display, fontSize: pick(L, 56, 48, 44), marginBottom: card ? 20 : 36 }}>{d.title ?? ""}</div>
      <svg width={W} height={H + 70} style={{ overflow: "visible" }}>
        <line x1={0} y1={Y(0)} x2={W} y2={Y(0)} stroke={T.rule} strokeWidth={2} />
        {series.map((s: any, k: number) => {
          const path = s.points.map((p: any, i: number) => `${i ? "L" : "M"}${X(i)},${Y(p.y)}`).join(" ");
          const len = 4000; const lastI = s.points.length - 1;
          return (
            <g key={k}>
              <path d={path} fill="none" stroke={colors[k % 3]} strokeWidth={6} strokeLinecap="round" strokeLinejoin="round"
                strokeDasharray={len} strokeDashoffset={len * (1 - prog)} />
              {prog >= 1 && <>
                <circle cx={X(lastI)} cy={Y(s.points[lastI].y)} r={10} fill={colors[k % 3]} />
                <text x={Math.min(X(lastI) + 18, W - 260)} y={Y(s.points[lastI].y) - 18} fontSize={card ? 26 : 30} fontWeight={600} fill={colors[k % 3]} fontFamily={T.text}>
                  {s.name} {fmt(s.points[lastI].y, d.unit)}</text>
              </>}
            </g>
          );
        })}
        {xs.map((x: string, i: number) => (
          <text key={i} x={X(i)} y={H + 44} textAnchor={i === 0 ? "start" : i === xs.length - 1 ? "end" : "middle"} fontSize={card ? 24 : 28} fill={T.slate} fontFamily={T.text}>{x}</text>
        ))}
      </svg>
      <Caption text={caption} vertical={vertical} card={card} />
    </Frame>
  );
};
