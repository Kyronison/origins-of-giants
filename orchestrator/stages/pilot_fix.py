"""Пилот 19.10 (STRATEGY.md, раздел 0.4): до рендера заменить архивные кадры, которые проверка соответствия
(visual_integrity) отклонила — чужая компания, другой человек, другое десятилетие.
Раунд 1: другой архивный кандидат (без генерации). Раунд 2: картинка предметов без людей по новому замыслу; не купилась —
нейтральная сцена эпохи без людей и надписей. Если и она не получилась, слот остаётся архивным и отклонённым: финальная
проверка (visual_integrity.review с enforce) держит рендер пилотного ролика, подмена тихо в ролик не уходит."""
import copy
import json
from .. import config, db, visual_integrity
from . import preflight, story
from . import story_assets as SA

ROUNDS = 2
NEUTRAL = ("quiet documentary photograph of an ordinary American small-town main street with modest storefronts and parked cars "
           "of the period, no people, no signs, no readable text, no logos")


def _bought(sl, before) -> bool:
    return sl.get("kind") == "image" and bool(sl.get("image")) and sl.get("image") != before.get("image")


def _archive_retry(x, sl, d, script, vid):
    from . import archive
    before = copy.deepcopy(sl)
    try:
        if archive.resolve(sl, d, preflight._context(x, script), vid, exclude=True, portrait=(sl.get("role") == "portrait")):
            if sl.get("src"): SA._video_dims(sl, d)
    except Exception as e: print(f"[pilot] {preflight._sid(x, sl)}: архив повторно: {str(e)[:120]}", flush=True)
    # 26.10 Walmart: неудачный повтор оставлял слот без кадра — пустой тёмный фон на 0:00 в рендере. Не нашлось — прежний кадр.
    # 27.10 Disney: кандидат скачан, отброшен по водяному знаку и удалён, а ссылка в слоте осталась — «Нет медиа» на проверке.
    have = lambda s: bool(s.get("src") or s.get("image")) and (d / (s.get("src") or s.get("image"))).is_file()
    if not have(sl) and have(before):
        sl.clear(); sl.update(before)


def _image(x, sl, d, script, vid, prompt, fal_cost) -> bool:
    """Архивный слот → новая иллюстрация без людей. False — купить не удалось, слот возвращён как был."""
    before = copy.deepcopy(sl)
    if sl.get("role") == "portrait":   # сгенерированное лицо нельзя подписать именем — колонка без портрета
        sl.update({"src": None, "image": None, "caption": None}); sl.pop("kind", None)
        return True
    sl["caption"] = None; sl["clip_seconds"] = None; sl["no_people"] = True
    for k in ("kind", "aspect", "archive", "credit"): sl.pop(k, None)
    for n, p in enumerate((prompt, NEUTRAL)):
        era = story.era_clause(preflight._era_of(x, script), p)
        if era and "no modern devices" not in p: p = p.rstrip(". ") + ", " + era
        preflight._replace(sl, d, config.IMAGE_MODEL, fal_cost, p, attempt=f"pilot{n}", ctx=preflight._context(x, script), vid=vid)
        if _bought(sl, before):
            preflight._record_reconceived_intent(sl, preflight._context(x, script))
            return True
    sl.clear(); sl.update(before)   # остаётся архивным: финальная проверка его увидит
    return False


def run(vid: str, d, tl: dict, script: str) -> dict:
    """Возвращает обновлённый timeline (тот же, если менять нечего)."""
    for r in range(1, ROUNDS + 1):
        visual_integrity.review(d, tl, script, vid, enforce=False)   # только отчёт: какие слоты отклонены
        bad = visual_integrity.failed_checks(d, tl, script) or []
        if not bad:
            print(f"[pilot] {vid}: проверка соответствия кадров чистая (раунд {r})", flush=True)
            return tl
        v = db.get(vid); s = v["payload"]["script"]; shots = s["shots"]
        pairs = {preflight._sid(x, sl): (x, sl) for x, sl in preflight._pairs(shots)}
        todo = [(*pairs[c["slot"]], c["why"]) for c in bad if c.get("slot") in pairs]
        print(f"[pilot] {vid}: раунд {r}, отклонено {len(bad)}, заменяю {len(todo)}", flush=True)
        fal_cost, failed = {"usd": 0.0}, []
        if r < ROUNDS:
            for x, sl, _ in todo: _archive_retry(x, sl, d, script, vid)
        else:
            for _, sl, _ in todo: sl["no_people"] = True   # замысел без людей: генератор не покупает «люди + без лиц»
            prompts = preflight._reconceive(todo, script, vid, f"pilot{r}")
            for x, sl, _ in todo:
                sid = preflight._sid(x, sl)
                prompt = (prompts.get(sid) or (None,))[0] or preflight.sanitize_prompt(sl.get("prompt") or sl.get("query") or "cinematic detail shot")
                if not _image(x, sl, d, script, vid, prompt, fal_cost): failed.append(sid)
        db.update(vid, payload={"script": {**s, "shots": shots}})
        preflight.sync_timeline(d, shots)
        tl = json.loads(config.read(d / "timeline.json"))
        print(f"[pilot] {vid}: раунд {r} — картинки по тарифу ≈${fal_cost['usd']:.2f}" +
              (f"; не заменены {len(failed)}: {', '.join(failed[:12])} — финальная проверка их удержит" if failed else ""), flush=True)
    return tl
