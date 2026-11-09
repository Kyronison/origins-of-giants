"""Озвучка «цепочкой» для ElevenLabs v3 (владелец 16–17.09 трижды: «между главами совсем разный голос»).

Что показали замеры Apple: диктор тот же (близость отпечатков голоса 0.85–0.97, тембр по полосам ±1 dB), но КАЖДЫЙ запрос v3 начинается
«свежим дублем» — выше на ~10 %, театральнее, медленнее — и успокаивается за 20–40 с. Глава = запрос, поэтому на каждой главе манера
прыгала: конец главы спокойный и быстрый, начало следующей — «трейлерное». Контекст из одной фразы не помогал: дубль длиннее фразы.

Схема:
  • текст главы режется на куски CHUNK_MIN–CHUNK_MAX символов по абзацам и предложениям (у коротких запросов v3 манера не уплывает);
  • запрос = хвост предыдущего куска (LEAD_MIN–LEAD_MAX символов, 2–3 фразы ≈ 10–15 с) + кусок; «свежий дубль» приходится на хвост и
    отрезается по таймингам в тихой точке; первому куску ролика хвостом служит нейтральная фраза FIRST_LEAD;
  • stability 0.5, теги только окраски (prompts/voice_tags_v2.md);
  • проверка каждого стыка: отпечаток голоса (voiceprint) последних/первых SEAM_SEC секунд, скачок высоты и размаха интонации; порог — по
    разбросу внутри кусков этого же ролика; плохой стык → кусок генерируется заново (до REROLLS раз), берётся лучший кандидат;
  • выравнивание: громкость речи к SPEECH_DB, темп куска к медиане ролика (±TEMPO_CLAMP, atempo — высота не меняется);
  • паузы между кусками задаются явно (абзац PARA_GAP, иначе SENT_GAP), хвосты — с затуханием; граница глав пишется в voice_parts.json —
    pauses.ensure режет ровно по ней (раньше рез «по концу слова + 0.15 с» захватывал начало следующей главы: щелчок «дже-» от «January»).
Сырые куски кэшируются в voice_chain/ по sha (текст + настройки): повтор и пересборка соседних глав не платят второй раз."""
import hashlib, json, os, re, subprocess
from concurrent.futures import ThreadPoolExecutor
import numpy as np
from .. import config, llm
from . import assets as A

SR = 44100
CHUNK_MIN, CHUNK_MAX = 900, 1600
LEAD_MIN, LEAD_MAX = 160, 360
FIRST_LEAD = "Some stories begin long before anyone notices them. This one does too, so let us start at the very beginning."
STABILITY = 0.5
TAGS_PROMPT = "voice_tags_v2"
SEAM_SEC = 12.0
REROLLS = int(os.getenv("VOICE_REROLLS", 1))   # 23.09: при 2 дублях 27–60 % оплаченных кусков выбрасывались, ровность стыков не росла
SPEECH_DB = -20.0
TEMPO_CLAMP = 0.07
PARA_GAP, SENT_GAP = 0.62, 0.42


def _ff() -> str:
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def _decode_bytes(data: bytes, sr: int = SR) -> np.ndarray:
    raw = subprocess.run([_ff(), "-v", "error", "-i", "-", "-f", "f32le", "-ac", "1", "-ar", str(sr), "-"], input=data, capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32).copy()


def _filter(x: np.ndarray, af: str, sr: int = SR, out_sr: int | None = None) -> np.ndarray:
    raw = subprocess.run([_ff(), "-v", "error", "-f", "f32le", "-ar", str(sr), "-ac", "1", "-i", "-", "-af", af, "-f", "f32le", "-ac", "1", "-ar", str(out_sr or sr), "-"],
                         input=x.astype(np.float32).tobytes(), capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32).copy()


def _env_db(x: np.ndarray, sr: int = SR, step: float = 0.01) -> np.ndarray:
    n = int(sr * step); k = len(x) // n
    return 20 * np.log10(np.sqrt((x[:k * n].reshape(k, n) ** 2).mean(axis=1)) + 1e-7)


def _sentences(t: str) -> list[str]:
    return [p for p in re.split(r"(?<=[.!?…])[\"”’)]*\s+", t.strip()) if p]


def chunks_of(section: str) -> list[dict]:
    """Куски главы: абзацы склеиваются до CHUNK_MIN, длинный абзац режется по предложениям; para=True — кусок начинается с нового абзаца."""
    out = []
    for para in [p.strip() for p in re.split(r"\n\s*\n", section) if p.strip()]:
        units = [para] if len(para) <= CHUNK_MAX else _sentences(para)
        first = True
        for u in units:
            if out and len(out[-1]["text"]) < CHUNK_MIN and len(out[-1]["text"]) + len(u) + 1 <= CHUNK_MAX:
                out[-1]["text"] += ("\n\n" if first and u is para else " ") + u
            else:
                out.append({"text": u, "para": first})
            first = False
    if len(out) > 1 and len(out[-1]["text"]) < CHUNK_MIN * 0.5 and len(out[-2]["text"]) + len(out[-1]["text"]) < CHUNK_MAX * 1.15:   # огрызок в конце главы
        tail = out.pop(); out[-1]["text"] += ("\n\n" if tail["para"] else " ") + tail["text"]
    return out


def _lead(prev_text: str | None) -> str:
    if not prev_text: return FIRST_LEAD
    sents, lead = _sentences(re.sub(r"\s+", " ", prev_text)), ""
    for s in reversed(sents):
        if lead and len(lead) + len(s) > LEAD_MAX: break
        lead = (s + " " + lead).strip()
        if len(lead) >= LEAD_MIN: break
    return lead or FIRST_LEAD


def _f0(x: np.ndarray, sr: int = SR) -> tuple[float, float]:
    """Медиана и размах (p90 − p10) высоты голоса, Гц — автокорреляция на 16 кГц."""
    y = _filter(x, "anull", sr, 16000); fs = 16000
    N, H, vals = int(0.04 * fs), int(0.02 * fs), []
    win = np.hanning(N)
    for i in range(0, len(y) - N, H):
        fr = y[i:i + N] * win
        if np.sqrt(np.mean(fr ** 2)) < 0.02: continue
        ac = np.correlate(fr, fr, "full")[N - 1:]; lo, hi = int(fs / 300), int(fs / 65); k = lo + int(np.argmax(ac[lo:hi]))
        if ac[0] > 0 and ac[k] / ac[0] > 0.5: vals.append(fs / k)
    if len(vals) < 10: return 0.0, 0.0
    v = np.array(vals); return float(np.median(v)), float(np.percentile(v, 90) - np.percentile(v, 10))


def _units(words: list[dict]) -> float:
    """«Произносимые буквы»: у чисел цифра ≈ 4 буквы («$2,495» читается долго) — темп по буквам устойчивее, чем по словам."""
    n = 0.0
    for w in words:
        digits = len(re.sub(r"\D", "", w["w"])); letters = len(re.sub(r"[^A-Za-z]", "", w["w"]))
        n += letters + 4 * digits
    return n


def _generate(text: str, para: bool, prev_text: str | None, cache, voice_id: str, attempt: int = 0, stab: float | None = None, tags: str | None = None,
              model: str = "eleven_v3") -> dict:
    """Один кусок: разметка тегами (кэш, только v3), запрос с хвостом предыдущего, вырезка хвоста по таймингам. Возвращает {x, words, lead_s, tail_s}."""
    lead = _lead(prev_text)
    stab = STABILITY if stab is None else stab; tags = tags or TAGS_PROMPT   # замороженные настройки ролика (аудит 23.09)
    v4 = model.startswith("eleven_v4")
    base = f"{model}|{voice_id}|{lead}|{text}|{attempt}" if v4 else f"{voice_id}|{stab}|{tags}|{lead}|{text}|{attempt}"   # ключ v3 прежний — кэш начатых роликов цел
    key = hashlib.sha1(base.encode("utf-8")).hexdigest()[:16]
    mp3, meta = cache / f"{key}.mp3", cache / f"{key}.json"
    if not (mp3.exists() and meta.exists()):
        if v4: tagged = text   # 01.10: теги подачи писались под v3; как их читает v4, не проверено — v4 идёт по чистому тексту (так звучал образец)
        else:
            tkey = cache / (hashlib.sha1(f"{tags}|{text}".encode("utf-8")).hexdigest()[:16] + ".tags.json")
            if tkey.exists(): tagged = json.loads(config.read(tkey))["text"]
            else:
                tagged = A._tag_chunk(text, prev_text, tags); config.write(tkey, json.dumps({"text": tagged}, ensure_ascii=False))
        say = lead + ("\n\n" if para else " ") + tagged
        audio, align = A._tts_fal_v4(say, voice_id) if v4 else A._tts_fal_v3(say, voice_id, stab)
        words = A._words(align, 0.0)
        mp3.write_bytes(audio); config.write(meta, json.dumps({"words": words, "lead_words": len(lead.split()), "chars": len(say)}))
    m = json.loads(config.read(meta)); words, n0 = m["words"], m["lead_words"]
    first_tok = A._norm(text.split()[0])
    if not (n0 < len(words) and A._norm(words[n0]["w"]) == first_tok):   # нормализация текста сдвинула счёт слов — ищем первое слово куска рядом
        near = [j for j in range(max(1, n0 - 4), min(len(words), n0 + 5)) if A._norm(words[j]["w"]) == first_tok]
        if not near: raise RuntimeError(f"[voice] первое слово куска «{first_tok}» не найдено после хвоста ({n0})")
        n0 = min(near, key=lambda j: abs(j - n0))
    x = _decode_bytes(mp3.read_bytes())
    env = _env_db(x)
    from .pauses import _quiet_cut
    cut = _quiet_cut(env, words[n0 - 1]["e"], words[n0]["s"])
    cut = max(cut, words[n0]["s"] - 0.25)                         # вдох перед фразой оставляем, длинную тишину — нет
    last_e = words[-1]["e"]
    # хвост: до затухания, но не дольше 0.5 с (v3 иногда дописывает в конце вздохи и шумы)
    a = int(last_e / 0.01); tail = next((k for k in range(a, min(len(env), a + 50)) if env[k] < -52), min(len(env), a + 50)); end = min(len(x) / SR, tail * 0.01 + 0.04)
    piece = x[int(cut * SR):int(end * SR)].copy()
    f = int(0.015 * SR); piece[:f] *= np.linspace(0, 1, f, dtype=np.float32)
    g = int(min(0.08, max(0.02, end - last_e)) * SR); piece[-g:] *= np.linspace(1, 0, g, dtype=np.float32)
    w = [{"w": q["w"], "s": round(q["s"] - cut, 3), "e": round(q["e"] - cut, 3)} for q in words[n0:]]
    return {"x": piece, "words": w, "key": key, "chars": m["chars"], "cut": round(cut, 2)}


def _seam(prev: dict, cur: dict) -> dict:
    from .. import voiceprint as VP
    n = int(SEAM_SEC * SR)
    a, b = prev["x"][-n:], cur["x"][:n]
    sim = VP.sim(VP.embed(_filter(a, "anull", SR, 16000)), VP.embed(_filter(b, "anull", SR, 16000)))
    fa, ra = _f0(a); fb, rb = _f0(b)
    return {"sim": round(sim, 3), "f0": round(fb / fa, 3) if fa and fb else 1.0, "range": round(rb / ra, 2) if ra and rb else 1.0}


def _inner(c: dict) -> float | None:
    from .. import voiceprint as VP
    n = int(SEAM_SEC * SR); mid = len(c["x"]) // 2
    if mid < n: return None
    return VP.sim(VP.embed(_filter(c["x"][mid - n:mid], "anull", SR, 16000)), VP.embed(_filter(c["x"][mid:mid + n], "anull", SR, 16000)))


REROLL_SIM = float(os.getenv("VOICE_REROLL_SIM", 0.72))   # дубль оплачиваем только когда стык реально плохой, а не «ниже четверти по ролику»
def _bad(s: dict, floor: float) -> bool:
    return s["sim"] < min(floor, REROLL_SIM) or abs(s["f0"] - 1) > 0.12 or not 0.55 <= s["range"] <= 1.8


def _score(s: dict) -> float:
    # скачок высоты до 3 % не слышен — штраф только сверх него (иначе кандидат с близостью 0.87 проигрывал исходному с 0.82 из-за +4 % высоты)
    return s["sim"] - 1.5 * max(0.0, abs(np.log(s["f0"])) - 0.03) - 0.08 * abs(np.log(s["range"]))


def build(d, sections: list[str], chapters: list[int] | None = None, first_prev: str | None = None, tempo: float | None = None) -> dict:
    """Озвучить главы (chapters — номера с 1; None — все) → d/voice.mp3, d/words.json, d/voice_parts.json. first_prev — текст перед первой
    из выбранных глав (хвост для её первого куска); для главы 1 — FIRST_LEAD."""
    voice_id = os.getenv("ELEVENLABS_VOICE_ID")
    if not voice_id: raise RuntimeError("ELEVENLABS_VOICE_ID пуст")
    # Настройки голоса замораживаются на ролик: они входят в ключ кэша, и смена стабильности или промпта разметки
    # посреди работы оплачивала ВСЮ озвучку заново (Google 20–21.09: 4 прохода, $21.67). Аудит 23.09.
    fz = d / "voice_settings.json"
    if fz.exists():
        st = json.loads(config.read(fz))
        if (st.get("voice_id"), st.get("stability"), st.get("tags_prompt")) != (voice_id, STABILITY, TAGS_PROMPT):
            print(f"[voice] настройки ролика заморожены ({st.get('tags_prompt')}, стабильность {st.get('stability')}) — беру их, "
                  f"иначе вся озвучка оплачивается заново", flush=True)
        voice_id, stab, tags = st.get("voice_id") or voice_id, st.get("stability", STABILITY), st.get("tags_prompt") or TAGS_PROMPT
        model = st.get("model") or "eleven_v3"   # ролики, начатые до 01.10, досылаются на v3 — модель внутри ролика не смешивается
    else:
        stab, tags, model = STABILITY, TAGS_PROMPT, config.TTS_CHAIN_MODEL
        config.write(fz, json.dumps({"voice_id": voice_id, "stability": stab, "tags_prompt": tags, "model": model}, ensure_ascii=False))
    print(f"[voice] модель озвучки ролика: {model}", flush=True)
    getattr(A, "TTS_CTX", {})["vid"] = d.name   # учёт расхода озвучки по ролику (getattr: watch мог загрузить assets до патча, 23.09)
    T = tempo if tempo is not None else config.TTS_TEMPO   # общий темп канала поверх выравнивания кусков
    cache = config.DATA / "cache" / "voice_chain"; cache.mkdir(parents=True, exist_ok=True)
    todo = chapters or list(range(1, len(sections) + 1))
    plan = []
    for n in todo:
        prev_text = sections[n - 2] if n >= 2 else first_prev
        for c in chunks_of(sections[n - 1]):
            plan.append({"chapter": n, "text": c["text"], "para": c["para"], "prev": prev_text}); prev_text = c["text"]
    print(f"[voice] цепочка: глав {len(todo)}, кусков {len(plan)}, символов {sum(len(p['text']) for p in plan)}", flush=True)
    with ThreadPoolExecutor(4) as ex:
        gen = list(ex.map(lambda p: _generate(p["text"], p["para"], p["prev"], cache, voice_id, stab=stab, tags=tags, model=model), plan))
    # Порог считаем по самим стыкам, а не по близости внутри куска (разбор 20.09): внутри куска голос всегда ближе к себе,
    # и порог выходил недостижимым — почти все дубли уходили впустую, а жадный выбор ухудшал ровность
    # (прогон с порогом 0.84 и 11 дублями: средн. 0.88 / мин 0.83; прогон с 0.86 и 48 дублями: средн. 0.80 / мин 0.66).
    seam0 = [_seam(gen[k - 1], gen[k]) for k in range(1, len(gen))]
    sims = sorted(s["sim"] for s in seam0)
    floor = float(min(0.82, np.percentile(sims, 25))) if len(sims) >= 4 else 0.78
    inner = [v for v in (_inner(c) for c in gen) if v is not None]
    if inner: print(f"[voice] близость внутри кусков {np.mean(inner):.2f} ± {np.std(inner):.2f}", flush=True)
    print(f"[voice] стыки: медиана {np.median(sims):.2f}, минимум {sims[0]:.2f} → порог {floor:.2f}", flush=True)
    rerolled, replaced_prev = 0, False
    for k in range(1, len(gen)):
        s = _seam(gen[k - 1], gen[k]) if replaced_prev else seam0[k - 1]   # пересчитываем только если предыдущий кусок заменили
        best, best_s = gen[k], s
        tries = 0
        while _bad(best_s, floor) and tries < REROLLS:
            tries += 1; rerolled += 1
            cand = _generate(plan[k]["text"], plan[k]["para"], plan[k]["prev"], cache, voice_id, attempt=tries, stab=stab, tags=tags, model=model)
            cs = _seam(gen[k - 1], cand)
            print(f"[voice] стык {k}: {best_s} — дубль {tries}: {cs}", flush=True)
            if _score(cs) > _score(best_s): best, best_s = cand, cs
        replaced_prev = best is not gen[k]
        gen[k] = best; plan[k]["seam"] = best_s
    if rerolled: print(f"[voice] дублей стыков: {rerolled} (≈${rerolled * 2.2:.2f} — считаем только действительно плохие стыки, аудит 23.09)", flush=True)
    try:   # сколько стоила озвучка именно этого ролика — раньше нигде не было видно
        spend = [json.loads(l) for l in open(config.DATA / "tts_spend.jsonl", encoding="utf-8") if l.strip()]
        mine = [x for x in spend if x.get("vid") == d.name]
        print(f"[voice] озвучка ролика: {sum(x['chars'] for x in mine)} знаков ≈ ${sum(x['usd'] for x in mine):.2f} всего по ролику", flush=True)
    except Exception: pass
    worst = [(k, plan[k].get("seam")) for k in range(1, len(gen)) if (plan[k].get("seam") or {}).get("sim", 1) < 0.70]
    if worst:   # предохранитель: такой стык слышно как смену голоса, о нём нужно знать явно
        print("[voice] ВНИМАНИЕ, стыки ниже 0.70: " + "; ".join(f"{k}: {s['sim']}" for k, s in worst), flush=True)
    # выравнивание громкости и темпа
    for c in gen:
        env = _env_db(c["x"]); act = env[env > -40]
        if len(act): c["x"] = c["x"] * (10 ** ((SPEECH_DB - float(10 * np.log10(np.mean(10 ** (act / 10))))) / 20))
        c["cps"] = _units(c["words"]) / max(1.0, sum(w["e"] - w["s"] for w in c["words"]))
    target = float(np.median([c["cps"] for c in gen]))
    for c in gen:
        k = float(np.clip(target / c["cps"], 1 - TEMPO_CLAMP, 1 + TEMPO_CLAMP)) * T; c["tempo"] = 1.0   # выравнивание кусков × общий темп канала
        if abs(k - 1) > 0.025:
            c["x"] = _filter(c["x"], f"atempo={k:.4f}"); c["tempo"] = round(k, 3)
            c["words"] = [{**w, "s": round(w["s"] / k, 3), "e": round(w["e"] / k, 3)} for w in c["words"]]
    # сборка: явные паузы между кусками, границы глав — в voice_parts.json
    out, words, parts, t = [], [], [], 0.0
    for k, (p, c) in enumerate(zip(plan, gen)):
        new_chapter = k > 0 and plan[k - 1]["chapter"] != p["chapter"]
        if k > 0 and not new_chapter:
            have = (len(gen[k - 1]["x"]) / SR - gen[k - 1]["words"][-1]["e"]) + c["words"][0]["s"]
            pad = max(0.0, (PARA_GAP if p["para"] else SENT_GAP) / T - have)
            if pad: out.append(np.zeros(int(pad * SR), dtype=np.float32)); t += pad
        if new_chapter: parts[-1]["chapter_end"] = round(t, 3)
        parts.append({"chapter": p["chapter"], "start": round(t, 3), "chars": len(p["text"]), "tempo": c["tempo"], "seam": p.get("seam"), "key": c["key"]})
        words += [{"w": w["w"], "s": round(w["s"] + t, 3), "e": round(w["e"] + t, 3)} for w in c["words"]]
        out.append(c["x"]); t += len(c["x"]) / SR
    y = np.concatenate(out); peak = float(np.max(np.abs(y))) or 1.0
    if peak > 0.97: y *= 0.97 / peak
    subprocess.run([_ff(), "-y", "-v", "error", "-f", "f32le", "-ar", str(SR), "-ac", "1", "-i", "-", "-c:a", "libmp3lame", "-b:a", "160k", str(d / "voice.mp3")],
                   input=y.astype(np.float32).tobytes(), check=True)
    config.write(d / "words.json", json.dumps(words))
    bounds = [p["chapter_end"] for p in parts if p.get("chapter_end") is not None]
    config.write(d / "voice_parts.json", json.dumps({"parts": parts, "chapter_bounds": bounds}, ensure_ascii=False, indent=1))
    seams = [p["seam"] for p in plan if p.get("seam")]
    print(f"[voice] готово: {t / 60:.1f} мин, стыков {len(seams)}, перегенераций {rerolled}, близость на стыках мин {min(s['sim'] for s in seams):.2f} / средн. "
          f"{np.mean([s['sim'] for s in seams]):.2f}, скачок высоты макс {max(abs(s['f0'] - 1) for s in seams) * 100:.0f}%, темп кусков ×{min(c['tempo'] for c in gen)}–×{max(c['tempo'] for c in gen)}", flush=True)
    return {"duration": t, "parts": parts, "bounds": bounds, "paid_chars": sum(c["chars"] for c in gen)}
