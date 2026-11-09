"""Очередь видео. Одна строка = одно видео, движется по статусам."""
import json, sqlite3
from contextlib import closing
from datetime import datetime
from . import config

STAGES = ["idea", "approved_topic", "scripted", "approved_script", "assets", "rendered",
          "qc_passed", "qc_failed", "approved_final", "uploaded_manual", "uploaded", "published", "analyzed", "rejected"]

# что значит «approve» из каждого состояния
APPROVE_NEXT = {"idea": "approved_topic", "scripted": "approved_script",
                "qc_passed": "approved_final", "qc_failed": "approved_final", "approved_final": "approved_final"}

def conn():
    config.DATA.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(config.DATA / "pipeline.db", timeout=30)   # 24.09: без ожидания блокировки записи терялись
    c.row_factory = sqlite3.Row
    try:   # WAL: чтение не блокирует запись, а запись — чтение; иначе watch и разовые скрипты дерутся за базу
        c.execute("PRAGMA journal_mode=WAL"); c.execute("PRAGMA busy_timeout=30000")
    except Exception: pass
    c.execute("""CREATE TABLE IF NOT EXISTS videos(
        id TEXT PRIMARY KEY, slug TEXT, status TEXT, title TEXT,
        payload TEXT, youtube_id TEXT, publish_at TEXT,
        created TEXT, updated TEXT)""")
    return c

def add(slug: str, title: str, payload: dict) -> str:
    vid = f"{datetime.now():%Y-%m-%d}-{slug}"
    with closing(conn()) as c, c:
        c.execute("INSERT OR IGNORE INTO videos VALUES(?,?,?,?,?,?,?,?,?)",
                  (vid, slug, "idea", title, json.dumps(payload, ensure_ascii=False),
                   None, None, datetime.now().isoformat(), datetime.now().isoformat()))
    return vid

def get(vid: str) -> dict:
    with closing(conn()) as c:
        r = c.execute("SELECT * FROM videos WHERE id=?", (vid,)).fetchone()
    if r is None: raise KeyError(f"Видео {vid} нет в очереди")
    d = dict(r); d["payload"] = json.loads(d["payload"] or "{}"); return d

def by_status(status: str) -> list[dict]:
    with closing(conn()) as c:
        rows = c.execute("SELECT id FROM videos WHERE status=? ORDER BY created", (status,)).fetchall()
    return [get(r["id"]) for r in rows]

def update(vid: str, status: str | None = None, *, expected_status=None, **fields):
    """Merge under the write transaction; concurrent workers cannot lose fields."""
    if set(fields) - {"payload", "title", "youtube_id", "publish_at", "slug"}:
        raise ValueError("Неизвестные поля videos")
    patch = fields.pop("payload", {})
    c = conn()
    try:
        c.execute("BEGIN IMMEDIATE")
        row = c.execute("SELECT status, payload FROM videos WHERE id=?", (vid,)).fetchone()
        if row is None: raise KeyError(f"Видео {vid} нет в очереди")
        if expected_status is not None and row["status"] != expected_status:
            raise ValueError(f"Статус {vid} уже изменился: {row['status']}")
        payload = {**json.loads(row["payload"] or "{}"), **patch}
        sets = {"payload": json.dumps(payload, ensure_ascii=False), "updated": datetime.now().isoformat(), **fields}
        if status: sets["status"] = status
        c.execute(f"UPDATE videos SET {', '.join(k+'=?' for k in sets)} WHERE id=?", (*sets.values(), vid))
        c.commit()
    except BaseException:
        c.rollback()
        raise
    finally:
        c.close()

def approve(vid: str) -> str:
    """approve из любого состояния, где ждём владельца. Возвращает новый статус."""
    from .locking import video_lock
    from . import gates
    with video_lock(vid, "approve"):
        v = get(vid)
        nxt = APPROVE_NEXT.get(v["status"])
        if not nxt: raise ValueError(f"{vid} в статусе {v['status']} — approve не нужен")
        approval = {}
        if nxt == "approved_script": approval["script_approval"] = gates.script_key(v)
        if nxt == "approved_final": approval["final_approval"] = gates.final_key(v, video_dir(vid))
        update(vid, nxt, expected_status=v["status"], payload=approval)
        return nxt

def recent_titles(n=10) -> list[str]:
    with closing(conn()) as c:
        return [r["title"] for r in c.execute(
            "SELECT title FROM videos WHERE status IN ('uploaded','published','analyzed') ORDER BY created DESC LIMIT ?", (n,))]

def video_dir(vid: str):
    if not vid or vid in (".", "..") or any(c in vid for c in '/\\:'):
        raise ValueError("Некорректный id видео")
    d = config.VIDEOS / vid; d.mkdir(parents=True, exist_ok=True); return d
