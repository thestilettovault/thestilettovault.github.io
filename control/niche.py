"""Niche config: load/save/clone the active niche's niche.json.

Scripts read tuning values through `cfg(path, default)`, which NEVER raises —
any error (missing file, missing key, bad JSON) just falls back to `default`,
so existing scripts keep working unmodified when niche config is absent.
"""
from __future__ import annotations

import copy
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NICHES_DIR = ROOT / "niches"
ACTIVE_FILE = NICHES_DIR / "active.txt"


def _niches_dir() -> Path:
    # re-derive from ROOT each call so tests can monkeypatch control.niche.ROOT
    return ROOT / "niches"


def _active_file() -> Path:
    return _niches_dir() / "active.txt"


def active_id() -> str:
    """Return the active niche id, or '' if none is set / file missing."""
    try:
        return _active_file().read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def _niche_json_path(nid: str) -> Path:
    return _niches_dir() / nid / "niche.json"


def _hub_json_path(nid: str) -> Path:
    return _niches_dir() / nid / "hub.json"


def load(nid: str | None = None) -> dict:
    """Load a niche's niche.json as a dict. Returns {} on any failure."""
    nid = nid or active_id()
    if not nid:
        return {}
    try:
        path = _niche_json_path(nid)
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _atomic_write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def save(cfg_data: dict, nid: str | None = None) -> None:
    """Atomically write a niche's niche.json."""
    nid = nid or active_id()
    if not nid:
        raise ValueError("no active niche and no nid given")
    _atomic_write(_niche_json_path(nid), cfg_data)


def cfg(path: str, default=None):
    """Dotted-path getter on the active niche's config.

    Example: cfg("thresholds.MIN_SOLD", 300)
    Never raises — any problem (missing niche, missing key, wrong type,
    corrupt json) returns `default`.
    """
    try:
        data = load()
        node = data
        for part in path.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node
    except Exception:
        return default


def _deep_merge(base: dict, partial: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in partial.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def update(partial: dict, nid: str | None = None) -> dict:
    """Deep-merge `partial` into the niche config and save. Returns new cfg."""
    nid = nid or active_id()
    if not nid:
        raise ValueError("no active niche and no nid given")
    current = load(nid)
    merged = _deep_merge(current, partial)
    save(merged, nid)
    return merged


def list_niches() -> list[str]:
    """List niche ids that have a niche.json."""
    d = _niches_dir()
    if not d.exists():
        return []
    out = []
    for child in sorted(d.iterdir()):
        if child.is_dir() and (child / "niche.json").exists():
            out.append(child.name)
    return out


def set_active(nid: str) -> None:
    if not _niche_json_path(nid).exists():
        raise ValueError(f"niche '{nid}' does not exist")
    f = _active_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(nid + "\n", encoding="utf-8")


def clone(src: str, dst: str, name: str) -> dict:
    """Copy niches/src -> niches/dst, blank out vertical-specific search
    data, keep hub account shells but clear login values. Raises if dst
    already exists.
    """
    src_dir = _niches_dir() / src
    dst_dir = _niches_dir() / dst
    if not src_dir.exists():
        raise ValueError(f"source niche '{src}' does not exist")
    if dst_dir.exists():
        raise ValueError(f"destination niche '{dst}' already exists")

    src_cfg = load(src)
    new_cfg = copy.deepcopy(src_cfg)
    new_cfg.setdefault("identity", {})
    new_cfg["identity"]["id"] = dst
    new_cfg["identity"]["name"] = name
    new_cfg.setdefault("sourcing", {})
    new_cfg["sourcing"]["aliexpress_searches"] = []
    new_cfg["sourcing"]["shops"] = []
    new_cfg.setdefault("research", {})
    new_cfg["research"]["trend_queries"] = []

    dst_dir.mkdir(parents=True, exist_ok=False)
    _atomic_write(_niche_json_path(dst), new_cfg)

    # hub: copy accounts shell, blank login values
    src_hub_path = _hub_json_path(src)
    new_hub = {"accounts": [], "links": []}
    if src_hub_path.exists():
        try:
            src_hub = json.loads(src_hub_path.read_text(encoding="utf-8"))
        except Exception:
            src_hub = {"accounts": [], "links": []}
        accounts = []
        for acc in src_hub.get("accounts", []):
            acc2 = copy.deepcopy(acc)
            acc2["login"] = ""
            accounts.append(acc2)
        new_hub = {"accounts": accounts, "links": []}
    _atomic_write(_hub_json_path(dst), new_hub)

    return new_cfg


def _cli(argv: list[str]) -> int:
    if not argv:
        print("usage: python -m control.niche <clone|list|use> ...")
        return 1
    cmd = argv[0]
    if cmd == "clone":
        if len(argv) < 4:
            print("usage: python -m control.niche clone <src> <dst> <name>")
            return 1
        src, dst, name = argv[1], argv[2], argv[3]
        clone(src, dst, name)
        print(f"cloned '{src}' -> '{dst}' ({name})")
        return 0
    if cmd == "list":
        for nid in list_niches():
            marker = "*" if nid == active_id() else " "
            print(f"{marker} {nid}")
        return 0
    if cmd == "use":
        if len(argv) < 2:
            print("usage: python -m control.niche use <id>")
            return 1
        set_active(argv[1])
        print(f"active niche -> {argv[1]}")
        return 0
    print(f"unknown command: {cmd}")
    return 1


if __name__ == "__main__":
    sys.exit(_cli(sys.argv[1:]))
