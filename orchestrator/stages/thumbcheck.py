"""Превью проверяется в том размере, в котором его видит зритель: 168×94 в ленте телефона (разбор Astra 20.09).

76% аудитории канала — мобильные. На 2560 px любое превью выглядит хорошо; решение о клике принимается по картинке
шириной с ноготь. Здесь: выбор превью → jpg под лимит YouTube (2 МБ) → уменьшение до ленты → чтение модели зрением
(что за цифра, что за слово, что происходит) → механические проверки контраста и площади лица/объекта."""
import io, json
from .. import config, llm

FEED_W = 168          # ширина превью в мобильной ленте YouTube
SHELF_W = 246         # на главной канала

def pick(d):
    """Выбранное превью: помеченное .keep владельцем, иначе thumb_2560.png / thumb_a.png.
    Выбор владельца имеет приоритет над разрешением остальных вариантов."""
    from PIL import Image
    cand = []
    keep = sorted(d.glob("thumb_*.keep"))
    if keep:
        if len(keep) != 1: raise ValueError("Несколько отметок .keep: выберите одно превью")
        png = d / (keep[0].stem + ".png")
        if not png.exists(): raise FileNotFoundError(f"Выбранное превью отсутствует: {png.name}")
        with Image.open(png) as im: im.verify()
        return png
    cand += [d / n for n in ("thumb_2560.png", "thumb_a.png") if (d / n).exists()]
    if not cand: return None
    def w(p):
        try: return Image.open(p).width
        except Exception: return 0
    return max(cand, key=w)

def prepare(d) -> dict:
    """publish/thumbnail_2560.jpg под лимит 2 МБ и publish/thumbnail_feed.png — как в ленте телефона."""
    from PIL import Image
    src = pick(d)
    if not src: return {"ok": False, "why": "превью не найдено"}
    out = d / "publish"; out.mkdir(exist_ok=True)
    im = Image.open(src).convert("RGB")
    if im.width < 1280: return {"ok": False, "why": f"превью всего {im.width}px шириной"}
    big = im if im.width <= 2560 else im.resize((2560, round(2560 * im.height / im.width)), Image.LANCZOS)
    jpg = out / "thumbnail_2560.jpg"
    for q in (95, 90, 85, 80, 72):
        big.save(jpg, "JPEG", quality=q, optimize=True)
        if jpg.stat().st_size <= 2 * 1024 * 1024: break
    feed = im.resize((FEED_W, round(FEED_W * im.height / im.width)), Image.LANCZOS)
    feed.save(out / "thumbnail_feed.png")
    im.resize((SHELF_W, round(SHELF_W * im.height / im.width)), Image.LANCZOS).save(out / "thumbnail_shelf.png")
    return {"ok": True, "src": src.name, "kb": round(jpg.stat().st_size / 1024), "size": f"{im.width}x{im.height}"}

def _contrast(png_bytes: bytes) -> dict:
    """Механика: разброс яркости и доля самых тёмных/светлых пикселей. Плоское превью в ленте сливается с фоном."""
    from PIL import Image, ImageStat
    im = Image.open(io.BytesIO(png_bytes)).convert("L")
    st = ImageStat.Stat(im)
    hist = im.histogram()
    n = sum(hist) or 1
    dark = sum(hist[:40]) / n; light = sum(hist[215:]) / n
    return {"stddev": round(st.stddev[0], 1), "dark": round(dark, 3), "light": round(light, 3)}

def readable(d, title: str, expect: str, vid: str = "") -> dict:
    """Что видно в ленте: модель читает уменьшенное превью и говорит, какая цифра и какое слово читаются.
    expect — главное число или слово, ради которого превью и сделано."""
    p = prepare(d)
    if not p.get("ok"): return {"ok": False, "notes": [p.get("why", "нет превью")]}
    feed = (d / "publish" / "thumbnail_feed.png").read_bytes()
    shelf = (d / "publish" / "thumbnail_shelf.png").read_bytes()
    res = llm.ask_vision(
        "Это превью ролика YouTube в том размере, в каком его видит зритель в ленте телефона (первая картинка, 168 px) "
        "и на главной канала (вторая, 246 px). Название ролика под превью: \"" + title + "\".\n"
        "Смотри как обычный зритель, не увеличивай мысленно. Верни JSON:\n"
        '{"numbers": ["цифры, которые реально читаются"], "words": ["слова, которые реально читаются"], '
        '"subject": "что изображено, одной фразой", "faces": "сколько лиц различимо", '
        '"readable": true|false, "clutter": true|false, "why": "что мешает, одно предложение"}',
        [feed, shelf], tag="thumbfeed_" + vid, model=config.LLM_MODEL_VISION)
    if any(type(res.get(k)) is not bool for k in ("readable", "clutter")):
        raise ValueError("Проверка превью вернула неполный ответ")
    c = _contrast(feed)
    notes = []
    got = " ".join([" ".join(res.get("numbers") or []), " ".join(res.get("words") or [])]).lower()
    want = (expect or "").lower().strip()
    norm = lambda x: x.replace(" ", "").replace("$", "").replace(",", "")   # модель читает «10.4b» без знака доллара — это не «не читается» (22.09)
    if want and want not in got and norm(want) not in norm(got):
        notes.append("в ленте не читается главное: «" + expect + "» (модель видит: " + (got or "ничего") + ")")
    if not res.get("readable"): notes.append("нечитаемо в ленте: " + str(res.get("why", "")))
    if res.get("clutter"): notes.append("перегружено деталями: " + str(res.get("why", "")))
    if c["stddev"] < 45: notes.append(f"плоский контраст (разброс яркости {c['stddev']} при норме от 45)")
    if c["dark"] > 0.6: notes.append("превью почти чёрное — в тёмной теме сольётся с фоном")
    out = {"ok": not notes, "notes": notes, "vision": res, "contrast": c, "file": p}
    print("[thumb] " + ("в ленте читается: " + got[:80] if not notes else "; ".join(notes)), flush=True)
    return out

def check(vid: str) -> dict:
    """Проверка превью готового ролика: главное число берём из брифа, иначе из названия."""
    from .. import db
    import re
    v = db.get(vid); d = db.video_dir(vid)
    b = v["payload"].get("brief") or {}
    title = v["title"] or ""
    expect = ""
    tv = v["payload"].get("thumbv") or {}   # обложка «до → после»: в ленте должна читаться её правая цифра, а не расчёт брифа
    if tv.get("hook2") and (d / "thumb_a.keep").exists() and (d / "thumb_a.keep").read_text(encoding="utf-8", errors="replace").startswith("thumbv"):
        expect = str(tv["hook2"])
    keep = (d / "thumb_a.keep").read_text(encoding="utf-8", errors="replace") if (d / "thumb_a.keep").exists() else ""
    if keep.startswith("variant"):   # обложки thumbx: главное в ленте — узнать компанию, число там может не стоять вовсе
        expect = str((v["payload"].get("thumbx") or {}).get("company") or "").split(" ")[0]
    if keep.startswith("thumbrec"):   # 27.09 шаблоны Astra: в ленте должен читаться текст обложки
        expect = str((v["payload"].get("thumbrec") or {}).get("text") or "").replace("|", " ").split(" ")[0]
    if keep.startswith("thumbrec poster"):   # 08.10 «плакат»: в ленте должен читаться знак бренда, строка формулы мелкая намеренно
        expect = str((v["payload"].get("thumbrec") or {}).get("company") or "").split(" ")[0]
    m = None if expect else re.search(r"\$?\d[\d.,]*\s?(?:billion|million|trillion|B|M|K|%)?", (b.get("original_calculation") or {}).get("result", "") or title)
    if m: expect = m.group(0).strip()
    r = readable(d, title, expect, vid)
    config.write(d / "publish" / "thumbnail_check.json", json.dumps(r, ensure_ascii=False, indent=1))
    return r
