"""Обезличенная съёмка эпохи вместо генерации (владелец 17.09: «больше оригинальных видео и меньше сгенерированных картинок; можно брать
не своё, но чтобы не было видно, что это другая компания» + «показывать современные кадры, когда говоришь про 19xx, очень странно»).

Замер Apple: 64 % хронометража — генерация, потому что архив ищется только по НАЗВАННОМУ (человек, продукт, событие). Под «склады забиты
товаром» или «разработчики делали игры» съёмки «про Apple» не существует. Решение — настоящая съёмка того же времени, но обезличенная:
  • до ERA_PD_MAX — фильмы общественного достояния с Internet Archive (Prelinger и др.: промышленные, учебные, рекламные ленты 1930–1990-х).
    Фильм скачивается один раз в общий кэш data/cache/ia и режется на куски для любых роликов канала;
  • с ERA_MODERN_FROM — Pexels (настоящая съёмка, лицензия Pexels);
  • между ними источник не используется: лучше генерация, чем анахронизм.
Правила (зашиты в промпты отбора): в кадре не должно быть узнаваемых логотипов и продуктов других компаний, экранного текста и титров;
подпись всегда обезличенная и честная — «electronics assembly, 1970», без имени нашей компании; эпоха кадра проверяется отдельно.
Год сцены берётся из era_year/подписи/года в фразе диктора; без года источник не применяется."""
import json, re, subprocess, threading
from .. import config, llm
from . import archive

IA_SEARCH = "https://archive.org/advancedsearch.php"
IA_META = "https://archive.org/metadata/"
# коллекции по эпохам: Prelinger — промышленные и учебные ленты 1930–1980; Computer Chronicles — ТВ-передача о компьютерах 1983–2002
# (офисы, магазины, выставки, техника тех лет); реклама и домашнее видео — фактура быта
# только кураторские коллекции без водяных знаков: Prelinger (промышленные и учебные ленты) и Computer Chronicles (ТВ о компьютерах 1983–2002)
IA_ERAS = [(1930, 1979, "prelinger"), (1983, 2002, "computerchronicles"), (1975, 1995, "classic_tv_commercials")]
ERA_PD_MAX = 1999           # позже общественного достояния почти нет
ERA_MODERN_FROM = 2005      # Pexels: только для современных сцен
ERA_TOL = 8                 # допуск по году: плёнка 1945-го под сцену 1978-го — чужая эпоха в кадре
CLIP_SEC = archive.CLIP_SEC
MAX_FILM_MB = 180
SKIP_HEAD, SKIP_TAIL = 25.0, 20.0
_used_films: dict = {}      # identifier → [секунды], уже взятые в этом ролике
_banks: dict = {}           # (год_от, год_до) → каталог размеченных кадров эпохи
_used_pexels: set = set()   # id клипов Pexels, уже взятых в этом ролике
_lock = threading.Lock()

QUERY = """Фраза документального фильма: «{phrase}». Нужен обезличенный кадр ТОГО ВРЕМЕНИ (около {year} года), который её иллюстрирует:
занятие, предмет, место, обстановка. Компанию и её продукты называть нельзя — нужна типовая съёмка эпохи (цех, склад, офис, магазин, улица, лаборатория).
Дай 2 поисковых запроса по-английски — по 1–2 слова, устойчивые словосочетания эпохи, без названий компаний, брендов и без года
(«assembly line», «warehouse», «computer store», «office workers», «trade show»), для архива документальных, учебных и рекламных фильмов,
и подпись для экрана: обезличенная, ≤ 5 слов, по-английски, с годом — «electronics assembly line, 1970».
Верни JSON: {"queries": ["…", "…"], "caption": "…"}"""

PICK = """Документальный фильм об истории компании. Фраза озвучки: «{phrase}». Нужен кадр примерно {year} года: {query}.
Ниже плитки с номерами и секундой из одного архивного фильма ({title}, {film_year}).
Выбери ОДНУ плитку, которая иллюстрирует фразу и выглядит как съёмка той эпохи.
Нельзя: экранный текст, титры, заставки, таблицы, логотипы и узнаваемые продукты любых компаний, крупные лица известных людей,
мультипликацию и схемы, тёмные и пустые кадры, современную технику в кадре про прошлое,
СКАН КИНОПЛЁНКИ (видны перфорация, рамки соседних кадров, несколько кадриков в ряд) — это брак, а не кадр.
Кадр должен быть обезличенным: обстановка, руки, техника, толпа — а не конкретная фирма.
Верни JSON: {"n": <номер плитки или 0>, "era_ok": true|false (съёмка похожа на {year} год ±10 лет), "why": "коротко", "caption": "обезличенная подпись ≤5 слов с годом, по-английски"}"""


def _ff():
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def reset():
    _used_films.clear(); _banks.clear(); _used_pexels.clear()


def era_of(sl: dict, ctx: str = "") -> int | None:
    """Год сцены: era_year слота → год в подписи → последний год, названный во фразе диктора."""
    for v in (sl.get("era_year"), sl.get("year")):
        if isinstance(v, (int, float)) and 1800 < int(v) < 2100: return int(v)
    m = re.search(r"\b(1[89]\d\d|20\d\d)\b", str(sl.get("caption") or ""))
    if m: return int(m.group(1))
    ys = re.findall(r"\b(1[89]\d\d|20\d\d)\b", ctx or "")
    return int(ys[-1]) if ys else None


QUERY_NOW = """Фраза документального фильма: «{phrase}». Нужен обезличенный кадр настоящей съёмки, который её иллюстрирует БУКВАЛЬНО — тем,
что человек делает или где находится: работа за ноутбуком, руки с телефоном, переговорка, склад, очередь в магазине, улица с прохожими.
Нельзя абстракции и метафоры (порт с контейнерами под фразу о выручке, биржевые графики под фразу о пользователях) и нельзя названия компаний.
Дай 3 поисковых запроса по-английски для видеостока (по 2–3 слова: «hands using smartphone», «developers working laptop», «people shopping mall»)
и подпись для экрана: обезличенная, ≤ 5 слов, по-английски, без года.
Верни JSON: {"queries": ["…", "…", "…"], "caption": "…"}"""


def _queries(phrase: str, year: int, vid: str) -> tuple[list[str], str]:
    tpl = QUERY_NOW if year >= ERA_MODERN_FROM else QUERY
    try:
        res = llm.ask_json(tpl.replace("{phrase}", phrase[:400]).replace("{year}", str(year)), max_tokens=500, tag=f"era_q_{vid}")
    except Exception as e:
        print(f"[era] запрос не составлен: {str(e)[:70]}"); return [], ""
    qs = [str(q).strip() for q in (res.get("queries") or []) if str(q).strip()][:3 if year >= ERA_MODERN_FROM else 2]
    return qs, str(res.get("caption") or "").strip()


def _collections(year: int) -> str:
    cols = [c for lo, hi, c in IA_ERAS if lo - ERA_TOL <= year <= hi + ERA_TOL]
    return " OR ".join(dict.fromkeys(" OR ".join(cols).split(" OR "))) or IA_ERAS[0][2]


def _ask_ia(query: str, rows: int) -> list[dict]:
    import requests
    p = {"q": query, "fl[]": ["identifier", "title", "year", "downloads"], "rows": rows, "output": "json", "sort[]": "downloads desc"}
    try:
        return requests.get(IA_SEARCH, params=p, headers={"User-Agent": archive.UA}, timeout=45).json()["response"]["docs"]
    except Exception as e:
        print(f"[era] поиск «{query[:50]}»: {str(e)[:60]}"); return []


def _search(q: str, year: int, rows: int = 8) -> list[dict]:
    """Фраза ищется в кавычках (поиск архива ANDит слова по всем полям и без кавычек почти всегда пуст), сначала с фильтром по годам."""
    cols = _collections(year); lo, hi = year - ERA_TOL, year + ERA_TOL
    phrase = '"' + q.replace('"', "") + '"'
    out, seen = [], set()
    for qq in (f'mediatype:(movies) AND collection:({cols}) AND {phrase} AND year:[{lo} TO {hi}]',
               f'mediatype:(movies) AND collection:({cols}) AND {phrase}',
               f'mediatype:(movies) AND collection:({cols}) AND (title:({q}) OR description:({q}))'):
        for d in _ask_ia(qq, rows):
            y = int(d["year"]) if str(d.get("year") or "").isdigit() else None
            if y and abs(y - year) > ERA_TOL: continue          # плёнка 1943 года под сцену 1984-го — мимо эпохи
            if not y and "computerchronicles" not in cols: continue   # без года берём только передачу с известными годами выпуска
            if d["identifier"] in seen: continue
            seen.add(d["identifier"]); d["_dy"] = abs((y or year) - year); out.append(d)
        if len(out) >= 3: break
    return sorted(out, key=lambda d: d["_dy"])[:rows]


WATERMARKED = ("periscope film", "periscopefilm", "footagefarm", "criticalpast", "critical past", "buyoutfootage")


def _meta(ident: str) -> dict:
    import requests
    cache = config.DATA / "cache" / "ia_meta"; cache.mkdir(parents=True, exist_ok=True)
    f = cache / f"{ident}.json"
    if f.exists():
        try: return json.loads(config.read(f))
        except Exception: pass
    try:
        m = requests.get(IA_META + ident, headers={"User-Agent": archive.UA}, timeout=60).json()
    except Exception as e:
        print(f"[era] метаданные {ident}: {str(e)[:60]}"); return {}
    config.write(f, json.dumps(m)); return m


def _clean_source(ident: str, m: dict) -> bool:
    """Отсев загрузчиков, которые ставят водяной знак и таймкод (Periscope Film, A/V Geeks и т. п.): их кадры всё равно бракуются проверкой."""
    md = m.get("metadata") or {}
    blob = " ".join(str(md.get(k) or "") for k in ("uploader", "creator", "credits", "publisher", "collection", "description"))[:600].lower()
    if ident.endswith("Vwr") or any(w in blob for w in WATERMARKED): return False
    return True


def _thumbs(ident: str, m: dict, skip_used: bool = True, limit: int = 20) -> list[dict]:
    """Готовая раскадровка архива: файлы <ident>.thumbs/<ident>_000060.jpg — секунда прямо в имени. Экономит скачивание фильма целиком."""
    import io, requests
    from concurrent.futures import ThreadPoolExecutor
    from PIL import Image
    names = [f["name"] for f in m.get("files", []) if ".thumbs/" in str(f.get("name", "")) and str(f.get("name", "")).endswith(".jpg")]
    if not names: return []
    used = _used_films.get(ident, []) if skip_used else []
    items = []
    for n in sorted(names):
        num = re.search(r"_(\d{6})\.jpg$", n)
        if not num: continue
        t = int(num.group(1))
        if t < SKIP_HEAD or any(abs(t - u) < CLIP_SEC * 1.5 for u in used): continue
        items.append({"t": float(t), "url": f"https://archive.org/download/{ident}/{requests.utils.quote(n)}"})
    items = items[:limit]
    def get(it):
        try:
            r = requests.get(it["url"], headers={"User-Agent": archive.UA}, timeout=40); r.raise_for_status()
            return {**it, "im": Image.open(io.BytesIO(r.content)), "label": f"{it['t']:.0f} s"}
        except Exception: return None
    with ThreadPoolExecutor(8) as ex:
        return [x for x in ex.map(get, items) if x]


def _direct(ident: str, t: float, out) -> bool:
    """Отрезок напрямую из mp4-производной архива: ffmpeg ищет позицию по HTTP и качает только нужные секунды. yt-dlp на лентах Prelinger
    (h.264 + Ogg) отдавал 20 КБ без видеодорожки — так молча терялась большая часть найденных кадров 1960–70-х."""
    import requests
    m = _meta(ident)
    files = [f for f in m.get("files", []) if str(f.get("name", "")).lower().endswith(".mp4") and "h.264" in str(f.get("format", "")).lower()]
    files = files or [f for f in m.get("files", []) if str(f.get("name", "")).lower().endswith(".mp4")]
    if not files: return False
    f = min(files, key=lambda x: int(x.get("size") or 1 << 40))     # самая лёгкая производная: нам хватает 480–720p
    url = f"https://archive.org/download/{ident}/{requests.utils.quote(f['name'])}"
    r = subprocess.run([_ff(), "-y", "-v", "error", "-ss", f"{max(0.0, t - 0.5):.2f}", "-i", url, "-t", str(CLIP_SEC), "-an",
                        "-vf", "scale='min(1920,iw)':-2", *config.ARCHIVE_X264, str(out)], capture_output=True, timeout=240)
    return out.exists() and out.stat().st_size > 50_000


def _section(ident: str, t: float, out) -> bool:
    """Только нужный отрезок: фильм целиком не качаем. Сначала напрямую ffmpeg по HTTP, при неудаче — yt-dlp."""
    try:
        if _direct(ident, t, out): return True
    except Exception as e: print(f"[era] отрезок напрямую {ident}@{int(t)}: {str(e)[:70]}")
    out.unlink(missing_ok=True)
    from yt_dlp.utils import download_range_func
    tmp = out.with_suffix(".part.mp4"); tmp.unlink(missing_ok=True)
    archive._ffdir()
    try:
        with archive._ydl(skip_download=False, outtmpl=str(tmp), format="b[height<=720]/bv*[height<=720]/b",
                          download_ranges=download_range_func(None, [(max(0.0, t - 0.5), t + CLIP_SEC + 1.0)]), force_keyframes_at_cuts=True) as y:
            y.download([f"https://archive.org/details/{ident}"])
    except Exception as e:
        print(f"[era] отрезок {ident}@{int(t)}: {str(e)[:70]}"); tmp.unlink(missing_ok=True); return False
    got = tmp if tmp.exists() else next(iter(out.parent.glob(tmp.stem + ".*")), None)
    if not got or got.stat().st_size < 50_000: return False
    r = subprocess.run([_ff(), "-y", "-v", "error", "-i", str(got), "-t", str(CLIP_SEC), "-an", "-vf", "scale='min(1920,iw)':-2",
                        *config.ARCHIVE_X264, str(out)], capture_output=True)
    got.unlink(missing_ok=True)
    return out.exists() and out.stat().st_size > 50_000


# ── Каталог кадров эпохи ───────────────────────────────────────────────────────────────────────────────────────────────
# Текстовый поиск архива — лотерея: «computer store» даёт 4 фильма, «office workers» и «electronics factory» — ноль
# (замер 17.09: 0 попаданий на 4 сцены 1980-х). Поэтому фильмы берутся ПУЛОМ по коллекции и годам, их раскадровки
# размечаются зрением один раз и кешируются: дальше подбор кадра под фразу — это поиск по тексту описаний, без новых запросов.
POOL_ROWS = 60          # сколько фильмов эпохи тянуть из архива
POOL_FILMS = 18         # сколько из них разметить (по одному запросу зрения на фильм, навсегда в кеш)
TILES_PER_FILM = 20

LABEL = """Плитки — кадры одного архивного фильма «{title}» ({year}), у каждой красный номер.
Для КАЖДОЙ плитки дай короткое описание по-английски (3–7 слов): что в кадре — обстановка, занятие, предметы, люди.
bad=true, если кадр непригоден как иллюстрация: экранный текст, титры, таблица, схема, мультипликация, логотип или узнаваемый
продукт компании, скан киноплёнки с перфорацией, тёмный или пустой кадр, а также ЛЮБАЯ студийная съёмка телепередачи: ведущий или гость
говорят в кадре, люди беседуют за столом в студии, интервью, экран компьютера с интерфейсом программы крупным планом.
Годится только «натура»: цех, офис, магазин, улица, лаборатория, склад, дом, руки за работой, техника в деле.
Верни JSON: {"tiles": [{"n": 1, "what": "workers at assembly line", "bad": false}, …]} — по плитке на каждый номер."""

CHOOSE = """Фраза документального фильма (около {year} года): «{phrase}».
Ниже список кадров архивной съёмки той эпохи с описаниями. Выбери ОДИН, который честно иллюстрирует фразу обстановкой или занятием.
Кадр обезличенный — это правильно: «люди за столами в офисе» под фразу о сотрудниках подходит, совпадение с компанией не нужно.
Не подходит явно чужая тема (спорт под фразу о финансах, кухня под фразу о заводе). Если ничего близкого нет — n = 0.
{list}
Верни JSON: {"n": <номер из списка или 0>, "caption": "обезличенная подпись ≤5 слов по-английски, без года"}"""


POOL_TOPICS = ("computer", "electronics", "office", "factory", "engineer", "business", "industry", "store", "technology", "workers", "school", "telephone")


def _pool(year: int) -> list[dict]:
    """Фильмы эпохи по ТЕМАМ (одно слово в названии/теме/описании + годы), а не по популярности: самые скачиваемые ленты Prelinger —
    реклама хлопьев и школьные фильмы о взрослении, из них на 22 сцены 1975–1977 годов не подошёл ни один кадр. По темам архив отдаёт
    «Threads of Technology» (1970), «Business 1984», «Bell Telephone Super Switch» (1977) — цеха, офисы, магазины, техника тех лет.
    Фильм, попавший в несколько тем, стоит выше. Кеш на год-корзину."""
    lo, hi = year - ERA_TOL, year + ERA_TOL
    cache = config.DATA / "cache" / "ia_pool"; cache.mkdir(parents=True, exist_ok=True)
    f = cache / f"{lo}-{hi}_topics.json"
    if f.exists():
        try: return json.loads(config.read(f))
        except Exception: pass
    found: dict = {}
    for kw in POOL_TOPICS:
        q = f"mediatype:(movies) AND collection:({_collections(year)}) AND year:[{lo} TO {hi}] AND (title:({kw}) OR subject:({kw}) OR description:({kw}))"
        for d in _ask_ia(q, 15):
            y = int(d["year"]) if str(d.get("year") or "").isdigit() else None
            if not y or abs(y - year) > ERA_TOL: continue
            it = found.setdefault(d["identifier"], {"identifier": d["identifier"], "title": str(d.get("title") or "")[:80], "year": y,
                                                    "downloads": d.get("downloads") or 0, "topics": []})
            it["topics"].append(kw)
    tv = lambda d: bool(re.search(r"^(Computer|UNIX|Amiga|TheMacin|Operatin|Business19|Slowdown|Japanese19|Robots|CC\d|episode_)", d["identifier"]))
    out = sorted(found.values(), key=lambda d: (tv(d), -len(d["topics"]), -int(d["downloads"] or 0)))
    if out: config.write(f, json.dumps(out, ensure_ascii=False))
    return out


def _label(doc: dict) -> list[dict]:
    """Разметка раскадровки фильма зрением: [{t, what}] без брака. Один запрос на фильм, кеш навсегда."""
    ident = doc["identifier"]
    cache = config.DATA / "cache" / "ia_labels"; cache.mkdir(parents=True, exist_ok=True)
    f = cache / f"{ident}.json"
    if f.exists():
        try: return json.loads(config.read(f))
        except Exception: pass
    m = _meta(ident)
    if not m or not _clean_source(ident, m): config.write(f, "[]"); return []
    tiles = _thumbs(ident, m, skip_used=False, limit=TILES_PER_FILM)
    if len(tiles) < 4: config.write(f, "[]"); return []
    try:
        r = llm.ask_vision(LABEL.replace("{title}", doc["title"]).replace("{year}", str(doc["year"])),
                           [archive._grid(tiles, cols=5, w=360, h=270)], tag=f"era_label_{ident}", max_tokens=3000)
    except Exception as e:
        print(f"[era] разметка {ident}: {str(e)[:70]}"); return []
    out = []
    for it in (r.get("tiles") or []):
        n = int(it.get("n") or 0)
        if not 1 <= n <= len(tiles) or it.get("bad"): continue
        what = str(it.get("what") or "").strip()
        if what: out.append({"t": tiles[n - 1]["t"], "what": what[:70]})
    config.write(f, json.dumps(out, ensure_ascii=False))
    print(f"[era] размечен {ident} ({doc['year']}): {len(out)} годных кадров из {len(tiles)}", flush=True)
    return out


def _bank(year: int) -> list[dict]:
    """Каталог кадров эпохи: [{ident, title, film_year, t, what}] из размеченных фильмов пула."""
    key = (year - ERA_TOL, year + ERA_TOL)
    if key in _banks: return _banks[key]
    out = []
    for doc in _pool(year)[:POOL_FILMS]:
        for it in _label(doc):
            out.append({"ident": doc["identifier"], "title": doc["title"], "film_year": doc["year"], "t": it["t"], "what": it["what"]})
    _banks[key] = out
    return out


def _choose(phrase: str, year: int, bank: list[dict], vid: str) -> tuple[dict | None, str]:
    """Кадр под фразу — по описаниям, без новых запросов зрения."""
    cand = [c for c in bank if not any(abs(c["t"] - u) < CLIP_SEC * 1.5 for u in _used_films.get(c["ident"], []))][:220]
    if not cand: return None, ""
    lst = "\n".join(f"{i + 1}. {c['what']} ({c['film_year']})" for i, c in enumerate(cand))
    try:
        r = llm.ask_json(CHOOSE.replace("{phrase}", phrase[:300]).replace("{year}", str(year)).replace("{list}", lst),
                         max_tokens=400, tag=f"era_choose_{vid}")
    except Exception as e:
        print(f"[era] выбор кадра: {str(e)[:70]}"); return None, ""
    n = int(r.get("n") or 0)
    if not 1 <= n <= len(cand): return None, ""
    return cand[n - 1], str(r.get("caption") or "").strip()


VERIFY = """Три кадра из одного вырезанного фрагмента — фоновая съёмка (b-roll) для документального фильма об истории технологической компании.
Фраза диктора в этот момент: «{phrase}». Эпоха рассказа — около {year} года. {kind_rule}
Это НЕ буквальная иллюстрация: под фразу о прибыли, сделке или регистрации фирмы буквальной съёмки не бывает, и этого не требуется.
Кадр уже подобран по смыслу; твоя задача — отсеять только брак. Ответь ОДНИМ общим вердиктом на фрагмент:
- fits: false ТОЛЬКО если кадры из явно чужого мира для такого фильма: война и оружие, спорт, кухня и еда, дети и школа, животные, религия,
  медицина, мультфильм, развлекательное шоу. Люди за работой, техника, электроника, офис, магазин, цех, лаборатория, улица, дом, руки — true.
- era_ok: съёмка похожа на {year} год (±10 лет) по технике, одежде, качеству изображения?
- bad_overlay: есть водяной знак, логотип канала или компании, экранный текст, титры, таблица, инфографика, таймкод?
- talking_head: почти весь кадр занимает говорящий человек (ведущий, интервью в студии)?
- filmstrip: внутри ОДНОГО кадра видна перфорация киноплёнки или рамки соседних кадриков? (Сам ряд из трёх кадров — наша раскладка для проверки, это не порок.)
- dark_or_tiny: кадры тёмные, пустые или объект неразличим?
- same_as_label: {label_rule}
- caption: что РЕАЛЬНО видно в кадрах — обезличенная подпись для экрана, ≤ 5 слов по-английски, без года и без названий компаний.
Кадры показаны рядом без каких-либо пометок с нашей стороны.
Верни JSON: {"fits": true|false, "era_ok": true|false, "bad_overlay": true|false, "talking_head": true|false, "filmstrip": true|false, "dark_or_tiny": true|false, "same_as_label": true|false, "caption": "…", "why": "коротко"}"""


def _strip(frames: list) -> bytes:
    """Кадры в ряд БЕЗ пометок. archive._grid рисует на плитках красные номера — проверка принимала их за «оверлей-метку» и браковала
    чистые кадры (17.09: так отклонялась большая часть найденной съёмки эпохи)."""
    import io
    from PIL import Image
    w, h, pad = 560, 315, 10
    out = Image.new("RGB", (len(frames) * w + (len(frames) + 1) * pad, h + 2 * pad), "white")
    for k, im in enumerate(frames):
        im = im.convert("RGB"); im.thumbnail((w, h)); out.paste(im, (pad + k * (w + pad) + (w - im.width) // 2, pad + (h - im.height) // 2))
    buf = io.BytesIO(); out.save(buf, "JPEG", quality=85); return buf.getvalue()


FLAGS = ("bad_overlay", "talking_head", "filmstrip", "dark_or_tiny")


def _one_verdict(r: dict) -> dict:
    """Модель иногда отвечает по каждому кадру ({"1": {...}, "2": {...}, "3": {...}}) — раньше в таком ответе не находилось ключа fits,
    и кадр считался отклонённым. Сводим: подходит, если подходит большинство; любой порок хотя бы в двух кадрах (оверлей — в любом) — брак."""
    if "fits" in r: return r
    per = [v for v in (r.get("frames") if isinstance(r.get("frames"), list) else list(r.values())) if isinstance(v, dict) and "fits" in v]
    if not per: return r
    n = len(per); out = {"fits": sum(bool(v.get("fits")) for v in per) * 2 > n, "era_ok": sum(bool(v.get("era_ok")) for v in per) * 2 >= n,
                         "why": "; ".join(str(v.get("why") or "") for v in per)[:160]}
    for f in FLAGS: out[f] = sum(bool(v.get(f)) for v in per) >= (1 if f == "bad_overlay" else 2)
    return out


def _verify(path, phrase: str, year: int, sid: str, vid: str, modern: bool, label: str | None = None) -> dict:
    """Своя проверка: у обезличенной съёмки не требуется совпадение с подписью (archive._verify_clip для неё слишком строг),
    у стока не требуется «архивность» — но экранный текст, логотипы, говорящая голова и скан плёнки запрещены всегда."""
    import io
    from PIL import Image
    ims = []
    for t in (1.0, CLIP_SEC / 2, CLIP_SEC - 1.5):
        r = subprocess.run([config.ffmpeg(), "-v", "error", "-ss", f"{t:.2f}", "-i", str(path), "-frames:v", "1", "-vf", "scale=640:-1",
                            "-f", "image2pipe", "-vcodec", "png", "-"], capture_output=True)
        if r.stdout: ims.append({"im": Image.open(io.BytesIO(r.stdout)), "label": f"{t:.0f}s"})
    if not ims: return {"ok": False, "why": "кадры не извлеклись"}
    rule = ("Это современная съёмка со стока — «архивность» не требуется, но постановочность допустима только если кадр не выглядит рекламным роликом."
            if modern else "Это архивная плёнка — допустимы зерно, 4:3 и выцветшие цвета.")
    try:
        # кадр выбирался по описанию ОДНОЙ раскадровки, а отрезок длится 8 с и часто уходит на другой план: 17.09 под подписью
        # «hand writing on desk, 1973» оказалось такси, под «assembly line» — шоссе. Подпись теперь пишется по самим кадрам.
        lab = (f"отрезок подбирался по описанию «{label}». Кадры показывают именно это (а не другой план того же фильма)?" if label
               else "всегда true (описания для сверки нет)")
        r = llm.ask_vision(VERIFY.replace("{phrase}", phrase[:300]).replace("{year}", str(year)).replace("{kind_rule}", rule).replace("{label_rule}", lab),
                           [_strip([x["im"] for x in ims])], tag=f"era_verify_{sid}_{vid}")
    except Exception as e:
        return {"ok": False, "why": f"проверка не удалась: {str(e)[:80]}"}   # непроверенный кадр в ролик не идёт
    r = _one_verdict(r)
    if label and r.get("same_as_label") is False: r["fits"] = False; r["why"] = "отрезок ушёл на другой план: " + str(r.get("why") or "")
    ok = bool(r.get("fits")) and not r.get("bad_overlay") and not r.get("talking_head") and not r.get("filmstrip") and not r.get("dark_or_tiny")         and (bool(r.get("era_ok")) or modern)
    return {"ok": ok, "caption": str(r.get("caption") or "").strip(), "why": r.get("why", "") + ("" if ok else f" [fits={r.get('fits')} era={r.get('era_ok')} overlay={r.get('bad_overlay')} head={r.get('talking_head')} strip={r.get('filmstrip')}]")}


def _pexels_fetch(q: str, out) -> int | None:
    """Клип со стока, которого в этом ролике ещё не было (assets._pexels на один запрос всегда отдаёт один и тот же ролик).
    Возвращает id клипа; занятость id отмечается до скачивания — слоты разрешаются в несколько потоков."""
    import os, requests
    r = requests.get("https://api.pexels.com/videos/search", params={"query": q, "per_page": 12, "orientation": "landscape"},
                     headers={"Authorization": os.getenv("PEXELS_API_KEY")}, timeout=60).json()
    for v in r.get("videos") or []:
        if not 5 <= (v.get("duration") or 0) <= 90: continue
        with _lock:
            if v["id"] in _used_pexels: continue
            _used_pexels.add(v["id"])
        files = [f for f in v["video_files"] if f.get("width") and 1280 <= f["width"] <= 1920] or v["video_files"]
        f = max(files, key=lambda x: x.get("width") or 0)
        out.write_bytes(requests.get(f["link"], timeout=300).content)
        return v["id"]
    return None


def _pexels(sl: dict, d, phrase: str, year: int, vid: str, queries: list[str]) -> bool:
    """Современная сцена: настоящая съёмка со стока. Проверяем кадры на логотипы и соответствие фразе; на запрос — до двух клипов."""
    out = d / "archive" / f"{sl['id']}.mp4"; out.parent.mkdir(parents=True, exist_ok=True)
    for q in queries:
        for _ in range(2):
            try: pid = _pexels_fetch(q, out)
            except Exception as e:
                print(f"[era] Pexels «{q}»: {str(e)[:60]}"); break
            if not pid: break
            chk = _verify(out, phrase, year, sl["id"], vid, modern=True)
            if not chk.get("ok"):
                print(f"[era] {sl['id']}: сток «{q}» отклонён — {chk.get('why', '')[:70]}"); out.unlink(missing_ok=True); continue
            w, h = archive._dims(out)
            from .assets import _duration
            try: secs = round(_duration(out), 2)
            except Exception: secs = CLIP_SEC
            sl.update({"image": None, "src": f"archive/{out.name}", "kind": "stock", "clip_seconds": secs, "aspect": round(w / h, 3) if h else 1.78,
                       "src_px": [w, h], "caption": None, "credit": "Pexels", "year": None, "archive": {"type": "stock", "key": f"pexels:{q}", "pexels_id": pid}})
            print(f"[era] {sl['id']}: сток Pexels «{q}»", flush=True)
            return True
    return False


def _put(sl: dict, out, ident: str, t: float, cap: str, film_year: int | None, title: str, why: str = "") -> None:
    """Заполнить слот скачанным отрезком: подпись — по году ФИЛЬМА (честно), а не по году сцены."""
    if film_year: cap = re.sub(r",?\s*(1[89]\d\d|20\d\d)s?\s*$", "", cap).strip(" ,") + f", {film_year}"
    _used_films.setdefault(ident, []).append(t)
    w, h = archive._dims(out)
    sl.update({"image": None, "src": f"archive/{out.name}", "kind": "archive", "clip_seconds": CLIP_SEC, "aspect": round(w / h, 3) if h else 1.78,
               "src_px": [w, h], "caption": cap or None, "year": archive._year_of(cap) or film_year, "credit": "Internet Archive (public domain)",
               "archive": {"type": "era", "key": f"ia:{ident}@{int(t)}", "url": f"https://archive.org/details/{ident}", "why": why, "title": title[:80]}})
    print(f"[era] {sl['id']}: {ident}@{int(t)} — «{cap}»", flush=True)


def _take(sl: dict, d, phrase: str, year: int, vid: str, caption: str) -> bool:
    """Кадр из каталога эпохи: описания уже размечены, остаётся выбрать по смыслу, вырезать отрезок и проверить в движении."""
    with _lock: bank = _bank(year)      # разметка пула — один раз, а не по разу на поток
    if not bank: return False
    for _ in range(3):
        with _lock:
            c, cap = _choose(phrase, year, bank, vid)
            if c: _used_films.setdefault(c["ident"], []).append(c["t"])     # не предлагать этот кадр повторно, даже если он не подойдёт
        if not c: return False
        out = d / "archive" / f"{sl['id']}.mp4"; out.parent.mkdir(parents=True, exist_ok=True)
        if not _section(c["ident"], c["t"], out): continue
        chk = _verify(out, phrase, year, sl["id"], vid, modern=False, label=c["what"])
        if not chk.get("ok"):
            print(f"[era] {sl['id']}: каталог {c['ident']}@{int(c['t'])} отклонён — {chk.get('why', '')[:80]}", flush=True)
            out.unlink(missing_ok=True); continue
        _put(sl, out, c["ident"], c["t"], chk.get("caption") or cap or c["what"] or caption, c["film_year"], c["title"], chk.get("why", ""))
        return True
    return False


def find(sl: dict, d, ctx: str, vid: str, phrase: str | None = None) -> bool:
    """Обезличенный кадр эпохи в слот. True — слот заполнен (src + kind + credit)."""
    year = era_of(sl, ctx)
    if not year: return False
    phrase = (phrase or ctx or sl.get("prompt") or "")[:400]
    queries, caption = _queries(phrase, year, vid)
    if not queries: return False
    if year >= ERA_MODERN_FROM: return _pexels(sl, d, phrase, year, vid, queries)
    if year > ERA_PD_MAX: return False   # 2000–2004: ни плёнки, ни уместного стока — пусть рисует генератор
    if _take(sl, d, phrase, year, vid, caption): return True
    for q in queries:
        for doc in _search(q, year)[:4]:
            ident = doc["identifier"]
            m = _meta(ident)
            if not m or not _clean_source(ident, m): continue
            tiles = _thumbs(ident, m)
            if len(tiles) < 4: continue
            try:
                res = llm.ask_vision(PICK.replace("{phrase}", phrase).replace("{year}", str(year)).replace("{query}", q)
                                     .replace("{title}", str(doc.get("title") or "")[:70]).replace("{film_year}", str(doc.get("year") or "?")),
                                     [archive._grid(tiles)], tag=f"era_pick_{sl['id']}_{vid}")
            except Exception as e:
                print(f"[era] отбор кадра: {str(e)[:70]}"); continue
            n = int(res.get("n") or 0)
            if not 1 <= n <= len(tiles) or not res.get("era_ok", True): continue
            t = tiles[n - 1]["t"]
            out = d / "archive" / f"{sl['id']}.mp4"; out.parent.mkdir(parents=True, exist_ok=True)
            if not _section(ident, t, out): continue
            # подпись — по году ФИЛЬМА (честно), а не по году сцены: «cannery workers, 1945» под фразу о 1978-м — обман
            film_year = int(doc["year"]) if str(doc.get("year") or "").isdigit() else None
            cap = (res.get("caption") or caption or "").strip()
            if film_year:
                cap = re.sub(r",?\s*(1[89]\d\d|20\d\d)s?\s*$", "", cap).strip(" ,") + f", {film_year}"
            chk = _verify(out, phrase, year, sl["id"], vid, modern=False)
            if not chk.get("ok"):
                print(f"[era] {sl['id']}: фрагмент {ident}@{int(t)} отклонён — {chk.get('why', '')[:80]}"); out.unlink(missing_ok=True); continue
            _used_films.setdefault(ident, []).append(t)
            w, h = archive._dims(out)
            yr = archive._year_of(cap) or (int(doc["year"]) if str(doc.get("year") or "").isdigit() else None)
            sl.update({"image": None, "src": f"archive/{out.name}", "kind": "archive", "clip_seconds": CLIP_SEC, "aspect": round(w / h, 3) if h else 1.78,
                       "src_px": [w, h], "caption": cap or None, "year": yr, "credit": "Internet Archive (public domain)",
                       "archive": {"type": "era", "key": f"ia:{ident}@{int(t)}", "url": f"https://archive.org/details/{ident}", "why": res.get("why", ""), "title": str(doc.get("title") or "")[:80]}})
            print(f"[era] {sl['id']}: {ident}@{int(t)} — «{cap}»", flush=True)
            return True
    return False


def seed(shots: list[dict]) -> None:
    """Кадры, уже стоящие в ролике (плёнка архива и клипы стока), повторно не предлагать — вызывать после reset()."""
    for x in shots:
        for sl in x.get("slots") or []:
            a = sl.get("archive") or {}; key = str(a.get("key") or "")
            if key.startswith("ia:") and "@" in key:
                ident, t = key[3:].rsplit("@", 1)
                try: _used_films.setdefault(ident, []).append(float(t))
                except ValueError: pass
            if a.get("pexels_id"): _used_pexels.add(a["pexels_id"])


def upgrade(vid: str, d, s: dict, tl: dict, words: list[dict], parts: set | None = None, limit: int | None = None, threads: int = 4,
            years: tuple[int, int] | None = None) -> dict:
    """Готовый ролик: сгенерированные картинки broll-сцен → настоящая съёмка эпохи (новые ролики получают её сразу в _resolve_slot).
    Фраза берётся из слов диктора в окне сцены. Современный сток не ставится в сцену, окружённую прошлым веком: год во фразе бывает
    забеганием вперёд («…а в 2007-м это изменит всё»), а владелец просил не показывать современные кадры под рассказ про 19xx."""
    from concurrent.futures import ThreadPoolExecutor
    from . import story_assets as SA
    limit = limit if limit is not None else config.ERA_MAX_PER_VIDEO
    by_id = {x["id"]: x for x in tl["scenes"]}
    # год называется в одной фразе из пяти (Apple: 21 сцена из 96) — остальным сценам год даёт рассказ: последний названный диктором.
    # Одиночному году не верим: «…а к 2025-му это будут триллионы» посреди 1980-х — забегание вперёд. Нужны два подряд названных года
    # одной эпохи (оба до 2000 или оба после, не дальше 15 лет друг от друга) — иначе сцена остаётся с картинкой.
    spoken = [(w["s"], int(y)) for w in words for y in re.findall(r"(?<!\d)(1[89]\d\d|20[0-2]\d)(?!\d)", w["w"])]

    def ctx_year(t: float) -> int | None:
        ys = [y for s_, y in spoken if s_ < t][-2:]
        if len(ys) < 2 or (ys[0] >= 2000) != (ys[1] >= 2000) or abs(ys[0] - ys[1]) > 15: return None
        return ys[1]

    jobs = []
    for x in s["shots"]:
        sc = by_id.get(x["id"])
        if not sc or x.get("type") != "broll" or (parts and x.get("part") not in parts): continue
        sl = (x.get("slots") or [{}])[0]
        if sl.get("kind") != "image": continue
        phrase = " ".join(w["w"] for w in words if sc["start"] - 0.05 <= w["s"] < sc["end"])[:400]
        y_phrase, y_ctx = era_of(sl, phrase), ctx_year(sc["start"])
        if y_phrase and y_ctx and abs(y_phrase - y_ctx) > ERA_TOL: y_phrase = None if (y_phrase >= 2000) != (y_ctx >= 2000) or abs(y_phrase - y_ctx) > 15 else y_phrase
        jobs.append({"shot": x, "slot": sl, "phrase": phrase, "year": y_phrase or ctx_year(sc["end"]), "t": sc["start"]})
    jobs.sort(key=lambda j: j["t"])
    known = [(k, j["year"]) for k, j in enumerate(jobs) if j["year"]]
    todo = []
    for k, j in enumerate(jobs):
        if not j["year"] or (years and not years[0] <= j["year"] <= years[1]): continue
        if j["year"] >= ERA_MODERN_FROM:
            near = [y for kk, y in known if kk != k and abs(kk - k) <= 3]
            if near and max(near) < 2000:
                print(f"[era] {j['shot']['id']}: год {j['year']} среди сцен {min(near)}–{max(near)} — забегание вперёд, сток не ставлю", flush=True); continue
        todo.append(j)
    reset(); seed(s["shots"])
    done, left = [], {"n": limit}

    def one(j):
        with _lock:
            if left["n"] <= 0: return
        sl, x = j["slot"], j["shot"]; old = {k: sl.get(k) for k in ("image", "src", "kind", "caption", "credit", "year", "aspect", "src_px", "clip_seconds", "archive")}
        try: ok = find(sl, d, j["phrase"], vid, j["phrase"])
        except Exception as e:
            import traceback
            print(f"[era] {x['id']}: {str(e)[-300:]} | {traceback.format_exc()[-500:]}", flush=True); ok = False
        if ok:
            SA._video_dims(sl, d); sl["focus_xy"] = [0.5, 0.45]; SA._mirror(x)
            with _lock: left["n"] -= 1; done.append((x["id"], j["year"], (sl.get("archive") or {}).get("key")))
        else:
            for k, v in old.items():
                if v is None: sl.pop(k, None)
                else: sl[k] = v
            sl["image"] = old["image"]; sl["src"] = old["src"]
        print(f"[era] {x['id']} ({j['year']}): {'ЗАМЕНЁН' if ok else 'нет'}", flush=True)

    with ThreadPoolExecutor(threads) as ex: list(ex.map(one, todo))
    print(f"[era] картинок в broll {len(jobs)}, с годом {len(todo)}, заменено {len(done)}", flush=True)
    return {"images": len(jobs), "tried": len(todo), "done": done}
