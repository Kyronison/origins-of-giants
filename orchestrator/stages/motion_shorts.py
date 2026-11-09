"""Моушен-шортсы (владелец 06.10 после лаборатории work/shorts-lab: «больше всего нравятся первые 2 и немного четвёртый»).
Три шаблона Remotion в remotion/src/motion: Blocks («квадраты денег»), Globe (глобус с сетью), Versus (две компании рядом).

Порядок — все проверки ДО платной озвучки и рендера (правило владельца «проверки до рендера»):
  1. plan   — Opus по сценарию, фактам и проверенному архиву ролика пишет N шортсов: шаблон, текст, данные сцен, список чисел;
  2. check  — код сверяет: каждое число текста и данных есть в фактах (или посчитано из них), якоря дословно в тексте,
              фото из архива ролика, точки глобуса — реальные координаты; ошибка → один повтор с перечнем ошибок;
  3. factcheck — Astra по фактам ролика; правка текста → модель заново привязывает якоря к исправленному тексту;
  4. voice  — один дубль ElevenLabs v4 голосом канала; якоря ищутся в пословных таймингах;
  5. render — shorts/motion_N.mp4; рядом shorts/mN/short.json и meta.json (название, описание). Папки sN не трогаем — там сданные шортсы старого формата.
Нет подходящего материала — шортса нет, а не шортс со случайной картинкой."""
import json, math, re, shutil, subprocess, hashlib, os
from pathlib import Path
from .. import db, config, llm
from . import assets as A

TEMPLATES = {"blocks": "Blocks", "globe": "Globe", "versus": "Versus"}
CTA = "Watch the full story on our channel."
CUE_KEYS = ("cue", "endCue", "stampCue", "questionCue", "answerCue", "closingCue", "allCue", "until", "appear", "vanish")


def _norm(t: str) -> str:
    return re.sub(r"[^a-z0-9]", "", t.lower())


def _tokens(text: str) -> list[str]:
    return [x for x in (_norm(w) for w in text.split()) if x]


def _find(tokens: list[str], phrase: str) -> bool:
    p = _tokens(phrase)
    return bool(p) and any(tokens[i:i + len(p)] == p for i in range(len(tokens) - len(p) + 1))


def _cues(obj, out=None) -> list[str]:
    out = [] if out is None else out
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in CUE_KEYS and isinstance(v, str): out.append(v)
            else: _cues(v, out)
    elif isinstance(obj, list):
        for v in obj: _cues(v, out)
    return out


# ── числа ────────────────────────────────────────────────────────────────────────────────────────
_NUM = re.compile(r"\d+(?:,\d{3})*(?:\.\d+)?")

def _fact_numbers(text: str) -> set[float]:
    """Все прочтения чисел факта: «$3,5 млн» (русская запятая) и «$1,321 млн» (тысячи) — оба варианта; млн↔млрд тоже."""
    out = set()
    for m in re.finditer(r"\d+(?:[.,\s]\d+)*", text):
        raw = m.group(0).replace(" ", " ").strip()
        variants = {raw.replace(" ", "").replace(",", ""), raw.replace(" ", "").replace(",", ".")}
        for v in variants:
            if v.count(".") > 1: v = v.replace(".", "")
            try: x = float(v)
            except ValueError: continue
            out |= {x, x * 1000, x / 1000}
    return out


def _close(a: float, b: float, tol: float = 0.015) -> bool:
    return abs(a - b) <= max(tol * max(abs(a), abs(b)), 1e-9)


def _check_numbers(sh: dict, facts: dict) -> list[str]:
    problems, allowed = [], []
    by_id = {f["id"]: f for f in facts.values()}
    pool = set().union(*[_fact_numbers(f"{f.get('date', '')} {f.get('fact', '')} {f.get('value', '')}") for f in facts.values()]) if facts else set()
    pending, errs = list(sh.get("numbers") or []), {}
    for _ in range(4):   # производные могут опираться на другие производные ($540 = 400 + 140 → ×6.9 = 540 / 78)
        rest = []
        for n in pending:
            try: val = float(n.get("value"))
            except (TypeError, ValueError): errs[id(n)] = f"число без значения: {n}"; continue
            if n.get("derived"):
                of = [float(x) for x in n.get("of") or []]
                if len(of) < 2: errs[id(n)] = f"{val}: derived без двух исходных чисел"; continue
                op = n["derived"]
                calc = {"sum": sum(of), "difference": of[0] - sum(of[1:]), "ratio": of[0] / of[1] if of[1] else float("nan"),
                        "share": 100 * of[0] / of[1] if of[1] else float("nan")}.get(op)
                if calc is None or not _close(val, calc, 0.03): errs[id(n)] = f"{val}: {op}{of} = {calc}"; continue
                bad = [x for x in of if not any(_close(x, y) for y in pool) and not any(_close(x, a) for a in allowed)]
                if bad: errs[id(n)] = f"{val}: исходные числа {bad} не найдены в фактах"; rest.append(n); continue
            else:
                f = by_id.get(n.get("fact"))
                if not f: errs[id(n)] = f"{val}: факт {n.get('fact')} не существует"; continue
                if not any(_close(val, y) for y in _fact_numbers(f"{f.get('date', '')} {f.get('fact', '')} {f.get('value', '')}")):
                    errs[id(n)] = f"{val}: в факте {n['fact']} такого числа нет"; continue
            errs.pop(id(n), None); allowed.append(val)
        if len(rest) == len(pending): break
        pending = rest
    problems += list(errs.values())
    def ok(x: float) -> bool:
        return x <= 12 or x == 100 or any(_close(x, a) for a in allowed)
    for m in _NUM.finditer(sh.get("script") or ""):
        raw = m.group(0).strip().rstrip(",.")
        try: x = float(raw.replace(",", "").replace(" ", ""))
        except ValueError: continue
        if not ok(x): problems.append(f"в тексте число {raw} не подтверждено списком numbers")
    def walk(o, path=""):
        if isinstance(o, dict):
            for k, v in o.items():
                if k in ("points", "camera", "lon", "lat", "zoom"): continue
                if k in ("value", "on") and isinstance(v, (int, float)) and not ok(float(v)): problems.append(f"в данных {path}.{k}={v} не подтверждено")
                elif k in ("text", "year", "versus") and isinstance(v, str):
                    for mm in _NUM.finditer(v):
                        try: x = float(mm.group(0).replace(",", "").strip())
                        except ValueError: continue
                        if not ok(x): problems.append(f"в надписи «{v}» число не подтверждено")
                else: walk(v, f"{path}.{k}")
        elif isinstance(o, list):
            for i, v in enumerate(o): walk(v, f"{path}[{i}]")
    walk(sh.get("data") or {})
    return problems


def _check(sh: dict, facts: dict, photos: dict) -> list[str]:
    p = []
    tpl, script, data = sh.get("template"), (sh.get("script") or "").strip(), sh.get("data") or {}
    if tpl not in TEMPLATES: p.append(f"неизвестный шаблон {tpl}")
    n = len(script.split())
    if not 55 <= n <= 105: p.append(f"в тексте {n} слов, нужно 65–95")
    if not script.endswith(CTA): p.append(f"текст должен заканчиваться фразой «{CTA}»")
    if len(sh.get("title") or "") > 60: p.append("название длиннее 60 знаков")
    toks = _tokens(script)
    for c in _cues(data):
        if not _find(toks, c): p.append(f"якоря «{c}» нет в тексте дословно")
    for ph in re.findall(r'"photo":\s*"([^"]+)"', json.dumps(data)):
        if ph not in photos: p.append(f"фото {ph} нет в архиве ролика")
    if tpl == "blocks":
        sc = data.get("scenes") or []
        if not any(s.get("type") == "fill" for s in sc): p.append("blocks без сцены fill")
        if data.get("unit") not in ("M", "B"): p.append("blocks: unit должен быть M или B")
        fills = [st for s in sc if s.get("type") == "fill" for st in s.get("steps") or []]
        top = max([float(st.get("value") or 0) for st in fills] or [0])
        for s in sc:   # 06.10 Pan Am: сравнение больше сетки закрасило её целиком — сумма A должна быть меньше итога сетки B
            if s.get("type") in ("compare", "block") and float(s.get("value") or 0) >= top:
                p.append(f"blocks: {s['type']} {s.get('value')} не меньше итога сетки {top} — большая сумма идёт в fill, меньшая в block/compare")
        if sc and _tokens(sc[0].get("cue") or "")[:1] != toks[:1]:
            p.append("blocks: первая сцена должна начинаться с первого слова текста (иначе пустой экран в начале)")
    if tpl == "globe":
        pts = data.get("points") or {}
        for k, v in pts.items():
            if not (isinstance(v, list) and len(v) == 2 and -180 <= v[0] <= 180 and -90 <= v[1] <= 90): p.append(f"точка {k}: неверные координаты {v}")
        for a, b, g in data.get("lines") or []:
            if a not in pts or b not in pts: p.append(f"линия {a}–{b}: нет точки")
            if g not in (data.get("groups") or {}): p.append(f"линия {a}–{b}: нет группы {g}")
        if not data.get("camera"): p.append("globe без камеры")
        if len(data.get("lines") or []) > 34: p.append("globe: больше 34 линий")
    if tpl == "versus":
        for side in ("left", "right"):
            s = data.get(side) or {}
            if not (0 <= float(s.get("on", -1)) <= 100): p.append(f"versus.{side}.on вне 0..100")
    return p + _check_numbers(sh, facts)


# ── материалы ролика ─────────────────────────────────────────────────────────────────────────────
def _photos(d: Path) -> dict:
    """Проверенные архивные фото ролика (без видео и вставок): id → слот."""
    tl = json.loads(config.read(d / "timeline.json"))
    out = {}
    for s in tl.get("scenes") or []:
        for sl in s.get("slots") or []:
            img = sl.get("image")
            if sl.get("kind") == "archive" and img and not sl.get("src") and sl.get("caption") and sl.get("role") != "inset" and (d / img).exists():
                out.setdefault(sl.get("id") or Path(img).stem, sl)
    return out


def _music(d: Path) -> Path | None:
    moods = {}
    for c in sorted((d / "sound").glob("cues_*.json")):
        try: moods[c.stem.replace("cues_", "theme_")] = (json.loads(config.read(c)).get("sections") or [{}])[0].get("mood")
        except Exception: pass
    themes = sorted((d / "sound").glob("theme_*.mp3"))
    for want in ("tension", "wonder", "mystery"):
        for th in themes:
            if moods.get(th.stem) == want: return th
    return themes[0] if themes else None


def _thumb(d: Path) -> Path | None:
    for c in (d / "publish" / "thumbnail_2560.jpg", d / "thumb_a.png", d / "thumb_2560.png"):
        if c.exists(): return c
    # In-N-Out собирался в отдельной копии: превью лежит в work/*/data/videos/<id>/publish
    return next(iter(sorted((config.ROOT / "work").glob(f"*/data/videos/{d.name}/publish/thumbnail_2560.jpg"))), None)


# ── план ─────────────────────────────────────────────────────────────────────────────────────────
def plan(vid: str, n: int = 3, force: bool = False) -> list[dict]:
    d = db.video_dir(vid); v = db.get(vid); out = d / "shorts" / "motion_plan.json"
    if out.exists() and not force: return json.loads(config.read(out))["shorts"]
    out.parent.mkdir(parents=True, exist_ok=True)
    facts = {f["id"]: f for f in ((v["payload"].get("research") or {}).get("facts") or []) if f.get("id")}
    photos = _photos(d)
    topic = v["payload"].get("topic") or {}
    script = ((v["payload"].get("script") or {}).get("script") or config.read(d / "script.md"))
    script = re.sub(r"\[F\d+\]|</?short>", "", script)
    listing = "\n".join(f"{k} | {sl.get('year') or ''} | {sl.get('caption')} | {sl.get('credit') or ''}" for k, sl in photos.items())
    base = config.prompt("short_motion", long_title=v["title"], company=topic.get("company") or topic.get("working_title") or "", n=n,
                         script=script[:60000], facts="\n".join(f"{k} ({f.get('date')}): {f.get('fact')}" for k, f in facts.items()), photos=listing)
    note, shorts = "", []
    for attempt in range(3):
        res = llm.ask_json(base + note, heavy=True, max_tokens=16000, tag=f"short_motion_{vid}", model=config.SHORT_SCRIPT_MODEL or None)
        shorts = res.get("shorts") or []
        errs = {i: _check(sh, facts, photos) for i, sh in enumerate(shorts)}
        bad = {i: e for i, e in errs.items() if e}
        print(f"[motion] план, попытка {attempt + 1}: шортсов {len(shorts)}, с ошибками {len(bad)}", flush=True)
        if len(shorts) >= n and not bad: break
        note = "\n\nПредыдущий ответ отклонён проверкой. Исправь ВСЕ ошибки и верни полный JSON заново:\n" + \
               "\n".join(f"- шортс {i + 1}: " + "; ".join(e[:8]) for i, e in bad.items()) + \
               (f"\n- нужно {n} шортса, было {len(shorts)}" if len(shorts) < n else "") + "\n\nПредыдущий ответ:\n" + json.dumps(res, ensure_ascii=False)[:30000]
    good = [sh for sh in shorts if not _check(sh, facts, photos)][:n]
    for sh in good: sh["title"] = re.sub(r"\s*[|·—-]\s*Origins of Giants\s*$", "", sh.get("title") or "", flags=re.I)
    if not good: raise RuntimeError("[motion] ни один шортс не прошёл проверку чисел и якорей")
    if config.FACTCHECK:
        good = [_factcheck(vid, sh, facts, photos) for sh in good]
        good = [sh for sh in good if sh]
    config.write(out, json.dumps({"shorts": good}, ensure_ascii=False, indent=1))
    return good


def _factcheck(vid: str, sh: dict, facts: dict, photos: dict) -> dict | None:
    from . import story
    body = sh["script"][: -len(CTA)].strip()
    s = story.factcheck(f"motion_{vid}", {"parts": [body], "script": body}, {"facts": list(facts.values())})
    fixed = (s.get("script") or body).strip()
    if fixed == body: return sh
    print(f"[motion] фактчек поправил текст «{sh.get('title')}» — привязываю сцены заново", flush=True)
    new_script = f"{fixed} {CTA}"
    for _ in range(2):
        res = llm.ask_json("Текст шортса исправлен фактчеком. Верни тот же JSON шортса, но script — ровно новый текст, а якоря, числа и надписи "
                           "приведи в соответствие с ним (якоря дословно из нового текста).\nНовый текст:\n" + new_script +
                           "\n\nСтарый JSON:\n" + json.dumps(sh, ensure_ascii=False), heavy=True, max_tokens=8000, tag=f"short_motion_sync_{vid}",
                           model=config.SHORT_SCRIPT_MODEL or None)
        res = res.get("short") or res
        res["script"] = new_script
        if not _check(res, facts, photos): return res
    print(f"[motion] «{sh.get('title')}» не удалось привязать после фактчека — шортс снят", flush=True)
    return None


# ── озвучка, сборка, рендер ──────────────────────────────────────────────────────────────────────
def _voice(base: Path, text: str, vid: str) -> list[dict]:
    voice_id = os.getenv("ELEVENLABS_VOICE_ID")
    sig = hashlib.sha256(("motion|" + voice_id + "|" + text).encode()).hexdigest()
    if (base / "voice.sha").exists() and (base / "voice.sha").read_text() == sig:
        return json.loads(config.read(base / "words.json"))
    A.TTS_CTX["vid"] = vid
    audio, al = A._tts_fal_v4(A.clean_text(text), voice_id)
    (base / "voice.mp3").write_bytes(audio); A._loudnorm(base / "voice.mp3")
    words = A._words(al, 0)
    config.write(base / "words.json", json.dumps(words)); (base / "voice.sha").write_text(sig)
    return words


def _blocks_counts(data: dict) -> dict:
    """Код, а не модель, решает, сколько квадратов: 1 квадрат = 10^k единиц, чтобы самая большая сумма уместилась в ≤ 600 клеток."""
    sc = data["scenes"]
    vals = [float(s.get("value") or 0) for s in sc if s.get("type") in ("block", "compare")] + [float(st["value"]) for s in sc if s.get("type") == "fill" for st in s["steps"]]
    mx = max(vals); u = 10 ** math.ceil(math.log10(mx / 600)) if mx > 600 else (1 if mx >= 40 else 10 ** math.floor(math.log10(mx / 40)))
    cnt = lambda x: max(1, round(float(x) / u))
    for s in sc:
        if s.get("type") in ("block", "compare"): s["count"] = cnt(s["value"])
        if s.get("type") == "fill":
            for st in s["steps"]: st["count"] = cnt(st["value"])
    money = next((st.get("prefix") for s in sc if s.get("type") == "fill" for st in s["steps"]), "") or ""
    mil = u * (1000 if data.get("unit") == "B" else 1)
    amount = f"{mil / 1000:g} BILLION" if mil >= 1000 else f"{mil:g} MILLION"
    data["unitLabel"] = f"1 SQUARE = {money}{amount}"
    return data


def build(vid: str, n: int = 3, force: bool = False, render: bool = True) -> list[Path]:
    d = db.video_dir(vid); v = db.get(vid)
    shorts = plan(vid, n, force)
    photos = _photos(d); music = _music(d); thumb = _thumb(d)
    outs = []
    for i, sh in enumerate(shorts, 1):
        base = d / "shorts" / f"m{i}"; base.mkdir(parents=True, exist_ok=True)   # не s{i}: там лежат сданные шортсы старого формата
        words = _voice(base, sh["script"], vid)
        toks = [_norm(w["w"]) for w in words]
        missing = [c for c in _cues(sh["data"]) + ["Watch the full"] if not _find(toks, c)]
        if missing: raise RuntimeError(f"[motion] s{i}: после озвучки не найдены якоря {missing}")
        data = json.loads(json.dumps(sh["data"]))
        # фото: id → локальный файл в папке шортса; подпись автора — из архива, а не от модели
        for j, ph in enumerate(sorted(set(re.findall(r'"photo":\s*"([^"]+)"', json.dumps(data))))):
            sl = photos[ph]; ext = Path(sl["image"]).suffix; name = f"photo_{j}{ext}"
            shutil.copy2(d / sl["image"], base / name)
            credit = " · ".join(str(x) for x in (sl.get("caption"), sl.get("credit")) if x)
            def swap(o):
                if isinstance(o, dict):
                    if o.get("photo") == ph: o["photo"] = name; o["credit"] = credit
                    for x in o.values(): swap(x)
                elif isinstance(o, list):
                    for x in o: swap(x)
            swap(data)
        if sh["template"] == "blocks": data = _blocks_counts(data)
        if music: shutil.copy2(music, base / "music.mp3")
        if thumb: shutil.copy2(thumb, base / "thumb.jpg")
        props = {"words": words, "duration": round(words[-1]["e"] + 1.6, 3), "voiceDur": round(A._duration(base / "voice.mp3"), 3), "musicDur": 0,
                 "music": bool(music), "title": v["title"], "data": data}
        config.write(base / "props.json", json.dumps(props, ensure_ascii=False))
        config.write(base / "short.json", json.dumps({"template": sh["template"], "title": sh.get("title"), "description": sh.get("description"),
                                                      "script": sh["script"], "numbers": sh.get("numbers")}, ensure_ascii=False, indent=1))
        credits = sorted({str(sl.get("credit")) for k, sl in photos.items() if k in json.dumps(sh["data"]) and sl.get("credit")})
        config.write(base / "meta.json", json.dumps({"title": sh.get("title"), "description": (sh.get("description") or "") + (f"\n\nPhotos: {', '.join(credits)}" if credits else ""),
                                                     "related_video": v["title"], "template": sh["template"]}, ensure_ascii=False, indent=1))
        # проверка до рендера: один кадр вычисляет все якоря шаблона — ошибка тут, а не посреди рендера
        still = subprocess.run(["npx", "remotion", "still", "src/motion/index.ts", TEMPLATES[sh["template"]], str(base / "frame0.png"), "--props", str(base / "props.json"),
                                "--public-dir", str(base), "--frame", "0", "--log", "error"], cwd=config.ROOT / "remotion", shell=True, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if still.returncode:
            err = re.findall(r"(cue not found: [^\n]+|Error: [^\n]+)", still.stdout + still.stderr)
            raise RuntimeError(f"[motion] s{i}: шаблон не собрался до рендера: {err[:2] or (still.stderr or still.stdout)[-300:]}")
        if render:
            out = d / "shorts" / f"motion_{i}.mp4"
            cmd = ["npx", "remotion", "render", "src/motion/index.ts", TEMPLATES[sh["template"]], str(out), "--props", str(base / "props.json"),
                   "--public-dir", str(base), "--concurrency", "6", "--log", "error"]
            r = subprocess.run(cmd, cwd=config.ROOT / "remotion", shell=True)
            if r.returncode: raise RuntimeError(f"[motion] s{i}: рендер упал ({r.returncode})")
            outs.append(out)
            print(f"[motion] s{i} {sh['template']}: «{sh.get('title')}» → {out.name}, {props['duration']:.1f} с", flush=True)
    return outs


# ── выкладка ─────────────────────────────────────────────────────────────────────────────────────
# Владелец 06.10: «поставь все шортсы в расписание, три из них, по одному к каждому видео, можешь выпускать сразу».
# Квота API — 10 000 единиц в сутки, загрузка — 1 600: девять шортсов за раз не проходят. Поэтому очередь в payload
# видео (motion_queue: файл → «now» или время ISO) и тик в цикле watch: грузит, пока пускает YouTube, остальное — через час.
def enqueue(vid: str, items: list[dict]):
    """items: [{"file": абсолютный путь mp4, "meta": путь meta.json, "at": "now" | ISO UTC}]"""
    q = dict(db.get(vid)["payload"].get("motion_queue") or {})
    for it in items: q[Path(it["file"]).name + "|" + it["file"]] = it
    db.update(vid, payload={"motion_queue": q})


def upload_tick() -> int:
    from . import upload as U
    from datetime import datetime, timezone, timedelta
    from contextlib import closing
    with closing(db.conn()) as c:
        rows = c.execute("SELECT id FROM videos WHERE payload LIKE '%motion_queue%' AND youtube_id IS NOT NULL").fetchall()
    y, n = None, 0
    for r in rows:
        v = db.get(r["id"]); p = v["payload"]; q = p.get("motion_queue") or {}
        done = dict(p.get("uploads") or {}); ids = list(p.get("shorts_ids") or []); sched = dict(p.get("shorts_schedule") or {})
        vmeta_p = db.video_dir(r["id"]) / "meta.json"
        tags = (json.loads(config.read(vmeta_p)).get("tags") if vmeta_p.exists() else None) or []
        url = f"https://www.youtube.com/watch?v={v['youtube_id']}"
        for key, it in sorted(q.items(), key=lambda kv: (kv[1]["at"] != "now", kv[1]["at"])):
            name = "motion:" + key
            if done.get(name): continue
            m = json.loads(config.read(Path(it["meta"])))
            now = datetime.now(timezone.utc)
            at = None if it["at"] == "now" else datetime.fromisoformat(it["at"])
            if at and at < now + timedelta(minutes=20): at = None   # время прошло, пока ждали квоту, — выходит сразу
            desc = "Full story: " + url + "\n\n" + (m.get("description") or "").split("\n\nPhotos:")[0] + "\n\nFull documentary on this channel:\n\"" + \
                   v["title"] + "\"\n" + url + "\n\n#Shorts" + ("\n\n" + m["description"].split("\n\n", 1)[1] if "\n\nPhotos:" in (m.get("description") or "") else "")
            status = {"privacyStatus": "public", "selfDeclaredMadeForKids": False, "containsSyntheticMedia": False} if at is None else \
                     {"privacyStatus": "private", "publishAt": at.isoformat(), "selfDeclaredMadeForKids": False, "containsSyntheticMedia": False}
            body = {"snippet": {"title": (m.get("title") or v["title"])[:100], "description": desc[:4900], "tags": tags[:10], "categoryId": "28",
                                "defaultLanguage": "en", "defaultAudioLanguage": "en"}, "status": status}
            try:
                y = y or U.yt()
                sid = U._once(y, name, done, body, it["file"])
            except U.UploadLimit:
                print("[motion] дневной лимит загрузок канала — продолжу позже", flush=True); return n
            except Exception as e:
                msg = str(e)
                if "quota" in msg.lower() or "403" in msg:
                    print("[motion] квота API YouTube исчерпана — продолжу после сброса", flush=True); return n
                print(f"[motion] загрузка {key}: {msg[:200]}", flush=True); continue
            ids.append(sid); sched[name] = (at or now).isoformat(); n += 1
            db.update(r["id"], payload={"uploads": done, "shorts_ids": ids, "shorts_schedule": sched})
            print(f"[motion] {r['id'][:30]}: {Path(it['file']).name} → {sid} ({'сразу' if at is None else at.isoformat()})", flush=True)
    return n


SHORT_HOURS_ET = (11, 14, 16)   # владелец 07.10 по графику «когда зрители на YouTube»: пик 18:00–24:00 МСК = 11:00–17:00 ET

def slots(after, n: int) -> list:
    """n свободных слотов шортсов по сетке SHORT_HOURS_ET, начиная с суток после after (UTC); занятые слоты всей очереди пропускаются."""
    from . import upload as U
    from datetime import datetime, timedelta, timezone
    taken = U._taken_shorts()
    from contextlib import closing
    with closing(db.conn()) as c:
        prs = [r["payload"] for r in c.execute("SELECT payload FROM videos WHERE payload LIKE '%motion_queue%'")]
    for pr in prs:
        for it in (json.loads(pr).get("motion_queue") or {}).values():
            if it.get("at") and it["at"] != "now": taken.add(datetime.fromisoformat(it["at"]).astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0))
    day = (after.astimezone(U.ET) + timedelta(days=1)).date(); out = []
    now = datetime.now(timezone.utc)
    while len(out) < n:
        for h in SHORT_HOURS_ET:
            u = datetime(day.year, day.month, day.day, h, tzinfo=U.ET).astimezone(timezone.utc)
            if u in taken or u < now + timedelta(minutes=30) or len(out) >= n: continue
            taken.add(u); out.append(u)
        day += timedelta(days=1)
    return out


def enqueue_new(vid: str, release):
    """После загрузки длинного ролика: его моушен-шортсы — в очередь на сутки после выхода (вызывает stages/upload.run)."""
    d = db.video_dir(vid)
    files = sorted((d / "shorts").glob("motion_*.mp4"))
    if not files: return
    ss = slots(release, len(files))
    enqueue(vid, [{"file": str(f), "meta": str(d / "shorts" / ("m" + f.stem.split("_")[-1]) / "meta.json"), "at": s.isoformat()} for f, s in zip(files, ss)])
    print(f"[motion] {vid}: {len(files)} шортсов в очереди: " + ", ".join(f"{s:%d.%m %H:%M}" for s in ss) + " UTC", flush=True)
