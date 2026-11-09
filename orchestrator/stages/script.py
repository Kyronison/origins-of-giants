"""Ресёрч → сценарий + storyboard → на утверждение."""
import csv, json, re
from .. import db, llm, telegram, config
from . import brief, claims

FACT_COLS = ["id", "fact", "value", "unit", "date", "source_url", "source_type"]
SCENE_TYPES = {"title", "stat", "bar_chart", "line_chart", "compare", "quote", "broll", "broll_ai", "broll_stock", "outro"}

def run(vid: str):
    v = db.get(vid); t = v["payload"]["topic"]; d = db.video_dir(vid)
    if (t.get("format") or "news") == "story": return run_story(vid)

    research = llm.ask_json(config.prompt("research", working_title=t["working_title"], thesis=t["thesis"]),
                            search=True, heavy=True, max_tokens=16000, tag=f"research_{vid}")
    facts = [f for f in research.get("facts", []) if f.get("id") and f.get("source_url")]
    if len(facts) < 5: raise ValueError(f"Ресёрч дал только {len(facts)} фактов с источниками — мало")
    research["facts"] = facts
    with open(d / "facts.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FACT_COLS, extrasaction="ignore")
        w.writeheader(); w.writerows(facts)

    extra = ""
    if v["payload"].get("fix_note"):
        extra = f"\n\nПРАВКИ ВЛАДЕЛЬЦА К ПРОШЛОЙ ВЕРСИИ (обязательно учесть): {v['payload']['fix_note']}"
    script = llm.ask_json(config.prompt("script", working_title=t["working_title"], thesis=t["thesis"],
                                        format=t.get("format") or "news", unit=t.get("unit") or "—", moods=" | ".join(config.music_moods()),
                                        facts_json=json.dumps(research, ensure_ascii=False)) + extra,
                          heavy=True, max_tokens=24000, tag=f"script_{vid}")

    _validate(script, {f["id"] for f in facts})
    script["storyboard"] = strip_fact_refs(script["storyboard"])   # «(F2, F3)» в подписях не должны попасть в кадр и в главы
    config.write(d / "script.md", f"# {script['title_options'][0]}\n\n{script['script']}")
    config.write(d / "storyboard.json", json.dumps(script["storyboard"], ensure_ascii=False, indent=2))
    cost = round(float(v["payload"].get("cost_usd", 0)) + llm.take_cost(), 4)
    db.update(vid, "scripted", title=script["title_options"][0],
              payload={"script": script, "research": research, "fix_note": None, "cost_usd": cost})
    telegram.ask_script_review(vid, d / "script.md")
    print(f"[script] расходы на видео: ${cost:.2f}")

def _validate(script: dict, ids: set):
    for k in ("title_options", "script", "description", "tags", "storyboard", "thumbnail_concepts"):
        if not script.get(k): raise ValueError(f"В ответе модели нет поля {k}")
    used = set(re.findall(r"\[(F\d+)\]", script["script"]))
    unknown = used - ids
    if unknown: raise ValueError(f"Сценарий ссылается на несуществующие факты: {unknown}")
    if not used: raise ValueError("В сценарии нет ни одной ссылки на факты — правило нарушено")
    for sc in script["storyboard"]:
        for k in ("id", "type", "anchor", "data"):
            if k not in sc: raise ValueError(f"Сцена без поля {k}: {sc}")
        if sc["type"] not in SCENE_TYPES: raise ValueError(f"Неизвестный тип сцены {sc['type']} в {sc['id']}")
    words = len(re.sub(r"\[F\d+\]|</?short>", "", script["script"]).split())
    if words < 900: raise ValueError(f"Сценарий слишком короткий: {words} слов")

FACT_REF = re.compile(r"\s*[(\[]\s*F\d+(?:\s*,\s*F\d+)*\s*[)\]]")

def strip_fact_refs(x, key=None):
    """Убирает ссылки вида [F3] / (F2, F3) из всех строк сториборда, кроме служебных полей fact_id / fact_ids."""
    if key in ("fact_id", "fact_ids", "id", "type", "anchor"): return x
    if isinstance(x, str): return FACT_REF.sub("", x).strip()
    if isinstance(x, list): return [strip_fact_refs(i, key) for i in x]
    if isinstance(x, dict): return {k: strip_fact_refs(v, k) for k, v in x.items()}
    return x

TARGET_GAP_WORDS = 55   # одна сцена на 20–25 секунд озвучки (~150 слов/мин)
MAX_GAP_WORDS = 75      # дольше 30 секунд на одной картинке — досылаем сцены
MIN_GAP_WORDS = 40      # чаще 16 секунд — прореживаем

def thin(sb: list[dict], script: str) -> list[dict]:
    """Оставляет сцены с шагом ≈TARGET_GAP_WORDS: из кандидатов в окне [MIN, MAX] после последней оставленной
    берём ближайшего к целевому шагу, при равенстве — не-stat (график, сравнение, цитата, broll)."""
    pos = _anchor_positions(sb, script)
    order = sorted(range(len(sb)), key=lambda i: pos[i] if pos[i] is not None else 10**6)
    sb = [sb[i] for i in order]; pos = [pos[i] for i in order]
    keep = [0]; last = pos[0] or 0
    i = 1
    while i < len(sb):
        window = [j for j in range(i, len(sb)) if pos[j] is not None and MIN_GAP_WORDS <= pos[j] - last <= MAX_GAP_WORDS]
        if window:
            j = min(window, key=lambda j: (abs(pos[j] - last - TARGET_GAP_WORDS) + (8 if sb[j]["type"] == "stat" else 0)))
        else:
            nxt = [j for j in range(i, len(sb)) if pos[j] is not None and pos[j] - last > MAX_GAP_WORDS]
            if not nxt: break
            j = nxt[0]
        keep.append(j); last = pos[j]; i = j + 1
    if sb[-1]["type"] == "outro" and keep[-1] != len(sb) - 1: keep.append(len(sb) - 1)
    out = [sb[k] for k in keep]
    print(f"[storyboard] прореживание: {len(sb)} → {len(out)} сцен")
    return out

def _anchor_positions(sb: list[dict], script: str) -> list[int | None]:
    """Позиция (в словах) каждого якоря в тексте озвучки — тем же способом, что и таймлайн."""
    from .assets import clean_text, _norm, _find
    toks = [_norm(w) for w in clean_text(script).split()]
    out, cur = [], 0
    for sc in sb:
        a = [_norm(w) for w in re.sub(r"\[F\d+\]", "", sc.get("anchor", "")).split()]; a = [w for w in a if w]
        i = None
        for n in (5, 4, 3):
            i = _find(toks, a[:n], cur) or _find(toks, a[:n])
            if i is not None: break
        out.append(i)
        if i is not None: cur = i
    return out

def densify(sb: list[dict], script: str, research: dict, section: str, vid: str) -> list[dict]:
    """Если между соседними якорями больше MAX_GAP_WORDS слов — просим модель добавить сцены на эти участки (одним вызовом)."""
    words = script.split()
    pos = _anchor_positions(sb, script)
    gaps = []
    for k in range(len(sb)):
        a = pos[k]; b = pos[k + 1] if k + 1 < len(sb) else len(words)
        if a is None or b is None: continue
        if b - a > MAX_GAP_WORDS:
            # фрагмент сценария между якорями (по исходному тексту с [Fn], чтобы модель видела fact_id)
            frag = " ".join(words[a:b])
            gaps.append({"after": sb[k]["id"], "words": b - a, "text": frag})
    if not gaps: return sb
    user = ("В сториборде есть участки сценария без смены сцены дольше минуты. Для каждого участка добавь сцены "
            f"(по одной на каждые 50–75 слов), в том же формате и стиле, что и остальные. Не повторяй существующие сцены.\n\n"
            "Существующие сцены (id, type, anchor):\n" + "\n".join(f"- {x['id']} {x['type']}: {x['anchor']}" for x in sb) +
            "\n\nУчастки:\n" + "\n\n".join(f"### после сцены {g['after']} ({g['words']} слов)\n{g['text']}" for g in gaps) +
            "\n\nФакты (для fact_id):\n" + json.dumps(research.get("facts", []), ensure_ascii=False) +
            "\n\nПравила формата сцен:\n" + section +
            "\n\nВерни JSON: {\"scenes\":[{\"after\":\"<id существующей сцены>\", ...поля сцены с новым уникальным id вида s101...}]}")
    res = llm.ask_json(user, heavy=True, max_tokens=12000, tag=f"densify_{vid}")
    added = 0
    for sc in res.get("scenes", []):
        if not all(k in sc for k in ("id", "type", "anchor", "data")) or sc["type"] not in SCENE_TYPES: continue
        sc.pop("after", None); sb.append(sc); added += 1
    print(f"[storyboard] уплотнение: {len(gaps)} участков, добавлено {added} сцен")
    return sb   # порядок восстановит таймлайн по якорям

def restoryboard(vid: str):
    """Сценарий и факты не трогаем — заново собираем только storyboard (+ music_mood, превью) по актуальному промпту.
    Нужно после смены визуальной схемы или когда визуальный QC забраковал раскладку."""
    v = db.get(vid); s = v["payload"]["script"]; research = v["payload"]["research"]; d = db.video_dir(vid); topic = v["payload"].get("topic", {})
    full = config.prompt("script", working_title=v["title"], thesis=topic.get("thesis", ""), format=topic.get("format") or "news",
                         unit=topic.get("unit") or "—", moods=" | ".join(config.music_moods()), facts_json="")
    section = full[full.index("Затем составь storyboard"):]
    user = ("Утверждённый сценарий (текст не менять, он уже озвучивается):\n\n" + s["script"] +
            "\n\nФакты (для fact_id):\n" + json.dumps(research, ensure_ascii=False) + "\n\n" + section +
            "\n\nВерни JSON только с полями storyboard, music_mood и thumbnail_concepts.")
    res = llm.ask_json(user, heavy=True, max_tokens=16000, tag=f"storyboard_{vid}")
    sb = res.get("storyboard") or []
    for sc in sb:
        for k in ("id", "type", "anchor", "data"):
            if k not in sc: raise ValueError(f"Сцена без поля {k}: {sc}")
        if sc["type"] not in SCENE_TYPES: raise ValueError(f"Неизвестный тип сцены {sc['type']} в {sc['id']}")
    if len(sb) < 12: raise ValueError(f"Сториборд слишком короткий: {len(sb)} сцен")
    sb = thin(densify(sb, s["script"], research, section, vid), s["script"])
    s["storyboard"] = strip_fact_refs(sb)
    if res.get("music_mood"): s["music_mood"] = res["music_mood"]
    if res.get("thumbnail_concepts"): s["thumbnail_concepts"] = res["thumbnail_concepts"]
    config.write(d / "storyboard.json", json.dumps(s["storyboard"], ensure_ascii=False, indent=2))
    cost = round(float(v["payload"].get("cost_usd", 0)) + llm.take_cost(), 4)
    db.update(vid, "approved_script", payload={"script": s, "cost_usd": cost})
    print(f"[storyboard] {len(sb)} сцен, mood={s.get('music_mood')}, расходы ${cost:.2f}")

def run_story(vid: str):
    """История компании: ресёрч → текст → кадры и титры → на утверждение."""
    from . import story
    v = db.get(vid); t = v["payload"]["topic"]; d = db.video_dir(vid)
    prev = v["payload"].get("research") or {}
    if len(prev.get("facts") or []) >= 10 and v["payload"].get("research_of", t.get("working_title")) == t.get("working_title"):
        research = prev; print(f"[research] из базы: фактов {len(prev['facts'])} — повтор этапа не платит за ресёрч второй раз", flush=True)   # 28.09
    else:
        research = llm.ask_json(config.prompt("research_story", working_title=t["working_title"], hero=t.get("hero") or t.get("ticker") or "",
                                              thesis=t.get("thesis", "")), search=True, heavy=True, max_tokens=16000, tag=f"research_{vid}")
    facts = [f for f in research.get("facts", []) if f.get("id") and f.get("source_url")]
    if len(facts) < 10: raise ValueError(f"Ресёрч дал только {len(facts)} фактов с источниками — мало для истории")
    research["facts"] = facts; story.facts_csv(d, facts)
    db.update(vid, payload={"research": research, "research_of": t.get("working_title")})   # ресёрч ($0.5–1.8) в базу сразу: падение ниже больше не повторяет его (аудит 23.09)
    extra = ""
    if v["payload"].get("fix_note"):
        extra = "\n\nПРАВКИ ВЛАДЕЛЬЦА К ПРОШЛОЙ ВЕРСИИ (обязательно учесть): " + str(v["payload"]["fix_note"])
    b = v["payload"].get("brief") if v["payload"].get("brief_of") == t.get("working_title") else None
    if not b:
        b = brief.make(vid, research, extra)   # замысел проверяем до 4 700 слов, озвучки и картинок (разбор 20.09)
        db.update(vid, payload={"brief": b, "brief_of": t.get("working_title")})   # и не платим за него второй раз при повторе этапа
    extra += brief.block(b)
    s = story.write_script(vid, research, extra)
    # 28.09: текст после фактчека — на диск; падение на вычитке, вступлении или кадрах не платит за фактчек второй раз
    import hashlib
    fc_p = d / "script_factchecked.json"; fc_key = hashlib.sha1(s["script"].encode("utf-8")).hexdigest()[:16]
    try: fc = json.loads(config.read(fc_p)) if fc_p.exists() else {}
    except Exception: fc = {}
    fc_hit = bool(config.FACTCHECK and fc.get("key") == fc_key)
    if fc_hit: s = fc["s"]; print("[factcheck] из черновика", flush=True)
    if config.FACTCHECK and not fc_hit: s = story.factcheck(vid, s, research)   # Astra ищет выдуманные детали, автор текста (LLM_MODEL_WRITER) правит помеченные фразы
    if config.FACTCHECK and not fc_hit: config.write(fc_p, json.dumps({"key": fc_key, "s": s}, ensure_ascii=False))
    checked = s["script"]   # текст, который прошёл фактчек: всё, что изменится ниже, проверяем повторно (claims.py)
    s = story.polish(vid, s)   # после фактчека: убрать пустые обороты, дубли и служебные пометки (добавлять факты редактору запрещено)
    s["script"] = story._unleak(s["script"]); s["parts"] = [story._unleak(p) for p in s.get("parts") or []]   # и когда вычитка отклонена
    s["script"] = story.round_spoken(s["script"]); s["parts"] = [story.round_spoken(p) for p in s.get("parts") or []]   # диктор не читает шесть знаков после точки
    # первые 90 секунд решают судьбу ролика — проверяем по темпу диктора ДО раскадровки и озвучки (stages/opening.py).
    # Переписывать вступление позже нельзя: якоря сцен первой минуты привязаны к его фразам (ревью 21.09)
    from . import opening
    op = opening.check_text(vid, d, s, b)
    if not op["ok"]:
        s = brief.rewrite_opening(vid, s, b, "; ".join(op["rules"] + [str(op["judge"].get("why", "")), str(op["judge"].get("rewrite_hint", ""))]))
        op = opening.check_text(vid, d, s, b)
        if not op["ok"]: print("[opening] после переписывания всё ещё слабо — идём дальше, это попадёт в отчёт QC", flush=True)
    if config.FACTCHECK:   # вычитка, правка вступления и склейки могли увести числа от проверенных выдержек
        cl = claims.verify(vid, checked, s["script"], research)
        if not cl["ok"]: s = claims.fix(vid, s, cl["bad"])
        config.write(d / "claims_check.json", json.dumps(cl, ensure_ascii=False, indent=1))
    # текст в базу ДО кадров: story.ensure_entities читает payload["script"], и на новом ролике этап падал по KeyError
    # (у Apple не всплывало — там сценарий оставался от прошлых прогонов). Заодно текст не теряется, если упадёт раскадровка.
    if t.get("style") == "cartoon" and config.ES_FIRST:   # 13.10 владелец: «сразу испанская озвучка» — раскадровка и голос по испанскому тексту
        from . import cartoon_es; s = cartoon_es.to_spanish(vid, s)
    db.update(vid, payload={"script": s, "research": research})
    s = story.write_shots(vid, s, research)
    config.write(d / "script.md", "# " + s["title_options"][0] + "\n\n" + s["script"] + "\n\n---\n" + story.factcheck_note(s))
    config.write(d / "shots.json", json.dumps({"shots": s["shots"], "overlays": s["overlays"]}, ensure_ascii=False, indent=2))
    cost = round(float(v["payload"].get("cost_usd", 0)) + llm.take_cost(), 4)
    db.update(vid, "scripted", title=s["title_options"][0], payload={"script": s, "research": research, "fix_note": None, "cost_usd": cost, "brief": b,
                                                                     "shot_downgrades": s.pop("shot_downgrades", []), "needs_review": s.pop("needs_review", False),
                                                                     "opening_needs_review": op.get("ok") is not True and (v["payload"].get("topic") or {}).get("style") != "cartoon", "script_approval": None,
                                                                     "release_gate": None, "final_approval": None})
    from .. import gates
    if config.AUTO_SCRIPT_APPROVE and gates.script_ready(db.get(vid)):
        db.update(vid, "approved_script")
        telegram.send(f"Сценарий `{vid}` готов и ушёл в производство сам.\n{story.factcheck_note(s)}\n"
                      f"Остановить: `reject {vid}`", file=d / "script.md")
    else:
        telegram.ask_script_review(vid, d / "script.md", note=story.factcheck_note(s))
    print(f"[story] {len(s['script'].split())} слов, {len(s['shots'])} кадров, {len(s['overlays'])} титров, расходы ${cost:.2f}")

def reshots(vid: str):
    """Пересобрать только кадры и титры story-видео под утверждённый текст."""
    from . import story
    v = db.get(vid); s = v["payload"]["script"]; d = db.video_dir(vid)
    s = story.write_shots(vid, s, v["payload"]["research"])
    config.write(d / "shots.json", json.dumps({"shots": s["shots"], "overlays": s["overlays"]}, ensure_ascii=False, indent=2))
    cost = round(float(v["payload"].get("cost_usd", 0)) + llm.take_cost(), 4)
    db.update(vid, "approved_script", payload={"script": s, "cost_usd": cost, "shot_downgrades": s.pop("shot_downgrades", []), "needs_review": s.pop("needs_review", False)})
    db.update(vid, payload={"script_approval": None, "release_gate": None, "final_approval": None})
    from .. import gates
    gates.require_script(vid)
    print(f"[story] {len(s['shots'])} кадров, {len(s['overlays'])} титров, расходы ${cost:.2f}")
