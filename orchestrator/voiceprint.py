"""Отпечаток голоса (speaker embedding ECAPA-TDNN, speechbrain) — объективная мера «тот же ли это голос».
Нужен, потому что ElevenLabs v3 в каждом запросе звучит чуть иначе, а высота/тембр/громкость по обычным замерам совпадают (владелец трижды
слышал «другой голос между главами»). Косинусная близость: один диктор в одной манере ≈ 0.75–0.9; заметно другой голос < 0.6."""
import subprocess
import numpy as np

_model = None


def _load():
    global _model
    if _model is None:
        import torch
        from speechbrain.inference.speaker import EncoderClassifier
        from speechbrain.utils.fetching import LocalStrategy
        from . import config
        # COPY: на Windows без прав администратора символические ссылки из кэша HF не создаются (WinError 1314)
        _model = EncoderClassifier.from_hparams(source="speechbrain/spkrec-ecapa-voxceleb", savedir=str(config.DATA / "cache" / "ecapa"),
                                                run_opts={"device": "cuda" if torch.cuda.is_available() else "cpu"}, local_strategy=LocalStrategy.COPY)
    return _model


def decode(path, sr: int = 16000) -> np.ndarray:
    import imageio_ffmpeg
    raw = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-v", "error", "-i", str(path), "-f", "f32le", "-ac", "1", "-ar", str(sr), "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32).copy()


def embed(x: np.ndarray) -> np.ndarray:
    import torch
    m = _load()
    with torch.no_grad():
        e = m.encode_batch(torch.from_numpy(x).unsqueeze(0)).squeeze().cpu().numpy()
    return e / (np.linalg.norm(e) + 1e-9)


def embed_span(x: np.ndarray, a: float, b: float, sr: int = 16000) -> np.ndarray:
    return embed(x[int(max(0, a) * sr):int(b * sr)])


def sim(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b))
