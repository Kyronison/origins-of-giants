"""Conservative request reservations against the SHARED spending ledger.

Confirmed provider costs remain distinct from estimates. Uncertain attempts keep
their reservation; unknown prices fail before payment. A provider price change
cannot be promised away: receipts are retained for actual billing reconciliation.
"""
import json
import math
import os
import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

_prices = {}
_prices_at = 0.0
_guard = threading.Lock()


class BudgetStop(RuntimeError):
    pass


def _pricing(model):
    global _prices_at, _prices
    with _guard:
        if time.time() - _prices_at > 3600:
            import requests
            response = requests.get("https://openrouter.ai/api/v1/models", timeout=30)
            response.raise_for_status()
            _prices = {x["id"]: x["pricing"] for x in response.json()["data"]}
            _prices_at = time.time()
        price = _prices.get(model)
    if not price:
        raise BudgetStop("No current tariff for " + model)
    return price


def reserve_amount(provider, model, arguments, fal_estimate):
    if provider == "fal":
        if fal_estimate is None or not math.isfinite(fal_estimate) or fal_estimate < 0:
            raise BudgetStop("Unknown fal tariff; refusing unbudgeted request: " + model)
        return max(0.01, 2 * fal_estimate)
    if provider != "openrouter" or not isinstance(arguments, dict):
        raise BudgetStop("Missing request parameters for cost reservation")
    if ":online" in model or arguments.get("tools"):
        raise BudgetStop("Paid external tools need an explicit tariff before use")
    p = _pricing(model)
    prompt_rate, completion_rate = float(p["prompt"]), float(p["completion"])
    text_bytes, images = 0, 0
    for msg in arguments.get("messages", []):
        content = msg.get("content", "")
        for item in content if isinstance(content, list) else [{"type": "text", "text": content}]:
            if item.get("type") == "image_url":
                images += 1
            elif item.get("type") == "text":
                text_bytes += len(str(item.get("text", "")).encode("utf-8"))
            else:
                raise BudgetStop("Unknown multimodal input cannot be safely priced")
    output = arguments.get("max_tokens")
    if not isinstance(output, int) or output < 1:
        raise BudgetStop("Output token ceiling is required")
    # UTF-8 bytes upper-bound text tokens; generous image token allowance plus
    # provider image charge, then double headroom for routing/tariff differences.
    bound = ((text_bytes + 1024 + images * 65536) * prompt_rate + output * completion_rate
             + images * float(p.get("image") or 0) + float(p.get("request") or 0))
    if not math.isfinite(bound) or bound < 0:
        raise BudgetStop("Invalid provider price")
    return max(0.02, 2 * bound)


def _legacy_month(c, month):
    """Include current-month original-channel videos not cut over to receipts."""
    path = os.getenv("SHARED_PIPELINE_DB")
    if not path or not Path(path).exists():
        return 0.0
    known = {r[0] for r in c.execute("SELECT video_id FROM baselines")}
    with sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True) as old:
        rows = old.execute("SELECT id,payload FROM videos WHERE created LIKE ?", (month + "%",)).fetchall()
    return sum(float(json.loads(payload or "{}").get("cost_usd") or 0)
               for vid, payload in rows if vid not in known)


def _foreign_reserve(provider, model):
    """Консервативная цена чужого неоценённого запроса: картинка/апскейл — $0.10, дешёвая текстовая модель — $0.10, прочие — $1.50."""
    m = str(model or "").lower()
    if provider == "fal": return 0.10
    if any(k in m for k in ("flash-lite", "flash", "mini", "haiku", "nano")): return 0.10
    return 1.50


def totals(c, video_id):
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    video = float(c.execute("SELECT COALESCE(SUM(amount_usd),0) FROM baselines WHERE video_id=?", (video_id,)).fetchone()[0])
    monthly = float(c.execute("SELECT COALESCE(SUM(amount_usd),0) FROM baselines WHERE created LIKE ?", (month + "%",)).fetchone()[0])
    monthly += _legacy_month(c, month)
    unknown = []
    for row in c.execute("SELECT r.*, b.reserved_usd FROM requests r LEFT JOIN budget_reservations b USING(attempt_id)"):
        if row["video_id"] != video_id and not row["created"].startswith(month):
            continue
        if row["confirmed_usd"] is not None:
            value = float(row["confirmed_usd"])
        elif row["reserved_usd"] is not None:
            value = float(row["reserved_usd"])
        elif row["estimated_usd"] is not None:
            value = 2 * float(row["estimated_usd"])
        elif row["video_id"] != video_id:
            # 23.10: другие конвейеры (EN/ES) пишут запросы без цены — провайдер не вернул cost, запрос упал или превью
            # не той «quality». Они больше не замораживают Ancestors: идут в месячную сумму консервативным резервом;
            # неизвестные запросы самого выпуска по-прежнему останавливают траты.
            value = _foreign_reserve(row["provider"], row["model"])
        else:
            unknown.append(row["attempt_id"])
            continue
        if row["video_id"] == video_id:
            video += value
        if row["created"].startswith(month):
            monthly += value
    return {"video_reserved_usd": video, "month_reserved_usd": monthly, "unknown_attempts": unknown}


def check_limits(c, video_id, amount=0):
    t = totals(c, video_id)
    if t["unknown_attempts"]:
        raise BudgetStop("Shared ledger has unpriced requests; reconcile before new Ancestors spending")
    if t["video_reserved_usd"] + amount > float(os.getenv("SPEND_VIDEO_LIMIT", "25")):
        raise BudgetStop(f"Pilot budget $25 would be exceeded: reserved ${t['video_reserved_usd']:.2f} + ${amount:.2f}")
    if t["month_reserved_usd"] + amount > float(os.getenv("SPEND_MONTH_LIMIT", "500")):
        raise BudgetStop(f"Shared monthly budget $500 would be exceeded: reserved ${t['month_reserved_usd']:.2f} + ${amount:.2f}")
    return t
