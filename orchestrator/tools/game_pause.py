"""Пауза конвейера на время игры (владелец 23.09.2026: «если запускается cs2.exe, весь рендер сразу ставится на паузу»).

Пока запущен процесс из списка игр, все рабочие процессы конвейера — Chrome рендера Remotion, node, ffmpeg, yt-dlp —
замораживаются средствами Windows (SuspendThread через psutil). Рендер не теряет ни кадра: после выхода из игры
процессы размораживаются и продолжают с того же места.

ЧТО НЕ ТРОГАЕТСЯ:
  • обычный Chrome владельца и любые чужие процессы — замораживаются ТОЛЬКО потомки наших python-процессов конвейера,
    поиск идёт по дереву процессов, а не по имени (у владельца открыт свой Chrome с десятком вкладок);
  • сам python конвейера — он в это время просто ждёт подпроцесс. Благодаря этому ЗАГРУЗКИ НА YOUTUBE НЕ ПРЕРЫВАЮТСЯ:
    они идут внутри python и упираются в сеть, а не в процессор, игре не мешают, а обрыв стоил бы часа.

ВАЖНО ПРО ТАЙМАУТЫ: пока процесс заморожен, системные часы идут. Remotion считает таймаут кадра по часам, поэтому
у рендера поднят --timeout (см. stages/render.py): иначе после долгой паузы кадр упал бы с «timed out» сразу при пробуждении.

Запуск: python -m orchestrator.tools.game_pause   (или game_pause.cmd в корне проекта)
Настройки в .env: PAUSE_ON_GAMES=cs2.exe,dota2.exe   PAUSE_POLL_SEC=3
"""
import os, sys, time
import psutil

# 25.09: по умолчанию пусто — владелец отключил паузу на время игры, рендер идёт всегда.
GAMES = {g.strip().lower() for g in os.getenv("PAUSE_ON_GAMES", "").split(",") if g.strip()}
POLL = float(os.getenv("PAUSE_POLL_SEC", 3))
OURS = ("orchestrator.main", "orchestrator/main", "nflx_es_rerender", "costco_rerender", "_run.py")   # наши python-процессы


def _pipeline_roots() -> list[psutil.Process]:
    """Наши python-процессы конвейера: watch и ручные прогоны. Их потомки — это и есть рендер."""
    out = []
    for p in psutil.process_iter(["name", "cmdline"]):
        try:
            if (p.info["name"] or "").lower() not in ("python.exe", "python"): continue
            cmd = " ".join(p.info["cmdline"] or "")
            if any(k in cmd for k in OURS): out.append(p)
        except (psutil.NoSuchProcess, psutil.AccessDenied): pass
    return out


def _workers() -> list[psutil.Process]:
    """Потомки наших процессов — Chrome Remotion, node, ffmpeg, yt-dlp. Чужой Chrome сюда не попадает по определению."""
    out, seen = [], set()
    for root in _pipeline_roots():
        try: kids = root.children(recursive=True)
        except (psutil.NoSuchProcess, psutil.AccessDenied): continue
        for k in kids:
            if k.pid in seen: continue
            seen.add(k.pid); out.append(k)
    return out


def _game() -> str | None:
    for p in psutil.process_iter(["name"]):
        try:
            n = (p.info["name"] or "").lower()
            if n in GAMES: return n
        except (psutil.NoSuchProcess, psutil.AccessDenied): pass
    return None


def main():
    if not GAMES:
        print("[pause] список игр пуст — пауза отключена, выхожу", flush=True); return
    print(f"[pause] слежу за {', '.join(sorted(GAMES))}; опрос каждые {POLL:g} с", flush=True)
    frozen: dict[int, psutil.Process] = {}
    while True:
        try:
            g = _game()
            if g and not frozen:
                for w in _workers():
                    try: w.suspend(); frozen[w.pid] = w
                    except (psutil.NoSuchProcess, psutil.AccessDenied) as e: print(f"[pause] {w.pid}: {str(e)[:60]}", flush=True)
                if frozen:   # пока конвейер между этапами, замораживать нечего — молчим, а не печатаем «0» каждые три секунды
                    print(f"[pause] {time.strftime('%H:%M')} запущен {g} — заморожено процессов: {len(frozen)} "
                          f"(рендер встал на том же кадре, загрузки на YouTube продолжаются)", flush=True)
            elif g and frozen:
                for w in _workers():   # конвейер мог запустить новый подпроцесс уже во время игры
                    if w.pid not in frozen:
                        try: w.suspend(); frozen[w.pid] = w; print(f"[pause] новый процесс {w.pid} ({w.name()}) — заморожен", flush=True)
                        except (psutil.NoSuchProcess, psutil.AccessDenied): pass
            elif not g and frozen:
                alive = 0
                for pid, w in list(frozen.items()):
                    try: w.resume(); alive += 1
                    except (psutil.NoSuchProcess, psutil.AccessDenied): pass
                frozen.clear()
                print(f"[pause] {time.strftime('%H:%M')} игра закрыта — разморожено: {alive}, работа продолжается", flush=True)
        except Exception as e:
            print(f"[pause] ошибка: {str(e)[:150]}", flush=True)
        time.sleep(POLL)


if __name__ == "__main__":
    try: main()
    except KeyboardInterrupt:
        print("[pause] остановлен — размораживаю всё, что держал", flush=True)
        for w in _workers():
            try: w.resume()
            except Exception: pass
        sys.exit(0)
