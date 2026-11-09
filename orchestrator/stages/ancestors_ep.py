"""Ordinary Ancestors — выпуски по формуле, снятой с Ink Explainer (16.10.2026, владелец: «сделай ты сценарий и ролик,
изучи предварительно все ролики Ink Explainer»; разбор — work/ancestors-v2/research/findings.md).

Отличия от пилота (ancestors_cartoon.py, Межирич): общая тема быта вместо одного раскопа; крючок про жизнь зрителя;
темп ~200 слов/мин; сквозной герой; цветные сцены + белые кадры с рукописными надписями; смена рисунка ~3 с.
Пилот этот модуль не трогает. Очередь ae_*: research → script (стоп на ae_script_review, сценарий смотрит владелец)
→ approve → assets → render → ae_ready. Загрузки здесь нет (только ancestors_youtube по явной команде).
Бриф выпуска — work/ordinary-ancestors/episodes/<slug>/episode.json."""
import hashlib
import json
import os
import shutil
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path

from .. import config, db, llm
from ..ancestors_profile import CHANNEL_ID

FORMAT = "ancestors_ink2"
EP_ROOT = config.ROOT / "work/ordinary-ancestors/episodes"
VERSION = "ancestors-ink2-v1"
TARGET_WPM = 200

STYLE = (". Simple hand-drawn cartoon in the style of a modern explainer channel: clean black marker outlines of even weight, "
         "flat solid colours, no gradients, no texture, no hatching, no realistic shading. People are simple stick-figure-like "
         "cartoon characters with big round heads, dot eyes, expressive eyebrows and simple mouths, thin limbs, and very clear "
         "emotions. Backgrounds are either a simple flat-coloured scene (sky, landscape, river, interior, firelight at night) "
         "or plain white, exactly as the shot asks. Any lettering is hand-written bold black marker capitals, only the "
         "exact words given in quotes, spelled exactly; no other text, no watermarks, no signatures")

CAST = ("RECURRING CHARACTERS (draw them identically every time): "
        "THE KID — a small Ice Age child about six years old, big round peach-coloured head, two dot eyes, expressive eyebrows, "
        "a messy red-brown tuft of hair tied up on top of the head with a thin cord, a simple knee-length brown fur tunic, bare feet "
        "or fur foot wraps. GROWN-UPS of the group — taller stick-figure adults with round peach heads, messy dark hair (one woman "
        "has a long dark braid), plain brown and grey hide-and-fur clothing. MODERN YOU — a modern stick figure with a round white "
        "head, short black hair and a plain grey hoodie, used only in present-day comparison shots. "
        "Ice Age rules: no metal, no pottery, no farming, no domesticated animals, no wheels, no buildings, no woven cloth.")

LOOKS = {"THE KID": "THE KID looks like: a small six-year-old with a big round peach head, dot eyes, expressive eyebrows, a messy red-brown "
                    "tuft of hair tied on top with a cord, a knee-length brown fur tunic",
         "MODERN YOU": "MODERN YOU looks like: a stick figure with a round white head, short black hair and a plain grey hoodie",
         "GROWN-UP": "GROWN-UPS look like: tall Ice Age stick-figure adults with round peach heads, messy dark hair and brown hide-and-fur "
                     "clothing (16.10: without this the model drew the Ice Age man in a modern shirt)"}
DONT = ("Draw only what this shot describes. Do not add a lineup or reference sheet of characters, do not add icons, charts or "
        "crossed-out symbols that the shot does not ask for. Do not add the grey-hoodie modern figure unless the shot names MODERN YOU")


HERO, HERO_WORDS = "THE KID", ("kid", "child", "toddler", "tuft", "six-year-old")
ERA = " Ice Age scenes contain only hides, furs, stone, bone, wood, plants and fire as materials."   # позитивно: список запретов модель рисовала значками


def set_episode(ep):
    """16.10: персонажи и эпоха — из episode.json["style"] (выпуск 3 — Урук, не ледниковый период); без поля — ледниковый набор."""
    global CAST, LOOKS, HERO, HERO_WORDS, ERA
    st = ep.get("style")
    if not st: return
    CAST, ERA, HERO, HERO_WORDS = st["cast"], " " + st["era"], st["hero"], tuple(st["hero_words"])
    LOOKS = {st["hero"]: st["hero_look"], "MODERN YOU": LOOKS["MODERN YOU"]}


def cast_for(prompt):
    """Внешность только тех героев, что названы в описании кадра, плюс прямые запреты (без списка «правил эпохи»)."""
    low = prompt.lower()
    if "white background" in low and ("hand-lettered" in low or "lettering" in low) and not any(w in low for w in ("kid", "child", "people", "figure", "modern you")):
        return "This is a lettering card: draw only the quoted words in black marker on white, with at most one tiny related doodle. No characters, no scene."
    looks = [v for k, v in LOOKS.items() if k in prompt or (k == HERO and "MODERN YOU" not in prompt and any(
        w in low for w in HERO_WORDS))]   # раскадровка часто пишет «child», а не «THE KID»
    if ("MODERN YOU" in prompt or "present-day" in low) and HERO not in prompt:   # 16.10 владелец: в современных сценах были древние люди
        looks = [LOOKS["MODERN YOU"]] if "MODERN YOU" in prompt else []   # без внешности древнего малыша (слово «kid» тянуло его в класс)
        return " ".join(looks) + ". " + DONT + ". Present-day scene: every person wears modern clothes and has ordinary modern hair; no fur or ancient clothing, no ancient hairstyles, no ancient people."
    era = "" if "MODERN YOU" in prompt and "THE KID" not in prompt else \
        " Ice Age scenes contain only hides, furs, stone, bone, wood, plants and fire as materials."   # позитивно: список запретов модель рисовала значками
    return " ".join(looks) + (". " if looks else "") + DONT + "." + era


RESEARCH = """You are the researcher for an English documentary episode on Ordinary Ancestors (everyday life before the modern world).
EPISODE: {title}
THESIS: {thesis}
Verify each research lead below against reliable sources (peer-reviewed papers, university or museum pages, major science
journalism). Correct leads where the sources say something different, drop what you cannot verify, and add up to 10 more strong,
concrete facts about children's daily life in the Upper Palaeolithic or in well-studied hunter-gatherer societies that serve the thesis.
For each verified fact return: id (F1, F2...), claim (one precise English sentence, numbers with units), date_label (e.g. "about
30,000 years ago" or "1987 study"), place, source_title, source_url, confidence ("high" or "medium").
LEADS:
{leads}
Return JSON {{"facts": [...], "corrections": ["lead -> what sources actually say"]}} with at least 25 facts."""

WRITE = """You write the narration for Ordinary Ancestors, a new English YouTube channel about everyday life before the modern
world. The proven format of this genre (studied across a top channel's whole catalogue):
- {w0}-{w1} words in exactly {parts} parts, spoken fast and energetically (~200 words per minute, about 11-12 minutes).
- Second person ("you"), conversational, confident and vivid. Short sentences mixed with longer ones. American English.
- Part 1 opens on the viewer's OWN present-day life for 3-6 sentences with concrete sensory details, then a hard turn
  ("Now rewind 30,000 years."), then one ordinary person of the past, then the common belief stated plainly, then the promise
  that evidence in the ground says otherwise, and the central question asked explicitly. Plant one open loop (an image or
  puzzle) that the very end returns to. One short natural sentence early in part 1 says the day you follow is imagined from
  real finds; after that, no stacked caveats ("researchers think" at most once per part, only where truly uncertain).
- Each later part: a question or problem -> the naive assumption -> "here's the thing" twist -> a specific find with place,
  rounded date and, where it helps, the researcher and year -> what it meant for that kid -> one linking sentence that opens
  the next problem.
- Concrete details over abstractions. Numbers only where they hit hard. Light humour and warmth through comparisons with the
  viewer's own life. Useful devices: an ancient moment told in a modern frame (a reality show, a job interview, a parenting
  forum), absurd pop-culture comparisons, a modern person dropped into the ancient scene. Invent your own jokes; never reuse
  jokes from books or other channels.
- Ending: a quick recap of what the evidence showed, then a callback to the viewer and to the open loop; the last line lands
  emotionally. No "subscribe", no "in this video", no mention of any other channel. Do not copy any existing video's wording.
- Every fact must come from RESEARCH. No invented named prehistoric people, no speech quotes from prehistoric people.
EPISODE TITLE: {title}
THESIS: {thesis}
HOOK IDEA: {hook}
CHAPTER PLAN: {plan}
RESEARCH (the only source of facts): {research}
Return JSON {{"parts": [{{"name": "short chapter name (2-6 words)", "text": "..."}}]}} with exactly {parts} parts."""

CHECK = """Fact-check this part of an English documentary narration against ONLY the supplied research.
Flag material factual errors: wrong numbers, dates, places, researchers, overstated certainty, or claims that the research
does not support. Imagined everyday scenes clearly framed as "imagine"/"you" are allowed. Do not rewrite for style.
Keep the narrator's voice: a fix replaces the wrong words with correct ones in the same tone. NEVER add disclaimer sentences such as
"the research does not establish…", "we cannot know…", "this is debated" — if certainty is overstated, change one word ("probably",
"one idea is"). Leave endings, jokes and rhetorical questions alone unless they state a false fact.
RESEARCH: {research}
NARRATION: {text}
Return JSON {{"fixes":[{{"old":"exact substring","new":"correction","why":"reason"}}],"unresolved":["issue you cannot fix from the research"]}}."""

BOARD = """Storyboard one part of an English Ordinary Ancestors episode. One STATIC drawing for EACH numbered beat; quick cuts
carry the rhythm (about 3 seconds per drawing). Each prompt is 30-70 English words, self-contained (re-describe characters by
their look every time), one clear idea per drawing. Mix, roughly: 55% scenes with characters in a simple flat-coloured setting
and clear emotion; 20% plain white background with 1-4 big hand-lettered words that punch the beat (give the exact words in
quotes, capitals); 15% the actual evidence drawn simply (footprints, finger lines on a cave ceiling, beads, a flint core) with
at most a short hand-lettered place label in quotes; 10% MODERN YOU comparison shots (mostly at the start and the end).
Never two white-background shots in a row; never the same composition twice in a row. Funny, warm, expressive faces; no gore,
no dead bodies shown (burials as simple beads and outlines only).
{cast}
FACTS FOR THIS PART: {facts}
BEATS:
{beats}
Return JSON {{"shots":[{{"n":1,"prompt":"..."}}]}} with exactly {count} entries, n = 1..{count}."""

QA = """Inspect these numbered drawings for an English cartoon history episode. Compare EACH with its narration
and intended drawing. Flag only material problems: wrong or misspelled lettering, extra text, watermarks; the recurring hero drawn
off-model ({hero_look}); things impossible in the period ({era}) except in MODERN YOU shots; ancient people in present-day shots;
photo, 3D or painterly style instead of a flat marker cartoon;
broken anatomy; gore; an unintelligible or blank picture; a picture that contradicts the narration.
Intents: {intents}
Return JSON {{"bad":[{{"n":1,"why":"specific visible problem and how to fix it"}}]}}; an empty list means all are fine."""


def _json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def _save(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8"); tmp.replace(path)


def _digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def _profile():
    if os.getenv("CHANNEL_PROFILE") != "ancestors":
        raise RuntimeError("Use the isolated Ordinary Ancestors profile")


def start(slug):
    _profile()
    ep = _json(EP_ROOT / slug / "episode.json")
    with closing(db.conn()) as c:
        for row in c.execute("SELECT id,payload FROM videos"):
            if (json.loads(row["payload"] or "{}").get("topic") or {}).get("episode") == slug: return row["id"]
    topic = {"format": FORMAT, "episode": slug, "channel_id": CHANNEL_ID, "working_title": ep["title"], "lang_target": "en"}
    vid = db.add("ancestors-" + slug, ep["title"], {"topic": topic, "lang": "en", "episode": ep})
    db.update(vid, "ae_topic")
    return vid


def _ep(vid):
    _profile(); v = db.get(vid)
    if (v["payload"].get("topic") or {}).get("format") != FORMAT: raise ValueError("not an ink2 episode")
    return v, v["payload"]["episode"], db.video_dir(vid)


def research(vid):
    v, ep, d = _ep(vid)
    path = d / "research.json"
    if not path.exists():
        r = llm.ask_json(RESEARCH.format(title=ep["title"], thesis=ep["thesis"], leads="\n".join("- " + x for x in ep["research_leads"])),
                         search=True, heavy=True, max_tokens=16000, tag=f"ae_research_{vid}")
        facts = [f for f in r.get("facts", []) if isinstance(f, dict) and f.get("claim") and str(f.get("source_url", "")).startswith("http")]
        if len(facts) < 20: raise ValueError(f"research: only {len(facts)} sourced facts")
        _save(path, {"facts": facts, "corrections": r.get("corrections", [])})
    db.update(vid, "ae_research")


def script(vid):
    v, ep, d = _ep(vid)
    res = _json(d / "research.json"); draft_path = d / "script_draft.json"
    if draft_path.exists(): draft = _json(draft_path)
    else:
        w0, w1 = ep.get("length_words", [2200, 2500]); n = ep.get("parts", 6)
        for _ in range(2):
            r = llm.ask_json(WRITE.format(w0=w0, w1=w1, parts=n, title=ep["title"], thesis=ep["thesis"], hook=ep["hook_idea"],
                                          plan="\n".join(f"{i + 1}. {p}" for i, p in enumerate(ep["chapters_plan"])),
                                          research=json.dumps(res["facts"], ensure_ascii=False)),
                             model=config.LLM_MODEL_WRITER, max_tokens=16000, tag=f"ae_write_{vid}")
            parts = r.get("parts") or []
            words = sum(len(str(p.get("text", "")).split()) for p in parts)
            if len(parts) == n and w0 * 0.9 <= words <= w1 * 1.1: break
        else: raise ValueError(f"script shape: {len(parts)} parts, {words} words")
        draft = {"parts": parts, "checked": []}; _save(draft_path, draft)
    issues = []
    for i, p in enumerate(draft["parts"]):
        if i in draft["checked"]: continue
        r = llm.ask_json(CHECK.format(research=json.dumps(res["facts"], ensure_ascii=False), text=p["text"]),
                         heavy=True, max_tokens=4000, tag=f"ae_check_{vid}_{i + 1}", model=config.LLM_MODEL_FACTCHECK or None)
        if not isinstance(r.get("fixes"), list) or not isinstance(r.get("unresolved"), list): raise ValueError("factcheck incomplete")
        for f in r["fixes"]:
            if isinstance(f.get("old"), str) and f["old"] and f["old"] in p["text"] and isinstance(f.get("new"), str):
                p["text"] = p["text"].replace(f["old"], f["new"])
            else: issues.append(f"part {i + 1}: fix not applied: {f}")
        issues += [f"part {i + 1}: {u}" for u in r["unresolved"]]
        _save(d / f"factcheck_{i + 1}.json", r); draft["checked"].append(i); _save(draft_path, draft)
    md = "# " + ep["title"] + "\n\n" + "\n\n".join(f"## {p['name']}\n\n{p['text']}" for p in draft["parts"])
    config.write(d / "script.md", md)
    words = sum(len(p["text"].split()) for p in draft["parts"])
    db.update(vid, "ae_script_review", payload={"script_words": words, "factcheck_open": issues})
    print(f"[ancestors-ep] сценарий готов на просмотр: {d / 'script.md'} ({words} слов, открытых замечаний {len(issues)})", flush=True)


def approve_script(vid):
    """Владелец (или редактор по его поручению) принял script.md — его текст и идёт в озвучку."""
    v, ep, d = _ep(vid)
    if v["status"] != "ae_script_review": raise ValueError("сценарий не ждёт просмотра: " + v["status"])
    text = config.read(d / "script.md")
    parts, names, cur = [], [], None
    for line in text.splitlines():
        if line.startswith("## "): names.append(line[3:].strip()); parts.append([])
        elif parts is not None and names: parts[-1].append(line)
    parts = [" ".join(" ".join(p).split()) for p in parts]
    if len(parts) != ep.get("parts", 6) or any(not p for p in parts): raise ValueError("script.md: ожидались части под заголовками ##")
    s = {"lang": "en", "names": names, "parts": parts, "script": "\n\n".join(parts), "sha": _digest(parts)}
    db.update(vid, "ae_scripted", payload={"script": s})


def _cast_style():
    config.CARTOON_STYLE = STYLE   # в процессе Ancestors: рисунки этого формата, не стиль пилота (средняя цена, как у сцен)


def assets(vid):
    from . import assets as A, es_cartoon, es_checks
    v, ep, d = _ep(vid); s = v["payload"]["script"]; res = _json(d / "research.json"); _cast_style(); set_episode(ep)
    board_path = d / "ae_board.json"
    board = _json(board_path) if board_path.exists() else {"parts": [], "script_sha": s["sha"], "version": VERSION}
    if board["script_sha"] != s["sha"]: raise RuntimeError("текст изменился после раскадровки")
    for i in range(len(board["parts"]), len(s["parts"])):
        beats = es_cartoon._beats(s["parts"][i])
        for attempt in range(3):   # модель иногда сбивается со счёта на длинной части — повтор только этой части
            r = llm.ask_json(BOARD.format(cast=CAST, facts=json.dumps(res["facts"], ensure_ascii=False)[:12000],
                                          beats="\n".join(f"{n}. {b}" for n, b in enumerate(beats, 1)), count=len(beats)),
                             heavy=True, max_tokens=20000, tag=f"ae_board_{vid}_{i + 1}", model=config.LLM_MODEL_SHOTS or None)
            got = {x.get("n"): x.get("prompt") for x in r.get("shots", []) if isinstance(x, dict)}
            if set(got) == set(range(1, len(beats) + 1)) and all(isinstance(p, str) and len(p.split()) >= 6 for p in got.values()): break   # кадр-надпись на белом бывает коротким
            print(f"[ancestors-ep] раскадровка части {i + 1}: {len(got)} из {len(beats)} — повтор", flush=True)
        else: raise ValueError(f"раскадровка части {i + 1}: нужно ровно {len(beats)} описаний")
        board["parts"].append({"beats": beats, "prompts": [got[n] for n in range(1, len(beats) + 1)]}); _save(board_path, board)
    config.TTS_TARGET_WPM = ep.get("wpm", TARGET_WPM)   # формат жанра: ~200 слов/мин; Charlie сам ~162 — 16.10 владелец: «не слишком быстро?», для выпуска можно задать wpm
    A._voice("\n\n".join(A.clean_text(t) for t in s["parts"]), d, [A.clean_text(t) for t in s["parts"]])
    words = _json(d / "words.json"); duration = round(float(words[-1]["e"]) + 1.2, 3)
    shots_path = d / "ae_shots.json"
    shots = _json(shots_path) if shots_path.exists() else [
        {"id": f"ae_p{i + 1}_{k + 1:03d}", "beat": b, "prompt": p}
        for i, part in enumerate(board["parts"]) for k, (b, p) in enumerate(zip(part["beats"], part["prompts"]))]

    def draw(x, repair=False):
        sid = x["id"] + (f"_v{x['rev']}" if x.get("rev") else "") + (f"_r{x.get('repairs', 0)}" if repair else "")
        path = d / "images" / (sid + ".png")
        if not path.exists():
            # 16.10: весь CAST к каждому кадру модель иногда рисовала буквально (персонажи в ряд, перечёркнутые значки) —
            # теперь только внешность тех, кто назван в кадре, и запреты прямым указанием
            prompt = x["prompt"] + ". " + cast_for(x["prompt"]) + (". Fix these visible mistakes: " + x.get("repair_reason", "") if repair else "")
            for attempt in range(2):
                try: A._image(prompt, d, sid, config.IMAGE_MODEL, cartoon=True); break
                except Exception as e:
                    if attempt: raise
                    print(f"[ancestors-ep] {sid}: {str(e)[:120]} — повтор", flush=True)
        return "images/" + path.name
    todo = [x for x in shots if not x.get("image")]
    with ThreadPoolExecutor(8) as pool:
        for x, f in zip(todo, pool.map(draw, todo)): x["image"] = f; _save(shots_path, shots)

    def check():
        def ask(batch):
            intents = [{"n": i, "narration": x["beat"], "intent": x["prompt"]} for i, x in enumerate(batch, 1)]
            return llm.ask_vision(QA.format(intents=json.dumps(intents, ensure_ascii=False), hero_look=LOOKS.get(HERO, ""), era=ERA.strip()), [es_cartoon._sheet([d / x["image"] for x in batch])],
                                  tag=f"ae_visual_{vid}", model=config.LLM_MODEL_VISION, max_tokens=2500)
        rep = es_checks.run(d, shots, "ae_visual_qa", [QA, VERSION, STYLE, CAST], ask, workers=3, batch_size=8)
        es_checks.require_complete(rep, "Ordinary Ancestors visual check")
        return rep
    rep = check(); bad = es_checks.failed_ids(rep)
    reasons = {x["id"]: "; ".join(z["why"] for z in x["issues"]) for x in rep["items"] if x["status"] == "FAIL"}
    redo = [x for x in shots if x["id"] in bad and x.get("repairs", 0) < 1]
    for x in redo: x["repair_reason"] = reasons[x["id"]]; x["repairs"] = x.get("repairs", 0) + 1
    with ThreadPoolExecutor(8) as pool:
        for x, f in zip(redo, pool.map(lambda it: draw(it, True), redo)): x["image"] = f; _save(shots_path, shots)
    rep = check()   # остаток — в отчёт (STRICT_GATES=0, владелец 07.10); проверка не завершена — повтор этапа
    starts = es_cartoon._times([x["beat"] for x in shots], words)
    if any(starts[i] >= starts[i + 1] for i in range(len(starts) - 1)): raise ValueError("сбой привязки кадров к озвучке")
    spec = {"duration": duration, "voice": "voice.mp3", "version": VERSION,
            "shots": [{"start": t, "end": starts[i + 1] if i + 1 < len(starts) else duration, "image": shots[i]["image"], "move": "static"}
                      for i, t in enumerate(starts)]}
    off, ps = 0, []
    for part in board["parts"]: ps.append(starts[off]); off += len(part["beats"])
    spec["part_starts"] = ps; _save(d / "ae_spec.json", spec)
    db.update(vid, "ae_assets", payload={"shots": len(shots), "duration": duration, "visual_qa": {"status": rep["status"], "counts": rep["counts"]}})


THUMB = ("YouTube thumbnail, 16:9, bright and readable at small size: {scene}. Big bold hand-lettered words at the top in bright yellow "
         "capitals with a thick black outline: \"{text}\". Flat cartoon, thick black outlines, saturated flat colours, one clear focal "
         "character with an exaggerated, readable emotion")


def render(vid):
    from . import assets as A, es_cartoon, sound
    from .qc import tech_check
    from PIL import Image
    v, ep, d = _ep(vid); spec = _json(d / "ae_spec.json"); s = v["payload"]["script"]; _cast_style(); set_episode(ep)
    pub = d / "publish"; pub.mkdir(exist_ok=True)
    th = ep.get("thumbnail") or {}
    if th and not (pub / "thumbnail.jpg").exists():
        A._image(THUMB.format(scene=th["scene"] + ". " + cast_for(th["scene"]), text=th["text"]), d, "thumb_main", config.IMAGE_MODEL, cartoon=True)
        Image.open(d / "images" / "thumb_main.png").convert("RGB").resize((1280, 720), Image.LANCZOS).save(pub / "thumbnail.jpg", quality=92)
    res = _json(d / "research.json")
    lines = [ep.get("description_hook", ""), "", "Chapters:"]
    for sec, name in zip(spec["part_starts"], s["names"]):
        n = int(sec) if sec > 1 else 0; lines.append(f"{n // 60:02d}:{n % 60:02d} {name}")
    lines += ["", "Sources:"]
    seen = set()
    for f in res["facts"]:
        if f["source_url"] in seen: continue
        seen.add(f["source_url"]); lines.append(f"{f.get('source_title', '')} — {f['source_url']}")
    lines += ["", "Illustrated reconstruction by Ordinary Ancestors: everyday scenes are imagined from real archaeological finds and studies."]
    config.write(pub / "title.txt", ep["title"]); config.write(pub / "description.txt", "\n".join(lines).strip()[:4900])
    final = d / "final.mp4"; tmp = config.RENDER_TMP; tmp.mkdir(parents=True, exist_ok=True)
    out, loud = tmp / (vid + ".mp4"), tmp / (vid + "_master.mp4")
    es_cartoon._ffmpeg_render(d, spec, out); sound.master(out, loud); loud.replace(out); shutil.move(str(out), str(final))
    tech = tech_check(final, {"duration": spec["duration"], "pauses": []})
    db.update(vid, "ae_ready", payload={"tech": tech})
    print(f"[ancestors-ep] готово на просмотр: {final} ({spec['duration'] / 60:.1f} мин); техпроверка: {'; '.join(tech) or 'чисто'}", flush=True)


NEXT = {"ae_topic": research, "ae_research": script, "ae_scripted": assets, "ae_assets": render}


def run_once():
    """Один этап одного выпуска (ae_script_review и ae_ready — остановки для владельца)."""
    _profile()
    from ..main import _execute
    from ..locking import FileLock, video_lock
    with FileLock(config.DATA / ".pipeline_ancestors.lock", "ancestors-ep"):
        for status, fn in NEXT.items():
            for v in db.by_status(status):
                with video_lock(v["id"], status):
                    if db.get(v["id"])["status"] == status: _execute(fn, v["id"], status); return v["id"], status
    return None
