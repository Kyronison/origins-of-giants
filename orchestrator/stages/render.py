"""Remotion: длинное видео, Shorts, превью. Папка видео отдаётся Remotion как public dir → staticFile().
Перед рендером — защита от рассинхрона пауз (timeline.pauses ↔ pauses.json) и проверка, что все файлы из timeline на месте."""
import json, re, shutil, subprocess
from pathlib import Path
from .. import db, config, series

RENDER_FREE_GB = float(__import__("os").getenv("RENDER_FREE_GB", 15))   # сколько места нужно на диске рендера

def _need_space(path, gb: float = None):
    """Рендер 33-минутного ролика пишет ~5 ГБ pre-encode и ~5 ГБ результата. 24.09 Costco упал на 97 % с «write EOF»,
    когда на E: осталось 11.8 ГБ — час работы впустую. Проверяем ДО запуска и говорим прямо, сколько не хватает."""
    import shutil as _sh
    need = RENDER_FREE_GB if gb is None else gb
    free = _sh.disk_usage(str(path)).free / 2**30
    if free < need:
        raise RuntimeError(f"на диске рендера свободно {free:.1f} ГБ, нужно {need:.0f} — рендер не начинаю. "
                           f"Убери старые копии из {path} (файлы *_prev.mp4 уже опубликованных роликов и папку remotion)")
    return free

def _rx(cmd: str, composition: str, out, props: dict, d, extra=()):
    from ..public_media import public_view
    # The stage holds .execution.lock on Windows. Never copy that lock, old
    # renders or unreferenced internal files into the browser's public tree.
    with public_view(d, props, config.RENDER_TMP) as public:
        return _rx_public(cmd, composition, out, props, d, extra, public)

def _rx_public(cmd, composition, out, props, d, extra, public):
    if cmd == "render":
        free = _need_space(config.RENDER_TMP, None if composition == "Main" else 6)   # 27.09: шортсу 15 ГБ не нужно — Safelite встал после готового Main
        print(f"[render] на диске свободно {free:.0f} ГБ", flush=True)
    pf = d / f"props_{composition}.json"          # --props файлом: JSON не влезает в командную строку Windows
    config.write(pf, json.dumps(props, ensure_ascii=False))
    crf = [f"--crf={config.RENDER_CRF}"] if cmd == "render" else []   # зерно плёнки съедает битрейт при crf по умолчанию
    speed = []   # скорость: параллельные вкладки Chrome (по умолчанию Remotion берёт 4 из 24 потоков) и GPU через ANGLE для фильтров плёнки
    if cmd == "render":
        if config.RENDER_CONCURRENCY: speed.append(f"--concurrency={config.RENDER_CONCURRENCY}")
        if config.RENDER_GL: speed.append(f"--gl={config.RENDER_GL}")
        speed.append(f"--timeout={config.RENDER_FRAME_TIMEOUT}")   # смена сети (VPN) во время рендера: fetch клипа повторяется, 30 с по умолчанию не хватало
    env = None
    if config.RENDER_TMP != config.DATA / "render_tmp":   # временная папка Remotion — туда же, куда промежуточный рендер (не на системный диск)
        import os
        t = config.RENDER_TMP / "remotion"; t.mkdir(parents=True, exist_ok=True); env = {**os.environ, "TEMP": str(t), "TMP": str(t)}
    import os, tempfile
    tdir = Path((env or os.environ).get("TEMP") or tempfile.gettempdir())
    before = set(tdir.glob("remotion-webpack-bundle-*"))
    try:
        try:
            subprocess.run([config.npx(), "remotion", cmd, "src/index.ts", composition, str(out),
                            "--props", str(pf), "--public-dir", str(public), *crf, *speed, *extra], cwd=config.REMOTION, check=True, env=env)
        except subprocess.CalledProcessError:
            # 27.09 Safelite: на 27 % Chrome «ran out of memory» (ERR_INSUFFICIENT_RESOURCES) при 12 вкладках — один повтор с половиной
            conc = [a for a in speed if a.startswith("--concurrency=")]
            if cmd != "render" or not conc: raise
            half = max(2, int(conc[0].split("=")[1]) // 2)
            print(f"[render] {composition} упал — повтор с --concurrency={half}", flush=True)
            speed = [a for a in speed if not a.startswith("--concurrency=")] + [f"--concurrency={half}"]
            subprocess.run([config.npx(), "remotion", cmd, "src/index.ts", composition, str(out),
                            "--props", str(pf), "--public-dir", str(public), *crf, *speed, *extra], cwd=config.REMOTION, check=True, env=env)
    finally:   # CLI оставляет бандл с копией папки ролика (~1.3 ГБ) на каждый вызов — 18.09 диск C: забился до нуля; убираем только свой (23.09: параллельные рендеры)
        for p in set(tdir.glob("remotion-webpack-bundle-*")) - before:
            if p.resolve().parent != tdir.resolve(): raise RuntimeError("Unsafe bundle cleanup target")
            shutil.rmtree(p, ignore_errors=True)

def contact_sheet(mp4, tl: dict, out, step: float = 3.0, cols: int = 6):
    """Кадр каждые step секунд из готового рендера с подписью «секунда · сцена · титры» — лист для просмотра глазами.
    ffmpeg Remotion без фильтра fps — по одному кадру через -ss."""
    import io
    from PIL import Image, ImageDraw
    W, H, pad = 480, 270, 6
    tiles = []
    t = 0.0
    while t < float(tl["duration"]) - 0.2:
        r = subprocess.run([config.ffmpeg(), "-v", "error", "-ss", f"{t:.3f}", "-i", str(mp4), "-frames:v", "1", "-vf", f"scale={W}:-1",
                            "-f", "image2pipe", "-vcodec", "png", "-"], capture_output=True)
        if r.stdout:
            im = Image.open(io.BytesIO(r.stdout)).convert("RGB").resize((W, H)); dr = ImageDraw.Draw(im)
            sc = next((f"{s['id']} {s['type']}" for s in tl["scenes"] if s["start"] <= t < s["end"]), "")
            ov = ",".join(o["type"] for o in tl.get("overlays") or [] if o["start"] <= t < o["end"])
            dr.rectangle([0, 0, W, 18], fill=(0, 0, 0)); dr.text((4, 3), f"{t:.1f}s {sc} {ov}", fill="white"); tiles.append(im)
        t += step
    rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * W + (cols + 1) * pad, rows * (H + pad) + pad), "white")
    for k, im in enumerate(tiles): sheet.paste(im, (pad + (k % cols) * (W + pad), pad + (k // cols) * (H + pad)))
    sheet.save(out, "JPEG", quality=85)
    return out

STOCK_CREDIT = re.compile(r"stock\.adobe|adobestock|shutterstock|gettyimages|alamy|dreamstime|istock|depositphotos|123rf|vecteezy|freepik", re.I)

def _portrait_guard(d, tl: dict):
    from . import story_assets as _SA
    _SA.dedupe_portraits(tl.get("scenes", []))   # одно фото под двумя именами — перед рендером (McDonald's 22.09)
    """Чужое лицо под именем человека — самая дорогая ошибка канала: она видна каждому и подрывает доверие ко всему ролику.
    Google 20.09: под карточкой «Craig Silverstein» стояло фото Брина, и в данных прямо было написано «Sergey Brin portrait».
    Проверка бесплатная: сверяем имя человека со всем, что известно про выбранный снимок, и с именами других людей ролика."""
    names = set()
    ep = d / "entities.json"
    if ep.exists():
        try: names = {str(c.get("name") or "").strip() for c in (json.loads(config.read(ep)).get("cast") or []) if c.get("name")}
        except Exception: names = set()
    for sc in tl["scenes"]:
        for sl in (sc.get("slots") or []):
            if sl.get("role") != "portrait" or not sl.get("person"): continue
            names.add(str(sl["person"]).strip())
    from . import story_assets, preflight
    try:   # есть ли на портрете лицо и тот ли это человек — до рендера, иначе однофамилец уедет в готовый ролик
        if preflight.verify_portraits(d, tl, d.name): config.write(d / "timeline.json", json.dumps(tl, ensure_ascii=False))
    except Exception as e:
        # Any unfinished check blocks rendering, including unexpected parsing or
        # media errors. Matching one exception phrase left other failures open.
        raise RuntimeError("[render] проверка портретов не завершена: " + str(e)[:160]) from e
    if story_assets.fill_missing_portraits(tl["scenes"]) + story_assets.reindex_people(tl["scenes"]) + story_assets.downgrade_faceless(tl["scenes"]):   # сперва чиним, потом ругаемся
        config.write(d / "timeline.json", json.dumps(tl, ensure_ascii=False))
    wrong = []
    # 1. карточка берёт имя из data.persons, а снимок — из слота по номеру: если поля разошлись, под именем стоит чужой человек
    for sc in tl["scenes"]:
        if sc.get("type") not in ("people", "quote"): continue
        slots = sc.get("slots") or []
        for p in (sc.get("data") or {}).get("persons") or []:
            i, who = p.get("portrait"), str(p.get("name") or "").strip()
            if not isinstance(i, int) or i >= len(slots) or not who: continue
            sl = slots[i]
            got = str(sl.get("person") or "").strip()
            if got and got != who and (sl.get("src") or sl.get("image")):
                wrong.append(f"{sc['id']}: карточка «{who}», а снимок из слота {i} — «{got}»")
                sl["src"] = sl["image"] = None
    # 2. то же по описанию источника: снимок другого человека, даже если поле person совпало
    for sc in tl["scenes"]:
        for sl in (sc.get("slots") or []):
            who = str(sl.get("person") or "").strip()
            if sl.get("role") != "portrait" or not who or not (sl.get("src") or sl.get("image")): continue
            # смотрим ТОЛЬКО то, что сказал источник (почему кадр выбран и как называется ролик), а не нашу подпись:
            # подпись мы ставим сами по имени человека, и она замаскировала бы подмену
            low = " ".join(str(x or "") for x in ((sl.get("archive") or {}).get("why"), (sl.get("archive") or {}).get("title"),
                                                  sl.get("prompt") if sl.get("kind") != "archive" else "")).lower()
            for other in names:
                if other == who or not other: continue
                sur = other.split()[-1].lower()
                if len(sur) < 4: continue
                if sur in low and who.split()[-1].lower() not in low:
                    wrong.append(f"{sc['id']}: под именем «{who}» снимок, описанный как «{other}»")
                    sl["src"] = sl["image"] = None
                    break
    if wrong:
        config.write(d / "timeline.json", json.dumps(tl, ensure_ascii=False))
        raise RuntimeError("[render] чужие лица под именами: " + "; ".join(wrong[:6]) +
                           f" — слоты очищены, прогони `stage preflight {d.name}` (портреты переберутся) и рендерь снова")

def guard(d, tl: dict, words: list[dict]):
    """Отказ рендерить рассинхрон: паузы в timeline ≠ pauses.json или таймлайн короче озвучки (до 24 с расхождения).
    Плюс дешёвые проверки, которые 20.09 сработали уже ПОСЛЕ рендера и стоили полной пересборки (владелец: «без переделок»):
    обрезанные и слишком длинные подписи чиним на месте, кадр со стоковым кредитом снимаем — рендер идёт уже чистым."""
    from . import pauses, story_assets
    pj = pauses.load(d)
    if len(tl.get("pauses") or []) != len(pj):
        raise RuntimeError(f"[render] timeline.pauses ({len(tl.get('pauses') or [])}) ≠ pauses.json ({len(pj)}) — запусти retime <id>")
    if words and tl["duration"] < words[-1]["e"]:
        raise RuntimeError(f"[render] timeline.duration {tl['duration']:.1f} < конец озвучки {words[-1]['e']:.1f} — запусти retime <id>")
    _portrait_guard(d, tl)
    fixed, stock = 0, []
    for sc in tl["scenes"]:
        for sl in (sc.get("slots") or [sc]):
            c = str(sl.get("caption") or "")
            if c:
                new = re.sub(r"[\s,;:~\-]+$", "", c)
                if len(new) > 56:   # длинную режем по слову, а не посреди слова — обрубок в кадре и есть брак
                    new = new[:56].rsplit(" ", 1)[0].rstrip(" ,;:-")
                if new != c: sl["caption"] = new; fixed += 1
            if STOCK_CREDIT.search(str(sl.get("credit") or "") + " " + str(sl.get("src") or sl.get("image") or "")):
                stock.append(sc["id"]); sl["src"] = sl["image"] = None
    if fixed: print(f"[render] подписей поправлено до рендера: {fixed}", flush=True)
    if stock:
        config.write(d / "timeline.json", json.dumps(tl, ensure_ascii=False))
        raise RuntimeError(f"[render] кадры со стоковым водяным знаком: {', '.join(stock[:6])} — слоты очищены, "
                           f"прогони `stage preflight {d.name}` и рендерь снова")
    if fixed: config.write(d / "timeline.json", json.dumps(tl, ensure_ascii=False))
    story_assets._check_files(d, tl)

def _public_for(d, spec: dict):
    """Временный public dir только с файлами, на которые ссылается спецификация шортса. Remotion копирует public dir целиком,
    а в папке ролика лежит сданный final.mp4 на несколько ГБ — его нельзя ни копировать, ни (правило владельца 19.09) уносить."""
    import re as _re, shutil
    pub = config.RENDER_TMP / f"pub_short_{d.name[:28]}"
    shutil.rmtree(pub, ignore_errors=True); pub.mkdir(parents=True, exist_ok=True)
    seen = set()
    def walk(x):
        if isinstance(x, dict): [walk(v) for v in x.values()]
        elif isinstance(x, list): [walk(v) for v in x]
        elif isinstance(x, str) and _re.search(r"\.[a-z0-9]{2,4}$", x) and x not in seen:
            seen.add(x); src = d / x
            if src.exists(): (pub / x).parent.mkdir(parents=True, exist_ok=True); shutil.copy2(src, pub / x)
    walk(spec)
    return pub

def hook_shorts(d, extra=(), only: list[int] | None = None) -> int:
    """Рендер шортсов ShortHook по shorts/sN/short.json → shorts/short_N.mp4 (only — только эти N).
    Public dir — временная папка с нужными файлами (_public_for): сданный final.mp4 не копируется и не переносится."""
    specs = sorted((d / "shorts").glob("s*/short.json"), key=lambda p: int(p.parent.name[1:]))
    done = 0
    for sp in specs:
        n = int(sp.parent.name[1:])
        if only and n not in only: continue
        spec = json.loads(config.read(sp))
        if spec.get("template"): continue   # моушен-шортс: рендерит stages/motion_shorts.py
        _rx("render", "ShortHook", d / "shorts" / f"short_{n}.mp4", {"spec": spec}, _public_for(d, spec), extra); done += 1
    return done

def shorts(vid: str, which: list[int] | None = None, start: int = 1):
    """Собрать и отрендерить шортсы для готового story-видео (команда `shorts <id> [номера новостей]`)."""
    from . import shorts as S
    d = db.video_dir(vid)
    specs = S.build(vid, which, start=start)
    n = hook_shorts(d, only=list(range(start, start + len(specs))) if start > 1 else None)   # final.mp4 не трогаем: у рендера свой public dir
    print(f"[render] шортсов: {n} → {d / 'shorts'}")

def run(vid: str):
    if ((db.get(vid)["payload"].get("topic") or {}).get("style")) == "cartoon":   # 12.10: испанский мультфильм — английский рендер не нужен
        from . import cartoon_es; return cartoon_es.run(vid)
    d = db.video_dir(vid)
    tl = json.loads(config.read(d / "timeline.json")); words = json.loads(config.read(d / "words.json"))
    if tl.get("format") == "story": guard(d, tl, words)
    _topic = (db.get(vid)["payload"].get("topic") or {})
    if tl.get("format") == "story" and config.THUMB_STYLE == "object9" and not (d / "thumb9" / "thumb_main.png").exists():
        # 14.10 владелец: весь канал в стиле 9 «вещь крупно» (название бренда в плашке, две строки, годы) + 2 варианта для A/B-теста
        from . import thumb9
        from .. import telegram as _tg
        _r9 = thumb9.make(vid)
        try: _tg.send(f"Превью `{vid}` (стиль 9) и варианты для A/B-теста.", file=_r9["files"].get("main"))
        except Exception: pass
    elif tl.get("format") == "story" and config.THUMB_STYLE == "trio" and not (d / "thumb_trio" / "plan.json").exists():
        # 19.10 владелец: превью в стилях 3 (тревел-постер), 9 (комикс), 10 (график) вместо «Плаката» — одно основным, два в A/B
        from . import thumb_trio
        from .. import telegram as _tg
        _rt = thumb_trio.make(vid)
        try: _tg.send(f"Превью `{vid}`: основное — стиль {_rt['main']}, два других для A/B-теста.", file=_rt["sheet"])
        except Exception: pass
    elif tl.get("format") == "story" and config.THUMB_STYLE not in ("object9", "trio") and config.THUMBV_AUTO and config.THUMB_REC and series.of(_topic):
        # 29.09 STRATEGY.md: обложка по макету серии — ДО рендера и один раз. Не собралась — ролик останавливается здесь,
        # а не получает старый «сплит»; час рендера при этом не потрачен.
        from . import thumbrec
        from .. import telegram as _tg
        _r = thumbrec.make(vid)
        if _r.get("fresh"):
            pl = _r["plan"]
            _tg.send(f"Обложка `{vid}`, макет «{pl['template']}»: «{pl['text']}».\n{pl['why']}", file=_r["sheet"])
    if tl.get("format") == "story" and config.RESTORE_ARCHIVE:   # старые клипы и мелкие фото — апскейл до рендера (stages/restore.py)
        from . import restore
        try: restore.run(vid, d, tl)
        except Exception as e: print(f"[render] реставрация пропущена: {str(e)[:120]}")
    if tl.get("format") == "story" and config.SOUND_SCORE and not tl.get("score"):
        from . import sound
        try:
            tl["score"] = sound.build(vid, d, tl, words); tl["music_tracks"] = []; tl["sfx_chapter"] = None
            config.write(d / "timeline.json", json.dumps(tl, ensure_ascii=False))
        except Exception as e:   # 07.10: партитура не собралась (лимит ElevenLabs) — рендер на готовых треках music_tracks, как до партитуры
            if not tl.get("music_tracks"): raise
            print(f"[sound] партитура не собралась ({str(e)[:140]}) — рендер на треках music_tracks", flush=True)
    if tl.get("format") == "story":
        from .. import visual_integrity
        review_script = (db.get(vid)["payload"].get("script") or {}).get("script") or config.read(d / "script.md")
        if config.is_pilot(vid):   # 19.10 пилот: отклонённые кадры заменяются до рендера, остаток держит рендер
            from . import pilot_fix
            tl = pilot_fix.run(vid, d, tl, review_script)
            from . import story_assets; story_assets._check_files(d, tl)   # 26.10 Walmart: замены пилота не должны оставлять пустых слотов в рендере
        visual_integrity.review(d, tl, review_script, vid)
    base = {"timeline": tl, "words": words}
    scale = [f"--scale={config.RENDER_HEIGHT / 1080:g}"] if config.RENDER_HEIGHT != 1080 else []
    # Remotion копирует public dir (папку ролика) в temp на каждый вызов: готовый final.mp4 (3 ГБ) внутри неё
    # размножался бы на каждый Short и превью и забивал диск. Main рендерится вне папки и переезжает в неё в конце;
    # прошлый final.mp4 — туда же, одна копия на случай отката.
    tmp = config.RENDER_TMP; tmp.mkdir(parents=True, exist_ok=True)
    main_out, prev = tmp / f"{vid}.mp4", tmp / f"{vid}_prev.mp4"
    moved = []
    for old in (d / "final.mp4", d / "preview_540p.mp4"):
        if old.exists():
            dest = prev if old.name == "final.mp4" else tmp / f"{vid}_{old.name}"
            shutil.move(str(old), str(dest)); moved.append((old, dest))
    try:
        if tl.get("format") == "story" and config.STILLCHECK:
            from . import stillcheck
            chk = stillcheck.run(d, tl, words, lang=tl.get("lang") or "en")
            if not chk["ok"]:
                raise RuntimeError("stillcheck: " + "; ".join(i["what"] for i in chk["issues"] if i["severity"] == "block")[:600])
    except BaseException:
        for old, dest in moved:
            if dest.exists() and not old.exists(): shutil.move(str(dest), str(old))
        raise
    try: _rx("render", "Main", main_out, base, d, scale)
    except Exception:   # 18.09: рендер упал на 96 % (кончился диск) — прошлый final остался в RENDER_TMP, а в папке ролика не было ничего
        if prev.exists() and not (d / "final.mp4").exists(): shutil.move(str(prev), str(d / "final.mp4"))
        main_out.unlink(missing_ok=True); raise
    if tl.get("score"):   # партитура сведена под −14 LUFS итогового ролика: YouTube тихий ролик не поднимает (был −19.4)
        from . import sound
        loud = tmp / f"{vid}_master.mp4"
        m = sound.master(main_out, loud); loud.replace(main_out)
        print(f"[render] мастеринг: {m['input_i']:.1f} LUFS → −14")
    # обложка «до → после» в стиле канала — сама, из проверенного портрета и цифр брифа (владелец 20.09: «превью в стиле канала»);
    # не собралась — остаётся генерированная, ролик не останавливаем
    if tl.get("format") == "story" and config.THUMBV_AUTO:
        # 27.09 (владелец: «превью делать по рекомендациям»): основная — по шаблонам разбора ниши Astra (stages/thumbrec.py);
        # сплит «было → стало» — только запасной, если шаблон не собрался. Обложку владельца (.keep) оба не трогают.
        done = bool(series.of(_topic)) and config.THUMB_REC   # обложка серии уже собрана до рендера
        if config.THUMB_REC and not done:
            try:
                from . import thumbrec
                from .. import telegram as _tg
                _r = thumbrec.make(vid); done = True
                pl = _r["plan"]
                if _r.get("fresh"): _tg.send(f"Обложка `{vid}` по шаблону {pl['template']}: «{pl['text']}».\n{pl['why']}", file=_r["sheet"])
            except Exception as e: print(f"[thumbrec] обложка по шаблону не собралась, делаю сплит: {str(e)[:200]}", flush=True)
        if not done:
            try:
                from . import thumbv; thumbv.make(vid, d, tl)
            except Exception as e: print(f"[thumbv] обложка в стиле канала не собралась, остаётся генерированная: {str(e)[:200]}", flush=True)
    for letter in "abc":   # обложки до шортсов: концовка шортса показывает превью полного видео (thumb_a.png)
        if (d / f"thumb_{letter}.keep").exists(): continue   # обложку выбрал владелец (ThumbV) — не перерисовывать генерированной
        if (d / f"thumb_{letter}.json").exists() and (d / f"thumb_{letter}_raw.png").exists():
            _rx("still", "Thumb", d / f"thumb_{letter}.png",
                {**base, "concept": json.loads(config.read(d / f"thumb_{letter}.json")), "image": f"thumb_{letter}_raw.png"}, d)
    (d / "shorts").mkdir(exist_ok=True)
    # готовый ролик переезжает на место ВСЕГДА: 18.09 у Remotion посреди рендера шортса пропала временная папка сведения звука,
    # исключение вылетело до этой строки — и 25-минутный отмастеренный final.mp4 остался лежать в render_tmp
    try:
        if tl.get("format") == "story" and config.SHORTS_PER_VIDEO > 0 and config.SHORTS_MOTION and not list((d / "shorts").glob("motion_*.mp4")):
            # 06.10 владелец: моушен-шортсы (stages/motion_shorts.py) — свой рендер, ShortHook для них не вызывается
            try:
                from . import motion_shorts; motion_shorts.build(vid, config.SHORTS_PER_VIDEO)
            except Exception as e: print(f"[render] моушен-шортсы не собрались: {str(e)[:200]}", flush=True)
        elif tl.get("format") == "story" and config.SHORTS_PER_VIDEO > 0 and not config.SHORTS_MOTION and not list((d / "shorts").glob("s*/short.json")):
            # спеки шортсов конвейер раньше не собирал сам — только команда `shorts <id>` (Netflix 22.09 вышел без шортса)
            try:
                from . import shorts as S; S.build(vid, None)
            except Exception as e: print(f"[render] спеки шортсов не собрались: {str(e)[:160]}", flush=True)
        n_short = hook_shorts(d, scale) if tl.get("format") == "story" else 0
        if tl.get("format") == "story":
            # старую композицию Short для story не трогаем НИКОГДА: это вертикальная обрезка длинного ролика
            # с пустой нижней половиной — владелец забраковал такой формат 17.09. Нет спеков — нет шортсов.
            if not n_short: print(f"[render] спеков шортсов нет (shorts/sN/short.json) — шортсы не рендерю, "
                                  f"собери их отдельно: `python -m orchestrator.main shorts {d.name}`", flush=True)
        elif not n_short:
            for i, seg in enumerate(tl["shorts"]):
                _rx("render", "Short", d / "shorts" / f"short_{i + 1}.mp4", {**base, "segment": seg}, d, scale)
    except subprocess.CalledProcessError as e:
        print(f"[render] шортс не отрендерился ({str(e)[-120:]}) — ролик всё равно ставлю на место, шортсы: `shorts {vid}`")
    finally:
        shutil.move(str(main_out), str(d / "final.mp4"))
    if tl.get("format") == "story":
        visual_integrity.seal_render(d, tl, review_script)
    db.update(vid, "rendered")
