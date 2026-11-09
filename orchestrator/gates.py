"""Approvals belong to an artifact version, never just a queue status."""
import hashlib
import json
from . import config


def script_key(v):
    p = v["payload"]
    # Render-time slot resolution may change shots; the reviewed text and review
    # reasons are stable. Regenerating shots explicitly clears the approval.
    data = [(p.get("script") or {}).get("script"), p.get("needs_review"), p.get("opening_needs_review")]
    return hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def script_ready(v):
    p = v["payload"]
    flagged = p.get("needs_review") or p.get("opening_needs_review")
    return not flagged or p.get("script_approval") == script_key(v)


def require_script(vid):
    from . import db, telegram
    v = db.get(vid)
    if script_ready(v): return True
    db.update(vid, "scripted", payload={"release_gate": None, "final_approval": None})
    telegram.ask_script_review(vid, db.video_dir(vid) / "script.md", note="Автопроверка требует просмотра сценария/раскадровки перед производством.")
    return False


def final_key(v, d):
    h = hashlib.sha256(script_key(v).encode())
    for name in ("timeline.json", "meta.json", "opening_check.json", "stillcheck/result.json", "visual_integrity.json",
                 "publish/title.txt", "publish/description.txt", "publish/tags.txt", "publish/thumbnail_2560.jpg"):
        p = d / name
        h.update(name.encode())
        h.update(p.read_bytes() if p.exists() else b"MISSING")
    # Detect replacement of a multi-GB render without reading it for every poll.
    for p in sorted(d.glob("thumb_*.keep")) + sorted(d.glob("thumb_*.png")) + [d / "final.mp4"]:
        h.update(p.name.encode())
        h.update(str((p.stat().st_size, p.stat().st_mtime_ns) if p.exists() else None).encode())
    return h.hexdigest()


def record(vid, checks):
    from . import db
    v = db.get(vid)
    gate = {"version": 1, "ok": all(x is True for x in checks.values()), "checks": checks,
            "key": final_key(v, db.video_dir(vid))}
    db.update(vid, payload={"release_gate": gate, "final_approval": None})
    return gate


def require_upload(v, d):
    p = v["payload"]
    key = final_key(v, d)
    if v["status"] == "approved_final" and p.get("final_approval") == key:
        return  # explicit owner override, including qc_failed
    gate = p.get("release_gate") or {}
    automatic = config.AUTO_APPROVE or not config.REQUIRE_FINAL_APPROVAL
    if automatic and v["status"] in ("qc_passed", "approved_final") and gate.get("version") == 1 and gate.get("ok") is True and gate.get("key") == key:
        return
    raise RuntimeError("Нет действующего допуска к загрузке: запустите QC или подтвердите текущую версию после просмотра")
