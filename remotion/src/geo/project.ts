import { GeoProjection, geoMercator, geoNaturalEarth1 } from "d3-geo";
import land from "./land50.json";

/** Проекция карты (§2.4): geoMercator для region/country, geoNaturalEarth1 для world; fitExtent по bbox точек
 *  с полями 35 %, минимальный bbox 40 км. Камера: масштаб ×0.55 от целевого → 1.0 — translate пересчитывается так,
 *  чтобы центр bbox оставался на месте. Суша — Natural Earth 50m (land50.json, make_geo.py), бандлится в код. */
export type Pt = { lon: number; lat: number };
export type Ring = [number, number][];
type Poly = { rings: Ring[]; bbox: [number, number, number, number] };

const KM_LAT = 111;
const kmLon = (lat: number) => KM_LAT * Math.max(0.2, Math.cos((lat * Math.PI) / 180));

/** bbox точек [lon0, lat0, lon1, lat1], растянутый до минимального размера minKm. */
export const bboxOf = (pts: Pt[], minKm = 40): [number, number, number, number] => {
  let x0 = Math.min(...pts.map((p) => p.lon)), x1 = Math.max(...pts.map((p) => p.lon));
  let y0 = Math.min(...pts.map((p) => p.lat)), y1 = Math.max(...pts.map((p) => p.lat));
  const cy = (y0 + y1) / 2;
  const minLat = minKm / KM_LAT, minLon = minKm / kmLon(cy);
  if (y1 - y0 < minLat) { const c = cy; y0 = c - minLat / 2; y1 = c + minLat / 2; }
  if (x1 - x0 < minLon) { const c = (x0 + x1) / 2; x0 = c - minLon / 2; x1 = c + minLon / 2; }
  return [x0, y0, x1, y1];
};

/** Разброс точек, км (по диагонали bbox без минимума). */
export const spreadKm = (pts: Pt[]): number => {
  if (pts.length < 2) return 0;
  const x0 = Math.min(...pts.map((p) => p.lon)), x1 = Math.max(...pts.map((p) => p.lon));
  const y0 = Math.min(...pts.map((p) => p.lat)), y1 = Math.max(...pts.map((p) => p.lat));
  const dx = (x1 - x0) * kmLon((y0 + y1) / 2), dy = (y1 - y0) * KM_LAT;
  return Math.sqrt(dx * dx + dy * dy);
};

export type Camera = { proj: GeoProjection; scale: number; translate: [number, number]; center: [number, number]; bbox: [number, number, number, number] };

export type Extent = [[number, number], [number, number]];

/** Целевая проекция под кадр w×h; extent — прямоугольник кадра, куда вписывается bbox (по умолчанию поля 35 %). */
export const fitProjection = (zoom: string, pts: Pt[], w: number, h: number, extent?: Extent, pad = 0.35): Camera => {
  const world = zoom === "world";
  const proj = world ? geoNaturalEarth1() : geoMercator();
  const bbox = bboxOf(pts);
  const [x0, y0, x1, y1] = bbox;
  // d3-geo: внешнее кольцо по часовой стрелке, иначе полигон = «весь мир минус bbox» и fit покажет глобус
  const feature: any = world
    ? { type: "Sphere" }
    : { type: "Feature", properties: {}, geometry: { type: "Polygon", coordinates: [[[x0, y0], [x0, y1], [x1, y1], [x1, y0], [x0, y0]]] } };
  const px = (w * pad) / 2, py = (h * pad) / 2;
  proj.fitExtent(world ? [[40, 40], [w - 40, h - 40]] : extent ?? [[px, py], [w - px, h - py]], feature);
  const center: [number, number] = [(x0 + x1) / 2, (y0 + y1) / 2];
  return { proj, scale: proj.scale(), translate: proj.translate() as [number, number], center, bbox };
};

/** Проекция «камеры»: масштаб ×c от целевого, центр bbox стоит на месте. */
export const cameraProjection = (cam: Camera, c: number, zoom: string, w = 1920, h = 1080): GeoProjection => {
  const proj = zoom === "world" ? geoNaturalEarth1() : geoMercator();
  const pc = cam.proj(cam.center) as [number, number];
  const t: [number, number] = [pc[0] + c * (cam.translate[0] - pc[0]), pc[1] + c * (cam.translate[1] - pc[1])];
  proj.scale(cam.scale * c).translate(t);
  // режем по кадру с запасом: континент за кадром не проецируется каждый кадр
  if (zoom !== "world") proj.clipExtent([[-w * 0.05, -h * 0.05], [w * 1.05, h * 1.05]]);
  return proj;
};

/** Полигоны суши с bbox — считаются один раз на модуль. */
const POLYS: Poly[] = ((land as any).features[0].geometry.coordinates as Ring[][]).map((rings) => {
  let x0 = 180, y0 = 90, x1 = -180, y1 = -90;
  for (const [x, y] of rings[0]) { if (x < x0) x0 = x; if (x > x1) x1 = x; if (y < y0) y0 = y; if (y > y1) y1 = y; }
  return { rings, bbox: [x0, y0, x1, y1] };
});

/** Суша, попадающая в географический bbox (для world — вся). */
export const landIn = (bbox: [number, number, number, number] | null): any => {
  const polys = bbox
    ? POLYS.filter((p) => p.bbox[2] >= bbox[0] && p.bbox[0] <= bbox[2] && p.bbox[3] >= bbox[1] && p.bbox[1] <= bbox[3])
    : POLYS;
  return { type: "MultiPolygon", coordinates: polys.map((p) => p.rings) };
};

/** Географический bbox видимой области при камере c (по углам кадра). */
export const visibleBbox = (proj: GeoProjection, w: number, h: number): [number, number, number, number] | null => {
  const a = proj.invert?.([0, 0]), b = proj.invert?.([w, h]);
  if (!a || !b || !isFinite(a[0]) || !isFinite(b[0]) || !isFinite(a[1]) || !isFinite(b[1])) return null;
  const lat = (v: number) => Math.max(-85, Math.min(85, v));   // Меркатор: за ±85° сетка даёт NaN
  return [Math.min(a[0], b[0]) - 1, lat(Math.min(a[1], b[1]) - 1), Math.max(a[0], b[0]) + 1, lat(Math.max(a[1], b[1]) + 1)];
};

/** Шаг сетки по размаху видимой области, градусы. */
export const graticuleStep = (bbox: [number, number, number, number] | null): number => {
  if (!bbox) return 15;
  const span = Math.max(bbox[2] - bbox[0], bbox[3] - bbox[1]);
  return span < 2 ? 0.25 : span < 5 ? 0.5 : span < 15 ? 1 : span < 60 ? 5 : 15;
};

/** Длина отрезка km на широте lat в пикселях текущей проекции. */
export const kmToPx = (proj: GeoProjection, lon: number, lat: number, km: number): number => {
  const a = proj([lon, lat]), b = proj([lon + km / kmLon(lat), lat]);
  return a && b ? Math.abs(b[0] - a[0]) : 0;
};
