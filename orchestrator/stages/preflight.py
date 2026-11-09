"""Визуальная проверка кадров story-видео ДО рендера: лист из ассетов каждого слота (картинка или кадр из клипа) с подписью, что должно быть,
→ модель с картинками отмечает брак и нерелевантность → плохие слоты заменяются с сохранением типа сцены (архив → другой кандидат;
портрет people без замены → колонка activity-only; картинка → перегенерация с очищенным промптом). Экономит час рендера на каждую итерацию."""
import copy, io, json, re, subprocess
from concurrent.futures import ThreadPoolExecutor
from .. import db, config, llm, visual_integrity
from . import assets as A
from . import story_assets as SA
from . import story

TEXTY = re.compile(r"\b(whiteboard|blackboard|chalkboard|sign|signage|banner|label|labeled|lettering|written|writing|text|words?|"
                   r"headline|newspaper|document|contract|policy|coin|coins|ticker|chart with numbers|logo|slogan|handwriting|notes?)\b", re.I)

def sanitize_prompt(p: str) -> str:
    """Убираем всё, что заставляет генератор рисовать буквы; добавляем явный запрет."""
    q = TEXTY.sub("", p or "")
    q = re.sub(r"\s{2,}", " ", q).strip(" ,.")
    return q + ", no writing anywhere, blank surfaces"

def frame_of(x: dict, d, at: float | None = None, width: int = 480) -> bytes | None:
    """Представительный кадр ассета: картинка как есть, у клипа — середина."""
    if x.get("src"):
        path = d / x["src"]; t = at if at is not None else max(0.5, (x.get("clip_seconds") or 6) / 2)
        r = subprocess.run([config.ffmpeg(), "-v", "error", "-ss", f"{t:.2f}", "-i", str(path), "-frames:v", "1", "-vf", f"scale={width}:-1",
                            "-f", "image2pipe", "-vcodec", "png", "-"], capture_output=True)
        return r.stdout or None
    if x.get("image"):
        from PIL import Image
        im = Image.open(d / x["image"]).convert("RGB"); im.thumbnail((width, width)); buf = io.BytesIO(); im.save(buf, "PNG"); return buf.getvalue()
    return None

def is_blank(png: bytes, archive: bool = False) -> bool:
    """Почти чёрный/белый или плоский кадр (фейд, заглушка). Для архива порог мягче: экраны старых компьютеров и ночная хроника — тёмные, но не пустые."""
    from PIL import Image, ImageStat
    im = Image.open(io.BytesIO(png)).convert("L"); st = ImageStat.Stat(im)
    if archive: return st.stddev[0] < 4 or (st.mean[0] < 6 and st.stddev[0] < 12) or st.mean[0] > 248
    return st.mean[0] < 18 or st.mean[0] > 238 or st.stddev[0] < 8

PROMPT = """Это кадры документального видео об истории компании: по одному кадру на слот сцены. Под номером — что на кадре ДОЛЖНО быть (замысел).
Отметь кадры, которые нельзя использовать:
- пустые, чёрные, белые, размытые в кашу;
- БЕЗ ГЛАВНОГО ОБЪЕКТА: голая стена, пустой стол, пустой угол комнаты, одинокий предмет на белом фоне, «минималистичная»
  композиция из одной коробки или листа бумаги. Зритель должен понимать, ЧТО ему показывают. Пустое помещение годится только
  тогда, когда пустота и есть смысл кадра (заброшенный офис под фразу о сокращениях) — иначе это брак;
- с ЛЮБЫМИ буквами, цифрами, надписями, логотипами, водяными знаками (даже мелкими, даже «правдоподобными»: неоновые вывески, коробки с маркировкой, книги с названием, экраны с текстом, диаграммы с подписями) и с псевдо-надписями — закорючками, похожими на текст, на панелях приборов, страницах и табличках;
- явно не по замыслу (замысел про завод — на кадре пиццерия; здание не того типа — мотель вместо школы; «blue box» — самодельный тоновый генератор с кнопками, а не синяя пластиковая коробка; «adding machine» — механический арифмометр с рулоном бумажной ленты, а не пишущая машинка);
- кадры с пометкой [hands] — фраза про реального названного человека: любое лицо, фигура, силуэт или человек со спины в кадре — брак (сгенерированный «двойник» под именем героя недопустим; только руки и предметы);
- АНАХРОНИЗМ: предмет, одежда, устройство или интерьер не из эпохи сцены (эпоха — в подписи под номером, «~1971» или десятилетие в замысле): планшет, смартфон, ноутбук, плоский монитор, наушники-вкладыши, современная одежда и причёски, современные автомобили в сцене про 1950–80-е — брак;
- уродливые артефакты генерации (лишние пальцы, сломанные лица, кривые предметы);
- стоковая «корпоративная» клишированность (рукопожатия в костюмах, ненатуральные улыбки в камеру), если замысел не про это;
- кадры с пометкой [activity] — иллюстрации занятия человека: на них НЕ должно быть ни одного человека, фигуры, силуэта или лица (только предметы и руки); любая фигура — брак.
Верни результат для каждого номера по схеме checks ниже."""

PROMPT_CARTOON = """Это кадры РИСОВАННОГО документального ролика об истории компании (тушь и акварель, кадр-виньетка на бумаге; обычные люди —
человечки с круглыми белыми головами, названные люди — шаржи). Под номером — что на кадре ДОЛЖНО быть (замысел). Отметь кадры, которые нельзя использовать:
- пустые, битые, размытые в кашу; без главного объекта (зритель не понимает, что показывают);
- надписи: НЕ по-испански, с ошибками в словах, абракадабра, псевдотекст или длиннее 6 слов в одной надписи — брак; короткие испанские реплики в пузырях и подписи на схемах — норма;
- явно не по замыслу (не тот предмет, не то место, не тот человек в шарже);
- АНАХРОНИЗМ: предмет, одежда, устройство не из эпохи сцены;
- уродливые артефакты генерации (лишние пальцы, сломанные лица);
- фотография или 3D-рендер вместо рисунка.
Верни результат для каждого номера по схеме checks ниже."""

PROMPT_ARCHIVE = """Это РЕАЛЬНЫЕ архивные кадры (фото и хроника) документального видео об истории компании: по одному кадру на слот сцены. Под номером — что на кадре должно быть и подпись, которую поставим.
Отметь только кадры, которые нельзя использовать:
- пустые, чёрные, белые, размытые в кашу, слишком мелкие или пикселизированные;
- современный ведущий, блогер или студия вместо хроники; заставка, титульная карточка или текст на весь экран; чужой логотип телеканала во весь угол; название канала или сайта, водяной знак в углу кадра;
- явно не то и не тот: другой человек, чем в подписи; современный кадр там, где подпись про прошлое; предмет не по замыслу;
- слот с пометкой [portrait] — портрет для колонки с именем: если это не тот человек, групповое фото без него в центре, памятник или рисунок — брак.
- вшитые субтитры (строка текста поверх речи) или таймкод монтажной копии в углу (01:16:04;12) — брак: владелец видит их как мусор на кадре;
Зерно старой плёнки и мелкая подпись телеканала эпохи внизу — норма.
Подлинная атрибутированная страница исторического документа или её выдержка — не заставка и не современная текстовая карточка. Если замысел требует документ, проверь именно его компанию, содержание, источник и даты. Чужой документ, поддельные строки, сгенерированная финансовая бумага или неподтверждённая атрибуция по-прежнему запрещены.
Верни результат для каждого номера по схеме checks ниже."""

PORTRAIT_CHECK = """Это кадр, который мы собираемся показать в колонке с именем человека в документальном фильме.
ИМЯ НА КАРТОЧКЕ: {name}
КЕМ БЫЛ: {role}
ЭПОХА СЦЕНЫ: {era}
ГОДЫ ЖИЗНИ: {years}
ГОД СНИМКА (по подписи/файлу): {photo_year}
ДРУГИЕ ЛЮДИ ЭТОЙ ИСТОРИИ (их фото под этим именем — ошибка): {others}

Ответь честно и строго, это важнее вежливости:
1. Видно ли на кадре ЛИЦО человека — различимое, не со спины, не силуэт, не вдалеке, не в толпе? Экран, слайд, здание,
   улица, предмет, логотип — это НЕ портрет. Лицо должно быть ЦЕЛИКОМ: если глаза или лоб срезаны краем снимка
   (виден только рот, подбородок, галстук) — это НЕ портрет (Copart 26.09).
2. Похоже ли, что это именно тот человек: пол, примерный возраст для этой эпохи, род занятий. Если на кадре военный
   в форме, а человек — профессор информатики; если снимок XIX века, а человек жил в XX — это другой человек (однофамилец).
   ВОЗРАСТ: если известны годы жизни и год снимка, посчитай, сколько человеку должно быть лет на снимке. Явно другой возраст
   (First American 26.09: «Bill Foley, 2009» — мужчина лет сорока с тёмными волосами, а Фоли 1944 г. р. тогда было 64) — plausible=false.
3. Если человек на кадре узнаваем как кто-то ДРУГОЙ — из списка выше или широко известная личность (McDonald's 22.09: под именем
   Мориса Макдональда стояло знаменитое фото Рэя Крока с бургером у вывески) — plausible=false и напиши, кто это.
В остальном не угадывай личность по чертам лица — оценивай явные несоответствия.

Верни JSON: {{"face": true|false, "plausible": true|false, "why": "одна фраза"}}"""

def verify_portraits(d, tl: dict, vid: str = "") -> list[str]:
    """Портрет под именем человека: есть ли вообще лицо и не однофамилец ли это (Google 21.09: под «Carl Victor Page»
    стоял солдат Первой мировой, под «Gloria Page» — снимок 1940-х с findagrave, под двумя основателями — экран и слайд).
    Негодные слоты очищаются: карточка честно покажет иллюстрацию занятия, а не чужое лицо."""
    jobs = []
    for sc in tl["scenes"]:
        if sc.get("type") not in ("people", "quote"): continue
        slots = sc.get("slots") or []
        for p in (sc.get("data") or {}).get("persons") or []:
            i = p.get("portrait")
            if not isinstance(i, int) or i >= len(slots): continue
            sl = slots[i]
            if not (sl.get("src") or sl.get("image")) or sl.get("portrait_ok"): continue
            jobs.append((sc, p, sl))
    seen = {id(j[2]) for j in jobs}
    for sc in tl["scenes"]:   # 26.09: снимок с именем человека в сцене хроники — тоже портрет, тоже проверяем
        if sc.get("type") in ("people", "quote"): continue
        for sl in sc.get("slots") or []:
            src = str(sl.get("image") or sl.get("src") or "")
            if sl.get("person") and src.startswith("archive/") and not sl.get("portrait_ok") and id(sl) not in seen:
                jobs.append((sc, {"name": sl["person"], "role": "", "_broll": True}, sl))
    if not jobs: return []
    bad = []
    cast = {}
    for x in tl.get("scenes", []):
        for q_ in (x.get("data") or {}).get("persons") or []:
            if q_.get("name"): cast.setdefault(q_["name"], q_.get("role") or "")
    def check(job):
        sc, p, sl = job
        png = frame_of(sl, d)
        if png is None: return (sc, p, sl, "кадр не читается")
        others = "; ".join(f"{n} ({r})" if r else n for n, r in cast.items() if n != p.get("name")) or "—"
        py = re.search(r"(1[89]|20)\d{2}", " ".join(str(x or "") for x in (sl.get("year"), sl.get("caption"), (sl.get("archive") or {}).get("date"))))
        q = PORTRAIT_CHECK.format(name=p.get("name", "?"), role=p.get("role") or "—", era=p.get("years") or sc.get("era") or "—", others=others,
                                  years=p.get("years") or "—", photo_year=py.group(0) if py else "—")
        try:
            r = llm.ask_vision(q, [png], tag=f"portrait_{vid}", model=config.LLM_MODEL_VISION)
        except Exception as e:
            print(f"[portrait] {p.get('name')}: {str(e)[:70]}"); return ("ERR", p, sl, str(e)[:120])
        if r.get("face") is True and r.get("plausible") is True:
            sl["portrait_ok"] = True; return None
        return (sc, p, sl, str(r.get("why") or "")[:90])
    errs = []
    with ThreadPoolExecutor(config.PREFLIGHT_WORKERS) as ex:
        for res in ex.map(check, jobs):
            if not res: continue
            if res[0] == "ERR": errs.append(f"{res[1].get('name')}: {res[3]}"); continue
            sc, p, sl, why = res
            if p.get("_broll"):   # сцена хроники: чужое лицо → кадр эпохи без людей, подпись снимаем
                prompt = re.sub(r"(?i)\b(an?\s+|the\s+)?(man|woman|men|women|person|people|businessman|businesswoman|clerk|worker|executive|founder|portrait)\b[^,]*,?\s*", "", sl.get("prompt") or "")
                prompt = "empty room, objects only: " + (prompt.strip(" ,") or "objects and setting of the era, documentary photograph") + ", nobody in frame, no people, no faces, no readable text"   # 26.09: «man in suit … no people» дал крупное лицо
                for k in ("person", "archive", "credit", "year", "clip_seconds"): sl.pop(k, None)
                sl.update({"kind": "image", "caption": None, "source": "image", "src": None, "image": None})
                fal = {"usd": 0.0}
                model = (db.get(vid)["payload"].get("image_model") if vid else None) or config.IMAGE_MODEL   # как весь ролик, не schnell
                _replace(sl, d, model, fal, prompt, attempt="portrait", vid=vid)
                if not sl.get("image"): raise RuntimeError(f"не удалось заменить чужой снимок {sl.get('id')} в сцене хроники")
                sl["aspect"] = round(config.IMAGE_WIDTH / config.IMAGE_HEIGHT, 3); sl.pop("src_px", None)
                bad.append(f"{p.get('name')} ({sc['id']}): {why} — заменён генерацией")
                print(f"[portrait] {p.get('name')} в хронике {sc['id']}: {why} — заменён кадром без людей", flush=True)
                continue
            sl["src"] = sl["image"] = None; sl["portrait_ok"] = False
            bad.append(f"{p.get('name')} ({sc['id']}): {why}")
            print(f"[portrait] снят {p.get('name')} в {sc['id']}: {why}", flush=True)
    if errs:   # 26.09: непроверенный портрет не должен уйти в рендер — проверенные уже помечены, повтор проверит остальные
        config.write(d / "timeline.json", json.dumps(tl, ensure_ascii=False))   # снятые и проверенные — сохраняем
        raise RuntimeError(f"проверка портретов не завершена ({len(errs)} из {len(jobs)}): " + "; ".join(errs[:3]))
    return bad

WATERMARK_CHECK = ("Look at this image carefully, including corners and the center. Is there ANY watermark, stock-agency overlay, semi-transparent logo or text "
                   "of a photo bank, print shop or image host (Getty Images, Alamy, Shutterstock, Pixels, Fine Art America, Photobucket, eBay, WorthPoint, etc.), "
                   "a photographer's signature or site name laid over the picture, or a repeated diagonal pattern of text? "
                   "Text that is part of the photographed scene itself (shop signs, labels on bottles, newspaper headlines, old print captions) is NOT a watermark. "
                   "Also: is this a modern document/template/screenshot rather than a historical photo or object? "
                   'Return JSON: {"watermark": true/false, "what": "exact text of the watermark or empty", "modern_document": true/false}')

def verify_web_photos(d, shots: list[dict], vid: str = "", img_model: str | None = None, fal_cost: dict | None = None, dry: bool = False) -> list[str]:
    """Веб-фото (archive/ + credit «photo: домен») — по одному снимку основной моделью зрения: водяной знак магазина печати или фотобанка,
    подпись фотографа поверх кадра, современный шаблон документа (Coca-Cola 28.09: pixels.com, fineartamerica, stlouispatina, dochub — финальный QC
    ловил их выборочно и после рендера, два лишних перерендера). Помеченные заменяются генерацией, подпись и credit снимаются.
    Ответы копятся в watermark_check.json (ключ — имя файла + размер): повтор этапа не платит за уже проверенные файлы.
    dry — только отчёт: без замен и без записи в папку ролика."""
    jobs = []
    for x, sl in _pairs(shots):
        img = str(sl.get("image") or "").replace("\\", "/")
        if not (img.startswith("archive/") and str(sl.get("credit") or "").startswith("photo:")): continue
        f = d / img
        if f.exists(): jobs.append((x, sl, f, f"{f.name}|{f.stat().st_size}"))
    if not jobs: return []
    cp = d / "watermark_check.json"
    try: cache = json.loads(config.read(cp)).get("files") or {}
    except Exception: cache = {}
    def look(job):
        x, sl, f, key = job
        if key in cache: return job, cache[key], None
        try:
            from PIL import Image
            im = Image.open(f).convert("RGB"); im.thumbnail((1600, 1600)); b = io.BytesIO(); im.save(b, "JPEG", quality=88)
            r = llm.ask_vision(WATERMARK_CHECK, [b.getvalue()], tag=f"wm_{vid}", max_tokens=600, model=config.LLM_MODEL_VISION)
            return job, {"watermark": bool(r.get("watermark")), "what": str(r.get("what") or "")[:120], "modern_document": bool(r.get("modern_document"))}, None
        except Exception as e: return job, None, str(e)[:120]
    new = sum(1 for j in jobs if j[3] not in cache)
    with ThreadPoolExecutor(config.PREFLIGHT_WORKERS) as ex: results = list(ex.map(look, jobs))
    errs, flagged = [], []
    for (x, sl, f, key), r, err in results:
        if err: errs.append(f"{_sid(x, sl)}: {err}"); continue
        cache[key] = r
        if r.get("watermark") or r.get("modern_document"): flagged.append((x, sl, r))
    if not dry: config.write(cp, json.dumps({"files": cache}, ensure_ascii=False, indent=1))
    print(f"[watermark] веб-фото {len(jobs)}, новых проверок {new}, помечено {len(flagged)}, ошибок {len(errs)}", flush=True)
    out = []
    model = img_model or (db.get(vid)["payload"].get("image_model") if vid and not dry else None) or config.IMAGE_MODEL
    fal = fal_cost if fal_cost is not None else {"usd": 0.0}
    bad = {id(sl) for _, sl, _ in flagged}
    order = [(x, sl) for x, sl in _pairs(shots)]
    def _clean_neighbor(x, sl):
        """Ближайшее по порядку фото той же части: Commons (credit не «photo:») или веб-фото, чистое по кэшу; не видео, не помеченное, не портрет."""
        part = str(x.get("id") or "").split("_")[0]
        here = next((i for i, (_, s2) in enumerate(order) if s2 is sl), 0)
        best = None
        for i, (x2, s2) in enumerate(order):
            if s2 is sl or id(s2) in bad or str(x2.get("id") or "").split("_")[0] != part: continue
            img = str(s2.get("image") or "").replace("\\", "/")
            if not img.startswith("archive/") or s2.get("src") or s2.get("role") == "portrait" or x2.get("type") in ("people", "quote"): continue
            f2 = d / img
            if not f2.exists(): continue
            web = str(s2.get("credit") or "").startswith("photo:")
            ok = (not web) or (lambda r: r is not None and not r.get("watermark") and not r.get("modern_document"))(cache.get(f"{f2.name}|{f2.stat().st_size}"))
            if ok and (best is None or abs(i - here) < best[0]): best = (abs(i - here), s2)
        return best[1] if best else None
    def fix(item):
        x, sl, r = item
        why = (f"водяной знак «{r.get('what')}»" if r.get("watermark") else "современный документ/шаблон") + f" ({sl.get('credit')})"
        if dry: return f"{_sid(x, sl)}: {why} — {sl.get('image')}"
        prompt = (sl.get("prompt") or "").strip() or "objects of the era on a desk, documentary photograph, no readable text"
        try:
            from .assets import validate_image_prompt; validate_image_prompt(prompt)
        except ValueError:
            # замысел с документом/экраном генерировать нельзя — берём проверенное фото соседней сцены той же части (06.10)
            nb = _clean_neighbor(x, sl)
            if nb:
                for k in ("image", "src", "kind", "archive", "credit", "caption", "year", "aspect", "focus_xy", "clip_seconds"): sl[k] = nb.get(k)
                sl["source"] = "archive"; sl["reused_from"] = nb.get("id")
                if sl is not x and len(x.get("slots") or []) == 1:
                    for k in ("caption", "credit"): x[k] = sl.get(k)
                print(f"[watermark] {_sid(x, sl)}: {why} — замысел с документом, взято проверенное фото соседней сцены {nb.get('id')}", flush=True)
                return f"{_sid(x, sl)}: {why} — фото соседней сцены {nb.get('id')}"
        for k in ("kind", "archive", "credit", "year", "aspect"): sl.pop(k, None)   # kind снят — _replace идёт сразу в генерацию, а не за новым веб-кандидатом
        sl.update({"source": "image", "caption": None, "credit": None})
        _replace(sl, d, model, fal, prompt, attempt="wm", vid=vid)
        if str(sl.get("image") or "").replace("\\", "/").startswith("archive/") or not sl.get("image"):
            raise RuntimeError(f"не удалось заменить кадр с водяным знаком {_sid(x, sl)}")
        if sl is not x and len(x.get("slots") or []) == 1:
            for k in ("caption", "credit"): x[k] = None
        print(f"[watermark] {_sid(x, sl)}: {why} — заменён генерацией", flush=True)
        return f"{_sid(x, sl)}: {why} — заменён генерацией"
    with ThreadPoolExecutor(config.PREFLIGHT_WORKERS) as ex:
        futs = [ex.submit(fix, it) for it in flagged]
    for f_ in futs:
        try: out.append(f_.result())
        except Exception as e: errs.append(str(e)[:120])
    if errs:   # правовой риск (config.QC_HARD): непроверенное или незаменённое веб-фото не должно уйти в рендер; проверенные уже в кэше
        raise RuntimeError(f"проверка водяных знаков не завершена ({len(errs)} из {len(jobs)}): " + "; ".join(errs[:3]))
    return out

def _era_of(x: dict, script: str) -> str | None:
    """Год сцены по тексту у якоря (своё предложение, иначе последний названный до, иначе первый после) — для проверки анахронизмов."""
    return story._year_near(x.get("anchor", ""), script, None)

def _label(sc: dict, sl: dict, script: str = "") -> str:
    """Подпись плитки листа: «v2_4/s2 [portrait] ~1971: Clara Jobs | query»; [hands] — фраза про названного человека, людей в кадре быть не должно."""
    role = sl.get("role"); tag = f" [{role}]" if role in ("portrait", "activity") else (" [hands]" if sl.get("no_people") and sl.get("kind") != "archive" else "")
    sid = sl.get("id") if sl is not sc else sc.get("id")
    # поздний снимок того же человека (снимка эпохи в открытом доступе нет): эпоху у него не проверяем, иначе проверка выбрасывает
    # единственный настоящий портрет и колонка остаётся пустой (Маккензи Скотт, 18.09: «portrait для 1994, но изображение современное»)
    if (sl.get("archive") or {}).get("relaxed"): return f"{sid}{tag} (поздний снимок того же человека — эпоху не проверять): " + (sl.get("caption") or "")
    era = _era_of(sc, script) if script else None
    return f"{sid}{tag}{' ~' + era if era else ''}: " + ((sl.get("caption") + " | " if sl.get("caption") else "") + (sl.get("query") or sl.get("prompt") or ""))

SHEET_GUIDE = ("\nНомера на красной полосе и подписи под изображениями — служебные данные проверочного листа, СНАРУЖИ исходного кадра. "
               "Они не входят в ролик: не бракуй исходник за эти подписи, их буквы или язык. "
               "Оцени само изображение между полосами; все реальные надписи, лица, фигуры, документы и дефекты ВНУТРИ него проверяй строго. "
               "Готовые титры и композиция ролика отдельно проверяются на собранных кадрах перед рендером.")

def sheet(items: list[tuple[int, str, bytes]], cols=4) -> bytes:
    from PIL import Image, ImageDraw, ImageFont, ImageOps
    try: font = ImageFont.truetype("arial.ttf", 12)
    except OSError: font = ImageFont.truetype("DejaVuSans.ttf", 12)
    ims = []
    for n, label, png in items:
        source = ImageOps.contain(Image.open(io.BytesIO(png)).convert("RGB"), (480, 270))
        im = Image.new("RGB", (480, 310), (20, 20, 20))
        im.paste(source, ((480-source.width)//2, 20+(270-source.height)//2))
        draw = ImageDraw.Draw(im); draw.rectangle([0, 0, 479, 19], fill="red")
        draw.text((4, 3), f"{n}", fill="white", font=font)
        draw.text((4, 294), label[:78], fill="white", font=font); ims.append(im)
    rows = (len(ims) + cols - 1) // cols; pad = 6
    out = Image.new("RGB", (cols * 480 + (cols + 1) * pad, rows * 310 + (rows + 1) * pad), "white")
    for k, im in enumerate(ims): out.paste(im, (pad + (k % cols) * 486, pad + (k // cols) * 316))
    buf = io.BytesIO(); out.save(buf, "JPEG", quality=80); return buf.getvalue()

RECONCEIVE = """Ты — режиссёр документального видео об истории компании. Ниже кадры, которые забракованы (с причиной), и фраза закадрового текста, на которой кадр стоит.
Для каждого придумай НОВЫЙ визуальный замысел и промпт для генерации картинки (15–35 слов, по-английски):
- никаких надписей, экранов с текстом, вывесок, логотипов, документов, монет, диаграмм, названий (генератор не умеет буквы) — вместо этого предметы, места, машины, руки, свет, погода, архивная фактура;
- люди нужны, когда фраза про человека: в одежде и обстановке эпохи, в действии, средний или общий план, лицо в профиль или не в камеру; запрещены крупные лица, взгляд в камеру, рукопожатия, совещания, вечеринки и портретное сходство с реальными людьми;
- кадры с пометкой [activity] и [hands] — ТОЛЬКО предметы и руки, без людей, фигур, силуэтов и людей со спины ([hands] — фраза про реального человека: сгенерированный «двойник» под его именем недопустим);
- эпоха строго та, что указана («эпоха: ~1971»): предметы, одежда, техника и интерьер того десятилетия; никаких планшетов, смартфонов, ноутбуков, плоских экранов и современной одежды — назови десятилетие в промпте явно;
- названия устройств не понимай буквально: «blue box» — самодельный тоновый генератор с кнопками и проводами, «adding machine» — механический арифмометр с бумажной лентой; описывай предмет по устройству;
- если указан «соседний кадр», не повторяй его мотив (руки над платой два кадра подряд — брак): возьми другой предмет или место из фразы;
- здания описывай по типу конкретно (public high school: приземистый корпус, флагшток, пустая парковка; garage: одноэтажный дом с гаражной дверью), а не «дворик с балконами»;
- замысел должен передавать смысл фразы метафорой или деталью (кризис — пустой цех и капающий кран; сделка — две чашки кофе на столе переговоров; рост — конвейер в движении);
- кинематографично, конкретно, одна сцена, один фокус (на чём остановится камера).
Верни JSON: {"shots":[{"id":"<id>","prompt":"...","motion":"slow push in|push in hard|zoom to detail|slow pull out|pan left|pan right|static"}]}"""

def _context(x: dict, script: str, span: int = 40) -> str:
    """Фраза озвучки вокруг якоря кадра."""
    words = script.split(); a = [w.lower().strip(".,!?;:\"'") for w in (x.get("anchor") or "").split()][:4]
    low = [w.lower().strip(".,!?;:\"'") for w in words]
    for i in range(len(low) - len(a) + 1):
        if a and low[i:i + len(a)] == a: return " ".join(words[max(0, i - 10):i + span])
    return x.get("anchor") or ""

RECONCEIVE_CARTOON = ("\n\nВАЖНО: это РИСОВАННЫЙ ролик (тушь и акварель). Здесь правила выше смягчены: людей можно — обычные как "
                      "«simple round-headed figures», названные — «caricature of <Имя>»; короткая надпись по-испански в кавычках (до 4 слов) допустима, "
                      "но лучше без неё, если брак был из-за букв.")

def _reconceive(bad: list[tuple[dict, dict, str]], script: str, vid: str, p: int, neighbours: dict | None = None) -> dict:
    """Один вызов Qwen на все плохие слоты прохода: новый визуальный замысел без букв (и без людей для activity/[hands]);
    neighbours — id сцены → замысел соседнего кадра, чтобы новый не повторял его мотив."""
    def who(x: dict, sl: dict) -> str:
        # activity — занятие конкретной персоны: без этого модель берёт предметы соседа по фразе («machinist and accountant» → станок у бухгалтера)
        if sl.get("role") != "activity": return ""
        p = next((p for p in ((x.get("data") or {}).get("persons") or []) if p.get("name") == sl.get("person")), {})
        return f"\nчьё занятие: {sl.get('person') or '?'} — {p.get('role') or 'занятие из старого замысла'}; предметы ИМЕННО этого занятия" if sl.get("person") else ""
    def tag(sl: dict) -> str: return " [activity]" if sl.get("role") == "activity" else (" [hands]" if sl.get("no_people") else "")
    def nb(x: dict) -> str: return f"\nсоседний кадр (не повторять мотив): {neighbours[x['id']]}" if neighbours and neighbours.get(x["id"]) else ""
    def plan(batch):
        listing = "\n\n".join(f"id: {_sid(x, sl)}" + tag(sl) + f"\nпричина брака: {why}\nстарый замысел: {sl.get('prompt') or sl.get('query')}"
                              + who(x, sl) + nb(x) + f"\nэпоха: ~{_era_of(x, script) or 'как в фразе'}\nфраза: {_context(x, script)}" for x, sl, why in batch)
        res = llm.ask_json((RECONCEIVE + RECONCEIVE_CARTOON if A.CARTOON["on"] else RECONCEIVE) + "\n\n" + listing, heavy=True, max_tokens=6000, effort="low",
                           tag=f"reconceive{p}_{vid}", model=config.LLM_MODEL_SHOTS or None)
        expected = {_sid(x, sl) for x, sl, _ in batch}
        out, blocked = {}, set()
        for row in res.get("shots", []):
            sid = row.get("id")
            if sid not in expected or sid in out or not isinstance(row.get("prompt"), str) or not row["prompt"].strip():
                raise RuntimeError("reconceive: некорректный или повторный замысел")
            try:
                if not A.CARTOON["on"]: A.validate_image_prompt(row['prompt'])
            except ValueError:   # 06.10: замысел с документом не покупаем, но и этап не роняем — сцена без замены в этом проходе
                blocked.add(sid); print(f"[preflight] {sid}: новый замысел с документом — без замены в этом проходе", flush=True); continue
            out[sid] = (row["prompt"], row.get("motion"))
        if set(out) | blocked != expected: raise RuntimeError("reconceive: замыслы получены не для всех кадров")
        return {**out, **{b: None for b in blocked}}
    # A giant repair list exhausted reasoning tokens without returning JSON.
    # Small complete plans avoid blind fallback to the original failed prompt;
    # every purchased result still passes the unchanged visual checker.
    batches = [bad[k:k + 12] for k in range(0, len(bad), 12)]
    out = {}
    with ThreadPoolExecutor(min(config.PREFLIGHT_WORKERS, 3)) as ex:
        for result in ex.map(plan, batches): out.update(result)
    return out

def _sid(x: dict, sl: dict) -> str: return sl.get("id") if sl is not x else x["id"]


def _record_reconceived_intent(slot: dict, narration: str):
    """Journal a newly generated illustration; keep source/person/narration checks binding."""
    if slot.get('kind') != 'image' or not slot.get('image') or slot.get('src'): return
    prior=copy.deepcopy(slot.get('visual_intent') or {})
    prompt=slot.get('prompt') or ''
    if prior.get('prompt')==prompt and prior.get('revision'): return
    reason=('Editorial replacement illustration, not a photograph of the named historical event or an authentic document. '
            'The unchanged narration, person, role, hands/no-people constraints and source-integrity rules still apply.')
    slot.setdefault('visual_intent_history',[]).append({'prior':prior,'reason':reason})
    slot['visual_intent']={'revision':reason,'prompt':prompt,'query':None,'caption':slot.get('caption'),
                           'person':slot.get('person') or prior.get('person'),'role':slot.get('role') or prior.get('role'),
                           'narration':narration}

def rejection_context_key(x: dict, sl: dict, script: str) -> str:
    """A rejection applies to the media under the requirements actually reviewed."""
    import hashlib
    evidence = visual_integrity.context(1, x, sl, _context(x, script, span=90))
    return hashlib.sha256((PROMPT + PROMPT_ARCHIVE + OPEN_STRICT + visual_integrity.RULES
                           + _label(x, sl, script) + evidence + '|intent-comparison-excludes-negation-v1'
                           + '|review-model:' + config.LLM_MODEL_VISION + '|external-metadata-sheet-v2' + SHEET_GUIDE).encode("utf-8")).hexdigest()

def _pairs(shots: list[dict]) -> list[tuple[dict, dict]]:
    """(сцена, слот) по всем сценам; старый плоский кадр — сам себе слот."""
    out = []
    for x in shots:
        # Native maps and text-only quotes need no optional inset or portrait.
        # Their rendered geometry/text still goes through stillcheck and QC.
        if x.get("type") in ("map", "quote", "chart", "stat", "compare") and x.get("slots") == [] and not (x.get("image") or x.get("src")):
            continue
        if isinstance(x.get("slots"), list) and x["slots"] and "source" not in x: out += [(x, sl) for sl in x["slots"]]
        else: out.append((x, x))
    return out

MOTIFS = {"пайка/плата/верстак": r"solder|breadboard|circuit board|workbench|resistor|transistor", "радио": r"\bradio|transmitter|antenna|vacuum tube",
          "наличные": r"\bcash|banknote|dollar bill|money", "гараж": r"\bgarage", "школа": r"\bschool|classroom", "стол с бумагами": r"\bledger|typewriter|adding machine",
          "аэросъёмка": r"\baerial|orchard", "телефон": r"\btelephone|\bphone\b|rotary", "коробка с проводами": r"\bbox\b.*\bwire|wire.*\bbox\b"}

def motif_of(prompt: str | None) -> str | None:
    """Мотив сгенерированного кадра по ключевым словам замысла — для проверки «соседние сцены не повторяют один мотив»."""
    p = (prompt or "").lower()
    return next((m for m, rx in MOTIFS.items() if re.search(rx, p)), None)

def _intent_words(prompt: str) -> set[str]:
    # Shared safety clauses describe exclusions, not the picture's subject.
    clauses = [part for part in re.split(r'[,;]', prompt or '')
               if not re.match(r'\s*(?:no\b|without\b|avoid\b|excluding\b)', part, re.I)]
    return set(re.findall(r'[a-z]{4,}', ' '.join(clauses).lower()))


def _initial_bad(pairs: list[tuple[dict, dict]], d) -> dict:
    """Брак без модели: клип короче сцены (зацикливание), одинаковые клипы, похожие замыслы (не внутри одной сцены), похожие картинки (aHash),
    тот же мотив у двух соседних сгенерированных broll (руки над платой дважды подряд)."""
    import hashlib, json as _json
    from PIL import Image
    bad = {}
    try: dur = {sc["id"]: sc["end"] - sc["start"] for sc in _json.loads(config.read(d / "timeline.json"))["scenes"]}
    except Exception: dur = {}
    seen_hash, seen_words, seen_ahash = {}, [], []
    prev_scene, prev_motif = None, None
    for i, (x, sl) in enumerate(pairs, 1):
        if x is not prev_scene:   # первый слот новой сцены: мотив соседнего broll
            m = motif_of(sl.get("prompt")) if x.get("type") == "broll" and sl.get("kind") == "image" else None
            if m and m == prev_motif: bad[i] = f"тот же мотив ({m}), что и предыдущий кадр"
            prev_scene, prev_motif = x, (m if x.get("type") == "broll" else None)
            if i in bad: continue
        if sl.get("src") and sl.get("clip_seconds") and sl.get("kind") != "archive" and dur.get(x["id"], 0) > sl["clip_seconds"] + 0.5: bad[i] = "клип короче сцены — зацикливание"; continue
        if sl.get("src") and (d / sl["src"]).exists():
            h = hashlib.md5((d / sl["src"]).read_bytes()[:200000]).hexdigest()
            if h in seen_hash: bad[i] = f"тот же клип, что и кадр {seen_hash[h]}"; continue
            seen_hash[h] = i
        if sl.get("role") == "portrait": continue   # один и тот же человек в разных сценах — не повтор (16.09 preflight заменил проверенные портреты)
        w = _intent_words(sl.get("prompt") or sl.get("query") or "")
        if w and sl.get("role") != "activity" and any(sid != x["id"] and len(w & p) / len(w | p) >= 0.6 for sid, p in seen_words): bad[i] = "повтор замысла"; continue
        seen_words.append((x["id"], w))
        if sl.get("image") and (d / sl["image"]).exists():
            im = Image.open(d / sl["image"]).convert("L").resize((8, 8)); px = list(im.getdata()); avg = sum(px) / 64
            ah = "".join("1" if p > avg else "0" for p in px)
            if any(sum(a != b for a, b in zip(ah, o)) <= 5 for o in seen_ahash): bad[i] = "почти такая же картинка уже была"; continue
            seen_ahash.append(ah)
    return bad

def run(vid: str, passes: int | None = None):
    v = db.get(vid); d = db.video_dir(vid); s = v["payload"]["script"]; shots = s["shots"]
    SA._cartoon["on"] = A.CARTOON["on"] = (v["payload"].get("topic") or {}).get("style") == "cartoon"   # 12.10: замены — тоже мультфильм
    spent = float(v["payload"].get("cost_usd", 0))
    img_model = v["payload"].get("image_model") or config.IMAGE_MODEL_CHEAP
    try:
        fal = check(d, shots, s["script"], vid, img_model, config.PREFLIGHT_PASSES if passes is None else passes)
    except Exception:
        # Paid replacements and their paths survive a failed verification pass.
        db.update(vid, payload={"script": {**s, "shots": shots}})
        raise
    total = round(spent + fal + llm.take_cost(), 4)
    db.update(vid, payload={"script": {**s, "shots": shots}, "cost_usd": total})
    print(f"[preflight] готово, расходы на видео ${total:.2f}")

RISKY_WORDS = ("text", "sign", "headline", "newspaper", "screen", "chart", "logo", "letter", "document", "poster", "label", "billboard",
               "надпис", "газет", "экран", "график", "логотип", "документ")

def _risky(pairs) -> set:
    """Слоты, где брак виден зрителю: лица и портреты, архив, кадры с текстом, цифрами и логотипами."""
    out = set()
    for x, sl in pairs:
        pr = str(sl.get("prompt") or sl.get("query") or "").lower()
        if (sl.get("kind") == "archive" or sl.get("role") in ("portrait", "person") or x.get("type") in ("people", "quote", "split", "map")
                or any(w in pr for w in RISKY_WORDS)):
            out.add(_sid(x, sl))
    return out

OPEN_STRICT = ("\n\nВАЖНО: это кадры ПЕРВЫХ ДВУХ МИНУТ ролика — здесь уходит половина зрителей, планка выше обычной. "
               "Бракуй и то, что обычно пропустил бы: типовой сток (руки над бумагами, пустой офис), мутный или тёмный кадр, "
               "кадр, который не показывает ИМЕННО то, о чём фраза, скучную композицию без главного объекта. Кадр должен цеплять с первого взгляда.")

def _opening_ids(shots: list[dict], script: str) -> set:
    """Сцены первых ~OPEN_WORDS слов сценария (первые две минуты)."""
    try:
        from .story import _positions
        pos = _positions(shots, script)
        return {x.get("id") for x, p_ in zip(shots, pos) if isinstance(x, dict) and p_ is not None and p_ < config.OPEN_WORDS}
    except Exception: return {x.get("id") for x in shots[:15] if isinstance(x, dict)}

def _source_pass_key(d, x, sl, png, script, prompt_text, model):
    import hashlib
    payload=['source-pass-v1',visual_integrity.media_key(d,sl),hashlib.sha256(png).hexdigest(),
             rejection_context_key(x,sl,script),prompt_text,model or config.LLM_MODEL_VISION]
    return hashlib.sha256(json.dumps(payload,ensure_ascii=False).encode('utf-8')).hexdigest()


def check(d, shots: list[dict], script: str, vid: str, img_model: str, passes: int = 4) -> float:
    """Проходы проверки и замены по слотам всех сцен; в конце — деградация сцен без обязательных слотов и обновление slots в timeline.json.
    Возвращает расходы fal."""
    fal_cost = {"usd": 0.0}
    if passes < 1: raise ValueError("preflight требует хотя бы один проход")
    verify_web_photos(d, shots, vid, img_model, fal_cost)   # 28.09: водяные знаки и шаблоны документов в веб-фото — до проходов, замены проверятся вместе со всеми
    recheck: set[str] | None = None   # со 2-го прохода модель смотрит только заменённые слоты (7 листов × 4 прохода × Sonnet = половина стоимости ролика)
    rejected_path = d / "preflight_rejections.json"
    rejected = json.loads(config.read(rejected_path)) if rejected_path.exists() else {}
    passed_path=d/'preflight_source_passes.json'
    try: source_passes=json.loads(config.read(passed_path)) if passed_path.exists() else {}
    except (ValueError,OSError):source_passes={}
    if not isinstance(source_passes,dict):source_passes={}
    for p in range(1, passes + 1):
        pairs = _pairs(shots)
        frames, bad = [], _initial_bad(pairs, d)
        for i, (x, sl) in enumerate(pairs, 1):
            if i in bad: continue
            if recheck is not None and _sid(x, sl) not in recheck: continue
            if not (sl.get("src") or sl.get("image")):
                if sl.get("role") == "portrait": continue   # пустой портрет — штатный случай (activity-only), не брак
                bad[i] = "слот без медиа"; continue
            fingerprint = visual_integrity.media_key(d, sl)
            if (rejected.get(_sid(x, sl), {}).get("key") == fingerprint
                    and rejected[_sid(x, sl)].get("context_key") == rejection_context_key(x, sl, script)):
                bad[i] = rejected[_sid(x, sl)]["why"]; continue
            png = frame_of(sl, d)
            if png is None or is_blank(png, sl.get("kind") == "archive"): bad[i] = "пустой или битый кадр"; continue
            frames.append((i, x, sl, png))
        opening = _opening_ids(shots, script)   # 27.09: первые ~2 минуты — основная модель и повышенная планка
        op = lambda f: f[1].get("id") in opening
        PR = PROMPT_CARTOON if A.CARTOON["on"] else PROMPT   # 13.10: испанский мультфильм — своя планка
        groups = [(PR + OPEN_STRICT, [f for f in frames if op(f) and f[2].get("kind") != "archive"], True),
                  (PROMPT_ARCHIVE + OPEN_STRICT, [f for f in frames if op(f) and f[2].get("kind") == "archive"], True),
                  (PR, [f for f in frames if not op(f) and f[2].get("kind") != "archive"], False),
                  (PROMPT_ARCHIVE, [f for f in frames if not op(f) and f[2].get("kind") == "archive"], False)]
        for prompt_text, batch, strict in [(pt, fr[k:k + 6], st) for pt, fr, st in groups for k in range(0, len(fr), 6)]:
            try:
                # первый проход — дешёвой моделью (Sonnet на 287 слотах стоил $7 за ролик), дальше Sonnet по помеченному; вступление — всегда основной
                vm = None if strict or any(sl.get("kind") == "archive" for _, _, sl, _ in batch) else (config.LLM_MODEL_VISION_CHEAP if (config.PREFLIGHT_CHEAP_FIRST and p == 1) else None)
                keys={n:_source_pass_key(d,x,sl,png,script,prompt_text,vm) for n,x,sl,png in batch}
                todo=[]
                for item in batch:
                    previous=source_passes.get(keys[item[0]])
                    if not (isinstance(previous,dict) and previous.get('ok') is True and isinstance(previous.get('why'),str) and previous['why'].strip()):
                        todo.append(item)
                if len(todo)!=len(batch):print(f'[preflight-cache] unchanged sources reused: {len(batch)-len(todo)}',flush=True)
                batch=todo
                if not batch:continue
                evidence = "\n".join(visual_integrity.context(n, x, sl, _context(x, script, span=90)) for n, x, sl, _ in batch)
                # 07.10: как при Greyhound/Pan Am — без свода целостности; 19.10: пилот сверяет кадр с текстом всегда
                rules = (visual_integrity.RULES + "\n" + evidence) if (config.STRICT_GATES or config.is_pilot(vid)) else ""
                res = llm.ask_vision(prompt_text + SHEET_GUIDE + rules, [sheet([(n, _label(x, sl, script), png) for n, x, sl, png in batch], cols=2)],
                                     tag=f"preflight{p}_{vid}", model=vm)
                nums = {b[0] for b in batch}
                for n, verdict in visual_integrity.verdicts(res, nums).items():
                    if not verdict["ok"]:
                        bad[n] = verdict["why"];source_passes.pop(keys[n],None)
                    else:source_passes[keys[n]]={'ok':True,'why':verdict['why']}
                config.write(passed_path,json.dumps(source_passes,ensure_ascii=False,indent=2))
            except Exception as e:
                if config.STRICT_GATES: raise RuntimeError("preflight: партия не прошла проверку") from e
                print(f"[preflight] партия: {e}", flush=True)
        print(f"[preflight] проход {p}: брак {len(bad)} из {len(pairs)} слотов" + (": " + ", ".join(f"{_sid(*pairs[n-1])} ({w[:30]})" for n, w in sorted(bad.items())[:12]) if bad else ""))
        for n, why in bad.items():
            x, sl = pairs[n - 1]
            if sl.get("src") or sl.get("image"):
                rejected[_sid(x, sl)] = {"key": visual_integrity.media_key(d, sl),
                                       "context_key": rejection_context_key(x, sl, script), "why": why}
        config.write(rejected_path, json.dumps(rejected, ensure_ascii=False, indent=2))
        if not bad: break
        if p == passes:
            config.write(d / "preflight_failed.json", json.dumps({"bad": bad}, ensure_ascii=False, indent=2))
            if config.STRICT_GATES: raise RuntimeError(f"preflight: после {passes} проходов осталось {len(bad)} проблемных слотов")
            print(f"[preflight] лимит проходов, остаток брака {len(bad)} остаётся — в отчёт QC (STRICT_GATES=0)", flush=True); break
        # замысел соседних кадров — чтобы переосмысленный не повторил мотив (руки над платой дважды подряд)
        order = [x for x in shots if isinstance(x, dict)]
        neighbours = {}
        for k, x in enumerate(order):
            near = [order[j] for j in (k - 1, k + 1) if 0 <= j < len(order) and order[j].get("type") == "broll"]
            prompts = [str(((y.get("slots") or [y])[0]).get("prompt") or "")[:120] for y in near]
            if prompts: neighbours[x["id"]] = " | ".join(pp for pp in prompts if pp)
        # со 2-го прохода смотрим не только замены, но и рискованные слоты (разбор 20.09): лица, архив, кадры с текстом и цифрами —
        # именно там брак заметен зрителю, а остальное декоративно и лишнего прохода не стоит
        fix = sorted(bad)
        if len(fix) > config.PREFLIGHT_MAX_FIX:
            risky = _risky(pairs)
            fix.sort(key=lambda n: (_sid(*pairs[n - 1]) not in risky, n))
            fix = sorted(fix[:config.PREFLIGHT_MAX_FIX])
            print(f"[preflight] брака {len(bad)}, переснимаю {len(fix)} (потолок {config.PREFLIGHT_MAX_FIX}); "
                  f"остальные {len(bad)-len(fix)} остаются как есть", flush=True)
        new_prompts = _reconceive([(*pairs[n - 1], bad[n]) for n in fix], script, vid, p, neighbours)
        recheck = {_sid(*pairs[n - 1]) for n in bad} | (_risky(pairs) if p == 1 else set())
        # замены идут параллельно: это 96% времени этапа, и каждая замена независима — свой слот, свой файл, своя сеть.
        # Разбор 20.09: на ролике Google это 94 слота × ~35 с подряд; в 6 потоков тот же код, те же модели, те же промпты.
        def _one(n: int):
            x, sl = pairs[n - 1]
            if _sid(x, sl) in new_prompts and new_prompts[_sid(x, sl)] is None: return   # замысел заблокирован — не покупаем
            pm = new_prompts.get(_sid(x, sl))
            before_media=(sl.get('image'),sl.get('src'),sl.get('prompt'))
            prompt = (pm[0] if pm else None) or sanitize_prompt(sl.get("prompt") or sl.get("query") or "cinematic detail shot")
            era = story.era_clause(_era_of(x, script), prompt)   # десятилетие и запрет современных вещей — и у переосмысленного промпта
            if era and "no modern devices" not in prompt: prompt = prompt.rstrip(". ") + ", " + era
            if pm and pm[1] and (sl is x or (x.get("type") == "broll" and (x.get("slots") or [None])[0] is sl)):
                x["motion"] = "slow push in" if pm[1] == "static" else pm[1]; x["motion_reconceived"] = True
            _replace(sl, d, img_model, fal_cost, prompt, attempt=p, ctx=_context(x, script), vid=vid)
            png = frame_of(sl, d) if (sl.get("src") or sl.get("image")) else None   # немедленная проверка и один повтор
            if (sl.get("src") or sl.get("image")) and (png is None or is_blank(png, sl.get("kind") == "archive")):
                print(f"[preflight] {_sid(x, sl)}: замена пустая — ещё раз", flush=True)
                _replace(sl, d, img_model, fal_cost, prompt, attempt=f"{p}b", ctx=_context(x, script), vid=vid)
            if pm and before_media!=(sl.get('image'),sl.get('src'),sl.get('prompt')):
                _record_reconceived_intent(sl, _context(x, script))
        with ThreadPoolExecutor(config.PREFLIGHT_WORKERS) as ex:
            for f in [ex.submit(_one, n) for n in fix]:
                try: f.result()
                except Exception as e: print(f"[preflight] замена не удалась: {str(e)[:120]}", flush=True)
    sync_timeline(d, shots)
    return fal_cost["usd"]

def sync_timeline(d, shots: list[dict]):
    """Медиа из раскадровки (после замен) → timeline.json; тайминги не трогаем."""
    _degrade_scenes(shots)
    if (d / "timeline.json").exists():
        tl = json.loads(config.read(d / "timeline.json"))   # обновляем медиа в таймлайне, тайминги не трогаем
        by_id = {x["id"]: x for x in shots}
        for sc in tl["scenes"]:
            x = by_id.get(sc["id"])
            if not x: continue
            if isinstance(x.get("slots"), list) and x["slots"] and "source" not in x:
                sc["slots"], sc["type"], sc["data"] = x["slots"], x["type"], x.get("data") or {}
                if x.pop("motion_reconceived", None): sc["motion"] = x.get("motion")
                if x["type"] == "broll": SA._mirror(x); SA._mirror(sc)
            else:
                sc["src"], sc["image"], sc["clip_seconds"] = x.get("src"), x.get("image"), x.get("clip_seconds")
                for k in ("caption", "kind", "aspect", "credit", "archive", "visual_intent"): sc[k] = x.get(k)
                if isinstance(sc.get("slots"), list) and sc["slots"]:
                    for k in ("src", "image", "clip_seconds", "caption", "kind", "aspect", "credit", "archive", "visual_intent"): sc["slots"][0][k] = x.get(k)
        if tl.get("format") == "story": SA._transitions(tl["scenes"])   # архивное видео могло стать картинкой — cut → xfade
        SA.fill_missing_portraits(tl["scenes"]); SA.reindex_people(tl["scenes"])   # своё лицо из другой сцены, затем номера карточек
        config.write(d / "timeline.json", json.dumps(tl, ensure_ascii=False, indent=2))

def _degrade_scenes(shots: list[dict]):
    """После замен: people — персоны без портрета и иллюстрации выбрасываются, никого → broll; split без слота → broll."""
    for x in shots:
        if not (isinstance(x.get("slots"), list) and "source" not in x): continue
        slots = x["slots"]
        if x["type"] == "people":
            new_slots, kept = [], []
            for p in (x.get("data") or {}).get("persons") or []:
                por = slots[p["portrait"]] if isinstance(p.get("portrait"), int) and p["portrait"] < len(slots) and SA._has_media(slots[p["portrait"]]) else None
                act = slots[p["activity"]] if isinstance(p.get("activity"), int) and p["activity"] < len(slots) and SA._has_media(slots[p["activity"]]) else None
                if not por and not act: print(f"[preflight] {x['id']}: {p['name']} без портрета и иллюстрации — убрана"); continue
                p["portrait"] = p["activity"] = None
                if por: p["portrait"] = len(new_slots); new_slots.append(por)
                if act: p["activity"] = len(new_slots); new_slots.append(act)
                kept.append(p)
            if not kept:
                alive = [sl for sl in slots if SA._has_media(sl)]
                for sl in alive[:1]: sl["role"] = "main"
                print(f"[preflight] {x['id']} people→broll: никого не осталось"); x["type"] = "broll"; x["data"] = {}; x["slots"] = alive[:1]; SA._mirror(x); continue
            sides = {1: ["center"], 2: ["left", "right"], 3: ["left", "center", "right"]}[len(kept)]
            for p, sd in zip(kept, sides): p["side"] = sd
            x["data"]["persons"] = kept; x["data"]["layout"] = {1: "solo", 2: "duo", 3: "trio"}[len(kept)]; x["slots"] = new_slots
        elif x["type"] == "split" and not all(SA._has_media(sl) for sl in slots):
            alive = [sl for sl in slots if SA._has_media(sl)]
            for sl in alive[:1]: sl["role"] = "main"
            print(f"[preflight] {x['id']} split→broll: слот без медиа"); x["type"] = "broll"; x["data"] = {}; x["slots"] = alive[:1]; SA._mirror(x)
        elif x["type"] == "map":
            x["slots"] = [sl for sl in slots if SA._has_media(sl)]

def _replace(x: dict, d, img_model: str, fal_cost: dict, prompt: str, attempt, ctx: str = "", vid: str = ""):
    """Плохой слот: архив → другой архивный кандидат (исключая забракованный); портрет без замены остаётся пустым (колонка activity-only);
    activity → перегенерация без людей; иначе новая картинка по переосмысленному промпту. Клипы Hailuo пересобираются отдельно (clips_for)."""
    old = copy.deepcopy(x); role = x.get("role")
    if x.get("kind") == "archive":
        from . import archive
        try:
            if archive.resolve(x, d, ctx, vid, exclude=True, portrait=(role == "portrait")):
                if x.get("src"): SA._video_dims(x, d)
                return
        except Exception as e: print(f"[preflight] {x['id']}: архив повторно: {e}")
        x["caption"] = None; x.pop("kind", None); x.pop("aspect", None); x.pop("archive", None); x.pop("credit", None); x["clip_seconds"] = None
        if role == "portrait":   # сгенерированное лицо нельзя подписать именем
            x["src"] = None; x["image"] = None; x["kind"] = None; print(f"[preflight] {x['id']}: портрет не заменён — колонка без портрета"); return
        prompt += SA.NO_FACE
    if role == "activity": prompt = prompt.rstrip(". ,") + SA.NO_PEOPLE if "no people" not in prompt else prompt
    if x.get("no_people") and "no person" not in prompt: prompt = prompt.rstrip(". ,") + story.NO_FIGURE   # фраза про названного человека — без двойников
    try:
        x["prompt"] = prompt; x["query"] = None
        if x.get("source") == "stock": x["source"] = "image"
        x["src"] = None
        framing = '' if A._people_forbidden(prompt) else ', faces not looking at camera'
        x["image"] = A._image(prompt + ("" if A.CARTOON["on"] else ", no writing anywhere, no lettering" + framing), d, f"{x['id']}_r{attempt}", img_model)
        x["kind"] = "image"; x["aspect"] = round(config.IMAGE_WIDTH / config.IMAGE_HEIGHT, 3); x.pop("src_px", None)
        if "focus_xy" in x: x["focus_xy"] = A._saliency_focus(d / x["image"])
        fal_cost["usd"] += config.image_price(img_model, config.IMAGE_WIDTH, config.IMAGE_HEIGHT)
    except Exception as e:
        print(f"[preflight] {x['id']}: не удалось заменить: {e}")
        x.clear(); x.update(old)

def clips_for(vid: str):
    """Для кадров source=clip без клипа (клип забракован и заменён картинкой) — новый клип Hailuo из прошедшей проверку картинки."""
    v = db.get(vid); d = db.video_dir(vid); s = v["payload"]["script"]; shots = s["shots"]; fal_cost = {"usd": 0.0}
    todo = [x for x in shots if x.get("source") == "clip" and not (x.get("src") or "").startswith("clips") and x.get("image")][:config.CLIP_MAX_PER_VIDEO]
    for x in todo:
        try: SA._clip(x, d, fal_cost); print(f"[preflight] клип {x['id']} пересобран")
        except Exception as e: print(f"[preflight] клип {x['id']}: {e}")
    total = round(float(v["payload"].get("cost_usd", 0)) + fal_cost["usd"], 4)
    db.update(vid, payload={"script": {**s, "shots": shots}, "cost_usd": total})
    tl = json.loads(config.read(d / "timeline.json")); by_id = {x["id"]: x for x in shots}
    for sc in tl["scenes"]:
        x = by_id.get(sc["id"])
        if x: sc["src"], sc["image"], sc["clip_seconds"] = x.get("src"), x.get("image"), x.get("clip_seconds")
    config.write(d / "timeline.json", json.dumps(tl, ensure_ascii=False, indent=2))
    print(f"[preflight] клипов пересобрано {len(todo)}, расходы ${total:.2f}")
