"""Звуковая партитура story-видео (владелец 17.09: «музыка монотонная и всё время идёт»).

Замер Apple: один трек на главу 4–5 минут на постоянной громкости, разброс громкости 2.5 LU, ролик −19.4 LUFS, 19 архивных клипов без звука,
акценты только на карточках глав. Партитура вместо подложки:
  • cues   — модель размечает повороты сюжета по предложениям с таймкодами → секции музыки (настроение, инструменты, вход), повороты, удары;
  • music  — ElevenLabs Music v2.5 (fal) пишет одну композицию кусками ровно под длительности секций (composition_plan);
  • curve  — общая кривая громкости музыки (шаг CURVE_DT): под речью ниже, в паузах поднимается, на карточке главы выше,
             перед поворотом — тишина, под живым звуком архива — почти ноль;
  • sfx    — пакет эффектов (генерируется один раз в data/sfx): удар на поворотах, мягкий низ на цифрах, бумага на ярлыках, машинка на подписях, свист на главах;
  • live   — живой звук архива (фраза со сцены, смех зала): диктор молчит, пауза вставлена в голос;
  • master — сведение итогового mp4 к −14 LUFS (YouTube громче не сделает, а тихий ролик звучит хуже соседних).
Сейчас собирается демо-окно (`demo`), полная интеграция в render — после «ок» владельца."""
import hashlib, json, math, re, shutil, subprocess
from .. import db, config, llm

CURVE_DT = 0.1
SPEECH_PAD = 0.18           # речь «длится» чуть дольше последнего слова — музыка не выпрыгивает в микропаузы
GAP_LIFT, CARD_LIFT, SWELL_LIFT = 2.6, 3.5, 1.9   # во сколько раз музыка громче: пауза без речи / карточка главы / смена части и удар
LIVE_DUCK = 0.12
REVEAL_SILENCE = 1.0
MUSIC_MODEL = "fal-ai/elevenlabs/music/v2.5"
SFX_MODEL = "fal-ai/elevenlabs/sound-effects/v2"

SFX = {   # имя → (описание для генерации, длительность, громкость по умолчанию относительно голоса)
    "hit": ("deep cinematic low impact hit with a short dark tail, documentary trailer, no music", 2.5, 0.55),
    "boom_soft": ("soft warm sub boom, gentle low thump, cinematic, short", 1.6, 0.4),
    "riser": ("subtle cinematic tension riser, airy reverse swell building for two seconds, ends abruptly", 2.2, 0.35),
    "whoosh": ("soft cinematic whoosh transition, airy and gentle", 1.2, 0.35),
    "type": ("vintage manual typewriter, quick sequence of six key strikes, close mic, dry room", 1.5, 0.22),
    "paper": ("glossy photograph print dropped onto a wooden desk, soft paper slap", 0.9, 0.35),
    "rewind": ("cassette tape fast rewind with a rising pitch sweep, short", 1.4, 0.45),
}
MOOD_BASE = {
    "mystery": ["mysterious", "sparse", "dark ambient textures"], "tension": ["tense", "pulsing low strings", "ticking percussion"],
    "drive": ["driving", "confident rhythm", "modern cinematic percussion"], "wonder": ["wonder", "shimmering arpeggios", "warm pads"],
    "triumph": ["triumphant", "uplifting strings", "big drums"], "loss": ["melancholic", "slow solo piano", "cello"],
    "hope": ["hopeful", "gentle build", "felt piano and strings"], "reflective": ["reflective", "calm", "soft piano and pad"],
}
NEGATIVE = ["vocals", "singing", "lyrics", "spoken words", "EDM drop", "dubstep", "trap hi-hats", "comedic"]


def _ff() -> str:
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def _dur(path) -> float:
    return float(subprocess.check_output([config.ffprobe(), "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)]))


def _fal(model: str, args: dict) -> dict:
    import fal_client
    return fal_client.subscribe(model, arguments=args)


def _download(url: str, out) -> None:
    from .assets import _get
    out.write_bytes(_get(url, timeout=300))


def _is_audio(b: bytes, ctype: str = "") -> bool:
    """Настоящий mp3/wav, а не HTML-страница отказа (07.10: «Do you restrict access» с HTTP 200 легла как 7 тем)."""
    if "html" in ctype.lower() or b[:15].lstrip().lower().startswith((b"<!doctype", b"<html", b"{")): return False
    return b[:3] == b"ID3" or (len(b) > 1 and b[0] == 0xFF and (b[1] & 0xE0) == 0xE0) or b[:4] == b"RIFF"

def _music(chunks: list[dict], seed: int, out) -> None:
    """Композиция ElevenLabs Music v2.5 → mp3 в out. Сначала напрямую (api.elevenlabs.io/v1/music: та же модель и тот же composition_plan,
    $0.15/мин против $0.60/мин с округлением до минуты на fal — аудит 18.09, у Amazon 25,8 мин тем: $15.5 → $3.9); при любой ошибке
    прямого API (кончились кредиты плана, нет прав у ключа, 5xx) — та же генерация через fal, чтобы сборка не вставала."""
    import os, requests
    key = os.getenv("ELEVENLABS_API_KEY")
    if config.MUSIC_DIRECT and key:
        try:
            px = (os.getenv("ELEVEN_PROXY") or os.getenv("GOOGLE_PROXY") or "").strip()   # 07.10: через VPS владельца в Happ — вне регион-блокировки
            r = requests.post("https://api.elevenlabs.io/v1/music", params={"output_format": "mp3_48000_192"},
                              headers={"xi-api-key": key, "Content-Type": "application/json"}, timeout=600,
                              json={"composition_plan": {"chunks": chunks}, "model_id": "music_v2_5", "seed": seed},
                              proxies={"https": px, "http": px} if px else None)
            if r.ok and len(r.content) > 10_000 and _is_audio(r.content, r.headers.get("content-type", "")):
                out.write_bytes(r.content); return
            print(f"[sound] музыка напрямую: HTTP {r.status_code} {r.text[:160]} — через fal", flush=True)
        except Exception as e:
            print(f"[sound] музыка напрямую: {str(e)[:160]} — через fal", flush=True)
    if not config.MUSIC_FAL_FALLBACK:   # 07.10: без прямого ElevenLabs партитуру не покупаем через fal — рендер возьмёт треки music_tracks
        raise RuntimeError("ElevenLabs Music напрямую недоступен (лимит/регион), запасной fal выключен (MUSIC_FAL_FALLBACK=0)")
    r = _fal(MUSIC_MODEL, {"composition_plan": {"chunks": chunks}, "seed": seed, "output_format": "mp3_48000_192"})
    _download(r["audio"]["url"], out)


# ---------- эффекты ----------

def sfx_pack(names=None) -> dict:
    """Эффекты генерируются один раз на весь канал (data/sfx/<имя>.mp3) и переиспользуются."""
    lib = config.DATA / "sfx"; lib.mkdir(parents=True, exist_ok=True); out = {}
    for name in names or SFX:
        p = lib / f"{name}.mp3"
        if not p.exists():
            text, dur, _ = SFX[name]
            r = _fal(SFX_MODEL, {"text": text, "duration_seconds": dur, "prompt_influence": 0.6})
            audio = r.get("audio"); audio = audio[0] if isinstance(audio, list) else audio
            raw = lib / f"{name}_raw.mp3"; _download(audio["url"], raw)
            # пик к −3 dBFS: громкость в миксе задаётся явно, а не случайной громкостью генерации
            subprocess.run([_ff(), "-y", "-v", "error", "-i", str(raw), "-af", "loudnorm=I=-16:TP=-3:LRA=11", "-ar", "48000", "-b:a", "192k", str(p)], check=True)
            raw.unlink(missing_ok=True)
            print(f"[sound] эффект {name} сгенерирован", flush=True)
        out[name] = p
    return out


# ---------- разметка сюжета ----------

def sentences(words: list[dict]) -> list[dict]:
    out, cur = [], []
    for w in words:
        cur.append(w)
        if re.search(r"[.!?…]$|[.!?]”$|[.!?]\"$", w["w"]):
            out.append({"s": cur[0]["s"], "e": cur[-1]["e"], "text": " ".join(x["w"] for x in cur)}); cur = []
    if cur: out.append({"s": cur[0]["s"], "e": cur[-1]["e"], "text": " ".join(x["w"] for x in cur)})
    return out


def cues(tag: str, sents: list[dict], marks: list[str]) -> dict:
    seg = "\n".join(f"[{i}] {s['s']:.1f}–{s['e']:.1f} с: {s['text']}" for i, s in enumerate(sents)) + ("\n\nОтметки:\n" + "\n".join(marks) if marks else "")
    res = llm.ask_json(config.prompt("sound_cues", segment=seg), heavy=True, max_tokens=4000, tag=f"sound_cues_{tag}")
    secs = sorted([x for x in res.get("sections") or [] if isinstance(x.get("start"), int) and 0 <= x["start"] < len(sents)], key=lambda x: x["start"])
    if not secs or secs[0]["start"] != 0: secs.insert(0, {"start": 0, "mood": "reflective", "intensity": 1, "styles": [], "transition_in": "fade"})
    res["sections"] = split_long(secs, sents)
    return res


MAX_SECTION = 45.0


def split_long(secs: list[dict], sents: list[dict]) -> list[dict]:
    """Секция длиннее MAX_SECTION снова звучит как подложка (модель дала 65 с драйва на 10 предложений) — делим на предложении
    ближе к середине; вторая половина — то же настроение с нарастанием."""
    out = []
    for k, sec in enumerate(secs):
        a = sents[sec["start"]]["s"]; nxt = secs[k + 1]["start"] if k + 1 < len(secs) else len(sents)
        b = sents[nxt]["s"] if nxt < len(sents) else sents[-1]["e"]
        out.append(sec)
        while b - a > MAX_SECTION:
            mid = a + (b - a) / 2
            cand = [i for i in range(out[-1]["start"] + 1, nxt) if not sents[i]["text"].startswith("[")]
            if not cand: break
            i = min(cand, key=lambda i: abs(sents[i]["s"] - mid))
            new = {**sec, "start": i, "intensity": min(3, int(sec.get("intensity") or 2) + 1), "styles": list(sec.get("styles") or []) + ["builds from the previous section"], "transition_in": "swell"}
            out.append(new); a = sents[i]["s"]
    return out


# ---------- музыка ----------

def compose(sections: list[dict], bounds: list[float], total: float, out, seed: int = 7) -> None:
    """Одна композиция кусками: длительность куска = длительность секции (минимум 3 с — короткие секции сливаются с соседней)."""
    chunks = []
    for sec, (a, b) in zip(sections, zip(bounds, bounds[1:] + [total])):
        dur = int(round((b - a) * 1000))
        styles = ["instrumental cinematic documentary score", "warm analog production"] + MOOD_BASE.get(sec.get("mood"), []) + list(sec.get("styles") or [])
        styles.append({1: "quiet, restrained", 2: "moderate energy", 3: "powerful, full"}.get(int(sec.get("intensity") or 2), "moderate energy"))
        ti = sec.get("transition_in")
        if ti == "hit": styles.append("opens with a strong low impact")
        elif ti == "swell": styles.append("opens with a rising swell")
        elif ti == "cut": styles.append("abrupt new section")
        if chunks and dur < 3000:
            chunks[-1]["duration_ms"] += dur; continue
        chunks.append({"text": "", "duration_ms": max(3000, min(120000, dur)), "positive_styles": styles[:10], "negative_styles": NEGATIVE})
    for c in chunks: c["text"] = c["text"] or "[instrumental]"   # пустой text у куска не проходит валидацию прямого API
    _music(chunks, seed, out)
    print(f"[sound] музыка: {len(chunks)} кусков, {sum(c['duration_ms'] for c in chunks) / 1000:.1f} с → {out.name}", flush=True)


def _styles(sec: dict) -> list[str]:
    styles = ["instrumental cinematic documentary score", "warm analog production"] + MOOD_BASE.get(sec.get("mood"), []) + list(sec.get("styles") or [])
    styles.append({1: "quiet, restrained", 2: "moderate energy", 3: "powerful, full"}.get(int(sec.get("intensity") or 2), "moderate energy"))
    ti = sec.get("transition_in")
    if ti == "hit": styles.append("opens with a strong low impact on the first beat")
    elif ti == "swell": styles.append("opens with a rising swell")
    styles.append("steady to the end, no fade out, no ending")
    return styles[:12]


XF_IN, XF_OUT = 0.8, 1.6    # кроссфейд соседних частей: новая входит за XF_IN до границы, старая уходит за XF_OUT после


def compose_sections(sections: list[dict], bounds: list[float], total: float, out_dir, tag: str, voice_path, below_db: float = 17.0, seed: int = 7) -> list[dict]:
    """Каждая секция — отдельная пьеса своего характера (одна композиция на всё окно пульсировала одинаковыми фразами и затухала к концу),
    с запасом на кроссфейд; громкость каждой пьесы выравнивается к голосу, интенсивность секции даёт ±2 dB."""
    from .. import loudness
    ends = bounds[1:] + [total]; music = []
    for i, (sec, a, b) in enumerate(zip(sections, bounds, ends)):
        if b - a < 2.0: continue
        start = max(0.0, a - (XF_IN if i else 0.0)); stop = min(total, b + (XF_OUT if b < total else 0.0))
        dur_ms = int(round((stop - start + 2.5) * 1000))   # +2.5 с: хвост пьесы (затухание) остаётся за границей
        p = out_dir / f"{tag}_s{i}.mp3"
        if not p.exists():
            chunks = [{"text": "[instrumental]", "duration_ms": max(3000, min(120000, dur_ms)), "positive_styles": _styles(sec), "negative_styles": NEGATIVE}]
            _music(chunks, seed + i, p)
            print(f"[sound] часть {i}: {sec.get('mood')}/{sec.get('intensity')} {stop - start:.1f} с", flush=True)
        g = loudness.music_gain(voice_path, p, below_db, hi=0.5) * {1: 0.8, 2: 1.0, 3: 1.25}.get(int(sec.get("intensity") or 2), 1.0)
        music.append({"src": p.name, "start": round(start, 3), "end": round(stop, 3), "offset": 0.0, "gain": round(g, 4),
                      "fade_in": XF_IN if i else 0.0, "fade_out": XF_OUT if b < total else 1.0})
    return music


def curve(total: float, words: list[dict], pauses: list[tuple], reveals: list[float], lives: list[tuple], swells: list[float] | None = None) -> list[float]:
    """Множитель громкости музыки с шагом CURVE_DT: 1 под речью, GAP_LIFT в паузах ≥ 0.6 с, CARD_LIFT под карточкой главы,
    0 за REVEAL_SILENCE до поворота, LIVE_DUCK под живым звуком. Сглаживание: вниз быстро (0.15 с), вверх медленно (0.7 с)."""
    n = int(math.ceil(total / CURVE_DT)) + 1
    speech = [False] * n
    for w in words:
        for k in range(int(w["s"] / CURVE_DT), min(n, int((w["e"] + SPEECH_PAD) / CURVE_DT) + 1)): speech[k] = True
    # микропаузы внутри фраз (< 0.6 с) не поднимают музыку
    target, k = [1.0] * n, 0
    while k < n:
        if speech[k]: k += 1; continue
        j = k
        while j < n and not speech[j]: j += 1
        if (j - k) * CURVE_DT >= 0.5:
            for x in range(k, j): target[x] = GAP_LIFT
        k = j
    for t in swells or []:   # смена части музыки и удар: музыка на 1.4 с выходит вперёд даже под речью
        for x in range(max(0, int(t / CURVE_DT)), min(n, int((t + 1.4) / CURVE_DT) + 1)): target[x] = max(target[x], SWELL_LIFT)
    for a, b in pauses:
        for x in range(int(a / CURVE_DT), min(n, int(b / CURVE_DT) + 1)): target[x] = CARD_LIFT
    for a, b in lives:
        for x in range(max(0, int((a - 0.3) / CURVE_DT)), min(n, int((b + 0.2) / CURVE_DT) + 1)): target[x] = LIVE_DUCK
    for t in reveals:
        for x in range(max(0, int((t - REVEAL_SILENCE) / CURVE_DT)), min(n, int((t + 0.05) / CURVE_DT) + 1)): target[x] = 0.0
    out, cur = [], target[0]
    down, up = CURVE_DT / 0.15, CURVE_DT / 0.4
    for x in target:
        cur = max(x, cur - down * max(cur, 0.3)) if x < cur else min(x, cur + up * max(cur, 0.3))
        out.append(round(cur, 3))
    return out


def short_score(d, spec: dict, base, voice_path) -> dict:
    """Партитура шортса по его структуре: хук и новость — ритмичный драйв с ударом на первом кадре; мост в прошлое — винтажная смена
    со звуком перемотки плёнки; концовка — разрешение и акцент на всплывающем превью. Музыка в шортсах громче, чем в длинном ролике."""
    total, end_at = spec["duration"], spec["end"]["start"]
    then_at = next((x["start"] for x in spec["shots"] if x.get("kind") == "then"), None)
    sections, bounds = [], [0.0]
    sections.append({"mood": "drive", "intensity": 3, "styles": ["modern cinematic hybrid", "punchy drums 118 BPM", "bold synth bass", "tech keynote energy"], "transition_in": "hit"})
    if then_at and then_at < end_at - 3:
        sections.append({"mood": "reflective", "intensity": 2, "styles": ["vintage 1970s warmth", "tape-saturated electric piano", "slower groove 80 BPM", "vinyl texture"], "transition_in": "cut"})
        bounds.append(then_at - 0.25)
    sections.append({"mood": "triumph", "intensity": 3, "styles": ["triumphant resolve", "big final chord", "rings out"], "transition_in": "swell"})
    bounds.append(end_at - 0.2)
    music_parts = compose_sections(sections, bounds, total, base, "score_part", voice_path, below_db=13.0, seed=11)
    for m in music_parts: m["src"] = f"shorts/{base.name}/" + m["src"]
    words = json.loads(config.read(d / spec["voice"].replace("voice_short.mp3", "words_short.json")))
    cv = curve(total, words, [(end_at, total)], [], [], swells=bounds[1:])
    cv = [round(min(1.8, x), 3) for x in cv]   # в шортсах без больших подъёмов: паузы короткие
    pack = sfx_pack()
    for p in pack.values(): shutil.copy(p, d / "sound" / p.name)
    sfx = []
    def add(name, at, vol=None):
        if 0 <= at < total: sfx.append({"src": f"sound/{name}.mp3", "at": round(at, 3), "volume": round(vol if vol is not None else SFX[name][2], 3), "dur": SFX[name][1] + 0.5})
    add("hit", 0.0, 0.5)
    for f in spec.get("flashes") or []: add("boom_soft", f["start"] - 0.02, 0.45)
    if then_at: add("rewind", then_at - 0.55, 0.5)
    add("whoosh", end_at - 0.05, 0.45); add("hit", end_at + 0.15, 0.35)
    return {"music": music_parts,
            "curve": {"dt": CURVE_DT, "v": cv}, "sfx": sorted(sfx, key=lambda x: x["at"]), "live": []}


# ---------- v2 (владелец 17.09 после демо: «неестественно, резкая смена звука»; «голос главный, музыка тише; без голоса можно громче») ----------
# Что было не так в v1: каждая часть — отдельная пьеса (другая тональность и темп — как переключение песни), громкость менялась ступеньками раз в кадр
# (до 12.5 dB за кадр), на цифрах удар + шлепок бумаги + подъём музыки под голосом. v2: одна тема на главу (одна композиция, внутри — только
# аранжировка плотнее/реже), смена темы только на карточке главы, сведение в numpy с плавной автоматикой, без эффектов под голосом.

BELOW_SPEECH_DB = 25.0      # музыка под голосом: на столько dB тише голоса
LIFT_DB = 9.0               # без голоса (карточка главы, конец шортса) музыка поднимается на столько dB
LIVE_DB = -8.0              # под живым звуком архива — ещё тише, чем под голосом
MIN_GAP = 1.0               # паузы короче — не «дыхание» музыки, а часть речи
ATTACK, RELEASE = 0.45, 1.3  # сек: уход музыки вниз / возврат вверх
MIX_SR = 48000
ARRANGE = {1: "sparse minimal arrangement, soft dynamics", 2: "fuller arrangement, gentle steady pulse", 3: "full arrangement, strongest momentum, still restrained under narration"}


def theme_chunks(sections: list[dict], bounds: list[float], a: float, b: float, tail: float = 4.0, min_len: float = 12.0) -> list[dict]:
    """Секции внутри [a, b) → куски одной композиции: тема (настроение, инструменты) задаётся первой секцией, дальше «та же тема», меняется только плотность."""
    ends = bounds[1:] + [1e9]
    spans = [(max(a, s0), min(b, s1), sec) for sec, s0, s1 in zip(sections, bounds, ends) if s1 > a and s0 < b]
    merged = []
    for s0, s1, sec in spans:
        if merged and (s1 - s0 < min_len or (sec.get("mood") in ("near silence", None))): merged[-1][1] = s1; continue
        merged.append([s0, s1, sec])
    if merged and merged[0][0] > a: merged[0][0] = a
    theme = merged[0][2] if merged else {"mood": "reflective", "styles": []}
    base = ["instrumental cinematic documentary underscore", "warm analog production", "designed to sit under narration, no busy melody in the midrange"] \
        + MOOD_BASE.get(theme.get("mood"), []) + [x for x in (theme.get("styles") or []) if "BPM" in x or any(k in x for k in ("piano", "strings", "synth", "pad", "percussion", "bass"))][:3]
    chunks = []
    for k, (s0, s1, sec) in enumerate(merged):
        dur = s1 - s0 + (tail if k == len(merged) - 1 else 0.0)
        styles = base + ["same theme and key throughout, evolves gradually" if k else "states the main theme gently", ARRANGE.get(int(sec.get("intensity") or 2), ARRANGE[2])]
        if k == len(merged) - 1: styles.append("keeps playing steadily at the end, no fade out, no final chord")
        chunks.append({"text": "[instrumental]", "duration_ms": int(round(max(3.0, min(120.0, dur)) * 1000)), "positive_styles": styles[:12], "negative_styles": NEGATIVE + ["abrupt changes", "sudden hits", "key change"]})
    return chunks


def compose_theme(chunks: list[dict], out, seed: int = 7) -> None:
    if out.exists(): return
    _music(chunks, seed, out)
    print(f"[sound] тема {out.name}: {len(chunks)} частей, {sum(c['duration_ms'] for c in chunks) / 1000:.1f} с", flush=True)


def _decode(path, sr: int = MIX_SR):
    import numpy as np
    raw = subprocess.run([_ff(), "-v", "error", "-i", str(path), "-f", "f32le", "-ac", "2", "-ar", str(sr), "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32).reshape(-1, 2).copy()


def _cos_fade(n: int):
    import numpy as np
    return (0.5 - 0.5 * np.cos(np.linspace(0, np.pi, max(1, n)))).astype(np.float32)


def mix(out, total: float, words: list[dict], voice_path, music: list[dict], sfx: list[dict] = (), live: list[dict] = (),
        below_db: float = BELOW_SPEECH_DB, lift_db: float = LIFT_DB, lift_zones: list[tuple] = (), sr: int = MIX_SR) -> dict:
    """Музыка + эффекты + живой звук одной дорожкой (голос остаётся отдельной дорожкой в Remotion).
    music: [{file, start, fade_in, fade_out}] — каждая пьеса на своём месте со своими косинусными фейдами; уровень пьесы — below_db ниже голоса;
    автоматика: под речью 0 dB, в паузах ≥ MIN_GAP и в lift_zones +lift_db, под живым звуком LIVE_DB; сглаживание ATTACK/RELEASE (без ступенек)."""
    import numpy as np
    from .. import loudness
    n = int(total * sr) + 1
    bus = np.zeros((n, 2), dtype=np.float32)
    v_db = loudness.rms_db(voice_path, seconds=None)
    for m in music:
        x = _decode(m["file"], sr)
        g = 10 ** ((v_db - below_db - loudness.rms_db(m["file"], seconds=None)) / 20)
        # пьеса короче своего окна = тишина до конца сцены и никакой ошибки (так пропала музыка в демо главы 5 после 64-й секунды):
        # добираем повтором с кроссфейдом и говорим об этом вслух — молчать тут нельзя
        need = int(((m["end"] - m["start"]) if m.get("end") is not None else (total - m["start"])) * sr)
        if len(x) < need - sr:
            print(f"[sound] тема короче окна на {(need - len(x)) / sr:.0f} с — добираю повтором с кроссфейдом")
            xf = max(1, min(int(2.0 * sr), len(x) // 4)); f = _cos_fade(xf)[:, None]
            parts, cur = [x.copy()], len(x)
            while cur < need:
                head = x.copy()
                parts[-1][-xf:] = parts[-1][-xf:] * f[::-1] + head[:xf] * f
                parts.append(head[xf:]); cur += len(head) - xf
            x = np.concatenate(parts)
        a = int(m["start"] * sr); b = min(n, a + len(x)); x = x[: b - a] * g
        if m.get("end") is not None:
            e = int(m["end"] * sr) - a
            if 0 < e < len(x): x = x[:e]
        L = len(x); fi, fo = min(L, int((m.get("fade_in") or 0) * sr)), min(L, int((m.get("fade_out") or 0) * sr))
        if fi: x[:fi] *= _cos_fade(fi)[:, None]
        if fo: x[L - fo:] *= _cos_fade(fo)[::-1][:, None]
        bus[a:a + L] += x
    # автоматика громкости музыки на 100 Гц
    cr = 100; m_ = int(total * cr) + 2
    speech = np.zeros(m_, dtype=bool)
    for w in words: speech[max(0, int((w["s"] - 0.2) * cr)):min(m_, int((w["e"] + 0.3) * cr) + 1)] = True
    k = 0
    while k < m_:   # короткие паузы между фразами — тоже речь
        if speech[k]: k += 1; continue
        j = k
        while j < m_ and not speech[j]: j += 1
        if k > 0 and j < m_ and (j - k) < MIN_GAP * cr: speech[k:j] = True
        k = j
    target = np.where(speech, 0.0, lift_db).astype(np.float32)
    for z0, z1 in lift_zones: target[int(z0 * cr):int(z1 * cr) + 1] = lift_db
    for lv in live: target[max(0, int((lv["at"] - 0.4) * cr)):int((lv["at"] + lv["dur"] + 0.3) * cr) + 1] = LIVE_DB
    env = np.empty_like(target); cur = float(target[0])
    ka, kr = 1 - math.exp(-1 / (cr * ATTACK)), 1 - math.exp(-1 / (cr * RELEASE))
    for i, t in enumerate(target):
        cur += (ka if t < cur else kr) * (t - cur); env[i] = cur
    step = sr * 60   # по минуте: на 28-минутном ролике кривая целиком — это три массива float64 по 650 МБ
    for i0 in range(0, n, step):
        i1 = min(n, i0 + step)
        bus[i0:i1] *= (10 ** (np.interp(np.arange(i0, i1) / sr, np.arange(m_) / cr, env) / 20)).astype(np.float32)[:, None]
    for x_ in list(sfx) + list(live):
        y = _decode(x_["file"], sr) * float(x_.get("volume", 1.0))
        if x_.get("dur"): y = y[: int(x_["dur"] * sr)]
        f = min(len(y), int(0.08 * sr))
        y[:f] *= _cos_fade(f)[:, None]; y[-f:] *= _cos_fade(f)[::-1][:, None]
        a = int(x_["at"] * sr); b = min(n, a + len(y)); bus[a:b] += y[: b - a]
    peak = float(np.max(np.abs(bus))) or 1.0
    if peak > 0.89: bus *= 0.89 / peak
    subprocess.run([_ff(), "-y", "-v", "error", "-f", "f32le", "-ar", str(sr), "-ac", "2", "-i", "-", "-c:a", "pcm_s16le", str(out)], input=bus.tobytes(), check=True)
    return {"voice_db": round(v_db, 1), "env_min": round(float(env.min()), 1), "env_max": round(float(env.max()), 1), "peak": round(peak, 3)}


THEME_MAX = 270.0            # одна композиция ElevenLabs Music — до 5 минут; длинная глава делится на две темы со стыком на паузе
CARD_OUT, CARD_IN = 2.2, 0.8  # смена темы внутри карточки главы: старая уходит к 2.2 с карточки, новая входит с 0.8 с (как в демо, которое принял владелец)


def _words_sig(words: list[dict]) -> str:
    return hashlib.sha1(json.dumps([len(words), words[0]["s"], words[-1]["e"], words[len(words) // 2]["s"]]).encode()).hexdigest()[:16]


def build(vid: str, d, tl: dict, words: list[dict]) -> dict:
    """Партитура всего ролика (звук v2, принятый владельцем по демо 17.09): одна тема на главу, смена темы — на карточке главы,
    музыка −25 dB под голосом и +9 dB в паузах, эффектов под голосом нет. Итог — одна дорожка sound/score.mp3 и блок timeline.score
    (Main.tsx играет её вместо MusicTracks и стингеров глав). Разметка и темы кешируются в sound/ и сбрасываются, если сменился голос."""
    sdir = d / "sound"; sdir.mkdir(exist_ok=True)
    total = float(tl["duration"]); sig = _words_sig(words); meta_p = sdir / "score.json"
    meta = json.loads(config.read(meta_p)) if meta_p.exists() else {}
    old_sigs = meta.get("theme_sigs") or {}; new_sigs = {}
    if meta.get("sig") != sig and not old_sigs:     # другой голос — другие тайминги: старые темы легли бы мимо поворотов
        for p in list(sdir.glob("theme_*.mp3")) + list(sdir.glob("cues_*.json")): p.unlink(missing_ok=True)
    # с 18.09 подпись у каждой темы своя: вырезка слова в 20:44 Amazon сдвинула только последнюю главу,
    # а общая подпись выбросила и перегенерировала все 8 тем (~$4 кредитами ElevenLabs и другая музыка в уже принятых главах)
    cards = sorted(float(p["at"]) for p in tl.get("pauses") or [])
    edges = [0.0] + cards + [total]
    sents_all = [s for s in sentences(words)]
    music, n_themes = [], 0
    for k, (a, b) in enumerate(zip(edges, edges[1:])):
        parts = max(1, math.ceil((b - a) / THEME_MAX))
        cuts = [a]
        for i in range(1, parts):   # стык тем внутри главы — на начале предложения, ближайшем к равной доле
            t = a + (b - a) * i / parts
            cand = [s["s"] for s in sents_all if a + 30 < s["s"] < b - 30]
            cuts.append(min(cand, key=lambda x: abs(x - t)) if cand else t)
        cuts.append(b)
        for i, (p0, p1) in enumerate(zip(cuts, cuts[1:])):
            sents = [s for s in sents_all if p0 - 0.01 <= s["s"] < p1]
            if not sents: continue
            cues_p = sdir / f"cues_{k + 1}_{i}.json"; name = f"{k + 1}_{i}"
            new_sigs[name] = hashlib.sha1(json.dumps([round(p0, 2), round(p1, 2), total if p1 >= total else 0, [(s["text"], round(s["s"], 2)) for s in sents]],
                                                     ensure_ascii=False).encode()).hexdigest()[:16]
            if old_sigs and old_sigs.get(name) != new_sigs[name]:   # окно этой темы сдвинулось или поменялся текст — только её и заново
                cues_p.unlink(missing_ok=True); (sdir / f"theme_{name}.mp3").unlink(missing_ok=True)
            # строка пропала при правке 18.09 19:53 (подписи тем) — render Microsoft 19.09 упал на NameError: plan
            plan = json.loads(config.read(cues_p)) if cues_p.exists() else cues(f"{vid}_{k + 1}_{i}", sents, [])
            config.write(cues_p, json.dumps(plan, ensure_ascii=False, indent=1))
            bounds = [p0] + [sents[q["start"]]["s"] for q in plan["sections"][1:]]
            first, last = i == 0, i == len(cuts) - 2
            start = p0 + (CARD_IN if (first and k) else 0.0) - (0.0 if first else XF_IN)
            end = (p1 + CARD_OUT) if (last and k < len(edges) - 2) else ((total + 0.5) if last else p1 + XF_OUT)
            f = sdir / f"theme_{k + 1}_{i}.mp3"
            compose_theme(theme_chunks(plan["sections"], bounds, start, end, tail=10.0), f, seed=40 + k * 3 + i)
            music.append({"file": f, "start": round(max(0.0, start), 3), "end": round(min(total + 0.5, end), 3),
                          "fade_in": 1.6 if (k or i) else 1.5, "fade_out": 2.0 if not (last and k == len(edges) - 2) else 3.0})
            n_themes += 1
    wav = sdir / "score.wav"
    info = mix(wav, total, words, d / "voice.mp3", music)
    out = sdir / "score.mp3"
    subprocess.run([_ff(), "-y", "-v", "error", "-i", str(wav), "-c:a", "libmp3lame", "-b:a", "256k", str(out)], check=True)
    wav.unlink(missing_ok=True)   # 320 МБ в папке видео Remotion копировал бы в temp при каждом рендере
    config.write(meta_p, json.dumps({"sig": sig, "themes": n_themes, "mix": info, "theme_sigs": new_sigs}, ensure_ascii=False))
    score = {"music": [{"src": "sound/score.mp3", "start": 0.0, "end": total, "offset": 0.0, "gain": 1.0}],
             "curve": {"dt": 1.0, "v": [1.0]}, "sfx": [], "live": []}
    print(f"[sound] партитура: глав {len(edges) - 1}, тем {n_themes}, сведение {info}", flush=True)
    return score


def master(src, dst, lufs: float = -14.0) -> dict:
    """Двухпроходный loudnorm по звуку, видео копируется. YouTube тихий ролик не поднимает."""
    first = subprocess.run([_ff(), "-hide_banner", "-i", str(src), "-vn", "-af", f"loudnorm=I={lufs}:TP=-1.0:LRA=11:print_format=json", "-f", "null", "-"],
                           capture_output=True, text=True).stderr
    m = json.loads(first[first.rindex("{"):first.rindex("}") + 1])
    af = (f"loudnorm=I={lufs}:TP=-1.0:LRA=11:measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}:"
          f"measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true")
    subprocess.run([_ff(), "-y", "-v", "error", "-i", str(src), "-c:v", "copy", "-af", af, "-c:a", "aac", "-b:a", "192k", "-ar", "48000", str(dst)], check=True)
    return {"input_i": float(m["input_i"]), "input_lra": float(m["input_lra"])}
