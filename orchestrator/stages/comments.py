"""Комментарий канала под каждым вышедшим длинным роликом (владелец 14.10.2026: «под видео везде стоят комментарии» — проверка нашла 12
английских лонгов и все испанские без нашего комментария). Текст — publish/pinned_comment.txt из комплекта ролика (факт + вопрос зрителям,
у английских — ещё источники). Под закрытым/отложенным роликом YouTube отвечает 403 — ставим после выхода, из цикла watch / watch-es.
Закрепить комментарий через API нельзя — это делается в Studio."""
import json
from datetime import datetime, timezone
from .. import config, db


def _ours(y, cid, vid):
    r = y.commentThreads().list(part="snippet", videoId=vid, maxResults=100).execute()
    return [t for t in r.get("items", []) if (t["snippet"]["topLevelComment"]["snippet"].get("authorChannelId") or {}).get("value") == cid]


def _tick(rows, y):
    now = datetime.now(timezone.utc); cid = None
    for r in rows:
        p = json.loads(r["payload"] or "{}")
        if p.get("long_comment") or not r["youtube_id"]: continue
        if r["publish_at"] and datetime.fromisoformat(r["publish_at"]) > now: continue
        f = config.VIDEOS / r["id"] / "publish" / "pinned_comment.txt"
        if not f.exists(): continue
        try:
            st = y.videos().list(part="status", id=r["youtube_id"]).execute().get("items") or []
            if not st or st[0]["status"]["privacyStatus"] != "public": continue
            cid = cid or y.channels().list(part="id", mine=True).execute()["items"][0]["id"]
            have = _ours(y, cid, r["youtube_id"])
            if have: db.update(r["id"], payload={"long_comment": have[0]["id"]}); continue
            c = y.commentThreads().insert(part="snippet", body={"snippet": {"videoId": r["youtube_id"], "topLevelComment": {"snippet": {
                "textOriginal": f.read_text(encoding="utf-8").strip()[:9500]}}}}).execute()
            db.update(r["id"], payload={"long_comment": c["id"]}); print(f"[comments] комментарий под {r['youtube_id']} ({r['id']})", flush=True)
        except Exception as e: print(f"[comments] {r['id']}: {str(e)[-140:]}", flush=True)


def en_tick():
    from contextlib import closing
    from .upload import yt
    with closing(db.conn()) as c:
        rows = c.execute("SELECT id, youtube_id, publish_at, payload FROM videos WHERE status IN ('uploaded', 'published') AND id NOT LIKE '%__es' "
                         "AND youtube_id IS NOT NULL AND created >= '2026-10-01' AND payload NOT LIKE '%\"long_comment\"%'").fetchall()
    if rows: _tick(rows, yt())


def es_tick():
    from contextlib import closing
    from .localize import _yt
    with closing(db.conn()) as c:
        rows = c.execute("SELECT id, youtube_id, publish_at, payload FROM videos WHERE status IN ('es_uploaded', 'localized_uploaded') "
                         "AND youtube_id IS NOT NULL AND created >= '2026-10-12' AND payload NOT LIKE '%\"long_comment\"%'").fetchall()
    if rows: _tick(rows, _yt("es"))
