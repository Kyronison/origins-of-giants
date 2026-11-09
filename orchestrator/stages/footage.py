"""Отчёт по кадрам ролика (STRATEGY.md, раздел 11, согласовано 29.09.2026): доля настоящей съёмки, чужие видеоотрезки длиннее
потолка и кадры агентств. Считается по готовому таймлайну, ничего не меняет.

Настоящая съёмка — архивное видео и фото: ролики YouTube, Wikimedia Commons, фото из сети, хроника эпохи. Сток и генерация в неё
не входят. Если настоящей съёмки меньше REAL_MIN, ролик ждёт решения владельца (строка в отчёте проверки качества).
Чужой видеоотрезок на экране — не дольше FOREIGN_MAX секунд подряд: длинные сцены режет stages/fill.py, здесь — контроль."""
import re
from .. import config

FOREIGN_MAX = 10.0
REAL_MIN = 0.25
AGENCY = re.compile(r"getty|associated press|\bAP Photo|\bAP Images|reuters|shutterstock|alamy|fine ?art ?america|pixels\.com|photobucket|"
                    r"agence france|\bAFP\b|bloomberg", re.I)
STOCK = re.compile(r"pexels|pixabay|unsplash|coverr", re.I)
NAMES = {"archive": "архив", "foreign_video": "чужое видео", "stock": "сток", "generated": "генерация", "graphics": "графика"}


def foreign(x: dict) -> bool:
    """В сцене идёт чужой видеоотрезок (ролик YouTube), а не кадр из него."""
    return any(str(sl.get("credit") or "").startswith("YouTube:") and sl.get("src") for sl in (x.get("slots") or []))


def kind(sl: dict, has_slots: bool = True) -> str:
    c = str(sl.get("credit") or "").strip()
    if not has_slots and not (sl.get("src") or sl.get("image")): return "graphics"
    if not c: return "generated"
    if STOCK.search(c): return "stock"
    if c.startswith("YouTube:") and sl.get("src"): return "foreign_video"
    return "archive"


def report(tl: dict) -> dict:
    total = 0.0; sec = {k: 0.0 for k in NAMES}; long, agency = [], []
    for x in tl.get("scenes") or []:
        d = max(0.0, float(x.get("end") or 0) - float(x.get("start") or 0))
        if not d: continue
        total += d
        slots = x.get("slots") or []
        for sl in (slots or [x]):
            k = kind(sl, bool(slots)); sec[k] += d / max(1, len(slots))
            c = str(sl.get("credit") or "")
            if AGENCY.search(c): agency.append({"scene": x.get("id"), "credit": c[:80]})
        seen = d - (config.CHAPTER_GAP if x.get("transition") == "dip" else 0.0)   # первый кадр главы стоит под карточкой главы
        if foreign(x) and seen > FOREIGN_MAX + 0.5: long.append({"scene": x.get("id"), "sec": round(seen, 1), "at": round(float(x.get("start") or 0), 1)})
    total = total or 1.0
    share = {k: round(v / total, 3) for k, v in sec.items()}
    real = round(share["archive"] + share["foreign_video"], 3)
    return {"seconds": round(total, 1), "share": share, "real_share": real, "foreign_long": long, "agency": agency,
            "ok": real >= REAL_MIN and not long and not agency}


def line(r: dict) -> str:
    """Строка для отчёта проверки качества."""
    s = r["share"]; pct = lambda v: f"{v * 100:.0f}%"
    out = (f"Кадры: настоящая съёмка {pct(r['real_share'])} (из неё чужое видео {pct(s['foreign_video'])}), сток {pct(s['stock'])}, "
           f"генерация {pct(s['generated'])}, графика {pct(s['graphics'])}.")
    if r["real_share"] < REAL_MIN: out += f"\n⚠ Настоящей съёмки меньше {pct(REAL_MIN)} — по стратегии такой ролик ждёт вашего решения."
    if r["foreign_long"]:
        out += (f"\n⚠ Чужие видеоотрезки длиннее {FOREIGN_MAX:.0f} с: " +
                ", ".join(f"{x['scene']} ({x['sec']} с, на {int(x['at'] // 60)}:{int(x['at'] % 60):02d})" for x in r["foreign_long"][:6]))
    if r["agency"]: out += "\n⚠ Кадры агентств или магазинов постеров: " + ", ".join(f"{x['scene']} — {x['credit']}" for x in r["agency"][:6])
    return out
