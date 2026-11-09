"""Уведомления и подтверждения. Кнопки шлют callback 'approve:<id>' / 'reject:<id>'."""
import os, json, requests
from . import db, config
from .locking import Busy, FileLock, video_lock

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN"); CHAT = os.getenv("TELEGRAM_CHAT_ID")
API = f"https://api.telegram.org/bot{TOKEN}"
CACHE = config.DATA / "tg_chat"

def _resolve_chat():
    """Use explicitly configured or previously paired chat; never trust the first sender."""
    global CHAT
    if CHAT: return
    if CACHE.exists(): CHAT = config.read(CACHE).strip(); return
    raise RuntimeError("Укажите TELEGRAM_CHAT_ID в .env")


def _authorized(u):
    try: _resolve_chat()
    except RuntimeError: return False
    callback = u.get("callback_query")
    message = callback.get("message", {}) if callback else u.get("message", {})
    sender = callback.get("from", {}) if callback else message.get("from", {})
    if str(message.get("chat", {}).get("id")) != str(CHAT): return False
    allowed = {x.strip() for x in os.getenv("TELEGRAM_ALLOWED_USER_IDS", "").split(",") if x.strip()}
    if not allowed and str(CHAT).isdigit(): allowed = {str(CHAT)}
    return not sender.get("is_bot", False) and str(sender.get("id")) in allowed


def _action(action, vid, note=None):
    if action not in ("approve", "reject", "fix"): raise ValueError("Неизвестная команда")
    with video_lock(vid, "telegram_" + action):
        v = db.get(vid)
        if action == "approve":
            if v["status"] in db.APPROVE_NEXT: db.approve(vid)
            return
        if v["status"] in ("uploaded", "published", "analyzed", "localized_uploaded"):
            raise ValueError("Уже загруженный ролик не меняется командой очереди")
        if action == "reject":
            db.update(vid, "rejected", expected_status=v["status"])
            return
        if not note or not note.strip(): raise ValueError("Пустые правки")
        for name in ("script_draft.json", "script_factchecked.json"):
            (db.video_dir(vid) / name).unlink(missing_ok=True)
        db.update(vid, "approved_topic", expected_status=v["status"], payload={"fix_note": note.strip(), "script_approval": None, "final_approval": None, "release_gate": None})

def _outbox(text: str, why: str = ""):
    """Телеграм недоступен (РФ-сеть без VPN) — складываем сообщение в файл, чтобы не терять и не валить этап."""
    print("[telegram недоступен" + (": " + why[:80] if why else "") + "]", text[:300], flush=True)
    try:
        p = config.DATA / "telegram_outbox.txt"; config.DATA.mkdir(parents=True, exist_ok=True)
        from datetime import datetime
        with open(p, "a", encoding="utf-8") as f: f.write(f"\n--- {datetime.now():%d.%m %H:%M}\n{text}\n")
    except Exception: pass
    return {}

def send(text: str, buttons: list[tuple[str, str]] | None = None, file=None):
    """Сообщение владельцу. Сеть до Telegram — не повод ронять этап: конвейер работает и без уведомлений."""
    if not TOKEN:
        print("[telegram выключен — нет TELEGRAM_BOT_TOKEN]", text[:300]); return {}
    try:
        return _send(text, buttons, file)
    except Exception as e:
        return _outbox(text, str(e))

def _send(text: str, buttons: list[tuple[str, str]] | None = None, file=None):
    _resolve_chat()
    markup = json.dumps({"inline_keyboard": [[{"text": t, "callback_data": d} for t, d in buttons]]}) if buttons else None
    if file:
        payload = {"chat_id": CHAT, "caption": text[:1000], "parse_mode": "Markdown"}
        if markup: payload["reply_markup"] = markup
        with open(file, "rb") as fh:
            r = requests.post(f"{API}/sendDocument", data=payload, files={"document": fh}, timeout=120).json()
        if not r.get("ok"):
            payload.pop("parse_mode")
            with open(file, "rb") as fh:
                r = requests.post(f"{API}/sendDocument", data=payload, files={"document": fh}, timeout=120).json()
        return r
    payload = {"chat_id": CHAT, "text": text[:4000], "parse_mode": "Markdown"}
    if markup: payload["reply_markup"] = markup
    r = requests.post(f"{API}/sendMessage", json=payload, timeout=30).json()
    if not r.get("ok"):   # Markdown не распарсился (подчёркивания в тексте и т.п.) — шлём как есть
        payload.pop("parse_mode"); r = requests.post(f"{API}/sendMessage", json=payload, timeout=30).json()
    return r

def ask_topic_choice(vid: str, topic: dict):
    s = topic.get("scores", {})
    badge = {"anatomy": "🏗 anatomy" + (f" · unit: {topic['unit']}" if topic.get("unit") else ""),
             "story": "📜 story · " + str(topic.get("hero") or "")}.get(topic.get("format"), "📰 news")
    send(f"{badge}\n*{topic['working_title']}*\n_{topic.get('thesis','')}_\n{topic.get('why_now','')}\n"
         f"спрос {s.get('demand','?')} · cpm {s.get('cpm','?')} · угол {s.get('angle','?')} · evergreen {s.get('evergreen','?')}",
         [("✅ Берём", f"approve:{vid}"), ("✖", f"reject:{vid}")])

def ask_script_review(vid: str, script_path, note: str = ""):
    send(f"Сценарий готов: `{vid}`\nПравки — сообщением, начни с `fix {vid}:`" + (f"\n\n{note}" if note else ""), file=script_path)
    send("После прочтения:", [("✅ В производство", f"approve:{vid}"), ("✖ Переписать", f"reject:{vid}")])

def ask_final_review(vid: str, final_path, note: str = ""):
    """Точка контроля 3: просмотр final.mp4 перед загрузкой. Файл до 50 МБ уходит в чат, иначе — только путь."""
    size_mb = os.path.getsize(final_path) / 1e6
    text = f"Рендер готов: `{vid}`\n{note}\nФайл: `{final_path}` ({size_mb:.0f} МБ)"
    if size_mb < 49: send(text, file=final_path)
    else: send(text + "\nБольше 50 МБ — смотри локально.")
    send("Загружать?", [("✅ Загрузить", f"approve:{vid}"), ("✖ Переписать", f"reject:{vid}")])

def poll():
    try:
        with FileLock(config.DATA / ".telegram.lock", "poll"):
            _poll()
    except Busy:
        return


def _poll():
    """Забирает нажатия кнопок и текстовые правки. Вызывается в начале каждого `run`."""
    if not TOKEN: return
    state = config.DATA / "tg_offset"; offset = int(config.read(state)) if state.exists() else 0
    try:
        r = requests.get(f"{API}/getUpdates", params={"offset": offset, "timeout": 0}, timeout=30).json()
    except Exception as e:   # без связи с Telegram очередь всё равно должна двигаться
        print("[telegram] опрос не прошёл:", str(e)[:100], flush=True); return
    for u in r.get("result", []):
        if not _authorized(u):
            config.write(state, str(u["update_id"] + 1))
            continue
        try:
            if "callback_query" in u:
                action, vid = u["callback_query"]["data"].split(":", 1)
                if action == "reject" and db.get(vid)["status"] in ("scripted", "qc_passed", "qc_failed"):
                    _action("fix", vid, "Переписать по запросу владельца")
                else:
                    _action(action, vid)
                try:
                    requests.post(f"{API}/answerCallbackQuery", json={"callback_query_id": u["callback_query"]["id"], "text": "Принято"}, timeout=30)
                except requests.RequestException:
                    print("[telegram] команда исполнена, подтверждение кнопки не доставлено")
            elif "message" in u and (u["message"].get("text") or "").strip().lower() in ("баланс", "деньги", "money", "/money"):
                from . import money
                try: send(money.report_text()); money.report_html()
                except Exception as e: send(f"Отчёт не собрался: {e}")
            elif "message" in u and (u["message"].get("text") or "").startswith("fix "):
                head, note = u["message"]["text"][4:].split(":", 1)
                _action("fix", head.strip(), note)
            elif "message" in u:
                parts = (u["message"].get("text") or "").strip().split()
                if len(parts) == 2 and parts[0] in ("approve", "reject"):
                    _action(parts[0], parts[1])
        except Busy:
            return  # keep this update pending until the running stage releases it
        except (KeyError, ValueError) as e:
            print(f"[telegram] пропускаю апдейт {u.get('update_id')}: {e}")
        config.write(state, str(u["update_id"] + 1))
