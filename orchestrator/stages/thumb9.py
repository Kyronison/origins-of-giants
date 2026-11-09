"""Превью английского канала в стиле 9 «вещь крупно» (владелец 14.10.2026 выбрал из 14 дизайнов и велел перевести на него весь канал).

Главная вещь бренда под прожектором на чёрном справа; слева сверху — название бренда в белой плашке с полосой цвета бренда (одинаково
на всех превью: «название точно нужно, только в едином стиле»); две строки крупно по формуле названия (вторая — цветом бренда); годы.
Плюс два варианта с другими вещами — для A/B-теста в Studio (Test & Compare через Chrome владельца)."""
import colorsys, json, shutil
from pathlib import Path
from .. import config, db, llm

SCENE = ("dramatic studio photograph of {objects} on a dark table, single hard spotlight from above, deep black background, cinematic, high contrast, "
         "objects placed on the right two thirds of the frame, the left third is empty dark background. No text, no letters, no numbers, no logos anywhere.")
ASK = """YouTube-ролик о компании {company}. Название ролика: «{title}». Подбери для превью:
- objects: 2–3 узнаваемых ПРЕДМЕТА бренда по-английски для студийного фото (продукт, фирменная вещь, символ эпохи), без логотипов и надписей;
- objects_alt1, objects_alt2: ещё два ДРУГИХ набора предметов для того же ролика (для A/B-теста превью);
- year0, year1: год основания и год конца («2024») или «TODAY», если компания жива;
- line1, line2: две строки ЗАГЛАВНЫМИ (до 10 знаков каждая) по формуле названия: «The Rise and Fall…» → THE RISE / AND FALL;
  «What Happened…» → WHAT / HAPPENED?; «The Fascinating Story…» → THE FULL / STORY; иначе — коротко и интригующе по смыслу;
- brand: короткое имя бренда для плашки (Red Lobster, Toys R Us); color: фирменный цвет в hex.
Верни JSON {{"objects": "...", "objects_alt1": "...", "objects_alt2": "...", "year0": "1968", "year1": "2024", "line1": "...", "line2": "...", "brand": "...", "color": "#c41e24"}}"""
FONTS = "C:/Windows/Fonts/"


def _color(c):
    try: col = tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))
    except Exception: col = (220, 40, 40)
    lum = (0.299 * col[0] + 0.587 * col[1] + 0.114 * col[2]) / 255
    if lum < 0.45:   # тёмный фирменный цвет на чёрном не читается — тот же оттенок, яркий и насыщенный
        hh, ss, _ = colorsys.rgb_to_hsv(*(x / 255 for x in col)); col = tuple(int(x * 255) for x in colorsys.hsv_to_rgb(hh, max(ss, 0.85), 1.0))
    return col


def compose(scene: Path, info: dict, out: Path, W: int = 2560, H: int = 1440):
    from PIL import Image, ImageDraw, ImageFont, ImageOps
    k = W / 1280
    im = ImageOps.fit(Image.open(scene).convert("RGB"), (W, H), Image.LANCZOS).convert("RGBA"); dr = ImageDraw.Draw(im)
    col = _color(info.get("color") or "#c41e24")
    name = str(info.get("brand") or "").upper(); fn = ImageFont.truetype(FONTS + "impact.ttf", int(78 * k))
    x0, y0 = int(40 * k), int(40 * k); tw = dr.textlength(name, font=fn)
    dr.rectangle((x0, y0, x0 + int(72 * k) + tw, y0 + int(104 * k)), fill=(255, 255, 255))
    dr.rectangle((x0, y0, x0 + int(14 * k), y0 + int(104 * k)), fill=col)
    dr.text((x0 + int(36 * k), y0 + int(52 * k)), name, font=fn, fill=(15, 15, 15), anchor="lm")
    fi = ImageFont.truetype(FONTS + "impact.ttf", int(130 * k))
    dr.text((x0, int(230 * k)), str(info["line1"]).upper(), font=fi, fill=(255, 255, 255))
    dr.text((x0, int(370 * k)), str(info["line2"]).upper(), font=fi, fill=col + (255,))
    dr.text((int(44 * k), int(530 * k)), f"{info['year0']} – {info['year1']}", font=ImageFont.truetype(FONTS + "bahnschrift.ttf", int(60 * k)), fill=(200, 200, 200))
    im.convert("RGB").save(out)


def make(vid: str, title: str | None = None, set_main: bool = True) -> dict:
    from PIL import Image
    from . import thumbx as X
    v = db.get(vid); d = db.video_dir(vid); t = v["payload"].get("topic") or {}; work = d / "thumb9"; work.mkdir(exist_ok=True)
    title = title or v["title"]
    ip = work / "info.json"
    info = json.loads(ip.read_text(encoding="utf-8")) if ip.exists() else llm.ask_json(
        ASK.format(company=t.get("company") or t.get("hero") or title, title=title), heavy=True, max_tokens=1000, tag=f"thumb9_{vid}")
    ip.write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")
    files = {}
    for key, objs in (("main", info["objects"]), ("alt1", info.get("objects_alt1")), ("alt2", info.get("objects_alt2"))):
        if not objs: continue
        sc = work / f"scene_{key}.png"; X._gen(SCENE.format(objects=objs), sc)
        png = work / f"thumb_{key}.png"; compose(sc, info, png)
        jpg = work / f"thumb_{key}.jpg"; im = Image.open(png).convert("RGB").resize((1920, 1080), Image.LANCZOS)
        for q in (92, 86, 80):
            im.save(jpg, "JPEG", quality=q, optimize=True)
            if jpg.stat().st_size < 2 * 1024 * 1024: break
        files[key] = jpg
    if set_main:
        for f in ("thumb_a.png", "thumb_2560.png"):
            if (d / f).exists() and not (d / f"{Path(f).stem}_gen.png").exists(): shutil.copy(d / f, d / f"{Path(f).stem}_gen.png")
        im = Image.open(work / "thumb_main.png").convert("RGB")
        im.save(d / "thumb_2560.png"); im.resize((1280, 720), Image.LANCZOS).save(d / "thumb_a.png")
        (d / "thumb_a.keep").write_text(f"thumb9 {info['line1']} {info['line2']}", encoding="utf-8")
        try:
            from . import thumbcheck; thumbcheck.prepare(d)
        except Exception as e: print(f"[thumb9] подготовка превью для загрузки: {str(e)[:120]}", flush=True)
        db.update(vid, payload={"thumb9": {**info, "files": {k: str(p) for k, p in files.items()}}})
    print(f"[thumb9] {vid}: {info.get('brand')} — {info['line1']} / {info['line2']}, вариантов для A/B {len(files)}", flush=True)
    return {"info": info, "files": files}
