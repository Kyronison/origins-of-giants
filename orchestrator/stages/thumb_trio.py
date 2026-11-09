"""Превью английского канала в стилях, выбранных владельцем 19.10.2026 (THUMB_STYLE=trio, STRATEGY.md раздел 0.2):
  03 — винтажный тревел-постер 1960-х, плоская трафаретная печать, крупная ретро-надпись внизу;
  09 — комикс: полутоновые точки, толстые контуры, крупная плашка-надпись;
  10 — финансовый стиль: тёмный фон, огромная стрелка графика вниз (падение) или вверх (полная история), крупный заголовок.
Основное — THUMB_TRIO_MAIN (по умолчанию 10), два других — для A/B-теста в Studio (Test & Compare через Chrome владельца).
Текст и узнаваемые цвета бренда рисует генератор (gpt-image-2.5): так владелец выбрал на доске стилей (work/ab-2026-10-19/style_board.jpg).
Собирается один раз; пересобрать — force=True."""
import json, re, shutil
from pathlib import Path
from .. import config, db, llm, series

T = "YouTube thumbnail, 16:9, bold and readable at small size, spelled exactly, the only text in the image is exactly: "
STYLE = {
 "03": "1960s mid-century travel poster, flat screen-print style, bold limited palette of {palette}, {poster}; " + T + "'{t03}' in big retro letters across the bottom.",
 "09": "Dynamic comic-book panel, halftone dots, thick ink lines, dramatic angle, vivid red, blue and yellow: {comic}; " + T + "'{t09}' in a big comic caption box.",
 "10": "Finance YouTube style, dark background, high contrast: {thing} on the right with a giant {arrow} behind it; " + T + "'{t10}' in big bold white and {accent} letters on the left.",
}
ASK = """Ты готовишь три превью YouTube-документалки канала Origins of Giants (зритель — мужчины 65+ из США, помнят бренды молодости).
Бренд: {company}. Название ролика: «{title}». Тип сюжета: {kind}. Тезис: {thesis}
Начало сценария (только эти факты можно утверждать):
{opening}

Верни JSON с полями (всё описание сцен — по-английски, для генератора картинок):
- palette: 3 цвета бренда/эпохи для тревел-постера («navy blue, white and warm orange»);
- poster: сцена тревел-постера — главная узнаваемая вещь или место бренда в его лучшие годы, героически и красиво;
- t03: надпись постера, 2–4 слова ЗАГЛАВНЫМИ («THE END OF PAN AM», «THE APPLE STORY»);
- comic: сцена комикса — драматичный, но правдивый момент сюжета; без крушений, катастроф, пострадавших и крови;
- t09: надпись комикса, 2–4 слова ЗАГЛАВНЫМИ («THE FALL OF PAN AM», «WHO BUYS WRECKS?»);
- thing: главная узнаваемая вещь бренда для финансового превью («a silver three-engine 1970s jet with blue stripes»);
- t10: заголовок финансового превью, 2–4 слова ЗАГЛАВНЫМИ («HOW PAN AM DIED» для падения, «HOW APPLE WON» для живого бренда).
Правила: всё буквально правда по ролику; чисел нет, кроме тех, что есть в сценарии; без SCAM/FRAUD; без лиц реальных людей и без
двойников; логотипы не описывай. Верни только JSON."""
BAN = re.compile(r"\b(crash\w*|wreckage|explod\w*|fire|burning|blood|injur\w*|dead bodies|victims?|disaster)\b", re.I)


def _problems(p: dict, script: str) -> list[str]:
    bad = []
    for k in ("palette", "poster", "t03", "comic", "t09", "thing", "t10"):
        if not str(p.get(k) or "").strip(): bad.append(f"нет {k}")
    for k in ("t03", "t09", "t10"):
        t = str(p.get(k) or ""); n = len(t.split())
        if not 2 <= n <= 5: bad.append(f"{k}: {n} слов, нужно 2–4")
        nums = set(re.findall(r"\d[\d.,]*", t)) - set(re.findall(r"\d[\d.,]*", script))
        if nums: bad.append(f"{k}: чисел {sorted(nums)} нет в сценарии")
    if BAN.search(str(p.get("comic") or "")) and "no crash" not in str(p.get("comic")): bad.append("comic: крушение/катастрофа запрещены")
    return bad


def plan(vid: str) -> dict:
    v = db.get(vid); pl = v["payload"]; t = pl.get("topic") or {}; s = (pl.get("script") or {}).get("script") or ""
    up = (series.of(t) or {}).get("story_type") == "history"
    q = ASK.format(company=series.brand(t) or t.get("company") or v["title"], title=v["title"], kind="полная история (бренд жив)" if up else "падение бренда",
                   thesis=str(t.get("thesis") or "")[:600], opening=re.sub(r"\[F\d+[^\]]*\]", "", s)[:3000])
    note, bad = "", []
    for _ in range(3):
        p = llm.ask_json(q + note, heavy=True, max_tokens=2000, tag=f"thumbtrio_{vid}")
        p = {k: str(p.get(k) or "").strip() for k in ("palette", "poster", "t03", "comic", "t09", "thing", "t10")}
        for k in ("t03", "t09", "t10"): p[k] = p[k].upper()
        bad = _problems(p, s + " " + v["title"])
        if not bad:
            p["comic"] += ", no crash, no damage, no fire, no injured people"
            p["arrow"] = "green stock chart arrow shooting UP" if up else "red stock chart arrow crashing down"
            p["accent"] = "green" if up else "red"
            return p
        note = "\n\nПрошлый ответ нарушил правила, исправь:\n- " + "\n- ".join(bad) + f"\nПрошлый ответ: {json.dumps(p, ensure_ascii=False)}"
    raise RuntimeError("план превью trio не прошёл проверку: " + "; ".join(bad))


def make(vid: str, set_main: bool = True, force: bool = False) -> dict:
    from PIL import Image, ImageOps
    from . import thumbx as X, thumbcheck
    d = db.video_dir(vid); work = d / "thumb_trio"; work.mkdir(exist_ok=True)
    pf = work / "plan.json"
    if force and pf.exists(): shutil.rmtree(work); work.mkdir()
    p = json.loads(config.read(pf)) if pf.exists() else plan(vid)
    config.write(pf, json.dumps(p, ensure_ascii=False, indent=1))
    files = {}
    for k, tpl in STYLE.items():
        png = work / f"{k}.png"; X._gen(tpl.format(**p), png)
        jpg = work / f"{k}.jpg"; im = ImageOps.fit(Image.open(png).convert("RGB"), (1920, 1080), Image.LANCZOS)
        for q in (92, 86, 80):
            im.save(jpg, "JPEG", quality=q, optimize=True)
            if jpg.stat().st_size < 2 * 1024 * 1024: break
        files[k] = jpg
    main = config.THUMB_TRIO_MAIN if config.THUMB_TRIO_MAIN in files else "10"
    sheet = Image.new("RGB", (3 * 640 + 40, 380), "white")
    for i, k in enumerate(STYLE): sheet.paste(Image.open(files[k]).convert("RGB").resize((640, 360)), (10 + i * 650, 10))
    sheet.save(work / "sheet.jpg", quality=86)
    if set_main:
        for f in ("thumb_a.png", "thumb_2560.png"):   # прежняя остаётся рядом на случай отката
            if (d / f).exists() and not (d / f"{Path(f).stem}_gen.png").exists(): shutil.copy(d / f, d / f"{Path(f).stem}_gen.png")
        im = Image.open(work / f"{main}.png").convert("RGB")
        ImageOps.fit(im, (2560, 1440), Image.LANCZOS).save(d / "thumb_2560.png")
        ImageOps.fit(im, (1920, 1080), Image.LANCZOS).save(d / "thumb_a.png")
        for k in d.glob("thumb_*.keep"): k.unlink()
        (d / "thumb_a.keep").write_text(f"thumbtrio {main} {p['t' + main]}", encoding="utf-8")
        thumbcheck.prepare(d)
        db.update(vid, payload={"thumb_trio": {"main": main, "files": {k: str(f) for k, f in files.items()}, "texts": {k: p["t" + k] for k in STYLE}}})
    print(f"[thumbtrio] {vid}: основное {main} «{p['t' + main]}», для A/B — " + ", ".join(f"{k} «{p['t' + k]}»" for k in STYLE if k != main), flush=True)
    return {"plan": p, "files": files, "main": main, "sheet": work / "sheet.jpg"}
