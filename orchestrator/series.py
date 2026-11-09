"""Правила серий (STRATEGY.md; смена курса владельцем 08.10.2026 — раздел 0).

Одно место для всего, что зависит от серии и типа сюжета: формула названия, макет превью, план частей сценария, схема вступления.
Серия и тип задаются пятым полем строки stories.txt: «A:collapse», «A:collapse:what», «B:mechanism:nologo».
  A — с 08.10 одна тема канала: падения брендов, которыми американец пользовался сам (авиакомпании, магазины, рестораны, игрушки).
  B — серия блока 1 (еда и магазин у дома); новых тем нет, код оставлен для вышедших роликов.
Формула названия (третий сегмент тега, по очереди в stories.txt): rise — «The Rise and Fall of X, the … That …»,
  what — «What Happened to X? The … That …», story — «The Fascinating Story of X, the … That …». Без сегмента: collapse → rise, иначе story.
Превью у всех серий одно — «Плакат» (выбор владельца 08.10, образец work/strategy-v2-thumbs/thumb_poster.jpg).
Типы сюжета: collapse (крах), decision (одно решение), family (семья), mechanism (скрытый механизм знакомой вещи).
Тема без пятого поля идёт по прежним правилам (серии нет) — так остаётся испанская очередь и ручные запуски."""
import re

TITLE_MAX = 100   # 08.10: длинные названия «весь сюжет в одной строке» (было 60); 100 — предел YouTube
TITLE_MIN = 55    # короче — сюжет в название не помещается
TYPES = ("collapse", "decision", "family", "mechanism", "history")   # history — пилот 19.10: полная история знакомого бренда (Walmart, Disney)
FORMULAS = {"rise": "The Rise and Fall of {b}", "what": "What Happened to {b}?", "story": "The Fascinating Story of {b}"}
CAPTION = {"rise": "THE RISE AND FALL", "what": "WHAT HAPPENED?", "story": "THE FULL STORY"}   # строка под знаком на превью
TAG = re.compile(r"^([AB])\s*:\s*(collapse|decision|family|mechanism|history)((?:\s*:\s*(?:nologo|rise|what|story))*)$", re.I)
THUMB = {"A": "poster", "B": "poster"}
THUMB_RU = {"poster": "плакат", "object": "предмет-герой", "iceberg": "айсберг"}
# слова, которым в названии нужен источник из ресёрча (STRATEGY.md, разделы 0 и 4)
RISKY = re.compile(r"\b(never|twice|doubled?|tripled?|every|always|only|all|none|nobody|half|most|first|last|biggest|largest)\b", re.I)
# жаргон инвестора: зритель — пассажир и покупатель, а не аналитик (пробный бриф Greyhound 29.09: «The Stations Were the Moat»)
JARGON = re.compile(r"\b(moat|flywheel|unit economics|ebitda|arbitrage|margins?|leverage|playbook|disrupt\w*)\b", re.I)
NUM = re.compile(r"\$?\d[\d.,]*\s?(?:%|[KMBT]\b|bn\b|million\b|billion\b|trillion\b)?", re.I)


def parse(tag: str) -> dict | None:
    m = TAG.match((tag or "").strip())
    if not m: return None
    extra = [x.strip().lower() for x in (m.group(3) or "").split(":") if x.strip()]
    out = {"series": m.group(1).upper(), "story_type": m.group(2).lower(), "no_logo": "nologo" in extra}
    f = [x for x in extra if x in FORMULAS]
    if f: out["formula"] = f[0]
    return out


def formula(topic: dict | None) -> str:
    t = topic or {}
    f = str(t.get("formula") or "").lower()
    if f in FORMULAS: return f
    return "rise" if str(t.get("story_type") or "").lower() == "collapse" else "story"


def of(topic: dict | None) -> dict | None:
    """Серия темы или None, если тема вне серий."""
    t = topic or {}
    if str(t.get("series") or "").upper() not in THUMB: return None
    st = str(t.get("story_type") or "mechanism").lower()
    st = st if st in TYPES else "mechanism"
    return {"series": str(t["series"]).upper(), "story_type": st, "no_logo": bool(t.get("no_logo")),
            "brand": brand(t), "formula": formula({**t, "story_type": st})}


def brand(topic: dict) -> str:
    """Имя героя так, как оно стоит в названии: поле «Компания» из stories.txt до скобки или тире."""
    return re.split(r"\s+[—–-]\s+|\s*\(|\s*,", str(topic.get("company") or "").strip())[0].strip()


def thumb_kind(topic: dict | None) -> str | None:
    s = of(topic)
    return THUMB[s["series"]] if s else None


def caption(topic: dict | None) -> str:
    s = of(topic)
    return CAPTION[s["formula"]] if s else ""


def _numbers(title: str, br: str) -> list[str]:
    """Числа названия без цифр из имени бренда («7-Eleven», «Forever 21»)."""
    t = re.sub(re.escape(br), " ", title, flags=re.I) if br else title
    return [n.strip() for n in NUM.findall(t) if re.search(r"\d", n)]


def title_rule(topic: dict | None) -> str:
    """Текст правила названия для промптов (бриф, упаковка, поля YouTube)."""
    s = of(topic)
    common = (f"Длина {TITLE_MIN}–{TITLE_MAX} знаков с пробелами. Не больше ОДНОГО числа. Слова Never, Twice, First, Last, Every, Always, "
              "Only, Biggest, любые доли и суммы допустимы, только если их прямо подтверждает факт ресёрча (укажи его id в title_facts). "
              "Без названий малоизвестных компаний и без техногигантов в названии: герой — то, что зритель США узнаёт по имени. "
              "Слова зрителя, не инвестора: без moat, flywheel, margin, unit economics.")
    if not s:
        return "Название: бренд в первых словах, один конкретный факт или конфликт. " + common
    b = s["brand"]; f = s["formula"]; head = FORMULAS[f].format(b=b)
    if s["story_type"] == "history":   # пилот 19.10: бренд жив и огромен — обещание «вся история», а не падение
        return (f"Название строго начинается с «{head}» и дальше пересказывает ВЕСЬ путь одной строкой: откуда бренд взялся (место, "
                f"первый магазин или первая вещь) и чем он стал для обычного американца — «{head}, the … That …». Зритель по одному "
                f"названию должен понять: вся история знакомой вещи от первого дня до сегодня. Образец формы (чужой ролик, не копировать "
                f"факты): The Fascinating Story of Compaq, the Houston Garage That Reverse-Engineered IBM and Built a PC Giant. " + common)
    examples = {
        "rise": [f"The Rise and Fall of Palm, the Santa Clara Startup That Built the First Smartphone and Lost to Apple",
                 f"The Rise and Fall of RadioShack: It Wired Every American Home, Then Lost It All"],
        "what": [f"What Happened to WordPerfect? The Utah Word Processor That Once Ruled Every American Office"],
        "story": [f"The Fascinating Story of Compaq, the Houston Garage That Reverse-Engineered IBM and Built a PC Giant"]}[f]
    return (f"Название строго начинается с «{head}» и дальше пересказывает ВЕСЬ сюжет одной строкой: кто это был (откуда, чем "
            f"был для обычного американца), чем прославился и как всё кончилось — «{head}, the … That …». Зритель по одному названию "
            f"должен понять, что получит: вещь из своей жизни, взлёт и падение. Образцы формы (чужие ролики, не копировать факты): "
            + " | ".join(examples) + ". " + common)


def pack_angles(topic: dict | None) -> str:
    """Чем различаются три варианта упаковки (stages/brief.py): формула у всех одна, разное — что стоит после имени бренда."""
    s = of(topic)
    if s and s["story_type"] == "history":
        return ("1) первый день — где и с чего бренд начался («the Arkansas Five-and-Dime That …»); 2) поступок, который сделал его "
                "великаном для обычного американца; 3) то, что помнит зритель, — вещь, место, вывеска, и чем бренд стал сегодня. "
                "Все три — одна полная история, разные двери в неё; падения и краха в названии нет.")
    if s:
        return ("1) происхождение и главный поступок — откуда бренд и что он первым сделал для обычного американца («the Detroit Charter "
                "That First Charged for Carry-Ons»); 2) вершина и падение — чем он владел и кому или чему проиграл («That Ruled X Before "
                "Losing to Y»); 3) то, что помнит зритель, — вещь, звук, цвет, вывеска, и чем это кончилось («the Yellow Jets That Ran Out "
                "of Runway»). Все три — один сюжет, разные двери в него.")
    return ("1) скрытый механизм — кто на самом деле получает деньги; 2) семья или решение — кто владеет и что он выбрал; "
            "3) цена для покупателя или парадокс масштаба.")


def title_problems(title: str, topic: dict | None, fact_ids=None, title_facts=None) -> list[str]:
    """Механическая проверка названия по правилам. fact_ids — id фактов ресёрча; title_facts — на что ссылается название."""
    t = (title or "").strip(); s = of(topic); bad = []
    if not t: return ["названия нет"]
    if len(t) > TITLE_MAX: bad.append(f"название {len(t)} знаков — больше {TITLE_MAX}")
    br = s["brand"] if s else brand(topic or {})
    nums = _numbers(t, br)
    if len(nums) > 1: bad.append(f"в названии {len(nums)} числа ({', '.join(nums)}) — можно одно")
    if s and br:
        if len(t) < TITLE_MIN: bad.append(f"название {len(t)} знаков — короче {TITLE_MIN}: сюжет не рассказан")
        low = re.sub(r"[’`]", "'", t.lower()); head = re.sub(r"[’`]", "'", FORMULAS[s["formula"]].format(b=br).lower())
        if not low.startswith(head):
            bad.append(f"название должно начинаться с «{FORMULAS[s['formula']].format(b=br)}» (формула этого ролика)")
        elif len(t[len(head):].split()) < 5:
            bad.append("после формулы меньше 5 слов — нужен сюжет: кто это был и чем кончилось")
        if re.search(r"\bmakes? (its )?money\b", low): bad.append("формула «How X Makes Money» не используется")
    j = JARGON.search(t)
    if j: bad.append(f"в названии жаргон инвестора «{j.group(0)}» — нужны слова зрителя")
    if fact_ids is not None and (nums or RISKY.search(t)):
        ok = [x for x in (title_facts or []) if x in set(fact_ids)]
        if not ok:
            what = ", ".join(nums + sorted({m.group(0) for m in RISKY.finditer(t)}))
            bad.append(f"в названии «{what}» — нужен подтверждающий факт ресёрча в title_facts")
    return bad


# ---------- вступление (STRATEGY.md, раздел 5) — гипотеза блока, одна схема на все ролики ----------

NUM_LIMIT_90 = 5   # чисел в первые 90 секунд
COLD_OPEN_MAX = 260   # слов во вступлении: при 2.3 слова в секунду это 113 секунд — прыжок в начало истории звучит до конца второй минуты
NO_CHANNEL_SEC = 120

COLD_OPEN = """1. Cold open (200–260 слов, около полутора минут). Схема блока, ходы строго по порядку:
   а) УТВЕРЖДЕНИЕ НАЗВАНИЯ — В ПЕРВЫЕ 10 СЕКУНД (первые 20–25 слов). Первая же фраза называет героя по имени и говорит то, ради чего
      зритель кликнул: что с ним случилось или в чём парадокс. Не дата ради даты, не атмосфера, не вопрос, не биография основателя.
      Зритель за 10 секунд должен понять: «это про то, что написано в названии, и мне сейчас это расскажут».
   б) МАСШТАБ — ОДНИМ-ДВУМЯ ЧИСЛАМИ. Насколько это было большим и чем кончилось: одна пара «было → стало» или одно число и одно
      сравнение из жизни зрителя. ВО ВСЁМ cold open НЕ БОЛЬШЕ ПЯТИ ЧИСЕЛ, считая годы. Остальные цифры — в следующих частях.
   в) СОБЫТИЕ на 15–45-й секунде: кто-то конкретный что-то сделал — подписал, продал, закрыл, отказал, назвал цену. Одна сцена,
      которую можно увидеть: здание, день, предмет, сделка. Не описание положения дел и не справка о компании.
   г) ОБЕЩАНИЕ МЕХАНИЗМА БЕЗ ОБЪЯСНЕНИЯ. Одна-две фразы-утверждения: на чём герой зарабатывал на самом деле и что это же его и
      погубило (или спасло). Назвать — да, объяснять — нет: объяснение зритель получает в середине ролика. Не вопросом.
   д) ОДИН ПРЫЖОК В НАЧАЛО: последняя фраза cold open переносит в первую сцену истории («To see how that happened, go back to 1914,
      to a mining town in Minnesota»). Дальше рассказ идёт строго по порядку лет, без возвратов и забеганий.
   е) ПИЛОТ 19.10 (STRATEGY.md, 0.4): первые 20–30 секунд — узнаваемая сцена или проблема из жизни зрителя (что он видел, покупал,
      держал в руках, где стоял в очереди); к 45-й секунде понятен главный вопрос ролика. Экономику показывай через действие людей
      (что стало с ценой на полке, кто звонил, кто упаковывал заказ на коленях), а не через выручку, проценты и площади. Финансовый
      факт допустим, только если без него непонятно, что происходит.
   В cold open НЕТ названия канала, слова «subscribe» и просьб к зрителю: о канале — не раньше третьей минуты (см. часть 2).
   Нельзя: «This story doesn't start with…», «But what few people know…», «In this video», риторические вопросы, термины без
   объяснения, перечисление дат и сумм подряд."""

CHANNEL_LINE = ("В КОНЦЕ этой части (это уже третья минута ролика, не раньше) — одна фраза о канале и подписке, 15–25 слов, в ней же тизер "
                "поворота из середины ролика, которого зритель ещё не знает. Своими словами. Раньше этого места канал и подписка не звучат.")

PLANS = {
    "collapse": """2. Откуда он взялся (550–650 слов): первая сцена истории, основатель или первые владельцы, первая идея. Места, даты, люди. {channel}
3. Вершина и настоящий бизнес (750–850): каким герой был на пике и чем он был для обычного человека (абзац «опыт зрителя» — здесь);
   на чём он зарабатывал на самом деле — единица, кто платил, какой актив стоял за вывеской. Через события, не через таблицу.
4. Первая трещина (750–850): решение или внешняя перемена, с которой началось падение; что было видно тогда и что не было.
5. Попытки спастись (650–750): новые владельцы, сделки, продажа частей, сокращения — что пробовали и почему не помогло.
6. Конец (650–750): банкротство, продажа или распад; кто что получил, что стало с людьми, зданиями, маршрутами, именем.
7. Что осталось и вердикт (500–600).""",
    "decision": """2. Откуда он взялся (550–650 слов): первая сцена истории, люди, первая идея. {channel}
3. Бизнес до решения (700–800): на чём герой зарабатывал и почему это работало; чем он был для обычного человека (абзац «опыт зрителя»).
4. Решение (850–950): комната, люди, варианты на столе, цена каждого; кто был за, кто против и почему. Это центральная часть ролика.
5. Что оно дало сразу (650–750): первые месяцы и годы после — деньги, рост, реакция соперников.
6. Счёт (700–800): чем за решение пришлось заплатить позже; одно и то же решение показать с двух сторон.
7. Что осталось и вердикт (500–600).""",
    "family": """2. Основатель (600–700 слов): первая сцена истории, откуда человек и что он придумал. {channel}
3. Правила дома (750–850): как семья владеет и управляет, на чём бренд зарабатывает на самом деле, какие правила основатель оставил
   (не продавать, не занимать, не пускать чужих); чем бренд был для обычного человека (абзац «опыт зрителя»).
4. Наследники (700–800): кто получил доли и должности, кто был готов, кто нет; первые расхождения.
5. Спор (750–850): конфликт внутри семьи или внешний покупатель — суд, предложение, голосование; позиции сторон с цифрами.
6. Чем кончилось (650–750): кто владеет брендом сейчас и сколько получила или потеряла семья.
7. Что осталось и вердикт (500–600).""",
    "mechanism": """2. Откуда это взялось (550–650 слов): первая сцена истории, люди, первая идея. {channel}
3. Первые годы (650–750): что не работало, кто мешал, откуда взялись деньги.
4. Механизм (850–950): как это зарабатывает на самом деле — единица, кто платит, кому достаётся доля, какой договор за этим стоит.
   Через конкретный случай, не через таблицу. Абзац «опыт зрителя» — здесь: что платит он сам и куда идут эти деньги.
5. Масштаб (650–750): рост, соперники, сделки, ошибки на масштабе.
6. Испытание (650–750): кризис, суд или перемена рынка, которая проверила механизм на прочность, и чем это кончилось.
7. Что осталось и вердикт (500–600).""",
    "history": """2. Первый день (550–650 слов): первая сцена истории — место, первый магазин или первая вещь, люди и их первая идея. {channel}
3. Первый прорыв (700–800): что впервые получилось и почему именно у них; чем бренд стал для обычного человека (абзац «опыт зрителя»).
4. Как он стал великаном (800–900): главный механизм роста через конкретные сцены — что видел покупатель, что делали продавцы,
   поставщики, соперники. Не таблица выручки, а поступки людей и их последствия.
5. Испытание (700–800): кризис, ошибка, суд или сильный соперник — как бренд чуть не потерял всё и что сделал.
6. Сегодня (650–750): каким бренд стал, что от первого дня осталось и что изменилось для обычного американца.
7. Что осталось и вердикт (500–600).""",
}

# пилот 19.10 (STRATEGY.md, 0.4): биография — только та, что объясняет поступок; справки о выручке — сценой
BIO_RULE = ("БИОГРАФИЯ И СПРАВКИ: дата рождения, родители, учёба основателя — только если без них непонятно следующее его решение или "
            "препятствие. Абзац-справка (выручка, рост в процентах, число сотрудников, площадь) заменяется сценой с людьми. Одно событие "
            "и одно объяснение причины рассказываются ОДИН раз за весь ролик.")

ENDING = """   Часть 7 по порядку: «Today, …» с сегодняшними цифрами → что пережило основателей и старые решения (здание, маршрут, правило,
   имя) → ВОЗВРАТ К ПЕРВОЙ СЦЕНЕ cold open → ВЕРДИКТ одной парой фраз («X did not fail because … . It failed because … .») →
   последние 35–50 слов: конкретная просьба рассказать в комментариях о ЛИЧНОМ опыте с героем ролика («If you ever rode …, tell us
   which year, which route, and what the ticket cost») → подписка → «Click the video on the screen. I'll see you there.» Своими словами."""

PART_RULE = ("НАЗВАНИЯ ЧАСТЕЙ (поле name) — ИЗ СОДЕРЖАНИЯ ЭТОГО РОЛИКА, 2–5 слов по-английски: событие, место, предмет или имя "
             "(«The Hibbing Bus», «Downtown Terminals», «The 1990 Strike»). Шаблонные имена «Origins», «The Struggle», «The Turning Point», "
             "«Scale», «The Crisis», «Legacy» запрещены: они одинаковы во всех роликах. Часть 1 называется «Cold open».")


def outline_parts(topic: dict | None) -> str:
    """Блок «Части» для prompts/story_outline.md: вступление по схеме блока и план частей по типу сюжета."""
    s = of(topic); st = s["story_type"] if s else "mechanism"
    ending = ENDING
    if st == "history":   # бренд жив: вердикт о том, почему он выжил и вырос, а не почему упал
        ending = ENDING.replace("(«X did not fail because … . It failed because … .»)", "(«X did not win because … . It won because … .»)")
    return (COLD_OPEN + "\n" + PLANS[st].replace("{channel}", CHANNEL_LINE) + "\n" + ending + "\n\n" + BIO_RULE + "\n\n" + PART_RULE)


def count_numbers(text: str) -> int:
    """Сколько чисел слышит зритель: цифрами и словами-числительными с единицей («two billion», «ninety percent»)."""
    t = re.sub(r"\[F\d+\]", " ", text or "")
    digits = re.findall(r"\$?\d[\d,]*(?:\.\d+)?", t)
    words = re.findall(r"\b(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|"
                       r"hundred|half|quarter)(?:[- ](?:one|two|three|four|five|six|seven|eight|nine))?\s+(?:hundred|thousand|million|billion|trillion|percent|"
                       r"dollars?|cents?|years?|times)\b", t, re.I)
    return len(digits) + len(words)
