# -*- coding: utf-8 -*-
"""Shared, crash-safe access to data/approved_catalog.json.

save_catalog() writes <file>.tmp in the same directory, fsyncs, then os.replace()s it
over the real file (atomic), under a simple cross-process lock file (<file>.lock).
Output formatting matches the old writers (ensure_ascii=False, indent=2).
"""
import json, os, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CATALOG_FILE = ROOT / "data" / "approved_catalog.json"

LOCK_WAIT = 10.0      # seconds to keep retrying
STALE_LOCK = 60.0     # a lock older than this is considered abandoned


def load_catalog(path=None):
    p = Path(path) if path else CATALOG_FILE
    if not p.exists():
        return []
    with open(p, encoding="utf-8-sig") as f:   # tolerate a stray BOM
        return json.load(f)


class _Lock:
    def __init__(self, target, wait=LOCK_WAIT, stale=STALE_LOCK):
        self.path = Path(str(target) + ".lock")
        self.wait, self.stale = wait, stale

    def __enter__(self):
        deadline = time.time() + self.wait
        while True:
            try:
                fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, str(os.getpid()).encode())
                os.close(fd)
                return self
            except (FileExistsError, PermissionError):   # PermissionError: Windows delete-pending race
                try:
                    if time.time() - self.path.stat().st_mtime > self.stale:
                        self.path.unlink()
                        continue
                except FileNotFoundError:
                    continue
                except OSError:
                    pass
                if time.time() >= deadline:
                    raise TimeoutError(f"catalog lock busy: {self.path}")
                time.sleep(0.1)

    def __exit__(self, *exc):
        try:
            self.path.unlink()
        except OSError:
            pass


def save_catalog(items, path=None):
    p = Path(path) if path else CATALOG_FILE
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(str(p) + ".tmp")
    with _Lock(p):
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(items, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, p)
        finally:
            if tmp.exists():
                try: tmp.unlink()
                except OSError: pass
