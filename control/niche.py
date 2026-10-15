"""Niche config: load/save/clone the active niche's niche.json.

Scripts read tuning values through `cfg(path, default)`, which NEVER raises —
any error (missing file, missing key, bad JSON) just falls back to `default`,
so existing scripts keep working unmodified when niche config is absent.
"""
from __future__ import annotations

import copy
import json
import re
import shutil
import sys
from pathlib import Path

from .atomic import write_json

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,31}$")


def validate_id(nid) -> str:
    """Niche ids become path segments — only [a-z0-9][a-z0-9_-]{1,31} allowed."""
    if not isinstance(nid, str) or not _ID_RE.fullmatch(nid):
        raise ValueError(f"invalid niche id: {nid!r}")
    return nid

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
    return _niches_dir() / validate_id(nid) / "niche.json"


def _hub_json_path(nid: str) -> Path:
    return _niches_dir() / validate_id(nid) / "hub.json"


_CACHE: dict = {}   # path -> (signature, parsed dict)


def _read_cached(path: Path) -> dict:
    """Parse a niche.json, re-reading only when its mtime/size changes."""
    key = str(path)
    st = path.stat()
    sig = (st.st_mtime_ns, st.st_size)
    hit = _CACHE.get(key)
    if hit and hit[0] == sig:
        return hit[1]
    data = json.loads(path.read_text(encoding="utf-8"))
    _CACHE[key] = (sig, data)
    return data


def load(nid: str | None = None) -> dict:
    """Load a niche's niche.json as a dict. Returns {} on any failure.
    Reads are cached per file and invalidated when the file's mtime changes;
    callers always get their own deep copy."""
    nid = nid or active_id()
    if not nid:
        return {}
    try:
        path = _niche_json_path(nid)  # invalid id -> ValueError -> {}
        return copy.deepcopy(_read_cached(path))
    except Exception:
        return {}


def _atomic_write(path: Path, data: dict) -> None:
    write_json(path, data)


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
        nid = active_id()
        if not nid:
            return default
        node = _read_cached(_niche_json_path(nid))
        for part in path.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return copy.deepcopy(node)
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
        if child.is_dir() and not child.name.startswith("_") and (child / "niche.json").exists():
            out.append(child.name)
    return out


def set_active(nid: str) -> None:
    if not _niche_json_path(nid).exists():
        raise ValueError(f"niche '{nid}' does not exist")
    f = _active_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(nid + "\n", encoding="utf-8")


TEMPLATE_ID = "_template"
_BLANK_HUB = {"accounts": [], "links": []}


def _env_names(env_path: Path | None = None) -> set:
    """NAMES defined in scripts/.env (never the values)."""
    p = env_path or (ROOT / "scripts" / ".env")
    names = set()
    try:
        for line in p.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k = line.split("=", 1)[0].strip()
                if k.startswith("export "):
                    k = k[7:].strip()
                names.add(k)
    except Exception:
        pass
    return names


def _blank_for_clone(c: dict, dst: str, name: str) -> dict:
    """Keep the structure + generic rules, blank everything vertical-specific."""
    c = copy.deepcopy(c)
    up = dst.upper().replace("-", "_")
    ident = c.setdefault("identity", {})
    ident.update({"id": dst, "name": name, "product_noun": "", "product_noun_plural": "",
                  "handle": "", "site": ""})
    c.setdefault("sourcing", {}).update({"aliexpress_searches": [], "shops": []})
    c.setdefault("research", {})["trend_queries"] = []
    site = c.setdefault("site", {})
    for k in ("public_url", "assets_base_url", "pages_repo", "pages_dir"):
        site[k] = ""
    pub = c.setdefault("publishing", {})
    pub["hashtags"] = []
    env = pub.setdefault("env", {})
    env["tiktok_id"] = f"ZERNIO_{up}_TIKTOK_ID"
    env["instagram_id"] = f"ZERNIO_{up}_INSTAGRAM_ID"
    prod = c.setdefault("production", {})
    prod["space_id"] = ""
    prod["space_label"] = ""
    prod["nodes"] = {k: "" for k in (prod.get("nodes") or {})}
    prod["agents_dir"] = f"niches/{dst}/agents"
    pin = c.setdefault("pinterest", {})
    pin.update({"board": "", "title_openers": [], "hashtags": "", "keywords": ""})
    comp = c.setdefault("compliance", {})
    comp["custom_domain"] = ""
    return c


CLONE_CHECKLIST = """\
Next steps for niche '{dst}':
  1. Fill niches/{dst}/niche.json  (identity, site, sourcing, publishing, production, pinterest)
  2. Edit niches/{dst}/agents/*.md  (persona, poses, stylist, qa - every TODO)
  3. Affiliate accounts -> put deeplink bases in scripts/.env
  4. Domain + GitHub Pages repo + compliance pages (about/disclosure/contact/privacy)
  5. Zernio accounts -> add ZERNIO_{up}_TIKTOK_ID / ZERNIO_{up}_INSTAGRAM_ID to scripts/.env
  6. Duplicate the Magnific Space -> production.space_id + production.nodes.*
  7. Telegram bot/chat, scheduled tasks
  8. py -3 -m control.niche check {dst}   (must exit 0)
See docs/TEMPLATE.md."""


def clone(src: str, dst: str, name: str) -> dict:
    """Create niches/dst from niches/src (or from the '_template' skeleton):
    niche.json with identity overwritten and vertical-specific data blanked,
    an agents/ folder copied from niches/_template/agents/ (TODO skeletons),
    an empty data/ folder with a README, and a hub.json with account shells
    (logins cleared). Raises if dst already exists."""
    if src != TEMPLATE_ID:
        validate_id(src)
    validate_id(dst)
    src_dir = _niches_dir() / src
    dst_dir = _niches_dir() / dst
    if not src_dir.exists():
        raise ValueError(f"source niche '{src}' does not exist")
    if dst_dir.exists():
        raise ValueError(f"destination niche '{dst}' already exists")

    try:
        src_cfg = json.loads((src_dir / "niche.json").read_text(encoding="utf-8"))
    except Exception:
        src_cfg = {}
    new_cfg = _blank_for_clone(src_cfg, dst, name)

    dst_dir.mkdir(parents=True, exist_ok=False)
    _atomic_write(_niche_json_path(dst), new_cfg)

    # agents/: TODO skeletons from the template (fallback: the source's agents/)
    tpl_agents = _niches_dir() / TEMPLATE_ID / "agents"
    if not tpl_agents.is_dir():
        tpl_agents = src_dir / "agents"
    agents_dst = dst_dir / "agents"
    if tpl_agents.is_dir():
        shutil.copytree(tpl_agents, agents_dst)
    else:
        agents_dst.mkdir()

    # data/: per-niche state lives here (README explains)
    data_dst = dst_dir / "data"
    data_dst.mkdir()
    (data_dst / "README.md").write_text(
        f"# {name} - niche data\n\nPer-niche state (catalog, queues, metrics) goes here.\n"
        "Today most engine scripts still read the global data/ folder; see docs/TEMPLATE.md "
        "(known limitations).\n", encoding="utf-8")

    # hub: copy accounts shell (names only) with login values cleared
    new_hub = dict(_BLANK_HUB)
    src_hub_path = src_dir / "hub.json"
    if src_hub_path.exists():
        try:
            src_hub = json.loads(src_hub_path.read_text(encoding="utf-8"))
            accounts = []
            for acc in src_hub.get("accounts", []):
                acc2 = copy.deepcopy(acc)
                acc2["login"] = ""
                accounts.append(acc2)
            new_hub = {"accounts": accounts, "links": []}
        except Exception:
            pass
    _atomic_write(_hub_json_path(dst), new_hub)

    return new_cfg


def _get(d: dict, path: str):
    node = d
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def check(nid: str, env_names=None) -> list[str]:
    """Return a list of problems that stop niche `nid` from being launch-ready
    (empty list = ready). `env_names` overrides the names read from scripts/.env
    (tests). Values of env vars are never read or printed."""
    validate_id(nid)
    path = _niche_json_path(nid)
    if not path.exists():
        return [f"niche.json missing for '{nid}'"]
    try:
        c = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        return [f"niche.json is not valid JSON: {e}"]
    problems: list[str] = []

    def need(key):
        v = _get(c, key)
        if v is None or (isinstance(v, (str, list, dict)) and not v):
            problems.append(f"missing: {key}")

    need("identity.name")
    need("identity.product_noun")
    need("site.public_url")
    if not (_get(c, "sourcing.aliexpress_searches") or _get(c, "sourcing.shops")):
        problems.append("missing: sourcing.aliexpress_searches or sourcing.shops (need at least one)")
    need("production.space_id")

    names = _env_names() if env_names is None else set(env_names)
    for k in ("api_key", "tiktok_id", "instagram_id"):
        var = _get(c, f"publishing.env.{k}")
        if not var:
            problems.append(f"missing: publishing.env.{k} (env var name)")
        elif var not in names:
            problems.append(f"env var {var} not found in scripts/.env")

    agents_dir = _get(c, "production.agents_dir")
    if not agents_dir:
        problems.append("missing: production.agents_dir")
    else:
        base = ROOT / agents_dir
        for options in (("persona.md", "ina.md"), ("poses.md",), ("stylist.md",), ("qa.md",)):
            if not any((base / o).is_file() for o in options):
                problems.append(f"agents file missing: {agents_dir}/{options[0]}")

    pages_dir = _get(c, "site.pages_dir")
    pages = _get(c, "compliance.required_pages") or []
    if not pages_dir:
        problems.append("missing: site.pages_dir (folder holding the compliance pages; '.' = repo root)")
    else:
        for pg in pages:
            if not (ROOT / pages_dir / pg).is_file():
                problems.append(f"compliance page missing: {pages_dir}/{pg}")
    return problems


def _cli(argv: list[str]) -> int:
    if not argv:
        print("usage: python -m control.niche <clone|check|list|use> ...")
        return 1
    cmd = argv[0]
    if cmd == "clone":
        if len(argv) < 4:
            print("usage: python -m control.niche clone <src> <dst> <name>")
            return 1
        src, dst, name = argv[1], argv[2], argv[3]
        clone(src, dst, name)
        print(f"cloned '{src}' -> '{dst}' ({name})")
        print(CLONE_CHECKLIST.format(dst=dst, up=dst.upper().replace("-", "_")))
        return 0
    if cmd == "check":
        if len(argv) < 2:
            print("usage: python -m control.niche check <id>")
            return 1
        problems = check(argv[1])
        if problems:
            print(f"niche '{argv[1]}' NOT ready ({len(problems)} problem(s)):")
            for p in problems:
                print(f"  - {p}")
            return 2
        print(f"niche '{argv[1]}' ready: all required fields present")
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
