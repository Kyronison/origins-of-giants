"""Эксперимент «две недели без шортсов» (владелец 23.09.2026).

Гипотеза: 11 шортсов против 6 документалок сделали канал «каналом шортсов» — за девять дней шортсы собрали ~4 650
просмотров и дали НОЛЬ переходов на длинные ролики (в источниках трафика документалок строки Shorts нет вовсе),
а аудитория шортсов (RU, UZ, PH) не пересекается со зрителями английских документалок. Проверяем, вырастут ли
показы и просмотры документалок, если две недели не выпускать шортсы.

База замеров записана 23.09 в data/experiment_no_shorts.json, шортсы выключены (SHORTS_PER_VIDEO=0),
пять уже загруженных шортсов сняты с расписания (файлы и id целы, publishAt просто убран).

Итоги: `python -m orchestrator.main experiment` — сравнивает те же метрики с базой. Смотреть 07.10.2026.
Важно: это не чистый A/B, а «до и после» на растущем канале: за две недели добавятся новые ролики,
поэтому главный показатель — не сумма просмотров, а СРЕДНЕЕ на документалку за первые 48 часов и доля
алгоритмического трафика (RELATED_VIDEO, browse) против трафика от подписчиков."""
import json
from . import config, db

LONG_FILE = config.DATA / "experiment_no_shorts.json"


def _long_ids(y) -> list[str]:
    """Документалки канала: длиннее 5 минут, опубликованные."""
    up = y.channels().list(part="contentDetails", mine=True).execute()["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    ids, tok = [], None
    while True:
        r = y.playlistItems().list(part="snippet", playlistId=up, maxResults=50, pageToken=tok).execute()
        ids += [i["snippet"]["resourceId"]["videoId"] for i in r["items"]]; tok = r.get("nextPageToken")
        if not tok: break
    out = []
    for a in range(0, len(ids), 50):
        for i in y.videos().list(part="snippet,status,contentDetails,statistics", id=",".join(ids[a:a + 50])).execute()["items"]:
            dur = i["contentDetails"]["duration"]; mins = int(dur.split("PT")[1].split("M")[0]) if "M" in dur else 0
            if mins > 5 and i["status"]["privacyStatus"] == "public": out.append(i)
    return out


def report(end: str = "2026-10-07"):
    from .stages import upload
    y = upload.yt(); a = upload.yt("youtubeAnalytics", "v2")
    base = json.loads(config.read(LONG_FILE)) if LONG_FILE.exists() else {}
    if not base: print("Нет базы замеров (data/experiment_no_shorts.json) — эксперимент не начинали."); return
    longs = _long_ids(y)
    ids = ",".join(i["id"] for i in longs)
    ch = y.channels().list(part="statistics", mine=True).execute()["items"][0]["statistics"]
    print(f"ЭКСПЕРИМЕНТ «без шортсов»: {base.get('started')} → {end}\n")
    b = base.get("channel", {})
    print(f"подписчиков: {b.get('subscriberCount')} → {ch.get('subscriberCount')}")
    print(f"просмотров канала: {b.get('viewCount')} → {ch.get('viewCount')}")
    print(f"\nДОКУМЕНТАЛКИ (просмотры на сейчас; * — вышли уже во время эксперимента):")
    was = base.get("long_videos", {})
    for i in sorted(longs, key=lambda x: x["snippet"]["publishedAt"]):
        v0 = (was.get(i["id"]) or {}).get("views")
        mark = "" if i["id"] in was else " *"
        print(f"  {i['snippet']['publishedAt'][5:10]} {int(i['statistics'].get('viewCount', 0)):6}"
              + (f" (было {v0})" if v0 is not None else "") + mark + "  " + i["snippet"]["title"][:50])
    q = dict(ids="channel==MINE", startDate=base.get("started", "2026-09-23"), endDate=end)
    try:
        rows = a.reports().query(**q, metrics="views,estimatedMinutesWatched,averageViewPercentage",
                                 dimensions="insightTrafficSourceType", filters=f"video=={ids}", sort="-views").execute().get("rows", [])
        print("\nИСТОЧНИКИ ТРАФИКА ДОКУМЕНТАЛОК за период эксперимента (источник, просмотры, минуты, ср.%):")
        for r in rows: print("  ", r)
        print("\nБЫЛО (до эксперимента):")
        for r in base.get("long_traffic", []): print("  ", r)
        algo = sum(r[1] for r in rows if r[0] in ("RELATED_VIDEO", "BROWSE_FEATURES", "YT_SEARCH"))
        algo0 = sum(r[1] for r in base.get("long_traffic", []) if r[0] in ("RELATED_VIDEO", "BROWSE_FEATURES", "YT_SEARCH"))
        print(f"\nАЛГОРИТМИЧЕСКИЙ ТРАФИК (похожие + поиск + лента): было {algo0} → стало {algo}")
        print("ВЫВОД: рост алгоритмического трафика и среднего на ролик = шортсы мешали; без изменений = дело не в них.")
    except Exception as e:
        print("\nаналитика недоступна:", str(e)[:200])
