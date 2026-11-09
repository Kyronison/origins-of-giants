"""Проверка рендера: сначала визуальная (контактный лист сцен → модель с картинками), потом текстовая.
Визуальные блокеры → qc_failed (решает владелец). Текстовые блокеры → назад на сценарий с заметкой (максимум 2 раза)."""
import io, json, subprocess
from .. import db, llm, telegram, config

MAX_AUTO_REWRITES = 2

def _kit(vid: str, v: dict, d, dur: float):
    """meta.json и комплект publish/ — нужны и когда QC забраковал: владелец вправе нажать «загрузить как есть»,
    и этап загрузки не должен падать на отсутствующем файле (20.09: Errno 2 meta.json, очередь ушла в повторы)."""
    try:
        if not (d / "meta.json").exists():
            config.write(d / "meta.json", json.dumps(_meta(v, dur), ensure_ascii=False, indent=2))
        if ((v["payload"].get("topic") or {}).get("format") or "news") == "story" and not (d / "publish" / "title.txt").exists():
            from . import publish; publish.run(vid)
    except Exception as e:
        print(f"[qc] комплект публикации не собран: {str(e)[:160]}", flush=True)

def tech_check(mp4, tl: dict) -> list[str]:
    """Проверка готового файла по времени, а не по кадрам (разбор 20.09): чёрные участки, тишина вне пауз глав, клиппинг, длительность.
    Контактный лист этого не видит: он смотрит по одному кадру на сцену."""
    import re as _re
    import imageio_ffmpeg
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    bad = []
    r = subprocess.run([ff, "-hide_banner", "-i", str(mp4), "-vf", "blackdetect=d=1.2:pix_th=0.06", "-af", "silencedetect=n=-48dB:d=3.5",
                        "-map", "0", "-f", "null", "-"], capture_output=True, text=True, errors="replace", check=True)
    log = r.stderr or ""
    pauses = [float(p["at"]) for p in (tl.get("pauses") or [])]
    for m in _re.finditer(r"black_start:([\d.]+) black_end:([\d.]+)", log):
        a, b = float(m.group(1)), float(m.group(2))
        if b > float(tl["duration"]) - 2.5: continue          # затемнение на финальных титрах — штатное
        bad.append(f"чёрный кадр {a:.1f}–{b:.1f} с")
    for m in _re.finditer(r"silence_start: ([\d.]+)[\s\S]{0,120}?silence_duration: ([\d.]+)", log):
        a, dur = float(m.group(1)), float(m.group(2))
        if any(abs(a - p) < 6 for p in pauses): continue      # пауза с карточкой главы — так и задумано
        if a > float(tl["duration"]) - 8: continue
        bad.append(f"тишина {dur:.1f} с с {a:.1f} с")
    v = subprocess.run([ff, "-hide_banner", "-i", str(mp4), "-af", "volumedetect", "-vn", "-f", "null", "-"], capture_output=True, text=True, errors="replace", check=True)
    mx = _re.search(r"max_volume: ([-\d.]+) dB", v.stderr or "")
    if not mx: raise RuntimeError("FFmpeg не вернул измерение громкости")
    if mx and float(mx.group(1)) > -0.3:
        # пик у потолка — норма для лимитированного мастера (Google 20.09: 3 сэмпла из 95 млн). Брак — это срезанные вершины,
        # поэтому смотрим число упёршихся сэмплов и плоские участки, а не сам пик
        a = subprocess.run([ff, "-hide_banner", "-i", str(mp4), "-map", "0:a:0", "-af", "astats=metadata=1:reset=0", "-f", "null", "-"],
                           capture_output=True, text=True, errors="replace", check=True)
        st = a.stderr or ""
        if not _re.search(r"Flat factor:\s*[\d.]+", st) or not _re.search(r"Peak count:\s*[\d.]+", st):
            raise RuntimeError("FFmpeg не вернул статистику клиппинга")
        clipped = max([int(x) for x in _re.findall(r"Number of clipped samples:\s*(\d+)", st)] or [0])
        flat = max([float(x) for x in _re.findall(r"Flat factor:\s*([\d.]+)", st)] or [0.0])
        peaks = max([float(x) for x in _re.findall(r"Peak count:\s*([\d.]+)", st)] or [0.0])
        if clipped > 100 or flat > 0.01:
            bad.append(f"клиппинг: пик {mx.group(1)} dB, срезано сэмплов {clipped}, плоских участков {flat:.3f}")
        else:
            print(f"[qc] пик {mx.group(1)} dB, но срезанных сэмплов {clipped} и вершин у потолка {peaks:.0f} — это лимитер, не перегруз", flush=True)
    dur = float(subprocess.check_output([config.ffprobe(), "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(mp4)]))
    if abs(dur - float(tl["duration"])) > 1.5: bad.append(f"длительность файла {dur:.1f} с ≠ таймлайн {float(tl['duration']):.1f} с")
    return bad

def run(vid: str):
    v = db.get(vid); d = db.video_dir(vid)
    from .. import gates
    db.update(vid, "rendered", payload={"release_gate": None, "final_approval": None})
    dur = float(subprocess.check_output([config.ffprobe(), "-v", "error", "-show_entries", "format=duration",
                                         "-of", "csv=p=0", str(d / "final.mp4")]))
    tl = json.loads(config.read(d / "timeline.json"))

    tech = tech_check(d / "final.mp4", tl)   # техпроверка по времени: чёрные кадры, тишина, клиппинг
    if tech: print("[qc] техпроверка: " + "; ".join(tech), flush=True)
    # 1. визуальный QC: обзорный лист — владельцу в Telegram; модели — все сцены листами по SHEET_CHUNK кадров (крупнее, ничего не пропущено)
    contact_sheet(d / "final.mp4", tl["scenes"], d / "contact.jpg")
    bad = []
    for a in range(0, len(tl["scenes"]), SHEET_CHUNK):
        idx = list(range(a, min(a + SHEET_CHUNK, len(tl["scenes"]))))
        sheet = contact_sheet(d / "final.mp4", tl["scenes"], d / f"contact_{a // SHEET_CHUNK + 1}.jpg", idx=idx)
        bad += visual_check(vid, tl["scenes"], sheet, idx)
    notes = [b for b in bad if b.get("severity") != "block"]; bad = [b for b in bad if b.get("severity") == "block"]
    vnote = ("Слабые кадры (не блокируют): " + "; ".join(f"{b['n']} {b.get('id','')}: {b['why']}" for b in notes)) if notes else ""
    # Владелец 20.09: «меньше пересборок, или пофиг — запускать так, с косяками». Пересборка после рендера стоит
    # ~$20 и полтора часа, поэтому забракованные кадры теперь останавливают ролик только при правовом риске
    # (водяной знак стока = неоплаченное превью, чужой логотип, документ не той компании). Остальное — в отчёт.
    hard = [b for b in bad if config.QC_HARD.search(str(b.get("why", "")))]
    if bad and (hard or not config.QC_SHIP_ANYWAY):
        note = "Визуальный QC: " + "; ".join(f"сцена {b['n']} ({b.get('id','')}): {b['why']}" for b in bad)
        db.update(vid, "qc_failed", payload={"qc_note": note})
        _kit(vid, v, d, dur)   # кнопка «загрузить как есть» должна работать: без meta.json и publish/ этап загрузки падал (20.09)
        telegram.send((f"Правовой риск в кадрах `{vid}`:\n" + "; ".join(b["why"] for b in hard) + "\n\nОстальное: " if hard else
                       f"Битые кадры в `{vid}`:\n") + note + "\n✅ — загрузить как есть, ✖ — переписать (или `fix {vid}: ...`)",
                      [("✅ Загрузить", f"approve:{vid}"), ("✖ Переписать", f"reject:{vid}")], file=d / "contact.jpg")
        return
    if bad:   # выпускаем как есть, но с честным списком
        vnote = ("Выпущено с замечаниями к кадрам: " + "; ".join(f"{b['n']} {b.get('id','')}: {b['why']}" for b in bad)
                 + ("\n" + vnote if vnote else ""))

    # 2. текстовый QC
    words = json.loads(config.read(d / "words.json"))
    transcript = " ".join(f"[{w['s']:.1f}] {w['w']}" if i % 25 == 0 else w["w"] for i, w in enumerate(words))
    meta = _meta(v, dur)
    fmt = (v["payload"].get("topic") or {}).get("format") or "news"
    target = "25–32 минуты" if fmt == "story" else "8–15 минут"   # 08.10 владелец: ~30 мин (STORY_WORDS=4300; было 20–24 с 27.09)
    res = llm.ask_json(config.prompt("qc", script=v["payload"]["script"]["script"], transcript=transcript, format=fmt, target_minutes=target,
                                     meta_json=json.dumps(meta, ensure_ascii=False)) +
                       f"\n\nФактическая длительность: {dur/60:.1f} мин. Недавние сценарии для сравнения структуры:\n" +
                       ("\n---\n".join(_recent_scripts(vid)) or "(это первое видео канала)"), heavy=True, max_tokens=12000, effort="low", tag=f"qc_{vid}")
    if not isinstance(res, dict) or type(res.get("pass")) is not bool or not isinstance(res.get("issues"), list):
        raise ValueError("Текстовый QC вернул неполный ответ")
    issues = res["issues"]
    if any(not isinstance(i, dict) or i.get("severity") not in ("block", "warn", "note") for i in issues):
        raise ValueError("Текстовый QC вернул некорректные замечания")
    blocks = [i for i in issues if i.get("severity") == "block"]
    if blocks and config.QC_SHIP_ANYWAY:
        # текст уже озвучен: «переписать» здесь означает заново сценарий, голос, кадры и рендер — это целый ролик заново.
        # Замечания остаются в отчёте и учитываются в следующем ролике через fix_note, но этот выпускаем.
        print("[qc] текстовые замечания не держат ролик: " + "; ".join(b.get("what", "")[:60] for b in blocks), flush=True)
        db.update(vid, payload={"fix_note_next": "; ".join(b.get("fix", "") for b in blocks)[:1500]})
        blocks = []
    # 27.09 Safelite: блокеры сняты «выпускаем как есть», но pass=false всё равно отправлял готовый ролик на полную переписку с пустой причиной
    if blocks or (not res.get("pass") and not config.QC_SHIP_ANYWAY):
        attempts = v["payload"].get("qc_attempts", 0) + 1
        note = "QC: " + "; ".join(f"{b.get('where','')}: {b.get('what','')} → {b.get('fix','')}" for b in blocks)
        if attempts > MAX_AUTO_REWRITES:
            db.update(vid, "qc_failed", payload={"qc_attempts": attempts, "qc_note": note})
            _kit(vid, v, d, dur)   # то же самое: владелец может решить грузить как есть
            telegram.send(f"QC не прошёл {attempts} раза подряд: `{vid}`\n{note}\n"
                          f"✅ — загрузить как есть, ✖ — переписать (или `fix {vid}: ...`)",
                          [("✅ Загрузить", f"approve:{vid}"), ("✖ Переписать", f"reject:{vid}")])
            return
        db.update(vid, "approved_topic", payload={"fix_note": note, "qc_attempts": attempts})
        telegram.send(f"QC не прошёл `{vid}` (попытка {attempts}), переписываю: " + "; ".join(b.get("what", "") for b in blocks))
        return
    config.write(d / "meta.json", json.dumps(meta, ensure_ascii=False, indent=2))
    publish_ok = fmt != "story"
    if fmt == "story":   # комплект для Studio (publish/): поля, главы, источники, субтитры ASCII, карточки шортсов; сбой не держит ролик
        import hashlib as _h
        sha = _h.sha1((json.dumps(meta, ensure_ascii=False) + (v["payload"].get("script") or {}).get("script", "")).encode("utf-8")).hexdigest()[:16]
        if v["payload"].get("publish_sha") == sha and (d / "publish" / "title.txt").exists():
            publish_ok = True
            print("[publish] поля Studio не менялись — не пересобираю", flush=True)
        else:
            try:
                from . import publish; meta = publish.run(vid); db.update(vid, payload={"publish_sha": sha})
                config.write(d / "meta.json", json.dumps(meta, ensure_ascii=False, indent=2))   # 25.09: загрузка читает meta.json,
                publish_ok = True
                # а до этой строки там оставалось ЧЕРНОВОЕ описание — у Boston Market 7 763 знака при лимите YouTube 5 000
            except Exception as e: print(f"[publish] не собран: {e}")
    thumb = {"ok": fmt != "story", "notes": []}
    if fmt == "story":   # превью смотрим в размере мобильной ленты: 76% аудитории канала — телефоны
        try:
            from . import thumbcheck; thumb = thumbcheck.check(vid)
        except Exception as e:
            thumb = {"ok": False, "notes": [f"Проверка не завершена: {str(e)[:160]}"]}
            print(f"[thumb] проверка не прошла: {e}")
    cost = round(float(v["payload"].get("cost_usd", 0)) + llm.take_cost(), 4)
    db.update(vid, "qc_passed", payload={"cost_usd": cost, "thumb_check": thumb})
    warns = (("Замечания: " + "; ".join(i.get("what", "") for i in issues)) if issues else "Замечаний нет.")
    if tech: warns += "\nТехпроверка: " + "; ".join(tech)
    if vnote: warns += "\n" + vnote[:1500]
    if thumb.get("notes"): warns += "\nПревью в ленте телефона: " + "; ".join(thumb["notes"])
    warns += f"\nРасходы на видео: ${cost:.2f} из ${config.BUDGET_USD:.0f}"
    fr, oc = {}, {}
    try:   # 29.09 STRATEGY.md: доля настоящей съёмки, чужие отрезки длиннее 10 с, кадры агентств
        from . import footage
        fr = footage.report(json.loads(config.read(d / "timeline.json")))
        db.update(vid, payload={"footage": fr}); warns += "\n" + footage.line(fr)
    except Exception as e: print(f"[qc] отчёт по кадрам: {e}", flush=True)
    try:   # обещание одним взглядом: название = превью = первые секунды (разбор канала 21.09)
        oc = json.loads(config.read(d / "opening_check.json")) if (d / "opening_check.json").exists() else {}
        tv = db.get(vid)["payload"].get("thumbv") or {}
        first = ((oc.get("windows") or {}).get("0-10") or "")[:140]
        warns += f"\nОбещание: «{meta['titles'][0]}» | превью: {tv.get('hook', 'генерированная')} → {tv.get('hook2', '—')} | 0–10 с: «{first}»"
        if oc and not oc.get("ok"): warns += "\nПервая минута слабая: " + "; ".join(oc.get("rules") or [])[:300]
    except Exception as e: print(f"[qc] строка обещания: {e}")
    try:
        from .. import money; money.report_html()   # дашборд обновляется после каждого QC
    except Exception as e: print(f"[money] {e}")
    # автономный режим (владелец 20.09: «хочу минимального участия»): ролик уходит в расписание сам, когда чисто всё,
    # что проверяется машиной — техпроверка файла, визуальный QC без блокеров, комплект публикации и превью в ленте.
    kit_ok = publish_ok and (fmt != "story" or all((d / "publish" / n).is_file() and (d / "publish" / n).stat().st_size > 0 for n in ("title.txt", "description.txt", "tags.txt", "thumbnail_2560.jpg")))
    from .. import visual_integrity
    integrity_ok = fmt != "story" or visual_integrity.approved(d, tl, v["payload"]["script"]["script"], rendered=True)
    gate = gates.record(vid, {"technical": not tech, "text": not blocks, "archive_context": integrity_ok,
                            "thumbnail": thumb.get("ok") is True, "kit": kit_ok,
                            "footage": fmt != "story" or fr.get("ok") is True,
                            "opening": fmt != "story" or not config.OPENING_GATE or oc.get("ok") is True,
                            "script_review": gates.script_ready(db.get(vid))})
    auto = gate["ok"] and (config.AUTO_APPROVE or not config.REQUIRE_FINAL_APPROVAL)
    if not auto:
        db.update(vid, "qc_passed" if gate["ok"] else "qc_failed")
        warns += "\nДопуск: " + ", ".join(k for k, ok in gate["checks"].items() if not ok)
        telegram.send("Контактный лист сцен:", file=d / "contact.jpg")
        telegram.ask_final_review(vid, d / "final.mp4", note=f"{meta['titles'][0]}\n{warns}")
    else:
        if config.REQUIRE_FINAL_APPROVAL: db.update(vid, "approved_final")   # очередь загрузит на ближайшем шаге
        kit = d / "publish" / "studio.txt"
        telegram.send(f"Ролик собран и уходит в расписание сам: `{vid}`\n{meta['titles'][0]}\n{warns}\n"
                      f"Все поля для Studio — в файле ниже. Остановить: `reject {vid}`",
                      file=kit if kit.exists() else d / "contact.jpg")

# ---------- визуальный QC ----------

MAX_SHEET_FRAMES = 48   # лимит OpenRouter на картинку — 30 МБ; 48 кадров JPEG ≈ 1–2 МБ
SHEET_CHUNK = 24        # кадров на лист для модели: Claude ужимает картинку до 2576 px по длинной стороне — 48 кадров становились по 250 px

def contact_sheet(video, scenes: list[dict], out, cols=4, width=480, idx: list[int] | None = None) -> bytes:
    """Кадр из середины каждой сцены (idx — какие сцены; по умолчанию все, для длинных роликов — равномерная выборка до MAX_SHEET_FRAMES)
    → сетка с номерами. JPEG-байты + файл."""
    from PIL import Image, ImageDraw
    idx = idx or list(range(len(scenes)))
    if len(idx) > MAX_SHEET_FRAMES:
        step = len(idx) / MAX_SHEET_FRAMES; idx = [int(i * step) for i in range(MAX_SHEET_FRAMES)]
    frames = []
    for i in idx:
        sc = scenes[i]; t = (sc["start"] + sc["end"]) / 2
        png = subprocess.run([config.ffmpeg(), "-v", "error", "-ss", f"{t:.2f}", "-i", str(video), "-frames:v", "1",
                              "-vf", f"scale={width}:-1", "-f", "image2pipe", "-vcodec", "png", "-"], capture_output=True, check=True).stdout
        frames.append((i, Image.open(io.BytesIO(png)).convert("RGB")))
    w, h = frames[0][1].size; rows = (len(frames) + cols - 1) // cols; pad = 8
    sheet = Image.new("RGB", (cols * w + (cols + 1) * pad, rows * h + (rows + 1) * pad), "white"); draw = ImageDraw.Draw(sheet)
    for k, (i, im) in enumerate(frames):
        x = pad + (k % cols) * (w + pad); y = pad + (k // cols) * (h + pad)
        sheet.paste(im, (x, y)); draw.rectangle([x, y, x + 150, y + 22], fill="red")
        draw.text((x + 5, y + 5), f"{i + 1}  {scenes[i]['id']}  {scenes[i]['type']}", fill="white")
    out = str(out).rsplit(".", 1)[0] + ".jpg"
    sheet.save(out, "JPEG", quality=82); buf = io.BytesIO(); sheet.save(buf, "JPEG", quality=82); return buf.getvalue()

VISUAL_PROMPT = """Это контактный лист документального видео: по одному кадру из середины каждой сцены, номер и тип сцены подписаны красным в углу.
Под списком — что в этот момент говорит диктор и подпись к кадру.

severity "block" — брак, с которым ролик нельзя выпускать:
- кадр-заглушка: пустой фон там, где должны быть заголовок, цифра или график; график или карточка без данных;
- обрезанный или наехавший текст, контент за пределами карточки;
- мусорные буквы и цифры на сгенерированной картинке (псевдотекст на обложках, вывесках, документах, чеках);
- артефакты генерации: лишние пальцы, расплывшиеся лица;
- водяной знак стока или фотобанка ПОВЕРХ изображения (Adobe Stock, Getty, Shutterstock, Alamy и т. п.). Мелкая машинописная строка «photo: …», «YouTube: …» или «Wikimedia Commons …» в правом нижнем углу кадра и «Origins of Giants» слева сверху — это наши собственные подписи источника и канала, НЕ водяной знак (Netflix 21.09: ролик встал из-за такой строки);
- подпись-плашка обрезана (слово оборвано на середине).
severity "note" — слабое место, решает владелец: связь кадра с фразой косвенная; главный объект фразы (человек, продукт) отсутствует,
хотя фраза конкретная; people-сцена с именем в подписи, а лица на кадре не видно (спиной, только руки); снимок явно другой эпохи,
а подпись это скрывает (подпись ставит год рассказа, а не год съёмки; дата на документе в кадре не совпадает с подписью).
Кто изображён на фото, НЕ определяй и не оценивай — только видно ли лицо.

НЕ отмечай вообще (это приёмы канала, а не брак):
- современный снимок места или предмета при рассказе о прошлом, если подпись честно ставит год съёмки («Princeton campus, 2022»);
- архивная съёмка или гравюра другой эпохи с честной подписью;
- атмосферный кадр без людей (стол, коридор, комната, город) под абстрактную или переходную фразу;
- тёмный или сдержанный по цвету кадр, если объект различим.
Верни JSON: {"bad":[{"n":<номер>,"severity":"block"|"note","why":"<коротко>"}]} — пустой список, если отмечать нечего.

{listing}"""

def visual_check(vid: str, scenes: list[dict], sheet_png: bytes, idx: list[int] | None = None) -> list[dict]:
    """Финальная проверка — сильной vision-моделью (config.LLM_MODEL_VISION_FINAL, аудит 18.09: Opus 5 — Arena Vision №10, Sonnet 5 — №33)."""
    idx = idx or list(range(len(scenes)))
    listing = "\n".join(f"{i + 1}. {scenes[i]['id']} · «{(scenes[i].get('anchor') or '')[:60]}…» · подпись: {scenes[i].get('caption') or '—'}" for i in idx)
    res = llm.ask_vision(VISUAL_PROMPT.replace("{listing}", listing), [sheet_png], tag=f"vqc_{vid}", model=config.LLM_MODEL_VISION_FINAL or None)
    if not isinstance(res, dict) or not isinstance(res.get("bad"), list):
        raise ValueError("Визуальный QC вернул неполный ответ")
    bad = []
    for b in res["bad"]:
        if not isinstance(b, dict) or b.get("severity") not in ("block", "note") or not b.get("why"):
            raise ValueError("Визуальный QC вернул некорректное замечание")
        n = int(b.get("n", 0))
        if n - 1 not in idx: raise ValueError("Визуальный QC указал сцену вне проверяемого листа")
        if 1 <= n <= len(scenes): bad.append({"n": n, "id": scenes[n - 1]["id"], "why": b.get("why", ""), "severity": b.get("severity") or "block"})
    return bad

# ---------- метаданные ----------

def _titles(v) -> list[str]:
    """Фолбэк без publish: обещание брифа (если латиницей) первым, «истории компании» — в конец (ревью 21.09)."""
    import re as _re
    from .brief import TITLE_BANAL
    s = v["payload"]["script"]; b = v["payload"].get("brief") or {}
    opts = list(s.get("title_options") or [])
    good = [t for t in opts if not TITLE_BANAL.search(t)]; banal = [t for t in opts if TITLE_BANAL.search(t)]
    tp = str(b.get("title_promise") or "").strip()
    if tp and not _re.search(r"[А-Яа-яЁё]", tp) and tp not in good: good.insert(0, tp[:100])
    return good + banal or [v["title"]]

def _meta(v, dur):
    s = v["payload"]["script"]; tl = json.loads(config.read(db.video_dir(v["id"]) / "timeline.json")); sb = tl["scenes"]
    chapters, last = ["0:00 Intro"], 0
    if tl.get("overlays"):   # story: главы — из карточек глав
        for o in tl["overlays"]:
            if o.get("type") == "chapter" and o.get("text") and o["start"] - last >= 10:
                chapters.append(f"{int(o['start'])//60}:{int(o['start'])%60:02d} {o['text']}"); last = o["start"]
    for sc in ([] if tl.get("overlays") else sb):
        if sc["type"] not in ("title", "stat", "bar_chart", "line_chart", "compare"): continue
        name = sc.get("caption") or sc["data"].get("title") or sc["data"].get("label") or sc["data"].get("text") or ""
        if sc["start"] - last < 10 or not name: continue   # YouTube: главы не короче 10 сек
        chapters.append(f"{int(sc['start'])//60}:{int(sc['start'])%60:02d} {name}"); last = sc["start"]
    chapters_txt = ("\n\nChapters\n" + "\n".join(chapters)) if len(chapters) >= 3 else ""
    pri = {"10-K": 0, "regulator": 1, "transcript": 2, "press": 3, "interview": 4, "analyst": 5}   # первоисточники первыми, без дублей
    urls, seen = [], set()
    for f in sorted(v["payload"]["research"]["facts"], key=lambda f: pri.get(f.get("source_type"), 9)):
        u = (f.get("source_url") or "").strip()
        if u and u not in seen: seen.add(u); urls.append(u)
    sources = "\n".join(f"- {u}" for u in urls[:12])
    from . import archive
    cred = archive.credits(s.get("shots") or [])
    archive_txt = ("\n\nArchive photos and footage\n" + cred) if cred else ""
    note = ("Some visuals and the voice in this video are produced with AI tools; archival photos and footage are credited above; research and conclusions are the author's."
            if cred else "Visuals and voice in this video are produced with AI tools; research, calculations and conclusions are the author's.")
    return {"titles": _titles(v), "tags": s["tags"][:30],
            "description": s["description"] + chapters_txt + "\n\nSources\n" + sources + archive_txt + "\n\n" + note}

def _recent_scripts(vid, n=10):
    from contextlib import closing
    with closing(db.conn()) as connection:
        ids = [r["id"] for r in connection.execute(
            "SELECT id FROM videos WHERE id!=? AND status IN ('uploaded','published','analyzed') ORDER BY created DESC LIMIT ?", (vid, n))]
    return [x["payload"]["script"]["script"][:3000] for x in
            [db.get(t) for t in ids]
            if x["payload"].get("script")]
