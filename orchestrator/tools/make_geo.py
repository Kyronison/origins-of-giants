"""Суша для MapScene: Natural Earth 50m land → упрощённый GeoJSON remotion/src/geo/land50.json (~600 КБ).

110m не годится: залив Сан-Франциско на нём исчезает, а SF–Cupertino — самый частый случай глав Origins.
Упрощение здесь же, на Python (Дуглас–Пекер + отсев мелких островов + округление координат), без mapshaper.
Данные public domain. Запуск один раз: python -m orchestrator.tools.make_geo [--tol 0.02]
"""
import argparse
import json
import math
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "remotion" / "src" / "geo" / "land50.json"
import sys; sys.path.insert(0, str(ROOT))
from orchestrator import config   # данные проекта с 18.09 на E: (DATA_DIR в .env)
CACHE = config.DATA / "cache" / "ne_50m_land.geojson"
URLS = [
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_land.geojson",
    "https://raw.githubusercontent.com/martynafford/natural-earth-geojson/master/50m/physical/ne_50m_land.json",
]
TARGET_KB = 600


def fetch() -> dict:
    if CACHE.exists() and CACHE.stat().st_size > 100_000:
        return json.loads(CACHE.read_text(encoding="utf8"))
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    last = None
    for u in URLS:
        try:
            print(f"[geo] скачиваю {u}")
            with urllib.request.urlopen(u, timeout=120) as r:
                raw = r.read()
            CACHE.write_bytes(raw)
            return json.loads(raw.decode("utf8"))
        except Exception as e:  # noqa: BLE001
            last = e
            print(f"[geo] не вышло: {e}")
    raise SystemExit(f"[geo] не удалось скачать Natural Earth: {last}")


def _dist2(p, a, b) -> float:
    """Квадрат расстояния от точки до отрезка ab (в градусах — для отбора вершин этого достаточно)."""
    ax, ay = a; bx, by = b; px, py = p
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return (px - ax) ** 2 + (py - ay) ** 2
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return (px - ax - t * dx) ** 2 + (py - ay - t * dy) ** 2


def simplify(pts: list, tol: float) -> list:
    """Дуглас–Пекер, итеративно (кольца бывают по 10 000 точек — рекурсия упрётся в лимит)."""
    if len(pts) < 3:
        return pts
    keep = [False] * len(pts); keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    t2 = tol * tol
    while stack:
        i, j = stack.pop()
        if j <= i + 1:
            continue
        best, bi = 0.0, -1
        for k in range(i + 1, j):
            d = _dist2(pts[k], pts[i], pts[j])
            if d > best:
                best, bi = d, k
        if best > t2:
            keep[bi] = True
            stack.append((i, bi)); stack.append((bi, j))
    return [p for p, k in zip(pts, keep) if k]


def ring_area(r: list) -> float:
    return abs(sum(r[i][0] * r[(i + 1) % len(r)][1] - r[(i + 1) % len(r)][0] * r[i][1] for i in range(len(r)))) / 2


def process(fc: dict, tol: float, min_area: float, digits: int) -> dict:
    polys = []
    for f in fc["features"]:
        g = f["geometry"]
        parts = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        for poly in parts:
            rings = []
            for i, ring in enumerate(poly):
                if ring_area(ring) < (min_area if i == 0 else min_area * 2):
                    if i == 0:
                        break
                    continue
                s = simplify(ring, tol)
                if len(s) < 4:
                    continue
                s = [[round(x, digits), round(y, digits)] for x, y in s]
                if s[0] != s[-1]:
                    s.append(s[0])
                rings.append(s)
            if rings:
                polys.append(rings)
    return {"type": "FeatureCollection",
            "features": [{"type": "Feature", "properties": {}, "geometry": {"type": "MultiPolygon", "coordinates": polys}}]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tol", type=float, default=0.02, help="допуск Дугласа–Пекера, градусы")
    ap.add_argument("--min-area", type=float, default=0.004, help="отсев островов мельче, кв. градусов")
    ap.add_argument("--digits", type=int, default=3)
    a = ap.parse_args()
    fc = fetch()
    tol = a.tol
    for _ in range(6):   # подгоняем допуск под целевой размер
        out = process(fc, tol, a.min_area, a.digits)
        txt = json.dumps(out, separators=(",", ":"))
        kb = len(txt.encode()) // 1024
        n = sum(len(r) for p in out["features"][0]["geometry"]["coordinates"] for r in p)
        print(f"[geo] tol={tol:.4f}: {kb} КБ, {n} вершин, {len(out['features'][0]['geometry']['coordinates'])} полигонов")
        if kb <= TARGET_KB * 1.1 or tol > 0.2:
            break
        tol *= math.sqrt(kb / TARGET_KB)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(txt, encoding="utf8")
    print(f"[geo] записан {OUT} ({kb} КБ)")


# --- подробный берег под одну карту -------------------------------------------------------------------------------
# 50m годится для стран и мира, но на городской карте (Сан-Франциско → Маунтин-Вью) у залива 59 вершин — грубые многоугольники.
# Для карт с разбросом до DETAIL_MAX_KM оркестратор вырезает Natural Earth 10m под видимую область и кладёт в scene.data.land.
CACHE10 = config.DATA / "cache" / "ne_10m_land.geojson"
URL10 = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_10m_land.geojson"
DETAIL_MAX_KM = 600
_polys10 = None


def _load10():
    global _polys10
    if _polys10 is None:
        if not (CACHE10.exists() and CACHE10.stat().st_size > 1_000_000):
            CACHE10.parent.mkdir(parents=True, exist_ok=True)
            req = urllib.request.Request(URL10, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=300) as r:
                raw = r.read(); need = int(r.headers.get("Content-Length") or 0)
            if need and len(raw) != need: raise IOError(f"ne_10m_land оборван: {len(raw)} из {need} байт")   # через VPN рвалось на 8.8 из 9.7 МБ
            CACHE10.write_bytes(raw)
        try: fc = json.loads(CACHE10.read_text(encoding="utf8"))
        except ValueError: CACHE10.unlink(missing_ok=True); raise
        _polys10 = []
        for f in fc["features"]:
            g = f["geometry"]
            for poly in (g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]):
                xs = [x for x, _ in poly[0]]; ys = [y for _, y in poly[0]]
                _polys10.append((poly, (min(xs), min(ys), max(xs), max(ys))))
    return _polys10


def _clip_ring(ring: list, box) -> list:
    """Сазерленд–Ходжмен по прямоугольнику; порядок обхода сохраняется (d3-geo различает сушу и «мир минус суша» по нему)."""
    x0, y0, x1, y1 = box
    edges = [(lambda p: p[0] >= x0, lambda a, b: (x0, a[1] + (b[1] - a[1]) * (x0 - a[0]) / (b[0] - a[0]))),
             (lambda p: p[0] <= x1, lambda a, b: (x1, a[1] + (b[1] - a[1]) * (x1 - a[0]) / (b[0] - a[0]))),
             (lambda p: p[1] >= y0, lambda a, b: (a[0] + (b[0] - a[0]) * (y0 - a[1]) / (b[1] - a[1]), y0)),
             (lambda p: p[1] <= y1, lambda a, b: (a[0] + (b[0] - a[0]) * (y1 - a[1]) / (b[1] - a[1]), y1))]
    out = [tuple(p) for p in (ring[:-1] if ring and ring[0] == ring[-1] else ring)]
    for inside, cut in edges:
        if not out: break
        src, out = out, []
        prev = src[-1]
        for cur in src:
            if inside(cur):
                if not inside(prev): out.append(cut(prev, cur))
                out.append(cur)
            elif inside(prev):
                out.append(cut(prev, cur))
            prev = cur
    return out


def detail(pts: list[dict]) -> list | None:
    """Суша 10m под карту по её точкам: bbox (минимум 40 км, как bboxOf в project.ts) × запас на широкую камеру (×0.55) и inset.
    Возвращает coordinates MultiPolygon или None (мировая/большая карта — хватает 50m)."""
    pts = [p for p in pts or [] if isinstance(p.get("lat"), (int, float)) and isinstance(p.get("lon"), (int, float))]
    if not pts: return None
    lat0, lat1 = min(p["lat"] for p in pts), max(p["lat"] for p in pts)
    lon0, lon1 = min(p["lon"] for p in pts), max(p["lon"] for p in pts)
    cy, cx = (lat0 + lat1) / 2, (lon0 + lon1) / 2
    k_lon = 111 * max(0.2, math.cos(math.radians(cy)))
    s_km = max(40.0, (lat1 - lat0) * 111, (lon1 - lon0) * k_lon)
    if s_km > DETAIL_MAX_KM: return None
    # видимая область при камере 0.55 и вписывании левее inset — до ~5 bbox по ширине и ~3 по высоте; берём с запасом
    hw, hh = 3.4 * s_km / k_lon, 2.4 * s_km / 111
    box = (cx - hw, cy - hh, cx + hw, cy + hh)
    tol = (2 * s_km / 111) / 1600          # ~полпикселя на финальной камере
    digits = 4 if s_km < 150 else 3
    polys = []
    for poly, (bx0, by0, bx1, by1) in _load10():
        if bx1 < box[0] or bx0 > box[2] or by1 < box[1] or by0 > box[3]: continue
        rings = []
        for i, ring in enumerate(poly):
            c = _clip_ring(ring, box)
            if len(c) < 3:
                if i == 0: break
                continue
            c = simplify(c + [c[0]], tol)
            if len(c) < 4:
                if i == 0: break
                continue
            c = [[round(x, digits), round(y, digits)] for x, y in c]
            if c[0] != c[-1]: c.append(c[0])
            rings.append(c)
        if rings: polys.append(rings)
    return polys or None


if __name__ == "__main__":
    main()
