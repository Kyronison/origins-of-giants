"""Громкость треков без внешних фильтров (ffmpeg у Remotion урезан): декодируем в WAV и считаем RMS активных окон."""
import array, io, math, subprocess, wave
from . import config

def envelope_db(path, seconds: float | None = 240, win_sec: float = 0.5) -> list[float]:
    """Огибающая: RMS в dBFS по окнам win_sec (тишина → -120)."""
    cmd = [config.ffmpeg(), "-v", "error", "-i", str(path), "-ac", "1", "-ar", "8000", "-f", "wav"]
    if seconds: cmd += ["-t", str(seconds)]
    raw = subprocess.run(cmd + ["pipe:1"], capture_output=True).stdout
    w = wave.open(io.BytesIO(raw)); a = array.array("h"); a.frombytes(w.readframes(w.getnframes()))
    win = int(8000 * win_sec); vals = []
    for i in range(0, len(a) - win, win):
        s = sum(x * x for x in a[i:i + win]) / win
        vals.append(10 * math.log10(s / (32768 ** 2)) if s > 0 else -120.0)
    return vals

def rms_db(path, seconds: float | None = 240, active_share: float = 0.7) -> float:
    """RMS в dBFS по самым громким active_share окнам (0.5 с): паузы голоса не занижают уровень."""
    vals = [v for v in envelope_db(path, seconds) if v > -119]
    if not vals: return -60.0
    vals.sort(); top = vals[int(len(vals) * (1 - active_share)):]
    return sum(top) / len(top)

def intro_offset(path, below_db: float | None = None, win_sec: float = 0.5) -> float:
    """Секунда, с которой трек главы стоит запускать: первое окно, где RMS ≥ (уровень трека − below_db), минус одно окно разгона.
    Треки с тихим интро (−68…−30 dB первые 7 с) под карточкой давали мёртвую тишину."""
    below = config.MUSIC_INTRO_DB if below_db is None else below_db
    env = envelope_db(path, 240, win_sec)
    if not env: return 0.0
    level = rms_db(path)
    k = next((i for i, v in enumerate(env) if v >= level - below), 0)
    return round(max(0.0, (k - 1) * win_sec), 2)

def attack_offset(path, below_peak_db: float = 12.0, win_sec: float = 0.1) -> float:
    """Секунда, с которой стартует стингер: первое окно в пределах below_peak_db от пика минус одно окно —
    вступление −63…−25 dBFS (1.5 с) под карточкой звучало как дыра, пик приходил через 2 с после карточки."""
    env = envelope_db(path, 10, win_sec)
    if not env: return 0.0
    peak = max(env)
    k = next((i for i, v in enumerate(env) if v >= peak - below_peak_db), 0)
    return round(max(0.0, (k - 1) * win_sec), 2)

def sfx_gain(voice_path, sfx_path, below_db: float | None = None, lo: float = 0.05, hi: float = 0.6) -> float:
    """Множитель громкости стингера: пик стингера (самые громкие 30 % окон) на below_db ниже голоса."""
    below = config.SFX_BELOW_DB if below_db is None else below_db
    v, m = rms_db(voice_path), rms_db(sfx_path, active_share=0.3)
    g = 10 ** ((v - below - m) / 20)
    print(f"[loudness] стингер {m:.1f} dBFS, голос {v:.1f} → volume {g:.3f}")
    return round(min(hi, max(lo, g)), 4)

def music_gain(voice_path, music_path, below_db: float = 22.0, lo: float = 0.02, hi: float = 0.25) -> float:
    """Множитель громкости трека, чтобы он играл на below_db ниже голоса."""
    v, m = rms_db(voice_path), rms_db(music_path)
    g = 10 ** ((v - below_db - m) / 20)
    print(f"[loudness] голос {v:.1f} dBFS, музыка {m:.1f} dBFS → volume {g:.3f} (музыка на {below_db:.0f} dB тише)")
    return round(min(hi, max(lo, g)), 4)
