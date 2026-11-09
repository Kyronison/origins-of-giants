"""Process-only configuration. Must run before importing orchestrator.config."""
import os
import sys
from pathlib import Path

CHANNEL_ID = "UClLCYofo9rweGQ0MwrVueoA"
COMMANDS = {"auth-ancestors", "verify-ancestors", "start-ancestors", "watch-ancestors",
            "run-ancestors", "status-ancestors", "upload-ancestors"}


def activate():
    if "orchestrator.config" in sys.modules:
        raise RuntimeError("Ancestors profile must be selected before importing config")
    root = Path(__file__).resolve().parent.parent
    # Read only non-secret path defaults; load_dotenv later supplies provider keys.
    from dotenv import dotenv_values
    original = dotenv_values(root / ".env")
    shared = Path(os.environ.get("ANCESTORS_SHARED_DATA") or original.get("DATA_DIR") or root / "data")
    data = Path(os.environ.get("ANCESTORS_DATA_DIR", "E:/OrdinaryAncestors/data"))
    if data.resolve() == shared.resolve():
        raise ValueError("Ancestors DATA must be separate from the existing channel DATA")
    os.environ.update({
        "CHANNEL_PROFILE": "ancestors", "CHANNEL_NAME": "Ordinary Ancestors",
        "DATA_DIR": str(data), "SPEND_LEDGER_PATH": str(shared / "spend.sqlite3"),
        "SHARED_PIPELINE_DB": str(shared / "pipeline.db"),
        "RENDER_TMP": str(data / "render_tmp"),
        "AUTO_PIPELINE": "0", "AUTO_BACKLOG": "0", "ES_AUTO": "0", "ES_CARTOON": "0",
        "ES_CARTOON_UPLOAD": "0", "SHORTS_PER_VIDEO": "0", "AUTO_APPROVE": "0",
        "REQUIRE_FINAL_APPROVAL": "1", "SPEND_VIDEO_LIMIT": "25", "SPEND_MONTH_LIMIT": "500",
        "BUDGET_USD": "25", "TTS_MODE": "v3_chain", "TTS_VIA_FAL": "1", "TTS_TARGET_WPM": "150",
        "TTS_TEMPO": "1.0",
    })
    os.environ.setdefault("YOUTUBE_CLIENT_SECRET_FILE", str(original.get("YOUTUBE_CLIENT_SECRET_FILE") or shared / "youtube_client_secret.json"))
    # Owner selected Charlie after listening to samples; explicit override wins.
    os.environ["ELEVENLABS_VOICE_ID"] = os.environ.get("ANCESTORS_VOICE_ID") or "IKne3meq5aSn9XLyUdCD"
    return data
