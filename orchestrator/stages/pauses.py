"""Пауза диктора на главах (docs/scene-grammar.md §3): в voice.mp3 физически вставляется CHAPTER_GAP секунд тишины перед
первым словом частей 2–7, words.json сдвигается, pauses.json хранит точки реза. Remotion дальше играет один voice.mp3,
а place()/музыка/Shorts получают правильные времена без переписывания. Идемпотентно: один раз на видео."""
import json, shutil, subprocess
from pathlib import Path
from .. import config
from . import assets as A

def part_names(s: dict) -> list[str]:
    """Названия частей по плану (Title Case, как на карточке главы); часть 1 — Cold open, карточки у неё нет."""
    outline = s.get("outline") or []
    out = []
    for i, p in enumerate(outline):
        name = (p.get("name") or f"Part {i + 1}").strip()
        out.append(" ".join(w if (w.lower() in ("and", "of", "the") and k) else w[:1].upper() + w[1:] for k, w in enumerate(name.split())))
    return out

def _resolve(vid_or_dir, parts):
    """vid → папка видео и части из payload; Path → папка, части обязательны."""
    if isinstance(vid_or_dir, Path) or (isinstance(vid_or_dir, str) and Path(vid_or_dir).is_dir() and not (config.VIDEOS / vid_or_dir).exists()):
        if not parts: raise ValueError("pauses.ensure(dir): нужен список частей")
        return Path(vid_or_dir), None, None
    from .. import db
    v = db.get(vid_or_dir); s = v["payload"]["script"]
    parts = parts or s.get("parts") or [p for p in s["script"].split("\n\n") if p.strip()]
    return db.video_dir(vid_or_dir), vid_or_dir, (s, parts)

def _ffmpeg() -> str:
    """Полный ffmpeg (anullsrc/concat есть не во всех сборках): imageio-ffmpeg, как в archive._ffdir."""
    try:
        import imageio_ffmpeg; return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception: return config.ffmpeg()

def _envelope(path, step: float = 0.01):
    """Огибающая громкости голоса, dBFS, шаг 10 мс — чтобы резать там, где голос реально затих, а не по концу слова из разметки."""
    import numpy as np
    raw = subprocess.run([_ffmpeg(), "-v", "error", "-i", str(path), "-f", "f32le", "-ac", "1", "-ar", "8000", "-"], capture_output=True, check=True).stdout
    x = np.frombuffer(raw, dtype=np.float32); n = int(8000 * step)
    k = len(x) // n
    return 20 * np.log10(np.sqrt((x[:k * n].reshape(k, n) ** 2).mean(axis=1)) + 1e-7)

def _quiet_cut(env, e: float, s: float, step: float = 0.01, floor_db: float = -50.0) -> float:
    """Секунда реза между концом слова e и началом следующего s: середина первого тихого участка (≥ 60 мс ниже floor_db), иначе самая тихая точка.
    Разметка v3 ставит конец слова раньше, чем затухает звук: рез на e + 0.15 обрывал хвост «breaking.» на −25 dB — щелчок «дзт» (владелец 17.09)."""
    a, b = int(e / step), max(int(e / step) + 1, int((s - 0.02) / step))
    seg = env[a:b]
    if not len(seg): return round((e + s) / 2, 3)
    run = 0
    for k, v in enumerate(seg):
        run = run + 1 if v < floor_db else 0
        if run >= 6:
            j = k
            while j + 1 < len(seg) and seg[j + 1] < floor_db: j += 1
            return round((a + (k - run + 1 + j + 1) / 2) * step, 3)
    return round((a + int(seg.argmin()) + 0.5) * step, 3)

def _cut_point(words: list[dict], i: int) -> tuple[int, float]:
    """Индекс первого слова новой части и секунда реза. Режем в зазор между словами: если зазор мал — ищем в ±2 словах
    границу ≥ CHAPTER_MIN_CUT_GAP (конец предложения), иначе середина зазора. Медиана межсловного зазора 0.07 с, поэтому
    «e + 0.15» без min резало бы следующее слово."""
    gap = config.CHAPTER_MIN_CUT_GAP
    def at(j): return words[j - 1]["e"], words[j]["s"]
    e, s = at(i)
    if s - e >= gap: return i, round(min(e + 0.15, (e + s) / 2), 3)
    cands = []
    for j in (i - 1, i + 1, i - 2, i + 2):
        if 1 <= j < len(words):
            e2, s2 = at(j)
            if s2 - e2 >= gap: cands.append((0 if words[j - 1]["w"][-1:] in ".!?" else 1, abs(j - i), j))
    if cands:
        j = min(cands)[2]; e2, s2 = at(j)
        return j, round(min(e2 + 0.15, (e2 + s2) / 2), 3)
    return i, round((e + s) / 2, 3)

def _all_at(tokens: list[str], phrase: list[str], start: int = 0) -> list[int]:
    """Все вхождения фразы, а не первое: начало части бывает не уникальным."""
    out, i = [], start
    while True:
        j = A._find(tokens, phrase, i)
        if j is None: return out
        out.append(j); i = j + 1

def _first_word_indexes(words: list[dict], parts: list[str]) -> list[int]:
    """Индексы первых слов частей 2..N: по первым 4 словам части, из всех совпадений берём ближайшее к сумме слов.
    Google 20.09: часть 7 начиналась с «So here is the company…», а в части 6 было «So here is the control test…» —
    первое совпадение уводило якорь на 169 слов назад, и этап падал. Настоящая проверка целостности — одна:
    слов в озвучке должно быть столько же, сколько в частях; коллизия фраз этапа не останавливает."""
    tokens = [A._norm(w["w"]) for w in words]
    ptoks_all = [[t for t in (A._norm(w) for w in A.clean_text(p).split()) if t] for p in parts]
    total = sum(len(x) for x in ptoks_all)
    if abs(len(words) - total) > 10:
        raise RuntimeError(f"[pauses] в озвучке {len(words)} слов, а в частях {total} — текст и голос разошлись, "
                           f"проверь payload['script']['parts'] и words.json")
    out, cum, pos = [], 0, 0
    for k, ptoks in enumerate(ptoks_all, 1):
        if k >= 2:
            cands = _all_at(tokens, ptoks[:4], pos) or _all_at(tokens, ptoks[:3], pos)
            i = min(cands, key=lambda j: abs(j - cum)) if cands else None
            if i is None or abs(i - cum) > 40:
                print(f"[pauses] часть {k}: якорь «{' '.join(ptoks[:4])}» "
                      f"{'не найден' if i is None else f'нашёлся на {i}, далеко от {cum}'} — беру сумму слов ({cum})", flush=True)
                i = cum
            elif abs(i - cum) > 10:
                print(f"[pauses] часть {k}: якорь на слове {i} при сумме {cum} — беру якорь", flush=True)
            if not 0 < i < len(words): raise RuntimeError(f"[pauses] часть {k}: индекс {i} вне words.json")
            out.append(i); pos = i
        cum += len(ptoks)
    return out

def _speech_onset(env, t: float, step: float = 0.01, look: float = 1.2) -> float:
    """Секунда, с которой после реза t начинается настоящая речь: ≥ 8 из 12 кадров по 10 мс громче −42 dB. Короткий всплеск перед ней —
    обрывок хвоста предыдущего куска озвучки цепочкой (глава 4 Apple: 30 мс на −35 dB сразу после 4-секундной тишины) — речью не считается."""
    a = int(t / step); seg = env[a:a + int(look / step)]
    for k in range(len(seg) - 12):
        if seg[k] > -42 and (seg[k:k + 12] > -42).sum() >= 8: return round(t + k * step, 3)
    return t

def _concat_filter(cuts: list[float], total: float, gap: float, heads: list[float] | None = None) -> str:
    """2k+1 сегментов: речь → тишина → речь …; на стыках afade 30 мс, aformat — чтобы concat не ругался на разные форматы.
    heads[n] — сколько секунд в начале сегмента после n-й паузы заглушить (afade in со сдвигом старта глушит всё до него)."""
    T = [0.0] + cuts + [total]; k = len(cuts); chain, inputs = [], []
    for n in range(k + 1):
        a, b = T[n], T[n + 1]
        f = f"[0:a]" + (f"atrim={a:.3f}:{b:.3f}" if n < k else f"atrim=start={a:.3f}") + ",asetpts=PTS-STARTPTS,aformat=sample_rates=44100:channel_layouts=stereo"
        if n > 0: f += f",afade=t=in:st={(heads[n - 1] if heads else 0.0):.3f}:d=0.03"
        if n < k: f += f",afade=t=out:st={max(0.0, b - a - 0.06):.3f}:d=0.06"
        chain.append(f + f"[a{n}]"); inputs.append(f"[a{n}]")
        if n < k:
            chain.append(f"anullsrc=r=44100:cl=stereo:d={gap:.3f}[s{n}]"); inputs.append(f"[s{n}]")
    return ";".join(chain) + ";" + "".join(inputs) + f"concat=n={2 * k + 1}:v=0:a=1[o]"

def ensure(vid_or_dir, parts: list[str] | None = None) -> list[dict]:
    """Один раз на видео: voice.mp3 → voice_raw.mp3 + паузы; words.json → words_raw.json + сдвиг; pauses.json.
    Повторный вызов при сходящихся длительностях ничего не меняет; если voice.mp3 перегенерирован без удаления voice_raw — падает громко."""
    d, vid, sp = _resolve(vid_or_dir, parts)
    s, parts = sp if sp else ({}, parts)
    names = part_names(s) if s else [f"Part {i + 1}" for i in range(len(parts))]
    voice, raw, wjson, wraw, pjson = d / "voice.mp3", d / "voice_raw.mp3", d / "words.json", d / "words_raw.json", d / "pauses.json"
    gap = config.CHAPTER_GAP
    if pjson.exists():
        pauses = json.loads(config.read(pjson))
        diff = A._duration(voice) - (A._duration(raw) if raw.exists() else 0) - sum(p["gap"] for p in pauses)
        if raw.exists() and abs(diff) <= 0.15:
            print(f"[pauses] уже есть: {len(pauses)} пауз, длительности сходятся ({diff:+.2f} с)"); return pauses
        raise RuntimeError(f"[pauses] pauses.json есть, но voice.mp3 не сходится с voice_raw.mp3 (+Σgap): расхождение {diff:+.2f} с. "
                           f"Кто-то перегенерировал озвучку — удали {pjson.name}, {raw.name} и {wraw.name} (или положи свежий voice.mp3 как voice_raw.mp3) и запусти снова")
    if not voice.exists(): raise FileNotFoundError(f"{voice} нет — сначала озвучка")
    if not raw.exists(): shutil.copy(voice, raw)
    if not wraw.exists(): shutil.copy(wjson, wraw)
    words = json.loads(config.read(wraw))
    idxs = _first_word_indexes(words, parts)
    if not idxs:
        config.write(pjson, "[]"); return []
    cuts, pauses, shift = [], [], 0.0
    env = _envelope(raw)
    vp = d / "voice_parts.json"   # озвучка цепочкой (voice_chain) знает точные границы глав — режем ровно по ним
    bounds = json.loads(config.read(vp)).get("chapter_bounds", []) if vp.exists() else []
    for k, i in enumerate(idxs):
        j, t = _cut_point(words, i)
        t = _quiet_cut(env, words[j - 1]["e"], words[j]["s"])
        exact = [b for b in bounds if words[j - 1]["e"] - 0.1 <= b <= words[j]["s"] + 0.1]
        if exact: t = round(exact[0], 3)
        if cuts and t <= cuts[-1]: raise RuntimeError(f"[pauses] точки реза не растут: {cuts[-1]} → {t}")
        cuts.append(t)
        pauses.append({"part": k + 2, "name": names[k + 1] if k + 1 < len(names) else f"Part {k + 2}", "word_index": j, "at": round(t + shift, 3), "gap": gap})
        shift += gap
    total = A._duration(raw)
    out = d / "voice_new.mp3"
    heads = []   # мусор между резом и первым словом главы (обрывок хвоста, щелчок) — в тишину; вдох перед словом уходит вместе с ним, это нормально
    for t in cuts:
        on = _speech_onset(env, t); heads.append(round(on - t - 0.05, 3) if on - t > 0.12 else 0.0)
    if any(heads): print("[pauses] заглушено в начале глав, с: " + ", ".join(f"{h:.2f}" for h in heads))
    subprocess.run([_ffmpeg(), "-y", "-v", "error", "-i", str(raw), "-filter_complex", _concat_filter(cuts, total, gap, heads), "-map", "[o]",
                    "-c:a", "libmp3lame", "-b:a", "192k", "-ar", "44100", str(out)], check=True)
    got = A._duration(out) - total - gap * len(cuts)
    if abs(got) > 0.15:
        out.unlink(missing_ok=True); raise RuntimeError(f"[pauses] длительность после вставки пауз не сходится: {got:+.2f} с")
    out.replace(voice)
    # слова после k-й паузы уезжают на Σ gap_m (m ≤ k)
    new_words, shift, k = [], 0.0, 0
    for j, w in enumerate(words):
        while k < len(pauses) and j >= pauses[k]["word_index"]: shift += pauses[k]["gap"]; k += 1
        new_words.append({**w, "s": round(w["s"] + shift, 3), "e": round(w["e"] + shift, 3)})
    config.write(wjson, json.dumps(new_words))
    config.write(pjson, json.dumps(pauses, ensure_ascii=False, indent=2))
    print("[pauses] " + ", ".join(f"{p['part']}:{p['name']}@{p['at']:.2f}" for p in pauses) + f"; voice.mp3 +{gap * len(pauses):.1f} с ({got:+.2f})")
    if vid and (d / "timeline.json").exists():
        from . import story_assets
        try: story_assets.retime(vid)
        except Exception as e: print(f"[pauses] retime не удался: {e}")
    return pauses

def load(d) -> list[dict]:
    p = Path(d) / "pauses.json"
    return json.loads(config.read(p)) if p.exists() else []
