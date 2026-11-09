"""Ordinary Ancestors: isolated, resumable, first-pilot-only illustrated history.

No queue replenishment, Shorts, comments, scheduling or automatic uploads. The
watch stops at anc_ready. An explicit upload-ancestors command is private only.
"""
import hashlib
import json
import os
import shutil
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path

from .. import config, db, llm
from ..ancestors_profile import CHANNEL_ID
from ..locking import FileLock, video_lock

FORMAT = "history_cartoon"
PILOT_KEY = "ordinary-ancestors-ice-age-home-v1"
TITLE = "A Winter Night Inside an Ice Age Home"
SEED = config.ROOT / "work/ordinary-ancestors/first-episode"
INK_FORMAT_VERSION = "ancestors-ink-flat-static-v1"
RENDER_VERSION = "ancestors-native-static-v1"
IMAGE_CONTEXT = 'Mezhyrich Structure Four, about 18,000 years ago is historical context, not a list of objects to add. Render ONLY the subjects explicitly requested by this shot. Do not add people, a dwelling, a roof, mammoth bones or a whole settlement to object, hand, landscape or evidence-detail scenes. If people are requested, use unnamed modern humans as original simple round-headed figures in plausible plain layered skin garments. If an imagined home covering is explicitly requested, show at most one simple opaque hide covering; its material and shape are hypothetical, and the actual roof and supports are unknown. No visible invented supporting poles, bone pillars, ridgepoles, stakes, lashings, fitted joints, chimney or precise entrance construction. In evidence diagrams, show only the requested simplified ground remains; a requested hypothetical covering can be a separate dotted outline, never a solid excavated structure. If mammoth bones are explicitly requested, they rest irregularly at ground level, with different shapes and sizes selected only from the requested skull, jaw, scapula, pelvis or long-bone types; never repeated upright femurs, identical posts, a regular fence or a symmetric rib-cage frame. This is not the museum reconstruction of Dwelling One. No added metal, pottery, farming, modern furniture, glass, dogs, ape-like people, text or labels. Keep pure white background, bold black outlines and flat solid color fills; firelight is a small flat orange accent, not a dark full-frame room.'

CHECK = """Review this English documentary narration against ONLY the supplied research.
This is an explicitly imagined winter evening informed by archaeology, not an eyewitness story.
Keep observations, debated interpretations and imagined actions clearly separate. Do not invent
family roles, exact weather, roof material, recipes or prehistoric speech. Preserve natural narration.
Give only material factual corrections as exact substring replacements. Do not rewrite for taste.
RESEARCH: {research}
NARRATION: {text}
Return JSON with BOTH keys: {{"fixes":[{{"old":"exact substring","new":"correction","why":"reason"}}],
"unresolved":[]}}. unresolved contains any material issue you cannot fix from this research.
"""

BOARD = """Storyboard Ordinary Ancestors, an English illustrated archaeological reconstruction.
One STATIC picture for EACH numbered beat; cuts between pictures provide the visual rhythm.
Each English prompt is 35-70 words, self-contained, with one clear action or object.
Compose on pure white: thick black outlines, flat solid colors, large readable simple shapes.
Use our own original round white heads, dot eyes, short mouth lines and thin limbs; no copied mascot.
Alternate a human action, one object close-up and a simplified evidence diagram. A wider view
must remain a minimal isolated drawing, not a full painted landscape or detailed room.
Do not request watercolor, paper texture, cross-hatching, gradients, realistic shadows or camera moves.
No decorative business metaphors. No on-image text; no added people in object-only scenes.
The unnamed people, evening, weather and roof are illustrative reconstruction, never evidence.
For an evidence reveal: surviving ground remains solid; hypothetical roof dotted/translucent.
Never invent detailed artefacts or mix archaeological sites. Modern location map only if requested
by the narration; avoid geographic map details that a generator cannot render reliably.
SCOPE AND VISUAL RULES: {rules}
FACTS FOR THIS PART: {facts}
BEATS:
{beats}
Return JSON {{"shots":[{{"n":1,"prompt":"..."}}]}} with exactly {count} unique n values 1..{count}.
"""

QA = """Inspect these numbered images for an English illustrated archaeology documentary.
Compare EACH with its matching narration and intended scene below. Flag material false objects,
wrong site/layout/period, metal or pottery, a symmetric elephant rib-cage house, modern furniture,
ancient people as apes, unsupported detailed props, text/watermarks, photo/3D instead of ink drawing,
severe anatomy, or a blank/unintelligible scene. Also flag watercolor/paper texture, painterly
full backgrounds, gradients/realistic shading, or failure to use a white background, bold black
outlines and flat colors. Figures must be original simple round-headed drawings.
A plausible reconstruction is allowed only as
described in the intent; evidence diagrams must distinguish remains from hypothetical roof.
Historical rules: {rules}
Shot intents: {intents}
Return JSON {{"bad":[{{"n":1,"why":"specific visible problem and correction"}}]}}.
An empty bad list means every image was inspected and fits its intended scene.
"""


def _json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def _save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def _profile():
    if os.getenv("CHANNEL_PROFILE") != "ancestors":
        raise RuntimeError("Use the isolated ancestors command, not the original channel profile")


def validate_research(research):
    if research.get("schema") != "ordinary-ancestors.research-brief.v1":
        raise ValueError("Expected the source-verified first-episode research brief")
    if research.get("episode", {}).get("title") != TITLE:
        raise ValueError("Only the explicitly requested first pilot is authorized")
    facts = research.get("facts", [])
    sources = {s["id"]: s for s in research.get("sources", [])}
    if len(facts) < 12 or not research.get("historical_scope") or not research.get("visual_historical_invariants"):
        raise ValueError("Historical research is incomplete")
    for fact in facts:
        refs = fact.get("source_ids", [])
        if not fact.get("id") or not fact.get("claim_en") or not refs or any(ref not in sources for ref in refs):
            raise ValueError("Each historical fact needs a valid source reference")
    if len(research.get("chapters", [])) != 5:
        raise ValueError("Expected the five-part 10-14 minute pilot brief")
    return research


def start():
    _profile()
    research = validate_research(_json(SEED / "research_brief.json"))
    with closing(db.conn()) as c:
        existing = list(c.execute("SELECT id,payload FROM videos"))
    for row in existing:
        if json.loads(row["payload"] or "{}").get("topic", {}).get("pilot_key") == PILOT_KEY:
            return row["id"]
    if existing:
        raise RuntimeError("Ancestors DATA is not an empty pilot queue; no additional topic will start")
    topic = {"format": FORMAT, "style": "cartoon", "pilot_key": PILOT_KEY,
             "channel_id": CHANNEL_ID, "working_title": TITLE, "lang_target": "en"}
    vid = db.add("ancestors-ice-age-home", TITLE, {"topic": topic, "lang": "en",
                 "research": research, "research_sha256": _digest(research), "private_pilot_only": True})
    _save(db.video_dir(vid) / "research.json", research)
    db.update(vid, "anc_topic")
    return vid


def validate_video(vid):
    _profile()
    v = db.get(vid)
    t = v["payload"].get("topic", {})
    if (t.get("format"), t.get("pilot_key"), t.get("channel_id")) != (FORMAT, PILOT_KEY, CHANNEL_ID):
        raise ValueError("This lane may operate only on the authorized Ordinary Ancestors pilot")
    r = validate_research(v["payload"].get("research", {}))
    if _digest(r) != v["payload"].get("research_sha256"):
        raise ValueError("Research changed after pilot creation; review before production")
    return v


def _script_shape(s):
    if s.get("lang") != "en" or len(s.get("parts", [])) != 5 or len(s.get("names", [])) != 5:
        raise ValueError("Expected English script with five text parts and five chapter names")
    if any(not isinstance(t, str) or not t.strip() for t in s["parts"]):
        raise ValueError("Script has an empty part")
    count = sum(len(x.split()) for x in s["parts"])
    if not 1400 <= count <= 1950:
        raise ValueError(f"Pilot should run 10-14 minutes at 140 wpm; received {count} words")
    return s


def script(vid):
    v = validate_video(vid)
    d = db.video_dir(vid)
    research = v["payload"]["research"]
    draft_path = d / "script_draft.json"
    if draft_path.exists():
        draft = _json(draft_path)
    else:
        # Prepared from the verified brief by the research/editorial task.
        # Missing input is a resumable stop, never a fallback paid research loop.
        supplied = _script_shape(_json(SEED / "script.json"))
        draft = {"script": supplied, "checked_parts": [], "research_sha256": _digest(research)}
        _save(draft_path, draft)
    if draft["research_sha256"] != _digest(research):
        raise ValueError("Draft evidence fingerprint mismatch")
    s = draft["script"]
    for i in range(5):
        if i in draft["checked_parts"]:
            continue
        text = s["parts"][i]
        result = llm.ask_json(CHECK.format(research=json.dumps(research, ensure_ascii=False), text=text),
                              heavy=True, max_tokens=3000, tag=f"anc_factcheck_{vid}_{i+1}",
                              model=config.LLM_MODEL_FACTCHECK or None)
        if not isinstance(result.get("fixes"), list) or not isinstance(result.get("unresolved"), list):
            raise ValueError("Factcheck returned an incomplete verdict")
        _save(d / f"factcheck_{i+1}.json", result)
        if result["unresolved"]:
            raise RuntimeError("Unresolved historical claim: " + str(result["unresolved"])[:500])
        for fix in result["fixes"]:
            old, new = fix.get("old"), fix.get("new")
            if not isinstance(old, str) or not old or old not in text or not isinstance(new, str):
                raise ValueError("Factchecker replacement does not match the narration")
            text = text.replace(old, new)
        s["parts"][i] = text
        draft["checked_parts"].append(i)
        _save(draft_path, draft)
    _script_shape(s)
    # The first scene must label the invented evening before the audience can
    # mistake it for an observed event. Preserve this precise evidence boundary.
    opening = " ".join(s["parts"][0].split()[:60]).lower()
    if not any(word in opening for word in ("reconstruction", "imagined")) or "mezhyrich" not in " ".join(s["parts"][0].split()[:110]).lower():
        raise ValueError("Opening reconstruction disclosure is missing or too late")
    s.update({"lang": "en", "script": "\n\n".join(s["parts"]),
              "years": [research["historical_scope"]["public_date_label"]] * 5})
    config.write(d / "script.md", "# " + TITLE + "\n\n" + "\n\n".join(
        "## " + name + "\n\n" + text for name, text in zip(s["names"], s["parts"])))
    db.update(vid, "anc_scripted", payload={"script": s, "script_checked": True})


def _rules(research):
    return json.dumps({"scope": research["historical_scope"],
                       "invariants": research["visual_historical_invariants"],
                       "exclude": research["claims_to_exclude"]}, ensure_ascii=False)



def _board_fingerprint(research):
    return _digest([INK_FORMAT_VERSION, BOARD, config.CARTOON_STYLE, IMAGE_CONTEXT, _rules(research)])


def _voice_profile(d):
    profile = {"voice_id": os.environ.get("ELEVENLABS_VOICE_ID"),
               "mode": config.TTS_MODE, "target_wpm": config.TTS_TARGET_WPM,
               "tempo": config.TTS_TEMPO}
    mark = d / "anc_voice_profile.json"
    if mark.exists():
        if _json(mark) != profile:
            raise RuntimeError("Ancestors voice profile changed; archive old voice outputs/settings before resuming")
    elif any((d / name).exists() for name in ("voice.mp3", "voice.sha", "words.json", "voice_settings.json")):
        raise RuntimeError("Unversioned Ancestors voice cache exists; review before adopting this voice profile")
    _save(mark, profile)
    return profile


def _check_images(vid, d, shots, research):
    from . import es_cartoon, es_checks
    rules = _rules(research)
    model = config.LLM_MODEL_VISION
    def ask(batch):
        intents = [{"n": i, "narration": x["beat"], "intent": x["prompt"]} for i, x in enumerate(batch, 1)]
        return llm.ask_vision(QA.format(rules=rules, intents=json.dumps(intents, ensure_ascii=False)),
                              [es_cartoon._sheet([d / x["image"] for x in batch])],
                              tag=f"anc_visual_{vid}", model=model, max_tokens=2200)
    result = es_checks.run(d, shots, "anc_visual_qa", [QA, rules, model, INK_FORMAT_VERSION, config.CARTOON_STYLE], ask,
                           workers=2, batch_size=6)
    es_checks.require_complete(result, "Ordinary Ancestors visual integrity")
    return result


def assets(vid):
    from . import assets as A, es_cartoon, es_checks
    v = validate_video(vid)
    d = db.video_dir(vid)
    s, research = v["payload"]["script"], v["payload"]["research"]
    if not v["payload"].get("script_checked"):
        raise RuntimeError("Complete factual review before buying assets")
    board_path = d / "anc_board.json"
    visual_sha256 = _board_fingerprint(research)
    board = _json(board_path) if board_path.exists() else {"parts": [], "script_sha256": _digest(s),
            "format_version": INK_FORMAT_VERSION, "visual_sha256": visual_sha256}
    if board.get("visual_sha256") != visual_sha256 or board.get("format_version") != INK_FORMAT_VERSION:
        raise RuntimeError("Ancestors storyboard style changed; explicitly archive and migrate the reviewed cached board")
    if board["script_sha256"] != _digest(s):
        raise RuntimeError("Narration changed after storyboard; review cached assets first")
    for i in range(len(board["parts"]), 5):
        beats = es_cartoon._beats(s["parts"][i])
        ids = research["chapters"][i].get("facts", [])
        facts = [f for f in research["facts"] if f["id"] in ids]
        result = llm.ask_json(BOARD.format(rules=_rules(research), facts=json.dumps(facts, ensure_ascii=False),
                              beats="\n".join(f"{n}. {b}" for n, b in enumerate(beats, 1)), count=len(beats)),
                              heavy=True, max_tokens=9000, tag=f"anc_board_{vid}_{i+1}",
                              model=config.LLM_MODEL_SHOTS or None)
        rows = result.get("shots", [])
        got = {x.get("n"): x.get("prompt") for x in rows if isinstance(x, dict)}
        if (len(rows) != len(beats) or set(got) != set(range(1, len(beats)+1)) or
                any(not isinstance(p, str) or len(p.split()) < 15 for p in got.values())):
            raise ValueError("Storyboard must supply exactly one complete prompt per beat")
        board["parts"].append({"beats": beats, "prompts": [got[n] for n in range(1, len(beats)+1)]})
        _save(board_path, board)
    parts = [A.clean_text(text) for text in s["parts"]]
    voice_profile = _voice_profile(d)
    A._voice("\n\n".join(parts), d, parts)
    words = _json(d / "words.json")
    if not words or float(words[-1]["e"]) <= 0:
        raise ValueError("Voice alignment is empty")
    duration = round(float(words[-1]["e"]) + 1.5, 3)
    if not 600 <= duration <= 840:
        raise RuntimeError(f"Pilot audio is {duration/60:.1f} minutes, outside requested 10-14; review tempo before images")
    shots_path = d / "anc_shots.json"
    shots = _json(shots_path) if shots_path.exists() else [
        {"id": f"anc_p{i+1}_{k+1:03d}", "beat": beat, "prompt": prompt}
        for i, part in enumerate(board["parts"]) for k, (beat, prompt) in enumerate(zip(part["beats"], part["prompts"]))]
    def draw(x, repair=False):
        revision = x.get("asset_revision", "")
        if revision and (not isinstance(revision, str) or not revision.isalnum()):
            raise ValueError("Ancestors asset_revision must contain only letters and digits")
        sid = x["id"] + ("_" + revision if revision else "") + ("_repair" if repair else "")
        path = d / "images" / (sid + ".png")
        if not path.exists():
            prompt = x["prompt"] + ". " + IMAGE_CONTEXT
            if repair:
                prompt += ". Correct these visible mistakes: " + x.get("repair_reason", "")
            A._image(prompt, d, sid, config.IMAGE_MODEL, cartoon=True)
        # Never substitute the previous picture for a missing or corrupt image.
        from PIL import Image
        with Image.open(path) as im:
            im.verify()
        return "images/" + path.name
    todo = [x for x in shots if not x.get("image")]
    with ThreadPoolExecutor(6) as pool:
        for x, filename in zip(todo, pool.map(draw, todo)):
            x["image"] = filename
            _save(shots_path, shots)
    report = _check_images(vid, d, shots, research)
    bad = es_checks.failed_ids(report)
    reasons = {x["id"]: "; ".join(z["why"] for z in x["issues"]) for x in report["items"] if x["status"] == "FAIL"}
    redo = [x for x in shots if x["id"] in bad and not x.get("repaired")]
    for x in redo:
        x["repair_reason"] = reasons[x["id"]]
    with ThreadPoolExecutor(6) as pool:
        for x, filename in zip(redo, pool.map(lambda item: draw(item, True), redo)):
            x.update(image=filename, repaired=True)
            _save(shots_path, shots)
    report = _check_images(vid, d, shots, research)
    summary = {"status": report["status"], "counts": report["counts"]}
    db.update(vid, payload={"visual_qa": summary})
    if report["status"] != "PASS":
        db.update(vid, "anc_review", payload={"review_reason": "Material visual issues remain after the one bounded repair"})
        return
    starts = es_cartoon._times([x["beat"] for x in shots], words)
    if any(starts[i] >= starts[i+1] for i in range(len(starts)-1)) or starts[-1] >= duration:
        raise ValueError("Non-monotonic storyboard alignment; review before render")
    spec_shots = [{"start": t, "end": starts[i+1] if i+1 < len(starts) else duration,
                   "image": shots[i]["image"], "move": "static"}
                  for i, t in enumerate(starts)]
    part_starts, offset = [], 0
    for part in board["parts"]:
        part_starts.append(starts[offset])
        offset += len(part["beats"])
    _save(d / "anc_spec.json", {"duration": duration, "voice": "voice.mp3", "shots": spec_shots,
          "part_starts": part_starts, "format_version": INK_FORMAT_VERSION,
          "visual_sha256": visual_sha256, "voice_profile": voice_profile})
    db.update(vid, "anc_assets", payload={"anc_shots": len(shots), "duration": duration})


def _publication(d, v, spec):
    from PIL import Image
    publish = d / "publish"
    publish.mkdir(exist_ok=True)
    research, s = v["payload"]["research"], v["payload"]["script"]
    lines = [research["opening_disclosure"]["description_note"], "", "Chapters:"]
    for seconds, name in zip(spec["part_starts"], s["names"]):
        n = int(seconds)
        lines.append(f"{n//60:02d}:{n%60:02d} {name}")
    lines += ["", "Sources:"]
    for source in research["sources"]:
        lines.append(source["title"] + " — " + source["url"])
    lines += ["", "Original illustrated reconstruction by Ordinary Ancestors. AI-assisted illustrations and narration; source-based editorial research."]
    description = "\n".join(lines)
    if len(description) > 5000:
        raise ValueError("Description exceeds YouTube limit; shorten sources manually, do not truncate evidence")
    config.write(publish / "title.txt", TITLE)
    config.write(publish / "description.txt", description)
    # The pilot's own checked opening frame is the initial reviewable thumbnail.
    # No additional paid image or invented historical objects are introduced.
    with Image.open(d / spec["shots"][0]["image"]) as im:
        im.convert("RGB").resize((1280, 720)).save(publish / "thumbnail.jpg", quality=92)
    _save(publish / "metadata.json", {"channel_id": CHANNEL_ID, "title": TITLE, "language": "en",
                                     "privacy": "private", "automatic_upload": False})


def render(vid):
    from . import es_cartoon, sound
    from .qc import tech_check
    v = validate_video(vid)
    if v["payload"].get("visual_qa", {}).get("status") != "PASS":
        raise RuntimeError("Visual integrity must pass before rendering")
    d = db.video_dir(vid)
    spec = _json(d / "anc_spec.json")
    if spec.get("visual_sha256") != _board_fingerprint(v["payload"]["research"]):
        raise RuntimeError("Ancestors render spec does not match the current visual profile")
    if any(x.get("move") != "static" for x in spec["shots"]):
        raise RuntimeError("Ancestors ink profile requires static drawings and simple cuts")
    _publication(d, v, spec)
    inputs = {name: hashlib.sha256((d / name).read_bytes()).hexdigest()
              for name in {spec["voice"], *(x["image"] for x in spec["shots"])}}
    fingerprint = _digest([RENDER_VERSION, spec, inputs])
    receipt = d / "render_receipt.json"
    final = d / "final.mp4"
    cached = _json(receipt) if receipt.exists() else {}
    if not final.exists() or cached.get("fingerprint") != fingerprint:
        tmp = config.RENDER_TMP
        tmp.mkdir(parents=True, exist_ok=True)
        out, loud = tmp / (vid + ".mp4"), tmp / (vid + "_master.mp4")
        es_cartoon._ffmpeg_render(d, spec, out)
        sound.master(out, loud)
        loud.replace(out)
        shutil.move(str(out), str(final))
        _save(receipt, {"fingerprint": fingerprint, "state": "rendered"})
    tech = tech_check(final, {"duration": spec["duration"], "pauses": []})
    db.update(vid, "anc_review" if tech else "anc_ready", payload={"tech": tech, "lang": "en"})
    print(f"[ancestors] {'QC review required' if tech else 'Ready for owner review'}: {final}", flush=True)


NEXT = {"anc_topic": script, "anc_scripted": assets, "anc_assets": render}


def run_queue():
    _profile()
    # Importing here avoids an import cycle with main's CLI dispatch.
    from ..main import _execute
    with FileLock(config.DATA / ".pipeline_ancestors.lock", "ancestors"):
        for status, fn in NEXT.items():
            items = db.by_status(status)
            if not items:
                continue
            if len(items) != 1:
                raise RuntimeError("Only one pilot may be active")
            v = items[0]
            with video_lock(v["id"], status):
                if db.get(v["id"])["status"] == status:
                    _execute(fn, v["id"], status)
            return  # One stage; no autostart or replenishment.


def watch(every=60):
    _profile()
    if every < 5:
        raise ValueError("Watcher interval must be at least five seconds")
    failures = 0
    transient_budget_stops = 0
    with FileLock(config.DATA / ".pipeline_ancestors.lock", "watch-ancestors"):
        print("[ancestors] Watching the existing pilot only; no automatic upload or new topics", flush=True)
        while True:
            try:
                run_queue()
                failures = 0
                transient_budget_stops = 0
            except Exception as exc:
                from ..ancestors_budget import BudgetStop
                traceback.print_exc()
                failures += 1
                transient_budget = (isinstance(exc, BudgetStop) and
                                    "Shared ledger has unpriced requests" in str(exc))
                transient_budget_stops = transient_budget_stops + 1 if transient_budget else 0
                _save(config.DATA / "watch_ancestors_error.json", {"type": type(exc).__name__,
                      "message": str(exc)[:1200], "at": time.time(), "failures": failures,
                      "transient_budget_stops": transient_budget_stops})
                if transient_budget:
                    if transient_budget_stops >= 3:
                        print("[ancestors] Shared ledger remains unpriced after three consecutive stops; stopped for review", flush=True)
                        return
                    # run_queue and _execute have unwound before this wait;
                    # existing reservations and completed asset caches stay intact.
                    print(f"[ancestors] Shared ledger is awaiting prices; retrying the cached stage in 60s ({transient_budget_stops}/3)", flush=True)
                    time.sleep(60)
                    continue
                if isinstance(exc, BudgetStop) or failures >= 3:
                    print("[ancestors] Stopped for review; paid stages will not retry automatically", flush=True)
                    return
            time.sleep(max(every, 300 * failures))
