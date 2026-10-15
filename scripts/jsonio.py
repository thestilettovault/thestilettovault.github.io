# -*- coding: utf-8 -*-
"""
jsonio.py — safe JSON file I/O for the sourcing pipeline.

  load(path, default)  default ONLY when the file is missing. A file that exists
                       but does not parse is copied to <name>.corrupt-<timestamp>
                       and the parse error is raised — callers must never treat a
                       corrupt file as "empty" and overwrite it.
  save(path, obj, **dump_kwargs)
                       atomic write (tmp file in the same dir, fsync, os.replace)
                       under a lock file.
  locked(path)         context manager for read-modify-write sequences:
                           with jsonio.locked(p):
                               d = jsonio.load(p, {}); d["x"] = 1; jsonio.save(p, d)

Locks are re-entrant inside one thread (save() inside locked() is fine).
"""
import json
import os
import shutil
import threading
import time
from contextlib import contextmanager
from datetime import datetime

LOCK_TIMEOUT = 10.0     # seconds to wait for a lock held by someone else
STALE_AFTER = 60.0      # a lock file older than this is considered abandoned

_tls = threading.local()


def _held():
    if not hasattr(_tls, "held"):
        _tls.held = {}
    return _tls.held


def _lock_path(path):
    return str(path) + ".lock"


@contextmanager
def locked(path):
    """Exclusive cross-process lock for `path` (re-entrant per thread)."""
    lp = _lock_path(path)
    held = _held()
    if held.get(lp):
        held[lp] += 1
        try:
            yield
        finally:
            held[lp] -= 1
        return
    d = os.path.dirname(os.path.abspath(lp))
    os.makedirs(d, exist_ok=True)
    deadline = time.time() + LOCK_TIMEOUT
    while True:
        try:
            fd = os.open(lp, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            break
        except FileExistsError:
            try:
                if time.time() - os.path.getmtime(lp) > STALE_AFTER:
                    os.remove(lp)
                    continue
            except OSError:
                continue            # vanished between exists-check and stat: retry
            if time.time() >= deadline:
                raise TimeoutError(f"jsonio: could not lock {path} within {LOCK_TIMEOUT}s")
            time.sleep(0.05)
    held[lp] = 1
    try:
        yield
    finally:
        held.pop(lp, None)
        try:
            os.remove(lp)
        except OSError:
            pass


def load(path, default=None):
    """Parsed JSON, or `default` if the file does not exist. Corrupt file →
    backed up as <name>.corrupt-<timestamp> and the error is raised."""
    path = str(path)
    if not os.path.exists(path):
        return default
    try:
        with open(path, encoding="utf-8-sig") as f:
            return json.load(f)
    except (ValueError, UnicodeDecodeError):      # JSONDecodeError is a ValueError
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = f"{path}.corrupt-{stamp}"
        try:
            shutil.copy2(path, backup)
        except OSError:
            pass
        raise


def save(path, obj, **dump_kwargs):
    """Atomically write `obj` as JSON (pass indent/ensure_ascii to keep a file's
    existing formatting)."""
    path = str(path)
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)
    with locked(path):
        tmp = f"{path}.tmp-{os.getpid()}-{threading.get_ident()}"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(obj, f, **dump_kwargs)
                f.flush()
                os.fsync(f.fileno())
            for attempt in range(10):       # Windows: replace fails while a reader has it open
                try:
                    os.replace(tmp, path)
                    break
                except PermissionError:
                    if attempt == 9:
                        raise
                    time.sleep(0.05)
        finally:
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass
