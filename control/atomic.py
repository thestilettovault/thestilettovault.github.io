"""Atomic JSON writes: tmp file + fsync + os.replace."""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path

_SEQ = 0
_SEQ_LOCK = threading.Lock()


def write_json(path, obj, **dump_kwargs) -> None:
    global _SEQ
    dump_kwargs.setdefault("ensure_ascii", False)
    dump_kwargs.setdefault("indent", 2)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _SEQ_LOCK:
        _SEQ += 1
        n = _SEQ
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{n}.tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(json.dumps(obj, **dump_kwargs))
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass
