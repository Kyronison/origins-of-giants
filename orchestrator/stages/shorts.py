"""YouTube Shorts: с 05.10 новые story-сборки используют calm-story-v1 (спокойные фразы, 4–6 смысловых сцен,
без ускорения речи, второй поверхности цифр и случайных кадров ради смены картинки). Старые спецификации и профиль legacy
сохраняют историческую подачу ниже. Типизированные моушен-панели реализованы штатным ShortHook/ShortStory.

Исторический формат «свежая безумная новость → полное видео» (владелец 17.09: «шортсы должны быть быстрее, динамичнее…
говоришь о какой-то новинке компании, а затем — если хочешь узнать, как они сюда пришли, заходи на канал, и превью видео должно всплывать»).

Раньше Short был вырезкой из длинного ролика: медленный темп, пустая нижняя половина вертикального кадра. Теперь у каждого шортса свой
сценарий на 30–45 с, своя энергичная озвучка и свой монтаж (remotion/src/ShortHook.tsx):
  1. news   — веб-поиск (Qwen :online) самых «вау» новостей компании за 45 дней, с фактами и ссылками → shorts/news.json;
  2. script — хук с числом в первой фразе → 2–3 удара фактами → почему безумно → мост в прошлое → призыв на канал; кадры с якорями;
  3. factcheck — Astra сверяет числа с фактами новости и происхождения;
  4. voice  — ElevenLabs v3 с энергичной разметкой (prompts/voice_tags_short.md), при медленной речи — ускорение atempo;
  5. кадры  — «сейчас»: реальные фото новости из веб-поиска (выбор vision-моделью, без водяных знаков и концепт-рендеров);
              «тогда»: архив из полного видео; смена кадра каждые 1–2.5 с;
  6. spec   — shorts/sN/short.json: кадры, субтитры по 1–3 слова, цифры крупно, концовка с превью полного видео.
Рендер — render.run (композиция ShortHook). Загрузка ручная: у шортса в YouTube Studio указать «Связанное видео» = полный ролик."""
import json, os, re, shutil, subprocess
import requests
from datetime import date
from .. import db, config, llm
from . import archive, assets as A, numbers as N

NEWS_DAYS = 45
TARGET_WPM = 175            # по чистой речи без пауз: быстрее — тараторит, медленнее — свайпают
MAX_TEMPO = 1.1
SENT_PAUSE, CLAUSE_PAUSE, WORD_PAUSE, IDEA_PAUSE = 0.45, 0.2, 0.08, 0.8   # паузы после точки / запятой / внутри фразы / перед сменой мысли
XFADE = 0.04                # кроссфейд на стыках вырезанных пауз
SHOT_MIN, SHOT_MAX = 0.8, 2.6
MAX_FLASHES = 5
END_HOLD = 2.4              # сколько держится превью после последнего слова
STOCK_SKIP = re.compile(r"shutterstock|gettyimages|alamy|dreamstime|istockphoto|depositphotos|123rf|pinterest|vecteezy|freepik|adobestock|pond5|wallpaper|youtube\.com|ytimg|"
                        r"yankodesign|behance|dribbble|artstation|reddit|twitter\.com|//x\.com|facebook|instagram|tiktok|threads\.net|conceptsiphone|concept|render|mockup|dummy|fan-?made", re.I)

PICK_NOW = """Кадр для вертикального YouTube Shorts (9:16) о свежей новости компании.
Новость и её проверенные факты: {news}
Фраза диктора: «{phrase}». Нужен снимок: {query}.
Бери только РЕАЛЬНОЕ фото именно этого продукта или события: официальное пресс-фото компании, фото с презентации, фото из обзора крупного СМИ.
Сверь с фактами: форма и детали продукта должны совпадать (например, книжка против раскладушки, размер экрана); старые модели и чужие продукты — нельзя.
Не бери: ЛЮБОЙ текст поверх снимка (заголовки «EXCLUSIVE», плашки, подписи), логотипы и водяные знаки сайтов и каналов (PhoneArena, EverythingApplePro, News X и т. п.),
коллажи, скриншоты статей и соцсетей, инфографику и графики, ИИ-иллюстрации и 3D-арт, фанатские концепт-рендеры (часто глянцевые, с неестественным фоном),
мемы, мелкие и мутные снимки. Если подходящего нет — 0, это лучше, чем неверный кадр.
Главный объект должен остаться в кадре при обрезке до вертикали (объект в центре или крупно).
Верни JSON: {"picks": [номера годных плиток по убыванию качества, до 3; пусто, если годных нет], "why": "коротко"}"""


def _norm_tokens(s: str) -> list[str]:
    return [t for t in (A._norm(x) for x in re.sub(r"\[[^\]]*\]", " ", s).split()) if t]


def _company(topic: dict) -> str:
    return topic.get("company") or topic.get("ticker") or topic.get("working_title") or ""


def news(vid: str, force: bool = False) -> list[dict]:
    d = db.video_dir(vid); v = db.get(vid); out = d / "shorts" / "news.json"
    if out.exists() and not force:
        return json.loads(config.read(out)).get("items", [])
    out.parent.mkdir(parents=True, exist_ok=True)
    res = llm.ask_json(config.prompt("short_news", today=date.today().isoformat(), company=_company(v["payload"]["topic"]), long_title=v["title"], days=NEWS_DAYS),
                       heavy=True, search=True, max_tokens=6000, tag=f"short_news_{vid}")
    config.write(out, json.dumps(res, ensure_ascii=False, indent=1))
    return res.get("items", [])


def moments(vid: str, force: bool = False, n: int = 3) -> list[dict]:
    """Сюжеты шортсов из самой документалки (SHORTS_SOURCE=story, разбор Astra 20.09): свежая новость — отдельная редакционная
    работа с проверкой актуальности, а материал ролика уже проверен фактчеком и стоил денег. Формат items тот же, что у news()."""
    d = db.video_dir(vid); v = db.get(vid); out = d / "shorts" / "moments.json"
    if out.exists() and not force:
        return json.loads(config.read(out)).get("items", [])
    out.parent.mkdir(parents=True, exist_ok=True)
    s = v["payload"]["script"]; research = v["payload"].get("research") or {}
    from . import brief as B
    b = v["payload"].get("brief") or {}
    segs = re.findall(r"<short>(.*?)</short>", s.get("script") or "", re.S)
    if not segs:   # автор не расставил теги — берём самые плотные по числам куски частей
        segs = sorted((s.get("parts") or []), key=lambda p: -len(re.findall(r"\d", p)))[:3]
    segs = [re.sub(r"\[F\d+\]", "", x).strip()[:1200] for x in segs[:4]]
    res = llm.ask_json(config.prompt("short_story", today=date.today().isoformat(), company=_company(v["payload"]["topic"]),
                                     long_title=v["title"], n=n, brief=B.text(b) if b else "(брифа нет)",
                                     segments="\n\n---\n\n".join(segs) or "(автор не отметил фрагменты)",
                                     facts_json=json.dumps(research.get("facts") or [], ensure_ascii=False)),
                       heavy=True, max_tokens=6000, tag=f"short_story_{vid}", model=config.LLM_MODEL_WRITER or None)
    items = [x for x in res.get("items", []) if x.get("headline") and (x.get("facts") or [])]
    config.write(out, json.dumps({"items": items}, ensure_ascii=False, indent=1))
    print(f"[shorts] сюжетов из ролика: {len(items)} — " + "; ".join(x["headline"][:50] for x in items), flush=True)
    return items


ENRICH = """Сегодня {today}. Новость о компании: {headline} ({date}).
Уже известные факты: {facts}
Найди в интернете 5–8 дополнительных ПРОВЕРЯЕМЫХ фактов именно об этой новости: характеристики, цены, сроки продаж, конструкция, что показали на презентации,
реакция рынка — с точными числами из источника и ссылкой. Слухи, прогнозы и «по данным инсайдеров» — не бери.
Верни JSON: {"facts": [{"fact": "по-английски", "value": <число или null>, "unit": "…", "source_url": "https://…"}]}"""


def _enrich(vid: str, item: dict) -> dict:
    """У новости из общего поиска 2–3 факта — на 30 секунд плотного текста мало, модель начинает лить воду или тащить чужие новости."""
    if len(item.get("facts") or []) >= 6: return item
    try:
        res = llm.ask_json(ENRICH.replace("{today}", date.today().isoformat()).replace("{headline}", item.get("headline") or "").replace("{date}", item.get("date") or "")
                           .replace("{facts}", json.dumps(item.get("facts") or [], ensure_ascii=False)), heavy=True, search=True, max_tokens=4000, tag=f"short_enrich_{vid}")
    except Exception as e:
        print(f"[shorts] дозапрос фактов: {e}"); return item
    seen = {(f.get("fact") or "")[:40].lower() for f in item.get("facts") or []}
    extra = [f for f in res.get("facts") or [] if f.get("fact") and f.get("source_url") and f["fact"][:40].lower() not in seen]
    print(f"[shorts] фактов о новости: {len(item.get('facts') or [])} + {len(extra)}", flush=True)
    return {**item, "facts": (item.get("facts") or []) + extra[:8]}


def _library(s: dict) -> dict:
    """Архивные кадры полного видео, пригодные для «тогда»: id → слот."""
    lib = {}
    for x in s.get("shots") or []:
        for sl in x.get("slots") or []:
            if sl.get("kind") == "archive" and (sl.get("image") or sl.get("src")) and sl.get("caption") and sl.get("role") != "inset":
                lib[sl["id"]] = sl
    return lib


def _broll(s: dict) -> list[dict]:
    """Кадры родительского ролика, уже прошедшие проверку зрением: подложки и сток (архив берёт _library).
    Нужны, когда веб-поиск для шортса пустой: проверенный кадр своего ролика лучше случайной картинки из сети
    и лучше одного и того же скриншота на весь шортс (Google 20.09: один кадр висел 19 секунд, в другом — чужая научная работа)."""
    out, seen = [], set()
    for x in s.get("shots") or []:
        for sl in (x.get("slots") or [x]):
            rel = sl.get("image") or sl.get("src")
            if not rel or rel in seen or sl.get("kind") == "archive" or sl.get("role") == "inset": continue
            seen.add(rel)
            out.append({**sl, "image": sl.get("image"), "src": sl.get("src"), "aspect": sl.get("aspect"), "focus_xy": sl.get("focus_xy"),
                        "clip_seconds": sl.get("clip_seconds"), "kind": "now", "from_story": True, "move": "detail"})
    return out


STOP_W = {"google", "search", "with", "that", "this", "from", "they", "their", "page", "shot", "view", "close", "wide", "scene", "photo"}

def _pick(cands: list[dict], shown: dict, prev, query: str = "", min_hit: int = 0) -> dict | None:
    """Наименее показанный кадр, не повторяющий предыдущий; при равенстве — тот, чей текст ближе к фразе.
    min_hit > 0 — вернуть только по-настоящему подходящий кадр (столько общих слов), иначе None."""
    key = lambda m: (m.get("image"), m.get("src"))
    words = {w for w in re.findall(r"[a-z]{4,}", (query or "").lower())} - STOP_W
    pool = [m for m in cands if key(m) != prev]
    if not pool: return None
    def hits(m):
        txt = " ".join(str(m.get(k) or "") for k in ("desc", "caption", "prompt", "query", "image", "src")).lower()
        return len(words & (set(re.findall(r"[a-z]{4,}", txt)) - STOP_W))
    best = min(pool, key=lambda m: (shown.get(key(m), 0), -hits(m)))
    if min_hit and hits(best) < min_hit:
        best = max(pool, key=hits)                      # ищем самый близкий по теме, а не самый редкий
        if hits(best) < min_hit: return None
    return dict(best)


def _anchor_idx(tokens: list[str], anchor: str, start: int) -> int | None:
    a = _norm_tokens(anchor)[:4]
    for n in (len(a), 3, 2):
        if n <= 0 or n > len(a): continue
        k = A._find(tokens, a[:n], start)
        if k is not None: return k
    return None


def _origin_facts(research: dict) -> list[dict]:
    return [f for f in research.get("facts", []) if str(f.get("date") or "")[:4].isdigit() and int(str(f["date"])[:4]) < 1990][:15]


def _script(vid: str, item: dict, others: list[dict], research: dict, title: str, company: str) -> dict:
    """Текст шортса (без кадров): кадры размечаются уже по тексту после фактчека, иначе правка ломает якоря."""
    note, res = "", {}
    for attempt in range(3):
        tpl = ("short_calm_script" if config.SHORT_STYLE == "calm-story-v1" else "short_funnel") if config.SHORTS_SOURCE == "story" else "short_script"
        res = llm.ask_json(config.prompt(tpl, company=company, long_title=title, news_json=json.dumps(item, ensure_ascii=False),
                                         origin_json=json.dumps(_origin_facts(research), ensure_ascii=False)) + note,
                           heavy=True, max_tokens=4000, tag=f"short_script_{vid}", model=config.SHORT_SCRIPT_MODEL or None)
        text = (res.get("script") or "").strip(); toks = _norm_tokens(text); cta = (res.get("cta") or "").strip()
        problems = []
        if not 50 <= len(toks) <= 95: problems.append(f"в тексте {len(toks)} слов, нужно 60–80")
        if not cta or _anchor_idx(toks, cta, max(0, len(toks) - 14)) is None: problems.append("cta должен быть последней фразой script дословно")
        if not problems: return res
        print(f"[shorts] сценарий: {'; '.join(problems)} — повтор", flush=True)
        note = "\n\nПредыдущая попытка отклонена: " + "; ".join(problems) + f". Текст был: {text}"
    return res


def _split_cta(plan: dict) -> tuple[str, str]:
    text, cta = plan["script"].strip(), (plan.get("cta") or "").strip()
    if cta and text.endswith(cta): return text[: -len(cta)].strip(), cta
    k = text.rfind(cta[:20]) if cta else -1
    return (text[:k].strip(), text[k:].strip()) if k > 0 else (text, cta)


def _factcheck(vid: str, plan: dict, item: dict, others: list[dict], research: dict) -> dict:
    """Astra сверяет тело шортса (без призыва на канал — его правка «убирала») с фактами новостей и происхождения."""
    from . import story
    body, cta = _split_cta(plan)
    facts = [{"id": f"N{i + 1}", **f} for i, f in enumerate([f for it in [item, *others] for f in it.get("facts") or []])] + list(research.get("facts") or [])
    s = story.factcheck(f"short_{vid}", {"parts": [body], "script": body}, {"facts": facts})
    fixed = s["script"].strip()
    if fixed != body:
        print(f"[shorts] фактчек поправил текст: {str(s.get('factcheck', {}).get('summary', ''))[:160]}", flush=True)
    plan["script"] = f"{fixed} {cta}".strip(); plan["cta"] = cta; plan["factcheck"] = s.get("factcheck")
    return plan


def _calm_panel(sh: dict, text: str) -> dict | None:
    """Diagrams may repeat narrated mechanisms, but cannot invent labels or figures."""
    panel = sh.get("panel")
    if not panel: return None
    if not isinstance(panel, dict) or panel.get("layout") != "flow":
        raise ValueError("Unsupported motion diagram")
    headline = str(panel.get("headline") or "").strip()
    nodes = panel.get("nodes") or []
    tokens = _norm_tokens(text)
    labels = [headline] + nodes if isinstance(nodes, list) else []
    if not headline or len(headline) > 75 or not 2 <= len(nodes) <= 3 or not labels:
        raise ValueError("Motion diagram needs a short headline and two or three steps")
    for label in labels:
        if not isinstance(label, str) or not label.strip() or (label != headline and len(label) > 36):
            raise ValueError("Motion label is missing or too long")
        phrase = _norm_tokens(label)
        if not phrase or A._find(tokens, phrase) is None:
            raise ValueError("Motion label is not present in the narration: " + label)
    if len(set(' '.join(_norm_tokens(n)) for n in nodes)) != len(nodes):
        raise ValueError("Repeated motion steps")
    if any(re.search(r"\d", label) for label in labels):
        raise ValueError("Numbers belong on one sourced surface, not repeated diagram labels")
    return {"layout":"flow", "headline":headline, "nodes":nodes,
            "kicker":"How it works", "footnote":"Illustration of the narrated mechanism"}

def _calm_panels(cut: list[dict], end_start: float) -> list[dict]:
    if not any(x.get("panel") for x in cut): return []
    panels = []
    for x in cut:
        if x["start"] >= end_start: continue
        panel = x.get("panel") or {"layout":"photo", "headline":"", "kicker":"",
            "footnote":" · ".join(str(v) for v in (x.get("caption"), x.get("year"), x.get("credit")) if v)}
        panels.append({**panel,"start":x["start"],"end":min(x["end"],end_start),
                       "image":x.get("image"),"src":x.get("src")})
    return panels

def _shots(vid: str, plan: dict, item: dict, lib: dict) -> list[dict]:
    listing = "\n".join(f"{k} | {'video' if sl.get('src') else 'photo'} | {sl.get('caption')}" for k, sl in list(lib.items())[:80])
    toks = _norm_tokens(plan["script"]); note, best, best_found = "", [], -1
    for attempt in range(2):
        calm = config.SHORT_STYLE == "calm-story-v1"
        res = llm.ask_json(config.prompt("short_calm_shots" if calm else "short_shots", script=plan["script"], cta=plan.get("cta") or "", news_json=json.dumps(item, ensure_ascii=False), library=listing) + note,
                           heavy=True, max_tokens=4000, tag=f"short_shots_{vid}", model=config.LLM_MODEL_SHOTS or None)
        shots = res.get("shots") or []; pos, found, previous = 0, 0, -1
        for sh in shots:
            k = _anchor_idx(toks, sh.get("anchor") or "", pos)
            if k is not None and (not calm or k > previous): found += 1; pos = k; previous = k
        if found > best_found: best, best_found = shots, found
        panel_error = ""
        if calm:
            try:
                for sh in shots: _calm_panel(sh, plan["script"])
            except ValueError as e: panel_error = str(e)
        if shots and not panel_error and (found == len(shots) if calm else found >= max(10, 0.8 * len(shots))) and (not calm or 3 <= len(shots) <= 8): return shots
        print(f"[shorts] кадры: якорей найдено {found} из {len(shots)} — повтор", flush=True)
        note = "\n\nПредыдущая попытка: якоря не совпали с текстом дословно. Копируй первые 2–3 слова фразы из текста символ в символ." + ("\nОшибка схемы: " + panel_error if panel_error else "")
    if config.SHORT_STYLE == "calm-story-v1":
        raise ValueError("Спокойный Shorts требует 3–8 смысловых сцен с дословными якорями; монтаж не прошёл проверку")
    return best


def _spoken_units(w: str) -> float:
    """Сколько «слов» звучит в токене: «$1,999» читается как 5–6 слов — иначе темп по числу токенов врёт."""
    digits = re.sub(r"\D", "", w)
    return max(1.0, len(digits) * 1.2) if digits else 1.0


def _pace(base, plan: dict | None = None) -> tuple[str, list[dict]]:
    """Паузы шортса по смыслу, с плавными стыками (владелец 17.09: «не успела закончиться мысль» → «более плавные переходы между предложениями/идеями»).
    Для каждой границы слов нужна пауза P: внутри фразы WORD_PAUSE, после запятой CLAUSE_PAUSE, после предложения SENT_PAUSE, перед сменой мысли
    (мост в прошлое, призыв) IDEA_PAUSE. Длинная пауза укорачивается (сохраняются затухание фразы и вдох перед следующей, стык — кроссфейд XFADE),
    короткая после предложения удлиняется тишиной с мягкими краями. Голос с stability 0.5 почти не держит пауз после точек — без удлинения фразы сливались."""
    import numpy as np
    from . import sound as S
    words = json.loads(config.read(base / "words.json"))
    src = base / "voice.mp3"
    sp = 1.0 if config.SHORT_STYLE == "calm-story-v1" else float(config.SHORT_SPEED or 1.0)
    if abs(sp - 1.0) > 0.01:
        # быстрее только РЕЧЬ: atempo не трогает высоту голоса, а паузы ниже выставляются заново в полную длину.
        # Ускорение готового файла целиком сжало бы и паузы — вернулась бы претензия «мысль не успевает закончиться».
        fast = base / "voice_fast.mp3"
        subprocess.run([S._ff(), "-y", "-v", "error", "-i", str(src), "-filter:a", f"atempo={sp:.3f}",
                        "-c:a", "libmp3lame", "-b:a", "192k", str(fast)], check=True)
        src = fast
        words = [{**w, "s": round(w["s"] / sp, 3), "e": round(w["e"] / sp, 3)} for w in words]
    toks = [A._norm(w["w"]) for w in words]
    ideas = set()
    if plan:
        for key in ("bridge", "cta"):
            k = _anchor_idx(toks, plan.get(key) or "", 0)
            if k: ideas.add(k)
        k = _bridge_idx(toks, words, plan, None)
        if k: ideas.add(k)
    def pause_for(k):
        if k + 1 in ideas: return IDEA_PAUSE, True
        if re.search(r"[.!?…]$", words[k]["w"]): return SENT_PAUSE, True
        if re.search(r"[,;:—–-]$", words[k]["w"]): return CLAUSE_PAUSE, False
        return WORD_PAUSE, False
    segs, a = [], max(0.0, words[0]["s"] - 0.12)          # (начало, конец в исходнике, что после: >0 тишина, <0 кроссфейд, 0 стык)
    for k, w in enumerate(words):
        if k + 1 == len(words):
            segs.append((a, w["e"] + 0.6, 0.0)); break
        nxt = words[k + 1]["s"]; g = max(0.0, nxt - w["e"]); P, grow = pause_for(k)
        if g > P + 2 * XFADE:
            segs.append((a, w["e"] + P * 0.6, -XFADE)); a = nxt - P * 0.4 - XFADE
        elif grow and g < P - 0.08:
            mid = w["e"] + g * 0.5
            segs.append((a, mid, P - g)); a = mid
    sr = 44100
    x = S._decode(src, sr).mean(axis=1).astype(np.float32)
    xf, edge = int(XFADE * sr), int(0.015 * sr)
    out = np.zeros(0, dtype=np.float32); shift, overlap = [], False
    for sa, sb, after in segs:
        piece = x[int(sa * sr):int(sb * sr)].copy()
        if overlap and len(out) >= xf and len(piece) > xf:
            fade = S._cos_fade(xf)
            out[-xf:] = out[-xf:] * fade[::-1] + piece[:xf] * fade
            shift.append((sa, (len(out) - xf) / sr - sa)); out = np.concatenate([out, piece[xf:]])
        else:
            if len(out) and len(piece) > edge: piece[:edge] *= S._cos_fade(edge)
            shift.append((sa, len(out) / sr - sa)); out = np.concatenate([out, piece])
        overlap = after < 0
        if after > 0:
            if len(out) > edge: out[-edge:] *= S._cos_fade(edge)[::-1]
            out = np.concatenate([out, np.zeros(int(after * sr), dtype=np.float32)])
    for w in words:
        _, d0 = max((sh for sh in shift if sh[0] <= w["s"] + 1e-3), key=lambda sh: sh[0])
        w["s"] = round(w["s"] + d0, 3); w["e"] = round(w["e"] + d0, 3)
    final = base / "voice_short.mp3"
    subprocess.run([S._ff(), "-y", "-v", "error", "-f", "f32le", "-ar", str(sr), "-ac", "1", "-i", "-", "-c:a", "libmp3lame", "-b:a", "192k", str(final)], input=out.tobytes(), check=True)
    raw_end = json.loads(config.read(base / "words.json"))[-1]["e"]
    print(f"[shorts] темп x{sp:g}, паузы: {raw_end:.1f} → {words[-1]['e']:.1f} с; смены мысли на словах {sorted(ideas)}; стыков {len(segs) - 1}", flush=True)
    config.write(base / "words_short.json", json.dumps(words))
    return f"shorts/{base.name}/{final.name}", words


_pick_cache: dict = {}


def _web_now(query: str, phrase: str, base, name: str, used: set, vid: str, news_item: dict) -> dict | None:
    """Реальное фото новости под кадр. Один поиск + один выбор на запрос: vision-модель возвращает до 3 годных снимков,
    лишние остаются в кэше запроса для следующих кадров (разные картинки без новых вызовов)."""
    key = (str(base), query.lower())
    if key not in _pick_cache:
        _pick_cache[key] = _pick_now(query, phrase, base, name, used, vid, news_item)
    while _pick_cache[key]:
        m = _pick_cache[key].pop(0)
        if m["image"] not in used: used.add(m["image"]); return m
    return None


def _pick_now(query: str, phrase: str, base, name: str, used: set, vid: str, news_item: dict) -> list[dict]:
    from ddgs import DDGS
    found = None
    for kw in ({"timelimit": "m"}, {}):   # «за месяц» есть не у всех бэкендов ddgs (bing падает на 'm') — тогда без фильтра
        try: found = DDGS().images(query, max_results=40, **kw); break
        except Exception as e: err = e
    if found is None: print(f"[shorts] поиск «{query}»: {str(err)[:100]}"); return []
    cands = []
    for r in found or []:
        img = r.get("image") or ""; page = r.get("url") or ""
        try: w, h = int(r.get("width") or 0), int(r.get("height") or 0)
        except (TypeError, ValueError): w, h = 0, 0
        if not img or STOCK_SKIP.search(img + " " + page + " " + (r.get("title") or "")) or archive.WEB_SKIP.search(img + " " + page): continue
        if max(w, h) < 900 or min(w, h) < 600: continue
        dom = re.sub(r"^https?://(www\.)?", "", page).split("/")[0]
        cands.append({"url": img, "page": page, "dom": dom, "label": f"{(r.get('title') or '')[:60]} | {dom} | {w}x{h}"})
        if len(cands) >= 12: break
    items = []
    for c in cands:
        try: items.append({**c, "im": archive._fetch_image(c["url"])})
        except Exception: pass
    if not items: return []
    facts = "; ".join([news_item.get("headline") or ""] + [f.get("fact") or "" for f in news_item.get("facts") or []])
    try:   # дешёвая модель пропускала концепт-рендеры, водяные знаки и инфографику (17.09) — отбор на основной vision-модели
        res = llm.ask_vision(PICK_NOW.replace("{news}", facts).replace("{phrase}", phrase).replace("{query}", query), [archive._grid(items)], tag=f"short_pick_{vid}")
    except Exception as e:
        print(f"[shorts] выбор кадра «{query}»: {e}"); return []
    picks = [int(n) for n in (res.get("picks") or [res.get("n")]) if str(n).isdigit() and 1 <= int(n) <= len(items)]
    out = []
    for k, n in enumerate(picks[:3]):
        c = items[n - 1]
        im = c["im"].convert("RGB"); im.thumbnail((2000, 2000)); p = base / f"{name}_{k}.jpg"; im.save(p, "JPEG", quality=90)
        out.append({"image": f"shorts/{base.name}/{p.name}", "aspect": round(im.width / im.height, 3), "focus_xy": A._saliency_focus(p), "credit": c["dom"], "kind": "now"})
    print(f"[shorts] «{query}»: кандидатов {len(items)}, годных {len(out)} — {res.get('why', '')[:80]}", flush=True)
    return out


BROWSER_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"}
ARTICLE_SKIP = re.compile(r"wikipedia|youtube|bloomberg|nytimes|wsj\.com|ft\.com|x\.com|twitter|facebook|instagram|reddit|tiktok", re.I)
IMG_SKIP = re.compile(r"avatar|logo|icon|sprite|sidebar|square|ytimg|gravatar|emoji|badge|author|profile|\.svg|/ads?/|pixel|placeholder|1x1", re.I)

POOL_PICK = """Снимки для вертикального YouTube Shorts о новости компании.
Новость ОФИЦИАЛЬНО объявлена {date} (это реальность, даже если ты о ней не знаешь — не отклоняй снимок из-за этого): {news}
Для каждой плитки реши, годится ли она как полноэкранный кадр:
- годится: официальное пресс-фото, фото с презентации, хендс-он фото журналиста именно этого продукта/события;
- НЕ годится: текст поверх снимка (заголовки, плашки, превью статей и видео), логотипы и водяные знаки сайтов, коллажи и сравнения «до/после»,
  скриншоты, инфографика, ИИ-арт, старые модели и чужие продукты, мелкие/мутные/тёмные снимки, аватары и иконки.
Верни JSON: {"tiles": [{"n": <номер>, "ok": true|false, "desc": "что на снимке, ≤ 6 слов по-английски", "quality": 1-5}]}"""


def _article_urls(item: dict) -> list[str]:
    """Страницы с настоящими фото новости: пресс-релиз компании и хендс-оны крупных СМИ (поиск ddgs), плюс ссылки фактов."""
    from ddgs import DDGS
    urls = []
    for q in (f"{item.get('headline')} newsroom", f"{item.get('headline')} hands-on photos"):
        try: urls += [r.get("href") or "" for r in DDGS().text(q, max_results=8)]
        except Exception as e: print(f"[shorts] поиск статей «{q[:50]}»: {str(e)[:80]}")
    urls += [f.get("source_url") or "" for f in item.get("facts") or []]
    urls = [u for u in dict.fromkeys(urls) if u.startswith("http") and not ARTICLE_SKIP.search(u)]
    urls.sort(key=lambda u: 0 if "/newsroom/" in u else 1)   # пресс-релиз компании — чистые официальные снимки
    return urls[:8]


def _article_images(url: str) -> list[str]:
    try:
        h = requests.get(url, headers=BROWSER_UA, timeout=25).text
    except Exception:
        return []
    found = re.findall(r'<meta[^>]+(?:property|name)="(?:og:image|twitter:image)"[^>]+content="([^"]+)"', h)
    for m in re.finditer(r'<(?:img|source)[^>]+>', h):
        tag = m.group(0)
        srcset = re.search(r'(?:data-)?srcset="([^"]+)"', tag)
        if srcset:   # самый крупный вариант из srcset
            opts = [x.strip().split(" ") for x in srcset.group(1).split(",") if x.strip()]
            best = max(opts, key=lambda o: int(re.sub(r"\D", "", o[1]) or 0) if len(o) > 1 else 0)
            found.append(best[0])
        src = re.search(r'(?:data-src|src)="([^"]+)"', tag)
        if src: found.append(src.group(1))
    out = []
    for u in found:
        u = u.replace("&amp;", "&")
        if u.startswith("//"): u = "https:" + u
        elif u.startswith("/"): u = re.match(r"https?://[^/]+", url).group(0) + u
        if u.startswith("http") and re.search(r"\.(jpe?g|png|webp)", u, re.I) and not IMG_SKIP.search(u): out.append(u)
    return list(dict.fromkeys(out))[:25]


def _ahash(im) -> int:
    g = im.convert("L").resize((8, 8)); px = list(g.getdata()); avg = sum(px) / 64
    return sum(1 << k for k, p in enumerate(px) if p > avg)


def _now_pool(vid: str, base, item: dict) -> list[dict]:
    """Пул реальных снимков новости: фото со страниц статей (пресс-релиз, хендс-оны) + поиск картинок по visual_queries;
    дубли по перцептивному хешу убираются; годность и описание каждого снимка — одна-две проверки vision-моделью."""
    cache = base / "now_pool.json"
    if cache.exists(): return json.loads(config.read(cache))
    cands, seen_urls = [], set()
    for u in _article_urls(item):
        dom = re.sub(r"^https?://(www\.)?", "", u).split("/")[0]
        for img in _article_images(u):
            if img not in seen_urls: seen_urls.add(img); cands.append({"url": img, "dom": dom})
    if len(cands) < 12:
        from ddgs import DDGS
        for q in (item.get("visual_queries") or [])[:3]:
            try:
                for r in DDGS().images(q, max_results=20):
                    img, page = r.get("image") or "", r.get("url") or ""
                    if img and img not in seen_urls and not STOCK_SKIP.search(img + " " + page + " " + (r.get("title") or "")):
                        seen_urls.add(img); cands.append({"url": img, "dom": re.sub(r"^https?://(www\.)?", "", page).split("/")[0]})
            except Exception as e: print(f"[shorts] поиск «{q}»: {str(e)[:80]}")
    items, hashes = [], []
    for c in cands:
        if len(items) >= 24: break
        try: im = archive._fetch_image(c["url"])
        except Exception: continue
        if im.width < 900 or im.height < 500: continue
        hsh = _ahash(im)
        if any(bin(hsh ^ x).count("1") <= 6 for x in hashes): continue
        hashes.append(hsh); items.append({**c, "im": im, "label": f"{c['dom']} | {im.width}x{im.height}"})
    print(f"[shorts] пул снимков новости: кандидатов {len(cands)}, уникальных крупных {len(items)}", flush=True)
    facts = "; ".join([item.get("headline") or ""] + [f.get("fact") or "" for f in item.get("facts") or []])
    pool = []
    for g0 in range(0, len(items), 12):
        group = items[g0:g0 + 12]
        try:
            res = llm.ask_vision(POOL_PICK.replace("{date}", item.get("date") or "").replace("{news}", facts), [archive._grid(group)], tag=f"short_pool_{vid}")
        except Exception as e:
            print(f"[shorts] проверка снимков: {e}"); continue
        for t in res.get("tiles") or []:
            n = int(t.get("n") or 0)
            if not (1 <= n <= len(group) and t.get("ok")): continue
            c = group[n - 1]; k = len(pool)
            im = c["im"].convert("RGB"); im.thumbnail((2200, 2200)); p = base / f"now_{k:02d}.jpg"; im.save(p, "JPEG", quality=90)
            pool.append({"image": f"shorts/{base.name}/{p.name}", "aspect": round(im.width / im.height, 3), "focus_xy": A._saliency_focus(p),
                         "credit": c["dom"], "kind": "now", "desc": t.get("desc") or "", "quality": int(t.get("quality") or 3)})
    pool.sort(key=lambda m: -m["quality"])
    print(f"[shorts] годных снимков новости: {len(pool)} — " + "; ".join(m["desc"] for m in pool[:8]), flush=True)
    config.write(cache, json.dumps(pool, ensure_ascii=False, indent=1))
    return pool


def _assign(pool: list[dict], query: str, shown: dict, prev) -> dict | None:
    """Снимок под кадр: совпадение слов запроса с описанием + качество − повторы; тот же снимок подряд — нельзя."""
    if not pool: return None
    q = set(_norm_tokens(query))
    def score(m):
        overlap = len(q & set(_norm_tokens(m.get("desc") or "")))
        return overlap * 2 + m.get("quality", 3) * 0.5 - shown.get((m.get("image"), None), 0) * 3 - (100 if (m.get("image"), None) == prev else 0)
    best = max(pool, key=score)
    return None if (best.get("image"), None) == prev and len(pool) > 1 else dict(best)


def _bridge_idx(toks: list[str], words: list[dict], plan: dict, cta_i: int | None) -> int | None:
    """Начало фразы-моста в прошлое (индекс слова озвучки): по полю bridge от сценариста, иначе предложение с годом до 2000 / «ago» / «founded» / «garage»."""
    if plan.get("bridge"):
        k = _anchor_idx(toks, plan["bridge"], 0)
        if k is not None: return k
    for k, t in enumerate(toks):
        if cta_i is not None and k >= cta_i: break
        if re.fullmatch(r"19\d\d|ago|founded|garage|decades", t):
            j = k
            while j > 0 and not re.search(r"[.!?]$", words[j - 1]["w"]): j -= 1
            return j
    return None


FLASH_LABEL_MAX = 20   # знаков в подписи: строка моноширинного шрифта 38 px под цифрой на плашке шириной экрана
_LABEL_STOP = {"of", "for", "to", "in", "on", "a", "an", "the", "per", "and", "at", "by", "from", "with", "its", "their", "his", "her", "our", "all"}


def _flash_labels(vid: str, n: int, plan: dict, words: list[dict], flashes: list[dict]) -> list[dict]:
    """27.09 (владелец): цифра на плашке без смысла («81%», «$7.8M MOSTLY») — шум. Подпись обязательна: что это за цифра,
    2–4 слова из фразы диктора. Слова подписи (кроме служебных) должны быть в тексте шортса. Нет подписи — нет плашки."""
    if not flashes: return flashes
    text = " ".join(w["w"] for w in words)
    def around(t):
        seg = [w["w"] for w in words if t - 4.0 <= w["s"] <= t + 3.0]
        return " ".join(seg)
    items = [{"i": k, "value": f["value"], "said": around(f["start"])} for k, f in enumerate(flashes)]
    prompt = ("Short vertical video. For each number shown big on screen, write a caption that says WHAT the number is, "
              "2 to 4 English words, max 20 characters, e.g. \"OF CLAIMS\", \"FOR 12 ACRES\", \"A YEAR IN FEES\", \"PHONE OPERATORS\". "
              "Use only words and facts present in the narration around it. If the narration does not make the meaning clear, return an empty label.\n\n"
              f"Full narration:\n{plan.get('script') or text}\n\nNumbers:\n{json.dumps(items, ensure_ascii=False)}\n\n"
              'Return JSON: {"labels": [{"i": 0, "label": "OF CLAIMS"}]}')
    try:
        res = llm.ask_json(prompt, tag=f"flash_labels_{vid}_s{n}", model=config.LLM_MODEL_POLISH or None, max_tokens=1500, effort="low")
    except Exception as e:
        print(f"[shorts] s{n}: подписи к цифрам не получены ({str(e)[:80]}) — плашек не будет", flush=True); return []
    got = {int(x.get("i", -1)): str(x.get("label") or "").strip() for x in res.get("labels") or [] if isinstance(x, dict)}
    vocab = {A._norm(w) for w in re.findall(r"[A-Za-z][A-Za-z'\-]*|\d[\d.,]*", (plan.get("script") or "") + " " + text)}
    out = []
    for k, f in enumerate(flashes):
        lab = re.sub(r"\s+", " ", got.get(k, "")).strip(" .,:;-")
        toks = [A._norm(t) for t in re.findall(r"[A-Za-z][A-Za-z'\-]*|\d[\d.,]*", lab)]
        content = [t for t in toks if t not in _LABEL_STOP]
        grounded = content and all(t in vocab or t.rstrip("s") in vocab or t + "s" in vocab for t in content)
        if lab and len(lab) <= FLASH_LABEL_MAX and 1 <= len(toks) <= 4 and grounded:
            out.append({**f, "label": lab.upper()})
        else:
            print(f"[shorts] s{n}: цифра {f['value']} без внятной подписи («{lab}») — плашку не ставлю", flush=True)
    return out


def _captions(words: list[dict], hot: set, until: float) -> list[dict]:
    caps, cur = [], []
    def close():
        if cur: caps.append({"start": cur[0]["s"], "words": [dict(w) for w in cur]})
    for i, w in enumerate(words):
        if w["s"] >= until: break
        token = A._norm(w["w"])
        w2 = {"w": w["w"], "s": w["s"], "e": w["e"], "hot": bool(re.search(r"\d", w["w"])) or token in hot}
        gap = cur and w["s"] - cur[-1]["e"] > 0.28
        calm = config.SHORT_STYLE == "calm-story-v1"
        if cur and (len(cur) >= (7 if calm else 3) or gap or (not calm and w2["hot"] and not cur[-1]["hot"] and len(cur) >= 2)): close(); cur = []
        cur.append(w2)
        if re.search(r"[.!?,:;—–]$", w["w"]): close(); cur = []
    close()
    for k, c in enumerate(caps):
        nxt = caps[k + 1]["start"] if k + 1 < len(caps) else until
        c["end"] = round(min(nxt, c["words"][-1]["e"] + 0.6), 3)
    if caps: caps[0]["start"] = 0.0   # первый кадр шортса — уже с текстом хука
    return caps


def _calm_voice(text: str, base, vid: str):
    """One plain v4 take in the channel voice, with exact alignment and resumable output."""
    import hashlib, os
    voice_id = os.getenv("ELEVENLABS_VOICE_ID")
    if not voice_id:
        raise RuntimeError("ELEVENLABS_VOICE_ID пуст")
    signature = hashlib.sha256(("calm-v4|" + voice_id + "|" + text).encode()).hexdigest()
    mark = base / "voice.sha"
    if mark.exists() and mark.read_text().strip() == signature and (base / "voice.mp3").exists() and (base / "words.json").exists():
        return
    previous = A.TTS_CTX.get("vid", "")
    A.TTS_CTX["vid"] = vid
    try:
        audio, alignment = A._tts_fal_v4(text, voice_id)
    finally:
        A.TTS_CTX["vid"] = previous
    words = A._words(alignment, 0)
    if A._plain_words(" ".join(w["w"] for w in words)) != A._plain_words(text):
        raise ValueError("[shorts] тайминги не соответствуют полной озвучке")
    if not words or any(w["e"] <= w["s"] or (i and w["s"] < words[i-1]["s"]) for i,w in enumerate(words)):
        raise ValueError("[shorts] некорректные тайминги озвучки")
    raw = base / "voice_calm_take.mp3"
    raw.write_bytes(audio)
    A._loudnorm(raw)
    if words[-1]["e"] > A._duration(raw) + .08:
        raise ValueError("[shorts] тайминги выходят за длительность озвучки")
    raw.replace(base / "voice.mp3")
    config.write(base / "words.json", json.dumps(words))
    mark.write_text(signature)


def build(vid: str, which: list[int] | None = None, force: bool = False, start: int = 1) -> list[dict]:
    """Шортсы для story-видео: which — номера новостей из news.json (по умолчанию первые SHORTS_PER_VIDEO);
    start — номер первой папки sN (дополнительный шортс к уже выпущенным: start=4 не трогает s1–s3)."""
    v = db.get(vid); d = db.video_dir(vid); s = v["payload"]["script"]; research = v["payload"].get("research") or {}
    company = _company(v["payload"]["topic"])
    items = moments(vid) if config.SHORTS_SOURCE == "story" else news(vid)
    # 28.09 владелец: новостные шортсы убрать (5 800 просмотров дали 2 подписчиков, аудитория не та) — запасного хода на новости больше нет
    if not items: print("[shorts] материала для шортсов не нашлось — шортсов не будет"); return []
    which = which or list(range(min(config.SHORTS_PER_VIDEO, len(items))))
    lib = _library(s); story_pool = _broll(s); specs = []
    print(f"[shorts] запас кадров из ролика: архив {len(lib)}, подложки {len(story_pool)}", flush=True)
    tl = json.loads(config.read(d / "timeline.json")) if (d / "timeline.json").exists() else {}
    music = next((m for m in tl.get("music_tracks") or [] if (m.get("mood") or "") in ("dramatic", "tense", "driving", "epic")), (tl.get("music_tracks") or [None])[0])
    if not music:   # у ролика сведённая партитура: render.run очищает music_tracks, и шортсы Amazon вышли без подложки (тишина в концовке, 19.09).
        th = sorted((d / "sound").glob("theme_1_*.mp3")) or sorted((d / "sound").glob("theme_*.mp3"))   # тема cold open — тревожная, под хук
        if th: music = {"src": f"sound/{th[0].name}", "volume": 0.054, "offset": 0}   # ×2.2 ниже → 0.12, как у шортсов Apple
    for n, idx in enumerate(which, start):
        item = items[idx]; base = d / "shorts" / f"s{n}"; base.mkdir(parents=True, exist_ok=True)
        plan_p = base / "plan.json"
        if plan_p.exists() and not force:
            plan = json.loads(config.read(plan_p))
        else:
            print(f"[shorts] s{n}: {item.get('headline')}", flush=True)
            others = [it for j, it in enumerate(items) if j != idx]
            item = _enrich(vid, item)
            plan = _script(vid, item, others, research, v["title"], company)
            if config.FACTCHECK: plan = _factcheck(vid, plan, item, others, research)
            plan["shots"] = _shots(vid, plan, item, lib)
            plan["news"] = item
            config.write(plan_p, json.dumps(plan, ensure_ascii=False, indent=1))
        item = plan.get("news") or item   # с дозапрошенными фактами — для отбора фото
        calm = config.SHORT_STYLE == "calm-story-v1"
        if calm:
            _calm_voice(A.clean_text(plan["script"]), base, vid)
        else:
            A._voice(A.clean_text(plan["script"]), base, tags_prompt=config.SHORT_TAGS_PROMPT, stability=config.SHORT_TTS_STABILITY)
        voice, words = _pace(base, plan)
        toks = [A._norm(w["w"]) for w in words]
        cta_i = _anchor_idx(toks, plan.get("cta") or "", len(toks) // 2)
        end_start = round(max(0.0, words[cta_i]["s"] - 0.15), 3) if cta_i is not None else round(words[-1]["e"] - 2.5, 3)
        duration = round(words[-1]["e"] + END_HOLD, 3)
        # кадры по якорям
        used, shots, pos, pool, shown = set(), [], 0, [], {}
        calm = config.SHORT_STYLE == "calm-story-v1"
        now_pool = [] if calm and config.SHORTS_SOURCE == "story" else _now_pool(vid, base, item)
        bridge_i = _bridge_idx(toks, words, plan, cta_i)
        then_ids = [x.get("library") for x in plan.get("shots") or [] if x.get("library") in lib]
        used_lib = set()
        pool += now_pool
        for j, sh in enumerate(plan.get("shots") or []):
            i = _anchor_idx(toks, sh.get("anchor") or "", pos)
            if i is None or (shots and words[i]["s"] <= shots[-1]["start"]): continue
            pos = i
            start = 0.0 if not shots else words[i]["s"]
            if start >= end_start - 0.3: break
            phrase = " ".join(w["w"] for w in words[i:i + 8])
            media = None
            panel = _calm_panel(sh, plan["script"]) if calm else None
            # род кадра — по месту в тексте, а не по разметке модели (Qwen пометил «versus 44 outside» прошлым): до моста — новость, после — архив
            kind = "then" if bridge_i is not None and i >= bridge_i else "now"
            if calm and not panel and kind == "then" and sh.get("library") not in lib:
                raise RuntimeError(f"[shorts] s{n}: нет точного архивного материала для «{phrase}»")
            if kind == "then" and sh.get("library") not in lib:
                spare = [k2 for k2 in then_ids if k2 not in used_lib] or then_ids or list(lib)
                sh = {**sh, "library": spare[0] if spare else None}
            sh = {**sh, "kind": kind}
            if panel:
                media = {"kind":"illustration", "credit":"Narrated mechanism diagram"}
            elif kind == "then" and sh.get("library") in lib:
                used_lib.add(sh["library"])
                sl = lib[sh["library"]]
                media = {**sl, "image": sl.get("image"), "src": sl.get("src"), "aspect": sl.get("aspect"), "focus_xy": sl.get("focus_xy"),
                         "year": sl.get("year"), "clip_seconds": sl.get("clip_seconds"), "kind": "then", "caption": sl.get("caption")}
            elif sh.get("kind") != "then":   # новость: снимок из пула статей по смыслу кадра; поиск по запросу — только если пул мал
                prev = (shots[-1].get("image"), shots[-1].get("src")) if shots else None
                # сперва свой проверенный материал, если он прямо по теме кадра: у ролика есть и работа 1998 года, и выдача,
                # и дата-центр — это лучше случайной картинки из веба, которую зрение пропустило как «похожую» (Google 20.09)
                own = _pick(list(lib.values()) + story_pool, shown, prev, sh.get("query") or phrase, min_hit=2)
                media = own or _assign(now_pool, sh.get("query") or phrase, shown, prev)
                if (not media or len(now_pool) < 4) and not own and sh.get("query"):
                    got = _web_now(sh["query"], phrase, base, f"q_{j:02d}", used, vid, item)
                    if got: media = got; now_pool.append({**got, "desc": sh["query"], "quality": 3})
            if calm and not media:
                raise RuntimeError(f"[shorts] s{n}: не найден соответствующий озвучке источник для «{phrase}»")
            if not media:   # кадр не нашёлся — другой снимок того же рода, а если и их нет, проверенный кадр из самого ролика
                prev = (shots[-1].get("image"), shots[-1].get("src")) if shots else None
                same = [m for m in pool if m["kind"] == ("then" if sh.get("kind") == "then" else "now")]
                media = _pick(same, shown, prev, sh.get("query") or phrase) or _pick(story_pool, shown, prev, sh.get("query") or phrase)
                if media: media["move"] = "detail"
            if not media: continue
            if media["kind"] == "then" and media not in pool: pool.append(media)
            key = (media.get("image"), media.get("src")); shown[key] = shown.get(key, 0) + 1
            shots.append({**media, "start": round(start, 3), "emphasis": sh.get("emphasis"), **({"panel":panel} if panel else {})})
        if not shots: raise RuntimeError(f"[shorts] s{n}: ни одного кадра")
        for a, b in zip(shots, shots[1:]): a["end"] = b["start"]
        shots[-1]["end"] = duration
        shots = [x for x in shots if x["end"] - x["start"] >= SHOT_MIN * 0.6 or x is shots[-1]]
        shots[0]["start"] = 0.0
        for a, b in zip(shots, shots[1:]): a["end"] = b["start"]   # выброшенный короткий кадр не оставляет дыру
        # длинный кадр режем на два с разным движением — смена картинки каждые ≤ SHOT_MAX с
        cut = []
        moves = ["in", "left", "out", "right"]
        for x in shots:
            last = x["end"] >= duration - 0.01; span_end = min(x["end"], end_start) if last else x["end"]
            t0, piece = x["start"], x
            while not calm and span_end - t0 > SHOT_MAX + 0.6:
                cut.append({**piece, "start": round(t0, 3), "end": round(t0 + SHOT_MAX * 0.8, 3)}); t0 += SHOT_MAX * 0.8
                # вторая половина длинного кадра — другое фото: сперва того же рода, затем любой проверенный кадр ролика,
                # лишь бы картинка сменилась (статичный кадр на 19 секунд — то, за что шортс и забраковали)
                prevk = (piece.get("image"), piece.get("src"))
                m = _pick([q for q in pool if q["kind"] == x["kind"]], shown, prevk) or _pick(story_pool, shown, prevk)
                if m:
                    shown[(m.get("image"), m.get("src"))] = shown.get((m.get("image"), m.get("src")), 0) + 1
                    piece = {**x, **m}
            cut.append({**piece, "start": round(t0, 3), "end": x["end"]})
        for j, x in enumerate(cut):
            if x.get("move") != "detail": x["move"] = moves[j % len(moves)]
            if j and cut[j - 1].get("image") == x.get("image") and cut[j - 1].get("src") == x.get("src"): x["move"] = "detail" if cut[j - 1].get("move") != "detail" else "out"
        hot = {A._norm(t) for sh in plan.get("shots") or [] for t in str(sh.get("emphasis") or "").split()}
        # цифры крупно: каждое значение один раз, не больше MAX_FLASHES, подпись — только короткая единица («inches», «computers»), не обрывок фразы
        flashes, seen_vals = [], set()
        for f in ([] if calm else N.flashes(words, seconds=1.8, dedupe_sec=999.0)):
            core = re.sub(r"[^\d.]", "", f["value"]).rstrip(".")
            if f["start"] >= end_start - 0.5 or f.get("label") == "years old" or core in seen_vals or len(flashes) >= MAX_FLASHES: continue
            seen_vals.add(core); lab = f.get("label") or ""
            if len(lab.split()) > 2 or re.search(r"\b(how|a|an|the|each|for|from|to|and|of|with|that|this|is|it)\b", lab, re.I): lab = ""
            flashes.append({"start": f["start"], "end": min(f["start"] + f["seconds"], end_start), "value": f["value"], "label": lab})
        flashes = _flash_labels(vid, n, plan, words, flashes)
        spec = {"duration": duration, "voice": voice, "shots": cut, "captions": _captions(words, hot, end_start), "flashes": flashes,
                "music": ({"src": music["src"], "volume": round(min(0.35, (music.get("volume") or 0.05) * (1.0 if calm else 2.2)), 3), "offset": music.get("offset") or 0} if music else None),
                "end": {"start": end_start, "thumb": "thumb_a.png" if (d / "thumb_a.png").exists() else None, "line1": "THE FULL STORY", "line2": "LINK IN COMMENTS"},
                "channel": config.CHANNEL_NAME, "title": plan.get("title"), "description": plan.get("description")}
        if calm:
            spec["style"] = "calm-story-v1"
            spec["story_panels"] = _calm_panels(cut, end_start)
            spec["end"]["line1"] = v["title"]
            spec["end"]["line2"] = "Watch the full story on our channel."
            spec["end"]["thumb"] = None
        config.write(base / "short.json", json.dumps(spec, ensure_ascii=False, indent=1))
        credits = sorted({x.get("credit") for x in cut if x.get("credit")})
        meta = {"title": plan.get("title"), "description": (plan.get("description") or "") + (f"\n\nPhotos: {', '.join(credits)}" if credits else ""),
                "related_video": v["title"], "news": item.get("headline"), "sources": list(dict.fromkeys(f.get("source_url") for f in item.get("facts") or [] if f.get("source_url")))}
        config.write(base / "meta.json", json.dumps(meta, ensure_ascii=False, indent=1))
        print(f"[shorts] s{n}: {duration:.1f} с, кадров {len(cut)}, субтитров {len(spec['captions'])}, цифр {len(flashes)}, превью с {end_start:.1f} с", flush=True)
        specs.append(spec)
    return specs
