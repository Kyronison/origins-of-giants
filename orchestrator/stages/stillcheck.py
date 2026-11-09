"""Проверка СОБРАННОГО КАДРА до рендера (владелец 22.09: «проверки должны быть до того, как ты поставил на рендер»).

Preflight смотрит на файлы слотов, guard — на подписи и тайминги; но композицию целиком — цитату, карточки людей, титры, субтитры,
цифры — до этого никто не видел до готового final.mp4, и брак стоил по 35–60 минут рендера (McDonald's: цитата под чужим лицом,
пустой текст цитаты; Netflix es: голое «51», субтитры по 7 слов). Теперь до рендера собираются 8–12 кадров-проб из самой композиции
(scripts/stills.mjs, один бандл), их смотрит модель зрения, и рендер начинается только если блокеров нет."""
import json, os, re, shutil, subprocess
from pathlib import Path
from .. import config, llm

PROMPT = """Это кадр из документального ролика, собранный автоматически ДО рендера. Найди брак композиции, а не содержания:
- текст обрезан краем кадра или плашкой, налезает на другой текст или на лицо;
- пустая карточка/плашка (рамка без фото, кавычки без текста, подпись без имени), placeholder;
- слово в кадре на другом языке, чем субтитры/подписи (ролик на {lang}); служебные слова вроде QUOTE/FILE, если язык не английский;
- число без единицы измерения и контекста («51», «20») крупно на экране (число с $ или M/B/% — норма);
- абракадабра/псевдотекст на сгенерированных предметах, вывесках, документах — только warn (это исходный кадр, не композиция);
- лицо на карточке обрезано сверху, или под двумя разными именами одно и то же лицо;
- субтитры длиннее двух строк или оборваны посреди слова.
Норма, не брак: цитата печатается по буквам синхронно с голосом (курсор и незаконченный текст допустимы); крупное число с мелкой единицей под ним (PERCENT, DOLLARS); размытый фон под карточкой главы; цитата-фрагмент со строчной буквы; вшитые субтитры показывают кусок фразы до 6 слов — кусок без точки в конце (следующие слова появятся дальше) это норма, брак только если слово оборвано посреди букв.
Верни JSON: {{"issues": [{{"severity": "block|warn", "what": "одна фраза"}}], "ok": true|false}} — ok=false только при block."""


def _pick(tl: dict, n_extra: int = 3) -> list[float]:
    """Секунды для проб: каждая цитата, первые две people-сцены, первая пара, первая-вторая цифра, первая карточка главы, + случайные broll."""
    fps = config.FPS if hasattr(config, "FPS") else 30
    ts = []
    sc = tl.get("scenes") or []; ov = tl.get("overlays") or []
    for s in [x for x in sc if x.get("type") == "quote"][:3]: ts.append(max(s["start"] + 1.0, s["end"] - 0.7))   # текст набран полностью (Costco 23.09: проба посреди набора = ложный блокер)
    for s in [x for x in sc if x.get("type") == "people"][:2]: ts.append(s["start"] + min(3.0, (s["end"] - s["start"]) * 0.5))
    for o in [x for x in ov if x.get("type") == "pair"][:1]: ts.append(o["start"] + 2.2)
    for o in [x for x in ov if x.get("type") == "flash"][:2]: ts.append(o["start"] + 2.0)   # после отсчёта числа (1.5 с), не «14» по пути к «15»
    for o in [x for x in ov if x.get("type") == "chapter"][:1]: ts.append(o["start"] + 1.5)
    dur = float(tl.get("duration") or 60)
    for k in range(n_extra): ts.append(dur * (0.15 + 0.3 * k))
    return sorted({round(t, 2) for t in ts if 0 <= t < dur})


def SOFT() -> str:
    """Сбой самой проверки: block только в строгом режиме (STRICT_GATES=1), иначе warn — как до 02.10 (владелец 07.10)."""
    return "block" if config.STRICT_GATES else "warn"

def run(d: Path, tl: dict, words: list[dict], lang: str = "en") -> dict:
    fps = 30
    times = _pick(tl)
    if not times: raise ValueError("Нет кадров для проверки композиции")
    work = d / "stillcheck"; shutil.rmtree(work, ignore_errors=True); work.mkdir()
    pf = work / "props.json"; config.write(pf, json.dumps({"timeline": tl, "words": words}, ensure_ascii=False))
    tmp = config.RENDER_TMP / "remotion"; tmp.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "TEMP": str(tmp), "TMP": str(tmp)}
    frames = [str(int(t * fps)) for t in times]
    import time as _t
    from ..public_media import public_view
    with public_view(d, {"timeline": tl, "words": words}, config.RENDER_TMP) as public:
        for attempt in range(3):   # шрифты Google через VPN иногда не грузятся (ERR_SSL_VERSION_OR_CIPHER_MISMATCH) — повтор, а не брак
            before = set(tmp.glob("remotion-webpack-bundle-*"))
            try:
                r = subprocess.run([shutil.which("node") or "node", "scripts/stills.mjs", str(public), str(pf), str(work), *frames],
                                   cwd=config.REMOTION, capture_output=True, text=True, errors="replace", env=env, timeout=1500)
            finally:
                for p in set(tmp.glob("remotion-webpack-bundle-*")) - before:
                    if p.resolve().parent != tmp.resolve(): raise RuntimeError("Unsafe bundle cleanup target")
                    shutil.rmtree(p, ignore_errors=True)
            if r.returncode == 0: break
            print(f"[stillcheck] попытка {attempt + 1}: {(r.stderr or r.stdout or '')[-160:]}", flush=True); _t.sleep(30)
    if r.returncode: raise RuntimeError("кадры-пробы не собрались: " + (r.stderr or r.stdout or "")[-500:])
    lang_name = {"en": "английском", "es": "испанском"}.get(lang, lang)
    issues, sheet = [], []
    for t, f in zip(times, frames):
        png = work / f"still_{f}.png"
        if not png.exists(): issues.append({"severity": "block", "what": f"кадр {t:.0f} с не собрался"}); continue
        try:
            res = llm.ask_vision(PROMPT.format(lang=lang_name), [png.read_bytes()], tag="stillcheck", model=config.LLM_MODEL_VISION)
        except Exception as e:
            issues.append({"severity": SOFT(), "what": f"{t:.0f} с: проверка не прошла ({str(e)[:60]})"}); continue
        if not isinstance(res, dict) or type(res.get("ok")) is not bool or not isinstance(res.get("issues"), list):
            issues.append({"severity": SOFT(), "what": f"{t:.0f} с: неполный ответ проверки"}); continue
        if any(not isinstance(i, dict) or i.get("severity") not in ("block", "warn") or not i.get("what") for i in res["issues"]):
            issues.append({"severity": SOFT(), "what": f"{t:.0f} с: некорректные замечания проверки"}); continue
        if res["ok"] is False and not any(isinstance(i, dict) and i.get("severity") == "block" for i in res["issues"]):
            issues.append({"severity": SOFT(), "what": f"{t:.0f} с: проверка отклонила кадр без объяснения"})
        for i in res.get("issues") or []:
            if isinstance(i, dict) and i.get("what"): issues.append({"severity": i.get("severity") or "warn", "what": f"{t:.0f} с: {i['what']}"})
        sheet.append(png)
    blocks = [i for i in issues if i["severity"] == "block"]
    out = {"ok": not blocks, "frames": len(times), "issues": issues}
    config.write(work / "result.json", json.dumps(out, ensure_ascii=False, indent=1))
    print(f"[stillcheck] кадров {len(times)}, блокеров {len(blocks)}, замечаний {len(issues) - len(blocks)}"
          + ("".join(f"\n  BLOCK {b['what']}" for b in blocks)) + ("".join(f"\n  warn {w['what']}" for w in issues if w['severity'] != 'block')[:1500]), flush=True)
    return out
