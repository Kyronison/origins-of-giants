"""Все вызовы LLM — через OpenRouter (OpenAI-совместимый API). Модели — в config по ролям (аудит 18.09): текст — Opus 5, поиск — GPT-5.6 Sol,
фактчек — GPT-6 Astra, раскадровка — Qwen3-Max, картинки — Sonnet 5 / Opus 5.
Веб-поиск включается суффиксом :online у модели. JSON-ответы парсятся жёстко.
Каждый ответ пишется в data/llm_log/, стоимость каждого вызова (OpenRouter отдаёт usage.cost) копится в COST."""
import base64, json, os, re, threading, uuid
from contextlib import contextmanager
from datetime import datetime
from urllib.parse import urlsplit
from . import config

_client = None
COST = {"usd": 0.0}
_cost_lock = threading.Lock()
_video = None


@contextmanager
def scope(vid):
    """Queue holds the process lock; workers inherit this stage's attribution."""
    global _video
    previous, _video = _video, vid
    try: yield
    finally: _video = previous

def reset():
    """Сбросить клиента OpenRouter: после смены сети старые соединения получают 403 «security policy» (26.09)."""
    global _client
    try:
        if _client is not None: _client.close()
    except Exception: pass
    _client = None

def client():
    global _client
    if _client is None:
        from openai import OpenAI
        key = os.getenv("OPENROUTER_API_KEY")
        if not key: raise RuntimeError("OPENROUTER_API_KEY пуст — заполни .env")
        _client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=key,
                         default_headers={"HTTP-Referer": "https://youtube.com", "X-Title": config.CHANNEL_NAME,
                                          "X-OpenRouter-Metadata": "enabled"})
    return _client

def take_cost() -> float:
    """Сколько потрачено с прошлого вызова take_cost — этапы кладут это в payload видео."""
    with _cost_lock:
        c = COST["usd"]; COST["usd"] = 0.0
    return round(c, 4)

def _account(resp) -> float:
    u = getattr(resp, "usage", None)
    cost = float(getattr(u, "cost", None) or (u.model_extra or {}).get("cost", 0) or 0) if u else 0.0
    with _cost_lock: COST["usd"] += cost
    return cost

def _log(tag: str, model: str, user: str, answer: str):
    d = config.DATA / "llm_log"; d.mkdir(parents=True, exist_ok=True)
    if _video and _video not in tag: tag += "_" + _video
    tag = re.sub(r'[<>:"/\\|?*]', "_", tag)
    config.write(d / f"{datetime.now():%Y%m%d-%H%M%S-%f}_{uuid.uuid4().hex[:8]}_{tag}.md", f"# {model}\n\n## prompt\n\n{user}\n\n## answer\n\n{answer}")

def _redact_diagnostic(value):
    """No request headers/images; redact credentials even if an error echoes them."""
    if isinstance(value, dict):
        return {k: "[REDACTED_SECRET]" if re.search(r"authorization|cookie|api[_-]?key|password|secret|access_token|refresh_token", k, re.I)
                else _redact_diagnostic(v) for k, v in value.items()}
    if isinstance(value, list): return [_redact_diagnostic(v) for v in value]
    if not isinstance(value, str): return value
    for name, secret in os.environ.items():
        if len(secret) >= 8 and re.search(r"KEY|TOKEN|SECRET|PASSWORD", name, re.I):
            value = value.replace(secret, "[REDACTED_SECRET]")
    value = re.sub(r"sk-[A-Za-z0-9_-]+|Bearer\s+\S+", "[REDACTED_SECRET]", value, flags=re.I)
    return re.sub(r"data:image/[^;\s]+;base64,[A-Za-z0-9+/=]+", "[REDACTED_IMAGE]", value)


def error_details(error, model=None):
    """Preserve the response, not credentials or the uploaded request payload."""
    response = getattr(error, "response", None)
    detail = {"error_type": type(error).__name__, "model": model,
              "status": getattr(error, "status_code", None)}
    if response is not None:
        detail["status"] = response.status_code
        url = urlsplit(str(response.url))
        detail["endpoint"] = f"{url.scheme}://{url.hostname}{':' + str(url.port) if url.port else ''}{url.path}"
        names = {"date", "server", "content-type", "content-length", "cf-ray", "cf-cache-status",
                 "retry-after", "via", "x-request-id", "x-correlation-id", "x-envoy-upstream-service-time"}
        detail["headers"] = {k: v for k, v in response.headers.items()
                             if k.lower() in names or k.lower().startswith(("x-openrouter-", "x-ratelimit-"))}
        try: detail["body"] = response.json()
        except (ValueError, UnicodeError): detail["body"] = response.text
    else:
        detail["body"] = getattr(error, "body", None) or str(error)
    body = detail["body"]
    if isinstance(body, dict):
        api_error = body.get("error")
        metadata = api_error.get("metadata") if isinstance(api_error, dict) else None
        detail["provider"] = (metadata or {}).get("provider_name") if isinstance(metadata, dict) else body.get("provider")
        detail["route"] = body.get("openrouter_metadata")
    return _redact_diagnostic(detail)


def _log_api_error(error, model, tag="api_error"):
    if getattr(error, "status_code", None) is None: return
    try:
        d = config.DATA / "llm_log"; d.mkdir(parents=True, exist_ok=True)
        tag = re.sub(r'[<>:"/\\|?*]', "_", tag)
        detail = error_details(error, model)
        detail["timestamp"] = datetime.now().astimezone().isoformat()
        config.write(d / f"{datetime.now():%Y%m%d-%H%M%S-%f}_{uuid.uuid4().hex[:8]}_{tag}_error.json",
                     json.dumps(detail, ensure_ascii=False, indent=2))
    except Exception:
        pass  # A diagnostic write failure must not hide the original API error.


def _edge_security_denial(error):
    body = getattr(error, "body", None)
    return (getattr(error, "status_code", None) == 403 and isinstance(body, dict)
            and body.get("success") is False and body.get("error") == "Access denied by security policy.")


def _extra(model: str, effort: str) -> dict:
    """usage.cost — чтобы считать бюджет; reasoning — только моделям, которые его понимают (Claude / *-thinking)."""
    extra = {"usage": {"include": True}}
    if "claude" in model or "thinking" in model: extra["reasoning"] = {"effort": effort}
    # 12.10: qwen3.8-max (замена снятой qwen3-max) думает по умолчанию и съедала весь max_tokens на рассуждения — пустой ответ (entities Sears)
    elif "qwen3.8" in model: extra["reasoning"] = {"effort": "low", "exclude": True}   # отключить нельзя (400)
    return extra


def _paid_create(**kw):
    """One receipt per provider response; errors retain an unresolved attempt."""
    from . import spend
    return spend.openrouter_call(lambda: client().chat.completions.create(**kw), model=kw.get("model", ""), arguments=kw)


def _create(**kw):
    """Запрос с ожиданием при 429: у OpenRouter лимит 20 запросов в минуту на модель для новых аккаунтов, а добивка кадров и съёмка эпохи
    идут в несколько потоков — 17.09 на полной пересборке Apple шесть длинных сцен остались без кадров из-за 429."""
    import time
    from openai import RateLimitError, APIStatusError
    for k in range(6):
        try: return _paid_create(**kw)
        except RateLimitError as e:
            _log_api_error(e, kw.get("model"))
            if k == 5: raise
            wait = 8 * (k + 1); print(f"[llm] 429 у {kw.get('model')} — жду {wait} с", flush=True); time.sleep(wait)
        except APIStatusError as e:
            _log_api_error(e, kw.get("model"))
            raise


def ask(user: str, *, heavy=False, search=False, max_tokens=8000, system: str | None = None, tag="ask", effort="medium", model: str | None = None) -> str:
    """При обрезке ответа (finish=length) — один повтор с большим лимитом и низким бюджетом рассуждений. model — явная модель (проверка фактов на Astra)."""
    model = model or (config.LLM_MODEL_RESEARCH if search and config.LLM_MODEL_RESEARCH else config.LLM_MODEL_HEAVY if heavy else config.LLM_MODEL)
    if search: model += ":online"
    msgs = [{"role": "system", "content": system or config.channel_prompt()}, {"role": "user", "content": user}]
    answer = ""
    for attempt, (eff, mt) in enumerate(((effort, max_tokens), ("low", int(max_tokens * 1.5)))):
        resp = _create(model=model, max_tokens=mt, messages=msgs, extra_body=_extra(model, eff))
        ch = resp.choices[0]; answer = ch.message.content or ""; cost = _account(resp); u = resp.usage
        _log(tag + ("" if attempt == 0 else "_retry"), f"{model} effort={eff} max_tokens={mt} finish={ch.finish_reason} "
             f"tokens={getattr(u, 'prompt_tokens', '?')}->{getattr(u, 'completion_tokens', '?')} cost=${cost:.4f}", user, answer)
        if answer.strip() and ch.finish_reason != "length": return answer
        print(f"[llm] {tag}: finish={ch.finish_reason}, ответ {len(answer)} символов — повтор")
    return answer

def clean(text: str) -> str:
    """Теги цитирования веб-поиска ((cite index="…">…</cite>) содержат кавычки и ломают JSON."""
    return re.sub(r"</?cite[^>]*>", "", text)

def extract_json(text: str) -> dict:
    t = clean(text).strip()
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", t, re.S)
    if m: t = m.group(1)
    else:
        m = re.search(r"\{.*\}", t, re.S)
        if not m: raise ValueError(f"Модель не вернула JSON:\n{text[:500]}")
        t = m.group(0)
    try:
        return json.loads(t)
    except json.JSONDecodeError as e:   # дешёвая vision-модель дописывает второй объект или пояснение после JSON — берём первый объект
        if "Extra data" in str(e): return json.JSONDecoder().raw_decode(t)[0]
        raise

REPAIR_SYSTEM = ("Ты — конвертер формата. Тебе дают текст, внутри которого есть JSON-объект с ошибками синтаксиса "
                 "(незакрытые кавычки, лишние теги, markdown). Верни тот же самый объект как один валидный JSON, "
                 "ничего не удаляя, не проверяя и не комментируя содержимое. Только JSON, без пояснений.")

def ask_json(user: str, tag="ask", **kw) -> dict:
    text = ask(user, tag=tag, **kw)
    if not text.strip(): raise ValueError(f"Пустой ответ модели ({tag}) — см. data/llm_log/")
    try:
        return extract_json(text)
    except (ValueError, json.JSONDecodeError) as e:
        fixed = ask(clean(text)[-90000:], system=REPAIR_SYSTEM, max_tokens=kw.get("max_tokens", 8000), tag=tag + "_repair", effort="low")
        try:
            return extract_json(fixed)
        except (ValueError, json.JSONDecodeError):
            raise ValueError(f"Невалидный JSON от модели ({e}); оба ответа лежат в data/llm_log/*{tag}*")

def extract_vision_json(text: str) -> dict:
    """Preserve every verdict when a provider returns the checks as a JSON array."""
    raw = clean(text).strip()
    fenced = re.fullmatch(r"```(?:json)?\s*([\s\S]*?)\s*```", raw)
    if fenced: raw = fenced.group(1).strip()
    if raw.startswith("["):
        items = json.loads(raw)
        if not items or not all(isinstance(x, dict) and type(x.get("n")) is int
                and type(x.get("ok")) is bool and isinstance(x.get("why"), str)
                and x["why"].strip() for x in items):
            raise ValueError("Vision array contains incomplete verdicts")
        # The caller still validates expected numbers, uniqueness and coverage.
        return {"checks": items}
    return extract_json(text)


def ask_vision(user: str, images: list[bytes], *, tag="vision", max_tokens=4000, model: str | None = None) -> dict:
    """Картинки + вопрос → JSON (модель config.LLM_MODEL_VISION; model — дешёвая для отбора кандидатов).
    Дешёвая модель бывает перегружена у провайдера (429) или отвечает не-JSON: пробуем её дважды, затем запасную дешёвую, затем основную."""
    import time
    content = [{"type": "image_url", "image_url": {"url": ("data:image/jpeg;base64," if b[:2] == bytes([0xFF, 0xD8]) else "data:image/png;base64,") + base64.b64encode(b).decode()}} for b in images]
    content.append({"type": "text", "text": user})
    chain = [model] * 2 if model else []
    if model and model == config.LLM_MODEL_VISION_CHEAP:   # дешёвая перегружена — запасная дешёвая, потом основная
        chain += [m for m in config.LLM_MODEL_VISION_FALLBACK.split(",") if m and m != model] + [config.LLM_MODEL_VISION]
    elif model and model != config.LLM_MODEL_VISION:       # сильная (финальный QC) — сразу на основную, не на дешёвую
        chain += [config.LLM_MODEL_VISION]
    chain = chain or [config.LLM_MODEL_VISION]
    last = None; skip = set()
    for k, m in enumerate(chain):
        if m in skip: continue   # пустой ответ или не-JSON — повтор той же модели не лечит (Netflix 21.09: 99 пустых ответов подряд, каждый с повтором)
        try:
            resp = _paid_create(model=m, max_tokens=max_tokens, extra_body=_extra(m, "low"),
                messages=[{"role": "system", "content": "Отвечай только валидным JSON без markdown."}, {"role": "user", "content": content}])
            answer = resp.choices[0].message.content or ""; cost = _account(resp)
            _log(tag, f"{m} vision images={len(images)} finish={resp.choices[0].finish_reason} cost=${cost:.4f}", user, answer)
            try: return extract_vision_json(answer)
            except json.JSONDecodeError:   # 28.10 Disney: судья кадров дважды вернул JSON с пропущенной запятой — чиним формат, а не роняем рендер
                if not answer.strip(): raise
                fixed = ask(clean(answer)[-90000:], system=REPAIR_SYSTEM, max_tokens=max_tokens, tag=tag + "_repair", effort="low")
                return extract_vision_json(fixed)
        except Exception as e:
            _log_api_error(e, m, tag)
            if _edge_security_denial(e): raise
            last = e
            if not any(x in str(e).lower() for x in ("429", "rate", "overload", "timeout", "timed out", "connection")) and m != chain[-1]: skip.add(m)
            if k + 1 < len(chain):
                print(f"[vision] {tag}: {m} — {str(e)[:90]}; дальше {chain[k + 1]}")
                if chain[k + 1] == m: time.sleep(4)
    raise last
