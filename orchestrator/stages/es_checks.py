"""Resumable ES visual checks. Known defects are reports; unfinished checks retry."""
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path


def _bad(response, count):
    if not isinstance(response, dict) or not isinstance(response.get("bad"), list):
        raise ValueError("проверка не вернула обязательный список bad")
    found = {}
    for item in response["bad"]:
        if (not isinstance(item, dict) or type(item.get("n")) is not int
                or not 1 <= item["n"] <= count
                or not isinstance(item.get("why"), str) or not item["why"].strip()):
            raise ValueError("проверка вернула некорректное замечание")
        found.setdefault(item["n"], []).append(dict(item))
    return found


def _key(d, shot, signature):
    h = hashlib.sha256(json.dumps([signature, shot.get("id"), shot.get("beat"),
                                  shot.get("prompt")], ensure_ascii=False, sort_keys=True).encode())
    with (d / shot["image"]).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def run(d: Path, shots: list[dict], name: str, signature, ask, workers=6, batch_size=12) -> dict:
    """Persist per-image outcomes; retry only UNKNOWN or changed input on resume.

    ``ask(batch)`` returns the model's complete ``{"bad": [...]}`` response.
    It is called once per unfinished batch here; queue backoff handles outages.
    The caller may perform its existing bounded repairs, then call again for
    the selected replacement files. PASS and FAIL are both reusable verdicts.
    """
    d = Path(d); path = d / f"{name}.json"
    try:
        old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        records = old.get("records", {}) if old.get("version") == 1 else {}
        if not isinstance(records, dict): records = {}
    except (OSError, ValueError, AttributeError):
        records = {}
    current, pending = [], []
    for shot in shots:
        item = {"id": shot["id"], "image": shot.get("image"), "status": "UNKNOWN", "issues": []}
        try:
            item["key"] = _key(d, shot, signature)
            cached = records.get(item["key"], {})
            if (isinstance(cached, dict) and cached.get("status") in ("PASS", "FAIL")
                    and isinstance(cached.get("issues"), list)
                    and (cached["status"] == "FAIL") == bool(cached["issues"])):
                item.update(cached)
            else:
                pending.append((shot, item))
        except (OSError, KeyError, TypeError) as exc:
            item["error"] = str(exc)[:300]
        current.append(item)

    def save():
        counts = {s: sum(item["status"] == s for item in current) for s in ("PASS", "FAIL", "UNKNOWN")}
        report = {"version": 1, "status": "UNKNOWN" if counts["UNKNOWN"] else "FAIL" if counts["FAIL"] else "PASS",
                  "counts": counts, "items": current, "records": records}
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(path)
        return report

    def check(batch):
        try:
            found = _bad(ask([shot for shot, _ in batch]), len(batch))
            return [{"status": "FAIL" if n in found else "PASS", "issues": found.get(n, [])}
                    for n in range(1, len(batch) + 1)]
        except Exception as exc:
            return [{"status": "UNKNOWN", "issues": [], "error": f"{type(exc).__name__}: {exc}"[:300]} for _ in batch]

    save()  # Even interrupted checks have an explicit unfinished receipt.
    if pending:
        batches = [pending[k:k + batch_size] for k in range(0, len(pending), batch_size)]
        with ThreadPoolExecutor(min(workers, len(batches))) as pool:
            jobs = {pool.submit(check, batch): batch for batch in batches}
            for job in as_completed(jobs):
                for (_, item), verdict in zip(jobs[job], job.result()):
                    item.update(verdict)
                    item["checked_at"] = datetime.now(timezone.utc).isoformat()
                    records[item["key"]] = {k: item[k] for k in ("status", "issues", "checked_at", "error") if k in item}
                save()
    return save()


def require_complete(report: dict, name: str):
    """FAIL stays report-only; UNKNOWN means the queue must finish the check."""
    if report.get("status") == "UNKNOWN":
        unknown = [str(item["id"]) for item in report["items"] if item["status"] == "UNKNOWN"]
        errors = [item["error"] for item in report["items"] if item["status"] == "UNKNOWN" and item.get("error")]
        raise RuntimeError(f"{name}: проверка не завершена (UNKNOWN), кадров {len(unknown)}: "
                           + ", ".join(unknown[:6]) + ". Результаты сохранены; очередь повторит только незавершённые проверки. "
                           + (errors[0] if errors else ""))


def failed_ids(report: dict) -> set[str]:
    return {item["id"] for item in report["items"] if item["status"] == "FAIL"}
