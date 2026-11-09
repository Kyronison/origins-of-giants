"""One strictly identified channel; explicit private pilot upload only."""
import json
import os
from pathlib import Path
from .. import config, db
from ..ancestors_profile import CHANNEL_ID

SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube.readonly"]


def _profile():
    if os.getenv("CHANNEL_PROFILE") != "ancestors":
        raise RuntimeError("Use an ancestors command: refusing the default channel profile")


def token_path():
    _profile()
    return config.DATA / "youtube_token_ancestors.json"


def verify(y):
    items = y.channels().list(part="id,snippet", mine=True).execute().get("items", [])
    if len(items) != 1 or items[0].get("id") != CHANNEL_ID:
        raise RuntimeError("Wrong YouTube channel: expected " + CHANNEL_ID + "; received " +
                           ", ".join(str(x.get("id")) for x in items))
    return {"id": CHANNEL_ID, "title": items[0].get("snippet", {}).get("title", "")}


def auth():
    from google_auth_oauthlib.flow import InstalledAppFlow
    from .upload import gbuild
    _profile()
    flow = InstalledAppFlow.from_client_secrets_file(os.environ["YOUTUBE_CLIENT_SECRET_FILE"], SCOPES)
    creds = flow.run_local_server(port=0, open_browser=False, timeout_seconds=600,
                                 authorization_prompt_message="ANCESTORS_AUTH_URL: {url}",
                                 success_message="Authorization received. You may close this tab.",
                                 access_type="offline", prompt="consent")
    result = verify(gbuild("youtube", "v3", creds))
    path = token_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(creds.to_json(), encoding="utf-8")
    tmp.replace(path)
    print("Ancestors OAuth verified:", result, "token:", path, flush=True)
    return result


def client():
    from google.oauth2.credentials import Credentials
    from .upload import gbuild
    path = token_path()
    if not path.exists():
        raise RuntimeError("Run auth-ancestors first")
    y = gbuild("youtube", "v3", Credentials.from_authorized_user_file(str(path), SCOPES))
    verify(y)
    return y


def upload_private(vid):
    from .upload import _once
    from googleapiclient.http import MediaFileUpload
    from ..locking import video_lock
    from .ancestors_cartoon import validate_video
    _profile()
    with video_lock(vid, "upload-ancestors-private"):
        v = validate_video(vid)
        if v["status"] not in ("anc_ready", "anc_uploaded"):
            raise RuntimeError("Pilot must finish production and QC before private upload")
        if v["payload"].get("tech") or v["payload"].get("visual_qa", {}).get("status") != "PASS":
            raise RuntimeError("Pilot QC is not clean")
        d = db.video_dir(vid)
        final = d / "final.mp4"
        if not final.exists() or final.stat().st_size < 20_000_000:
            raise RuntimeError("Final video missing or incomplete")
        y = client()  # Verify the selected account before EVERY mutation.
        verify(y)
        done = dict(v["payload"].get("uploads") or {})
        body = {"snippet": {"title": (d / "publish/title.txt").read_text(encoding="utf-8").strip(),
                            "description": (d / "publish/description.txt").read_text(encoding="utf-8"),
                            "categoryId": "27", "defaultLanguage": "en", "defaultAudioLanguage": "en"},
                "status": {"privacyStatus": "private", "selfDeclaredMadeForKids": False}}
        ident = _once(y, "ancestors_pilot", done, body, final)
        remote = y.videos().list(part="snippet,status", id=ident).execute().get("items", [])
        if not remote or remote[0].get("snippet", {}).get("channelId") != CHANNEL_ID:
            raise RuntimeError("Upload receipt does not belong to the expected channel")
        if remote[0].get("status", {}).get("privacyStatus") != "private":
            raise RuntimeError("Expected private pilot; do not alter visibility automatically")
        db.update(vid, "anc_uploaded", youtube_id=ident, publish_at=None,
                  payload={"uploads": done, "upload_privacy": "private"})
        thumbnail = d / "publish/thumbnail.jpg"
        if thumbnail.exists() and not v["payload"].get("thumbnail_uploaded"):
            verify(y)
            y.thumbnails().set(videoId=ident, media_body=MediaFileUpload(str(thumbnail))).execute()
            db.update(vid, payload={"thumbnail_uploaded": True})
        print("Private pilot:", "https://www.youtube.com/watch?v=" + ident, flush=True)
        return ident
