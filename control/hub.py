"""Accounts/links hub + masked .env key listing.

Never prints or returns raw secret values except through `reveal()`, which
is meant to be gated behind an explicit user action in the app layer.
"""
from __future__ import annotations

import datetime
import json
import os
import re
from pathlib import Path

from . import niche as _niche

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / "scripts" / ".env"

_LINE_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$")


def mask(v: str) -> str:
    """Mask a secret: first 4 + '...' + last 3. Short values (<8 chars) -> '***'."""
    if v is None:
        return ""
    if len(v) < 8:
        return "•••"
    return f"{v[:4]}…{v[-3:]}"


def _parse_env() -> dict[str, str]:
    """Parse ENV_PATH into {name: value}. Never raises; missing file -> {}."""
    path = ENV_PATH
    out: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return out
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = _LINE_RE.match(line)
        if not m:
            continue
        name, value = m.group(1), m.group(2)
        # strip surrounding quotes if present
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        out[name] = value
    return out


def keys() -> list[dict]:
    """List env keys with masked values, set flag, and file mtime (never raw values)."""
    values = _parse_env()
    try:
        mtime = datetime.datetime.fromtimestamp(
            ENV_PATH.stat().st_mtime, tz=datetime.timezone.utc
        ).isoformat()
    except Exception:
        mtime = None
    out = []
    for name, value in values.items():
        out.append(
            {
                "name": name,
                "masked": mask(value) if value else "",
                "set": bool(value),
                "updated": mtime,
            }
        )
    return out


def reveal(name: str) -> str | None:
    """Return the raw value for `name`, or None if not set/found."""
    values = _parse_env()
    return values.get(name)


def _hub_path(nid: str) -> Path:
    return ROOT / "niches" / nid / "hub.json"


def load_hub(nid: str | None = None) -> dict:
    nid = nid or _niche.active_id()
    if not nid:
        return {"accounts": [], "links": []}
    try:
        return json.loads(_hub_path(nid).read_text(encoding="utf-8"))
    except Exception:
        return {"accounts": [], "links": []}


def save_hub(data: dict, nid: str | None = None) -> None:
    nid = nid or _niche.active_id()
    if not nid:
        raise ValueError("no active niche and no nid given")
    path = _hub_path(nid)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def accounts(nid: str | None = None) -> list[dict]:
    return load_hub(nid).get("accounts", [])


def links(nid: str | None = None) -> list[dict]:
    return load_hub(nid).get("links", [])
