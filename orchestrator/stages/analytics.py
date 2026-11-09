"""Воскресенье: метрики по всем видео за 7 дней → отчёт + learnings.md."""
import json, traceback
from datetime import date, timedelta
from .. import db, llm, telegram, config
from .upload import yt

def run():
    ya = yt("youtubeAnalytics", "v2"); end = date.today(); start = end - timedelta(days=7)
    vids = [v for s in ("published", "analyzed", "uploaded") for v in db.by_status(s) if v["youtube_id"]]
    if not vids: print("Нет опубликованных видео — аналитике нечего считать"); return
    data = []
    for v in vids:
        base = dict(ids="channel==MINE", startDate=str(start), endDate=str(end), filters=f"video=={v['youtube_id']}")
        try:
            tot = ya.reports().query(**base, metrics="views,estimatedMinutesWatched,averageViewPercentage,subscribersGained,estimatedRevenue,cardClickRate").execute()
            ret = ya.reports().query(**base, metrics="audienceWatchRatio", dimensions="elapsedVideoTimeRatio").execute()
            src = ya.reports().query(**base, metrics="views", dimensions="insightTrafficSourceType").execute()
        except Exception:
            traceback.print_exc(); continue
        data.append({"id": v["id"], "title": v["title"],
                     "totals": dict(zip([c["name"] for c in tot["columnHeaders"]], tot["rows"][0] if tot.get("rows") else [])),
                     "retention": ret.get("rows", []), "traffic": src.get("rows", [])})
        if v["status"] == "uploaded": db.update(v["id"], "published")
    learn = config.DATA / "learnings.md"
    res = llm.ask_json(config.prompt("analytics", analytics_json=json.dumps(data, ensure_ascii=False),
                                     learnings=config.read(learn) if learn.exists() else "(пусто)"), heavy=True, max_tokens=12000, tag="analytics")
    config.write(learn, res["learnings_md"])
    config.write(config.DATA / f"report_{end}.md", res["report_md"])
    telegram.send(res["report_md"])
