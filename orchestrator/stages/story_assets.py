"""Ассеты story-формата: слоты сцен (архив Commons/YouTube / сток / картинка), иллюстрации занятий для people, точка фокуса,
паузы диктора на главах, музыка по частям, таймлайн по контракту docs/scene-grammar.md §6.3."""
import json, os, random, re, requests, shutil, threading
from concurrent.futures import ThreadPoolExecutor
from .. import db, config, llm
from . import assets as A
from . import archive
from . import pauses as P
from .story import NO_PEOPLE   # запрет людей в иллюстрациях занятий (people); story не импортирует story_assets — цикла нет

_lock = threading.Lock()
_used_stock: set = set()   # id клипов Pexels, уже взятых в этом видео — один клип не должен встречаться дважды
CHAPTER_SEC = config.CHAPTER_SEC   # карточка главы на экране; под ней меняется музыка
CAPTION_SEC = 5.0                  # подпись архивного кадра (кто, год) держится столько секунд, потом уходит
ROLE_BY_TYPE = {"broll": ["main"], "people": ["portrait"], "quote": ["portrait"], "map": ["inset"], "split": ["left", "right"], "montage": ["item"], "object": ["hero"]}
NO_FACE = ", not a portrait of any real person, face turned away"

_probe = {"spent": 0.0, "miss": 0, "hits": 0, "closed": False}
_cartoon = {"on": False}   # 12.10: ролик испанского канала в стиле мультфильма — без архива, стока и хроники

def _probe_open() -> bool:
    """Пробы «хроника вместо генерации» идут, пока есть бюджет времени и хроника вообще находится (Netflix 21.09: 1 156 отклонений, 3,5 часа)."""
    return not _probe["closed"]

def _probe_note(hit: bool, sec: float):
    with _lock:
        _probe["spent"] += sec
        if hit: _probe["hits"] += 1; _probe["miss"] = 0
        else: _probe["miss"] += 1
        if not _probe["closed"] and (_probe["spent"] > config.ARCHIVE_FIRST_BUDGET_SEC or _probe["miss"] >= config.ARCHIVE_FIRST_MISS_STOP):
            _probe["closed"] = True
            print(f"[slot] пробы хроники закрыты: найдено {_probe['hits']}, промахов подряд {_probe['miss']}, потрачено {_probe['spent']:.0f} с — дальше генерация", flush=True)

def run(vid: str):
    from .. import gates
    if not gates.require_script(vid): return
    from .story import _normalize_shot
    _probe.update({"spent": 0.0, "miss": 0, "hits": 0, "closed": False})
    v = db.get(vid); d = db.video_dir(vid); s = v["payload"]["script"]
    _cartoon["on"] = A.CARTOON["on"] = (v["payload"].get("topic") or {}).get("style") == "cartoon"
    shots = [x if isinstance(x.get("slots"), list) and "source" not in x else _normalize_shot(x) for x in s["shots"]]
    overlays = s.get("overlays", [])
    from .. import money
    spent = money.spent(vid); fal_cost = {"usd": 0.0}
    # 12.10: личный потолок ролика по решению владельца (Sears — сгорело ~$22 на снятой модели, «доделать»); иначе общий BUDGET_USD
    budget = float(v["payload"].get("budget_usd") or config.BUDGET_USD)
    n_img = sum(1 for x in shots for sl in x["slots"] if sl["source"] == "image") + sum(len((x.get("data") or {}).get("persons") or []) for x in shots if x["type"] == "people")
    img_model = config.IMAGE_MODEL_CHEAP   # story: много кадров → schnell по умолчанию; dev — если бюджет позволяет
    est_dev = n_img * config.image_price(config.IMAGE_MODEL, config.IMAGE_WIDTH, config.IMAGE_HEIGHT) + 3 * 0.04
    if spent + est_dev <= budget: img_model = config.IMAGE_MODEL
    estimate = n_img * config.image_price(img_model, config.IMAGE_WIDTH, config.IMAGE_HEIGHT) + 3 * 0.04
    if spent + estimate > budget:
        raise RuntimeError(f"Бюджет превышен до закупки кадров: ${spent:.2f} + ~${estimate:.2f} > ${budget:.2f}")
    types = {}
    for x in shots: types[x["type"]] = types.get(x["type"], 0) + 1
    print(f"[story] сцен {len(shots)}: " + ", ".join(f"{t} {n}" for t, n in types.items()) +
          f"; слотов archive {sum(1 for x in shots for sl in x['slots'] if sl['source'] == 'archive')}, картинок ~{n_img} на {img_model}")
    clean = A.clean_text(s["script"])
    cast = [c["name"] for c in (v["payload"].get("entities") or {}).get("cast") or [] if c.get("name")]
    archive.reset(); _used_stock.clear()
    archive.video_budget(None if config.ARCHIVE_VIDEO_MAX < 0 else config.ARCHIVE_VIDEO_MAX)   # 08.10 дешёвый режим: клипы — вступлению
    if _cartoon["on"]: archive.video_budget(0); img_model = config.IMAGE_MODEL   # мультфильм: всё рисует основная модель
    if config.ERA_FOOTAGE and not _cartoon["on"]:
        from . import era_footage
        era_footage.reset(); _era_budget["left"] = config.ERA_MAX_PER_VIDEO
    # озвучка — первой и синхронно: ElevenLabs закрыт по гео без VPN, и падать надо ДО того, как потрачены деньги на 90 архивных
    # слотов и картинки (15.09: озвучка упала в 403, а пул продолжал искать кадры, и всё пропало при исключении)
    import os as _os
    _old_voice = _os.environ.get("ELEVENLABS_VOICE_ID")
    if s.get("lang") == "es" and config.ES_VOICE_ID: _os.environ["ELEVENLABS_VOICE_ID"] = config.ES_VOICE_ID   # голос второго канала
    try: A._voice(clean, d, [A.clean_text(p) for p in s.get("parts") or []])
    finally:
        if _old_voice: _os.environ["ELEVENLABS_VOICE_ID"] = _old_voice
    pauses = P.ensure(vid, s.get("parts"))   # тишина на главах — сразу после озвучки, до таймлайна
    # первая минута по реальным секундам озвучки — ДО покупки кадров (разбор канала 21.09: обрыв удержания на 10–30 с).
    # Провал → переписывается только вступление, озвучка пересобирается из кэша (2–3 куска), проверка повторяется один раз.
    # Переписывать здесь НЕЛЬЗЯ: раскадровка уже привязана якорями к фразам вступления (ревью 21.09) — переписывание
    # идёт в script.py до раскадровки, а здесь по реальным секундам только отчёт (строка «Обещание» в QC).
    if config.OPENING_GATE and not _cartoon["on"]:   # 12.10: правила вступления — английского канала; испанский мультфильм идёт своим форматом
        try:
            from . import opening
            opening_result = opening.check(vid, d, v["payload"].get("brief") or {})
        except Exception as e:
            config.write(d / "opening_check.json", json.dumps({"ok": False, "error": str(e)[:160]}))
            raise RuntimeError("Проверка вступления по озвучке не завершена") from e
        if opening_result.get("ok") is not True:
            db.update(vid, payload={"opening_needs_review": True, "release_gate": None, "final_approval": None})
            raise RuntimeError("Вступление по озвучке не прошло: исправьте его до закупки кадров")
    with ThreadPoolExecutor(6) as ex:
        jobs = [ex.submit(_resolve_slots, x, d, img_model, fal_cost, _ctx(x, clean), vid, cast) for x in shots]
        thumbs = [ex.submit(A._thumb, c, d, "abc"[i], {"model": img_model}, fal_cost) for i, c in enumerate(s.get("thumbnail_concepts", [])[:3])]
        for f in jobs + thumbs: f.result()
    tracks = _music_tracks(s, d)
    tl = _timeline(d, shots, overlays, s["script"], v["title"], tracks, pauses=pauses, film=config.film_block())
    if config.FILL_LONG_SCENES:   # ни один кадр не висит дольше потолка (stages/fill.py): режем длинные сцены по предложениям и добиваем кадрами
        from . import fill
        s["shots"] = shots
        res = fill.run(vid, d, s, tl, json.loads(config.read(d / "words.json")), img_model=img_model, cast=cast)
        shots = s["shots"]; fal_cost["usd"] += res.get("fal", 0.0)
        if res.get("shots"): tl = _timeline(d, shots, overlays, s["script"], v["title"], tracks, pauses=pauses, film=config.film_block())
        # 29.09 (Greyhound: местные новости 15.8 с на 0:00): кусок добивки сам мог получить длинный ролик YouTube или растянуться
        # при сборке — второй проход только по чужим отрезкам длиннее footage.FOREIGN_MAX, до preflight и рендера
        from . import footage
        long_ids = {x["scene"] for x in footage.report(tl)["foreign_long"]}
        if long_ids:
            print(f"[fill] чужие отрезки длиннее {footage.FOREIGN_MAX:.0f} с после сборки: {sorted(long_ids)} — второй проход", flush=True)
            s["shots"] = shots
            res2 = fill.run(vid, d, s, tl, json.loads(config.read(d / "words.json")), img_model=img_model, cast=cast, ids=long_ids)
            shots = s["shots"]; fal_cost["usd"] += res2.get("fal", 0.0)
            if res2.get("shots"): tl = _timeline(d, shots, overlays, s["script"], v["title"], tracks, pauses=pauses, film=config.film_block())
            left = footage.report(tl)["foreign_long"]
            if left: print("[fill] после второго прохода остались длинные чужие отрезки: " + ", ".join(f"{x['scene']} {x['sec']} с" for x in left), flush=True)
    total = round(spent + fal_cost["usd"] + llm.take_cost(), 4)
    # статус — ПОСЛЕ preflight (рецензия 23.09): очередь по статусу "assets" идёт на рендер, и падение проверки кадров
    # означало бы рендер с непроверенными кадрами при следующем проходе. payload сохраняем сразу — preflight его читает.
    db.update(vid, payload={"script": {**s, "shots": shots}, "cost_usd": total, "image_model": img_model, "tts_chars": len(clean)})
    print(f"[story] расходы на видео: ${total:.2f} (fal ~${fal_cost['usd']:.2f}); архивных слотов {sum(1 for x in shots for sl in x['slots'] if sl.get('kind') == 'archive')}")
    from . import preflight; preflight.run(vid)   # брак и нерелевантность кадров — до часа рендера
    db.update(vid, "assets")   # только теперь этап считается пройденным

def _ctx(x: dict, script: str, span: int = 40) -> str:
    """Фраза озвучки вокруг якоря кадра — контекст для отбора архивных кадров."""
    words = script.split(); a = [w.lower().strip(".,!?;:\"'“”‘’") for w in (x.get("anchor") or "").split()][:4]
    low = [w.lower().strip(".,!?;:\"'“”‘’") for w in words]
    for i in range(len(low) - len(a) + 1):
        if a and low[i:i + len(a)] == a: return " ".join(words[max(0, i - 8):i + span])
    return x.get("anchor") or ""

# ---------- слоты ----------

def _has_media(sl: dict) -> bool: return bool(sl.get("src") or sl.get("image"))

_era_budget = {"left": 0}   # сколько слотов ещё можно отдать съёмке эпохи в этом ролике (каждый — отбор и проверка на vision)

PROMPT_NOISE = re.compile(r"\b(cinematic|photorealistic|photograph|photo|shot|close-?up|wide|angle|lighting|light|film grain|grain|"
                          r"shallow depth of field|bokeh|dramatic|no people|no faces|no text|no lettering|no logos|no readable words|"
                          r"hands only|objects only|no figures|no silhouettes|blank surfaces|no writing anywhere)\b", re.I)

def _archive_query(prompt: str, alt: bool = False) -> str:
    """Поисковый запрос к хронике из промпта генерации: выкидываем операторские слова и запреты, оставляем предмет и эпоху."""
    q = PROMPT_NOISE.sub(" ", prompt or "")
    q = re.sub(r"[,;].*$", "", q) if not alt else q
    q = re.sub(r"\s{2,}", " ", q).strip(" ,.-")
    words = q.split()
    return " ".join(words[:9] if not alt else words[:14])

def _resolve_slot(sl: dict, d, img_model: str, fal_cost: dict, ctx: str = "", vid: str = "", portrait: bool = False, generate: bool = True) -> bool:
    """archive → Commons/YouTube; stock → Pexels; image → Flux. Любая ошибка или пустой поиск → откат к следующему по дешевизне
    (в конце — картинка по prompt). portrait — портрет для people: без генерации лица (generate=False → слот остаётся пустым)."""
    from .. import visual_integrity
    visual_integrity.remember_intent(sl, ctx)
    sl["src"] = None; sl["image"] = None
    try:
        if _cartoon["on"]: return _cartoon_slot(sl, d, img_model, fal_cost, portrait)
        # Сначала настоящая хроника, даже если раскадровка попросила картинку (владелец 21.09: «в сети много хроники Google,
        # а ты ставишь генерацию, которая стоит денег»). Архив бесплатен, он же — то, чем канал отличается от конвейера.
        # Пробуем только там, где есть по чему искать, и не трогаем портреты (у них свой путь) и иллюстрации занятий без людей.
        if (config.ARCHIVE_FIRST and sl["source"] == "image" and not portrait and not sl.get("no_people")
                and (sl.get("query") or sl.get("prompt")) and _probe_open()):
            q = sl.get("query") or _archive_query(sl.get("prompt") or "")
            if q:
                probe = {**sl, "source": "archive", "query": q, "query_alt": sl.get("query_alt") or _archive_query(sl.get("prompt") or "", alt=True)}
                import time as _t
                t0 = _t.time(); hit = archive.resolve(probe, d, ctx, vid, quick=True); _probe_note(hit, _t.time() - t0)
                if hit:
                    for k in ("src", "image", "kind", "aspect", "caption", "credit", "clip_seconds", "year", "archive", "focus_xy", "src_px", "at"):
                        sl[k] = probe.get(k)
                    print(f"[slot] {sl['id']}: вместо генерации — хроника по «{q[:48]}»", flush=True)
                    return True
        if sl["source"] == "archive":
            if archive.resolve(sl, d, ctx, vid, portrait=portrait): return True
            print(f"[slot] {sl['id']}: архив не найден по «{sl.get('query')}»" + (" — портрет не генерируем" if not generate else " — пробую съёмку эпохи"))
            if not generate: sl["caption"] = None; sl["kind"] = None; return False
        # обезличенная съёмка эпохи вместо генерации (владелец 17.09): плёнка общественного достояния до 1999, сток — с 2005
        if config.ERA_FOOTAGE and not portrait and _era_budget["left"] > 0:
            from . import era_footage
            try:
                if era_footage.find(sl, d, ctx, vid): _era_budget["left"] -= 1; return True
            except Exception as e: print(f"[era] {sl['id']}: {str(e)[:80]}")
        sl["caption"] = None; sl.pop("kind", None); sl.pop("aspect", None)
        if sl["source"] == "stock" and _stock(sl, d): sl["kind"] = "stock"; return True
        prompt = sl.get("prompt") or sl.get("query") or ""
        if not prompt: return False
        if sl["source"] == "archive": prompt += NO_FACE
        sl["image"] = A._image(prompt, d, sl["id"], img_model); sl["kind"] = "image"; sl["aspect"] = round(config.IMAGE_WIDTH / config.IMAGE_HEIGHT, 3)
        with _lock: fal_cost["usd"] += config.image_price(img_model, config.IMAGE_WIDTH, config.IMAGE_HEIGHT)
        return True
    except Exception as e:
        print(f"[slot] {sl['id']}: {e}"); return False

def _cartoon_slot(sl: dict, d, img_model: str, fal_cost: dict, portrait: bool) -> bool:
    """Мультфильм испанского канала: каждый слот рисуется; портрет — шарж на названного человека (владелец 12.10: «шаржи можно, как у них»)."""
    sl["caption"] = None if not portrait else sl.get("caption"); sl.pop("kind", None); sl.pop("aspect", None)
    if portrait:
        who = sl.get("caption") or sl.get("query") or ""
        prompt = (f"caricature portrait of {who}, head and shoulders, recognizable face, " + (sl.get("prompt") or ""))
    else:
        prompt = sl.get("prompt") or sl.get("query") or ""
        for bad in (", not a portrait of any real person, face turned away", ", hands and objects only, no face, no person, no figure, no silhouette"):
            prompt = prompt.replace(bad, "")
    if not prompt: return False
    sl["source"] = "image"; sl.pop("no_people", None)
    sl["image"] = A._image(prompt, d, sl["id"], img_model, cartoon=True); sl["kind"] = "image"; sl["aspect"] = round(config.IMAGE_WIDTH / config.IMAGE_HEIGHT, 3)
    with _lock: fal_cost["usd"] += config.image_price(img_model, config.IMAGE_WIDTH, config.IMAGE_HEIGHT)
    return True

def _shot(x: dict, d, img_model: str, fal_cost: dict, ctx: str = "", vid: str = ""):
    """Старый плоский кадр (source на верхнем уровне) — как один слот."""
    if x.get("source") == "clip": x["source"] = "image"
    x.setdefault("id", "x"); _resolve_slot(x, d, img_model, fal_cost, ctx, vid)

def _activity_slot(x: dict, i: int, p: dict, d, fal_cost: dict) -> dict | None:
    """Иллюстрация занятия персоны: только предметы и руки, schnell."""
    sid = f"{x['id']}_a{i + 1}"; prompt = str(p.get("activity_prompt") or "")
    if not prompt: return None
    try:
        img = A._image(prompt, d, sid, config.ACTIVITY_MODEL)
        with _lock: fal_cost["usd"] += config.image_price(config.ACTIVITY_MODEL, config.IMAGE_WIDTH, config.IMAGE_HEIGHT)
        return {"id": sid, "role": "activity", "source": "image", "prompt": prompt, "caption": None, "src": None, "image": img, "kind": "image",
                "aspect": round(config.IMAGE_WIDTH / config.IMAGE_HEIGHT, 3), "person": p["name"]}
    except Exception as e:
        print(f"[slot] {sid}: {e}"); return None

def _people_assemble(x: dict, d, img_model: str, fal_cost: dict, ctx: str, vid: str):
    """Портреты уже разрешены; добавляем activity-слоты, пишем индексы в persons, выбрасываем персон без медиа; никого → broll."""
    persons = x["data"]["persons"]; portraits = x["slots"]; slots, kept = [], []
    for i, p in enumerate(persons):
        por = portraits[i] if i < len(portraits) else None
        act = _activity_slot(x, i, p, d, fal_cost)
        if not (por and _has_media(por)) and not act:
            print(f"[slot] {x['id']}: у {p['name']} ни портрета, ни иллюстрации — персона убрана"); continue
        p["portrait"] = None; p["activity"] = None
        if por and _has_media(por): p["portrait"] = len(slots); slots.append(por)
        if act: p["activity"] = len(slots); slots.append(act)
        kept.append(p)
    if not kept:
        x["downgrade"] = "people: ни у одной персоны нет медиа"; print(f"[slot] {x['id']} people→broll: {x['downgrade']}")
        sl = next((s for s in portraits if _has_media(s)), None) or (portraits[0] if portraits else {"id": f"{x['id']}_s1", "source": "image", "prompt": "empty workshop of the era"})
        if not _has_media(sl):
            sl["source"] = "image"; sl["prompt"] = (sl.get("prompt") or "objects of the era on a table") + NO_FACE; _resolve_slot(sl, d, img_model, fal_cost, ctx, vid)
        sl["role"] = "main"; x["type"] = "broll"; x["data"] = {}; x["slots"] = [sl]; return
    sides = {1: ["center"], 2: ["left", "right"], 3: ["left", "center", "right"]}[len(kept)]
    if sorted(str(p.get("side")) for p in kept) != sorted(sides):
        for p, sd in zip(kept, sides): p["side"] = sd
    x["data"]["persons"] = kept; x["data"]["layout"] = {1: "solo", 2: "duo", 3: "trio"}[len(kept)]; x["slots"] = slots

PORTRAIT_COPY = ("src", "image", "aspect", "focus_xy", "kind", "clip_seconds", "year", "credit", "caption", "archive", "src_px", "at")

def fill_missing_portraits(scenes: list[dict]) -> int:
    """Если лицо человека уже найдено в одной сцене — ставим его и там, где портрет не нашёлся.
    Google 20.09: у Брина был снимок в двух сценах из четырёх, в остальных карточка осталась без лица,
    хотя файл лежал в той же папке. Настоящее фото важнее разнообразия кадров."""
    pool: dict = {}
    for sc in scenes:
        for sl in (sc.get("slots") or []):
            who = str(sl.get("person") or "").strip()
            if sl.get("role") == "portrait" and who and _has_media(sl): pool.setdefault(who, []).append(sl)
    n = 0
    dedupe_portraits(scenes)   # прежде чем размножать найденное лицо по сценам — убедиться, что оно не стоит под двумя именами
    for sc in scenes:
        if sc.get("type") not in ("people", "quote"): continue
        for sl in (sc.get("slots") or []):
            who = str(sl.get("person") or "").strip()
            if sl.get("role") != "portrait" or not who or _has_media(sl) or sl.get("portrait_omitted") is True: continue
            src = next((s for s in pool.get(who, []) if s is not sl), None)
            if not src: continue
            for k in PORTRAIT_COPY: sl[k] = src.get(k)
            n += 1
            print(f"[people] {sc['id']}: {who} — портрет взят из другой сцены ({sl.get('src') or sl.get('image')})", flush=True)
    return n

def downgrade_faceless(scenes: list[dict]) -> int:
    """Сцена людей, где ни у одной персоны нет настоящего снимка, — обычный кадр с иллюстрацией занятия (26.09, First American:
    после снятых однофамильцев карточка Паркера показывала пустое поле с буквой «C»). Если хоть у одного лицо есть — карточка остаётся."""
    n = 0
    for sc in scenes:
        if sc.get("type") != "people": continue
        slots = sc.get("slots") or []; persons = (sc.get("data") or {}).get("persons") or []
        def media(i): return isinstance(i, int) and 0 <= i < len(slots) and _has_media(slots[i])
        if not persons or any(media(p.get("portrait")) for p in persons): continue
        act = next((slots[p["activity"]] for p in persons if media(p.get("activity"))), None)
        if not act: continue
        act = dict(act); act["role"] = "main"; act["caption"] = None
        sc["type"] = "broll"; sc["data"] = {}; sc["slots"] = [act]; sc["downgrade"] = "people: настоящих снимков не осталось"
        print(f"[people] {sc['id']}: снимков {', '.join(str(p.get('name')) for p in persons)} нет — сцена показывает занятие", flush=True)
        n += 1
    return n

def dedupe_portraits(scenes: list[dict], cast: list[str] | None = None) -> int:
    """Одно и то же фото (файл или адрес) под двумя разными именами — McDonald's 22.09: снимок Ричарда с бургером стоял и под
    «Maurice», и под «Richard». Остаётся у первого по касту, у остальных портрет снимается: без лица честнее, чем с чужим."""
    import os
    order = {n: i for i, n in enumerate(cast or [])}
    owner: dict = {}
    def keys(sl):
        ks = set()
        for k in ("src", "image"):
            if sl.get(k): ks.add(os.path.basename(str(sl[k])).split(".")[0].rsplit("_r", 1)[0])
        a = sl.get("archive") or {}
        for k in ("url", "key"):
            if a.get(k): ks.add(str(a[k]))
        return ks
    slots = [(sc, sl) for sc in scenes if sc.get("type") in ("people", "quote") for sl in (sc.get("slots") or [])
             if sl.get("role") == "portrait" and sl.get("person") and _has_media(sl)]
    for sc, sl in sorted(slots, key=lambda t: order.get(t[1]["person"], 99)):
        for k in keys(sl):
            owner.setdefault(k, sl["person"])
    n = 0
    for sc, sl in slots:
        who = {owner[k] for k in keys(sl) if k in owner}
        if who and sl["person"] not in who:
            print(f"[people] {sc['id']}: под «{sl['person']}» то же фото, что у {', '.join(who)} — портрет снят", flush=True)
            sl["src"] = sl["image"] = None; sl["portrait_ok"] = False; n += 1
    return n

def reindex_people(scenes: list[dict]) -> int:
    """Пересчёт номеров portrait/activity в карточках людей по полям person и role самих слотов.
    Номера пишутся при сборке, но проверка кадров потом заменяет и выбрасывает слоты — и карточка начинает брать
    чужой кадр по устаревшему номеру (Google 20.09: под именем Craig Silverstein оказался портрет Брина).
    Вызывать после любой правки слотов people-сцены."""
    fixed = 0
    for sc in scenes:
        if sc.get("type") not in ("people", "quote"): continue
        slots = sc.get("slots") or []
        for p in (sc.get("data") or {}).get("persons") or []:
            name = str(p.get("name") or "").strip()
            if not name: continue
            pi = next((i for i, s in enumerate(slots) if s.get("role") == "portrait" and str(s.get("person") or "").strip() == name and _has_media(s)), None)
            ai = next((i for i, s in enumerate(slots) if s.get("role") == "activity" and str(s.get("person") or "").strip() == name), None)
            if p.get("portrait") != pi or p.get("activity") != ai:
                fixed += 1
                print(f"[people] {sc['id']}: {name} — кадр {p.get('portrait')}→{pi}, иллюстрация {p.get('activity')}→{ai}", flush=True)
            p["portrait"], p["activity"] = pi, ai
    return fixed

def _named_person(caption: str | None, cast: list[str] | None) -> str | None:
    """Имя из cast, которое стоит в подписи архивного кадра («Steve Wozniak, Homestead High yearbook 1968»)."""
    cap = (caption or "").lower()
    return next((n for n in (cast or []) if n and n.lower() in cap), None)

def _resolve_slots(x: dict, d, img_model: str, fal_cost: dict, ctx: str = "", vid: str = "", cast: list[str] | None = None):
    """Все слоты сцены; activity-слоты для people; не больше одного видео-слота на сцену; focus_xy (для архивного фото с именем
    в подписи — по лицу названного человека через vision, иначе по резкости); деградация split/people без медиа; зеркало для broll."""
    t = x.get("type") or "broll"; slots = x.get("slots") or []
    roles = ROLE_BY_TYPE.get(t, ["backdrop"])
    has_video = False
    for i, sl in enumerate(slots):
        sl["id"] = f"{x['id']}_s{i + 1}"; sl.setdefault("role", roles[min(i, len(roles) - 1)])
        if has_video:   # второй декодер OffthreadVideo удваивает время рендера
            sl["media"] = "photo"
            if sl["source"] == "stock": sl["source"] = "image"
        portrait = t in ("people", "quote")
        _resolve_slot(sl, d, img_model, fal_cost, ctx, vid, portrait=portrait, generate=not portrait or _cartoon["on"])
        if sl.get("src"): has_video = True
    if t == "people": _people_assemble(x, d, img_model, fal_cost, ctx, vid)
    elif t == "split" and not all(_has_media(sl) for sl in slots):
        alive = [sl for sl in slots if _has_media(sl)]
        x["downgrade"] = "split: один из слотов пуст"; print(f"[slot] {x['id']} split→broll: {x['downgrade']}")
        if alive:
            lab = (x["data"].get(alive[0].get("role") or "left") or {}).get("label")
            if lab and not alive[0].get("caption"): alive[0]["caption"] = lab
            alive[0]["role"] = "main"
        x["type"] = "broll"; x["data"] = {}; x["slots"] = alive[:1]
    elif t == "map":
        x["slots"] = [sl for sl in slots if _has_media(sl)]   # карта без inset — нормально
    elif t == "broll" and slots and not _has_media(slots[0]):
        print(f"[slot] {x['id']}: слот без медиа — Remotion покажет плашку с подписью")
    for sl in x["slots"]:
        if sl.get("src"): _video_dims(sl, d)   # aspect всегда из файла (кэш yt мог дать 4:3 при aspect 16:9 → кадр растянут)
        sl["focus_xy"] = [0.5, 0.5] if sl.get("src") else (A._saliency_focus(d / sl["image"]) if sl.get("image") else [0.5, 0.5])
        # групповое архивное фото с именем в подписи (ежегодник): наезд ведёт к лицу названного человека, а не к «самой резкой клетке»
        who = _named_person(sl.get("caption"), cast) if sl.get("kind") == "archive" and sl.get("image") and sl.get("role") != "portrait" else None
        if who:
            xy = archive.locate(d / sl["image"], who, sl.get("caption") or "", vid)
            if xy: sl["focus_xy"] = xy; sl["focus_who"] = who
        for k in ("src", "image", "kind", "aspect", "clip_seconds", "credit", "caption", "year"): sl.setdefault(k, None)
        sl.setdefault("at", None)
    if x["type"] == "broll": _mirror(x)

def _video_dims(sl: dict, d):
    """aspect и размер исходника видео-слота — по самому файлу (src_px нужен плёнке: зерно на апскейле 480p слабее)."""
    try:
        w, h = archive._dims(d / sl["src"])
        if w > 16 and h > 9: sl["aspect"] = round(w / h, 3); sl["src_px"] = [w, h]
    except Exception as e: print(f"[slot] {sl.get('id')}: размер видео не прочитан: {e}")

def _mirror(x: dict):
    """Первый слот дублируется на верхний уровень broll-сцены — Short.tsx, Subtitles и старый preflight работают без изменений."""
    sl = (x.get("slots") or [{}])[0]
    for k in ("src", "image", "kind", "aspect", "clip_seconds", "credit", "caption", "focus_xy"): x[k] = sl.get(k)

STOP = {"a", "an", "the", "of", "in", "on", "at", "and", "with", "for", "to", "from", "by", "old", "vintage", "close", "up", "shot", "view", "aerial"}

def _relevance(query: str, video: dict) -> float:
    """Pexels не отдаёт теги, но slug в url клипа описывает его: доля слов запроса, найденных в slug."""
    q = {w for w in re.findall(r"[a-z]+", query.lower()) if w not in STOP and len(w) > 2}
    slug = set(re.findall(r"[a-z]+", (video.get("url") or "").lower().split("/video/")[-1]))
    if not q: return 0.0
    hits = sum(1 for w in q if w in slug or any(s.startswith(w[:5]) for s in slug))
    return hits / len(q)

def _stock(x: dict, d, exclude: list | None = None) -> bool:
    """Ищем клип по запросу, берём только релевантные (slug совпадает с запросом), ≥ 1280px, 6–30 с; пропускаем уже отвергнутые."""
    q = x.get("query") or ""
    if not q: return False
    tried = x.setdefault("_tried", []); (d / "stock").mkdir(exist_ok=True); out = d / "stock" / f"{x['id']}.mp4"
    for query in (q, " ".join(q.split()[:2])):
        r = requests.get("https://api.pexels.com/videos/search", params={"query": query, "per_page": 15, "orientation": "landscape", "size": "medium"},
                         headers={"Authorization": os.getenv("PEXELS_API_KEY")}, timeout=60).json()
        cands = [v for v in (r.get("videos") or []) if 6 <= v.get("duration", 0) <= 30 and v["id"] not in tried and v["id"] not in _used_stock]
        cands = [(v, _relevance(q, v)) for v in cands]
        cands = [(v, s) for v, s in cands if s >= config.STOCK_MIN_RELEVANCE]   # описание клипа должно совпадать с запросом
        if not cands: continue
        cands.sort(key=lambda t: (-t[1], abs(t[0]["duration"] - 12)))
        for v, score in cands[:3]:
            files = [f for f in v["video_files"] if f.get("width") and config.STOCK_MIN_WIDTH <= f["width"] <= 1920 and f.get("file_type") == "video/mp4"]
            if not files: continue
            f = max(files, key=lambda f: f["width"])
            out.write_bytes(requests.get(f["link"], timeout=300).content); tried.append(v["id"])
            with _lock: _used_stock.add(v["id"])
            x["src"] = f"stock/{x['id']}.mp4"; x["clip_seconds"] = A._duration(out); x["credit"] = v.get("user", {}).get("name", ""); x["relevance"] = round(score, 2)
            x["aspect"] = round((f.get("width") or 16) / (f.get("height") or 9), 3)
            return True
    return False

def _clip(x: dict, d, fal_cost: dict):
    import fal_client
    (d / "clips").mkdir(exist_ok=True); out = d / "clips" / f"{x['id']}.mp4"
    img = (d / x["image"]).resolve()
    url = fal_client.upload_file(str(img))
    r = fal_client.subscribe(config.CLIP_MODEL, arguments={"image_url": url, "prompt": (x.get("prompt") or "") + ", " + (x.get("motion") or "slow camera move") + ", cinematic, no text",
                                                          "duration": str(config.CLIP_SECONDS), "prompt_optimizer": True})
    out.write_bytes(requests.get(r["video"]["url"], timeout=300).content)
    x["src"] = f"clips/{x['id']}.mp4"; x["clip_seconds"] = A._duration(out)
    with _lock: fal_cost["usd"] += config.CLIP_PRICE

# ---------- музыка по главам ----------

DEFAULT_MOODS = [("cold", "dramatic"), ("origin", "calm"), ("struggle", "sad"), ("turning", "inspirational"), ("scale", "bright"), ("crisis", "dramatic"), ("legacy", "inspirational")]

def _mood_for(part: dict, fallback: str) -> str:
    if part.get("mood"): return str(part["mood"]).lower()
    name = (part.get("name") or "").lower()
    return next((m for k, m in DEFAULT_MOODS if k in name), fallback)

def _music_tracks(s: dict, d, parts: list[int] | None = None) -> list[dict]:
    """Свой трек на каждую часть сценария (настроение из плана или по названию части). Файлы копируются в music/, порядок — по частям."""
    outline = s.get("outline") or [{"name": f"part {i}"} for i in range(1, 8)]
    lib = [p for p in config.MUSIC.glob("*") if p.suffix.lower() in (".mp3", ".wav", ".m4a", ".ogg") and not p.stem.startswith("sfx")]
    if not lib: print("[music] библиотека data/music пуста — видео без музыки"); return []
    fallback = (s.get("music_mood") or "calm").lower()
    idx = parts or list(range(1, len(outline) + 1))
    (d / "music").mkdir(exist_ok=True); tracks, last = [], None
    for i in idx:
        part = outline[i - 1] if 0 < i <= len(outline) else {}
        mood = _mood_for(part, fallback)
        pick = [p for p in lib if p.stem.lower().startswith(mood[:5])] or [p for p in lib if p.stem.lower().startswith(fallback[:5])] or lib
        pool = [p for p in pick if p != last] or pick
        src = random.choice(pool); last = src
        dst = d / "music" / f"p{i}{src.suffix.lower()}"; shutil.copy(src, dst)
        tracks.append({"part": i, "mood": mood, "src": f"music/{dst.name}", "file": src.name})
    sfx = next((p for p in config.MUSIC.glob("sfx_chapter.*")), None)
    if sfx: shutil.copy(sfx, d / "music" / sfx.name)
    print("[music] " + ", ".join(f"{t['part']}:{t['file']}" for t in tracks) + (f"; акцент {sfx.name}" if sfx else ""))
    return tracks

def _track_volume(d, src: str) -> float:
    try:
        from .. import loudness
        return loudness.music_gain(d / "voice.mp3", d / src, config.MUSIC_BELOW_DB)
    except Exception as e:
        print(f"[loudness] {e} — беру MUSIC_VOLUME={config.MUSIC_VOLUME}"); return config.MUSIC_VOLUME

def _track_offset(d, src: str) -> float:
    """Секунда файла, с которой трек главы стартует под карточкой (пропуск тихого интро, §3.5)."""
    try:
        from .. import loudness
        off = loudness.intro_offset(d / src)
        if off: print(f"[loudness] {src}: тихое интро — старт с {off:.1f} с")
        return off
    except Exception as e:
        print(f"[loudness] {src}: {e} — старт с 0"); return 0.0

def _sfx_offset(d, sfx: str | None) -> float | None:
    """Секунда стингера, с которой он звучит под карточкой: тихое вступление (1.5 с до −25 dBFS) пропускаем — атака в первые 0.3 с."""
    if not sfx: return None
    try:
        from .. import loudness
        return loudness.attack_offset(d / sfx)
    except Exception as e:
        print(f"[loudness] стингер offset: {e} — 0"); return 0.0

def _sfx_volume(d, sfx: str | None) -> float | None:
    if not sfx: return None
    try:
        from .. import loudness
        return loudness.sfx_gain(d / "voice.mp3", d / sfx)
    except Exception as e:
        print(f"[loudness] стингер: {e} — 0.15"); return 0.15

# ---------- таймлайн ----------

def _strip_private(o):
    """Ключи с «_» — рабочие пометки этапов отбора (какие кандидаты уже пробовали и т. п.). В timeline.json они не нужны,
    а один из них (_today) хранил объект картинки PIL и ронял запись всего таймлайна (Amazon 18.09)."""
    if isinstance(o, dict):
        for k in [k for k in o if isinstance(k, str) and k.startswith("_")]: o.pop(k)
        for v in o.values(): _strip_private(v)
    elif isinstance(o, list):
        for v in o: _strip_private(v)
    return o


def _as_scene(x: dict) -> dict:
    """Старый плоский кадр (timeline до слотов) → сцена со слотом-зеркалом."""
    if isinstance(x.get("slots"), list) and x["slots"] and "source" not in x: return x
    if not isinstance(x.get("slots"), list) or not x["slots"]:
        sl = {"id": f"{x['id']}_s1", "role": "main"}
        for k in ("source", "query", "query_alt", "media", "caption", "prompt", "focus", "src", "image", "kind", "aspect", "clip_seconds", "credit", "year"):
            sl[k] = x.get(k)
        sl["focus_xy"] = x.get("focus_xy") or [0.5, 0.5]; sl["at"] = None
        x["slots"] = [sl]
    x.setdefault("type", "broll"); x.setdefault("data", {})
    return x

def _find_idx(text: list[str], anchor: str, pos: int = 0):
    a = [A._norm(w) for w in re.sub(r"\[F\d+\]", "", anchor or "").split()]; a = [w for w in a if w]
    for n in (5, 4, 3):
        i = A._find(text, a[:n], pos)
        if i is None: i = A._find(text, a[:n])
        if i is not None: return i
    return None

def _transitions(shots: list[dict]):
    """Переходы (§2.12) по уже отсортированным сценам: dip (первый кадр главы) не трогаем; cut — вход/выход полнокадрового
    архивного видео (broll) или сцена после montage; иначе xfade. Вызывается и из preflight — после замен медиа вид перехода может поменяться."""
    for i, x in enumerate(shots):
        if x.get("transition") == "dip": continue
        sl = (x.get("slots") or [{}])[0]
        prev = shots[i - 1] if i else None; psl = ((prev or {}).get("slots") or [{}])[0]
        # склейка хроники — только у полнокадрового архивного видео (broll); inset карты или портрет-видео people — не повод для cut
        arch_video = x.get("type") == "broll" and bool(sl.get("src")) and sl.get("kind") == "archive"
        prev_cut = prev is not None and (prev.get("type") == "montage" or (prev.get("type") == "broll" and bool(psl.get("src")) and psl.get("kind") == "archive"))
        x["transition"] = "cut" if (arch_video or prev_cut) else "xfade"

def _fix_short(shots: list[dict], words: list[dict]):
    """broll короче SCENE_MIN_SEC (следующий кадр начался слишком рано): если следующая сцена стоит посреди предложения — её старт
    сдвигается к началу следующего предложения («for $150 each» больше не режется склейкой на архивное видео); иначе короткий broll
    выбрасывается и предыдущая сцена держится дольше. Первый кадр главы (dip) и первую сцену не трогаем."""
    def sent_start(k): return k is not None and (k == 0 or words[k - 1]["w"][-1:] in ".!?;")
    i = 1
    while i < len(shots):
        prev, x = shots[i - 1], shots[i]
        short = prev["type"] == "broll" and x["start"] - prev["start"] < config.SCENE_MIN_SEC and x.get("transition") != "dip"
        if not short: i += 1; continue
        k = x.get("_idx"); done = False
        if k is not None and not sent_start(k):
            k2 = next((j for j in range(k + 1, min(len(words), k + 16)) if sent_start(j)), None)
            if k2 is not None:
                t2 = words[k2]["s"]; nxt_end = shots[i + 1]["start"] if i + 1 < len(shots) else words[-1]["e"] + 2
                if t2 - prev["start"] >= config.SCENE_MIN_SEC - 0.5 and (nxt_end - t2 >= config.SCENE_MIN_SEC * 0.8):   # 4.5 с с целой фразой лучше выброшенного кадра
                    print(f"[story] {x['id']}: старт {x['start']:.1f} → {t2:.1f} с (начало предложения; {prev['id']} держал бы {x['start'] - prev['start']:.1f} с)")
                    x["start"] = round(t2, 3); x["_idx"] = k2; done = True
        if not done and i - 1 > 0 and prev.get("transition") != "dip":
            print(f"[story] {prev['id']}: broll {x['start'] - prev['start']:.1f} с < {config.SCENE_MIN_SEC:.0f} — выброшен, {shots[i - 2]['id']} держится дольше")
            shots.pop(i - 1); continue
        i += 1

PEOPLE_MIN_SEC = 8.0   # сцена с людьми короче — «ничего не понятно» (владелец 16.09, пролог 4.5 с): колонки въезжают, плашки печатаются

def _hold_people(shots: list[dict]):
    """Сцена people короче PEOPLE_MIN_SEC держится дольше за счёт следующего broll, если тот остаётся не короче SCENE_MIN_SEC;
    иначе следующий broll выбрасывается целиком (его текст звучит под людьми). Первый кадр главы (dip) не сдвигаем."""
    i = 0
    while i + 1 < len(shots):
        x, nxt = shots[i], shots[i + 1]
        dur = nxt["start"] - x["start"]
        if x["type"] not in ("people", "quote") or dur >= PEOPLE_MIN_SEC or nxt.get("transition") == "dip" or nxt["type"] != "broll":
            i += 1; continue
        need = PEOPLE_MIN_SEC - dur
        after = (shots[i + 2]["start"] if i + 2 < len(shots) else nxt["start"] + 60) - (nxt["start"] + need)
        if after >= config.SCENE_MIN_SEC:
            print(f"[story] {x['id']}: люди {dur:.1f} с → {PEOPLE_MIN_SEC:.0f} с, {nxt['id']} стартует позже")
            nxt["start"] = round(nxt["start"] + need, 3); i += 1
        else:
            print(f"[story] {x['id']}: люди {dur:.1f} с — {nxt['id']} выброшен, люди держатся до следующей сцены")
            shots.pop(i + 1)

def _map_points(x: dict, text: list[str], words: list[dict], i0: int):
    """Точки карты по якорям: `at` на своём слове; точка, чей якорь звучит позже конца сцены больше чем на MAP_AHEAD_SEC
    («Wozniak» за 14 с до упоминания), не показывается — лучше две точки вовремя, чем три раньше времени; минимум две остаются."""
    d = x.get("data") or {}; pts = d.get("points") or []
    info = []
    for p in pts:
        k = _find_idx(text, p.get("anchor", ""), i0) if p.get("anchor") else None
        late = (words[k]["s"] - x["end"]) if k is not None else None
        info.append((p, k, late))
    kept = [t for t in info if t[2] is None or t[2] <= config.MAP_AHEAD_SEC]
    dropped = [t for t in info if t not in kept]
    for t in sorted(dropped, key=lambda t: t[2]):   # минимум две точки — возвращаем ближайшие по времени
        if len(kept) >= 2: break
        kept.append(t); dropped.remove(t)
    kept.sort(key=lambda t: info.index(t))
    for p, k, late in kept:
        p["at"] = round(max(0.0, words[k]["s"] - x["start"]), 2) if k is not None and words[k]["s"] < x["end"] + 1 else None
        if p.get("anchor") and p["at"] is None: print(f"[story] {x['id']}: якорь «{p['anchor']}» вне сцены — точка без синхронизации")
    if dropped:
        print(f"[story] {x['id']} map: точки {', '.join(str(t[0].get('name')) for t in dropped)} — якорь позже сцены на {max(t[2] for t in dropped):.0f} с, не показываются")
        old = [t[0] for t in info]; idx = {old.index(t[0]): n for n, t in enumerate(kept)}
        route = d.get("route")
        if isinstance(route, list):
            new_route = [idx[i] for i in route if i in idx]
            if len(new_route) < 2: new_route = None; d["distance_label"] = None
            d["route"] = new_route
        d["points"] = [t[0] for t in kept]
        if not any(p.get("main") for p in d["points"]): d["points"][0]["main"] = True
    route, pts = d.get("route"), d.get("points") or []
    if d.get("distance_label") and isinstance(route, list) and len(route) >= 2:   # старые shots (до валидации подписи): «a few miles» на 46 км
        from .story import _km, _distance_ok
        km = sum(_km(pts[a]["lat"], pts[a]["lon"], pts[b]["lat"], pts[b]["lon"]) for a, b in zip(route, route[1:]))
        if not _distance_ok(str(d["distance_label"]), km): print(f"[story] {x['id']} map: подпись «{d['distance_label']}» не про маршрут ({km:.0f} км) — убрана"); d["distance_label"] = None

def _with_land(x: dict) -> dict:
    """Карта города/региона: берег Natural Earth 10m под её область (на общем 50m залив Сан-Франциско — грубый многоугольник)."""
    data = x.get("data") or {}
    if x.get("type") != "map" or data.get("zoom") == "world": return x
    try:
        from ..tools import make_geo
        land = make_geo.detail(data.get("points") or [])
    except Exception as e:
        print(f"[story] {x['id']} map: подробный берег не вышел ({str(e)[:80]}) — общий 50m"); return x
    return {**x, "data": {**data, "land": land}} if land else x

def _thin_flashes(auto: list[dict], gap: float = 25.0, first90: int = 3, cap: int = 40) -> list[dict]:
    """Из всех цифр озвучки на экран идут важные: деньги, проценты, масштаб (K/M/B/T) — вес 2; счёт с подписью — 1; голое число — 0 (не показываем).
    Между плашками не меньше gap секунд (при конфликте остаётся более важная), в первые 90 с не больше first90, всего не больше cap.
    Главная пара (type=pair) остаётся всегда. McDonald's 22.09: было 143 плашки, 16 за первые 90 секунд."""
    def w(o):
        if o.get("type") == "pair": return 9
        v = str(o.get("value") or "")
        if "$" in v or "%" in v or re.search(r"\d[KMBT]$", v) or "–" in v: return 2
        return 1 if o.get("label") else 0
    cands = sorted([o for o in auto if w(o) > 0], key=lambda o: (-w(o), o["start"]))
    kept: list[dict] = []
    for o in cands:
        if w(o) < 9:
            if any(abs(o["start"] - k["start"]) < gap for k in kept): continue
            if o["start"] < 90 and sum(1 for k in kept if k["start"] < 90) >= first90: continue
            if len(kept) >= cap: continue
        kept.append(o)
    kept.sort(key=lambda o: o["start"])
    print(f"[story] цифр на экран после отбора: {len(kept)} из {len(auto)} (не чаще раза в {gap:.0f} с, в первые 90 с ≤ {first90})", flush=True)
    return kept

def _norm_num(v: str) -> str:
    return re.sub(r"[^0-9a-z.]", "", str(v).lower())

def _same_num(a_raw, b_raw) -> bool:
    a, n = _norm_num(a_raw), _norm_num(b_raw)
    return bool(a) and (a == n or (a[:-1].split(".")[0] == n[:-1].split(".")[0] and a[-1:] == n[-1:]))

def _mag(v: str) -> str:
    """Масштаб числа: k/m/b/t по суффиксу или слову, пусто — голое число."""
    m = re.search(r"\d\s*(k|m|b|t|thousand|million|billion|trillion)\b", str(v).lower())
    return (m.group(1)[0] if m else "")

def _pair_and_sources(d, auto: list[dict]) -> list[dict]:
    """Главная цифра ролика (правая цифра обложки) при первом упоминании — полноэкранной парой «было → стало» (владелец 21.09);
    остальные цифры идут строкой-леджером. Данные пары — из payload.thumbv или брифа, лежат рядом в thumbv/props_a.json."""
    try:
        from .. import db as _db
        v = _db.get(d.name); b = v["payload"].get("brief") or {}; tv = v["payload"].get("thumbv") or {}
        then, now = str(tv.get("hook") or b.get("thumb_then") or ""), str(tv.get("hook2") or b.get("thumb_now") or "")
        yrs = [tv.get("tagL"), tv.get("tagR")] if tv.get("tagL") else list(b.get("thumb_years") or [])
        if then and now:
            units = [str(u).strip() for u in (b.get("thumb_units") or [])][:2]
            if len(units) != 2 or not all(units): units = []
            if not units and _mag(then) != _mag(now) and re.search(r"\d", then) and re.search(r"\d", now):
                # 26.09 Verisign: «$21B → $10.97» с одними годами читалось как превращение миллиардов в десять долларов
                print(f"[story] пара {then} → {now} не ставится: разный масштаб чисел, а подписей, что это за числа, в брифе нет", flush=True)
                return auto
            order = sorted([o for o in auto if o.get("start") is not None], key=lambda o: o["start"])
            t_then = next((o["start"] for o in order if _same_num(o["value"], then)), None)
            if t_then is None and re.search(r"\d", then):
                print(f"[story] пара {then} → {now} не ставится: левое число в тексте не звучит", flush=True)
                return auto
            yl, yr = str((yrs + ["", ""])[0] or ""), str((yrs + ["", ""])[1] or "")
            tl = " · ".join(x for x in (yl, units[0] if units else "") if x)
            tr = " · ".join(x for x in (yr, units[1] if units else "") if x)
            for o in order:
                if t_then is not None and o["start"] < t_then: continue   # 26.09: пара на 94-й секунде, а $21B звучит минут через пять
                if _same_num(o["value"], now):
                    o.update({"type": "pair", "then": then, "now": now, "tagL": tl, "tagR": tr, "seconds": 4.0})
                    print(f"[story] главная пара {then} → {now} на {o['start']:.0f}-й секунде ({tl} / {tr})", flush=True); break
            else:
                print(f"[story] пара {then} → {now} не ставится: после левого числа правое больше не звучит", flush=True)
    except Exception as e: print(f"[story] главная пара не поставлена: {str(e)[:120]}", flush=True)
    return auto

def _timeline(d, shots: list[dict], overlays: list[dict], script: str, title: str, tracks: list[dict] | None = None,
              pauses: list[dict] | None = None, film: dict | None = None) -> dict:
    """Сцены и титры по словам words.json (уже сдвинутым паузами). Карточки глав — из pauses (chapter от модели выбрасывается);
    первый кадр главы стартует на at с transition dip; музыка по границам пауз; film-блок; зеркало первого слота у broll."""
    words = json.loads(config.read(d / "words.json"))
    text = [A._norm(w["w"]) for w in words]
    shots = [_as_scene(x) for x in shots]
    def place(items):
        pos = 0
        for it in items:
            idx = _find_idx(text, it.get("anchor", ""), pos)
            it["start"] = words[idx]["s"] if idx is not None else None; it["_idx"] = idx
            if idx is not None: pos = idx
    place(shots); place(overlays)
    if config.NUMBER_FLASHES:   # каждая цифра озвучки — на экран на своих словах (numbers.py); flash от модели заменяются
        from . import numbers as N
        auto = N.flashes(words)
        # возраст человека из сцены people («Steve Jobs is 21. Steve Wozniak is 25.») — в плашку его колонки, а не общей цифрой в углу
        # (владелец 16.09: возраст обоих всплывал в одном месте над Джобсом)
        anchored = sorted([x for x in shots if x.get("_idx") is not None], key=lambda x: x["_idx"])
        for o in auto:
            if o.get("label") != "years old": continue
            k = next((j for j in range(len(anchored) - 1, -1, -1) if anchored[j]["_idx"] <= o["_idx"] + 2), None)   # сцена, на которой звучит возраст
            host = anchored[k] if k is not None else None
            if host and host.get("type") != "people" and k > 0 and anchored[k - 1].get("type") == "people" \
                    and words[o["_idx"]]["s"] - words[anchored[k - 1]["_idx"]]["s"] < PEOPLE_MIN_SEC:
                host = anchored[k - 1]   # короткая сцена людей будет продлена до PEOPLE_MIN_SEC (_hold_people) — возраст звучит под ней
            if not host or host.get("type") != "people": continue
            persons = (host.get("data") or {}).get("persons") or []
            # ближайшее имя перед цифрой; фамилия надёжнее имени («Steve Jobs is 21. Steve Wozniak is 25.» — оба Steve)
            firsts = [(p.get("name") or "").split()[0].lower() for p in persons if p.get("name")]
            who = None
            for k in range(o["_idx"] - 1, max(-1, o["_idx"] - 6), -1):
                tok = re.sub(r"[^a-z]", "", words[k]["w"].lower())
                for p in persons:
                    parts = [n.lower() for n in (p.get("name") or "").split()]
                    if not parts: continue
                    if tok == parts[-1] or (tok == parts[0] and firsts.count(parts[0]) == 1): who = p; break
                if who or (k < o["_idx"] - 1 and re.search(r"[.!?]$", words[k]["w"])): break   # не заходим в предыдущее предложение
            if who:
                who["age"] = o["value"]; who["age_t"] = words[o["_idx"]]["s"]; o["type"] = "_age"
        auto = [o for o in auto if o["type"] != "_age"]
        auto = _thin_flashes(_pair_and_sources(d, auto))   # СНАЧАЛА прореживаем: до 23.09 в overlays ложился полный список,
        overlays = [o for o in overlays if o.get("type") != "flash"] + auto   # а прореженный оставался только в логе (Costco: 102 плашки при логе «35»)
        print(f"[story] цифр на экран: {len(auto)} (" + ", ".join(o["value"] for o in auto[:12]) + ("…" if len(auto) > 12 else "") + ")")
    for i, x in enumerate(shots):   # кадры без якоря — между соседями
        if x["start"] is None:
            prev = next((y["start"] for y in reversed(shots[:i]) if y["start"] is not None), 0)
            nxt = next((y["start"] for y in shots[i + 1:] if y["start"] is not None), words[-1]["e"])
            x["start"] = (prev + nxt) / 2
    shots.sort(key=lambda x: x["start"]); shots[0]["start"] = 0.0
    dur = words[-1]["e"] + 2
    pauses = [p for p in (pauses or []) if 0 <= p["at"] < dur]
    # первый кадр главы: сцена на первых словах части стартует под карточкой (start = at, dip), предыдущая заканчивается на at
    for p in pauses:
        idx = p.get("word_index"); ws = words[idx]["s"] if isinstance(idx, int) and 0 <= idx < len(words) else p["at"] + p["gap"]
        j = next((k for k, x in enumerate(shots) if x["start"] >= ws - 0.05), None)
        if j is not None and j > 0 and shots[j]["start"] - p["at"] <= 15:
            shots[j]["start"] = p["at"]; shots[j]["transition"] = "dip"
        else: print(f"[story] глава {p['part']}: рядом с паузой {p['at']:.1f} с нет сцены — карточка над предыдущим кадром")
    def ends():   # последняя сцена держится до конца ролика (голая бумага в хвосте — пустой кадр)
        for i, x in enumerate(shots):
            x["end"] = shots[i + 1]["start"] if i + 1 < len(shots) else dur
            x.setdefault("type", "broll")
    ends()
    _fix_short(shots, words); ends()
    _hold_people(shots); ends()
    chapter_end = {p["at"]: p["at"] + config.CHAPTER_LEAD + config.CHAPTER_SEC for p in pauses}
    # карта: якорь точки в следующей сцене → продлеваем карту (≤ 36 слов ≈ 15 с голоса), если соседу остаётся ≥ 6 с;
    # и минимум на хореографию (камера + точки + маршрут + подпись) после проявления карточки
    for i, x in enumerate(shots[:-1]):
        if x["type"] != "map": continue
        nxt = shots[i + 1]; pts = (x.get("data") or {}).get("points") or []
        veil = chapter_end.get(x["start"], x["start"]) + 0.3 - x["start"] if x.get("transition") == "dip" else 0.0
        need = x["start"] + veil + 0.6 + 0.9 * len(pts) + 2.5
        i0 = _find_idx(text, x.get("anchor", "")) or 0
        for p in pts:
            k = _find_idx(text, p.get("anchor", ""), i0) if p.get("anchor") else None
            if k is not None and words[k]["s"] >= x["end"]: need = max(need, words[k]["e"] + 1.5)
        cap = x["start"] + veil + 15.0
        new_end = min(need, cap)
        if new_end > x["end"] + 0.05:
            if nxt["end"] - new_end >= 6.0:
                print(f"[story] {x['id']} map: продлена {x['end']:.1f} → {new_end:.1f} с (якоря точек / хореография), {nxt['id']} позже")
                nxt["start"] = round(new_end, 3); ends()
            else: print(f"[story] {x['id']} map: точки за пределами сцены ({need:.1f} с), продлить нельзя — {nxt['id']} стал бы короче 6 с")
    _transitions(shots)
    for i, x in enumerate(shots):
        x.pop("_tried", None); x.pop("_idx", None)
        for s2 in x["slots"]: s2.pop("_tried", None)
        # секунда появления элементов относительно начала сцены — по якорям точек карты / слотов montage
        i0 = _find_idx(text, x.get("anchor", "")) or 0
        if x["type"] == "map": _map_points(x, text, words, i0)
        for el in [s2 for s2 in x["slots"] if s2.get("anchor")]:
            k = _find_idx(text, el.get("anchor", ""), i0) if el.get("anchor") else None
            el["at"] = round(max(0.0, words[k]["s"] - x["start"]), 2) if k is not None and words[k]["s"] < x["end"] + 1 else None
            if el.get("anchor") and el["at"] is None: print(f"[story] {x['id']}: якорь «{el['anchor']}» вне сцены — элемент без синхронизации")
        # картинка дольше STILL_MAX_SEC: «slow push in» 1.00→1.07 за 12 с не читается как движение — усиливаем наезд
        sl0 = (x["slots"] or [{}])[0]
        if x["type"] == "broll" and sl0.get("image") and not sl0.get("src") and x["end"] - x["start"] > config.STILL_MAX_SEC \
                and re.search(r"static|slow push", str(x.get("motion") or ""), re.I):
            x["motion"] = "push in hard"; print(f"[story] {x['id']}: картинка {x['end'] - x['start']:.1f} с — наезд усилен (push in hard)")
        if x["type"] == "broll": _mirror(x)
    ov = []
    for p in pauses:
        ov.append({"type": "chapter", "n": p["part"], "text": p["name"], "start": round(p["at"] + config.CHAPTER_LEAD, 3),
                   "end": round(p["at"] + config.CHAPTER_LEAD + config.CHAPTER_SEC, 3), "pause": {"at": p["at"], "gap": p["gap"]}})
    k = 0
    for o in overlays:
        if o["start"] is None: continue
        if o["type"] == "chapter":
            if pauses or (d / "pauses.json").exists(): continue   # карточки строятся из пауз; без pauses.json — старое поведение
            o["end"] = o["start"] + CHAPTER_SEC; k += 1; o.setdefault("n", o.get("part") or k + 1)
        else:
            o["end"] = round(o["start"] + min(float(o.get("seconds") or 3), {"caption": 4, "flash": 3, "year": 2.5}.get(o["type"], 3)), 3)
        ov.append({k2: v for k2, v in o.items() if k2 not in ("part", "_idx")})
    ov.sort(key=lambda o: o["start"])
    # титры не должны сталкиваться: caption/flash рядом с карточкой главы или с подписью архивного кадра — убираем или сдвигаем
    chapters = [o for o in ov if o["type"] == "chapter"]
    def near_chapter(t): return any(c["start"] - 1 <= t <= c["end"] + 1 for c in chapters)
    for i, x in enumerate(shots):   # подпись первого кадра главы появляется после карточки; иначе — после входного наплыва
        # (+0.2 с), чтобы карточка архива не печаталась поверх ещё видимых плашек предыдущей сцены
        xf = 0.0 if x.get("transition") in ("cut", "dip") or i == 0 else (config.XFADE_RICH_SEC if x["type"] in config.RICH_TYPES else 0.5)
        x["caption_delay"] = next((round(c["end"] - x["start"] + 0.3, 2) for c in chapters if c["start"] - 0.5 <= x["start"] <= c["end"]), round(xf + 0.2, 2) if xf else 0)
    for o in ov:   # цифра остаётся на своих словах (flash слева сверху, карточка архива слева снизу); если они совпали по времени —
        # карточка архива печатается после ухода цифры, когда сцене хватает места, иначе обе (углы разные)
        if o["type"] != "flash" or o["start"] is None: continue
        o["end"] = round(min(o["end"], dur), 3)
        sc = next((x for x in shots if x.get("caption") and x["start"] <= o["start"] < x["start"] + x.get("caption_delay", 0) + CAPTION_SEC), None)
        if sc:
            t2 = round(o["end"] - sc["start"] + 0.3, 2)
            if sc["end"] - sc["start"] - t2 >= 3.0:
                sc["caption_delay"] = t2; print(f"[story] {sc['id']}: карточка архива после flash «{o.get('value')}» (+{t2:.1f} с)")
            else: print(f"[story] flash «{o.get('value')}» и карточка архива {sc['id']} одновременно — углы разные, оставлено")
    cap_windows = [(x["start"] + x.get("caption_delay", 0), x["start"] + x.get("caption_delay", 0) + CAPTION_SEC) for x in shots if x.get("caption")]
    keep = []
    for o in ov:
        if o["type"] == "chapter": keep.append(o); continue
        if near_chapter(o["start"]): continue
        if o["type"] == "caption" and any(a - 1 <= o["start"] <= b + 1 for a, b in cap_windows): continue   # архивный кадр уже подписан
        keep.append(o)
    ov = keep
    ov.sort(key=lambda o: o["start"])
    # музыка: границы = паузы (или карточки глав у старых видео); трек части i звучит от своей границы до следующей;
    # offset — старт трека с первого громкого места (тихое интро под карточкой = мёртвая тишина)
    music_tracks = []
    if tracks:
        bounds = [0.0] + ([p["at"] for p in pauses] if pauses else [o["start"] for o in ov if o["type"] == "chapter"]) + [dur]
        vol, off = {}, {}
        for i in range(len(bounds) - 1):
            t = tracks[min(i, len(tracks) - 1)]
            if t["src"] not in vol: vol[t["src"]] = _track_volume(d, t["src"]); off[t["src"]] = _track_offset(d, t["src"])
            music_tracks.append({"src": t["src"], "start": round(bounds[i], 3), "end": round(bounds[i + 1], 3), "volume": vol[t["src"]], "mood": t.get("mood"),
                                 "offset": off[t["src"]] if i > 0 else 0.0})
    sfx = next((f"music/{p.name}" for p in (d / "music").glob("sfx_chapter.*")), None) if (d / "music").exists() else None
    scenes = [_with_land(x) for x in shots]   # копии: подробный берег только в timeline, не в payload
    tl = {"scenes": scenes, "overlays": ov, "duration": dur, "shorts": A._short_segments(script, words),
          "channel": config.CHANNEL_NAME, "title": title, "music": None, "music_volume": 0, "music_tracks": music_tracks, "sfx_chapter": sfx,
          "sfx_volume": _sfx_volume(d, sfx) if pauses else None, "sfx_offset": _sfx_offset(d, sfx) if pauses else None,
          "subtitles": config.STORY_SUBTITLES, "format": "story", "voice": True, "voice_src": "voice.mp3",
          "pauses": [{"part": p["part"], "name": p["name"], "at": p["at"], "gap": p["gap"]} for p in pauses], "film": film}
    _check_cover(tl)
    _strip_private(tl)   # служебные ключи этапов (_tried, _today и пр.) в таймлайне не нужны и иногда несут несериализуемое
    config.write(d / "timeline.json", json.dumps(tl, ensure_ascii=False, indent=2))
    types = {}
    for x in shots: types[x["type"]] = types.get(x["type"], 0) + 1
    print(f"[story] таймлайн: {len(shots)} сцен (" + ", ".join(f"{t} {n}" for t, n in types.items()) + f"), {len(ov)} титров, {len(music_tracks)} музыкальных отрезков, "
          f"{len(pauses)} пауз, плёнка {film['strength'] if film else 'нет'}, {dur/60:.1f} мин")
    return tl

def retime(vid: str) -> dict:
    """Пересобрать timeline.json из payload.script.shots/overlays (ассеты уже разрешены) на новых words.json и pauses.json.
    Треки — из существующего music_tracks (уникальные src по порядку), иначе заново. Без сети."""
    v = db.get(vid); d = db.video_dir(vid); s = v["payload"]["script"]
    tracks = []
    if (d / "timeline.json").exists():
        old = json.loads(config.read(d / "timeline.json"))
        for t in old.get("music_tracks") or []:
            if t["src"] not in [x["src"] for x in tracks]: tracks.append({"src": t["src"], "mood": t.get("mood"), "part": len(tracks) + 1})
    if not tracks: tracks = _music_tracks(s, d)
    tl = _timeline(d, s["shots"], s.get("overlays", []), s["script"], v["title"], tracks, pauses=P.load(d), film=config.film_block())
    print(f"[retime] {vid}: {len(tl['scenes'])} сцен, {tl['duration']:.1f} с")
    return tl

def _check_cover(tl: dict):
    """Каждая секунда ролика покрыта сценой: первая с 0, без дыр между соседями, последняя до duration. Падает громко."""
    sc = sorted(tl.get("scenes") or [], key=lambda x: x["start"])
    if not sc: raise RuntimeError("[check] в timeline нет сцен")
    gaps = []
    if sc[0]["start"] > 0.01: gaps.append(f"0–{sc[0]['start']:.2f}")
    for a, b in zip(sc, sc[1:]):
        if b["start"] > a["end"] + 0.01: gaps.append(f"{a['end']:.2f}–{b['start']:.2f} ({a['id']}→{b['id']})")
    if sc[-1]["end"] < tl["duration"] - 0.01: gaps.append(f"{sc[-1]['end']:.2f}–{tl['duration']:.2f} (хвост после {sc[-1]['id']})")
    if gaps: raise RuntimeError("[check] в таймлайне пустые окна без сцены: " + "; ".join(gaps))

def _check_files(d, tl: dict) -> int:
    """Каждый src/image из timeline существует и не пустой — иначе чёрный хвост в рендере (demo4); каждая секунда покрыта сценой. Падает громко."""
    _check_cover(tl)
    missing = []
    VISUAL = ("broll", "split")   # у этих сцен показывать нечего, кроме кадра; у map/people/quote своя картинка
    for sc in tl.get("scenes", []):
        for sl in (sc.get("slots") or [sc]):
            for k in ("src", "image"):
                p = sl.get(k)
                if not p: continue
                f = d / p
                if not f.exists() or f.stat().st_size < 2000: missing.append(f"{sc['id']}/{sl.get('id', k)}: {p}")
            # 24.09: слот вообще без кадра проверка молча пропускала («if not p: continue»), и в опубликованный Costco
            # ушли 20 секунд пустоты на 25:19 и 25:38. Теперь пустой слот видимой сцены останавливает рендер.
            if sc.get("type") in VISUAL and not (sl.get("src") or sl.get("image")):
                missing.append(f"{sc['id']}/{sl.get('id', '?')}: слот без кадра ({sc.get('type')}, {sc.get('start', 0):.0f}–{sc.get('end', 0):.0f} с)")
    for t in tl.get("music_tracks") or []:
        if not (d / t["src"]).exists(): missing.append(f"music: {t['src']}")
    if missing: raise RuntimeError("[check] в timeline есть файлы, которых нет или они пустые:\n  " + "\n  ".join(missing))
    n = sum(1 for sc in tl.get("scenes", []) for sl in (sc.get("slots") or [sc]) if sl.get("src") or sl.get("image"))
    print(f"[check] файлов на месте: {n}")
    return n
