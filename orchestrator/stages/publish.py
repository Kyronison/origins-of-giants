"""Комплект публикации для ручной загрузки в Studio: publish/ — название, описание, теги, закреп, субтитры, карточка полей Studio
и карточки шортсов. Раньше собирался разовым скриптом на каждый ролик (Amazon 18.09); с 19.09 — этап после QC.
Текстовые поля пишет автор текста (LLM_MODEL_WRITER) по готовому сценарию; главы, источники, титры архива и субтитры — кодом.
Ограничения канала: без расширенных функций внешние ссылки в описании не работают — источники названиями, а не URL;
YouTube не разобрал SRT с типографскими кавычками и тире — субтитры в ASCII."""
import json, re
from .. import db, llm, config, series
from .brief import TITLE_BANAL

NICE = {"sec.gov": "SEC filings (10-K, S-1) - sec.gov", "nytimes.com": "The New York Times archive", "wsj.com": "The Wall Street Journal",
        "reuters.com": "Reuters", "bbc.com": "BBC News", "bbc.co.uk": "BBC News", "cnbc.com": "CNBC", "theverge.com": "The Verge",
        "bloomberg.com": "Bloomberg", "ft.com": "Financial Times", "forbes.com": "Forbes", "fortune.com": "Fortune",
        "washingtonpost.com": "The Washington Post", "wired.com": "Wired", "latimes.com": "Los Angeles Times", "time.com": "TIME",
        "economist.com": "The Economist", "businessinsider.com": "Business Insider", "computerhistory.org": "Computer History Museum",
        "microsoft.com": "Microsoft", "news.microsoft.com": "Microsoft News Center", "aboutamazon.com": "Amazon Newsroom",
        "ir.aboutamazon.com": "Amazon Investor Relations", "q4cdn.com": "Annual reports and shareholder letters", "apple.com": "Apple Newsroom", "justice.gov": "U.S. Department of Justice"}
ASCII = {"’": "'", "‘": "'", "“": '"', "”": '"', "—": " - ", "–": "-", "→": "->", "…": "...", " ": " "}
STUDIO = """ПОЛЯ В STUDIO
  Thumbnail ........... thumbnail_2560.jpg (если дневной лимит превью кончился — поставить в расписание без него и добавить завтра)
  Playlist ............ Company Origins
  Audience ............ No, it's not made for kids
  Age restriction ..... No
  Paid promotion ...... No
  Altered content ..... No (решение владельца 20.09, подтверждено 29.09; риск: YouTube может поставить пометку сам)
  Automatic chapters .. On (главы уже в описании)
  Language ............ English (United States), Caption certification: None
  Subtitles ........... subtitles_en.srt -> English -> With timing
  License / Embedding . Standard YouTube License / On
  Category ............ Science & Technology
  Comments ............ On, Hold potentially inappropriate, Sort by Top
  End screen .......... последние 20 с: прошлый ролик канала + Subscribe
  Visibility .......... Schedule, среда / пятница / воскресенье 00:00 МСК (17:00 в Нью-Йорке; с 04.11 — 01:00 МСК)"""
SHORT_FIELDS = """ПОЛЯ В STUDIO
  Audience ............ No, it's not made for kids
  Paid promotion ...... No
  Altered content ..... No
  Category ............ Science & Technology
  Language ............ English (United States)
  Comments ............ On / Basic / Anyone
  Related video ....... если поле открылось — выбрать полный ролик; если нет, ссылка идёт в описание и закреп
  Visibility .......... Schedule, 02:00 МСК, в дни без длинного ролика или через сутки после него"""

PROMPT = """Ты готовишь поля YouTube для англоязычного документального ролика канала Origins of Giants (бренды, которые зритель США знает по названию).
Тема: {working_title}
Тезис: {thesis}
ОБЕЩАНИЕ НАЗВАНИЯ из редакционного брифа: {promise}
Что диктор реально произносит в первые 60 секунд ролика:
{first60}
Варианты названия из сценария: {titles}
Главы (номер части → название и главные события):
{chapters}
Начало сценария (cold open):
{opening}
Финал сценария:
{ending}
Шортсы этого ролика (название → описание):
{shorts}

Правила:
- Все числа, даты, имена и цитаты — ТОЛЬКО из этого текста. Новых фактов не добавлять.
- title: название ролика. Возьми ОБЕЩАНИЕ НАЗВАНИЯ из брифа ДОСЛОВНО, если его утверждение звучит в первые 60 секунд (текст выше).
  Менять его можно, только если оно нарушает правило или не звучит в ролике. Правило: {title_rule}
  Без кликбейта, которого нет в ролике.
- description_hook: 3 абзаца для начала описания — 1) самый сильный поворот истории с точными цифрами; 2) тезис: на чём компания
  на самом деле зарабатывает и когда это решилось; 3) что зритель увидит (4–6 ключевых моментов через запятую). Без ссылок, без хэштегов.
- first_chapter: название первой главы (0:00) до 45 знаков — крючок cold open, не «Intro».
- chapters: для каждой части со 2-й — название главы до 45 знаков ИЗ СОДЕРЖАНИЯ этой части: событие, место, предмет или имя
  («The 1990 strike and the replacement drivers»). Шаблонные слова Origins, The Struggle, The Turning Point, Scale, The Crisis, Legacy
  и конструкция «<Имя части>: …» запрещены: главы не должны совпадать от ролика к ролику.
- tags: 15–20 тегов: компания, основатели, «<Company> history», «<Company> documentary», ключевые продукты и события, «business documentary»,
  «company history», «Origins of Giants».
- pinned: закреплённый комментарий — один неожиданный факт из ролика (2–3 фразы) и КОНКРЕТНАЯ просьба рассказать о личном опыте
  с продуктом компании («Have you ever …? Tell us what it was, which year, and what it cost you.»). Разбор Tech District 27.09:
  просьба о личном опыте даёт комментарии, общее «какую компанию разобрать следующей» — нет.
- hashtags: ровно 3, первый — компания, например ["#Microsoft", "#BillGates", "#Documentary"].
- short_pins: для каждого шортса по порядку — закреп из 1–2 фраз, который ведёт на полный ролик (ссылку добавят сами).
Верни JSON: {{"title":"...","description_hook":"...","first_chapter":"...","chapters":{{"2":"...","3":"..."}},"tags":["..."],"pinned":"...",
"hashtags":["..."],"short_pins":["..."]}}"""


def _ascii(s: str) -> str:
    for a, b in ASCII.items(): s = s.replace(a, b)
    s = re.sub(r"[ \t]{2,}", " ", s)   # «AWS — just» иначе становится «AWS  -  just»
    # 26.09 Verisign: « .com» склеивалось в «$10.97.com» — пробел убираем, только если после знака конец, пробел или закрывающая кавычка/скобка
    return re.sub(r" +([.,;:!?])(?=$|[\s\"')\]])", r"\1", s)

def _ts(t: float) -> str:
    t = int(t); h, m, sec = t // 3600, t // 60 % 60, t % 60
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"

def srt(words: list[dict]) -> str:
    """Субтитры по пословным таймингам: фраза до ~84 знаков, перенос строки посередине, только ASCII."""
    cues, cur = [], []
    def flush():
        if cur: cues.append((cur[0]["s"], cur[-1]["e"], " ".join(w["w"] for w in cur))); cur.clear()
    for w in words:
        if cur and (w["s"] - cur[-1]["e"] > 0.7 or len(" ".join(x["w"] for x in cur)) + len(w["w"]) + 1 > 84): flush()
        cur.append(w)
        if re.search(r"[.!?…][\"”’)]*$", w["w"]) and len(" ".join(x["w"] for x in cur)) >= 28: flush()
    flush()
    def f(t):
        ms = int(round(t * 1000)); return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"
    blocks = []
    for n, (a, b, txt) in enumerate(cues, 1):
        import unicodedata   # остальное (é, ×, ², ₂…) — в ближайший ASCII, иначе assert ниже (Microsoft 19.09)
        txt = unicodedata.normalize("NFKD", _ascii(txt)).encode("ascii", "ignore").decode().strip()
        txt = re.sub(r"^[.,;:!?]\s*", "", txt)                      # знак от предыдущей фразы не должен открывать реплику
        if not txt: continue
        b = max(b, a + 0.9)
        if n < len(cues): b = min(b + 0.25, cues[n][0] - 0.04)
        if len(txt) > 44:
            mid = len(txt) // 2; i = min((i for i, ch in enumerate(txt) if ch == " "), key=lambda i: abs(i - mid)); txt = txt[:i] + "\n" + txt[i + 1:]
        blocks.append(f"{len(blocks) + 1}\n{f(a)} --> {f(b)}\n{txt}\n")
    out = "\n".join(blocks)
    assert all(ord(c) < 128 for c in out), "в субтитрах остались не-ASCII символы"
    return out

def _sources(v: dict) -> list[str]:
    """Источники — только те, на которые реально опирается текст, названиями (без URL), первоисточники первыми."""
    used = set(re.findall(r"\[(F\d+)\]", v["payload"]["script"]["script"]))
    pri = {"10-K": 0, "regulator": 1, "transcript": 2, "press": 3, "interview": 4, "analyst": 5}
    out = []
    for f in sorted(v["payload"]["research"]["facts"], key=lambda f: pri.get(f.get("source_type"), 9)):
        if f["id"] not in used: continue
        dom = re.sub(r"^https?://(www\.)?", "", f.get("source_url") or "").split("/")[0].lower()
        if not dom: continue
        label = NICE.get(dom) or NICE.get(".".join(dom.split(".")[-2:])) or dom
        if label not in out: out.append(label)
    return out[:12]

def _clean_credit(c: str) -> str:
    """Поле Artist с Commons бывает мусорным: имя файла («Jeff_Bezos'_iconic_laugh.jpg: …»), «derivative work: …», описание снимка вместо автора."""
    c = re.sub(r"^[^:;]*\.(?:jpe?g|png|tiff?|svg|webp)\s*:\s*", "", c, flags=re.I)
    c = re.sub(r"\s*derivative work\s*:\s*", ", ", c, flags=re.I)
    c = re.sub(r"^This image uses .*?(\([^)]*\))$", r"NASA \1", c)
    m = re.match(r"^(.{3,60}?)\s*\1(\s*\(.*\))?$", c)   # «Unknown authorUnknown author (…)»
    if m: c = m.group(1) + (m.group(2) or "")
    if len(c) > 90:
        lic = c[c.rfind("("):] if c.endswith(")") else ""
        c = c[:60].rsplit(" ", 1)[0] + (" " + lic if lic else "")
    return c

def _credits(tl: dict) -> tuple[list[str], list[str], list[str]]:
    import html
    yt, wm, web = [], [], []
    for sc in tl["scenes"]:
        for sl in sc.get("slots") or []:
            c = html.unescape((sl.get("credit") or "").strip())
            if not c: continue
            if c.startswith("YouTube:"): yt.append(c[8:].strip())
            elif "Wikimedia Commons" in c: wm.append(_clean_credit(re.sub(r"\s*/\s*Wikimedia Commons\s*", " ", c).strip()))
            elif c.startswith("photo:"): web.append(c[6:].strip())
    u = lambda xs: list(dict.fromkeys(x for x in xs if x))
    return u(yt), u(wm), u(web)

def _numbers(s: str) -> set[str]:
    return {n.rstrip(".,").replace(",", "") for n in re.findall(r"\d[\d.,]*", s)}

def run(vid: str) -> dict:
    v = db.get(vid); d = db.video_dir(vid); out = d / "publish"; out.mkdir(exist_ok=True)
    tl = json.loads(config.read(d / "timeline.json")); words = json.loads(config.read(d / "words.json"))
    s, t = v["payload"]["script"], v["payload"].get("topic") or {}
    outline = {int(o.get("part", i)): o for i, o in enumerate(s.get("outline") or [], 1)}
    pauses = tl.get("pauses") or []
    parts_txt = s.get("parts") or [s["script"]]
    specs = sorted((d / "shorts").glob("s*/short.json"))
    shorts = [json.loads(config.read(p)) for p in specs]
    b = v["payload"].get("brief") or {}
    first60 = " ".join(w["w"] for w in words if float(w.get("s", 0)) < 60)[:1600] or "(озвучки нет)"
    q = PROMPT.format(working_title=t.get("working_title", v["title"]), thesis=t.get("thesis", ""), titles=" | ".join(s.get("title_options", [])),
                   title_rule=series.title_rule(t),
                   promise=b.get("title_promise") or "(в брифе нет — возьми самый конкретный факт первых 60 секунд)", first60=first60,
                   chapters="\n".join(f"{p['part']}. {p.get('name')}: " + "; ".join((outline.get(p["part"]) or {}).get("beats", [])[:4]) for p in pauses),
                   opening=re.sub(r"\[F\d+[^\]]*\]", "", parts_txt[0])[:2500], ending=re.sub(r"\[F\d+[^\]]*\]", "", parts_txt[-1])[-2000:],
                   shorts="\n".join(f"- {x.get('title')}: {x.get('description', '')[:200]}" for x in shorts) or "(шортсов нет)")
    fact_ids = [f["id"] for f in (v["payload"].get("research") or {}).get("facts") or []]
    allowed = _numbers(s["script"]) | _numbers(" ".join(s.get("title_options", []))) | _numbers(t.get("working_title", ""))   # обещание брифа не добавляем: числа названия должны звучать в ролике
    for attempt in range(2):
        r = llm.ask_json(q, heavy=True, max_tokens=4000, tag=f"publish_{vid}", model=config.LLM_MODEL_WRITER or None)
        gen = " ".join([r.get("title", ""), r.get("description_hook", ""), r.get("first_chapter", ""), " ".join((r.get("chapters") or {}).values()), r.get("pinned", "")])
        extra = {n for n in _numbers(gen) - allowed if len(n) > 1}
        banal = bool(TITLE_BANAL.search(_ascii(r.get("title") or "")))
        tbad = series.title_problems(_ascii(r.get("title") or ""), t, fact_ids, b.get("title_facts"))
        if not extra and not banal and not tbad: break
        if tbad:
            print(f"[publish] название «{r.get('title')}»: " + "; ".join(tbad) + (" — переписываю" if not attempt else ""), flush=True)
            q += f"\n\nНазвание «{r.get('title')}» нарушает правило: " + "; ".join(tbad) + ". Исправь именно это."
        if extra:
            print(f"[publish] в полях числа не из сценария {sorted(extra)[:8]}" + (" — переписываю" if not attempt else " — оставлено, проверь вручную"), flush=True)
            q += f"\n\nВ прошлой версии были числа, которых нет в сценарии: {sorted(extra)[:12]}. Убери их."
        if banal:
            print(f"[publish] название «{r.get('title')}» — «история компании»" + (" — переписываю" if not attempt else ""), flush=True)
            q += (f"\n\nНазвание «{r.get('title')}» — «история компании» (How X Started / The Story of / History): запрещено. "
                  "Дай один конкретный факт или конфликт с числом или именем, который звучит в первые 60 секунд.")
    title = _ascii(r.get("title") or s["title_options"][0])[:100]
    if TITLE_BANAL.search(title):   # модель всё же написала «историю компании» — берём обещание брифа как есть
        alt = _ascii(b.get("title_promise") or "").strip()
        if re.search(r"[А-Яа-яЁё]", alt): alt = ""   # обещание не по-английски — в название не годится
        print(f"[publish] название «{title}» — «история компании»" + (f", ставлю обещание брифа: «{alt}»" if alt else " (в брифе обещания нет, оставлено)"), flush=True)
        if alt: title = alt[:100]
    tbad = series.title_problems(title, t, fact_ids, b.get("title_facts"))   # STRATEGY.md раздел 0 (08.10): формула, 55–100 знаков, одно число, источник
    if tbad:
        alt = _ascii(b.get("title_promise") or "").strip()
        if alt and not re.search(r"[А-Яа-яЁё]", alt) and not series.title_problems(alt, t, fact_ids, b.get("title_facts")):
            print(f"[publish] название «{title}» не проходит правило блока ({'; '.join(tbad)}) — ставлю название из брифа: «{alt}»", flush=True)
            title, tbad = alt, []
        else:
            print(f"[publish] название «{title}» не проходит правило блока: {'; '.join(tbad)} — нужно решение владельца", flush=True)
            try:
                from .. import telegram
                telegram.send(f"Название `{vid}` не проходит правило блока:\n«{title}»\n• " + "\n• ".join(tbad) + "\nРолик не остановлен; поправь название перед выходом.")
            except Exception: pass
    chapters = [f"0:00 {_ascii(r.get('first_chapter') or 'The beginning')}"]
    for p in pauses:
        name = (r.get("chapters") or {}).get(str(p["part"])) or p.get("name") or f"Part {p['part']}"
        chapters.append(f"{_ts(p['at'] + 0.4)} {_ascii(name)}")
    yt, wm, web = _credits(tl)
    tags = [_ascii(x) for x in (r.get("tags") or s.get("tags") or [])][:20]
    tags += [x for x in ("business documentary", "company history", "Origins of Giants") if x not in tags]
    while len(", ".join(tags)) > 480: tags.pop(-4)   # лимит поля тегов — 500 знаков
    hashtags = " ".join((r.get("hashtags") or [])[:3]) or "#Documentary"

    def credits_block(max_credits: int = 40) -> str:
        """Атрибуция архива. Владелец 20.09 попросил убрать её из описания — уносим в закреплённый комментарий:
        снимки Commons идут под CC BY / CC BY-SA, где указание автора является условием лицензии, а не вежливостью."""
        cut = lambda xs, sep: sep.join(xs[:max_credits]) + (f"{sep}and others" if len(xs) > max_credits else "")
        credit = []
        if yt: credit.append(f"Footage (YouTube): {cut(yt, ', ')}.")
        if wm: credit.append(f"Photos (Wikimedia Commons, CC BY / CC BY-SA): {cut(wm, '; ')}.")
        if web: credit.append(f"Other photos: {cut(web, ', ')}.")
        credit += ["Stock footage: Pexels.",
                   "Archival material is used for commentary and education. If you hold the rights to anything shown here and want it credited "
                   "differently or removed, reach us through the channel's About page and we'll fix it."]
        return "SOURCES AND ARCHIVAL CREDITS\n\n" + "\n\n".join(credit) + "\n\nSources used in this video:\n" + "\n".join("- " + x for x in _sources(v))

    def desc(max_credits: int) -> str:
        # с 20.09 описание без блоков SOURCES и ARCHIVAL FOOTAGE (решение владельца): только крючок, главы и подписка
        src = _sources(v) if config.DESC_SOURCES else []   # 20.09 владелец убрал источники из описания; возврат — флагом DESC_SOURCES после его «да»
        return "\n\n".join([_ascii(r.get("description_hook") or s.get("description", "")).strip(),
                            "CHAPTERS\n" + "\n".join(chapters)] + (["SOURCES\n" + "\n".join("- " + x for x in src)] if src else []) + [
                            "Origins of Giants tells how the world's biggest companies actually began. Subscribe for the next one.",
                            hashtags])
    n = 60
    text = desc(n)
    while len(text) > 4900 and n > 5: n -= 5; text = desc(n)
    text = text.replace("<", "(").replace(">", ")")   # угловые скобки YouTube в описании не принимает

    config.write(out / "title.txt", title); config.write(out / "description.txt", text)
    pinned = (_ascii(r.get("pinned") or "").strip() + "\n\n" + _ascii(credits_block())).strip()   # атрибуция переехала сюда из описания
    config.write(out / "tags.txt", ", ".join(tags)); config.write(out / "pinned_comment.txt", pinned)
    config.write(out / "subtitles_en.srt", srt(words)); config.write(out / "studio.txt", STUDIO)
    pins = r.get("short_pins") or []
    for i, sh in enumerate(shorts, 1):
        stitle = _ascii(sh.get("title") or f"{title} (Short)")[:100]
        sdesc = (_ascii(sh.get("description") or "").split(" Watch ")[0].strip() + f'\n\nFull documentary on this channel:\n"{title}"\nССЫЛКА_НА_РОЛИК\n\n'
                 + " ".join((r.get("hashtags") or ["#Documentary"])[:1]) + " #Shorts")
        card = (f"ШОРТС {i}   файл: shorts/short_{i}.mp4\n{'=' * 70}\n\nНАЗВАНИЕ ({len(stitle)} знаков)\n{stitle}\n\nОПИСАНИЕ ({len(sdesc)} знаков)\n{sdesc}\n\n"
                f"ТЕГИ\n{', '.join(tags[:8])}\n\nЗАКРЕПЛЁННЫЙ КОММЕНТАРИЙ\n{_ascii(pins[i - 1]) if i <= len(pins) else ''}\nССЫЛКА_НА_РОЛИК\n\n{SHORT_FIELDS}\n")
        config.write(out / f"short_{i}.txt", card)
    meta = {"titles": [title] + [x for x in s.get("title_options", []) if x != title], "tags": tags, "description": text, "title_problems": tbad}
    config.write(d / "meta.json", json.dumps(meta, ensure_ascii=False, indent=2))
    print(f"[publish] {title} | описание {len(text)} из 5000 | тегов {len(tags)} | глав {len(chapters)} | шортсов {len(shorts)} → {out}", flush=True)
    return meta
