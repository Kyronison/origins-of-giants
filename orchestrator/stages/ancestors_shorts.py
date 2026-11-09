"""Ordinary Ancestors: шортс-тизер к выпуску (16.10.2026 владелец: «к нему же нужен шортс»). Как у испанского канала (es_shorts.py):
отрывок 40–58 с голосом из выпуска, те же сцены перерисованы вертикально (cast_for из ancestors_ep), заголовок первые 3 с,
субтитры по словам; монтаж — es_shorts._render. Файлы — <выпуск>/shorts/. Загрузка — отдельной командой (upload)."""
import json
from concurrent.futures import ThreadPoolExecutor
from .. import config, db, llm
from . import ancestors_ep as E, es_shorts as S

PICK = """English YouTube documentary about everyday life in the Ice Age: "{title}". Below are narration sentences with start-end
seconds. Choose ONE continuous excerpt for YouTube Shorts lasting 40-58 seconds that works with no context: it opens with a hook
(a surprising find, a vivid image, a sharp contrast with the viewer's life) and ends on a payoff or a sharp question; avoid the first
20 seconds of the video. Also write:
- line1, line2: on-screen title in CAPITALS, each line at most 18 characters; line2 is the twist;
- title: Shorts title, at most 70 characters, only what the excerpt says;
- hook: one sentence (max 120 characters) for the description.
Return JSON {{"first": 12, "last": 20, "line1": "...", "line2": "...", "title": "...", "hook": "...", "why": "коротко по-русски"}}
{lines}"""

VERT = (", tall vertical portrait 9:16 composition, the scene stacked from top to bottom, main subject in the middle third of the frame, "
        "leave the top quarter calm and simple")


def build(vid):
    E._profile(); E._cast_style()
    from . import assets as A
    v = db.get(vid); E.set_episode(v["payload"].get("episode") or {}); d = db.video_dir(vid); sd = d / "shorts"; sd.mkdir(exist_ok=True); pf = sd / "plan.json"
    if pf.exists(): plan = json.loads(pf.read_text(encoding="utf-8"))
    else:
        words = json.loads((d / "words.json").read_text(encoding="utf-8")); sents = S._sentences(words)
        lines = "\n".join(f"{i}. [{s['s']:.1f}-{s['e']:.1f}] {s['t']}" for i, s in enumerate(sents))
        for _ in range(3):
            r = llm.ask_json(PICK.format(title=v["title"], lines=lines), heavy=True, max_tokens=8000, tag=f"anc_short_pick_{vid}")
            a, b = int(r["first"]), int(r["last"])
            if not 0 <= a < len(sents): continue
            b = min(max(a, b), len(sents) - 1)
            while sents[b]["e"] - sents[a]["s"] < 40 and b + 1 < len(sents): b += 1
            while sents[b]["e"] - sents[a]["s"] > 58 and b > a: b -= 1
            if 38 <= sents[b]["e"] - sents[a]["s"] <= 62: break
        else: raise ValueError("отрывок для шортса не подобран")
        t0, t1 = sents[a]["s"] - 0.1, sents[b]["e"] + 0.25
        spec = json.loads((d / "ae_spec.json").read_text(encoding="utf-8"))
        prompts = {x["image"]: x["prompt"] for x in json.loads((d / "ae_shots.json").read_text(encoding="utf-8"))}
        shots = [dict(s, prompt=prompts[s["image"]], move="in") for s in spec["shots"] if s["end"] > t0 + 0.3 and s["start"] < t1]
        sw = [w for w in words if w["s"] >= t0]
        for s in shots:   # карточки-надписи в шортсе дублируют заголовок и субтитры — вместо них сцена по словам диктора
            low = s["prompt"].lower()
            if "white background" in low and ("hand-lettered" in low or "lettering" in low):
                said = " ".join(w["w"] for w in sw if s["start"] <= w["s"] < s["end"])
                s["prompt"] = (f"One simple flat-coloured scene with {E.HERO} that shows what the narrator says: "
                               f"\"{said}\". No lettering at all.")
        plan = {"t0": t0, "t1": t1, "line1": r["line1"].upper(), "line2": r["line2"].upper(), "title": r["title"], "hook": r["hook"],
                "why": r.get("why", ""), "shots": shots, "text": " ".join(s["t"] for s in sents[a:b + 1])}
        pf.write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")

    def draw(i):
        s = plan["shots"][i]; sid = f"v{i:02d}" + (f"_r{s['rev']}" if s.get("rev") else ""); f = sd / f"{sid}.png"
        if not f.exists():
            p = A._image(s["prompt"] + VERT + ". " + E.cast_for(s["prompt"]), sd, sid, config.IMAGE_MODEL, w=1024, h=1824, cartoon=True)
            (sd / p).replace(f)
        s["vimage"] = f.name
    with ThreadPoolExecutor(8) as ex: list(ex.map(draw, range(len(plan["shots"]))))
    pf.write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
    S._render(d, sd, plan, sd / "short.mp4")
    kit = {"title": (plan["title"][:90] + " #shorts")[:100],
           "description": f"{plan['hook']} #shorts\n\nFull documentary on this channel:\n{v['title']}\n"
                          + (f"https://www.youtube.com/watch?v={v['youtube_id']}\n" if v.get("youtube_id") else "") + "\n#Shorts",
           "seconds": round(plan["t1"] - plan["t0"], 1), "line1": plan["line1"], "line2": plan["line2"], "why": plan["why"]}
    (sd / "studio.json").write_text(json.dumps(kit, ensure_ascii=False, indent=1), encoding="utf-8")
    db.update(vid, payload={"short": {"status": "rendered", "title": kit["title"], "seconds": kit["seconds"]}})
    print(f"[ancestors-short] собран {sd / 'short.mp4'} ({kit['seconds']} с) — {kit['title']}", flush=True)
