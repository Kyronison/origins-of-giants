"""YouTube Data API: длинное видео в ближайший слот, Shorts — по одному в день после.

Квота API — 10 000 единиц/сутки, каждая загрузка стоит 1 600: длинное + 3 Shorts = 6 400.
Два видео в один день через API не пройдут — очередь подхватит второе на следующем часовом запуске после сброса квоты.
UPLOAD_MODE=manual: этап только готовит upload.txt и ждёт `link <id> <youtube_id>` от владельца
(нужно, пока API-проект не прошёл YouTube compliance audit — иначе ролики, залитые через API, остаются private)."""
import json, os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from .. import db, telegram, config

SCOPES = ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube",
          "https://www.googleapis.com/auth/youtube.force-ssl",   # комментарии от канала (оба токена переизданы 23.09)
          "https://www.googleapis.com/auth/yt-analytics.readonly",
          "https://www.googleapis.com/auth/yt-analytics-monetary.readonly"]   # estimatedRevenue в аналитике
TOKEN = config.DATA / "youtube_token.json"
ET = ZoneInfo("America/New_York")

def auth():
    secret = os.getenv("YOUTUBE_CLIENT_SECRET_FILE", "data/youtube_client_secret.json")
    if not os.path.exists(secret): raise FileNotFoundError(f"Нет файла OAuth-клиента: {secret}")
    flow = InstalledAppFlow.from_client_secrets_file(secret, SCOPES)
    creds = flow.run_local_server(port=0)
    config.DATA.mkdir(parents=True, exist_ok=True); config.write(TOKEN, creds.to_json())
    print("Токен сохранён:", TOKEN)

def gbuild(api: str, ver: str, creds):
    """Клиент Google API. Если задан GOOGLE_PROXY (порт Happ/xray, владелец 06.10) и порт отвечает — через него:
    DNS и TLS к googleapis делает VPS владельца, ночные «Unable to find the server at oauth2.googleapis.com» уходят.
    Порт не отвечает — напрямую, как раньше (VPN не трогаем)."""
    px = os.getenv("GOOGLE_PROXY", "").strip()
    if px:
        import socket, httplib2, google_auth_httplib2
        from urllib.parse import urlparse
        u = urlparse(px)
        try:
            socket.create_connection((u.hostname, u.port), timeout=3).close()
            http = httplib2.Http(timeout=600, proxy_info=httplib2.ProxyInfo(httplib2.socks.PROXY_TYPE_HTTP, u.hostname, u.port))
            http.redirect_codes = http.redirect_codes - {308}   # 308 = Resume Incomplete возобновляемой загрузки, не редирект
            return build(api, ver, http=google_auth_httplib2.AuthorizedHttp(creds, http=http), cache_discovery=False)
        except OSError as e:
            print(f"[google] прокси {px} не отвечает ({e}) — напрямую", flush=True)
    return build(api, ver, credentials=creds)

def yt(api="youtube", ver="v3"):
    if not TOKEN.exists(): raise RuntimeError("Нет data/youtube_token.json — запусти auth-youtube")
    return gbuild(api, ver, Credentials.from_authorized_user_file(str(TOKEN), SCOPES))

def _is_english_publication(row) -> bool:
    """Recognize both Spanish pipelines without consuming their calendar dates.

    Legacy English records have no language field. Keep reserving their dates
    unless the record explicitly belongs to a localization or the Spanish lane.
    """
    if (row["status"] or "").startswith(("es_", "localized")) or row["id"].endswith("__es"):
        return False
    try:
        payload = json.loads(row["payload"] or "{}")
    except (TypeError, ValueError):
        return True  # malformed legacy metadata must not free an English slot
    if not isinstance(payload, dict): return True
    topic = payload.get("topic") or {}
    script = payload.get("script") or {}
    if payload.get("es_only_skip") or (isinstance(topic, dict) and topic.get("es_only")):
        return False
    languages = [payload.get("lang")]
    if isinstance(script, dict): languages.append(script.get("lang"))
    if isinstance(topic, dict): languages.append(topic.get("lang_target"))
    return not any(lang and str(lang).lower().split("-")[0] != "en" for lang in languages)


def next_slot(lead_h: float = 12) -> datetime:
    """Следующий слот сетки: вечер US East (с учётом DST) в дни PUBLISH_WEEKDAYS_ET, не раньше чем через lead_h часов
    и не раньше PUBLISH_NOT_BEFORE. В один день по времени US East выходит один ролик (STRATEGY.md, раздел 6)."""
    c = db.conn()
    try:
        taken = {r["publish_at"] for r in c.execute("SELECT id, status, payload, publish_at FROM videos WHERE publish_at IS NOT NULL")
                 if _is_english_publication(r)}
    finally:
        c.close()
    days = set()
    for iso in taken:
        try: days.add(datetime.fromisoformat(iso).astimezone(ET).date())
        except Exception: pass
    now = datetime.now(timezone.utc); floor = now + timedelta(hours=lead_h)
    if config.PUBLISH_NOT_BEFORE:
        try: floor = max(floor, datetime.fromisoformat(config.PUBLISH_NOT_BEFORE.replace("Z", "+00:00")))
        except ValueError: print("[upload] PUBLISH_NOT_BEFORE не разобран: " + config.PUBLISH_NOT_BEFORE, flush=True)
    t = now.astimezone(ET).replace(hour=config.PUBLISH_HOUR_ET, minute=0, second=0, microsecond=0)
    while (t < floor or t.astimezone(timezone.utc).isoformat() in taken or t.date() in days
           or (config.PUBLISH_WEEKDAYS_ET and t.weekday() not in config.PUBLISH_WEEKDAYS_ET)):
        t += timedelta(days=1)
    return t.astimezone(timezone.utc)

def _guard(d):
    """Перед загрузкой: файл на месте, не обрезок, комплект публикации собран. Квота API — 1 600 единиц на ролик,
    повторная загрузка того же файла стоит ещё столько же, поэтому проверяем до, а не после."""
    f = d / "final.mp4"
    if not f.exists(): raise FileNotFoundError("нет final.mp4 — рендер не доехал")
    if f.stat().st_size < 20 * 1024 * 1024: raise ValueError(f"final.mp4 всего {f.stat().st_size / 1e6:.1f} МБ — похоже на обрезок")
    for name in ("title.txt", "description.txt", "tags.txt"):
        if not (d / "publish" / name).exists(): raise FileNotFoundError("нет комплекта публикации: publish/" + name)

class UploadLimit(Exception):
    """Канал исчерпал дневной лимит загрузок YouTube. Повторять раньше следующих суток бессмысленно:
    файл уходит на сервер целиком и только потом отклоняется (20.09: 5 ГБ впустую)."""

def _once(y, key: str, done: dict, body: dict, path) -> str:
    """Идемпотентная загрузка: один файл — одна загрузка. Если этап падал после видео, но до шортсов,
    повтор не создаёт второй копии на канале."""
    if done.get(key): print("[upload] " + key + " уже загружен: " + done[key], flush=True); return done[key]
    from pathlib import Path
    path = Path(path)
    receipt = path.with_name(path.name + ".upload.json")
    if receipt.exists():
        saved = json.loads(config.read(receipt))
        if saved.get("youtube_id"):
            done[key] = saved["youtube_id"]
            if saved.get("publish_at"): body.setdefault("status", {})["publishAt"] = saved["publish_at"]
            return saved["youtube_id"]
        if saved.get("state") == "pending":
            raise RuntimeError(f"Результат прошлой загрузки {key} неизвестен. Сверьте ролик в Studio и привяжите id командой link; повторная загрузка заблокирована")
    def save_receipt(data):
        tmp = receipt.with_suffix(receipt.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
            f.flush(); os.fsync(f.fileno())
        tmp.replace(receipt)
    import time, random
    sn = body.get("snippet") or {}   # страховка по лимитам YouTube: 100 знаков заголовок, 5000 описание, 500 на все теги
    if sn.get("title"): sn["title"] = sn["title"][:100]
    if sn.get("description") and len(sn["description"]) > 5000:
        print(f"[upload] описание {len(sn['description'])} знаков — режу до 5000", flush=True)
        sn["description"] = sn["description"][:4997].rsplit("\n", 1)[0]
    tg, total = [], 0
    for t in (sn.get("tags") or []):
        if total + len(t) + 1 > 480: break
        tg.append(t); total += len(t) + 1
    if tg: sn["tags"] = tg
    req = y.videos().insert(part="snippet,status", body=body, media_body=MediaFileUpload(str(path), chunksize=16 * 1024 * 1024, resumable=True))
    save_receipt({"state": "pending", "file": path.name, "started_at": datetime.now(timezone.utc).isoformat()})
    r, err, last = None, 0, -1
    while r is None:   # возобновляемая сессия: обрыв сети (SSL EOF, сброс соединения через VPN) — повтор того же куска, не новая загрузка (23.09)
        try:
            st, r = req.next_chunk(num_retries=3); err = 0
            if st and int(st.progress() * 10) != last: last = int(st.progress() * 10); print(f"[upload] {key}: {st.progress() * 100:.0f}%", flush=True)
        except Exception as e:
            if "uploadLimitExceeded" in str(e) or "exceeded the number of videos" in str(e):
                save_receipt({"state": "rejected", "reason": "uploadLimitExceeded"})
                raise UploadLimit(str(e)[:200]) from e
            code = getattr(getattr(e, "resp", None), "status", None)
            if code and 400 <= code < 500 and code not in (408, 429):   # 25.09: повторять отказ по метаданным бессмысленно —
                raise RuntimeError(f"YouTube отклонил запрос ({code}): {str(e)[:400]}") from e   # 34 повтора одного и того же 400
            err += 1; print(f"[upload] {key}: обрыв ({err}): {str(e)[:100]}", flush=True)
            if err > 40: raise
            time.sleep(min(90, 5 * err) + random.random() * 3)
    save_receipt({"state": "complete", "youtube_id": r["id"], "publish_at": body.get("status", {}).get("publishAt")})
    done[key] = r["id"]; return r["id"]

def _taken_shorts() -> set:
    """Уже занятые слоты шортсов по всей очереди: при ежедневном выпуске шортсы разных роликов иначе сталкиваются."""
    out = set()
    for r in db.conn().execute("SELECT payload FROM videos WHERE payload LIKE '%shorts_schedule%'"):
        try: sched = (json.loads(r["payload"]) or {}).get("shorts_schedule") or {}
        except Exception: continue
        for iso in sched.values():
            try: out.add(datetime.fromisoformat(iso).astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0))
            except Exception: pass
    return out

def _short_slot(slot: datetime, i: int, taken: set | None = None, video_days: set | None = None) -> datetime:
    """Слот шортса по сетке SHORT_HOURS_ET (утро и вечер США, владелец 26.09), не раньше SHORT_DAYS[i]-х суток после ролика.
    Слоты разных роликов не пересекаются; у одного ролика — не больше одного шортса в сутки (video_days — его занятые даты ET)."""
    taken = _taken_shorts() if taken is None else taken
    video_days = set() if video_days is None else video_days
    days = config.SHORT_DAYS[i] if i < len(config.SHORT_DAYS) else (config.SHORT_DAYS[-1] + 2 * (i - len(config.SHORT_DAYS) + 1))
    hours = sorted(config.SHORT_HOURS_ET or [config.SHORT_HOUR_ET])
    base = (slot.astimezone(ET) + timedelta(days=days)).date()
    now = datetime.now(timezone.utc)
    for k in range(90):
        day = base + timedelta(days=k)
        if day in video_days: continue
        for h in hours:
            u = datetime(day.year, day.month, day.day, h, tzinfo=ET).astimezone(timezone.utc)
            if u in taken or u < now + timedelta(minutes=20): continue
            taken.add(u); video_days.add(day)
            return u
    raise RuntimeError("свободного слота для шортса нет на 90 дней вперёд")

def run(vid: str):
    v = db.get(vid); d = db.video_dir(vid); meta = json.loads(config.read(d / "meta.json"))
    from .. import gates
    gates.require_upload(v, d)
    # The approved master is ready to upload: use the same one-hour margin as
    # late-slot recovery. Manual preparation retains the twelve-hour lead.
    slot = next_slot(lead_h=12 if config.UPLOAD_MODE == "manual" else 1)
    if config.UPLOAD_MODE == "manual": return _manual(vid, d, meta, slot)
    _guard(d)
    hold = float(v["payload"].get("upload_hold_until") or 0)
    if hold > datetime.now(timezone.utc).timestamp():   # дневной лимит канала: повтор гонит те же гигабайты впустую
        left = (hold - datetime.now(timezone.utc).timestamp()) / 3600
        print(f"[upload] лимит загрузок YouTube: жду ещё {left:.1f} ч", flush=True); return
    if (v["payload"].get("topic") or {}).get("es_only"):   # тема испанской очереди: английская версия — только сырьё для локализации
        db.update(vid, "uploaded", payload={"uploads": {}, "es_only_skip": True}); print(f"[upload] {vid}: es-only — на английский канал не грузим", flush=True); return
    y = yt(); done = dict(v["payload"].get("uploads") or {})
    if v["youtube_id"]: done.setdefault("final.mp4", v["youtube_id"])
    if v["publish_at"]:
        from datetime import datetime as _dt
        try: slot = _dt.fromisoformat(v["publish_at"])   # повтор этапа не переносит уже назначенную дату
        except ValueError: pass
    if slot < datetime.now(timezone.utc) + timedelta(minutes=20):   # 29.09 STRATEGY.md: опоздавший ролик выходит в следующий слот сетки, а не «через полчаса»
        slot = next_slot(lead_h=1)
        print(f"[upload] {vid}: назначенное время прошло — следующий слот сетки {slot:%d.%m %H:%M} UTC", flush=True)
    body = {"snippet": {"title": meta["titles"][0], "description": meta["description"], "tags": meta["tags"],
                        "categoryId": "28", "defaultLanguage": "en", "defaultAudioLanguage": "en"},
            "status": {"privacyStatus": "private", "publishAt": slot.isoformat(), "selfDeclaredMadeForKids": False,
                       "containsSyntheticMedia": False}}   # владелец 20.09: плашку «Altered content» не ставим
    try:
        yid = _once(y, "final.mp4", done, body, d / "final.mp4")
        slot = datetime.fromisoformat(body["status"]["publishAt"])
    except UploadLimit as e:
        until = datetime.now(timezone.utc) + timedelta(hours=6)
        db.update(vid, payload={"upload_hold_until": until.timestamp()})
        telegram.send(f"YouTube не принял `{vid}`: дневной лимит загрузок канала исчерпан.\n"
                      f"Файл готов и лежит на диске, повторю сам после {until.astimezone(ET):%H:%M} ET "
                      f"(через 6 часов). Раньше пробовать бессмысленно — 5 ГБ уходят впустую.")
        print(f"[upload] лимит загрузок YouTube: пауза до {until:%H:%M} UTC", flush=True)
        return
    db.update(vid, youtube_id=yid, publish_at=slot.isoformat(), payload={"uploads": done})   # сохраняем id сразу: падение ниже не приведёт ко второй загрузке
    r = {"id": yid}
    url = f"https://www.youtube.com/watch?v={yid}"
    thumb_note = ""
    thumb = next((p for p in (d / "publish" / "thumbnail_2560.jpg", d / "thumb_2560.png", d / "thumb_a.png") if p.exists()), None)
    if thumb:
        try: y.thumbnails().set(videoId=r["id"], media_body=MediaFileUpload(str(thumb))).execute()
        except Exception as e: thumb_note = "\nПревью не встало (дневной лимит канала?): " + str(e)[:120]
    try:   # плейлист канала — только длинные ролики
        pls = y.playlists().list(part="snippet", mine=True, maxResults=25).execute().get("items", [])
        pl = next((x["id"] for x in pls if "documentar" in x["snippet"]["title"].lower()), None)
        if pl: y.playlistItems().insert(part="snippet", body={"snippet": {"playlistId": pl, "resourceId": {"kind": "youtube#video", "videoId": r["id"]}}}).execute()
    except Exception as e: print("[upload] плейлист: " + str(e)[:120])
    shorts = []
    taken_shorts = _taken_shorts(); sched = dict(v["payload"].get("shorts_schedule") or {}); vdays = set()
    for i, f in enumerate(sorted((d / "shorts").glob("short_*.mp4"))):
        sm = d / "shorts" / ("s" + f.stem.split("_")[-1]) / "meta.json"   # своё название и описание шортса (stages/shorts.py)
        m = json.loads(config.read(sm)) if sm.exists() else {}
        title = (m.get("title") or meta["titles"][0] + " #Shorts")[:100]
        head = (m.get("description") or meta["description"].split("\n\n")[0]).split("\n\nPhotos:")[0]
        desc = "Full story: " + url + "\n\n" + head + "\n\nFull documentary on this channel:\n\"" + meta["titles"][0] + "\"\n" + url + "\n\n#Shorts"   # ссылка первой строкой — видна без «ещё» (23.09)
        sb = {"snippet": {"title": title, "description": desc, "tags": meta["tags"][:10], "categoryId": "28",
                          "defaultLanguage": "en", "defaultAudioLanguage": "en"},
              # ритм шортсов (26.09): два слота в день — утро и вечер США, не раньше +1/+2/+4 суток после ролика
              "status": {"privacyStatus": "private", "publishAt": _short_slot(slot, i, taken_shorts, vdays).isoformat(),
                         "selfDeclaredMadeForKids": False, "containsSyntheticMedia": False}}
        if f.name in done and f.name in sched:   # уже загружен при прошлой попытке — слот не пересчитываем
            shorts.append(done[f.name]); continue
        sched[f.name] = sb["status"]["publishAt"]
        try:
            shorts.append(_once(y, f.name, done, sb, f))
        except UploadLimit:   # 26.09 Copart: лимит на третьем шортсе — ждём 6 ч, а не падаем с сообщением раз в час
            sched.pop(f.name, None)
            db.update(vid, payload={"uploads": done, "shorts_schedule": sched, "upload_hold_until": datetime.now(timezone.utc).timestamp() + 6 * 3600})
            telegram.send(f"`{vid}`: ролик загружен, но {f.name} упёрся в дневной лимит YouTube — догружу сам через 6 часов.")
            print(f"[upload] {f.name}: дневной лимит — пауза 6 ч", flush=True); return
        db.update(vid, payload={"uploads": done, "shorts_schedule": sched})
    for card in (d / "publish").glob("short_*.txt"):   # в карточках — настоящая ссылка вместо заглушки
        config.write(card, config.read(card).replace("ССЫЛКА_НА_РОЛИК", url))
    db.update(vid, "uploaded", youtube_id=r["id"], publish_at=slot.isoformat(), payload={"shorts_ids": shorts, "uploads": done})
    try:   # 06.10 владелец: моушен-шортсы ролика — по три в день, с суток после выхода; грузит motion_shorts.upload_tick в цикле watch
        from . import motion_shorts; motion_shorts.enqueue_new(vid, slot)
    except Exception as e: print("[upload] моушен-шортсы в очередь: " + str(e)[:160], flush=True)
    msk = slot.astimezone(ZoneInfo("Europe/Moscow")).strftime("%d.%m %H:%M")   # 29.09: через часовой пояс — после перевода часов в США разница 8 ч, а не 7
    telegram.send(f"Загружено приватным, выйдет {slot.astimezone(ET):%d.%m %H:%M} ET ({msk} МСК): {url}\n"
                  f"Шортсов: {len(shorts)} — по одному в следующие дни.{thumb_note}\nПроверь в Studio и подтверди публикацию.")

def _short_hooks(p: dict, vid: str) -> dict:
    """youtube_id шортса → его фраза-крючок (описание шортса из meta.json без строки фото)."""
    out = {}; up = p.get("uploads") or {}; q = p.get("motion_queue") or {}
    for key, sid in up.items():
        meta = None
        if key.startswith("motion:") and key[len("motion:"):] in q: meta = q[key[len("motion:"):]].get("meta")
        elif key.startswith("short_") and key.endswith(".mp4"): meta = str(db.video_dir(vid) / "shorts" / ("s" + key[:-4].split("_")[-1]) / "meta.json")
        try: out[sid] = (json.loads(config.read(meta)).get("description") or "").split("\n\nPhotos:")[0].strip() if meta else ""
        except Exception: out[sid] = ""
    return out

def short_comment(p: dict, sid: str, title: str, url: str, vid: str = "") -> str:
    """Владелец 06.10: комментарий под шортсом — его крючок с #shorts, затем полный ролик и ссылка (образец In-N-Out)."""
    hook = _short_hooks(p, vid).get(sid, "")
    if hook and "#shorts" not in hook.lower(): hook += " #shorts"
    return (hook + "\n\n" if hook else "") + "Full documentary on this channel:\n\"" + title + "\"\n" + url + "\n\n#Shorts"

def short_comments_tick():
    """Комментарий канала со ссылкой на полный ролик под каждым вышедшим шортсом (концовка шортса: «link in comments», 23.09).
    Под приватным/отложенным шортсом YouTube отвечает 403 — поэтому только после слота публикации, из цикла watch."""
    now = datetime.now(timezone.utc); y = None
    for r in db.conn().execute("SELECT id, title, youtube_id, payload FROM videos WHERE youtube_id IS NOT NULL AND payload LIKE '%shorts_ids%'"):
        p = json.loads(r["payload"]) if isinstance(r["payload"], str) else (r["payload"] or {})
        ids = [s for s in (p.get("shorts_ids") or []) if s]; done = list(p.get("shorts_link_comments") or []); sched = p.get("shorts_schedule") or {}
        todo = [s for s in ids if s not in done]
        if not todo: continue
        slots = sorted(datetime.fromisoformat(v) for v in sched.values()) if sched else []
        if slots and slots[0] > now: continue   # ни один шортс ещё не вышел
        try: y = y or yt()
        except Exception as e: print("[shorts] комментарии: " + str(e)[:100], flush=True); return
        url = f"https://www.youtube.com/watch?v={r['youtube_id']}"; changed = False
        for sid in todo:
            try:
                st = y.videos().list(part="status", id=sid).execute().get("items") or []
                if not st: done.append(sid); changed = True; continue   # шортс удалён
                if st[0]["status"]["privacyStatus"] != "public": continue
                have = y.commentThreads().list(part="snippet", videoId=sid, maxResults=50).execute().get("items", [])
                if any(url in (t["snippet"]["topLevelComment"]["snippet"].get("textOriginal") or "") for t in have):
                    done.append(sid); changed = True   # комментарий уже есть (запись могла не сохраниться) — не дублируем
                    print(f"[shorts] под {sid} комментарий уже есть — помечаю сделанным", flush=True); continue
                y.commentThreads().insert(part="snippet", body={"snippet": {"videoId": sid, "topLevelComment": {"snippet": {"textOriginal":
                    short_comment(p, sid, r["title"], url, r["id"])}}}}).execute()
                done.append(sid); changed = True; print(f"[shorts] комментарий со ссылкой под {sid}", flush=True)
                db.update(r["id"], payload={"shorts_link_comments": done})   # пишем СРАЗУ, а не в конце цикла
            except Exception as e: print(f"[shorts] комментарий под {sid}: {str(e)[-120:]}", flush=True)
        if changed: db.update(r["id"], payload={"shorts_link_comments": done})

def _manual(vid: str, d, meta: dict, slot: datetime):
    txt = (f"TITLE\n{meta['titles'][0]}\n\nALT TITLES (A/B)\n" + "\n".join(meta["titles"][1:]) +
           f"\n\nDESCRIPTION\n{meta['description']}\n\nTAGS\n{', '.join(meta['tags'])}\n\n"
           f"SCHEDULE: {slot.astimezone(ET):%Y-%m-%d %H:%M} ET\nCategory: Science & Technology\n"
           f"Altered or synthetic content: NO\nMade for kids: NO\nThumbnail: thumb_a.png\nShorts: shorts/*.mp4 — по одному в день после длинного\n")
    config.write(d / "upload.txt", txt)
    db.update(vid, "uploaded_manual", publish_at=slot.isoformat())
    telegram.send(f"Ручная загрузка `{vid}`: final.mp4, thumb_a.png, shorts/ и upload.txt в папке видео.\n"
                  f"После публикации: `python -m orchestrator.main link {vid} <youtube_id>`", file=d / "upload.txt")
