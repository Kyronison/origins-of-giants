"""CLI и движок очереди. `run` двигает каждое видео на один шаг вперёд."""
import sys, traceback
from .ancestors_profile import COMMANDS as _ANC_COMMANDS, activate as _anc_activate
if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] in _ANC_COMMANDS:
    _anc_activate()  # Before db/config imports: separate DATA, queue and OAuth.
for _s in (sys.stdout, sys.stderr):   # кириллица в консоли Windows и в data/log.txt; построчный вывод — лог preflight не теряется при обрыве процесса
    if hasattr(_s, "reconfigure"): _s.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
from . import db, telegram, config, money
from .locking import Busy, video_lock as lock, exclusive
from .stages import topics, script, assets, render, qc, upload, analytics, preflight, metrics

NEXT = {"approved_topic": script.run, "approved_script": assets.run, "assets": render.run, "rendered": qc.run}
from .stages import es_cartoon   # 13.10 владелец: испанский канал — свой конвейер (рисунок во весь кадр, смена ~4 с, без титров)
ES_NEXT = {"es_topic": es_cartoon.script, "es_scripted": es_cartoon.assets, "es_assets": es_cartoon.render}
if not config.ES_LANE: NEXT.update(ES_NEXT)   # без отдельной полосы испанские этапы идут в общей очереди
if config.REQUIRE_FINAL_APPROVAL: NEXT["approved_final"] = upload.run   # qc_passed ждёт кнопку владельца
else: NEXT["qc_passed"] = NEXT["approved_final"] = upload.run

STAGE_FN = {"script": script.run, "storyboard": script.restoryboard, "shots": script.reshots, "preflight": preflight.run, "clips": preflight.clips_for, "assets": assets.run, "render": render.run, "qc": qc.run, "upload": upload.run}

FAIL_N: dict[str, int] = {}     # id → сколько раз подряд упало: пауза между повторами растёт, уведомления редеют
FAILED: dict[str, float] = {}   # id → время последнего падения: в watch не долбить упавший этап каждые 30 с (и не спамить в Telegram)
RETRY_AFTER = 600

ES_BUSY = ("es_topic", "es_scripted", "es_assets")
BUSY_STATES = ("approved_topic", "scripted", "approved_script", "assets", "rendered", "qc_passed", "approved_final") + (() if config.ES_LANE else ES_BUSY)

_LOW_FAL = [0.0]   # когда последний раз напоминали про баланс: без этого напоминание уходило каждую минуту
_LOW_DISK = [0.0]  # то же для места на диске
_LOW_OR = [0.0]    # то же для OpenRouter: 25.09 баланс ушёл в минус и один и тот же трейсбек 402 повторялся каждые 10 минут
OR_MIN = 12.0      # меньше этого на OpenRouter — новую историю не начинаем: моделей на ролик уходит около $12

def _es_cartoon_ready(now_iso: str) -> bool:
    """Можно начинать испанский мультфильм: режим включён и впереди меньше двух испанских роликов (запланированных или ждущих «да»)."""
    if not (config.ES_CARTOON and (config.ROOT / "stories_es.txt").exists()): return False
    n = db.conn().execute("SELECT COUNT(*) AS c FROM videos WHERE id LIKE '%__es' AND ((status = 'localized_uploaded' AND publish_at > ?) "
                          "OR status = 'localized') AND created >= '2026-10-12'", (now_iso,)).fetchone()["c"]
    n += db.conn().execute("SELECT COUNT(*) AS c FROM videos WHERE status = 'es_ready' OR (status = 'es_uploaded' AND publish_at > ?)", (now_iso,)).fetchone()["c"]   # 13.10: испанский-сразу
    return n < 2

def _es_autostart():
    """Испанская полоса: новая тема, когда в полосе пусто, впереди меньше двух испанских роликов и есть деньги на модели и картинки."""
    import shutil
    from datetime import datetime, timezone
    if not (config.ES_CARTOON and config.ES_NEW) or any(db.by_status(st) for st in ES_BUSY): return
    if shutil.disk_usage(str(config.DATA)).free / 2 ** 30 < config.MIN_FREE_GB_START: return
    if not _es_cartoon_ready(datetime.now(timezone.utc).isoformat()): return
    fal, orl = money.fal_left(), money.or_left()
    if (fal is not None and fal < 8) or (orl is not None and orl < 6):
        print(f"[watch-es] мало денег (fal ${fal}, OpenRouter ${orl}) — новую испанскую тему не начинаю", flush=True); return
    c = es_cartoon.queue()
    if not c: return
    vid = es_cartoon.start(c)
    try: telegram.send(f"🇪🇸 Начинаю испанский ролик сам: `{vid}` — La historia COMPLETA de {c['company']}\nОтменить: `reject {vid}`")
    except Exception: pass

def watch_es(every: int = 60):
    """Испанская полоса (13.10): этапы es_cartoon и автостарт испанских тем, отдельно от английского watch. Telegram не опрашивает."""
    import time
    from .locking import FileLock
    with FileLock(config.DATA / ".pipeline_es.lock", "watch_es"):
        print(f"[watch-es] старт, опрос каждые {every} с", flush=True)
        while True:
            try:
                for status, fn in ES_NEXT.items():
                    for v in db.by_status(status):
                        if time.time() - FAILED.get(v["id"], 0) < min(RETRY_AFTER * FAIL_N.get(v["id"], 1), 3600): continue
                        try:
                            with lock(v["id"], status):
                                if db.get(v["id"])["status"] != status: continue
                                print(f"{v['id']}: {status} -> {fn.__name__}", flush=True)
                                _execute(fn, v["id"], status)
                                FAILED.pop(v["id"], None); FAIL_N.pop(v["id"], None)
                        except Busy: continue
                        except Exception as e:
                            traceback.print_exc(); FAILED[v["id"]] = time.time(); n = FAIL_N[v["id"]] = FAIL_N.get(v["id"], 0) + 1
                            if n >= 4: FAILED[v["id"]] = time.time() + 10 ** 9
                            if n in (1, 3, 4):
                                try: telegram.send(f"⚠️ испанский `{v['id']}` упал на этапе {status} (попытка {n}): {str(e)[:300]}")
                                except Exception: pass
                _es_autostart()
                from .stages import comments; comments.es_tick()   # 14.10: комментарий под вышедшим испанским роликом
                from .stages import es_shorts   # 15.10 владелец: шортс к каждому испанскому ролику (вариант B)
                for vid in es_shorts.due():
                    key = vid + ":short"
                    if time.time() - FAILED.get(key, 0) < min(RETRY_AFTER * FAIL_N.get(key, 1), 3600): continue
                    try:
                        with lock(vid, "es_short"): _execute(es_shorts.run, vid, "es_short")
                        FAILED.pop(key, None); FAIL_N.pop(key, None)
                    except Busy: continue
                    except Exception as e:
                        traceback.print_exc(); FAILED[key] = time.time(); FAIL_N[key] = FAIL_N.get(key, 0) + 1
                        if FAIL_N[key] in (1, 4):
                            try: telegram.send(f"⚠️ испанский шортс `{vid}` не собрался (попытка {FAIL_N[key]}): {str(e)[:300]}")
                            except Exception: pass
                es_shorts.comment_tick()
            except Exception as e:
                print(f"[watch-es] ошибка: {e}", flush=True)
            time.sleep(every)

def _autostart():
    """Когда в работе пусто, очередь сама берёт следующую историю из stories.txt (владелец 20.09: «хочу минимального участия»).
    Ограничители: не больше AUTO_PIPELINE_PER_DAY запусков в сутки и остаток на fal хотя бы на один ролик."""
    import time
    from datetime import date, datetime
    if not config.AUTO_PIPELINE: return
    if any(db.by_status(st) for st in BUSY_STATES): return
    force_es = False
    import shutil
    free = shutil.disk_usage(str(config.DATA)).free / 2 ** 30   # 29.09 STRATEGY.md: без места ролик падает на рендере, деньги на сценарий уже потрачены
    if free < config.MIN_FREE_GB_START:
        if int(time.time()) % 1800 < 60: print(f"[queue] на диске данных свободно {free:.1f} ГБ, нужно {config.MIN_FREE_GB_START:.0f} — новую историю не начинаю", flush=True)
        if time.time() - _LOW_DISK[0] > 12 * 3600:
            _LOW_DISK[0] = time.time()
            try: telegram.send(f"💾 На диске данных свободно {free:.1f} ГБ (нужно {config.MIN_FREE_GB_START:.0f}) — конвейер не начинает новые ролики. Напомню не раньше чем через 12 часов.")
            except Exception: pass
        return
    if config.AUTO_BACKLOG > 0:
        # режим запаса (владелец 22.09): ролики делаются подряд, пока впереди меньше AUTO_BACKLOG запланированных и не вышедших;
        # слот каждому даёт upload.next_slot — ближайший свободный вечер, по одному в день
        from datetime import timezone
        now_iso = datetime.now(timezone.utc).isoformat()
        ahead = db.conn().execute("SELECT COUNT(*) AS c FROM videos WHERE status = 'uploaded' AND publish_at > ?", (now_iso,)).fetchone()["c"]
        if ahead >= config.AUTO_BACKLOG:
            if _es_cartoon_ready(now_iso) and not config.ES_LANE: force_es = True   # 12.10: английский запас полон — время испанского мультфильма
            else:
                if int(time.time()) % 1800 < 60: print(f"[queue] запас полон: {ahead} роликов впереди (лимит {config.AUTO_BACKLOG})", flush=True)
                return
    else:
        today = f"{date.today()}"
        n = db.conn().execute("SELECT COUNT(*) AS c FROM videos WHERE created LIKE ? AND status != 'rejected'", (today + "%",)).fetchone()["c"]
        if n >= config.AUTO_PIPELINE_PER_DAY: return
        # ролик дня начинаем утром: сборка занимает около двух часов, вечерний слот — 19:00 ET.
        # Позже AUTO_PIPELINE_UNTIL не начинаем: такой ролик к слоту не успеет и сломает ритм «каждый день в одно время».
        hour = datetime.now().hour
        if not (config.AUTO_PIPELINE_HOUR <= hour < config.AUTO_PIPELINE_UNTIL):
            if hour < config.AUTO_PIPELINE_HOUR: print(f"[queue] ролик дня стартует в {config.AUTO_PIPELINE_HOUR}:00", flush=True)
            return
    orl = money.or_left()
    if orl is not None and orl < OR_MIN:   # 25.09: раньше смотрели только fal, и очередь бралась за ролик без денег на модели
        print(f"[queue] на OpenRouter осталось ${orl:.2f} — следующую историю не начинаю", flush=True)
        if time.time() - _LOW_OR[0] > 12 * 3600:
            _LOW_OR[0] = time.time()
            try: telegram.send(f"💳 На OpenRouter осталось ${orl:.2f} — конвейер не начинает новые ролики. "
                               f"Пополнить: https://openrouter.ai/settings/credits\nНапомню не раньше чем через 12 часов.")
            except Exception: pass
        return
    left = money.fal_left()
    if left is not None and left < 18:
        print(f"[queue] на fal осталось ${left:.2f} — следующую историю не начинаю", flush=True)
        if time.time() - _LOW_FAL[0] > 12 * 3600:   # очередь тикает раз в минуту: напоминание о балансе — не чаще чем раз в 12 часов
            _LOW_FAL[0] = time.time()
            try: telegram.send(f"На fal осталось ${left:.2f} — конвейер не начинает новые ролики до пополнения. "
                               f"Напомню об этом не раньше чем через 12 часов.")
            except Exception: pass
        return
    try:
        # вторая очередь (владелец 22.09): темы для испаноговорящих из stories_es.txt чередуются с основной по доле ES_QUEUE_SHARE
        n_es = db.conn().execute("SELECT COUNT(*) AS c FROM videos WHERE status != 'rejected' AND payload LIKE '%stories_es.txt%'").fetchone()["c"]
        n_all = db.conn().execute("SELECT COUNT(*) AS c FROM videos WHERE status != 'rejected' AND payload LIKE '%\"format\": \"story\"%' AND id NOT LIKE '%__es'").fetchone()["c"]
        src = "stories_es.txt" if config.ES_AUTO and config.ES_QUEUE_SHARE > 0 and n_es < (n_all + 1) * config.ES_QUEUE_SHARE and (config.ROOT / "stories_es.txt").exists() else None
        if config.ES_CARTOON and not config.ES_LANE and (config.ROOT / "stories_es.txt").exists():
            # 12.10 владелец: испанские мультфильмы чередуются с английскими роликами один к одному
            last = db.conn().execute("SELECT payload FROM videos WHERE status != 'rejected' AND id NOT LIKE '%__es' "
                                     "AND payload LIKE '%\"format\": \"story\"%' ORDER BY created DESC LIMIT 1").fetchone()
            last_es = bool(last and "stories_es.txt" in (last["payload"] or ""))
            from datetime import timezone as _tz
            if force_es or (not last_es and _es_cartoon_ready(datetime.now(_tz.utc).isoformat())): src = "stories_es.txt"
        if src == "stories_es.txt" and config.ES_NEW:   # 13.10: испанская тема — в свой конвейер, без английского сценария
            c = es_cartoon.queue(); ids = [es_cartoon.start(c)] if c else []
        else: ids = topics.run_story(1, auto=True, source=src)
        if ids: telegram.send(f"Начинаю следующий ролик сам: `{ids[0]}`" + (" (тема испанской очереди)" if src else "") + f"\nОтменить: `reject {ids[0]}`")
    except Exception as e:
        print("[queue] автостарт:", str(e)[:200], flush=True)

_METRICS_AT = [0.0]

def _metrics_tick(every_h: float = 4.0):
    """Срезы метрик по расписанию — внутри очереди, чтобы не заводить отдельный планировщик."""
    import time
    if time.time() - _METRICS_AT[0] < every_h * 3600: return
    _METRICS_AT[0] = time.time()
    try:
        metrics.backfill_ids(); metrics.take(quiet=True)
    except Exception as e: print("[metrics]", str(e)[:200], flush=True)
    from .stages import retention
    for fn in (metrics.hit_check, metrics.weekly_tick, retention.tick):   # 29.09 STRATEGY.md: правило «за попаданием», таблица по понедельникам, место на диске
        try: fn()
        except Exception as e: print(f"[metrics] {fn.__name__}:", str(e)[:200], flush=True)

@exclusive
def run_queue():
    import time
    telegram.poll()
    try:   # 14.10 владелец: комментарий канала под каждым вышедшим лонгом
        from .stages import comments; comments.en_tick()
    except Exception as e: print("[comments] " + str(e)[:120], flush=True)
    try: upload.short_comments_tick()   # ссылка на полный ролик под вышедшими шортсами (23.09)
    except Exception as e: print("[shorts] комментарии: " + str(e)[:120], flush=True)
    try:   # 06.10 владелец: моушен-шортсы вышедших роликов — очередь загрузки в пределах квоты API
        from .stages import motion_shorts; motion_shorts.upload_tick()
    except Exception as e: print("[motion] выкладка: " + str(e)[:160], flush=True)
    for status, fn in NEXT.items():
        for v in db.by_status(status):
            if time.time() - FAILED.get(v["id"], 0) < min(RETRY_AFTER * FAIL_N.get(v["id"], 1), 3600): continue
            try:
                with lock(v["id"], status):
                    v = db.get(v["id"])
                    if v["status"] != status: continue
                    print(f"{v['id']}: {status} -> {fn.__module__.split('.')[-1]}", flush=True)
                    if not v["payload"].get("config_manifest"):   # с какими настройками и кодом ролик собирался — в его карточку
                        db.update(v["id"], payload={"config_manifest": config.manifest()})
                    _execute(fn, v["id"], status)
                    FAILED.pop(v["id"], None); FAIL_N.pop(v["id"], None)
            except Busy as b:
                print(f"[queue] {v['id']}: {b}", flush=True); continue
            except Exception as e:
                traceback.print_exc(); FAILED[v["id"]] = time.time()
                n = FAIL_N[v["id"]] = FAIL_N.get(v["id"], 0) + 1
                wait = min(RETRY_AFTER * n, 3600)                     # чем дольше не чинится, тем реже повтор
                # 26.09: сменилась сеть (VPN/маршрут) — старые соединения получают 403 «security policy»; свежие работают
                if "security policy" in str(e) or "ConnectionError" in type(e).__name__ or "Connection" in str(e)[:120]:
                    from . import llm as _llm; _llm.reset()
                    FAILED[v["id"]] = time.time() - min(RETRY_AFTER * FAIL_N[v["id"]], 3600) + 120   # повтор через 2 минуты с новыми соединениями
                    print(f"[queue] {v['id']}: сетевой отказ ({str(e)[:80]}) — клиент пересоздан, повтор через 2 мин", flush=True)
                    if n in (3, 10):
                        try: telegram.send(f"🌐 `{v['id']}`: запросы к моделям отклоняются уже {n} раз подряд (сеть/VPN?). Пересоздаю соединения и повторяю.")
                        except Exception: pass
                    continue
                # 25.09: деньги сами не появятся — повторять раз в 10 минут бессмысленно, а в Telegram нужна причина, а не трейсбек
                if "402" in str(e) or "more credits" in str(e) or "available credit" in str(e):
                    orl = money.or_left(max_age=0); FAIL_N[v["id"]] = max(n, 6); wait = 3600
                    print(f"[queue] {v['id']}: на OpenRouter ${orl if orl is not None else '?'} — этап {status} ждёт пополнения", flush=True)
                    if time.time() - _LOW_OR[0] > 12 * 3600:
                        _LOW_OR[0] = time.time()
                        try: telegram.send(f"💳 Деньги на OpenRouter кончились (остаток ${orl if orl is not None else '?'}). "
                                           f"`{v['id']}` стоит на этапе {status} и ждёт пополнения: "
                                           f"https://openrouter.ai/settings/credits\nПроверяю раз в час, напомню не раньше чем через 12.")
                        except Exception: pass
                    continue
                # 11.10: Sears упал 30+ раз на снятой модели (404), и каждая попытка заново платила за вычитку, вступление и сверку
                # фактов (~$0.7) — $22 впустую. После 4 одинаковых падений ролик ставится на стоп до перезапуска watch или ручного этапа.
                if n >= 4:
                    FAILED[v["id"]] = time.time() + 10 ** 9
                    print(f"[queue] {v['id']}: {n} падений подряд на этапе {status} — остановлен, чтобы не платить за повторы", flush=True)
                    try: telegram.send(f"⛔ `{v['id']}` упал {n} раза подряд на этапе {status}: {str(e)[:300]}\n"
                                       f"Повторы остановлены, чтобы не тратить деньги. Нужна починка; после неё — перезапуск watch.")
                    except Exception: pass
                    continue
                # одно и то же падение раз в 10 минут в Telegram — спам (владелец 20.09): пишем 1-й раз, 3-й и дальше раз в час
                if n in (1, 3) or n % 6 == 0:
                    try: telegram.send(f"⚠️ `{v['id']}` упало на этапе {status}" + (f" (попытка {n})" if n > 1 else "") +
                                       f": {e}\nСледующий повтор через {wait // 60} мин." +
                                       ("\nДальше об этом же падении буду писать раз в час." if n == 1 else ""))
                    except Exception as te: print("[telegram]", te)
    _localize_tick(); _metrics_tick(); _autostart()

def _localize_tick():
    """Испанская версия для каждого готового английского ролика (ES_AUTO): загруженный/вышедший story-ролик без пометки es_done →
    localize.build + upload на второй канал. Темы es_only на английский канал не грузятся (upload это пропускает), но сюда попадают так же."""
    import time
    if not config.ES_AUTO: return
    from .stages import localize
    rows = db.conn().execute("SELECT id FROM videos WHERE status IN ('uploaded', 'published') AND id NOT LIKE '%__es' "
                             "AND payload LIKE '%\"format\": \"story\"%' AND payload NOT LIKE '%\"es_done\"%' AND created >= '2026-09-21' ORDER BY created LIMIT 1").fetchall()
    for r in rows:
        vid = r["id"]
        if time.time() - FAILED.get(vid + "__es", 0) < 3600: continue
        try:
            with lock(vid, "localize"):
                print(f"{vid}: → localize es", flush=True)
                vid2 = localize.build(vid, "es")
                localize.upload(vid2)
                db.update(vid, payload={"es_done": vid2}); FAILED.pop(vid + "__es", None)
        except Busy: continue
        except Exception as e:
            traceback.print_exc(); FAILED[vid + "__es"] = time.time()
            try: telegram.send(f"⚠️ испанская версия `{vid}` не собралась: {str(e)[:200]}\nПовтор через час.")
            except Exception: pass

@exclusive
def watch(every: int = 30):
    """Постоянный режим на ноутбуке/VPS: каждые N секунд опрашивает Telegram и двигает очередь, если есть что двигать.
    Кнопки в Telegram срабатывают в течение полуминуты. Останавливать: Ctrl+C или закрыть процесс."""
    import time
    import json as _json, os as _os
    print(f"[watch] старт, опрос каждые {every} с, pid {_os.getpid()}", flush=True)
    print("[watch] настройки этого процесса: " + _json.dumps(config.manifest(), ensure_ascii=False), flush=True)
    while True:
        try:
            telegram.poll()
            pending = [v["id"] for st in NEXT for v in db.by_status(st)]
            if pending: print(f"[watch] {time.strftime('%H:%M')} в работе: {pending}", flush=True)
            run_queue()   # и когда пусто: в конце run_queue метрики и автостарт следующей истории
        except Exception as e:
            print(f"[watch] ошибка: {e}", flush=True)
        time.sleep(every)

def _execute(fn, vid, name):
    """Attribute each paid request to its video, including failed stages."""
    from . import llm, spend
    llm.take_cost()  # discard unassigned costs from reports and earlier commands
    from .stages import assets as _A, story_assets as _SA, story as _S
    _A.CARTOON["on"] = _SA._cartoon["on"] = _S.CARTOON["on"] = False   # 12.10: режим мультфильма включает только этап испанского ролика
    money.begin_stage(vid)
    try:
        with spend.scope(vid, name), llm.scope(vid): return fn(vid)
    finally:
        _A.CARTOON["on"] = _SA._cartoon["on"] = _S.CARTOON["on"] = False   # шортсы и обложки английского канала после этапа — в обычном стиле
        money.reconcile(vid)


VIDEO_COST_COMMANDS = {"thumb", "thumbv", "stillcheck", "localize", "localize-kit",
                       "brief", "demo", "shorts", "motion_shorts", "publish", "entities"}


def video_command(fn, vid, name):
    """Keep manual video helpers inside the same accounting and video lock."""
    with lock(vid, name):
        return _execute(lambda _vid: fn(), vid, name)


@exclusive
def stage(name: str, vid: str):
    """Один этап для одного видео, без проверки статуса — для пошагового прогона и отладки."""
    with lock(vid, name):
        _execute(STAGE_FN[name], vid, name)

def demo(vid: str, t0: float | None = None, length: float = 90, film: float = 0.8, force: bool = False, render_out: bool = True):
    """Демо-срез по грамматике сцен (docs/scene-grammar.md §3.6) на готовом голосе: entities → паузы на главах → окно из паузного voice.mp3
    → типизированные сцены (people/map/split/broll) → слоты → preflight → сводка типов и деградаций → demo_film08.mp4 (+ demo_film0.mp4 при --film 0).
    По умолчанию окно начинается за 12 с до первой паузы (хвост cold open → карточка «Origins» → родители/карта). Меньше двух богатых сцен и не --force — стоп до рендера."""
    import json, subprocess
    from concurrent.futures import ThreadPoolExecutor
    from . import llm
    from .stages import story, story_assets as SA, archive, pauses as P
    v = db.get(vid); d = db.video_dir(vid); s = v["payload"]["script"]
    entities = story.ensure_entities(vid)
    pauses = P.ensure(vid, s.get("parts"))
    words = json.loads(config.read(d / "words.json"))
    if t0 is None: t0 = max(0.0, pauses[0]["at"] - 12) if pauses else 0.0
    t1 = t0 + length
    dd = d / "demo"; dd.mkdir(exist_ok=True)
    subprocess.run([config.ffmpeg(), "-y", "-v", "error", "-ss", f"{t0:.3f}", "-t", f"{length:.3f}", "-i", str(d / "voice.mp3"),
                    "-c:a", "libmp3lame", "-b:a", "128k", str(dd / "voice.mp3")], check=True)
    w = [{"w": x["w"], "s": round(x["s"] - t0, 3), "e": round(x["e"] - t0, 3)} for x in words if t0 <= x["s"] < t1]
    config.write(dd / "words.json", json.dumps(w))
    idx0 = next(i for i, x in enumerate(words) if t0 <= x["s"])   # индексы слов окна в полном words.json
    win_pauses = [{**p, "at": round(p["at"] - t0, 3), "word_index": p["word_index"] - idx0} for p in pauses if t0 <= p["at"] < t1]
    k0 = sum(1 for p in pauses if p["at"] <= t0) + 1   # часть, в которой начинается окно
    parts = [k0] + [p["part"] for p in win_pauses]
    text = story.window_text(s["script"], [x["w"] for x in w[:4]], [x["w"] for x in w[-4:]])   # с [Fn] и абзацами — для подсказок
    plain = " ".join(x["w"] for x in w); n = len(plain.split())
    facts = (v["payload"].get("research") or {}).get("facts", [])
    print(f"[demo] {t0:.0f}–{t1:.0f} с, {n} слов, части {parts}, пауз в окне {len(win_pauses)}")
    # границы частей внутри окна: люди на новой части подсказываются «впервые» заново
    part_starts = [" ".join(x["w"] for x in w[p["word_index"]:p["word_index"] + 4]) for p in win_pauses if 0 <= p["word_index"] < len(w)]
    shots, overlays, downgrades, _ = story.shots_for_text(vid, max(parts), text, entities, facts, {"year": None}, prefix="d", n_parts=len(s.get("parts") or []) or 7,
                                                          part_starts=part_starts)
    if not shots: raise RuntimeError("модель не дала сцен")
    shots = story._regularize(shots, plain, downgrades)
    overlays = story._tidy_overlays(overlays, s.get("outline") or [], facts, plain)
    from .stages.script import strip_fact_refs
    shots = strip_fact_refs(shots); overlays = strip_fact_refs(overlays, "overlay")
    archive.reset(); SA._used_stock.clear(); fal_cost = {"usd": 0.0}; img_model = config.IMAGE_MODEL_CHEAP
    cast = [c["name"] for c in entities.get("cast") or [] if c.get("name")]
    with ThreadPoolExecutor(4) as ex:
        for f in [ex.submit(SA._resolve_slots, x, dd, img_model, fal_cost, SA._ctx(x, plain), vid, cast) for x in shots]: f.result()
    for x in shots:
        if x.get("downgrade"): downgrades.append({"id": x["id"], "from": "resolve", "why": x["downgrade"]})
    tracks = SA._music_tracks(s, dd, parts)
    fb = config.film_block(film if film else config.FILM_LOOK)
    SA._timeline(dd, shots, overlays, plain, v["title"], tracks, pauses=win_pauses, film=fb)
    fal_cost["usd"] += preflight.check(dd, shots, plain, vid, img_model, passes=3)   # брак и подмены — как в большом ролике
    tl2 = json.loads(config.read(dd / "timeline.json"))
    for x in shots:
        x.pop("_tried", None)
        for sl in x.get("slots") or []: sl.pop("_tried", None)
    config.write(dd / "shots.json", json.dumps({"shots": shots, "overlays": overlays, "downgrades": downgrades}, ensure_ascii=False, indent=2))
    rich = [x for x in shots if x["type"] != "broll"]
    print("[demo] сводка:\n" + story.summary(shots, downgrades))
    print(f"[demo] сцен {len(shots)} (богатых {len(rich)}), архивных слотов {sum(1 for x in shots for sl in x.get('slots') or [] if sl.get('kind') == 'archive')}, "
          f"титров {len(tl2['overlays'])}, пауз {len(tl2['pauses'])}; расходы: fal ${fal_cost['usd']:.2f}, LLM ${llm.take_cost():.2f}")
    if len(rich) < 2 and not force:
        print("[demo] богатых сцен меньше двух — стоп до рендера (добавь --force, чтобы рендерить всё равно)"); return
    if not render_out:
        print("[demo] --no-render: таймлайн собран, рендер пропущен:", dd / "timeline.json"); return
    SA._check_files(dd, tl2)
    outs = []
    for tag, strength in (("film08", 0.8),) + ((("film0", 0.0),) if not film else ()):
        tl2["film"] = config.film_block(strength); out = dd / f"demo_{tag}.mp4"
        render._rx("render", "Main", out, {"timeline": tl2, "words": w}, dd)   # 1080p; --scale даёт дробные размеры кадра и валит ffmpeg
        outs.append(out); print("[demo] готово:", out)
    # контактный лист по готовому рендеру — всегда, чтобы смотреть тот файл, который отдаём
    try: print("[demo] контактный лист:", render.contact_sheet(outs[0], tl2, dd / "contact.jpg"))
    except Exception as e: print("[demo] контактный лист не собрался:", e)
    try:
        for out in outs:
            if out.stat().st_size < 49_000_000: telegram.send(f"Демо грамматики сцен ({length:.0f} с, {out.stem}):", file=out)
            else: telegram.send(f"Демо готово ({length:.0f} с), файл больше лимита Telegram: {out}")
    except Exception as e: print("[telegram]", e)

def _demo_cli(args: list[str]):
    """demo <id> [t0|auto] [length] [--film 0|0.8] [--force] [--no-render]"""
    flags = {a for a in args if a.startswith("--") and "=" not in a and a not in ("--film",)}
    pos, film, i = [], 0.8, 0
    while i < len(args):
        a = args[i]
        if a == "--film": film = float(args[i + 1]); i += 2; continue
        if a.startswith("--film="): film = float(a.split("=", 1)[1])
        elif not a.startswith("--"): pos.append(a)
        i += 1
    t0 = None if len(pos) < 2 or pos[1] == "auto" else float(pos[1])
    length = float(pos[2]) if len(pos) > 2 else 90
    demo(pos[0], t0, length, film, force="--force" in flags, render_out="--no-render" not in flags)

def status():
    for r in db.conn().execute("SELECT * FROM videos ORDER BY created DESC LIMIT 30"):
        print(f"{r['id']:<45} {r['status']:<16} {r['title'] or ''}")

def link(vid: str, youtube_id: str):
    """UPLOAD_MODE=manual: владелец залил вручную и сообщает id ролика."""
    from datetime import datetime, timezone
    db.update(vid, "uploaded", youtube_id=youtube_id, publish_at=datetime.now(timezone.utc).isoformat())
    print(vid, "-> uploaded", youtube_id)

def doctor():
    """Проверка окружения перед первым прогоном."""
    import os, shutil
    ok = True
    def check(name, cond, hint=""):
        nonlocal ok; ok &= bool(cond); print(("  ok  " if cond else "  --  ") + name + ("" if cond else f"   <- {hint}"))
    print("Ключи в .env:")
    for k in ("OPENROUTER_API_KEY", "ELEVENLABS_API_KEY", "ELEVENLABS_VOICE_ID", "FAL_KEY", "PEXELS_API_KEY", "TELEGRAM_BOT_TOKEN"):
        check(k, os.getenv(k), "пусто")
    print("Файлы:")
    check("YOUTUBE_CLIENT_SECRET_FILE", os.path.exists(os.getenv("YOUTUBE_CLIENT_SECRET_FILE", "")), "нет файла OAuth-клиента")
    check("data/youtube_token.json", (config.DATA / "youtube_token.json").exists(), "запусти auth-youtube")
    check("data/pipeline.db", (config.DATA / "pipeline.db").exists(), "запусти init")
    print("Инструменты:")
    check("node", shutil.which("node"), "поставь Node.js 18+")
    check("remotion/node_modules", (config.REMOTION / "node_modules" / "remotion").exists(), "cd remotion && npm install")
    try: check("ffprobe", config.ffprobe())
    except RuntimeError as e: check("ffprobe", False, str(e))
    for mod in ("openai", "elevenlabs", "fal_client", "googleapiclient", "google_auth_oauthlib"):
        try: __import__(mod); check(f"python: {mod}", True)
        except ImportError: check(f"python: {mod}", False, "pip install -r requirements.txt")
    print("Настройки:", f"AI_BROLL_MAX_CLIPS={config.AI_BROLL_MAX_CLIPS}", f"REQUIRE_FINAL_APPROVAL={config.REQUIRE_FINAL_APPROVAL}",
          f"UPLOAD_MODE={config.UPLOAD_MODE}", f"RENDER_HEIGHT={config.RENDER_HEIGHT}", f"DATA_DIR={config.DATA}")
    print("Готово к первому прогону." if ok else "Есть незакрытые пункты (см. «--»).")

if __name__ == "__main__":
    cmd, *args = sys.argv[1:] or ["run"]
    cmds = {"init": lambda: (config.VIDEOS.mkdir(parents=True, exist_ok=True), db.conn()),
            "topics": topics.run, "run": run_queue, "analytics": analytics.run,
            "metrics": lambda: (metrics.backfill_ids(), metrics.take(quiet=True), print(metrics.table())),
            "metrics-table": lambda: print(metrics.table()),
            "thumb": lambda: print(__import__("orchestrator.stages.thumbcheck", fromlist=["x"]).check(args[0])),
            "thumbv": lambda: print(__import__("orchestrator.stages.thumbv", fromlist=["x"]).make(args[0])),   # обложка «до → после» заново
            "stillcheck": lambda: print(__import__("orchestrator.stages.stillcheck", fromlist=["x"]).run(db.video_dir(args[0]), __import__("json").loads(config.read(db.video_dir(args[0]) / "timeline.json")), __import__("json").loads(config.read(db.video_dir(args[0]) / "words.json")), (args[1] if len(args) > 1 else "en"))),
            # второй канал (испанский): версия готового ролика, бренд-графика, вход и загрузка своим токеном (stages/localize.py)
            "localize": lambda: print(__import__("orchestrator.stages.localize", fromlist=["x"]).build(args[0], args[1] if len(args) > 1 else "es")),
            "localize-kit": lambda: __import__("orchestrator.stages.localize", fromlist=["x"]).build(args[0], args[1] if len(args) > 1 else "es", render=False),
            "auth-es": lambda: __import__("orchestrator.stages.localize", fromlist=["x"]).auth("es"),
            "auth-ancestors": lambda: __import__("orchestrator.stages.ancestors_youtube", fromlist=["x"]).auth(),
            "verify-ancestors": lambda: print(__import__("orchestrator.stages.ancestors_youtube", fromlist=["x"]).verify(__import__("orchestrator.stages.ancestors_youtube", fromlist=["x"]).client())),
            "start-ancestors": lambda: print(__import__("orchestrator.stages.ancestors_cartoon", fromlist=["x"]).start()),
            "status-ancestors": status,
            "run-ancestors": lambda: __import__("orchestrator.stages.ancestors_cartoon", fromlist=["x"]).run_queue(),
            "watch-ancestors": lambda: __import__("orchestrator.stages.ancestors_cartoon", fromlist=["x"]).watch(int(args[0]) if args else 60),
            "upload-ancestors": lambda: __import__("orchestrator.stages.ancestors_youtube", fromlist=["x"]).upload_private(args[0]),
            "upload-es": lambda: print(__import__("orchestrator.stages.localize", fromlist=["x"]).upload(args[0])),
            "brand-es": lambda: print(__import__("orchestrator.stages.localize", fromlist=["x"]).brand("es")),
            "brief": lambda: print(__import__("orchestrator.stages.brief", fromlist=["x"]).make(args[0], db.get(args[0])["payload"]["research"])),
            "topics-story": lambda: topics.run_story(int(next((a for a in args if a.isdigit()), 1)), auto="--auto" in args),
            "auth-youtube": upload.auth, "doctor": doctor, "status": status,
            "approve": lambda: print(args[0], "->", db.approve(args[0])),
            "reject": lambda: db.update(args[0], "rejected"),
            "stage": lambda: stage(args[0], args[1]),
            "link": lambda: link(args[0], args[1]),
            "watch": lambda: watch(int(args[0]) if args else 30),
            "watch-es": lambda: watch_es(int(args[0]) if args else 60),
            "demo": lambda: _demo_cli(args),
            "pauses": lambda: __import__("orchestrator.stages.pauses", fromlist=["x"]).ensure(args[0]),
            "shorts": lambda: __import__("orchestrator.stages.render", fromlist=["x"]).shorts(args[0], [int(x) for x in args[1:]] or None),
            "motion_upload": lambda: __import__("orchestrator.stages.motion_shorts", fromlist=["x"]).upload_tick(),
            "motion_shorts": lambda: __import__("orchestrator.stages.motion_shorts", fromlist=["x"]).build(args[0], int(args[1]) if len(args) > 1 else 3),
            "publish": lambda: __import__("orchestrator.stages.publish", fromlist=["x"]).run(args[0]),   # комплект для Studio заново (после шортсов)
            "retime": lambda: __import__("orchestrator.stages.story_assets", fromlist=["x"]).retime(args[0]),
            "entities": lambda: __import__("orchestrator.stages.story", fromlist=["x"]).ensure_entities(args[0]),
            "money": lambda: (print(__import__("orchestrator.money", fromlist=["x"]).report_text()), print("HTML:", __import__("orchestrator.money", fromlist=["x"]).report_html())),
            "experiment": lambda: __import__("orchestrator.experiment", fromlist=["x"]).report(*args)}   # итоги «двух недель без шортсов» (23.09 → 07.10)
    if cmd not in cmds:
        print("Команды:", ", ".join(cmds)); sys.exit(1)
    # All mutating CLI commands share the watch lock, including legacy helpers.
    if cmd in {"status", "doctor", "metrics-table", "money", "experiment", "watch-es", "watch-ancestors", "status-ancestors"}:   # separate lane locks
        cmds[cmd]()
    elif cmd in VIDEO_COST_COMMANDS:
        exclusive(lambda: video_command(cmds[cmd], args[0], cmd))()
    else:
        exclusive(cmds[cmd])()
