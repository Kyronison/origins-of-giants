"""Process and thread locks. The OS releases ownership even after a crash."""
import json
import os
import threading
import time
from functools import wraps
from pathlib import Path

from . import config


class Busy(RuntimeError):
    pass


_guard = threading.Lock()
_owners = {}


def _pid_alive(pid):
    try:
        import psutil
        return psutil.pid_exists(int(pid))
    except (TypeError, ValueError):
        return True
    except Exception:
        return True  # an unverifiable legacy lock is not safe to steal


class FileLock:
    def __init__(self, path, stage="", legacy=None):
        self.path = Path(path)
        self.stage = stage
        self.legacy = legacy

    def __enter__(self):
        key = str(self.path.resolve())
        owner = (os.getpid(), threading.get_ident())
        with _guard:
            previous = _owners.get(key)
            if previous:
                if previous[0] != owner:
                    raise Busy(f"Занято: {self.path.name}")
                previous[1] += 1
                self.key = key
                return self
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fh = self.path.open("a+b")
            try:
                # Lock a persistent byte; never unlink this file (inode race).
                fh.seek(0, 2)
                if fh.tell() == 0:
                    fh.write(b"0"); fh.flush()
                fh.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                fh.close()
                raise Busy(f"Занято другим процессом: {self.path.name}") from exc
            try:
                if self.legacy and self.legacy.exists():
                    info = json.loads(self.legacy.read_text(encoding="utf-8"))
                    if info.get("pid") != os.getpid() and _pid_alive(info.get("pid")):
                        raise Busy(f"Занято процессом {info.get('pid')}: {info.get('stage')}")
                if self.legacy:
                    self.legacy.write_text(json.dumps({"pid": os.getpid(), "stage": self.stage, "at": time.time()}), encoding="utf-8")
            except Exception:
                fh.close()
                raise
            _owners[key] = [owner, 1, fh]
            self.key = key
        return self

    def __exit__(self, *args):
        with _guard:
            owned = _owners[self.key]
            owned[1] -= 1
            if owned[1]:
                return
            try:
                if self.legacy and self.legacy.exists():
                    try: info = json.loads(self.legacy.read_text(encoding="utf-8"))
                    except (ValueError, OSError): info = {}
                    if info.get("pid") == os.getpid():
                        self.legacy.unlink()
            finally:
                owned[2].close()
                del _owners[self.key]


def video_lock(vid, stage=""):
    from . import db
    d = db.video_dir(vid)
    return FileLock(d / ".execution.lock", stage, d / ".lock")


def exclusive(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        with FileLock(config.DATA / ".pipeline.lock", fn.__name__):
            return fn(*args, **kwargs)
    return wrapped
