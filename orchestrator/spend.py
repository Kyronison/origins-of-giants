"""Request receipts, separate from shared account balances and the production queue.

No provider prices are fetched here. Configured tariffs are estimates; only an
explicit billing receipt (OpenRouter usage.cost, or later reconciliation) is
confirmed. Unknown prices and interrupted requests remain visible.
"""
import contextvars
import math
import os
import sqlite3
import threading
import uuid
from contextlib import contextmanager, closing
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import wraps

from . import config


@dataclass(frozen=True)
class Attribution:
    video_id: str
    stage: str


_context = contextvars.ContextVar("spend_attribution", default=None)
_active_fal = contextvars.ContextVar("spend_fal_call", default=False)
_guard = threading.RLock()
_process_context = None
_scope_count = 0
_installed = []


def _now():
    return datetime.now(timezone.utc).isoformat()


def _path():
    from pathlib import Path
    return Path(os.environ["SPEND_LEDGER_PATH"]) if os.getenv("SPEND_LEDGER_PATH") else config.DATA / "spend.sqlite3"


def _connect():
    _path().parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(_path(), timeout=30)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA busy_timeout=30000")
    c.execute("""CREATE TABLE IF NOT EXISTS baselines(
        video_id TEXT PRIMARY KEY, amount_usd REAL NOT NULL,
        llm_usd REAL NOT NULL, fal_usd REAL NOT NULL, created TEXT NOT NULL)""")
    c.execute("""CREATE TABLE IF NOT EXISTS requests(
        attempt_id TEXT PRIMARY KEY, provider TEXT NOT NULL, request_id TEXT,
        video_id TEXT NOT NULL, stage TEXT NOT NULL, model TEXT NOT NULL,
        state TEXT NOT NULL, confirmed_usd REAL, estimated_usd REAL,
        price_source TEXT, error_type TEXT, created TEXT NOT NULL, updated TEXT NOT NULL,
        UNIQUE(provider, request_id))""")
    c.execute("""CREATE TABLE IF NOT EXISTS budget_reservations(
        attempt_id TEXT PRIMARY KEY, reserved_usd REAL NOT NULL)""")
    c.commit()
    return c


def ensure_baseline(video_id, amount_usd, llm_usd=0.0, fal_usd=0.0):
    """One immutable cutover per video; never reprice its historical bill."""
    with closing(_connect()) as c, c:
        c.execute("INSERT OR IGNORE INTO baselines VALUES(?,?,?,?,?)",
                  (video_id, float(amount_usd), float(llm_usd), float(fal_usd), _now()))


def baseline(video_id):
    if not _path().exists():
        return None
    with closing(_connect()) as c:
        row = c.execute("SELECT * FROM baselines WHERE video_id=?", (video_id,)).fetchone()
    return dict(row) if row else None


def current():
    # ThreadPoolExecutor does not copy ContextVars. A queue process runs exactly
    # one video stage; its workers use this immutable fallback. Different stages
    # in the same process cannot overlap. EN and ES use different processes.
    return _context.get() or _process_context


@contextmanager
def scope(video_id, stage):
    global _process_context, _scope_count
    value = Attribution(str(video_id), str(stage))
    with _guard:
        if _process_context is not None and _process_context != value:
            raise RuntimeError("Two video spend scopes cannot share one process")
        if not _scope_count:
            _installed.extend(install_fal())
        _process_context = value
        _scope_count += 1
    token = _context.set(value)
    try:
        yield
    finally:
        _context.reset(token)
        with _guard:
            _scope_count -= 1
            if not _scope_count:
                _process_context = None
                while _installed:
                    module, name, original, wrapped = _installed.pop()
                    if getattr(module, name, None) is wrapped:
                        setattr(module, name, original)


def _estimate_fal(model, arguments):
    """Only existing explicit tariffs, never config.image_price's fallback."""
    a = arguments if isinstance(arguments, dict) else {}
    if model in ("fal-ai/elevenlabs/tts/eleven-v3", "fal-ai/elevenlabs/tts/eleven-v4",
                 "fal-ai/elevenlabs/tts/multilingual-v2"):
        from .stages.assets import TTS_USD_PER_1K, TTS_V4_USD_PER_1K
        rate = TTS_V4_USD_PER_1K if model.endswith("eleven-v4") else TTS_USD_PER_1K
        if isinstance(a.get("text"), str):
            return len(a["text"]) / 1000 * rate, "configured_tts_tariff"
    count = a.get("num_images", 1)
    if not isinstance(count, (int, float)) or count < 1:
        return None, None
    if model in config.IMAGE_PRICE_FLAT:
        # Existing GPT tariff is medium only. High/default/other qualities have
        # no explicit configured tariff: do not silently use the medium price.
        if "gpt-image" in model and a.get("quality") != "medium":
            return None, None
        return config.IMAGE_PRICE_FLAT[model] * count, "configured_image_flat"
    size = a.get("image_size")
    if model in config.IMAGE_PRICE_PER_MP and isinstance(size, dict):
        w, h = size.get("width"), size.get("height")
        if isinstance(w, (int, float)) and isinstance(h, (int, float)) and w > 0 and h > 0:
            return config.IMAGE_PRICE_PER_MP[model] * math.ceil(w * h / 1e6) * count, "configured_image_per_mp"
    return None, None


def _begin(provider, model, arguments=None, attribution=None):
    at = attribution or current()
    if at is None:
        return None
    estimate, source = _estimate_fal(model, arguments) if provider == "fal" else (None, None)
    reservation = None
    if os.getenv("CHANNEL_PROFILE") == "ancestors":
        from .ancestors_budget import reserve_amount
        reservation = reserve_amount(provider, model, arguments, estimate)
    attempt = uuid.uuid4().hex
    now = _now()
    with closing(_connect()) as c, c:
        if reservation is not None:
            from .ancestors_budget import check_limits
            c.execute("BEGIN IMMEDIATE")
            check_limits(c, at.video_id, reservation)
        c.execute("INSERT INTO requests VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                  (attempt, provider, None, at.video_id, at.stage, str(model), "pending",
                   None, estimate, source, None, now, now))
        if reservation is not None:
            c.execute("INSERT INTO budget_reservations VALUES(?,?)", (attempt, reservation))
    return attempt


def _update(attempt, *, request_id=None, state=None, confirmed_usd=None, price_source=None, error_type=None):
    if attempt is None:
        return None
    if confirmed_usd is not None and (not math.isfinite(float(confirmed_usd)) or float(confirmed_usd) < 0):
        raise ValueError("Invalid confirmed charge")
    with closing(_connect()) as c:
        c.execute("BEGIN IMMEDIATE")
        row = c.execute("SELECT * FROM requests WHERE attempt_id=?", (attempt,)).fetchone()
        if row is None:
            raise KeyError("Spend attempt is missing")
        if request_id:
            duplicate = c.execute("SELECT * FROM requests WHERE provider=? AND request_id=?",
                                  (row["provider"], str(request_id))).fetchone()
            if duplicate and duplicate["attempt_id"] != attempt:
                if (duplicate["video_id"], duplicate["model"]) != (row["video_id"], row["model"]):
                    raise ValueError("Provider request ID belongs to another video or model")
                c.execute("DELETE FROM requests WHERE attempt_id=?", (attempt,))
                attempt, row = duplicate["attempt_id"], duplicate
        fields = {"updated": _now()}
        if request_id:
            fields["request_id"] = str(request_id)
        if state and row["state"] != "succeeded":
            fields["state"] = state
        if confirmed_usd is not None:
            if row["confirmed_usd"] is not None and abs(row["confirmed_usd"] - float(confirmed_usd)) > 1e-9:
                raise ValueError("Conflicting provider charges for the same request ID")
            fields["confirmed_usd"] = float(confirmed_usd)
            fields["price_source"] = price_source or "provider_receipt"
        if error_type:
            fields["error_type"] = error_type
        c.execute(f"UPDATE requests SET {', '.join(k+'=?' for k in fields)} WHERE attempt_id=?",
                  (*fields.values(), attempt))
        c.commit()
    return attempt


def record_confirmed(provider, request_id, amount_usd, evidence):
    """Attach an explicit billing receipt to an already recorded provider job."""
    if not request_id or not evidence:
        raise ValueError("A provider job ID and billing evidence are required")
    with closing(_connect()) as c:
        row = c.execute("SELECT attempt_id FROM requests WHERE provider=? AND request_id=?",
                        (provider, str(request_id))).fetchone()
    if not row:
        raise KeyError("Provider job has no local request receipt")
    return _update(row["attempt_id"], confirmed_usd=amount_usd, price_source=str(evidence))


def _after_call(attempt, **fields):
    """Never turn an already purchased result into another paid retry.

    The durable pre-call attempt remains pending/unresolved if this update
    fails. Do not swallow consistency errors (conflicting IDs or charges).
    """
    try:
        return _update(attempt, **fields)
    except (sqlite3.Error, OSError) as exc:
        print(f"[money] receipt update unavailable ({type(exc).__name__}); attempt {attempt} remains unresolved", flush=True)
        return attempt


def summary(video_id):
    base = baseline(video_id)
    if base is None:
        return None
    with closing(_connect()) as c:
        rows = list(c.execute("SELECT * FROM requests WHERE video_id=?", (video_id,)))
    confirmed = sum(r["confirmed_usd"] for r in rows if r["confirmed_usd"] is not None)
    estimated = sum(r["estimated_usd"] for r in rows if r["confirmed_usd"] is None and r["estimated_usd"] is not None)
    unknown = sum(r["confirmed_usd"] is None and r["estimated_usd"] is None for r in rows)
    unresolved = sum(r["state"] != "succeeded" for r in rows)
    providers = {}
    for r in rows:
        value = r["confirmed_usd"] if r["confirmed_usd"] is not None else r["estimated_usd"]
        providers[r["provider"]] = providers.get(r["provider"], 0.0) + (value or 0.0)
    return {"baseline_usd": base["amount_usd"], "baseline_llm_usd": base["llm_usd"],
            "baseline_fal_usd": base["fal_usd"], "confirmed_usd": confirmed,
            "estimated_usd": estimated, "unknown_requests": unknown, "unresolved_requests": unresolved,
            "requests": len(rows), "providers": providers,
            "accounted_usd": base["amount_usd"] + confirmed + estimated,
            "complete": unknown == 0 and unresolved == 0}


def openrouter_call(call, *, model, arguments=None):
    attempt = _begin("openrouter", model, arguments)
    try:
        result = call()
    except BaseException as exc:
        _after_call(attempt, state="unresolved", error_type=type(exc).__name__)
        raise
    usage = getattr(result, "usage", None)
    amount = getattr(usage, "cost", None)
    if amount is None:
        amount = (getattr(usage, "model_extra", None) or {}).get("cost")
    _after_call(attempt, request_id=getattr(result, "id", None), state="succeeded",
            confirmed_usd=amount, price_source="openrouter_usage.cost")
    return result


def _result_id(result):
    return result.get("request_id") if isinstance(result, dict) else getattr(result, "request_id", None)


class _Handle:
    def __init__(self, original, attempt, asynchronous=False):
        self._original, self._attempt, self._asynchronous = original, attempt, asynchronous

    def __getattr__(self, name):
        return getattr(self._original, name)

    def get(self, *args, **kwargs):
        if self._asynchronous:
            return self._get_async(*args, **kwargs)
        try:
            result = self._original.get(*args, **kwargs)
        except BaseException as exc:
            _after_call(self._attempt, state="unresolved", error_type=type(exc).__name__)
            raise
        _after_call(self._attempt, state="succeeded")
        return result

    async def _get_async(self, *args, **kwargs):
        try:
            result = await self._original.get(*args, **kwargs)
        except BaseException as exc:
            _after_call(self._attempt, state="unresolved", error_type=type(exc).__name__)
            raise
        _after_call(self._attempt, state="succeeded")
        return result


def _fal_wrapper(original, name):
    asynchronous = name.endswith("_async")
    kind = name.removesuffix("_async")

    def prepare(application, args, kwargs):
        arguments = kwargs.get("arguments", args[0] if args else None)
        holder = [_begin("fal", application, arguments)]
        if holder[0] is None:
            return holder
        if kind == "subscribe":
            callback = kwargs.get("on_enqueue")
            def enqueued(request_id):
                holder[0] = _after_call(holder[0], request_id=request_id)
                return callback(request_id) if callback else None
            kwargs["on_enqueue"] = enqueued
        return holder

    def done(holder, result):
        if holder[0] is None:
            return result
        holder[0] = _after_call(holder[0], request_id=_result_id(result),
                            state="pending" if kind == "submit" else "succeeded")
        return _Handle(result, holder[0], asynchronous) if kind == "submit" else result

    @wraps(original)
    def sync(application, *args, **kwargs):
        if _active_fal.get():
            return original(application, *args, **kwargs)
        holder = prepare(application, args, kwargs)
        token = _active_fal.set(True)
        try:
            result = original(application, *args, **kwargs)
        except BaseException as exc:
            holder[0] = _after_call(holder[0], request_id=getattr(exc, "request_id", None),
                                state="unresolved", error_type=type(exc).__name__)
            raise
        finally:
            _active_fal.reset(token)
        return done(holder, result)

    @wraps(original)
    async def async_(application, *args, **kwargs):
        if _active_fal.get():
            return await original(application, *args, **kwargs)
        holder = prepare(application, args, kwargs)
        token = _active_fal.set(True)
        try:
            result = await original(application, *args, **kwargs)
        except BaseException as exc:
            holder[0] = _after_call(holder[0], request_id=getattr(exc, "request_id", None),
                                state="unresolved", error_type=type(exc).__name__)
            raise
        finally:
            _active_fal.reset(token)
        return done(holder, result)

    wrapped = async_ if asynchronous else sync
    wrapped._spend_receipts = True
    return wrapped


def install_fal(module=None):
    """Cover module-level SDK APIs used by every fal purchase in this repo.

    subscribe's on_enqueue persists the provider job before waiting, including
    arguments.sync_mode image payloads. run lacks a job ID in some SDK results;
    those receipts retain a local attempt ID and explicitly unknown billing.
    """
    if module is None:
        import fal_client as module
    changed = []
    with _guard:
        for name in ("subscribe", "subscribe_async", "submit", "submit_async", "run", "run_async"):
            original = getattr(module, name, None)
            if original is not None and not getattr(original, "_spend_receipts", False):
                wrapped = _fal_wrapper(original, name)
                setattr(module, name, wrapped)
                changed.append((module, name, original, wrapped))
    return changed
