import { useMemo } from "react";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { geoGraticule, geoPath } from "d3-geo";
import { Slot as SlotT, T } from "../theme";
import { Slot } from "./Slot";
import { D as DS } from "../dossier";
import { Pt, cameraProjection, fitProjection, graticuleStep, kmToPx, landIn, spreadKm, visibleBbox } from "../geo/project";

/** map (§2.4): SVG-карта на бумаге — суша, сетка, точки чернилами (главная красная) с пульсом по `at`,
 *  маршрут красной пунктирной дугой с бегущей точкой, подписи с ореолом, заголовок региона, inset 640×360 справа внизу,
 *  масштабная линейка при разбросе < 20 км. Камера ×0.55 → 1.0 за 1.8 с, постоянный дрейф 0.5 %.
 *  `delay` (сек) — первый кадр главы стоит под карточкой: нулевая точка хореографии (камера, точки, маршрут, inset) сдвигается
 *  на caption_delay, под вуалью — только суша (сразу, без проявления); точки с `at` (слово диктора) идут по своему времени. */
const W = 1920, H = 1080;
// заметно темнее спецификации (#DDE1E6 / rule): грейд плёнки (contrast/sepia/тепло) съедал разницу суши и воды
const LAND = DS.land, COAST = DS.coast;   // «Архивное досье»: тёплая бумага, суша охрой   // ещё темнее: на демо суша сливалась с бумагой под выцветанием плёнки
const INSET_W = 640, INSET_H = 360 + 34;
type MapPoint = Pt & { name?: string; label?: string; at?: number | null; main?: boolean };

/** Квадратичная Безье с контрольной точкой, смещённой перпендикулярно на 12 % длины; sub-кривая до u (де Кастельжо). */
const arc = (a: [number, number], b: [number, number], u: number) => {
  const dx = b[0] - a[0], dy = b[1] - a[1], len = Math.hypot(dx, dy) || 1;
  const nx = -dy / len, ny = dx / len;
  const sign = ny < 0 ? 1 : -1;   // дуга выгибается вверх
  const c: [number, number] = [(a[0] + b[0]) / 2 + sign * nx * 0.12 * len, (a[1] + b[1]) / 2 + sign * ny * 0.12 * len];
  const c1: [number, number] = [a[0] + (c[0] - a[0]) * u, a[1] + (c[1] - a[1]) * u];
  const q = (t: number): [number, number] => [(1 - t) ** 2 * a[0] + 2 * (1 - t) * t * c[0] + t * t * b[0], (1 - t) ** 2 * a[1] + 2 * (1 - t) * t * c[1] + t * t * b[1]];
  const end = q(u);
  return { d: `M${a[0].toFixed(1)},${a[1].toFixed(1)} Q${c1[0].toFixed(1)},${c1[1].toFixed(1)} ${end[0].toFixed(1)},${end[1].toFixed(1)}`, end, len };
};

export const MapScene: React.FC<{ d: any; slots: SlotT[]; delay?: number }> = ({ d, slots, delay = 0 }) => {
  const f0 = useCurrentFrame(); const { fps } = useVideoConfig();
  const D = Math.max(0, Math.round(delay * fps));
  const f = f0 - D;            // кадр хореографии: под карточкой (f < 0) карта стоит на широкой камере
  const t = f0 / fps;
  const pts: MapPoint[] = (d.points ?? []).filter((p: any) => Number.isFinite(p?.lat) && Number.isFinite(p?.lon)).slice(0, 5);
  const zoom: string = d.zoom ?? "region";
  const inset = slots.find((s) => s.image || s.src);
  const cam = useMemo(() => {
    if (!pts.length) return null;
    if (!inset) return fitProjection(zoom, pts, W, H);
    // точки не должны прятаться под inset: вписываем bbox либо левее него, либо выше — что даст больший масштаб
    const px = W * 0.175, py = H * 0.175;
    const left = fitProjection(zoom, pts, W, H, [[px, py], [W - T.pad - INSET_W - 60, H - py]]);
    const above = fitProjection(zoom, pts, W, H, [[px, py], [W - px, H - T.pad - INSET_H - 60]]);
    return left.scale >= above.scale ? left : above;
  }, [JSON.stringify(pts.map((p) => [p.lon, p.lat])), zoom, !!inset]);
  // камера: ×0.55 → 1.0 за 1.8 с, easeOutCubic
  const cp = interpolate(f, [0, fps * 1.8], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const c = 0.55 + 0.45 * (1 - Math.pow(1 - cp, 3));
  const proj = useMemo(() => (cam ? cameraProjection(cam, c, zoom) : null), [cam, c, zoom]);
  // суша: полигоны, видимые при самой широкой камере (0.55), считаем один раз
  const wideBox = useMemo(() => (cam ? (zoom === "world" ? null : visibleBbox(cameraProjection(cam, 0.55, zoom), W, H)) : null), [cam, zoom]);
  // суша: подробный берег Natural Earth 10m, вырезанный под эту карту оркестратором (d.land), иначе общий 50m —
  // на 50m у залива Сан-Франциско 59 вершин, городская карта выглядела грубыми многоугольниками
  const land = useMemo(() => (Array.isArray(d.land) && d.land.length ? { type: "MultiPolygon", coordinates: d.land } : landIn(wideBox)), [wideBox, d.land]);
  const step = useMemo(() => graticuleStep(cam ? visibleBbox(cameraProjection(cam, 1, zoom), W, H) : null), [cam, zoom]);
  const grat = useMemo(() => {
    const g = geoGraticule().step([step, step]);
    if (wideBox) g.extent([[wideBox[0] - step, wideBox[1] - step], [wideBox[2] + step, wideBox[3] + step]]);
    return g();
  }, [step, wideBox]);
  const xyEnd = useMemo(() => { const pe = cam ? cameraProjection(cam, 1, zoom) : null; return pts.map((p) => ((pe && pe([p.lon, p.lat])) ?? [0, 0]) as [number, number]); },
    [cam, zoom, JSON.stringify(pts.map((p) => [p.lon, p.lat]))]);
  if (!cam || !proj) return <AbsoluteFill style={{ background: DS.cream }} />;
  const path = geoPath(proj);
  // под карточкой суша стоит сразу (пустой лист бумаги под вуалью — тот же «пустой кадр»); без карточки — проявляется за 20 кадров
  const landO = D > 0 ? 0.9 : interpolate(f, [0, 20], [0, 0.9], { extrapolateRight: "clamp" });
  const drift = `translate(${(Math.sin(t / 4) * 0.005 * W).toFixed(2)}px, ${(Math.cos(t / 5.3) * 0.005 * H).toFixed(2)}px)`;
  const xy = pts.map((p) => (proj([p.lon, p.lat]) ?? [0, 0]) as [number, number]);
  const mainIdx = Math.max(0, pts.findIndex((p) => p.main));
  // точка с `at` появляется на своём слове (не раньше проявления); точки без якоря — после проявления и после последней
  // синхронной точки, через 0.9 с друг за другом
  const synced = pts.map((p) => (typeof p.at === "number" ? Math.max(p.at * fps, D + fps * 0.6) : null));
  const lastSynced = Math.max(D + fps * 0.6, ...synced.filter((x): x is number => x !== null).map((x) => x + fps * 0.9));
  let k2 = 0;
  const atF = pts.map((_, k) => Math.round(synced[k] ?? (lastSynced + fps * 0.9 * k2++)));
  const route: number[] = Array.isArray(d.route) ? d.route.filter((i: any) => Number.isInteger(i) && i >= 0 && i < pts.length) : [];
  const segs = route.slice(1).map((b, k) => ({ a: route[k], b }));
  const segStart = segs.map((s) => Math.max(atF[s.a], atF[s.b]) + 2);   // сразу после появления точки k+1
  const routeDone = segs.length ? Math.max(...segStart) + fps * 1.0 : 0;
  const spread = spreadKm(pts);
  const insetIn = spring({ frame: f - 45, fps, config: { damping: 200, stiffness: 120 } });
  const barPx = spread < 20 ? kmToPx(proj, cam.center[0], cam.center[1], 5) : 0;
  // подпись справа, если не наезжает на соседнюю точку и на inset (Mountain View уходил под вставку); ширина — оценка по числу букв
  const insetBox = inset ? [W - T.pad - INSET_W - 30, H - T.pad - INSET_H - 30] : null;
  const labelPos = (k: number): "right" | "left" => {   // по финальной камере: сторона подписи не прыгает во время наезда
    const [x, y] = xyEnd[k];
    const wLab = 18 + Math.max((pts[k].name ?? "").length * 16, (pts[k].label ?? "").length * 15);
    const hitsInset = !!insetBox && x + wLab > insetBox[0] && y + 44 > insetBox[1];
    return hitsInset || xyEnd.some(([ox, oy], j) => j !== k && ox > x && ox - x < 300 && Math.abs(oy - y) < 70) ? "left" : "right";
  };
  // заголовок региона: под карточкой (D > 0) стоит сразу — после проявления карта не должна 1.5 с быть серым многоугольником без подписи
  const titleO = D > 0 ? 1 : interpolate(f, [6, 24], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  return (
    <AbsoluteFill style={{ background: DS.cream, overflow: "hidden" }}>
      <svg width={W} height={H} style={{ position: "absolute", inset: 0, transform: drift }}>
        <g opacity={landO}>
          <path d={path(grat) ?? ""} fill="none" stroke={DS.grid} strokeWidth={0.6} opacity={0.5} />
          <path d={path(land) ?? ""} fill={LAND} stroke={COAST} strokeWidth={1.2} strokeLinejoin="round" />
        </g>
        {segs.map((s, k) => {
          const u = interpolate(f0, [segStart[k], segStart[k] + fps * 1.0], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
          const e = 1 - Math.pow(1 - u, 3);
          if (e <= 0) return null;
          const { d: dd, end } = arc(xy[s.a], xy[s.b], e);
          return (
            <g key={k}>
              <path d={dd} fill="none" stroke={DS.ox} strokeWidth={3} strokeDasharray="10 8" strokeLinecap="round" />
              {e < 1 && <circle cx={end[0]} cy={end[1]} r={5} fill={DS.brown} />}
            </g>
          );
        })}
        {pts.map((p, k) => {
          const s = spring({ frame: f0 - atF[k], fps, config: { damping: 14, stiffness: 170 } });
          if (f0 < atF[k]) return null;
          const [x, y] = xy[k];
          const pulse = interpolate(f0, [atF[k], atF[k] + fps * 0.8], [0, 1], { extrapolateRight: "clamp" });
          const rise = interpolate(f0, [atF[k] + 2, atF[k] + 12], [10, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
          const lo = interpolate(f0, [atF[k] + 2, atF[k] + 12], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
          const side = labelPos(k), tx = side === "right" ? x + 18 : x - 18, anchor = side === "right" ? "start" : "end";
          const main = k === mainIdx;
          return (
            <g key={k}>
              {pulse < 1 && <circle cx={x} cy={y} r={9 + 21 * pulse} fill="none" stroke={main ? DS.ox : DS.brown} strokeWidth={2} opacity={0.6 * (1 - pulse)} />}
              <circle cx={x} cy={y} r={9 * s} fill={main ? DS.ox : DS.brown} stroke={DS.cream} strokeWidth={3} />
              <g opacity={lo} transform={`translate(0 ${rise})`}>
                <text x={tx} y={y + 8} textAnchor={anchor} fontFamily={DS.serif} fontSize={30} fontWeight={500} fill={DS.brown}
                  stroke={DS.cream} strokeWidth={6} strokeLinejoin="round" style={{ paintOrder: "stroke" }}>{p.name ?? ""}</text>
                {p.label && (
                  <text x={tx} y={y + 36} textAnchor={anchor} fontFamily={DS.mono} fontSize={24} fill={DS.coast}
                    stroke={DS.cream} strokeWidth={5} strokeLinejoin="round" style={{ paintOrder: "stroke" }}>{p.label}</text>
                )}
              </g>
            </g>
          );
        })}
      </svg>
      {/* заголовок региона */}
      {d.title && (
        <div style={{ position: "absolute", left: T.pad, top: T.pad * 1.35, fontFamily: DS.mono, fontSize: 22, letterSpacing: 6, textTransform: "uppercase", color: DS.coast, opacity: titleO }}>
          {d.title}
        </div>
      )}
      {/* подпись расстояния — в конце маршрута */}
      {d.distance_label && segs.length > 0 && f0 >= routeDone && (() => {
        const o = interpolate(f0, [routeDone, routeDone + 10], [0, 1], { extrapolateRight: "clamp" });
        const last = segs[segs.length - 1]; const [ax, ay] = xy[last.a], [bx, by] = xy[last.b];
        const mx = (ax + bx) / 2, my = (ay + by) / 2 - 0.12 * Math.hypot(bx - ax, by - ay) - 28;
        return (
          <div style={{ position: "absolute", left: mx, top: my, transform: "translate(-50%, -100%)", opacity: o, background: DS.cream, border: `1px solid ${DS.grid}`,
            padding: "6px 14px 7px", fontFamily: DS.mono, fontSize: 24, color: DS.ox, whiteSpace: "nowrap" }}>{d.distance_label}</div>
        );
      })()}
      {/* масштабная линейка при разбросе < 20 км */}
      {barPx > 20 && (
        <div style={{ position: "absolute", left: T.pad, bottom: T.pad * 1.1, opacity: landO }}>
          <div style={{ width: barPx, height: 3, background: DS.brown }} />
          <div style={{ fontFamily: DS.mono, fontSize: 20, color: DS.coast, marginTop: 6, letterSpacing: 1 }}>5 km</div>
        </div>
      )}
      {/* inset — архивный вид города на бумажной рамке */}
      {inset && f >= 45 && (   // f — с учётом delay: inset въезжает после проявления
        <div style={{ position: "absolute", right: T.pad, bottom: T.pad, width: INSET_W, height: 360 + (inset.caption ? 34 : 0), padding: 10, background: DS.cream,
          boxShadow: "0 24px 60px rgba(0,0,0,.28)", opacity: insetIn, transform: `translateY(${(1 - insetIn) * 30}px)` }}>
          <div style={{ position: "relative", width: 640, height: 360, overflow: "hidden" }}>
            <Slot slot={inset} fit="cover" w={640} h={360} push={[1, 1.06]} matte={false} drift={false} />
          </div>
          {inset.caption && <div style={{ fontFamily: DS.mono, fontSize: 20, color: DS.coast, marginTop: 8, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{inset.caption}</div>}
        </div>
      )}
    </AbsoluteFill>
  );
};
