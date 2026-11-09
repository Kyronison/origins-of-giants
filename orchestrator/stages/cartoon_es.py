"""Испанский канал Orígenes de Gigantes в стиле мультфильма (владелец 12.10.2026: «такие же ролики, только мультяшные, на испанском, как у Built On You»).

Ролик собирается обычным конвейером по теме из stories_es.txt с topic.style = "cartoon": английский ресёрч, сценарий (~2900 слов) и раскадровка,
все кадры рисуются (шаржи на героев разрешены), затем вместо английского рендера — localize.build(cartoon=True): перевод, испанская озвучка,
рендер. Обложка — шаблон, утверждённый владельцем 12.10: шарж слева, сцена внизу, название и годы на чистом небе (Alfa Slab One, сжатый,
чёрный без обводки), справа детальная почтовая марка. Название — «La historia COMPLETA de X en N minutos».
Загрузка — сразу (ES_CARTOON_UPLOAD=1) или после «да» владельца (по умолчанию)."""
import json
from pathlib import Path
from .. import config, db, llm, telegram

FONT = config.ROOT / "work" / "es-cartoon" / "fonts" / "AlfaSlabOne-Regular.ttf"
SCENE = ("bright clean cartoon illustration in the style of modern YouTube company-history documentaries: thick dark outlines, flat vivid colors, "   # 13.10 владелец: «небо слишком пустое» — как у Built On You
         "soft cel shading, sunny daylight, crisp detail, 16:9 wide shot from a slightly elevated angle. The scenery is big, busy and detailed and fills "
         "the lower two thirds of the image; the horizon is about one third from the top, so the sky is only the top third (pale light blue, a few soft "
         "clouds). In that sky, in the upper middle of the picture between the person and the right side, 2–3 small objects from the story fly or float: "
         "{sky}. The top-right area (right half, top 36%) stays plain light sky with nothing in it — buildings and trees there stay below that line — for a title. The person on the left is a friendly "
         "caricature with a big head, thick orange outline around him, arms crossed, confident, standing tall in the left third from the bottom edge up. "
         "No text, no letters, no numbers, no logos anywhere.")
STAMP = ("A single small square postage stamp, front view, flat and straight, centered. Perforated white serrated edges with round tooth "   # 13.10: плоская, как у Built On You
         "holes, a thin white margin, a solid {color} square field. In the middle: a simple flat vector icon of {subject} in white with a few clean "
         "{color}-colored detail lines, bold readable shape, like a modern app icon, no shading, no texture, no engraving. Plain light-grey "
         "background. No text, no letters, no numbers.")


def _info(vid: str) -> dict:
    """Что нарисовать на обложке — одним запросом по теме и началу сценария."""
    v = db.get(vid); t = v["payload"].get("topic") or {}; s = v["payload"].get("script") or {}
    cast = [c.get("name") for c in ((v["payload"].get("entities") or {}).get("cast") or []) if c.get("name")][:6]
    q = (f"Компания: {t.get('company') or t.get('ticker')}. Люди: {', '.join(cast) or t.get('people', '')}.\n"
         f"Начало сценария: {(s.get('script') or '')[:1800]}\n\n"
         "Подготовь обложку в стиле канала Built On You. Верни JSON:\n"
         '{"brand": "короткое имя бренда, как его знает зритель (Apple, Zara, Real Madrid)", "founded": год основания числом,'
         ' "founder": "главный основатель для шаржа (один человек, максимум двое)", "founder_look": "внешность в узнаваемые годы по-английски: волосы, очки, одежда",'
         ' "scene": "по-английски: самая узнаваемая сцена империи компании, низко в кадре (здание, завод, магазин, продукт), без надписей",'
         ' "sky_objects": "по-английски: 2–3 небольших предмета из истории компании, которые летят или парят в небе (small propeller plane, a flying contract with a torn edge, a spinning disc, a ringing bell)",'
         ' "stamp_subject": "по-английски: ОДИН крупный простой предмет-символ компании без логотипа, узнаваемый в 50 пикселях (old desktop computer, cardboard parcel box, magnifying glass, electric car, film clapperboard, soda bottle, shopping cart, football) — не плата, не схема, не мелкая деталь",'
         ' "stamp_color": "по-английски: цвет поля марки по цвету бренда (charcoal grey, warm orange, royal blue, deep red)"}')
    r = llm.ask_json(q, max_tokens=900, tag=f"thumb_es_info_{vid}")
    r["brand"] = str(r.get("brand") or t.get("company") or "").strip()
    return r


def _sky_ok(path) -> tuple[float, float]:
    from PIL import Image, ImageOps, ImageFilter, ImageStat
    im = ImageOps.fit(Image.open(path).convert("L"), (1280, 720)); box = im.crop((600, 0, 1260, 250))   # 13.10: чистым должен быть только угол под название и годы
    return ImageStat.Stat(box).mean[0], ImageStat.Stat(box.filter(ImageFilter.FIND_EDGES)).mean[0]


def _gen(prompt: str, out: Path, w: int, h: int):
    import fal_client
    from . import assets as A
    if out.exists(): return
    m = config.THUMB_IMAGE_MODEL
    r = fal_client.subscribe(m, arguments=A.image_args(m, prompt, w, h, thumb=True))
    out.write_bytes(A._get(r["images"][0]["url"], timeout=180))


def _cut_stamp(src):
    """Марка без BiRefNet (тот рвал зубцы): заливка серого фона от углов, белые зубцы светлее и останавливают заливку."""
    from PIL import Image, ImageDraw, ImageFilter
    im = Image.open(src).convert("RGB"); w, h = im.size; probe = im.copy()
    for c in [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1), (w // 2, 0), (w // 2, h - 1), (0, h // 2), (w - 1, h // 2)]:
        if probe.getpixel(c) != (255, 0, 255): ImageDraw.floodfill(probe, c, (255, 0, 255), thresh=24)
    m = Image.new("L", (w, h), 0); px = probe.load(); mp = m.load()
    for y in range(h):
        for x in range(w): mp[x, y] = 0 if px[x, y] == (255, 0, 255) else 255
    m = m.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(0.8))
    out = im.convert("RGBA"); out.putalpha(m); return out.crop(m.getbbox())


def _text(txt: str, size: int, squeeze: float = 0.84, glow: bool = True):
    """Чёрный узкий шрифт без обводки; под буквами — мягкое светлое свечение (13.10: сцена выше, годы иногда ложатся на детали)."""
    from PIL import Image, ImageDraw, ImageFont, ImageFilter
    f = ImageFont.truetype(str(FONT), size); bb = f.getbbox(txt); pad = size // 8
    im = Image.new("RGBA", (bb[2] - bb[0] + 2 * pad, bb[3] - bb[1] + 2 * pad), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((pad - bb[0], pad - bb[1]), txt, font=f, fill=(15, 15, 15, 255))
    if glow:
        a = im.split()[-1].filter(ImageFilter.MaxFilter(9)).filter(ImageFilter.GaussianBlur(size / 9))
        halo = Image.new("RGBA", im.size, (250, 252, 255, 0)); halo.putalpha(a.point(lambda v: int(v * 0.75)))
        halo.alpha_composite(im); im = halo
    return im.resize((max(1, int(im.width * squeeze)), im.height), Image.LANCZOS)


def thumb(vid: str, vid2: str):
    """Обложка по шаблону 12.10 → thumb_2560.png, thumb_a.png, publish/thumbnail_2560.jpg (≤ 2 МБ)."""
    from PIL import Image, ImageOps
    from .localize import _dir
    d2 = vid2 if isinstance(vid2, Path) else _dir(vid2)   # 13.10: Path — испанский-сразу ролик в своей папке
    work = d2 / "thumb_es"; work.mkdir(parents=True, exist_ok=True)
    info_p = work / "info.json"
    info = json.loads(config.read(info_p)) if info_p.exists() else _info(vid)
    config.write(info_p, json.dumps(info, ensure_ascii=False, indent=1))
    scene_prompt = (SCENE.format(sky=info.get("sky_objects") or "a small propeller plane and a paper airplane") + f" Caricature of {info.get('founder')}: {info.get('founder_look')}. Scene: {info.get('scene')}.")
    best = None
    for i in range(3):   # верх справа должен быть чистым небом — иначе текст ляжет на детали (владелец 12.10)
        p = work / f"scene_{i}.png"; _gen(scene_prompt, p, 1920, 1088)
        lum, det = _sky_ok(p); score = det - lum / 20
        print(f"[thumb-es] сцена {i}: яркость неба {lum:.0f}, детали {det:.1f}", flush=True)
        if best is None or score < best[0]: best = (score, p)
        if lum > 170 and det < 8: break
    raw = work / "stamp_raw.png"
    _gen(STAMP.format(color=info.get("stamp_color") or "royal blue", subject=info.get("stamp_subject") or "a factory and a globe"), raw, 1024, 1024)
    W, H = 2560, 1440
    im = ImageOps.fit(Image.open(best[1]).convert("RGB"), (W, H), Image.LANCZOS).convert("RGBA")
    name = info["brand"].upper(); founded = info.get("founded")
    nm = _text(name, 320); maxw = int(W * 0.46)
    if nm.width > maxw: nm = nm.resize((maxw, int(nm.height * maxw / nm.width)), Image.LANCZOS)
    yr = _text(f"{founded} – 2026", 200) if founded else None
    if yr is not None and yr.width > maxw: yr = yr.resize((maxw, int(yr.height * maxw / yr.width)), Image.LANCZOS)
    st = _cut_stamp(raw); s = int(nm.height * 0.78); st = st.resize((int(st.width * s / st.height), s), Image.LANCZOS)
    block_w = nm.width + 10 + st.width; x0 = min(W - 56 - block_w, int(W * 0.70) - block_w // 2); y0 = 30
    im.alpha_composite(nm, (x0, y0)); im.alpha_composite(st, (x0 + nm.width + 10, y0 + (nm.height - st.height) // 2))
    if yr is not None: im.alpha_composite(yr, (x0 + (nm.width - yr.width) // 2, y0 + nm.height - 30))
    big = im.convert("RGB"); big.save(d2 / "thumb_2560.png"); big.resize((1280, 720), Image.LANCZOS).save(d2 / "thumb_a.png")
    (d2 / "thumb_a.keep").write_text("cartoon es 12.10", encoding="utf-8"); (d2 / "publish").mkdir(exist_ok=True)
    for qq in (92, 86, 80, 72):
        big.save(d2 / "publish" / "thumbnail_2560.jpg", "JPEG", quality=qq, optimize=True)
        if (d2 / "publish" / "thumbnail_2560.jpg").stat().st_size <= 2 * 1024 * 1024: break
    db.update(vid, payload={"thumb_es": info})
    print(f"[thumb-es] обложка: {name} {founded} – 2026, марка «{info.get('stamp_subject')}»", flush=True)


def kit(vid: str, vid2: str, tl2: dict):
    """Название «La historia COMPLETA de X en N minutos», описание с главами, теги, закреп, поля Studio — по-испански."""
    from .publish import _ascii, _ts, STUDIO
    from .localize import _dir, LANGS
    L = LANGS["es"]; d2 = vid2 if isinstance(vid2, Path) else _dir(vid2); v = db.get(vid)
    info = v["payload"].get("thumb_es") or {}; brand = info.get("brand") or (v["payload"].get("topic") or {}).get("company") or ""
    minutes = max(1, round(float(tl2["duration"]) / 60))
    title = f"La historia COMPLETA de {brand} en {minutes} minutos"
    sc = v["payload"].get("script") or {}
    script_es = sc.get("script", "") if sc.get("lang") == "es" else ""   # 13.10: сценарий уже испанский (озвучка сразу по-испански)
    if not script_es:
        tr = json.loads(config.read(d2 / "translation.json")); script_es = "\n\n".join(" ".join(p) for p in tr)
    q = (f"Канал «{L['channel']}» (нейтральный латиноамериканский испанский), документальный мультфильм «{title}». Текст ролика:\n{script_es[:6000]}\n\n"
         "Напиши для YouTube: description — 2 абзаца по-испански (первая строка цепляет конкретным фактом из ролика, затем о чём история; "
         "без выдуманных фактов, только из текста; это рассказ, а не спор — без слова «tesis» и без «¿tengo razón?»), tags — 15 тегов (испанские и английские: компания, основатели, «historia de ...»), "
         "pinned — закреплённый комментарий: интересный факт из ролика + вопрос зрителям; hashtags — 3. "
         'Верни JSON {"description": "...", "tags": ["..."], "pinned": "...", "hashtags": ["#..."]}')
    r = llm.ask_json(q, heavy=True, max_tokens=3000, tag=f"kit_es_{vid}", model=config.LLM_MODEL_WRITER or None)
    names = {o.get("n"): o.get("text") for o in tl2.get("overlays") or [] if o.get("type") == "chapter"}
    chapters = ["0:00 " + _ascii(names.get(1) or "Inicio")]
    for p in tl2.get("pauses") or []:
        chapters.append(f"{_ts(p['at'] + 0.4)} {_ascii(names.get(p['part']) or p.get('name') or 'Parte ' + str(p['part']))}")
    text = "\n\n".join([_ascii(r.get("description") or "").strip(), L["chapters"] + "\n" + "\n".join(chapters),
                        "Orígenes de Gigantes cuenta la historia COMPLETA de las empresas que conoces. Suscríbete para la próxima.",
                        *(["Fuentes (libros): " + "; ".join(((v["payload"].get("research") or {}).get("books") or []))] if (v["payload"].get("research") or {}).get("books") else []),
                        " ".join((r.get("hashtags") or ["#Documental"])[:3])])
    tg = [_ascii(x) for x in (r.get("tags") or [])][:18]
    for x in (L["channel"], "documental animado", "historia de empresas"):
        if x not in tg: tg.append(x)
    while len(", ".join(tg)) > 480: tg.pop(-4)
    out = d2 / "publish"; out.mkdir(exist_ok=True)
    config.write(out / "title.txt", title[:100]); config.write(out / "description.txt", text.replace("<", "(").replace(">", ")"))
    config.write(out / "tags.txt", ", ".join(tg)); config.write(out / "pinned_comment.txt", _ascii(r.get("pinned") or ""))
    config.write(out / "studio.txt", STUDIO.replace("English (United States)", "Spanish (Latin America)")
                 .replace("Company Origins", "Documentales: Orígenes de Gigantes").replace("subtitles_en.srt -> English -> With timing", "нет (у Built On You их тоже нет)")
                 .replace("среда / пятница / воскресенье 00:00 МСК (17:00 в Нью-Йорке; с 04.11 — 01:00 МСК)", "ближайший свободный вечер испанского канала, 00:00 МСК"))
    config.write(d2 / "meta.json", json.dumps({"titles": [title], "tags": tg, "description": text}, ensure_ascii=False, indent=2))
    print(f"[kit-es] {title} | глав {len(chapters)} | тегов {len(tg)}", flush=True)


def to_spanish(vid: str, s: dict) -> dict:
    """13.10 владелец: «сразу испанская озвучка». Сценарий после фактчека переводится по предложениям ДО раскадровки:
    раскадровка, озвучка и тайминги — сразу по-испански, английской озвучки нет. Английский текст остаётся в s["en"]."""
    import hashlib
    from . import localize
    from .assets import clean_text
    d = db.video_dir(vid); parts_en = s.get("parts") or [s["script"]]
    key = hashlib.sha1("\n\n".join(parts_en).encode("utf-8")).hexdigest()[:16]
    cache = d / "translation_es.json"
    try: c = json.loads(config.read(cache)) if cache.exists() else {}
    except Exception: c = {}
    if c.get("key") != key:
        sents = localize._translate_parts(parts_en, "es", vid)
        names = {f"p{i}": (o.get("name") or "") for i, o in enumerate(s.get("outline") or [], 1) if o.get("name")}
        c = {"key": key, "sents": sents, "names": localize._translate_strings(names, "es", vid) if names else {}}
        config.write(cache, json.dumps(c, ensure_ascii=False, indent=1))
    parts_es = [" ".join(x) for x in c["sents"]]
    s = {**s, "en": {"script": s["script"], "parts": parts_en}, "parts": parts_es, "script": "\n\n".join(parts_es), "lang": "es"}
    s["outline"] = [{**o, "name": c["names"].get(f"p{i}", o.get("name"))} for i, o in enumerate(s.get("outline") or [], 1)]
    print(f"[cartoon-es] сценарий по-испански: {len(clean_text(s['script']).split())} слов, частей {len(parts_es)}", flush=True)
    return s


def _strings_es(vid: str, tl: dict):
    """Подписи в кадре и карточки глав — по-испански (раскадровщик мог написать их по-английски); цифровые вспышки убираем:
    числа в испанской речи разбираются ненадёжно, а у Built On You цифры нарисованы в самих кадрах."""
    from . import localize
    tl["overlays"] = [o for o in tl.get("overlays") or [] if o.get("type") not in ("flash", "pair")]
    items, refs = {}, {}
    def reg(key, obj, field):
        t = obj.get(field)
        if t and isinstance(t, str) and len(t) > 2: items[key] = t; refs[key] = (obj, field)
    for i, sc in enumerate(tl.get("scenes") or []):
        reg(f"s{i}.c", sc, "caption"); dd = sc.get("data") or {}
        for k, sl in enumerate(sc.get("slots") or []):
            if sl.get("role") != "portrait": reg(f"s{i}.sl{k}", sl, "caption")
        for k, per in enumerate(dd.get("persons") or []): reg(f"s{i}.p{k}", per, "role")
        for f in ("text", "role", "stakes", "title", "subject"): reg(f"s{i}.{f}", dd, f)
        for side in ("left", "right"):
            if isinstance(dd.get(side), dict): reg(f"s{i}.{side}", dd[side], "label")
        for k, pt in enumerate(dd.get("points") or []): reg(f"s{i}.pt{k}", pt, "label")
    for j, o in enumerate(tl.get("overlays") or []):
        for f in ("text", "label"): reg(f"o{j}.{f}", o, f)
    tr = localize._translate_strings(items, "es", vid)
    for k, (obj, field) in refs.items(): obj[field] = tr.get(k, obj[field])


def finish_es(vid: str):
    """Испанский-сразу ролик: подписи по-испански, музыка, обложка, комплект, пробы кадров, рендер, мастеринг — в папке ролика."""
    import shutil
    from . import sound, render as R, stillcheck
    from .qc import tech_check
    from .localize import LANGS
    d = db.video_dir(vid); tl = json.loads(config.read(d / "timeline.json")); words = json.loads(config.read(d / "words.json"))
    if not tl.get("es_ready"):
        _strings_es(vid, tl)
        tl.update({"channel": LANGS["es"]["channel"], "lang": "es", "theme": "dossier_es", "subtitles": False, "film": None, "es_ready": True})
        try: tl["score"] = sound.build(vid, d, tl, words); tl["music_tracks"] = []; tl["sfx_chapter"] = None
        except Exception as e:   # лимит ElevenLabs Music — остаются треки глав из сборки кадров
            if not tl.get("music_tracks"): raise
            print(f"[cartoon-es] партитура не собралась ({str(e)[:100]}) — треки глав", flush=True)
        config.write(d / "timeline.json", json.dumps(tl, ensure_ascii=False, indent=1))
    if not (d / "publish" / "thumbnail_2560.jpg").exists(): thumb(vid, d)
    kit(vid, d, tl)
    if config.STILLCHECK:
        chk = stillcheck.run(d, tl, words, lang="es")
        if not chk["ok"]: raise RuntimeError("stillcheck: " + "; ".join(i["what"] for i in chk["issues"] if i["severity"] == "block")[:600])
    scale = [f"--scale={config.RENDER_HEIGHT / 1080:g}"] if config.RENDER_HEIGHT != 1080 else []
    tmp = config.RENDER_TMP; tmp.mkdir(parents=True, exist_ok=True); out = tmp / f"{vid}.mp4"
    R._rx("render", "Main", out, {"timeline": tl, "words": words}, d, scale)
    loud = tmp / f"{vid}_master.mp4"; sound.master(out, loud); loud.replace(out)
    shutil.move(str(out), str(d / "final.mp4"))
    tech = tech_check(d / "final.mp4", tl); R.contact_sheet(d / "final.mp4", tl, d / "contact.jpg")
    db.update(vid, "es_ready", payload={"tech": tech, "lang": "es"})
    print(f"[cartoon-es] готово: {d / 'final.mp4'} | {tl['duration'] / 60:.1f} мин | техпроверка: {'; '.join(tech) or 'чисто'}", flush=True)


def _next_slot_es():
    from datetime import datetime, timedelta, timezone
    msk = timezone(timedelta(hours=3))   # 13.10 владелец: «пусть каждый ролик выходит в 18:00» (МСК), по одному в день
    taken = {datetime.fromisoformat(r["publish_at"]).date() for r in db.conn().execute(
        "SELECT publish_at FROM videos WHERE publish_at IS NOT NULL AND (id LIKE '%__es' OR status = 'es_uploaded')")}
    now = datetime.now(timezone.utc)
    t = now.astimezone(msk).replace(hour=18, minute=0, second=0, microsecond=0)
    # 19.10 (владелец поручил решить по статистике): 2 ролика в неделю вместо раза в два дня — ES_WEEKDAYS_MSK, 0 — понедельник
    days = set(config.ES_WEEKDAYS_MSK)
    if taken:   # 14.10 владелец: «выпускать видео через 2 дня» — следующий не раньше чем через два дня после последнего запланированного
        t = max(t, datetime.combine(max(taken) + timedelta(days=2), t.timetz()))
    while (t < now + timedelta(hours=1) or t.astimezone(timezone.utc).date() in taken
           or (days and t.astimezone(msk).weekday() not in days)): t += timedelta(days=1)
    return t.astimezone(timezone.utc)


def upload_es(vid: str) -> str:
    """Загрузка испанского-сразу ролика на второй канал (приватно в ближайший свободный вечер, обложка, язык — испанский)."""
    from datetime import datetime, timedelta, timezone
    from googleapiclient.http import MediaFileUpload
    from .upload import _once
    from .localize import _yt
    v = db.get(vid); d = db.video_dir(vid); f = d / "final.mp4"
    if not f.exists() or f.stat().st_size < 20 * 1024 * 1024: raise FileNotFoundError("нет final.mp4")
    title = config.read(d / "publish" / "title.txt").strip(); desc = config.read(d / "publish" / "description.txt").strip()
    tags = [t.strip() for t in config.read(d / "publish" / "tags.txt").split(",") if t.strip()]
    y = _yt("es"); done = dict(v["payload"].get("uploads") or {})
    slot = datetime.fromisoformat(v["publish_at"]) if v["publish_at"] else _next_slot_es()
    if slot < datetime.now(timezone.utc) + timedelta(minutes=10): slot = (datetime.now(timezone.utc) + timedelta(minutes=15)).replace(second=0, microsecond=0)
    body = {"snippet": {"title": title[:100], "description": desc, "tags": tags, "categoryId": "28", "defaultLanguage": "es", "defaultAudioLanguage": "es"},
            "status": {"privacyStatus": "private", "publishAt": slot.isoformat(), "selfDeclaredMadeForKids": False, "embeddable": True, "publicStatsViewable": True}}
    yid = _once(y, "final.mp4", done, body, f)
    db.update(vid, "es_uploaded", youtube_id=yid, publish_at=slot.isoformat(), payload={"uploads": done})
    th = d / "publish" / "thumbnail_2560.jpg"
    if th.exists():
        try: y.thumbnails().set(videoId=yid, media_body=MediaFileUpload(str(th))).execute()
        except Exception as e: print("[cartoon-es] обложка:", str(e)[:120])
    try:   # плейлист канала (13.10: ролики загружаются сами — и в плейлист сами)
        pls = {p["snippet"]["title"]: p["id"] for p in y.playlists().list(part="snippet", mine=True, maxResults=50).execute()["items"]}
        pid = next((i for t_, i in pls.items() if "Documentales" in t_), None)
        if pid: y.playlistItems().insert(part="snippet", body={"snippet": {"playlistId": pid, "resourceId": {"kind": "youtube#video", "videoId": yid}}}).execute()
    except Exception as e: print("[cartoon-es] плейлист:", str(e)[:120], flush=True)
    try: telegram.send(f"🇪🇸 Испанский ролик загружен сам: {title}\nhttps://www.youtube.com/watch?v={yid} — выход {slot.astimezone().strftime('%d.%m %H:%M')}",
                       file=d / "publish" / "studio.txt")
    except Exception: pass
    print(f"[cartoon-es] загружен: https://www.youtube.com/watch?v={yid} — выход {slot.astimezone().strftime('%d.%m %H:%M')}", flush=True)
    return yid


def run(vid: str):
    """Стадия вместо английского рендера. Сценарий уже испанский (13.10) — всё в папке ролика; иначе (Apple 13.10) — старый путь через localize."""
    if ((db.get(vid)["payload"].get("script") or {}).get("lang")) == "es":
        finish_es(vid); d = db.video_dir(vid); title = config.read(d / "publish" / "title.txt").strip()
        if config.ES_CARTOON_UPLOAD:
            yid = upload_es(vid)
            telegram.send(f"🇪🇸 Испанский мультфильм загружен: {title}\nhttps://www.youtube.com/watch?v={yid}", file=d / "publish" / "thumbnail_2560.jpg")
        else:
            telegram.send(f"🇪🇸 Испанский мультфильм собран и ждёт «да»: `{vid}`\n{title}", file=d / "contact.jpg")
            try: telegram.send("Обложка:", file=d / "publish" / "thumbnail_2560.jpg")
            except Exception: pass
        print(f"[cartoon-es] {vid}: {title}", flush=True); return
    from . import localize
    vid2 = localize.build(vid, "es", render=True, cartoon=True)
    db.update(vid, "es_built", payload={"es_done": vid2})
    d2 = localize._dir(vid2); title = config.read(d2 / "publish" / "title.txt").strip()
    if config.ES_CARTOON_UPLOAD:
        yid = localize.upload(vid2)
        telegram.send(f"🇪🇸 Испанский мультфильм загружен: {title}\nhttps://www.youtube.com/watch?v={yid}", file=d2 / "publish" / "thumbnail_2560.jpg")
    else:
        telegram.send(f"🇪🇸 Испанский мультфильм собран и ждёт «да»: `{vid2}`\n{title}", file=d2 / "contact.jpg")
        try: telegram.send("Обложка:", file=d2 / "publish" / "thumbnail_2560.jpg")
        except Exception: pass
    print(f"[cartoon-es] {vid} → {vid2}: {title}", flush=True)
