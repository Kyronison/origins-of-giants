"""Редакционный бриф — контрольная точка ПЕРЕД дорогим сценарием и ассетами (разбор Astra 20.09).

Раньше после ресёрча сразу писались 4 700 слов, озвучка и картинки: ошибка в замысле стоила полный прогон.
Теперь между ресёрчем и сценарием стоит бриф: кому ролик, на какой вопрос отвечает, спорный тезис с фактами,
контраргумент, свой расчёт, обещание названия и выплата вступления. Бриф проверяется механически и утверждается
здесь же; владельца дёргаем, только если после повтора бриф всё равно пустой — иначе смысл автономности теряется."""
import json, re
from .. import db, llm, telegram, config, series

FIELDS = ("audience", "viewer_question", "thesis", "counterargument", "original_calculation", "primary_sources", "title_promise", "opening_payoff")
# подписи обложки (thumb_then / thumb_now) — не обязательны: их доберёт stages/thumbv.py по фактам; но если есть — по размеру плашек ThumbV
# название-«история компании»: так назывался Apple (How Apple Started…) — 3 400 показов, CTR 1,3 % (разбор канала 21.09)
_BANAL_RE = re.compile(r"\b(the )?(story|history|origins?|rise( and fall)?) of\b(?! giants)|\bhow it all (began|started)\b|"
                         r"\bhow\b.{0,50}\b(started|began|was born|was founded|got started|built [a-z]+ from)\b|"
                         r"\b(?-i:[A-Z][\w']+) history( documentary)?\b", re.I)
THEN_MAX, NOW_MAX = 10, 7   # плашки ThumbV kind=split: слева 104 px («$1,000,000» влезает), справа 168 px («$294B», «$3T»)
CYRILLIC = re.compile(r"[А-Яа-яЁё]")
BANAL = ("история компании", "как всё начиналось", "путь от гаража", "rise and fall", "the story of", "how it all began")

_TD_TAIL = re.compile(r",\s+(the|a|an)\s.{6,}?\b(that|who|which|before|after|until)\b", re.I)


class _Banal:
    """«История компании» без конфликта не кликают (Apple 21.09: CTR 1,3 %). Но формула лидеров ниши с описанием и конфликтом
    в хвосте — «The Fascinating Story of X, the … That …», «The Rise and Fall of X, the … Before …» — лучшая у Tech District (27.09)."""
    def search(self, t):
        m = _BANAL_RE.search(t or "")
        return None if (m and _TD_TAIL.search(t or "")) else m


TITLE_BANAL = _Banal()


def _problems(b: dict, research: dict, topic: dict | None = None) -> list[str]:
    ids = {f["id"] for f in research.get("facts", [])}
    urls = {f.get("source_url") for f in research.get("facts", [])}
    p = []
    for k in FIELDS:
        if not b.get(k): p.append("нет поля " + k)
    th = (b.get("thesis") or "").strip()
    if len(th.split()) < 8: p.append("тезис короче 8 слов — это заголовок, а не утверждение")
    if not re.search(r"\d", th): p.append("в тезисе нет ни одного числа")
    if any(x in th.lower() for x in BANAL): p.append("тезис пересказывает историю компании, а не утверждает механизм")
    if len([x for x in (b.get("thesis_facts") or []) if x in ids]) < 2: p.append("тезис не опирается минимум на два факта ресёрча (thesis_facts)")
    ca = (b.get("counterargument") or "").strip()
    if len(ca.split()) < 6: p.append("контраргумент пустой")
    if ca.lower() == th.lower(): p.append("контраргумент повторяет тезис")
    if not (b.get("counter_answer") or "").strip(): p.append("нет ответа на контраргумент")
    calc = b.get("original_calculation") or {}
    if not calc.get("formula") or not calc.get("result"): p.append("свой расчёт без формулы или без результата")
    if len([x for x in (calc.get("inputs") or []) if x in ids]) < 1: p.append("в расчёте нет ни одного факта из ресёрча")
    if len([u for u in (b.get("primary_sources") or []) if u in urls]) < 3: p.append("меньше трёх первичных источников из ресёрча")
    tp = (b.get("title_promise") or "").strip()
    if tp: p += ["название: " + x for x in series.title_problems(tp, topic, ids, b.get("title_facts"))]   # STRATEGY.md раздел 0 (08.10): формула, 55–100 знаков, одно число, источник
    if tp and TITLE_BANAL.search(tp): p.append("обещание названия — «история компании» (how X started / story of): такое не кликают")
    if tp and CYRILLIC.search(tp): p.append("обещание названия не по-английски — оно идёт в название на YouTube")
    facts_txt = json.dumps(research.get("facts", []), ensure_ascii=False)
    names = [n for n in re.findall(r"\b[A-Z][a-z]+ [A-Z][a-z]+\b", tp) if n in facts_txt]   # Title Case сам по себе именем не считается
    if tp and not re.search(r"\d", tp) and not names and not series.of(topic): p.append("в обещании названия нет ни числа, ни имени из ресёрча")
    for k, lim in (("thumb_then", THEN_MAX), ("thumb_now", NOW_MAX)):
        if len(str(b.get(k) or "")) > lim: p.append(f"{k} длиннее {lim} знаков — не влезет в плашку обложки")
    un = b.get("thumb_units") or []   # 26.09: без подписей пара «$21B → $10.97» читалась как превращение одного в другое
    if b.get("thumb_then") and b.get("thumb_now") and (len(un) != 2 or any(not str(u).strip() or len(str(u)) > 16 for u in un)):
        p.append("thumb_units: нужны две подписи до 16 знаков — что это за числа слева и справа")
    if len((b.get("opening_payoff") or "").split()) > 45: p.append("выплата вступления длиннее 45 слов")
    return p

PACK = """Ты упаковываешь YouTube-документалку (канал Origins of Giants: бренды, которые зритель США знает по названию; что с ними
случилось и на чём они зарабатывали на самом деле).
Герой: {company}. Рабочая тема: {working_title}. Тезис: {thesis}
Бриф: название «{promise}»; превью «{then} → {now}» ({years}); почему: {why}
Факты ресёрча (только они): {facts}

ПРАВИЛО НАЗВАНИЯ (одно для всех трёх вариантов): {title_rule}

Предложи ТРИ заметно разных варианта упаковки. Формула у всех одна — та, что в правиле; различаются они тем, ЧТО обещают:
{angles} Каждый:
- title — по правилу названия, по-английски, без кликбейта, которого нет в ролике;
- title_facts — id фактов ресёрча, которые подтверждают название;
- thumb_then ≤10 знаков и thumb_now ≤7 знаков — число или слово из фактов; thumb_units — две подписи ≤16 знаков, ЧТО это за числа;
- thumb_years — два года; thumb_facts — id фактов; opening_payoff — что зритель узнаёт в первые 40 секунд (≤40 слов, событие, а не справка).
Верни JSON: {{"options": [{{"angle": "...", "title": "...", "title_facts": ["F.."], "thumb_then": "...", "thumb_now": "...", "thumb_units": ["...", "..."],
"thumb_years": ["...", "..."], "thumb_facts": ["F.."], "opening_payoff": "..."}}]}}"""

JUDGE = """Ты — продюсер упаковки YouTube с данными CTR бизнес-документалок. Зритель — американец, который знает этот бренд по названию.
Оцени три варианта упаковки по шкале 1–10 по каждому критерию: clarity (за 1 секунду понятно, о чём, на телефоне),
curiosity (хочется узнать ответ), truth (обещание честно выполняется фактами), fit (название и превью дополняют, а не повторяют друг друга).
Формула названия у всех вариантов одна и задана заранее — её не оценивай; оценивай, что именно обещано и выполнимо ли это.
Название длинное (до 100 знаков) и пересказывает весь сюжет: кто это был для обычного американца, чем прославился и чем кончилось
(08.10, по образцу Tech District). Вариант, где после формулы нет ни взлёта, ни конца, получает curiosity и fit не выше 4.
Превью у всех вариантов — один шаблон «Плакат» со знаком бренда; оценивай название. Слова — пассажира и покупателя, не инвестора.
Варианты: {options}
truth строго: если цифры в названии и превью сравнивают разные величины (выручку с прибылью, цену сделки с ценой за штуку) или
обещание не выполняется фактами — truth ниже 7.
Верни JSON: {{"scores": [{{"n": 1, "clarity": 0, "curiosity": 0, "truth": 0, "fit": 0, "why": "..."}}], "best": 1, "why": "одно предложение"}}"""


def packaging(vid: str, b: dict, research: dict, t: dict) -> dict:
    """27.09: три варианта «название + превью» до сценария, судья выбирает лучший; бриф и сценарий пишутся под него."""
    facts = json.dumps([{k: f.get(k) for k in ("id", "fact", "value", "year") if f.get(k) is not None} for f in (research.get("facts") or [])][:60], ensure_ascii=False)[:9000]
    q = PACK.format(company=t.get("company") or t.get("ticker") or "", working_title=t.get("working_title", ""), thesis=str(t.get("thesis", ""))[:400],
                    title_rule=series.title_rule(t), angles=series.pack_angles(t),
                    promise=b.get("title_promise", ""), then=b.get("thumb_then", ""), now=b.get("thumb_now", ""),
                    years=", ".join(b.get("thumb_years") or []), why=b.get("thumb_why", ""), facts=facts)
    opts = (llm.ask_json(q, heavy=True, max_tokens=8000, tag="pack_" + vid, model=config.LLM_MODEL_WRITER or None).get("options") or [])[:3]
    ok = []
    for o in opts:
        o = dict(o); tb = {**b, "title_promise": o.get("title", ""), "thumb_then": o.get("thumb_then"), "thumb_now": o.get("thumb_now"),
                           "thumb_units": o.get("thumb_units"), "opening_payoff": o.get("opening_payoff"), "title_facts": o.get("title_facts")}
        bad_o = [x for x in _problems(tb, research, t) if "thumb" in x or "обещание" in x or "выплата" in x or "название" in x]
        if bad_o: print(f"[pack] вариант «{o.get('title')}» отклонён: " + "; ".join(bad_o), flush=True)
        else: ok.append(o)
    if len(ok) < 2: print(f"[pack] годных вариантов {len(ok)} — оставляю бриф как есть", flush=True); return b
    j = llm.ask_json(JUDGE.format(options=json.dumps([{"n": i + 1, **o} for i, o in enumerate(ok)], ensure_ascii=False)),
                     max_tokens=2000, tag="packjudge_" + vid, model=config.LLM_MODEL_FACTCHECK or None)
    sc = {int(x.get("n") or 0): x for x in (j.get("scores") or [])}
    def total(k):   # честность — отсечка, а не слагаемое: красивое, но неверное обещание не берём (Copart 27.09)
        x = sc.get(k) or {}; tr = float(x.get("truth") or 0)
        return -1 if tr < 7 else float(x.get("clarity") or 0) + float(x.get("curiosity") or 0) + float(x.get("fit") or 0) + tr
    n = max(range(1, len(ok) + 1), key=total)
    if total(n) < 0: print("[pack] ни один вариант не прошёл по честности — бриф как есть", flush=True); return b
    w = ok[n - 1]
    b = {**b, "title_promise": w["title"], "thumb_then": w["thumb_then"], "thumb_now": w["thumb_now"], "thumb_units": w.get("thumb_units"),
         "thumb_years": w.get("thumb_years") or b.get("thumb_years"), "thumb_facts": w.get("thumb_facts") or b.get("thumb_facts"),
         "opening_payoff": w.get("opening_payoff") or b.get("opening_payoff"), "title_facts": w.get("title_facts") or b.get("title_facts"),
         "packaging": {"options": ok, "judge": j, "chosen": n}}
    print(f"[pack] выбран вариант {n} из {len(ok)}: «{w['title']}» | {w['thumb_then']} → {w['thumb_now']} — {j.get('why', '')}", flush=True)
    return b


def make(vid: str, research: dict, extra: str = "") -> dict:
    """Бриф и самопроверка. Один повтор с перечнем замечаний, после него — стоп и владельцу в Telegram."""
    v = db.get(vid); t = v["payload"]["topic"]; d = db.video_dir(vid)
    company = (str(t.get("company") or t.get("ticker") or "") + " — люди: " + str(t.get("hero") or "—")).strip()
    base = config.prompt("brief", working_title=t["working_title"], company=company, thesis=t.get("thesis", ""),
                         title_rule=series.title_rule(t), facts_json=json.dumps(research, ensure_ascii=False)) + extra
    b = llm.ask_json(base, heavy=True, max_tokens=7000, tag="brief_" + vid, model=config.LLM_MODEL_WRITER or None)
    bad = _problems(b, research, t)
    if bad:
        print("[brief] замечания: " + "; ".join(bad), flush=True)
        b = llm.ask_json(base + "\n\nПРЕДЫДУЩАЯ ПОПЫТКА ОТКЛОНЕНА РЕДАКТОРОМ: " + "; ".join(bad) +
                         "\nИсправь именно это, остальное можно сохранить. Вот она:\n" + json.dumps(b, ensure_ascii=False),
                         heavy=True, max_tokens=7000, tag="brief2_" + vid, model=config.LLM_MODEL_WRITER or None)
        bad = _problems(b, research, t)
    if not bad:
        try: b = packaging(vid, b, research, t)   # 27.09: упаковка до сценария — три варианта, судья выбирает
        except Exception as e: print(f"[pack] упаковка не собралась, бриф как есть: {str(e)[:120]}", flush=True)
    b["approved"] = not bad; b["problems"] = bad
    config.write(d / "brief.md", text(b))
    db.update(vid, payload={"brief": b})
    if bad:
        telegram.send("Бриф " + vid + " не собрался даже со второй попытки:\n• " + "\n• ".join(bad) +
                      "\nРесёрч, видимо, не даёт темы. Отклонить: reject " + vid, file=d / "brief.md")
        raise ValueError("Бриф не прошёл проверку: " + "; ".join(bad))
    print("[brief] тезис: " + b["thesis"], flush=True)
    calc = b.get("original_calculation") or {}
    print("[brief] свой расчёт: " + str(calc.get("name")) + " = " + str(calc.get("result")), flush=True)
    return b

def text(b: dict) -> str:
    calc = b.get("original_calculation") or {}
    return ("# Редакционный бриф\n\n"
            "**Зритель:** " + str(b.get("audience", "")) + "\n\n**Его вопрос:** " + str(b.get("viewer_question", "")) + "\n\n"
            "**Тезис:** " + str(b.get("thesis", "")) + "  \nфакты: " + ", ".join(b.get("thesis_facts") or []) + "\n\n"
            "**Контраргумент:** " + str(b.get("counterargument", "")) + "  \n**Ответ:** " + str(b.get("counter_answer", "")) + "\n\n"
            "**Свой расчёт:** " + str(calc.get("name", "")) + " — " + str(calc.get("formula", "")) + " = **" + str(calc.get("result", "")) + "** "
            "(входные: " + ", ".join(calc.get("inputs") or []) + ")\n\n"
            "**Обещание названия:** " + str(b.get("title_promise", "")) + "\n\n"
            "**Выплата вступления:** " + str(b.get("opening_payoff", "")) + "\n\n"
            "**Чего не делаем:** " + "; ".join(b.get("avoid") or []) + "\n\n"
            "**Источники:**\n" + "\n".join("- " + u for u in (b.get("primary_sources") or [])) +
            ("\n\n**Не закрыто:** " + "; ".join(b["problems"]) if b.get("problems") else ""))

def block(b: dict) -> str:
    """Блок брифа для промптов сценария: всё, что обязан выполнить текст."""
    calc = b.get("original_calculation") or {}
    return ("\n\nРЕДАКЦИОННЫЙ БРИФ (утверждён, выполнять обязательно):\n"
            "- Зритель: " + str(b.get("audience", "")) + "\n"
            "- Его вопрос: " + str(b.get("viewer_question", "")) + "\n"
            "- Тезис ролика (доказать по ходу): " + str(b.get("thesis", "")) + "\n"
            "- Возражение скептика, на которое надо ответить в тексте: " + str(b.get("counterargument", "")) + " → " + str(b.get("counter_answer", "")) + "\n"
            "- Свой расчёт, который должен прозвучать голосом: " + str(calc.get("name", "")) + " = " + str(calc.get("result", "")) + " (" + str(calc.get("formula", "")) + ")\n"
            "- Первые 40 секунд обязаны дать: " + str(b.get("opening_payoff", "")) + "\n"
            "- Название ролика (зритель кликнул ради этого — его утверждение звучит словами в первые 10 секунд): " + str(b.get("title_promise", "")) + "\n"
            "- Не делать: " + ("; ".join(b.get("avoid") or []) or "—") + "\n")

def check_opening(vid: str, s: dict, b: dict) -> dict:
    """Выполняет ли вступление обещание брифа. Если нет — переписываем только первую часть, весь сценарий не трогаем."""
    parts = s.get("parts") or [s["script"]]
    head = " ".join(re.sub(r"\[F\d+\]|</?short>", "", parts[0]).split()[:170])
    res = llm.ask_json("Вот обещание вступления из редакционного брифа и первые 170 слов готового сценария.\n\n"
                       "ОБЕЩАНИЕ: " + str(b.get("opening_payoff", "")) + "\nТЕЗИС: " + str(b.get("thesis", "")) +
                       "\n\nВСТУПЛЕНИЕ:\n" + head + "\n\n"
                       "Вопрос: зритель, включивший ролик с телефона, получает это обещание в этих словах — конкретный факт или число, "
                       "а не намёк и не представление канала? Верни JSON: "
                       '{"ok": true|false, "why": "одно предложение", "missing": "чего не хватает"}',
                       max_tokens=800, tag="opening_" + vid, model=config.LLM_MODEL_FACTCHECK or None)
    print("[brief] вступление: " + ("ок" if res.get("ok") else "не выполняет обещание") + " — " + str(res.get("why", "")), flush=True)
    return res

def rewrite_opening(vid: str, s: dict, b: dict, why: str) -> dict:
    """Переписывает только первую часть под обещание брифа и пересобирает s['script'] — без перезапуска всего сценария."""
    parts = s.get("parts") or []
    if not parts: return s
    res = llm.ask_json("Перепиши ТОЛЬКО вступительную часть документального сценария так, чтобы она выполняла обещание брифа.\n\n"
                       "ОБЕЩАНИЕ: " + str(b.get("opening_payoff", "")) + "\nТЕЗИС: " + str(b.get("thesis", "")) +
                       "\nНАЗВАНИЕ РОЛИКА (зритель кликнул ради этого — его утверждение звучит в первые 10 секунд, то есть в первых ~23 словах): "
                       + str(b.get("title_promise", "")) +
                       "\nЧТО НЕ ТАК СЕЙЧАС: " + why + "\n\n"
                       "Правила: тот же голос и стиль, те же ссылки на факты [Fn] (можно добавить из уже имеющихся), "
                       "схема по порядку: 1) первая фраза не длиннее 20 слов называет героя по имени и говорит утверждение названия; "
                       "2) масштаб одним-двумя числами — во всём вступлении НЕ БОЛЬШЕ ПЯТИ чисел, считая годы и числа словами; "
                       "3) на 15–45-й секунде событие: кто-то конкретный что-то сделал; 4) механизм назван и обещан, но не объяснён; "
                       "5) последняя фраза — единственный прыжок в начало истории. Названия канала, слова subscribe и просьб к зрителю нет. "
                       "Ни одного вопроса: только утверждения. Не длиннее 260 слов. Каждая фраза продолжает предыдущую — не оставляй реплик, "
                       "которые отвечают на удалённый текст. "
                       "Последняя фраза должна подводить ко второй части так же, как сейчас.\n\n"
                       "ТЕКУЩЕЕ ВСТУПЛЕНИЕ:\n" + parts[0] + "\n\nВерни JSON: {\"text\": \"новое вступление\"}",
                       heavy=True, max_tokens=4000, tag="opening_fix_" + vid, model=config.LLM_MODEL_WRITER or None)
    new = (res.get("text") or "").strip()
    if len(new.split()) < len(parts[0].split()) * 0.7:
        print("[brief] новое вступление короче на треть — оставляю прежнее", flush=True); return s
    parts[0] = new; s["parts"] = parts; s["script"] = "\n\n".join(parts)
    print("[brief] вступление переписано под обещание брифа", flush=True)
    return s
