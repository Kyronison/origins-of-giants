"""Формат story: история компании и основателя, 32–36 минут (с 19.09; было 22–28). Текст — по частям; раскадровка — типизированные сцены
(docs/scene-grammar.md): entities → подсказки в тексте → сцены broll/people/map/split(+B-типы) → валидация в Python с деградацией,
квоты на часть, один ремонтный вызов, порог остановки. Карточки глав ставит pauses.py, модель их не выдаёт."""
import json, math, re
from .. import db, llm, config, series
from .script import strip_fact_refs, FACT_COLS

SHOT_TARGET, SHOT_MIN, SHOT_MAX = 16, 10, 24   # слов между кадрами broll ≈ 6–7 с при 130–150 слов/мин (референс: 6–10 с)
SHOT_MIN_RICH_AFTER_RICH = 8                   # две богатые сцены подряд могут стоять ближе SHOT_MIN_RICH — первая короче, но обе остаются
MAX_FLASHES = config.MAX_BIG_NUMBERS
SLOT_KEYS = ("source", "query", "query_alt", "media", "caption", "prompt", "focus", "anchor")
NO_PEOPLE = ", no people, no figures, no silhouettes, no faces, hands or objects only, no lettering"
TEXTY_SLOT = re.compile(config.TEXTY_SLOT, re.I)
FACT_TAG = re.compile(r"\[(F\d+)\]")
# нижняя норма слов по частям (середина диапазонов в prompts/story_outline.md): 4 500–5 000 слов ≈ 32–36 мин при TTS_TEMPO ≈ 140 слов/мин
PART_WORDS = {1: 210, 2: 750, 3: 750, 4: 850, 5: 750, 6: 750, 7: 600}

# 29.09 STRATEGY.md, раздел 5: схема вступления блока. Правило идёт в промпт той части, которой касается.
PART_RULES = {
    1: ("ЭТО COLD OPEN. Первая фраза называет героя по имени и говорит то, что обещано в названии ролика, — это первые 10 секунд. "
        f"Во всей части НЕ БОЛЬШЕ {series.NUM_LIMIT_90} ЧИСЕЛ, считая годы и числа словами: масштаб даётся одним-двумя числами, остальные цифры — в следующих частях. "
        "Механизм назови и пообещай, но не объясняй. Последняя фраза — единственный прыжок в начало истории. "
        "Название канала, слово subscribe и любые просьбы к зрителю в этой части НЕ звучат."),
    2: series.CHANNEL_LINE,
}

def write_script(vid: str, research: dict, extra: str = "") -> dict:
    """План и метаданные одним вызовом, затем семь частей отдельными вызовами (модель не держит 4000 слов в одном ответе).
    Возвращает script-словарь без раскадровки."""
    v = db.get(vid); t = v["payload"]["topic"]
    company = f"{t.get('ticker', '')} {t.get('hero') or ''}".strip()
    facts_json = json.dumps(research, ensure_ascii=False)
    # 28.09: черновик на диске — повтор этапа после падения не платит второй раз за план и готовые части (Coca-Cola: 3 сценария с нуля, ~$10)
    import hashlib
    draft_p = db.video_dir(vid) / "script_draft.json"
    parts_plan = series.outline_parts(t); title_rule = series.title_rule(t)   # 29.09 STRATEGY.md: вступление по схеме блока, план частей по типу сюжета
    key = hashlib.sha1((facts_json + extra + str(t.get('words') or config.STORY_WORDS) + t["working_title"] + str(config.LLM_MODEL_WRITER) + parts_plan + title_rule).encode("utf-8")).hexdigest()[:16]
    try: draft = json.loads(config.read(draft_p)) if draft_p.exists() else {}
    except Exception: draft = {}
    if draft.get("key") != key: draft = {"key": key, "parts": []}
    save = lambda: config.write(draft_p, json.dumps(draft, ensure_ascii=False))
    if draft.get("plan"): plan = draft["plan"]; print(f"[story] план из черновика, готовых частей {len(draft['parts'])}", flush=True)
    else:
        plan = llm.ask_json(config.prompt("story_outline", working_title=t["working_title"], company=company, thesis=t.get("thesis", ""),
                                          moods=" | ".join(config.music_moods()), facts_json=facts_json, parts_plan=parts_plan, title_rule=title_rule) + extra,
                            heavy=True, max_tokens=18000, tag=f"outline_{vid}", model=config.LLM_MODEL_WRITER or None)   # 29.09: при 12000 план обрывался и запрашивался дважды
    for k in ("title_options", "description", "tags", "thumbnail_concepts", "outline"):
        if not plan.get(k): raise ValueError(f"В плане нет поля {k}")
    outline = plan["outline"]
    if len(outline) < 6: raise ValueError(f"В плане {len(outline)} частей вместо 7")
    draft["plan"] = plan; save()
    # бюджет слов на весь сценарий, а не квота на каждую часть (разбор 20.09: жёсткие квоты плодят повторы и по два вступления).
    # Доли берём из плана; части, которые план занизил, подтягиваются пропорционально, но сумма всегда равна STORY_WORDS.
    weights = [max(float(p.get("words") or 0), PART_WORDS.get(k, 700) * 0.6) for k, p in enumerate(outline, 1)]
    target_words = int(t.get('words') or config.STORY_WORDS)   # 12.10: у мультфильмов испанского канала своя длина
    budget = target_words * config.WRITER_WORDS_FACTOR
    targets = [max(300, round(budget * w / sum(weights))) for w in weights]
    if targets[0] > series.COLD_OPEN_MAX:   # 29.09 (пробный Greyhound: вступление 290 слов, обещание механизма ушло за 90-ю секунду): лишнее — остальным частям
        surplus = targets[0] - series.COLD_OPEN_MAX; targets[0] = series.COLD_OPEN_MAX   # 30.09: не «extra» — это имя занято добавкой к промпту (Pan Am падал)
        rest = sum(targets[1:]) or 1
        targets[1:] = [t + round(surplus * t / rest) for t in targets[1:]]
    print(f"[story] бюджет {target_words} слов → по частям: {targets}", flush=True)
    parts, tail, used_facts = [], "(это начало рассказа)", []
    for i, part in enumerate(outline, 1):
        words = targets[i - 1]
        short_rule = ("Отметь один сегмент для Shorts тегом <short> … </short> (25–45 сек, самодостаточная сцена)." if i in (2, 4, 6)
                      else "Тег <short> в этой части не нужен.")
        part_rule = PART_RULES.get(i, "")
        ask = lambda note="": llm.ask_json(config.prompt("story_part", working_title=t["working_title"], company=company, thesis=t.get("thesis", ""),
                                         outline_json=json.dumps(outline, ensure_ascii=False), facts_json=facts_json, previous_tail=tail,
                                         part_no=i, part_name=part.get("name", f"Part {i}"), words=words, min_words=int(words * 0.9),
                                         beats="\n".join(f"- {b}" for b in part.get("beats", [])), part_facts=", ".join(part.get("facts", [])) or "—",
                                         bridge=part.get("bridge", ""), short_rule=short_rule, part_rule=part_rule) + extra + note,
                           heavy=True, max_tokens=8000, tag=f"part{i}_{vid}", model=config.LLM_MODEL_WRITER or None)
        count = lambda x: len(re.sub(r"\[F\d+\]|</?short>", "", x).split())
        # что уже прозвучало: без этого части пишутся независимо и повторяют экспозицию (разбор 20.09)
        note = ("\n\nУЖЕ РАССКАЗАНО В ПРЕДЫДУЩИХ ЧАСТЯХ (не объяснять заново, ссылаться одной фразой): " + ", ".join(used_facts)) if used_facts else ""
        cached = draft["parts"][i - 1] if len(draft["parts"]) >= i else None
        text = cached or (ask(note).get("text") or "").strip(); n = count(text)
        if n < words * (0.5 if i > 1 else 0.4): raise ValueError(f"Часть {i} слишком короткая: {n} слов при цели {words}")
        if not cached: draft["parts"] = draft["parts"][:i - 1] + [text]; save()
        parts.append(text); tail = " ".join(text.split()[-120:])
        used_facts += [f for f in re.findall(r"\[(F\d+)\]", text) if f not in used_facts]
        print(f"[story] часть {i} «{part.get('name')}»: {n} слов (цель {words})")
    total_now = sum(len(re.sub(r"\[F\d+\]|</?short>", "", p).split()) for p in parts)
    if total_now < budget * 0.85:   # добираем один раз и только по сценарию целиком, а не по каждой части
        k = max(range(len(parts)), key=lambda j: targets[j] - len(re.sub(r"\[F\d+\]|</?short>", "", parts[j]).split()))
        part, i, words, tail = outline[k], k + 1, targets[k], (" ".join(parts[k - 1].split()[-120:]) if k else "(это начало рассказа)")
        short_rule = ("Отметь один сегмент для Shorts тегом <short> … </short> (25–45 сек, самодостаточная сцена)." if i in (2, 4, 6) else "Тег <short> в этой части не нужен.")
        print(f"[story] сценарий {total_now} слов при бюджете {int(budget)} — дописываю часть {i}", flush=True)
        again = (ask(f"\n\nЭта часть вышла короче плана. Напиши её заново на {words} слов: больше конкретных СОБЫТИЙ, сцен и людей "
                     "из фактов и timeline ресёрча. Никакой воды и повторов уже сказанного.").get("text") or "").strip()
        if len(again.split()) > len(parts[k].split()): parts[k] = again
    script = "\n\n".join(parts)
    s = {k: plan[k] for k in ("title_options", "description", "tags", "thumbnail_concepts")}
    s["music_mood"] = plan.get("music_mood"); s["script"] = script; s["outline"] = outline; s["parts"] = parts
    total = len(re.sub(r"\[F\d+\]|</?short>", "", script).split())
    # 27.09: порог был зашит под старую цель 4500 слов — после STORY_WORDS=3300 (20–24 мин) Coca-Cola браковалась с 3417 словами
    if total < 0.85 * target_words: raise ValueError(f"Сценарий слишком короткий для story: {total} слов (цель {target_words})")
    used = set(re.findall(r"\[(F\d+)\]", script)); ids = {f["id"] for f in research["facts"]}
    if used - ids: raise ValueError(f"Сценарий ссылается на несуществующие факты: {used - ids}")
    if not used: raise ValueError("В сценарии нет ни одной ссылки на факты")
    print(f"[story] всего {total} слов, фактов {len(used)}, shorts {script.count('<short>')}")
    return s

SPOKEN_NUM = re.compile(r"(\d+)\.(\d{3,})(?=\s*(?:billion|million|trillion|percent|%|\b))", re.I)

def round_spoken(text: str) -> str:
    """Числа, которые диктор произносит вслух, — не больше двух знаков после точки.
    Google 20.09: в тексте оказались «$1.465934 billion» и «$3.189223 billion», и голос честно читал
    «one point four six five nine three four billion». Точные значения остаются в описании и источниках."""
    def fix(m):
        whole, frac = m.group(1), m.group(2)
        val = round(float(f"{whole}.{frac}"), 2)
        out = f"{val:.2f}".rstrip("0").rstrip(".")
        return out
    return SPOKEN_NUM.sub(fix, text)

def polish(vid: str, s: dict) -> dict:
    """Вычитка после фактчека (Amazon 18.09): проверка фактов вырезает непроверенные детали и оставляет вместо них пустые обороты,
    дубли между главами и служебные пометки редактора прямо в тексте диктора. Редактор может только удалять, склеивать и
    переформулировать уже сказанное — добавлять факты, числа и даты запрещено, и это проверяется здесь же."""
    before = re.sub(r"\[F\d+\]|</?short>", "", s["script"])
    try:
        res = llm.ask_json(config.prompt("story_polish", parts_json=json.dumps(s["parts"], ensure_ascii=False)),
                           heavy=True, max_tokens=24000, tag=f"polish_{vid}", model=config.LLM_MODEL_POLISH or None)
    except Exception as e:
        print(f"[polish] не удалось, текст оставлен как есть: {str(e)[:90]}"); return s
    parts = [str(x).strip() for x in (res.get("parts") or [])]
    if len(parts) != len(s["parts"]) or any(not x for x in parts):
        print(f"[polish] вернулось {len(parts)} частей вместо {len(s['parts'])} — текст оставлен как есть"); return s
    joined = "\n\n".join(parts)
    after = re.sub(r"\[F\d+\]|</?short>", "", joined)
    nums_b, nums_a = set(re.findall(r"\d[\d.,]*", before)), set(re.findall(r"\d[\d.,]*", after))
    if nums_a - nums_b:
        print(f"[polish] появились новые числа {sorted(nums_a - nums_b)[:8]} — текст оставлен как есть"); return s
    ids_b, ids_a = set(re.findall(r"\[(F\d+)\]", s["script"])), set(re.findall(r"\[(F\d+)\]", joined))
    if ids_a - ids_b:
        print(f"[polish] появились ссылки на чужие факты {ids_a - ids_b} — текст оставлен как есть"); return s
    wb, wa = len(before.split()), len(after.split())
    if wa < wb * 0.75:
        print(f"[polish] текст ужался с {wb} до {wa} слов — слишком много, оставлен как есть"); return s
    for r in (res.get("removed") or [])[:12]: print(f"[polish] убрано: {str(r)[:120]}")
    print(f"[polish] {wb} -> {wa} слов, фактов {len(ids_a)} из {len(ids_b)}", flush=True)
    joined = _unleak(joined); parts = [_unleak(p) for p in parts]
    return {**s, "parts": parts, "script": joined}


LEAK = re.compile(r"\b(?:the|this) (?:supplied|provided|given) (estimate|data|figures?|numbers?)\b", re.I)

def _unleak(text: str) -> str:
    """Служебная отсылка к материалам ресёрча в тексте диктора (Amazon 18.09: «The supplied estimate puts Amazon's take rate…» ушло в озвучку):
    «The supplied estimate» → «One estimate». Остальные варианты — предупреждение в лог, текст не трогаем."""
    def repl(m):
        art, noun = m.group(0).split()[0], m.group(1)
        if noun.lower() in ("estimate", "figure"): return ("One " if art[0].isupper() else "one ") + noun   # «The supplied estimate» → «One estimate»
        return f"{art} {noun}"                                                                              # «the provided data» → «the data»
    fixed = LEAK.sub(repl, text)
    for m in re.finditer(r"\b(?:according to the (?:facts|research|sources provided)|the research (?:shows|says)|per the source)\b", fixed, re.I):
        print(f"[polish] служебная отсылка в тексте диктора: «…{fixed[max(0, m.start() - 40):m.end() + 40]}…»")
    return fixed


# ---------- entities: реестр людей, мест, дат, предметов и цитат (§5.1) ----------

_CITIES: dict | None = None

def _cities() -> dict:
    """orchestrator/data/cities.csv (geonames cities15000) → {имя в нижнем регистре: [строки]}."""
    global _CITIES
    if _CITIES is None:
        import csv
        _CITIES = {}
        with open(config.CITIES_CSV, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                try: r["lat"], r["lon"], r["population"] = float(r["lat"]), float(r["lon"]), int(r["population"] or 0)
                except ValueError: continue
                for key in {r["name"].lower(), r["asciiname"].lower()}: _CITIES.setdefault(key, []).append(r)
    return _CITIES

def _km(lat1, lon1, lat2, lon2) -> float:
    p = math.pi / 180
    a = 0.5 - math.cos((lat2 - lat1) * p) / 2 + math.cos(lat1 * p) * math.cos(lat2 * p) * (1 - math.cos((lon2 - lon1) * p)) / 2
    return 12742 * math.asin(math.sqrt(max(0.0, a)))

def _coords_ok(lat, lon) -> bool:
    try: return -90 <= float(lat) <= 90 and -180 <= float(lon) <= 180 and (float(lat), float(lon)) != (0.0, 0.0)
    except (TypeError, ValueError): return False

def _city_lookup(name: str, country: str | None = None, admin1: str | None = None, near: tuple | None = None, others: list | None = None) -> dict | None:
    """Строка cities.csv по имени + country (+ admin1); при нескольких кандидатах — ближайший к подсказке модели (≤ 200 км),
    иначе ближайший к остальным точкам, иначе самый населённый."""
    rows = _cities().get((name or "").strip().lower()) or []
    if not rows: return None
    if country: rows = [r for r in rows if r["country"].upper() == str(country).upper()] or rows
    if admin1: rows = [r for r in rows if r["admin1"].lower() == str(admin1).lower()] or rows
    if len(rows) == 1: return rows[0]
    if near and _coords_ok(*near):
        best = min(rows, key=lambda r: _km(r["lat"], r["lon"], float(near[0]), float(near[1])))
        if _km(best["lat"], best["lon"], float(near[0]), float(near[1])) <= 200: return best
    if others:
        clat = sum(o[0] for o in others) / len(others); clon = sum(o[1] for o in others) / len(others)
        return min(rows, key=lambda r: _km(r["lat"], r["lon"], clat, clon))
    return max(rows, key=lambda r: r["population"])

def _in_text(name: str, text: str) -> bool:
    name = (name or "").strip()
    return bool(name) and re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)", text, re.I) is not None

def _qtokens(s: str) -> list[str]:
    s = str(s or "").lower().replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"').replace("…", " ")
    return [t for t in re.sub(r"[^a-z0-9']+", " ", s).split() if t]

def _quote_in_text(quote: str, text: str, share: float = 0.8) -> bool:
    """Цитата найдена, если ≥ share её слов идут в тексте подряд (кавычки и многоточия нормализуются)."""
    q, t = _qtokens(quote), _qtokens(text)
    if not q: return False
    n = max(1, math.ceil(len(q) * share)); joined = " " + " ".join(t) + " "
    return any((" " + " ".join(q[i:i + n]) + " ") in joined for i in range(0, len(q) - n + 1))

def _names_of(c: dict) -> list[str]:
    return [n for n in [c.get("name")] + list(c.get("aliases") or []) if n and len(str(n)) > 2]

def _cast_lookup(name: str, entities: dict) -> dict | None:
    n = (name or "").strip().lower()
    for c in entities.get("cast") or []:
        if n and any(n == str(a).lower() for a in _names_of(c)): return c
    for c in entities.get("cast") or []:   # «Paul Jobs» ↔ «Paul and Clara Jobs»: совпадение по фамилии + имени внутри
        parts = n.split()
        if len(parts) >= 2 and all(_in_text(p, c.get("name") or "") for p in parts): return c
    return None

def _gaz_lookup(name: str, entities: dict) -> dict | None:
    n = (name or "").strip().lower()
    for g in entities.get("gazetteer") or []:
        if n and any(n == str(a).lower() for a in _names_of(g)): return g
    return None

def _fact_life_years(person: dict, facts: list[dict]) -> str:
    """Life dates are optional. A generated cast record is not a biographical source."""
    years = str(person.get("years") or "").replace("-", "–").strip()
    if not re.fullmatch(r"\d{4}–(\d{4})?|\d{4}", years): return ""
    # Family biographies can contain other people's dates. Omit optional dates
    # from these ambiguous facts instead of associating any nearby year with the subject.
    texts = [str(f.get('text') or f.get('fact') or '') for f in facts]
    relevant = ' '.join(t for t in texts if _in_text(person['name'],t)
                        and not re.search(r'\b(father|mother|parents?|brother|sister|son|daughter|wife|husband)\b|отец|матер|брат|сестр|сын|доч',t,re.I))
    requested = re.findall(r'\d{4}', years)
    def dated(event,year):
        return re.search(r'(?:'+event+r')(?:(?!\d{4})[^.!?\n]){0,65}\b'+year+r'\b',relevant,re.I)
    if not dated(r'\bborn\b|\bbirth\b|родил\w*|рожд\w*',requested[0]):return ""
    if len(requested)==2 and not dated(r'\bdied\b|\bdeath\b|умер\w*|смерт\w*',requested[1]):return ""
    return years

def write_entities(vid: str, s: dict, research: dict) -> dict:
    """Один дешёвый вызов до раскадровки; всё сверяется с текстом, фактами и cities.csv. Кэш — payload.entities и entities.json."""
    text = s["script"]; facts = research.get("facts", []); fact_ids = {f["id"] for f in facts}
    res = llm.ask_json(config.prompt("story_entities", script=text, facts_json=json.dumps(facts, ensure_ascii=False),
                                     outline_json=json.dumps(s.get("outline") or [], ensure_ascii=False)),
                       heavy=True, max_tokens=8000, tag=f"entities_{vid}")
    ent = {"cast": [], "gazetteer": [], "timeline": [], "objects": [], "quotes": []}
    dropped = []
    for c in res.get("cast") or []:
        if not isinstance(c, dict) or not c.get("name"): continue
        c["aliases"] = [a for a in (c.get("aliases") or []) if isinstance(a, str) and len(a) > 2]
        if not any(_in_text(n, text) for n in _names_of(c)): dropped.append(f"cast {c['name']}"); continue
        c["years"] = _fact_life_years(c, facts)
        c["public"] = bool(c.get("public")); ent["cast"].append(c)
    for g in res.get("gazetteer") or []:
        if not isinstance(g, dict) or not g.get("name"): continue
        g["aliases"] = [a for a in (g.get("aliases") or []) if isinstance(a, str) and len(a) > 2]
        if not any(_in_text(n, text) for n in _names_of(g)): dropped.append(f"place {g['name']}"); continue
        near = (g.get("lat"), g.get("lon")) if _coords_ok(g.get("lat"), g.get("lon")) else None
        row = _city_lookup(g["name"], g.get("country"), g.get("admin1"), near=near)
        if row:
            if near and _km(row["lat"], row["lon"], float(near[0]), float(near[1])) > 50:
                print(f"[entities] {g['name']}: координаты модели {near} далеко от csv ({row['lat']}, {row['lon']}) — беру csv")
            g.update(lat=row["lat"], lon=row["lon"], country=row["country"], admin1=row["admin1"], verified=True)
        elif near:
            g.update(lat=float(g["lat"]), lon=float(g["lon"]), verified=False); print(f"[entities] {g['name']}: нет в cities.csv, координаты модели без сверки")
        else: dropped.append(f"place {g['name']} (нет координат)"); continue
        ent["gazetteer"].append(g)
    years_in_text = set(re.findall(r"\b(1[89]\d\d|20\d\d)\b", text)) | {str(f.get("date") or "")[:4] for f in facts}
    for t in res.get("timeline") or []:
        if not isinstance(t, dict) or not str(t.get("year") or "").isdigit(): continue
        if str(t["year"]) not in years_in_text: dropped.append(f"timeline {t.get('year')} {t.get('label')}"); continue
        if t.get("fact_id") not in fact_ids: t["fact_id"] = None
        ent["timeline"].append(t)
    for o in res.get("objects") or []:
        if not isinstance(o, dict) or not o.get("name"): continue
        o["numbers"] = [n for n in (o.get("numbers") or []) if isinstance(n, dict) and n.get("fact_id") in fact_ids and n.get("text")]
        ent["objects"].append(o)
    for q in res.get("quotes") or []:
        if not isinstance(q, dict) or not q.get("text"): continue
        if not _quote_in_text(q["text"], text): dropped.append(f"quote «{str(q['text'])[:30]}…»"); continue
        if q.get("fact_id") not in fact_ids: q["fact_id"] = None
        ent["quotes"].append(q)
    print(f"[entities] cast {len(ent['cast'])}, places {len(ent['gazetteer'])} ({sum(1 for g in ent['gazetteer'] if g.get('verified'))} по csv), "
          f"timeline {len(ent['timeline'])}, objects {len(ent['objects'])}, quotes {len(ent['quotes'])}" + (f"; отброшено: {', '.join(dropped)}" if dropped else ""))
    # 27.09 Safelite: одинаковый открытый год («1950–») у нескольких людей — заглушка модели, а не факт: снимаем
    from collections import Counter
    yrs = Counter(str(c.get("years") or "").strip() for c in ent.get("cast") or [] if re.fullmatch(r"\d{4}\s*[–-]\s*", str(c.get("years") or "").strip()))
    for c in ent.get("cast") or []:
        y = str(c.get("years") or "").strip()
        if yrs.get(y, 0) >= 2: print(f"[entities] {c.get('name')}: год «{y}» у нескольких людей — заглушка, снимаю", flush=True); c["years"] = ""
    config.write(db.video_dir(vid) / "entities.json", json.dumps(ent, ensure_ascii=False, indent=2))
    return ent

def ensure_entities(vid: str) -> dict:
    """payload.entities, если есть; иначе вызов + сохранение."""
    v = db.get(vid)
    if v["payload"].get("entities"): return v["payload"]["entities"]
    ent = write_entities(vid, v["payload"]["script"], v["payload"].get("research") or {})
    cost = round(float(v["payload"].get("cost_usd", 0)) + llm.take_cost(), 4)
    db.update(vid, payload={"entities": ent, "cost_usd": cost})
    return ent

# ---------- подсказки в тексте (§5.2) ----------

COMPARE_RE = re.compile(r"\b(unlike|rivals?|competitors?|versus|vs\.?|compared (?:to|with)|instead of|then and now|is now a|are now|today,? (?:the|it|that|this)|(?:decades?|years) later,? (?:the|that|it))\b", re.I)
LIST_RE = re.compile(r"(?:\b[\w'’-]+(?: [\w'’-]+){0,3}, ){2,}(?:and|or) ")
NUM_RE = re.compile(r"(?:\$|€|£)?\d[\d,]*(?:\.\d+)?\s?(?:%|percent|million|billion|thousand|trillion|[KMB]\b)?")

def _hints_for(para: str, entities: dict, state: dict) -> dict:
    """Триггеры одного абзаца по entities и регэкспам. PERSON — впервые в части или снова через ≥ PERSON_RESHOW_WORDS (≈ 2 мин);
    state["shown"] помечается при подсказке, а между кусками снимается, если модель так и не дала people (shots_for_text)."""
    h = {"PERSON": [], "PLACE": [], "YEAR": [], "NUMBER": [], "QUOTE": [], "LIST": 0, "COMPARE": ""}
    for c in entities.get("cast") or []:
        if any(_in_text(n, para) for n in _names_of(c)):
            last = state.setdefault("shown", {}).get(c["name"])
            if last is None or state.get("pos", 0) - last >= config.PERSON_RESHOW_WORDS:
                h["PERSON"].append(c); state["shown"][c["name"]] = state.get("pos", 0)
    for g in entities.get("gazetteer") or []:
        if any(_in_text(n, para) for n in _names_of(g)): h["PLACE"].append(g["name"])
    h["YEAR"] = list(dict.fromkeys(re.findall(r"\b(1[89]\d\d|20\d\d)\b", para)))
    if h["YEAR"]: state["year"] = h["YEAR"][-1]
    for m in FACT_TAG.finditer(para):
        nums = NUM_RE.findall(para[max(0, m.start() - 60):m.start()])
        nums = [n for n in nums if re.search(r"\d", n) and not re.fullmatch(r"(1[89]\d\d|20\d\d)", n.strip())]
        if nums: h["NUMBER"].append(f"{nums[-1].strip()} [{m.group(1)}]")
    for q in entities.get("quotes") or []:
        if _quote_in_text(q["text"], para): h["QUOTE"].append(q.get("fact_id") or "—")
    for m in re.finditer(r"[“\"]([^”\"]{20,240})[”\"]\s*(?:\[(F\d+)\])?", para):
        if len(m.group(1).split()) <= 30 and m.group(2) and m.group(2) not in h["QUOTE"]: h["QUOTE"].append(m.group(2))
    lists = [len(m.group(0).split(",")) for m in LIST_RE.finditer(para)]
    if lists and max(lists) >= 3: h["LIST"] = max(lists)
    m = COMPARE_RE.search(para)
    if m: h["COMPARE"] = "then/today" if re.search(r"now|today|later", m.group(0), re.I) else "vs"
    return h

def _hint_line(h: dict) -> str:
    parts = []
    if h["PERSON"]: parts.append("PERSON " + ", ".join(f"{c['name']}" + (f" ({c['role']})" if c.get("role") else "") for c in h["PERSON"]))
    if h["PLACE"]: parts.append("PLACE " + ", ".join(dict.fromkeys(h["PLACE"])))
    if h["YEAR"]: parts.append("YEAR " + ", ".join(h["YEAR"]))
    if h["NUMBER"]: parts.append("NUMBER " + ", ".join(h["NUMBER"]))
    if h["QUOTE"]: parts.append("QUOTE " + ", ".join(h["QUOTE"]))
    if h["LIST"]: parts.append(f"LIST {h['LIST']}")
    if h["COMPARE"]: parts.append(f"COMPARE {h['COMPARE']}")
    return " | ".join(parts)

def _starts_part(para: str, part_starts: list[str] | None) -> bool:
    """Абзац начинает новую часть (первые 4 слова части найдены в нём) — люди показываются «впервые в части» заново."""
    if not part_starts: return False
    from .assets import _norm
    toks = [_norm(w) for w in para.split()]
    for ps in part_starts:
        a = [_norm(w) for w in ps.split()][:4]
        if a and any(toks[i:i + len(a)] == a for i in range(len(toks) - len(a) + 1)): return True
    return False

def _annotate_paras(paras: list[str], entities: dict, state: dict, part_starts: list[str] | None = None) -> tuple[list[tuple[str, dict]], str]:
    """Подсказки для списка абзацев с текущим state (по кускам — чтобы «уже показанные» были из прошлых кусков, а не из всей части)."""
    out = []
    for p in paras:
        if _starts_part(p, part_starts): state["shown"] = {}
        h = _hints_for(p, entities, state); out.append((p, h)); state["pos"] = state.get("pos", 0) + len(p.split())
    text = "\n\n".join((f"⟶ hints: {_hint_line(h)}\n" if _hint_line(h) else "") + p for p, h in out)
    return out, text

def _annotate(part: str, entities: dict, facts: list, state: dict, part_starts: list[str] | None = None) -> tuple[list[tuple[str, dict]], str]:
    """Перед каждым абзацем — «⟶ hints: …». Возвращает [(абзац, hints)] и размеченный текст. state: показанные люди, текущий год."""
    return _annotate_paras([p.strip() for p in re.split(r"\n\s*\n", part) if p.strip()], entities, state, part_starts)

def _chunks(paras: list, limit: int = 300) -> list[list]:
    """Абзацы (строки или пары (абзац, hints)) группируются в куски ≤ limit слов (ответ на 600 слов с типизированными сценами не влезает в max_tokens)."""
    chunks, cur, n = [], [], 0
    for p in paras:
        k = len((p[0] if isinstance(p, tuple) else p).split())
        if cur and n + k > limit: chunks.append(cur); cur, n = [], 0
        cur.append(p); n += k
    if cur: chunks.append(cur)
    return chunks

# ---------- нормализация и валидация сцен (§5.5) ----------

def _normalize_shot(x: dict) -> dict:
    """Плоский shot → broll со слотом; type вне каталога → broll; у слота source/prompt/media по умолчанию; текстовые слоты переписываются."""
    if not isinstance(x.get("slots"), list) or "source" in x:
        slot = {k: x.pop(k) for k in SLOT_KEYS if k in x}
        x["slots"] = [slot] if slot else []
        if x.get("type") not in config.SCENE_TYPES: x["type"] = "broll"
    if x.get("type") not in config.SCENE_TYPES: x["type"] = "broll"
    if not isinstance(x.get("data"), dict): x["data"] = {}
    x.setdefault("motion", "slow push in"); x.pop("transition", None)   # переходы решает Python (§2.12)
    slots = []
    for sl in x["slots"]:
        if not isinstance(sl, dict): continue
        src = str(sl.get("source") or "image").lower()
        sl["source"] = src if src in ("archive", "image", "stock") else "image"
        sl["media"] = str(sl.get("media") or "any").lower()
        if sl["media"] not in ("photo", "video", "any"): sl["media"] = "any"
        q = str(sl.get("query") or "").strip(); sl["query"] = q or None
        sl["prompt"] = str(sl.get("prompt") or "").strip() or (q + ", archival documentary still" if q else "")
        if TEXTY_SLOT.search(f"{q} {sl['prompt']}"):   # доски, графики, заголовки: генератор рисует буквы, архив приносит Yahoo Finance
            sl["prompt"] = TEXTY_SLOT.sub("", sl["prompt"]).strip(" ,") + ", objects of the era on a desk, without lettering"
            sl["caption"] = None; sl["source"] = "image"; sl["query"] = None
        if sl["source"] != "archive": sl["caption"] = None
        if not sl["prompt"] and not sl["query"]: continue
        slots.append(sl)
    x["slots"] = slots
    # «static» у картинки — ноль движения 10 с; статику оставляем только архивному видео (карта — не Slot)
    if str(x.get("motion") or "").lower() == "static" and x["type"] != "map" and not (slots and slots[0]["source"] == "archive" and slots[0]["media"] == "video"):
        x["motion"] = "slow push in"
    return x

def _sentence_at(anchor: str, text: str) -> str:
    """Предложение сценария, на котором стоит якорь (от якоря до .!?; и ещё до 30 слов после — сцена держит несколько фраз)."""
    from .assets import _norm
    a = [w for w in (_norm(w) for w in re.sub(r"\[F\d+\]", "", anchor or "").split()) if w][:4]
    toks = re.sub(r"\[F\d+\]|</?short>", "", text or "").split(); low = [_norm(w) for w in toks]
    i = next((i for i in range(len(low) - len(a) + 1) if a and low[i:i + len(a)] == a), None)
    if i is None: return ""
    j = next((j for j in range(i, min(len(toks), i + 45)) if toks[j][-1:] in ".!?"), min(len(toks) - 1, i + 30))
    return " ".join(toks[i:j + 1])

CARTOON = {"on": False}   # раскадровка мультфильма: выставляется по теме ролика
CARTOON_SHOTS = ("\nСТИЛЬ РОЛИКА — РИСОВАННЫЙ, КАК У КАНАЛА BUILT ON YOU (тушь и акварель, кадр-виньетка на бумаге). Каждый слот — source \"image\", "
                 "никаких archive и stock. Промпт по-английски, 20–45 слов, одна понятная сцена. Чередуй виды кадров: (1) сцена с людьми — названных "
                 "людей рисуй как «caricature of <Имя>, <внешность и одежда того года>», остальные — «simple round-headed figures»; (2) один предмет "
                 "на бумаге крупно («a single object on the paper: ...»); (3) рисованная схема или график от руки с 1–4 короткими подписями. "
                 "Примерно каждый третий кадр — с пузырём реплики или подписью: текст пиши в промпте В КАВЫЧКАХ, ПО-ИСПАНСКИ, заглавными, "
                 "не длиннее 4 слов (speech bubble \"¡QUIERO UNO!\", label \"EL CICLO DE APPLE\"). Числа в надписях — только из текста. "
                 "Год и эпоха — в каждом промпте (одежда, техника, машины того десятилетия).\n")
NO_FIGURE = ", hands and objects only, no face, no person, no figure, no silhouette"

def _no_figures(x: dict, part_text: str, entities: dict):
    """Фраза про человека из cast → сгенерированный кадр не имеет права показывать «двойника» (мужчина в очках паяет = «это Возняк»):
    image-слоты (и запасной prompt архива) получают запрет лиц и фигур и пометку no_people для preflight."""
    if x["type"] in ("people", "map") or not part_text or CARTOON["on"]: return   # мультфильм: шарж на героя разрешён (владелец 12.10)
    sent = _sentence_at(x.get("anchor", ""), part_text)
    who = [c["name"] for c in entities.get("cast") or [] if any(_in_text(n, sent) for n in _names_of(c))]
    if not who: return
    for sl in x.get("slots") or []:
        pr = str(sl.get("prompt") or "")
        if pr and "no person" not in pr: sl["prompt"] = pr.rstrip(". ") + NO_FIGURE
        sl["no_people"] = True; sl["person_in_phrase"] = who[0]

def _degrade(x: dict, reason: str, slot: dict | None = None) -> tuple[dict, str]:
    """Сцена → broll на одном слоте (первом уцелевшем или указанном)."""
    keep = slot or (x["slots"][0] if x.get("slots") else None)
    if keep: keep.pop("role", None)   # роль (portrait/left/inset) больше не действует — у broll слот main
    x["type"] = "broll"; x["slots"] = [keep] if keep else []; x["data"] = {}
    return x, reason

def _next_sentence_anchor(anchor: str, text: str) -> str | None:
    """Первые 5 слов предложения, идущего за предложением с якорем, — своё место для кадра-занятия."""
    from .assets import _norm
    a = [w for w in (_norm(w) for w in re.sub(r"\[F\d+\]", "", anchor or "").split()) if w][:4]
    toks = re.sub(r"\[F\d+\]|</?short>", "", text).split()
    low = [_norm(w) for w in toks]
    i = next((i for i in range(len(low) - len(a) + 1) if a and low[i:i + len(a)] == a), None)
    if i is None: return None
    j = next((j for j in range(i, len(toks)) if toks[j][-1:] in ".!?" and len(toks[j].strip(".!?\"'”’")) > 1), None)
    if j is None or j + 1 >= len(toks): return None
    nxt = toks[j + 1:j + 6]
    return " ".join(nxt) if len(nxt) >= 3 else None

def _activity_broll(x: dict, text: str) -> dict | None:
    """При деградации people → broll иллюстрация занятия (предметы, без людей) не пропадает: отдельный broll на следующей фразе
    («Woz… ham radios» — кадр про радиоприёмник, §7)."""
    p = next((p for p in (x.get("data") or {}).get("persons") or [] if p.get("activity_prompt")), None)
    if not p: return None
    anchor = _next_sentence_anchor(x.get("anchor", ""), text)
    if not anchor: return None
    prompt = str(p["activity_prompt"]).rstrip(". ")
    if "no people" not in prompt: prompt += NO_PEOPLE
    return {"id": f"{x['id']}a", "anchor": anchor, "type": "broll", "part": x.get("part"), "motion": "zoom to detail", "data": {},
            "slots": [{"source": "image", "query": None, "query_alt": None, "media": "photo", "caption": None, "prompt": prompt, "focus": "objects"}]}

def _same_rich(a: dict | None, b: dict) -> bool:
    """Одинаковые богатые типы подряд запрещены — кроме people про разных людей (Woz после родителей)."""
    if not a or a.get("type") == "broll" or a.get("type") != b.get("type"): return False
    if a["type"] != "people": return True
    na = {p.get("name") for p in (a.get("data") or {}).get("persons") or []}; nb = {p.get("name") for p in (b.get("data") or {}).get("persons") or []}
    return not na or not nb or bool(na & nb)

def _person_slot(p: dict, c: dict | None) -> dict:
    q = (c or {}).get("portrait_query") or p["name"]
    return {"source": "archive", "query": q, "query_alt": f"{p['name']} portrait", "media": "photo", "caption": p["name"], "prompt": p.get("activity_prompt") or ""}

def _portrait_queries(c: dict | None, name: str, year: str | None) -> tuple[str, str]:
    """Запрос портрета по эпохе сцены: до 1990 — era_queries.young (Commons «Steve Wozniak 1977» есть, интервью 1984 под «age eleven» — нет),
    иначе later; общий portrait_query — запасной."""
    c = c or {}; eq = c.get("era_queries") or {}
    base = c.get("portrait_query") or name
    y = int(year) if year and str(year).isdigit() else None
    era = (eq.get("young") if y is None or y < 1990 else eq.get("later")) or ""
    return (era, base) if era and era != base else (base, f"{name} portrait")

def _validate_quote(x: dict, part_text: str, entities: dict, year: str | None = None) -> tuple[dict, str | None]:
    """Цитата-сцена (владелец 21.09): портрет автора + текст, который печатается вслед за голосом. Только дословная цитата из текста части,
    автор — из cast; портрет ищется и проверяется так же, как у people (role=portrait, person, verify_portraits). Иначе → broll."""
    dd = x["data"]; text = str(dd.get("text") or "").strip().strip("\"“”")
    if not text or len(text.split()) > 30: return _degrade(x, "quote: нет текста или длиннее 30 слов")
    if not _quote_in_text(text, part_text): return _degrade(x, "quote: цитаты нет в тексте части дословно")
    c = _cast_lookup(str(dd.get("who") or ""), entities)
    if not c: return _degrade(x, f"quote: автора «{dd.get('who')}» нет в cast")
    p = {"name": c["name"], "role": c.get("role") or "", "years": c.get("years") or "", "portrait": 0}
    sl = x["slots"][0] if x["slots"] and isinstance(x["slots"][0], dict) else _person_slot(p, c)
    sl["source"] = "archive"; sl["role"] = "portrait"; sl["media"] = "photo"
    q, q_alt = _portrait_queries(c, c["name"], year)
    sl["query"], sl["query_alt"] = q, q_alt; sl["caption"] = c["name"]; sl["person"] = c["name"]; sl["era_year"] = year; sl["years"] = c.get("years") or ""
    x["slots"] = [sl]
    x["data"] = {"text": text, "who": c["name"], "role": p["role"], "year": str(dd.get("year") or "").strip(), "persons": [p]}
    x["anchor"] = text   # сцена стартует на первом слове цитаты: текст печатается вслед за голосом с первой секунды (McDonald's 22.09: якорь стоял за 7 с до цитаты)
    return x, None

def _validate_people(x: dict, part_text: str, entities: dict, year: str | None = None) -> tuple[dict, str | None]:
    persons = [p for p in (x["data"].get("persons") or []) if isinstance(p, dict) and p.get("name")][:3]
    slots = list(x["slots"]); pairs, dropped = [], []
    for i, p in enumerate(persons):
        c = _cast_lookup(p["name"], entities)
        if c:
            p["name"] = c["name"]; p["years"] = c.get("years") or ""
            if not p.get("role"): p["role"] = c.get("role") or ""
        elif _in_text(p["name"], part_text): p["years"] = ""
        else: dropped.append(p["name"]); continue
        role = str(p.get("role") or "").strip()
        ap = str(p.get("activity_prompt") or "").strip() or (f"close-up of the tools and objects of a {role}, hands only" if role else "close-up of everyday objects of the era on a wooden table")
        p["activity_prompt"] = ap.rstrip(".") + NO_PEOPLE
        sl = slots[i] if i < len(slots) and isinstance(slots[i], dict) else _person_slot(p, c)
        sl["source"] = "archive"; sl["role"] = "portrait"
        q, q_alt = _portrait_queries(c, p["name"], year)
        sl["query"], sl["query_alt"] = q, sl.get("query_alt") or q_alt   # запрос модели уступает реестру: эпоха портрета — по году сцены
        sl["caption"] = p["name"]; sl["person"] = p["name"]; sl["era_year"] = year; sl["years"] = p.get("years") or ""
        if not sl.get("prompt"): sl["prompt"] = p["activity_prompt"]
        pairs.append((p, sl))
    if not pairs: return _degrade(x, f"people: персон нет в cast и тексте ({', '.join(dropped) or 'пусто'})")
    sides = {1: ["center"], 2: ["left", "right"], 3: ["left", "center", "right"]}[len(pairs)]
    given = [str(p.get("side") or "").lower() for p, _ in pairs]
    if sorted(given) != sorted(sides):
        for (p, _), sd in zip(pairs, sides): p["side"] = sd
    x["data"] = {"layout": {1: "solo", 2: "duo", 3: "trio"}[len(pairs)], "persons": [p for p, _ in pairs]}
    x["slots"] = [sl for _, sl in pairs]
    return x, (f"people: выброшены {', '.join(dropped)}" if dropped else None)

def _validate_map(x: dict, entities: dict) -> tuple[dict, str | None]:
    d = x["data"]; pts = [p for p in (d.get("points") or []) if isinstance(p, dict) and p.get("name")][:5]
    valid, idx_map, dropped = [], {}, []
    known = [(float(g["lat"]), float(g["lon"])) for g in entities.get("gazetteer") or []]
    for i, p in enumerate(pts):
        g = _gaz_lookup(p["name"], entities)
        if g:
            p.update(name=g["name"], lat=g["lat"], lon=g["lon"], country=g.get("country"), admin1=g.get("admin1"))
        else:
            near = (p.get("lat"), p.get("lon")) if _coords_ok(p.get("lat"), p.get("lon")) else None
            row = _city_lookup(p["name"], p.get("country"), p.get("admin1"), near=near, others=known or None)
            if not row: dropped.append(p["name"]); continue
            p.update(lat=row["lat"], lon=row["lon"], country=row["country"], admin1=row["admin1"])
        p["label"] = str(p.get("label") or "")[:40]; idx_map[i] = len(valid); valid.append(p)
    if len(valid) < 2:
        inset = x["slots"][0] if x["slots"] else None
        city = (valid or pts or [{"name": ""}])[0]["name"]
        if not inset and city: inset = {"source": "archive", "query": f"{city} aerial 1970s", "query_alt": f"{city} street 1960s", "media": "photo", "caption": city, "prompt": f"aerial view of a mid-century town, {city}, faded color photo"}
        return _degrade(x, f"map: валидных точек {len(valid)} < 2" + (f" (нет в базе: {', '.join(dropped)})" if dropped else ""), inset)
    route = d.get("route")
    if isinstance(route, list):
        route = [idx_map[i] for i in route if isinstance(i, int) and i in idx_map]
        if len(route) < 2: route = None
    else: route = None
    if not any(p.get("main") for p in valid): valid[0]["main"] = True
    label = str(d.get("distance_label"))[:30] if d.get("distance_label") else None
    if label and route:   # «a few miles» на дуге SF → Mountain View (46 км) — подпись врёт: сверяем с длиной маршрута
        km = sum(_km(valid[a]["lat"], valid[a]["lon"], valid[b]["lat"], valid[b]["lon"]) for a, b in zip(route, route[1:]))
        if not _distance_ok(label, km): print(f"[shots] {x['id']} map: подпись «{label}» не про маршрут ({km:.0f} км) — убрана"); label = None
    elif label and not route: label = None
    x["data"] = {"title": str(d.get("title") or valid[0].get("admin1") or "")[:40], "zoom": d.get("zoom") if d.get("zoom") in ("region", "country", "world") else "region",
                 "points": valid, "route": route, "distance_label": label}
    x["slots"] = x["slots"][:1]
    for sl in x["slots"]:   # inset — только фото Commons (город подтверждается названием файла); видео-раскадровка приносила зоопарк Окленда как «Mountain View»
        sl["role"] = "inset"; sl["media"] = "photo"
    return x, (f"map: выброшены точки {', '.join(dropped)}" if dropped else None)

def _distance_ok(label: str, km: float) -> bool:
    """Подпись расстояния совпадает с маршрутом: «a few miles» ≤ 15 км, «N miles/km» — в пределах ±40 %; иначе не наша фраза."""
    t = label.lower()
    m = re.search(r"(\d[\d,.]*)\s*(miles?|mi\b|km|kilomet)", t)
    if m:
        try: v = float(m.group(1).replace(",", ""))
        except ValueError: return True
        want = v * (1.609 if m.group(2).startswith(("mi",)) else 1.0)
        return abs(km - want) <= max(3.0, 0.4 * want)
    if re.search(r"\b(a few|few|couple|short|nearby|next door|down the road)\b", t): return km <= 15
    if re.search(r"\b(across|cross-country|coast to coast|overseas|halfway)\b", t): return km >= 500
    return True

def _validate_split(x: dict) -> tuple[dict, str | None]:
    d = x["data"]; slots = x["slots"]
    if len(slots) < 2: return _degrade(x, f"split: слотов {len(slots)} вместо 2")
    slots = slots[:2]
    mode = str(d.get("mode") or "vs").lower()
    if mode not in ("vs", "then_now"): mode = "vs"
    labels = []
    for side, sl in zip(("left", "right"), slots):
        lab = (d.get(side) or {}).get("label") if isinstance(d.get(side), dict) else d.get(side)
        lab = str(lab or sl.get("caption") or sl.get("query") or "").strip()
        if not lab: return _degrade(x, f"split: пустая подпись {side}")
        labels.append(lab[:40]); sl["role"] = side
    x["data"] = {"mode": mode, "left": {"label": labels[0]}, "right": {"label": labels[1]}, "stakes": (str(d["stakes"])[:60] if d.get("stakes") else None)}
    x["slots"] = slots
    return x, None

NO_MODERN = "no modern devices, no screens, no modern clothing"

def era_clause(year, prompt: str = "") -> str:
    """Что дописать к prompt генерации по году сцены: десятилетие (если в prompt его нет) и запрет современных вещей для сцен до
    MODERN_ERA_FROM — планшет у подростка 1971 года дешевле не рисовать, чем ловить в preflight. Год неизвестен → только запрет."""
    y = str(year or "")
    parts = []
    if re.fullmatch(r"(1[89]|20)\d\d", y) and not re.search(r"\b(1[89]|20)\d\d(s)?\b", prompt): parts.append(f"{y[:3]}0s")
    if not re.fullmatch(r"(1[89]|20)\d\d", y) or int(y) < config.MODERN_ERA_FROM: parts.append(NO_MODERN)
    return ", ".join(parts)

def _year_near(anchor: str, text: str, fallback) -> str | None:
    """Год сцены: последний год, названный в тексте до якоря (в пределах ~600 символов), иначе первый после, иначе текущий год state."""
    from .assets import _norm
    a = [w for w in (_norm(w) for w in re.sub(r"\[F\d+\]", "", anchor or "").split()) if w][:3]
    toks = text.split(); low = [_norm(w) for w in toks]
    i = next((i for i in range(len(low) - len(a) + 1) if a and low[i:i + len(a)] == a), None)
    if i is None: return fallback
    j = next((j for j in range(i, min(len(toks), i + 45)) if toks[j][-1:] in ".!?"), min(len(toks), i + 45))   # своё предложение — в приоритете
    sent = " ".join(toks[i:j + 1]); before = " ".join(toks[max(0, i - 110):i]); after = " ".join(toks[j:j + 40])
    Y = r"\b(1[89]\d\d|20\d\d)\b"
    ys = re.findall(Y, sent) or re.findall(Y, before) or re.findall(Y, after)
    return ys[-1] if ys else fallback

def _era_prompts(x: dict, state: dict, part_text: str = ""):
    """Слотам, которые могут уйти в генерацию (image, запасной prompt archive), дописываем эпоху сцены (год по тексту у якоря)."""
    year = _year_near(x.get("anchor", ""), part_text, state.get("year")) if part_text else state.get("year")
    for sl in x.get("slots") or []:
        pr = str(sl.get("prompt") or "")
        if not pr or "no modern devices" in pr: continue
        clause = era_clause(year, pr)
        if clause: sl["prompt"] = pr.rstrip(". ") + ", " + clause

def _validate_shot(x: dict, part_text: str, entities: dict, facts: list, state: dict) -> tuple[dict, str | None]:
    """По типу; провал → broll с причиной. Типы вне SCENE_TYPES_ENABLED (фаза B) → broll на первом слоте, object → flash из первой выноски."""
    t = x["type"]
    _era_prompts(x, state, part_text)
    if not x["slots"] and t in ("broll", "people", "split", "montage", "quote", "object"):
        return _degrade(x, f"{t}: слотов нет")
    if t not in config.SCENE_TYPES_ENABLED:
        if t == "object":
            ids = {f["id"] for f in facts}
            for c in x["data"].get("callouts") or []:
                if isinstance(c, dict) and c.get("fact_id") in ids and re.search(r"\d", str(c.get("text") or "")):
                    x.setdefault("_overlays", []).append({"type": "flash", "anchor": x.get("anchor"), "value": str(c["text"]), "label": str(c.get("note") or ""), "fact_id": c["fact_id"], "seconds": 3}); break
        return _degrade(x, f"{t}: тип не включён (фаза B)")
    if t == "people": return _validate_people(x, part_text, entities, _year_near(x.get("anchor", ""), part_text, state.get("year")) if part_text else state.get("year"))
    if t == "map": return _validate_map(x, entities)
    if t == "quote": return _validate_quote(x, part_text, entities, _year_near(x.get("anchor", ""), part_text, state.get("year")) if part_text else state.get("year"))
    if t == "split": _no_figures(x, part_text, entities); return _validate_split(x)
    x["slots"] = x["slots"][:1]; x["data"] = {k: v for k, v in x["data"].items() if k == "subject"}
    _no_figures(x, part_text, entities)
    return x, None

WORDNUM = {"one-third": 1 / 3, "one third": 1 / 3, "a third": 1 / 3, "two-thirds": 2 / 3, "two thirds": 2 / 3, "three-quarters": 0.75, "a quarter": 0.25, "one-quarter": 0.25, "half": 0.5}
MULT = {"k": 1e3, "thousand": 1e3, "m": 1e6, "mn": 1e6, "million": 1e6, "b": 1e9, "bn": 1e9, "billion": 1e9, "t": 1e12, "tn": 1e12, "trillion": 1e12}

def _num(s) -> float | None:
    """«$85.2B», «70%», «$666.66», «1,000», «one-third» → float (множители K/M/B/T)."""
    if s is None: return None
    if isinstance(s, (int, float)): return float(s)
    t = str(s).lower().strip()
    for k, v in WORDNUM.items():
        if k in t: return v
    m = re.search(r"(\d[\d,]*(?:\.\d+)?)\s*(%|percent|thousand|million|billion|trillion|bn|mn|tn|[kmbt]\b)?", t)
    if not m: return None
    try: v = float(m.group(1).replace(",", ""))
    except ValueError: return None
    return v * MULT.get((m.group(2) or "").strip(), 1)

# ---------- квоты, ремонт, сводка ----------

def _part_of(x: dict) -> int:
    m = re.match(r"v(\d+)_", str(x.get("id") or ""))
    return int(x.get("part") or (m.group(1) if m else 0))

def _missing_people(shots: list[dict], hints: list[dict], entities: dict) -> list[str]:
    """PERSON из подсказок, кому модель так и не дала people (публичные фигуры — с портретом на Commons): в ремонт по именам."""
    made = {p.get("name") for x in shots if x["type"] == "people" for p in (x.get("data") or {}).get("persons") or []}
    out = []
    for h in hints:
        for c in h["PERSON"]:
            if c["name"] not in made and c["name"] not in out and (_cast_lookup(c["name"], entities) or {}).get("public", True): out.append(c["name"])
    return out

def _needs(shots: list[dict], hints: list[dict], part_no: int, entities: dict | None = None) -> dict:
    """Чего не хватает части после валидации: people на каждые 2 PERSON и на каждого подсказанного, но не показанного публичного человека
    (Steve Jobs без портрета при двух упоминаниях — брак), map при ≥ 2 PLACE, богатых сцен ≥ RICH_MIN_PER_PART."""
    if part_no < 2: return {}
    have = {}
    for x in shots: have[x["type"]] = have.get(x["type"], 0) + 1
    n_person = len({c["name"] for h in hints for c in h["PERSON"]}); places = {p for h in hints for p in h["PLACE"]}
    need = {}
    en = config.SCENE_TYPES_ENABLED
    if "people" in en and n_person and have.get("people", 0) < min(3, math.ceil(n_person / 2)): need["people"] = min(3, math.ceil(n_person / 2)) - have.get("people", 0)
    missing = _missing_people(shots, hints, entities or {}) if "people" in en else []
    if missing and have.get("people", 0) + need.get("people", 0) < config.RICH_MAX_PER_VIDEO["people"]: need["people"] = max(need.get("people", 0), min(2, len(missing)))
    if "map" in en and len(places) >= 2 and not have.get("map"): need["map"] = 1
    rich = sum(v for t, v in have.items() if t != "broll") + sum(need.values())
    if rich < config.RICH_MIN_PER_PART:
        if "split" in en and any(h["COMPARE"] for h in hints) and not have.get("split"): need["split"] = 1
        elif "people" in en and n_person: need["people"] = need.get("people", 0) + 1
    return need

def _cap_rich(shots: list[dict], downgrades: list[dict], part_no: int, text: str = ""):
    """Верхние квоты части: ≤ RICH_MAX_PER_PART по типу, одинаковые богатые типы подряд (кроме people про других людей) → второй в broll,
    богатых ≤ RICH_MAX_SHARE. people при деградации оставляет иллюстрацию занятия отдельным broll на следующей фразе."""
    seen, prev, extra = {}, None, []
    def drop(x, reason):
        t = x["type"]
        act = _activity_broll(x, text) if t == "people" and text else None
        _degrade(x, reason); downgrades.append({"id": x["id"], "from": t, "why": reason}); print(f"[shots] {x['id']} {t}→broll: {reason}")
        if act: extra.append((x, act)); print(f"[shots] {act['id']}: занятие сохранено отдельным broll на «{act['anchor']}»")
    for x in shots:
        t = x["type"]
        if t == "broll": prev = None; continue
        seen[t] = seen.get(t, 0) + 1
        reason = None
        if seen[t] > config.RICH_MAX_PER_PART.get(t, 99): reason = f"{t}: больше {config.RICH_MAX_PER_PART[t]} на часть"
        elif _same_rich(prev, x): reason = f"{t}: тот же богатый тип подряд"
        if reason: drop(x, reason)
        else: prev = x
    rich = [x for x in shots if x["type"] != "broll"]
    over = len(rich) - int(len(shots) * config.RICH_MAX_SHARE)
    for x in rich[::-1][:max(0, over)]: drop(x, "богатых сцен больше половины")
    for x, act in extra: shots.insert(shots.index(x) + 1, act)

def _candidates(paras: list[tuple[str, dict]], need: dict, entities: dict, who: list[str] | None = None) -> list[str]:
    """Фразы-кандидаты для ремонта: предложения с людьми (people; если ремонт по именам — только с ними, в том числе полуфразы
    после «;»: «Jobs, charismatic and restless, …»), с ≥ 2 местами (map), со сравнением (split)."""
    out = []
    for p, h in paras:
        for sent in re.split(r"(?<=[.!?;])\s+", p):
            tags = []
            if "people" in need:
                ppl = [c for c in entities.get("cast") or [] if any(_in_text(n, sent) for n in _names_of(c))]
                if who: ppl = [c for c in ppl if c["name"] in who]
                if ppl: tags.append("PERSON " + ", ".join(f"{c['name']}" + (f" ({c['role']})" if c.get("role") else "") for c in ppl))
            if "map" in need:
                pl = [g["name"] for g in entities.get("gazetteer") or [] if any(_in_text(n, sent) for n in _names_of(g))]
                if len(pl) >= 2 or (pl and re.search(r"\b(moved|miles|km|from .* to)\b", sent, re.I)): tags.append("PLACE " + ", ".join(pl))
            if "split" in need and COMPARE_RE.search(sent): tags.append("COMPARE")
            if tags: out.append(f"- [{' | '.join(tags)}] «{sent.strip()}»")
    return out[:24]

def _repair(vid: str, part_no: int, paras: list[tuple[str, dict]], need: dict, part_text: str, entities: dict, facts: list, state: dict, prefix: str,
            who: list[str] | None = None) -> tuple[list[dict], list[dict]]:
    cands = _candidates(paras, need, entities, who)
    if not cands and who: cands = _candidates(paras, need, entities)
    if not cands: print(f"[shots] часть {part_no}: ремонт невозможен — нет фраз-кандидатов для {need}"); return [], []
    reqs = "\n".join(f"- {t} × {n}" + (f" — про {', '.join(who)} (portrait по одному на сцену, solo)" if t == "people" and who else "") for t, n in need.items())
    constraints = ("\nПриоритет реализации: допустимы только типы " + ", ".join(config.SCENE_TYPES_ENABLED) +
                   ". Имя в persons.name — только имя человека из текста или cast, без роли и скобок; роль — отдельное поле role.\n")
    res = llm.ask_json(config.prompt("story_shots_repair", part_no=part_no, requests=reqs, candidates="\n".join(cands), facts_json=json.dumps(facts, ensure_ascii=False)) + constraints,
                       heavy=True, max_tokens=6000, tag=f"repair{part_no}_{vid}", model=config.LLM_MODEL_SHOTS or None)
    shots, downgrades = [], []
    for k, x in enumerate(res.get("shots") or [], 1):
        if not isinstance(x, dict) or not x.get("anchor") or x.get("type") not in need: continue
        x = _normalize_shot(x); x["id"] = f"{prefix}r{k}"; x["part"] = part_no
        x, why = _validate_shot(x, part_text, entities, facts, state)
        if x["type"] == "broll":
            downgrades.append({"id": x["id"], "from": "repair", "why": why or "?"}); print(f"[shots] ремонт {x['id']}→broll: {why}"); continue
        shots.append(x)
    print(f"[shots] часть {part_no}: ремонт дал {len(shots)} сцен из запрошенных {sum(need.values())}")
    return shots, downgrades

def _merge_repaired(shots: list[dict], repaired: list[dict], text: str) -> list[dict]:
    """Вставка по якорю: broll на той же фразе (±4 слова) замещается, иначе сцена добавляется (порядок восстановит _regularize)."""
    if not repaired: return shots
    pos = _positions(shots + repaired, text); base = pos[:len(shots)]
    for r, pr in zip(repaired, pos[len(shots):]):
        j = next((i for i, x in enumerate(shots) if x["type"] == "broll" and pr is not None and base[i] is not None and abs(base[i] - pr) <= 4), None)
        if j is None: shots.append(r)
        else: shots[j] = r
    return shots

def shots_for_text(vid: str, part_no: int, part: str, entities: dict, facts: list, state: dict, prefix: str, n_parts: int = 7,
                   part_starts: list[str] | None = None) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    """Раскадровка одной части (или окна демо): куски ≤ 300 слов → подсказки с текущим state → вызовы → нормализация/валидация → квоты → один ремонт.
    «Уже показанные люди» — те, кому модель реально дала people; PERSON без people-сцены в куске снимается и подсказывается снова.
    part_starts — первые слова частей внутри текста (окно демо через несколько частей): на границе части люди снова «впервые».
    Возвращает (shots, overlays, downgrades, hints)."""
    state["shown"] = {}; state["people_shown"] = {}
    CARTOON["on"] = ((db.get(vid)["payload"].get("topic") or {}).get("style") == "cartoon") if vid else False
    facts_json = json.dumps(facts, ensure_ascii=False)
    shots, overlays, downgrades, paras = [], [], [], []
    chunks = _chunks([p.strip() for p in re.split(r"\n\s*\n", part) if p.strip()])
    for k, chunk in enumerate(chunks, 1):
        pairs, text = _annotate_paras(chunk, entities, state, part_starts); paras += pairs
        n = len(re.sub(r"\[F\d+\]|⟶ hints:.*", "", text).split())
        shown = ", ".join(state["people_shown"]) or "—"
        header = (f"(Это часть {part_no} из {n_parts}, кусок {k} из {len(chunks)}, {n} слов. Раскадровка нужна ТОЛЬКО для этого текста; якоря — из этого текста, дословно. "
                  f"Сцен: {max(2, n // 22)}–{max(3, n // 14)}" + (", из них не-broll — не меньше двух" if part_no >= 2 else " (cold open: chart не нужен)") +
                  f". Уже показанные в этой части люди (people): {shown}; текущий год: {state.get('year') or '—'}.)\n\n")
        constraints = ("\nПриоритет реализации: допустимы только типы " + ", ".join(config.SCENE_TYPES_ENABLED) +
                       ". Остальные типы из каталога выше сейчас не реализованы; используй broll и короткие overlays flash/year/caption. "
                       "Имя в persons.name — только имя человека из текста или cast, без роли и скобок; роль — отдельное поле role.\n")
        if CARTOON["on"]: constraints += CARTOON_SHOTS
        res = llm.ask_json(config.prompt("story_shots", script=header + text, facts_json=facts_json) + constraints, heavy=True, max_tokens=12000, tag=f"shots{prefix}{k}_{vid}", model=config.LLM_MODEL_SHOTS or None)
        got, made = 0, set()
        for n_, x in enumerate(res.get("shots") or [], 1):
            if not isinstance(x, dict) or not x.get("anchor"): continue
            x = _normalize_shot(x); x["id"] = f"{prefix}{k}_{n_}"; x["part"] = part_no
            t0 = x["type"]
            x, why = _validate_shot(x, part, entities, facts, state)
            if why:
                if x["type"] != t0: downgrades.append({"id": x["id"], "from": t0, "why": why}); print(f"[shots] {x['id']} {t0}→broll: {why}")
                else: print(f"[shots] {x['id']} {t0}: {why}")
            overlays.extend(x.pop("_overlays", []))
            if not x["slots"] and x["type"] == "broll": continue
            if x["type"] == "people": made |= {p["name"] for p in x["data"]["persons"]}
            shots.append(x); got += 1
        for o in res.get("overlays") or []:
            if isinstance(o, dict) and o.get("anchor") and o.get("type") in ("caption", "flash", "year"): o["part"] = part_no; overlays.append(o)
        hinted = {c["name"] for _, h in pairs for c in h["PERSON"]}
        for name in hinted - made: state["shown"].pop(name, None)   # подсказка была, people не дали — в следующем куске подскажем снова
        for name in made: state["people_shown"][name] = state.get("pos", 0)
        print(f"[shots] часть {part_no} кусок {k}: {got} сцен, {len(res.get('overlays') or [])} титров" + (f"; без people остались {', '.join(sorted(hinted - made))}" if hinted - made else ""))
    hints = [h for _, h in paras]
    need = _needs(shots, hints, part_no, entities)
    if need:
        who = _missing_people(shots, hints, entities) if "people" in need else []
        print(f"[shots] часть {part_no}: не хватает {need}" + (f" (без сцены: {', '.join(who)})" if who else "") + " — ремонт")
        rep, dg = _repair(vid, part_no, paras, need, part, entities, facts, state, prefix, who); downgrades += dg
        shots = _merge_repaired(shots, rep, part)
        still = _needs(shots, hints, part_no, entities)
        if still: print(f"[shots] часть {part_no}: после ремонта всё ещё не хватает {still}")
    _cap_rich(shots, downgrades, part_no, part)
    for o in overlays: o.setdefault("part", part_no)
    return shots, overlays, downgrades, hints

def summary(shots: list[dict], downgrades: list[dict]) -> str:
    """Сводка типов по частям и деградаций — в лог и в Telegram."""
    by_part = {}
    for x in shots: by_part.setdefault(_part_of(x), {}).setdefault(x["type"], 0); by_part[_part_of(x)][x["type"]] += 1
    lines = [f"part {p}: " + ", ".join(f"{t} {n}" for t, n in sorted(c.items(), key=lambda kv: (kv[0] == "broll", kv[0]))) for p, c in sorted(by_part.items())]
    if downgrades: lines.append("деградации: " + "; ".join(f"{d['id']} {d['from']}→broll ({d['why'][:50]})" for d in downgrades[:30]) + (" …" if len(downgrades) > 30 else ""))
    return "\n".join(lines)

def write_shots(vid: str, s: dict, research: dict) -> dict:
    """Слои shots и overlays по частям (куски ≤ 300 слов). Плотность выравнивает _regularize, квоты и ремонт — на часть, порог остановки — на видео."""
    parts = s.get("parts") or [p for p in re.split(r"\n\s*\n", s["script"]) if p.strip()]
    facts = research.get("facts", [])
    entities = ensure_entities(vid)
    state = {"year": None}
    shots, overlays, downgrades = [], [], []
    for i, part in enumerate(parts, 1):
        sh, ov, dg, _ = shots_for_text(vid, i, part, entities, facts, state, prefix=f"v{i}_", n_parts=len(parts))
        shots += sh; overlays += ov; downgrades += dg
    if len(shots) < 40: raise ValueError(f"Слишком мало кадров: {len(shots)}")
    shots = _regularize(shots, s["script"], downgrades)
    _video_caps(shots, downgrades)
    big_scenes = sum(1 for x in shots if x["type"] in ("object", "chart"))
    overlays = _tidy_overlays(overlays, s.get("outline") or [], facts, s["script"], big_scenes)
    s["shots"] = strip_fact_refs(shots); s["overlays"] = strip_fact_refs(overlays, "overlay")
    s["shot_downgrades"] = downgrades
    rich = [x for x in s["shots"] if x["type"] != "broll" and _part_of(x) >= 2]
    issued = len(rich) + sum(1 for d in downgrades if d["from"] in config.RICH_TYPES and _part_of({"id": d["id"]}) >= 2)
    s["needs_review"] = len(rich) < 8 or (issued and len(downgrades) > 0.4 * issued)
    text = summary(s["shots"], downgrades)
    print(f"[shots] итого {len(s['shots'])} сцен ({len(rich)} богатых в частях 2–7, {sum(1 for x in s['shots'] for sl in x['slots'] if sl.get('source') == 'archive')} архивных слотов), {len(s['overlays'])} титров\n" + text)
    if s["needs_review"]:
        print("[shots] ПОРОГ: богатых сцен мало или деградаций > 40 % — нужен просмотр")
        try:
            from .. import telegram; telegram.send(f"⚠️ `{vid}`: раскадровка требует просмотра (богатых {len(rich)}, деградаций {len(downgrades)})\n{text[:1500]}")
        except Exception as e: print("[telegram]", e)
    return s

def _video_caps(shots: list[dict], downgrades: list[dict]):
    """На видео: people ≤ 10, montage ≤ 5, split ≤ 6 (лишние → broll); архивных слотов ≤ ARCHIVE_SLOTS_MAX (сверх — image)."""
    seen = {}
    for x in shots:
        t = x["type"]
        if t in config.RICH_MAX_PER_VIDEO:
            seen[t] = seen.get(t, 0) + 1
            if seen[t] > config.RICH_MAX_PER_VIDEO[t]:
                _degrade(x, f"{t}: больше {config.RICH_MAX_PER_VIDEO[t]} на видео"); downgrades.append({"id": x["id"], "from": t, "why": f"{t}: лимит на видео"})
    n = 0
    for x in shots:
        for sl in x["slots"]:
            if sl.get("source") == "archive":
                n += 1
                if n > config.ARCHIVE_SLOTS_MAX: sl["source"] = "image"; sl["caption"] = None

# ---------- титры ----------

def _tidy_overlays(overlays: list[dict], outline: list[dict] | None = None, facts: list | None = None, script: str | None = None, big_scenes: int = 0) -> list[dict]:
    """chapter от модели выбрасывается (карточки строит pauses); flash без цифры → caption, чужой fact_id → skip; year ≤ 1 на часть, ≤ 4 на видео,
    не ближе ~8 с (20 слов) к flash/caption; общий бюджет цифр MAX_BIG_NUMBERS вместе с object/chart, приоритет деньгам и долям."""
    ids = {f["id"] for f in facts} if facts is not None else None
    out = []
    for o in overlays:
        t = o.get("type")
        if t == "chapter": continue
        if t == "flash":
            if not re.search(r"\d", str(o.get("value", ""))):
                o["type"] = "caption"; o["text"] = str(o.get("value", "")) + (f" — {o['label']}" if o.get("label") else "")
            elif ids is not None and o.get("fact_id") not in ids: print(f"[overlays] flash {o.get('value')}: fact_id {o.get('fact_id')} вне research — пропуск"); continue
            else: o["count"] = bool(config.FLASH_COUNT)
        elif t == "year":
            if not re.fullmatch(r"\d{4}", str(o.get("value", "")).strip()): continue
            o["value"] = str(o["value"]).strip(); o["from"] = str(o.get("from") or "").strip() or None
        elif t != "caption": continue
        out.append(o)
    seen_vals = set()
    for o in out:   # одна и та же цифра дважды на экране — лишнее
        if o["type"] == "flash":
            key = re.sub(r"\s", "", str(o.get("value", "")).lower())
            if key in seen_vals: o["type"] = "skip"
            seen_vals.add(key)
    out = [o for o in out if o["type"] != "skip"]
    if script:   # year: не чаще одного на часть, не ближе 20 слов к flash/caption
        pos = _positions(out, script); per_part, years = {}, 0
        for o, p in zip(out, pos):
            if o["type"] != "year": continue
            pt = o.get("part", 0)
            near = any(q["type"] in ("flash", "caption") and p is not None and pq is not None and abs(p - pq) < 20 for q, pq in zip(out, pos))
            if per_part.get(pt) or years >= 4 or near: o["type"] = "skip"; continue
            per_part[pt] = True; years += 1
        out = [o for o in out if o["type"] != "skip"]
    budget = max(0, config.MAX_BIG_NUMBERS - big_scenes - sum(1 for o in out if o["type"] == "year"))
    flashes = [o for o in out if o["type"] == "flash"]
    if len(flashes) > budget:
        strong = [o for o in flashes if re.search(r"[$%]|billion|million", str(o.get("value", "")) + " " + str(o.get("label", "")), re.I)]
        pool = strong if len(strong) >= budget else flashes
        keep = set()
        if budget:
            step = len(pool) / budget; keep = {id(pool[int(i * step)]) for i in range(budget)}
        for o in flashes:
            if id(o) not in keep: o["type"] = "skip"
        out = [o for o in out if o["type"] != "skip"]
    return out

# ---------- плотность кадров ----------

def _positions(items: list[dict], script: str) -> list[int | None]:
    from .assets import clean_text, _norm, _find
    toks = [_norm(w) for w in clean_text(script).split()]
    out, cur = [], 0
    for it in items:
        a = [_norm(w) for w in re.sub(r"\[F\d+\]", "", it.get("anchor") or "").split()]; a = [w for w in a if w]
        i = None
        for n in (5, 4, 3):
            i = _find(toks, a[:n], cur)
            if i is None: i = _find(toks, a[:n])
            if i is not None: break
        if i is None and len(a) >= 2: i = _find(toks, a[:2], cur)   # одно неверное слово в якоре не должно выбрасывать кадр
        out.append(i)
        if i is not None: cur = i
    return out

def _sentence_starts(script: str) -> set[int]:
    """Индексы слов (в токенах clean_text), с которых начинается предложение или полуфраза после «;»."""
    from .assets import clean_text
    toks = clean_text(script).split()
    return {0} | {i for i in range(1, len(toks)) if toks[i - 1][-1:] in ".!?;"}

def _is_video_archive(x: dict) -> bool:
    sl = (x.get("slots") or [{}])[0]
    return sl.get("source") == "archive" and sl.get("media") == "video"

def _regularize(shots: list[dict], script: str, downgrades: list[dict] | None = None) -> list[dict]:
    """Сортировка по якорям, прореживание: бюджет слов у сцены по её типу (SHOT_MAX_BY_TYPE; картинка/архивное фото — SHOT_MAX_BROLL_STILL,
    чтобы статичный кадр не висел 14 с), минимум SHOT_MIN_RICH у богатых; бонус кандидату за архив/клип и за любой богатый тип.
    Окно пустое, а следующий кандидат дальше бюджета — берём ближайшего «слишком раннего» (≥ 4 слов), а не пропускаем его."""
    pos = _positions(shots, script)
    starts = _sentence_starts(script)
    order = sorted(range(len(shots)), key=lambda i: pos[i] if pos[i] is not None else 10**6)
    shots = [shots[i] for i in order]; pos = [pos[i] for i in order]
    keep, last = [0], pos[0] or 0
    i = 1
    while i < len(shots):
        kept = shots[keep[-1]]; kt = kept.get("type", "broll")
        still = kt == "broll" and not _is_video_archive(kept)
        lo = (config.SHOT_MIN_BROLL_STILL if still else SHOT_MIN) if kt == "broll" else config.SHOT_MIN_RICH
        hi = config.SHOT_MAX_BROLL_STILL if still else config.SHOT_MAX_BY_TYPE.get(kt, SHOT_MAX)
        if last >= config.OPEN_WORDS:   # 27.09: после первых ~2 минут кадры держатся дольше — меньше генераций и проверок
            if still: lo, hi = config.SHOT_LATE_STILL
            else: hi = int(hi * config.SHOT_LATE_FACTOR)
        if _is_video_archive(kept): hi = min(hi, 30)   # клип 16 с не должен зацикливаться (CLIP_SEC)
        target = (lo + hi) / 2 if still or kt != "broll" else SHOT_TARGET
        if last >= config.OPEN_WORDS: target = max(target, 24)   # 27.09: после вступления — ~10 с на кадр для любого типа
        def rich(j): return shots[j].get("type", "broll") != "broll"
        # богатая сцена сразу за богатой (карта на «born in San Francisco», родители на «adopted…») допускается с 8 слов — иначе одна из них теряется
        window = [j for j in range(i, len(shots)) if pos[j] is not None and (lo if not rich(j) else min(lo, SHOT_MIN_RICH_AFTER_RICH)) <= pos[j] - last <= hi]
        if window:
            def score(j):
                x = shots[j]; sl = (x.get("slots") or [{}])[0]
                bonus = 3 if (rich(j) or sl.get("source") in ("archive", "clip") or x.get("source") in ("archive", "clip")) else 0
                return abs(pos[j] - last - target) - bonus
            pool = [j for j in window if rich(j)] or window   # богатая сцена в окне важнее ближайшего к цели broll: пропущенная — потеряна навсегда
            j = min(pool, key=score)
        else:
            nxt = [j for j in range(i, len(shots)) if pos[j] is not None and pos[j] - last > hi]
            # «ранний» кандидат (≥ 4 слов) берётся только когда следующий кадр дальше бюджета (иначе картинка висит 14 с) и только с начала
            # предложения — шестисловный «They sold them door-to-door» перед «for $150 each» рвал фразу на склейке
            near = [j for j in range(i, len(shots)) if pos[j] is not None and 4 <= pos[j] - last < lo and pos[j] in starts]
            if near and nxt: j = near[-1]
            elif nxt: j = nxt[0]
            else: break
        keep.append(j); last = pos[j]; i = j + 1
    out = [shots[k] for k in keep]
    prev, extra = None, []
    for x in out:   # после прореживания одинаковые богатые типы могли встать подряд (people про других людей — можно)
        t = x.get("type", "broll")
        if _same_rich(prev, x):
            act = _activity_broll(x, script) if t == "people" else None
            _degrade(x, f"{t}: тот же богатый тип подряд")
            if downgrades is not None: downgrades.append({"id": x["id"], "from": t, "why": "тот же богатый тип подряд"})
            if act: extra.append((x, act))
            t = "broll"
        prev = x if t != "broll" else None
    for x, act in extra:   # занятие деградированной people — отдельным кадром, если до следующего кадра ≥ 8 слов
        k = out.index(x); p = _positions([act] + out[k + 1:k + 2], script)
        if p[0] is not None and (len(p) < 2 or p[1] is None or p[1] - p[0] >= 8): out.insert(k + 1, act); print(f"[shots] {act['id']}: занятие сохранено отдельным broll на «{act['anchor']}»")
    print(f"[shots] {len(shots)} → {len(out)} кадров после выравнивания")
    return out

def factcheck(vid: str, s: dict, research: dict) -> dict:
    """Проверка выдуманных деталей сильной моделью (config.LLM_MODEL_FACTCHECK: цитаты, числа, даты, имена, «живописные» подробности),
    затем точечная правка помеченных фраз автором текста (config.LLM_MODEL_WRITER). Решение владельца 15.09: проверяет Astra; с 18.09 пишет Opus 5."""
    parts = s.get("parts") or [p for p in re.split(r"\n\s*\n", s["script"]) if p.strip()]
    marked = "\n\n".join(f"=== PART {i} ===\n{p}" for i, p in enumerate(parts, 1))
    facts_json = json.dumps(research.get("facts", []), ensure_ascii=False)
    try:
        res = llm.ask_json(config.prompt("factcheck", script=marked, facts_json=facts_json), model=config.LLM_MODEL_FACTCHECK,
                           max_tokens=20000, tag=f"factcheck_{vid}", effort="high")   # 60+ замечаний не влезали в 8k → повтор удваивал цену
    except Exception as e:
        print(f"[factcheck] не удалась: {e}"); s["factcheck"] = {"error": str(e)[:200], "issues": []}; return s
    issues = [x for x in res.get("issues", []) if x.get("quote") and x.get("verdict") in ("unsupported", "contradicts", "arithmetic")]
    fixed = []
    for i in range(1, len(parts) + 1):
        mine = [x for x in issues if str(x.get("part") or "") == str(i) or (not x.get("part") and x["quote"][:40] in parts[i - 1])]
        if not mine: continue
        listing = "\n".join(f"- «{x['quote']}» — {x['verdict']}: {x.get('why', '')} → {x.get('fix', '')}" for x in mine)
        try:
            r = llm.ask_json(config.prompt("story_fix", part_no=i, text=parts[i - 1], issues=listing), heavy=True, max_tokens=6000, tag=f"storyfix{i}_{vid}", model=config.LLM_MODEL_WRITER or None)
            new = (r.get("text") or "").strip(); n_old, n_new = len(parts[i - 1].split()), len(new.split())
            if new and 0.8 * n_old <= n_new <= 1.2 * n_old: parts[i - 1] = new; fixed.append(i)
            else: print(f"[factcheck] часть {i}: правка отклонена (длина {n_old}→{n_new})")
        except Exception as e:
            print(f"[factcheck] часть {i}: {e}")
    s["parts"] = parts; s["script"] = "\n\n".join(parts)
    s["factcheck"] = {"issues": issues, "fixed_parts": fixed, "summary": res.get("summary", "")}
    print(f"[factcheck] замечаний {len(issues)}, исправлены части {fixed}: {res.get('summary', '')[:200]}")
    return s

def factcheck_note(s: dict) -> str:
    """Сводка проверки для владельца (Telegram и script.md)."""
    fc = s.get("factcheck") or {}
    if fc.get("error"): return f"Проверка фактов не удалась: {fc['error']}"
    issues = fc.get("issues", [])
    if not issues: return "Проверка фактов (Astra): выдуманных деталей не найдено."
    lines = [f"Проверка фактов (Astra): замечаний {len(issues)}, исправлены части {fc.get('fixed_parts')}. {fc.get('summary', '')}"]
    lines += [f"• [{x.get('verdict')}] «{x['quote'][:90]}» — {str(x.get('why', ''))[:120]}" for x in issues[:8]]
    return "\n".join(lines)

def facts_csv(d, facts: list[dict]):
    import csv
    with open(d / "facts.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FACT_COLS, extrasaction="ignore"); w.writeheader(); w.writerows(facts)

def window_text(script: str, first: list[str], last: list[str]) -> str:
    """Фрагмент сценария (с [Fn] и абзацами) между первыми и последними словами окна демо — чтобы подсказки NUMBER/QUOTE видели fact_id."""
    from .assets import _norm, _find
    raw = re.sub(r"</?short>", "", script)
    paras = [p for p in re.split(r"\n\s*\n", raw) if p.strip()]
    stream, ptoks = [], []
    for pi, p in enumerate(paras):
        toks = p.split(); ptoks.append(toks)
        for ti, t in enumerate(toks):
            if FACT_TAG.fullmatch(t): continue
            n = _norm(t)
            if n: stream.append((n, pi, ti))
    norms = [s[0] for s in stream]
    f = [_norm(w) for w in first if _norm(w)]; l = [_norm(w) for w in last if _norm(w)]
    i0 = _find(norms, f[:4]); i0 = 0 if i0 is None else i0
    i1 = _find(norms, l[-4:], i0)
    i1 = len(stream) - 1 if i1 is None else min(len(stream) - 1, i1 + len(l[-4:]) - 1)
    (p0, t0), (p1, t1) = stream[i0][1:], stream[i1][1:]
    out = []
    for pi in range(p0, p1 + 1):
        toks = ptoks[pi]; a = t0 if pi == p0 else 0; b = (t1 + 1) if pi == p1 else len(toks)
        if b < len(toks) and FACT_TAG.fullmatch(toks[b]): b += 1
        out.append(" ".join(toks[a:b]))
    return "\n\n".join(out)
