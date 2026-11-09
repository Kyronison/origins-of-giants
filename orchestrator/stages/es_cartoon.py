"""Испанский канал Orígenes de Gigantes — СВОЙ конвейер (владелец 13.10.2026: «на новом канале нужно делать совсем по-новому, не брать
ничего из старого канала; чисто картинки с приближением, без логотипа, можно без музыки; кадры меняются очень часто»).

Как у Built On You (разбор их роликов: work/builtonyou/seq_*.jpg; замер смены кадров — в среднем раз в ~4 с, резкая смена, лёгкое
движение внутри кадра; ни титров, ни карточек глав, ни логотипа):
  es_topic    → script(): ресёрч с источниками, план и текст СРАЗУ по-испански (крючок из сегодняшнего дня, затем история по порядку —
                от семьи основателя до наших дней), проверка фактов по ресёрчу → es_scripted
  es_scripted → assets(): озвучка, разбивка текста на «удары» ~10 слов (~4 с), промпт рисунка на каждый удар, ~300 рисунков,
                одна проверка картинок глазами модели и одна перерисовка брака → es_assets
  es_assets   → render(): превью по шаблону 12.10 (cartoon_es.thumb), комплект Studio (cartoon_es.kit), рендер композиции CartoonES,
                громкость −14 LUFS, техпроверка → es_ready (ждёт «да» владельца) → cartoon_es.upload_es → es_uploaded.
С английским конвейером общие только инструменты: вызов моделей, генератор картинок, голос, рендерер."""
import json, re, random, hashlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from .. import config, db, llm, telegram

FORMAT = "es_cartoon"
BEAT_WORDS = 10          # ~4 с испанской речи на одну картинку (замер Built On You: смена раз в 2–5 с)
PARTS = 6

# стиль рисунка — config.CARTOON_STYLE (assets._image(cartoon=True)), утверждён владельцем 13.10 по пробе work/es-cartoon/style_v2

OUTLINE = """Ты автор испаноязычного YouTube-канала «Orígenes de Gigantes» в формате Built On You: «La historia COMPLETA de {company}» —
вся история компании за ~22 минуты одним рассказом. Зритель — Латинская Америка, Испания и испаноязычные США.
Факты (единственный источник; ничего сверх них не утверждать):
{facts}

Составь план из {parts} частей. Устройство ролика:
1) крючок (40–60 секунд): узнаваемая сцена из сегодняшнего дня с компанией и вопрос-загадка, как до этого дошло; без цифр-лавины;
2) дальше строго по порядку времени: откуда основатель (семья, детство, первая работа), как родилась идея, первые годы и первый успех,
   рост, кризисы и ошибки, переломные решения, как компания стала гигантом, что с ней сейчас; финал возвращается к сцене крючка.
Каждая часть — эпоха со своим названием по-испански (2–5 слов, живое, без двоеточий).
Верни JSON: {{"parts": [{{"name": "...", "years": "1964–1986", "beats": ["событие или сцена", "..."], "facts": ["F3", "F7"]}}]}}"""

PART = """Пиши закадровый текст документального мультфильма «La historia COMPLETA de {company}» для канала «Orígenes de Gigantes»
на нейтральном латиноамериканском испанском. Это часть {n} из {total}: «{name}» ({years}).
План всего ролика: {plan}
Сцены этой части: {beats}
Конец предыдущей части (продолжай без повторов): {tail}
Факты (единственный источник: имена, даты, суммы, цитаты — только отсюда; если факта нет — не утверждай):
{facts}

Как писать (манера Built On You): живой рассказ человеку за столом, короткие и средние фразы, конкретные сцены — кто, где, что
сделал; лёгкая ирония; не больше одного-двух чисел на абзац; без тезисов вида «этот фильм доказывает», без лекции о бизнес-модели,
без слов «en este video»; суммы — словами или как «$7.100 millones». Примерно {words} слов (не меньше {min_words}).
Без заголовков, ссылок на факты, ремарок и тегов — только текст, который прочитает диктор.
Верни JSON: {{"text": "..."}}"""

CHECK = """Проверь испанский закадровый текст по фактам. Найди утверждения, которых нет в фактах или которые им противоречат
(даты, суммы, имена, кто что сделал, цитаты). Для каждого дай точную замену: старая фраза дословно из текста → исправленная фраза
(или более осторожная формулировка без неподтверждённой детали). Мелкий пересказ и связки не трогай.
Факты: {facts}

Текст: {text}

Верни JSON: {{"fixes": [{{"old": "фраза дословно", "new": "исправление", "why": "кратко по-русски"}}]}}"""

BOARD = """Ты раскадровщик канала в стиле Built On You. Ниже закадровый текст, разбитый на пронумерованные куски по ~4 секунды.
На КАЖДЫЙ кусок — одна картинка. Компания: {company}. Эпоха части: {years}.
Правила:
- prompt по-английски, 20–45 слов, одна понятная сцена, которая показывает смысл куска (буквально или наглядной метафорой);
- чередуй: сцена с людьми; один предмет на чистой бумаге крупно («a single object on plain off-white paper: ...»); наглядная метафора
  (коробка из шляпы фокусника, весы, лестница, лавина); простая рисованная схема или карта со стрелками;
- обычные люди — «simple round-headed figures»; названный в тексте известный человек — «caricature of <Имя>, <внешность того года>»;
- примерно каждая третья картинка — с короткой надписью В КАВЫЧКАХ ПО-ИСПАНСКИ, заглавными, до 4 слов: реплика в пузыре
  (speech bubble "¡NO PUEDE SER!"), табличка, подпись на схеме; числа в надписях — только из текста;
- одежда, техника, машины, интерьеры — строго той эпохи, назови год или десятилетие в промпте;
- соседние картинки не повторяют один и тот же предмет или ракурс.
Куски:
{beats}
Верни JSON: {{"shots": [{{"n": 1, "prompt": "..."}}]}} — ровно {count} элементов, n от 1 до {count}."""

QA = """Это {n} картинок для рисованного документального ролика на ИСПАНСКОМ (тушь и акварель, человечки с круглыми головами).
Отметь номера картинок, которые нельзя ставить в ролик: надпись не по-испански, с ошибкой, абракадабра или длиннее 6 слов; фотография
или 3D вместо рисунка; уродливые руки и лица; пустая или непонятная картинка; логотип реальной компании крупно.
Верни JSON: {{"bad": [{{"n": 3, "why": "кратко"}}]}} (пустой список, если всё годится)."""


# ---------- очередь ----------

def queue() -> dict | None:
    """Следующая тема из stories_es.txt, по которой ещё нет испанского ролика (ни старого Apple, ни нового конвейера)."""
    used = set()
    for r in db.conn().execute("SELECT payload FROM videos WHERE status != 'rejected'"):
        p = r["payload"] or ""
        if "stories_es.txt" in p or f'"format": "{FORMAT}"' in p:
            m = re.search(r'"ticker":\s*"([A-Z.\-]+)"', p)
            if m: used.add(m.group(1))
    for line in config.read(config.ROOT / "stories_es.txt").splitlines():
        if not line.strip() or line.startswith("#"): continue
        if line.strip().upper().startswith("STOP-OLD"): continue   # заслонка для старого пути (topics.story_queue на ней останавливается)
        if line.strip().upper().startswith("STOP"): break
        parts = [x.strip() for x in line.split("|", 3)]
        if len(parts) < 4 or "already made" in parts[3]: continue
        ticker, name, people, hint = parts
        if ticker not in used:
            return {"ticker": ticker, "company": name, "people": people, "hint": hint.replace("— es-only", "").replace("es-only", "").strip(" —")}
    return None


def start(c: dict) -> str:
    brand = re.sub(r"\s*\(.*?\)", "", c["company"]).strip()
    m = re.search(r"\((.*?)\)", c["company"]); brand = m.group(1) if m and len(m.group(1)) < 20 else brand   # «Inditex (Zara)» → Zara
    topic = {"format": FORMAT, "style": "cartoon", "ticker": c["ticker"], "company": brand, "company_full": c["company"],
             "people": c["people"], "hint": c["hint"], "source": "stories_es.txt", "working_title": f"La historia COMPLETA de {brand}"}
    vid = db.add(re.sub(r"[^a-z0-9]+", "-", f"{c['ticker']}-historia-completa".lower()).strip("-"), topic["working_title"], {"topic": topic})
    db.update(vid, "es_topic")
    print(f"[es] новая тема: {vid} — {topic['working_title']}", flush=True)
    return vid


# ---------- сценарий ----------

def _facts(research: dict) -> str:
    """Keep both web (fact/value) and book (claim/number) evidence intact.

    Source URLs, units, periods and book locators belong to the evidence given
    to the writer and factchecker. Do not filter by truthiness: zero/False are
    meaningful values, and future source metadata must survive this boundary.
    """
    facts = research.get("facts") or []
    if not isinstance(facts, list) or any(not isinstance(f, dict) for f in facts):
        raise ValueError("Ресёрч: facts должен быть списком записей")
    return json.dumps(facts, ensure_ascii=False)


def script(vid: str):
    v = db.get(vid); t = v["payload"]["topic"]; d = db.video_dir(vid)
    research = v["payload"].get("research") or {}
    if len(research.get("facts") or []) < 15:
        research = llm.ask_json(config.prompt("research_story", working_title=f"The complete history of {t['company_full']}",
                                              hero=t.get("people") or t["company"],
                                              thesis="the complete chronological story: founders' background, origin, growth, crises, turning points, today. "
                                                     "Also use the best-known books about the company and its founders: open excerpts, author interviews, reviews quoting them. " + (t.get("hint") or "")),
                                search=True, heavy=True, max_tokens=16000, tag=f"es_research_{vid}")
        research["facts"] = [f for f in research.get("facts", []) if f.get("id") and f.get("source_url")]
        if len(research["facts"]) < 15: raise ValueError(f"Ресёрч дал {len(research['facts'])} фактов с источниками — мало для полной истории")
        db.update(vid, payload={"research": research})
    if not research.get("books_merged"):   # 13.10 владелец присылает книги: data/books/<ТИКЕР>/ — их факты в ресёрч (stages/es_books.py)
        from . import es_books
        bf, titles = es_books.facts(t["ticker"], t["company"], vid)
        if bf:
            keys = [k.lower() for k in re.findall(r"[A-Za-z][A-Za-z]+", t["company"] + " " + (t.get("people") or "")) if len(k) > 3]
            rel = [f for f in bf if any(k in (f.get("claim") or "").lower() for k in keys)] or bf
            step = max(1, len(rel) // 220); rel = rel[::step][:220]   # не больше ~220 фактов книг: план и части должны помещаться в запрос
            research["facts"] = [f for f in research["facts"] if not str(f.get("id", "")).startswith("B")] + rel
            research["books"] = titles
            print(f"[es] книги: {', '.join(titles)} — фактов {len(bf)}, в ресёрч {len(rel)}", flush=True)
        research["books_merged"] = True; db.update(vid, payload={"research": research})
    facts = _facts(research)
    draft_p = d / "es_script_draft.json"
    draft = json.loads(config.read(draft_p)) if draft_p.exists() else {}
    if not draft.get("plan"):
        draft["plan"] = llm.ask_json(OUTLINE.format(company=t["company"], facts=facts, parts=PARTS), heavy=True, max_tokens=6000,
                                     tag=f"es_outline_{vid}", model=config.LLM_MODEL_WRITER or None)["parts"][:PARTS]
        draft["texts"] = []; config.write(draft_p, json.dumps(draft, ensure_ascii=False))
    plan = draft["plan"]
    # 13.10 владелец: «желательно, чтобы они все не были по 21 минуте» — длина своя у каждого ролика: от ~15 до ~27 минут,
    # больше там, где больше фактов (богатая история — длиннее), плюс случайный разброс; число в названии меняется вместе с ней
    if not draft.get("words"):
        rich = min(1.0, len(research.get("facts") or []) / 60)
        draft["words"] = int(round((2200 + 1400 * rich + random.Random(vid).randint(-300, 500)) / 50) * 50)
        config.write(draft_p, json.dumps(draft, ensure_ascii=False))
    total_words = draft["words"]; print(f"[es] длина ролика: ~{total_words} слов (~{total_words / 145:.0f} мин)", flush=True)
    weights = [0.07] + [0.93 / (len(plan) - 1)] * (len(plan) - 1)
    plan_line = " | ".join(f"{i}. {p['name']} ({p.get('years', '')})" for i, p in enumerate(plan, 1))
    tail = "(это начало ролика)"
    for i, p in enumerate(plan, 1):
        if len(draft["texts"]) >= i: tail = " ".join(draft["texts"][i - 1].split()[-80:]); continue
        words = max(150, round(total_words * weights[i - 1]))
        text = llm.ask_json(PART.format(company=t["company"], n=i, total=len(plan), name=p["name"], years=p.get("years", ""), plan=plan_line,
                                        beats="; ".join(p.get("beats") or []), tail=tail, facts=facts, words=words, min_words=int(words * 0.85)),
                            heavy=True, max_tokens=8000, tag=f"es_part{i}_{vid}", model=config.LLM_MODEL_WRITER or None).get("text", "").strip()
        if len(text.split()) < words * 0.5: raise ValueError(f"Часть {i} слишком короткая: {len(text.split())} слов при цели {words}")
        draft["texts"].append(text); config.write(draft_p, json.dumps(draft, ensure_ascii=False))
        tail = " ".join(text.split()[-80:]); print(f"[es] часть {i} «{p['name']}»: {len(text.split())} слов", flush=True)
    texts = list(draft["texts"])
    if not draft.get("checked"):   # проверка фактов по ресёрчу: точечные замены фраз
        def check(i):   # 13.10 владелец «ускорь»: части проверяются параллельно
            tx = texts[i]; n = 0
            r = llm.ask_json(CHECK.format(facts=facts, text=tx), heavy=True, max_tokens=4000, tag=f"es_check{i + 1}_{vid}",
                             model=config.LLM_MODEL_FACTCHECK or None)
            for f in r.get("fixes") or []:
                if f.get("old") and f.get("new") and f["old"] in tx: tx = tx.replace(f["old"], f["new"]); n += 1
            return tx, n
        with ThreadPoolExecutor(len(texts)) as ex: res = list(ex.map(check, range(len(texts))))
        texts = [r[0] for r in res]; n_fix = sum(r[1] for r in res)
        draft["texts"] = texts; draft["checked"] = True; config.write(draft_p, json.dumps(draft, ensure_ascii=False))
        print(f"[es] проверка фактов: исправлено фраз {n_fix}", flush=True)
    s = {"lang": "es", "parts": texts, "names": [p["name"] for p in plan], "years": [p.get("years", "") for p in plan], "script": "\n\n".join(texts)}
    config.write(d / "script.md", f"# {t['working_title']}\n\n" + "\n\n".join(f"## {n}\n\n{tx}" for n, tx in zip(s["names"], texts)))
    db.update(vid, "es_scripted", payload={"script": s})
    print(f"[es] сценарий: {len(s['script'].split())} слов, частей {len(texts)}", flush=True)


# ---------- кадры ----------

def _beats(text: str) -> list[str]:
    """Куски ~BEAT_WORDS слов по границам предложений; длинные предложения режутся по запятым, затем по счёту слов."""
    from .assets import clean_text
    sents = [x for x in re.split(r"(?<=[.!?…])\s+", " ".join(clean_text(text).split())) if x.strip()]
    out, cur = [], []
    def flush():
        if cur: out.append(" ".join(cur)); cur.clear()
    for snt in sents:
        w = snt.split()
        if len(cur) + len(w) <= BEAT_WORDS * 1.4: cur.extend(w)
        else:
            flush()
            if len(w) <= BEAT_WORDS * 1.6: cur.extend(w)
            else:
                pieces = re.split(r"(?<=[,;:])\s+", snt); buf = []
                for pc in pieces:
                    pw = pc.split()
                    if buf and len(buf) + len(pw) > BEAT_WORDS * 1.3: out.append(" ".join(buf)); buf = []
                    buf.extend(pw)
                    while len(buf) > BEAT_WORDS * 1.8: out.append(" ".join(buf[:BEAT_WORDS])); buf = buf[BEAT_WORDS:]
                if buf: cur.extend(buf)
        if len(cur) >= BEAT_WORDS: flush()
    flush()
    return out


def _norm(w: str) -> str:
    import unicodedata
    w = unicodedata.normalize("NFKD", w.lower()); return "".join(ch for ch in w if ch.isalnum())


def _times(beats: list[str], words: list[dict]) -> list[float]:
    """Начало каждого куска по словам озвучки: последовательное сопоставление нормализованных слов."""
    import difflib
    toks, owner = [], []
    for k, b in enumerate(beats):
        for w in b.split():
            n = _norm(w)
            if n: toks.append(n); owner.append(k)
    spoken = [_norm(w["w"]) for w in words]
    sm = difflib.SequenceMatcher(None, toks, spoken, autojunk=False)
    tok2word = {}
    for a, b, n in sm.get_matching_blocks():
        for j in range(n): tok2word[a + j] = b + j
    starts, first = [], {}
    for i, k in enumerate(owner):
        if k not in first and i in tok2word: first[k] = words[tok2word[i]]["s"]
    last = 0.0
    for k in range(len(beats)):
        t = first.get(k)
        if t is None or t < last: t = last + 0.5   # кусок не сопоставился — сразу за предыдущим
        starts.append(round(t, 3)); last = t
    starts[0] = 0.0
    return starts


def _sheet(paths: list[Path]) -> bytes:
    import io
    from PIL import Image, ImageDraw, ImageFont
    w, h, cols = 400, 225, 4; rows = (len(paths) + cols - 1) // cols
    sh = Image.new("RGB", (cols * w, rows * (h + 26)), "white"); dr = ImageDraw.Draw(sh); f = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 20)
    for i, p in enumerate(paths):
        im = Image.open(p).convert("RGB").resize((w, h)); x, y = (i % cols) * w, (i // cols) * (h + 26)
        sh.paste(im, (x, y + 26)); dr.text((x + 4, y + 2), str(i + 1), font=f, fill="black")
    buf = io.BytesIO(); sh.save(buf, "JPEG", quality=82); return buf.getvalue()


def _check_images(vid: str, d: Path, shots: list[dict]) -> dict:
    from . import es_checks
    model = config.LLM_MODEL_VISION_CHEAP or config.LLM_MODEL_VISION
    def ask(batch):
        return llm.ask_vision(QA.format(n=len(batch)), [_sheet([d / x["image"] for x in batch])],
                              tag=f"es_qa_{vid}", model=model)
    report = es_checks.run(d, shots, "es_image_qa", [QA, model, "sheet-400x225-v1"], ask)
    print(f"[es] проверка картинок: {report['status']} {report['counts']}", flush=True)
    es_checks.require_complete(report, "Испанские картинки")
    return report


def assets(vid: str):
    import os
    from . import assets as A
    v = db.get(vid); t = v["payload"]["topic"]; s = v["payload"]["script"]; d = db.video_dir(vid)
    clean_parts = [A.clean_text(p) for p in s["parts"]]
    def voice():   # озвучка не нужна раскадровке и рисункам — идёт параллельно с ними
        old_voice = os.environ.get("ELEVENLABS_VOICE_ID")
        if config.ES_VOICE_ID: os.environ["ELEVENLABS_VOICE_ID"] = config.ES_VOICE_ID   # голос испанского канала, если выбран
        try: A._voice("\n\n".join(clean_parts), d, clean_parts)
        finally:
            if old_voice: os.environ["ELEVENLABS_VOICE_ID"] = old_voice
    pool = ThreadPoolExecutor(1); voice_job = pool.submit(voice)
    try:
        board_p = d / "es_board.json"
        board = json.loads(config.read(board_p)) if board_p.exists() else {"parts": []}
        def plan_part(i):
            beats = _beats(s["parts"][i])
            res = llm.ask_json(BOARD.format(company=t["company"], years=(s.get("years") or [""] * 9)[i], count=len(beats),
                                            beats="\n".join(f"{n}. {b}" for n, b in enumerate(beats, 1))),
                               heavy=True, max_tokens=16000, tag=f"es_board{i + 1}_{vid}", model=config.LLM_MODEL_SHOTS or None)
            got = {int(x.get("n") or 0): x.get("prompt") for x in res.get("shots") or [] if isinstance(x, dict)}
            prompts, prev = [], f"a scene from the story of {t['company']}"
            for n in range(1, len(beats) + 1):
                prev = got.get(n) or prev; prompts.append(prev)
            print(f"[es] раскадровка части {i + 1}: {len(beats)} картинок (без промпта {len(beats) - len(got)})", flush=True)
            return {"beats": beats, "prompts": prompts}
        if len(board["parts"]) < len(s["parts"]):
            todo = list(range(len(board["parts"]), len(s["parts"])))
            with ThreadPoolExecutor(len(todo)) as ex: board["parts"] += list(ex.map(plan_part, todo))
            config.write(board_p, json.dumps(board, ensure_ascii=False, indent=1))
        shots = [{"id": f"p{i + 1}_{k + 1:03d}", "beat": b, "prompt": pr} for i, bp in enumerate(board["parts"]) for k, (b, pr) in enumerate(zip(bp["beats"], bp["prompts"]))]
        (d / "images").mkdir(exist_ok=True)
        def draw(x, suffix=""):
            out = d / "images" / f"{x['id']}{suffix}.png"
            if out.exists(): return out
            r = None
            for attempt in range(2):
                try: return Path(d / A._image(x["prompt"] + (", no text at all" if suffix else ""), d, x["id"] + suffix, config.IMAGE_MODEL, cartoon=True))
                except Exception as e: r = e
            print(f"[es] {x['id']}: картинка не получилась: {str(r)[:120]}", flush=True); return None
        with ThreadPoolExecutor(16) as ex: files = list(ex.map(draw, shots))
        # Finish the concurrent voice before a resumable QA failure can leave the
        # stage. Voice and original/replacement images retain their existing caches.
        voice_job.result()
        for x, f in zip(shots, files):
            x["image"] = f"images/{f.name}" if f else None
        from . import es_checks
        report = _check_images(vid, d, shots)
        bad = es_checks.failed_ids(report)
        # Existing repair budget: one redraw without text; known residual defects
        # remain in the report. A failed model request is UNKNOWN, never clean.
        redo = [x for x in shots if x["id"] in bad]
        with ThreadPoolExecutor(16) as ex:
            for x, f2 in zip(redo, ex.map(lambda x: draw(x, "_r"), redo)):
                if f2: x["image"] = f"images/{f2.name}"
        print(f"[es] картинок {sum(1 for f in files if f)} из {len(shots)}, перерисовано {len(bad)}", flush=True)
        from . import es_celebs
        es_celebs.clean(vid, shots)   # 13.10 владелец: посторонние знаменитости в кадре — «это важно» (в Apple их было на 64 кадрах из 295)
        report = _check_images(vid, d, shots)   # replacements also need a completed verdict
        words = json.loads(config.read(d / "words.json"))
        beats = [x["beat"] for x in shots]; starts = _times(beats, words)
        duration = round(float(words[-1]["e"]) + 1.5, 3)
        rnd = random.Random(vid); moves = ["in", "out", "left", "right", "in", "in"]
        spec_shots = []
        for k, x in enumerate(shots):
            img = x.get("image") or (spec_shots[-1]["image"] if spec_shots else None)
            if not img: continue
            end = starts[k + 1] if k + 1 < len(starts) else duration
            if end - starts[k] < 0.4 and spec_shots: spec_shots[-1]["end"] = round(end, 3); continue
            spec_shots.append({"start": starts[k], "end": round(end, 3), "image": img, "move": rnd.choice(moves)})
        part_starts, k = [], 0
        for bp in board["parts"]: part_starts.append(starts[k] if k < len(starts) else 0.0); k += len(bp["beats"])
        spec = {"duration": duration, "voice": "voice.mp3", "shots": spec_shots, "part_starts": part_starts}
        config.write(d / "es_spec.json", json.dumps(spec, ensure_ascii=False, indent=1))
        db.update(vid, "es_assets", payload={"es_shots": len(spec_shots),
                  "es_image_qa": {"status": report["status"], "counts": report["counts"]}})
        print(f"[es] монтаж: {len(spec_shots)} картинок на {duration / 60:.1f} мин (в среднем {duration / max(1, len(spec_shots)):.1f} с)", flush=True)
    finally:
        pool.shutdown(wait=True)   # keep in-flight voice and its spend inside the stage scope



def _ffmpeg_render(d: Path, spec: dict, out: Path):
    """Монтаж целиком на видеокарте (владелец 13.10: «поставь что-то на видеокарту», RTX 4080): приближение и сдвиг каждого кадра
    считает torch на CUDA (grid_sample, бикубика), готовые кадры идут в ffmpeg и кодируются h264_nvenc; звук — озвучка.
    zoompan в ffmpeg на процессоре давал ~25 кадров/с — в 20 раз медленнее."""
    import subprocess, imageio_ffmpeg, torch
    import torch.nn.functional as F
    from PIL import Image
    import numpy as np
    ff = imageio_ffmpeg.get_ffmpeg_exe(); fps, W, H = 30, 1920, 1080; dev = "cuda" if torch.cuda.is_available() else "cpu"
    total = max(1, round(spec["duration"] * fps))
    proc = subprocess.Popen([ff, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(fps), "-i", "-",
                             "-i", str(d / spec["voice"]), "-map", "0:v", "-map", "1:a", "-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr",
                             "-cq", "20", "-b:v", "0", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out)],
                            stdin=subprocess.PIPE)
    shots = spec["shots"]; written = 0
    try:
        for k, s in enumerate(shots):
            f0 = round(s["start"] * fps) if k else 0
            f1 = round(shots[k + 1]["start"] * fps) if k + 1 < len(shots) else total
            n = max(1, f1 - f0)
            im = np.asarray(Image.open(d / s["image"]).convert("RGB"), dtype=np.uint8)
            src = torch.from_numpy(im).to(dev).permute(2, 0, 1).unsqueeze(0).float() / 255.0
            m = s.get("move") or "in"
            for j0 in range(0, n, 48):
                p = torch.arange(j0, min(n, j0 + 48), device=dev, dtype=torch.float32) / max(1, n - 1)
                if m == "in": z = 1.03 + 0.09 * p
                elif m == "out": z = 1.12 - 0.08 * p
                elif m == "static": z = torch.ones_like(p)
                else: z = torch.full_like(p, 1.08)
                room = 1 - 1 / z   # насколько можно сдвинуть центр, не выходя за край картинки (в координатах [-1, 1])
                tx = (0.5 - p) * room if m == "left" else (p - 0.5) * room if m == "right" else torch.zeros_like(p)
                theta = torch.zeros(len(p), 2, 3, device=dev)
                theta[:, 0, 0] = 1 / z; theta[:, 1, 1] = 1 / z; theta[:, 0, 2] = tx
                grid = F.affine_grid(theta, (len(p), 3, H, W), align_corners=False)
                fr = F.grid_sample(src.expand(len(p), -1, -1, -1), grid, mode="bicubic", padding_mode="border", align_corners=False)
                fr = (fr.clamp(0, 1) * 255).round().to(torch.uint8).permute(0, 2, 3, 1).contiguous().cpu().numpy()
                proc.stdin.write(fr.tobytes()); written += len(p)
        proc.stdin.close()
        if proc.wait() != 0: raise RuntimeError("ffmpeg (nvenc) завершился с ошибкой")
    except Exception:
        proc.kill(); raise
    print(f"[es] монтаж на видеокарте: {len(shots)} картинок, {written} кадров → {out.name}", flush=True)


# ---------- рендер ----------

def render(vid: str):
    import shutil
    from . import render as R, sound, cartoon_es
    from .qc import tech_check
    v = db.get(vid); s = v["payload"]["script"]; d = db.video_dir(vid)
    spec = json.loads(config.read(d / "es_spec.json"))
    tl = {"duration": spec["duration"], "pauses": [{"at": t, "part": i + 1, "name": n} for i, (t, n) in enumerate(zip(spec["part_starts"], s["names"])) if i > 0],
          "overlays": [{"type": "chapter", "n": i + 1, "text": n} for i, n in enumerate(s["names"])]}
    if not (d / "publish" / "thumbnail_2560.jpg").exists(): cartoon_es.thumb(vid, d)
    cartoon_es.kit(vid, d, tl)
    tmp = config.RENDER_TMP; tmp.mkdir(parents=True, exist_ok=True); out = tmp / f"{vid}.mp4"
    _ffmpeg_render(d, spec, out)   # 13.10: ffmpeg + NVENC на RTX 4080 вместо Remotion (тот же монтаж: картинка, приближение, резкая смена)
    loud = tmp / f"{vid}_master.mp4"; sound.master(out, loud); loud.replace(out)
    shutil.move(str(out), str(d / "final.mp4"))
    tech = tech_check(d / "final.mp4", {"duration": spec["duration"], "pauses": []})
    db.update(vid, "es_ready", payload={"tech": tech, "lang": "es"})
    title = config.read(d / "publish" / "title.txt").strip()
    print(f"[es] готово: {d / 'final.mp4'} | {spec['duration'] / 60:.1f} мин | техпроверка: {'; '.join(tech) or 'чисто'}", flush=True)
    try:
        telegram.send(f"🇪🇸 Испанский ролик собран и ждёт «да»: `{vid}`\n{title}", file=d / "publish" / "thumbnail_2560.jpg")
    except Exception: pass
    if config.ES_CARTOON_UPLOAD: cartoon_es.upload_es(vid)
