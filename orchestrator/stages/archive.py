"""Реальные кадры вместо генерации: фото с Wikimedia Commons (лицензии CC / public domain) и видео с YouTube (yt-dlp).
Кандидатов выбирает модель с картинками: для фото — сетка превью, для видео — раскадровка YouTube (storyboard), по ней
находим момент и скачиваем только его. Каждый выбранный кадр получает подпись (кто/что, год) и кредит источника."""
import io, json, pathlib, re, shutil, subprocess, threading, requests
from .. import config, llm, visual_integrity

UA = "OriginsOfGiants/0.1 (documentary research)"
_lock = threading.Lock()
_yt_info: dict = {}          # video_id → info yt-dlp (кэш на процесс)
_used_yt: dict = {}          # video_id → [секунды], чтобы не взять один момент дважды
_used_photos: set = set()    # названия файлов Commons, уже взятых в этом видео
CLIP_SEC = 16                # длина вырезки из YouTube: сцена в story ≈ 6–10 с, запас на длинные
YT_MAX_SEC = 25 * 60         # ролики длиннее не скачиваем
MAX_TILES = 60               # плиток раскадровки в одном листе для модели

def reset():
    _yt_info.clear(); _used_yt.clear(); _used_photos.clear()

# 08.10.2026 дешёвый режим (владелец: «да давай»): видеоклип ищут только первые ARCHIVE_VIDEO_MAX архивных слотов по порядку сцен —
# это вступление и начало ролика. Остальные архивные слоты сразу берут фото (Commons, затем пресса). На Thomas Cook охота за клипами
# стоила ~$6.3 из $22 (946 проверок клипов дорогой моделью); у Tech District видео нет вообще — только фото.
_video_budget = {"left": None if config.ARCHIVE_VIDEO_MAX < 0 else config.ARCHIVE_VIDEO_MAX}

def video_budget(n: int | None):
    """Сколько слотов ещё могут искать видео; None — без потолка. Ставит story_assets.run в начале закупки кадров."""
    with _lock: _video_budget["left"] = n

def _video_ok(x: dict) -> bool:
    """Слот берёт одно место из бюджета видео один раз (повторный поиск того же слота место не тратит)."""
    if x.get("_vb"): return True
    with _lock:
        left = _video_budget["left"]
        if left is not None:
            if left <= 0: return False
            _video_budget["left"] = left - 1
    x["_vb"] = True
    return True

def _planned_caption(x):
    if isinstance(x.get("visual_intent"), dict): return x["visual_intent"].get("caption") or ""
    return x.get("caption") or ""

def resolve(x: dict, d, ctx: str, vid: str, exclude: bool = False, portrait: bool = False, quick: bool = False) -> bool:
    """x — кадр или слот source=archive: query, media (photo|video|any), caption. Ставит image или src и подпись.
    exclude — не брать то, что уже пробовали; portrait — нужен портрет одного человека (people): сначала фото Commons."""
    visual_integrity.remember_intent(x, ctx)
    media = (x.get("media") or "any").lower()
    # видео даёт «живую» хронику, фото Commons — точную атрибуцию; для photo сначала фото, иначе сначала видео
    order = ["photo", "video"] if (media == "photo" or portrait) else ["video", "photo"]
    if exclude:   # забракованный источник: для YouTube — id ролика, для Commons — название файла
        key = (x.get("archive") or {}).get("key", "")
        x.setdefault("_tried", []).append(key[3:].split("@")[0] if key.startswith("yt:") else key)
    x.pop("_today", None)
    if quick:   # проба «хроника вместо генерации»: один запрос, только фото Commons — без скачивания роликов, веб-поиска и запасных путей
        try: ok = bool(x.get("query")) and _photo(x, d, ctx, vid, x["query"], False)
        except Exception as e: print(f"[archive] {x['id']} quick: {e}"); ok = False
        if ok: print(f"[archive] {x['id']}: photo (проба) — {x.get('caption')} ({x['archive'].get('key', '')[:60]})"); return True
        # владелец 21.09: «подзабьём на права, чтобы было больше настоящих фото» — снимки из прессы, блогов и сайтов компаний под fair use
        # (комментарий, 5–10 с на кадр, подпись источника); агентства и фотобанки отсечены WEB_SKIP — претензии шлют именно они
        try: ok = bool(x.get("query")) and _web_photo(x, d, ctx, vid, x["query"], False)
        except Exception as e: print(f"[archive] {x['id']} quick web: {e}"); ok = False
        if ok: print(f"[archive] {x['id']}: web (проба) — {x.get('caption')} ({x['archive'].get('url', '')[:60]})")
        return ok
    for query in dict.fromkeys([x.get("query") or "", x.get("query_alt") or ""]):   # точный запрос, затем широкий запасной
        if not query: continue
        for kind in order:
            if kind == "video" and not portrait and not _video_ok(x):
                x["_novideo"] = True; continue   # бюджет видео исчерпан — только фото, дальше и веб-поиск фото
            try:
                ok = _photo(x, d, ctx, vid, query, portrait) if kind == "photo" else _video(x, d, ctx, vid, query, portrait)
            except Exception as e:
                print(f"[archive] {x['id']} {kind}: {e}"); ok = False
            if ok:
                print(f"[archive] {x['id']}: {kind} — {x.get('caption')} ({x['archive'].get('key', '')[:60]})"); return True
    if portrait or (x.get("media") or "").lower() == "photo" or x.pop("_novideo", False):   # веб-поиск картинок: снимок эпохи часто есть в прессе, но не на Commons
        for query in dict.fromkeys([x.get("query") or "", x.get("query_alt") or ""]):
            if not query: continue
            try:
                if _web_photo(x, d, ctx, vid, query, portrait):
                    print(f"[archive] {x['id']}: web — {x.get('caption')} ({x['archive'].get('url', '')[:60]})"); return True
            except Exception as e:
                print(f"[archive] {x['id']} web: {e}")
    died = re.search(r"\d{4}\s*[–-]\s*(\d{4})", str(x.get("years") or ""))
    if portrait and died and int(died.group(1)) < 1985:   # умер до 1985 — «позднего снимка» в прессе не бывает: под именем окажется брат или однофамилец (McDonald's 22.09)
        print(f"[archive] {x['id']}: {x.get('person')} умер в {died.group(1)} — поздний снимок не ищем, лучше без портрета"); return False
    if portrait:   # снимка эпохи нет — более поздний снимок того же человека (владелец 16.09: «а где фото Пола Террелла?»)
        name = x.get("person") or " ".join(w for w in (x.get("query") or "").split()[:3] if w[:1].isupper())
        try:
            x["_tried"] = []
            if name and _photo(x, d, ctx, vid, name, portrait=True, relaxed=True):
                x["archive"]["relaxed"] = True   # preflight не проверяет эпоху у позднего снимка — иначе выбросит единственный портрет
                _crop_to_person(x, d, name, vid)
                print(f"[archive] {x['id']}: portrait (поздний снимок) — {x.get('caption')} ({x['archive'].get('key', '')[:60]})"); return True
            # у многих людей (Маккензи Скотт, 18.09) снимков на Commons нет совсем, а в прессе их сотни — поздний снимок ищем и там
            if name and _web_photo(x, d, ctx, vid, name, portrait=True, relaxed=True):
                x["archive"]["relaxed"] = True
                _crop_to_person(x, d, name, vid)
                print(f"[archive] {x['id']}: portrait web (поздний снимок) — {x.get('caption')} ({x['archive'].get('url', '')[:60]})"); return True
        except Exception as e:
            print(f"[archive] {x['id']} relaxed portrait: {e}")
    today = x.pop("_today", None)   # современный снимок здания/места («…, today») — только когда снимка эпохи нет ни по одному запросу
    if today and _apply_photo(x, d, *today):
        print(f"[archive] {x['id']}: photo (today, последний фолбэк) — {x.get('caption')} ({x['archive'].get('key', '')[:60]})"); return True
    return False

def _crop_to_person(x: dict, d, name: str, vid: str, aspect: float = 0.8) -> None:
    """Поздний снимок часто групповой (Маккензи Скотт рядом с Джеффом на Oscar party), а колонка портрета режет кадр строго по центру —
    и попадает в промежуток между людьми. Режем файл заранее: прямоугольник 4:5 вокруг лица названного человека."""
    if not x.get("image"): return
    from PIL import Image
    p = d / x["image"]
    try:
        im = Image.open(p).convert("RGB")
        if im.width / im.height <= aspect * 1.15: return            # уже вертикальный — одиночный портрет
        xy = locate(p, name, x.get("caption") or name, vid)
        if not xy: return
        cw = min(im.width, int(im.height * aspect)); cx = int(xy[0] * im.width)
        x0 = max(0, min(im.width - cw, cx - cw // 2))
        im.crop((x0, 0, x0 + cw, im.height)).save(p, "JPEG", quality=92)
        x["aspect"] = round(cw / im.height, 3); x["focus_xy"] = [0.5, round(xy[1], 3)]
        print(f"[archive] {x['id']}: групповой снимок обрезан вокруг «{name}» ({cw}x{im.height})")
    except Exception as e:
        print(f"[archive] {x['id']}: обрезка вокруг лица не удалась: {str(e)[:70]}")

# ---------- фото: Wikimedia Commons ----------

def _clean_cap(cap: str) -> str:
    """Модель переносит в подпись служебную метку плитки «описание | автор | 750x460» (Microsoft 19.09: «Lakeside School 750x460» в кадре)."""
    cap = re.sub(r"\s*\b\d{2,4}\s*[x×]\s*\d{2,4}\b", "", cap)
    return re.sub(r"\s*\|\s*", " ", cap).strip(" ,|-")

def _plain(html: str) -> str:
    """HTML поля Commons → текст. unescape: иначе «&amp;» уезжало в описание ролика (Amazon 18.09); повтор «X X» — след двух ссылок на одного автора."""
    import html as H
    t = re.sub(r"\s+", " ", H.unescape(re.sub(r"<[^>]+>", " ", html or ""))).strip()
    return re.sub(r"^(.{3,60}?)\s*\1$", r"\1", t)

def commons_search(q: str, n: int = 10) -> list[dict]:
    """Поиск файлов; превью 640px берём из API (прямые ссылки на произвольные размеры Commons больше не отдаёт)."""
    r = requests.get("https://commons.wikimedia.org/w/api.php", headers={"User-Agent": UA}, timeout=60, params={
        "action": "query", "generator": "search", "gsrsearch": f"{q} filetype:bitmap", "gsrnamespace": 6, "gsrlimit": n,
        "prop": "imageinfo", "iiprop": "url|size|extmetadata", "iiurlwidth": 640, "format": "json"}).json()
    out = []
    for p in sorted((r.get("query", {}).get("pages") or {}).values(), key=lambda p: p.get("index", 99)):
        ii = (p.get("imageinfo") or [{}])[0]; m = ii.get("extmetadata") or {}
        if not ii.get("width") or ii["width"] < 640 or ii.get("height", 0) < 400: continue
        if re.search(r"\.(svg|gif|pdf|djvu)$", p["title"], re.I): continue
        out.append({"key": p["title"], "url": ii.get("url"), "thumb": ii.get("thumburl") or ii.get("url"),
                    "w": ii["width"], "h": ii["height"], "license": _plain(m.get("LicenseShortName", {}).get("value", "")),
                    "artist": _plain(m.get("Artist", {}).get("value", ""))[:80], "date": _plain(m.get("DateTimeOriginal", {}).get("value", ""))[:20],
                    "desc": _plain(m.get("ImageDescription", {}).get("value", ""))[:220]})
    return out

PICK_PHOTO = """Документальное видео об истории компании. Нужен реальный архивный снимок под фразу озвучки:
«{ctx}»
Что ищем: {query}. Подпись, которую планируем: «{caption}».
Ниже сетка кандидатов с номерами; под каждым — название и описание файла с Wikimedia Commons (в описании часто есть год).
Выбери ОДИН снимок, который честно иллюстрирует фразу: тот же человек, предмет или место, и та же эпоха (если фраза про 1976 год, снимок 2010 года не подходит, если это не «сегодня»).
Не бери: памятники, статуи и куклы вместо людей; логотипы, скриншоты, схемы, карты, обложки, документы и кадры с крупным текстом; мемы, коллажи, рисунки; снимки, где главный объект не виден или слишком мелкий; плохое качество.
Если человек на снимке не тот, кого ищем, — не бери. Водяной знак, название канала или сайта в углу — брак.
Исключение по эпохе: если фраза про прошлое, а подходящий снимок современный — брать можно ТОЛЬКО здание или место (не людей и не предметы), и тогда подпись без года, со словом today («Homestead High School, today») и modern=true. Год в подписи ставь только тот, что есть в описании файла; если даты нет — подпись без года (не выдумывай «mid-1900s»).
{portrait_rule}{place_rule}
Верни JSON: {"n": <номер или 0, если ничего не подходит>, "why": "коротко", "modern": true|false (снимок современный, подпись today), "year": <год снимка по описанию файла или null>, "caption": "подпись: если планируемая верна для этого снимка — она же, иначе поправь по описанию файла (имя или предмет, год), ≤6 слов, по-английски"}"""

PLACE_RULE = ("\nЭто врезка для карты: на снимке должен быть именно этот город или его окрестности ({place}) — подтверждение только в названии или описании файла. "
              "Другой город, зоопарк, парк развлечений, аттракцион, интерьер — не подходит: верни 0.")

LOCATE = """На снимке должен быть {name} (подпись: «{caption}»). Найди именно этого человека (по подписи, порядку, описанию, характерным чертам).
Верни JSON: {"found": true|false, "x": <центр лица по горизонтали, 0..1 от левого края>, "y": <центр лица по вертикали, 0..1 от верха>, "why": "коротко"}.
Если на снимке один человек — его координаты; если нельзя понять, кто из людей он, — found=false."""

def locate(path, name: str, caption: str, vid: str) -> list[float] | None:
    """Точка лица названного человека на групповом архивном фото (ежегодник) — для наезда Ken Burns к нему, а не к «самой резкой клетке».
    Один vision-вызов (~$0.005); None, если не найден. Координаты клампятся в [0.12, 0.88] без смеси с центром."""
    from PIL import Image
    try:
        im = Image.open(path).convert("RGB"); im.thumbnail((1024, 1024)); buf = io.BytesIO(); im.save(buf, "JPEG", quality=85)
        r = llm.ask_vision(LOCATE.replace("{name}", name).replace("{caption}", caption), [buf.getvalue()], tag=f"locate_{vid}")
        if not r.get("found"): print(f"[archive] {name} на снимке не найден: {r.get('why', '')[:60]}"); return None
        x, y = float(r["x"]), float(r["y"])
        if not (0 <= x <= 1 and 0 <= y <= 1): return None
        xy = [round(min(0.88, max(0.12, x)), 3), round(min(0.88, max(0.12, y)), 3)]
        print(f"[archive] {name}: лицо в {xy} — наезд туда"); return xy
    except Exception as e:
        print(f"[archive] locate {name}: {e}"); return None

GENERIC_CAP = set("""hq headquarters office offices store stores shop factory plant building buildings street downtown interior exterior
lobby early late mid circa the of in at and a an on new old first original staff employees workers team customers warehouse
center centre room floor desk booth corporate company inc corp ltd co llc campus site area city town main north south east west
january february march april may june july august september october november december jan feb mar apr jun jul aug sep sept oct nov dec""".split())

def _strip_unsourced_name(cap: str, evidence: str) -> str:
    """Название в подписи к фото Commons, которого нет в названии/описании файла, — догадка модели зрения:
    26.09 Verisign, «Newport Systems Solutions UK office» подписан как «Network Solutions HQ». Подпись снимаем целиком."""
    if not cap: return cap
    ev = re.sub(r"[^a-z0-9]", "", (evidence or "").lower())
    toks = [t for t in re.findall(r"[A-Za-z][A-Za-z&'.-]{2,}", cap) if t.lower().strip(".'") not in GENERIC_CAP]
    miss = [t for t in toks if re.sub(r"[^a-z0-9]", "", t.lower()) not in ev]
    if miss:
        print(f"[archive] подпись «{cap}» снята: {', '.join(miss)} нет в описании файла", flush=True)
        return ""
    return cap

def _strip_unsourced_year(cap: str, evidence: str) -> str:
    """Год/десятилетие в подписи, которого нет ни в дате, ни в описании файла Commons, — выдумка модели («mid-1900s»): убираем."""
    m = re.search(r",?\s*(?:c\.\s*|circa\s+|mid-|early\s+|late\s+)?((?:1[6-9]|20)\d\d)s?\s*$", cap)
    if not m: return cap
    return cap if m.group(1)[:3] in (evidence or "") else cap[:m.start()].strip(" ,")

PORTRAIT_RELAXED = ("Снимка эпохи у этого человека в свободных источниках нет. Возьми более ПОЗДНИЙ снимок ТОГО ЖЕ человека: его имя обязано быть в названии "
                    "или описании файла; групповое фото допустимо, если он назван и виден. Подпись — имя и реальный год снимка из описания файла. "
                    "Это не здание: modern=false. Если ни на одном снимке его нет — 0.")
PORTRAIT_RULE = ("Нужен ПОРТРЕТ одного человека: лицо видно, снимок не групповой (если на фото несколько людей и искомый не главный — не бери), "
                 "не памятник, не восковая фигура, не рисунок, без вшитого текста поверх снимка (титр документалки, субтитры, подпись, водяной знак). Если ни один кандидат не является портретом именно этого человека — верни 0. "
                 "Если подходят несколько — бери ближайший по эпохе к фразе (фраза про юность — молодой снимок); в caption — имя и год снимка («Steve Wozniak, 1977»).")

def person_caption(name: str | None, cap: str, year) -> str:
    """Подпись портрета — всегда «кто, год» («Steve Wozniak, 1984»), не описание («interview footage»)."""
    if not name: return cap
    y = _year_of(str(year or "")) or _year_of(cap)
    return f"{name}, {y}" if y else name

def _grid(items: list[dict], cols: int = 4, w: int = 400, h: int = 300, label_key: str = "label") -> bytes:
    from PIL import Image, ImageDraw
    rows = (len(items) + cols - 1) // cols; pad = 8; cap_h = 44
    out = Image.new("RGB", (cols * w + (cols + 1) * pad, rows * (h + cap_h) + (rows + 1) * pad), "white"); dr = ImageDraw.Draw(out)
    for k, it in enumerate(items):
        x0 = pad + (k % cols) * (w + pad); y0 = pad + (k // cols) * (h + cap_h + pad)
        im = it["im"].convert("RGB"); im.thumbnail((w, h)); out.paste(im, (x0 + (w - im.width) // 2, y0 + (h - im.height) // 2))
        dr.rectangle([x0, y0, x0 + 44, y0 + 24], fill="red"); dr.text((x0 + 6, y0 + 5), str(k + 1), fill="white")
        txt = it.get(label_key, "")
        dr.text((x0, y0 + h + 4), txt[:70], fill="black"); dr.text((x0, y0 + h + 22), txt[70:140], fill="black")
    buf = io.BytesIO(); out.save(buf, "JPEG", quality=82); return buf.getvalue()

def _commons_url(title: str, width: int) -> str | None:
    """Ссылка на уменьшенную копию файла нужной ширины — через API (иначе оригинал в 30 МБ)."""
    try:
        r = requests.get("https://commons.wikimedia.org/w/api.php", headers={"User-Agent": UA}, timeout=60, params={
            "action": "query", "titles": title, "prop": "imageinfo", "iiprop": "url", "iiurlwidth": width, "format": "json"}).json()
        return list(r["query"]["pages"].values())[0]["imageinfo"][0].get("thumburl")
    except Exception: return None

_commons_sem = threading.Semaphore(2)   # upload.wikimedia.org режет параллельные запросы (429)

BROWSER_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"

def _fetch_image(url: str):
    """Commons — с нашим UA и семафором (429); чужие сайты (веб-поиск) — с браузерным UA, иначе многие отдают 403."""
    from PIL import Image
    import time
    wiki = "wikimedia.org" in url or "wikipedia.org" in url
    for attempt in range(4):
        with _commons_sem:
            r = requests.get(url, headers={"User-Agent": UA if wiki else BROWSER_UA, "Referer": "https://www.google.com/"}, timeout=60)
        if r.status_code == 429: time.sleep(2 * (attempt + 1)); continue
        r.raise_for_status(); return Image.open(io.BytesIO(r.content))
    r.raise_for_status()

def _year_of(date: str) -> int | None:
    m = re.search(r"\b(1[89]\d\d|20\d\d)\b", date or "")
    return int(m.group(1)) if m else None

def _photo(x: dict, d, ctx: str, vid: str, q: str | None = None, portrait: bool = False, relaxed: bool = False) -> bool:
    q = q or x.get("query") or ""
    if not q: return False
    tried = set(x.get("_tried") or [])
    seen, cands = set(), []
    short = " ".join(w for w in q.split() if not re.fullmatch(r"(19|20)\d\ds?|young|old|early|late|apple|company", w, re.I))[:60]
    for query in dict.fromkeys([q, short]):   # точный запрос, затем без года и общих слов — в Commons мало снимков с годом в описании
        if not query: continue
        for c in commons_search(query, 12):
            if c["key"] in _used_photos or c["key"] in tried or c["key"] in seen: continue
            seen.add(c["key"]); cands.append(c)
        if len(cands) >= 8: break
    cands = cands[:8]
    if not cands: return False
    items = []
    for c in cands:
        try: items.append({**c, "im": _fetch_image(c["thumb"]), "label": f"{c['key'][5:]} | {c['date']} | {c['desc']}"})
        except Exception as e: print(f"[archive] превью {c['key'][5:50]}: {str(e)[:80]}")
    if not items: return False
    print(f"[archive] {x['id']}: фото-кандидатов {len(items)} по «{q}»")
    place = re.sub(r",.*$", "", x.get("caption") or "").strip() or q
    era = x.get("era") or x.get("era_year")
    era_rule = (f"\nСЦЕНА ПРО {era} ГОД. Портрет должен быть той эпохи (±10 лет по возрасту человека и виду снимка); иначе 0." if portrait and era and not relaxed else "")
    # портреты выбирает основная vision-модель: дешёвая взяла фото компьютера Apple-1 как «портрет Возняка» (16.09)
    res = llm.ask_vision(PICK_PHOTO.replace("{ctx}", ctx).replace("{query}", q).replace("{caption}", _planned_caption(x))
                         .replace("{portrait_rule}", ((PORTRAIT_RELAXED if relaxed else PORTRAIT_RULE) + era_rule) if portrait else "").replace("{place_rule}", PLACE_RULE.replace("{place}", place) if x.get("role") == "inset" else ""),
                         [_grid(items)], model=config.LLM_MODEL_VISION if portrait else config.LLM_MODEL_VISION_CHEAP, tag=f"pickphoto_{x['id']}_{vid}")
    n = int(res.get("n") or 0)
    if not 1 <= n <= len(items):
        x.setdefault("_tried", []).extend(c["key"] for c in items); return False
    c = items[n - 1]
    person = (x.get("person") or "").strip()
    if portrait and person and person.split()[-1].lower() not in (c["key"] + " " + c["desc"]).lower():
        # у Commons имя человека есть в названии или описании файла; нет — модель взяла чужой снимок (Террелл → вывеска магазина в Техасе, 16.09)
        print(f"[archive] {x['id']}: {c['key'][5:60]} — в названии/описании нет «{person}», отклонено")
        x.setdefault("_tried", []).extend(cc["key"] for cc in items); return False
    if not relaxed and (res.get("modern") or re.search(r"\btoday\b", str(res.get("caption") or ""), re.I)):
        # современное здание/место — годится только последним фолбэком: сначала остальные запросы (ежегодник, 1970s)
        # без превью (PngImageFile): кандидат хранится в самом кадре, а тот уезжает в timeline.json — объект картинки
        # не сериализуется и ронял весь этап ассетов (Amazon 18.09). _apply_photo всё равно перекачивает файл по key/url.
        if not x.get("_today"): x["_today"] = ({k: v for k, v in c.items() if k != "im"}, res); print(f"[archive] {x['id']}: современный снимок {c['key'][5:50]} отложен — ищу эпоху")
        x.setdefault("_tried", []).extend(cc["key"] for cc in items); return False
    return _apply_photo(x, d, c, res)

WEB_RULE = ("\nЭто результаты поиска картинок в вебе (не Commons): под каждой — заголовок страницы и сайт. Убедись, что это именно тот человек или предмет "
            "(имя в заголовке), снимок той эпохи (одежда, качество, ч/б), не мерч (футболки, кружки), не рисунок, не кадр из фильма с актёром, "
            "не современный снимок. Сайты магазинов и аукционов допустимы, если на снимке настоящая фотография.\n"
            "ОТДЕЛЬНО ОТСЕКАЙ ИИ-ГЕНЕРАЦИЮ: статьи всё чаще иллюстрируют нарисованными «историческими» снимками. Признаки — слишком ровный "
            "чистый свет, пластиковая кожа, симметричное лицо, бессмысленные буквы на предметах и вывесках, лишние или сросшиеся пальцы, "
            "современный логотип компании в сцене прошлого, безупречная композиция без случайного мусора. Настоящий архивный снимок обычно "
            "зернистый, кривовато скадрирован, с бытовыми деталями в кадре. Сомневаешься — верни 0.")
# контентфермы про знаменитостей и SEO-агрегаторы иллюстрируют статьи ИИ-картинками: 18.09 оттуда пришёл «снимок Безоса,
# пакующего заказ» — чужое лицо, кривые надписи на коробках и логотип-улыбка за пять лет до его появления
WEB_SKIP = re.compile(r"craiyon|lexica\.art|openart\.ai|playgroundai|nightcafe|pixai|civitai|midjourney|stablediffusionweb|starryai|deepai\.org|ideogram|dreamstudio|leonardo\.ai|seaart|tensor\.art|aiease|"   # ИИ-генерации с чужим знаком — не архив (26.09)
                      r"poshmark|etsy|redbubble|aliexpress|teepublic|shutterstock|gettyimages|alamy|dreamstime|istockphoto|pinterest|"
                      # превью стоков идут с водяным знаком поверх кадра и без лицензии (Google 20.09: Adobe Stock в кадре на 17:28)
                      r"stock\.adobe|adobestock|depositphotos|123rf|vecteezy|freepik|pond5|bigstockphoto|canstockphoto|stockvault|"
                      r"shutterstock\.com|dissolve\.com|agefotostock|photodune|stocksy|offset\.com|masterfile|zumapress|imago-images|"
                      # агентства: единственные, кто системно ищет свои снимки и шлёт претензии — под запретом и при «мягких» правах (21.09)
                      r"apimages|apnews\.com|reutersconnect|reuters\.com|afpforum|afp\.com|epaimages|wireimage|filmmagic|corbis|newscom|rexfeatures|"
                      r"paimages|splashnews|backgrid|bridgemanimages|granger\.com|mptvimages|everettcollection|"
                      r"celebpath|celebsagewiki|networth|biographyhost|wikibio|starsunfolded|amarujala|rausr|ceotudent|"
                      # 24.09 (разбор кадров Mercado Libre): фотобанки и агрегаторы чужих картинок, проскочившие мимо списка,
                      # плюс сайты, которые заведомо не первоисточник — обои, сканы документов, витрины магазинов, соцсети
                      r"africaimages|stockcake|wallpapercave|wallpaperaccess|wallhaven|hdwallpapers|peakpx|scribd\.com|slideshare|coursehero|studocu|academia\.edu|animalia-life|creatocustomboxes|sellerportal|rewardly|bidaya\.global|blogspot\.com|wordpress\.com|tumblr\.com|facebook\.com|instagram\.com|tiktok\.com|ebay\.|amazon\.[a-z]{2,3}/|mercadolibre\.com\.[a-z]{2}/[Mm]LA|"
                      # 28.09 (Coca-Cola): магазины печати и постеров — превью всегда с водяным знаком; конструкторы документов — современные шаблоны
                      r"pixels\.com|fineartamerica|pixelsmerch|society6|zazzle|worthpoint|photobucket|dochub|pdffiller|templateroller|"
                      # 29.09 STRATEGY.md: фото деловых изданий с собственными фотослужбами (Copart 26.09: снимок bloomberg.com)
                      r"bloomberg\.com|gettyimages|media\.gettyimages", re.I)

def _web_photo(x: dict, d, ctx: str, vid: str, q: str, portrait: bool = False, relaxed: bool = False) -> bool:
    """Поиск картинок в вебе (DuckDuckGo, без ключа) — когда ни Commons, ни YouTube не дали снимка эпохи. Владелец 16.09: «просто в поиске по имени».
    Снимки чужие: в описание ролика идёт кредит с сайтом (fair use в документальном комментарии, риск ниже, чем у видео)."""
    from ddgs import DDGS
    tried = set(x.get("_tried") or [])
    try: found = DDGS().images(q, max_results=14)
    except Exception as e: print(f"[archive] web {x['id']}: {e}"); return False
    cands = []
    for r in found or []:
        img = r.get("image") or ""; page = r.get("url") or r.get("source") or ""
        if not img or img in tried or img in _used_photos or WEB_SKIP.search(page + " " + img): continue
        try: w, hh = int(r.get("width") or 0), int(r.get("height") or 0)   # DDG отдаёт размеры строками
        except (TypeError, ValueError): w, hh = 0, 0
        if w < 500 or hh < 400: continue
        dom = re.sub(r"^https?://(www\.)?", "", page).split("/")[0]
        cands.append({"key": img, "url": img, "thumb": r.get("thumbnail") or img, "w": w, "h": hh, "license": "web (fair use)",
                      "artist": dom, "date": "", "desc": (r.get("title") or "")[:160], "page": page})
    cands = cands[:8]
    if not cands: return False
    items = []
    for c in cands:
        try: items.append({**c, "im": _fetch_image(c["thumb"]), "label": f"{c['desc'][:70]} | {c['artist']} | {c['w']}x{c['h']}"})
        except Exception as e: print(f"[archive] web превью {c['artist']}: {str(e)[:60]}")
    if not items: return False
    print(f"[archive] {x['id']}: веб-кандидатов {len(items)} по «{q}»")
    era = None if relaxed else (x.get("era") or x.get("era_year"))   # мягкий режим: снимка эпохи нет — годится поздний того же человека
    era_rule = (f"\nСЦЕНА ПРО {era} ГОД. Снимок должен быть той эпохи (±10 лет): возраст человека, причёска, одежда, качество и цвет фото. "
                f"Современный снимок постаревшего человека под сцену {era} года — брак, верни 0. В JSON добавь \"era_ok\": true|false.") if era else ""
    prompt = (PICK_PHOTO.replace("{ctx}", ctx).replace("{query}", q).replace("{caption}", _planned_caption(x))
              .replace("{portrait_rule}", (PORTRAIT_RELAXED if relaxed else PORTRAIT_RULE) if portrait else "").replace("{place_rule}", "") + WEB_RULE + (era_rule if era else ""))
    # веб-выдача шумная (обои, мерч, современные фото): портреты выбирает основная vision-модель — дешёвая взяла седого Возняка под 1976 год
    res = llm.ask_vision(prompt, [_grid(items)], model=config.LLM_MODEL_VISION if portrait else config.LLM_MODEL_VISION_CHEAP, tag=f"pickweb_{x['id']}_{vid}")
    n = int(res.get("n") or 0)
    # в мягком режиме современный снимок того же человека — ровно то, что ищем (год снимка честно уйдёт в подпись)
    if not 1 <= n <= len(items) or (res.get("modern") and not relaxed) or (era and res.get("era_ok") is False):
        x.setdefault("_tried", []).extend(c["key"] for c in items); return False
    c = items[n - 1]
    if not _apply_photo(x, d, c, res): return False
    mark = _corner_watermark(d / x["image"]) if x.get("image") else None
    if mark:   # чужой знак в углу: обрезать нельзя (снятие авторства), кадр не берём — ищем следующего кандидата
        print(f"[archive] {x['id']}: водяной знак «{mark}» — кадр отброшен", flush=True)
        x.setdefault("_tried", []).append(c["key"]); x["src"] = None; x["image"] = None; x["kind"] = None
        try: (d / "archive" / f"{x['id']}.jpg").unlink(missing_ok=True)
        except Exception: pass
        return False
    x["credit"] = f"photo: {c['artist']}"; x["archive"] = {"type": "web", "key": c["key"], "url": c["page"], "description": c.get("desc"), "date": c.get("date"), "why": res.get("why", "")}
    return True

MARK_TEXT = re.compile(r"(?:https?://|www\.)|\b[a-z0-9-]{3,}\.(?:com|net|org|ru|de|dk|uk|io|me|info|biz|news|tv|photo|club|global)\b|"
                       r"\u00a9|\(c\)\s*\d|getty|shutterstock|alamy|reuters|associated\s*press|\bap\s+photo\b|\bafp\b|\bepa\b|"
                       r"istock|depositphotos|dreamstime|adobe\s*stock|stock\s*photo|all\s+rights\s+reserved", re.I)

def _corner_watermark(path) -> str | None:
    """Знак сайта/фотобанка в углу снимка. Смотрим четыре угла в исходном разрешении: в общей сетке кандидатов
    такая надпись мельче пикселя и всегда проходит мимо (Boston Market 24.09: «thedailymeal.com» в кадре)."""
    from PIL import Image
    try:
        im = Image.open(path).convert("RGB"); w, h = im.size
        cw, ch = max(160, w // 3), max(90, h // 4)
        boxes = [(0, 0, cw, ch), (w - cw, 0, w, ch), (0, h - ch, cw, h), (w - cw, h - ch, w, h)]
        crops = [im.crop(b) for b in boxes]
        cwid = max(c.width for c in crops); chei = max(c.height for c in crops)
        sheet = Image.new("RGB", (cwid * 2, chei * 2), (12, 12, 12))
        for i, c in enumerate(crops): sheet.paste(c, ((i % 2) * cwid, (i // 2) * chei))
        buf = io.BytesIO(); sheet.save(buf, "JPEG", quality=88)
        r = llm.ask_vision("Это четыре угла одной фотографии. Есть ли на них водяной знак, название сайта, адрес в интернете, "
                           "логотип фотобанка, подпись агентства или наложенный логотип телеканала? Обычные вывески, надписи на "
                           "зданиях, номера машин и текст в самой сцене — НЕ водяной знак. "
                           'Верни JSON: {"mark": true|false, "text": "что именно написано, если есть"}',
                           [buf.getvalue()], model=config.LLM_MODEL_VISION_CHEAP, tag="watermark")
        t = (r.get("text") or "").strip()
        if not r.get("mark") or not t: return None
        # модель зовёт знаком любую вывеску в кадре («BUD LIGHT», «Nasdaq»), поэтому берём только то, что похоже
        # на настоящий знак: адрес сайта, копирайт или имя агентства (Boston Market 24.09: 15 находок, настоящих 3)
        if MARK_TEXT.search(t): return t[:60]
        return None
    except Exception as e:
        print(f"[archive] проверка водяного знака не удалась: {str(e)[:70]}", flush=True); return None

CLAIM_CAP = re.compile(r"\b(annual report|10-?k|filing|prospectus|certificate|contract|agreement|ledger|balance sheet|statement|memo|memorandum|invoice|receipt|logo|letterhead|chart|graph|blueprint|patent|press release|earnings)\b", re.I)


def _caption_for(res: dict, planned: str) -> str:
    """Подпись кадра: только то, что модель зрения реально увидела. Планируемую подпись берём как запасную,
    НО не тогда, когда она называет конкретный документ или логотип — иначе на экране появляется утверждение,
    которого на снимке нет (Boston Market 24.09: «Blockbuster Annual Report» под чужой бумагой)."""
    seen = (res.get("caption") or "").strip()
    if seen: return seen
    planned = (planned or "").strip()
    return "" if planned and CLAIM_CAP.search(planned) else planned


def _apply_photo(x: dict, d, c: dict, res: dict) -> bool:
    if x.get("person") and str(c.get("key", "")).startswith("File:"):   # 27.09: портрет — только если фамилия есть в описании файла
        sur = re.sub(r"[^a-z]", "", str(x["person"]).split()[-1].lower())
        ev = re.sub(r"[^a-z]", "", f"{c.get('key', '')} {c.get('desc', '')}".lower())
        if len(sur) >= 3 and sur not in ev:
            print(f"[archive] {x['id']}: {str(c.get('key'))[5:60]} — в описании файла нет «{x['person']}», не беру", flush=True); return False
    try: im = _fetch_image(_commons_url(c["key"], 1920) or c["url"]).convert("RGB")
    except Exception as e:
        # сайт отдал страницу вместо файла (защита от хотлинка) — берём превью, которое модель уже видела и выбрала
        # (Мигель Безос 18.09: верный снимок выбран, а heightline.com на полный размер ответил HTML — слот остался пустым)
        try:
            if not c.get("thumb") or c["thumb"] == c.get("url"): raise ValueError("превью нет")
            im = _fetch_image(c["thumb"]).convert("RGB")
            if im.width < 300: raise ValueError(f"превью {im.width}px — слишком мелкое")
            print(f"[archive] {x['id']}: полный файл не скачался ({str(e)[:50]}) — взято превью {im.width}x{im.height}")
        except Exception as e2:
            print(f"[archive] {x['id']}: {c['key'][5:50]} не скачался: {e} / превью: {str(e2)[:60]}"); return False
    (d / "archive").mkdir(exist_ok=True); out = d / "archive" / f"{x['id']}.jpg"
    im.thumbnail((1920, 1920)); im.save(out, "JPEG", quality=90)
    with _lock: _used_photos.add(c["key"])
    x["src"] = None; x["image"] = f"archive/{x['id']}.jpg"; x["aspect"] = round(im.width / im.height, 3); x["kind"] = "archive"
    x["clip_seconds"] = None; x["year"] = _year_of(c["date"]) or _year_of(str(res.get("year") or ""))   # год снимка — для грейда по эпохе в Slot.tsx
    cap = _strip_unsourced_year(_caption_for(res, x.get("caption") or ""), f"{c['date']} {c['desc']} {c['key']} {res.get('year') or ''}")
    if not x.get("person"):   # у портрета имя проверяет PORTRAIT_RULE и person_caption
        cap = _strip_unsourced_name(cap, f"{c['desc']} {c['key']}")
    if x.get("person"): cap = person_caption(x["person"], cap, x["year"])
    x["caption"] = _clean_cap(cap) if cap else None
    x["credit"] = f"{c['artist'] or 'unknown'} / Wikimedia Commons ({c['license']})"
    x["archive"] = {"type": "photo", "key": c["key"], "url": c.get("url"), "description": c.get("desc"), "license": c["license"], "date": c["date"], "why": res.get("why", "")}
    return True

# ---------- видео: YouTube через yt-dlp ----------

def _ffdir() -> str:
    """yt-dlp ищет в ffmpeg_location файлы с именами ffmpeg.exe/ffprobe.exe: собираем такую папку из полного ffmpeg (imageio) и ffprobe Remotion."""
    import imageio_ffmpeg
    b = config.DATA / "bin"; b.mkdir(parents=True, exist_ok=True)
    ff = b / ("ffmpeg.exe" if config.os.name == "nt" else "ffmpeg")
    if not ff.exists(): shutil.copy(imageio_ffmpeg.get_ffmpeg_exe(), ff)
    fp = b / ("ffprobe.exe" if config.os.name == "nt" else "ffprobe")
    if not fp.exists() or not config._runs(str(fp)):
        # ffprobe Remotion — 170 КБ и тянет соседние av*.dll: без них копия падает с 3221225781, а папка уходит в PATH
        try:
            src = pathlib.Path(config.ffprobe())
            shutil.copy(src, fp)
            for dll in src.parent.glob("*.dll"):
                if not (b / dll.name).exists(): shutil.copy(dll, b / dll.name)
            if not config._runs(str(fp)): fp.unlink(missing_ok=True); print("[archive] ffprobe в data/bin не запускается — убран", flush=True)
        except Exception as e:
            fp.unlink(missing_ok=True); print(f"[archive] ffprobe не скопирован: {str(e)[:80]}", flush=True)
    # проверка «ffmpeg установлен?» перед скачиванием отрезка смотрит только в PATH, ffmpeg_location ей не указ
    if str(b) not in config.os.environ.get("PATH", ""): config.os.environ["PATH"] = str(b) + config.os.pathsep + config.os.environ.get("PATH", "")
    return str(b)

def _ydl(**kw):
    import yt_dlp
    return yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "skip_download": True, "ffmpeg_location": _ffdir(), **kw})

def yt_search(q: str, n: int = 5) -> list[dict]:
    with _ydl(extract_flat=True) as y: r = y.extract_info(f"ytsearch{n}:{q}", download=False)
    return [e for e in (r.get("entries") or []) if e.get("duration") and 20 <= e["duration"] <= YT_MAX_SEC]

def yt_info(video_id: str) -> dict:
    with _lock:
        if video_id in _yt_info: return _yt_info[video_id]
    with _ydl() as y: info = y.extract_info(video_id, download=False)
    with _lock: _yt_info[video_id] = info
    return info

def storyboard(info: dict) -> list[tuple[float, object]]:
    """[(секунда, PIL-плитка)] по раскадровке YouTube — превью всего ролика без скачивания видео."""
    from PIL import Image
    sbs = [f for f in info.get("formats", []) if f.get("format_note") == "storyboard" and f.get("fragments")]
    if not sbs: return []
    sb = max(sbs, key=lambda f: (f.get("width") or 0)); rows, cols = sb.get("rows") or 5, sb.get("columns") or 5
    fps = sb.get("fps") or 0.2; tw, th = sb.get("width") or 160, sb.get("height") or 90
    tiles, k = [], 0
    for fr in sb["fragments"]:
        try: im = Image.open(io.BytesIO(requests.get(fr["url"], headers={"User-Agent": UA}, timeout=60).content)).convert("RGB")
        except Exception: k += rows * cols; continue
        for r in range(rows):
            for c in range(cols):
                t = k / fps; k += 1
                if t > (info.get("duration") or 1e9): break
                tile = im.crop((c * tw, r * th, (c + 1) * tw, (r + 1) * th))
                if tile.getbbox(): tiles.append((t, tile))
    return tiles

PICK_TILE = """Документальное видео об истории компании. Нужен настоящий видеофрагмент под фразу озвучки:
«{ctx}»
Что ищем: {query}. Планируемая подпись: «{caption}». Ролик YouTube: «{title}» ({year}). Ниже раскадровка ролика: плитки с номерами и секундой.
Выбери ОДНУ плитку, где в кадре именно это: тот человек, предмет, место, событие — и это выглядит как хроника той эпохи (архивная съёмка, ТВ-интервью тех лет, реклама, фото тех лет в кадре, экран той машины).
Не бери: современного ведущего, блогера или студию (в том числе человека из прошлого, но постаревшего, если подпись про его молодость); заставки, титульные карточки, плашки телеканалов и текст на весь экран; инфографику, графики, анимации и коллажи других авторов; тёмные и чёрные кадры; мелкие объекты на пустом фоне; чужие логотипы; крупное лицо другого человека.
Эпоха: если фраза про прошлое, а плитка — современная съёмка, брать можно ТОЛЬКО место или здание (не людей), и тогда подпись без года, со словом today («Homestead High School today»). Подписывать современный кадр прошлым годом нельзя.
Название канала, сайта или водяной знак в углу плитки (даже полупрозрачный) — это modern_overlay=true, такую плитку не бери. Вшитые субтитры поверх речи и таймкод в углу (01:16:04;12) — тоже modern_overlay=true.
Название ролика — тоже свидетельство: если оно говорит о другом городе, объекте или событии (zoo, ride, gondola, parade, другой город), плитка не подходит, даже если пейзаж похож.
Верни JSON: {"n": <номер плитки или 0, если подходящего нет>, "period_footage": true|false (плитка — настоящая съёмка или фото той эпохи, а не современная графика, анимация, 3D или вырезанный предмет с датой), "modern_overlay": true|false (логотип канала, плашка, заголовок, ведущий, водяной знак в углу), "year": <год съёмки по названию ролика или по кадру, иначе null>, "why": "коротко", "caption": "подпись: если планируемая верна для этой плитки — она же, иначе поправь (кто/что, год или today), ≤6 слов, по-английски"}"""

VERIFY_CLIP = """Это три кадра из вырезанного видеофрагмента (начало, середина, конец) для документального видео. Фраза озвучки: «{ctx}».
Планируемая подпись: «{caption}». Что искали: {query}. Ролик, из которого вырезан фрагмент: «{title}».
Ответь по каждому пункту честно, по всем трём кадрам сразу:
- period_footage: это настоящая съёмка или фото ТОЙ эпохи (зерно плёнки, 4:3, одежда и техника времени, ТВ-графика тех лет)? Современная анимация, инфографика, 3D-модель, вырезанный на белом фоне предмет с крупной датой, студийная графика — это false.
- matches: на кадрах именно то, что ищем (тот человек, предмет, место, событие), и подпись верна для того, что видно? Если название ролика называет другой город, объект или событие (zoo, ride, gondola, parade, другой город), чем подпись, — matches=false: подписать чужое место реальным именем нельзя.
- modern_overlay: есть ли логотип или водяной знак телеканала/ютуб-канала (в том числе мелкое название канала или сайта в углу кадра), современная плашка, крупный заголовок, ведущий или блогер, постаревший герой (когда подпись про его молодость)? Любой водяной знак в углу — true. Вшитые субтитры (строка текста поверх речи, например «UNABLE TO SEE A») и таймкод монтажной копии (цифры вида 01:16:04;12 в углу) — тоже true.
- dark_or_tiny: кадры тёмные, пустые или объект крошечный?
Верни JSON: {"period_footage": true|false, "matches": true|false, "modern_overlay": true|false, "dark_or_tiny": true|false, "year": <год съёмки по названию ролика или кадру, иначе null>, "why": "коротко", "caption": "подпись ≤6 слов, по-английски: кто/что и год (та же или исправленная)"}"""

def _video(x: dict, d, ctx: str, vid: str, q: str | None = None, portrait: bool = False) -> bool:
    import imageio_ffmpeg
    q = q or x.get("query") or ""
    if not q: return False
    tried = set(x.get("_tried") or [])
    cands = [c for c in yt_search(q, 6) if c["id"] not in tried]
    # каналы новостных/объяснительных медиа с водяным знаком в углу исключаем целиком, а не понижаем
    cands = [c for c in cands if not BAD_CHANNEL.search(f"{c.get('channel') or ''} {c.get('uploader') or ''} {c.get('title') or ''}")
             and not BAD_TITLE.search(c.get("title") or "")]
    cands.sort(key=lambda c: (_rank(c.get("title") or ""), c["duration"]))
    for c in cands[:3]:
        try:
            info = yt_info(c["id"]); tiles = storyboard(info)
        except Exception as e:
            print(f"[archive] yt {c['id']}: {e}"); continue
        if len(tiles) < 4: continue
        used = _used_yt.get(c["id"], [])
        tiles = [t for t in tiles if all(abs(t[0] - u) > CLIP_SEC for u in used)]
        if len(tiles) > MAX_TILES:
            step = len(tiles) / MAX_TILES; tiles = [tiles[int(i * step)] for i in range(MAX_TILES)]
        items = [{"im": im, "label": f"{int(t)//60}:{int(t)%60:02d}"} for t, im in tiles]
        year = (info.get("upload_date") or "")[:4]
        res = llm.ask_vision(PICK_TILE.replace("{ctx}", ctx).replace("{query}", q).replace("{title}", info.get("title") or "").replace("{year}", year).replace("{caption}", _planned_caption(x)),
                             [_grid(items, cols=6, w=240, h=135)], model=config.LLM_MODEL_VISION_CHEAP, tag=f"picktile_{x['id']}_{vid}")
        n = int(res.get("n") or 0)
        if not 1 <= n <= len(tiles) or res.get("period_footage") is not True or res.get("modern_overlay") is not False:
            print(f"[archive] {x['id']}: ролик {c['id']} не подошёл — {res.get('why', '')[:80]}"); x.setdefault("_tried", []).append(c["id"]); continue
        t = max(0.0, tiles[n - 1][0] - 1.0)
        t = min(t, max(0.0, (info.get("duration") or CLIP_SEC) - CLIP_SEC))
        t_abs = t
        src, t = _download(info, d, t)
        sw, sh = _dims(src)
        if sw < config.VIDEO_MIN_WIDTH:   # 320×240 на 1080p — каша даже без плёнки
            print(f"[archive] {x['id']}: ролик {c['id']} — исходник {sw}×{sh}, уже {config.VIDEO_MIN_WIDTH} px"); x.setdefault("_tried", []).append(c["id"]); continue
        (d / "archive").mkdir(exist_ok=True); out = d / "archive" / f"{x['id']}.mp4"
        subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-v", "error", "-ss", f"{t:.2f}", "-i", str(src), "-t", str(CLIP_SEC), "-an",
                        "-vf", "scale='min(1920,iw)':-2", *config.ARCHIVE_X264, str(out)], check=True)
        with _lock: _used_yt.setdefault(c["id"], []).append(t_abs)
        cap = _caption_for(res, x.get("caption") or "")
        chk = _verify_clip(out, ctx, q, _planned_caption(x), x["id"], vid, info.get("title") or "")
        if not chk.get("ok"):
            print(f"[archive] {x['id']}: фрагмент {c['id']}@{int(t_abs)} отклонён — {chk.get('why', '')}")
            x.setdefault("_tried", []).append(c["id"])   # 23.09: отклонённый ролик выбирался снова и снова — до 29 проверок зрением на один слот
            out.unlink(missing_ok=True); continue
        cap = (chk.get("caption") or cap).strip()
        yr = _year_of(str(chk.get("year") or res.get("year") or "")) or _year_of(cap) or _year_of(info.get("title") or "")
        if portrait or x.get("person"): cap = person_caption(x.get("person") or x.get("caption"), cap, yr)
        w, h = _dims(out)
        x["image"] = None; x["src"] = f"archive/{x['id']}.mp4"; x["clip_seconds"] = CLIP_SEC; x["aspect"] = round(w / h, 3) if h else 1.78; x["kind"] = "archive"
        x["src_px"] = [w, h]; x["year"] = yr
        x["caption"] = _clean_cap(cap) if cap else None
        # на экране — только канал (две строки кредита рядом с карточкой архива перегружали кадр); название ролика — в описание (credits)
        x["credit"] = f"YouTube: {(info.get('channel') or info.get('uploader') or '')[:48]}"
        x["archive"] = {"type": "video", "key": f"yt:{c['id']}@{int(t_abs)}", "url": f"https://youtu.be/{c['id']}?t={int(t_abs)}", "why": res.get("why", ""),
                        "title": info.get("title", ""), "description": (info.get("description") or "")[:2000]}
        return True
    return False

def _download(info: dict, d, t: float):
    """Только нужный отрезок видеодорожки ≤720p (yt-dlp режет через ffmpeg по HTTPS): секунды, а не весь ролик.
    Возвращает файл и смещение искомого момента внутри него. Если отрезок не вышел — весь ролик (кэш в yt/)."""
    from yt_dlp.utils import download_range_func
    cache = config.DATA / "cache" / "yt"; cache.mkdir(parents=True, exist_ok=True)   # вне папки видео: Remotion копирует public dir целиком
    a = max(0.0, t - 1.0); b = a + CLIP_SEC + 3
    part = cache / f"{info['id']}_{int(a)}.mp4"
    if not (part.exists() and part.stat().st_size > 50000):
        try:
            with _ydl(skip_download=False, outtmpl=str(part), format="bv*[ext=mp4][height<=720][protocol^=http]/bv*[height<=720]/b[height<=720]",
                      merge_output_format="mp4", download_ranges=download_range_func(None, [(a, b)]), force_keyframes_at_cuts=True) as y:
                y.download([f"https://www.youtube.com/watch?v={info['id']}"])
        except Exception as e:
            print(f"[archive] отрезок {info['id']}@{int(a)}: {e}")
            import os, time
            pp = part.with_name(part.name + ".part")
            for _ in range(5):   # свежий файл держит антивирус: yt-dlp сдаётся после 3 попыток переименования (Microsoft 19.09, 4 из 36)
                if part.exists() or not pp.exists(): break
                time.sleep(3)
                try: os.replace(pp, part); print(f"[archive] отрезок {info['id']}@{int(a)}: переименован со второй попытки")
                except OSError: pass
    if part.exists() and part.stat().st_size > 50000: return part, t - a
    full = cache / f"{info['id']}.mp4"
    if not (full.exists() and full.stat().st_size > 100000):
        with _ydl(skip_download=False, outtmpl=str(full), format="bv*[ext=mp4][height<=480][protocol^=http]/bv*[height<=480]/b[height<=480]",
                  merge_output_format="mp4") as y:
            y.download([f"https://www.youtube.com/watch?v={info['id']}"])
        if not full.exists():   # yt-dlp мог добавить расширение
            cand = next(iter(cache.glob(f"{info['id']}.*")), None)
            if cand: cand.rename(full)
    return full, t

GOOD = re.compile(r"\b(19[2-9]\d|200\d|archiv|vintage|original|commercial|interview|documentary|footage|newsreel|rare|full|keynote|introduc|unveil)", re.I)
BAD = re.compile(r"\b(explained|explain|why |how |history of|history:|story of|the story|rise of|fall of|evolution|top \d|vs\.?|reaction|review|unboxing|shorts?|tiktok|"
                 r"bar chart|ranking|timeline|animation|animated|explainer)", re.I)
BAD_CHANNEL = re.compile(r"\b(yahoo|cnbc|insider|vox|wsj|verge|bloomberg|"
                         # 29.09 STRATEGY.md, раздел 11: агентства и вещатели — единственные, кто системно шлёт претензии за видео
                         r"reuters|associated press|ap archive|afp|getty|british path[eé]|cnn|msnbc|nbc news|cbs news|abc news|fox news|fox business|"
                         r"espn|nfl|nba|mlb|nhl)\b", re.I)   # исключаются полностью (§2.2)
# 29.09 STRATEGY.md, раздел 11: без фрагментов рекламы, фильмов и трансляций правообладателя — только по названию ролика
BAD_TITLE = re.compile(r"\b(commercials?|tv ad|tv spot|advert(isement)?s?|trailer|full movie|full film|full episode|full game|highlights|"
                       r"super bowl|official video|music video|livestream|live stream)\b", re.I)

def _rank(title: str) -> int:
    """Хроника вперёд (год, interview, commercial, footage), современные объяснялки и инфографика — назад."""
    return (0 if GOOD.search(title) else 1) + (2 if BAD.search(title) else 0)

def _verify_clip(path, ctx: str, q: str, cap: str, sid: str, vid: str, title: str = "") -> dict:
    from PIL import Image
    ims = []
    for t in (1.0, CLIP_SEC * 0.3, CLIP_SEC / 2, CLIP_SEC * 0.7, CLIP_SEC - 1.5):   # 3 кадра пропускали титр посреди клипа («A COMPANY BUILT IN»)
        r = subprocess.run([config.ffmpeg(), "-v", "error", "-ss", f"{t:.2f}", "-i", str(path), "-frames:v", "1", "-vf", "scale=640:-1",
                            "-f", "image2pipe", "-vcodec", "png", "-"], capture_output=True)
        if r.stdout: ims.append({"im": Image.open(io.BytesIO(r.stdout)), "label": f"{t:.0f}s"})
    if len(ims) != 5: return {"ok": False, "why": "извлечены не все контрольные кадры"}
    try:
        r = llm.ask_vision(VERIFY_CLIP.replace("{ctx}", ctx).replace("{caption}", cap).replace("{query}", q).replace("{title}", title[:120]),
                           [_grid(ims, cols=3, w=520, h=300)], tag=f"verify_{sid}_{vid}")
    except Exception as e:
        return {"ok": False, "why": f"проверка не удалась: {e}"}
    if not isinstance(r, dict): return {"ok": False, "why": "неполный ответ проверки"}
    ok = (r.get("period_footage") is True and r.get("matches") is True
          and r.get("modern_overlay") is False and r.get("dark_or_tiny") is False)
    return {"ok": ok, "why": r.get("why", "") + ("" if ok else f" [period={r.get('period_footage')} match={r.get('matches')} overlay={r.get('modern_overlay')} dark={r.get('dark_or_tiny')}]"),
            "caption": r.get("caption"), "year": r.get("year")}

def _dims(path) -> tuple[int, int]:
    """Размер видео: ffprobe, иначе первый кадр через ffmpeg + PIL; (16, 9) только если файл не читается вовсе."""
    try:
        o = subprocess.check_output([config.ffprobe(), "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0", str(path)])
        w, h = o.decode().strip().split(",")[:2]; return int(w), int(h)
    except Exception: pass
    try:
        from PIL import Image
        r = subprocess.run([config.ffmpeg(), "-v", "error", "-ss", "0.5", "-i", str(path), "-frames:v", "1", "-f", "image2pipe", "-vcodec", "png", "-"], capture_output=True)
        im = Image.open(io.BytesIO(r.stdout)); return im.width, im.height
    except Exception: return 16, 9

def credits(shots: list[dict]) -> str:
    """Строка для описания на YouTube: источники реальных кадров."""
    lines, seen = [], set()
    for x in shots:
        for sl in (x.get("slots") if isinstance(x.get("slots"), list) and "source" not in x else [x]):
            a = sl.get("archive") or {}
            c = sl.get("credit") or ""
            if not c or c in seen: continue
            seen.add(c); lines.append("- " + c + (f" — {a['title']}" if a.get("title") else "") + (f" {a['url']}" if a.get("url") else ""))
    return "\n".join(lines[:40])
