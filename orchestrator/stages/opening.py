"""Проверка первых двух минут ПО ОЗВУЧКЕ, а не по тексту (разбор канала 21.09: у Apple две трети зрителей уходят в первую
минуту при 3 400 показах; проверка «первых 170 слов» смотрела не туда — 170 слов это 70 секунд, а обрыв на 10–30-й).

Схема вступления блока 1 (STRATEGY.md, раздел 5; согласована 29.09.2026, заморожена до 24.11). Это гипотеза, а не доказанный приём:
  0–10   — назван герой и звучит утверждение названия; никаких «this story starts…», «in this video»;
  0–90   — масштаб одним-двумя числами, всего не больше пяти чисел (раньше было 10–20);
  15–45  — событие: кто-то конкретный что-то сделал;
  0–90   — механизм назван и обещан, но не объяснён;
  0–120  — ни названия канала, ни просьбы подписаться.
Сначала дешёвые правила, затем одна оценка сильной моделью. Провал → переписывается только вступление (brief.rewrite_opening),
проверка повторяется один раз. Всё это ДО покупки кадров."""
import json, re
from .. import config, db, llm, series

THROAT = re.compile(r"\b(this (story|video|documentary) (doesn'?t|does not|will|is going to)|in this video|welcome to|today we|"
                    r"let'?s (take a look|dive|start)|before we (begin|start))\b", re.I)
CHANNEL = re.compile(r"\b(subscribe|origins of giants)\b", re.I)   # 29.09: канал и подписка — не раньше третьей минуты
FACT = re.compile(r"\d|\$|\b[A-Z][a-z]+ [A-Z][a-z]+\b")   # число, сумма или имя из двух слов

BIO = re.compile(r"\b(was born|born in|adopted|grew up|raised (in|by)|his (father|mother|parents)|her (father|mother|parents)|dropped out|went to (school|college)|graduated|is \d{2} years old|(aged|age) \d{2}|\bis \d{2}\b|\bwas \d{2}\b)\b", re.I)
WINDOWS = ((0, 10), (10, 30), (15, 45), (30, 90), (0, 60), (0, 90), (0, 120))

def words_from_text(text: str, wps: float | None = None) -> list[dict]:
    """Псевдо-тайминги по темпу диктора: проверка ДО озвучки и раскадровки (после раскадровки переписывать вступление нельзя —
    якоря сцен первой минуты привязаны к фразам; ревью 21.09). Точность ±10 %: у Bill 2.34–2.41 слов/с на первых 90 с."""
    wps = wps or config.OPENING_WPS
    ws = re.sub(r"\[F\d+\]|</?short>", " ", text).split()
    return [{"w": w, "s": i / wps} for i, w in enumerate(ws)]

def windows(words: list[dict]) -> dict:
    """Текст по окнам времени озвучки."""
    out = {}
    for a, b in WINDOWS:
        out[f"{a}-{b}"] = " ".join(w["w"] for w in words if a <= float(w["s"]) < b)
    return out

def _plain(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower().replace("’", "'").replace("'", "")).strip()

def rules(win: dict, brand: str = "") -> tuple[list[str], list[str]]:
    """(жёсткие, мягкие): мягкие — в отчёт, но сами по себе не отправляют вступление на переписывание."""
    bad = []; soft = []
    first = win["0-10"]
    if brand:
        if _plain(brand) not in _plain(first): bad.append(f"в первые 10 секунд не назван герой ролика «{brand}»")
    elif not FACT.search(first): bad.append("в первых 10 секундах нет ни числа, ни имени — только подводка")
    for k in ("0-10", "10-30", "30-90"):
        m = THROAT.search(win.get(k, ""))
        if m: bad.append(f"в окне {k} с: «{m.group(0)}» — пустой оборот, зритель уходит")
    m = CHANNEL.search(win.get("0-120", ""))
    if m: bad.append(f"в первые две минуты звучит «{m.group(0)}» — канал и подписка не раньше третьей минуты")
    n = series.count_numbers(win.get("0-90", ""))
    if n > series.NUM_LIMIT_90: bad.append(f"в первые 90 секунд {n} чисел — по схеме блока не больше {series.NUM_LIMIT_90}, считая годы")
    q = re.search(r"[^.!?]*\?", win.get("0-90", ""))
    if q: bad.append(f"во вступлении вопрос «{q.group(0).strip()[:80]}» — по схеме блока только утверждения")
    sent = re.split(r"[.!?]", first)[0].split()
    if len(sent) > 20: soft.append(f"первая фраза {len(sent)} слов — длинно для старта, лучше ≤ 12")
    # 25.09: именно здесь уходит половина зрителей (кривая удержания Apple: 95 % на 17-й секунде, 48 % на 50-й).
    ev = win.get("15-45", "")
    if ev and len(BIO.findall(ev)) >= 2:
        bad.append("на 15–45 секунде биографическая справка (возраст, родители, учёба) вместо события")
    return bad, soft

def judge(vid: str, win: dict, brief: dict) -> dict:
    q = ("Ты — редактор документального YouTube-канала о брендах, которые зритель США знает по названию. Аудитория смотрит на ТВ и "
         "телефоне, решение «уйти» принимает в первые 10–30 секунд. Ниже — что ДИКТОР УСПЕВАЕТ СКАЗАТЬ в первые 10, 30 и 90 секунд "
         "готовой озвучки (это не сценарий, это реальные секунды).\n\n"
         f"0–10 с: {win['0-10']}\n\n10–30 с: {win['10-30']}\n\n15–45 с: {win.get('15-45', '')}\n\n30–90 с: {win['30-90']}\n\n"
         f"ОБЕЩАНИЕ БРИФА (что зритель должен узнать в первые 40 с): {brief.get('opening_payoff', '—')}\n"
         f"НАЗВАНИЕ РОЛИКА (то, ради чего кликнули): {brief.get('title_promise', '—')}\n"
         f"ТЕЗИС РОЛИКА: {brief.get('thesis', '—')}\n\n"
         "Оцени строго:\n"
         "1. ok10 — в первые 10 секунд назван герой и прозвучало утверждение названия: кликнувший сразу слышит то, за чем пришёл. "
         "Декорации, дата ради даты, биография основателя — false.\n"
         "2. ok30 — к 30-й секунде ясен масштаб и ставка: насколько это было большим и чем кончилось, одним-двумя числами, "
         "а не списком цифр.\n"
         "3. ok_event — В ОКНЕ 15–45 с происходит СОБЫТИЕ: кто-то конкретный что-то сделал, продал, закрыл, отказал, "
         "потребовал, подписал, потерял, назвал цену. Это самый дорогой участок ролика: по кривой удержания "
         "именно здесь уходит половина зрителей. Состояние дел — НЕ событие: возраст героев, происхождение, учёба, описание "
         "города и эпохи, справка о компании. Если в окне только такое — ставь false.\n"
         "4. ok90 — к 90-й секунде механизм НАЗВАН И ОБЕЩАН: зритель знает, на чём герой зарабатывал на самом деле или что его "
         "убило, и понимает, что объяснение впереди. Если механизм не назван вовсе — false. Если он уже разжёван по шагам "
         "в первые 90 секунд и досматривать незачем — тоже false.\n"
         "5. ok_promise — утверждение НАЗВАНИЯ названо словами диктора до 60-й секунды (не намёком). "
         "Если названия нет (—), ставь true.\n"
         "Верни JSON: {\"ok10\": true|false, \"ok30\": true|false, \"ok_event\": true|false, \"ok90\": true|false, \"ok_promise\": true|false, "
         "\"why\": \"одно-два предложения\", \"rewrite_hint\": \"чем открыть и в каком порядке: утверждение названия → масштаб → событие → обещание механизма\"}")
    return llm.ask_json(q, max_tokens=900, tag="opening_" + vid, model=config.LLM_MODEL_FACTCHECK or None)

def _verdict(vid: str, win: dict, brief: dict, d, name: str) -> dict:
    try: topic = db.get(vid)["payload"].get("topic") or {}
    except Exception: topic = {}
    ser = series.of(topic)
    # 27.10 Disney: одна и та же озвучка у судьи проходила 2 раза из 4, и повтор этапа заваливал уже принятое вступление.
    # Тот же текст окон, уже получивший «ok», повторно не судим.
    try: prev = json.loads(config.read(d / name)) if (d / name).exists() else None
    except Exception: prev = None
    if isinstance(prev, dict) and prev.get("ok") is True and prev.get("windows") == win:
        print(f"[opening] та же озвучка уже прошла проверку ({name}) — повтор не нужен", flush=True)
        return prev
    bad, soft = rules(win, ser["brand"] if ser else "")
    res = judge(vid, win, brief or {})
    if not isinstance(res, dict) or any(type(res.get(k)) is not bool for k in ("ok10", "ok30", "ok_event", "ok90", "ok_promise")):
        raise ValueError("Проверка вступления вернула неполный ответ")
    if res.get("ok_promise") is False: bad = bad + ["утверждение названия не прозвучало в первые 60 с"]
    if res.get("ok_event") is False: bad = bad + ["на 15–45 секунде нет события — там уходит половина зрителей"]
    ok = not bad and bool(res.get("ok10")) and bool(res.get("ok30")) and bool(res.get("ok90"))
    out = {"ok": ok, "rules": bad, "soft": soft, "judge": res, "windows": win, "numbers_90": series.count_numbers(win.get("0-90", "")),
           "scheme": "STRATEGY.md раздел 5, 29.09.2026"}
    config.write(d / name, json.dumps(out, ensure_ascii=False, indent=1))
    print("[opening] " + ("первые две минуты в порядке" if ok else "вступление слабое: " + "; ".join(bad + [str(res.get("why", ""))]))
          + f" | чисел за 90 с: {out['numbers_90']}" + ("; замечания: " + "; ".join(soft) if soft else ""), flush=True)
    return out

def check(vid: str, d, brief: dict) -> dict:
    """По реальной озвучке (words.json) — после раскадровки только отчёт."""
    return _verdict(vid, windows(json.loads(config.read(d / "words.json"))), brief, d, "opening_check.json")

def check_text(vid: str, d, s: dict, brief: dict) -> dict:
    """По тексту и темпу диктора — до раскадровки, здесь вступление ещё можно переписать."""
    parts = s.get("parts") or [s["script"]]
    return _verdict(vid, windows(words_from_text(" ".join(parts[:2]))), brief, d, "opening_check_text.json")
