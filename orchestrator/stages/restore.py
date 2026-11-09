"""Реставрация архива перед рендером (аудит 18.09: единственное, что дал бы DaVinci Resolve Studio, — Super Scale и шумодав на старых
клипах; то же на fal без $295 и без процесса Resolve). Клипы ниже RESTORE_MIN_H — Topaz Precision видео, фото меньше RESTORE_MIN_PHOTO
по длинной стороне — Topaz Precision фото (High Fidelity V3, БЕЗ улучшения лиц).
Проверено глазами на архиве Amazon 18.09 (data/board/restore): генеративные SeedVR2 и CodeFormer дорисовывают лица реальных людей
(на групповом фото Принстона 1986 лица 20 px стали чужими, у портрета Мигеля Безоса поменялись глаза и губы), Recraft Crisp их искажает.
Для документалки это подмена — только неизменяющий апскейл.
Файл заменяется на месте (имя в timeline то же), оригинал — рядом с суффиксом .orig; сделанное — в restore.json, повторный запуск ничего не тратит.
Ошибка на одном файле не валит этап: остаётся оригинал (и повторяется при следующем запуске)."""
import json, math, shutil, subprocess, threading
from concurrent.futures import ThreadPoolExecutor
from .. import config

VIDEO_MODEL = "topaz/upscale/video/precision"
PHOTO_MODEL = "topaz/upscale/image/precision"
VIDEO_PRICE_10S = 0.20      # $ за 10 с выхода ≤1080p (страница fal 18.09)
PHOTO_PRICE = 0.08          # $ за фото до 24 МП
_lock = threading.Lock()


def _refs(scenes: list[dict]) -> set[str]:
    """Все файлы архива/стока, на которые ссылается таймлайн (сцены и их слоты)."""
    out = set()
    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k in ("src", "image") and isinstance(v, str) and v.split("/")[0] in ("archive", "stock"): out.add(v)
                else: walk(v)
        elif isinstance(o, list):
            for v in o: walk(v)
    walk(scenes)
    return out


def _dims(path) -> tuple[int, int]:
    s = subprocess.check_output([config.ffprobe(), "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                                 "-of", "csv=p=0", str(path)]).decode().strip().split(",")
    return int(s[0]), int(s[1])


def _dur(path) -> float:
    return float(subprocess.check_output([config.ffprobe(), "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)]))


def _people_scene(rel: str, scenes: list[dict]) -> bool:
    """Клип из people-сцены или портретного слота — видеомодель под лица (Iris: чистит, не меняя черт)."""
    for s in scenes:
        blob = json.dumps(s, ensure_ascii=False)
        if rel in blob: return s.get("type") == "people" or "_p_" in rel
    return "_p_" in rel


def video(src, out, model: str = "Proteus", factor: float = 2.0) -> None:
    import fal_client, requests
    url = fal_client.upload_file(str(src))
    r = fal_client.subscribe(VIDEO_MODEL, arguments={"video_url": url, "model": model, "upscale_factor": factor, "H264_output": True})
    out.write_bytes(requests.get(r["video"]["url"], timeout=600).content)


def photo(src, out, long_side: int) -> None:
    import fal_client, requests
    from PIL import Image
    w, h = Image.open(src).size
    factor = min(4.0, max(1.5, round(long_side / max(w, h), 2)))
    r = fal_client.subscribe(PHOTO_MODEL, arguments={"image_url": fal_client.upload_file(str(src)), "upscale_factor": factor, "model": "High Fidelity V3",
                                                     "face_enhancement": False, "output_format": "png"})
    tmp = out.with_suffix(".restore.png"); tmp.write_bytes(requests.get(r["image"]["url"], timeout=300).content)
    im = Image.open(tmp).convert("RGB"); tmp.unlink(missing_ok=True)
    if out.suffix.lower() in (".jpg", ".jpeg"): im.save(out, "JPEG", quality=94)
    else: im.save(out)


def run(vid: str, d, tl: dict) -> dict:
    """Возвращает {"clips": n, "photos": n, "usd": ~}. RESTORE_MIN_H / RESTORE_MIN_PHOTO — пороги, RESTORE_ARCHIVE=0 — выключить."""
    from PIL import Image
    log_p = d / "restore.json"
    done = json.loads(config.read(log_p)) if log_p.exists() else {}
    # сколько секунд файл реально на экране: короткий проходной кадр тянуть Topaz-ом незачем (разбор 20.09)
    secs: dict = {}
    for sc in tl["scenes"]:
        dur = float(sc.get("end", 0)) - float(sc.get("start", 0))
        for sl in (sc.get("slots") or [sc]):
            for key in ("src", "image"):
                rel = sl.get(key)
                if rel: secs[rel] = secs.get(rel, 0.0) + dur
    jobs = []
    for rel in sorted(_refs(tl["scenes"]), key=lambda r: -secs.get(r, 0.0)):
        p = d / rel
        if rel in done or not p.exists(): continue
        if secs.get(rel, 0.0) < config.RESTORE_MIN_SEC: continue
        try:
            if p.suffix.lower() == ".mp4":
                w, h = _dims(p)
                if h < config.RESTORE_MIN_H: jobs.append(("video", rel, w, h))
            else:
                w, h = Image.open(p).size
                if max(w, h) < config.RESTORE_MIN_PHOTO: jobs.append(("photo", rel, w, h))
        except Exception as e: print(f"[restore] {rel}: не читается ({str(e)[:60]})")
    left = max(0, config.RESTORE_MAX_JOBS - len(done))   # лимит на РОЛИК, не на запуск: иначе каждый перерендер добирал ещё 10 файлов по ~$1.2 (аудит 23.09)
    if len(jobs) > left:
        print(f"[restore] кандидатов {len(jobs)}, уже сделано {len(done)}, беру {left} самых заметных")
        jobs = jobs[:left]
    if not jobs: return {"clips": 0, "photos": 0, "usd": 0.0}
    cost = {"usd": 0.0, "clips": 0, "photos": 0}

    def one(job):
        kind, rel, w, h = job; p = d / rel; orig = p.with_name(p.stem + ".orig" + p.suffix)
        face = _people_scene(rel, tl["scenes"])
        try:
            if not orig.exists(): shutil.copy2(p, orig)
            tmp = p.with_name(p.stem + ".up" + p.suffix)
            if kind == "video":
                factor = 2.0 if h * 2 <= 1080 else round(1080 / h, 2)   # 480p → 960p, 320×240 → 480p (не 4× сразу: на 480p Topaz советует 2× за проход)
                model = "Iris" if face else "Proteus"
                video(orig, tmp, model, factor)
                nw, nh = _dims(tmp)
                with _lock: cost["usd"] += VIDEO_PRICE_10S * math.ceil(_dur(orig) / 10); cost["clips"] += 1
                info = {"kind": kind, "model": f"{VIDEO_MODEL}:{model}", "from": [w, h], "to": [nw, nh]}
            else:
                photo(orig, tmp, config.RESTORE_PHOTO_TARGET)
                nw, nh = Image.open(tmp).size
                with _lock: cost["usd"] += PHOTO_PRICE; cost["photos"] += 1
                info = {"kind": kind, "model": PHOTO_MODEL + ":HFv3", "from": [w, h], "to": [nw, nh]}
            tmp.replace(p)
            with _lock: done[rel] = info
            print(f"[restore] {rel}: {w}×{h} → {info['to'][0]}×{info['to'][1]} ({info['model'].split('/')[-1]})", flush=True)
        except Exception as e:
            print(f"[restore] {rel}: оставлен оригинал, повторю при следующем рендере — {str(e)[:120]}", flush=True)

    with ThreadPoolExecutor(4) as ex: list(ex.map(one, jobs))
    config.write(log_p, json.dumps(done, ensure_ascii=False, indent=1))
    print(f"[restore] клипов {cost['clips']}, фото {cost['photos']}, ≈${cost['usd']:.2f}", flush=True)
    return {"clips": cost["clips"], "photos": cost["photos"], "usd": round(cost["usd"], 3)}
