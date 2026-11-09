"""Место на диске данных (решение владельца 29.09.2026): готовый final.mp4 вышедшего ролика уходит с диска через FINAL_KEEP_DAYS
дней после выхода. Копия ролика остаётся на YouTube; сценарий, кадры, превью, шортсы и комплект публикации остаются в папке ролика.

Режим FINAL_RETENTION в .env:
  move   — перенос в FINAL_ARCHIVE_DIR на другом диске (по умолчанию). Архив чистит владелец, когда сочтёт нужным;
  delete — файл удаляется с диска насовсем. Этот режим включает только владелец, своей рукой в .env;
  off    — ничего не делать.
Перед тем как убрать файл, проверяется, что ролик на YouTube открыт и обработан. Не подтвердилось — файл остаётся на месте.
Зачем: блоку из 18 роликов нужно около 95 ГБ, а рендер не стартует, если свободно меньше 15 ГБ (STRATEGY.md, раздел 12)."""
import json, os, shutil, time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from .. import config, db, telegram

STATES = ("published", "analyzed", "localized_uploaded")
_TOLD = [0.0]


def _client(vid: str):
    """Клиент YouTube того канала, куда ушёл ролик: испанские версии (id с «__es») загружены своим токеном."""
    from .upload import yt, SCOPES
    if not str(vid).endswith("__es"): return yt()
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    tok = config.DATA / "youtube_token_es.json"
    if not tok.exists(): return None
    from .upload import gbuild
    return gbuild("youtube", "v3", Credentials.from_authorized_user_file(str(tok), SCOPES))


def _live(vid: str, yid: str) -> bool:
    """Ролик на YouTube открыт и обработан."""
    y = _client(vid)
    if not y: return False
    it = y.videos().list(part="status", id=yid).execute().get("items") or []
    return bool(it) and it[0]["status"].get("privacyStatus") == "public" and it[0]["status"].get("uploadStatus") == "processed"


def due() -> list[dict]:
    """Ролики, чей final.mp4 пора убирать с диска данных."""
    edge = datetime.now(timezone.utc) - timedelta(days=config.FINAL_KEEP_DAYS); out = []
    for st in STATES:
        for v in db.by_status(st):
            f = db.video_dir(v["id"]) / "final.mp4"
            if not v["youtube_id"] or not v["publish_at"] or not f.exists(): continue
            try: at = datetime.fromisoformat(v["publish_at"])
            except ValueError: continue
            if at.tzinfo is None: at = at.replace(tzinfo=timezone.utc)
            if at <= edge: out.append({"id": v["id"], "youtube_id": v["youtube_id"], "file": f, "gb": round(f.stat().st_size / 2 ** 30, 2), "published": at})
    return sorted(out, key=lambda x: x["published"])


def tick(dry: bool = False) -> list[str]:
    mode = config.FINAL_RETENTION
    if mode not in ("move", "delete"): return []
    done = []
    for x in due():
        try:
            if not _live(x["id"], x["youtube_id"]):
                print(f"[retention] {x['id']}: ролик на YouTube не подтверждён как открытый — файл остаётся", flush=True); continue
            if dry: done.append(f"{x['id']} ({x['gb']} ГБ)"); continue
            if mode == "move":
                root = Path(config.FINAL_ARCHIVE_DIR)
                free = shutil.disk_usage(root.anchor or str(root)).free / 2 ** 30
                if free - x["gb"] < config.ARCHIVE_MIN_FREE_GB:
                    print(f"[retention] в архиве мало места: свободно {free:.1f} ГБ — перенос остановлен", flush=True)
                    if time.time() - _TOLD[0] > 24 * 3600:
                        _TOLD[0] = time.time()
                        telegram.send(f"💾 Архив готовых роликов ({root}) почти полон: на диске свободно {free:.0f} ГБ. "
                                      f"Ролики старше {config.FINAL_KEEP_DAYS} дней есть на YouTube — папку архива можно удалить. "
                                      "Пока места нет, готовые файлы остаются на диске данных.")
                    break
                dst = root / x["id"] / "final.mp4"; dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(x["file"], dst)
                if dst.stat().st_size != x["file"].stat().st_size:
                    dst.unlink(missing_ok=True); raise RuntimeError("копия в архиве не совпала по размеру")
                os.remove(x["file"]); where = str(dst)
            else:
                os.remove(x["file"]); where = ""
            db.update(x["id"], payload={"final_archived": {"at": datetime.now(timezone.utc).isoformat(), "mode": mode, "to": where, "gb": x["gb"]}})
            done.append(f"{x['id']} ({x['gb']} ГБ)")
            print(f"[retention] {x['id']}: final.mp4 {x['gb']} ГБ — " + ("перенесён в " + where if where else "удалён с диска"), flush=True)
        except Exception as e:
            print(f"[retention] {x['id']}: {str(e)[:160]}", flush=True)
    return done
