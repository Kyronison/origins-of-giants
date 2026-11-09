"""Второй канал на другом языке (владелец 22.09: «придумай всё для испанского канала end-to-end»).

Из готового английского ролика собирается локальная версия в папке `<vid>__es`: перевод сценария по предложениям (1:1, чтобы
тайминги сцен переносились по предложениям), озвучка тем же конвейером (ElevenLabs v3 через fal, голос ES_VOICE_ID), паузы глав,
тайм-карта английские слова → испанские, все подписи в кадре переводятся одним запросом, музыка собирается заново под новые
границы глав, обложка та же (цифры и годы), комплект публикации по-испански с главами по новым таймкодам, рендер, техпроверка.
Кадры, портреты и картинки не покупаются второй раз: папки archive/images/stock подключаются ссылками (junction).
Загрузка — на второй канал своим токеном (`auth-es`, data/youtube_token_es.json), статусы `localized`/`localized_uploaded`
вне очереди NEXT, чтобы watch не отправил испанский ролик на английский канал."""
import io, json, os, re, shutil, subprocess, bisect
from datetime import datetime, timedelta, timezone
from pathlib import Path
from .. import config, db, llm

LANGS = {
    "es": {"name": "español neutro latinoamericano (Latin American Spanish, neutral)", "channel": "Orígenes de Gigantes",
           "tagline": "Documentales sobre cómo se hizo el dinero", "mark": "G",
           "subscribe": "Orígenes de Gigantes cuenta cómo empezaron de verdad las empresas más grandes del mundo. Suscríbete para el próximo.",
           "full": "Documental completo en nuestro canal", "yt_lang": "es", "chapters": "CAPÍTULOS", "token": "youtube_token_es.json"},
}
SENT = re.compile(r"(?<=[.!?…])\s+(?=[\"“(\[]?[A-Z0-9$¿¡])")


def _dir(vid2: str) -> Path:
    return config.VIDEOS / vid2


def _link(src: Path, dst: Path):
    """Копия папки кадров исходного ролика. Junction не годится: бандлер Remotion пытается сделать symlink и падает с EPERM
    (Netflix es 22.09). Копии удаляются после загрузки на канал (_cleanup), чтобы не держать по 1.5 ГБ на версию."""
    if not src.exists(): return
    shutil.copytree(src, dst, dirs_exist_ok=True)   # папка могла остаться частично (после _cleanup туда кладётся дорисованная вырезка) — докопировать (23.09)


def _cleanup(d2: Path):
    """После загрузки: копии archive/images/stock/music не нужны — оригиналы лежат у английского ролика."""
    for sub in ("archive", "images", "stock", "music"):
        p = d2 / sub
        if p.exists() and not p.is_symlink():
            shutil.rmtree(p, ignore_errors=True)


def _sentences(text: str) -> list[str]:
    from .assets import clean_text
    t = " ".join(clean_text(text).split())
    return [s for s in SENT.split(t) if s.strip()]


def _translate_parts(parts: list[str], lang: str, vid: str) -> list[list[str]]:
    """Перевод по предложениям 1:1: столько же предложений, тот же порядок — по ним переносятся тайминги сцен."""
    L = LANGS[lang]; out = []
    for i, p in enumerate(parts, 1):
        sents = _sentences(p)
        q = (f"Переведи закадровый текст документального фильма об истории компании на {L['name']}. Аудитория — Латинская Америка и "
             "испаноязычные США. Стиль: живой, разговорный, без канцелярита, с той же иронией; цифры, суммы, годы, имена и названия "
             "компаний — без изменений; доллары остаются долларами ($). Каждое предложение переводится РОВНО одним предложением, порядок тот же — "
             "верни JSON-список той же длины. Не сокращай и не добавляй.\n\n" + json.dumps(sents, ensure_ascii=False))
        r = llm.ask_json('{"sentences": ' + "" if False else q + '\n\nФормат ответа: {"sentences": ["...", "..."]}', heavy=True, max_tokens=9000,
                         tag=f"loc_{lang}_{i}_{vid}", model=config.LLM_MODEL_WRITER or None)
        es = [str(x).strip() for x in (r.get("sentences") or [])]
        if len(es) != len(sents):
            print(f"[localize] часть {i}: {len(sents)} → {len(es)} предложений, выравниваю пропорционально", flush=True)
        out.append(es or sents)
        print(f"[localize] часть {i}: {len(sents)} предложений → {sum(len(s.split()) for s in es)} слов", flush=True)
    return out


def _translate_strings(items: dict, lang: str, vid: str) -> dict:
    if not items: return {}
    L = LANGS[lang]
    q = (f"Переведи подписи из кадра документального фильма на {L['name']}. Это короткие титры: места и даты, названия глав, роли людей, "
         "подписи к цифрам, ярлыки схем. Имена людей, названия компаний и продуктов, годы и суммы — без изменений. Регистр как в оригинале "
         "(если ВСЁ ЗАГЛАВНЫМИ — так же). Верни JSON с теми же ключами.\n\n" + json.dumps(items, ensure_ascii=False))
    r = llm.ask_json(q, heavy=True, max_tokens=9000, tag=f"loc_strings_{vid}", model=config.LLM_MODEL_WRITER or None)
    return {k: str(r.get(k) or v) for k, v in items.items()}


def _time_map(words_en, parts_en, words_es, parts_es):
    """Функция t_en → t_es по предложениям внутри каждой части (если число предложений сошлось), иначе пропорционально по части."""
    def bounds(words, parts_sents):
        idx = 0; out = []
        for sents in parts_sents:
            part = []
            for s in sents:
                n = len(s.split()); part.append((idx, min(idx + n, len(words) - 1))); idx += n
            out.append(part)
        return out
    b_en, b_es = bounds(words_en, parts_en), bounds(words_es, parts_es)
    starts_en = [w["s"] for w in words_en]
    def f(t: float) -> float:
        i = max(0, bisect.bisect_right(starts_en, t) - 1)
        for p, part in enumerate(b_en):
            for k, (a, b) in enumerate(part):
                if a <= i <= b:
                    if len(b_es[p]) == len(part): a2, b2 = b_es[p][k]
                    else:
                        pa, pb = part[0][0], part[-1][1]; qa, qb = b_es[p][0][0], b_es[p][-1][1]
                        fr = (i - pa) / max(1, pb - pa); a2 = b2 = int(qa + fr * (qb - qa))
                    fr = (i - a) / max(1, b - a)
                    j = min(len(words_es) - 1, int(round(a2 + fr * (b2 - a2))))
                    within = t - words_en[i]["s"]
                    return round(words_es[j]["s"] + min(within, 0.6), 3)
        return round(t * (words_es[-1]["e"] / words_en[-1]["e"]), 3)
    return f


def build(vid: str, lang: str = "es", render: bool = True, cartoon: bool = False) -> str:
    from . import assets as A, pauses as P, sound, render as R
    from .qc import tech_check
    L = LANGS[lang]; v = db.get(vid); d = db.video_dir(vid); vid2 = f"{vid}__{lang}"; d2 = _dir(vid2)
    d2.mkdir(parents=True, exist_ok=True)
    for sub in ("archive", "images", "stock", "music"): _link(d / sub, d2 / sub)
    (d2 / "publish").mkdir(exist_ok=True); (d2 / "sound").mkdir(exist_ok=True)
    s = v["payload"]["script"]; parts_en = s.get("parts") or [s["script"]]
    tl = json.loads(config.read(d / "timeline.json")); words_en = json.loads(config.read(d / "words.json"))
    # 1. перевод по предложениям
    sents_en = [_sentences(p) for p in parts_en]
    cache = d2 / "translation.json"
    if cache.exists(): sents_es = json.loads(config.read(cache))
    else:
        sents_es = _translate_parts(parts_en, lang, vid); config.write(cache, json.dumps(sents_es, ensure_ascii=False, indent=1))
    parts_es = [" ".join(x) for x in sents_es]; script_es = "\n\n".join(parts_es)
    # 2. озвучка + паузы (голос второго канала)
    old_voice = os.environ.get("ELEVENLABS_VOICE_ID"); os.environ["ELEVENLABS_VOICE_ID"] = config.ES_VOICE_ID or old_voice
    try:
        A._voice(A.clean_text(script_es), d2, [A.clean_text(p) for p in parts_es])
        pauses = P.ensure(d2, parts_es)
    finally:
        if old_voice: os.environ["ELEVENLABS_VOICE_ID"] = old_voice
    words_es = json.loads(config.read(d2 / "words.json"))
    fmap = _time_map(words_en, sents_en, words_es, sents_es)
    # 3. таймлайн: времена по карте, подписи — переводом
    tl2 = json.loads(json.dumps(tl)); tl2["channel"] = L["channel"]; tl2["lang"] = lang; tl2["theme"] = "neon"; tl2["subtitles"] = True   # cinético: вшитые субтитры
    tail = float(tl["duration"]) - float(words_en[-1]["e"])
    tl2["duration"] = round(float(words_es[-1]["e"]) + max(1.5, tail), 3)
    tl2["pauses"] = pauses
    pause_at_en = {round(p["at"], 1): p for p in tl.get("pauses") or []}
    pause_by_part = {p["part"]: p for p in pauses}
    strings = {}
    def reg(key, text):
        if text and isinstance(text, str) and re.search(r"[A-Za-z]{3}", text): strings[key] = text
    scenes = tl2["scenes"]
    for i, sc in enumerate(scenes):
        st_en = sc["start"]
        p = pause_at_en.get(round(st_en, 1))
        sc["start"] = 0.0 if i == 0 else (pause_by_part[p["part"]]["at"] if p and p["part"] in pause_by_part else fmap(st_en))
        reg(f"s{i}.caption", sc.get("caption"))
        for k, sl in enumerate(sc.get("slots") or []):
            if sl.get("role") != "portrait": reg(f"s{i}.slot{k}.caption", sl.get("caption"))
        dd = sc.get("data") or {}
        for k, per in enumerate(dd.get("persons") or []): reg(f"s{i}.person{k}.role", per.get("role"))
        if sc["type"] == "quote": reg(f"s{i}.q.text", dd.get("text")); reg(f"s{i}.q.role", dd.get("role"))
        if sc["type"] == "split":
            for side in ("left", "right"): reg(f"s{i}.{side}.label", (dd.get(side) or {}).get("label"))
            reg(f"s{i}.stakes", dd.get("stakes"))
        if sc["type"] == "map":
            reg(f"s{i}.map.title", dd.get("title"))
            for k, pt in enumerate(dd.get("points") or []): reg(f"s{i}.pt{k}.label", pt.get("label"))
        for k in ("title", "subject"): reg(f"s{i}.{k}", dd.get(k))
    for i, sc in enumerate(scenes):
        sc["end"] = scenes[i + 1]["start"] if i + 1 < len(scenes) else tl2["duration"]
        if sc["end"] <= sc["start"] + 0.3 and i + 1 < len(scenes): sc["end"] = sc["start"] + 0.3; scenes[i + 1]["start"] = sc["end"]
    # цифры на экран считаем заново по английской озвучке текущим numbers.flashes (у старых роликов «51» + «4B» вместо «$51.4B»),
    # затем прореживаем и переносим по тайм-карте; унаследованные flash-титры выбрасываем
    from . import numbers as N
    from .story_assets import _pair_and_sources, _thin_flashes
    fresh = _thin_flashes(_pair_and_sources(d, N.flashes(words_en)))
    keep = [o for o in (tl2.get("overlays") or []) if o.get("type") not in ("flash", "pair")]
    tl2["overlays"] = keep + [{**o, "end": round(o["start"] + o.get("seconds", 2.6), 3)} for o in fresh]
    ov2 = []
    for j, o in enumerate(tl2.get("overlays") or []):
        if o["type"] == "chapter":
            p = pause_by_part.get(o.get("n"))
            if not p: continue
            o["start"] = round(p["at"] + 0.4, 3); o["end"] = round(o["start"] + 3.4, 3); o["pause"] = {"at": p["at"], "gap": p["gap"]}
            reg(f"o{j}.text", o.get("text"))
        else:
            dur = o["end"] - o["start"]; o["start"] = fmap(o["start"]); o["end"] = round(o["start"] + dur, 3)
            if o["type"] == "caption": reg(f"o{j}.text", o.get("text"))
            if o["type"] in ("flash", "pair"): reg(f"o{j}.label", o.get("label")); reg(f"o{j}.tagL", o.get("tagL")); reg(f"o{j}.tagR", o.get("tagR"))
        ov2.append(o)
    tl2["overlays"] = ov2   # порядок как при регистрации строк: перевод кладётся по тем же индексам j, сортировка и прореживание — после
    tr = _translate_strings(strings, lang, vid)
    def put(key, obj, field):
        if key in tr: obj[field] = tr[key]
    for i, sc in enumerate(scenes):
        put(f"s{i}.caption", sc, "caption")
        for k, sl in enumerate(sc.get("slots") or []): put(f"s{i}.slot{k}.caption", sl, "caption")
        dd = sc.get("data") or {}
        for k, per in enumerate(dd.get("persons") or []): put(f"s{i}.person{k}.role", per, "role")
        put(f"s{i}.q.text", dd, "text"); put(f"s{i}.q.role", dd, "role"); put(f"s{i}.stakes", dd, "stakes"); put(f"s{i}.map.title", dd, "title")
        for side in ("left", "right"):
            if isinstance(dd.get(side), dict): put(f"s{i}.{side}.label", dd[side], "label")
        for k, pt in enumerate(dd.get("points") or []): put(f"s{i}.pt{k}.label", pt, "label")
        put(f"s{i}.title", dd, "title"); put(f"s{i}.subject", dd, "subject")
    for j, o in enumerate(tl2["overlays"]):
        put(f"o{j}.text", o, "text"); put(f"o{j}.label", o, "label"); put(f"o{j}.tagL", o, "tagL"); put(f"o{j}.tagR", o, "tagR")
    tl2["overlays"] = sorted(tl2["overlays"], key=lambda o: o["start"])
    tl2["shorts"] = [{"start": fmap(x["start"]), "end": fmap(x["end"])} for x in tl.get("shorts") or []]
    # 4. музыка заново под новые главы
    tl2["score"] = None; tl2["music_tracks"] = []; tl2["sfx_chapter"] = None
    try: tl2["score"] = sound.build(vid2, d2, tl2, words_es)
    except Exception as e:   # 13.10: лимит ElevenLabs Music — треки глав английской версии на испанских границах глав
        bounds = [0.0] + [p["at"] for p in pauses] + [tl2["duration"]]
        tl2["music_tracks"] = [{**t, "start": round(bounds[k], 3), "end": round(bounds[k + 1], 3)}
                               for k, t in enumerate(tl.get("music_tracks") or []) if k + 1 < len(bounds)]
        if not tl2["music_tracks"]: raise
        print(f"[localize] партитура не собралась ({str(e)[:100]}) — треки глав: {len(tl2['music_tracks'])}", flush=True)
    config.write(d2 / "timeline.json", json.dumps(tl2, ensure_ascii=False, indent=1))
    # 5. база и обложка
    payload = {"lang": lang, "source_vid": vid, "topic": v["payload"].get("topic"), "brief": v["payload"].get("brief"), "thumbv": v["payload"].get("thumbv"),
               "script": {**s, "parts": parts_es, "script": script_es}, "entities": v["payload"].get("entities")}
    with db.conn() as c:
        c.execute("INSERT OR IGNORE INTO videos VALUES(?,?,?,?,?,?,?,?,?)", (vid2, v["slug"] + "-" + lang, "localized", v["title"], json.dumps(payload, ensure_ascii=False),
                                                                             None, None, datetime.now().isoformat(), datetime.now().isoformat()))
    db.update(vid2, "localized", payload=payload)
    if cartoon:   # 13.10: титры в бумажной теме (dossier) под рисунок, без вшитых субтитров — как у Built On You
        tl2["theme"] = "dossier_es"; tl2["subtitles"] = False; tl2["film"] = None;   # и без «старой плёнки» (царапины, мерцание) поверх рисунка
        config.write(d2 / "timeline.json", json.dumps(tl2, ensure_ascii=False, indent=1))
    if cartoon:   # 12.10: обложка и комплект мультфильма — в cartoon_es (шаблон, утверждённый владельцем)
        from . import cartoon_es; cartoon_es.thumb(vid, vid2); cartoon_es.kit(vid, vid2, tl2)
    else:
        try: thumb_face(vid, vid2, lang)   # обложка второго канала: лицо + образ компании + обещание (cinético)
        except Exception as e:
            print(f"[localize] обложка cinético не собралась ({str(e)[:120]}) — беру английскую", flush=True)
            for f in ("thumb_a.png", "thumb_2560.png", "thumb_a.keep"):
                if (d / f).exists(): shutil.copy(d / f, d2 / f)
            if (d / "publish" / "thumbnail_2560.jpg").exists(): shutil.copy(d / "publish" / "thumbnail_2560.jpg", d2 / "publish" / "thumbnail_2560.jpg")
        # 6. комплект публикации
        kit(vid, vid2, lang, tl2)
    print(f"[localize] {vid2}: {len(scenes)} сцен, {tl2['duration']/60:.1f} мин (англ. {tl['duration']/60:.1f})", flush=True)
    if not render: return vid2
    # 7. рендер + мастеринг + техпроверка
    base = {"timeline": tl2, "words": words_es}
    if config.STILLCHECK:   # кадры-пробы до рендера (владелец 22.09)
        from . import stillcheck
        chk = stillcheck.run(d2, tl2, words_es, lang=lang)
        if not chk["ok"]: raise RuntimeError("stillcheck: " + "; ".join(i["what"] for i in chk["issues"] if i["severity"] == "block")[:600])
    scale = [f"--scale={config.RENDER_HEIGHT / 1080:g}"] if config.RENDER_HEIGHT != 1080 else []
    tmp = config.RENDER_TMP; tmp.mkdir(parents=True, exist_ok=True); main_out = tmp / f"{vid2}.mp4"
    R._rx("render", "Main", main_out, base, d2, scale)
    loud = tmp / f"{vid2}_master.mp4"; m = sound.master(main_out, loud); loud.replace(main_out)
    shutil.move(str(main_out), str(d2 / "final.mp4"))
    tech = tech_check(d2 / "final.mp4", tl2)
    R.contact_sheet(d2 / "final.mp4", tl2, d2 / "contact.jpg")   # render.contact_sheet берёт весь таймлайн, не список сцен
    db.update(vid2, "localized", payload={"tech": tech})
    print(f"[localize] готово: {d2 / 'final.mp4'} | мастеринг {m['input_i']:.1f} → −14 LUFS | техпроверка: {'; '.join(tech) or 'чисто'}", flush=True)
    return vid2


def keep_largest(png) -> None:
    """В вырезке оставить только самую большую связную фигуру: дорисовка иногда добавляет второго человека или обломок (McDonald's 23.09)."""
    import numpy as np
    from PIL import Image
    from scipy import ndimage
    im = Image.open(png).convert("RGBA"); a = np.array(im.split()[3]); lab, n = ndimage.label(a > 10)
    if n <= 1: return
    sizes = ndimage.sum(np.ones_like(a), lab, range(1, n + 1)); keep = int(np.argmax(sizes)) + 1
    a[lab != keep] = 0; im.putalpha(Image.fromarray(a)); bb = im.split()[3].getbbox(); im.crop(bb).save(png)
    print(f"[thumb] вырезка: убрано лишних фрагментов {n - 1}", flush=True)

def complete_cut(src, out, pad: int = 340, min_rows: float = 0.25) -> bool:
    """Вырезка героя обрезана краем фото (альфа упирается в левый/правый край на ≥25% строк) → дорисовать плечо FLUX Fill узкой маской
    только на этих строках (широкая маска дорисовывала второго человека, Netflix es 23.09), полосу вклеить в полноразмерный холст, вырезать заново."""
    import numpy as np, fal_client
    from PIL import Image, ImageFilter
    from .assets import cutout, _get
    im = Image.open(src).convert("RGBA"); a = np.array(im.split()[3]) > 10; H, W = a.shape
    side = "right" if a[:, -1].sum() >= min_rows * H else "left" if a[:, 0].sum() >= min_rows * H else None
    if not side: return False
    if side == "left": im = im.transpose(Image.FLIP_LEFT_RIGHT); a = a[:, ::-1]
    rows = np.where(a[:, -1])[0]; y0 = max(0, int(rows.min()) - 40)
    canvas = Image.new("RGB", (W + pad, H), (58, 56, 54)); canvas.paste(im, (0, 0), im)
    mask = Image.new("L", (W + pad, H), 0); mask.paste(255, (W - 10, y0, W + pad, H))
    tmp = out.parent / (out.stem + "_op"); tmp.mkdir(exist_ok=True); sp, mp = tmp / "src.png", tmp / "mask.png"; canvas.save(sp); mask.save(mp)
    prompt = ("photo of a person, seated or standing; the picture continues to the right with only their own shoulder and upper arm in the same clothes, "
              "arm resting down, then empty plain dark gray background; nobody else in the frame, no second person, no objects, no text, "
              "same lighting, photorealistic, seamless")
    r = fal_client.subscribe("fal-ai/flux-pro/v1/fill", arguments={"prompt": prompt, "image_url": fal_client.upload_file(str(sp)),
                                                                    "mask_url": fal_client.upload_file(str(mp)), "output_format": "png", "safety_tolerance": "5"})
    gen = Image.open(io.BytesIO(_get(r["images"][0]["url"], timeout=180))).convert("RGB")
    if gen.size != canvas.size: gen = gen.resize(canvas.size, Image.LANCZOS)
    full = Image.composite(gen, canvas, mask.filter(ImageFilter.GaussianBlur(6)))
    if side == "left": full = full.transpose(Image.FLIP_LEFT_RIGHT)
    fp = tmp / "full.png"; full.save(fp); cutout(fp, out, portrait=True, trim=True); keep_largest(out)
    print(f"[thumb] вырезка обрезана {side}: плечо дорисовано → {out.name}", flush=True)
    return True

def thumb_face(vid: str, vid2: str, lang: str = "es"):
    """Обложка cinético (владелец 22.09): фон — образ компании (правая панель английской обложки), слева вырезанное лицо героя,
    справа столбиком логотип · 2–3 слова по-испански · цифра. Слова подбирает модель из обещания названия: глагол-событие + сумма."""
    import subprocess as sp
    from PIL import Image
    v = db.get(vid); d = db.video_dir(vid); d2 = _dir(vid2); tv = v["payload"].get("thumbv") or {}; b = v["payload"].get("brief") or {}
    if not (tv.get("bg2") and tv.get("cut")): raise ValueError("у английского ролика нет обложки конвейера (thumbv)")
    q = (f"Обложка YouTube для испаноязычного канала. Обещание ролика: {b.get('title_promise') or v['title']}.\n"
         f"Стартовая цифра истории (должна быть во второй строке): {tv.get('hook')}. Итоговая цифра {tv.get('hook2')} уже стоит на обложке отдельно — в строках её НЕ повторять.\n"
         "Дай две строки на нейтральном латиноамериканском испанском: строка 1 — глагол-событие или короткая фраза (RECHAZADO, VENDIERON, LO ECHARON, "
         f"DIJO QUE NO), строка 2 — уточнение со стартовой цифрой (POR {tv.get('hook')}). Каждая строка не длиннее 11 знаков, ЗАГЛАВНЫМИ, без точек. "
         "Верни JSON {\"line1\": \"...\", \"line2\": \"...\"}")
    r = llm.ask_json(q, max_tokens=300, tag=f"thumb_es_{vid2}", model=config.LLM_MODEL_FACTCHECK or None)
    l1, l2 = str(r.get("line1") or "").strip().upper()[:12], str(r.get("line2") or "").strip().upper()[:12]
    if tv.get("hook2") and str(tv["hook2"]).upper() in l2: l2 = f"POR {tv.get('hook')}"[:12]   # модель повторила итоговую цифру — ставим стартовую
    cut_rel = tv["cut"]
    try:
        (d2 / "archive").mkdir(exist_ok=True)
        if complete_cut(d / tv["cut"], d2 / "archive" / "cut_thumbv_full.png"): cut_rel = "archive/cut_thumbv_full.png"
    except Exception as e: print(f"[thumb] дорисовка не удалась, беру вырезку как есть: {str(e)[:120]}", flush=True)
    props = {"variant": "bold", "kind": "face", "bg": tv["bg2"], "cut": cut_rel, "cutH": 640, "cutX": -20, "markSize": 52, "text1": f"{l1}|{l2}", "hook2": tv.get("hook2")}
    for k in ("mark", "logo", "brandWord"):
        if tv.get(k): props[k] = tv[k]
    work = d2 / "thumbv"; work.mkdir(exist_ok=True); pf = work / "props_a.json"; config.write(pf, json.dumps(props, ensure_ascii=False))
    tmp = config.RENDER_TMP / "remotion"; tmp.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "THUMB_SCALE": "2", "TEMP": str(tmp), "TMP": str(tmp)}
    before = set(tmp.glob("remotion-webpack-bundle-*"))
    try: rr = sp.run([shutil.which("node") or "node", "scripts/thumbs.mjs", str(d2), str(pf), str(work), str(pf)], cwd=config.REMOTION, capture_output=True, text=True, errors="replace", env=env, timeout=900)
    finally:
        for p in set(tmp.glob("remotion-webpack-bundle-*")) - before: shutil.rmtree(p, ignore_errors=True)
    big = work / "thumb_a.png"
    if rr.returncode or not big.exists(): raise RuntimeError("рендер обложки: " + (rr.stderr or rr.stdout or "")[-400:])
    im = Image.open(big).convert("RGB")
    if im.size != (2560, 1440): im = im.resize((2560, 1440), Image.LANCZOS)
    im.save(d2 / "thumb_2560.png"); im.resize((1280, 720), Image.LANCZOS).save(d2 / "thumb_a.png"); (d2 / "thumb_a.keep").write_text("thumbv face es", encoding="utf-8")
    (d2 / "publish").mkdir(exist_ok=True)
    for qq in (92, 86, 80):
        im.save(d2 / "publish" / "thumbnail_2560.jpg", "JPEG", quality=qq, optimize=True)
        if (d2 / "publish" / "thumbnail_2560.jpg").stat().st_size <= 2 * 1024 * 1024: break
    db.update(vid2, payload={"thumb_es": {**props, "lines": [l1, l2]}})
    print(f"[localize] обложка cinético: {l1} / {l2} · {tv.get('hook2')}", flush=True)


def kit(vid: str, vid2: str, lang: str, tl2: dict):
    """Название, описание с главами по новым таймкодам, теги, закреп — по-испански; поля Studio — те же."""
    from .publish import _ascii, _ts, STUDIO
    L = LANGS[lang]; d = db.video_dir(vid); d2 = _dir(vid2)
    title = config.read(d / "publish" / "title.txt").strip(); desc = config.read(d / "publish" / "description.txt").strip()
    tags = config.read(d / "publish" / "tags.txt").strip(); pinned = config.read(d / "publish" / "pinned_comment.txt").strip()
    hook = desc.split("\n\nCHAPTERS")[0]
    q = (f"Переведи поля YouTube документального ролика на {L['name']} для канала «{L['channel']}». Имена, названия компаний, суммы и годы — без изменений. "
         "title — до 95 знаков, естественный испанский заголовок с тем же конкретным обещанием; description — те же абзацы; tags — 15–18 тегов "
         "(испанские + английские названия компаний и людей); pinned — первый абзац закрепа (вопрос зрителям в конце); hashtags — 3.\n\n"
         + json.dumps({"title": title, "description": hook, "tags": tags, "pinned": pinned.split("\n\n")[0]}, ensure_ascii=False) +
         '\n\nВерни JSON: {"title": "...", "description": "...", "tags": ["..."], "pinned": "...", "hashtags": ["#..."]}')
    r = llm.ask_json(q, heavy=True, max_tokens=4000, tag=f"loc_kit_{vid2}", model=config.LLM_MODEL_WRITER or None)
    names = {o.get("n"): o.get("text") for o in tl2.get("overlays") or [] if o.get("type") == "chapter"}
    first = next((o.get("text") for o in tl2.get("overlays") or [] if o.get("type") == "chapter" and o.get("n") == 1), None)
    chapters = ["0:00 " + _ascii(first or "Inicio")]
    for p in tl2.get("pauses") or []:
        chapters.append(f"{_ts(p['at'] + 0.4)} {_ascii(names.get(p['part']) or p.get('name') or 'Parte ' + str(p['part']))}")
    text = "\n\n".join([_ascii(r.get("description") or hook).strip(), L["chapters"] + "\n" + "\n".join(chapters), L["subscribe"],
                        " ".join((r.get("hashtags") or ["#Documental"])[:3])])
    t2 = _ascii(r.get("title") or title)[:100]
    tg = [_ascii(x) for x in (r.get("tags") or [])][:20]
    for x in (L["channel"], "documental", "historia empresarial"):
        if x not in tg: tg.append(x)
    while len(", ".join(tg)) > 480: tg.pop(-4)
    out = d2 / "publish"; out.mkdir(exist_ok=True)
    config.write(out / "title.txt", t2); config.write(out / "description.txt", text.replace("<", "(").replace(">", ")"))
    config.write(out / "tags.txt", ", ".join(tg))
    config.write(out / "pinned_comment.txt", (_ascii(r.get("pinned") or "") + "\n\n" + "\n\n".join(pinned.split("\n\n")[1:])).strip())
    config.write(out / "studio.txt", STUDIO.replace("English (United States)", "Spanish (Latin America)"))
    config.write(d2 / "meta.json", json.dumps({"titles": [t2], "tags": tg, "description": text}, ensure_ascii=False, indent=2))
    print(f"[localize] комплект: {t2} | глав {len(chapters)} | тегов {len(tg)}", flush=True)


def _token(lang: str) -> Path:
    return config.DATA / LANGS[lang]["token"]


def auth(lang: str = "es"):
    from google_auth_oauthlib.flow import InstalledAppFlow
    from .upload import SCOPES
    secret = os.getenv("YOUTUBE_CLIENT_SECRET_FILE", "data/youtube_client_secret.json")
    creds = InstalledAppFlow.from_client_secrets_file(secret, SCOPES).run_local_server(port=0)
    config.write(_token(lang), creds.to_json()); print("Токен второго канала сохранён:", _token(lang))


def _yt(lang: str):
    from googleapiclient.discovery import build as gbuild
    from google.oauth2.credentials import Credentials
    from .upload import SCOPES
    t = _token(lang)
    if not t.exists(): raise RuntimeError(f"нет {t.name} — запусти `auth-{lang}` и войди в аккаунт второго канала")
    from .upload import gbuild as _gb
    return _gb("youtube", "v3", Credentials.from_authorized_user_file(str(t), SCOPES))


def _next_slot(lang: str) -> datetime:
    from .upload import ET
    taken = {r["publish_at"] for r in db.conn().execute("SELECT publish_at FROM videos WHERE publish_at IS NOT NULL AND id LIKE ?", (f"%__{lang}",))}
    now = datetime.now(timezone.utc)
    t = now.astimezone(ET).replace(hour=config.PUBLISH_HOUR_ET, minute=0, second=0, microsecond=0)
    while t < now + timedelta(hours=6) or t.astimezone(timezone.utc).isoformat() in taken: t += timedelta(days=1)
    return t.astimezone(timezone.utc)


def upload(vid2: str):
    """Загрузка на второй канал: приватно в ближайший свободный вечерний слот этого канала, обложка, язык — испанский."""
    from googleapiclient.http import MediaFileUpload
    from .upload import _once
    v = db.get(vid2); lang = v["payload"].get("lang") or "es"; L = LANGS[lang]; d = _dir(vid2)
    f = d / "final.mp4"
    if not f.exists() or f.stat().st_size < 20 * 1024 * 1024: raise FileNotFoundError("нет final.mp4 локальной версии")
    title = config.read(d / "publish" / "title.txt").strip(); desc = config.read(d / "publish" / "description.txt").strip()
    tags = [t.strip() for t in config.read(d / "publish" / "tags.txt").split(",") if t.strip()]
    y = _yt(lang); done = dict(v["payload"].get("uploads") or {})
    slot = datetime.fromisoformat(v["publish_at"]) if v["publish_at"] else _next_slot(lang)
    if slot < datetime.now(timezone.utc) + timedelta(minutes=10):   # слот из БД уже прошёл (23.09: «сегодня в 02:00», загрузка опоздала) — ближайшее возможное время, а не ошибка API
        slot = (datetime.now(timezone.utc) + timedelta(minutes=15)).replace(second=0, microsecond=0); print(f"[upload-{lang}] слот прошёл, ставлю {slot.isoformat()}", flush=True)
    body = {"snippet": {"title": title[:100], "description": desc, "tags": tags, "categoryId": "28", "defaultLanguage": L["yt_lang"], "defaultAudioLanguage": L["yt_lang"]},
            "status": {"privacyStatus": "private", "publishAt": slot.isoformat(), "selfDeclaredMadeForKids": False, "embeddable": True, "publicStatsViewable": True}}
    yid = _once(y, "final.mp4", done, body, f)
    db.update(vid2, "localized_uploaded", youtube_id=yid, publish_at=slot.isoformat(), payload={"uploads": done})
    thumb = d / "publish" / "thumbnail_2560.jpg"
    if thumb.exists():
        try: y.thumbnails().set(videoId=yid, media_body=MediaFileUpload(str(thumb))).execute()
        except Exception as e: print("[localize] обложка:", str(e)[:120])
    print(f"[localize] загружен на канал {L['channel']}: https://www.youtube.com/watch?v={yid} — выход {slot.astimezone().strftime('%d.%m %H:%M')} местного", flush=True)
    _cleanup(d)
    return yid


def brand(lang: str = "es"):
    """Аватар и шапка второго канала (Stills Avatar/Banner из Brand.tsx) → data/board/<lang>/."""
    from . import render as R
    L = LANGS[lang]; out = config.DATA / "board" / lang; out.mkdir(parents=True, exist_ok=True)
    props = {"name": L["channel"], "tagline": L["tagline"]}
    for comp in ("AvatarES", "BannerES", "WatermarkES"):   # направление «Neón» (BrandES.tsx), выбор владельца 22.09
        R._rx("still", comp, out / f"{comp.lower()}.png", props, out)
        print("[localize] бренд:", out / f"{comp.lower()}.png", flush=True)
    return out
