"""Обложка в стиле канала «до → после» без участия владельца (владелец 20.09: «ты должен делать превью в стиле канала»).
До 21.09 сетку ThumbV собирал разовый скрипт под каждый ролик, а конвейер сам рисовал генерированную картинку с заголовком —
в автономном режиме на канал ушла бы чужая по стилю обложка.

Слева ч/б «тогда»: фон эпохи и вырезанный герой, цифра старта; справа «сейчас» и большая цифра; посередине знак бренда.
Цифры — из брифа (thumb_then / thumb_now / thumb_years), чего нет — одним запросом по фактам ресёрча. Портрет — только
проверенный кадр из самого ролика (portrait_ok после preflight.verify_portraits): без него обложка не собирается и остаётся
генерированная (честная запасная лучше чужого лица). Название, превью и первые 60 секунд — одно обещание (разбор канала 21.09)."""
import json, os, re, shutil, subprocess
from pathlib import Path
from .. import config, db, llm

MARKS = {"GOOGL": "google", "GOOG": "google", "MSFT": "microsoft", "AMZN": "amazon", "NFLX": "netflix"}
# компании без встроенного знака в ThumbV: надпись именем (topic хранит тикер и героев, а не название компании)
NAMES = {"AAPL": "Apple", "NVDA": "NVIDIA", "META": "Meta", "TSLA": "Tesla", "NFLX": "Netflix", "ORCL": "Oracle", "INTC": "Intel", "IBM": "IBM",
         "UBER": "Uber", "ABNB": "Airbnb", "NKE": "Nike", "SBUX": "Starbucks", "MCD": "McDonald's", "DIS": "Disney", "KO": "Coca-Cola",
         "WMT": "Walmart", "COST": "Costco", "JPM": "JPMorgan", "V": "Visa", "MA": "Mastercard", "PYPL": "PayPal", "ADBE": "Adobe",
         "CRM": "Salesforce", "AMD": "AMD", "TSM": "TSMC", "ASML": "ASML", "SPOT": "Spotify", "SHOP": "Shopify", "BRK": "Berkshire", "F": "Ford"}
THEN_MAX, NOW_MAX = 10, 7   # плашки kind=split: слева 104 px («$1,000,000» влезает), справа 168 px («$294B», «$3T»); длиннее — не влезет и не прочтётся
NOPPL = ", no people, no readable words, no logos, no brand names, no text"
IMG = (".jpg", ".jpeg", ".png", ".webp")


def _hooks(v: dict, b: dict, vid: str) -> dict:
    """then / now / годы / два фона. Бриф главнее модели; модель добирает недостающее из фактов и объясняет откуда цифры."""
    facts = (v["payload"].get("research") or {}).get("facts") or []
    t = v["payload"].get("topic") or {}
    have = {k: b.get(k) for k in ("thumb_then", "thumb_now", "thumb_years") if b.get(k)}
    fx = "\n".join(f"- {f.get('id')}: {str(f.get('fact') or f.get('text') or f.get('claim') or '')[:220]}"
                   + (f" [{f.get('value')} {f.get('unit') or ''}, {f.get('date') or f.get('as_of') or ''}]" if f.get("value") else "") for f in facts[:80])
    q = ("Ты собираешь обложку YouTube в сетке «до → после» для документального ролика об истории компании (аудитория США).\n"
         f"Компания: {t.get('ticker', '')} {t.get('hero') or ''}\nОбещание названия: {b.get('title_promise') or v.get('title')}\n"
         f"Тезис: {b.get('thesis') or t.get('thesis', '')}\nУже решено в брифе (не менять): {json.dumps(have, ensure_ascii=False)}\n\n"
         f"Факты ресёрча:\n{fx}\n\n"
         "Нужно:\n"
         "- then: подпись слева, «тогда» — стартовая цифра или одно слово ИЗ ФАКТОВ, не длиннее 10 знаков («$800», «$1,000,000», «ILLEGAL», «2 PEOPLE»).\n"
         "- now: подпись справа, «сейчас» — сегодняшний масштаб той же вещи, не длиннее 8 знаков («$3T», «$294B», «$678B»). Цифра из фактов "
         "или простая производная от них (укажи формулу в why). Никаких чисел, которых нельзя вывести из фактов.\n"
         "- years: два года ['тогда', 'сейчас'] — год события слева и текущий год из фактов.\n"
         "- bg_then: описание чёрно-белой документальной фотографии места, где всё началось (эпоха, предметы, интерьер), по-английски, "
         "без людей, без текста и логотипов.\n"
         "- bg_now: описание современной широкой фотографии того, КАК ЭТОТ БИЗНЕС ВЫГЛЯДИТ СЕГОДНЯ ДЛЯ КЛИЕНТА — свой образ для каждой компании: "
         "гостиная с большим экраном (стриминг), ресторан с очередью авто, торговый зал, конвейер, порт, стадион, штаб-квартира. "
         "По-английски, без людей, без текста и логотипов. НЕ повторять образы соседних роликов канала: " + (_recent_bgs(vid) or "—") + ". "
         "Дата-центры и серверные стойки — только если компания буквально продаёт вычисления, и не чаще раза на пять роликов.\n"
         "Верни JSON: {\"then\": \"...\", \"now\": \"...\", \"years\": [\"1976\", \"2026\"], \"bg_then\": \"...\", \"bg_now\": \"...\", \"why\": \"...\"}")
    r = llm.ask_json(q, max_tokens=900, tag="thumbv_" + vid, model=config.LLM_MODEL_FACTCHECK or None)
    years = have.get("thumb_years") or r.get("years") or []
    years = [str(y).strip() for y in years if re.fullmatch(r"\d{4}", str(y).strip())] if isinstance(years, (list, tuple)) else []
    out = {"then": str(have.get("thumb_then") or r.get("then") or "").strip().upper(),
           "now": str(have.get("thumb_now") or r.get("now") or "").strip().upper(),
           "years": years[:2] if len(years) == 2 else [],
           "bg_then": str(r.get("bg_then") or "").strip(), "bg_now": str(r.get("bg_now") or "").strip(), "why": str(r.get("why") or "")}
    for k, lim in (("then", THEN_MAX), ("now", NOW_MAX)):
        if not out[k]: raise ValueError(f"обложка: нет подписи {k}")
        if len(out[k]) > lim: raise ValueError(f"обложка: подпись {k} «{out[k]}» длиннее {lim} знаков — не влезет в плашку")
    if not out["bg_then"] or not out["bg_now"]: raise ValueError("обложка: модель не описала фоны")
    print(f"[thumbv] {out['then']} → {out['now']} ({' → '.join(out['years']) or 'без годов'}); {out['why'][:160]}", flush=True)
    return out


def _recent_bgs(vid: str, n: int = 5) -> str:
    """Правые фоны последних обложек — чтобы не ставить серверную в третий раз подряд (владелец 21.09: «нужно разнообразие»)."""
    try:
        rows = db.conn().execute("SELECT id, payload FROM videos WHERE id != ? ORDER BY rowid DESC LIMIT 12", (vid,)).fetchall()
        out = []
        for r in rows:
            tv = (json.loads(r["payload"] or "{}").get("thumbv") or {})
            if tv.get("bg_now_prompt"): out.append(str(tv["bg_now_prompt"])[:90])
        return "; ".join(out[:n]) or "data center server racks (Google, Netflix), office servers (Microsoft)"
    except Exception: return "data center server racks"

def _frame(src: Path, out: Path, clip_seconds: float | None) -> Path:
    """Кадр из архивного клипа: портреты в ролике часто взяты из видео. Берём середину клипа — именно этот кадр смотрела
    проверка лиц (preflight.verify_portraits: clip_seconds / 2); slot.at — смещение появления в сцене, не время в клипе."""
    try: dur = float(subprocess.check_output([config.ffprobe(), "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(src)], timeout=60))
    except Exception: dur = float(clip_seconds or 6)
    t = max(0.5, (float(clip_seconds) if clip_seconds else dur) / 2)
    subprocess.run([config.ffmpeg(), "-y", "-v", "error", "-ss", f"{t:.2f}", "-i", str(src),
                    "-frames:v", "1", "-q:v", "2", str(out)], check=True, timeout=120)
    return out


def _portrait(v: dict, d: Path, tl: dict) -> tuple[Path, str] | None:
    """Проверенный портрет героя из самого ролика: сперва первый в касте, потом ранняя эпоха (левая панель — «тогда», ч/б),
    фото раньше кадра из видео, ранние сцены раньше поздних."""
    cast = [c["name"] for c in (v["payload"].get("entities") or {}).get("cast") or [] if c.get("name")]
    cands = []
    for s in tl.get("scenes", []):
        for sl in s.get("slots") or []:
            if not sl.get("portrait_ok") or sl.get("role") != "portrait": continue
            src = sl.get("src") or sl.get("image")
            if not src or not (d / src).exists(): continue
            who = str(sl.get("person") or sl.get("caption") or "")
            rank = cast.index(who) if who in cast else len(cast)
            m = re.search(r"\d{4}", str(sl.get("era_year") or sl.get("year") or ""))
            era = int(m.group(0)) if m else 9999
            is_img = Path(src).suffix.lower() in IMG
            try: asp = float(sl.get("aspect") or 1.5)
            except (TypeError, ValueError): asp = 1.5
            group = 0 if asp <= 1.05 else 1   # широкий снимок — почти всегда групповой (Netflix 21.09: Хастингс в Корпусе мира с тремя людьми ушёл на обложку)
            cands.append((rank, group, era, 0 if is_img else 1, float(s.get("start") or 0), d / src, who, sl.get("clip_seconds")))
    if not cands: return None
    cands.sort(key=lambda c: c[:5])
    for rank, group, era, _, _, src, who, clip_seconds in cands[:6]:
        if src.suffix.lower() not in IMG:
            src = _frame(src, d / "archive" / "thumbv_frame.jpg", clip_seconds)
        if _solo(src, who): return src, who
        print(f"[thumbv] {src.name}: не сольный портрет {who} — следующий кандидат", flush=True)
    return None


def _solo(src: Path, who: str) -> bool:
    """Обложка — лицо канала: в кадре ровно один человек, лицо крупно и анфас/три четверти. Сбой проверки = отказ (лучше генерированная)."""
    try:
        r = llm.ask_vision("Это фото пойдёт на обложку YouTube как вырезанный портрет человека по имени " + who + ". Верни JSON: "
                           '{"people": <сколько людей в кадре>, "face_large": true|false, "ok": true|false, "why": "..."}. '
                           "ok=true только если в кадре РОВНО один человек, лицо занимает заметную часть кадра, смотрит в камеру или в три четверти, "
                           "нет посторонних людей, сцены, трибуны с логотипами и текста поверх.",
                           [src.read_bytes()], tag="thumbv_solo", model=config.LLM_MODEL_VISION)
        return bool(r.get("ok")) and int(r.get("people") or 0) == 1
    except Exception as e:
        print(f"[thumbv] проверка портрета не прошла: {str(e)[:120]}", flush=True); return False


def _cut_uncropped(v: dict, d: Path, cut: Path, fal_usd: list, tl: dict | None = None):
    """Перебираем проверенные портреты, пока не найдём такой, где голова не обрезана исходным снимком (владелец 22.09:
    «люди не должны быть обрезанными»). Возвращает (источник, имя, edges): edges.side — обрезанный бок ушёл за рамку, снимок при
    необходимости отзеркален (обрезка справа → слева), чтобы край всегда прятался за левым краем кадра."""
    from PIL import Image, ImageOps
    from . import assets as A
    tried = set()
    for attempt in range(6):
        por = _portrait_nth(v, d, tl, tried)
        if not por: break
        src, who = por; tried.add(src)
        im = Image.open(src); W, H = im.size
        if max(W, H) < 1000:   # мелкий снимок (коллаж, старая пресса) — апскейл до вырезки, иначе лицо на обложке пиксельное (McDonald's 22.09)
            try:
                from . import restore
                up = d / "archive" / f"thumbv_up_{src.stem}.png"
                if not up.exists(): restore.photo(src, up, 1800)
                if up.exists(): src = up; im = Image.open(src); W, H = im.size; print(f"[thumbv] {src.name}: апскейл до {W}×{H}", flush=True)
            except Exception as e: print(f"[thumbv] апскейл не удался: {str(e)[:80]}", flush=True)
        bb = A.cutout(src, cut, portrait=True, trim=False); fal_usd.append(0.02)
        if not bb or (bb[3] - bb[1]) < 260: print(f"[thumbv] {src.name}: вырезка мелкая {bb}", flush=True); continue
        top, left, right = bb[1] <= 3, bb[0] <= 3, bb[2] >= W - 3
        if top: print(f"[thumbv] {src.name}: голова обрезана снимком — следующий кандидат", flush=True); continue
        c = Image.open(cut); c = c.crop(c.split()[-1].getbbox())
        if right and not left: c = ImageOps.mirror(c); left, right = True, False   # обрезанный бок — к левому краю кадра
        c.save(cut)
        return src, who, {"side": bool(left), "mirrored": right is False and bb[2] >= W - 3}
    raise ValueError("нет проверенного портрета с целой головой — обложку в стиле канала не собрать")


def _portrait_nth(v: dict, d: Path, tl: dict | None, skip: set):
    """Следующий кандидат портрета, минуя уже отвергнутые файлы."""
    import json as _j
    tl = tl or _j.loads(config.read(d / "timeline.json"))
    cast = [c["name"] for c in (v["payload"].get("entities") or {}).get("cast") or [] if c.get("name")]
    cands = []
    for s in tl.get("scenes", []):
        for sl in s.get("slots") or []:
            if not sl.get("portrait_ok") or sl.get("role") != "portrait": continue
            src = sl.get("src") or sl.get("image")
            if not src or not (d / src).exists() or (d / src) in skip: continue
            who = str(sl.get("person") or sl.get("caption") or "")
            rank = cast.index(who) if who in cast else len(cast)
            m = re.search(r"\d{4}", str(sl.get("era_year") or sl.get("year") or "")); era = int(m.group(0)) if m else 9999
            try: asp = float(sl.get("aspect") or 1.5)
            except (TypeError, ValueError): asp = 1.5
            is_img = Path(src).suffix.lower() in IMG
            cands.append((rank, 0 if asp <= 1.05 else 1, era, 0 if is_img else 1, float(s.get("start") or 0), d / src, who, sl.get("clip_seconds")))
    cands.sort(key=lambda c: c[:5])
    for rank, group, era, _, _, src, who, clip_seconds in cands:
        if src in skip: continue
        if src.suffix.lower() not in IMG:
            src2 = _frame(src, d / "archive" / f"thumbv_frame_{src.stem}.jpg", clip_seconds)
            if src2 in skip: continue
            skip.add(src); src = src2
        if _solo(src, who): return src, who
        skip.add(src); print(f"[thumbv] {src.name}: не сольный портрет {who} — следующий кандидат", flush=True)
    return None


def company_name(t: dict) -> str:
    """Название компании для обложки. Тикер и код темы на обложку не попадают (Boston Market 24.09: «BOSTONCHK»)."""
    if str(t.get("company") or "").strip(): return str(t["company"]).strip()
    tk = str(t.get("ticker") or "").upper()
    if tk in NAMES: return NAMES[tk]
    if tk in {"AMZN": 1, "GOOGL": 1, "GOOG": 1, "MSFT": 1}:   # у них встроенный знак, в NAMES их не было — AMZN дал «Jeff Bezos Turned»
        return {"AMZN": "Amazon", "GOOGL": "Google", "GOOG": "Google", "MSFT": "Microsoft"}[tk]
    for f in ("stories.txt", "stories_es.txt"):
        p = config.ROOT / f
        if not p.exists(): continue
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            parts = [x.strip() for x in line.lstrip("#").split("|")]
            if len(parts) >= 2 and parts[0].upper() == tk and parts[1]:
                return re.split(r"\s+[—–-]\s+|\s*\(", parts[1])[0].strip()
    m = re.match(r"^(?:How|Why|When|Inside|The)?\s*((?:[A-Z][\w&'.-]*\s?){1,3})", str(t.get("working_title") or ""))
    return (m.group(1).strip() if m else "") or tk.title()


def _key(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s).lower().replace("'s", "s"))


# 08.10: отраслевые хвосты — знак Spirit Airlines на Commons подписан просто «spirit», Eastern Air Lines — «Eastern»
CORP_TAIL = re.compile(r"(\s+(airlines|air\s+lines|airways|lines|stores|restaurants|foods|motors|title|inc\.?|corp\.?|corporation|company|co\.?|group|holdings|financial|wholesale|international|plc|ltd\.?|s\.?a\.?|n\.?v\.?|ag|se))+$", re.I)

def _keys(name: str) -> list[str]:
    """Полное название и без служебного хвоста: логотип First American Title на Commons подписан «First American»."""
    ks = [_key(name), _key(CORP_TAIL.sub("", name.strip()))]
    return [k for i, k in enumerate(ks) if len(k) >= 3 and k not in ks[:i]]


def _trim(png: bytes) -> bytes:
    """Обрезать белые и прозрачные поля вокруг знака (отступ 3 %)."""
    import io
    from PIL import Image, ImageChops
    try:
        im = Image.open(io.BytesIO(png)).convert("RGBA")
        bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
        flat = Image.alpha_composite(bg, im).convert("RGB")
        diff = ImageChops.difference(flat, Image.new("RGB", im.size, (255, 255, 255))).convert("L").point(lambda v: 255 if v > 18 else 0)
        bb = diff.getbbox()
        if not bb: return png
        pad = int(0.03 * max(bb[2] - bb[0], bb[3] - bb[1]))
        bb = (max(0, bb[0] - pad), max(0, bb[1] - pad), min(im.width, bb[2] + pad), min(im.height, bb[3] + pad))
        out = io.BytesIO(); im.crop(bb).save(out, "PNG"); return out.getvalue()
    except Exception: return png


def _logo(name: str, d: Path, about: str = "") -> tuple[Path, bool] | None:
    """Настоящий логотип компании (владелец 22.09: «везде хороший логотип, а не надпись белым»; 26.09: «адаптируй под компанию»).
    Источники: Commons → файлы enwiki по названию → логотипы со страницы компании в enwiki (First American: «FALogo FA Vert-rgb.png»).
    Кандидата проверяет основная модель зрения: дословный текст знака содержит название ЦЕЛЫМИ словами (не «First Americans Museum»),
    это не дочерняя марка или доменная зона (Verisign: .name, .cc) и та же компания по описанию."""
    import requests
    from . import archive as AR
    out = d / "archive" / "logo_thumbv.png"; sym = d / "archive" / "logo_symbol_thumbv.png"; meta = d / "archive" / "logo_thumbv.json"
    keys = _keys(name); key = keys[0] if keys else ""
    try: mm = json.loads(meta.read_text(encoding="utf-8")) if meta.exists() else {}
    except Exception: mm = {}
    if mm.get("key") == key and mm.get("v") == 3:   # кэш годится, только если проверен для ЭТОЙ компании текущей проверкой
        if mm.get("symbol") and sym.exists(): return sym, True
        if not mm.get("symbol") and out.exists(): return out, False
    for f in (out, sym): f.unlink(missing_ok=True)
    if len(key) < 3: return None
    names = [n for n in dict.fromkeys([name, CORP_TAIL.sub("", name.strip())]) if n]
    seen, found = set(), {"full": None}
    OLD = re.compile(r"old|19[0-9]{2}|200[0-9]|former|vintage|monochrome|black|white\b|variant|local|inverted|outline|\balt\b|"
                     r"\((?!20[1-3][0-9]\))[^)]*\)", re.I)   # «(Sedona)» — бирюзовые арки одного города (26.09); «(2012)» — можно

    def api(host, **params):
        try:
            r = requests.get(f"https://{host}/w/api.php", headers={"User-Agent": AR.UA}, timeout=60, params={"format": "json", **params}).json()
        except Exception as e: print(f"[thumbv] логотип {host}: {str(e)[:80]}", flush=True); return {}
        if r.get("error"): print(f"[thumbv] логотип {host}: {str(r['error'].get('info'))[:100]}", flush=True); return {}
        return r

    def check(t: str, url: str):
        """None — не подошёл; (путь, символ?) — подошёл символ; полный знак запоминается в found."""
        if t in seen: return None
        seen.add(t)
        try: data = AR._fetch_image(url); png = data if isinstance(data, bytes) else None
        except Exception: png = None
        if png is None:
            try: png = requests.get(url, headers={"User-Agent": AR.UA}, timeout=60).content
            except Exception: return None
        try:
            v = llm.ask_vision(
                f"Нужен текущий официальный логотип компании {name}{(' — ' + about) if about else ''}. Посмотри на картинку и верни JSON: "
                "{\"text\": \"весь текст на знаке ДОСЛОВНО, как написан; пусто, если текста нет\", \"brand\": \"чей это знак, если узнаёшь\", "
                "\"is_logo\": true|false, \"symbol_only\": true|false, \"sub_brand\": true|false, \"same_company\": true|false, \"why\": \"...\"}. "
                "is_logo=true — чистый фирменный знак в стандартных цветах (не фото, не скриншот, не флаг/герб/карта, не старый вариант); "
                "региональный или экологичный цветовой вариант (зелёные/бирюзовые арки McDonald's, монохром) — is_logo=false. "
                "symbol_only=true — только символ без написанного названия. "
                f"sub_brand=true — знак дочерней марки, продукта, доменной зоны, сервиса или подразделения, а не самой компании "
                "(зона .name у Verisign, Kirkland Signature у Costco). "
                "same_company=false — другая организация с похожим названием (музей, фонд, клуб, город, команда, другая фирма).",
                [png], tag="thumbv_logo", model=config.LLM_MODEL_VISION)
        except Exception as e: print(f"[thumbv] логотип {t[:50]}: {str(e)[:60]}", flush=True); return None
        words = re.findall(r"[a-z0-9]+", str(v.get("text") or "").lower().replace("'s", "s"))
        def whole(n):
            w = re.findall(r"[a-z0-9]+", n.lower().replace("'s", "s"))
            joined = "".join(words)
            return bool(w) and (any(words[i:i + len(w)] == w for i in range(len(words) - len(w) + 1))
                                or joined == _key(n) or (len(w) > 1 and joined.startswith(_key(n)) and len(joined) - len(_key(n)) <= 3))
        brand = _key(v.get("brand") or "")
        fits = (bool(words) and any(whole(n) for n in names)) or (not words and bool(v.get("symbol_only")) and any(k in brand for k in keys))
        if not v.get("is_logo") or v.get("sub_brand") or v.get("same_company") is False or not fits:
            print(f"[thumbv] логотип {t[5:60]} отклонён: текст «{v.get('text', '')}», марка «{v.get('brand', '')}»", flush=True); return None
        if v.get("symbol_only"):
            sym.write_bytes(_trim(png)); meta.write_text(json.dumps({"key": key, "file": t, "symbol": True, "v": 3}), encoding="utf-8")
            print(f"[thumbv] символ бренда: {t}", flush=True); return sym, True
        if found["full"] is None: found["full"] = (t, png)
        return None

    # 1-2. поиск файлов по названию: Commons, затем enwiki
    for host in ("commons.wikimedia.org", "en.wikipedia.org"):
        for q in (f"{name} logo", f"{name} logo svg", f"{name} symbol logo", f"{name} wordmark"):
            r = api(host, action="query", generator="search", gsrsearch=q + " -filetype:pdf -filetype:video -filetype:audio", gsrnamespace=6,
                    gsrlimit=12, prop="imageinfo", iiprop="url|size|mime", iiurlwidth=1000)
            for pg in sorted((r.get("query", {}).get("pages") or {}).values(), key=lambda x: x.get("index", 99)):
                t = pg["title"]; ii = (pg.get("imageinfo") or [{}])[0]
                if "logo" not in t.lower() or not ii.get("thumburl") or not any(k in _key(t) for k in keys): continue
                if OLD.search(t) and "current" not in t.lower(): continue
                got = check(t, ii["thumburl"])
                if got: return got
                if len(seen) >= 12: break
        if found["full"]: break
    # 3. логотипы со страницы самой компании в enwiki (имя файла может не содержать названия)
    if not found["full"]:
        for q in (f"{name} company", name):
            hits = (api("en.wikipedia.org", action="query", list="search", srsearch=q, srlimit=3).get("query") or {}).get("search") or []
            for h in hits:
                r = api("en.wikipedia.org", action="query", titles=h["title"], generator="images", gimlimit=50, prop="imageinfo",
                        iiprop="url|size|mime", iiurlwidth=1000)
                for pg in (r.get("query", {}).get("pages") or {}).values():
                    t = pg["title"]; ii = (pg.get("imageinfo") or [{}])[0]
                    if "logo" not in t.lower() or not ii.get("thumburl") or (OLD.search(t) and "current" not in t.lower()): continue
                    if re.search(r"commons-logo|wikiquote|wiktionary|wikidata|question_book|edit-clear|symbol category", t, re.I): continue
                    got = check(t, ii["thumburl"])
                    if got: return got
                if found["full"]: break
            if found["full"]: break
    if found["full"]:
        t, png = found["full"]
        out.write_bytes(_trim(png)); meta.write_text(json.dumps({"key": key, "file": t, "symbol": False, "v": 3}), encoding="utf-8")
        print(f"[thumbv] логотип (с названием): {t}", flush=True); return out, False
    return None


def _brand_color(png: Path) -> str | None:
    """Фирменный цвет — самый частый насыщенный цвет знака (белый, чёрный и серый не в счёт)."""
    from PIL import Image
    import colorsys
    try: im = Image.open(png).convert("RGBA"); im.thumbnail((200, 200))
    except Exception: return None
    bins = {}
    for r, g, b, a in im.getdata():
        if a < 128: continue
        h, l, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
        if s < 0.35 or l < 0.12 or l > 0.88: continue
        k = (r // 24, g // 24, b // 24); bins[k] = bins.get(k, 0) + 1
    if not bins: return None
    r, g, b = [c * 24 + 12 for c in max(bins, key=bins.get)]
    return f"#{r:02X}{g:02X}{b:02X}"


def _aspect(png: Path) -> float:
    from PIL import Image
    try:
        im = Image.open(png).convert("RGBA"); bb = im.split()[-1].getbbox() or (0, 0, im.width, im.height)
        return round((bb[2] - bb[0]) / max(1, bb[3] - bb[1]), 3)
    except Exception: return 2.0


LOGO_STYLES = {
    "pill": "тёмная плашка с логотипом сверху по центру — нейтрально, подходит всем",
    "sign": "световой короб-вывеска с логотипом в фирменных цветах на стороне «сейчас» — розница, рестораны, бренды, которые люди видят на фасадах",
    "stamp": "печать цвета бренда, повёрнутая, на стороне «сейчас» — сделки, реестры, страхование, договоры, банки, всё, что держится на бумаге и подписи",
    "badge": "логотип белым на плашке фирменного цвета — технологии, платформы, сервисы, приложения",
    "ghost": "крупный полупрозрачный знак за правой цифрой — только для узнаваемого символа без текста",
}


def _recent_styles(vid: str, n: int = 2) -> list[str]:
    rows = db.conn().execute("SELECT id, payload FROM videos WHERE id != ? AND payload LIKE '%logoStyle%' ORDER BY created DESC LIMIT ?", (vid, n)).fetchall()
    out = []
    for r in rows:
        try: out.append(json.loads(r["payload"]).get("thumbv", {}).get("logoStyle"))
        except Exception: pass
    return [x for x in out if x]


def _cls(r, g, b):
    import colorsys
    h, l, s_ = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
    return "white" if l > 0.9 else "black" if l < 0.12 else "grey" if s_ < 0.2 else f"h{int(h * 12) % 12}"


def _knockout(png: Path) -> Path:
    """Маска для перекраски: белое внутри знака — прозрачно (иначе галочка в круге Verisign заливается цветом)."""
    from PIL import Image
    out = png.with_name(png.stem.replace("logo", "logo_mask") + ".png")
    im = Image.open(png).convert("RGBA"); px = im.load(); n0 = n1 = 0
    for y in range(im.height):
        for x in range(im.width):
            r, g, b, a = px[x, y]
            if a < 128: continue
            n0 += 1
            if min(r, g, b) > 225: px[x, y] = (r, g, b, 0); n1 += 1
    if n0 and n1 / n0 > 0.85: im = Image.open(png).convert("RGBA")   # белый знак на прозрачном — маска и есть знак
    im.save(out); return out


def _mono(png: Path) -> bool:
    """Знак можно перекрасить в один цвет и он останется читаемым: разные цвета почти не соприкасаются."""
    from PIL import Image
    try:
        im = Image.open(_knockout(png)).convert("RGBA"); bb = im.split()[-1].getbbox()
        if not bb: return False
        im = im.crop(bb); im.thumbnail((240, 240)); px = im.load()
    except Exception: return False
    W, H = im.size; cl = {}
    for y in range(H):
        for x in range(W):
            r, g, b, a = px[x, y]
            if a >= 128: cl[(x, y)] = _cls(r, g, b)
    if not cl: return False
    touch = sum(1 for (x, y), c in cl.items() for q in ((x + 1, y), (x, y + 1)) if q in cl and cl[q] != c
                and "grey" not in (c, cl[q]))   # серый — сглаживание краёв, не отдельный цвет
    return touch / len(cl) < 0.02


def _logo_style(vid: str, v: dict, name: str, logo: Path | None, symbol: bool, bg2: Path, mono: bool = True) -> tuple[str, str]:
    """Подача логотипа под тему ролика и компанию (владелец 26.09: «не надо со всеми компаниями делать одинаковый логотип»)."""
    t = v["payload"].get("topic") or {}
    recent = _recent_styles(vid)
    allowed = [k for k in LOGO_STYLES if k != "ghost" or symbol]
    if not logo: allowed = [k for k in allowed if k in ("pill", "stamp", "sign")]
    elif not mono: allowed = [k for k in allowed if k not in ("badge", "stamp")]   # многоцветный/залитый знак не перекрашиваем
    opts = "\n".join(f"- {k}: {LOGO_STYLES[k]}" for k in allowed)
    imgs = [p.read_bytes() for p in (logo, bg2) if p and p.exists()]
    try:
        r = llm.ask_vision(
            f"Обложка YouTube-документалки о компании {name}. Тема: {t.get('working_title', '')}. Тезис: {str(t.get('thesis', ''))[:400]}.\n"
            f"На картинках: {'логотип компании и ' if logo else ''}фон правой половины обложки («сейчас»).\n"
            f"Выбери, как подать логотип, чтобы подача говорила о теме ролика и отрасли компании:\n{opts}\n"
            f"Прошлые ролики канала использовали: {', '.join(recent) or '—'}. Повторять их можно, только если другие варианты явно хуже.\n"
            "Верни JSON: {\"style\": \"...\", \"why\": \"одно предложение\"}.", imgs, tag=f"thumbv_style_{vid}", model=config.LLM_MODEL_VISION)
        st = str(r.get("style") or "").strip().lower()
        if st in allowed: return st, str(r.get("why") or "")
    except Exception as e: print(f"[thumbv] подача логотипа: {str(e)[:80]}", flush=True)
    for st in ("stamp", "badge", "sign", "pill"):   # запасной выбор — любой разрешённый, не как в прошлый раз
        if st in allowed and st not in recent: return st, "запасной выбор"
    return "pill", "запасной выбор"


def _wordmark(name: str, out: Path) -> Path:
    """Компания без встроенного знака: надпись именем компании (BrandMark красит её в белый сам)."""
    from PIL import Image, ImageDraw, ImageFont
    font = None
    for f in ("impact.ttf", "arialbd.ttf", "Arial Bold.ttf"):
        try: font = ImageFont.truetype(f, 120); break
        except Exception: continue
    font = font or ImageFont.load_default()
    im = Image.new("RGBA", (10, 10)); dr = ImageDraw.Draw(im)
    x0, y0, x1, y1 = dr.textbbox((0, 0), name, font=font)
    im = Image.new("RGBA", (x1 - x0 + 40, y1 - y0 + 40), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((20 - x0, 20 - y0), name, font=font, fill=(20, 12, 8, 255))
    im.save(out); return out


def _bg(prompt: str, out: Path, fal_usd: list) -> Path:
    if out.exists(): return out
    import fal_client
    from . import assets as A
    model = config.THUMB_IMAGE_MODEL
    r = fal_client.subscribe(model, arguments=A.image_args(model, prompt + NOPPL + ", documentary photograph, film grain, cinematic wide shot", 1920, 1088, thumb=True))
    out.write_bytes(A._get(r["images"][0]["url"], timeout=180))
    fal_usd.append(0.04 if "gpt-image" in model else config.image_price(model, 1920, 1088))
    return out


def make(vid: str, d: Path | None = None, tl: dict | None = None, force: bool = False) -> Path | None:
    """thumb_a.png (1280×720) + thumb_2560.png + thumb_a.keep. Ошибка — исключение наверх: вызывающий решает, оставлять ли генерированную.
    Обложку, выбранную владельцем (thumb_*.keep без пометки thumbv), без force не трогаем: результат остаётся в thumbv/."""
    from . import assets as A
    v = db.get(vid); d = d or db.video_dir(vid)
    tl = tl or json.loads(config.read(d / "timeline.json"))
    owners = [k for k in d.glob("thumb_*.keep") if not k.read_text(encoding="utf-8", errors="replace").startswith("thumbv")]
    keep_owner = bool(owners) and not force
    b = v["payload"].get("brief") or {}; t = v["payload"].get("topic") or {}
    fal_usd = [0.0]; carried = llm.take_cost()   # накопленное этапом рендера (кадры-пробы) раньше выбрасывалось — теперь попадёт в стоимость (рецензия 23.09)
    try:
        (d / "archive").mkdir(exist_ok=True); (d / "images").mkdir(exist_ok=True)
        cut = d / "archive" / "cut_thumbv.png"
        prev = v["payload"].get("thumbv") or {}
        if cut.exists() and prev.get("person") and prev.get("source") and not os.environ.get("THUMBV_NEW_PORTRAIT"):
            # 26.09: пересборка (логотип, подписи) не перебирает портреты заново — проверка «сольный ли» у дешёвой модели нестабильна
            src, who, edges = d / "archive" / prev["source"], prev["person"], {"side": prev.get("cutX") == -70}
            print(f"[thumbv] портрет прежний: {who} ({prev['source']})", flush=True)
        else:
            src, who, edges = _cut_uncropped(v, d, cut, fal_usd, tl)
        hooks = _hooks(v, b, vid)
        bg1 = _bg(hooks["bg_then"], d / "images" / "bg_thumbv_then.png", fal_usd)
        bg2 = _bg(hooks["bg_now"], d / "images" / "bg_thumbv_now.png", fal_usd)
        ticker = str(t.get("ticker") or "").upper()
        props = {"variant": "bold", "kind": "split", "bg": bg1.relative_to(d).as_posix(), "bg2": bg2.relative_to(d).as_posix(),
                 "cut": cut.relative_to(d).as_posix(), "cutH": 500, "cutX": -70 if edges.get("side") else -10, "markSize": 86,   # обрезанный бок — за рамку
                 "hook": hooks["then"], "hook2": hooks["now"], "person": who}
        if len(hooks["years"]) == 2:
            units = [str(u).strip() for u in (b.get("thumb_units") or [])][:2]   # 26.09: «$21B → $10.97» без подписей читалось как превращение
            props["tagL"], props["tagR"] = [" · ".join(x for x in (str(y), units[i] if len(units) == 2 else "") if x) for i, y in enumerate(hooks["years"])]
        cname = company_name(t)
        if ticker in MARKS: props["mark"] = MARKS[ticker]; props["logoStyle"] = "pill"
        else:
            got = _logo(cname, d, about=str((v["payload"].get("topic") or {}).get("thesis") or "")[:200])
            if got and got[1]: props["logo"] = got[0].relative_to(d).as_posix(); props["brandWord"] = cname   # символ + название рядом
            elif got: props["logo"] = got[0].relative_to(d).as_posix()                                     # полный логотип уже с названием
            else: props["brandWord"] = cname.upper()   # логотип не нашёлся — название шрифтом обложки (запасной вариант)
            if got:
                props["logoAspect"] = _aspect(got[0]); props["brandColor"] = _brand_color(got[0]) or "#B3261E"
                props["logoMask"] = _knockout(got[0]).relative_to(d).as_posix()
            else: props["brandColor"] = "#B3261E"
            mono = _mono(got[0]) if got else True
            props["logoStyle"], why_style = _logo_style(vid, v, cname, got[0] if got else None, bool(got and got[1]), bg2, mono)
            print(f"[thumbv] подача логотипа {cname}: {props['logoStyle']} ({props['brandColor']}) — {why_style}", flush=True)
        work = d / "thumbv"; work.mkdir(exist_ok=True)
        pf = work / "props_a.json"; config.write(pf, json.dumps(props, ensure_ascii=False))
        # бандл Remotion (копия папки ролика, ~1.5 ГБ) — во временную папку рендера, не на системный диск, и убирается всегда (18.09: C: забился до нуля)
        tmp = config.RENDER_TMP / "remotion"; tmp.mkdir(parents=True, exist_ok=True)
        env = {**os.environ, "THUMB_SCALE": "2", "TEMP": str(tmp), "TMP": str(tmp)}
        before = set(tmp.glob("remotion-webpack-bundle-*"))
        try:
            r = subprocess.run([shutil.which("node") or "node", "scripts/thumbs.mjs", str(d), str(pf), str(work), str(pf)],
                               cwd=config.REMOTION, capture_output=True, text=True, errors="replace", env=env, timeout=900)
        finally:   # только свой бандл — параллельный рендер держит свой (23.09)
            for p in set(tmp.glob("remotion-webpack-bundle-*")) - before: shutil.rmtree(p, ignore_errors=True)
        big = work / "thumb_a.png"
        if r.returncode or not big.exists():
            raise RuntimeError("рендер ThumbV: " + (r.stderr or r.stdout or "")[-600:])
        from PIL import Image
        im = Image.open(big).convert("RGB")
        if im.size != (2560, 1440): im = im.resize((2560, 1440), Image.LANCZOS)
        if keep_owner:
            print(f"[thumbv] обложка владельца ({owners[0].name}) не тронута; вариант конвейера — {big}", flush=True)
            return big
        for old in ("thumb_a.png", "thumb_2560.png"):   # генерированная обложка остаётся рядом на случай отката
            if (d / old).exists() and not (d / f"{Path(old).stem}_gen.png").exists(): shutil.copy(d / old, d / f"{Path(old).stem}_gen.png")
        im.save(d / "thumb_2560.png"); im.resize((1280, 720), Image.LANCZOS).save(d / "thumb_a.png")
        (d / "thumb_a.keep").write_text("thumbv " + hooks["then"] + " -> " + hooks["now"], encoding="utf-8")
        db.update(vid, payload={"thumbv": {**props, "why": hooks["why"], "source": src.name, "bg_now_prompt": hooks["bg_now"], "bg_then_prompt": hooks["bg_then"]}})
        print(f"[thumbv] обложка в стиле канала: {hooks['then']} → {hooks['now']}, герой {who} из {src.name}, ≈${sum(fal_usd):.2f}", flush=True)
        return d / "thumb_a.png"
    finally:   # расходы записываются и при сбое: запросы к модели и fal уже оплачены
        spent = round(carried + llm.take_cost() + sum(fal_usd), 4)
        if spent:
            cur = float((db.get(vid)["payload"] or {}).get("cost_usd", 0))
            db.update(vid, payload={"cost_usd": round(cur + spent, 4)})
