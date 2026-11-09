"""Единый отчёт по деньгам: остатки на сервисах и расходы по каждому видео.
Источники: OpenRouter /credits, fal /billing/user_balance, ElevenLabs /user/subscription (если у ключа есть право user_read; иначе — наши подсчёты символов),
Pexels — заголовки лимита. После перехода на квитанции расходы видео — неизменяемый
исторический baseline + журнал spend.sqlite3. Тарифная оценка не является списанием."""
import os, re, json, html, requests
from datetime import datetime, date
from . import config, db, spend

ELEVEN_PLAN_CHARS = int(os.getenv("ELEVENLABS_PLAN_CHARS", 100000))   # Creator: 100k символов в месяц

def fal_left() -> float | None:
    """Общий баланс fal (None — не узнали); не цена отдельного ролика или этапа."""
    try:
        x = requests.get("https://rest.alpha.fal.ai/billing/user_balance", headers={"Authorization": "Key " + os.environ["FAL_KEY"]}, timeout=20)
        return float(x.text.strip().strip('"')) if x.status_code == 200 else None
    except Exception: return None

_OR_CACHE = [0.0, None]   # (когда спрашивали, остаток): /credits отвечает медленнее fal, а очередь тикает раз в минуту

def or_left(max_age: float = 300) -> float | None:
    """Остаток на OpenRouter в долларах. None — если спросить не удалось (тогда решения по балансу не принимаем)."""
    import time, requests
    if _OR_CACHE[1] is not None and time.time() - _OR_CACHE[0] < max_age: return _OR_CACHE[1]
    try:
        r = requests.get("https://openrouter.ai/api/v1/credits",
                         headers={"Authorization": "Bearer " + os.environ["OPENROUTER_API_KEY"]}, timeout=20).json()["data"]
        _OR_CACHE[0], _OR_CACHE[1] = time.time(), round(float(r["total_credits"]) - float(r["total_usage"]), 2)
        return _OR_CACHE[1]
    except Exception: return None

def balances() -> dict:
    out = {}
    try:
        r = requests.get("https://openrouter.ai/api/v1/credits", headers={"Authorization": "Bearer " + os.environ["OPENROUTER_API_KEY"]}, timeout=20).json()["data"]
        out["openrouter"] = {"left": round(r["total_credits"] - r["total_usage"], 2), "total": round(r["total_credits"], 2)}
    except Exception as e: out["openrouter"] = {"error": str(e)[:80]}
    try:
        x = requests.get("https://rest.alpha.fal.ai/billing/user_balance", headers={"Authorization": "Key " + os.environ["FAL_KEY"]}, timeout=20)
        out["fal"] = {"left": round(float(x.text.strip().strip('"')), 2)} if x.status_code == 200 else {"error": f"HTTP {x.status_code}"}
    except Exception as e: out["fal"] = {"error": str(e)[:80]}
    try:
        x = requests.get("https://api.elevenlabs.io/v1/user/subscription", headers={"xi-api-key": os.environ["ELEVENLABS_API_KEY"]}, timeout=20)
        if x.status_code == 200:
            j = x.json(); out["elevenlabs"] = {"used": j.get("character_count"), "limit": j.get("character_limit"), "tier": j.get("tier"),
                                               "reset": datetime.fromtimestamp(j["next_character_count_reset_unix"]).strftime("%d.%m") if j.get("next_character_count_reset_unix") else None, "source": "api"}
        else: out["elevenlabs"] = {"source": "estimate", "limit": ELEVEN_PLAN_CHARS, "note": "у ключа нет права User: read — считаю по нашим озвучкам"}
    except Exception as e: out["elevenlabs"] = {"error": str(e)[:80]}
    try:
        x = requests.get("https://api.pexels.com/videos/search", params={"query": "rain", "per_page": 1}, headers={"Authorization": os.environ["PEXELS_API_KEY"]}, timeout=20)
        out["pexels"] = {"left": int(x.headers.get("X-Ratelimit-Remaining", 0)), "limit": int(x.headers.get("X-Ratelimit-Limit", 0))}
    except Exception as e: out["pexels"] = {"error": str(e)[:80]}
    try:
        import shutil; u = shutil.disk_usage(str(config.DATA)); out["disk"] = {"free_gb": round(u.free / 1e9, 1)}
    except Exception: pass
    return out

def _llm_cost_by_video() -> dict:
    """Сумма cost=$… из заголовков логов, сгруппированная по id видео в имени файла."""
    acc = {}
    ids = _all_ids()
    for p in (config.DATA / "llm_log").glob("*.md"):
        try:
            with p.open(encoding="utf-8") as f: head = f.readline()
        except Exception: continue
        m = re.search(r"cost=\$([\d.]+)", head)
        if not m: continue
        vid = next((v for v in ids if v in p.name), "_other")
        acc[vid] = acc.get(vid, 0.0) + float(m.group(1))
    return acc

def _all_ids():
    c = db.conn()
    try: return sorted((r["id"] for r in c.execute("SELECT id FROM videos")), key=len, reverse=True)
    finally: c.close()


def _legacy_spent(vid):
    p = db.get(vid)["payload"]
    logged = _llm_cost_by_video().get(vid, 0.0)
    return max(float(p.get("cost_usd") or 0), logged + float(p.get("fal_usd") or 0))


def begin_stage(vid):
    """Freeze the existing bill once, before any newly tracked request starts."""
    if spend.baseline(vid) is None:
        p = db.get(vid)["payload"]
        logged = _llm_cost_by_video().get(vid, 0.0)
        fal = float(p.get("fal_usd") or 0)
        amount = max(float(p.get("cost_usd") or 0), logged + fal)
        spend.ensure_baseline(vid, amount, logged, fal)


def spent(vid):
    """Accounted amount, including labelled estimates; unknown charges are separate."""
    receipt = spend.summary(vid)
    return receipt["accounted_usd"] if receipt is not None else _legacy_spent(vid)


def reconcile(vid):
    """Recover receipts even on failure; ignore interim legacy stage estimates."""
    receipt = spend.summary(vid)
    patch = {"cost_usd": round(receipt["accounted_usd"] if receipt else _legacy_spent(vid), 6)}
    if receipt is not None:
        patch["spend_receipts"] = receipt
    db.update(vid, payload=patch)

def per_video() -> list[dict]:
    llm = _llm_cost_by_video(); rows = []
    for r in db.conn().execute("SELECT id, title, status, payload, created FROM videos WHERE status NOT IN ('idea','rejected') ORDER BY created DESC"):
        p = json.loads(r["payload"] or "{}"); s = p.get("script") or {}
        chars = p.get("tts_chars") or (len(re.sub(r"\s*\[F\d+\]|</?short>", "", s.get("script", ""))) if s.get("script") and p.get("cost_usd") else 0)
        total = float(p.get("cost_usd") or 0); l = round(llm.get(r["id"], 0.0), 3)
        fal = float(p["fal_usd"]) if p.get("fal_usd") is not None else max(0.0, total - l)   # fal_usd — по балансу до/после этапов
        if p.get("fal_usd") is not None: total = l + fal
        receipt = spend.summary(r["id"])
        if receipt is not None:
            total = receipt["accounted_usd"]
            l = receipt["baseline_llm_usd"] + receipt["providers"].get("openrouter", 0.0)
            fal = receipt["baseline_fal_usd"] + receipt["providers"].get("fal", 0.0)
        rows.append({"id": r["id"], "title": r["title"] or "", "status": r["status"], "total": round(total, 2), "llm": l, "fal": round(fal, 2),
                     "tts_chars": chars, "created": r["created"][:10], "format": (p.get("topic") or {}).get("format", ""),
                     "receipt": receipt, "accounting_note": _accounting_note(receipt)})
    return rows


def _accounting_note(receipt):
    if receipt is None:
        return "исторический учёт, без сверки по запросам"
    parts = [f"история ${receipt['baseline_usd']:.2f}", f"новые подтверждённые ${receipt['confirmed_usd']:.2f}"]
    if receipt["estimated_usd"]:
        parts.append(f"оценка ${receipt['estimated_usd']:.2f}")
    if receipt["unknown_requests"]:
        parts.append(f"неизвестная цена: {receipt['unknown_requests']} запросов; итог неполный")
    if receipt["unresolved_requests"]:
        parts.append(f"неопределённый результат: {receipt['unresolved_requests']} запросов")
    return "; ".join(parts)


def report_text() -> str:
    b = balances(); v = per_video(); month = date.today().strftime("%Y-%m")
    chars_month = sum(x["tts_chars"] for x in v if x["created"].startswith(month))
    lines = ["*Балансы*"]
    o = b.get("openrouter", {}); lines.append(f"OpenRouter: ${o.get('left', '?')} из ${o.get('total', '?')}" if "left" in o else f"OpenRouter: {o.get('error')}")
    f = b.get("fal", {}); lines.append(f"fal.ai: ${f.get('left', '?')}" if "left" in f else f"fal.ai: {f.get('error')}")
    e = b.get("elevenlabs", {})
    if e.get("source") == "api": lines.append(f"ElevenLabs ({e.get('tier')}): {e['used']:,} из {e['limit']:,} символов, сброс {e.get('reset')}")
    else: lines.append(f"ElevenLabs: ~{chars_month:,} из {ELEVEN_PLAN_CHARS:,} символов за месяц по нашим озвучкам (точную квоту API не отдаёт: включи право User: read у ключа)")
    px = b.get("pexels", {}); lines.append(f"Pexels: {px.get('left', '?'):,} из {px.get('limit', '?'):,} запросов в месяц" if "left" in px else "")
    if "disk" in b: lines.append(f"Диск: {b['disk']['free_gb']} ГБ свободно")
    lines.append("\n*Учтено по видео* (исторические суммы + новые квитанции; оценки и неизвестные цены указаны отдельно)")
    for x in v:
        lines.append(f"• {x['created']} `{x['id'][:34]}` — учтено ${x['total']:.2f} (LLM ${x['llm']:.2f}, fal ${x['fal']:.2f}), {x['tts_chars']:,} симв. озвучки, {x['status']}\n  {x['accounting_note']}")
    lines.append(f"\nУчтено с 15.09: ${sum(x['total'] for x in v):.2f} за {len(v)} видео. Неизвестные цены в сумму не включены; оценки не равны подтверждённым списаниям.")
    return "\n".join(l for l in lines if l is not None)

def report_html(path=None) -> str:
    b = balances(); v = per_video(); month = date.today().strftime("%Y-%m")
    chars_month = sum(x["tts_chars"] for x in v if x["created"].startswith(month))
    def card(title, value, sub=""):
        return f'<div class="card"><div class="k">{html.escape(title)}</div><div class="v">{html.escape(str(value))}</div><div class="s">{html.escape(sub)}</div></div>'
    o, f, e, px = b.get("openrouter", {}), b.get("fal", {}), b.get("elevenlabs", {}), b.get("pexels", {})
    cards = [card("OpenRouter", f"${o.get('left', '?')}", f"из ${o.get('total', '?')} · общий баланс"),
             card("fal.ai", f"${f.get('left', '?')}", "общий баланс; цена ролика — по квитанциям"),
             card("ElevenLabs", (f"{e['used']:,} / {e['limit']:,}" if e.get("source") == "api" else f"~{chars_month:,} / {ELEVEN_PLAN_CHARS:,}"),
                  ("символов, сброс " + str(e.get("reset"))) if e.get("source") == "api" else "символов за месяц по нашим озвучкам (включи User: read у ключа для точной квоты)"),
             card("Pexels", f"{px.get('left', '?'):,}" if "left" in px else "?", f"из {px.get('limit', '?'):,} запросов/мес"),
             card("Диск", f"{b.get('disk', {}).get('free_gb', '?')} ГБ", "свободно под рендер")]
    rows = "".join(f"<tr><td>{x['created']}</td><td>{html.escape(x['title'][:60])}<br><span class='id'>{x['id']}</span><br>{html.escape(x['accounting_note'])}</td><td>{x['format']}</td><td>{x['status']}</td>"
                   f"<td class='n'>${x['total']:.2f}</td><td class='n'>${x['llm']:.2f}</td><td class='n'>${x['fal']:.2f}</td><td class='n'>{x['tts_chars']:,}</td></tr>" for x in v)
    total = sum(x["total"] for x in v)
    doc = f"""<!doctype html><html lang="ru"><head><meta charset="utf-8"><title>Origins of Giants — деньги</title>
<style>body{{font-family:Inter,Segoe UI,Arial,sans-serif;background:#EDEFF2;color:#16191F;margin:0;padding:32px}}h1{{font-family:Georgia,serif;font-weight:600;margin:0 0 4px}}
.sub{{color:#6E7784;margin-bottom:24px}}.cards{{display:flex;flex-wrap:wrap;gap:14px;margin-bottom:28px}}.card{{background:#fff;padding:16px 20px;min-width:180px;flex:1;border-top:4px solid #16191F}}
.card:first-child{{border-top-color:#E63B2E}}.k{{color:#6E7784;font-size:13px}}.v{{font-family:Georgia,serif;font-size:32px;font-weight:600;margin:4px 0}}.s{{color:#6E7784;font-size:12px}}
table{{width:100%;border-collapse:collapse;background:#fff}}th,td{{text-align:left;padding:10px 12px;border-bottom:1px solid #C7CCD3;font-size:14px;vertical-align:top}}th{{color:#6E7784;font-weight:500}}
td.n,th.n{{text-align:right;font-variant-numeric:tabular-nums}}.id{{color:#6E7784;font-size:11px}}.tot{{margin-top:12px;color:#6E7784}}.rule{{height:6px;width:120px;background:#E63B2E;margin:8px 0 20px}}</style></head>
<body><h1>Origins of Giants — деньги</h1><div class="sub">обновлено {datetime.now():%d.%m.%Y %H:%M} · команда <code>money</code> или слово «баланс» боту</div><div class="rule"></div>
<div class="cards">{''.join(cards)}</div>
<table><tr><th>дата</th><th>видео</th><th>формат</th><th>статус</th><th class="n">учтено</th><th class="n">LLM</th><th class="n">fal</th><th class="n">символов озвучки</th></tr>{rows}</table>
<div class="tot">Учтено с 15.09: ${total:.2f} за {len(v)} видео. Неизвестные цены не включены; оценки не равны подтверждённым списаниям.</div></body></html>"""
    path = path or (config.DATA / "dashboard.html"); config.write(path, doc); return str(path)
