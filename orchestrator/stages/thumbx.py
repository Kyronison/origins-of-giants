"""Три варианта обложки по исследованию ниши 26.09 (владелец: «из превью вообще не читается, про что это, надписи компании не видно»).

Что выигрывает у конкурентов и в открытых данных: компания узнаётся за секунду (логотип или продукт — главный объект, 30–50 %
ширины), не больше трёх элементов, 0–3 слова, одно число, яркая картинка. Старый шаблон (сплит, два числа, два года, стрелка,
маленький логотип) в ленте телефона не читался; CTR 1,0–1,3 % при норме YouTube 2–10 %.

Варианты (ThumbV.tsx, variant=bold):
  logohero — огромный логотип на белой панели над яркой сценой компании + 2–3 слова в жёлтой плашке (основной);
  bignum   — одно число из сценария высотой почти в полкадра + подпись, логотип, яркая сцена справа;
  phrase   — «было → стало» одной фразой на сцене эпохи, логотип в углу.
Два других — для Test & Compare в Studio (API YouTube его не умеет).
"""
import json, os, re, shutil, subprocess
from pathlib import Path
from .. import config, db, llm

PLAN = """You design YouTube thumbnail text for a long documentary on the channel Origins of Giants (how big companies really make money).
Company: {company}
Video title (the thumbnail must COMPLEMENT it, not repeat it): {title}
Thesis: {thesis}
Brief notes: {brief}
Script opening:
{opening}

Return JSON only:
{{"hero_text": "2-3 words, max 14 characters, UPPERCASE, a curiosity hook that is literally true for this video and does NOT repeat the title's numbers (e.g. YOU PAID THEM, THEY SAID NO, NOBODY NOTICED)",
 "big_number": "ONE number exactly as it appears in the script, max 5 characters, the most surprising one (e.g. 3%, $800, 14%)",
 "number_label": "max 16 characters, UPPERCASE, what the number is (e.g. FOR CLAIMS, MARKUP CAP)",
 "phrase_then": "max 10 characters, UPPERCASE, the humble start (e.g. 6 CLERKS, $800, 1 GARAGE)",
 "phrase_now": "max 7 characters, a dollar amount with $ that is the result (e.g. $7.5B, $300B) — never a bare count",
 "bg_now": "image prompt: bright, saturated, present-day scene that instantly signals this company's business (its typical storefront, product, place of use), sunny, vivid colors, wide shot, subject on the right half, no people's faces, no text, no logos, no signs",
 "bg_then": "image prompt: warm sepia scene of the company's humble start era, may include anonymous people with faces turned down or away, dramatic light, wide shot, no readable text"}}"""


def _nums(s: str) -> set[str]:
    return {re.sub(r"[^0-9.]", "", n).strip(".") for n in re.findall(r"\d[\d.,]*", s or "")} - {""}


def plan(vid: str, title: str) -> dict:
    """Тексты и фоны для трёх вариантов. Число — только из сценария; иначе правая цифра брифа."""
    from .thumbv import company_name
    v = db.get(vid); p = v["payload"]; t = p.get("topic") or {}; b = p.get("brief") or {}
    s = (p.get("script") or {}).get("script") or ""
    company = company_name(t)
    brief = {k: b.get(k) for k in ("thumb_then", "thumb_now", "thumb_units", "thumb_why", "opening_payoff", "viewer_question") if b.get(k)}
    q = PLAN.format(company=company, title=title, thesis=str(t.get("thesis") or "")[:500], brief=json.dumps(brief, ensure_ascii=False)[:900],
                    opening=re.sub(r"\[F\d+[^\]]*\]", "", s)[:2500])
    r = llm.ask_json(q, heavy=True, max_tokens=1500, tag=f"thumbx_{vid}", model=config.LLM_MODEL_WRITER or None)
    clip = lambda k, n: str(r.get(k) or "").strip()[:n]
    out = {"company": company, "hero_text": clip("hero_text", 16).upper(), "big_number": clip("big_number", 6),
           "number_label": clip("number_label", 18).upper(), "phrase_then": clip("phrase_then", 11).upper(),
           "phrase_now": clip("phrase_now", 8), "bg_now": clip("bg_now", 600), "bg_then": clip("bg_then", 600)}
    allowed = _nums(s) | _nums(title)
    if not (_nums(out["big_number"]) and _nums(out["big_number"]) <= allowed):   # число не из сценария — берём цифру брифа
        print(f"[thumbx] {vid}: число «{out['big_number']}» не найдено в сценарии — беру из брифа", flush=True)
        out["big_number"] = str(b.get("thumb_now") or "")[:6]
    if not (_nums(out["phrase_now"]) <= allowed): out["phrase_now"] = str(b.get("thumb_now") or out["phrase_now"])[:8]
    return out


def _logo_ready(d: Path, company: str, about: str) -> tuple[str, float, str] | None:
    """Проверенный логотип (thumbv._logo), без полей, не мельче 700 px по длинной стороне; путь, пропорции, фирменный цвет."""
    from PIL import Image
    from . import thumbv as T
    got = T._logo(company, d, about=about)
    if not got: return None
    f = got[0]
    im = Image.open(f)
    if max(im.size) < 700:   # логотипы из enwiki бывают по 300 px: на панели в треть кадра они мылятся
        try:
            from . import restore
            flat = f.with_name(f.stem + "_flat.png"); up = f.with_name(f.stem + "_up.png")
            bg = Image.new("RGBA", im.size, (255, 255, 255, 255)); Image.alpha_composite(bg, im.convert("RGBA")).convert("RGB").save(flat)
            restore.photo(flat, up, 1200)
            if up.exists(): shutil.copy(up, f); print(f"[thumbx] логотип увеличен: {im.size} → {Image.open(f).size}", flush=True)
        except Exception as e: print(f"[thumbx] апскейл логотипа не удался: {str(e)[:80]}", flush=True)
    color = T._brand_color(f) or "#0C3C6C"
    r, g, b_ = (int(color[i:i + 2], 16) for i in (1, 3, 5))
    if (0.299 * r + 0.587 * g + 0.114 * b_) / 255 > 0.55: color = "#0C2238"   # светлый фирменный цвет (жёлтый) — под жёлтой цифрой не годится
    return f.relative_to(d).as_posix(), T._aspect(f), color


def _gen(prompt: str, out: Path):
    if out.exists(): return
    import fal_client
    from . import assets as A
    m = config.THUMB_IMAGE_MODEL
    r = fal_client.subscribe(m, arguments=A.image_args(m, prompt, 1920, 1088, thumb=True))
    out.write_bytes(A._get(r["images"][0]["url"], timeout=180))


def make(vid: str, title: str | None = None, set_main: bool = False) -> dict:
    """Три варианта в thumbv/variants/First_*.jpg (2560×1440, ≤2 МБ) и лист для ленты. set_main — logohero становится основной обложкой."""
    from PIL import Image
    v = db.get(vid); d = db.video_dir(vid); t = v["payload"].get("topic") or {}
    title = title or v["title"] or ""
    work = d / "thumbv" / "variants"; work.mkdir(parents=True, exist_ok=True); (d / "images").mkdir(exist_ok=True); (d / "archive").mkdir(exist_ok=True)
    pl = plan(vid, title); config.write(work / "plan.json", json.dumps(pl, ensure_ascii=False, indent=1))
    logo = _logo_ready(d, pl["company"], str(t.get("thesis") or "")[:200])
    if not logo: print(f"[thumbx] {vid}: логотип {pl['company']} не найден — название шрифтом", flush=True)
    _gen(pl["bg_now"] + ", vivid saturated colors, bright daylight, no text, no logos, no signs, no readable letters", d / "images" / "thumbx_now.png")
    _gen(pl["bg_then"] + ", warm sepia documentary photograph, no readable text", d / "images" / "thumbx_then.png")
    pub = config.RENDER_TMP / f"thumbx_{vid[:40]}"; shutil.rmtree(pub, ignore_errors=True); (pub / "images").mkdir(parents=True); (pub / "archive").mkdir()
    for f in ("images/thumbx_now.png", "images/thumbx_then.png"): shutil.copy(d / f, pub / f)
    base = {"variant": "bold", "brandColor": "#0C3C6C"}
    if logo:
        shutil.copy(d / logo[0], pub / logo[0]); base.update({"logo": logo[0], "logoAspect": logo[1], "brandColor": logo[2]})
    else: base["brandWord"] = pl["company"].upper()
    V = {"logohero": {"kind": "logohero", "bg": "images/thumbx_now.png", "text1": pl["hero_text"]},
         "bignum": {"kind": "bignum", "bg": "images/thumbx_now.png", "hook": pl["big_number"], "text1": pl["number_label"]},
         "phrase": {"kind": "phrase", "bg": "images/thumbx_then.png", "text1": pl["phrase_then"], "text2": pl["phrase_now"]}}
    files = []
    for name, pr in V.items():
        pf = work / f"props_{name}.json"; config.write(pf, json.dumps({**base, **pr}, ensure_ascii=False)); files.append(str(pf))
    tmp = config.RENDER_TMP / "remotion"; tmp.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "THUMB_SCALE": "2", "TEMP": str(tmp), "TMP": str(tmp)}
    try:
        r = subprocess.run([shutil.which("node") or "node", "scripts/thumbs.mjs", str(pub), files[0], str(work), *files],
                           cwd=config.REMOTION, capture_output=True, text=True, errors="replace", env=env, timeout=900)
    finally: shutil.rmtree(pub, ignore_errors=True)
    if r.returncode: raise RuntimeError("рендер вариантов: " + (r.stderr or r.stdout)[-500:])
    short = re.sub(r"[^A-Za-z0-9]+", "_", pl["company"]).strip("_")[:30] or "video"
    out = {}
    for name in V:
        im = Image.open(work / f"thumb_{name}.png").convert("RGB").resize((2560, 1440), Image.LANCZOS)
        jpg = work / f"{short}_{name}.jpg"
        for q in (95, 90, 85, 80):
            im.save(jpg, "JPEG", quality=q, optimize=True)
            if jpg.stat().st_size <= 2 * 1024 * 1024: break
        out[name] = jpg
    tiles = [Image.open(work / f"thumb_{n}.png").convert("RGB").resize((246, 138), Image.LANCZOS) for n in V]
    sheet = Image.new("RGB", (246 * 3 + 40, 158), "white")
    for i, tl in enumerate(tiles): sheet.paste(tl, (10 + i * 256, 10))
    sheet.save(work / "compare_feed.png")
    if set_main:
        from . import thumbcheck
        for f in ("thumb_a.png", "thumb_2560.png"):
            if (d / f).exists() and not (d / f.replace(".png", "_oldtemplate.png")).exists(): shutil.copy(d / f, d / f.replace(".png", "_oldtemplate.png"))
        im = Image.open(work / "thumb_logohero.png").convert("RGB").resize((2560, 1440), Image.LANCZOS)
        im.save(d / "thumb_2560.png"); im.resize((1280, 720), Image.LANCZOS).save(d / "thumb_a.png")
        (d / "thumb_a.keep").write_text("variant logohero (thumbx)", encoding="utf-8")
        thumbcheck.prepare(d)
    db.update(vid, payload={"thumbx": {**pl, "files": {k: str(p) for k, p in out.items()}, "logo": bool(logo)}})
    print(f"[thumbx] {vid}: {pl['company']} | «{pl['hero_text']}» | {pl['big_number']} {pl['number_label']} | {pl['phrase_then']} → {pl['phrase_now']}", flush=True)
    return {"plan": pl, "files": out, "sheet": work / "compare_feed.png"}
