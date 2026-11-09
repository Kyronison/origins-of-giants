"""Срезы метрик по каждому ролику отдельно: 24 ч, 72 ч, 7, 14 и 28 дней после публикации.

STRATEGY.md (согласовано 29.09.2026), раздел 8: единица всех порогов — публичный счётчик ролика на 14-й день жизни; ролик засчитывается,
если настоящих просмотров (аналитика) не меньше 30% счётчика. Каждый понедельник — таблица по длинным роликам блока: 7, 14, 28-й день.
Срезы первых дней собираются молча: по первым 1–3 дням ролик не оценивается. Единственное действие по цифрам — правило «за попаданием».

Зачем (разбор 20.09): агрегат «за 28 дней» смешивает ролики разного возраста и шортсы с длинными,
по нему нельзя понять, сработала ли правка названия или превью. Срез фиксирует состояние одного ролика
в одном и том же возрасте — их можно сравнивать между роликами.
Таблица snapshots(video_id, age_h, taken, data). Публичный счётчик фиксирован; неполная аналитика догружается."""
import json, traceback
from datetime import datetime, timezone, timedelta
from .. import db, config, telegram
from .upload import yt

AGES_H = [24, 72, 168, 336, 672]     # 1 д, 3 д, 7 д, 14 д, 28 д
HITS = (2000, 10000)                 # правило «за попаданием»: пороги публичного счётчика
REAL_SHARE_MIN = 0.30                # доля настоящих просмотров, при которой ролик засчитывается
LAG_H = 2                            # аналитика отстаёт: срез берём не раньше чем через 2 часа после возраста
ANALYTICS_LAG_H = 72
PUBLIC_WINDOW_H = 6                 # задержка 2 ч + период опроса 4 ч

def _table():
    c = db.conn()
    c.execute("""CREATE TABLE IF NOT EXISTS snapshots(
        video_id TEXT, age_h INTEGER, taken TEXT, data TEXT, PRIMARY KEY(video_id, age_h))""")
    c.commit(); return c

def have(vid: str) -> set:
    c = _table()
    try:
        return {r["age_h"] for r in c.execute("SELECT age_h, data FROM snapshots WHERE video_id=?", (vid,))
                if json.loads(r["data"]).get("complete") is True}
    finally: c.close()


def snapshot_quality(data, h):
    age = data.get("age_h_real")
    return (data.get("complete") is True and data.get("public_views") is not None
            and isinstance(age, (int, float)) and h <= age <= h + PUBLIC_WINDOW_H)

def rows(vid: str) -> list[dict]:
    c = _table()
    try:
        return [{"age_h": r["age_h"], "taken": r["taken"], **json.loads(r["data"])}
                for r in c.execute("SELECT * FROM snapshots WHERE video_id=? ORDER BY age_h", (vid,))]
    finally: c.close()

def _published_at(y, yid: str) -> datetime | None:
    r = y.videos().list(part="snippet,status", id=yid).execute().get("items") or []
    if not r: return None
    s = r[0]["status"]
    if s.get("privacyStatus") != "public": return None      # ещё не вышел — возраст считать не от чего
    t = r[0]["snippet"]["publishedAt"].replace("Z", "+00:00")
    return datetime.fromisoformat(t)

def _query(ya, yid: str, start: str, end: str) -> dict:
    base = dict(ids="channel==MINE", startDate=start, endDate=end, filters=f"video=={yid}")
    out = {}
    def q(key, **kw):
        try:
            r = ya.reports().query(**base, **kw).execute()
            cols = [c["name"] for c in r["columnHeaders"]]
            out[key] = [dict(zip(cols, row)) for row in (r.get("rows") or [])]
        except Exception as e:
            out[key] = []; out.setdefault("errors", []).append(f"{key}: {str(e)[:120]}")
    q("totals", metrics="views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,subscribersGained,likes,comments,shares")
    q("ctr", metrics="impressions,impressionsClickThroughRate")   # показы бывают доступны не всегда и не сразу
    q("traffic", metrics="views,estimatedMinutesWatched", dimensions="insightTrafficSourceType", sort="-views")
    q("country", metrics="views", dimensions="country", sort="-views", maxResults=8)
    q("device", metrics="views", dimensions="deviceType", sort="-views")
    q("retention", metrics="audienceWatchRatio", dimensions="elapsedVideoTimeRatio")
    return out

def take(only: str | None = None, quiet: bool = False) -> list[str]:
    """Берёт все недостающие срезы для всех опубликованных роликов. Возвращает список сделанных срезов."""
    y = yt(); ya = yt("youtubeAnalytics", "v2"); c = _table(); done = []
    vids = [v for st in ("uploaded", "published", "analyzed") for v in db.by_status(st) if v["youtube_id"]]
    if only: vids = [v for v in vids if v["id"] == only]
    now = datetime.now(timezone.utc)
    for v in vids:
        try: pub = _published_at(y, v["youtube_id"])
        except Exception: traceback.print_exc(); continue
        if not pub: continue
        age = (now - pub).total_seconds() / 3600
        got = have(v["id"])
        for h in AGES_H:
            if h in got or age < h + LAG_H: continue
            old = c.execute("SELECT taken, data FROM snapshots WHERE video_id=? AND age_h=?", (v["id"], h)).fetchone()
            previous = json.loads(old["data"]) if old else {}
            data = _query(ya, v["youtube_id"], pub.date().isoformat(), (pub + timedelta(hours=h)).date().isoformat())
            data["published_at"] = pub.isoformat(); data["title"] = v["title"]; data["youtube_id"] = v["youtube_id"]
            if previous.get("public_views") is not None:
                for key in ("public_views", "age_h_real", "public_taken_at"):
                    if key in previous: data[key] = previous[key]
            else:
                try:
                    data["public_views"] = public(y, [v["youtube_id"]]).get(v["youtube_id"])
                    data["age_h_real"] = round(age, 1)
                    data["public_taken_at"] = now.isoformat()
                except Exception as e: print("[metrics] публичный счётчик:", str(e)[:100], flush=True)
            core_errors = [e for e in data.get("errors", []) if not e.startswith("ctr:")]
            data["complete"] = bool(data.get("totals")) and not core_errors and data.get("public_views") is not None and age >= h + ANALYTICS_LAG_H
            data["analytics_updated_at"] = now.isoformat()
            data["public_on_time"] = isinstance(data.get("age_h_real"), (int, float)) and h <= data["age_h_real"] <= h + PUBLIC_WINDOW_H
            data["analytics_window"] = "calendar_dates"
            with c: c.execute("INSERT OR REPLACE INTO snapshots VALUES(?,?,?,?)",
                              (v["id"], h, old["taken"] if old else now.isoformat(), json.dumps(data, ensure_ascii=False)))
            done.append(f"{v['id']} @{h}ч")
            t = (data.get("totals") or [{}])[0]
            print(f"[metrics] {v['id']} {h}ч: просмотров {t.get('views', 0)}, средний просмотр {t.get('averageViewDuration', 0)} с, "
                  f"подписок {t.get('subscribersGained', 0)}", flush=True)
        if v["status"] == "uploaded" and age > 1: db.update(v["id"], "published")
    # 29.09 STRATEGY.md: срезы в Telegram по одному не уходят — раз в неделю приходит таблица (weekly_tick)
    c.close()
    return done

def public(y, yids: list[str]) -> dict:
    """Публичный счётчик просмотров по id роликов."""
    out = {}
    for i in range(0, len(yids), 50):
        for it in y.videos().list(part="statistics", id=",".join(yids[i:i + 50])).execute().get("items", []):
            out[it["id"]] = int(it["statistics"].get("viewCount") or 0)
    return out

def block_videos() -> list[dict]:
    """Длинные ролики блока: у темы есть серия (orchestrator/series.py), ролик загружен."""
    out = [v for st in ("uploaded", "published", "analyzed") for v in db.by_status(st)
           if v["youtube_id"] and ((v["payload"].get("topic") or {}).get("series")) and not str(v["id"]).endswith("__es")]
    return sorted(out, key=lambda v: v["publish_at"] or "")

def block_rows() -> list[dict]:
    """Срезы 7, 14 и 28-го дня роликов блока одной строкой на ролик."""
    c = _table(); out = []
    for n, v in enumerate(block_videos(), 1):
        snaps = {r["age_h"]: json.loads(r["data"]) for r in c.execute("SELECT age_h, data FROM snapshots WHERE video_id=?", (v["id"],))}
        row = {"n": n, "id": v["id"], "title": v["title"], "series": (v["payload"].get("topic") or {}).get("series"), "publish_at": v["publish_at"]}
        for h, k in ((168, "d7"), (336, "d14"), (672, "d28")):
            d = snaps.get(h)
            if not d: continue
            t = (d.get("totals") or [{}])[0]
            rel = next((x for x in d.get("traffic") or [] if x.get("insightTrafficSourceType") == "RELATED_VIDEO"), {})
            pub, real = d.get("public_views"), int(t.get("views") or 0)
            row[k] = {"public": pub, "real": real, "min": int(t.get("estimatedMinutesWatched") or 0), "subs": int(t.get("subscribersGained") or 0),
                      "rel_min": round(float(rel["estimatedMinutesWatched"]) / float(rel["views"]), 1) if rel.get("views") else None,
                      "quality": snapshot_quality(d, h),
                      "counts": snapshot_quality(d, h) and bool(pub) and real >= REAL_SHARE_MIN * pub}
        out.append(row)
    c.close()
    return out

def weekly_text() -> str:
    rows = block_rows()
    if not rows: return "Таблица блока: роликов блока с возрастом от 7 дней пока нет."
    out = ["Таблица блока 1 (длинные ролики; счётчик / настоящие просмотры / минуты / минут на зрителя из «похожих» / подписки)"]
    for r in rows:
        cells = []
        for k, name in (("d7", "7 д"), ("d14", "14 д"), ("d28", "28 д")):
            x = r.get(k)
            if x: cells.append(f"{name}: {x['public'] if x['public'] is not None else '—'} / {x['real']} / {x['min']} / {x['rel_min'] if x['rel_min'] is not None else '—'} / {x['subs']}"
                               + (" (срез неполный или счётчик снят с опозданием)" if not x["quality"] else "" if x["counts"] or k != "d14" else " (не засчитан: настоящих меньше 30%)"))
        out.append(f"№{r['n']} [{r['series']}] {str(r['title'])[:48]}\n   " + ("; ".join(cells) if cells else "младше 7 дней"))
    d14 = sorted(r["d14"]["public"] for r in rows if r.get("d14") and r["d14"]["counts"] and r["d14"]["public"] is not None)
    from statistics import median
    if d14: out.append(f"Засчитано роликов на 14-й день: {len(d14)}, медиана счётчика {median(d14):g}.")
    out.append("Решения по таблице не принимаются, кроме правила «за попаданием». Разбор — 24.11.2026.")
    return "\n".join(out)

def weekly_tick():
    """Раз в неделю, в понедельник после 10:00 по Москве, — таблица блока в Telegram."""
    from zoneinfo import ZoneInfo
    now = datetime.now(ZoneInfo("Europe/Moscow"))
    if now.weekday() != 0 or now.hour < 10: return
    flag = config.DATA / "metrics_weekly.json"; week = now.strftime("%G-W%V")
    try: last = json.loads(config.read(flag)).get("week") if flag.exists() else None
    except Exception: last = None
    if last == week: return
    if not block_videos(): return
    if telegram.send(weekly_text()).get("ok") is True:
        config.write(flag, json.dumps({"week": week, "sent": now.isoformat()}))

def hit_check():
    """Правило «за попаданием» (STRATEGY.md, раздел 6): ролик блока достиг 2 000 или 10 000 по публичному счётчику — сообщение владельцу.
    Очередь сама не переставляется: слоты отдаются продолжениям серии после ответа владельца."""
    vids = [v for v in block_videos() if v["status"] != "uploaded" or (v["publish_at"] or "") < datetime.now(timezone.utc).isoformat()]
    if not vids: return
    y = yt(); now = public(y, [v["youtube_id"] for v in vids])
    for v in vids:
        n = now.get(v["youtube_id"], 0); told = set(v["payload"].get("hit_told") or [])
        new = [h for h in HITS if n >= h and h not in told]
        if not new: continue
        real = None
        try:
            pub = _published_at(y, v["youtube_id"])
            r = yt("youtubeAnalytics", "v2").reports().query(ids="channel==MINE", startDate=pub.date().isoformat(), endDate=datetime.now(timezone.utc).date().isoformat(),
                                                          metrics="views", filters=f"video=={v['youtube_id']}").execute()
            real = int((r.get("rows") or [[0]])[0][0])
        except Exception as e: print("[metrics] настоящие просмотры:", str(e)[:100], flush=True)
        if real is None or real < REAL_SHARE_MIN * n: continue
        h = max(new); ser = (v["payload"].get("topic") or {}).get("series")
        share = f"{real} ({real / n * 100:.0f}% счётчика; аналитика отстаёт на 2–3 дня, доля может вырасти)" if real is not None else "пока нет данных"
        rule = ("все оставшиеся слоты блока отдаются этой серии" if h >= 10000 else "два ближайших свободных слота отдаются продолжениям той же серии")
        sent = telegram.send(f"🎯 Правило «за попаданием»: `{v['id']}`\n«{v['title']}» — {n} просмотров по счётчику (порог {h}).\n"
                      f"Настоящих просмотров: {share}. Правило действует при доле от 30%.\nСерия {ser}: {rule}. Это исполнение плана, а не смена курса.")
        if sent.get("ok") is True:
            db.update(v["id"], payload={"hit_told": sorted(told | set(new))})

def uploads() -> list[dict]:
    """Все свои ролики: id, название, длительность в секундах, дата публикации."""
    import re
    y = yt(); ch = y.channels().list(part="contentDetails", mine=True).execute()["items"][0]
    up = ch["contentDetails"]["relatedPlaylists"]["uploads"]; tok = None; ids = []
    while True:
        r = y.playlistItems().list(part="snippet", playlistId=up, maxResults=50, pageToken=tok).execute()
        ids += [it["snippet"]["resourceId"]["videoId"] for it in r.get("items", [])]
        tok = r.get("nextPageToken")
        if not tok: break
    out = []
    for i in range(0, len(ids), 50):
        for it in y.videos().list(part="snippet,status,contentDetails", id=",".join(ids[i:i + 50])).execute().get("items", []):
            m = re.match(r"PT(?:(\d+)M)?(?:(\d+)S)?", it["contentDetails"]["duration"])
            out.append({"id": it["id"], "title": it["snippet"]["title"], "privacy": it["status"]["privacyStatus"],
                        "sec": int(m.group(1) or 0) * 60 + int(m.group(2) or 0) if m else 0,
                        "at": it["status"].get("publishAt") or it["snippet"]["publishedAt"]})
    return out

def backfill_ids() -> int:
    """Recover only an unambiguous exact title or durable upload receipt."""
    import json
    mine = uploads()
    taken = {r["youtube_id"] for r in db.conn().execute("SELECT youtube_id FROM videos WHERE youtube_id IS NOT NULL")}
    n = 0
    for st in ("uploaded_manual", "uploaded", "published", "analyzed", "qc_passed", "approved_final", "rendered"):
        for v in db.by_status(st):
            if v["youtube_id"] or not v["title"]: continue
            t = v["title"].strip().lower()
            receipt = db.video_dir(v["id"]) / "final.mp4.upload.json"
            if receipt.exists():
                saved = json.loads(config.read(receipt))
                if saved.get("state") == "pending": continue  # ambiguous completion needs owner reconciliation
                yid = saved.get("youtube_id")
                if not any(u["id"] == yid for u in mine) or yid in taken: continue
            else:
                cand = [u for u in mine if u["id"] not in taken and u["title"].strip().lower() == t]
                yid = cand[0]["id"] if len(cand) == 1 else None
            if not yid: continue
            u = next((x for x in mine if x["id"] == yid), {})
            db.update(v["id"], "published" if u.get("privacy") == "public" else None,
                      youtube_id=yid, publish_at=(u.get("at") or "").replace("Z", "+00:00") or None)
            taken.add(yid); n += 1; print(f"[metrics] {v['id']} → {yid} ({u.get('title', '')[:50]})")
    return n

def table() -> str:
    """Компактная сводка всех срезов: по ней видно, что меняется от ролика к ролику в одном возрасте."""
    c = _table(); out = []
    for r in c.execute("SELECT * FROM snapshots ORDER BY video_id, age_h"):
        d = json.loads(r["data"]); t = (d.get("totals") or [{}])[0]; ctr = (d.get("ctr") or [{}])[0]
        src = ", ".join(f"{x['insightTrafficSourceType'].lower()} {x['views']}" for x in (d.get("traffic") or [])[:3])
        out.append(f"{r['video_id'][:24]:24} {r['age_h']:>4}ч  просм {t.get('views', 0):>5}  ср.просмотр {t.get('averageViewDuration', 0):>4} с  "
                   f"показы {ctr.get('impressions', '—')}  CTR {ctr.get('impressionsClickThroughRate', '—')}  подп {t.get('subscribersGained', 0):>3}  [{src}]")
    return "\n".join(out) or "(срезов пока нет)"
