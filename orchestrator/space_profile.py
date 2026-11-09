"""Космический канал (23.10.2026, проверка направления «космос» из work/niche-analysis-2026-10-23/analysis.md).

Изолированный профиль по образцу Ordinary Ancestors: свои данные E:/SpaceChannel/data (очередь, ролики, токен YouTube),
общий журнал расходов E:/OriginsOfGiants/data/spend.sqlite3 с той же консервативной проверкой бюджета (ancestors_budget):
каждый платный запрос резервируется до оплаты; неоценённые запросы в журнале блокируют траты; лимит выпуска SPEND_VIDEO_LIMIT
(цель GPT — ~$16 на выпуск), общий месячный $500.

Общие модули (spend.py, config.py) не меняются — работающие watch EN/ES держат их в памяти. Резервирование ставится в процессе
этого профиля через install() (замена spend._begin), поэтому activate() + install() вызываются только из точек входа space.
"""
import os
import sys
import uuid
from contextlib import closing
from pathlib import Path

CHANNEL_ID = os.environ.get("SPACE_CHANNEL_ID", "")   # заполняется после OAuth владельца (verify сверяет каждый запрос записи)
DATA_DEFAULT = "E:/SpaceChannel/data"

SYSTEM = ("You produce an English science explainer channel about extreme objects and physical scales in space. "
          "Use only the supplied facts and calculations. Keep established knowledge, estimates with uncertainty and "
          "hypotheses clearly apart; never present a hypothesis as a discovery. No invented numbers, quotes or sources. "
          "Follow the requested JSON schema exactly.")


def activate():
    if "orchestrator.config" in sys.modules:
        raise RuntimeError("Space profile must be selected before importing config")
    root = Path(__file__).resolve().parent.parent
    from dotenv import dotenv_values
    original = dotenv_values(root / ".env")
    shared = Path(original.get("DATA_DIR") or root / "data")
    data = Path(os.environ.get("SPACE_DATA_DIR", DATA_DEFAULT))
    if data.resolve() == shared.resolve():
        raise ValueError("Space DATA must be separate from the existing channel DATA")
    os.environ.update({
        "CHANNEL_PROFILE": "space", "CHANNEL_NAME": os.environ.get("SPACE_CHANNEL_NAME", "Space channel"),
        "DATA_DIR": str(data), "SPEND_LEDGER_PATH": str(shared / "spend.sqlite3"),
        "SHARED_PIPELINE_DB": str(shared / "pipeline.db"),
        "RENDER_TMP": str(data / "render_tmp"),
        "AUTO_PIPELINE": "0", "AUTO_BACKLOG": "0", "ES_AUTO": "0", "ES_CARTOON": "0",
        "ES_CARTOON_UPLOAD": "0", "SHORTS_PER_VIDEO": "0", "AUTO_APPROVE": "0",
        "REQUIRE_FINAL_APPROVAL": "1", "SPEND_VIDEO_LIMIT": os.environ.get("SPACE_VIDEO_LIMIT", "16"), "SPEND_MONTH_LIMIT": "500",
        "BUDGET_USD": "16", "TTS_MODE": "v3_chain", "TTS_VIA_FAL": "1", "TTS_TARGET_WPM": "150", "TTS_TEMPO": "1.0",
        "IMAGE_MODEL": "openai/gpt-image-2.5/flare/text-to-image",
    })
    os.environ.setdefault("YOUTUBE_CLIENT_SECRET_FILE", str(original.get("YOUTUBE_CLIENT_SECRET_FILE") or shared / "youtube_client_secret.json"))
    os.environ["ELEVENLABS_VOICE_ID"] = os.environ.get("SPACE_VOICE_ID") or original.get("SPACE_VOICE_ID") or ""
    return data


def install():
    """Резерв до оплаты для каждого запроса OpenRouter/fal этого процесса (та же логика, что у профиля ancestors в spend._begin)."""
    from . import config, spend
    from .ancestors_budget import reserve_amount, check_limits
    if os.getenv("CHANNEL_PROFILE") != "space":
        raise RuntimeError("install() only inside the space profile")
    if Path(spend._path()).resolve() != Path("E:/OriginsOfGiants/data/spend.sqlite3").resolve():
        raise RuntimeError("Space spending must go to the shared ledger")

    def _begin(provider, model, arguments=None, attribution=None):
        at = attribution or spend.current()
        if at is None:
            return None
        estimate, source = spend._estimate_fal(model, arguments) if provider == "fal" else (None, None)
        reservation = reserve_amount(provider, model, arguments, estimate)
        attempt = uuid.uuid4().hex
        now = spend._now()
        with closing(spend._connect()) as c, c:
            c.execute("BEGIN IMMEDIATE")
            check_limits(c, at.video_id, reservation)
            c.execute("INSERT INTO requests VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                      (attempt, provider, None, at.video_id, at.stage, str(model), "pending",
                       None, estimate, source, None, now, now))
            c.execute("INSERT INTO budget_reservations VALUES(?,?)", (attempt, reservation))
        return attempt

    spend._begin = _begin
    config.channel_prompt = lambda: SYSTEM
