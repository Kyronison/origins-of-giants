"""Основная обложка роликов. Макет задаёт серия (STRATEGY.md; с 08.10.2026 у всех серий один макет — «плакат», раздел 0):

  poster  («плакат», с 08.10 — весь канал) — тёплая иллюстрация: вымышленный человек эпохи бренда слева, узнаваемая вещь бренда
                        и табличка конца справа внизу; настоящий знак бренда крупно справа сверху, под ним строка формулы названия
                        (— THE RISE AND FALL —). Знак и строка ставятся здесь, в PIL, а не генератором. Образец владельца — Spirit,
                        work/strategy-v2-thumbs/thumb_poster.jpg.

  object  («предмет-герой», серия A) — одна вещь, по которой бренд узнают все, крупно и в том состоянии, о котором ролик;
                        заголовок в две строки слева сверху, логотип-наклейка справа сверху.
  iceberg («айсберг», серия B и темы вне серий) — над водой то, что все видят, под водой — на чём деньги на самом деле;
                        белая бирка у надводной части, жёлтая плашка у подводной, логотип-наклейка сверху слева.
  illus   (тест)     — редакционная иллюстрация для Test & Compare. По умолчанию НЕ делается: тест имеет смысл, когда ролик
                        набрал 3 500 показов за неделю. Запуск вручную: make(vid, illus=True, force=True).

Обложка собирается ОДИН раз (владелец 28.09: «не нужно каждый перерендер делать новые превью»): повторный вызов возвращает
готовую и ничего не генерирует. Пересобрать — только force=True. Обложку владельца (.keep не от конвейера) не трогаем никогда.

Правила текста: обещание — механизм или поворот, а не рост компании; 1–4 слова, дополняет название и не повторяет его; число —
только из сценария; никаких «SCAM/BANKRUPT/DEAD» без оснований; без серверных, без лиц реальных людей, без надписей от генератора.
Тема-категория (no_logo) идёт без логотипа."""
import json, os, re, shutil, subprocess
from pathlib import Path
from .. import config, db, llm, series

HEAD = """You design a YouTube thumbnail for a 20-24 minute documentary on the channel Origins of Giants
(the channel tells what really happened to brands Americans know by name, and what their real business was).
Brand / subject: {company}
Video title (the thumbnail must COMPLEMENT it and must not repeat it): {title}
Thesis: {thesis}
Brief notes: {brief}
Script opening:
{opening}
"""

PLAN = {
 "iceberg": HEAD + """
Main thumbnail = ICEBERG: split view above/below the waterline. Above the water floats a small, instantly recognizable thing everyone
associates with this brand (its product or the service people see). Below the water, huge, is what the business really earns on
(for McDonald's: a burger above, a big block of land with a restaurant building below; for Verisign: a laptop above, a vault of coins behind
a toll gate below). Two labels: "top" names the visible thing, "bottom" names the hidden money.
Test thumbnail = ILLUSTRATION: a bold editorial comic illustration of the same hidden mechanism as one vivid scene, plus a 2-3 word caption.

Rules:
- top: 1-2 words, max 12 characters, UPPERCASE (e.g. BURGERS, YOUR .COM, WINDSHIELDS).
- bottom: 1-3 words, max 14 characters, UPPERCASE, what the money really is (e.g. REAL ESTATE, THEIR TOLL, THE SYRUP).
- illus_text: 2-3 words, max 18 characters, UPPERCASE; you may split two parts with "|" (second part is highlighted), e.g. "THE REAL|PRODUCT".
{common}
Return JSON only:
{{"why": "one sentence: the promise this thumbnail makes", "top": "...", "bottom": "...", "above": "small object floating above the water",
 "below": "the huge hidden thing under the water", "illus_scene": "...", "illus_text": "..."}}""",
 "poster": HEAD + """
Main thumbnail = WARM ILLUSTRATED POSTER, one fixed template for the whole channel (like a museum poster of the brand's era):
- LEFT THIRD: chest-up portrait of ONE FICTIONAL person tied to the brand in its best years — an employee in the brand's uniform or a
  typical customer of that era — looking straight at the viewer with a quiet, telling expression. Never a real, named person.
- CENTER and RIGHT: the place where people met this brand (a store front, an airport gate, a restaurant counter, a bus terminal), in the
  state that tells THIS story (closing day, dusk, empty, dust).
- FOREGROUND RIGHT: ONE object every American associates with this brand (a product, a uniform item, a cup, a toy, a bag, a ticket),
  large and detailed.
- A hand-written paper sign or shop placard in the scene with sign_text (the end of the story: FINAL FLIGHT, CLOSED, LAST DAY, STORE CLOSING).
- UPPER RIGHT QUARTER: calm plain sky or plain wall, nothing in it: the real logo and a caption are added there by the pipeline.

Rules:
- sign_text: 1-3 words, max 14 characters, UPPERCASE, literally true for this story (if the brand still exists, no CLOSED-type words;
  use what really ended, and only if the script supports it).
- accent: one brand color in plain English for small accents (e.g. "mustard yellow", "royal blue", "fire-engine red").
{common}
Return JSON only:
{{"why": "one sentence: the promise this thumbnail makes", "person": "the fictional person: role, age, era clothing in brand colors, expression",
 "setting": "the place and time of day, one sentence", "object": "the hero object and its state, one sentence", "sign_text": "...",
 "accent": "...", "illus_scene": "...", "illus_text": "..."}}""",
 "object": HEAD + """
Main thumbnail = HERO OBJECT IN CLOSE-UP: ONE physical thing that every American associates with this brand, seen close in a
three-quarter front view, very large, filling the right two thirds of the frame from edge to edge, in the state that tells THIS story
(for Greyhound: a silver intercity coach, headlights on, at the curb of a shuttered downtown bus terminal at dusk, wet asphalt;
for Pan Am: the nose and front of a white 1970s jumbo jet on an empty apron, covered engines, weeds in the concrete).
The upper left third is calm empty sky or plain wall: the headline "WHAT HAPPENED / TO [BRAND]?" goes there and is fixed for the series.
Test thumbnail = ILLUSTRATION: a bold editorial comic illustration of the same turn of the story as one vivid scene, plus a 2-3 word caption.

Rules:
- text: return "" — the headline is fixed for the series and is added by the pipeline.
- illus_text: 2-3 words, max 18 characters, UPPERCASE; you may split two parts with "|".
{common}
Return JSON only:
{{"why": "one sentence: the promise this thumbnail makes", "text": "LINE ONE|LINE TWO", "object_scene": "the hero object and the place, one sentence",
 "illus_scene": "...", "illus_text": "..."}}"""}

COMMON = """- Everything literally true for this video. A number only if it is in the script. No SCAM / BANKRUPT / DEAD / FRAUD unless the script says so.
  No false either/or ("NOT BURGERS") unless the script plainly says so.
- Every scene field is an image-generation description in English of OBJECTS and places only. No real people, no faces of real people,
  no server rooms or data centers. All surfaces blank: no text, no letters, no numbers, no logos, no signs, no liveries with names."""

POSTER_COMMON = """- Everything literally true for this video. A number only if it is in the script. No SCAM / BANKRUPT / DEAD / FRAUD unless the script says so.
- Scene fields are image-generation descriptions in English. The person is fictional and anonymous: no real people, no lookalikes.
  No logos, brand names or text anywhere except sign_text; uniforms, shop fronts and aircraft carry colors only, no names."""

BAN = re.compile(r"\b(scam|bankrupt|dead|fraud|evil|destroyed)\b", re.I)
SERVER = re.compile(r"\b(server|servers|data ?cent(er|re)s?|rack|racks)\b", re.I)
BLANK = ", all surfaces blank, no text, no letters, no numbers, no logos, no signs, no real people"
ICEBERG = ("split view above and below the waterline of a calm ocean: above the water floats {above} on a tiny ice floe, "
           "below the water, visible through clear blue water, {below}, like the hidden part of an iceberg, dramatic underwater light, "
           "photorealistic, wide shot, empty sky in the top corners" + BLANK)
OBJECT = ("photorealistic documentary photograph, close three-quarter front view, dramatic low evening light: {scene}. The subject is the hero, "
          "very large, filling the right two thirds of the frame from edge to edge; the upper left third is calm empty sky or plain wall, "
          "saturated colors, sharp detail, reflections on wet ground" + BLANK)
# 29.09 владелец выбрал макет серии A на образце Greyhound (вариант C): надпись одна на всю серию, бренд — словом, потому что знак без
# названия узнают не все. Длинное имя уменьшает шрифт в ThumbV, а не переносится.
SERIES_A_TEXT = "WHAT HAPPENED|TO {brand}?"
POSTER = ("Vintage editorial illustration for a documentary poster, painterly realism, warm faded sepia palette with {accent} accents, "
          "subtle paper texture, high detail, strong separation of subjects, 16:9. Left third: chest-up portrait of {person}, a fictional "
          "person, looking straight at the viewer. Center and right: {setting}. Foreground right: {object}, large and detailed, with a "
          "hand-written paper sign that reads exactly '{sign}'. The upper right quarter is calm plain sky or plain wall with nothing in it. "
          "No other text, letters, numbers, logos or brand names anywhere; uniforms, shop fronts and vehicles carry colors only.")
ILLUS = "bold editorial comic illustration, thick outlines, vivid flat colors, dramatic lighting: {scene}" + BLANK
LIMITS = {"iceberg": {"top": (1, 2, 12), "bottom": (1, 3, 14)}, "object": {}, "poster": {"sign_text": (1, 3, 14)}}   # 29.09: надпись серии A задана, модель её не пишет
SCENES = {"iceberg": ("above", "below"), "object": ("object_scene",), "poster": ("person", "setting", "object")}
FIELDS = ("why", "top", "bottom", "above", "below", "text", "object_scene", "person", "setting", "object", "sign_text", "accent",
          "illus_scene", "illus_text")


def _nums(s: str) -> set[str]:
    return {re.sub(r"[^0-9.]", "", n).strip(".") for n in re.findall(r"\d[\d.,]*", s or "")} - {""}


def _problems(pl: dict, script: str, kind: str = "iceberg", illus: bool = True, brand: str = "") -> list[str]:
    bad = []
    lim = dict(LIMITS[kind])
    if illus: lim["illus_text"] = (2, 3, 18)
    for k, (lo, hi, n) in lim.items():
        t = pl.get(k, ""); words = [w for w in re.split(r"[\s|]+", t) if w]
        if not (lo <= len(words) <= hi): bad.append(f"{k}: {len(words)} words, need {lo}-{hi}")
        if len(t.replace("|", "")) > n: bad.append(f"{k}: longer than {n} characters")
        if _nums(t) - _nums(script): bad.append(f"{k}: number {sorted(_nums(t) - _nums(script))} is not in the script")
        m = BAN.search(t)
        if m and not re.search(rf"\b{m.group(0)}\b", script, re.I): bad.append(f"{k}: «{m.group(0)}» is not supported by the script")
    if kind == "object":
        pass
    for k in SCENES[kind] + (("illus_scene",) if illus else ()):
        if not pl.get(k): bad.append(f"{k} is empty")
        if SERVER.search(pl.get(k, "")): bad.append(f"{k}: no server rooms or data centers")
    return bad


def plan(vid: str, title: str, kind: str = "iceberg", illus: bool = True) -> dict:
    from .thumbv import company_name
    v = db.get(vid); p = v["payload"]; t = p.get("topic") or {}; b = p.get("brief") or {}
    s = (p.get("script") or {}).get("script") or ""
    company = company_name(t)
    brief = {k: b.get(k) for k in ("thesis", "viewer_question", "opening_payoff", "thumb_why") if b.get(k)}
    q = PLAN[kind].format(company=company, title=title, thesis=str(t.get("thesis") or b.get("thesis") or "")[:700],
                          brief=json.dumps(brief, ensure_ascii=False)[:1500], opening=re.sub(r"\[F\d+[^\]]*\]", "", s)[:2500],
                          common=POSTER_COMMON if kind == "poster" else COMMON)
    note, bad = "", []
    for attempt in range(3):
        r = llm.ask_json(q + note, heavy=True, max_tokens=2000, tag=f"thumbrec_{vid}", model=config.LLM_MODEL_WRITER or None)
        pl = {k: str(r.get(k) or "").strip() for k in FIELDS}
        for k in ("top", "bottom", "text", "illus_text", "sign_text"): pl[k] = pl[k].upper()
        if kind == "object": pl["text"] = SERIES_A_TEXT.format(brand=(series.brand(t) or company).upper())
        if kind == "poster": pl["text"] = series.caption(t); pl["accent"] = pl["accent"] or "warm brand"
        bad = _problems(pl, s + " " + title, kind, illus, series.brand(t))
        if not bad: return {**pl, "company": company, "kind": kind}
        print(f"[thumbrec] {vid}: план не прошёл ({'; '.join(bad)}) — повтор", flush=True)
        note = "\n\nYour previous answer broke these rules, fix them:\n- " + "\n- ".join(bad) + f"\nPrevious answer: {json.dumps(pl, ensure_ascii=False)}"
    raise RuntimeError("план обложки не прошёл проверку: " + "; ".join(bad))


def _cutout(d, logo):
    """Логотип на белой подложке → на прозрачной (владелец 27.09: «лого на фоне белого прямоугольника ужасно смотрятся»).
    Заливка идёт от краёв по почти белым пикселям: белое внутри знака, обведённое контуром, остаётся. Подложки нет — логотип как есть."""
    from PIL import Image, ImageDraw
    if not logo: return logo
    src = d / logo[0]
    im = Image.open(src).convert("RGBA"); w, h = im.size
    flat = Image.alpha_composite(Image.new("RGBA", im.size, (255, 255, 255, 255)), im).convert("RGB")
    edge = [(x, y) for x in range(0, w, 4) for y in (0, h - 1)] + [(x, y) for y in range(0, h, 4) for x in (0, w - 1)]
    solid = [xy for xy in edge if im.getpixel(xy)[3] > 200 and min(flat.getpixel(xy)) > 235]
    if len(solid) < len(edge) * 0.5: return logo
    mark = (255, 0, 255)
    for xy in solid[::8]:
        if flat.getpixel(xy) != mark: ImageDraw.floodfill(flat, xy, mark, thresh=40)
    out = im.copy(); po = out.load(); pf = flat.load(); n = 0
    for y in range(h):
        for x in range(w):
            if pf[x, y] == mark: po[x, y] = (255, 255, 255, 0); n += 1
    box = out.getbbox()
    if not box or n > w * h * 0.95: return logo   # вырезалось всё — знак сам белый, оставляем как есть
    out = out.crop(box); dst = src.with_name(src.stem + "_cut.png"); out.save(dst)
    print(f"[thumbrec] логотип: белая подложка убрана ({n / (w * h):.0%} кадра), {out.size[0]}x{out.size[1]}", flush=True)
    return dst.relative_to(d).as_posix(), round(out.size[0] / out.size[1], 3), logo[2]


def _label(pl: dict) -> dict:
    """Поля для сообщения в Telegram и для thumbcheck (первое слово text должно читаться в ленте)."""
    kind = pl.get("kind") or "iceberg"
    text = (pl.get("text", "").replace("|", " ") if kind == "object" else
            f"{pl.get('text', '')} / {pl.get('sign_text', '')}" if kind == "poster" else f"{pl.get('top', '')} / {pl.get('bottom', '')}")
    return {"template": series.THUMB_RU.get(kind, kind), "text": text, "text_alt": pl.get("illus_text", "").replace("|", " ")}


def ready(vid: str) -> dict | None:
    """Уже собранная обложка этого ролика или None. Макет должен совпадать с макетом серии."""
    d = db.video_dir(vid); work = d / "thumbv" / "rec"
    t = db.get(vid)["payload"].get("topic") or {}
    try: pl = json.loads(config.read(work / "plan.json"))
    except Exception: return None
    if not (work / "thumb_main.jpg").exists() or (pl.get("kind") or "iceberg") != (series.thumb_kind(t) or "iceberg"): return None
    files = {"main": work / "thumb_main.jpg"}
    if (work / "thumb_alt.jpg").exists(): files["alt"] = work / "thumb_alt.jpg"
    return {"plan": {**pl, **_label(pl)}, "files": files, "sheet": work / "sheet.jpg", "fresh": False}


def compose_poster(scene, logo, caption: str, out, name: str = "", W: int = 2560, H: int = 1440):
    """Плакат: сцена генератора + настоящий знак справа сверху + строка формулы под ним (образец владельца 08.10 — Spirit).
    Знак встаёт в верхнюю правую четверть, которую генератор оставляет пустой. Если знак сливается с фоном — светлая или тёмная
    плашка. Темы без знака (nologo) — имя бренда крупным шрифтом с засечками."""
    from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageStat, ImageFilter
    im = ImageOps.fit(Image.open(scene).convert("RGB"), (W, H), Image.LANCZOS).convert("RGBA")
    cx, top, maxw, maxh = int(W * 0.775), int(H * 0.06), int(W * 0.37), int(H * 0.19)
    region = im.crop((int(W * 0.58), int(H * 0.03), int(W * 0.97), int(H * 0.36))).convert("L")
    bg_l = ImageStat.Stat(region).mean[0] / 255
    font = lambda n, size: ImageFont.truetype(f"C:/Windows/Fonts/{n}", size)
    if logo and Path(logo).exists():
        lg = Image.open(logo).convert("RGBA")
        k = min(maxw / lg.width, maxh / lg.height); lg = lg.resize((max(1, round(lg.width * k)), max(1, round(lg.height * k))), Image.LANCZOS)
        a = lg.split()[-1]; lum = ImageStat.Stat(lg.convert("L"), a).mean[0] / 255 if a.getbbox() else 0.5
    else:   # без знака — имя бренда
        f = font("georgiab.ttf", 150); txt = (name or "").upper() or "?"
        while ImageDraw.Draw(im).textlength(txt, font=f) > maxw and f.size > 60: f = font("georgiab.ttf", f.size - 6)
        bb = ImageDraw.Draw(im).textbbox((0, 0), txt, font=f)
        lg = Image.new("RGBA", (bb[2] - bb[0] + 8, bb[3] - bb[1] + 8), (0, 0, 0, 0))
        dark = bg_l > 0.5; ImageDraw.Draw(lg).text((4 - bb[0], 4 - bb[1]), txt, font=f, fill=(33, 26, 20, 255) if dark else (246, 238, 222, 255))
        lum = 0.1 if dark else 0.95
    x = cx - lg.width // 2; y = top
    # 11.10 владелец: «what happened не видно» — строка формулы крупным жирным шрифтом на тёмной полосе под знаком (выбор владельца)
    fc = font("georgiab.ttf", int(H * 0.062)); txt = (caption or "").upper(); dr = ImageDraw.Draw(im)
    tw = dr.textlength(txt, font=fc) if txt else 0; tb = dr.textbbox((0, 0), txt or "X", font=fc); th = tb[3] - tb[1]
    pad = (int(W * 0.018), int(H * 0.022)); plate_w = max(lg.width, int(tw)) + 2 * pad[0]
    box = (cx - plate_w // 2, y - pad[1], cx + plate_w // 2, y + lg.height + pad[1])
    if abs(lum - bg_l) < 0.35:   # знак сливается с фоном — плашка противоположной яркости, со скруглением и мягкой тенью
        fill = (246, 238, 222, 245) if lum < 0.5 else (32, 26, 22, 235)
        sh = Image.new("RGBA", im.size, (0, 0, 0, 0)); ImageDraw.Draw(sh).rounded_rectangle((box[0], box[1] + 8, box[2], box[3] + 8), 24, fill=(0, 0, 0, 110))
        im = Image.alpha_composite(im, sh.filter(ImageFilter.GaussianBlur(10)))
        ImageDraw.Draw(im).rounded_rectangle(box, 22, fill=fill)
    im.alpha_composite(lg, (x, y))
    if txt:
        rb = (box[0], box[3] + int(H * 0.012), box[2], box[3] + int(H * 0.012) + th + 2 * int(H * 0.02))
        band = Image.new("RGBA", im.size, (0, 0, 0, 0)); ImageDraw.Draw(band).rounded_rectangle(rb, 18, fill=(28, 22, 18, 225))
        im = Image.alpha_composite(im, band)
        ImageDraw.Draw(im).text((cx - tw / 2, rb[1] + int(H * 0.02) - tb[1]), txt, font=fc, fill=(250, 236, 200, 255))
    im.convert("RGB").save(out)
    return out


def make(vid: str, title: str | None = None, set_main: bool = True, force: bool = False, illus: bool | None = None, relayout: bool = False) -> dict:
    """Основная обложка по макету серии; illus=True — ещё и иллюстрация для Test & Compare. Собирается один раз (force — пересобрать)."""
    from PIL import Image
    from . import thumbx as X, thumbcheck
    if not force and not relayout:
        got = ready(vid)
        if got: print(f"[thumbrec] {vid}: обложка уже собрана ({got['plan']['template']}: «{got['plan']['text']}») — не пересобираю", flush=True); return got
    illus = config.THUMB_ILLUS if illus is None else illus
    v = db.get(vid); d = db.video_dir(vid); t = v["payload"].get("topic") or {}; b = v["payload"].get("brief") or {}
    title = title or b.get("title_promise") or v["title"] or ""
    kind = series.thumb_kind(t) or "iceberg"; ser = series.of(t) or {}
    work = d / "thumbv" / "rec"; work.mkdir(parents=True, exist_ok=True); (d / "images").mkdir(exist_ok=True); (d / "archive").mkdir(exist_ok=True)
    old = None
    if relayout:   # тот же план и тот же фон, меняется только вёрстка (логотип, шрифт): без новой генерации
        try: old = json.loads(config.read(work / "plan.json"))
        except Exception: old = None
        if old and (old.get("kind") or "iceberg") != kind: old = None
    pl = old or plan(vid, title, kind, illus); config.write(work / "plan.json", json.dumps(pl, ensure_ascii=False, indent=1))
    logo = None if ser.get("no_logo") else _cutout(d, X._logo_ready(d, pl["company"], str(t.get("thesis") or "")[:200]))
    if not logo and not ser.get("no_logo"): print(f"[thumbrec] {vid}: логотип {pl['company']} не найден — обложка без него", flush=True)
    if kind == "poster":
        main_prompt = POSTER.format(accent=pl.get("accent") or "warm brand", person=pl["person"], setting=pl["setting"],
                                    object=pl["object"], sign=pl["sign_text"])
        illus = False   # тест-иллюстрация плакату не нужна: он сам иллюстрация
    else:
        main_prompt = OBJECT.format(scene=pl["object_scene"]) if kind == "object" else ICEBERG.format(above=pl["above"], below=pl["below"])
    imgs = {"main": (d / "images" / f"thumbrec_{kind}.png", main_prompt)}
    if illus: imgs["alt"] = (d / "images" / "thumbrec_illus.png", ILLUS.format(scene=pl["illus_scene"]))
    for f, prompt in imgs.values():
        if f.exists() and not old: f.unlink()
        X._gen(prompt, f)   # готовый файл _gen не перегенерирует
    if kind == "poster":   # плакат собирается в PIL: сцена генератора + настоящий знак + строка формулы
        compose_poster(imgs["main"][0], d / logo[0] if logo else None, pl["text"], work / "thumb_main.png", name=series.brand(t) or pl["company"])
        return _finish(vid, d, work, pl, {"main": None}, kind, set_main, logo)
    pub = config.RENDER_TMP / f"thumbrec_{vid[:40]}"; shutil.rmtree(pub, ignore_errors=True); (pub / "images").mkdir(parents=True); (pub / "archive").mkdir()
    for f, _ in imgs.values(): shutil.copy(f, pub / "images" / f.name)
    base = {"variant": "bold", "brandColor": logo[2] if logo else "#1B3A5C"}
    if logo: shutil.copy(d / logo[0], pub / logo[0]); base.update({"logo": logo[0], "logoAspect": logo[1]})
    bg = "images/" + imgs["main"][0].name
    V = {"main": ({**base, "kind": "object", "bg": bg, "text1": pl["text"], "logoSticker": True} if kind == "object" else
                  {**base, "kind": "iceberg", "bg": bg, "text1": pl["top"], "text2": pl["bottom"]})}
    if illus: V["alt"] = {**base, "kind": "illus", "bg": "images/thumbrec_illus.png", "text1": pl["illus_text"]}
    files = []
    for name, pr in V.items():
        pf = work / f"props_{name}.json"; config.write(pf, json.dumps(pr, ensure_ascii=False)); files.append(str(pf))
    for old in ("thumb_alt.png", "thumb_alt.jpg"):
        if not illus: (work / old).unlink(missing_ok=True)
    tmp = config.RENDER_TMP / "remotion"; tmp.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "THUMB_SCALE": "2", "TEMP": str(tmp), "TMP": str(tmp)}
    try:
        r = subprocess.run([shutil.which("node") or "node", "scripts/thumbs.mjs", str(pub), files[0], str(work), *files],
                           cwd=config.REMOTION, capture_output=True, text=True, errors="replace", env=env, timeout=900)
    finally: shutil.rmtree(pub, ignore_errors=True)
    if r.returncode: raise RuntimeError("рендер обложки: " + (r.stderr or r.stdout)[-500:])
    return _finish(vid, d, work, pl, V, kind, set_main, logo)


def _finish(vid, d, work, pl, V, kind, set_main, logo) -> dict:
    """Общий хвост сборки: jpg под лимит YouTube, лист для Telegram, установка основной обложки."""
    from PIL import Image
    from . import thumbcheck
    out = {}
    for name in V:
        im = Image.open(work / f"thumb_{name}.png").convert("RGB").resize((2560, 1440), Image.LANCZOS)
        jpg = work / f"thumb_{name}.jpg"
        for q in (95, 90, 85, 80):
            im.save(jpg, "JPEG", quality=q, optimize=True)
            if jpg.stat().st_size <= 2 * 1024 * 1024: break
        out[name] = jpg
    n = len(V)
    sheet = Image.new("RGB", (n * 640 + 10 * (n + 1), 360 + 20 + 98 + 30), "white")   # лист для Telegram: крупно и в размере ленты телефона
    for i, name in enumerate(V):
        im = Image.open(work / f"thumb_{name}.png").convert("RGB")
        sheet.paste(im.resize((640, 360), Image.LANCZOS), (10 + i * 650, 10)); sheet.paste(im.resize((175, 98), Image.LANCZOS), (10 + i * 185, 390))
    sheet.save(work / "sheet.jpg", quality=88)
    lab = _label(pl)
    owners = [k for k in d.glob("thumb_*.keep") if not k.read_text(encoding="utf-8", errors="replace").startswith(("thumbv", "thumbrec"))]
    if not set_main:
        print(f"[thumbrec] пробный прогон — основная обложка не тронута: {out['main']}", flush=True)
    elif owners:
        print(f"[thumbrec] обложка владельца ({owners[0].name}) не тронута; вариант конвейера — {out['main']}", flush=True)
    else:
        for f in ("thumb_a.png", "thumb_2560.png"):   # прежняя остаётся рядом на случай отката
            if (d / f).exists() and not (d / f"{Path(f).stem}_gen.png").exists(): shutil.copy(d / f, d / f"{Path(f).stem}_gen.png")
        im = Image.open(work / "thumb_main.png").convert("RGB").resize((2560, 1440), Image.LANCZOS)
        im.save(d / "thumb_2560.png"); im.resize((1280, 720), Image.LANCZOS).save(d / "thumb_a.png")
        (d / "thumb_a.keep").write_text(f"thumbrec {kind} {lab['text']}", encoding="utf-8")
        try: thumbcheck.prepare(d)
        except Exception as e: print(f"[thumbrec] подготовка превью для загрузки: {str(e)[:120]}", flush=True)
    pl.update(lab)
    if set_main: db.update(vid, payload={"thumbrec": {**pl, "files": {k: str(p) for k, p in out.items()}, "logo": bool(logo)}})
    print(f"[thumbrec] {vid}: {lab['template']} «{lab['text']}»" + (f", тест-иллюстрация «{pl['illus_text']}»" if "alt" in V else "") + f" | {pl['why']}", flush=True)
    return {"plan": pl, "files": out, "sheet": work / "sheet.jpg", "fresh": True}
