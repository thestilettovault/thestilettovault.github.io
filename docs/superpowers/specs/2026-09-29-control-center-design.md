# Control Center — Design (2026-09-29)

## Goal
One local place for Ofer to see and control the whole affiliate engine (sales, clicks,
posts, products, affiliate programs, accounts/keys, research, tuning), and a niche
config layer so the same engine can be switched/cloned to another product vertical.

## Decisions (approved in chat)
- Local Flask app on `127.0.0.1:8787` now; phone access (Tailscale) later — no code change.
- Secrets: single source `scripts/.env` (git-ignored). UI shows masked + copy/reveal.
  No account passwords stored anywhere in the hub — only email/login URL/purpose.
- Telegram bot stays; dashboard adds control, doesn't replace it.
- The public GitHub Pages dashboard is retired after migration (or reduced to totals).

## Architecture
```
control/
  app.py        Flask app, routes, single-instance lock, per-start CSRF token
  niche.py      niche config load/save/clone (niches/<id>/niche.json, niches/active.txt)
  hub.py        accounts + links (niches/<id>/hub.json) + masked keys from scripts/.env
  services.py   thin wrappers over existing scripts (metrics, products, zernio, registry, trends)
  learning.py   performance-by-attribute + weekly summary text
  static/       index.html, app.js, style.css  (vanilla JS, Hebrew RTL, dark)
niches/
  active.txt            "stiletto"
  stiletto/niche.json   search terms, thresholds, slots, trend queries, filters
  stiletto/hub.json     accounts, important links
start_control.bat       starts the app (pythonw) and opens the browser
```
Existing scripts stay the executors; services.py imports them. Scripts read niche.json
through `control.niche.cfg()` with fallback to their current constants (no behavior change
when the key is missing).

## Screens
1. **Overview** — KPI cards (sales/revenue, clicks today/7d, posts scheduled/published/failed,
   conversion); "Needs you now" (awaiting ad choice, open signup cards, failed posts, stale jobs)
   with action buttons; system health (bot alive, last run of each task/log, Magnific balance n/a ok).
2. **Products** — table of catalog + production state + clicks/sales; approve/reject; add by URL;
   finalize+schedule a chosen shoe to a date.
3. **Schedule** — Zernio posts grouped by day/platform, status + live URL; move (PUT
   scheduledFor), cancel (DELETE), retry failed (tiktok_retry).
4. **Affiliates & Hub** — registry table (value/sale, status, signup link) with Activate
   (paste link) and Add brand (probe); accounts list; masked keys with copy/reveal; links.
5. **Research** — trend log with affiliate status; "what worked" table by attribute;
   weekly summary.
6. **Tuning** — edit niche.json fields; "Run now" for heel hunter (manual note only — it
   needs Claude), morning scout (dry/real), collect metrics, tiktok retry.

## API (JSON, all mutating routes require header `X-Token: <per-start token>`)
GET  /api/overview, /api/products, /api/posts, /api/registry, /api/hub, /api/trends,
     /api/learning, /api/niche, /api/health
POST /api/products/approve {url,title,image_url,domain,commission} | /reject {url,title}
POST /api/products/add {url}
POST /api/posts/move {id, scheduledFor} | /cancel {id} | /retry
POST /api/registry/add {domain} | /activate {domain, link}
POST /api/keys/reveal {name}
PUT  /api/niche {…partial…}
POST /api/run/{scout_dry|scout|metrics|tiktok_retry}
POST /api/niche/clone {from, to, name}

## Security
- Bind 127.0.0.1 only. Per-start random token injected into index.html; required on every
  POST/PUT (blocks CSRF from other sites the browser visits). Reveal endpoint also checks
  Host header is localhost.
- Scrub plaintext secrets from `CONTEXT_FOR_NEXT_SESSION.md` → pointers to `scripts/.env`.

## Learning
Join catalog/production entries with Admitad clicks-per-subid + sales and Zernio post
status. Attributes: price band (<$20, 20–50, 50–100, 100+), domain/program, discount band,
has_video, weekday/hour. Output: rows {attribute, value, shoes, clicks, clicks_per_shoe,
sales}. Weekly summary = top/bottom 2 per attribute as Hebrew sentences (no LLM needed).

## Niche switching / cloning
`niche.json` holds everything vertical-specific. `clone(from,to,name)` copies config and
hub accounts shell, blanks search terms/sources, sets active niche optional. Data files
stay per-project for now (one engine = one repo); full multi-tenant data is out of scope.

## Testing
pytest for niche/hub/services/learning with monkeypatched IO; Flask test client for routes
+ token guard. Manual browser check of each screen.

## Out of scope
Phone access, multi-user auth, automated affiliate signup (never), trend forecasting.
