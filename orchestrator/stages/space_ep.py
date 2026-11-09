"""Absurd Scale (космос, 23.10.2026): выпуск от утверждённого сценария до готового файла.

Очередь sp_*: start (проверки чисел и расчётов, сценарий уже утверждён владельцем) → sp_scripted → voice → sp_voiced →
build (раскадровка storyboard.json привязывается к таймингам голоса, размеры тел берутся из space_physics, снимки из библиотеки,
иллюстрации gpt-image) → sp_built → sheet (кадр каждой сцены на просмотр ДО рендера) → sp_sheet → render → sp_ready.
Загрузки здесь нет (work/space-channel/upload_ep.py по «да» владельца). Только в профиле space (orchestrator/space_profile.py).
Выпуск — work/space-channel/episodes/<slug>/: episode.json, facts.json, script.md, storyboard.json."""
import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from .. import config, db
from . import space_physics as P

FORMAT = "space_v1"
EP_ROOT = config.ROOT / "work/space-channel/episodes"
LIB = Path("E:/SpaceChannel/data/library")
TARGET_WPM = 150
END_CARD = 4.0
AI_STYLE = (". Cinematic but restrained science illustration, dark space background, soft realistic light, no text, no letters, "
            "no labels, no logos, no watermark, no people's faces")


def _profile():
    if os.getenv("CHANNEL_PROFILE") != "space":
        raise RuntimeError("Use the isolated space profile")


def _json(p): return json.loads(Path(p).read_text(encoding="utf-8-sig"))


def _save(p, v):
    p = Path(p); p.parent.mkdir(parents=True, exist_ok=True); tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(v, ensure_ascii=False, indent=1), encoding="utf-8"); tmp.replace(p)


def parse_script(md):
    title, names, parts = None, [], []
    for line in md.splitlines():
        if line.startswith("# ") and title is None: title = line[2:].strip()
        elif line.startswith("## "): names.append(line[3:].strip()); parts.append([])
        elif names: parts[-1].append(line)
    parts = ["\n\n".join(p.strip() for p in re.split(r"\n\s*\n", "\n".join(x)) if p.strip()) for x in parts]
    return title, names, parts


def checks(slug):
    """Числа сценария и расчёты — до озвучки. Ошибка останавливает выпуск (это техническая проверка фактов, не брак кадров)."""
    ep = EP_ROOT / slug
    facts = _json(ep / "facts.json")["facts"]
    text = (ep / "script.md").read_text(encoding="utf-8")
    bad = [f"расчёт: {e}" for e in P.check_calcs(facts)] + [f"число без факта: {n}" for n in P.check_script(text, facts)]
    nosrc = [f["id"] for f in facts if not str(f.get("source_url", "")).startswith("http")]
    bad += [f"факт без источника: {i}" for i in nosrc]
    return bad


def start(slug):
    _profile()
    bad = checks(slug)
    if bad: raise ValueError("; ".join(bad))
    ep = EP_ROOT / slug
    title, names, parts = parse_script((ep / "script.md").read_text(encoding="utf-8"))
    for v in db.by_status("sp_scripted") + db.by_status("sp_voiced") + db.by_status("sp_built") + db.by_status("sp_sheet") + db.by_status("sp_ready"):
        if v["payload"].get("slug") == slug: return v["id"]
    meta = _json(ep / "episode.json")
    s = {"names": names, "parts": parts, "sha": hashlib.sha256(json.dumps(parts).encode()).hexdigest()}
    vid = db.add("space-" + slug, title, {"format": FORMAT, "slug": slug, "episode": meta, "script": s, "lang": "en",
                                          "script_approved": meta.get("approved")})
    db.update(vid, "sp_scripted")
    return vid


def _ep(vid):
    _profile(); v = db.get(vid)
    if v["payload"].get("format") != FORMAT: raise ValueError("not a space episode")
    return v, EP_ROOT / v["payload"]["slug"], db.video_dir(vid)


def voice(vid):
    from . import assets as A
    v, ep, d = _ep(vid); s = v["payload"]["script"]
    now = parse_script((ep / "script.md").read_text(encoding="utf-8"))[2]
    if hashlib.sha256(json.dumps(now).encode()).hexdigest() != s["sha"]: raise RuntimeError("script.md изменён после утверждения")
    config.TTS_TARGET_WPM = TARGET_WPM
    A._voice("\n\n".join(A.clean_text(t) for t in s["parts"]), d, [A.clean_text(t) for t in s["parts"]])
    w = _json(d / "words.json")
    db.update(vid, "sp_voiced", payload={"voice_seconds": round(w[-1]["e"], 2)})


# ---------- раскадровка ----------
def _tok(s):
    return re.findall(r"[a-z0-9]+", s.lower().replace("’", "'").replace("'", ""))


def _anchors(words, anchors):
    """Время начала каждой фразы-якоря; поиск строго вперёд по словам озвучки."""
    flat = []
    for i, w in enumerate(words):
        for t in _tok(w["w"]): flat.append((t, i))
    toks = [t for t, _ in flat]; pos, out = 0, []
    for a in anchors:
        q = _tok(a)
        for j in range(pos, len(toks) - len(q) + 1):
            if toks[j:j + len(q)] == q:
                out.append(words[flat[j][1]]["s"]); pos = j + len(q); break
        else:
            raise ValueError(f"якорь не найден после позиции {pos}: «{a}»")
    return out


def _body(ref):
    if isinstance(ref, str): ref = {"key": ref}
    if ref["key"].startswith("bh:"):   # чёрная дыра: радиус горизонта из массы
        h = P.BLACK_HOLES[ref["key"][3:]]
        b = {"name": h["name"], "r": P.schwarzschild_km(h["m_sun"]) / P.R_SUN_KM, "color": "#000", "kind": "bh"}
        b.update({k: v for k, v in ref.items() if k != "key"}); return b
    s = P.STARS[ref["key"]]
    b = {"name": s["name"], "r": s["r_sun"], "color": s["color"], "kind": "planet" if ref["key"] in ("earth", "jupiter") else "star",
         "fuzzy": s["r_sun"] > 300}
    b.update({k: v for k, v in ref.items() if k != "key"})
    return b


def _orbits(data):
    st = data.pop("star")
    if st == "bh":
        r_to = P.schwarzschild_km(data.pop("m_sun")) / P.AU_KM; color, kind = "#000", "bh"
    else:
        s = P.STARS[st]; r_to = s["r_sun"] * P.R_SUN_KM / P.AU_KM; color, kind = s["color"], "star"
        data.setdefault("fuzzy", s["r_sun"] > 300)
    names = data.pop("planets")
    return {**data, "color": data.get("color", color), "kind": kind, "r_from_au": data.get("r_from_au", P.R_SUN_KM / P.AU_KM), "r_to_au": r_to,
            "orbits": [{"name": n, "a": P.ORBITS_AU[n], "highlight": n == "Earth"} for n in names]}


def _photo(d, sid, data, fal_cost):
    from PIL import Image
    pub = d / "public" / "img"; pub.mkdir(parents=True, exist_ok=True)
    if "lib" in data:
        meta = _json(LIB / "library.json")[data["lib"]]
        out = pub / (data["lib"] + ".jpg")
        if not out.exists():
            im = Image.open(LIB / meta["file"]).convert("RGB"); im.thumbnail((2600, 2600), Image.LANCZOS); im.save(out, quality=90)
        return {**{k: v for k, v in data.items() if k != "lib"}, "src": "img/" + out.name}, "Image: " + meta["credit"]
    out = pub / (sid + ".png")
    if not out.exists():
        import fal_client
        from .assets import image_args, _get
        model = config.IMAGE_MODEL
        r = fal_client.subscribe(model, arguments=image_args(model, data["prompt"] + AI_STYLE, 1920, 1080))
        out.write_bytes(_get(r["images"][0]["url"], timeout=120)); fal_cost["images"] = fal_cost.get("images", 0) + 1
    return {**{k: v for k, v in data.items() if k != "prompt"}, "src": "img/" + out.name}, "Illustration (AI-generated), not a real image"


def build(vid):
    v, ep, d = _ep(vid); s = v["payload"]["script"]
    words = _json(d / "words.json"); board = _json(ep / "storyboard.json")
    starts = _anchors(words, [x["at"] for x in board["shots"]])
    if any(b <= a for a, b in zip(starts, starts[1:])): raise ValueError("якоря идут не по порядку")
    # главы: время первого слова каждой части
    part_starts = _anchors(words, [" ".join(p.split()[:6]) for p in s["parts"]])
    duration = round(words[-1]["e"] + END_CARD, 2)
    shots, fal_cost = [], {}
    for i, x in enumerate(board["shots"]):
        t0 = 0.0 if i == 0 else starts[i]
        t1 = starts[i + 1] if i + 1 < len(starts) else words[-1]["e"] + 0.6
        data = json.loads(json.dumps(x.get("data", {})))
        typ, source = x["type"], x.get("source")
        if typ == "compare": data["bodies"] = [_body(b) for b in data["bodies"]]
        elif typ == "orbits": data = _orbits(data)
        elif typ == "photo":
            data, credit = _photo(d, f"sp_{i + 1:03d}", data, fal_cost); source = source or credit
        ch = max(k for k, ps in enumerate(part_starts) if ps <= starts[i] + 0.01) if i else 0
        kicker = None if typ == "card" and data.get("chapter") else f"{ch + 1:02d} · {s['names'][ch]}"
        shots.append({"id": f"sp_{i + 1:03d}", "type": typ, "start": round(t0, 3), "end": round(t1, 3), "data": data,
                      "tag": x.get("tag"), "source": source, "kicker": x.get("kicker", kicker)})
    shots.append({"id": "sp_end", "type": "card", "start": round(words[-1]["e"] + 0.6, 3), "end": duration, "tag": None, "source": None, "kicker": None,
                  "data": {"text": "ABSURD SCALE", "sub": board.get("end_sub", "The universe, measured honestly"), "color": "#FFB547"}})
    long = [f"{x['id']} {x['end'] - x['start']:.1f} с" for x in shots if x["end"] - x["start"] > 16]
    pub = d / "public"; pub.mkdir(exist_ok=True); shutil.copy2(d / "voice.mp3", pub / "voice.mp3")
    shutil.copytree(LIB / "fonts", pub / "fonts", dirs_exist_ok=True)   # шрифты локально: рендер не ходит в сеть
    spec = {"duration": duration, "voice": "voice.mp3", "music": None, "shots": shots, "title": v["title"]}
    _save(d / "space_spec.json", spec)
    db.update(vid, "sp_built", payload={"shots": len(shots), "duration": duration, "long_shots": long, "part_starts": part_starts,
                                        "ai_images": fal_cost.get("images", 0)})
    print(f"[space] раскадровка: {len(shots)} кадров, {duration / 60:.1f} мин; длинные (>16 с): {long or 'нет'}", flush=True)


# ---------- Remotion ----------
def _remotion(cmd, comp, out, props, public, extra=()):
    # своя временная папка на каждый выпуск: уборка бандла одного процесса не должна задевать параллельный рендер другого (23.10 так упал рендер)
    tmp = Path(os.environ.get("RENDER_TMP", "E:/SpaceChannel/data/render_tmp")) / "remotion" / Path(public).parent.name; tmp.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "TEMP": str(tmp), "TMP": str(tmp)}
    before = set(tmp.glob("remotion-webpack-bundle-*"))
    try:
        subprocess.run([config.npx(), "remotion", cmd, "src/space/index.ts", comp, str(out), "--props", str(props), "--public-dir", str(public), *extra],
                       cwd=config.REMOTION, check=True, env=env)
    finally:
        for p in set(tmp.glob("remotion-webpack-bundle-*")) - before:
            shutil.rmtree(p, ignore_errors=True)


def sheet(vid):
    """По кадру каждой сцены (на 80% её длины) + листы по 12 — смотреть глазами до рендера."""
    from PIL import Image, ImageDraw
    v, ep, d = _ep(vid); spec = _json(d / "space_spec.json")
    props = d / "props_sheet.json"; _save(props, {"spec": spec})
    out = d / "sheet"; shutil.rmtree(out, ignore_errors=True); out.mkdir()
    _remotion("render", "SpaceSheet", out, props, d / "public", ["--sequence", "--image-format=jpeg", "--scale=0.5"])
    frames = sorted(out.glob("*.jp*g"))
    if len(frames) != len(spec["shots"]): raise RuntimeError(f"лист: {len(frames)} кадров из {len(spec['shots'])}")
    sheets = []
    for k in range(0, len(frames), 12):
        page = Image.new("RGB", (3 * 640, 4 * 380), "#000"); dr = ImageDraw.Draw(page)
        for j, f in enumerate(frames[k:k + 12]):
            x, y = (j % 3) * 640, (j // 3) * 380
            page.paste(Image.open(f).resize((640, 360)), (x, y))
            sh = spec["shots"][k + j]
            dr.text((x + 6, y + 362), f"{sh['id']} {sh['start']:.0f}s {sh['type']}", fill="#ffb547")
        p = d / f"sheet_{k // 12 + 1:02d}.jpg"; page.save(p, quality=85); sheets.append(str(p))
    db.update(vid, "sp_sheet", payload={"sheets": sheets})
    print("[space] листы кадров:", *sheets, sep="\n  ", flush=True)


def render(vid):
    from . import sound
    from .qc import tech_check
    v, ep, d = _ep(vid); spec = _json(d / "space_spec.json")
    props = d / "props_render.json"; _save(props, {"spec": spec})
    tmp = Path(config.RENDER_TMP); tmp.mkdir(parents=True, exist_ok=True)
    out, loud = tmp / (vid + ".mp4"), tmp / (vid + "_master.mp4")
    _remotion("render", "Space", out, props, d / "public", ["--crf=18", "--concurrency=6"])
    sound.master(out, loud); loud.replace(out)
    publish_texts(vid)
    shutil.move(str(out), str(d / "final.mp4"))
    tech = tech_check(d / "final.mp4", {"duration": spec["duration"], "pauses": []})
    db.update(vid, "sp_ready", payload={"tech": tech})
    print(f"[space] готово: {d / 'final.mp4'} ({spec['duration'] / 60:.1f} мин); техпроверка: {'; '.join(tech) or 'чисто'}", flush=True)


def publish_texts(vid):
    """Описание в стиле Origins of Giants (владелец 24.10: «без источников, изображений и т. д.»): два абзаца-крючка, «In this video:»,
    CHAPTERS, строка канала, хэштеги. Тексты — episode.json["description"]; источники остаются в facts.json и на экране."""
    v, ep, d = _ep(vid); s = v["payload"]["script"]
    meta = _json(ep / "episode.json"); desc = meta["description"]
    pub = d / "publish"; pub.mkdir(exist_ok=True)
    names = desc.get("chapters") or s["names"]
    chapters = [f"{int(sec) // 60}:{int(sec) % 60:02d} {name}" for sec, name in zip([0.0] + v["payload"]["part_starts"][1:], names)]
    text = "\n\n".join(desc["paragraphs"] + ["In this video: " + desc["in_this_video"], "CHAPTERS\n" + "\n".join(chapters),
                                               "Absurd Scale explains the most extreme objects in the universe, drawn to real scale. Subscribe for the next one.",
                                               desc["hashtags"]])
    config.write(pub / "title.txt", meta.get("youtube_title") or v["title"])
    config.write(pub / "description.txt", text[:4900])
    config.write(pub / "tags.txt", ", ".join(meta.get("tags", [])))


NEXT = {"sp_scripted": voice, "sp_voiced": build, "sp_built": sheet}
