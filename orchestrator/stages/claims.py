"""Реестр утверждений и повторная проверка того, что изменилось после правок (разбор Astra 20.09).

Фактчек проверяет свежий текст, но после него текст ещё правят: редактор склеивает фразы, автор переписывает вступление,
вычитка убирает обороты. Числа при этом «переезжают» — и проверенными они быть перестают.
Здесь: реестр фактов ресёрча с выдержками и датами → числа, появившиеся или изменившиеся после правок → сверка только их.
Дёшево: один вызов на ролик, и только если изменения есть."""
import json, re
from .. import config, llm

NUM = re.compile(r"\$?\d[\d,.]*\s?(?:%|percent|billion|million|trillion|thousand|bn|m|k)?", re.I)
YEAR = re.compile(r"^(1[6-9]\d\d|20[0-5]\d)$")

def registry(research: dict) -> list[dict]:
    """Факты ресёрча в виде реестра: id, утверждение, число и единица, источник, дословная выдержка, дата документа."""
    out = []
    for f in research.get("facts", []) or []:
        out.append({"id": f.get("id"), "claim": f.get("fact"), "value": f.get("value"), "unit": f.get("unit"),
                    "url": f.get("source_url"), "quote": f.get("quote"), "as_of": f.get("as_of") or f.get("date")})
    return out

def _norm(x: str) -> str:
    return re.sub(r"[\s,]", "", x.lower().rstrip(".")).replace("percent", "%").replace("bn", "billion")

def _nums(text: str) -> dict:
    """Число → окружающая фраза (для проверки в контексте, а не «голой» цифры)."""
    words = text.split()
    out = {}
    for m in NUM.finditer(text):
        raw = m.group(0).strip()
        digits = re.sub(r"[^\d]", "", raw)
        if not digits or YEAR.match(digits) and len(digits) == 4: continue   # годы проверяет фактчек по timeline, не здесь
        k = len(text[:m.start()].split())
        out[_norm(raw)] = " ".join(words[max(0, k - 10):k + 10])
    return out

def changed(before: str, after: str) -> list[dict]:
    """Числа, которых не было в проверенном тексте или у которых сменился контекст."""
    b, a = _nums(before), _nums(after)
    out = []
    for n, ctx in a.items():
        if n not in b: out.append({"number": n, "context": ctx, "why": "новое число"})
        elif _norm(b[n])[:60] != _norm(ctx)[:60]: out.append({"number": n, "context": ctx, "why": "то же число в другой фразе"})
    return out

def verify(vid: str, before: str, after: str, research: dict) -> dict:
    """Проверяет только изменившееся. Возвращает {"ok": bool, "bad": [{number, context, why, fix}]}"""
    items = changed(before, after)
    if not items:
        print("[claims] после правок числа не менялись", flush=True); return {"ok": True, "bad": [], "checked": 0}
    reg = registry(research)
    res = llm.ask_json(
        "Ты — проверяющий редактор. Ниже реестр проверенных фактов с дословными выдержками из источников и числа, которые появились "
        "или переехали в другую фразу уже ПОСЛЕ фактчека. Для каждого числа реши, подтверждается ли оно реестром именно в таком виде "
        "и именно в этом контексте (единицы, период, компания, кто кому платит).\n\n"
        "РЕЕСТР:\n" + json.dumps(reg, ensure_ascii=False)[:60000] +
        "\n\nЧИСЛА ПОСЛЕ ПРАВОК:\n" + json.dumps(items, ensure_ascii=False)[:20000] +
        "\n\nВерни JSON: {\"bad\": [{\"number\": \"...\", \"context\": \"фраза как есть\", \"why\": \"чем не подтверждается\", "
        "\"fix\": \"как переписать фразу, чтобы она соответствовала реестру\"}]} — в bad только то, что реестром НЕ подтверждается.",
        max_tokens=4000, tag="claims_" + vid, model=config.LLM_MODEL_FACTCHECK or None)
    bad = [b for b in (res.get("bad") or []) if b.get("context")]
    print(f"[claims] проверено изменений: {len(items)}, не подтверждено: {len(bad)}", flush=True)
    for b in bad[:6]: print("  - " + str(b.get("number")) + ": " + str(b.get("why"))[:120], flush=True)
    return {"ok": not bad, "bad": bad, "checked": len(items)}

def fix(vid: str, s: dict, bad: list[dict]) -> dict:
    """Правит только помеченные фразы, остального текста не трогает (как после фактчека)."""
    if not bad: return s
    res = llm.ask_json(
        "Ниже фразы документального сценария с числами, которые не подтверждаются реестром фактов, и как их поправить.\n"
        "Перепиши КАЖДУЮ фразу минимально: сохрани ритм и длину, убери или замени непроверенное число по подсказке fix. "
        "Ничего нового не добавляй.\n\n" + json.dumps(bad, ensure_ascii=False)[:20000] +
        "\n\nВерни JSON: {\"edits\": [{\"from\": \"фраза как есть\", \"to\": \"исправленная фраза\"}]}",
        heavy=True, max_tokens=4000, tag="claims_fix_" + vid, model=config.LLM_MODEL_WRITER or None)
    n = 0
    for e in res.get("edits") or []:
        a, b = (e.get("from") or "").strip(), (e.get("to") or "").strip()
        if not a or not b or a not in s["script"]: continue
        s["script"] = s["script"].replace(a, b)
        s["parts"] = [p.replace(a, b) for p in s.get("parts") or []]
        n += 1
    print(f"[claims] поправлено фраз: {n} из {len(bad)}", flush=True)
    return s
