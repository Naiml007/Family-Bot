# Technical Specification & Refactoring Roadmap — TheSnow Discord Bot

> Target: transform the monolithic `bot.py` (1306 lines) into a modular, high-performance,
> near-zero-idle-cost, well-tested, and security-hardened system.
> This document is the authoritative plan. Each phase is independently shippable.

---

## 1. Current-State Analysis

### 1.1 What exists today
- **One file** (`bot.py`) containing: persistence, helpers, embed builders, persistent
  `discord.ui.View` classes, slash commands, and a background scheduler.
- **Stack:** `discord.py` (app_commands + `tasks.loop`), synchronous `sqlite3`, `python-dotenv`,
  `zoneinfo` (Europe/London).
- **Persistence:** a single SQLite file `family.db` with 11 tables, created/migrated at import time
  (`bot.py:39-76`).
- **Interaction model:** persistent panels with buttons; multi-step input gathered through
  chat-based forms (`chat_form`, `bot.py:260-325`) using `bot.wait_for("message")`.
- **Scheduling:** one `@tasks.loop(seconds=20)` ticker (`bot.py:1275-1301`) that polls the DB for
  due reminders, events, and Cowshed/Plantation alerts.

### 1.2 Architectural pain points (evidence)
| # | Problem | Location |
|---|---------|----------|
| A1 | God module — all concerns in one file | whole file |
| A2 | Global mutable singletons (`db`, `bot`, `tree`, `ACTIVE`, `BUILDERS`, `VIEWS`) | `bot.py:39,227,546,985,1002-1003` |
| A3 | Hidden coupling via globals (`stamp()` reaches global `bot`; `repost_panel` reaches `BUILDERS`/`VIEWS`) | `bot.py:118-123,344-352` |
| A4 | Blocking I/O on the event loop — sync `sqlite3` inside `async` handlers | `bot.py:78-81` + every handler |
| A5 | Fixed 20 s polling loop — never idle | `bot.py:1275` |
| A6 | N+1 queries in embed builders | `seed_qty` per seed `bot.py:399-418`; `cfg_get` twice per key `bot.py:134` |
| A7 | No DB indexes on hot columns (`guild_id`, `next_run`, `start_ts`, `ack`) | schema `bot.py:41-64` |
| A8 | Fragile migration via `try/except ALTER TABLE` | `bot.py:65-76` |
| A9 | Non-atomic multi-statement writes (armory vest + weapon) | `bot.py:734-742` |
| A10 | Errors swallowed with `print` only | `bot.py:1297-1298` |
| A11 | No logging, no tests, no CI | — |
| A12 | Missing authorization on money actions (deposit/withdraw buttons) | `BalanceView` `bot.py:562-596` |
| A13 | User-supplied URLs rendered as embed images (tracking-pixel / SSRF-adjacent) | `bot.py:232-239,861-862` |
| A14 | `default_permissions` is only a client hint; no server-side enforcement | `bot.py:1012,1029,1037` |
| A15 | Token read with `os.environ[...]` → hard crash, no validation | `bot.py:1306` |

---

## 2. Target Architecture (Modularity & Scalability)

### 2.1 Package layout
Replace `bot.py` with an installable package. Each feature is a self-contained module that
registers itself; no module imports another feature module.

```
TheSnow/
├── pyproject.toml                # deps, entry point, tool config (ruff/mypy/pytest)
├── .env.example                  # documented env vars (no secrets)
├── README.md
├── thesnow/
│   ├── __init__.py
│   ├── main.py                   # composition root: build config, db, bot, extensions
│   ├── config.py                 # typed settings loaded once (pydantic-settings)
│   ├── core/
│   │   ├── database.py           # async DB facade + connection pool + migrations
│   │   ├── migrations.py         # versioned, forward-only schema migrations
│   │   ├── scheduler.py          # event-driven scheduler (replaces 20s loop)
│   │   ├── forms.py              # chat-form engine (state machine, no globals)
│   │   ├── permissions.py        # single source of truth for authorization
│   │   ├── embeds.py             # embed builders (pure functions, injected deps)
│   │   ├── logging.py            # structured logging config
│   │   └── errors.py             # Oops + global error handler
│   ├── features/
│   │   ├── balance/              # __init__.py (extension), views.py, service.py, embeds.py
│   │   ├── seeds/
│   │   ├── solar/
│   │   ├── armory/
│   │   ├── storage/
│   │   ├── finance/
│   │   ├── bonus/                # tickets + bonus log
│   │   ├── schedule/             # cowshed + plantation timers
│   │   ├── reminders/            # custom + diplomacy
│   │   └── events/
│   └── shared/
│       ├── pagination.py  time.py  validation.py  ratelimit.py
└── tests/
    ├── unit/            # pure logic: parsers, time math, embed builders, permissions
    ├── integration/     # service + DB with a temp sqlite
    └── bot/             # discord.py interactions via mocked gateway
```

### 2.2 Dependency & extension model
- `main.py` is the **only** file that wires concrete implementations together (composition root).
- Each feature exposes an `async def setup(bot)` (a discord.py **extension**) that registers its
  commands, views, and scheduler jobs. Features are loaded from a list in config → adding/removing a
  feature is a one-line change.
- Shared services (DB, scheduler, permissions) are passed **explicitly** into builders/views via
  constructors or a small `AppContext` dataclass — no module-global `bot`/`db`.
- `BUILDERS`/`VIEWS` registries (`bot.py:546,985`) become a per-feature `panel.py` that returns
  `(embed_builder, view_factory)`; the setup command looks them up from a registry keyed by feature.

### 2.3 Scalability
- Per-guild state is already keyed by `guild_id`; keep that. The async DB facade allows a single
  process to serve many guilds without blocking.
- If growth demands it, the scheduler and DB are the only scale-sensitive pieces: the scheduler can
  move to per-shard tasks, and the DB facade can swap SQLite → Postgres behind the same interface
  (parameterized SQL already used everywhere, so the surface is small).

---

## 3. Performance Optimization

### 3.1 Eliminate event-loop blocking (highest impact)
- Replace the synchronous `sqlite3` connection with **async access**:
  - Preferred: `aiosqlite` behind a thin `Database` facade exposing `execute/fetchone/fetchall`
    that current `run/one/many` (`bot.py:78-81`) already mirror — minimal call-site churn.
  - Each operation runs in the DB thread; the event loop stays free.
- Wrap all Discord I/O that can fail in bounded retries with exponential backoff + jitter
  (HTTP 429/5xx), instead of ad-hoc `try/except discord.HTTPException`.

### 3.2 Query & schema optimization
- Add indexes:
  ```sql
  CREATE INDEX IF NOT EXISTS ix_reminders_due   ON reminders(next_run);
  CREATE INDEX IF NOT EXISTS ix_events_pending  ON events(start_sent, start_ts);
  CREATE INDEX IF NOT EXISTS ix_balance_guild   ON balance_log(guild_id, id DESC);
  CREATE INDEX IF NOT EXISTS ix_alerts_ack      ON active_alerts(guild_id, ack);
  CREATE INDEX IF NOT EXISTS ix_solar_guild_ts  ON solar_log(guild_id, ts);
  ```
- Enable **WAL** mode + `synchronous=NORMAL` + a bounded connection pool (`PRAGMA journal_mode=WAL`).
- Remove N+1:
  - `e_seeds` (`bot.py:402-418`): one `SELECT seed FROM seeds WHERE guild_id=?` then map in memory
    instead of 6 `seed_qty` calls.
  - `allowed()` (`bot.py:132-137`): read each `cfg_get` **once** (currently twice per key).
- Cache per-guild config in memory with write-through invalidation in `cfg_set`, so hot permission
  and channel lookups avoid a DB round-trip.

### 3.3 Hot-path latency
- Persistent views already use `custom_id` + `timeout=None` (good) — keep.
- Defer non-critical work: log embeds and panel reposts should be enqueued and flushed asynchronously
  so the user-facing interaction returns first (`publish`, `bot.py:354-356`).
- Build embeds from cached aggregates where staleness is acceptable; otherwise keep single-query
  aggregate SQL (already used in `bal_stats`/`e_solar`).

---

## 4. Resource Efficiency (idle ≈ 0)

### 4.1 Replace fixed polling with an event-driven scheduler
- The `seconds=20` loop (`bot.py:1275`) wakes 4,320×/day per process regardless of work. Replace with
  a **single computed next-deadline** scheduler:
  - On startup and after every mutation, compute `next = min(next_run, start_ts - remind_min,
    next_cow_ts, next_plant_ts)`.
  - Sleep until `next` (plus small jitter), fire due jobs, recompute. Idle cost → one sleeping task.
  - Use `asyncio.Event` to wake early when a new reminder/event is inserted.
- Keep the existing 20 s loop only as an optional safety net (configurable, default off).

### 4.2 Avoid redundant work
- `process_uk_schedules` (`bot.py:1202-1273`) scans all enabled guilds every tick; with the
  event-driven scheduler it runs only when a slot boundary is near.
- Re-ping logic (5-min) becomes its own scheduled wakeup per active alert instead of a full scan.
- Cache embeds per `(guild, feature)` and only rebuild on mutation (panels are static between events).

### 4.3 Footprint
- One process, one DB pool, one scheduler task. No busy loops, no per-tick full-table scans.
- Target steady state: event loop idle, sleeping until next deadline; CPU ≈ 0, RAM flat.

---

## 5. Reliability & Debugging (near-zero bug density)

### 5.1 Structure for testability
- Pure logic (time math `next_cow_ts`/`next_plant_ts`, `num`, `parse_answer`, `bar`, embed builders,
  permission decisions) lives in `shared/` and `core/` with **no Discord/DB dependencies** → unit
  tested directly.
- Services take an injected DB interface → integration tested against a temp SQLite file.
- Discord interactions tested with a mocked gateway/`Interaction`.

### 5.2 Testing methodology
- **Unit** (pytest): parsers, UK time/DST boundaries, loan/balance math, permission matrix.
- **Integration**: each feature service against a real temp DB; migrations run from empty → latest.
- **Bot**: simulate button/slash interactions; assert embeds, DB writes, and permission denials.
- **Property-based** (hypothesis) for `num`/`parse_answer`/scheduling math.
- **Coverage gate** (e.g. ≥ 90% on `core/` and `shared/`) in CI.
- **CI**: ruff (lint) + mypy (types) + pytest on every push.

### 5.3 Defensive runtime
- Replace `print` (`bot.py:1297-1298,1304`) with structured logging (`structlog`/stdlib) with levels
  and guild/user context.
- Global error handler on the tree + `on_error` for views: log full traceback, reply with a generic
  user message (no internal leakage).
- Wrap multi-statement writes in **transactions** (armory vest+weapon `bot.py:734-742`, storage upsert)
  so partial failures roll back.
- Replace `try/except ALTER` migrations (`bot.py:65-76`) with a `schema_version` table and ordered,
  idempotent migration functions.
- Bounded retries + circuit breaker around Discord calls; never let a single failed send kill the
  scheduler (isolate per-job try/except with logging).

---

## 6. Security Hardening

### 6.1 Findings & fixes
| ID | Finding | Fix |
|----|---------|-----|
| S1 | Money buttons (deposit/withdraw) have **no** permission check | Route every state-changing action through `permissions.authorize(i, action)`; default-deny. |
| S2 | `default_permissions` is only a hint (`bot.py:1012,1029,1037`) | Re-check `administrator`/role in code for every admin command (pattern already in `allowed`). |
| S3 | Arbitrary user URL rendered as embed image (`bot.py:232-239,861`) | Allow-list image hosts or proxy through a safe fetcher; reject non-allow-listed hosts; strip tracking params. |
| S4 | Token via `os.environ[...]` crash; no validation | Load via `config.py`; fail fast with a clear message; never log token; add `.env.example`. |
| S5 | No rate limiting on forms/tickets/channel creation | Add per-user cooldown (e.g. token bucket in `shared/ratelimit.py`) on ticket creation and form starts. |
| S6 | Ticket channel creation can be abused | Enforce max open tickets per user (already dedup by topic) + global cap + cooldown. |
| S7 | Reaction ack (`on_raw_reaction_add`) trusts any reactor | Confirm intended; if restricted, verify reactor role against `mod_role`/`deputy_role`. |
| S8 | `@everyone`/role mass pings | Keep `AllowedMentions(roles=True)` scoped to the configured role only (already) — add guild-level opt-out. |
| S9 | No guild allowlist | Optional `ALLOWED_GUILD_IDS` to refuse operating in unknown guilds. |
| S10 | SQL injection | **Already safe** — all queries parameterized; keep it a rule in review. |

### 6.2 Cross-cutting
- Principle of least privilege: one Discord bot token, scoped perms; DB file readable only by the
  service account.
- Log security-relevant events (permission denials, ticket creation, withdrawals) with actor + guild.
- Redact secrets/tokens/PII in logs; never echo raw user input into errors.
- Dependency hygiene: pin versions in `pyproject.toml`, run `pip-audit` in CI.

---

## 7. Phased Roadmap

1. **Phase 0 — Safety net (no behavior change).** Add `pyproject.toml`, ruff/mypy/pytest, structured
   logging, `.env.example`, global error handler. Fix S1/S2 (authorization) and S4 (config).
2. **Phase 1 — Core extraction.** Build `core/` (database async facade + pool + WAL + indexes,
   migrations, permissions, forms, embeds, scheduler, errors). Migrate helpers off globals.
3. **Phase 2 — Feature modules.** Move each feature into `features/*` as extensions with
   `panel.py`/`service.py`/`views.py`. Wire via composition root. Delete `BUILDERS`/`VIEWS` globals.
4. **Phase 3 — Performance.** Async DB everywhere, remove N+1, config cache, async publish queue,
   retry/backoff on Discord calls.
5. **Phase 4 — Resource efficiency.** Replace 20 s loop with event-driven scheduler; per-alert re-ping
   wakeups; embed caching.
6. **Phase 5 — Hardening & tests.** Close S3/S5/S6/S7/S9; reach coverage gate; add property tests;
   `pip-audit` in CI.

Each phase ends green (lint + types + tests) and is independently deployable.

---

## 8. Acceptance Criteria
- No module-global `bot`/`db`/`ACTIVE`; wiring only in `main.py`.
- Event loop never blocks on I/O; DB access is async.
- Idle CPU ≈ 0 (no fixed-interval polling loop in steady state).
- All state-changing actions pass `permissions.authorize`; admin commands enforced server-side.
- Migrations are versioned and run from empty → latest in CI.
- Coverage ≥ 90% on `core/` + `shared/`; ruff + mypy + pytest green in CI.
- No secrets in repo; `.env.example` documents all config.

---

*Skipped: concrete code for each module (this is the spec/roadmap, not the implementation), and a
Postgres migration (noted as a future option behind the DB facade, not required now). Risk: the
chat-form → async-DB and scheduler rewrites are the highest-risk steps; land them behind the Phase 0
safety net and feature-by-feature to keep each step reversible.*