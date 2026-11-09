import React from "react";
import { AbsoluteFill } from "remotion";
import { S, rng } from "./theme";

/** Аватар и баннер космического канала: тот же язык, что в роликах — крошечная точка рядом с огромным диском. */
export type BrandSpec = { name: string; mark?: string; tagline?: string; variant?: string };

const Disc: React.FC<{ cx: number; cy: number; r: number; color: string }> = ({ cx, cy, r, color }) => (
  <g>
    <defs>
      <radialGradient id={"bd" + Math.round(r)} cx="42%" cy="40%" r="62%">
        <stop offset="0%" stopColor="#fff" stopOpacity={0.85} /><stop offset="28%" stopColor={color} /><stop offset="100%" stopColor={color} stopOpacity={0.7} />
      </radialGradient>
      <radialGradient id={"bh" + Math.round(r)} cx="50%" cy="50%" r="50%">
        <stop offset="78%" stopColor={color} stopOpacity={0.4} /><stop offset="100%" stopColor={color} stopOpacity={0} />
      </radialGradient>
    </defs>
    <circle cx={cx} cy={cy} r={r * 1.14} fill={`url(#bh${Math.round(r)})`} />
    <circle cx={cx} cy={cy} r={r} fill={`url(#bd${Math.round(r)})`} />
  </g>
);

const Stars: React.FC<{ w: number; h: number; n: number }> = ({ w, h, n }) => {
  const r = rng(11);
  return <g>{Array.from({ length: n }, (_, i) => <circle key={i} cx={r() * w} cy={r() * h} r={r() ** 3 * 2.4 + 0.4} fill="#fff" opacity={0.2 + r() * 0.5} />)}</g>;
};

export const SpaceAvatar: React.FC<{ spec: BrandSpec }> = ({ spec }) => (
  <AbsoluteFill style={{ background: S.bg }}>
    <svg width={800} height={800} viewBox="0 0 800 800">
      <rect width={800} height={800} fill={S.bg} />
      <Stars w={800} h={800} n={70} />
      <Disc cx={470} cy={430} r={250} color="#ff6b3d" />
      <circle cx={170} cy={560} r={9} fill="#ffd34d" />
      <line x1={120} y1={600} x2={720} y2={600} stroke={S.text} strokeWidth={6} opacity={0.0} />
      {spec.mark && <text x={470} y={500} textAnchor="middle" fill="#fff" fontFamily={S.display} fontWeight={800} fontSize={210} opacity={0.95}>{spec.mark}</text>}
    </svg>
  </AbsoluteFill>
);

export const SpaceBanner: React.FC<{ spec: BrandSpec }> = ({ spec }) => (
  <AbsoluteFill style={{ background: S.bg }}>
    <svg width={2560} height={1440} viewBox="0 0 2560 1440">
      <rect width={2560} height={1440} fill={S.bg} />
      <Stars w={2560} h={1440} n={420} />
      {/* безопасная зона YouTube 1546×423 по центру: текст только в ней */}
      <Disc cx={2050} cy={720} r={300} color="#ff6b3d" />
      <circle cx={1650} cy={1005} r={4} fill="#ffd34d" />
      <text x={1640} y={1050} textAnchor="end" fill={S.dim} fontFamily={S.body} fontWeight={500} fontSize={26}>the Sun, same scale</text>
      <text x={1280} y={705} textAnchor="middle" fill={S.text} fontFamily={S.display} fontWeight={800} fontSize={124}>{spec.name}</text>
      {spec.tagline && <text x={1280} y={790} textAnchor="middle" fill={S.amber} fontFamily={S.body} fontWeight={600} fontSize={46}>{spec.tagline}</text>}
    </svg>
  </AbsoluteFill>
);
