"""Озвучка, фоны сцен (Flux), музыка, превью. Параллельно после approve сценария. Считает расходы и держит бюджет."""
import base64, json, os, random, re, shutil, subprocess, threading, requests
from concurrent.futures import ThreadPoolExecutor
from .. import db, config, llm

def run(vid: str):
    from .. import gates
    if not gates.require_script(vid): return
    v = db.get(vid); d = db.video_dir(vid); s = v["payload"]["script"]
    if s.get("shots"):   # story-формат: кадры и титры
        from . import story_assets; return story_assets.run(vid)
    sb = s["storyboard"]
    clean = clean_text(s["script"])
    from .. import money
    spent = money.spent(vid)
    plan = _budget_plan(sb, spent)   # какая модель картинок укладывается в бюджет
    fal_cost = {"usd": 0.0}
    with ThreadPoolExecutor(6) as ex:
        voice = ex.submit(_voice, clean, d)
        visuals = [ex.submit(_visual, sc, d, plan, fal_cost) for sc in sb]
        thumbs = [ex.submit(_thumb, c, d, "abc"[i], plan, fal_cost) for i, c in enumerate(s.get("thumbnail_concepts", [])[:3])]
        music = ex.submit(_music, s.get("music_mood") or "calm", d, fal_cost)
        voice.result()
        for f in visuals + thumbs + [music]: f.result()
    _write_timeline(vid, d, sb)
    total = round(spent + fal_cost["usd"] + llm.take_cost(), 4)
    db.update(vid, "assets", payload={"script": {**s, "storyboard": sb}, "cost_usd": total, "image_model": plan["model"], "tts_chars": len(clean)})
    print(f"[assets] расходы на видео: ${total:.2f} (картинки {plan['model']} ~${fal_cost['usd']:.2f})")

def clean_text(script: str) -> str:
    """Текст для озвучки: без [Fn], тегов <short>, markdown-заголовков и жирного."""
    # и списки «[F15, F16]»: v3 принимал их за тег подачи, а в субтитрах Amazon оставалось «segment . Thirty years…»
    t = re.sub(r"\s*[\[(]\s*F\d+(?:\s*,\s*F\d+)*\s*[\])]", "", script)
    t = re.sub(r"</?short>", "", t)
    t = re.sub(r"^\s*#+\s*", "", t, flags=re.M)
    t = t.replace("**", "")
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r" +([.,;:!?])", r"\1", t)
    return re.sub(r"\n{3,}", "\n\n", t).strip()

# ---------- бюджет ----------

def _budget_plan(sb: list[dict], spent: float) -> dict:
    """Фоны на все сцены + 3 превью. Если с основной моделью не влезаем в BUDGET_USD — берём дешёвую."""
    n = sum(1 for sc in sb if config.SCENE_IMAGES) + 3
    for model in (config.IMAGE_MODEL, config.IMAGE_MODEL_CHEAP):
        est = n * config.image_price(model, config.IMAGE_WIDTH, config.IMAGE_HEIGHT)
        if spent + est <= config.BUDGET_USD: return {"model": model, "estimate": est}
    raise RuntimeError(f"Бюджет превышен: потрачено ${spent:.2f}, картинки требуют ещё ~${est:.2f}, лимит ${config.BUDGET_USD:.2f}")

# ---------- голос ----------

def _chunks(text: str, limit: int) -> list[str]:
    """Режем по абзацам (лимит модели — 10k символов на запрос), длинный абзац — по предложениям."""
    parts = []
    for para in re.split(r"\n\s*\n", text):
        para = para.strip()
        if not para: continue
        units = [para] if len(para) <= limit else re.split(r"(?<=[.!?])\s+", para)
        for u in units:
            if parts and len(parts[-1]) + len(u) + 2 <= limit: parts[-1] += ("\n\n" if u is para else " ") + u
            else: parts.append(u)
    return parts

def _duration(path) -> float:
    return float(subprocess.check_output([config.ffprobe(), "-v", "error", "-show_entries", "format=duration",
                                          "-of", "csv=p=0", str(path)]))

def _words(a, offset: float) -> list[dict]:
    """Слова с таймингами из посимвольной разметки. Теги подачи ElevenLabs v3 («[thoughtful]», «[short pause]») есть в символах,
    но не звучат — символы внутри квадратных скобок пропускаем, иначе якоря сцен не находятся."""
    out, cur, start, end, tag = [], "", None, None, False
    for ch, t0, t1 in zip(a.characters, a.character_start_times_seconds, a.character_end_times_seconds):
        if ch == "[": tag = True; continue
        if tag:
            if ch == "]": tag = False
            continue
        if ch.isspace():
            if cur: out.append({"w": cur, "s": round(start + offset, 3), "e": round(end + offset, 3)}); cur, start = "", None
        else:
            if start is None: start = t0
            cur += ch; end = t1
    if cur: out.append({"w": cur, "s": round(start + offset, 3), "e": round(end + offset, 3)})
    return out

def _voice_settings():
    from elevenlabs import VoiceSettings
    if config.ELEVENLABS_MODEL.startswith("eleven_v3"):   # v3 принимает только stability из {0, 0.5, 1}
        return VoiceSettings(stability=0.5, similarity_boost=config.TTS_SIMILARITY, use_speaker_boost=True)
    return VoiceSettings(stability=config.TTS_STABILITY, similarity_boost=config.TTS_SIMILARITY, style=config.TTS_STYLE, use_speaker_boost=True)

def _get(url: str, timeout: float = 180, tries: int = 4) -> bytes:
    """Скачивание с повторами: CDN fal (v3b.fal.media) через VPN иногда обрывает чтение на больших файлах (озвучка 5 МБ, картинки)."""
    import time
    from urllib.parse import urlsplit
    if url.startswith("data:"):   # sync_mode: картинка уже в ответе fal
        import base64; return base64.b64decode(url.split(",", 1)[1])
    if urlsplit(url).hostname == "v3b.fal.media":
        from ..downloads import fal_ranges
        return fal_ranges(url, timeout=timeout)
    last = None
    for i in range(tries):
        try:
            r = requests.get(url, timeout=(20, timeout), stream=True); r.raise_for_status()
            return b"".join(r.iter_content(1 << 16))
        except Exception as e:
            last = e; print(f"[download] попытка {i + 1}/{tries} не удалась: {str(e)[:80]}"); time.sleep(5 * (i + 1))
    raise RuntimeError(f"не скачалось после {tries} попыток: {last}")

def _loudnorm(p):
    """Громкость куска озвучки к единому уровню (EBU R128, −18 LUFS) полным ffmpeg; длительность и тайминги слов не меняются."""
    import imageio_ffmpeg
    out = p.with_name(p.stem + "_n.mp3")
    r = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-v", "error", "-i", str(p), "-af", "loudnorm=I=-18:TP=-1.5:LRA=11", "-ar", "44100",
                        "-c:a", "libmp3lame", "-b:a", "128k", str(out)], capture_output=True)
    if r.returncode or not out.exists(): print(f"[voice] loudnorm {p.name}: {r.stderr[-120:]}"); return p
    if abs(_duration(out) - _duration(p)) > 0.08: out.unlink(); return p
    p.unlink(); out.rename(p); return p

TTS_CTX = {"vid": ""}          # какой ролик сейчас озвучивается — для учёта расхода (аудит 23.09)
TTS_USD_PER_1K = 0.10          # ElevenLabs v3 через fal

TTS_V4_USD_PER_1K = 0.08       # ElevenLabs v4 через fal (прайс fal 01.10)
def _tts_account(chars: int, per_1k: float | None = None, model: str = "eleven_v3") -> float:
    """Каждый платный запрос озвучки — строкой в data/tts_spend.jsonl: раньше голос (половина расходов на fal) нигде не был виден."""
    usd = round(chars * (TTS_USD_PER_1K if per_1k is None else per_1k) / 1000, 4)
    try:
        with open(config.DATA / "tts_spend.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps({"vid": TTS_CTX.get("vid") or "", "chars": chars, "usd": usd, "model": model}, ensure_ascii=False) + "\n")
    except Exception: pass
    return usd

def _tts_fal_v3(text: str, voice_id: str, stability: float | None = None):
    """ElevenLabs v3 через fal: тот же голос, пословные тайминги; теги подачи в тексте не звучат."""
    import types, fal_client
    _tts_account(len(text))
    r = fal_client.subscribe("fal-ai/elevenlabs/tts/eleven-v3", arguments={"text": text, "voice": voice_id, "stability": config.TTS_V3_STABILITY if stability is None else stability, "timestamps": True})
    audio = _get(r["audio"]["url"], timeout=300)
    merged = {"characters": [], "character_start_times_seconds": [], "character_end_times_seconds": []}
    for a in (r.get("timestamps") or []):
        for k in merged: merged[k] += list(a.get(k) or [])
    return audio, types.SimpleNamespace(**merged)

def _tts_fal_v4(text: str, voice_id: str):
    """ElevenLabs v4 через fal (владелец 01.10): тот же голос, пословные тайминги; настройки по умолчанию — на них владелец слушал образец.
    previous_text/next_text у v4 нет — непрерывность даёт цепочка с хвостом предыдущего куска (voice_chain)."""
    import types, fal_client
    _tts_account(len(text), TTS_V4_USD_PER_1K, "eleven_v4")
    r = fal_client.subscribe("fal-ai/elevenlabs/tts/eleven-v4", arguments={"text": text, "voice": voice_id, "timestamps": True})
    audio = _get(r["audio"]["url"], timeout=300)
    merged = {"characters": [], "character_start_times_seconds": [], "character_end_times_seconds": []}
    for a in (r.get("timestamps") or []):
        for k in merged: merged[k] += list(a.get(k) or [])
    return audio, types.SimpleNamespace(**merged)

def _plain_words(s: str) -> list[str]:
    s = re.sub(r"\[[^\]]*\]", " ", s)
    s = s.replace("…", "...").replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return re.findall(r"[A-Za-z0-9$%']+", s.lower())

def _tag_chunk(chunk: str, prev: str | None = None, prompt: str = "voice_tags") -> str:
    """Разметка интонаций для v3 (Qwen): теги подачи в квадратных скобках, слова не меняются. Если модель тронула слова — кусок без тегов."""
    try:
        res = llm.ask_json(config.prompt(prompt, text=chunk, previous=(prev or "")[-600:] or "(начало ролика)"), heavy=True, max_tokens=4000, tag="voice_tags")
        tagged = (res.get("text") or "").strip()
    except Exception as e:
        print(f"[voice] разметка не удалась: {str(e)[:80]} — кусок без тегов"); return chunk
    if not tagged or _plain_words(tagged) != _plain_words(chunk):
        print("[voice] разметка изменила слова — кусок без тегов"); return chunk
    return tagged

def _tts_blocked(e: Exception) -> bool:
    """ElevenLabs напрямую закрыт по региону: вместо JSON приходит HTML-страница «restrict access» или Cloudflare-челлендж."""
    s = str(e)
    return any(k in s for k in ("restrict-access", "Just a moment", "text/html", "cf-mitigated", "status_code: 403"))

def _tts_fal(text: str, voice_id: str, prev: str | None, nxt: str | None):
    """Тот же ElevenLabs multilingual v2, но через fal (гео-независимо; тот же голос, те же настройки, те же пословные тайминги)."""
    import types, fal_client
    args = {"text": text, "voice": voice_id, "stability": config.TTS_STABILITY, "similarity_boost": config.TTS_SIMILARITY, "style": config.TTS_STYLE, "timestamps": True}
    if prev: args["previous_text"] = prev
    if nxt: args["next_text"] = nxt
    r = fal_client.subscribe("fal-ai/elevenlabs/tts/multilingual-v2", arguments=args)
    audio = _get(r["audio"]["url"], timeout=300)
    merged = {"characters": [], "character_start_times_seconds": [], "character_end_times_seconds": []}
    for a in (r.get("timestamps") or []):
        for k in merged: merged[k] += list(a.get(k) or [])
    return audio, types.SimpleNamespace(**merged)

def retempo(d, sections: list[str]) -> float | None:
    """Подогнать темп озвучки к TTS_TARGET_WPM: темп речи и пауз масштабируется почти линейно, поэтому одна пересборка из кэша кусков
    (без запросов к TTS) попадает в цель. Возвращает новый множитель или None, если поправка не нужна."""
    if not config.TTS_TARGET_WPM: return None
    w = json.loads(config.read(d / "words.json")); wpm = len(w) / max(1e-6, (w[-1]["e"] - w[0]["s"]) / 60)
    if abs(wpm / config.TTS_TARGET_WPM - 1) <= 0.03: return None
    t = max(0.9, min(1.35, config.TTS_TEMPO * config.TTS_TARGET_WPM / wpm))
    print(f"[voice] темп {wpm:.0f} слов/мин при ×{config.TTS_TEMPO:g} — пересобираю с ×{t:.3f} под {config.TTS_TARGET_WPM:.0f}", flush=True)
    from . import voice_chain; voice_chain.build(d, sections, tempo=t); return t

def _voice(text: str, d, sections: list[str] | None = None, tags_prompt: str = "voice_tags", stability: float | None = None):
    """sections — части сценария (главы). В режиме v3 каждая глава озвучивается одним запросом: v3 не склеивает куски между собой,
    и каждый запрос звучит чуть иначе — стык прячется под паузой главы с карточкой и сменой музыки (владелец 16.09: «после 6 минут резко меняется голос»)."""
    import hashlib
    voice_id = os.getenv("ELEVENLABS_VOICE_ID")
    if not voice_id: raise RuntimeError("ELEVENLABS_VOICE_ID пуст — выбери голос и положи id в .env")
    if config.TTS_MODE == "v3_chain" and sections and _plain_words(" ".join(sections)) == _plain_words(text):
        # озвучка цепочкой (stages/voice_chain.py): короткие куски с хвостом предыдущего, проверка стыков отпечатком голоса — манера не прыгает между главами
        tempo = (f"tempo{config.TTS_TEMPO:g}|" if config.TTS_TEMPO != 1 else "") + (f"wpm{config.TTS_TARGET_WPM:g}|" if config.TTS_TARGET_WPM else "")   # смена темпа — пересборка из кэша кусков, без новых запросов
        sha = hashlib.sha1(("v3_chain|" + tempo + text).encode("utf-8")).hexdigest(); mark = d / "voice.sha"
        if mark.exists() and mark.read_text().strip() == sha and (d / "voice.mp3").exists() and (d / "words.json").exists():
            print("[voice] озвучка этого текста уже есть — пропускаю"); return
        from . import voice_chain
        voice_chain.build(d, sections); retempo(d, sections); mark.write_text(sha); return
    v3 = config.TTS_MODE in ("v3_tags", "v3_chain")   # владелец 16.09 выбрал вариант C: ElevenLabs v3 + разметка интонаций
    # озвучка того же текста в том же режиме уже есть (повтор этапа после падения на кадрах) — не платим второй раз
    key = config.TTS_MODE + "|" + text
    if tags_prompt != "voice_tags" or stability is not None: key = f"{config.TTS_MODE}|{tags_prompt}|{stability}|{text}"   # старые sha длинных роликов не меняются
    sha = hashlib.sha1(key.encode("utf-8")).hexdigest(); mark = d / "voice.sha"
    if mark.exists() and mark.read_text().strip() == sha and (d / "voice.mp3").exists() and (d / "words.json").exists():
        print("[voice] озвучка этого текста уже есть — пропускаю"); return
    if v3 and sections and _plain_words(" ".join(sections)) == _plain_words(text):
        chunks = []
        for sec in sections:   # глава целиком, если влезает в лимит запроса; иначе режем по абзацам (стык внутри главы — редкость)
            chunks += [sec] if len(sec) <= config.TTS_V3_MAX_CHARS else _chunks(sec, config.TTS_CHUNK_CHARS)
        print(f"[voice] v3: {len(chunks)} запросов по главам (стыки под паузами глав)", flush=True)
    else:
        chunks = _chunks(text, config.TTS_CHUNK_CHARS)
    words, offset, parts = [], 0.0, []
    el, use_fal = None, os.getenv("TTS_VIA_FAL", "0") == "1"
    for i, ch in enumerate(chunks):
        prev, nxt = (chunks[i - 1] if i else None), (chunks[i + 1] if i + 1 < len(chunks) else None)
        say = _tag_chunk(ch, prev, tags_prompt) if v3 else ch   # шортсы — энергичная разметка (voice_tags_short)
        if not use_fal:
            try:
                if el is None:
                    from elevenlabs.client import ElevenLabs; el = ElevenLabs()
                if v3:   # v3 не поддерживает previous_text/next_text; stability только 0 / 0.5 / 1
                    from elevenlabs import VoiceSettings
                    r = el.text_to_speech.convert_with_timestamps(voice_id, text=say, model_id="eleven_v3", output_format="mp3_44100_128",
                                                                  voice_settings=VoiceSettings(stability=config.TTS_V3_STABILITY if stability is None else stability))
                else:
                    r = el.text_to_speech.convert_with_timestamps(
                        voice_id, text=ch, model_id=config.ELEVENLABS_MODEL, output_format="mp3_44100_128", voice_settings=_voice_settings(),
                        previous_text=prev, next_text=nxt)
                audio, align = base64.b64decode(r.audio_base_64), r.alignment
            except Exception as e:
                if not _tts_blocked(e): raise
                print("[voice] ElevenLabs напрямую закрыт по региону — озвучка через fal (тот же голос и тайминги)"); use_fal = True
        if use_fal:
            audio, align = _tts_fal_v3(say, voice_id, stability) if v3 else _tts_fal(ch, voice_id, prev, nxt)
        print(f"[voice] кусок {i + 1}/{len(chunks)}: {len(ch)} символов" + (f", тегов {len(re.findall(r'\[[^\]]+\]', say))}" if v3 else ""), flush=True)
        p = d / f"voice_part{i}.mp3"; p.write_bytes(audio)
        if v3: p = _loudnorm(p)   # разные запросы v3 чуть отличаются по громкости — выравниваем до склейки (длительность не меняется)
        parts.append(p)
        words += _words(align, offset)
        offset += _duration(p)
    if len(parts) == 1:
        parts[0].replace(d / "voice.mp3")
    else:   # склейка с перекодированием — без стыков и с точными оффсетами
        lst = d / "voice_parts.txt"
        config.write(lst, "\n".join(f"file '{p.name}'" for p in parts))
        subprocess.run([config.ffmpeg(), "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", lst.name,
                        "-c:a", "libmp3lame", "-b:a", "128k", "voice.mp3"], cwd=d, check=True)
        for p in parts: p.unlink()
        lst.unlink()
    config.write(d / "words.json", json.dumps(words)); mark.write_text(sha)

# ---------- визуал сцен ----------

_ai_budget = {"used": 0}; _lock = threading.Lock()
# единый стиль всех фонов — это и есть «единый видеоряд»: одна палитра, один свет, одна оптика
IMAGE_STYLE = (", cinematic still frame, muted cold palette with one warm accent, soft directional light, light haze, "
               "35mm lens, shallow depth of field, subtle film grain, no text, no lettering, no signage, no logos, no brand names, no watermark, no one looking at camera")

def _visual(scene: dict, d, plan: dict, fal_cost: dict):
    """Фон для любой сцены (Flux) + видео-клип для broll в пределах бюджета (Kling). Ошибки не валят этап."""
    scene["src"] = None; scene.setdefault("image", None)
    is_broll = scene["type"].startswith("broll")
    data = scene.get("data") or {}
    try:
        if is_broll:
            vp = data.get("video_prompt") or data.get("prompt")
            with _lock:
                use_ai = bool(vp) and _ai_budget["used"] < config.AI_BROLL_MAX_CLIPS
                if use_ai: _ai_budget["used"] += 1
            if use_ai:
                import fal_client
                (d / "broll").mkdir(exist_ok=True); out = d / "broll" / f"{scene['id']}.mp4"
                r = fal_client.subscribe("fal-ai/kling-video/v2.5-turbo/pro/text-to-video",
                                         arguments={"prompt": vp + ", cinematic, no text, no watermark", "duration": "5", "aspect_ratio": "16:9"})
                out.write_bytes(requests.get(r["video"]["url"], timeout=300).content)
                with _lock: fal_cost["usd"] += config.KLING_CLIP_PRICE
                scene["src"] = f"broll/{scene['id']}.mp4"; scene["clip_seconds"] = _duration(out)
                return
        prompt = scene.get("image_prompt") or data.get("prompt") or data.get("query")
        if config.SCENE_IMAGES and prompt:
            scene["image"] = _image(prompt, d, scene["id"], plan["model"])
            with _lock: fal_cost["usd"] += config.image_price(plan["model"], config.IMAGE_WIDTH, config.IMAGE_HEIGHT)
        elif is_broll:   # старый режим: сток Pexels
            q = data.get("query") or (prompt or "")[:40]
            (d / "broll").mkdir(exist_ok=True); out = d / "broll" / f"{scene['id']}.mp4"
            if q and (_pexels(q, out) or _pexels(" ".join(q.split()[:2]), out)):
                scene["src"] = f"broll/{scene['id']}.mp4"; scene["clip_seconds"] = _duration(out)
    except Exception as e:
        print(f"[visual] {scene['id']}: {e}")

# Слова, после которых генератор обязательно напишет на картинке абракадабру (Boston Market 24.09).
DOC_WORDS = re.compile(r"\b(diploma|diplomas|degree certificate|license|licence|deed|deeds|title deed|bond certificate|stock certificate|cheque|check stub|banknote|poster|signboard|document|documents|ledger|ledgers|spreadsheet|balance sheet|annual report|10-?k|filing|filings|"
                       r"prospectus|certificate|share certificate|stock certificate|contract|agreement|invoice|receipt|"
                       r"statement|statements|memo|memorandum|report|reports|newspaper|headline|chart|graph|diagram|"
                       r"screen|monitor|laptop screen|dashboard|table of numbers|printout|letter|telegram|form|blueprint)\b", re.I)
# Чем заменяем: предметный план того же смысла, но без единой читаемой буквы.
DOC_SAFE = ("extreme close-up of hands over a desk, edge of a manila folder and a stack of paper seen at a steep angle, "
            "paper out of focus so no text is legible, typewriter and a metal filing drawer in the background, "
            "warm desk lamp, shallow depth of field, documentary photograph, absolutely no readable text anywhere")


SIGN_WORDS = re.compile(r"\b(sign|signs|signage|signboard|billboard|storefront|shopfront|facade|façade|marquee|banner|van|vans|truck|trucks|"
                        r"fleet|livery|uniform|t-?shirt|jersey|badge|whiteboard|chalkboard|blackboard|cork ?board|bulletin board|index cards?|"
                        r"sticky notes?|post-?it|fax|label|labels|packaging|box|boxes|map|maps|screen|monitor|phone screen|headquarters|office building)\b", re.I)
SIGN_SAFE = (", every sign, wall, vehicle side, garment, board, label and screen completely blank and plain, no lettering, no logos, "
             "no numbers, no writing of any kind")   # Safelite 27.09: ~20 кадров с псевдотекстом на вывесках, фургоне, футболке, доске

def _sanitize_prompt(prompt: str) -> str:
    """Промпт с документом переписывается в предметный кадр без текста: генератор всё равно напишет абракадабру,
    а цифры и названия в наших роликах несут плашки и подписи, а не сама картинка. Вывески, фасады, машины, одежда,
    доски и экраны — сцена остаётся, но все поверхности пустые (27.09)."""
    if not prompt: return prompt
    clauses = re.split(r"[,;]", prompt)
    negative = [s.strip() for s in clauses if re.match(r"^\s*(?:no|without|avoid|excluding)\b", s, re.I)]
    active = ", ".join(s for s in clauses if not re.match(r"^\s*(?:no|without|avoid|excluding)\b", s, re.I))
    # A ban such as "no documents, no screens" is not a request to generate
    # those objects. Preserve the intended kitchen/car/factory scene.
    if not DOC_WORDS.search(active) and SIGN_WORDS.search(active) and "no lettering" not in prompt:
        return prompt + SIGN_SAFE
    if not DOC_WORDS.search(active): return prompt
    # Keep the useful physical subject when only a secondary paper prop is
    # unsafe. Replacing the entire scene with DOC_SAFE erased propellers,
    # calculators and workshop equipment and bought repetitive desk shots.
    retained = [s.strip() for s in clauses if s.strip()
                and not re.match(r"^\s*(?:no|without|avoid|excluding)\b", s, re.I)
                and not DOC_WORDS.search(s)]
    physical = re.compile(r"\b(calculator|propeller|calipers|engine|aircraft|helmet|tool|tools|trolley|stairs|"
                          r"landing gear|fuselage|keyboard|cabinet|cabinets|briefcase|wrench|socket|sockets)\b", re.I)
    if any(physical.search(s) for s in retained):
        return ", ".join(retained + negative + ["no documents, no readable text, no lettering, no logos, no numbers, blank surfaces"])
    era = ""
    m = re.search(r"\b(18|19|20)\d{2}s?\b", prompt)
    if m: era = f", {m.group(0)} period props and styling"
    if re.search(r"\b(?:no (?:people|person|face|faces|figure|figures)|hands (?:and objects )?only)\b", prompt, re.I):
        negative.append("hands and inanimate objects only, no heads, no torsos, no human figures or silhouettes, faces entirely outside the frame")
    return DOC_SAFE + era + (", " + ", ".join(negative) if negative else "")

def _positive_clauses(prompt: str) -> list[str]:
    return [s.strip() for s in re.split(r'[,;]', prompt)
            if s.strip() and not re.match(r'^\s*(?:no|without|avoid|excluding)\b', s, re.I)]


def _people_forbidden(prompt: str) -> bool:
    return bool(re.search(r'\bno (?:people|person|persons|figures|human figures|silhouettes)\b|\bnobody (?:present|visible)\b', prompt, re.I))


def validate_image_prompt(prompt: str) -> None:
    """Reject a broken scene plan BEFORE purchasing; never replace its meaning silently."""
    active=', '.join(_positive_clauses(prompt))
    if DOC_WORDS.search(active):
        raise ValueError('Image purchase blocked: document, chart or text-bearing prop requires a verified source/native scene or a new explicit visual plan; automatic desk substitution is disabled')
    if _people_forbidden(prompt):
        people=re.compile(r'\b(people|persons?|workers?|mechanics?|employees?|executives?|men|women|man|woman|figures|silhouettes)\b',re.I)
        if people.search(active):
            raise ValueError('Image purchase blocked: the plan requests human figures and forbids them at the same time')


CARTOON = {"on": False}   # 12.10: ролик испанского канала — все сцены (и замены preflight) рисуются мультфильмом

def _image(prompt: str, d, sid: str, model: str, w: int | None = None, h: int | None = None, style: str | None = None, cartoon: bool = False) -> str:
    """style=None — киностиль сцен (IMAGE_STYLE); для обложек передаётся свой (там нужен взгляд в камеру и без зерна).
    Модели ultra берут не размер, а пропорцию, и рисуют сразу в 2K — обложке это на пользу."""
    import fal_client
    (d / "images").mkdir(exist_ok=True); out = d / "images" / f"{sid}.png"
    if style is None and not (cartoon or CARTOON["on"]):   # только сцены; обложки — своим стилем; мультфильм пишет испанские надписи сам (13.10)
        validate_image_prompt(prompt)
        prompt = _sanitize_prompt(prompt)  # Only nonsemantic precautions remain: documents were rejected above.
    w, h = w or config.IMAGE_WIDTH, h or config.IMAGE_HEIGHT
    image_style=IMAGE_STYLE if style is None else style
    if cartoon or (style is None and CARTOON["on"]): image_style = config.CARTOON_STYLE   # 12.10 испанский мультфильм: шаржи и яркие цвета вместо киностиля
    if style is None and _people_forbidden(prompt):
        image_style=image_style.replace(', no one looking at camera','')
    r = fal_client.subscribe(model, arguments=image_args(model, prompt + image_style, w, h, thumb=style is not None))
    out.write_bytes(_get(r["images"][0]["url"], timeout=120))
    return f"images/{sid}.png"

def image_args(model: str, prompt: str, w: int, h: int, thumb: bool = False) -> dict:
    """Аргументы fal под семейство модели (схемы сняты 18.09.2026). ultra/MAI/Reve берут пропорцию; GPT Image — размер кратный 16 и качество
    (сцены — medium, обложки — high: config.GPT_IMAGE_QUALITY); остальные — точный размер."""
    ar = "16:9" if w > h else ("9:16" if h > w else "1:1")
    args = {"prompt": prompt}
    if "ultra" in model or "mai-image" in model or "/reve/" in model: args["aspect_ratio"] = ar
    elif "gpt-image" in model:
        args["image_size"] = {"width": round(w / 16) * 16, "height": round(h / 16) * 16}
        args["quality"] = config.GPT_IMAGE_QUALITY_THUMB if thumb else config.GPT_IMAGE_QUALITY
        args["output_format"] = "png"
    else: args["image_size"] = {"width": w, "height": h}
    if "gpt-image" in model or "flux" in model: args["sync_mode"] = True   # 13.10: картинка в ответе, без медленного CDN
    if "schnell" in model: args["num_inference_steps"] = 4
    if "/wan/" in model: args["output_format"] = "png"
    return args

def cutout(src, out, portrait: bool = True, trim: bool = True) -> tuple[int, int, int, int] | None:
    """Вырезка фигуры/предмета для обложки (BiRefNet v2, MIT). Аудит 18.09: вариант по умолчанию «General Use (Light)» 1024² терял волосы —
    для людей Portrait, для предметов Heavy, оба в 2048². trim — обрезка по альфе (так делались *_cut_trim.png обложек). Возвращает bbox."""
    import fal_client
    from PIL import Image
    r = fal_client.subscribe("fal-ai/birefnet/v2", arguments={"image_url": fal_client.upload_file(str(src)), "operating_resolution": "2048x2048",
                                                              "model": "Portrait" if portrait else "General Use (Heavy)", "refine_foreground": True,
                                                              "output_format": "png"})
    out.write_bytes(_get(r["image"]["url"], timeout=180))
    im = Image.open(out); bb = im.split()[-1].getbbox()
    if trim and bb: im.crop(bb).save(out)
    return bb

def _saliency_focus(path) -> list[float]:
    """Точка фокуса для Ken Burns (docs/scene-grammar.md §2.1): 256 px по ширине → blur 2 px (зерно и мелкий текст не тянут точку)
    → лапласиан → сетка 5×5 с весом к центру (1 − 0.6·dist) → центр масс лучшей клетки → кламп [0.3, 0.7] → смесь с центром 50/50.
    Любая ошибка → центр кадра."""
    try:
        import numpy as np
        from PIL import Image, ImageFilter
        im = Image.open(path).convert("L")
        w = 256; h = max(8, round(im.height * w / im.width))
        im = im.resize((w, h)).filter(ImageFilter.GaussianBlur(2))
        a = np.asarray(im, dtype=np.float32)
        lap = np.abs(-4 * a[1:-1, 1:-1] + a[:-2, 1:-1] + a[2:, 1:-1] + a[1:-1, :-2] + a[1:-1, 2:])
        H, W = lap.shape; best, best_score = None, -1.0
        for gy in range(5):
            for gx in range(5):
                y0, y1 = H * gy // 5, H * (gy + 1) // 5; x0, x1 = W * gx // 5, W * (gx + 1) // 5
                cell = lap[y0:y1, x0:x1]
                if cell.size == 0: continue
                dist = (((gx - 2) / 2) ** 2 + ((gy - 2) / 2) ** 2) ** 0.5 / 2 ** 0.5
                score = float(cell.mean()) * (1 - 0.6 * dist)
                if score > best_score: best_score, best = score, (y0, y1, x0, x1)
        y0, y1, x0, x1 = best; cell = lap[y0:y1, x0:x1]; tot = float(cell.sum())
        if tot <= 0: return [0.5, 0.5]
        ys, xs = np.mgrid[y0:y1, x0:x1]
        cx = float((xs * cell).sum() / tot) / W; cy = float((ys * cell).sum() / tot) / H
        sx, sy = min(0.7, max(0.3, cx)), min(0.7, max(0.3, cy))
        return [round(0.25 + 0.5 * sx, 3), round(0.25 + 0.5 * sy, 3)]
    except Exception as e:
        print(f"[focus] {path}: {e}"); return [0.5, 0.5]

def _pexels(q: str, out) -> bool:
    r = requests.get("https://api.pexels.com/videos/search", params={"query": q, "per_page": 8, "orientation": "landscape"},
                     headers={"Authorization": os.getenv("PEXELS_API_KEY")}, timeout=60).json()
    vids = r.get("videos") or []
    if not vids: return False
    best = max(vids, key=lambda x: x["width"])
    files = [f for f in best["video_files"] if f.get("width") and f["width"] <= 1920] or best["video_files"]
    f = max(files, key=lambda x: x.get("width") or 0)
    out.write_bytes(requests.get(f["link"], timeout=300).content)
    return True

def _thumb(concept: dict, d, letter: str, plan: dict, fal_cost: dict):
    try:
        import fal_client
        # обложка — своя модель (config.THUMB_IMAGE_MODEL), не сценовая: до 18.09 константа была объявлена, но сюда не доходила
        model = config.THUMB_IMAGE_MODEL or plan["model"]
        r = fal_client.subscribe(model, arguments=image_args(model, concept["visual"] + ", editorial photography, high contrast, clean background"
                                                             + config.THUMB_IMAGE_STYLE, 1920, 1080, thumb=True))
        (d / f"thumb_{letter}_raw.png").write_bytes(_get(r["images"][0]["url"], timeout=120))
        config.write(d / f"thumb_{letter}.json", json.dumps(concept, ensure_ascii=False))  # текст накладывает Remotion (Still)
        with _lock: fal_cost["usd"] += 0.04 if "gpt-image" in model else config.image_price(model, 1920, 1080)
    except Exception as e:
        print(f"[thumb] {letter}: {e}")

# ---------- музыка ----------

def _music(mood: str, d, fal_cost: dict):
    """Ambient под голос: трек из data/music/ (имя файла содержит настроение: calm / tense / driving / warm),
    иначе любой из библиотеки, иначе — генерация (MUSIC_GENERATE=1), иначе без музыки."""
    try:
        lib = [p for p in config.MUSIC.glob("*") if p.suffix.lower() in (".mp3", ".wav", ".m4a", ".ogg")]
        pick = [p for p in lib if mood.lower() in p.stem.lower()] or lib
        if pick:
            src = random.choice(pick); shutil.copy(src, d / ("music" + src.suffix.lower())); print(f"[music] {src.name} ({mood})"); return
        if config.MUSIC_GENERATE:
            import fal_client
            r = fal_client.subscribe("fal-ai/stable-audio-25/text-to-audio", arguments={
                "prompt": f"{mood} ambient background music for a documentary about business, minimal, no drums, no vocals, slow evolving pads", "seconds_total": 180})
            (d / "music.mp3").write_bytes(requests.get(r["audio_file"]["url"], timeout=300).content)
            with _lock: fal_cost["usd"] += 0.2
            print("[music] сгенерирован ambient"); return
        print("[music] библиотека data/music пуста — видео без музыки")
    except Exception as e:
        print(f"[music] {e}")

# ---------- таймлайн ----------

def _music_volume(d, music) -> float:
    if not music: return 0.0
    try:
        from .. import loudness
        return loudness.music_gain(d / "voice.mp3", d / music, config.MUSIC_BELOW_DB)
    except Exception as e:
        print(f"[loudness] {e} — беру MUSIC_VOLUME={config.MUSIC_VOLUME}"); return config.MUSIC_VOLUME

def _norm(w: str) -> str: return w.lower().strip(".,!?;:\"'“”‘’()")

def _find(text: list[str], phrase: list[str], start=0):
    n = len(phrase)
    if not n: return None
    return next((i for i in range(start, len(text) - n + 1) if text[i:i + n] == phrase), None)

def _write_timeline(vid: str, d, sb: list[dict]) -> dict:
    """Привязывает каждую сцену к таймкоду по anchor-фразе в пословных таймингах."""
    v = db.get(vid); words = json.loads(config.read(d / "words.json"))
    text = [_norm(w["w"]) for w in words]
    pos = 0
    for sc in sb:
        anchor = [_norm(a) for a in re.sub(r"\[F\d+\]", "", sc.get("anchor", "")).split()]
        anchor = [a for a in anchor if a]
        idx = None
        for n in (5, 4, 3):
            idx = _find(text, anchor[:n], pos) or _find(text, anchor[:n])
            if idx is not None: break
        sc["start"] = words[idx]["s"] if idx is not None else None
        if idx is not None: pos = idx
    for i, sc in enumerate(sb):   # сцены без найденного якоря — середина между соседями
        if sc["start"] is None:
            prev = next((x["start"] for x in reversed(sb[:i]) if x["start"] is not None), 0)
            nxt = next((x["start"] for x in sb[i + 1:] if x["start"] is not None), words[-1]["e"])
            sc["start"] = (prev + nxt) / 2
    sb.sort(key=lambda x: x["start"])
    sb[0]["start"] = 0.0
    for i, sc in enumerate(sb):
        sc["end"] = sb[i + 1]["start"] if i + 1 < len(sb) else words[-1]["e"] + 1.5
    music = next((f"music{p.suffix.lower()}" for p in d.glob("music.*")), None)
    tl = {"scenes": sb, "duration": words[-1]["e"] + 2, "shorts": _short_segments(v["payload"]["script"]["script"], words),
          "channel": config.CHANNEL_NAME, "title": v["title"], "music": music, "music_volume": _music_volume(d, music)}
    config.write(d / "timeline.json", json.dumps(tl, ensure_ascii=False, indent=2))
    return tl

def _short_segments(script: str, words):
    """<short>…</short> в сценарии → интервалы времени по первым/последним словам сегмента."""
    segs = []; text = [_norm(w["w"]) for w in words]
    for m in re.finditer(r"<short>(.*?)</short>", script, re.S):
        ws = [_norm(x) for x in re.sub(r"\[F\d+\]", "", m.group(1)).split()]; ws = [x for x in ws if x]
        if len(ws) < 8: continue
        si = _find(text, ws[:4]); ei = _find(text, ws[-4:], si or 0)
        if si is not None and ei is not None and ei > si:
            segs.append({"start": round(max(0, words[si]["s"] - 0.2), 3), "end": round(words[ei + 3]["e"] + 0.4, 3)})
    return segs[:config.SHORTS_PER_VIDEO]
