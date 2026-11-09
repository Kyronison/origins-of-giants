"""Испанские шортсы (владелец 15.10.2026: «Лучше вариант B» из проб work/shorts-lab-es). Один шортс к каждому испанскому ролику:
- отрывок 40–58 с из самого ролика (голос ролика, целые предложения, понятен без контекста);
- те же сцены, что в ролике на этом отрезке, перерисованы под вертикальный кадр в стиле канала; надписи на рисунках — по-испански;
- проверка на посторонних знаменитостей (до двух перерисовок); проверка не состоялась ≠ «чисто»: шортс ждёт следующего круга;
- заголовок на бумажной плашке первые 3 с, субтитры по словам (звучащее слово — красным) на плашке внизу;
- выход на следующий день после ролика в 18:00 МСК (между роликами, которые идут через день), комментарий со ссылкой на ролик — после выхода.
Загрузка — только при ES_SHORTS_UPLOAD=1 (первый шортс владелец смотрит сам). Файлы — в папке ролика shorts_es/."""
import json, os, re, subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from .. import config, db, llm, telegram

W, H, FPS = 1080, 1920, 30
INK, RED, PAPER = (43, 38, 34), (178, 40, 30), (246, 239, 222)
FONT = config.ROOT / "work" / "es-cartoon" / "fonts" / "AlfaSlabOne-Regular.ttf"
MSK = timezone(timedelta(hours=3))
UPLOAD = os.getenv("ES_SHORTS_UPLOAD", "0") == "1"   # .env уже загружен config

PICK = """Испанский документальный ролик о компании {company}. Ниже — предложения закадрового текста с временем начала и конца (секунды).
Выбери ОДИН непрерывный отрывок для YouTube Shorts длиной от 40 до 58 секунд (конец последнего минус начало первого):
- понятен без остального ролика: первое предложение не опирается на прошлое («eso», «él», «entonces», «mientras tanto» без ясного предмета);
- первое предложение — крючок (резкий факт, число, конфликт), последнее — развязка или острый вопрос;
- не из первых 90 секунд ролика; лучше поворотный момент истории с понятной ставкой.
Ещё придумай:
- line1, line2 — заголовок на экран ЗАГЛАВНЫМИ по-испански, каждая строка до 18 знаков; line2 — поворот (с числом из отрывка, если оно есть);
- title — название шортса по-испански до 70 знаков, только то, что сказано в отрывке, без выдумок; без слов «tesis», «teoría», без вопросов-загадок;
- числа везде в испанской записи: «2.500 MILLONES», «$80.000 MILLONES», «57%» — никаких «M», «B», «bn»;
- hook — одна фраза-крючок по-испански до 120 знаков для описания.
Верни JSON {{"first": 12, "last": 20, "line1": "...", "line2": "...", "title": "...", "hook": "...", "why": "по-русски, коротко"}}

{lines}"""

REDRAW = """Это описания рисунков для испанского документального мультфильма о {company} (горизонтальный кадр). Перепиши каждое для ВЕРТИКАЛЬНОГО кадра:
то же содержание и те же люди; любой текст на рисунке (подписи, таблички, заголовки газет) — по-испански, коротко, в одинарных кавычках;
из реальных людей оставь только героев истории ({allowed}), остальных замени безымянными человечками с круглыми головами.
Числа — в испанской записи («$80.000 millones», «$45.600 millones», «18%»), никаких «B»/«M»; число — только на табличке, ярлыке или чеке,
небольшое, а не огромными цифрами во весь кадр (сверху кадра будет заголовок).
Верни JSON {{"prompts": ["...", ...]}} — ровно {n} описаний в том же порядке.

{items}"""

CELEBS = """Это {n} вертикальных рисунков для документального мультфильма о компании {company}. Под каждым номером — фраза диктора:
{lines}

Найди рисунки, где нарисован УЗНАВАЕМЫЙ реальный знаменитый человек (политик, предприниматель, артист, учёный, спортсмен), которого НЕТ
в фразе под этим номером и нет среди героев истории: {allowed}. Обычные человечки с круглыми головами и безымянные люди — норма.
Отдельно отметь узнаваемые трагические места (например, башни-близнецы Всемирного торгового центра).
Верни JSON {{"bad": [{{"n": 3, "who": "кто это похоже", "why": "кратко"}}]}} (пустой список, если всё чисто)."""

VERT = (", tall vertical portrait composition, the scene stacked from top to bottom, main subject in the middle of the frame"
        ", every person in the picture is either a simple round-headed figure or a caricature of {allowed} when named; absolutely no other real famous people, "
        "no politicians, no presidents, no Bill Gates, no Elon Musk, no celebrities in the crowd; no twin towers, no World Trade Center")


def _sentences(words):
    out, cur = [], []
    for w in words:
        cur.append(w)
        if re.search(r"[.!?…]$", w["w"]): out.append(cur); cur = []
    if cur: out.append(cur)
    return [{"s": c[0]["s"], "e": c[-1]["e"], "t": " ".join(w["w"] for w in c)} for c in out]


def _board_prompt(d, image):
    m = re.search(r"p(\d+)_(\d+)", image)
    if not m: return None
    parts = json.loads(config.read(d / "es_board.json"))["parts"]
    p, n = int(m.group(1)) - 1, int(m.group(2)) - 1
    try: return parts[p]["prompts"][n]
    except (IndexError, KeyError): return None


def _plan(vid, d, t):
    words = json.loads(config.read(d / "words.json")); sents = _sentences(words)
    lines = "\n".join(f"{i}. [{s['s']:.1f}–{s['e']:.1f}] {s['t']}" for i, s in enumerate(sents))
    for _ in range(3):
        r = llm.ask_json(PICK.format(company=t["company"], lines=lines), heavy=True, max_tokens=8000, tag=f"es_short_pick_{vid}")
        a, b = int(r["first"]), int(r["last"])
        if not 0 <= a < len(sents): continue
        b = min(max(a, b), len(sents) - 1)   # модель плохо складывает секунды: длину подгоняем сами по целым предложениям
        while sents[b]["e"] - sents[a]["s"] < 40 and b + 1 < len(sents): b += 1
        while sents[b]["e"] - sents[a]["s"] > 58 and b > a: b -= 1
        if 38 <= sents[b]["e"] - sents[a]["s"] <= 62: break
    else: raise ValueError("отрывок для шортса не подобран (длина вне 40–58 с)")
    t0, t1 = sents[a]["s"] - 0.1, sents[b]["e"] + 0.25
    spec = json.loads(config.read(d / "es_spec.json"))
    shots = [dict(s) for s in spec["shots"] if s["end"] > t0 + 0.3 and s["start"] < t1]
    src = [_board_prompt(d, s["image"]) or "Simple round-headed figures acting out: " + " ".join(
        w["w"] for w in words if s["start"] <= w["s"] < s["end"]) for s in shots]
    allowed = t.get("people") or t["company"]
    rr = llm.ask_json(REDRAW.format(company=t["company"], allowed=allowed, n=len(src), items="\n".join(f"{i + 1}. {p}" for i, p in enumerate(src))),
                      max_tokens=4000, tag=f"es_short_redraw_{vid}")
    prompts = rr.get("prompts") or []
    if len(prompts) != len(shots): raise ValueError(f"перепись описаний: {len(prompts)} вместо {len(shots)}")
    for s, p in zip(shots, prompts):
        s["prompt"] = p; s["beat"] = " ".join(w["w"] for w in words if s["start"] <= w["s"] < s["end"])[:200]
    return {"t0": t0, "t1": t1, "line1": r["line1"].upper(), "line2": r["line2"].upper(), "title": r["title"], "hook": r["hook"],
            "why": r.get("why", ""), "shots": shots, "text": " ".join(s["t"] for s in sents[a:b + 1])}


def _draw(sd, plan, allowed, which):
    from . import assets as A
    def one(i):
        s = plan["shots"][i]; n = s.get("redraw", 0); sid = f"v{i:02d}" + (f"_c{n}" if n else "")
        f = sd / f"{sid}.png"
        if not f.exists():
            p = A._image(s["prompt"] + VERT.format(allowed=allowed), sd, sid, config.IMAGE_MODEL, w=1024, h=1824, cartoon=True)
            (sd / p).replace(f)
        s["vimage"] = f.name
    with ThreadPoolExecutor(12) as ex: list(ex.map(one, which))


def _celebs(vid, sd, plan, t):
    """{номер кадра: кто} — посторонние знаменитости. Сбой проверки — исключение (не «чисто»)."""
    import io
    from PIL import Image, ImageDraw, ImageFont
    shots = plan["shots"]; w, h, cols = 270, 480, 5; rows = (len(shots) + cols - 1) // cols
    sh = Image.new("RGB", (cols * w, rows * (h + 30)), "white"); dr = ImageDraw.Draw(sh); f = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 24)
    for i, s in enumerate(shots):
        x, y = (i % cols) * w, (i // cols) * (h + 30)
        sh.paste(Image.open(sd / s["vimage"]).convert("RGB").resize((w, h)), (x, y + 30)); dr.text((x + 4, y + 2), str(i + 1), font=f, fill="black")
    buf = io.BytesIO(); sh.save(buf, "JPEG", quality=88)
    allowed = t.get("people") or t["company"]
    r = llm.ask_vision(CELEBS.format(n=len(shots), company=t["company"], allowed=allowed,
                                     lines="\n".join(f"{i + 1}. {s['beat']}" for i, s in enumerate(shots))),
                       [buf.getvalue()], tag=f"es_short_celebs_{vid}", model=config.LLM_MODEL_VISION)
    if not isinstance(r, dict) or not isinstance(r.get("bad"), list): raise ValueError("проверка знаменитостей не дала ответа")
    return {int(b["n"]) - 1: b.get("who", "") for b in r["bad"] if isinstance(b, dict) and str(b.get("n", "")).isdigit() and 0 < int(b["n"]) <= len(shots)}


def _render(d, sd, plan, out):
    import imageio_ffmpeg
    from PIL import Image, ImageDraw, ImageFont, ImageFilter
    ff = imageio_ffmpeg.get_ffmpeg_exe(); t0, t1 = plan["t0"], plan["t1"]; dur = t1 - t0
    words = [w for w in json.loads(config.read(d / "words.json")) if w["s"] >= t0 - 0.05 and w["e"] <= t1 + 0.05]
    ch, cur = [], []
    for w in words:
        cur.append(w)
        if len(cur) == 3 or re.search(r"[.,!?;:…]$", w["w"]): ch.append(cur); cur = []
    if cur: ch.append(cur)
    font = lambda sz: ImageFont.truetype(str(FONT), sz)
    imgs = {s["vimage"]: Image.open(sd / s["vimage"]).convert("RGB") for s in plan["shots"]}
    shots = plan["shots"]

    def caption(im, t):
        c = next((c for i, c in enumerate(ch) if c[0]["s"] - t0 <= t < (ch[i + 1][0]["s"] - t0 if i + 1 < len(ch) else 1e9)), None)
        if not c: return
        dr = ImageDraw.Draw(im); f = font(84)
        parts = [(w["w"].upper(), RED if w["s"] - t0 <= t < w["e"] - t0 + 0.08 else INK) for w in c]
        size = lambda f: sum(dr.textlength(s, font=f) for s, _ in parts) + dr.textlength(" ", font=f) * (len(parts) - 1)
        tw = size(f)
        if tw > W - 110: f = font(int(84 * (W - 110) / tw)); tw = size(f)
        x = (W - tw) / 2; y = 1560; pad = 28; bb = (x - pad, y - 62, x + tw + pad, y + 62)
        sh = Image.new("RGBA", im.size, (0, 0, 0, 0)); ImageDraw.Draw(sh).rounded_rectangle(bb, 26, fill=(0, 0, 0, 90))
        im.alpha_composite(sh.filter(ImageFilter.GaussianBlur(8)))
        dr = ImageDraw.Draw(im); dr.rounded_rectangle(bb, 26, fill=PAPER + (245,), outline=INK, width=4)
        sp = dr.textlength(" ", font=f)
        for s, col in parts: dr.text((x, y), s, font=f, fill=col, anchor="lm"); x += dr.textlength(s, font=f) + sp

    def title(im):
        im.alpha_composite(Image.new("RGBA", (W, 330), PAPER + (235,)), (0, 120)); dr = ImageDraw.Draw(im)
        for i, (s, col) in enumerate(zip((plan["line1"], plan["line2"]), (INK, RED))):
            f = font(112)
            while dr.textlength(s, font=f) > W - 90: f = font(f.size - 4)
            dr.text((W // 2, 220 + i * 132), s, font=f, fill=col, anchor="mm")

    def frame(t):
        at = t + t0
        i = next((k for k, s in enumerate(shots) if at < s["end"]), len(shots) - 1); s = shots[i]
        st = max(s["start"], t0); p = min(1.0, max(0.0, (at - st) / max(0.1, min(s["end"], t1) - st)))
        img = imgs[s["vimage"]]; iw, ih = img.size; kind = s.get("move", "in")
        z = 1.0 + 0.08 * (p if kind != "out" else 1 - p); cw, chh = iw / z, ih / z
        if cw / chh > W / H: cw = chh * W / H
        else: chh = cw * H / W
        dx = (iw - cw) * ({"left": 1 - p, "right": p}.get(kind, 0.5)); dy = (ih - chh) / 2
        im = img.crop((int(dx), int(dy), int(dx + cw), int(dy + chh))).resize((W, H), Image.BILINEAR).convert("RGBA")
        if t < 3.0: title(im)
        caption(im, t)
        return im

    aud = sd / "voice.m4a"
    subprocess.run([ff, "-y", "-v", "error", "-ss", f"{t0:.3f}", "-to", f"{t1:.3f}", "-i", str(d / "voice.mp3"),
                    "-af", f"afade=t=in:d=0.05,afade=t=out:st={dur - 0.4:.2f}:d=0.4", "-c:a", "aac", "-b:a", "192k", str(aud)], check=True)
    tmp = out.with_suffix(".part.mp4")
    p = subprocess.Popen([ff, "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-i", str(aud),
                          "-c:v", "h264_nvenc", "-preset", "p5", "-cq", "19", "-pix_fmt", "yuv420p", "-c:a", "copy", "-shortest", str(tmp)], stdin=subprocess.PIPE)
    for k in range(int(dur * FPS)): p.stdin.write(frame(k / FPS).convert("RGB").tobytes())
    p.stdin.close()
    if p.wait() != 0: raise RuntimeError("ffmpeg (шортс) завершился с ошибкой")
    tmp.replace(out)


def _comment_text(v, sh):
    return (f"{sh['hook']} #shorts\n\nDocumental completo en el canal:\n{v['title']}\n"
            f"https://www.youtube.com/watch?v={v['youtube_id']}\n\n#Shorts")


def build(vid: str):
    """План → вертикальные рисунки → проверка знаменитостей → рендер. Повторный запуск продолжает с готового (рисунки не покупаются дважды)."""
    v = db.get(vid); d = db.video_dir(vid); t = v["payload"]["topic"]; sd = d / "shorts_es"; sd.mkdir(exist_ok=True)
    pf = sd / "plan.json"
    plan = json.loads(config.read(pf)) if pf.exists() else _plan(vid, d, t)
    config.write(pf, json.dumps(plan, ensure_ascii=False, indent=1))
    allowed = t.get("people") or t["company"]
    _draw(sd, plan, allowed, [i for i, s in enumerate(plan["shots"]) if not s.get("vimage") or not (sd / s["vimage"]).exists()])
    config.write(pf, json.dumps(plan, ensure_ascii=False, indent=1))
    for rnd in range(3):   # проверка → до двух перерисовок → контрольная проверка
        bad = _celebs(vid, sd, plan, t)
        print(f"[es-short] {vid}: круг {rnd + 1}, посторонние знаменитости: " + (", ".join(f"{i + 1} ({w})" for i, w in bad.items()) or "нет"), flush=True)
        if not bad: break
        if rnd == 2:
            db.update(vid, payload={"es_short": {"status": "blocked", "why": "знаменитости после двух перерисовок: " + ", ".join(bad.values())}})
            telegram.send(f"🇪🇸 Шортс `{vid}` не собран: на рисунках остались посторонние знаменитости ({', '.join(bad.values())}).")
            return
        for i in bad: plan["shots"][i]["redraw"] = plan["shots"][i].get("redraw", 0) + 1
        _draw(sd, plan, allowed, list(bad)); config.write(pf, json.dumps(plan, ensure_ascii=False, indent=1))
    out = sd / "short.mp4"; _render(d, sd, plan, out)
    kit = {"title": (plan["title"][:90] + " #shorts")[:100], "description": _comment_text(v, plan) if v.get("youtube_id") else plan["hook"] + " #shorts",
           "comment": _comment_text(v, plan) if v.get("youtube_id") else "", "line1": plan["line1"], "line2": plan["line2"],
           "seconds": round(plan["t1"] - plan["t0"], 1), "why": plan["why"]}
    config.write(sd / "studio.json", json.dumps(kit, ensure_ascii=False, indent=1))
    db.update(vid, payload={"es_short": {"status": "rendered", "file": str(out), **{k: kit[k] for k in ("title", "seconds")}}})
    print(f"[es-short] {vid}: собран {out} ({kit['seconds']} с) — {kit['title']}", flush=True)


def upload(vid: str):
    from googleapiclient.http import MediaFileUpload  # noqa: F401  (тот же клиент, что у роликов)
    from .upload import _once
    from .localize import _yt
    v = db.get(vid); d = db.video_dir(vid); sd = d / "shorts_es"; kit = json.loads(config.read(sd / "studio.json"))
    if not v.get("youtube_id") or not v.get("publish_at"): raise ValueError("ролик ещё не загружен — шортсу не на что ссылаться")
    long_at = datetime.fromisoformat(v["publish_at"]); slot = long_at + timedelta(days=1)   # между роликами, которые идут через день
    now = datetime.now(timezone.utc)
    if slot < now + timedelta(hours=1): slot = now.astimezone(MSK).replace(hour=18, minute=0, second=0, microsecond=0)
    # 15.10: два шортса в один день не ставим (Apple встал на тот же вечер, что Amazon) — следующий свободный вечер 18:00 МСК
    taken = {datetime.fromisoformat(x["payload"]["es_short"]["publish_at"]).astimezone(MSK).date() for x in db.by_status("es_uploaded")
             if x["id"] != vid and (x["payload"].get("es_short") or {}).get("publish_at")}
    while slot < now + timedelta(hours=1) or slot.astimezone(MSK).date() in taken: slot += timedelta(days=1)
    body = {"snippet": {"title": kit["title"], "description": _comment_text(v, {"hook": kit["description"].split(" #shorts")[0]}),
                        "categoryId": "28", "defaultLanguage": "es", "defaultAudioLanguage": "es", "tags": ["shorts", v["payload"]["topic"]["company"]]},
            "status": {"privacyStatus": "private", "publishAt": slot.astimezone(timezone.utc).isoformat(), "selfDeclaredMadeForKids": False,
                       "embeddable": True, "publicStatsViewable": True}}
    done = dict(v["payload"].get("uploads") or {})
    yid = _once(_yt("es"), "short_es.mp4", done, body, sd / "short.mp4")
    sh = dict(v["payload"].get("es_short") or {}); sh.update({"status": "uploaded", "youtube_id": yid, "publish_at": body["status"]["publishAt"]})
    db.update(vid, payload={"uploads": done, "es_short": sh})
    try: telegram.send(f"🇪🇸 Шортс загружен: {kit['title']}\nhttps://www.youtube.com/shorts/{yid} — выход {slot.astimezone(MSK).strftime('%d.%m %H:%M')} МСК")
    except Exception: pass
    print(f"[es-short] {vid}: загружен https://www.youtube.com/shorts/{yid}, выход {slot.astimezone(MSK):%d.%m %H:%M} МСК", flush=True)


def run(vid: str):
    sh = (db.get(vid)["payload"].get("es_short") or {})
    if sh.get("status") not in ("rendered", "uploaded", "blocked"): build(vid)
    if UPLOAD and (db.get(vid)["payload"].get("es_short") or {}).get("status") == "rendered": upload(vid)


def due() -> list[str]:
    """Испанские ролики нового формата, которым шортс ещё нужен (собрать, или загрузить при ES_SHORTS_UPLOAD=1)."""
    out = []
    for v in db.by_status("es_uploaded"):
        if (v["payload"].get("topic") or {}).get("format") != "es_cartoon": continue
        st = (v["payload"].get("es_short") or {}).get("status")
        if st in (None, "") or (st == "rendered" and UPLOAD): out.append(v["id"])
    return out


def comment_tick():
    """Комментарий со ссылкой на ролик под вышедшим шортсом (под закрытым YouTube отвечает 403)."""
    rows = [v for v in db.by_status("es_uploaded") if (v["payload"].get("es_short") or {}).get("status") == "uploaded"
            and not v["payload"]["es_short"].get("comment_id")]
    if not rows: return
    from .localize import _yt
    y = _yt("es")
    for v in rows:
        sh = dict(v["payload"]["es_short"])
        if datetime.fromisoformat(sh["publish_at"]) > datetime.now(timezone.utc): continue
        try:
            st = y.videos().list(part="status", id=sh["youtube_id"]).execute().get("items") or []
            if not st or st[0]["status"]["privacyStatus"] != "public": continue
            kit = json.loads(config.read(db.video_dir(v["id"]) / "shorts_es" / "studio.json"))
            text = _comment_text(v, {"hook": kit["description"].split(" #shorts")[0]})
            c = y.commentThreads().insert(part="snippet", body={"snippet": {"videoId": sh["youtube_id"], "topLevelComment": {"snippet": {"textOriginal": text}}}}).execute()
            sh["comment_id"] = c["id"]; db.update(v["id"], payload={"es_short": sh})
            print(f"[es-short] комментарий под шортсом {sh['youtube_id']}", flush=True)
        except Exception as e: print(f"[es-short] комментарий {v['id']}: {str(e)[-140:]}", flush=True)
