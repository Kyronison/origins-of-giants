"""Понедельник: 5 news + 5 anatomy тем → Telegram. Владелец жмёт ✅ на 2–3.
anatomy-темы берутся по очереди из companies.txt (первые 5 компаний, которых ещё нет в очереди видео)."""
import re
from .. import db, llm, telegram, config, series

def next_companies(n=5) -> list[dict]:
    used = set()
    for r in db.conn().execute("SELECT payload FROM videos WHERE status NOT IN ('rejected', 'archived')"):
        m = re.search(r'"ticker":\s*"([A-Z.\-]+)"', r["payload"] or "")
        if m: used.add(m.group(1))
    out = []
    for line in config.read(config.ROOT / "companies.txt").splitlines():
        if not line.strip() or line.startswith("#"): continue
        ticker, name, unit = [x.strip() for x in line.split("|", 2)]
        if ticker not in used: out.append({"ticker": ticker, "name": name, "unit": unit})
        if len(out) >= n: break
    return out

def run():
    comps = next_companies()
    listing = "\n".join(f"- {c['ticker']}: {c['name']} (единица: {c['unit']})" for c in comps) or "(список компаний исчерпан — предложи 5 своих)"
    data = llm.ask_json(config.prompt("topics", companies=listing) + "\n\nrecent_titles: " + str(db.recent_titles()),
                        search=True, heavy=True, max_tokens=12000, tag="topics")
    telegram.send("Темы на неделю — выбери 2–3:")
    for t in data["topics"][:10]:
        slug = re.sub(r"[^a-z0-9]+", "-", str(t.get("slug") or t["working_title"]).lower()).strip("-")[:40]
        if t.get("format") == "anatomy" and t.get("ticker"): slug = f"{t['ticker'].lower().replace('.', '-')}-{slug}"[:40]
        vid = db.add(slug, t["working_title"], {"topic": t})
        telegram.ask_topic_choice(vid, t)


# ---------- формат story: ежедневный выпуск (владелец 18.09: «первый месяц — каждый день») ----------

STORY_PROMPT = """Канал Origins of Giants: англоязычные документальные истории брендов, которые зритель США знает по названию, на 20–24 минуты
(формат story: драматургия, реальные архивные кадры, цифры мелькают на секунды). Уже вышли:
{done}

Составь ОДНУ тему про {name} (код {ticker}); главные люди: {people}. Подсказка угла (не факт, проверь): {hint}.
Тип сюжета: {story_type}. Герой ролика — сам бренд или вещь «{name}»: зритель пришёл узнать про неё, люди — действующие лица.
Используй web search: свежие цифры 2026 года и актуальный повод.
Требования:
- hero — основатель(и) с годами жизни (живой человек — «b. YYYY», без тире);
- thesis — неочевидная мысль, которую доказывает вся история: не «как компания выросла», а на чём она зарабатывает на самом деле
  и в какой момент это было решено. Одно предложение;
- working_title — английское название ролика. {title_rule}
- why_now — почему смотреть сейчас (свежее событие 2026 года);
- unit — единица экономики (один заказ, один подписчик, один доллар выручки сегмента);
- sources — 5–8 АНГЛОЯЗЫЧНЫХ ссылок на первоисточники (10-K, письма акционерам, пресс-релизы, крупная деловая пресса, архивы).
Верни JSON: {{"slug":"...","format":"story","ticker":"{ticker}","working_title":"...","thesis":"...","hero":"...","unit":"...","why_now":"...",
"scores":{{"demand":1-5,"cpm":1-5,"angle":1-5,"evergreen":1-5}},"sources":["..."]}}"""


STORY_TYPES = {"collapse": "крах — что было настоящим бизнесом героя и что его убило",
               "decision": "одно решение — выбор, после которого всё пошло иначе, и его цена",
               "family": "семья — кто владеет брендом, как его делили и чем это кончилось",
               "mechanism": "скрытый механизм знакомой вещи — кто и на чём зарабатывает на самом деле",
               "history": "полная история — как знакомый бренд от первого дня стал тем, чем он есть сегодня, и какой поступок это решил"}

def story_queue(n: int = 1, source: str | None = None) -> list[dict]:
    """Следующие компании из stories.txt, по которым ещё нет story-ролика (отклонённые не считаются)."""
    used = set()
    for r in db.conn().execute("SELECT payload FROM videos WHERE status NOT IN ('rejected', 'archived')"):
        p = r["payload"] or ""
        if '"format": "story"' in p or '"format":"story"' in p:
            m = re.search(r'"ticker":\s*"([A-Z.\-]+)"', p)
            if m: used.add(m.group(1))
    out = []
    for line in config.read(config.ROOT / (source or "stories.txt")).splitlines():
        if not line.strip() or line.startswith("#"): continue
        if line.strip().upper().startswith("STOP"): break   # 29.09: ниже — темы, которые ждут замера или решения владельца; очередь дальше не идёт
        ticker, name, people, hint = [x.strip() for x in line.split("|", 3)]
        tag = None
        if "|" in hint:   # пятое поле — серия и тип сюжета: «A:collapse», «B:mechanism:nologo» (orchestrator/series.py)
            h2, last = [x.strip() for x in hint.rsplit("|", 1)]
            tag = series.parse(last)
            if tag: hint = h2
        if "already made" in hint: continue   # stories_es: уже есть английский ролик — он локализуется сам
        es_only = "es-only" in hint; hint = hint.replace("— es-only", "").replace("es-only", "").strip(" —")
        if ticker not in used: out.append({"ticker": ticker, "name": name, "people": people, "hint": hint, "es_only": es_only, "source": source or "stories.txt", **(tag or {})})
        if len(out) >= n: break
    return out


def run_story(n: int = 1, auto: bool = False, source: str | None = None) -> list[str]:
    """n тем формата story → Telegram с кнопкой «Берём» (auto=True — сразу в производство, без кнопки)."""
    done = [r["title"] for r in db.conn().execute("SELECT title FROM videos WHERE status != 'rejected' AND payload LIKE '%\"format\": \"story\"%'")]
    ids = []
    for c in story_queue(n, source):
        c2 = {k: v for k, v in c.items() if k in ("ticker", "name", "people", "hint")}
        ser = {k: c[k] for k in ("series", "story_type", "no_logo", "formula") if k in c}
        c2["story_type"] = STORY_TYPES.get(ser.get("story_type"), STORY_TYPES["mechanism"])
        c2["title_rule"] = series.title_rule({"company": c["name"], **ser})
        t = llm.ask_json(STORY_PROMPT.format(done="\n".join(f"- {x}" for x in done) or "(пока ничего)", **c2), search=True, heavy=True,
                         max_tokens=6000, tag=f"topic_story_{c['ticker'].lower()}")
        t["format"] = "story"; t["ticker"] = c["ticker"]; t["source"] = c["source"]; t["es_only"] = bool(c.get("es_only")); t.update(ser)
        if c.get("name"): t["company"] = str(c["name"]).strip()
        if c["source"] == "stories_es.txt" and config.ES_CARTOON:   # 12.10 владелец: испанский канал — мультфильм ~20 мин, только на испанском
            t.update({"style": "cartoon", "words": config.ES_CARTOON_WORDS, "es_only": True, "lang_target": "es"})   # 26.09: без него на обложку попадал тикер («BOSTONCHK»)
        slug = re.sub(r"[^a-z0-9]+", "-", str(t.get("slug") or t["working_title"]).lower()).strip("-")[:36]
        vid = db.add(f"{c['ticker'].lower()}-{slug}"[:44], t["working_title"], {"topic": t})
        if auto: db.update(vid, "approved_topic")
        else: telegram.ask_topic_choice(vid, t)
        print(f"[topics] {vid}: {t['working_title']}" + (" → в производство" if auto else " → ждёт кнопки"), flush=True)
        ids.append(vid); done.append(t["working_title"])
    return ids
