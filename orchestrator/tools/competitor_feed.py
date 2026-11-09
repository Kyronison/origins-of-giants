"""Новые ролики конкурентов за последние сутки — сырьё для ежедневной сводки и комментариев (владелец 28.09).
Источник — RSS каналов YouTube (квоту API не тратит); к каждому ролику — начало автосубтитров, чтобы комментарий был по делу.
Запуск: python -m orchestrator.tools.competitor_feed [часов=26]  →  E:\\OriginsOfGiants\\data\\competitors\\feed_YYYY-MM-DD.json"""
import json, re, sys, warnings
from datetime import datetime, timedelta, timezone
from pathlib import Path
import xml.etree.ElementTree as ET
import requests

warnings.filterwarnings("ignore")
DATA = Path(r"E:\OriginsOfGiants\data"); OUT = DATA / "competitors"
NS = {"a": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015", "m": "http://search.yahoo.com/mrss/"}


def transcript(vid: str, limit: int = 6000) -> str:
    try:
        import yt_dlp
        ydl = yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "skip_download": True})
        info = ydl.extract_info(f"https://www.youtube.com/watch?v={vid}", download=False)
        caps = (info.get("automatic_captions") or {}).get("en") or (info.get("subtitles") or {}).get("en") or []
        url = next((c["url"] for c in caps if c.get("ext") == "json3"), None)
        dur = info.get("duration") or 0
        if not url: return f"[duration {dur}s] (субтитров нет)"
        ev = requests.get(url, timeout=60).json().get("events") or []
        text = re.sub(r"\s+", " ", " ".join(s.get("utf8", "") for e in ev for s in e.get("segs") or [])).strip()
        return f"[duration {dur}s] " + text[:limit]
    except Exception as e:
        return f"(текст не получен: {str(e)[:100]})"


def main(hours: float = 26):
    comp = json.loads((DATA / "competitors.json").read_text(encoding="utf-8"))
    since = datetime.now(timezone.utc) - timedelta(hours=hours); items = []
    for name, c in comp.items():
        if not c.get("sure"): continue
        try:
            root = ET.fromstring(requests.get(f"https://www.youtube.com/feeds/videos.xml?channel_id={c['id']}", timeout=30).content)
        except Exception as e:
            print(f"{name}: лента не получена — {str(e)[:80]}"); continue
        for e in root.findall("a:entry", NS):
            pub = datetime.fromisoformat(e.find("a:published", NS).text)
            if pub < since: continue
            vid = e.find("yt:videoId", NS).text; st = e.find("m:group/m:community/m:statistics", NS)
            items.append({"channel": name, "subs": c.get("subs"), "title": e.find("a:title", NS).text, "url": f"https://www.youtube.com/watch?v={vid}",
                          "published": pub.isoformat(), "hours_ago": round((datetime.now(timezone.utc) - pub).total_seconds() / 3600, 1),
                          "views": int(st.get("views")) if st is not None else None, "transcript": transcript(vid)})
    items = [i for i in items if "/shorts/" not in i["url"] and not re.search(r"\[duration (\d+)s\]", i["transcript"]) or int((re.search(r"\[duration (\d+)s\]", i["transcript"]) or [0, 999])[1]) > 180]
    items.sort(key=lambda i: i["hours_ago"])
    OUT.mkdir(parents=True, exist_ok=True)
    f = OUT / f"feed_{datetime.now():%Y-%m-%d}.json"; f.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"новых длинных роликов за {hours:g} ч: {len(items)} → {f}")
    for i in items: print(f"  {i['hours_ago']:>5} ч | {i['channel']} | {i['title'][:80]} | {i['views']} просм.")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main(float(sys.argv[1]) if len(sys.argv) > 1 else 26)
