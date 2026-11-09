"""Испанский канал: посторонние знаменитости в кадре (владелец 13.10.2026: «это важно» — модель подрисовывала в толпу Эйнштейна,
Фриду Кало, Маска). Проверка глазами модели пачками по 12 с текстом каждого куска; найденное перерисовывается с явным запретом."""
import io, json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from .. import config, db, llm

ASK = """Это {n} рисунков для документального мультфильма о компании {company}. Под каждым номером — фраза диктора, к которой стоит рисунок:
{lines}

Найди рисунки, где нарисован УЗНАВАЕМЫЙ реальный знаменитый человек (учёный, артист, политик, предприниматель, спортсмен), которого НЕТ
в фразе под этим номером и нет среди героев истории: {allowed}. Обычные человечки с круглыми головами и безымянные люди — норма.
Верни JSON: {{"bad": [{{"n": 3, "who": "кто это похоже", "why": "кратко"}}]}} (пустой список, если посторонних знаменитостей нет)."""

NO_CELEBS = (", every person in the picture is either a simple round-headed figure or {allowed}; absolutely no other real famous people, "
             "no Einstein, no Frida Kahlo, no Elon Musk, no Bill Gates, no celebrities in the crowd")


def _sheet(paths: list[Path]) -> bytes:
    from PIL import Image, ImageDraw, ImageFont
    w, h, cols = 480, 270, 4; rows = (len(paths) + cols - 1) // cols
    sh = Image.new("RGB", (cols * w, rows * (h + 28)), "white"); dr = ImageDraw.Draw(sh); f = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 22)
    for i, p in enumerate(paths):
        x, y = (i % cols) * w, (i // cols) * (h + 28)
        sh.paste(Image.open(p).convert("RGB").resize((w, h)), (x, y + 28)); dr.text((x + 4, y + 2), str(i + 1), font=f, fill="black")
    buf = io.BytesIO(); sh.save(buf, "JPEG", quality=85); return buf.getvalue()


def _check(vid: str, d: Path, shots: list[dict], topic: dict) -> dict:
    from . import es_checks
    allowed = topic.get("people") or topic["company"]
    model = config.LLM_MODEL_VISION
    def ask(batch):
        lines = "\n".join(f"{n}. {x['beat']}" for n, x in enumerate(batch, 1))
        return llm.ask_vision(ASK.format(n=len(batch), company=topic["company"], lines=lines, allowed=allowed),
                              [_sheet([d / x["image"] for x in batch])], tag=f"es_celebs_{vid}", model=model)
    report = es_checks.run(d, shots, "es_celebrity_qa", [ASK, model, topic["company"], allowed, "sheet-480x270-v1"], ask)
    print(f"[celebs] {vid}: {report['status']} {report['counts']}", flush=True)
    es_checks.require_complete(report, "Посторонние знаменитости")
    return report


def scan(vid: str) -> list[dict]:
    """Кадры монтажа с посторонними знаменитостями: [{"image", "beat", "prompt", "who"}]."""
    d = db.video_dir(vid); v = db.get(vid); t = v["payload"]["topic"]
    board = json.loads(config.read(d / "es_board.json"))
    shots = [{"id": f"p{i + 1}_{k + 1:03d}", "beat": b, "prompt": pr} for i, bp in enumerate(board["parts"]) for k, (b, pr) in enumerate(zip(bp["beats"], bp["prompts"]))]
    spec = json.loads(config.read(d / "es_spec.json")); used = {s["image"] for s in spec["shots"]}
    by_img = {}
    for x in shots:
        for img in (f"images/{x['id']}{suffix}.png" for suffix in ("_c2", "_c1", "_c", "_r", "")):
            if img in used: by_img[img] = x; break
    selected = [{**x, "image": img} for img, x in by_img.items()]
    report = _check(vid, d, selected, t)
    verdicts = {item["id"]: item for item in report["items"]}
    found = [{**x, "who": verdicts[x["id"]]["issues"][0].get("who")}
             for x in selected if verdicts[x["id"]]["status"] == "FAIL"]
    print(f"[celebs] {vid}: проверено {len(selected)} кадров, посторонние знаменитости на {len(found)}: "
          + ", ".join(f"{b['id']} ({b.get('who')})" for b in found), flush=True)
    return found


def fix(vid: str, found: list[dict]) -> int:
    """Перерисовка найденного с запретом посторонних знаменитостей; в монтаже кадр заменяется на новый файл (_c.png)."""
    from . import assets as A
    d = db.video_dir(vid); t = db.get(vid)["payload"]["topic"]; allowed = t.get("people") or t["company"]
    spec_p = d / "es_spec.json"; spec = json.loads(config.read(spec_p))
    def redraw(b):
        sid = b["id"] + "_c"
        if (d / "images" / f"{sid}.png").exists(): return b["image"], f"images/{sid}.png"
        for _ in range(2):
            try: return b["image"], A._image(b["prompt"] + NO_CELEBS.format(allowed=f"caricatures of {allowed} when named"), d, sid, config.IMAGE_MODEL, cartoon=True)
            except Exception as e: print(f"[celebs] {sid}: {str(e)[:100]}", flush=True)
        return b["image"], None
    with ThreadPoolExecutor(12) as ex: pairs = dict(p for p in ex.map(redraw, found) if p[1])
    for s in spec["shots"]:
        if s["image"] in pairs: s["image"] = pairs[s["image"]]
    config.write(spec_p, json.dumps(spec, ensure_ascii=False, indent=1))
    print(f"[celebs] перерисовано {len(pairs)} из {len(found)}", flush=True)
    return len(pairs)


def clean(vid: str, shots: list[dict], rounds: int = 2) -> int:
    """Внутри сборки кадров (es_cartoon.assets): shots [{id, beat, prompt, image}] — до двух кругов «проверка → перерисовка» посторонних
    знаменитостей; в shots подставляются новые файлы. Возвращает, сколько кадров перерисовано."""
    from . import assets as A
    d = db.video_dir(vid); t = db.get(vid)["payload"]["topic"]; allowed = t.get("people") or t["company"]
    from . import es_checks
    total = 0; selected = [x for x in shots if x.get("image")]
    # The extra iteration only verifies the final replacements; it never buys
    # a third repair. Known residual FAIL stays report-only (owner 07.10).
    for rnd in range(rounds + 1):
        report = _check(vid, d, selected, t)
        verdicts = {item["id"]: item for item in report["items"]}
        failed = es_checks.failed_ids(report)
        found = [(x, verdicts[x["id"]]["issues"][0].get("who"))
                 for x in selected if x["id"] in failed]
        print(f"[celebs] круг {rnd + 1}: проверено {len(selected)}, посторонние знаменитости на {len(found)}: "
              + ", ".join(f"{x['id']} ({who})" for x, who in found[:20]), flush=True)
        if not found or rnd == rounds: break
        def redraw(item):
            x, _ = item; sid = f"{x['id']}_c{rnd + 1}"
            if (d / "images" / f"{sid}.png").exists():
                return x, f"images/{sid}.png"   # resume after UNKNOWN without another image purchase
            for _ in range(2):
                try: return x, A._image(x["prompt"] + NO_CELEBS.format(allowed=f"caricatures of {allowed} when named"), d, sid, config.IMAGE_MODEL, cartoon=True)
                except Exception as e: print(f"[celebs] {sid}: {str(e)[:100]}", flush=True)
            return x, None
        with ThreadPoolExecutor(12) as ex:
            for x, img in ex.map(redraw, found):
                if img: x["image"] = img; total += 1
    return total
