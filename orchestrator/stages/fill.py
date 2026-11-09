"""Добивка кадров: ни одна сцена не висит дольше потолка (владелец 17.09: «один кадр с пальцем и телефоном идёт 35 секунд — почему так»).

Замер Apple: 19 сцен из 116 длиннее 20 с — 9.5 минуты ролика; причины: модель расставляет кадры неравномерно, типы фазы B (chart/quote/object)
деградируют в broll и часть из них выпадает при прореживании, а потолка длины сцены в _timeline не было — предыдущий кадр просто тянулся.
Схема: по готовому таймлайну находим сцены длиннее потолка (картинка/фото STILL_MAX, архивное видео CLIP_MAX, people/map/split RICH_MAX),
режем их текст по началам предложений (при длинном предложении — по запятым/тире) на куски TARGET ± , первый кусок остаётся исходной сцене,
на остальные модель придумывает кадры (prompts/story_fill.md), слоты разрешаются тем же путём, что и обычные (архив → веб → генерация),
новые shots с якорями на первых словах куска дописываются в payload.script.shots — дальше их ставит обычный _timeline."""
import json, re
from concurrent.futures import ThreadPoolExecutor
from .. import config, llm
from . import assets as A, story, story_assets as SA, footage

STILL_MAX, CLIP_MAX, RICH_MAX = 12.0, 20.0, 26.0
TARGET, PIECE_MIN, PIECE_MAX = 8.5, 5.5, 11.5
RICH_KEEP = 18.0            # богатая сцена (люди, карта) держит свою хореографию, остаток уходит новым кадрам


FOREIGN_KEEP, FOREIGN_PIECE_MIN = 7.0, 5.0   # 29.09 STRATEGY.md: чужой видеоотрезок (ролик YouTube) на экране не дольше footage.FOREIGN_MAX секунд подряд


def _limit(x: dict) -> float:
    if footage.foreign(x): return footage.FOREIGN_MAX
    if x.get("type") != "broll": return RICH_MAX
    sl = (x.get("slots") or [{}])[0]
    return CLIP_MAX if sl.get("src") else STILL_MAX


def _cuts(words: list[dict], i0: int, i1: int, first_keep: float, PIECE_MIN: float = PIECE_MIN, PIECE_MAX: float = PIECE_MAX) -> list[int]:
    """Индексы слов, с которых начинаются новые кадры внутри сцены words[i0:i1]."""
    t_end = words[i1 - 1]["e"]
    sent = [k for k in range(i0 + 1, i1) if re.search(r"[.!?…][\"”’)]*$", words[k - 1]["w"])]
    clause = [k for k in range(i0 + 1, i1) if re.search(r"[,;:—–][\"”’)]*$", words[k - 1]["w"]) or words[k]["s"] - words[k - 1]["e"] > 0.35]
    out, p, want = [], words[i0]["s"], first_keep
    # хвост короче SCENE_MIN_SEC сборка таймлайна выбрасывает — для чужого видео это значит, что отрезок снова идёт целиком (Greyhound 29.09)
    tail_min = config.SCENE_MIN_SEC + 0.2 if PIECE_MAX <= 10.0 else PIECE_MIN * 0.8
    while t_end - p > max(want, PIECE_MAX):
        def pick(cands):
            ok = [k for k in cands if PIECE_MIN <= words[k]["s"] - p <= max(PIECE_MAX, want + 3) and t_end - words[k]["s"] >= tail_min]
            return min(ok, key=lambda k: abs(words[k]["s"] - p - want)) if ok else None
        k = pick(sent)
        if k is None: k = pick(clause)
        if k is None and PIECE_MAX <= 10.0: k = pick(range(i0 + 1, i1))   # чужой видеоотрезок: нет границы фразы — режем по слову, потолок важнее
        if k is None:
            later = [k for k in sent + clause if words[k]["s"] - p >= PIECE_MIN and t_end - words[k]["s"] >= tail_min]
            if not later: break
            k = min(later)
        out.append(k); p = words[k]["s"]; want = TARGET
    return out


def plan(tl: dict, words: list[dict], parts: set | None = None, ids: set | None = None) -> list[dict]:
    """Длинные сцены → куски. Возвращает [{scene, pieces: [{i0, i1, text, anchor}]}]."""
    res = []
    for x in tl["scenes"]:
        if parts and x.get("part") not in parts: continue
        if ids is not None and x["id"] not in ids: continue
        if str(x["id"]).startswith("live_"): continue
        dur = x["end"] - x["start"]; lim = _limit(x)
        if footage.foreign(x) and x.get("transition") == "dip": dur -= config.CHAPTER_GAP   # видимая часть первого кадра главы
        if dur <= lim: continue
        idx = [k for k, w in enumerate(words) if x["start"] - 0.05 <= w["s"] < x["end"] - 0.05]
        if len(idx) < 12: continue
        i0, i1 = idx[0], idx[-1] + 1
        fr = footage.foreign(x)
        keep = FOREIGN_KEEP if fr else TARGET if x.get("type") == "broll" else RICH_KEEP
        if fr:   # потолок считается от начала сцены, а не от первого слова; под карточкой главы отрезок не виден
            hidden = config.CHAPTER_GAP if x.get("transition") == "dip" else 0.0
            keep = max(FOREIGN_PIECE_MIN, FOREIGN_KEEP - max(0.0, words[i0]["s"] - x["start"] - hidden))
        elif x.get("transition") == "dip": keep += config.CHAPTER_GAP   # первый кадр главы стоит под карточкой
        cuts = _cuts(words, i0, i1, keep, FOREIGN_PIECE_MIN, footage.FOREIGN_MAX) if fr else _cuts(words, i0, i1, keep)
        if not cuts: continue
        pieces = []
        for a, b in zip(cuts, cuts[1:] + [i1]):
            pieces.append({"i0": a, "i1": b, "text": " ".join(w["w"] for w in words[a:b]), "anchor": " ".join(w["w"] for w in words[a:a + 5]),
                           "sec": round(words[b - 1]["e"] - words[a]["s"], 1)})
        res.append({"scene": x, "pieces": pieces})
    return res


def _describe(x: dict | None) -> str:
    if not x: return "—"
    sl = (x.get("slots") or [{}])[0]
    return f"{x.get('type')}: " + (sl.get("caption") or sl.get("query") or (sl.get("prompt") or "")[:100] or "?")


def run(vid: str, d, s: dict, tl: dict, words: list[dict], parts: set | None = None, img_model: str | None = None, cast: list[str] | None = None,
        ids: set | None = None) -> dict:
    """Добавляет shots в s["shots"] (на месте). d — папка ролика (медиа кладутся туда же). Возвращает сводку. ids — только эти сцены."""
    jobs = plan(tl, words, parts, ids)
    if not jobs: print("[fill] длинных сцен нет"); return {"scenes": 0, "shots": 0, "fal": 0.0}
    scenes = tl["scenes"]; by_id = {x["id"]: k for k, x in enumerate(scenes)}
    clean = A.clean_text(s["script"]); cast = cast or []
    existing = {x["id"] for x in s["shots"]}
    new_shots = []
    def ask(job):
        x = job["scene"]; k = by_id[x["id"]]
        i0, i1 = job["pieces"][0]["i0"], job["pieces"][-1]["i1"]
        ctx = " ".join(w["w"] for w in words[max(0, i0 - 40):min(len(words), i1 + 25)])
        frags = "\n".join(f"{n}. ({p['sec']} с) {p['text']}" for n, p in enumerate(job["pieces"], 1))
        near = " | ".join(_describe(scenes[j]) for j in (k - 1, k + 1) if 0 <= j < len(scenes))
        try:
            res = llm.ask_json(config.prompt("story_fill", context=ctx, current=_describe(x), neighbours=near, fragments=frags), heavy=True, max_tokens=3000, tag=f"fill_{vid}", model=config.LLM_MODEL_SHOTS or None)
        except Exception as e:
            print(f"[fill] {x['id']}: {e}"); return []
        got = {int(r.get("n") or 0): r for r in res.get("shots") or [] if isinstance(r, dict)}
        out = []
        for n, p in enumerate(job["pieces"], 1):
            r = got.get(n)
            if not r: continue
            sid = f"{x['id']}_f{n}"
            if sid in existing: continue
            shot = {"id": sid, "anchor": p["anchor"], "type": "broll", "part": x.get("part"), "motion": r.get("motion") or "slow push in", "data": {}, "fill": True,
                    "slots": [{k2: r.get(k2) for k2 in ("source", "query", "query_alt", "media", "caption", "prompt", "focus")}]}
            out.append(story._normalize_shot(shot))
        return out
    with ThreadPoolExecutor(4) as ex:
        for shots in ex.map(ask, jobs): new_shots += shots
    print(f"[fill] длинных сцен {len(jobs)}, новых кадров {len(new_shots)} — разрешаю слоты", flush=True)
    fal_cost = {"usd": 0.0}; model = img_model or config.IMAGE_MODEL_CHEAP
    from . import archive
    archive.reset()   # уже стоящие в ролике снимки и ролики YouTube не повторяем
    for y in s["shots"]:
        for sl in y.get("slots") or []:
            key = (sl.get("archive") or {}).get("key") or ""
            if key.startswith("yt:"): archive._used_yt.setdefault(key[3:].split("@")[0], []).append(float(key.split("@")[1]) if "@" in key else 0.0)
            elif key: archive._used_photos.add(key)
    if config.ERA_FOOTAGE:
        from . import era_footage
        era_footage.reset(); era_footage.seed(s["shots"]); SA._era_budget["left"] = config.ERA_MAX_PER_VIDEO
    with ThreadPoolExecutor(4) as ex:
        list(ex.map(lambda x: SA._resolve_slots(x, d, model, fal_cost, SA._ctx(x, clean), vid, cast), new_shots))
    ok = [x for x in new_shots if x.get("slots") and SA._has_media(x["slots"][0])]
    from . import preflight
    try: fal_cost["usd"] += preflight.check(d, ok, clean, vid, model, passes=2)
    except Exception as e: print(f"[fill] preflight: {e}")
    ok = [x for x in ok if x.get("slots") and SA._has_media(x["slots"][0])]
    # вставка в порядке текста: сразу после исходной сцены
    order = {x["id"]: k for k, x in enumerate(s["shots"])}
    for x in ok:
        host = x["id"].rsplit("_f", 1)[0]
        pos = max((k for i, k in order.items() if i == host or i.startswith(host + "_f")), default=len(s["shots"]) - 1)
        s["shots"].insert(pos + 1, x); order = {y["id"]: k for k, y in enumerate(s["shots"])}
    kinds = {}
    for x in ok: kinds[x["slots"][0].get("kind") or "?"] = kinds.get(x["slots"][0].get("kind") or "?", 0) + 1
    print(f"[fill] добавлено {len(ok)} кадров ({', '.join(f'{k} {v}' for k, v in kinds.items())}); без медиа отброшено {len(new_shots) - len(ok)}; fal ${fal_cost['usd']:.2f}", flush=True)
    return {"scenes": len(jobs), "shots": len(ok), "fal": fal_cost["usd"]}
